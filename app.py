"""Site Labour Attendance: a small single-page Flask application."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import hmac
import logging
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

ROOT = Path(__file__).resolve().parent
INSTANCE = ROOT / "instance"
INSTANCE.mkdir(parents=True, exist_ok=True)
DEFAULT_DB = INSTANCE / "attendance.db"
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["DATABASE_PATH"] = os.environ.get("DATABASE_PATH", str(DEFAULT_DB))
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = app.logger

@contextmanager
def db_connect():
    path = Path(app.config["DATABASE_PATH"])
    if not path.parent.is_dir():
        raise OSError(f"Database directory is unavailable: {path.parent}")
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS attendance (
          id INTEGER PRIMARY KEY, attendance_date TEXT NOT NULL UNIQUE,
          labour_count INTEGER NOT NULL CHECK(labour_count >= 0),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")

def now_iso():
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")

def valid_date(value):
    if not isinstance(value, str) or len(value) != 10: return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except (TypeError, ValueError): return None

def valid_count(value):
    if isinstance(value, bool): return None
    s = str(value)
    if not s.isdecimal(): return None
    number = int(s)
    return number if number <= 9223372036854775807 else None

def row_dict(row): return dict(row) if row else None

@app.before_request
def csrf_check():
    if "csrf" not in session: session["csrf"] = secrets.token_urlsafe(32)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied, session["csrf"]):
            return jsonify(error="Your session expired. Reload the page and try again."), 400

@app.errorhandler(sqlite3.Error)
@app.errorhandler(OSError)
def database_error(exc):
    log.exception("Attendance database operation failed")
    return jsonify(error="The attendance database is unavailable. No changes were made."), 503

@app.get("/")
def index():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    return render_template("index.html", today=today, csrf=session["csrf"])

@app.get("/api/attendance")
def list_attendance():
    month = request.args.get("month", "")
    try:
        year, mon = map(int, month.split("-"))
        if not 1 <= mon <= 12 or not 2000 <= year <= 9999: raise ValueError
    except ValueError: return jsonify(error="Select a valid month."), 400
    with db_connect() as conn:
        recent = conn.execute("SELECT * FROM attendance ORDER BY attendance_date DESC LIMIT 5").fetchall()
        all_rows = conn.execute("SELECT * FROM attendance ORDER BY attendance_date DESC").fetchall()
        monthly = conn.execute("SELECT * FROM attendance WHERE substr(attendance_date,1,7)=? ORDER BY attendance_date", (month,)).fetchall()
    return jsonify(recent=[row_dict(r) for r in recent], all=[row_dict(r) for r in all_rows],
                   month=[row_dict(r) for r in monthly], total=sum(r["labour_count"] for r in monthly), days=len(monthly))

@app.get("/api/attendance/by-date/<date_text>")
def by_date(date_text):
    if not valid_date(date_text): return jsonify(error="Select a valid date."), 400
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM attendance WHERE attendance_date=?", (date_text,)).fetchone()
    return jsonify(record=row_dict(row))

@app.post("/api/attendance")
def create_attendance():
    data = request.get_json(silent=True) or {}
    d, count = valid_date(data.get("date")), valid_count(data.get("count"))
    if not d or count is None: return jsonify(error="Enter a valid date and a non-negative whole-number labour count."), 400
    timestamp = now_iso()
    with db_connect() as conn:
        existing = conn.execute("SELECT * FROM attendance WHERE attendance_date=?", (d.isoformat(),)).fetchone()
        if existing: return jsonify(error="That date already has attendance. Confirm an update before saving.", existing=row_dict(existing)), 409
        conn.execute("INSERT INTO attendance(attendance_date,labour_count,created_at,updated_at) VALUES(?,?,?,?)", (d.isoformat(), count, timestamp, timestamp))
    return jsonify(message="Attendance saved.")

@app.put("/api/attendance/<int:record_id>")
def update_attendance(record_id):
    data = request.get_json(silent=True) or {}
    d, count = valid_date(data.get("date")), valid_count(data.get("count"))
    if not d or count is None: return jsonify(error="Enter a valid date and a non-negative whole-number labour count."), 400
    replace_id = data.get("replace_id")
    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        source = conn.execute("SELECT * FROM attendance WHERE id=?", (record_id,)).fetchone()
        if not source: return jsonify(error="This attendance record no longer exists."), 404
        target = conn.execute("SELECT * FROM attendance WHERE attendance_date=? AND id<>?", (d.isoformat(), record_id)).fetchone()
        if target and str(replace_id or "") != str(target["id"]):
            return jsonify(error="The destination date already has attendance. Confirm replacement explicitly to replace that record.", destination=row_dict(target)), 409
        if target: conn.execute("DELETE FROM attendance WHERE id=?", (target["id"],))
        conn.execute("UPDATE attendance SET attendance_date=?, labour_count=?, updated_at=? WHERE id=?", (d.isoformat(), count, now_iso(), record_id))
    return jsonify(message="Attendance updated." + (" The destination record was replaced." if target else ""))

@app.delete("/api/attendance/<int:record_id>")
def delete_attendance(record_id):
    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM attendance WHERE id=?", (record_id,)).fetchone()
        if not row: return jsonify(error="This attendance record no longer exists."), 404
        conn.execute("DELETE FROM attendance WHERE id=?", (record_id,))
    return jsonify(message="Attendance deleted.")

with app.app_context(): init_db()

if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
