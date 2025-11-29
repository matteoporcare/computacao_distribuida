# flask/app.py
from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, and_
from datetime import datetime, timezone
import logging, json, os, requests, time
from functools import wraps
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# ---------- CONFIG ----------
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordenador:3000")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "secret-token")  # replace in production
SQLITE_PATH = os.environ.get("SQLITE_PATH", "sqlite:///agendamento.db")
LOCK_TTL_MS = int(os.environ.get("LOCK_TTL_MS", "15000"))

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(asctime)s:%(name)s:%(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
logger = logging.getLogger("servico-agendamento")

# ---------- METRICS ----------
REQ_COUNTER = Counter("app_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
SCHED_CREATED = Counter("agendamentos_created_total", "Total agendamentos created")

# ---------- APP & DB ----------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLITE_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------- MODELS ----------
class Cientista(db.Model):
    __tablename__ = "cientistas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False, unique=True)

class Telescopio(db.Model):
    __tablename__ = "telescopios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String, nullable=False, unique=True)

class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    id = db.Column(db.Integer, primary_key=True)
    cientista_id = db.Column(db.Integer, db.ForeignKey("cientistas.id"), nullable=False)
    telescopio_id = db.Column(db.Integer, db.ForeignKey("telescopios.id"), nullable=False)
    horario_inicio_utc = db.Column(db.DateTime, nullable=False)
    horario_fim_utc = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String, nullable=False, default="CONFIRMED")
    __table_args__ = (CheckConstraint("horario_inicio_utc < horario_fim_utc", name="ck_horario"),)

# ---------- HELPERS ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def emit_audit(event_type, details):
    # simple audit log to stdout (or file if you prefer)
    logger.info(json.dumps({"timestamp": now_iso(), "event_type": event_type, "details": details}))

def require_token(f):
    @wraps(f)
    def decorated(*a, **kw):
        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            abort(401, "Missing token")
        t = token.split(" ", 1)[1]
        if t != ADMIN_TOKEN:
            abort(403, "Invalid token")
        return f(*a, **kw)
    return decorated

def acquire_lock(resource, ttl_ms=LOCK_TTL_MS):
    url = f"{COORDINATOR_URL.rstrip('/')}/lock"
    logger.info(f"[LOCK-TRY] resource={resource} url={url}")
    try:
        r = requests.post(url, json={"resource": resource, "ttl_ms": ttl_ms}, timeout=3)
        logger.info(f"[LOCK-RESP] status={r.status_code} body={r.text}")
        if r.status_code == 200:
            return True, r.json()
        else:
            return False, r.json()
    except Exception as e:
        logger.error(f"[LOCK-ERROR] {e}")
        return False, {"error": "coordinator-unreachable", "detail": str(e)}

def release_lock(resource, owner):
    url = f"{COORDINATOR_URL.rstrip('/')}/unlock"
    try:
        requests.post(url, json={"resource": resource, "owner": owner}, timeout=2)
    except Exception as e:
        logger.warning(f"[UNLOCK-ERR] {e}")

# ---------- ROUTES ----------
@app.before_request
def _count_req():
    # increment basic metric
    # endpoint may be None for 404s
    pass

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","time": now_iso()}), 200

@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.route("/openapi.yaml", methods=["GET"])
def openapi_spec():
    # returns a minimal OpenAPI (you can serve static file instead)
    with open(os.path.join(os.path.dirname(__file__),"openapi.yml"), "r") as fh:
        return fh.read(), 200, {"Content-Type":"text/yaml"}

@app.route("/time", methods=["GET"])
def get_time():
    REQ_COUNTER.labels(method="GET", endpoint="/time", status="200").inc()
    return jsonify({"server_time_utc": now_iso()}), 200

@app.route("/agendamentos", methods=["POST"])
def create_agendamento():
    REQ_COUNTER.labels(method="POST", endpoint="/agendamentos", status="202").inc()
    data = request.get_json(force=True)
    required = ["cientista_id","telescopio_id","horario_inicio_utc","horario_fim_utc"]
    for r in required:
        if r not in data:
            abort(400, f"{r} required")
    try:
        inicio = datetime.fromisoformat(data["horario_inicio_utc"].replace("Z","+00:00"))
        fim = datetime.fromisoformat(data["horario_fim_utc"].replace("Z","+00:00"))
    except:
        abort(400, "invalid dates")

    resource = f"telescopio-{data['telescopio_id']}_{data['horario_inicio_utc']}"
    ok, info = acquire_lock(resource)
    if not ok:
        return jsonify({"error":"Conflict","details":info}), 409

    owner = info.get("owner")
    try:
        conflict = Agendamento.query.filter(
            Agendamento.telescopio_id==data["telescopio_id"],
            Agendamento.status=="CONFIRMED",
            and_(Agendamento.horario_inicio_utc < fim, Agendamento.horario_fim_utc > inicio)
        ).first()
        if conflict:
            return jsonify({"error":"Conflict","message":"Conflito no BD"}), 409

        a = Agendamento(
            cientista_id=data["cientista_id"],
            telescopio_id=data["telescopio_id"],
            horario_inicio_utc=inicio,
            horario_fim_utc=fim,
            status="CONFIRMED"
        )
        db.session.add(a)
        db.session.commit()
        SCHED_CREATED.inc()
        emit_audit("AGENDAMENTO_CRIADO", {"id": a.id, "cientista": a.cientista_id, "telescopio": a.telescopio_id})
        return jsonify({"id": a.id, "status":"CONFIRMED"}), 201
    finally:
        release_lock(resource, owner)

# admin-only listing example
@app.route("/admin/locks", methods=["GET"])
@require_token
def admin_locks():
    r = requests.get(f"{COORDINATOR_URL.rstrip('/')}/locks", timeout=3)
    return r.json(), r.status_code

# ---------- INIT ----------
def seed():
    if Telescopio.query.count()==0:
        db.session.add(Telescopio(nome="Hubble-Acad"))
    if Cientista.query.count()==0:
        db.session.add(Cientista(nome="Teste", email="teste@example.com"))
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
