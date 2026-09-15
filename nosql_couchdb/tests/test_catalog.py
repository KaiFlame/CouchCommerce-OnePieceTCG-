from card_catalog import normalize, merge_card, collect, SOURCES


def test_variants_do_not_overwrite_same_card_code():
    base = {"card_set_id": "OP01-001", "card_image_id": "OP01-001",
            "card_name": "Zoro", "card_image": "https://optcgapi.com/media/OP01-001.jpg"}
    promo = {**base, "card_image": "https://optcgapi.com/media/promo.jpg"}
    assert normalize(base, "Coleções")["_id"] != normalize(promo, "Promocionais")["_id"]


def test_sync_preserves_inventory_and_revision():
    old = {"_rev": "2-old", "preco": 89.90, "estoque": 5, "ativo": False}
    merged = merge_card({"nome": "Zoro"}, old)
    assert all(merged[k] == v for k, v in old.items())
    assert merge_card({"nome": "Zoro"})["preco"] is None


def test_missing_images_do_not_collapse_cards():
    rows = [{"card_name": "A", "card_image_id": "a", "card_image": None},
            {"card_name": "B", "card_image_id": "b", "card_image": None}]
    cards = collect({endpoint: rows for endpoint in SOURCES})
    assert len([c for c in cards.values() if c["grupo"] == "Promocionais"]) == 2


def test_duplicate_images_are_deduplicated():
    row = {"card_name": "Zoro", "card_image_id": "OP01-001",
           "card_image": "https://optcgapi.com/media/OP01-001.jpg"}
    assert len(collect({endpoint: [row] for endpoint in SOURCES})) == 1
