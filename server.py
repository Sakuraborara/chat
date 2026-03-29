import argparse
import os
import sqlite3
import threading
from datetime import datetime
from functools import wraps
from secrets import token_urlsafe

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.environ.get("CHAT_DB_PATH", "chat_server.db")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7

app = Flask(__name__)
_db_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db_lock:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                msg_type TEXT NOT NULL,
                filename TEXT,
                ciphertext TEXT NOT NULL,
                nonce TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(recipient_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()
        conn.close()


def _cleanup_sessions(conn):
    now = int(datetime.utcnow().timestamp())
    conn.execute(
        "DELETE FROM sessions WHERE (? - created_at) > ?", (now, TOKEN_TTL_SECONDS)
    )


def auth_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "missing bearer token"}), 401

        token = auth.split(" ", 1)[1].strip()
        with _db_lock:
            conn = get_conn()
            _cleanup_sessions(conn)
            row = conn.execute(
                """
                SELECT u.id, u.username
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            conn.commit()
            conn.close()

        if not row:
            return jsonify({"error": "invalid or expired token"}), 401

        request.user = {"id": row["id"], "username": row["username"]}
        return func(*args, **kwargs)

    return wrapper


@app.post("/api/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if len(username) < 3:
        return jsonify({"error": "username must be at least 3 chars"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 chars"}), 400

    with _db_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
                (username, generate_password_hash(password), datetime.utcnow().isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "username already exists"}), 409
        conn.close()

    return jsonify({"ok": True})


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    with _db_lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            conn.close()
            return jsonify({"error": "invalid username or password"}), 401

        token = token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
            (token, row["id"], int(datetime.utcnow().timestamp())),
        )
        conn.commit()
        conn.close()

    return jsonify({"token": token, "username": username})


@app.post("/api/messages/send")
@auth_required
def send_message():
    payload = request.get_json(silent=True) or {}
    recipient = (payload.get("recipient") or "").strip()
    msg_type = payload.get("msg_type")
    filename = payload.get("filename")
    ciphertext = payload.get("ciphertext")
    nonce = payload.get("nonce")
    salt = payload.get("salt")

    if msg_type not in ("text", "file"):
        return jsonify({"error": "msg_type must be text or file"}), 400
    if not recipient or not ciphertext or not nonce or not salt:
        return jsonify({"error": "missing required fields"}), 400

    with _db_lock:
        conn = get_conn()
        recipient_row = conn.execute(
            "SELECT id FROM users WHERE username=?", (recipient,)
        ).fetchone()
        if not recipient_row:
            conn.close()
            return jsonify({"error": "recipient not found"}), 404

        conn.execute(
            """
            INSERT INTO messages(
                sender_id, recipient_id, msg_type, filename,
                ciphertext, nonce, salt, created_at, delivered
            ) VALUES(?,?,?,?,?,?,?,?,0)
            """,
            (
                request.user["id"],
                recipient_row["id"],
                msg_type,
                filename,
                ciphertext,
                nonce,
                salt,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    return jsonify({"ok": True})


@app.get("/api/messages/poll")
@auth_required
def poll_messages():
    with _db_lock:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT m.id, su.username AS sender, m.msg_type, m.filename,
                   m.ciphertext, m.nonce, m.salt, m.created_at
            FROM messages m
            JOIN users su ON su.id = m.sender_id
            WHERE m.recipient_id = ? AND m.delivered = 0
            ORDER BY m.id ASC
            """,
            (request.user["id"],),
        ).fetchall()

        ids = [r["id"] for r in rows]
        if ids:
            conn.execute(
                f"UPDATE messages SET delivered = 1 WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
        conn.commit()
        conn.close()

    return jsonify(
        {
            "messages": [
                {
                    "id": r["id"],
                    "sender": r["sender"],
                    "msg_type": r["msg_type"],
                    "filename": r["filename"],
                    "ciphertext": r["ciphertext"],
                    "nonce": r["nonce"],
                    "salt": r["salt"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        }
    )


@app.get("/api/messages/list")
@auth_required
def list_messages():
    with _db_lock:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT m.id, su.username AS sender, m.msg_type, m.filename, m.created_at, m.delivered
            FROM messages m
            JOIN users su ON su.id = m.sender_id
            WHERE m.recipient_id = ?
            ORDER BY m.id DESC
            LIMIT 100
            """,
            (request.user["id"],),
        ).fetchall()
        conn.close()

    return jsonify(
        {
            "messages": [dict(r) for r in rows],
        }
    )


def main():
    parser = argparse.ArgumentParser(description="Lightweight HTTPS chat server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=43623)
    parser.add_argument("--cert", default="cert.pem", help="TLS cert file")
    parser.add_argument("--key", default="key.pem", help="TLS private key")
    args = parser.parse_args()

    if not (os.path.exists(args.cert) and os.path.exists(args.key)):
        raise SystemExit(
            "Missing TLS files. Create cert.pem and key.pem (for example via OpenSSL) before startup."
        )

    init_db()
    app.run(host=args.host, port=args.port, ssl_context=(args.cert, args.key), threaded=True)


if __name__ == "__main__":
    main()
