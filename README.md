# 更便捷版：Windows 客户端 + VPS 一键部署面板（HTTPS）

这版重点做了“便捷性”重构：
- 客户端支持**保存配置**、**测试连接**、**表格化收件箱**、**一键下载附件**。
- 部署端支持在一个面板里输入 **域名/邮箱/API Key**，直接完成**安装后端 + Nginx + SSL 证书**。

## 目录结构

- `client/windows_client.py`：Windows GUI 客户端。
- `server/app.py`：Flask API 服务端。
- `deploy/vps_panel.py`：VPS 部署面板（安装/卸载/重启）。

## 客户端特性（Windows）

1. 强制仅允许 `https://` 服务器地址。
2. 发送文本消息与文件给指定用户。
3. 收件箱以表格显示，支持下载选中的附件。
4. 自动保存最近一次配置（`client/client_config.json`）。

运行：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python client\windows_client.py
```

## VPS 面板（更便捷）

面板运行后打开 `http://<VPS_IP>:8088`，填写：
- 域名（已解析到 VPS）
- 邮箱（申请证书）
- API Key（客户端与服务端鉴权）

点击“安装并配置 HTTPS”会尝试自动执行：
1. 安装依赖（`nginx`, `certbot`, `python3-venv` 等）
2. 创建 Python 虚拟环境并安装依赖
3. 写入并启动 `chat-server` systemd 服务
4. 写入 Nginx 反向代理配置
5. 申请并启用 HTTPS 证书（Let's Encrypt）

运行面板：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python deploy/vps_panel.py
```

## 服务端 API

- `POST /api/send`：发送消息/文件。
- `GET /api/inbox/<username>?limit=200`：拉取收件箱。
- `GET /api/messages/<message_id>/download`：下载附件。
- `GET /health`：健康检查。

鉴权方式：请求头 `X-API-Key`。

## 注意事项

- 请确保域名 DNS 已正确指向 VPS。
- 面板脚本需 root 权限（systemd/nginx/certbot）。
- 卸载默认不删除数据库与证书文件，避免误删数据。
