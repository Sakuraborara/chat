from __future__ import annotations

import base64
import binascii
import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "messages.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SESSION_TTL_HOURS = 24 * 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_str() -> str:
    return utc_now().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                message TEXT,
                file_name TEXT,
                file_path TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def create_app() -> Flask:
    app = Flask(__name__)

    def current_user() -> str | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.replace("Bearer ", "", 1).strip()
        if not token:
            return None
        with _connect() as conn:
            row = conn.execute(
                "SELECT username, expires_at FROM sessions WHERE token = ?",
                (token,),
            ).fetchone()
            if not row:
                return None
            if datetime.fromisoformat(row["expires_at"]) < utc_now():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
            return str(row["username"])

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok", "time": utc_now_str()}, 200

    @app.post("/api/register")
    def register():
        payload = request.get_json(silent=True) or {}
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""

        if len(username) < 3 or len(password) < 6:
            return jsonify({"error": "username>=3 and password>=6"}), 400

        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)
        try:
            with _connect() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                    (username, password_hash, salt, utc_now_str()),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "username already exists"}), 409

        return jsonify({"status": "registered", "username": username}), 201

    @app.post("/api/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""

        with _connect() as conn:
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                return jsonify({"error": "invalid credentials"}), 401

            if row["password_hash"] != hash_password(password, row["salt"]):
                return jsonify({"error": "invalid credentials"}), 401

            token = str(uuid.uuid4())
            expires_at = (utc_now() + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
            conn.execute(
                "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, username, utc_now_str(), expires_at),
            )
            conn.commit()

        return jsonify({"status": "ok", "token": token, "username": username, "expires_at": expires_at}), 200

    @app.post("/api/send")
    def send_message():
        user = current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        recipient = (payload.get("recipient") or "").strip()
        message = (payload.get("message") or "").strip()
        file_name = payload.get("file_name")
        file_content_b64 = payload.get("file_content_b64")

        if not recipient:
            return jsonify({"error": "recipient is required"}), 400

        message_id = str(uuid.uuid4())
        file_path = None
        safe_file_name = None

        if file_name and file_content_b64:
            safe_file_name = Path(file_name).name
            try:
                raw = base64.b64decode(file_content_b64, validate=True)
            except (binascii.Error, ValueError):
                return jsonify({"error": "invalid file content"}), 400
            stored_name = f"{message_id}_{safe_file_name}"
            (UPLOAD_DIR / stored_name).write_bytes(raw)
            file_path = stored_name

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, sender, recipient, message, file_name, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, user, recipient, message, safe_file_name, file_path, utc_now_str()),
            )
            conn.commit()

        return jsonify({"status": "sent", "id": message_id}), 201

    @app.get("/api/inbox")
    def inbox():
        user = current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        limit = min(max(int(request.args.get("limit", 200)), 1), 500)
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, sender, recipient, message, file_name, file_path, created_at
                FROM messages
                WHERE recipient = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user, limit),
            ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["download_url"] = f"/api/messages/{item['id']}/download" if item.get("file_path") else None
            items.append(item)
        return jsonify({"items": items, "username": user}), 200

    @app.get("/api/messages/<message_id>/download")
    def download_by_message(message_id: str):
        user = current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT file_path FROM messages
                WHERE id = ? AND recipient = ? AND file_path IS NOT NULL
                """,
                (message_id, user),
            ).fetchone()

        if not row:
            return jsonify({"error": "file not found"}), 404
        return send_from_directory(UPLOAD_DIR, row["file_path"], as_attachment=True)

    return app


init_db()
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
