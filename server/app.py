import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
INBOX_DIR = DATA_DIR / "inbox"
LOCK = Lock()


def _init_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]", encoding="utf-8")


def _load_users():
    return set(json.loads(USERS_FILE.read_text(encoding="utf-8")))


def _save_users(users):
    USERS_FILE.write_text(json.dumps(sorted(users), ensure_ascii=False, indent=2), encoding="utf-8")


def _inbox_file(username: str) -> Path:
    return INBOX_DIR / f"{username}.json"


def _append_inbox(username: str, item: dict):
    file = _inbox_file(username)
    payload = []
    if file.exists():
        payload = json.loads(file.read_text(encoding="utf-8"))
    payload.append(item)
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_and_clear_inbox(username: str):
    file = _inbox_file(username)
    if not file.exists():
        return []
    payload = json.loads(file.read_text(encoding="utf-8"))
    file.write_text("[]", encoding="utf-8")
    return payload


def _auth_user():
    username = request.headers.get("X-Username", "").strip()
    if not username:
        return None, (jsonify({"error": "缺少 X-Username 请求头"}), 401)
    users = _load_users()
    if username not in users:
        return None, (jsonify({"error": f"用户 {username} 未注册"}), 403)
    return username, None


@app.post("/api/register")
def register():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    if not username:
        return jsonify({"error": "username 不能为空"}), 400
    with LOCK:
        users = _load_users()
        users.add(username)
        _save_users(users)
    return jsonify({"ok": True, "username": username})


@app.post("/api/send_message")
def send_message():
    sender, err = _auth_user()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    target = str(body.get("to", "")).strip()
    message = str(body.get("message", "")).strip()
    if not target or not message:
        return jsonify({"error": "to 和 message 必填"}), 400

    users = _load_users()
    if target not in users:
        return jsonify({"error": f"目标用户 {target} 不存在"}), 404

    item = {
        "type": "message",
        "from": sender,
        "to": target,
        "message": message,
        "at": datetime.utcnow().isoformat() + "Z",
    }
    with LOCK:
        _append_inbox(target, item)
    return jsonify({"ok": True})


@app.post("/api/send_file")
def send_file():
    sender, err = _auth_user()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    target = str(body.get("to", "")).strip()
    filename = str(body.get("filename", "")).strip()
    content_b64 = str(body.get("content_b64", "")).strip()
    if not target or not filename or not content_b64:
        return jsonify({"error": "to、filename、content_b64 必填"}), 400

    users = _load_users()
    if target not in users:
        return jsonify({"error": f"目标用户 {target} 不存在"}), 404

    item = {
        "type": "file",
        "from": sender,
        "to": target,
        "filename": filename,
        "content_b64": content_b64,
        "at": datetime.utcnow().isoformat() + "Z",
    }
    with LOCK:
        _append_inbox(target, item)
    return jsonify({"ok": True})


@app.get("/api/inbox")
def inbox():
    username, err = _auth_user()
    if err:
        return err
    with LOCK:
        items = _read_and_clear_inbox(username)
    return jsonify({"items": items})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


if __name__ == "__main__":
    _init_storage()
    parser = argparse.ArgumentParser(description="HTTPS messenger server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert", default=str(BASE_DIR / "certs" / "server.crt"))
    parser.add_argument("--key", default=str(BASE_DIR / "certs" / "server.key"))
    args = parser.parse_args()

    if not (os.path.exists(args.cert) and os.path.exists(args.key)):
        raise SystemExit(
            "证书不存在，请先运行部署面板 install 生成证书。"
            f"\ncert={args.cert}\nkey={args.key}"
        )

    app.run(host=args.host, port=args.port, ssl_context=(args.cert, args.key))
