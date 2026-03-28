# Python 本地 HTTPS 通讯软件（Windows 客户端 + VPS 服务端）

这个项目提供一套可直接二次开发的示例：

- Windows 本地 **Python 图形客户端**（Tkinter）
- 基于 HTTPS 的 **消息/文件收发能力**
- 部署到 VPS 的 **服务端脚本**
- 一个 **交互式部署面板**（安装/卸载/启动/停止/状态）

> 满足你的要求：不是输入脚本链接后直接部署，而是通过面板进行安装和卸载管理。

---

## 1. 客户端（Windows）

文件：`secure_transfer_client.py`

### 功能

- 输入服务器地址（必须 `https://` 开头）
- 输入自己的用户名并注册
- 向指定用户发送文本消息
- 向指定用户发送文件（Base64 编码后通过 HTTPS 传输）
- 拉取收件箱并自动保存收到的文件到：
  - `C:\Users\<用户名>\Downloads\secure_inbox`

### 运行

```bash
pip install requests
python secure_transfer_client.py
```

---

## 2. 服务端（VPS）

目录：`server/`

### 文件说明

- `server/app.py`：HTTPS API 服务
- `server/requirements.txt`：依赖
- `server/deploy_panel.py`：部署面板（交互式）

### API 能力

- `POST /api/register` 注册用户
- `POST /api/send_message` 发送消息
- `POST /api/send_file` 发送文件
- `GET /api/inbox` 拉取并清空收件箱
- `GET /healthz` 健康检查

所有接口都运行在 HTTPS 下。

---

## 3. VPS 一键部署面板（含安装/卸载）

在 VPS 中进入项目目录后运行：

```bash
cd server
sudo python3 deploy_panel.py
```

你会看到菜单：

- `1` 安装 / 更新
- `2` 卸载
- `3` 启动服务
- `4` 停止服务
- `5` 查看状态
- `0` 退出

### 安装动作会做什么

- 创建虚拟环境 `.venv`
- 安装依赖 `flask`
- 生成自签名 TLS 证书（`server/certs/server.crt` + `server/certs/server.key`）
- 写入 `systemd` 服务：`secure-msg-server`
- 启动并设置开机自启

### 卸载动作会做什么

- 停止并禁用 systemd 服务
- 删除 systemd 服务文件
- 删除 `.venv`
- 保留证书和数据（可按需手动删除）

---

## 4. 证书说明

部署面板默认生成的是 **自签名证书**。

- 生产环境建议替换成受信任 CA 证书（例如 Let's Encrypt）
- 客户端勾选“校验证书”时，需要服务器证书可被系统信任
- 开发测试可先不勾选“校验证书”

---

## 5. 打包 Windows 可执行程序（可选）

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed secure_transfer_client.py
```

生成后的 exe 在 `dist/` 下。
