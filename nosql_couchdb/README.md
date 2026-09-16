# FACAMP NoSQL Shop — Apache CouchDB + Flask

Comece pelo [mini relatório-tutorial de Docker e CouchDB](docs/DOCKER_COUCHDB_TUTORIAL.md).
A [auditoria dos slides](docs/ADERENCIA_PROFESSOR.md) separa o que foi comprovado
do que ainda falta na aplicação e na entrega.

## Catálogo de cartas OPTCG

O catálogo importa apenas cartas avulsas: coleções, cartas de starter decks,
promocionais e DON!!. Para atualizar os dados, com CouchDB ativo:

```powershell
docker compose exec app flask --app app sync-cards
```

A sincronização faz quatro consultas à OPTCG API. As visitas ao catálogo leem
somente o CouchDB; as imagens são carregadas do provedor sob demanda.
Preços, estoques e estado ativo existentes são preservados. Novas cartas ficam
com preço não definido e estoque zero até configuração da loja. Os preços de
mercado da API não são convertidos nem usados como preços de venda em reais.

Artes diferentes recebem identificadores próprios, mesmo quando compartilham
o código da carta. Entradas com a mesma imagem são deduplicadas. Algumas cartas
não têm imagem na fonte; o catálogo sinaliza isso sem substituir sua arte.
Não há atualização automática: execute sync-cards quando necessário.

Validação: `docker compose exec app python -m pytest -q`.

Projeto didático completo para comparar modelagem documental com o projeto relacional.

## Execução
Na pasta `nosql_couchdb`, com Docker Desktop aberto:

```powershell
python scripts/preparar_env.py
docker compose config --quiet
docker compose up -d --build --wait couchdb
docker compose build app
docker compose run --rm --no-deps app flask --app app init-db
docker compose --profile web up -d --wait app
docker compose ps
```

Site: `http://127.0.0.1:5000`. Fauxton: `http://127.0.0.1:5984/_utils/`.
O login do Fauxton usa `COUCHDB_USER` e `COUCHDB_PASSWORD` do `.env` local.
O seed cria somente três cartas ficticiamente precificadas; `sync-cards` é uma etapa separada.

O perfil `web` controla o Flask em Docker. Sem esse perfil, `up` inicia só o banco.
Para desenvolver Flask na `.venv`, primeiro pare `app` com `docker compose stop app`;
instale `requirements.txt` e use `python -m flask --app app run --debug`.
`python-dotenv` faz o CLI Flask ler `.env` automaticamente. Execute pela pasta do projeto.
`python app.py` não carrega esse arquivo automaticamente: prefira o comando Flask acima.

Dentro do Docker, Flask conecta em `couchdb:5984`; no Windows, em `127.0.0.1:5984`.
Dados ficam no volume `couchdb_data`. Não use `docker compose down -v` se quiser preservá-los.

## Conceitos praticados
- documentos JSON e agregados
- embed x reference
- `_id` e `_rev`
- Mango Query e índices
- REST/HTTP
- concorrência otimista
- `_bulk_docs` e limites de atomicidade
- replicação, segurança e monitoramento

## Importante
`_bulk_docs` não é transação ACID multi-documento. O exercício de checkout serve para discutir conflito, retry, idempotência e compensação.
