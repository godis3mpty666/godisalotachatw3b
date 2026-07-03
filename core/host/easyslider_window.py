from __future__ import annotations

import json
import base64
import ctypes
import os
import sys
import tkinter as tk
import urllib.request
from pathlib import Path
from typing import Any


WINDOW_TITLE = "godisalotachat 3asyslid3r"
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, data: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
    raw = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class EasySliderWindow:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#080a18")
        self.settings: dict[str, Any] = {}
        self.language = "de"
        self.images: list[tk.PhotoImage] = []
        self.opened = False
        self._last_settings_key = ""
        self._open_after_id = None
        self._collapse_after_id = None
        self._target_alpha = 0.88
        try:
            self.root.attributes("-alpha", 0.88)
        except Exception:
            pass
        if os.name == "nt":
            try:
                self.root.wm_attributes("-toolwindow", True)
            except Exception:
                pass

        self.frame = tk.Frame(self.root, bg="#080a18", padx=8, pady=8)
        self.frame.pack(fill="both", expand=True)
        self.root.bind("<Enter>", lambda _e: self.schedule_open())
        self.frame.bind("<Enter>", lambda _e: self.schedule_open())
        self.root.bind("<Leave>", lambda _e: self.schedule_collapse())

    def run(self) -> int:
        self.root.after(100, self.reload)
        self.root.after(250, self.poll_pointer)
        self.root.after(500, self.poll_settings)
        self.root.mainloop()
        return 0

    def poll_settings(self) -> None:
        try:
            data = _fetch_json(f"{self.base_url}/api/settings", timeout=1.0)
            ui = data.get("ui") or {}
            settings = (ui.get("3asyslid3r") or {})
            language = "en" if str(ui.get("language") or "de").lower().startswith("en") else "de"
            key = json.dumps({"settings": settings, "language": language}, sort_keys=True)
            if key != self._last_settings_key:
                self.reload(settings, language)
        except Exception:
            pass
        self.root.after(2500, self.poll_settings)

    def reload(self, settings: dict[str, Any] | None = None, language: str | None = None) -> None:
        if settings is None:
            ui = _fetch_json(f"{self.base_url}/api/settings").get("ui") or {}
            settings = ui.get("3asyslid3r") or {}
            language = str(ui.get("language") or "de")
        self.settings = settings
        self.language = "en" if str(language or "de").lower().startswith("en") else "de"
        self._last_settings_key = json.dumps({"settings": settings, "language": self.language}, sort_keys=True)
        enabled = bool(settings.get("enabled", True))
        if not enabled:
            self.root.withdraw()
            return
        self.root.deiconify()
        self.opened = False
        self.build_buttons()
        try:
            opacity = max(0, min(100, int(float(settings.get("opacity", 82)))))
            self._target_alpha = max(0.08, opacity / 100)
        except Exception:
            pass
        self.position(collapsed=True)

    def build_buttons(self) -> None:
        for child in list(self.frame.winfo_children()):
            child.destroy()
        self.images.clear()
        buttons = [b for b in (self.settings.get("buttons") or []) if b.get("enabled", True)]
        edge = str(self.settings.get("edge") or "left").lower()
        horizontal = edge in {"top", "bottom"}
        for button in buttons:
            label = str(button.get("label") or button.get("id") or "Button")
            if self.language == "en":
                label = {"Plattformen": "Platforms"}.get(label, label)
            path = str(button.get("path") or "/")
            image = self.load_image(str(button.get("id") or ""))
            kwargs = {
                "text": label,
                "command": lambda p=path: self.activate(p),
                "bg": "#171a29",
                "fg": "#f7f8ff",
                "activebackground": "#865cff",
                "activeforeground": "#ffffff",
                "relief": "flat",
                "bd": 0,
                "padx": 10,
                "pady": 8,
                "font": ("Segoe UI", 10, "bold"),
            }
            if image:
                kwargs["image"] = image
                kwargs["compound"] = "left"
            btn = tk.Button(self.frame, **kwargs)
            if horizontal:
                btn.pack(side="left", padx=4, pady=0)
            else:
                btn.pack(side="top", padx=0, pady=4, fill="x")
            btn.bind("<Enter>", lambda _e: self.schedule_open())
        self.root.update_idletasks()

    def load_image(self, button_id: str) -> tk.PhotoImage | None:
        safe_id = "".join(ch for ch in button_id.lower() if ch.isalnum() or ch in "_-")
        if not safe_id:
            return None
        try:
            with urllib.request.urlopen(f"{self.base_url}/slider-asset/{safe_id}.png", timeout=1.0) as resp:
                data = resp.read()
            img = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            if img.width() > 24 or img.height() > 24:
                scale = max(1, int(max(img.width() / 24, img.height() / 24)))
                img = img.subsample(scale, scale)
            self.images.append(img)
            return img
        except Exception:
            return None

    def position(self, collapsed: bool = False) -> None:
        self.root.update_idletasks()
        edge = str(self.settings.get("edge") or "left").lower()
        sx, sy, sw, sh = self.virtual_screen()
        req_w = max(24, self.root.winfo_reqwidth())
        req_h = max(24, self.root.winfo_reqheight())
        if collapsed:
            try:
                self.root.attributes("-alpha", 0.01)
            except Exception:
                pass
            if edge in {"left", "right"}:
                w, h = 2, sh
                x = sx if edge == "left" else sx + sw - w
                y = sy
            else:
                w, h = sw, 2
                x = sx
                y = sy if edge == "top" else sy + sh - h
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            return
        try:
            self.root.attributes("-alpha", self._target_alpha)
        except Exception:
            pass
        w, h = req_w, req_h
        if edge == "right":
            x = sx + sw - w
            y = sy + max(0, int((sh - h) / 2))
        elif edge == "top":
            x = sx + max(0, int((sw - w) / 2))
            y = sy
        elif edge == "bottom":
            x = sx + max(0, int((sw - w) / 2))
            y = sy + sh - h
        else:
            x = sx
            y = sy + max(0, int((sh - h) / 2))
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def virtual_screen(self) -> tuple[int, int, int, int]:
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                sx = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
                sy = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
                sw = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
                sh = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
                if sw > 0 and sh > 0:
                    return sx, sy, sw, sh
            except Exception:
                pass
        return 0, 0, int(self.root.winfo_screenwidth()), int(self.root.winfo_screenheight())

    def pointer_xy(self) -> tuple[int, int]:
        try:
            return int(self.root.winfo_pointerx()), int(self.root.winfo_pointery())
        except Exception:
            return -100000, -100000

    def pointer_on_edge(self) -> bool:
        edge = str(self.settings.get("edge") or "left").lower()
        sx, sy, sw, sh = self.virtual_screen()
        px, py = self.pointer_xy()
        margin = 3
        if edge == "right":
            return sx + sw - margin <= px <= sx + sw + margin and sy <= py <= sy + sh
        if edge == "top":
            return sy - margin <= py <= sy + margin and sx <= px <= sx + sw
        if edge == "bottom":
            return sy + sh - margin <= py <= sy + sh + margin and sx <= px <= sx + sw
        return sx - margin <= px <= sx + margin and sy <= py <= sy + sh

    def pointer_inside_window(self) -> bool:
        try:
            x, y = int(self.root.winfo_x()), int(self.root.winfo_y())
            w, h = int(self.root.winfo_width()), int(self.root.winfo_height())
            px, py = self.pointer_xy()
            return x <= px <= x + w and y <= py <= y + h
        except Exception:
            return False

    def poll_pointer(self) -> None:
        try:
            if bool(self.settings.get("enabled", True)):
                if self.opened:
                    if not self.pointer_inside_window():
                        self.schedule_collapse()
                elif self.pointer_on_edge():
                    self.schedule_open()
                else:
                    self.cancel_scheduled_open()
        except Exception:
            pass
        self.root.after(80, self.poll_pointer)

    def open_delay_ms(self) -> int:
        try:
            return max(0, min(120000, int(float(self.settings.get("delaySeconds", 2) or 2) * 1000)))
        except Exception:
            return 2000

    def schedule_open(self) -> None:
        if self.opened or self._open_after_id is not None:
            return
        self._open_after_id = self.root.after(self.open_delay_ms(), self._delayed_open)

    def cancel_scheduled_open(self) -> None:
        if self._open_after_id is None:
            return
        try:
            self.root.after_cancel(self._open_after_id)
        except Exception:
            pass
        self._open_after_id = None

    def _delayed_open(self) -> None:
        self._open_after_id = None
        if self.pointer_on_edge() or self.pointer_inside_window():
            self.open_bar()

    def schedule_collapse(self) -> None:
        if not self.opened or self._collapse_after_id is not None:
            return
        self._collapse_after_id = self.root.after(700, self._collapse_if_outside)

    def _collapse_if_outside(self) -> None:
        self._collapse_after_id = None
        if self.opened and not self.pointer_inside_window():
            self.opened = False
            self.position(collapsed=True)

    def open_bar(self) -> None:
        if not bool(self.settings.get("enabled", True)):
            return
        self.cancel_scheduled_open()
        self.opened = True
        self.position(collapsed=False)

    def activate(self, path: str) -> None:
        try:
            _post_json(f"{self.base_url}/api/3asyslid3r/activate", {"path": path}, timeout=1.5)
        except Exception:
            pass
        self.opened = False
        self.position(collapsed=True)


def run_easyslider(url: str) -> int:
    try:
        return EasySliderWindow(url).run()
    except Exception:
        try:
            log_dir = Path(sys.executable).resolve().parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "easyslider_error.log").write_text(str(sys.exc_info()[1]), encoding="utf-8")
        except Exception:
            pass
        raise
