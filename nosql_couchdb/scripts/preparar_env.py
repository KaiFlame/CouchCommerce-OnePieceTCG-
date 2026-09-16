"""Gera credenciais locais; preserva as existentes e acrescenta chaves ausentes."""
from pathlib import Path
import secrets


def main():
    destino = Path(__file__).resolve().parents[1] / ".env"
    app_password = secrets.token_hex(32)
    conteudo = (
        f"SECRET_KEY={secrets.token_hex(32)}\n"
        "COUCHDB_USER=admin\n"
        f"COUCHDB_PASSWORD={secrets.token_hex(32)}\n"
        "COUCHDB_DATABASE=ecommerce_facamp\n"
        "APP_COUCHDB_USER=loja_app\n"
        f"APP_COUCHDB_PASSWORD={app_password}\n"
        "COUCHDB_URL=http://${APP_COUCHDB_USER}:${APP_COUCHDB_PASSWORD}@127.0.0.1:5984\n"
    )
    try:
        with destino.open("x", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
    except FileExistsError:
        print(".env ja existe: credenciais preservadas.")
    else:
        print(".env criado com credenciais aleatorias. Nao envie esse arquivo ao GitHub.")
    current = destino.read_text(encoding="utf-8")
    names = {line.split("=", 1)[0] for line in current.splitlines() if "=" in line}
    missing = {"APP_COUCHDB_USER": "loja_app", "APP_COUCHDB_PASSWORD": app_password}
    with destino.open("a", encoding="utf-8") as arquivo:
        for name, value in missing.items():
            if name not in names:
                arquivo.write(f"\n{name}={value}\n")
    # Corrige somente o valor padrão antigo; credenciais personalizadas são preservadas.
    current = destino.read_text(encoding="utf-8")
    legacy = "COUCHDB_URL=http://${COUCHDB_USER}:${COUCHDB_PASSWORD}@127.0.0.1:5984"
    restricted = "COUCHDB_URL=http://${APP_COUCHDB_USER}:${APP_COUCHDB_PASSWORD}@127.0.0.1:5984"
    if legacy in current:
        destino.write_text(current.replace(legacy, restricted), encoding="utf-8")
    print("Credenciais administrativas e da aplicacao preparadas (valores omitidos).")


if __name__ == "__main__":
    main()
