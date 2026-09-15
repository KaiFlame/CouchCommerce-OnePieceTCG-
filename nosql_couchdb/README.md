# FACAMP NoSQL Shop — Apache CouchDB + Flask

## Catálogo de cartas OPTCG

O catálogo importa apenas cartas avulsas: coleções, cartas de starter decks,
promocionais e DON!!. Para atualizar os dados, com CouchDB ativo:

```bash
python3 -m flask --app app sync-cards
python3 -m flask --app app run --port 5001
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

Validação: `python3 -m pytest -q`.

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
