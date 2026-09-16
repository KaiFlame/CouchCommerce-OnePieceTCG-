from copy import deepcopy
import pytest
import app as shop
from werkzeug.security import generate_password_hash


@pytest.fixture
def checkout_env(monkeypatch):
    shop.app.config.update(TESTING=True, SECRET_KEY="test-only")
    writes = []
    product = {"_id": "produto:x", "_rev": "1-x", "tipo": "produto",
               "carta_api_id": "X", "nome": "Carta teste", "estoque": 100,
               "preco": 10, "ativo": True}
    customer = {"_id": "cliente:test", "nome": "Pessoa Teste",
                "senha_hash": generate_password_hash("test-password")}
    monkeypatch.setattr(shop, "get", lambda _: deepcopy(product))
    monkeypatch.setattr(shop, "find", lambda *a, **kw: [customer])
    def couch(*a, **kw):
        writes.extend(kw["json"]["docs"])
        return [{"ok": True} for _ in writes]
    monkeypatch.setattr(shop, "couch", couch)
    client = shop.app.test_client()
    with client.session_transaction() as session:
        session["carrinho"] = {"produto:x": 2}
    return client, writes


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
    client, writes = checkout_env
    for method in (client.get, client.post):
        response = method("/checkout")
        assert response.status_code == 302 and response.location.endswith("/login")
    assert not writes
    response = client.post("/login", data={"email":"teste@example.test", "senha":"test-password"})
    assert response.location.endswith("/checkout")
    with client.session_transaction() as session:
        assert session["carrinho"] == {"produto:x": 2}


@pytest.mark.parametrize("field,value", [("nome",""),("nome","Teste"),("cep",""),
    ("cep","abc12345678"),("logradouro"," "),("numero",""),("bairro",""),
    ("cidade",""),("uf","XX")])
def test_invalid_delivery_never_writes_or_reduces_stock(checkout_env, field, value):
    client, writes = checkout_env
    data = address(sign_in(client)); data[field] = value
    assert client.post("/checkout", data=data).status_code == 422
    assert not writes
    with client.session_transaction() as session:
        assert session["carrinho"] == {"produto:x": 2}


def test_no_token_cannot_create_order(checkout_env):
    client, writes = checkout_env
    sign_in(client)
    assert client.post("/checkout", data=address("invalid")).status_code == 302
    assert not writes


def test_valid_delivery_is_saved_and_stock_decreases(checkout_env):
    client, writes = checkout_env
    data = address(sign_in(client))
    assert not writes
    response = client.post("/checkout", data=data)
    assert response.location.endswith("/pedidos")
    product, order = writes
    assert product["estoque"] == 98
    assert order["entrega"]["cep"] == "13000000"
    assert order["entrega"]["nome"] == "Pessoa Teste"
    assert order["total"] == 20
    with client.session_transaction() as session:
        assert not session["carrinho"]
    client.post("/checkout", data=data)
    assert len(writes) == 2


def test_expired_account_cannot_checkout(checkout_env, monkeypatch):
    client, writes = checkout_env
    token = sign_in(client)
    monkeypatch.setattr(shop, "find", lambda *a, **kw: [])
    assert client.post("/checkout", data=address(token)).location.endswith("/login")
    assert not writes


def test_quantity_can_be_added_and_updated(monkeypatch):
    shop.app.config.update(TESTING=True, SECRET_KEY="test-only")
    product = {"_id": "produto:x", "tipo": "produto", "ativo": True,
               "preco": 10, "estoque": 50, "carta_api_id": "X", "nome": "X"}
    monkeypatch.setattr(shop, "get", lambda _: deepcopy(product))
    client = shop.app.test_client()
    assert client.post("/carrinho/adicionar/produto:x",
                       data={"quantidade": "4"}).status_code == 302
    with client.session_transaction() as session:
        assert session["carrinho"]["produto:x"] == 4
    assert client.post("/carrinho/atualizar/produto:x",
                       data={"quantidade": "7"}).status_code == 302
    with client.session_transaction() as session:
        assert session["carrinho"]["produto:x"] == 7
    assert client.post("/carrinho/atualizar/produto:x",
                       data={"quantidade": "0"}).status_code == 302
    with client.session_transaction() as session:
        assert "produto:x" not in session["carrinho"]


def test_ajax_add_returns_json_without_redirecting(monkeypatch):
    shop.app.config.update(TESTING=True, SECRET_KEY="test-only")
    product = {"_id": "produto:x", "tipo": "produto", "ativo": True,
               "preco": 10, "estoque": 50, "carta_api_id": "X", "nome": "X"}
    monkeypatch.setattr(shop, "get", lambda _: deepcopy(product))
    client = shop.app.test_client()
    response = client.post(
        "/carrinho/adicionar/produto:x",
        data={"quantidade": "3"},
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.is_json
    assert response.json["ok"] is True
    assert response.json["cart_count"] == 3
    assert response.json["product_quantity"] == 3
