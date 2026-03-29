# Windows 客户端 + VPS 一键脚本部署（HTTPS）

你要求的是 **VPS 端像一键脚本那样快捷部署**，本版本已提供：

- `deploy/quick_deploy.sh`：支持交互菜单和命令行一键安装/卸载/重启/状态查看。
- `client/windows_client.py`：Windows 图形客户端（HTTPS、收件箱表格、附件下载）。
- `server/app.py`：Flask 消息服务端。

## 1) VPS 一键部署（推荐）

进入项目目录后执行：

```bash
sudo bash deploy/quick_deploy.sh
```

会出现菜单：

- 安装并配置 HTTPS
- 卸载
- 重启服务
- 查看状态

### 非交互一键安装

```bash
sudo bash deploy/quick_deploy.sh install -d chat.example.com -e ops@example.com -k 'your-strong-api-key'
```

该命令会自动完成：
1. 安装依赖（`python3-venv`, `nginx`, `certbot` 等）
2. 创建 `.venv` 并安装 Python 依赖
3. 写入并启动 `chat-server` systemd 服务
4. 写入 Nginx 反向代理
5. 自动申请并启用 HTTPS 证书（Let's Encrypt）

### 卸载

```bash
sudo bash deploy/quick_deploy.sh uninstall
```

> 卸载默认不会删除消息数据库和上传文件。

## 2) Windows 客户端

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python client\windows_client.py
```

客户端功能：
- 强制服务器地址为 `https://`
- 发送文本和文件
- 测试连接
- 收件箱表格展示
- 选中消息下载附件
- 自动保存最近配置（`client/client_config.json`）

## 3) 服务端 API

- `POST /api/send`：发送消息/文件
- `GET /api/inbox/<username>?limit=200`：拉取收件箱
- `GET /api/messages/<message_id>/download`：下载附件
- `GET /health`：健康检查

请求头鉴权：`X-API-Key`

## 4) 注意事项

- 运行一键脚本需 root 权限。
- 域名需提前解析到 VPS，且 80/443 端口可访问。
- 生产环境请使用高强度 API Key。
