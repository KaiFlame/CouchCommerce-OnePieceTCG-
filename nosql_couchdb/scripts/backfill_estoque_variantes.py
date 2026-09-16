"""Inicializa somente variantes afetadas pelo bug histórico de estoque zero."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_catalog import INITIAL_STOCK
from database import CouchDB, DatabaseError


def eligible(doc):
    return (doc.get("tipo") == "produto" and doc.get("ativo") is True and
            doc.get("origem") == "optcgapi.com" and doc.get("estoque") == 0 and
            doc.get("estoque_inicializado") is not True and not doc.get("substituido_por"))


def main():
    db = CouchDB()
    targets = [doc for doc in db.find_all({"tipo": "produto"}) if eligible(doc)]
    for offset in range(0, len(targets), 200):
        batch = targets[offset:offset + 200]
        for doc in batch:
            doc["estoque"] = INITIAL_STOCK
            doc["estoque_inicializado"] = True
        results = db.bulk(batch)
        if len(results) != len(batch) or any(not result.get("ok") for result in results):
            raise RuntimeError("Backfill interrompido: confira os resultados individuais do lote.")
    remaining = [doc for doc in db.find_all({"tipo": "produto"}) if eligible(doc)]
    if remaining:
        raise RuntimeError("Backfill incompleto: documentos elegíveis restantes.")
    print({"updated": len(targets), "remaining": len(remaining), "initial_stock": INITIAL_STOCK})


if __name__ == "__main__":
    try:
        main()
    except (DatabaseError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
