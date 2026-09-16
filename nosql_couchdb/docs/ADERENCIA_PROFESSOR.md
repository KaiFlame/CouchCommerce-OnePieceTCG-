# Aderência aos slides e evidências

Atualizado em 16/09/2026 após execução real. Referências: HTMLs da disciplina sobre o
ciclo NoSQL e o projeto prático CouchDB.

## Modelagem adotada

A aplicação mantém o exemplo didático do professor: `produto`, `cliente` e `pedido`.
`produto` substitui o produto genérico por uma carta identificada por `carta_api_id`.
O preço é calculado como `market_price USD × 5`; estoque e ativo são regras locais.

O CouchDB guarda nome, imagem, coleção e propriedades usadas na vitrine/filtros para
reduzir dependência externa. Efeito, poder e custo permanecem no cache da API. O pedido
referencia cliente/produto e embute o snapshot dos itens. Assim, o histórico não muda
quando a API ou o produto mudam.

## Rastreabilidade

| Requisito dos slides | Implementação | Evidência |
|---|---|---|
| Documentos e agregados | Três tipos, IDs prefixados e `schema_version` | Fauxton e `setup_db.py` |
| Referência e embed | Pedido referencia cliente/produto e embute itens | `checkout_service.py` |
| Docker e CouchDB | Serviços isolados, volumes e healthchecks | `docker compose ps` |
| Mango e índices | Seis índices coerentes com as consultas | `scripts/verificar_couchdb.py` |
| `_id`, `_rev` e 409 | Reservas otimistas com três tentativas | testes e verificador |
| `_bulk_docs` não ACID | Falha parcial demonstrada e resultados conferidos | verificador |
| Consistência do checkout | Idempotência, estoque não negativo e compensação | 40 testes |
| Senhas e segredos | Hash Werkzeug, `.env`, conta CouchDB restrita e CSRF | código + HTTP 401 anônimo |
| Testes de integração | Carta real até pedido confirmado em banco isolado | `evidencias/fluxo_completo.json` |
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
