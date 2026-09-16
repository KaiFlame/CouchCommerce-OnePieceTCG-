"""REST do CouchDB: timeouts, revisões e erros sem expor credenciais."""
import os
import logging
from urllib.parse import quote, unquote, urlsplit

import requests

log = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    def __init__(self, status, message="Falha no CouchDB"):
        self.status = status
        super().__init__(message)


class CouchDB:
    def __init__(self, url=None, name=None):
        address = urlsplit(url or os.environ["COUCHDB_URL"])
        self.base = f"{address.scheme}://{address.hostname}:{address.port or 5984}"
        self.auth = (unquote(address.username or ""), unquote(address.password or ""))
        self.name = name or os.getenv("COUCHDB_DATABASE", "ecommerce_facamp")

    def request(self, method, path, **kwargs):
        try:
            response = requests.request(method, self.base + path, auth=self.auth,
                                        timeout=kwargs.pop("timeout", 15), **kwargs)
        except requests.RequestException:
            log.warning("couchdb_connection_error method=%s", method)
            raise DatabaseError(503, "Banco temporariamente indisponível") from None
        if response.status_code >= 400:
            log.warning("couchdb_http_error status=%s method=%s", response.status_code, method)
            raise DatabaseError(response.status_code)
        return response.json() if response.content else {}

    def couch(self, method, path="", **kwargs):
        return self.request(method, "/" + quote(self.name, safe="") + path, **kwargs)

    def get(self, doc_id):
        try:
            return self.couch("GET", "/" + quote(doc_id, safe=":"))
        except DatabaseError as error:
            if error.status == 404:
                return None
            raise

    def save(self, doc):
        result = self.couch("PUT", "/" + quote(doc["_id"], safe=":"), json=doc)
        doc["_rev"] = result["rev"]
        return result

    def find(self, selector, fields=None, limit=100):
        query = {"selector": selector, "limit": limit}
        if fields:
            query["fields"] = fields
        return self.couch("POST", "/_find", json=query)["docs"]

    def find_all(self, selector):
        docs, bookmark = [], None
        while True:
            query = {"selector": selector, "limit": 500}
            if bookmark:
                query["bookmark"] = bookmark
            result = self.couch("POST", "/_find", json=query)
            docs.extend(result["docs"])
            next_bookmark = result.get("bookmark")
            if not result["docs"] or next_bookmark == bookmark:
                return docs
            bookmark = next_bookmark

    def bulk(self, docs):
        """O chamador deve conferir CADA resultado; HTTP 201 não garante o lote."""
        result = self.couch("POST", "/_bulk_docs", json={"docs": docs})
        if not isinstance(result, list) or len(result) != len(docs):
            raise DatabaseError(503, "Resposta incompleta do lote")
        return result
