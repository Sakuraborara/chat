import random
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from datetime import datetime


@dataclass
class ChatMessage:
    sender: str
    content: str
    timestamp: str


class AnimeChatApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("萌萌聊天室 ✨")
        self.root.geometry("960x640")
        self.root.minsize(820, 520)

        self.base_dir = Path(__file__).resolve().parent
        self.bg_dir = self.base_dir / "assets" / "backgrounds"
        self.background_images: dict[str, tk.PhotoImage] = {}

        self._style()
        self._load_backgrounds()
        self._build_ui()
        self._send_welcome_message()

    def _style(self) -> None:
        self.root.configure(bg="#FFEFF8")
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Cute.TFrame", background="#FFEFF8")
        style.configure("Panel.TFrame", background="#FFF8FD")
        style.configure("Cute.TLabel", background="#FFF8FD", foreground="#8B4D7A", font=("Microsoft YaHei UI", 10))
        style.configure(
            "Title.TLabel",
            background="#FFF8FD",
            foreground="#D15AA5",
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        style.configure(
            "Cute.TButton",
            background="#FFB6DE",
            foreground="#6E2A57",
            borderwidth=0,
            focusthickness=0,
            padding=(12, 8),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("Cute.TButton", background=[("active", "#FFA4D6")])

    def _load_backgrounds(self) -> None:
        self.background_images.clear()
        if not self.bg_dir.exists():
            return

        for path in sorted(self.bg_dir.glob("*.ppm")) + sorted(self.bg_dir.glob("*.png")) + sorted(self.bg_dir.glob("*.gif")):
            try:
                self.background_images[path.stem] = tk.PhotoImage(file=path)
            except tk.TclError:
                continue

    def _build_ui(self) -> None:
        self.background_label = tk.Label(self.root, bd=0)
        self.background_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        outer = ttk.Frame(self.root, style="Cute.TFrame", padding=16)
        outer.pack(fill="both", expand=True)

        panel = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        panel.pack(fill="both", expand=True)

        header = ttk.Frame(panel, style="Panel.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="🌸 二次元萌萌聊天室", style="Title.TLabel").pack(side="left")

        controls = ttk.Frame(header, style="Panel.TFrame")
        controls.pack(side="right")

        ttk.Label(controls, text="背景：", style="Cute.TLabel").pack(side="left", padx=(0, 4))
        self.bg_var = tk.StringVar(value="")
        self.bg_picker = ttk.Combobox(controls, textvariable=self.bg_var, state="readonly", width=16)
        self.bg_picker.pack(side="left")
        self.bg_picker.bind("<<ComboboxSelected>>", self._on_pick_background)

        ttk.Button(controls, text="加载图片", style="Cute.TButton", command=self._load_custom_background).pack(side="left", padx=8)

        content = ttk.Frame(panel, style="Panel.TFrame")
        content.pack(fill="both", expand=True, pady=(12, 10))

        self.chat_canvas = tk.Canvas(content, bg="#FFF4FB", highlightthickness=0)
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)

        self.chat_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.messages_frame = ttk.Frame(self.chat_canvas, style="Panel.TFrame")
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.messages_frame, anchor="nw")

        self.messages_frame.bind("<Configure>", self._on_messages_resized)
        self.chat_canvas.bind("<Configure>", self._on_canvas_resized)

        input_bar = ttk.Frame(panel, style="Panel.TFrame")
        input_bar.pack(fill="x")

        self.user_input = tk.Text(input_bar, height=3, bg="#FFFFFF", fg="#6A3D59", relief="flat", font=("Microsoft YaHei UI", 11))
        self.user_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.user_input.bind("<Return>", self._handle_enter)

        ttk.Button(input_bar, text="发送 ✨", style="Cute.TButton", command=self.send_message).pack(side="left")

        self._refresh_background_options()

    def _refresh_background_options(self) -> None:
        names = list(self.background_images.keys())
        self.bg_picker["values"] = names
        if names:
            self.bg_var.set(names[0])
            self._set_background(names[0])

    def _set_background(self, name: str) -> None:
        image = self.background_images.get(name)
        if image:
            self.background_label.configure(image=image)
            self.background_label.image = image

    def _on_pick_background(self, _event: object) -> None:
        self._set_background(self.bg_var.get())

    def _load_custom_background(self) -> None:
        path = filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[("Image files", "*.png *.gif *.ppm"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            image = tk.PhotoImage(file=path)
        except tk.TclError:
            messagebox.showerror("加载失败", "这个图片格式暂不支持，请使用 PNG/GIF/PPM 图片。")
            return

        key = f"自定义-{Path(path).stem}"
        self.background_images[key] = image
        self._refresh_background_options()
        self.bg_var.set(key)
        self._set_background(key)

    def _on_messages_resized(self, _event: object) -> None:
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def _on_canvas_resized(self, event: tk.Event) -> None:
        self.chat_canvas.itemconfigure(self.canvas_window, width=event.width)

    def _handle_enter(self, event: tk.Event) -> str:
        if event.state & 0x0001:  # shift
            return ""
        self.send_message()
        return "break"

    def _send_welcome_message(self) -> None:
        msg = ChatMessage(sender="Momo酱", content="欢迎来到萌萌聊天室～今天也要元气满满哦！", timestamp=self._now())
        self._add_message_bubble(msg)

    def send_message(self) -> None:
        content = self.user_input.get("1.0", "end").strip()
        if not content:
            return

        self.user_input.delete("1.0", "end")
        user_msg = ChatMessage(sender="你", content=content, timestamp=self._now())
        self._add_message_bubble(user_msg, is_user=True)

        reply = ChatMessage(sender="Momo酱", content=self._generate_reply(content), timestamp=self._now())
        self.root.after(260, lambda: self._add_message_bubble(reply))

    def _generate_reply(self, text: str) -> str:
        lower = text.lower()
        keyword_replies = {
            "你好": "你好呀～(๑˃ᴗ˂)ﻭ 有什么想聊的吗？",
            "学习": "学习也要劳逸结合喔！要不要我给你列个番茄钟计划？",
            "工作": "辛苦啦！记得喝口水，伸个懒腰，继续加油～",
            "心情": "如果今天有点emo，就给自己一点点奖励吧，比如一杯奶茶✨",
            "天气": "不管天气怎样，今天你都很可爱！",
        }

        for key, value in keyword_replies.items():
            if key in text or key in lower:
                return value

        endings = [
            "我在认真听你说呢～",
            "说得好有道理，记在小本本上啦！",
            "嗯嗯，我也这么觉得！",
            "收到！要不要继续展开讲讲？",
            "太有趣了，再说一点嘛～",
        ]
        return random.choice(endings)

    def _add_message_bubble(self, message: ChatMessage, is_user: bool = False) -> None:
        row = ttk.Frame(self.messages_frame, style="Panel.TFrame")
        row.pack(fill="x", pady=6, padx=8)

        bubble_color = "#FFE0F4" if is_user else "#FFF8D8"
        text_color = "#7D365F" if is_user else "#7A5E24"
        anchor = "e" if is_user else "w"

        container = tk.Frame(row, bg="#FFF8FD")
        container.pack(anchor=anchor, fill="x")

        name = tk.Label(container, text=f"{message.sender} · {message.timestamp}", fg="#AF78A0", bg="#FFF8FD", font=("Microsoft YaHei UI", 9))
        name.pack(anchor=anchor)

        bubble = tk.Label(
            container,
            text=message.content,
            justify="left",
            wraplength=620,
            bg=bubble_color,
            fg=text_color,
            font=("Microsoft YaHei UI", 11),
            padx=12,
            pady=10,
        )
        bubble.pack(anchor=anchor)

        self.root.after(10, lambda: self.chat_canvas.yview_moveto(1.0))

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M")


def main() -> None:
    root = tk.Tk()
    app = AnimeChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
