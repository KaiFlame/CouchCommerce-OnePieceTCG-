def test_produto_valido():
    p={"tipo":"produto","preco":10.0,"estoque":0}
    assert p["tipo"]=="produto" and p["preco"]>=0 and p["estoque"]>=0

def test_pedido_embute_itens():
    p={"tipo":"pedido","itens":[{"produto_id":"produto:x","quantidade":1}]}
    assert len(p["itens"])==1
