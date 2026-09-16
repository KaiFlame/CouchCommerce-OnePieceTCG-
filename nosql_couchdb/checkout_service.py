"""Checkout consistente sobre a concorrência otimista do CouchDB."""
import hashlib
import json
import logging
import time
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from card_catalog import now
from database import DatabaseError

log = logging.getLogger(__name__)
MAX_RETRIES = 3


class CheckoutError(ValueError):
    pass


def _money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0:
            raise CheckoutError("Preço inválido ou indisponível.")
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise CheckoutError("Preço inválido ou indisponível.") from None


def _cart_hash(cart):
    return hashlib.sha256(json.dumps(cart, sort_keys=True).encode()).hexdigest()


def _order_id(client_id, token):
    try:
        key = str(uuid.UUID(token))
    except (ValueError, TypeError, AttributeError):
        raise CheckoutError("O formulário expirou. Revise o pedido novamente.") from None
    return "pedido:" + str(uuid.uuid5(uuid.NAMESPACE_URL, client_id + ":" + key))


def validate_cart(cart):
    if not isinstance(cart, dict) or not 1 <= len(cart) <= 30:
        raise CheckoutError("Carrinho inválido.")
    for product_id, quantity in cart.items():
        if not isinstance(product_id, str) or not product_id.startswith("produto:") or len(product_id) > 180:
            raise CheckoutError("Produto inválido no carrinho.")
        if type(quantity) is not int or not 1 <= quantity <= 99:
            raise CheckoutError("Quantidade inválida no carrinho.")


def _items(store, cart):
    items = []
    for product_id, quantity in sorted(cart.items()):
        product = store.get(product_id)
        if not product or product.get("tipo") != "produto" or not product.get("ativo"):
            raise CheckoutError("Uma carta não está disponível.")
        if type(product.get("estoque")) is not int or product["estoque"] < quantity:
            raise CheckoutError("Estoque insuficiente para " + (product.get("nome") or product_id))
        price = _money(product.get("preco"))
        items.append({"produto_id": product_id, "carta_api_id": product["carta_api_id"],
                      "variante_api_id": product.get("variante_api_id", product_id),
                      "nome": product.get("nome") or product["carta_api_id"],
                      "imagem": product.get("imagem", ""), "quantidade": quantity,
                      "preco_unitario": float(price), "subtotal": float(price * quantity)})
    return items


def _save_status(store, order_id, status, reason=None):
    for attempt in range(MAX_RETRIES):
        order = store.get(order_id)
        if order["status"] in ("CONFIRMADO", "CANCELADO"):
            return order
        order.update(status=status, atualizado_em=now())
        if reason:
            order["motivo"] = str(reason)[:200]
        try:
            store.save(order)
            return order
        except DatabaseError as error:
            if error.status not in (409, 503) or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _reserve(store, order, item):
    for attempt in range(MAX_RETRIES):
        product = store.get(item["produto_id"])
        if not product:
            raise CheckoutError("Carta removida durante o checkout.")
        reservations = product.setdefault("reservas_checkout", {})
        if order["_id"] in reservations:
            return
        if (not product.get("ativo") or type(product.get("estoque")) is not int
                or product["estoque"] < item["quantidade"]):
            raise CheckoutError("Estoque insuficiente durante o checkout.")
        if _money(product.get("preco")) != _money(item["preco_unitario"]):
            raise CheckoutError("O preço mudou. Confira o carrinho novamente.")
        product["estoque"] -= item["quantidade"]
        reservations[order["_id"]] = item["quantidade"]
        product["atualizado_em"] = now()
        try:
            store.save(product)
            return
        except DatabaseError as error:
            if error.status not in (409, 503) or attempt == MAX_RETRIES - 1:
                raise
            log.warning("checkout_conflict order=%s product=%s attempt=%s",
                        order["_id"], product["_id"], attempt + 1)
            time.sleep(0.05 * (attempt + 1))


def _release(store, order, refund):
    for item in order["itens"]:
        for attempt in range(MAX_RETRIES):
            product = store.get(item["produto_id"])
            if not product:
                raise DatabaseError(503, "Produto ausente na compensação")
            quantity = product.get("reservas_checkout", {}).pop(order["_id"], None)
            if quantity is None:
                break
            if refund:
                product["estoque"] += quantity
            product["atualizado_em"] = now()
            try:
                store.save(product)
                break
            except DatabaseError as error:
                if error.status not in (409, 503) or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))


def compensate(store, order, reason="Falha intermediária"):
    current = store.get(order["_id"])
    if current["status"] == "CONFIRMADO":
        _release(store, current, refund=False)
        return current
    if current["status"] == "CANCELADO":
        return current
    current = _save_status(store, current["_id"], "COMPENSANDO", reason)
    try:
        _release(store, current, refund=True)
        return _save_status(store, current["_id"], "CANCELADO", reason)
    except DatabaseError:
        log.error("checkout_compensation_pending order=%s", current["_id"])
        return _save_status(store, current["_id"], "COMPENSACAO_PENDENTE", reason)


def place_order(store, client_id, cart, delivery, token):
    """Cria um pedido idempotente e nunca deixa estoque negativo."""
    validate_cart(cart)
    identifier = _order_id(client_id, token)
    expected_hash = _cart_hash(cart)
    order = store.get(identifier)
    if order:
        if order.get("carrinho_hash") != expected_hash:
            raise CheckoutError("A confirmação já foi usada com outro carrinho.")
        if order["status"] == "CONFIRMADO":
            return order
        if order["status"] in ("CANCELADO", "COMPENSACAO_PENDENTE", "COMPENSANDO"):
            raise CheckoutError("O pedido anterior foi cancelado. Revise o carrinho.")
    else:
        items = _items(store, cart)
        order = {"_id": identifier, "tipo": "pedido", "cliente_id": client_id,
                 "status": "PROCESSANDO", "itens": items, "entrega": delivery,
                 "total": float(sum(Decimal(str(item["subtotal"])) for item in items)),
                 "carrinho_hash": expected_hash, "schema_version": 2,
                 "criado_em": now(), "atualizado_em": now()}
        try:
            store.save(order)
        except DatabaseError as error:
            if error.status != 409:
                raise
            order = store.get(identifier)
            if not order or order.get("carrinho_hash") != expected_hash:
                raise CheckoutError("Conflito ao criar o pedido.") from None
    try:
        for item in order["itens"]:
            _reserve(store, order, item)
        order = _save_status(store, identifier, "CONFIRMADO")
    except (CheckoutError, DatabaseError) as error:
        order = compensate(store, order, error)
        if order["status"] != "CONFIRMADO":
            raise CheckoutError("Checkout cancelado; qualquer baixa parcial foi compensada.") from error
    try:
        _release(store, order, refund=False)
    except DatabaseError:
        log.warning("checkout_cleanup_pending order=%s", identifier)
    log.info("checkout_finished order=%s status=%s", identifier, order["status"])
    return order


def recover_pending(store):
    recovered = []
    for status in ("PROCESSANDO", "COMPENSANDO", "COMPENSACAO_PENDENTE"):
        for order in store.find({"tipo": "pedido", "status": status}, limit=100):
            recovered.append(compensate(store, order, "Recuperação administrativa"))
    return recovered
