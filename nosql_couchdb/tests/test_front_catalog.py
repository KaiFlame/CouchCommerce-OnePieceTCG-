"""Testes rápidos do catálogo, fallback e endpoint de saúde."""
import os
os.environ.setdefault("SECRET_KEY", "test-only-secret-" * 4)
os.environ.setdefault("COUCHDB_URL", "http://test:test@localhost:5984")

import app as project
from database import DatabaseError
from werkzeug.security import check_password_hash

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


def test_catalog_groups_arts_without_losing_selected_variant():
    art = {**PRODUCTS[0], "_id": "produto:OP01-001_p1", "variante_api_id": "OP01-001_p1",
           "imagem": "https://optcgapi.com/media/static/Card_Images/OP01-001_p1.jpg"}
    grouped = project.agrupar_por_carta([{**PRODUCTS[0], "variante_api_id": "OP01-001"}, art])
    assert len(grouped) == 1
    assert grouped[0]["total_variantes"] == 2
    assert {variant["_id"] for variant in grouped[0]["variantes"]} == {"produto:OP01-001", "produto:OP01-001_p1"}


def test_selected_alternate_art_is_the_cart_item(monkeypatch):
    alternate = {**PRODUCTS[0], "_id": "produto:OP01-001_p1", "variante_api_id": "OP01-001_p1",
                 "estoque": 2, "ativo": True}
    monkeypatch.setattr(project, "get", lambda product_id: alternate if product_id == alternate["_id"] else None)
    client = project.app.test_client()
    client.get("/")
    with client.session_transaction() as session:
        csrf = session["form_csrf_token"]
    assert client.post("/carrinho/adicionar/" + alternate["_id"], data={"csrf_token": csrf}).status_code == 302
    with client.session_transaction() as session:
        assert session["carrinho"] == {alternate["_id"]: 1}


def test_registration_duplicate_login_and_post_logout(monkeypatch):
    customers, saved = [], []

    def find(selector, fields=None, limit=100):
        return [customer for customer in customers
                if all(customer.get(key) == value for key, value in selector.items())][:limit]

    def save(customer):
        customers.append(customer.copy())
        saved.append(customer.copy())

    monkeypatch.setattr(project, "find", find)
    monkeypatch.setattr(project, "save", save)
    client = project.app.test_client()
    client.get("/cadastro")
    with client.session_transaction() as session:
        csrf = session["form_csrf_token"]
    data = {"csrf_token": csrf, "nome": "Pessoa Teste", "email": "PESSOA@EXAMPLE.TEST",
            "senha": "Senha-de-teste-123", "confirmacao": "Senha-de-teste-123"}
    assert client.post("/cadastro", data=data).location.endswith("/login")
    assert len(saved) == 1 and saved[0]["_id"].startswith("cliente:")
    assert saved[0]["email"] == "pessoa@example.test" and "senha" not in saved[0]
    assert check_password_hash(saved[0]["senha_hash"], data["senha"])
    assert b"E-mail j" in client.post("/cadastro", data=data).data
    assert len(saved) == 1
    client.get("/login")
    with client.session_transaction() as session:
        csrf = session["form_csrf_token"]
    assert client.post("/login", data={"csrf_token": csrf, "email": data["email"], "senha": data["senha"]}).status_code == 302
    with client.session_transaction() as session:
        csrf = session["form_csrf_token"]
    assert client.post("/logout", data={"csrf_token": csrf}).status_code == 302
    with client.session_transaction() as session:
        assert "cliente_id" not in session
