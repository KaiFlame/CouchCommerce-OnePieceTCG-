# Roteiro Fauxton
1. Acesse `http://127.0.0.1:5984/_utils/`.
2. Abra `ecommerce_facamp`.
3. Observe documentos `produto:*`, `cliente:*`, `pedido:*`.
4. Edite um produto e observe `_rev`.
5. Teste Mango Query com `{ "selector": {"tipo":"produto"} }`.
6. Crie índice `tipo + categoria`.
7. Abra duas abas e force conflito de revisão.
8. Explore o menu de replicação.
