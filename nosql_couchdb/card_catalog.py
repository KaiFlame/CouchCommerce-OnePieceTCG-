"""Importação explícita e repetível; nunca consulta a API durante uma visita."""
import hashlib
from pathlib import PurePosixPath
from urllib.parse import urlparse
import requests

SOURCES = {"allSetCards": "Coleções", "allSTCards": "Starter decks",
           "allPromos": "Promocionais", "allDonCards": "DON!!"}


def normalize(card, group):
    image = card.get("card_image") or ""
    if image and (urlparse(image).scheme != "https" or urlparse(image).hostname != "optcgapi.com"):
        raise ValueError("URL de imagem inesperada")
    image_id = card.get("card_image_id") or ""
    stem = PurePosixPath(urlparse(image).path).stem
    # Promoções podem reutilizar o código e image_id de uma arte diferente.
    identity = image_id if (stem == image_id or (not image and group != "Promocionais")) else "art-" + hashlib.sha256((image or group + str(card.get("card_name")) + image_id).encode()).hexdigest()[:24]
    return {"_id": "produto:" + identity, "tipo": "produto",
            "carta_api_id": card.get("card_set_id") or image_id or identity,
            "nome": card.get("card_name") or card.get("optcg_don_name") or identity,
            "imagem": image, "colecao": card.get("set_name") or "DON!!",
            "grupo": group, "raridade": card.get("rarity") or "—",
            "cor": card.get("card_color") or "Sem cor",
            "categoria": card.get("card_type") or "DON!!",
            "poder": card.get("card_power"), "custo": card.get("card_cost"),
            "efeito": card.get("card_text") or "", "origem": "optcgapi.com"}


def collect(payloads):
    documents = {}
    seen_images = set()
    for endpoint, group in SOURCES.items():
        rows = payloads[endpoint]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Resposta vazia ou inválida: " + endpoint)
        for row in rows:
            doc = normalize(row, group)
            image_key = doc["imagem"] or doc["_id"]
            if image_key not in seen_images:
                seen_images.add(image_key)
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
    if existing:
        return {**existing, **metadata}
    return {**metadata, "preco": None, "estoque": 0, "ativo": True}
