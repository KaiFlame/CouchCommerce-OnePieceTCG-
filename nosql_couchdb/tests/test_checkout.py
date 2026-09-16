from copy import deepcopy

import pytest
import app as shop
from checkout_service import CheckoutError, place_order
from database import DatabaseError
from werkzeug.security import generate_password_hash


class MemoryStore:
    """CouchDB mínimo para verificar revisões, conflito e compensação."""
    def __init__(self, *docs):
        self.docs = {doc["_id"]: deepcopy(doc) for doc in docs}
        self.failures = {}

    def get(self, doc_id):
        return deepcopy(self.docs.get(doc_id))

    def save(self, doc):
        if self.failures.get(doc["_id"], 0):
            self.failures[doc["_id"]] -= 1
            raise DatabaseError(503)
        current = self.docs.get(doc["_id"])
        if current and doc.get("_rev") != current.get("_rev"):
            raise DatabaseError(409)
        if not current and doc.get("_rev"):
            raise DatabaseError(409)
        revision = str(int((current or {}).get("_rev", "0-x").split("-")[0]) + 1) + "-x"
        saved = deepcopy(doc)
        saved["_rev"] = revision
        self.docs[doc["_id"]] = saved
        doc["_rev"] = revision
        return {"ok": True, "id": doc["_id"], "rev": revision}

    def find(self, selector, fields=None, limit=100):
        matches = [deepcopy(doc) for doc in self.docs.values()
                   if all(doc.get(key) == value for key, value in selector.items())]
        return matches[:limit]


@pytest.fixture
def checkout_env(monkeypatch):
    shop.app.config.update(TESTING=True, SECRET_KEY="test-only")
    product = {"_id": "produto:x", "_rev": "1-x", "tipo": "produto",
               "carta_api_id": "X", "nome": "Carta teste", "estoque": 100,
               "preco": 10.0, "ativo": True}
    customer = {"_id": "cliente:test", "_rev": "1-x", "tipo": "cliente",
                "nome": "Pessoa Teste", "email": "teste@example.test",
                "senha_hash": generate_password_hash("test-password")}
    store = MemoryStore(product, customer)
    monkeypatch.setattr(shop, "db", store)
    client = shop.app.test_client()
    with client.session_transaction() as session:
        session["carrinho"] = {"produto:x": 2}
    return client, store


def sign_in(client):
    with client.session_transaction() as session:
        session["cliente_id"] = "cliente:test"
        session["cliente_nome"] = "Pessoa Teste"
    assert client.get("/checkout").status_code == 200
    with client.session_transaction() as session:
        return session["checkout_token"]


def address(token):
    return dict(csrf_token=token, nome="Pessoa Teste", cep="13000-000",
                logradouro="Rua de Teste", numero="100", complemento="",
                bairro="Centro", cidade="Campinas", uf="SP")


def test_guest_cannot_checkout_and_login_returns_to_delivery(checkout_env):
    client, store = checkout_env
    assert client.get("/checkout").location.endswith("/login")
    client.get("/login")
    with client.session_transaction() as session:
        csrf = session["form_csrf_token"]
    response = client.post("/login", data={"csrf_token": csrf,
                           "email": "teste@example.test", "senha": "test-password"})
    assert response.location.endswith("/checkout")
    assert not [doc for doc in store.docs.values() if doc.get("tipo") == "pedido"]


@pytest.mark.parametrize("field,value", [("nome",""),("nome","Teste"),("cep",""),
    ("cep","abc12345678"),("logradouro"," "),("numero",""),("bairro",""),
    ("cidade",""),("uf","XX")])
def test_invalid_delivery_never_writes_or_reduces_stock(checkout_env, field, value):
    client, store = checkout_env
    data = address(sign_in(client)); data[field] = value
    assert client.post("/checkout", data=data).status_code == 422
    assert store.get("produto:x")["estoque"] == 100


def test_no_token_cannot_create_order(checkout_env):
    client, store = checkout_env
    sign_in(client)
    assert client.post("/checkout", data=address("invalid")).status_code == 302
    assert store.get("produto:x")["estoque"] == 100


def test_valid_delivery_is_saved_and_stock_decreases(checkout_env):
    client, store = checkout_env
    response = client.post("/checkout", data=address(sign_in(client)))
    assert response.location.endswith("/pedidos")
    assert store.get("produto:x")["estoque"] == 98
    orders = [doc for doc in store.docs.values() if doc.get("tipo") == "pedido"]
    assert len(orders) == 1 and orders[0]["status"] == "CONFIRMADO"
    assert orders[0]["entrega"]["cep"] == "13000000"
    assert orders[0]["total"] == 20


def test_idempotency_does_not_reduce_stock_twice():
    product = {"_id": "produto:x", "_rev": "1-x", "tipo": "produto",
               "carta_api_id": "X", "nome": "Carta", "estoque": 3,
               "preco": 10.0, "ativo": True}
    store = MemoryStore(product)
    token = "b6ca6a9e-423e-4bd5-9fb2-5fd8302f27cb"
    first = place_order(store, "cliente:x", {"produto:x": 1}, {"cep": "13000000"}, token)
    second = place_order(store, "cliente:x", {"produto:x": 1}, {"cep": "13000000"}, token)
    assert first["_id"] == second["_id"]
    assert store.get("produto:x")["estoque"] == 2


def test_revision_conflict_is_retried_without_double_decrement():
    class ConflictOnceStore(MemoryStore):
        def __init__(self, *docs):
            super().__init__(*docs)
            self.conflict = True

        def save(self, doc):
            if doc["_id"] == "produto:x" and doc.get("reservas_checkout") and self.conflict:
                self.conflict = False
                raise DatabaseError(409)
            return super().save(doc)

    product = {"_id": "produto:x", "_rev": "1-x", "tipo": "produto",
               "carta_api_id": "X", "nome": "Carta", "estoque": 3,
               "preco": 10.0, "ativo": True}
    store = ConflictOnceStore(product)
    order = place_order(store, "cliente:x", {"produto:x": 1}, {"cep": "13000000"},
                        "b6ca6a9e-423e-4bd5-9fb2-5fd8302f27cb")
    assert order["status"] == "CONFIRMADO"
    assert store.get("produto:x")["estoque"] == 2


def test_partial_failure_compensates_reserved_stock():
    docs = [{"_id": f"produto:{code}", "_rev": "1-x", "tipo": "produto",
             "carta_api_id": code, "nome": code, "estoque": 2,
             "preco": 10.0, "ativo": True} for code in ("a", "b")]
    store = MemoryStore(*docs)
    store.failures["produto:b"] = 3
    with pytest.raises(CheckoutError):
        place_order(store, "cliente:x", {"produto:a": 1, "produto:b": 1},
                    {"cep": "13000000"}, "b6ca6a9e-423e-4bd5-9fb2-5fd8302f27cb")
    assert store.get("produto:a")["estoque"] == 2
    assert store.get("produto:b")["estoque"] == 2
    order = next(doc for doc in store.docs.values() if doc.get("tipo") == "pedido")
    assert order["status"] == "CANCELADO"


def test_expired_account_cannot_checkout(checkout_env):
    client, store = checkout_env
    token = sign_in(client)
    del store.docs["cliente:test"]
    assert client.post("/checkout", data=address(token)).location.endswith("/login")
    assert store.get("produto:x")["estoque"] == 100
