import os
import uuid
import math
import re
import secrets
import logging
import time
from card_catalog import fetch_cards, merge_card, enrich, save_cache, now, CACHE_FILE
from checkout_service import CheckoutError, place_order, recover_pending
from database import CouchDB, DatabaseError
from setup_db import initialize, application_user
from datetime import datetime, timezone
from functools import wraps

import requests
import click
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for, g, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

# Configuração da aplicação e do CouchDB
app = Flask(__name__)
load_dotenv()
app.secret_key = os.environ["SECRET_KEY"]
if len(app.secret_key) < 32:
    raise RuntimeError("Defina SECRET_KEY com pelo menos 32 caracteres aleatórios.")
app.config.update(MAX_CONTENT_LENGTH=16 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE") == "1")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
db = CouchDB()
app.jinja_env.filters["brl"] = lambda value: f"{float(value):.2f}".replace(".", ",")


def form_csrf_token():
    """Token simples para os formulários que alteram a sessão ou o banco."""
    return session.setdefault("form_csrf_token", secrets.token_urlsafe(32))


def valid_form_csrf():
    expected = session.get("form_csrf_token", "")
    received = request.form.get("csrf_token", "")
    return bool(expected and received and secrets.compare_digest(expected, received))


app.jinja_env.globals["form_csrf_token"] = form_csrf_token


@app.before_request
def start_request():
    g.started = time.monotonic()
    g.request_id = uuid.uuid4().hex[:12]


@app.after_request
def observe_request(response):
    elapsed = round((time.monotonic() - g.started) * 1000, 2)
    app.logger.info("http request_id=%s route=%s method=%s status=%s duration_ms=%s",
                    g.request_id, request.endpoint, request.method, response.status_code, elapsed)
    response.headers.update({"X-Request-ID": g.request_id, "X-Content-Type-Options": "nosniff",
                             "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
                             "Content-Security-Policy": "default-src 'self'; img-src 'self' https://optcgapi.com; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"})
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(DatabaseError)
def database_unavailable(error):
    return render_template("erro.html", mensagem="Banco temporariamente indisponível. Tente novamente em instantes."), 503


@app.get("/health")
def health():
    started = time.monotonic()
    try:
        db.couch("GET")
        status, code = "ok", 200
    except DatabaseError:
        status, code = "unavailable", 503
    age = round(time.time() - CACHE_FILE.stat().st_mtime) if CACHE_FILE.exists() else None
    return jsonify(status=status, couchdb=status, database_ms=round((time.monotonic()-started)*1000, 2),
                   catalog_cache_age_seconds=age, catalog_degraded=age is None or age > 86400), code


# Funções de acesso ao CouchDB
def raw(method, url, **kwargs):
    return db.request(method, url, **kwargs)


def couch(method, path="", **kwargs):
    return db.couch(method, path, **kwargs)


def ensure_db():
    initialize(db, seed=False)


def save(doc):
    return db.save(doc)


def get(doc_id):
    return db.get(doc_id)


def find(selector, fields=None, limit=100):
    return db.find(selector, fields, limit)


def preparar_produto_para_exibicao(produto):
    """Usa os metadados importados, mantendo compatibilidade com produtos antigos."""
    produto_exibicao = enrich(produto)
    produto_exibicao["nome"] = produto.get("nome") or produto["carta_api_id"]
    produto_exibicao["categoria"] = produto.get("categoria") or "One Piece TCG"
    return produto_exibicao


def agrupar_por_carta(produtos):
    """Conserva cada produto/arte no banco e agrupa somente a vitrine."""
    grupos = {}
    for produto in produtos:
        chave = produto["carta_api_id"]
        grupo = grupos.setdefault(chave, {"carta_api_id": chave, "variantes": []})
        grupo["variantes"].append(produto)
    cartas = []
    for grupo in grupos.values():
        variantes = sorted(grupo["variantes"], key=lambda item: item["_id"])
        # A primeira opção comprável é a arte inicial; as demais continuam acessíveis no modal.
        selecionada = next((item for item in variantes if item.get("ativo") and
                            item.get("estoque", 0) > 0 and item.get("preco") is not None), variantes[0])
        cartas.append({**selecionada, "variantes": variantes,
                       "total_variantes": len(variantes)})
    return cartas


# Dados mínimos para estudo antes da integração com a API de cartas
def seed():
    initialize(db)


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
    todos = [enrich(product) for product in all_products()]
    options = {field: sorted({p.get(field) or "—" for p in todos})
               for field in ("grupo", "colecao", "cor", "raridade", "categoria")}
    produtos = agrupar_por_carta(todos)
    q = request.args.get("q", "").strip()[:150]
    selected_filters = {field: request.args.get(field) for field in options if request.args.get(field)}

    def matching_variants(card):
        matches = card["variantes"]
        if q:
            matches = [item for item in matches if q.casefold() in
                       (item.get("nome", "") + " " + item["carta_api_id"] + " " +
                        item.get("variante_api_id", "")).casefold()]
        for field, value in selected_filters.items():
            matches = [item for item in matches if item.get(field) == value]
        if request.args.get("estoque") == "1":
            matches = [item for item in matches if item.get("estoque", 0) > 0 and item.get("preco") is not None]
        return matches

    filtrados = []
    for card in produtos:
        matches = matching_variants(card)
        if matches:
            selected = next((item for item in matches if item.get("ativo") and
                             item.get("estoque", 0) > 0 and item.get("preco") is not None), matches[0])
            filtrados.append({**selected, "variantes": card["variantes"],
                              "total_variantes": card["total_variantes"]})
    produtos = filtrados
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
    featured = [p for p in agrupar_por_carta(todos) if p["carta_api_id"] in
                ("OP01-001", "OP01-003", "OP05-119") and p.get("imagem")][:3]
    return render_template("catalogo.html", produtos=produtos[(page-1)*24:page*24],
                           total=total, total_catalogo=len(agrupar_por_carta(todos)),
                           total_variantes=len(todos), options=options,
                           page=page, pages=pages, page_url=page_url, featured=featured)


def all_products():
    return db.find_all({"tipo": "produto", "ativo": True})


@app.post("/carrinho/adicionar/<path:produto_id>")
def adicionar(produto_id):
    if not valid_form_csrf():
        flash("O formulário expirou. Tente novamente.")
        return redirect(url_for("catalogo"))
    if not re.fullmatch(r"produto:[A-Za-z0-9._:-]{1,160}", produto_id):
        flash("Carta inválida.")
        return redirect(url_for("catalogo"))
    produto = get(produto_id)
    if not produto or not produto.get("ativo") or produto.get("preco") is None:
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
        produto_salvo = get(produto_id)
        if not produto_salvo:
            continue
        produto = preparar_produto_para_exibicao(produto_salvo)
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
        if not valid_form_csrf():
            flash("O formulário expirou. Tente novamente.")
            return redirect(url_for("cadastro"))
        senha = request.form.get("senha", "")
        confirmacao = request.form.get("confirmacao", "")
        if senha != confirmacao:
            flash("As senhas não coincidem.")
            return render_template("cadastro.html")
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not 2 <= len(nome) <= 80 or any(ord(char) < 32 for char in nome):
            flash("Informe um nome válido (2 a 80 caracteres).")
            return render_template("cadastro.html"), 422
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            flash("Informe um e-mail válido.")
            return render_template("cadastro.html"), 422
        if not 8 <= len(senha) <= 128:
            flash("A senha deve ter entre 8 e 128 caracteres.")
            return render_template("cadastro.html"), 422
        cliente_existente = find({"tipo": "cliente", "email": email}, limit=1)
        if cliente_existente:
            flash("E-mail já cadastrado.")
            return render_template("cadastro.html")

        # UUID5 dá ao e-mail normalizado uma identidade determinística: em uma corrida,
        # CouchDB devolve 409 para a segunda criação em vez de aceitar dois clientes.
        cliente = {
            "_id": f"cliente:{uuid.uuid5(uuid.NAMESPACE_URL, 'cliente:' + email)}",
            "tipo": "cliente",
            "nome": nome,
            "email": email,
            "senha_hash": generate_password_hash(senha),
            "criado_em": datetime.now(timezone.utc).isoformat(),
        }
        try:
            save(cliente)
        except DatabaseError as error:
            if error.status != 409:
                raise
            flash("E-mail já cadastrado.")
            return render_template("cadastro.html")
        flash("Cadastro realizado.")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not valid_form_csrf():
            flash("O formulário expirou. Tente novamente.")
            return redirect(url_for("login"))
        email = request.form.get("email", "").strip().lower()[:254]
        senha = request.form.get("senha", "")[:128]
        clientes = find({"tipo": "cliente", "email": email}, limit=1)

        credenciais_invalidas = not clientes or not check_password_hash(
            clientes[0].get("senha_hash", ""), senha
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


@app.post("/logout")
def logout():
    if not valid_form_csrf():
        flash("O formulário expirou. Tente novamente.")
        return redirect(url_for("catalogo"))
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

    token = session.setdefault("checkout_token", str(uuid.uuid4()))
    entrega = {"nome": clientes[0].get("nome", "")}
    erros = {}
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf_token", ""), token):
            flash("O formulário expirou. Revise a entrega e tente novamente.")
            return redirect(url_for("checkout"))
        entrega, erros = validar_entrega(request.form)

    itens_do_pedido = []
    total = 0.0

    for produto_id, quantidade in carrinho_atual.items():
        produto = get(produto_id)
        if not produto:
            flash("Uma carta do carrinho não existe mais.")
            return redirect(url_for("carrinho"))
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
                "variante_api_id": produto.get("variante_api_id", produto["_id"]),
                "imagem": produto_exibicao.get("imagem", ""),
                "nome": produto_exibicao["nome"],
                "quantidade": quantidade,
                "preco_unitario": preco_unitario,
                "subtotal": subtotal,
            }
        )

        total += subtotal
    if request.method == "GET" or erros:
        return render_template("checkout.html", entrega=entrega, erros=erros,
                               estados=ESTADOS, itens=itens_do_pedido,
                               total=round(total, 2), csrf_token=token), (422 if erros else 200)

    try:
        pedido = place_order(db, session["cliente_id"], carrinho_atual, entrega, token)
    except CheckoutError as error:
        app.logger.warning("checkout_rejected request_id=%s reason=%s", g.request_id, error)
        session.pop("checkout_token", None)
        flash(str(error))
        return redirect(url_for("carrinho"))

    if pedido.get("status") != "CONFIRMADO":
        raise DatabaseError(503, "Pedido sem confirmação")
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


@app.cli.command("setup-user")
def setup_user():
    """Execute pelo serviço admin; o servidor web usa somente o usuário da loja."""
    application_user(db)
    print("Usuário da aplicação configurado, sem privilégios de administrador.")


@app.cli.command("sync-cards")
def sync_cards():
    """Atualiza preço (USD × 5) e cache; preserva estoque e ativo."""
    try:
        cards = fetch_cards()
        save_cache(import_cards(cards))
    except (requests.RequestException, ValueError, DatabaseError):
        raise click.ClickException("Sincronização incompleta. Cache anterior preservado; execute novamente. Credenciais omitidas.") from None


@app.cli.command("recover-checkouts")
def recover_checkouts():
    """Compensa reservas deixadas por uma interrupção durante o checkout."""
    recovered = recover_pending(db)
    click.echo(f"{len(recovered)} pedido(s) pendente(s) processado(s).")


def import_cards(cards):
    # init-db é uma etapa administrativa separada. Sincronizar não cria índices.
    # Migração suave: versões anteriores usavam o ID da imagem no _id. Reutilize-o
    # quando a mesma URL já existir, preservando estoque, pedidos e carrinhos.
    existing_products = db.find_all({"tipo": "produto"})
    existing_by_image = {item.get("imagem"): item for item in existing_products if item.get("imagem")}
    synchronized = {}
    for metadata in cards.values():
        previous = existing_by_image.get(metadata.get("imagem"))
        if previous:
            metadata = {**metadata, "_id": previous["_id"]}
        synchronized[metadata["_id"]] = metadata
    ids = list(synchronized)
    count = 0
    changed = 0
    for start in range(0, len(ids), 200):
        keys = ids[start:start+200]
        rows = couch("POST", "/_all_docs?include_docs=true", json={"keys": keys})["rows"]
        existing = {r["id"]: r.get("doc") for r in rows if "id" in r}
        documents = [merge_card(synchronized[k], existing.get(k)) for k in keys]
        documents = [document for document in documents if document is not existing.get(document["_id"])]
        if not documents:
            continue
        results = db.bulk(documents)
        for document, result in zip(documents, results):
            if result.get("id") != document["_id"]:
                raise DatabaseError(503, "Identificador inesperado no lote")
            if result.get("error") == "conflict":
                for attempt in range(3):
                    current = get(document["_id"])
                    try:
                        save(merge_card(synchronized[document["_id"]], current))
                        break
                    except DatabaseError as error:
                        if error.status != 409 or attempt == 2:
                            raise
            elif not result.get("ok"):
                raise DatabaseError(503, "Falha individual na sincronização")
        count += len(results)
        changed += len(documents)
    # Uma versão antiga do normalizador criou IDs ``art-...`` quando a API não
    # trazia URL de imagem. A fonte atual já oferece a variante equivalente. Não
    # apagamos esses documentos (podem ser úteis em histórico), mas retiramos da
    # vitrine somente os legados sem estoque e sem identidade de variante.
    legacy = [item for item in existing_products if item.get("origem") == "optcgapi.com" and
              not item.get("variante_api_id") and item.get("ativo") and item.get("estoque") == 0]
    for start in range(0, len(legacy), 200):
        batch = []
        for item in legacy[start:start+200]:
            item.update(ativo=False, substituido_por="sincronizacao_api_atual", atualizado_em=now())
            batch.append(item)
        results = db.bulk(batch)
        if any(not result.get("ok") for result in results):
            raise DatabaseError(503, "Falha ao arquivar projeção legada")
    archived = len(legacy)
    app.logger.info("catalog_sync products=%s changed=%s priced=%s", len(synchronized), changed,
                    sum(c.get("preco") is not None for c in synchronized.values()))
    print(f"{len(synchronized)} variantes verificadas; {changed} atualizadas; {archived} legadas arquivadas.")
    return synchronized


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
