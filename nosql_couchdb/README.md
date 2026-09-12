# FACAMP NoSQL Shop — Apache CouchDB + Flask

Projeto didático completo para comparar modelagem documental com o projeto relacional.

## Execução
1. `docker compose up -d`
2. `python -m venv .venv`
3. Ative a venv e rode `pip install -r requirements.txt`
4. Configure as variáveis de `.env.example` no terminal
5. `flask --app app init-db`
6. `flask --app app run --debug`
7. Abra `http://127.0.0.1:5000`
8. Fauxton: `http://127.0.0.1:5984/_utils/`

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
