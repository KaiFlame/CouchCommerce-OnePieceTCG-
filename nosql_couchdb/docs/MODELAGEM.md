# Modelagem documental

## Produto

```json
{
  "_id": "produto:OP01-001",
  "_rev": "2-...",
  "tipo": "produto",
  "carta_api_id": "OP01-001",
  "variante_api_id": "OP01-001_p1",
  "nome": "Roronoa Zoro",
  "imagem": "https://optcgapi.com/...",
  "colecao": "Romance Dawn",
  "grupo": "Coleções",
  "cor": "Red",
  "raridade": "L",
  "categoria": "LEADER",
  "preco_usd": 2.15,
  "preco": 10.75,
  "estoque": 5,
  "ativo": true,
  "schema_version": 2,
  "origem": "optcgapi.com",
  "criado_em": "...",
  "atualizado_em": "..."
}
```

É a projeção comercial local de uma arte/variante. `carta_api_id` agrupa a carta lógica;
`variante_api_id` vem da identidade estável da arte na API (desambiguada pela URL somente
quando a fonte reutiliza o próprio ID). O frontend agrupa as variantes no detalhe, mas o
estoque, preço, carrinho e pedido sempre usam o `produto_id` da variante escolhida.
Efeito, poder e custo ficam no cache da integração e não são duplicados no CouchDB.

## Cliente

```json
{
  "_id": "cliente:<uuid>",
  "_rev": "1-...",
  "tipo": "cliente",
  "nome": "Pessoa Exemplo",
  "email": "pessoa@example.com",
  "senha_hash": "scrypt:...",
  "criado_em": "..."
}
```

A senha nunca é persistida nem registrada em log; apenas o hash. O e-mail é consultado
por índice Mango para cadastro e login.

## Pedido

```json
{
  "_id": "pedido:<uuid determinístico>",
  "_rev": "2-...",
  "tipo": "pedido",
  "cliente_id": "cliente:<uuid>",
  "status": "CONFIRMADO",
  "itens": [
    {
      "produto_id": "produto:OP01-001",
      "carta_api_id": "OP01-001",
      "variante_api_id": "OP01-001_p1",
      "nome": "Roronoa Zoro",
      "imagem": "https://optcgapi.com/...",
      "quantidade": 1,
      "preco_unitario": 10.75,
      "subtotal": 10.75
    }
  ],
  "entrega": {"nome": "Pessoa Exemplo", "cep": "13000000", "logradouro": "..."},
  "total": 10.75,
  "carrinho_hash": "...",
  "schema_version": 2,
  "criado_em": "...",
  "atualizado_em": "..."
}
```

O ID determinístico combina cliente e token de confirmação, garantindo idempotência.
Itens e entrega são snapshots imutáveis; o histórico não depende da API nem do produto atual.
