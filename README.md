# 萌萌聊天室（Windows）

一个可爱的二次元风聊天小程序，使用 Python + Tkinter 编写，支持：

- 🌸 可爱风格聊天界面
- 💬 基础聊天功能（你发消息，Momo酱回复）
- 🖼️ 背景图片切换（内置 + 自定义）

## 运行方式

> 需要 Python 3.10+（Windows 推荐 3.11）

```bash
python anime_chat.py
```

## 背景图片

程序会自动读取 `assets/backgrounds/` 目录下的图片，当前支持：

- `.ppm`（内置可直接使用）
- `.png`
- `.gif`

你也可以在界面点击 **“加载图片”**，选择本地图片作为聊天背景。

## 打包为 Windows 可执行程序（可选）

如果你要发给没有 Python 环境的同学，可以打包：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --add-data "assets;backgrounds" anime_chat.py
```

打包后可执行文件会在 `dist/` 下。

## 项目结构

```text
.
├─ anime_chat.py
├─ assets/
│  └─ backgrounds/
│     ├─ sakura.ppm
│     ├─ sky_dream.ppm
│     └─ peach_milk.ppm
└─ README.md
```

祝你聊天愉快，天天开心 ✨
