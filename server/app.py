from __future__ import annotations

import base64
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

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}, 200

    def _authorized() -> bool:
        api_key = request.headers.get("X-API-Key", "")
        return api_key and api_key == app.config["API_KEY"]

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
            raw = base64.b64decode(file_content_b64)
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
                (
                    message_id,
                    sender,
                    recipient,
                    message,
                    safe_file_name,
                    file_path,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

        return jsonify({"status": "sent", "id": message_id}), 201

    @app.get("/api/inbox/<username>")
    def inbox(username: str):
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401

        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, sender, recipient, message, file_name, file_path, created_at
                FROM messages
                WHERE recipient = ?
                ORDER BY created_at DESC
                LIMIT 200
                """,
                (username,),
            ).fetchall()

        data = []
        for row in rows:
            item = dict(row)
            if item.get("file_path"):
                item["download_url"] = f"/api/file/{item['file_path']}"
            else:
                item["download_url"] = None
            data.append(item)

        return jsonify({"items": data}), 200

    @app.get("/api/file/<path:stored_name>")
    def get_file(stored_name: str):
        if not _authorized():
            return jsonify({"error": "Unauthorized"}), 401
        return send_from_directory(UPLOAD_DIR, stored_name, as_attachment=True)

    return app


init_db()
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
