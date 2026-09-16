import pytest
from card_catalog import normalize, merge_card, collect, SOURCES, price_brl


def test_variants_do_not_overwrite_same_card_code():
    base = {"card_set_id": "OP01-001", "card_image_id": "OP01-001",
            "card_name": "Zoro", "card_image": "https://optcgapi.com/media/OP01-001.jpg"}
    promo = {**base, "card_image": "https://optcgapi.com/media/promo.jpg"}
    assert normalize(base, "Coleções")["_id"] != normalize(promo, "Promocionais")["_id"]


def test_sync_preserves_inventory_and_revision():
    old = {"_rev": "2-old", "preco": 89.90, "estoque": 5, "ativo": False}
    merged = merge_card({"nome": "Zoro", "preco": 10.75, "preco_usd": 2.15}, old)
    assert all(merged[k] == old[k] for k in ("_rev", "estoque", "ativo"))
    assert merged["preco"] == 10.75
    assert merge_card({"nome": "Zoro"})["preco"] is None


@pytest.mark.parametrize("usd,expected", [(2.15, 10.75), ("0.333", 1.67), ("0.001", 0.01),
                                         (None, None), (0, None), (-1, None), ("NaN", None),
                                         ("Infinity", None), ("invalid", None), ("0.0001", None)])
def test_price_conversion(usd, expected):
    assert price_brl(usd) == expected


def test_commercial_document_does_not_store_full_card():
    metadata = {"_id": "produto:test", "nome": "Zoro", "efeito": "texto", "poder": "5000",
                "custo": "3", "cor": "Red", "raridade": "R"}
    document = merge_card(metadata)
    assert not {"efeito", "poder", "custo"} & document.keys()
    assert document["cor"] == "Red" and document["raridade"] == "R"


@pytest.mark.parametrize("url", ["http://optcgapi.com/card.jpg", "https://evil.example/card.jpg", "javascript:alert(1)"])
def test_reject_unexpected_image_source(url):
    with pytest.raises(ValueError):
        normalize({"card_image": url}, "Coleções")


def test_missing_images_do_not_collapse_cards():
    rows = [{"card_name": "A", "card_image_id": "a", "card_image": None},
            {"card_name": "B", "card_image_id": "b", "card_image": None}]
    cards = collect({endpoint: rows for endpoint in SOURCES})
    assert len([c for c in cards.values() if c["grupo"] == "Promocionais"]) == 2


def test_duplicate_images_are_deduplicated():
    row = {"card_name": "Zoro", "card_image_id": "OP01-001",
           "card_image": "https://optcgapi.com/media/OP01-001.jpg"}
    assert len(collect({endpoint: [row] for endpoint in SOURCES})) == 1
