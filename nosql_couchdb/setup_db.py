"""Estrutura didática: banco, índices por consulta, usuário e validação mínima."""
import os

from database import DatabaseError
from card_catalog import now

INDEXES = {
    "idx_tipo_ativo": ["tipo", "ativo"],
    "idx_tipo_carta_api_id": ["tipo", "carta_api_id"],
    "idx_tipo_categoria": ["tipo", "categoria"],
    "idx_tipo_email": ["tipo", "email"],
    "idx_tipo_cliente": ["tipo", "cliente_id"],
    "idx_tipo_status": ["tipo", "status"],
}

VALIDATION = """function(doc, old, user) {
  if (doc._id.indexOf('_design/') === 0) return;
  if (doc._deleted) {
    if (user.roles.indexOf('_admin') < 0) throw({forbidden:'Somente administrador pode excluir'});
    return;
  }
  if (['produto','cliente','pedido'].indexOf(doc.tipo) < 0) throw({forbidden:'Tipo invalido'});
  if (doc._id.indexOf(doc.tipo + ':') !== 0) throw({forbidden:'Prefixo invalido'});
  if (doc.tipo === 'produto') {
    if (typeof doc.carta_api_id !== 'string' || typeof doc.nome !== 'string')
      throw({forbidden:'Produto sem identificacao'});
    if (typeof doc.estoque !== 'number' || doc.estoque < 0 || doc.estoque % 1 !== 0)
      throw({forbidden:'Estoque deve ser inteiro e nao negativo'});
    if (doc.preco !== null && (typeof doc.preco !== 'number' || doc.preco <= 0))
      throw({forbidden:'Preco invalido'});
    if (doc.reservas_checkout) for (var key in doc.reservas_checkout) {
      var qtd = doc.reservas_checkout[key];
      if (typeof qtd !== 'number' || qtd < 1 || qtd % 1 !== 0)
        throw({forbidden:'Reserva invalida'});
    }
  }
  if (doc.tipo === 'cliente') {
    if (typeof doc.email !== 'string' || typeof doc.senha_hash !== 'string' || doc.senha)
      throw({forbidden:'Cliente invalido'});
  }
  if (doc.tipo === 'pedido') {
    var estados = ['CRIADO','PROCESSANDO','CONFIRMADO','COMPENSANDO','COMPENSACAO_PENDENTE','CANCELADO'];
    if (typeof doc.cliente_id !== 'string' || !Array.isArray(doc.itens) || !doc.itens.length)
      throw({forbidden:'Pedido incompleto'});
    if (estados.indexOf(doc.status) < 0 || typeof doc.total !== 'number' || doc.total < 0)
      throw({forbidden:'Pedido invalido'});
    if (old && (JSON.stringify(old.itens) !== JSON.stringify(doc.itens) ||
                old.cliente_id !== doc.cliente_id || old.total !== doc.total ||
                JSON.stringify(old.entrega) !== JSON.stringify(doc.entrega)))
      throw({forbidden:'Snapshot do pedido e imutavel'});
  }
}"""


def initialize(db, seed=True):
    try:
        db.couch("PUT")
    except DatabaseError as error:
        if error.status != 412:
            raise
    for name, fields in INDEXES.items():
        db.couch("POST", "/_index", json={"index": {"fields": fields}, "name": name, "type": "json"})
    design = db.get("_design/regras") or {"_id": "_design/regras"}
    design["validate_doc_update"] = VALIDATION
    db.save(design)
    if seed:
        for code, quantity in (("OP01-001", 5), ("OP01-002", 8), ("OP01-003", 12)):
            identifier = "produto:" + code
            if not db.get(identifier):
                db.save({"_id": identifier, "tipo": "produto", "carta_api_id": code,
                         "nome": code, "preco": None, "estoque": quantity, "ativo": True,
                         "schema_version": 2, "criado_em": now(), "atualizado_em": now()})


def application_user(db):
    name = os.environ["APP_COUCHDB_USER"]
    password = os.environ["APP_COUCHDB_PASSWORD"]
    path = "/_users/org.couchdb.user:" + name
    try:
        doc = db.request("GET", path)
    except DatabaseError as error:
        if error.status != 404:
            raise
        doc = {"_id": "org.couchdb.user:" + name}
    doc.update(name=name, password=password, roles=["loja"], type="user")
    db.request("PUT", path, json=doc)
    db.couch("PUT", "/_security", json={"admins": {"names": [], "roles": []},
                                        "members": {"names": [name], "roles": ["loja"]}})
