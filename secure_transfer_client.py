import base64
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import requests


class SecureClientUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Secure HTTPS Messenger")
        self.root.geometry("760x560")

        self.server_var = tk.StringVar(value="https://127.0.0.1:8443")
        self.user_var = tk.StringVar(value="alice")
        self.target_var = tk.StringVar(value="bob")
        self.verify_tls_var = tk.BooleanVar(value=False)

        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self.root, padx=12, pady=10)
        top.pack(fill="x")

        tk.Label(top, text="服务器地址(HTTPS):").grid(row=0, column=0, sticky="w")
        tk.Entry(top, textvariable=self.server_var, width=45).grid(row=0, column=1, sticky="we", padx=6)

        tk.Checkbutton(top, text="校验证书", variable=self.verify_tls_var).grid(row=0, column=2, sticky="w")

        tk.Label(top, text="我的用户名:").grid(row=1, column=0, sticky="w", pady=5)
        tk.Entry(top, textvariable=self.user_var, width=20).grid(row=1, column=1, sticky="w", padx=6)

        tk.Button(top, text="注册/登录", command=self.register_user).grid(row=1, column=2, sticky="w")

        tk.Label(top, text="目标用户:").grid(row=2, column=0, sticky="w", pady=5)
        tk.Entry(top, textvariable=self.target_var, width=20).grid(row=2, column=1, sticky="w", padx=6)

        tk.Label(top, text="文本消息:").grid(row=3, column=0, sticky="nw", pady=5)
        self.message_text = tk.Text(top, height=4, width=55)
        self.message_text.grid(row=3, column=1, columnspan=2, sticky="we", padx=6)

        action = tk.Frame(self.root, padx=12)
        action.pack(fill="x")

        tk.Button(action, text="发送消息", command=self.send_message).pack(side="left", padx=3)
        tk.Button(action, text="发送文件", command=self.send_file).pack(side="left", padx=3)
        tk.Button(action, text="拉取收件箱", command=self.fetch_inbox_async).pack(side="left", padx=3)

        self.log_area = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word")
        self.log_area.pack(fill="both", expand=True, padx=12, pady=10)

        self._log("客户端就绪。请输入 HTTPS 服务器地址并注册用户名。")

    def _headers(self):
        return {"X-Username": self.user_var.get().strip()}

    def _base(self):
        base = self.server_var.get().strip()
        if not base.startswith("https://"):
            raise ValueError("服务器地址必须以 https:// 开头")
        return base.rstrip("/")

    def _verify(self):
        return self.verify_tls_var.get()

    def _log(self, msg: str):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"{msg}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def _request(self, method: str, path: str, json=None):
        url = f"{self._base()}{path}"
        return requests.request(
            method,
            url,
            json=json,
            headers=self._headers(),
            timeout=20,
            verify=self._verify(),
        )

    def register_user(self):
        username = self.user_var.get().strip()
        if not username:
            messagebox.showwarning("提示", "请输入用户名")
            return
        try:
            resp = self._request("POST", "/api/register", json={"username": username})
            resp.raise_for_status()
            self._log(f"✅ 注册成功: {username}")
        except Exception as exc:
            self._log(f"❌ 注册失败: {exc}")

    def send_message(self):
        target = self.target_var.get().strip()
        content = self.message_text.get("1.0", "end").strip()
        if not target or not content:
            messagebox.showwarning("提示", "目标用户和消息内容都不能为空")
            return
        try:
            resp = self._request("POST", "/api/send_message", json={"to": target, "message": content})
            resp.raise_for_status()
            self._log(f"✅ 消息已发送给 {target}")
            self.message_text.delete("1.0", "end")
        except Exception as exc:
            self._log(f"❌ 发送失败: {exc}")

    def send_file(self):
        target = self.target_var.get().strip()
        if not target:
            messagebox.showwarning("提示", "请输入目标用户")
            return

        file_path = filedialog.askopenfilename(title="选择要发送的文件")
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "to": target,
                "filename": os.path.basename(file_path),
                "content_b64": data,
            }
            resp = self._request("POST", "/api/send_file", json=payload)
            resp.raise_for_status()
            self._log(f"✅ 文件已发送给 {target}: {os.path.basename(file_path)}")
        except Exception as exc:
            self._log(f"❌ 文件发送失败: {exc}")

    def fetch_inbox_async(self):
        threading.Thread(target=self.fetch_inbox, daemon=True).start()

    def fetch_inbox(self):
        try:
            resp = self._request("GET", "/api/inbox")
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                self._log("📭 暂无新消息")
                return
            self._log(f"📥 收到 {len(items)} 条新内容")
            download_dir = os.path.join(os.path.expanduser("~"), "Downloads", "secure_inbox")
            os.makedirs(download_dir, exist_ok=True)
            for item in items:
                if item.get("type") == "message":
                    self._log(f"💬 {item['from']} -> {self.user_var.get().strip()}: {item['message']}")
                elif item.get("type") == "file":
                    name = item.get("filename", "unknown.bin")
                    output = os.path.join(download_dir, name)
                    with open(output, "wb") as f:
                        f.write(base64.b64decode(item["content_b64"]))
                    self._log(f"📎 收到文件 {name}，已保存到: {output}")
        except Exception as exc:
            self._log(f"❌ 拉取收件箱失败: {exc}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SecureClientUI(root)
    root.mainloop()
