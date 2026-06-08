from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from urllib import error, request


API_BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_MS = 1000


class DesktopReminder:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("护眼提醒伴侣")
        self.root.geometry("360x140")
        self.root.resizable(False, False)

        self.status_var = tk.StringVar(value="正在监听护眼提醒...")
        ttk.Label(self.root, text="护眼提醒伴侣", font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(22, 8))
        ttk.Label(self.root, textvariable=self.status_var).pack()
        ttk.Button(self.root, text="退出", command=self.root.destroy).pack(pady=18)

        self.showing_alert = False
        self.root.after(200, self.poll)

    def run(self) -> None:
        self.root.mainloop()

    def poll(self) -> None:
        if not self.showing_alert:
            try:
                alerts = self.fetch_pending_alerts()
                if alerts:
                    self.show_alert(alerts[0])
                    self.status_var.set("已显示桌面提醒")
                else:
                    self.status_var.set("正在监听护眼提醒...")
            except Exception as exc:
                self.status_var.set(f"连接后端失败，继续重试：{exc}")
        self.root.after(POLL_INTERVAL_MS, self.poll)

    def fetch_pending_alerts(self) -> list[dict]:
        with request.urlopen(f"{API_BASE_URL}/api/desktop-alerts/pending", timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))

    def update_alert_status(self, alert_id: int, status: str) -> None:
        payload = json.dumps({"status": status}).encode("utf-8")
        req = request.Request(
            f"{API_BASE_URL}/api/desktop-alerts/{alert_id}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with request.urlopen(req, timeout=1.5):
                pass
        except (OSError, error.URLError):
            self.status_var.set("提醒状态同步失败，稍后可重试")

    def show_alert(self, alert: dict) -> None:
        self.showing_alert = True
        alert_id = int(alert["id"])
        self.update_alert_status(alert_id, "shown")

        window = tk.Toplevel(self.root)
        window.title(alert["title"])
        window.configure(bg="#b91c1c")
        window.attributes("-topmost", True)
        window.attributes("-fullscreen", True)
        window.focus_force()
        window.lift()

        container = tk.Frame(window, bg="#b91c1c")
        container.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            container,
            text=alert["title"],
            fg="#ffffff",
            bg="#b91c1c",
            font=("Microsoft YaHei UI", 48, "bold"),
        ).pack(pady=(0, 24))
        tk.Label(
            container,
            text=alert["message"],
            fg="#fff7ed",
            bg="#b91c1c",
            wraplength=900,
            justify="center",
            font=("Microsoft YaHei UI", 22),
        ).pack(pady=(0, 42))

        button = tk.Button(
            container,
            text="我知道了，开始休息",
            command=lambda: self.close_alert(window, alert_id),
            bg="#ffffff",
            fg="#7f1d1d",
            activebackground="#fee2e2",
            activeforeground="#7f1d1d",
            bd=0,
            padx=42,
            pady=16,
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        button.pack()
        button.focus_set()

        window.bind("<Escape>", lambda _event: self.close_alert(window, alert_id))
        window.bind("<Return>", lambda _event: self.close_alert(window, alert_id))
        window.protocol("WM_DELETE_WINDOW", lambda: self.close_alert(window, alert_id))

    def close_alert(self, window: tk.Toplevel, alert_id: int) -> None:
        if window.winfo_exists():
            window.destroy()
        self.update_alert_status(alert_id, "acknowledged")
        self.showing_alert = False
        self.status_var.set("正在监听护眼提醒...")


if __name__ == "__main__":
    DesktopReminder().run()
