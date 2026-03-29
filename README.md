# Windows 客户端 + VPS 一键脚本部署（HTTPS）

按你的新要求，已改为：
- 增加 **注册 / 登录** 功能。
- 删除 API Key 机制，改用登录会话 Token。
- VPS 保留 **一键脚本 + 面板** 两种部署方式。

## 1) VPS 一键脚本（推荐）

```bash
sudo bash deploy/quick_deploy.sh
```

脚本菜单：
- 安装并配置 HTTPS
- 卸载
- 重启服务
- 查看状态

### 非交互一键安装

```bash
sudo bash deploy/quick_deploy.sh install -d chat.example.com -e ops@example.com
```

自动完成：依赖安装、venv、systemd、Nginx、Let's Encrypt 证书。

## 2) VPS 面板部署

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo .venv/bin/python deploy/vps_panel.py
```

打开 `http://<VPS_IP>:8088`，输入域名和邮箱，可执行安装/卸载/重启。

## 3) Windows 客户端

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python client\windows_client.py
```

客户端流程：
1. 输入 `https://` 服务器地址。
2. 注册账号。
3. 登录获取会话。
4. 发送消息/文件、刷新收件箱、下载附件。

## 4) 服务端 API

- `POST /api/register`：注册
- `POST /api/login`：登录
- `POST /api/send`：发送消息/文件（需登录）
- `GET /api/inbox?limit=200`：拉取当前登录用户收件箱
- `GET /api/messages/<message_id>/download`：下载附件（仅收件人）
- `GET /health`：健康检查

鉴权方式：`Authorization: Bearer <token>`

## 5) 注意事项

- 一键脚本与面板都需要 root 权限。
- 域名需先解析到 VPS，80/443 端口要开放。
- 这是基础示例，生产环境建议再加密码强度策略、限流、审计日志。
