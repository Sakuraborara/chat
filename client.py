import base64
import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

POLL_SECONDS = 5
CONFIG_PATH = Path("client_config.json")


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    return kdf.derive(password.encode("utf-8"))


def encrypt_data(data: bytes, password: str):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(password, salt)
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, data, None)
    return (
        base64.b64encode(ciphertext).decode("utf-8"),
        base64.b64encode(nonce).decode("utf-8"),
        base64.b64encode(salt).decode("utf-8"),
    )


def decrypt_data(ciphertext_b64: str, nonce_b64: str, salt_b64: str, password: str) -> bytes:
    ciphertext = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    salt = base64.b64decode(salt_b64)
    key = derive_key(password, salt)
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, None)


class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HTTPS AES-256 本地通讯客户端")
        self.root.geometry("980x720")

        self.server_var = tk.StringVar(value="https://127.0.0.1:43623")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.recipient_var = tk.StringVar()

        self.token = None
        self.running = False
        self.msg_queue = queue.Queue()
        self.insecure_skip_verify_var = tk.BooleanVar(value=False)
        self.ca_cert_path_var = tk.StringVar()

        self._build_ui()
        self._load_config()
        self._schedule_queue_pump()

    def _build_ui(self):
        top = tk.LabelFrame(self.root, text="服务器与登录")
        top.pack(fill="x", padx=8, pady=8)

        tk.Label(top, text="服务器地址(HTTPS):").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        tk.Entry(top, width=45, textvariable=self.server_var).grid(row=0, column=1, sticky="w", padx=5, pady=4)
        tk.Button(top, text="保存地址", command=self.save_config).grid(row=0, column=2, padx=5, pady=4)
        tk.Checkbutton(
            top,
            text="跳过证书校验(不安全，仅测试)",
            variable=self.insecure_skip_verify_var,
        ).grid(row=0, column=3, columnspan=2, sticky="w", padx=5, pady=4)

        tk.Label(top, text="自定义CA证书(可选):").grid(row=0, column=5, sticky="w", padx=5, pady=4)
        tk.Entry(top, width=26, textvariable=self.ca_cert_path_var).grid(row=0, column=6, sticky="w", padx=5, pady=4)
        tk.Button(top, text="选择证书", command=self.pick_ca_cert).grid(row=0, column=7, padx=5, pady=4)

        tk.Label(top, text="用户名:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        tk.Entry(top, width=20, textvariable=self.username_var).grid(row=1, column=1, sticky="w", padx=5, pady=4)

        tk.Label(top, text="登录密码:").grid(row=1, column=2, sticky="w", padx=5, pady=4)
        tk.Entry(top, width=20, show="*", textvariable=self.password_var).grid(row=1, column=3, sticky="w", padx=5, pady=4)

        tk.Button(top, text="注册", command=self.register).grid(row=1, column=4, padx=5, pady=4)
        tk.Button(top, text="登录", command=self.login).grid(row=1, column=5, padx=5, pady=4)

        mid = tk.LabelFrame(self.root, text="发送")
        mid.pack(fill="x", padx=8, pady=8)

        tk.Label(mid, text="收件人用户名:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        tk.Entry(mid, width=22, textvariable=self.recipient_var).grid(row=0, column=1, sticky="w", padx=5, pady=4)

        tk.Label(mid, text="文本消息:").grid(row=1, column=0, sticky="nw", padx=5, pady=4)
        self.message_input = scrolledtext.ScrolledText(mid, width=80, height=8)
        self.message_input.grid(row=1, column=1, columnspan=5, sticky="we", padx=5, pady=4)

        tk.Button(mid, text="发送文本(设置本次密码)", command=self.send_text).grid(row=2, column=1, sticky="w", padx=5, pady=4)
        tk.Button(mid, text="发送文件(设置本次密码)", command=self.send_file).grid(row=2, column=2, sticky="w", padx=5, pady=4)

        lower = tk.LabelFrame(self.root, text="接收列表")
        lower.pack(fill="both", expand=True, padx=8, pady=8)

        self.received_list = tk.Listbox(lower, height=15)
        self.received_list.pack(fill="both", expand=True, padx=5, pady=5)
        self.received_list.bind("<Double-Button-1>", self.open_selected_message)

        self.log = scrolledtext.ScrolledText(self.root, width=100, height=10)
        self.log.pack(fill="both", padx=8, pady=(0, 8))

    def _log(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def _request(self, method, path, **kwargs):
        url = self.server_var.get().rstrip("/") + path
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        verify = self._tls_verify_value()
        return requests.request(method, url, headers=headers, timeout=10, verify=verify, **kwargs)

    def _tls_verify_value(self):
        if self.insecure_skip_verify_var.get():
            return False
        cert_path = self.ca_cert_path_var.get().strip()
        if cert_path:
            return cert_path
        return True

    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                obj = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.server_var.set(obj.get("server", self.server_var.get()))
                self.insecure_skip_verify_var.set(bool(obj.get("insecure_skip_verify", False)))
                self.ca_cert_path_var.set(obj.get("ca_cert_path", ""))
            except Exception:
                pass

    def save_config(self):
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "server": self.server_var.get(),
                    "insecure_skip_verify": self.insecure_skip_verify_var.get(),
                    "ca_cert_path": self.ca_cert_path_var.get().strip(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._log("已保存服务器地址。")

    def pick_ca_cert(self):
        path = filedialog.askopenfilename(title="选择CA证书", filetypes=[("PEM/CRT", "*.pem *.crt"), ("All", "*.*")])
        if path:
            self.ca_cert_path_var.set(path)

    def register(self):
        try:
            resp = self._request(
                "POST",
                "/api/register",
                json={"username": self.username_var.get().strip(), "password": self.password_var.get()},
            )
            if resp.ok:
                messagebox.showinfo("成功", "注册成功，请登录")
            else:
                messagebox.showerror("错误", resp.text)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def login(self):
        try:
            resp = self._request(
                "POST",
                "/api/login",
                json={"username": self.username_var.get().strip(), "password": self.password_var.get()},
            )
            if not resp.ok:
                messagebox.showerror("登录失败", resp.text)
                return

            data = resp.json()
            self.token = data["token"]
            self._log(f"已登录: {data['username']}")
            self.start_polling()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def start_polling(self):
        if self.running:
            return
        self.running = True

        def worker():
            while self.running:
                try:
                    resp = self._request("GET", "/api/messages/poll")
                    if resp.ok:
                        for msg in resp.json().get("messages", []):
                            self.msg_queue.put(msg)
                except Exception as e:
                    self.msg_queue.put({"error": str(e)})
                finally:
                    threading.Event().wait(POLL_SECONDS)

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_queue_pump(self):
        while not self.msg_queue.empty():
            msg = self.msg_queue.get_nowait()
            if "error" in msg:
                self._log(f"轮询错误: {msg['error']}")
                continue
            label = f"#{msg['id']} 来自:{msg['sender']} 类型:{msg['msg_type']} 时间:{msg['created_at']}"
            if msg.get("filename"):
                label += f" 文件:{msg['filename']}"
            self.received_list.insert(tk.END, label)
            self.received_list.itemconfig(tk.END, {'fg': 'blue'})
            self.received_list.insert(tk.END, json.dumps(msg, ensure_ascii=False))
            self._ack_messages([msg["id"]])
        self.root.after(1000, self._schedule_queue_pump)

    def _ack_messages(self, ids):
        try:
            resp = self._request("POST", "/api/messages/ack", json={"message_ids": ids})
            if not resp.ok:
                self._log(f"回执失败: {resp.text}")
        except Exception as e:
            self._log(f"回执异常: {e}")

    def _get_message_password(self):
        pwd = simpledialog.askstring("本次消息密码", "请输入本次消息加密密码(>=8位):", show="*")
        if not pwd or len(pwd) < 8:
            messagebox.showerror("错误", "消息密码至少8位")
            return None
        return pwd

    def send_text(self):
        if not self.token:
            messagebox.showwarning("提示", "请先登录")
            return
        recipient = self.recipient_var.get().strip()
        if not recipient:
            messagebox.showwarning("提示", "请填写收件人")
            return

        text = self.message_input.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请输入消息")
            return

        pwd = self._get_message_password()
        if not pwd:
            return

        ciphertext, nonce, salt = encrypt_data(text.encode("utf-8"), pwd)
        payload = {
            "recipient": recipient,
            "msg_type": "text",
            "filename": None,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "salt": salt,
        }
        self._send_payload(payload)

    def send_file(self):
        if not self.token:
            messagebox.showwarning("提示", "请先登录")
            return

        recipient = self.recipient_var.get().strip()
        if not recipient:
            messagebox.showwarning("提示", "请填写收件人")
            return

        path = filedialog.askopenfilename(title="选择文件")
        if not path:
            return

        pwd = self._get_message_password()
        if not pwd:
            return

        raw = Path(path).read_bytes()
        file_blob = base64.b64encode(raw)
        ciphertext, nonce, salt = encrypt_data(file_blob, pwd)
        payload = {
            "recipient": recipient,
            "msg_type": "file",
            "filename": Path(path).name,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "salt": salt,
        }
        self._send_payload(payload)

    def _send_payload(self, payload):
        try:
            resp = self._request("POST", "/api/messages/send", json=payload)
            if resp.ok:
                self._log("发送成功")
            else:
                self._log(f"发送失败: {resp.text}")
        except Exception as e:
            self._log(f"发送异常: {e}")

    def open_selected_message(self, _evt):
        index = self.received_list.curselection()
        if not index:
            return
        i = index[0]
        if i + 1 >= self.received_list.size():
            return
        raw = self.received_list.get(i + 1)
        try:
            msg = json.loads(raw)
        except Exception:
            return

        pwd = simpledialog.askstring("解密消息", "请输入该条消息密码:", show="*")
        if not pwd:
            return

        try:
            plain = decrypt_data(msg["ciphertext"], msg["nonce"], msg["salt"], pwd)
            if msg["msg_type"] == "text":
                messagebox.showinfo("消息内容", plain.decode("utf-8", errors="replace"))
            else:
                save_path = filedialog.asksaveasfilename(initialfile=msg.get("filename") or "received.bin")
                if save_path:
                    Path(save_path).write_bytes(base64.b64decode(plain))
                    messagebox.showinfo("成功", f"文件已保存到: {save_path}")
        except Exception as e:
            messagebox.showerror("解密失败", str(e))


def main():
    if os.environ.get("CHAT_CLIENT_ALLOW_INSECURE_TLS") == "1":
        requests.packages.urllib3.disable_warnings()  # noqa
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, "running", False), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
