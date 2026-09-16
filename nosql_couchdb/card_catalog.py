"""API externa -> cache de características + produto comercial mínimo."""
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import requests

SOURCES = {"allSetCards": "Coleções", "allSTCards": "Starter decks",
           "allPromos": "Promocionais", "allDonCards": "DON!!"}
CACHE_FILE = Path(os.getenv("CATALOG_CACHE", ".local/catalog/cards.json"))
RATE = Decimal("5")
INITIAL_STOCK = int(os.getenv("CATALOG_INITIAL_STOCK", "5"))
_cache = (None, {})


def now():
    return datetime.now(timezone.utc).isoformat()


def price_brl(value):
    """Preço comercial didático: market_price USD × 5, centavos HALF_UP."""
    try:
        dollars = Decimal(str(value))
        if not dollars.is_finite() or dollars <= 0 or dollars > 1_000_000:
            return None
        result = (dollars * RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return float(result) if result > 0 else None
    except (InvalidOperation, ValueError):
        return None


def normalize(card, group):
    image = card.get("card_image") or ""
    if image and (urlparse(image).scheme != "https" or urlparse(image).hostname != "optcgapi.com"):
        raise ValueError("URL de imagem inesperada")
    image_id = str(card.get("card_image_id") or "")
    stem = PurePosixPath(urlparse(image).path).stem
    # Promoções podem reutilizar o código e image_id de uma arte diferente.
    identity = image_id if (stem == image_id or (not image and group != "Promocionais")) else "art-" + hashlib.sha256((image or group + str(card.get("card_name")) + image_id).encode()).hexdigest()[:24]
    return {"_id": "produto:" + identity, "tipo": "produto",
            # ``card_set_id`` representa a carta lógica; ``card_image_id`` representa
            # a arte/variante devolvida pela API. Alguns registros promocionais
            # reutilizam este último, por isso collect() o desambigua pela imagem.
            "carta_api_id": card.get("card_set_id") or card.get("don_id") or image_id or identity,
            "variante_api_id": image_id or identity,
            "nome": card.get("card_name") or card.get("optcg_don_name") or identity,
            "imagem": image, "colecao": card.get("set_name") or "DON!!",
            "grupo": group, "raridade": card.get("rarity") or "—",
            "cor": card.get("card_color") or "Sem cor",
            "categoria": card.get("card_type") or "DON!!",
            "poder": card.get("card_power"), "custo": card.get("card_cost"),
            "efeito": card.get("card_text") or "", "origem": "optcgapi.com",
            "preco_usd": float(card["market_price"]) if price_brl(card.get("market_price")) is not None else None,
            "preco": price_brl(card.get("market_price")),
            "preco_data_api": card.get("date_scraped")}


def collect(payloads):
    documents = {}
    seen_images = set()
    variants = []
    for endpoint, group in SOURCES.items():
        rows = payloads[endpoint]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Resposta vazia ou inválida: " + endpoint)
        for row in rows:
            doc = normalize(row, group)
            image_key = doc["imagem"] or doc["_id"]
            if image_key not in seen_images:
                seen_images.add(image_key)
                variants.append(doc)
    # card_image_id é a identidade preferida. Quando a própria fonte reutiliza o
    # mesmo ID em imagens distintas, o sufixo determinístico evita colisões.
    image_sets = {}
    for doc in variants:
        image_sets.setdefault(doc["variante_api_id"], set()).add(doc["imagem"] or doc["_id"])
    for doc in variants:
        variant_id = doc["variante_api_id"]
        if len(image_sets[variant_id]) > 1:
            variant_id += ":" + hashlib.sha256((doc["imagem"] or doc["_id"]).encode()).hexdigest()[:12]
        doc["variante_api_id"] = variant_id
        doc["_id"] = "produto:" + variant_id
        documents[doc["_id"]] = doc
    return documents


def fetch_cards():
    payloads = {}
    for endpoint in SOURCES:
        response = requests.get(f"https://optcgapi.com/api/{endpoint}/", timeout=90)
        response.raise_for_status()
        payloads[endpoint] = response.json()
    return collect(payloads)


def merge_card(metadata, existing=None):
    """Atualiza preço/cache; preserva estoque e ativo da loja."""
    existing = existing or {}
    # Somente os campos usados pela vitrine/filtros são repetidos no banco.
    # Texto, poder e custo continuam apenas no cache da API.
    fields = ("_id", "tipo", "carta_api_id", "variante_api_id", "nome", "imagem", "colecao", "grupo",
              "cor", "raridade", "categoria",
              "preco", "preco_usd", "preco_data_api")
    if not 0 <= INITIAL_STOCK <= 999:
        raise ValueError("CATALOG_INITIAL_STOCK deve estar entre 0 e 999")
    # A API de cartas não fornece estoque da loja. Cada arte é um produto próprio:
    # variantes novas recebem o estoque inicial configurável uma única vez. O marcador
    # impede que uma sincronização futura ressuscite uma arte já esgotada.
    initialized = existing.get("estoque_inicializado") is True
    previous_stock = existing.get("estoque", 0)
    stock = previous_stock if initialized or previous_stock not in (None, 0) else INITIAL_STOCK
    doc = dict(existing)
    doc.update({key: metadata.get(key) for key in fields})
    doc.update(estoque=stock, estoque_inicializado=True, ativo=existing.get("ativo", True),
               schema_version=2, criado_em=existing.get("criado_em", now()),
               cambio=5, origem="optcgapi.com")
    # Não altere a revisão/timestamp quando API e projeção comercial não mudaram.
    compared = set(fields) | {"estoque", "estoque_inicializado", "ativo", "schema_version", "criado_em", "cambio", "origem"}
    if existing and all(existing.get(key) == doc.get(key) for key in compared):
        return existing
    doc["atualizado_em"] = now()
    return doc


def save_cache(cards):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"atualizado_em": now(), "cards": cards}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(CACHE_FILE)


def cached_cards():
    global _cache
    try:
        stamp = CACHE_FILE.stat().st_mtime_ns
        if stamp != _cache[0]:
            _cache = (stamp, json.loads(CACHE_FILE.read_text(encoding="utf-8"))["cards"])
        return _cache[1]
    except (OSError, ValueError, KeyError):
        return {}


def enrich(product):
    # O preço/estoque do banco sempre prevalece sobre a API/cache.
    return {**cached_cards().get(product["_id"], {}), **product,
            "nome": product.get("nome") or product["carta_api_id"]}
