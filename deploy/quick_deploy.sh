#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="chat-server"
VENV_DIR="$APP_DIR/.venv"
NGINX_SITE="/etc/nginx/sites-available/chat-server"

DOMAIN=""
EMAIL=""

log() { echo -e "[+] $*"; }
warn() { echo -e "[!] $*"; }
err() { echo -e "[x] $*" >&2; }

need_root() {
  if [[ ${EUID} -ne 0 ]]; then
    err "请用 root 运行，例如: sudo bash deploy/quick_deploy.sh"
    exit 1
  fi
}

prompt_missing() {
  [[ -n "$DOMAIN" ]] || read -r -p "请输入域名(已解析到VPS): " DOMAIN
  [[ -n "$EMAIL" ]] || read -r -p "请输入邮箱(用于证书): " EMAIL

  if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
    err "域名/邮箱都不能为空"
    exit 1
  fi
}

write_service() {
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Chat HTTPS Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/gunicorn -w 2 -b 127.0.0.1:5000 server.app:app
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
}

write_nginx() {
  cat > "$NGINX_SITE" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/chat-server
}

install_all() {
  need_root
  prompt_missing

  log "安装系统依赖"
  apt-get update
  apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx

  log "创建虚拟环境并安装依赖"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

  mkdir -p "$APP_DIR/server/data/uploads"
  write_service
  write_nginx

  log "重载并启动服务"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"

  log "检查 Nginx 配置"
  nginx -t
  systemctl reload nginx

  log "申请 HTTPS 证书"
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
  systemctl reload nginx

  log "部署完成。客户端服务器地址填写: https://${DOMAIN}"
}

uninstall_all() {
  need_root
  warn "开始卸载服务（不会删除数据库和上传文件）"
  systemctl stop "$SERVICE_NAME" || true
  systemctl disable "$SERVICE_NAME" || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"

  rm -f "$NGINX_SITE"
  rm -f /etc/nginx/sites-enabled/chat-server
  systemctl daemon-reload
  nginx -t || true
  systemctl reload nginx || true

  log "卸载完成"
}

restart_service() {
  need_root
  systemctl restart "$SERVICE_NAME"
  systemctl status "$SERVICE_NAME" --no-pager -l || true
}

show_status() {
  systemctl status "$SERVICE_NAME" --no-pager -l || true
  echo
  nginx -t || true
}

menu() {
  while true; do
    cat <<'EOF'
==============================
 Chat VPS 一键部署脚本
==============================
1) 安装并配置 HTTPS
2) 卸载
3) 重启服务
4) 查看状态
0) 退出
EOF
    read -r -p "请选择 [0-4]: " ch
    case "$ch" in
      1) DOMAIN=""; EMAIL=""; prompt_missing; install_all ;;
      2) uninstall_all ;;
      3) restart_service ;;
      4) show_status ;;
      0) exit 0 ;;
      *) warn "无效选项" ;;
    esac
  done
}

cmd="${1:-menu}"
if [[ "$cmd" == "install" ]]; then
  shift || true
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -d|--domain) DOMAIN="$2"; shift 2 ;;
      -e|--email) EMAIL="$2"; shift 2 ;;
      *) err "未知参数: $1"; exit 1 ;;
    esac
  done
  install_all
elif [[ "$cmd" == "uninstall" ]]; then
  uninstall_all
elif [[ "$cmd" == "restart" ]]; then
  restart_service
elif [[ "$cmd" == "status" ]]; then
  show_status
elif [[ "$cmd" == "menu" ]]; then
  menu
else
  cat <<EOF
用法:
  bash deploy/quick_deploy.sh menu
  bash deploy/quick_deploy.sh install -d 域名 -e 邮箱
  bash deploy/quick_deploy.sh uninstall
  bash deploy/quick_deploy.sh restart
  bash deploy/quick_deploy.sh status
EOF
  exit 1
fi
