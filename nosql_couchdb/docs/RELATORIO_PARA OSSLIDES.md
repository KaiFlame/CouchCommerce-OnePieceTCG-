## Requisitos funcionais

| Requisito | Demonstração |
|---|---|
| RF01 — listar produtos | `GET /`, busca/filtros e paginação do catálogo |
| RF02 — cadastrar cliente | `GET/POST /cadastro`, hash de senha e e-mail único |
| RF03 — autenticar | `GET/POST /login`, sessão e `POST /logout` com CSRF |
| RF04 — finalizar pedido | `/carrinho` → `/checkout` → `pedido:...` e baixa de estoque |
| RF05 — consultar histórico | `GET /pedidos`, consulta Mango por `cliente_id` |

## Por que CouchDB/NoSQL

O catálogo é uma projeção documental de variantes de carta, com campos variáveis vindos
da API e leitura direta para vitrine/filtros. Pedido é um agregado que embute o snapshot
imutável dos itens; CouchDB atende esses padrões via JSON/REST, Mango e MVCC por `_rev`.

## Rastreabilidade

| Requisito dos slides | Implementação | Evidência |
|---|---|---|
| Documentos e agregados | Três tipos, IDs prefixados e `schema_version` | Fauxton e `setup_db.py` |
| Referência e embed | Pedido referencia cliente/produto e embute itens | `checkout_service.py` |
| Docker e CouchDB | Serviços isolados, volumes e healthchecks | `docker compose ps` |
| Mango e índices | Seis índices coerentes com as consultas | `scripts/verificar_couchdb.py` |
| `_id`, `_rev` e 409 | Reservas otimistas com três tentativas | testes e verificador |
| `_bulk_docs` não ACID | Falha parcial demonstrada e resultados conferidos | verificador |
| Consistência do checkout | Idempotência, estoque não negativo, compensação e snapshot da arte | testes + E2E |
| Senhas e segredos | Hash Werkzeug, `.env`, conta CouchDB restrita e CSRF | código + HTTP 401 anônimo |
| Testes de integração | Carta real, escolha de arte, cadastro e pedido confirmado em banco isolado | `evidencias/fluxo_completo.json` |
| Replicação | Segunda instância, conteúdo comparado por SHA-256 | `evidencias/replicacao.json` |
| Backup e restore | Backup lógico e restauração em banco novo | `evidencias/backup.json` e `restore.json` |
| Observabilidade | `/health`, request ID, duração e logs de falha | healthcheck do Compose |
| Deploy | Execução local reproduzível | README; cloud é opcional nos slides |

## Índices Mango

| Consulta | Índice |
|---|---|
| Produtos ativos | `idx_tipo_ativo`: `tipo`, `ativo` |
| Produto por código | `idx_tipo_carta_api_id`: `tipo`, `carta_api_id` |
| Produto por categoria | `idx_tipo_categoria`: `tipo`, `categoria` |
| Cliente por e-mail | `idx_tipo_email`: `tipo`, `email` |
| Pedidos do cliente | `idx_tipo_cliente`: `tipo`, `cliente_id` |
| Pedidos por status | `idx_tipo_status`: `tipo`, `status` |

Os demais filtros visuais são aplicados em memória porque o catálogo é carregado uma vez
por requisição. `_explain` confirma a seleção dos seis índices obrigatórios.

## Limites declarados

- A OPTCG API é um fornecedor externo; o catálogo continua com banco/cache se ela falhar.
- O backup é lógico: preserva o conteúdo, mas cria novas revisões MVCC na restauração.
- O deploy em nuvem não foi criado porque não havia infraestrutura no repositório e o
  material o apresenta como opcional.
- Os JSONs de evidência omitem credenciais, endereços e senhas.
