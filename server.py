#!/usr/bin/env python3
"""轻量化 HTTPS 消息服务端。

功能：
- 注册 / 登录
- 发送端到端加密（服务端仅存密文）消息/文件
- 离线消息队列（收件人上线后拉取）
- 监听 43623 端口
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path("chat_server.db")
DEFAULT_PORT = 43623

app = FastAPI(title="Lightweight Secure Chat Server", version="1.0.0")


@dataclass
class UserContext:
    user_id: int
    username: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class SendMessageRequest(BaseModel):
    recipient: str
    payload_type: str = Field(pattern="^(text|file)$")
    ciphertext_b64: str
    nonce_b64: str
    salt_b64: str
    filename: Optional[str] = None


class PullRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            payload_type TEXT NOT NULL,
            ciphertext_b64 TEXT NOT NULL,
            nonce_b64 TEXT NOT NULL,
            salt_b64 TEXT NOT NULL,
            filename TEXT,
            created_at INTEGER NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0,
            delivered_at INTEGER,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_recipient_delivered ON messages(recipient_id, delivered)")
    conn.commit()
    conn.close()


def hash_password(password: str, salt: bytes) -> str:
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000, dklen=32)
    return hashed.hex()


def auth_user(authorization: Optional[str] = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    conn = db_conn()
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT users.id AS user_id, users.username
        FROM sessions
        JOIN users ON sessions.user_id = users.id
        WHERE sessions.token = ?
        """,
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="无效 token")
    return UserContext(user_id=row["user_id"], username=row["username"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "time": int(time.time())}


@app.post("/register")
def register(req: RegisterRequest) -> dict:
    salt = os.urandom(16)
    password_hash = hash_password(req.password, salt)
    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users(username, password_hash, password_salt, created_at) VALUES(?,?,?,?)",
            (req.username, password_hash, salt.hex(), int(time.time())),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已存在")
    finally:
        conn.close()
    return {"ok": True}


@app.post("/login")
def login(req: LoginRequest) -> dict:
    conn = db_conn()
    cur = conn.cursor()
    user = cur.execute("SELECT id, username, password_hash, password_salt FROM users WHERE username = ?", (req.username,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    expected = hash_password(req.password, bytes.fromhex(user["password_salt"]))
    if not secrets.compare_digest(expected, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = secrets.token_urlsafe(32)
    cur.execute("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", (token, user["id"], int(time.time())))
    conn.commit()
    conn.close()
    return {"token": token, "username": user["username"]}


@app.post("/messages/send")
def send_message(req: SendMessageRequest, user: UserContext = Depends(auth_user)) -> dict:
    conn = db_conn()
    cur = conn.cursor()
    recipient_row = cur.execute("SELECT id FROM users WHERE username = ?", (req.recipient,)).fetchone()
    if not recipient_row:
        conn.close()
        raise HTTPException(status_code=404, detail="收件人不存在")

    cur.execute(
        """
        INSERT INTO messages(
            sender_id, recipient_id, payload_type,
            ciphertext_b64, nonce_b64, salt_b64, filename,
            created_at, delivered
        ) VALUES(?,?,?,?,?,?,?,?,0)
        """,
        (
            user.user_id,
            recipient_row["id"],
            req.payload_type,
            req.ciphertext_b64,
            req.nonce_b64,
            req.salt_b64,
            req.filename,
            int(time.time()),
        ),
    )
    message_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "message_id": message_id}


@app.post("/messages/pull")
def pull_messages(req: PullRequest, user: UserContext = Depends(auth_user)) -> dict:
    conn = db_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT m.id, u.username AS sender, m.payload_type, m.ciphertext_b64,
               m.nonce_b64, m.salt_b64, m.filename, m.created_at
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? AND m.delivered = 0
        ORDER BY m.id ASC
        LIMIT ?
        """,
        (user.user_id, req.limit),
    ).fetchall()

    ids = [r["id"] for r in rows]
    if ids:
        cur.execute(
            f"UPDATE messages SET delivered = 1, delivered_at = ? WHERE id IN ({','.join('?' for _ in ids)})",
            (int(time.time()), *ids),
        )
        conn.commit()
    conn.close()

    return {
        "messages": [
            {
                "id": r["id"],
                "sender": r["sender"],
                "payload_type": r["payload_type"],
                "ciphertext_b64": r["ciphertext_b64"],
                "nonce_b64": r["nonce_b64"],
                "salt_b64": r["salt_b64"],
                "filename": r["filename"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


if __name__ == "__main__":
    import uvicorn

    certfile = os.getenv("TLS_CERTFILE", "cert.pem")
    keyfile = os.getenv("TLS_KEYFILE", "key.pem")
    if not (Path(certfile).exists() and Path(keyfile).exists()):
        raise SystemExit(
            "需要 HTTPS 证书。请先准备 cert.pem 和 key.pem，或通过 TLS_CERTFILE/TLS_KEYFILE 指定路径。"
        )
    uvicorn.run("server:app", host="0.0.0.0", port=DEFAULT_PORT, ssl_certfile=certfile, ssl_keyfile=keyfile)
