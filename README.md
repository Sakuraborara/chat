# Windows 客户端 + VPS 一键脚本启动面板部署（HTTPS）

你这次要求的是：**一键脚本只负责启动面板，部署/卸载都在面板里做，不要拆开**。
本版本已改成这个流程。

## 整体流程

1. 在 VPS 项目根目录运行一键脚本：`quick_deploy.sh`（或 `deploy/quick_deploy.sh`）。
2. 脚本启动部署面板服务（`chat-deploy-panel`）。
3. 打开面板 `http://<VPS_IP>:8088`。
4. 在面板点击安装/卸载程序（`chat-server`）。

---

## 1) VPS 一键脚本（仅启动/管理面板）

> 注意：请先 `cd` 到项目根目录再执行脚本，否则会出现 `No such file or directory`。

```bash
sudo bash quick_deploy.sh setup
```

会自动：
- 安装 Python 运行环境
- 创建 `.venv` 并安装依赖
- 写入并启动 `chat-deploy-panel` systemd 服务

### 其他命令

```bash
sudo bash quick_deploy.sh start
sudo bash quick_deploy.sh stop
sudo bash quick_deploy.sh status
sudo bash quick_deploy.sh uninstall-panel
```

也可以直接进菜单：

```bash
sudo bash quick_deploy.sh
```

## 2) 面板部署（真正的程序安装/卸载入口）

面板文件：`deploy/vps_panel.py`。

启动后访问：`http://<VPS_IP>:8088`

面板中可执行：
- 安装并配置 HTTPS（安装 chat-server + Nginx + 证书）
- 卸载 chat-server
- 重启 chat-server

## 3) Windows 客户端

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python client\windows_client.py
```

客户端流程：
1. 输入 `https://` 服务器地址
2. 注册账号
3. 登录
4. 发送消息/文件、刷新收件箱、下载附件

## 4) 服务端 API

- `POST /api/register`：注册
- `POST /api/login`：登录
- `POST /api/send`：发送消息/文件（需登录）
- `GET /api/inbox?limit=200`：拉取当前登录用户收件箱
- `GET /api/messages/<message_id>/download`：下载附件（仅收件人）
- `GET /health`：健康检查

鉴权方式：`Authorization: Bearer <token>`

## 5) 注意事项

- 一键脚本和面板都需要 root 权限。
- 域名需先解析到 VPS，80/443 端口要开放。
- 生产环境建议再补充限流、审计、密码策略。
