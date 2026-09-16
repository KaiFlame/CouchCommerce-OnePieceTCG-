"""Replicação, backup lógico consistente e restauração em banco NOVO.

Execute no serviço admin. Arquivos completos ficam em .local (fora do Git).
Evidências públicas contêm somente contagens, hashes e nomes dos bancos.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import CouchDB, DatabaseError

PRIVATE = Path(".local/operations")
EVIDENCE = Path("evidencias")


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def contents(db):
    return [row["doc"] for row in db.couch("GET", "/_all_docs", params={"include_docs": "true"})["rows"]]


def clean(doc):
    return {key: value for key, value in doc.items() if key not in ("_rev", "_revisions", "_conflicts")}


def digest(documents):
    canonical = sorted([clean(doc) for doc in documents], key=lambda d: d["_id"])
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replicate(source):
    replica = CouchDB(os.environ["REPLICA_URL"], name=source.name + "_replica")
    try:
        replica.couch("PUT")
    except DatabaseError as error:
        if error.status != 412:
            raise
    security = source.couch("GET", "/_security")
    replica.couch("PUT", "/_security", json=security)

    def endpoint(db):
        return {"url": db.base + "/" + db.name,
                "auth": {"basic": {"username": db.auth[0], "password": db.auth[1]}}}

    start = time.monotonic()
    result = source.request("POST", "/_replicate", timeout=120,
                            json={"source": endpoint(source), "target": endpoint(replica)})
    original, copied = contents(source), contents(replica)
    if not result.get("ok") or digest(original) != digest(copied):
        raise RuntimeError("Replicação divergente; confira se a origem estava sendo alterada.")
    evidence = {"source": source.name, "target": replica.name, "instances": 2,
                "documents": len(copied), "content_sha256": digest(copied),
                "seconds": round(time.monotonic()-start, 3), "verified_at": stamp(),
                "mode": "one-shot", "ok": True}
    write_json(EVIDENCE / "replicacao.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False))


def backup(source):
    # Sequência igual antes/depois evita vender um dump concorrente como snapshot.
    before = source.couch("GET")["update_seq"]
    docs = contents(source)
    after = source.couch("GET")["update_seq"]
    if before != after:
        raise RuntimeError("Banco mudou durante o backup. Pause as escritas e repita.")
    payload = {"format": 1, "database": source.name, "created_at": stamp(),
               "update_seq": after, "security": source.couch("GET", "/_security"),
               "docs": [clean(doc) for doc in docs], "sha256": digest(docs)}
    filename = PRIVATE / (source.name + "_" + payload["created_at"] + ".json")
    write_json(filename, payload)
    write_json(EVIDENCE / "backup.json", {k: payload[k] for k in ("database", "created_at", "sha256", "update_seq")}
               | {"documents": len(docs), "file": str(filename), "type": "logical-json", "ok": True})
    print("Backup privado criado:", filename)
    return filename


def restore(source, filename):
    payload = json.loads(Path(filename).read_text(encoding="utf-8"))
    if payload.get("format") != 1 or digest(payload["docs"]) != payload["sha256"]:
        raise RuntimeError("Formato ou checksum de backup inválido.")
    target = CouchDB(name=source.name + "_restore_" + stamp())
    start = time.monotonic()
    target.couch("PUT")  # 412 aborta: nunca sobrescrever um banco existente.
    target.couch("PUT", "/_security", json=payload["security"])
    for offset in range(0, len(payload["docs"]), 200):
        batch = payload["docs"][offset:offset+200]
        results = target.bulk(batch)
        if any(not result.get("ok") for result in results):
            raise RuntimeError("Restauração incompleta: conferir resultados do lote.")
    restored = contents(target)
    if digest(restored) != payload["sha256"]:
        raise RuntimeError("Conteúdo restaurado diverge do backup.")
    evidence = {"source": source.name, "restored_database": target.name, "documents": len(restored),
                "sha256": digest(restored), "seconds": round(time.monotonic()-start, 3),
                "revisions": "novas; backup lógico não preserva árvore MVCC", "ok": True}
    write_json(EVIDENCE / "restore.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["replicate", "backup", "restore", "demo"])
    parser.add_argument("file", nargs="?")
    args = parser.parse_args()
    db = CouchDB()
    if args.action in ("replicate", "demo"):
        replicate(db)
    if args.action in ("backup", "demo"):
        path = backup(db)
    if args.action == "demo":
        restore(db, path)
    if args.action == "restore":
        if not args.file:
            parser.error("restore exige o arquivo de backup")
        restore(db, args.file)


if __name__ == "__main__":
    try:
        main()
    except (DatabaseError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
