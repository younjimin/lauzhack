"""
auth_db.py — ability+ login, SQL storage and patient <-> physiotherapist data exchange.

Storage: SQLite (Python standard library, one file: instance/abilityplus.db).
All queries are plain SQL with parameters, so moving to PostgreSQL/MySQL later
means changing get_db() and a few type names in SCHEMA.

    from auth_db import init_auth, login_required, current_user
    init_auth(app, default_prescriptions, validate_fn)

Roles
  patient  does exercises; sessions are saved to their account
  doctor   (physiotherapist) links patients, sets prescriptions, reviews sessions, sends notes

Environment
  GEM_DB          database file            (default instance/abilityplus.db)
  GEM_SECRET_KEY  cookie signing key       (default: generated once, saved in instance/secret_key)
  GEM_DEMO=0      do not create the demo accounts on an empty database
"""
import json
import os
import secrets
import sqlite3
import time
from functools import wraps

from flask import Blueprint, Response, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

DEMO_PASSWORD = "demo1234"
DEMO_DOCTOR = ("doctor@abilityplus.demo", "Dr. Lea Martin")
DEMO_PATIENT = ("patient@abilityplus.demo", "Alex Morgan")
MIN_PASSWORD_LEN = 8
MAX_MESSAGE_LEN = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    role          TEXT NOT NULL CHECK (role IN ('patient', 'doctor')),
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS care_links (
    doctor_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (doctor_id, patient_id)
);

CREATE TABLE IF NOT EXISTS prescriptions (
    patient_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_key TEXT NOT NULL,
    params_json  TEXT NOT NULL,
    doctor_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (patient_id, exercise_key)
);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_key  TEXT,
    exercise      TEXT NOT NULL,
    side          TEXT,
    reps          INTEGER NOT NULL,
    target_reps   INTEGER,
    partial_reps  INTEGER,
    out_of_range  INTEGER,
    pain          INTEGER NOT NULL DEFAULT 0,
    completed     INTEGER NOT NULL DEFAULT 0,
    ended_by      TEXT,
    duration_sec  REAL,
    lowest_angle  REAL,
    highest_angle REAL,
    rom_deg       REAL,
    accuracy_pct  REAL,
    summary_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    reviewed_at   TEXT,
    reviewed_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    doctor_note   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_patient ON sessions(patient_id, created_at);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    read_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender_id, recipient_id, created_at);
"""

bp = Blueprint("auth_db", __name__)

# Set by init_auth()
_defaults = {}            # exercise_key -> default prescription (from main.py)
_validate = None          # fn(rx) -> complete rx, raises ValueError if invalid


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def db_path():
    return os.environ.get("GEM_DB", os.path.join(INSTANCE_DIR, "abilityplus.db"))


def get_db():
    if "db" not in g:
        path = db_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        g.db = sqlite3.connect(path, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@bp.teardown_app_request
def _close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def days_ago(n):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - n * 86400))


def _load_secret_key():
    key = os.environ.get("GEM_SECRET_KEY")
    if key:
        return key
    path = os.path.join(INSTANCE_DIR, "secret_key")
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        key = secrets.token_hex(32)
        with open(path, "w") as f:
            f.write(key)
        return key


def _create_user(db, role, name, email, password):
    cur = db.execute(
        "INSERT INTO users (role, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (role, name, email, generate_password_hash(password), now()))
    return cur.lastrowid


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    empty = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    if empty and os.environ.get("GEM_DEMO", "1") != "0":
        doctor_id = _create_user(db, "doctor", DEMO_DOCTOR[1], DEMO_DOCTOR[0], DEMO_PASSWORD)
        patient_id = _create_user(db, "patient", DEMO_PATIENT[1], DEMO_PATIENT[0], DEMO_PASSWORD)
        db.execute("INSERT INTO care_links (doctor_id, patient_id, created_at) VALUES (?, ?, ?)",
                   (doctor_id, patient_id, now()))
        print(f"Demo accounts created (password '{DEMO_PASSWORD}'): {DEMO_DOCTOR[0]}, {DEMO_PATIENT[0]}")
    db.commit()


def init_auth(app, default_prescriptions, validate_fn):
    """Call once after creating the Flask app."""
    global _defaults, _validate
    _defaults = default_prescriptions
    _validate = validate_fn
    app.secret_key = _load_secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=7 * 86400)
    app.register_blueprint(bp)
    with app.app_context():
        init_db()


# --------------------------------------------------
# CURRENT USER / ACCESS CONTROL
# --------------------------------------------------

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    if "user" not in g:
        row = get_db().execute("SELECT id, role, name, email FROM users WHERE id = ?", (uid,)).fetchone()
        g.user = dict(row) if row else None
        if row is None:
            session.clear()
    return g.user


def login_required(role=None):
    """Protects a route. API routes answer 401/403 JSON; pages redirect to /login."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            is_api = request.path.startswith("/api/")
            if user is None:
                if is_api:
                    return jsonify({"success": False, "error": "Please log in."}), 401
                return redirect("/login")
            if role and user["role"] != role:
                if is_api:
                    return jsonify({"success": False, "error": f"Only {role} accounts can do this."}), 403
                return redirect("/")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def is_linked(doctor_id, patient_id):
    return get_db().execute("SELECT 1 FROM care_links WHERE doctor_id = ? AND patient_id = ?",
                            (doctor_id, patient_id)).fetchone() is not None


def can_talk(a, b):
    """Messages are only allowed between a doctor and their linked patient."""
    return is_linked(a, b) or is_linked(b, a)


def _bad(msg, code=400):
    return jsonify({"success": False, "error": msg}), code


def _clean_email(value):
    return str(value or "").strip().lower()


# --------------------------------------------------
# PRESCRIPTIONS AND SESSIONS (used by main.py)
# --------------------------------------------------

def patient_prescriptions(patient_id):
    """Defaults from main.py, overridden by what the patient's physiotherapist saved."""
    out = {key: dict(rx) for key, rx in _defaults.items()}
    rows = get_db().execute("SELECT exercise_key, params_json, updated_at FROM prescriptions WHERE patient_id = ?",
                            (patient_id,)).fetchall()
    for row in rows:
        if row["exercise_key"] in out:
            out[row["exercise_key"]].update(json.loads(row["params_json"]))
            out[row["exercise_key"]]["updated_at"] = row["updated_at"]
    return out


def save_session_to_db(patient_id, summary):
    """Stores one finished exercise session. Returns the new session id."""
    fm = summary.get("finger_metrics") or {}
    db = get_db()
    cur = db.execute(
        """INSERT INTO sessions (patient_id, exercise_key, exercise, side, reps, target_reps, partial_reps,
               out_of_range, pain, completed, ended_by, duration_sec, lowest_angle, highest_angle, rom_deg,
               accuracy_pct, summary_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (patient_id, summary.get("ui_exercise"), summary.get("exercise"), summary.get("side"),
         int(summary.get("reps") or 0), (summary.get("prescription") or {}).get("reps"),
         summary.get("partial_reps"), summary.get("out_of_range"), int(bool(summary.get("pain"))),
         int(bool(summary.get("completed"))), summary.get("ended_by"), summary.get("duration_sec"),
         summary.get("lowest_angle"), summary.get("highest_angle"), summary.get("rom_deg"),
         fm.get("accuracy_pct", summary.get("accuracy_pct")), json.dumps(summary), summary.get("saved_at") or now()))
    db.commit()
    return cur.lastrowid


SESSION_COLUMNS = ("id, patient_id, exercise_key, exercise, side, reps, target_reps, partial_reps, out_of_range, "
                   "pain, completed, ended_by, duration_sec, lowest_angle, highest_angle, rom_deg, accuracy_pct, "
                   "created_at, reviewed_at, doctor_note")


def _session_dict(row):
    d = dict(row)
    d["pain"], d["completed"] = bool(d["pain"]), bool(d["completed"])
    d["needs_review"] = (d["pain"] or (d["out_of_range"] or 0) > 0) and d["reviewed_at"] is None
    return d


def _list_sessions(patient_id, limit=50):
    rows = get_db().execute(f"SELECT {SESSION_COLUMNS}, summary_json FROM sessions WHERE patient_id = ? "
                            "ORDER BY created_at DESC, id DESC LIMIT ?", (patient_id, limit)).fetchall()
    out = []
    for r in rows:
        d = _session_dict(r)
        try:
            summary = json.loads(d.pop("summary_json") or "{}")
        except ValueError:
            summary = {}
        d["active_sec"] = summary.get("active_sec")
        d["breaks"] = len(summary.get("breaks") or [])          # breathing breaks during the session
        fm = summary.get("finger_metrics")                       # finger opposition details (compact)
        d["finger"] = None if not fm else {k: fm.get(k) for k in
                                           ("avg_touch_sec", "consistency_pct", "missed_touches", "hardest_finger")}
        d["input"] = summary.get("input")                        # cognitive games: "camera" | "mouse"
        dt = summary.get("dual_task")                            # dual-task mode results (compact)
        d["dual"] = None if not dt else {
            "baseline_in_zone_pct": (dt.get("baseline") or {}).get("in_zone_pct"),
            "dual_in_zone_pct": (dt.get("dual") or {}).get("in_zone_pct"),
            "cost_pct": dt.get("dual_task_cost_pct"),
            "accuracy_pct": (dt.get("cognitive") or {}).get("accuracy_pct"),
            "mean_rt_sec": (dt.get("cognitive") or {}).get("mean_rt_sec"),
        }
        out.append(d)
    return out


def _stats(patient_id):
    db = get_db()
    week = days_ago(7)
    row = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(created_at >= ?) AS week,
                  COUNT(DISTINCT CASE WHEN created_at >= ? THEN substr(created_at, 1, 10) END) AS active_days,
                  SUM(completed) AS completed,
                  SUM(pain) AS pain,
                  SUM(out_of_range > 0) AS warnings,
                  SUM((pain = 1 OR out_of_range > 0) AND reviewed_at IS NULL) AS needs_review,
                  MAX(created_at) AS last_session
           FROM sessions WHERE patient_id = ?""", (week, week, patient_id)).fetchone()
    d = {k: (row[k] or 0) for k in ("total", "week", "active_days", "completed", "pain", "warnings", "needs_review")}
    d["last_session"] = row["last_session"]
    d["completion_pct"] = round(d["completed"] / d["total"] * 100) if d["total"] else None
    return d


# --------------------------------------------------
# PAGES
# --------------------------------------------------

@bp.route("/login")
def login_page():
    if current_user():
        return redirect("/")
    return send_from_directory(FRONTEND_DIR, "login.html")


@bp.route("/doctor")
@login_required("doctor")
def doctor_page():
    return send_from_directory(FRONTEND_DIR, "doctor.html")


@bp.route("/account-bar.js")
def account_bar_js():
    return send_from_directory(FRONTEND_DIR, "account-bar.js", mimetype="application/javascript")


# --------------------------------------------------
# API: AUTH
# --------------------------------------------------

@bp.route("/api/auth/register", methods=["POST"])
def api_register():
    body = request.get_json(silent=True) or {}
    role = body.get("role", "patient")
    name = str(body.get("name") or "").strip()
    email = _clean_email(body.get("email"))
    password = str(body.get("password") or "")
    if role not in ("patient", "doctor"):
        return _bad("Role must be patient or physiotherapist.")
    if not name or len(name) > 100:
        return _bad("Please enter your name.")
    if "@" not in email or len(email) > 200:
        return _bad("Please enter a valid email address.")
    if len(password) < MIN_PASSWORD_LEN:
        return _bad(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    db = get_db()
    try:
        uid = _create_user(db, role, name, email, password)
        db.commit()
    except sqlite3.IntegrityError:
        return _bad("An account with this email already exists.", 409)
    session.clear()
    session["user_id"] = uid
    session.permanent = True
    return jsonify({"success": True, "user": {"id": uid, "role": role, "name": name, "email": email}})


@bp.route("/api/auth/login", methods=["POST"])
def api_login():
    body = request.get_json(silent=True) or {}
    email = _clean_email(body.get("email"))
    row = get_db().execute("SELECT id, role, name, email, password_hash FROM users WHERE email = ?",
                           (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], str(body.get("password") or "")):
        return _bad("Wrong email or password.", 401)
    session.clear()
    session["user_id"] = row["id"]
    session.permanent = True
    return jsonify({"success": True, "user": {k: row[k] for k in ("id", "role", "name", "email")}})


@bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@bp.route("/api/auth/me")
def api_me():
    user = current_user()
    demo = get_db().execute("SELECT 1 FROM users WHERE email = ?", (DEMO_DOCTOR[0],)).fetchone() is not None
    return jsonify({"user": user, "demo_accounts": demo})


# --------------------------------------------------
# API: MESSAGES (both directions)
# --------------------------------------------------

@bp.route("/api/messages/<int:other_id>")
@login_required()
def api_messages(other_id):
    me = current_user()
    if not can_talk(me["id"], other_id):
        return _bad("You are not connected to this person.", 403)
    db = get_db()
    rows = db.execute(
        """SELECT id, sender_id, recipient_id, body, created_at, read_at FROM messages
           WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
           ORDER BY created_at, id""", (me["id"], other_id, other_id, me["id"])).fetchall()
    db.execute("UPDATE messages SET read_at = ? WHERE sender_id = ? AND recipient_id = ? AND read_at IS NULL",
               (now(), other_id, me["id"]))
    db.commit()
    return jsonify({"messages": [dict(r) | {"mine": r["sender_id"] == me["id"]} for r in rows]})


@bp.route("/api/messages/<int:other_id>", methods=["POST"])
@login_required()
def api_send_message(other_id):
    me = current_user()
    if not can_talk(me["id"], other_id):
        return _bad("You are not connected to this person.", 403)
    text = str((request.get_json(silent=True) or {}).get("body") or "").strip()
    if not text:
        return _bad("Message is empty.")
    if len(text) > MAX_MESSAGE_LEN:
        return _bad(f"Message is too long (max {MAX_MESSAGE_LEN} characters).")
    db = get_db()
    cur = db.execute("INSERT INTO messages (sender_id, recipient_id, body, created_at) VALUES (?, ?, ?, ?)",
                     (me["id"], other_id, text, now()))
    db.commit()
    return jsonify({"success": True, "id": cur.lastrowid})


@bp.route("/api/messages/unread")
@login_required()
def api_unread():
    rows = get_db().execute("SELECT sender_id, COUNT(*) AS n FROM messages WHERE recipient_id = ? AND read_at IS NULL "
                            "GROUP BY sender_id", (current_user()["id"],)).fetchall()
    return jsonify({"total": sum(r["n"] for r in rows), "by_sender": {str(r["sender_id"]): r["n"] for r in rows}})


# --------------------------------------------------
# API: PATIENT
# --------------------------------------------------

@bp.route("/api/patient/overview")
@login_required("patient")
def api_patient_overview():
    me = current_user()
    db = get_db()
    doctors = [dict(r) for r in db.execute(
        "SELECT u.id, u.name, u.email FROM care_links l JOIN users u ON u.id = l.doctor_id "
        "WHERE l.patient_id = ? ORDER BY l.created_at", (me["id"],)).fetchall()]
    return jsonify({"user": me, "doctors": doctors, "prescriptions": patient_prescriptions(me["id"]),
                    "stats": _stats(me["id"]), "sessions": _list_sessions(me["id"], 20)})


@bp.route("/api/patient/sessions")
@login_required("patient")
def api_patient_sessions():
    return jsonify({"sessions": _list_sessions(current_user()["id"], 200)})


# --------------------------------------------------
# API: DOCTOR
# --------------------------------------------------

def _require_patient(pid):
    """Returns (patient row, None) or (None, error response) if the doctor is not linked."""
    me = current_user()
    if not is_linked(me["id"], pid):
        return None, _bad("This patient is not on your list.", 404)
    row = get_db().execute("SELECT id, name, email, created_at FROM users WHERE id = ? AND role = 'patient'",
                           (pid,)).fetchone()
    if row is None:
        return None, _bad("This patient account no longer exists.", 404)
    return dict(row), None


@bp.route("/api/doctor/patients")
@login_required("doctor")
def api_doctor_patients():
    me = current_user()
    db = get_db()
    rows = db.execute(
        """SELECT u.id, u.name, u.email,
                  (SELECT COUNT(*) FROM messages m WHERE m.sender_id = u.id AND m.recipient_id = ? AND m.read_at IS NULL) AS unread
           FROM care_links l JOIN users u ON u.id = l.patient_id
           WHERE l.doctor_id = ?""", (me["id"], me["id"])).fetchall()
    patients = [dict(r) | {"stats": _stats(r["id"])} for r in rows]
    patients.sort(key=lambda p: (p["stats"]["needs_review"], p["unread"], p["stats"]["last_session"] or ""),
                  reverse=True)
    return jsonify({"patients": patients})


@bp.route("/api/doctor/patients", methods=["POST"])
@login_required("doctor")
def api_doctor_add_patient():
    me = current_user()
    email = _clean_email((request.get_json(silent=True) or {}).get("email"))
    db = get_db()
    row = db.execute("SELECT id, role, name FROM users WHERE email = ?", (email,)).fetchone()
    if row is None:
        return _bad("No account with this email. Ask the patient to register first.", 404)
    if row["role"] != "patient":
        return _bad("This account is not a patient account.")
    db.execute("INSERT OR IGNORE INTO care_links (doctor_id, patient_id, created_at) VALUES (?, ?, ?)",
               (me["id"], row["id"], now()))
    db.commit()
    return jsonify({"success": True, "patient": {"id": row["id"], "name": row["name"], "email": email}})


@bp.route("/api/doctor/patients/<int:pid>")
@login_required("doctor")
def api_doctor_patient(pid):
    patient, err = _require_patient(pid)
    if err:
        return err
    return jsonify({"patient": patient, "stats": _stats(pid), "prescriptions": patient_prescriptions(pid),
                    "sessions": _list_sessions(pid, 100)})


@bp.route("/api/doctor/patients/<int:pid>/prescriptions/<key>", methods=["POST"])
@login_required("doctor")
def api_doctor_set_prescription(pid, key):
    _, err = _require_patient(pid)
    if err:
        return err
    if key not in _defaults:
        return _bad(f"Unknown exercise '{key}'.", 404)
    body = request.get_json(silent=True) or {}
    current = patient_prescriptions(pid)[key]
    current.pop("updated_at", None)
    changes = {}
    try:
        for field in ("rest_angle", "target_angle", "safe_limit"):
            if field in body and body[field] not in (None, ""):
                value = float(body[field])
                changes[field] = int(value) if value.is_integer() else value
        if "reps" in body:
            changes["reps"] = int(body["reps"])
        if "side" in body:
            changes["side"] = str(body["side"])
        full = _validate({**current, **changes})
    except (ValueError, TypeError) as error:
        return _bad(str(error))
    stored = {k: full[k] for k in ("rest_angle", "target_angle", "safe_limit", "reps", "side") if k in full}
    db = get_db()
    db.execute("""INSERT INTO prescriptions (patient_id, exercise_key, params_json, doctor_id, updated_at)
                  VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(patient_id, exercise_key) DO UPDATE SET
                      params_json = excluded.params_json, doctor_id = excluded.doctor_id,
                      updated_at = excluded.updated_at""",
               (pid, key, json.dumps(stored), current_user()["id"], now()))
    db.commit()
    return jsonify({"success": True, "prescription": patient_prescriptions(pid)[key]})


@bp.route("/api/doctor/sessions/<int:sid>")
@login_required("doctor")
def api_doctor_session(sid):
    row = get_db().execute(f"SELECT {SESSION_COLUMNS}, summary_json FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None or not is_linked(current_user()["id"], row["patient_id"]):
        return _bad("Session not found.", 404)
    d = _session_dict(row)
    summary = json.loads(d.pop("summary_json"))
    summary.pop("events", None)
    d["summary"] = summary
    return jsonify({"session": d})


@bp.route("/api/doctor/sessions/<int:sid>/review", methods=["POST"])
@login_required("doctor")
def api_doctor_review(sid):
    me = current_user()
    db = get_db()
    row = db.execute("SELECT patient_id FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None or not is_linked(me["id"], row["patient_id"]):
        return _bad("Session not found.", 404)
    note = str((request.get_json(silent=True) or {}).get("note") or "").strip()[:MAX_MESSAGE_LEN] or None
    db.execute("UPDATE sessions SET reviewed_at = ?, reviewed_by = ?, doctor_note = ? WHERE id = ?",
               (now(), me["id"], note, sid))
    db.commit()
    return jsonify({"success": True})


@bp.route("/api/doctor/patients/<int:pid>/export")
@login_required("doctor")
def api_doctor_export(pid):
    patient, err = _require_patient(pid)
    if err:
        return err
    rows = get_db().execute(f"SELECT {SESSION_COLUMNS}, summary_json FROM sessions WHERE patient_id = ? "
                            "ORDER BY created_at", (pid,)).fetchall()
    sessions_out = []
    for r in rows:
        d = _session_dict(r)
        d["summary"] = json.loads(d.pop("summary_json"))
        sessions_out.append(d)
    payload = {"generated_at": now(), "patient": patient, "prescriptions": patient_prescriptions(pid),
               "note": "Prototype data. Angles are webcam estimates, not clinical measurements.",
               "sessions": sessions_out}
    return Response(json.dumps(payload, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=abilityplus-patient-{pid}.json"})
