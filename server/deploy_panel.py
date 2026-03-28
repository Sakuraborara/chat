#!/usr/bin/env python3
"""
VPS 部署面板（交互式）。
提供：安装、卸载、启动、停止、状态。
安装来源：可直接输入 deploy_panel.py 的 GitHub 地址，面板会自动解析仓库并拉取部署。
"""

from __future__ import annotations

import json
import os
import re
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
DEFAULT_BLOB_URL = (
    "https://github.com/Sakuraborara/chat/blob/"
    "codex/create-python-windows-local-client-server-app/server/deploy_panel.py"
)
DEFAULT_SCRIPT_PATH = "server/deploy_panel.py"
DEFAULT_BRANCH = "main"


def run(cmd: list[str], check: bool = True, cwd: Path | None = None):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check, cwd=str(cwd) if cwd else None)


def ensure_root():
    if os.geteuid() != 0:
        print("请使用 root 运行，例如: sudo python3 deploy_panel.py")
        sys.exit(1)


def parse_blob_url(blob_url: str, script_path: str) -> tuple[str, str] | None:
    """
    从 GitHub blob 地址解析出 repo_url 与 branch。
    支持 branch 名字包含斜杠（例如 codex/create-xxx）。
    """
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+)/blob/(.+)$", blob_url.strip())
    if not m:
        return None

    owner, repo, rest = m.group(1), m.group(2), m.group(3)
    suffix = f"/{script_path}"
    if not rest.endswith(suffix):
        return None

    branch = rest[: -len(suffix)].strip("/")
    if not branch:
        return None

    repo_url = f"https://github.com/{owner}/{repo}.git"
    return repo_url, branch


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "blob_url": DEFAULT_BLOB_URL,
        "script_path": DEFAULT_SCRIPT_PATH,
        "repo_url": "",
        "branch": DEFAULT_BRANCH,
    }


def save_config(payload: dict):
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ask_source_config() -> tuple[str, str]:
    cfg = load_config()
    blob_url = input(f"deploy_panel.py GitHub 地址 [{cfg.get('blob_url', DEFAULT_BLOB_URL)}]: ").strip()
    blob_url = blob_url or cfg.get("blob_url", DEFAULT_BLOB_URL)

    script_path = input(f"该脚本在仓库中的路径 [{cfg.get('script_path', DEFAULT_SCRIPT_PATH)}]: ").strip()
    script_path = script_path or cfg.get("script_path", DEFAULT_SCRIPT_PATH)

    parsed = parse_blob_url(blob_url, script_path)
    if parsed:
        repo_url, branch = parsed
        print(f"已自动解析仓库: {repo_url}")
        print(f"已自动解析分支: {branch}")
    else:
        print("⚠️ 无法从脚本地址自动解析，改为手动输入仓库和分支。")
        repo_default = cfg.get("repo_url") or "https://github.com/owner/repo.git"
        branch_default = cfg.get("branch", DEFAULT_BRANCH)
        repo_url = input(f"GitHub 仓库地址 [{repo_default}]: ").strip() or repo_default
        branch = input(f"分支 [{branch_default}]: ").strip() or branch_default

    save_config(
        {
            "blob_url": blob_url,
            "script_path": script_path,
            "repo_url": repo_url,
            "branch": branch,
        }
    )
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
    print("\n===> 安装服务中（根据 deploy_panel.py GitHub 地址自动拉取）...")

    repo_url, branch = ask_source_config()
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
1) 安装 / 更新（输入 deploy_panel.py GitHub 地址）
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
