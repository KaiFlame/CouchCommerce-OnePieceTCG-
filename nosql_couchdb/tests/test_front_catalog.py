"""Testes rápidos do catálogo, fallback e endpoint de saúde."""
import os
os.environ.setdefault("SECRET_KEY", "test-only-secret-" * 4)
os.environ.setdefault("COUCHDB_URL", "http://test:test@localhost:5984")

import app as project
from database import DatabaseError

PRODUCTS = [{"_id": "produto:OP01-001", "tipo": "produto", "carta_api_id": "OP01-001",
             "nome": "Roronoa Zoro", "categoria": "Leader", "preco": 10.75, "estoque": 5,
             "ativo": True, "imagem": "https://optcgapi.com/media/static/Card_Images/OP01-001.jpg"}]


def test_catalog_real_template_filters_and_price(monkeypatch):
    monkeypatch.setattr(project, "all_products", lambda: PRODUCTS)
    client = project.app.test_client()
    response = client.get("/?q=OP01-001")
    assert response.status_code == 200
    assert b"10,75" in response.data
    assert PRODUCTS[0]["imagem"].encode() in response.data
    assert b"Content-Security-Policy" not in response.data
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Nenhuma carta encontrada" in client.get("/?q=inexistente").text


def test_catalog_escapes_html(monkeypatch):
    monkeypatch.setattr(project, "all_products", lambda: [{**PRODUCTS[0], "nome": "<script>alert(1)</script>"}])
    response = project.app.test_client().get("/")
    assert b"<script>alert(1)</script>" not in response.data


def test_health_and_database_outage(monkeypatch):
    monkeypatch.setattr(project.db, "couch", lambda *a, **kw: {"db_name": "test"})
    assert project.app.test_client().get("/health").json["status"] == "ok"
    def unavailable(*args, **kwargs):
        raise DatabaseError(503)
    monkeypatch.setattr(project.db, "couch", unavailable)
    assert project.app.test_client().get("/health").status_code == 503
    response = project.app.test_client().get("/")
    assert response.status_code == 503
    assert b"password" not in response.data


def test_enrichment_fallback_and_local_price(monkeypatch):
    import card_catalog
    monkeypatch.setattr(card_catalog, "cached_cards", lambda: {})
    assert card_catalog.enrich(PRODUCTS[0])["nome"] == "Roronoa Zoro"
    monkeypatch.setattr(card_catalog, "cached_cards", lambda: {"produto:OP01-001": {"preco": 999, "raridade": "L"}})
    enriched = card_catalog.enrich(PRODUCTS[0])
    assert enriched["preco"] == 10.75 and enriched["raridade"] == "L"
