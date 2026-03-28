from __future__ import annotations

import base64
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests

CONFIG_PATH = Path(__file__).with_name("client_config.json")


class ChatClientUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HTTPS 消息/文件客户端")
        self.root.geometry("900x620")

        cfg = self._load_config()
        self.server_var = tk.StringVar(value=cfg.get("server", "https://your-domain.com"))
        self.api_key_var = tk.StringVar(value=cfg.get("api_key", "change-me"))
        self.sender_var = tk.StringVar(value=cfg.get("sender", "alice"))
        self.recipient_var = tk.StringVar(value=cfg.get("recipient", "bob"))
        self.file_var = tk.StringVar()

        self._build_ui()

    def _load_config(self) -> dict:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_config(self) -> None:
        data = {
            "server": self.server_var.get().strip(),
            "api_key": self.api_key_var.get().strip(),
            "sender": self.sender_var.get().strip(),
            "recipient": self.recipient_var.get().strip(),
        }
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(frame, text="连接配置", padding=10)
        form.pack(fill=tk.X)

        labels = [
            ("服务器(HTTPS)", self.server_var),
            ("API Key", self.api_key_var),
            ("我的用户名", self.sender_var),
            ("目标用户名", self.recipient_var),
        ]
        for i, (label, var) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(form, textvariable=var, width=70).grid(row=i, column=1, sticky="ew", pady=4)

        btn_bar = ttk.Frame(form)
        btn_bar.grid(row=0, column=2, rowspan=4, padx=(10, 0))
        ttk.Button(btn_bar, text="保存配置", command=self._save_config).pack(fill=tk.X)
        ttk.Button(btn_bar, text="测试连接", command=self.test_connection).pack(fill=tk.X, pady=(6, 0))

        form.columnconfigure(1, weight=1)

        send_box = ttk.LabelFrame(frame, text="发送", padding=10)
        send_box.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(send_box, text="消息").grid(row=0, column=0, sticky="nw")
        self.message_text = tk.Text(send_box, height=5)
        self.message_text.grid(row=0, column=1, sticky="ew")
        ttk.Label(send_box, text="文件").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(send_box, textvariable=self.file_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(send_box, text="选择", command=self.pick_file).grid(row=1, column=2, padx=(8, 0))
        ttk.Button(send_box, text="发送消息/文件", command=self.send).grid(row=2, column=1, sticky="e")
        send_box.columnconfigure(1, weight=1)

        inbox_box = ttk.LabelFrame(frame, text="收件箱", padding=10)
        inbox_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        top = ttk.Frame(inbox_box)
        top.pack(fill=tk.X)
        ttk.Button(top, text="刷新", command=self.load_inbox).pack(side=tk.LEFT)
        ttk.Button(top, text="下载选中文件", command=self.download_selected).pack(side=tk.LEFT, padx=8)

        cols = ("time", "from", "to", "message", "file", "id")
        self.tree = ttk.Treeview(inbox_box, columns=cols, show="headings", height=14)
        for col, title, width in [
            ("time", "时间", 170),
            ("from", "发送人", 90),
            ("to", "接收人", 90),
            ("message", "消息", 280),
            ("file", "文件", 160),
            ("id", "ID", 0),
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        self.tree.column("id", width=0, stretch=False)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.status_var).pack(fill=tk.X, pady=(8, 0))

    def _server(self) -> str:
        server = self.server_var.get().strip().rstrip("/")
        if not server.startswith("https://"):
            raise ValueError("服务器地址必须是 https:// 开头")
        return server

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key_var.get().strip()}

    def _request(self, method: str, path: str, **kwargs):
        server = self._server()
        resp = requests.request(method, f"{server}{path}", headers=self._headers(), timeout=20, **kwargs)
        resp.raise_for_status()
        return resp

    def set_status(self, text: str):
        self.status_var.set(text)

    def test_connection(self):
        try:
            resp = self._request("GET", "/health")
            self.set_status(f"连接成功: {resp.json().get('time')}")
        except Exception as exc:
            messagebox.showerror("连接失败", str(exc))
            self.set_status("连接失败")

    def pick_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.file_var.set(path)

    def send(self):
        try:
            payload = {
                "sender": self.sender_var.get().strip(),
                "recipient": self.recipient_var.get().strip(),
                "message": self.message_text.get("1.0", tk.END).strip(),
            }
            file_path = self.file_var.get().strip()
            if file_path:
                p = Path(file_path)
                if not p.exists():
                    raise ValueError("文件不存在")
                payload["file_name"] = p.name
                payload["file_content_b64"] = base64.b64encode(p.read_bytes()).decode("ascii")

            resp = self._request("POST", "/api/send", json=payload)
            msg_id = resp.json().get("id")
            self.set_status(f"发送成功，ID: {msg_id}")
            self.message_text.delete("1.0", tk.END)
            self.file_var.set("")
            self._save_config()
        except Exception as exc:
            messagebox.showerror("发送失败", str(exc))
            self.set_status("发送失败")

    def load_inbox(self):
        try:
            username = self.sender_var.get().strip()
            resp = self._request("GET", f"/api/inbox/{username}", params={"limit": 200})
            items = resp.json().get("items", [])

            for row in self.tree.get_children():
                self.tree.delete(row)

            for item in items:
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        item.get("created_at", ""),
                        item.get("sender", ""),
                        item.get("recipient", ""),
                        item.get("message", ""),
                        item.get("file_name") or "",
                        item.get("id"),
                    ),
                )
            self.set_status(f"已加载 {len(items)} 条消息")
            self._save_config()
        except Exception as exc:
            messagebox.showerror("拉取失败", str(exc))
            self.set_status("拉取失败")

    def download_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一条消息")
            return
        values = self.tree.item(selected[0], "values")
        file_name = values[4]
        message_id = values[5]
        if not file_name:
            messagebox.showwarning("提示", "该消息没有附件")
            return
        target = filedialog.asksaveasfilename(initialfile=file_name)
        if not target:
            return

        try:
            resp = self._request("GET", f"/api/messages/{message_id}/download")
            Path(target).write_bytes(resp.content)
            self.set_status(f"文件已保存: {target}")
        except Exception as exc:
            messagebox.showerror("下载失败", str(exc))
            self.set_status("下载失败")


if __name__ == "__main__":
    root = tk.Tk()
    ChatClientUI(root)
    root.mainloop()
