#!/usr/bin/env python3
"""
VPS 部署面板（交互式）。
提供：安装、卸载、启动、停止、状态。
安装来源：从 GitHub 仓库拉取代码，而不是使用面板所在目录的本地代码。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PANEL_DIR / ".panel_config.json"
SERVICE_NAME = "secure-msg-server"
SERVICE_FILE = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
DEPLOY_ROOT = Path("/opt/secure-msg-server")
APP_DIR = DEPLOY_ROOT / "server"
VENV_DIR = DEPLOY_ROOT / ".venv"
CERT_DIR = DEPLOY_ROOT / "certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"
DEFAULT_REPO_URL = "https://github.com/your-org/your-repo.git"
DEFAULT_BRANCH = "main"


def run(cmd: list[str], check: bool = True, cwd: Path | None = None):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check, cwd=str(cwd) if cwd else None)


def ensure_root():
    if os.geteuid() != 0:
        print("请使用 root 运行，例如: sudo python3 deploy_panel.py")
        sys.exit(1)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"repo_url": DEFAULT_REPO_URL, "branch": DEFAULT_BRANCH}


def save_config(repo_url: str, branch: str):
    payload = {"repo_url": repo_url, "branch": branch}
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ask_repo_config() -> tuple[str, str]:
    cfg = load_config()
    current_url = cfg.get("repo_url", DEFAULT_REPO_URL)
    current_branch = cfg.get("branch", DEFAULT_BRANCH)

    print("\n--- GitHub 部署配置 ---")
    repo_url = input(f"GitHub 仓库地址 [{current_url}]: ").strip() or current_url
    branch = input(f"分支 [{current_branch}]: ").strip() or current_branch
    save_config(repo_url, branch)
    return repo_url, branch


def sync_repo_from_github(repo_url: str, branch: str):
    DEPLOY_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if not (DEPLOY_ROOT / ".git").exists():
        if DEPLOY_ROOT.exists():
            shutil.rmtree(DEPLOY_ROOT)
        run(["git", "clone", "-b", branch, repo_url, str(DEPLOY_ROOT)])
    else:
        run(["git", "fetch", "origin"], cwd=DEPLOY_ROOT)
        run(["git", "checkout", branch], cwd=DEPLOY_ROOT)
        run(["git", "pull", "origin", branch], cwd=DEPLOY_ROOT)


def ensure_service_file():
    python_bin = str(VENV_DIR / "bin" / "python")
    app_path = APP_DIR / "app.py"
    content = f"""[Unit]
Description=Secure HTTPS Messenger Server
After=network.target

[Service]
Type=simple
WorkingDirectory={APP_DIR}
ExecStart={python_bin} {app_path} --host 0.0.0.0 --port 8443 --cert {CERT_FILE} --key {KEY_FILE}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
    SERVICE_FILE.write_text(content, encoding="utf-8")


def install():
    ensure_root()
    print("\n===> 安装服务中（从 GitHub 拉取）...")

    repo_url, branch = ask_repo_config()
    if "github.com" not in repo_url:
        print("⚠️ 你输入的地址看起来不是 GitHub，仍会继续尝试。")

    sync_repo_from_github(repo_url, branch)

    if not (APP_DIR / "requirements.txt").exists() or not (APP_DIR / "app.py").exists():
        raise SystemExit("仓库结构不正确：需要包含 server/app.py 和 server/requirements.txt")

    run(["python3", "-m", "venv", str(VENV_DIR)])
    pip = str(VENV_DIR / "bin" / "pip")
    run([pip, "install", "--upgrade", "pip"])
    run([pip, "install", "-r", str(APP_DIR / "requirements.txt")])

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

    ensure_service_file()
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", SERVICE_NAME])
    run(["systemctl", "restart", SERVICE_NAME])

    print("\n✅ 安装完成")
    print(f"部署目录: {DEPLOY_ROOT}")
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
    print("✅ 卸载完成（仓库代码、证书和数据默认保留）")


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
1) 安装 / 更新（GitHub 拉取）
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
