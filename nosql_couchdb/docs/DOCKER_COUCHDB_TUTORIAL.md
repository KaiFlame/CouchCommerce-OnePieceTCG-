# Docker + CouchDB: mini relatório-tutorial

Verificado em 15/09/2026, horário de Brasília. Ambiente local do CouchCommerce One Piece TCG.

## 1. O que ficou pronto

Docker Engine 29.8.0 e Compose v5.5.1 estão funcionando. CouchDB 3.5.2 e Flask/Gunicorn
estão em contêineres separados, ambos `healthy`. O banco `ecommerce_facamp` contém os
três produtos do seed e quatro índices Mango. Não foi feita a importação externa de cartas.

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
docker compose build app
docker compose run --rm --no-deps app flask --app app init-db
```

- `up`: cria/inicia o banco; `-d`: libera o terminal; `--wait`: aguarda saúde.
- `build app`: prepara a imagem Python do projeto.
- `run --rm`: usa essa imagem para executar `init-db` e remove somente esse contêiner temporário.
- `init-db`: cria `ecommerce_facamp`, três produtos e índices. Não apaga produtos já existentes.

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

Resultado esperado: três produtos. O seed tem códigos, preços de estudo e estoques;
nomes, imagens e filtros completos dependem da futura sincronização com a API.

## 5. Repetir as verificações

```powershell
docker compose exec app python -m pytest -q
docker compose exec app python scripts/verificar_couchdb.py
docker compose logs --tail 30 couchdb app
docker stats --no-stream
```

Comprovamos: seis testes aprovados; consultas Mango usando os quatro índices;
acesso anônimo ao banco recusado com 401; revisão antiga recusada com 409;
falha parcial em `_bulk_docs`; quatro páginas Flask retornando 200.
O script cria e remove somente um banco temporário próprio para os testes de escrita.
Ele não realiza compras em `ecommerce_facamp`.

Recriamos o contêiner do banco mantendo seu volume e repetimos `init-db`:
os produtos mantiveram IDs, revisões, preços e estoques.
Isso comprova persistência e repetição segura do seed neste cenário, não backup nem
idempotência de checkout. Os resultados estão em [evidencias_docker.json](evidencias_docker.json).

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

## 7. Ajustes e próximos passos

Corrigimos variáveis ausentes no exemplo, proteção do `.env` no Git/build, configuração
single-node e permissões do arquivo INI. Fixamos as imagens-base por digest, separamos
Flask no perfil `web`, adicionamos verificações de saúde e logs HTTP do Gunicorn.
As regras de negócio de `app.py` e a integração em `card_catalog.py` foram preservadas.

O reparo anterior do Windows concluiu WSL/virtualização. Pastas de sockets do Docker
foram movidas para backups locais recuperáveis; não eram dados do CouchDB.
Nesta etapa não foi necessário login externo, alteração na BIOS nem nova reinicialização.

Próximo passo didático: inspecionar esses três documentos e a consulta acima no Fauxton.
Depois, seguir a [auditoria de aderência](ADERENCIA_PROFESSOR.md), que registra as pendências
antes da entrega. O ambiente está pronto; o projeto completo ainda não está finalizado.

Referências técnicas: [CouchDB single-node](https://docs.couchdb.org/en/stable/setup/single-node.html),
[CouchDB em Docker](https://docs.couchdb.org/en/stable/install/docker.html),
[variáveis no Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[CLI Flask e dotenv](https://flask.palletsprojects.com/en/stable/cli/#environment-variables-from-dotenv).
