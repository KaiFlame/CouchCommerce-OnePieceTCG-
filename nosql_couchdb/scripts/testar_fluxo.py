"""Prova isolada do fluxo API/CouchDB -> catálogo -> carrinho -> pedido.

Executar somente pelo serviço ``admin``. Usa um banco temporário e o remove ao fim,
sem alterar clientes, estoque ou pedidos da demonstração principal.
"""
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as shop
from database import CouchDB, DatabaseError
from setup_db import initialize


EVIDENCE = Path("evidencias/fluxo_completo.json")


def expect(response, status, stage):
    if response.status_code != status:
        raise RuntimeError(f"{stage}: HTTP {response.status_code}")


def main():
    source = CouchDB()
    candidates = source.find_all({"tipo": "produto", "ativo": True})
    by_card = {}
    for candidate in candidates:
        if candidate.get("preco") is not None:
            by_card.setdefault(candidate["carta_api_id"], []).append(candidate)
    variants = next((items[:2] for items in by_card.values() if len(items) >= 2), None)
    if not variants:
        raise RuntimeError("Sincronize cartas com ao menos duas artes precificadas antes do teste.")

    database_name = "ecommerce_e2e_" + uuid.uuid4().hex[:12]
    test_db = CouchDB(name=database_name)
    try:
        initialize(test_db, seed=False)
        product, selected_variant = (deepcopy(variants[0]), deepcopy(variants[1]))
        for item in (product, selected_variant):
            item.pop("_rev", None)
            item.update(estoque=2, ativo=True)
            test_db.save(item)
        shop.db = test_db
        shop.app.config.update(TESTING=True)
        client = shop.app.test_client()

        catalog = client.get("/?q=" + product["carta_api_id"])
        expect(catalog, 200, "catalogo")
        if product["nome"] not in catalog.text or selected_variant["_id"] not in catalog.text:
            raise RuntimeError("A carta real ou sua arte alternativa não apareceu no catálogo.")
        with client.session_transaction() as session:
            csrf = session["form_csrf_token"]

        registration = client.post("/cadastro", data={
            "csrf_token": csrf, "nome": "Cliente de Integração",
            "email": f"e2e-{uuid.uuid4().hex}@example.test",
            "senha": "Senha-de-teste-123", "confirmacao": "Senha-de-teste-123",
        })
        expect(registration, 302, "cadastro")
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["form_csrf_token"]
        login = client.post("/login", data={"csrf_token": csrf,
                            "email": next(doc["email"] for doc in test_db.find({"tipo": "cliente"}, limit=1)),
                            "senha": "Senha-de-teste-123"})
        expect(login, 302, "login")

        client.get("/")
        with client.session_transaction() as session:
            csrf = session["form_csrf_token"]
        added = client.post("/carrinho/adicionar/" + selected_variant["_id"],
                            data={"csrf_token": csrf})
        expect(added, 302, "carrinho")
        expect(client.get("/carrinho"), 200, "resumo_carrinho")
        expect(client.get("/checkout"), 200, "checkout")
        with client.session_transaction() as session:
            checkout_token = session["checkout_token"]
        checkout = client.post("/checkout", data={
            "csrf_token": checkout_token, "nome": "Cliente de Integração",
            "cep": "13000000", "logradouro": "Rua de Teste", "numero": "1",
            "complemento": "", "bairro": "Centro", "cidade": "Campinas", "uf": "SP",
        })
        expect(checkout, 302, "confirmacao")
        expect(client.get("/pedidos"), 200, "historico")

        orders = test_db.find({"tipo": "pedido"}, limit=10)
        saved_variant = test_db.get(selected_variant["_id"])
        if (len(orders) != 1 or orders[0]["status"] != "CONFIRMADO" or
                saved_variant["estoque"] != 1 or
                orders[0]["itens"][0].get("variante_api_id") != selected_variant.get("variante_api_id")):
            raise RuntimeError("Pedido ou baixa de estoque divergente.")
        evidence = {
            "ok": True, "database": database_name, "isolated": True,
            "stages": ["carta_real", "catalogo", "cadastro", "login", "carrinho",
                       "checkout", "pedido", "consulta_historico"],
            "card": product["carta_api_id"], "selected_variant": selected_variant.get("variante_api_id"),
            "price_brl": selected_variant["preco"],
            "order_status": orders[0]["status"], "stock_before": 2,
            "stock_after": saved_variant["estoque"], "documents": len(test_db.find_all({})),
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        try:
            source.request("DELETE", "/" + database_name)
        except DatabaseError as error:
            if error.status != 404:
                raise


if __name__ == "__main__":
    main()
