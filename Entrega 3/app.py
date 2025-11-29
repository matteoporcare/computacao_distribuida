from flask import Flask, request, jsonify, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, and_
from datetime import datetime, timezone
import logging
import json
import time
import random
import os
import requests

# ---------------------------- LOGGING ---------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(asctime)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("servico-agendamento")
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = logging.FileHandler("audit.log")

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return record.getMessage()

audit_handler.setFormatter(JSONFormatter())
audit_logger.addHandler(audit_handler)

# ---------------------------- APP & DB ---------------------------- #
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///agendamento.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Coordinator URL (configurable)
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:3000")

# ---------------------------- MODELOS ---------------------------- #
class Cientista(db.Model):
    __tablename__ = "cientistas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False, unique=True)
    instituicao = db.Column(db.String)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                              onupdate=lambda: datetime.now(timezone.utc))

class Telescopio(db.Model):
    __tablename__ = "telescopios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String, nullable=False, unique=True)
    timezone = db.Column(db.String)
    disponivel = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                              onupdate=lambda: datetime.now(timezone.utc))

class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    id = db.Column(db.Integer, primary_key=True)
    cientista_id = db.Column(db.Integer, db.ForeignKey("cientistas.id"), nullable=False)
    telescopio_id = db.Column(db.Integer, db.ForeignKey("telescopios.id"), nullable=False)
    horario_inicio_utc = db.Column(db.DateTime, nullable=False)
    horario_fim_utc = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String, nullable=False, default="CONFIRMED")
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                              onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        CheckConstraint("horario_inicio_utc < horario_fim_utc", name="ck_horario"),
    )

# ---------------------------- HELPERS ---------------------------- #
def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def emit_audit(event_type, details):
    audit_logger.info(json.dumps({
        "timestamp_utc": now_iso(),
        "level": "AUDIT",
        "event_type": event_type,
        "service": "servico-agendamento",
        "details": details
    }))

def acquire_lock(resource, ttl_ms=30000):
    url = f"{COORDINATOR_URL}/lock"
    try:
        r = requests.post(url, json={"resource": resource, "ttl_ms": ttl_ms}, timeout=2.0)
    except requests.RequestException as e:
        logger.error(f"Erro ao contatar coordenador: {e}")
        return False, {"error":"coordinator-unreachable"}
    if r.status_code == 200:
        return True, r.json()
    else:
        try:
            return False, r.json()
        except:
            return False, {"error":"unknown"}

def release_lock(resource, owner=None):
    url = f"{COORDINATOR_URL}/unlock"
    try:
        payload = {"resource": resource}
        if owner: payload["owner"] = owner
        r = requests.post(url, json=payload, timeout=2.0)
        return r.status_code == 200
    except requests.RequestException as e:
        logger.error(f"Erro liberando lock: {e}")
        return False

# ---------------------------- ROTAS ---------------------------- #
@app.route("/time", methods=["GET"])
def get_time():
    return jsonify({"server_time_utc": now_iso()}), 200

@app.route("/cientistas", methods=["POST"])
def create_cientista():
    data = request.get_json(force=True)
    if not data.get("nome") or not data.get("email"):
        abort(400, "nome e email são obrigatórios")
    c = Cientista(nome=data["nome"], email=data["email"], instituicao=data.get("instituicao"))
    db.session.add(c)
    try:
        db.session.commit()
    except:
        db.session.rollback()
        abort(400, "email duplicado ou inválido")
    return jsonify({"id": c.id, "nome": c.nome, "email": c.email}), 201

@app.route("/telescopios", methods=["GET"])
def list_telescopios():
    ts = Telescopio.query.all()
    return jsonify([{"id": t.id, "nome": t.nome, "disponivel": t.disponivel} for t in ts]), 200

@app.route("/agendamentos", methods=["GET"])
def list_agendamentos():
    tel = request.args.get("telescopio", type=int)
    q = Agendamento.query
    if tel:
        q = q.filter_by(telescopio_id=tel)
    ags = q.all()
    return jsonify([{
        "id": a.id,
        "cientista_id": a.cientista_id,
        "telescopio_id": a.telescopio_id,
        "horario_inicio_utc": a.horario_inicio_utc.isoformat(),
        "horario_fim_utc": a.horario_fim_utc.isoformat(),
        "status": a.status
    } for a in ags]), 200

@app.route("/agendamentos", methods=["POST"])
def create_agendamento():
    data = request.get_json(force=True)
    required = ["cientista_id", "telescopio_id", "horario_inicio_utc", "horario_fim_utc"]
    for r in required:
        if r not in data:
            abort(400, f"{r} é obrigatório")

    try:
        inicio = datetime.fromisoformat(data["horario_inicio_utc"].replace("Z", "+00:00"))
        fim = datetime.fromisoformat(data["horario_fim_utc"].replace("Z", "+00:00"))
    except:
        abort(400, "datas devem estar em ISO 8601 UTC")

    resource = f"telescopio-{data['telescopio_id']}_{data['horario_inicio_utc']}"
    locked = False
    owner = None
    # Tentar adquirir lock antes de tocar no BD
    ok, info = acquire_lock(resource, ttl_ms=15000)
    if not ok:
        # coordenador respondeu 409 ou estava inacessível
        return jsonify({"error": "Conflict", "reason": info}), 409
    else:
        locked = True
        owner = info.get("owner")

    try:
        # verificação de conflito no BD (após lock)
        conflict = Agendamento.query.filter(
            Agendamento.telescopio_id == data["telescopio_id"],
            Agendamento.status == "CONFIRMED",
            and_(Agendamento.horario_inicio_utc < fim, Agendamento.horario_fim_utc > inicio)
        ).first()

        if conflict:
            return jsonify({"error": "Conflict", "message": "Recurso ocupado no BD"}), 409

        a = Agendamento(
            cientista_id=data["cientista_id"],
            telescopio_id=data["telescopio_id"],
            horario_inicio_utc=inicio,
            horario_fim_utc=fim,
            status="CONFIRMED"
        )
        db.session.add(a)
        db.session.commit()

        emit_audit("AGENDAMENTO_CRIADO", {
            "agendamento_id": a.id,
            "cientista_id": a.cientista_id,
            "telescopio_id": a.telescopio_id
        })

        return jsonify({
            "id": a.id,
            "cientista_id": a.cientista_id,
            "telescopio_id": a.telescopio_id,
            "horario_inicio_utc": data["horario_inicio_utc"],
            "horario_fim_utc": data["horario_fim_utc"],
            "status": "CONFIRMED"
        }), 201
    finally:
        if locked:
            release_lock(resource, owner=owner)

@app.route("/agendamentos/<int:ag_id>/cancel", methods=["POST"])
def cancel_agendamento(ag_id):
    a = Agendamento.query.get_or_404(ag_id)
    a.status = "CANCELLED"
    db.session.commit()
    emit_audit("AGENDAMENTO_CANCELADO", {"agendamento_id": ag_id})
    return jsonify({"id": ag_id, "status": "CANCELLED"}), 200

# ---------------------------- INIT ---------------------------- #
def seed():
    if Telescopio.query.count() == 0:
        t = Telescopio(nome="Hubble-Acad", timezone="UTC", disponivel=True)
        db.session.add(t)
        db.session.commit()
    if Cientista.query.count() == 0:
        c = Cientista(nome="Teste", email="teste@example.com")
        db.session.add(c)
        db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed()
    app.run(host="0.0.0.0", port=5000, debug=False)
