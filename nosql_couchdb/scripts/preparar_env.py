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
    values = {line.split("=", 1)[0]: line.split("=", 1)[1].strip()
              for line in current.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    missing = {"APP_COUCHDB_USER": "loja_app", "APP_COUCHDB_PASSWORD": app_password}
    for name, value in missing.items():
        if not values.get(name):
            lines = current.splitlines()
            changed = False
            for index, line in enumerate(lines):
                if line.split("=", 1)[0] == name:
                    lines[index] = f"{name}={value}"
                    changed = True
            current = "\n".join(lines) + "\n" if changed else current + f"\n{name}={value}\n"
    # O dotenv resolve variáveis na ordem do arquivo: a URL precisa ficar depois
    # das credenciais restritas para não gerar avisos falsos no Compose.
    restricted = "COUCHDB_URL=http://${APP_COUCHDB_USER}:${APP_COUCHDB_PASSWORD}@127.0.0.1:5984"
    lines = [line for line in current.splitlines() if not line.startswith("COUCHDB_URL=")]
    current = "\n".join(lines) + "\n" + restricted + "\n"
    destino.write_text(current, encoding="utf-8")
    print("Credenciais administrativas e da aplicacao preparadas (valores omitidos).")


if __name__ == "__main__":
    main()
