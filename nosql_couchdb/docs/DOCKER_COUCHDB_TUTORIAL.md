# Docker + CouchDB: mini relatório-tutorial

Atualizado em 16/09/2026. Ambiente local do CouchCommerce One Piece TCG.

## 1. O que ficou pronto

Docker Engine 29.8.0 e Compose v5.5.1 estão funcionando. CouchDB 3.5.2 e Flask/Gunicorn
estão em contêineres separados e `healthy`. O banco contém 5.549 cartas reais importadas,
seis índices Mango e regras de validação documental.

O navegador acessa Flask na porta 5000. Flask acessa CouchDB pela rede do Compose,
usando `couchdb:5984`. Fauxton é a interface administrativa do CouchDB, na porta 5984.
O volume `nosql_couchdb_couchdb_data` guarda os dados independentemente do contêiner.

O WSL é a base Linux usada pelo Docker Desktop; você não precisa abrir Ubuntu para trabalhar.
A `.venv` isola dependências Python quando Flask roda no Windows. Dentro do contêiner,
as dependências já estão instaladas na imagem.

## 2. Preparar o projeto — uma vez por computador

Abra o Docker Desktop e um PowerShell. Entre na pasta:

```powershell
cd 'C:\Users\Guilherme\Documents\GitHub\CouchCommerce-OnePieceTCG-\nosql_couchdb'
python scripts/preparar_env.py
docker compose config --quiet
```

O primeiro comando Python gera `.env` com senha e chave aleatórias. Se ele já existir,
preserva seu conteúdo. O segundo valida o Compose sem imprimir os segredos.
Neste computador, essa preparação já foi feita. Não envie `.env` ao GitHub.

## 3. Subir banco e inicializar — slides 19–24

```powershell
docker compose up -d --build --wait couchdb
docker compose --profile tools build admin
docker compose --profile tools run --rm admin flask --app app init-db
docker compose --profile tools run --rm admin flask --app app setup-user
docker compose --profile tools run --rm admin flask --app app sync-cards
```

- `up`: cria/inicia o banco; `-d`: libera o terminal; `--wait`: aguarda saúde.
- `build admin`: prepara a mesma aplicação com credenciais administrativas apenas para tarefas.
- `run --rm`: remove somente o contêiner temporário, nunca o volume do banco.
- `init-db`: cria o banco, índices e validação; `setup-user` cria a conta restrita do site.
- `sync-cards`: importa/atualiza cartas e preços, preservando estoque e `_rev`.

A configuração `single_node=true` cria os bancos internos `_users` e `_replicator`.
Eles são infraestrutura do CouchDB, não novos tipos de documento da loja.

## 4. Abrir o site e o Fauxton

```powershell
docker compose --profile web up -d --wait app
docker compose ps
```

Abra o [site](http://127.0.0.1:5000) e o [Fauxton](http://127.0.0.1:5984/_utils/).
No Fauxton, use `COUCHDB_USER` e `COUCHDB_PASSWORD` do seu `.env`.
Você pode consultar esse arquivo localmente com `notepad .env`.
Essa conta administra o banco; é diferente do cadastro de cliente da loja.

Em **Databases → ecommerce_facamp → All Documents**, observe `produto:OP01-001`
e seu `_rev`. Em **Mango Query**, execute:

```json
{
  "selector": {"tipo": "produto", "ativo": true},
  "fields": ["_id", "carta_api_id", "preco", "estoque"]
}
```

Resultado esperado: cartas sincronizadas. O preço é o `market_price` da API multiplicado
por 5; cartas sem preço continuam disponíveis para consulta.

## 5. Repetir as verificações

```powershell
docker compose run --rm --no-deps app python -m pytest -q
docker compose --profile tools run --rm admin python scripts/verificar_couchdb.py
docker compose --profile tools run --rm admin python scripts/testar_fluxo.py
docker compose logs --tail 30 couchdb app
docker stats --no-stream
```

Comprovamos: 40 testes aprovados; consultas Mango usando seis índices;
acesso anônimo recusado com 401; revisão antiga recusada com 409; falha parcial em
`_bulk_docs`; health check e fluxo completo autenticado retornando resultados reais.
O script cria e remove somente um banco temporário próprio para os testes de escrita.
Ele não realiza compras em `ecommerce_facamp`.

Recriamos o contêiner do banco mantendo seu volume e repetimos `init-db`:
os produtos mantiveram IDs, revisões, preços e estoques.
Replicação, backup e restauração foram comprovados por checksum. Os resultados ficam
em `docs/evidencias`, e o backup completo privado em `.local/operations`.

## 6. Uso diário

Para parar preservando dados: `docker compose --profile web stop`.
Para voltar com o banco já inicializado: `docker compose --profile web up -d --wait`.
Depois de editar Python/templates, reconstrua a aplicação:
`docker compose --profile web up -d --build --wait app`.
O código é copiado para a imagem; não há atualização automática por volume de código.

Para desenvolver Flask no Windows, pare o contêiner `app` e use a `.venv`:

```powershell
docker compose stop app
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run --debug
```

O CLI Flask lê `.env` via `python-dotenv`. A URL local usa `127.0.0.1`, enquanto
o Compose substitui essa URL por `couchdb` dentro da aplicação em Docker.
Não rode os dois Flask na porta 5000 simultaneamente. Não use `down -v`: isso remove o volume.

## 7. Operações e entrega

```powershell
docker compose --profile ops up -d --wait couchdb-replica
docker compose --profile tools --profile ops run --rm admin python scripts/operacoes.py demo
```

O comando demonstra replicação para uma segunda instância, backup lógico com checksum e
restauração em banco novo. Ele não sobrescreve `ecommerce_facamp`.

O reparo anterior do Windows concluiu WSL/virtualização. Pastas de sockets do Docker
foram movidas para backups locais recuperáveis; não eram dados do CouchDB.
Nesta etapa não foi necessário login externo, alteração na BIOS nem nova reinicialização.

Para a apresentação, inspecione um `produto`, `cliente` e `pedido` no Fauxton e mostre
os JSONs de `docs/evidencias`. Deploy em nuvem não foi criado porque o material o trata
como opcional e não havia infraestrutura de deploy no repositório.

Referências técnicas: [CouchDB single-node](https://docs.couchdb.org/en/stable/setup/single-node.html),
[CouchDB em Docker](https://docs.couchdb.org/en/stable/install/docker.html),
[variáveis no Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[CLI Flask e dotenv](https://flask.palletsprojects.com/en/stable/cli/#environment-variables-from-dotenv).
