# Python 本地 HTTPS + AES-256 通讯程序（Windows 客户端 + 轻量服务端）

本项目提供：
- **服务端**（`server.py`）：支持注册、登录、离线消息队列、收件列表、HTTPS 传输。
- **Windows 本地客户端**（`client.py`）：Tkinter 图形界面，支持配置服务器地址、给指定用户发文本或文件，每条消息单独设置密码并用 **AES-256** 加密。

> 服务端默认监听端口：`43623`

## 1. 功能符合性说明

- 使用指定服务器通信：客户端可在 GUI 输入 HTTPS 服务器地址。
- 使用 HTTPS：服务端必须加载 `cert.pem` 与 `key.pem` 后启动 TLS。
- 每次发送设置本次密码：客户端发送文本/文件前都会弹窗要求输入“本次消息密码”。
- AES-256 加密：客户端使用 PBKDF2 + AES-GCM(256-bit key) 在本地加密后上传。
- 发给对应收件人：服务端按 `recipient` 存储消息。
- 收件人上线后获取列表并下发：客户端登录后轮询 `/api/messages/poll`，收到自己的未投递消息。
- 收件人不在线则等待：服务端 SQLite 保存未投递消息，收件人在线后再取。
- 客户端图形界面：支持服务器地址、登录注册、发消息、发文件、收件列表、双击解密。
- 服务端轻量部署：单文件 Flask + SQLite，适合 1C/512M/5GB 小配置机器。

## 2. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. 生成 HTTPS 证书（测试环境）

```bash
./generate_self_signed_cert.sh
```

会在当前目录生成：
- `cert.pem`
- `key.pem`

## 4. 启动服务端（部署到 43623）

```bash
python server.py --host 0.0.0.0 --port 43623 --cert cert.pem --key key.pem
```

## 5. 启动客户端（Windows 本地）

```bash
python client.py
```

打开后：
1. 输入服务器地址（例如 `https://你的服务器IP:43623`）。
2. 注册并登录。
3. 输入收件人用户名。
4. 发送文本或文件时设置“本次消息密码”。
5. 收件人在列表双击消息，输入对应密码解密。

## 6. 服务端 API 摘要

- `POST /api/register` 注册
- `POST /api/login` 登录，返回 token
- `POST /api/messages/send` 发送消息（Bearer token）
- `GET /api/messages/poll` 拉取未投递消息并标记已投递（Bearer token）
- `GET /api/messages/list` 最近消息列表（Bearer token）

## 7. 资源占用建议（1C/512M/5GB）

- 使用 `python server.py` 单进程即可。
- SQLite 存储轻量、免外部数据库。
- 若并发上升可改用 gunicorn/gevent（仍可轻量，不必 Docker）。
- 建议使用 Nginx 做反向代理与证书管理（生产环境）。

## 8. 安全提醒

- 当前客户端为了便于测试，`requests` 使用 `verify=False`（忽略证书校验）。
  - 生产环境应改为：
    - 使用受信任证书，
    - 或在客户端指定 CA 证书做校验。
- 消息密码不经过服务端，只有发送/接收双方知道。
- 请为用户登录密码启用更强策略、可增加限流与审计。
