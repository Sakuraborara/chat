from __future__ import annotations

import base64
import binascii
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "messages.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
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
    app.config["API_KEY"] = os.getenv("CHAT_API_KEY", "change-me")

    def _authorized() -> bool:
        api_key = request.headers.get("X-API-Key", "")
        return bool(api_key and api_key == app.config["API_KEY"])

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok", "time": utc_now()}, 200

    @app.post("/api/send")
    def send_message():
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        sender = (payload.get("sender") or "").strip()
        recipient = (payload.get("recipient") or "").strip()
        message = (payload.get("message") or "").strip()
        file_name = payload.get("file_name")
        file_content_b64 = payload.get("file_content_b64")

        if not sender or not recipient:
            return jsonify({"error": "sender and recipient are required"}), 400

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
            full_path = UPLOAD_DIR / stored_name
            full_path.write_bytes(raw)
            file_path = stored_name

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, sender, recipient, message, file_name, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, sender, recipient, message, safe_file_name, file_path, utc_now()),
            )
            conn.commit()

        return jsonify({"status": "sent", "id": message_id}), 201

    @app.get("/api/inbox/<username>")
    def inbox(username: str):
        if not _authorized():
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
                (username, limit),
            ).fetchall()

        data = []
        for row in rows:
            item = dict(row)
            item["download_url"] = f"/api/messages/{item['id']}/download" if item.get("file_path") else None
            data.append(item)
        return jsonify({"items": data}), 200

    @app.get("/api/messages/<message_id>/download")
    def download_by_message(message_id: str):
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        with _connect() as conn:
            row = conn.execute(
                "SELECT file_path FROM messages WHERE id = ? AND file_path IS NOT NULL",
                (message_id,),
            ).fetchone()
        if not row:
            return jsonify({"error": "file not found"}), 404
        return send_from_directory(UPLOAD_DIR, row["file_path"], as_attachment=True)

    return app


init_db()
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
