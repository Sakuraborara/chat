# 轻量化 HTTPS 离线消息系统（Python）

满足你的需求：
- Windows 本地客户端（图形界面）
- 指定服务器 HTTPS 通讯
- 每条消息单独密码，AES-256-GCM 加密后发送
- 指定收件人发送文本/文件
- 收件人上线后拉取离线消息列表
- 服务端注册 / 登录功能
- 服务端监听 `43623` 端口
- 无 Docker，适配 `1C / 512MB RAM / 5GB ROM`

## 目录
- `server.py`：服务端 API（FastAPI + SQLite）
- `client_gui.py`：Windows 客户端 GUI（Tkinter）
- `requirements.txt`：依赖

## 1) 服务端部署（Linux）

### 安装
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 生成 HTTPS 证书（测试用自签名）
> 生产环境建议使用 Let's Encrypt 等正式证书。

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=your.server.domain"
```

### 启动
```bash
python server.py
```
服务监听：`0.0.0.0:43623`（HTTPS）

## 2) Windows 客户端运行

### 安装
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 启动
```powershell
py client_gui.py
```

### 首次连接自签名证书
如果你使用的是自签名证书，`requests` 默认会校验证书，可能失败：
- 推荐：把证书导入 Windows 信任根
- 或改成正式 CA 证书

## 3) 使用流程
1. 双方各自注册账号。
2. 登录后，发送方填写：收件人 + 本次消息密码 + 文本/文件。
3. 客户端先用本次密码做 PBKDF2 派生，再用 AES-256-GCM 加密。
4. 服务端仅保存密文与元数据。
5. 收件人点击“拉取消息”后会看到消息列表；离线期间消息保留，直到上线拉取。

## 4) 安全说明
- **每条消息都可使用不同密码**（你提出的“每次发送设置本次消息密码”）。
- 服务端无法解密消息正文（仅中转/存储密文）。
- 登录密码在服务端使用 PBKDF2-HMAC-SHA256 存储散列。

## 5) 低配置建议
- SQLite 单文件存储，减少资源占用。
- 单进程 uvicorn 即可运行。
- 及时清理旧消息可降低磁盘占用。
