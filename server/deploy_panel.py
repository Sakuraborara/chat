#!/usr/bin/env python3
"""
VPS 部署面板（交互式）。
提供：安装、卸载、启动、停止、状态。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVICE_NAME = "secure-msg-server"
SERVICE_FILE = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
VENV_DIR = BASE_DIR / ".venv"
CERT_DIR = BASE_DIR / "certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"


def run(cmd: list[str], check: bool = True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def ensure_root():
    if os.geteuid() != 0:
        print("请使用 root 运行，例如: sudo python3 deploy_panel.py")
        sys.exit(1)


def install():
    ensure_root()
    print("\n===> 安装服务中...")
    run(["python3", "-m", "venv", str(VENV_DIR)])
    pip = str(VENV_DIR / "bin" / "pip")
    run([pip, "install", "--upgrade", "pip"])
    run([pip, "install", "-r", str(BASE_DIR / "requirements.txt")])

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(KEY_FILE),
                "-out",
                str(CERT_FILE),
                "-days",
                "365",
                "-nodes",
                "-subj",
                "/CN=secure-msg-server",
            ]
        )

    python_bin = str(VENV_DIR / "bin" / "python")
    content = f"""[Unit]
Description=Secure HTTPS Messenger Server
After=network.target

[Service]
Type=simple
WorkingDirectory={BASE_DIR}
ExecStart={python_bin} {BASE_DIR / 'app.py'} --host 0.0.0.0 --port 8443
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
    SERVICE_FILE.write_text(content, encoding="utf-8")

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", SERVICE_NAME])
    run(["systemctl", "restart", SERVICE_NAME])

    print("\n✅ 安装完成")
    print(f"证书路径: {CERT_FILE}")
    print(f"服务名: {SERVICE_NAME}")


def uninstall():
    ensure_root()
    print("\n===> 卸载服务中...")
    run(["systemctl", "disable", "--now", SERVICE_NAME], check=False)
    if SERVICE_FILE.exists():
        SERVICE_FILE.unlink()
    run(["systemctl", "daemon-reload"])

    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    print("✅ 卸载完成（证书和数据默认保留）")


def status():
    ensure_root()
    run(["systemctl", "status", SERVICE_NAME], check=False)


def start():
    ensure_root()
    run(["systemctl", "start", SERVICE_NAME])


def stop():
    ensure_root()
    run(["systemctl", "stop", SERVICE_NAME])


def menu():
    print(
        """
==============================
Secure HTTPS Messenger 面板
==============================
1) 安装 / 更新
2) 卸载
3) 启动服务
4) 停止服务
5) 查看状态
0) 退出
"""
    )


def main():
    actions = {
        "1": install,
        "2": uninstall,
        "3": start,
        "4": stop,
        "5": status,
    }
    while True:
        menu()
        choice = input("请输入选项: ").strip()
        if choice == "0":
            print("已退出")
            return
        action = actions.get(choice)
        if not action:
            print("无效选项，请重试。")
            continue
        try:
            action()
        except subprocess.CalledProcessError as e:
            print(f"命令执行失败: {e}")


if __name__ == "__main__":
    main()
