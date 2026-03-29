#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$APP_DIR/.venv"
PANEL_SERVICE="chat-deploy-panel"
PANEL_PORT="8088"

log() { echo -e "[+] $*"; }
warn() { echo -e "[!] $*"; }
err() { echo -e "[x] $*" >&2; }

need_root() {
  if [[ ${EUID} -ne 0 ]]; then
    err "请用 root 运行，例如: sudo bash deploy/quick_deploy.sh"
    exit 1
  fi
}

write_panel_service() {
  cat > "/etc/systemd/system/${PANEL_SERVICE}.service" <<EOF
[Unit]
Description=Chat Deploy Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/deploy/vps_panel.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
}

setup_panel() {
  need_root
  log "安装启动面板所需依赖"
  apt-get update
  apt-get install -y python3-venv python3-pip

  log "创建虚拟环境并安装 requirements"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

  write_panel_service
  systemctl daemon-reload
  systemctl enable "$PANEL_SERVICE"
  systemctl restart "$PANEL_SERVICE"

  log "部署面板已启动"
  log "访问地址: http://<VPS_IP>:${PANEL_PORT}"
  log "后续的程序部署/卸载请在面板中操作"
}

start_panel() {
  need_root
  systemctl start "$PANEL_SERVICE"
  systemctl status "$PANEL_SERVICE" --no-pager -l || true
}

stop_panel() {
  need_root
  systemctl stop "$PANEL_SERVICE"
  systemctl status "$PANEL_SERVICE" --no-pager -l || true
}

status_panel() {
  systemctl status "$PANEL_SERVICE" --no-pager -l || true
}

uninstall_panel() {
  need_root
  warn "卸载面板服务（不会卸载已通过面板部署的 chat-server）"
  systemctl stop "$PANEL_SERVICE" || true
  systemctl disable "$PANEL_SERVICE" || true
  rm -f "/etc/systemd/system/${PANEL_SERVICE}.service"
  systemctl daemon-reload
  log "面板服务已卸载"
}

menu() {
  while true; do
    cat <<'EOF'
==============================
 Chat 一键脚本（仅启动面板）
==============================
1) 一键安装并启动部署面板
2) 启动面板
3) 停止面板
4) 查看面板状态
5) 卸载面板
0) 退出
EOF
    read -r -p "请选择 [0-5]: " ch
    case "$ch" in
      1) setup_panel ;;
      2) start_panel ;;
      3) stop_panel ;;
      4) status_panel ;;
      5) uninstall_panel ;;
      0) exit 0 ;;
      *) warn "无效选项" ;;
    esac
  done
}

cmd="${1:-menu}"
case "$cmd" in
  setup) setup_panel ;;
  start) start_panel ;;
  stop) stop_panel ;;
  status) status_panel ;;
  uninstall-panel) uninstall_panel ;;
  menu) menu ;;
  *)
    cat <<EOF
用法:
  bash deploy/quick_deploy.sh menu
  bash deploy/quick_deploy.sh setup
  bash deploy/quick_deploy.sh start
  bash deploy/quick_deploy.sh stop
  bash deploy/quick_deploy.sh status
  bash deploy/quick_deploy.sh uninstall-panel
EOF
    exit 1
    ;;
esac
