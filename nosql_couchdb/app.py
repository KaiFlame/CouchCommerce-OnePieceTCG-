import os
import uuid
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

response = requests.get('https://optcgapi.com/api/sets/card/OP01-001/')
response_text = response.json()


# Configuração da aplicação e do CouchDB
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")

COUCHDB_URL = os.getenv(
    "COUCHDB_URL", "http://admin:admin@127.0.0.1:5984"
).rstrip("/")
DB_NAME = os.getenv("COUCHDB_DATABASE", "ecommerce_facamp")
DB_URL = f"{COUCHDB_URL}/{DB_NAME}"


# Funções de acesso ao CouchDB
def raw(method, url, **kwargs):
    resposta = requests.request(method, url, timeout=10, **kwargs)
    if resposta.status_code >= 400:
        raise RuntimeError(f"CouchDB {resposta.status_code}: {resposta.text}")
    return resposta.json() if resposta.text else {}


def couch(method, path="", **kwargs):
    return raw(method, f"{DB_URL}{path}", **kwargs)


def ensure_db():
    resposta = requests.put(DB_URL, timeout=10)
    if resposta.status_code not in (201, 202, 412):
        raise RuntimeError(resposta.text)


def save(doc):
    if "_id" in doc:
        return couch("PUT", f"/{doc['_id']}", json=doc)
    return couch("POST", "", json=doc)


def get(doc_id):
    return couch("GET", f"/{doc_id}")


def find(selector, fields=None, limit=100):
    consulta = {"selector": selector, "limit": limit}
    if fields:
        consulta["fields"] = fields
    return couch("POST", "/_find", json=consulta).get("docs", [])


def preparar_produto_para_exibicao(produto):
    """Prepara os dados esperados pelas telas sem alterar o documento no CouchDB.

    Na integração com a API externa, esta função será substituída pelo
    enriquecimento que buscará nome, coleção, raridade e imagem da carta.
    """
    produto_exibicao = produto.copy()
    produto_exibicao["nome"] = produto["carta_api_id"]
    produto_exibicao["categoria"] = "One Piece TCG"
    return produto_exibicao


# Dados mínimos para estudo antes da integração com a API de cartas
def seed():
    ensure_db()
    produtos = [
        {
            "_id": "produto:OP01-001",
            "tipo": "produto",
            "carta_api_id": "OP01-001",
            "preco": 89.90,
            "estoque": 5,
            "ativo": True,
        },
        {
            "_id": "produto:OP01-002",
            "tipo": "produto",
            "carta_api_id": "OP01-002",
            "preco": 39.90,
            "estoque": 8,
            "ativo": True,
        },
        {
            "_id": "produto:OP01-003",
            "tipo": "produto",
            "carta_api_id": "OP01-003",
            "preco": 24.90,
            "estoque": 12,
            "ativo": True,
        },
    ]

    for produto in produtos:
        resposta = requests.put(
            f"{DB_URL}/{produto['_id']}", json=produto, timeout=10
        )
        if resposta.status_code not in (201, 202, 409):
            raise RuntimeError(resposta.text)

    indices = [
        (["tipo", "ativo"], "idx_tipo_ativo"),
        (["tipo", "carta_api_id"], "idx_tipo_carta_api_id"),
        (["tipo", "email"], "idx_tipo_email"),
        (["tipo", "cliente_id"], "idx_tipo_cliente"),
    ]
    for campos, nome in indices:
        couch(
            "POST",
            "/_index",
            json={"index": {"fields": campos}, "name": nome, "type": "json"},
        )


def login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if not session.get("cliente_id"):
            flash("Faça login para continuar.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrap


# Catálogo e carrinho
@app.route("/")
def catalogo():
    produtos_db = find(
        {"tipo": "produto", "ativo": True},
        ["_id", "carta_api_id", "preco", "estoque", "ativo"],
    )
    produtos = [
        preparar_produto_para_exibicao(produto) for produto in produtos_db
    ]
    produtos.sort(key=lambda produto: produto["carta_api_id"])
    return render_template("catalogo.html", produtos=produtos)


@app.post("/carrinho/adicionar/<path:produto_id>")
def adicionar(produto_id):
    produto = get(produto_id)
    carrinho_atual = session.get("carrinho", {})
    quantidade = int(carrinho_atual.get(produto_id, 0)) + 1

    if quantidade > int(produto.get("estoque", 0)):
        flash("Estoque insuficiente.")
        return redirect(url_for("catalogo"))

    carrinho_atual[produto_id] = quantidade
    session["carrinho"] = carrinho_atual
    session.modified = True
    return redirect(url_for("catalogo"))


@app.route("/carrinho")
def carrinho():
    itens = []
    total = 0.0

    for produto_id, quantidade in session.get("carrinho", {}).items():
        produto = preparar_produto_para_exibicao(get(produto_id))
        quantidade = int(quantidade)
        subtotal = float(produto["preco"]) * quantidade
        total += subtotal
        itens.append(
            {"produto": produto, "qtd": quantidade, "subtotal": subtotal}
        )

    return render_template("carrinho.html", itens=itens, total=total)


# Cadastro e autenticação de clientes
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        cliente_existente = find({"tipo": "cliente", "email": email}, limit=1)
        if cliente_existente:
            flash("E-mail já cadastrado.")
            return render_template("cadastro.html")

        cliente = {
            "_id": f"cliente:{uuid.uuid4()}",
            "tipo": "cliente",
            "nome": request.form["nome"].strip(),
            "email": email,
            "senha_hash": generate_password_hash(request.form["senha"]),
            "criado_em": datetime.now(timezone.utc).isoformat(),
        }
        save(cliente)
        flash("Cadastro realizado.")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        clientes = find({"tipo": "cliente", "email": email}, limit=1)

        credenciais_invalidas = not clientes or not check_password_hash(
            clientes[0]["senha_hash"], request.form["senha"]
        )
        if credenciais_invalidas:
            flash("Credenciais inválidas.")
            return render_template("login.html")

        cliente = clientes[0]
        session["cliente_id"] = cliente["_id"]
        session["cliente_nome"] = cliente["nome"]
        return redirect(url_for("catalogo"))

    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("catalogo"))


# Checkout e histórico de pedidos
@app.post("/checkout")
@login_required
def checkout():
    carrinho_atual = session.get("carrinho", {})
    if not carrinho_atual:
        flash("Carrinho vazio.")
        return redirect(url_for("catalogo"))

    produtos_atualizados = []
    itens_do_pedido = []
    total = 0.0

    for produto_id, quantidade in carrinho_atual.items():
        produto = get(produto_id)
        produto_exibicao = preparar_produto_para_exibicao(produto)
        quantidade = int(quantidade)

        if produto["estoque"] < quantidade:
            flash(f"Estoque insuficiente para {produto_exibicao['nome']}")
            return redirect(url_for("carrinho"))

        preco_unitario = float(produto["preco"])
        subtotal = round(quantidade * preco_unitario, 2)
        itens_do_pedido.append(
            {
                "produto_id": produto["_id"],
                "carta_api_id": produto["carta_api_id"],
                "nome": produto_exibicao["nome"],
                "quantidade": quantidade,
                "preco_unitario": preco_unitario,
                "subtotal": subtotal,
            }
        )

        total += subtotal
        produto["estoque"] -= quantidade
        produtos_atualizados.append(produto)

    pedido = {
        "_id": f"pedido:{uuid.uuid4()}",
        "tipo": "pedido",
        "cliente_id": session["cliente_id"],
        "status": "CRIADO",
        "itens": itens_do_pedido,
        "total": round(total, 2),
        "criado_em": datetime.now(timezone.utc).isoformat(),
    }
    resultado = couch(
        "POST",
        "/_bulk_docs",
        json={"docs": produtos_atualizados + [pedido]},
    )
    if any(item.get("error") for item in resultado):
        flash("Conflito no checkout; recarregue e tente novamente.")
        return redirect(url_for("carrinho"))

    session["carrinho"] = {}
    flash("Pedido criado.")
    return redirect(url_for("pedidos"))


@app.get("/pedidos")
@login_required
def pedidos():
    pedidos_do_cliente = find(
        {"tipo": "pedido", "cliente_id": session["cliente_id"]}
    )
    pedidos_do_cliente.sort(
        key=lambda pedido: pedido.get("criado_em", ""), reverse=True
    )
    return render_template("pedidos.html", pedidos=pedidos_do_cliente)


@app.cli.command("init-db")
def init_db():
    seed()
    print("Banco CouchDB inicializado.")


if __name__ == "__main__":
    ensure_db()
    app.run(debug=True)
