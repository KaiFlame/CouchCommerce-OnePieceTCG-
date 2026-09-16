# Auditoria: professor, conversa e repositório

Data: 15/09/2026. Fontes lidas: os HTMLs `facamp_tai_projeto_pratico_nosql_couchdb_animacao_interativa_v3.html`
e `facamp_tai_nosql_ciclo_completo_animacao_interativa r1.html`, em Downloads.
Os números abaixo são os títulos numerados dos slides, não a posição no navegador.

## Decisão de modelagem em vigor

A decisão mais recente da conversa substituiu `usuario/estoque/compra` por
`cliente/produto/pedido`, próximos do exemplo do professor. O repositório segue essa decisão:
produto guarda `carta_api_id`, preço e estoque; cliente guarda hash; pedido referencia
cliente e embute itens com código, nome, quantidade, preço unitário e subtotal.
O histórico usa esses snapshots, sem consultar a API externa.

Existe uma diferença a decidir: `card_catalog.py` já importa nome, imagem, coleção,
raridade, cor, poder, custo e efeito para `produto`. O catálogo lê o banco e não consulta
a API em cada visita. Isso é denormalização possível no modelo documental, mas ultrapassa
a proposta mais recente de guardar apenas código/preço/estoque. Esta configuração não
mudou essa implementação nem executou `sync-cards`.

Novas cartas importadas têm `preco=null` e estoque zero; preço automático por raridade
ainda não existe. O seed usa preços manuais fictícios. Variantes de arte podem ter IDs
diferentes do código da carta; `carta_api_id` é a referência usada na consulta.

A aplicação segue Flask/Jinja do kit. A Macro API JSON separada, mencionada antes na conversa,
ainda não existe. Não é necessário criá-la para reproduzir o kit; se o front separado for
mantido, será preciso acordar esse contrato com seu amigo.

## Rastreabilidade

| Professor | Adaptação / evidência atual | Situação |
|---|---|---|
| Projeto 6, 9: requisitos e padrões de acesso | Fluxo catálogo/cadastro/login/carrinho/checkout/histórico no código; falta consolidar requisitos e justificativa NoSQL | Parcial |
| Projeto 10–17: documentos, embed/reference, snapshots | Três tipos do professor; itens embutidos em pedido e referências a cliente/produto; falta formalizar esquema e sua versão | Parcial |
| Projeto 18–21: Docker, Fauxton, database | CouchDB 3.5.2, nó único, volume, localhost:5984 e `ecommerce_facamp` | Verificado |
| Projeto 16, 23–24: consultas e índices Mango | Índices `tipo+ativo`, `tipo+carta_api_id`, `tipo+email`, `tipo+cliente_id`; uso comprovado com `_explain` | Verificado para essas consultas |
| Projeto 16, 24 e roteiro Fauxton: categoria | Filtro atual de categoria ocorre em Python após carregar o catálogo; não existe índice `tipo+categoria` no seed | Pendente se reproduzir essa consulta Mango |
| Projeto 25: `_id`, `_rev`, conflito | PUT com revisão antiga retornou 409 em banco isolado | Verificado |
| Projeto 26, 36, 39–41: `_bulk_docs` e consistência | Lote de teste gravou pedido e rejeitou produto; checkout verifica erros, mas não compensa sucesso parcial | Parcial, risco de negócio aberto |
| Projeto 29–38: Flask e sessão | Flask conectado por HTTP; catálogo/login/cadastro/carrinho retornam 200; sessão e snapshots estão no código | Parcial: fluxo autenticado completo ainda não testado |
| Projeto 42: testes | Seis testes existentes aprovados + script de integração real de infraestrutura; os testes básicos não exercitam checkout | Parcial |
| Projeto 43: segurança | Hash no código, segredos locais aleatórios, `.env` ignorado no Git/imagem, localhost e bloqueio anônimo 401 | Parcial: aplicação ainda usa admin, há defaults fracos e falta proteção de produção |
| Projeto 27, 44: replicação, backup e restore | Volume persiste após recriar contêiner; não houve replicação nem restauração de backup | Pendente; volume não é backup |
| Projeto 7, 45 e NoSQL 61: observabilidade | Healthchecks, logs HTTP e amostra de CPU/memória/I/O em evidência; falta endpoint dedicado de saúde e rotina com alertas | Parcial |
| Projeto 47–50, 55: implantação e evidências | Implantação local reproduzível, tutorial e evidência JSON; acesso externo/cloud não configurado | Local pronto; cloud é opcional no slide 7 |

## Índices que realmente existem

| Consulta | Índice |
|---|---|
| Produtos ativos | `idx_tipo_ativo`: tipo, ativo |
| Produto por código externo | `idx_tipo_carta_api_id`: tipo, carta_api_id |
| Cliente por e-mail | `idx_tipo_email`: tipo, email |
| Pedidos por cliente | `idx_tipo_cliente`: tipo, cliente_id |

As consultas de clientes/pedidos retornam zero porque ainda não há clientes ou pedidos
no banco da loja. `_explain` confirma a seleção do índice, não desempenho sob carga.
Consulta/índice por status de pedido, presente no planejamento anterior, ainda é pendência.
Filtros atuais de cor/raridade/coleção não são Mango: são aplicados em memória no Flask.

## Limites importantes antes da entrega

- [ ] Confirmar com a dupla se os metadados importados serão cache local ou se voltaremos ao produto mínimo.
- [ ] Definir requisitos, exemplos JSON, esquema/versionamento e contrato do front.
- [ ] Definir o cálculo de preço, validar entradas e proibir estoque negativo inclusive em concorrência.
- [ ] Completar checkout: checar cada resultado, retry limitado, idempotência e compensação durável.
- [ ] Testar cadastro/login, checkout normal, falha parcial, concorrência e histórico de ponta a ponta.
- [ ] Criar consultas/índices adicionais apenas quando usados; praticar categoria conforme o roteiro do professor.
- [ ] Separar conta administrativa de conta da aplicação; remover defaults inseguros, tratar CSRF e validar entradas.
- [ ] Demonstrar replicação para outra instância e testar backup/restore, com metas RPO/RTO.
- [ ] Adicionar endpoint de saúde e registrar três métricas com limites e ações de resposta.
- [ ] Organizar prints do Fauxton, modelos, queries e evidências finais. Se publicar fora do PC, configurar TLS e segredos.

Retry/idempotência/compensação foram compromissos da conversa e estratégias discutidas
pelo professor. A compensação também aparece como extensão no slide 51; não foi tratada
como algo já implementado. Cloud é opção de hospedagem, não obrigação de contratar serviço.
O material NoSQL geral apresenta outras famílias de banco como conteúdo comparativo,
não como obrigação de adicionar Redis, MongoDB ou outro banco ao projeto CouchDB.

## O que a configuração alterou

Compose, Dockerfiles, `.env.example`, exclusões Git/build, dependência `python-dotenv`, README,
scripts de preparação/verificação e esta documentação. O arquivo `.env` local é privado.
Não houve commit/push, alteração de regra de compra nem sincronização com API externa.
As evidências estão em [evidencias_docker.json](evidencias_docker.json).
