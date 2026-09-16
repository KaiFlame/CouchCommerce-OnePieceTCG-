"""Verifica a infraestrutura real; escreve somente em um banco temporario proprio.

Execute no container app, que ja recebe COUCHDB_URL pelo Compose.
Nao testa a seguranca do checkout: demonstra os mecanismos do CouchDB isoladamente.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import requests


def exigir(condicao, mensagem):
    if not condicao:
        raise RuntimeError(mensagem)


def main():
    url = urlsplit(os.environ["COUCHDB_URL"])
    base = f"{url.scheme}://{url.hostname}:{url.port or 5984}"
    banco = os.environ.get("COUCHDB_DATABASE", "ecommerce_facamp")
    sessao = requests.Session()
    sessao.auth = (unquote(url.username or ""), unquote(url.password or ""))

    def http(method, path, esperado=(200,), **kwargs):
        resposta = sessao.request(method, base + path, timeout=15, **kwargs)
        exigir(resposta.status_code in esperado,
               f"{method} {path}: HTTP {resposta.status_code}; esperado {esperado}")
        return resposta

    relatorio = {"verificado_em_utc": datetime.now(timezone.utc).isoformat()}
    relatorio["couchdb_version"] = http("GET", "/").json()["version"]
    exigir(http("GET", "/_up").json()["status"] == "ok", "Saude do banco")
    relatorio["saude_couchdb"] = "ok"
    bancos = http("GET", "/_all_dbs").json()
    exigir(all(nome in bancos for nome in (banco, "_users", "_replicator")),
           "Banco do projeto ou bancos de sistema ausentes")
    relatorio["bancos"] = bancos

    anonimo = requests.get(f"{base}/{banco}/_all_docs", timeout=10)
    exigir(anonimo.status_code in (401, 403), "Banco acessivel sem autenticacao")
    relatorio["acesso_anonimo_bloqueado_http"] = anonimo.status_code
    indices = http("GET", f"/{banco}/_index").json()["indexes"]
    nomes = sorted(i["name"] for i in indices if i["type"] == "json")
    exigir(set(("idx_tipo_ativo", "idx_tipo_carta_api_id", "idx_tipo_email",
                "idx_tipo_cliente")).issubset(nomes), "Indices minimos ausentes")
    relatorio["indices_json"] = nomes
    consultas = {
        "ativos": {"tipo": "produto", "ativo": True},
        "carta": {"tipo": "produto", "carta_api_id": "OP01-001"},
        "cliente_email": {"tipo": "cliente", "email": "teste@example.invalid"},
        "pedidos_cliente": {"tipo": "pedido", "cliente_id": "cliente:teste"},
    }
    relatorio["mango"] = {}
    for nome, selector in consultas.items():
        query = {"selector": selector, "limit": 100}
        plano = http("POST", f"/{banco}/_explain", json=query).json()
        exigir(plano["index"]["type"] == "json", f"Indice nao utilizado: {nome}")
        docs = http("POST", f"/{banco}/_find", json=query).json()["docs"]
        relatorio["mango"][nome] = {"indice": plano["index"]["name"], "resultados": len(docs)}

    produtos = http("POST", f"/{banco}/_find", json={
        "selector": {"tipo": "produto"}, "limit": 1000,
        "fields": ["_id", "_rev", "carta_api_id", "preco", "estoque"],
    }).json()["docs"]
    exigir(len(produtos) >= 3, "Seed nao encontrado")
    relatorio["produtos"] = produtos

    temporario = "verificacao_docker_" + uuid.uuid4().hex
    criado = False
    try:
        http("PUT", f"/{temporario}", esperado=(201, 202))
        criado = True
        caminho = f"/{temporario}/produto:teste"
        produto = {"_id": "produto:teste", "tipo": "produto", "estoque": 2, "preco": 10}
        rev1 = http("PUT", caminho, esperado=(201, 202), json=produto).json()["rev"]
        antigo = {**produto, "_rev": rev1, "estoque": 1}
        rev2 = http("PUT", caminho, esperado=(201, 202), json=antigo).json()["rev"]
        exigir(rev1 != rev2, "Revisao nao mudou")
        http("PUT", caminho, esperado=(409,), json=antigo)
        relatorio["conflito_rev_http"] = 409

        # HTTP 201 do lote nao significa sucesso de cada documento.
        lote = http("POST", f"/{temporario}/_bulk_docs", esperado=(201, 202), json={
            "docs": [antigo, {"_id": "pedido:teste", "tipo": "pedido", "itens": []}],
        }).json()
        exigir(len(lote) == 2, "Resultado de lote incompleto")
        exigir(lote[0].get("error") == "conflict" and lote[1].get("ok") is True,
               "Falha parcial esperada nao observada")
        exigir(http("GET", caminho).json()["estoque"] == 1, "Conflito mudou estoque")
        http("GET", f"/{temporario}/pedido:teste")
        relatorio["bulk_nao_atomico"] = {"produto": "conflict", "pedido": "gravado"}
    finally:
        # Nunca apaga ecommerce_facamp: somente o banco aleatorio criado acima.
        if criado:
            http("DELETE", f"/{temporario}", esperado=(200, 202))
            relatorio["banco_temporario_removido"] = True

    relatorio["rotas_flask"] = {}
    for path in ("/", "/login", "/cadastro", "/carrinho"):
        r = requests.get("http://app:5000" + path, timeout=15)
        exigir(r.status_code == 200, f"Flask {path}: HTTP {r.status_code}")
        relatorio["rotas_flask"][path] = r.status_code
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException:
        raise SystemExit("Falha de conexao; confira docker compose ps e os logs. Credenciais omitidas.")
