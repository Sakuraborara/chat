#!/usr/bin/env python3
"""Windows 本地客户端（Tkinter）.

功能：
- 输入服务器地址
- 注册/登录
- 向指定用户发送文本或文件
- 每条消息独立密码 + AES-256-GCM 加密
- 拉取离线消息并解密/保存
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    return kdf.derive(password.encode("utf-8"))


def encrypt_payload(raw_bytes: bytes, message_password: str) -> dict:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(message_password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)
    return {
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "salt_b64": base64.b64encode(salt).decode(),
    }


def decrypt_payload(ciphertext_b64: str, nonce_b64: str, salt_b64: str, message_password: str) -> bytes:
    salt = base64.b64decode(salt_b64)
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    key = derive_key(message_password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


class ChatClientUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Secure Local Chat Client")
        self.token = None

        self.server_var = tk.StringVar(value="https://127.0.0.1:43623")
        self.user_var = tk.StringVar()
        self.pass_var = tk.StringVar()
        self.recipient_var = tk.StringVar()
        self.msg_pass_var = tk.StringVar()

        self._build_ui()

    def _build_ui(self) -> None:
        frm = tk.Frame(self.root, padx=8, pady=8)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="服务器 URL").grid(row=0, column=0, sticky="w")
        tk.Entry(frm, textvariable=self.server_var, width=50).grid(row=0, column=1, columnspan=4, sticky="we")

        tk.Label(frm, text="用户名").grid(row=1, column=0, sticky="w")
        tk.Entry(frm, textvariable=self.user_var, width=18).grid(row=1, column=1, sticky="w")
        tk.Label(frm, text="登录密码").grid(row=1, column=2, sticky="w")
        tk.Entry(frm, textvariable=self.pass_var, show="*", width=18).grid(row=1, column=3, sticky="w")
        tk.Button(frm, text="注册", command=self.register).grid(row=1, column=4)
        tk.Button(frm, text="登录", command=self.login).grid(row=1, column=5)

        tk.Label(frm, text="收件人").grid(row=2, column=0, sticky="w")
        tk.Entry(frm, textvariable=self.recipient_var, width=18).grid(row=2, column=1, sticky="w")
        tk.Label(frm, text="本次消息密码").grid(row=2, column=2, sticky="w")
        tk.Entry(frm, textvariable=self.msg_pass_var, show="*", width=18).grid(row=2, column=3, sticky="w")

        tk.Label(frm, text="消息文本").grid(row=3, column=0, sticky="nw")
        self.text_input = scrolledtext.ScrolledText(frm, width=70, height=8)
        self.text_input.grid(row=3, column=1, columnspan=5, sticky="we")

        tk.Button(frm, text="发送文本", command=self.send_text).grid(row=4, column=1, sticky="w")
        tk.Button(frm, text="发送文件", command=self.send_file).grid(row=4, column=2, sticky="w")
        tk.Button(frm, text="拉取消息", command=self.pull_messages).grid(row=4, column=3, sticky="w")

        tk.Label(frm, text="收件箱日志").grid(row=5, column=0, sticky="nw")
        self.log_box = scrolledtext.ScrolledText(frm, width=70, height=12)
        self.log_box.grid(row=5, column=1, columnspan=5, sticky="we")

    def _headers(self) -> dict:
        if not self.token:
            raise RuntimeError("请先登录")
        return {"Authorization": f"Bearer {self.token}"}

    def _server(self) -> str:
        return self.server_var.get().rstrip("/")

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self._server()}{path}"
        kwargs.setdefault("timeout", 10)
        return requests.request(method, url, verify=True, **kwargs)

    def register(self):
        try:
            r = self._request(
                "POST",
                "/register",
                json={"username": self.user_var.get(), "password": self.pass_var.get()},
            )
            if r.ok:
                messagebox.showinfo("成功", "注册成功")
            else:
                messagebox.showerror("失败", r.text)
        except Exception as e:
            messagebox.showerror("异常", str(e))

    def login(self):
        try:
            r = self._request(
                "POST",
                "/login",
                json={"username": self.user_var.get(), "password": self.pass_var.get()},
            )
            if not r.ok:
                messagebox.showerror("登录失败", r.text)
                return
            self.token = r.json()["token"]
            messagebox.showinfo("成功", "登录成功")
        except Exception as e:
            messagebox.showerror("异常", str(e))

    def send_text(self):
        msg = self.text_input.get("1.0", "end").strip()
        if not msg:
            messagebox.showwarning("提示", "消息不能为空")
            return
        self._send_encrypted("text", msg.encode("utf-8"), None)

    def send_file(self):
        file_path = filedialog.askopenfilename()
        if not file_path:
            return
        data = Path(file_path).read_bytes()
        self._send_encrypted("file", data, Path(file_path).name)

    def _send_encrypted(self, payload_type: str, raw: bytes, filename: str | None):
        try:
            payload = encrypt_payload(raw, self.msg_pass_var.get())
            body = {
                "recipient": self.recipient_var.get(),
                "payload_type": payload_type,
                "filename": filename,
                **payload,
            }
            r = self._request("POST", "/messages/send", json=body, headers=self._headers())
            if r.ok:
                self.log_box.insert("end", f"[发送成功] to={self.recipient_var.get()} type={payload_type}\n")
            else:
                self.log_box.insert("end", f"[发送失败] {r.text}\n")
        except Exception as e:
            messagebox.showerror("异常", str(e))

    def pull_messages(self):
        try:
            r = self._request("POST", "/messages/pull", json={"limit": 50}, headers=self._headers())
            if not r.ok:
                self.log_box.insert("end", f"[拉取失败] {r.text}\n")
                return
            msgs = r.json().get("messages", [])
            if not msgs:
                self.log_box.insert("end", "[无新消息]\n")
                return

            password = self.msg_pass_var.get()
            save_dir = Path("downloads")
            save_dir.mkdir(exist_ok=True)
            for m in msgs:
                try:
                    plain = decrypt_payload(m["ciphertext_b64"], m["nonce_b64"], m["salt_b64"], password)
                except Exception:
                    self.log_box.insert("end", f"[解密失败] id={m['id']} sender={m['sender']}（密码不匹配）\n")
                    continue

                if m["payload_type"] == "text":
                    text = plain.decode("utf-8", errors="replace")
                    self.log_box.insert("end", f"[文本] from={m['sender']} id={m['id']} msg={text}\n")
                else:
                    filename = m.get("filename") or f"file_{m['id']}.bin"
                    out = save_dir / filename
                    out.write_bytes(plain)
                    self.log_box.insert("end", f"[文件] from={m['sender']} id={m['id']} 保存到 {out}\n")
        except Exception as e:
            messagebox.showerror("异常", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClientUI(root)
    root.mainloop()
