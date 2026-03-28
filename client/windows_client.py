from __future__ import annotations

import base64
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests


class ChatClientUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HTTPS 文件/消息客户端")
        self.root.geometry("720x520")

        self.server_var = tk.StringVar(value="https://your-server-domain")
        self.api_key_var = tk.StringVar(value="change-me")
        self.sender_var = tk.StringVar(value="alice")
        self.recipient_var = tk.StringVar(value="bob")
        self.file_var = tk.StringVar()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        row = 0
        for label, var in [
            ("服务器地址 (HTTPS)", self.server_var),
            ("API Key", self.api_key_var),
            ("发送人", self.sender_var),
            ("接收人", self.recipient_var),
        ]:
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frm, textvariable=var, width=60).grid(row=row, column=1, sticky="ew", pady=4)
            row += 1

        ttk.Label(frm, text="消息内容").grid(row=row, column=0, sticky="nw", pady=4)
        self.message_text = tk.Text(frm, height=8)
        self.message_text.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(frm, text="文件").grid(row=row, column=0, sticky="w", pady=4)
        file_entry = ttk.Entry(frm, textvariable=self.file_var, width=48)
        file_entry.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Button(frm, text="选择文件", command=self.pick_file).grid(row=row, column=1, sticky="e")
        row += 1

        buttons = ttk.Frame(frm)
        buttons.grid(row=row, column=1, sticky="ew", pady=8)
        ttk.Button(buttons, text="发送消息/文件", command=self.send).pack(side=tk.LEFT)
        ttk.Button(buttons, text="刷新收件箱", command=self.load_inbox).pack(side=tk.LEFT, padx=8)
        row += 1

        ttk.Label(frm, text="收件箱").grid(row=row, column=0, sticky="nw", pady=4)
        self.inbox = tk.Text(frm, height=14)
        self.inbox.grid(row=row, column=1, sticky="nsew")

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(row, weight=1)

    def pick_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.file_var.set(path)

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key_var.get().strip()}

    def send(self):
        server = self.server_var.get().strip().rstrip("/")
        if not server.startswith("https://"):
            messagebox.showerror("错误", "服务器地址必须以 https:// 开头")
            return

        payload = {
            "sender": self.sender_var.get().strip(),
            "recipient": self.recipient_var.get().strip(),
            "message": self.message_text.get("1.0", tk.END).strip(),
        }

        file_path = self.file_var.get().strip()
        if file_path:
            p = Path(file_path)
            if not p.exists():
                messagebox.showerror("错误", "文件不存在")
                return
            payload["file_name"] = p.name
            payload["file_content_b64"] = base64.b64encode(p.read_bytes()).decode("ascii")

        try:
            resp = requests.post(
                f"{server}/api/send",
                json=payload,
                headers=self._headers(),
                timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            messagebox.showerror("发送失败", str(exc))
            return

        messagebox.showinfo("成功", f"发送完成: {resp.json()}")

    def load_inbox(self):
        server = self.server_var.get().strip().rstrip("/")
        if not server.startswith("https://"):
            messagebox.showerror("错误", "服务器地址必须以 https:// 开头")
            return

        username = self.sender_var.get().strip()
        try:
            resp = requests.get(
                f"{server}/api/inbox/{username}",
                headers=self._headers(),
                timeout=20,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except requests.RequestException as exc:
            messagebox.showerror("拉取失败", str(exc))
            return

        self.inbox.delete("1.0", tk.END)
        if not items:
            self.inbox.insert(tk.END, "暂无消息\n")
            return

        for item in items:
            self.inbox.insert(
                tk.END,
                (
                    f"[{item['created_at']}] {item['sender']} -> {item['recipient']}\n"
                    f"消息: {item.get('message') or ''}\n"
                    f"文件: {item.get('file_name') or '无'}\n"
                    f"下载: {server}{item.get('download_url') or ''}\n"
                    "-" * 60
                    + "\n"
                ),
            )


if __name__ == "__main__":
    root = tk.Tk()
    ChatClientUI(root)
    root.mainloop()
