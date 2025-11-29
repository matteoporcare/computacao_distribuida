from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, and_
from datetime import datetime, timezone
import logging
import json
import time
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

# Coordenador dentro do Docker
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordenador:3000")

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

# ---------------------- LOCK DISTRIBUÍDO ---------------------- #
def acquire_lock(resource, ttl_ms=15000):
    url = f"{COORDINATOR_URL}/lock"
    logger.info(f"[LOCK-TRY] resource={resource}")

    try:
        r = requests.post(url, json={"resource": resource, "ttl_ms": ttl_ms}, timeout=3.0)
        logger.info(f"[LOCK-RESP] status={r.status_code} body={r.text}")

        if r.status_code == 200:
            return True, r.json()

        return False, r.json()

    except Exception as e:
        logger.error(f"[LOCK-ERROR] {e}")
        return False, {"error": "coordinator-unreachable"}

def release_lock(resource, owner):
    url = f"{COORDINATOR_URL}/unlock"
    logger.info(f"[UNLOCK-TRY] resource={resource}")

    try:
        requests.post(url, json={"resource": resource, "owner": owner}, timeout=3.0)
    except:
        logger.error("[UNLOCK-ERROR] erro ao liberar lock")

# ---------------------------- ROTAS ---------------------------- #
@app.route("/agendamentos", methods=["POST"])
def create_agendamento():
    data = request.get_json(force=True)

    required = ["cientista_id", "telescopio_id", "horario_inicio_utc", "horario_fim_utc"]
    for r in required:
        if r not in data:
            abort(400, f"{r} obrigatório")

    inicio = datetime.fromisoformat(data["horario_inicio_utc"].replace("Z","+00:00"))
    fim = datetime.fromisoformat(data["horario_fim_utc"].replace("Z","+00:00"))

    # ---------------- ACQUIRE LOCK ---------------- #
    resource = f"telescopio-{data['telescopio_id']}_{data['horario_inicio_utc']}"
    ok, info = acquire_lock(resource)

    if not ok:
        return jsonify({"error": "Conflict", "details": info}), 409

    owner = info["owner"]

    try:
        # Conflito no banco
        conflict = Agendamento.query.filter(
            Agendamento.telescopio_id == data["telescopio_id"],
            Agendamento.status == "CONFIRMED",
            and_(Agendamento.horario_inicio_utc < fim,
                 Agendamento.horario_fim_utc > inicio)
        ).first()

        if conflict:
            return jsonify({"error": "Conflict", "message": "Conflito no BD"}), 409

        a = Agendamento(
            cientista_id=data["cientista_id"],
            telescopio_id=data["telescopio_id"],
            horario_inicio_utc=inicio,
            horario_fim_utc=fim,
            status="CONFIRMED"
        )
        db.session.add(a)
        db.session.commit()

        return jsonify({"id": a.id, "status": "CONFIRMED"}), 201

    finally:
        release_lock(resource, owner)

# ---------------------------- INIT ---------------------------- #
def seed():
    if Telescopio.query.count() == 0:
        db.session.add(Telescopio(nome="Hubble-Acad", timezone="UTC"))
    if Cientista.query.count() == 0:
        db.session.add(Cientista(nome="Teste", email="teste@example.com"))
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed()
    app.run(host="0.0.0.0", port=5000)
