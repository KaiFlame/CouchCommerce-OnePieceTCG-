# CouchCommerce — manual rápido

E-commerce didático de One Piece TCG com Flask, CouchDB e Docker. O banco mantém os
três documentos do exemplo do professor: `produto`, `cliente` e `pedido`.

## 1. Preparação

Abra o Docker Desktop e entre na pasta do projeto:

```powershell
cd 'C:\Users\Guilherme\Documents\GitHub\CouchCommerce-OnePieceTCG-\nosql_couchdb'
```

No macOS/Linux, use o caminho onde o repositório foi clonado e `python3` se necessário.

## 2. Primeira execução

```powershell
python scripts/preparar_env.py
docker compose config --quiet
docker compose up -d --wait couchdb
docker compose --profile tools build admin
docker compose --profile tools run --rm admin flask --app app init-db
docker compose --profile tools run --rm admin flask --app app setup-user
docker compose --profile tools run --rm admin flask --app app sync-cards
docker compose --profile web up -d --build --wait app
```

O carregamento inicial das cartas pode demorar. Os comandos podem ser repetidos sem
apagar produtos, estoques ou pedidos existentes.

## 3. Abrir e executar diariamente

- Loja: http://127.0.0.1:5000
- Saúde: http://127.0.0.1:5000/health
- CouchDB/Fauxton: http://127.0.0.1:5984/_utils/

Após a primeira configuração, basta iniciar com:

```powershell
docker compose --profile web up -d --wait
```

Depois de alterar código ou templates, reconstrua:

```powershell
docker compose --profile web up -d --build --wait app
```

## 4. Conferir o banco no Fauxton

1. Abra http://127.0.0.1:5984/_utils/.
2. Veja `COUCHDB_USER` e `COUCHDB_PASSWORD` no arquivo `.env` local.
3. Entre em **Databases → ecommerce_facamp → All Documents**.
4. Procure IDs iniciados por `produto:`, `cliente:` e `pedido:`.
5. Abra um documento e confira `_id`, `_rev`, `tipo` e os demais campos JSON.

Em **Mango Query**, teste:

```json
{
  "selector": {"tipo": "produto", "ativo": true},
  "fields": ["_id", "_rev", "carta_api_id", "nome", "preco", "estoque"],
  "limit": 10
}
```

Os seis índices atendem produtos ativos, código da carta, categoria, e-mail do cliente,
pedidos por cliente e pedidos por status.

## 5. Conferir automaticamente

```powershell
docker compose run --rm --no-deps app python -m pytest -q
docker compose --profile tools run --rm admin python scripts/verificar_couchdb.py
docker compose --profile tools run --rm admin python scripts/testar_fluxo.py
```

O esperado atualmente é `40 passed`. O teste completo usa um banco temporário e não
altera clientes, estoque ou pedidos da loja principal.

## 6. Atualizar cartas

```powershell
docker compose --profile tools run --rm admin flask --app app sync-cards
```

O preço didático é `market_price USD × 5`. A sincronização preserva estoque, estado
ativo e revisões. Se a API falhar, o site usa o CouchDB e o último cache válido.

## 7. Replicação, backup e restauração

```powershell
docker compose --profile ops up -d --wait couchdb-replica
docker compose --profile tools --profile ops run --rm admin python scripts/operacoes.py demo
```

O backup completo fica em `.local/operations`; evidências ficam em `docs/evidencias`.
A restauração sempre cria um banco novo e não sobrescreve `ecommerce_facamp`.

## 8. Parar sem perder dados

```powershell
docker compose --profile web --profile ops stop
```

Não use `docker compose down -v`: `-v` remove os volumes do banco. O `.env` contém
segredos locais e não deve ser enviado ao GitHub.

## Documentação complementar

- [Modelagem](docs/MODELAGEM.md)
- [Aderência aos requisitos](docs/ADERENCIA_PROFESSOR.md)
- [Tutorial detalhado](docs/DOCKER_COUCHDB_TUTORIAL.md)
