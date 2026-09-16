"""Gera credenciais locais; nunca sobrescreve um .env existente."""
from pathlib import Path
import secrets


def main():
    destino = Path(__file__).resolve().parents[1] / ".env"
    conteudo = (
        f"SECRET_KEY={secrets.token_hex(32)}\n"
        "COUCHDB_USER=admin\n"
        f"COUCHDB_PASSWORD={secrets.token_hex(32)}\n"
        "COUCHDB_DATABASE=ecommerce_facamp\n"
        "COUCHDB_URL=http://${COUCHDB_USER}:${COUCHDB_PASSWORD}@127.0.0.1:5984\n"
    )
    try:
        with destino.open("x", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
    except FileExistsError:
        print(".env ja existe: credenciais preservadas.")
    else:
        print(".env criado com credenciais aleatorias. Nao envie esse arquivo ao GitHub.")


if __name__ == "__main__":
    main()
