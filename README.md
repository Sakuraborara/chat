# Python 本地通讯程序（Windows 客户端 + VPS 服务端）

本项目包含：

1. `client/windows_client.py`：Windows 本地 GUI 客户端（Tkinter）。
2. `server/app.py`：服务端 API（Flask），支持给指定用户发送消息/文件。
3. `deploy/vps_panel.py`：VPS 部署面板（Flask），提供**安装 / 卸载 / 重启**功能。

## 功能说明

- 通讯协议：客户端要求服务器地址必须是 `https://`。
- 发送：支持向指定用户发送文本消息和文件。
- 收件箱：客户端可拉取指定用户消息列表。
- 服务端部署：通过面板按钮执行安装和卸载，不是输入脚本链接直接部署。

## Windows 客户端运行

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python client\windows_client.py
```

## VPS 部署面板运行

> 需要 root 权限（用于写入 systemd 服务）。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python deploy/vps_panel.py
```

打开：`http://<VPS_IP>:8088`，点击“安装”后会创建并启动 `chat-server` systemd 服务。

## HTTPS 配置（必需）

面板只负责安装后端服务（监听 `127.0.0.1:5000`）。
你需要在 VPS 上配置 Nginx + SSL 证书（如 Let's Encrypt），并将域名反代到该端口。
客户端只能填写 `https://your-domain`。

## 安全提示

- 默认 `CHAT_API_KEY=change-me`，生产环境请务必改为强随机值。
- 推荐仅开放 443 端口，面板端口应加防火墙白名单或仅内网访问。
