import os
import uuid
import math
import re
import secrets
from card_catalog import fetch_cards, merge_card
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# Configuração da aplicação e do CouchDB
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

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
    """Usa os metadados importados, mantendo compatibilidade com produtos antigos."""
    produto_exibicao = produto.copy()
    produto_exibicao["nome"] = produto.get("nome") or produto["carta_api_id"]
    produto_exibicao["categoria"] = produto.get("categoria") or "One Piece TCG"
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
            if request.endpoint == "checkout":
                session["voltar_checkout"] = True
            flash("Faça login para continuar.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrap


# Catálogo e carrinho
@app.route("/")
def catalogo():
    todos = all_products()
    options = {field: sorted({p.get(field) or "—" for p in todos})
               for field in ("grupo", "colecao", "cor", "raridade", "categoria")}
    produtos = todos
    q = request.args.get("q", "").strip()[:150]
    if q:
        produtos = [p for p in produtos if q.casefold() in
                    (p.get("nome", "") + " " + p["carta_api_id"]).casefold()]
    for field in options:
        value = request.args.get(field)
        if value:
            produtos = [p for p in produtos if p.get(field) == value]
    if request.args.get("estoque") == "1":
        produtos = [p for p in produtos if p.get("estoque", 0) > 0 and p.get("preco") is not None]
    order = request.args.get("ordem", "codigo")
    if order == "nome":
        produtos.sort(key=lambda p: p.get("nome", "").casefold())
    elif order == "preco":
        produtos.sort(key=lambda p: (p.get("preco") is None, p.get("preco") or 0))
    else:
        produtos.sort(key=lambda p: (p["carta_api_id"], p["_id"]))
    total = len(produtos)
    pages = max(1, math.ceil(total / 24))
    page = max(1, min(request.args.get("pagina", 1, type=int), pages))
    args = request.args.to_dict()
    args.pop("pagina", None)
    page_url = lambda n: url_for("catalogo", **args, pagina=n) + "#colecao"
    featured = [p for p in todos if p["carta_api_id"] in
                ("OP01-001", "OP01-003", "OP05-119") and p.get("imagem")][:3]
    return render_template("catalogo.html", produtos=produtos[(page-1)*24:page*24],
                           total=total, total_catalogo=len(todos), options=options,
                           page=page, pages=pages, page_url=page_url, featured=featured)


def all_products():
    docs, bookmark = [], None
    while True:
        query = {"selector": {"tipo": "produto", "ativo": True}, "limit": 500}
        if bookmark:
            query["bookmark"] = bookmark
        result = couch("POST", "/_find", json=query)
        batch = result.get("docs", [])
        docs.extend(batch)
        next_bookmark = result.get("bookmark")
        if not batch or next_bookmark == bookmark:
            return docs
        bookmark = next_bookmark


@app.post("/carrinho/adicionar/<path:produto_id>")
def adicionar(produto_id):
    produto = get(produto_id)
    if not produto.get("ativo") or produto.get("preco") is None:
        flash("Esta carta está disponível apenas para consulta.")
        return redirect(url_for("catalogo"))
    carrinho_atual = session.get("carrinho", {})
    quantidade = int(carrinho_atual.get(produto_id, 0)) + 1

    if quantidade > int(produto.get("estoque", 0)):
        flash("Estoque insuficiente.")
        return redirect(url_for("catalogo"))

    carrinho_atual[produto_id] = quantidade
    session["carrinho"] = carrinho_atual
    session.modified = True
    flash("Carta adicionada ao carrinho.")
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
        senha = request.form["senha"]
        confirmacao = request.form.get("confirmacao", "")
        if senha != confirmacao:
            flash("As senhas não coincidem.")
            return render_template("cadastro.html")
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
            "senha_hash": generate_password_hash(senha),
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
        if session.pop("voltar_checkout", False):
            return redirect(url_for("checkout"))
        return redirect(url_for("catalogo"))

    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("catalogo"))


# Checkout e histórico de pedidos
ESTADOS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def validar_entrega(form):
    labels = {"nome": "Nome do destinatário", "cep": "CEP", "logradouro": "Rua / avenida",
              "numero": "Número", "bairro": "Bairro", "cidade": "Cidade", "uf": "Estado"}
    entrega = {key: form.get(key, "").strip() for key in (*labels, "complemento")}
    erros = {key: f"Preencha {label.lower()}." for key, label in labels.items() if not entrega[key]}
    for key, value in entrega.items():
        if len(value) > 150:
            erros[key] = "Use no máximo 150 caracteres."
    if entrega["nome"] and len(entrega["nome"].split()) < 2:
        erros["nome"] = "Informe o nome completo do destinatário."
    if entrega["cep"] and not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", entrega["cep"]):
        erros["cep"] = "Informe um CEP com 8 dígitos."
    if entrega["uf"] and entrega["uf"] not in ESTADOS:
        erros["uf"] = "Selecione um estado válido."
    if not erros:
        entrega["cep"] = entrega["cep"].replace("-", "")
    return entrega, erros


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    clientes = find({"tipo": "cliente", "_id": session["cliente_id"]}, limit=1)
    if not clientes:
        session.pop("cliente_id", None)
        session.pop("cliente_nome", None)
        session["voltar_checkout"] = True
        flash("Sua sessão expirou. Entre novamente para finalizar.")
        return redirect(url_for("login"))
    carrinho_atual = session.get("carrinho", {})
    if not carrinho_atual:
        flash("Carrinho vazio.")
        return redirect(url_for("catalogo"))

    token = session.setdefault("checkout_token", secrets.token_urlsafe(32))
    entrega = {"nome": clientes[0].get("nome", "")}
    erros = {}
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf_token", ""), token):
            flash("O formulário expirou. Revise a entrega e tente novamente.")
            return redirect(url_for("checkout"))
        entrega, erros = validar_entrega(request.form)

    produtos_atualizados = []
    itens_do_pedido = []
    total = 0.0

    for produto_id, quantidade in carrinho_atual.items():
        produto = get(produto_id)
        produto_exibicao = preparar_produto_para_exibicao(produto)
        quantidade = int(quantidade)
        if quantidade < 1 or not produto.get("ativo") or produto.get("preco") is None:
            flash("Uma carta do carrinho não está disponível para compra.")
            return redirect(url_for("carrinho"))

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

    if request.method == "GET" or erros:
        return render_template("checkout.html", entrega=entrega, erros=erros,
                               estados=ESTADOS, itens=itens_do_pedido,
                               total=round(total, 2), csrf_token=token), (422 if erros else 200)

    pedido = {
        "_id": f"pedido:{uuid.uuid4()}",
        "tipo": "pedido",
        "cliente_id": session["cliente_id"],
        "entrega": entrega,
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
    session.pop("checkout_token", None)
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


@app.cli.command("sync-cards")
def sync_cards():
    """Atualiza metadados; preserva preço, estoque e estado de cada produto."""
    import_cards(fetch_cards())


def import_cards(cards):
    ensure_db()
    ids = list(cards)
    count = 0
    for start in range(0, len(ids), 200):
        keys = ids[start:start+200]
        rows = couch("POST", "/_all_docs?include_docs=true", json={"keys": keys})["rows"]
        existing = {r["id"]: r.get("doc") for r in rows if "id" in r}
        documents = [merge_card(cards[k], existing.get(k)) for k in keys]
        results = couch("POST", "/_bulk_docs", json={"docs": documents})
        failures = [r for r in results if r.get("error")]
        if failures:
            raise RuntimeError(f"Importação interrompida: {len(failures)} erros no lote.")
        count += len(results)
    print(f"{count} cartas sincronizadas; preços e estoques preservados.")


if __name__ == "__main__":
    ensure_db()
    app.run(debug=True)
