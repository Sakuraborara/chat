from __future__ import annotations

import os
import subprocess
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

APP_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = APP_DIR / "server"
VENV_DIR = APP_DIR / ".venv"
SERVICE_NAME = "chat-server"

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"/><title>部署面板</title></head>
<body style="font-family: Arial; max-width: 880px; margin: 20px auto;">
  <h2>VPS 部署面板</h2>
  <p>用于安装/卸载 HTTPS 聊天服务（配合 Nginx + 证书）。</p>
  <p><b>状态：</b>{{ status }}</p>
  <form method="post" action="{{ url_for('install') }}"><button>安装</button></form>
  <form method="post" action="{{ url_for('uninstall') }}" style="margin-top:8px;"><button>卸载</button></form>
  <form method="post" action="{{ url_for('restart') }}" style="margin-top:8px;"><button>重启服务</button></form>
  <h3>输出</h3>
  <pre>{{ output }}</pre>
</body>
</html>
"""


def run(cmd: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return proc.returncode, proc.stdout + "\n" + proc.stderr


def service_status() -> str:
    code, _ = run(f"systemctl is-active {SERVICE_NAME}")
    return "运行中" if code == 0 else "未运行"


def install_service() -> str:
    logs = []
    cmds = [
        f"python3 -m venv {VENV_DIR}",
        f"{VENV_DIR}/bin/pip install --upgrade pip",
        f"{VENV_DIR}/bin/pip install -r {APP_DIR / 'requirements.txt'}",
        f"mkdir -p {SERVER_DIR / 'data' / 'uploads'}",
    ]

    service_file = f"""[Unit]
Description=Chat HTTPS Server
After=network.target

[Service]
Type=simple
WorkingDirectory={APP_DIR}
Environment=CHAT_API_KEY={os.getenv('CHAT_API_KEY', 'change-me')}
ExecStart={VENV_DIR}/bin/gunicorn -w 2 -b 127.0.0.1:5000 server.app:app
Restart=always
User=root

[Install]
WantedBy=multi-user.target
"""
    Path(f"/etc/systemd/system/{SERVICE_NAME}.service").write_text(service_file)

    for cmd in cmds:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}")
        if code != 0:
            logs.append("安装中断。")
            return "\n".join(logs)

    for cmd in ["systemctl daemon-reload", f"systemctl enable {SERVICE_NAME}", f"systemctl restart {SERVICE_NAME}"]:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}")

    logs.append(
        "\n安装完成。请使用 Nginx 反代 127.0.0.1:5000 并配置 SSL 证书（Let's Encrypt），客户端必须使用 https:// 地址。"
    )
    return "\n".join(logs)


def uninstall_service() -> str:
    logs = []
    cmds = [
        f"systemctl stop {SERVICE_NAME}",
        f"systemctl disable {SERVICE_NAME}",
        f"rm -f /etc/systemd/system/{SERVICE_NAME}.service",
        "systemctl daemon-reload",
    ]
    for cmd in cmds:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}")

    logs.append("已卸载服务（数据目录未删除）。")
    return "\n".join(logs)


@app.get("/")
def index():
    return render_template_string(HTML, status=service_status(), output="")


@app.post("/install")
def install():
    output = install_service()
    return render_template_string(HTML, status=service_status(), output=output)


@app.post("/uninstall")
def uninstall():
    output = uninstall_service()
    return render_template_string(HTML, status=service_status(), output=output)


@app.post("/restart")
def restart():
    code, out = run(f"systemctl restart {SERVICE_NAME}")
    output = f"$ systemctl restart {SERVICE_NAME}\n{out}\n返回码: {code}"
    return render_template_string(HTML, status=service_status(), output=output)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088)
