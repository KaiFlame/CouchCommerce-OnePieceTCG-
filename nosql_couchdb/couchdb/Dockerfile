# CouchDB 3.5.2: digest da imagem oficial validada neste laboratorio.
FROM couchdb:3@sha256:9ea24cbd76522fe845d1c32c7fd1dcfc8a3ba73dcc4817d62f8a7f7f1dfaffe3

# Copia com permissoes Linux corretas; evita conflitos do bind mount no Windows.
COPY --chown=couchdb:couchdb --chmod=644 single-node.ini /opt/couchdb/etc/local.d/10-single-node.ini
