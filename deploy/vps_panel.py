from __future__ import annotations

import os
import subprocess
from pathlib import Path

from flask import Flask, render_template_string, request

APP_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = APP_DIR / ".venv"
SERVICE_NAME = "chat-server"
NGINX_SITE = Path("/etc/nginx/sites-available/chat-server")

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Chat 部署面板</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 960px; margin: 20px auto; }
    fieldset { margin: 12px 0; }
    input { width: 320px; }
    pre { background:#111; color:#eee; padding:12px; white-space:pre-wrap; }
    button { margin-right: 6px; }
  </style>
</head>
<body>
  <h2>VPS 一键部署面板</h2>
  <p>状态：<b>{{ status }}</b></p>

  <form method="post" action="/install">
    <fieldset>
      <legend>安装参数</legend>
      <div>域名（已解析到本机）: <input name="domain" placeholder="chat.example.com" required /></div>
      <div>邮箱（用于证书）: <input name="email" placeholder="ops@example.com" required /></div>
      <div>API Key: <input name="api_key" placeholder="请填写强随机密钥" required /></div>
    </fieldset>
    <button type="submit">安装并配置 HTTPS</button>
  </form>

  <form method="post" action="/restart"><button type="submit">重启服务</button></form>
  <form method="post" action="/uninstall"><button type="submit">卸载</button></form>

  <h3>日志</h3>
  <pre>{{ output }}</pre>
</body>
</html>
"""


def run(cmd: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return proc.returncode, (proc.stdout + "\n" + proc.stderr).strip()


def status() -> str:
    code, _ = run(f"systemctl is-active {SERVICE_NAME}")
    return "运行中" if code == 0 else "未运行"


def render(output: str = ""):
    return render_template_string(HTML, status=status(), output=output)


def install_service(domain: str, email: str, api_key: str) -> str:
    logs: list[str] = []

    setup_cmds = [
        "apt-get update",
        "apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx",
        f"python3 -m venv {VENV_DIR}",
        f"{VENV_DIR}/bin/pip install --upgrade pip",
        f"{VENV_DIR}/bin/pip install -r {APP_DIR / 'requirements.txt'}",
        f"mkdir -p {APP_DIR / 'server' / 'data' / 'uploads'}",
    ]
    for cmd in setup_cmds:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}\n")
        if code != 0:
            logs.append("安装中断，请检查报错。")
            return "\n".join(logs)

    service_text = f"""[Unit]
Description=Chat HTTPS Server
After=network.target

[Service]
Type=simple
WorkingDirectory={APP_DIR}
Environment=CHAT_API_KEY={api_key}
ExecStart={VENV_DIR}/bin/gunicorn -w 2 -b 127.0.0.1:5000 server.app:app
Restart=always
User=root

[Install]
WantedBy=multi-user.target
"""
    Path(f"/etc/systemd/system/{SERVICE_NAME}.service").write_text(service_text, encoding="utf-8")

    nginx_text = f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    NGINX_SITE.write_text(nginx_text, encoding="utf-8")

    enable_cmds = [
        f"ln -sf {NGINX_SITE} /etc/nginx/sites-enabled/chat-server",
        "nginx -t",
        "systemctl reload nginx",
        "systemctl daemon-reload",
        f"systemctl enable {SERVICE_NAME}",
        f"systemctl restart {SERVICE_NAME}",
        f"certbot --nginx -d {domain} --non-interactive --agree-tos -m {email} --redirect",
        "systemctl reload nginx",
    ]
    for cmd in enable_cmds:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}\n")
        if code != 0:
            logs.append("部分步骤失败，请根据日志手动修复。")
            break

    logs.append(f"安装流程结束。客户端请填写：https://{domain}")
    return "\n".join(logs)


def uninstall_service() -> str:
    logs: list[str] = []
    cmds = [
        f"systemctl stop {SERVICE_NAME}",
        f"systemctl disable {SERVICE_NAME}",
        f"rm -f /etc/systemd/system/{SERVICE_NAME}.service",
        f"rm -f {NGINX_SITE}",
        "rm -f /etc/nginx/sites-enabled/chat-server",
        "systemctl daemon-reload",
        "nginx -t",
        "systemctl reload nginx",
    ]
    for cmd in cmds:
        code, out = run(cmd)
        logs.append(f"$ {cmd}\n{out}\n")
    logs.append("卸载完成（证书和数据库文件未删除）。")
    return "\n".join(logs)


@app.get("/")
def index():
    return render()


@app.post("/install")
def install():
    domain = request.form.get("domain", "").strip()
    email = request.form.get("email", "").strip()
    api_key = request.form.get("api_key", "").strip()
    if not domain or not email or not api_key:
        return render("参数不完整")
    return render(install_service(domain, email, api_key))


@app.post("/restart")
def restart():
    code, out = run(f"systemctl restart {SERVICE_NAME}")
    return render(f"$ systemctl restart {SERVICE_NAME}\n{out}\n返回码: {code}")


@app.post("/uninstall")
def uninstall():
    return render(uninstall_service())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088)
