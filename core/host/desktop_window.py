from __future__ import annotations

import ctypes
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Any


WINDOW_TITLE = "godisalotachat Desktop Chat"
TRANSPARENT_KEY = "#010203"
DEFAULT_SIZE = (780, 820)
MIN_SIZE = (320, 240)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
MB_OK = 0x00000000
GA_ROOT = 2

user32 = ctypes.windll.user32 if os.name == "nt" else None

PLATFORM_LABELS = {
    "twitch": "Twitch",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "kick": "Kick",
}
PLATFORM_ICONS = {
    "twitch": "▣",
    "tiktok": "♪",
    "youtube": "▶",
    "kick": "K",
}
PLATFORM_COLORS = {
    "twitch": "#9146ff",
    "tiktok": "#161616",
    "youtube": "#ff0000",
    "kick": "#53fc18",
}


def _message_box(text: str, title: str = WINDOW_TITLE, flags: int = MB_OK) -> int:
    if user32 is None:
        print(f"{title}: {text}")
        return 1
    return int(user32.MessageBoxW(None, str(text), str(title), flags))


def _log(text: str) -> None:
    try:
        print(f"[desktop-window] {text}", flush=True)
    except Exception:
        pass


def _get_window_long(hwnd: int) -> int:
    if sys.maxsize > 2**32:
        return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))
    return int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))


def _set_window_long(hwnd: int, value: int) -> None:
    if sys.maxsize > 2**32:
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, value)
    else:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, value)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)


def _set_clickthrough(hwnd: int | None, enabled: bool) -> None:
    if user32 is None or not hwnd:
        return
    try:
        style = _get_window_long(hwnd)
        # Tkinter setzt fuer -transparentcolor selbst WS_EX_LAYERED und die
        # Layer-Attribute. Wir duerfen das hier nicht neu erzwingen, sonst
        # kann der transparente Farbkey kaputtgehen und das Fenster wird schwarz.
        style |= WS_EX_TOOLWINDOW
        style &= ~WS_EX_APPWINDOW
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        _set_window_long(hwnd, style)
    except Exception as exc:
        _log(f"click-through konnte nicht gesetzt werden: {exc}")



def _candidate_hwnds_from_widget(widget) -> list[int]:
    """Tkinter erzeugt mehrere HWNDs (Toplevel/Canvas/Wrapper).
    Click-through muss auf alle relevanten Handles, sonst blockt eines davon
    weiterhin die Maus und das Spiel darunter bekommt keine Klicks.
    """
    if user32 is None or widget is None:
        return []
    handles: list[int] = []
    try:
        hwnd = int(widget.winfo_id())
        if hwnd:
            handles.append(hwnd)
            try:
                root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT))
                if root_hwnd:
                    handles.append(root_hwnd)
            except Exception:
                pass
    except Exception:
        pass
    # Dedupe, Reihenfolge erhalten
    out: list[int] = []
    for hwnd in handles:
        if hwnd and hwnd not in out:
            out.append(hwnd)
    return out


def _set_widget_clickthrough(widget, enabled: bool) -> None:
    for hwnd in _candidate_hwnds_from_widget(widget):
        _set_clickthrough(hwnd, enabled)
    try:
        for child in widget.winfo_children():
            _set_widget_clickthrough(child, enabled)
    except Exception:
        pass

def _hex_to_rgb(value: str | None, fallback: str = "#0d101d") -> tuple[int, int, int]:
    s = str(value or fallback).strip().lstrip("#")
    if len(s) != 6:
        s = fallback.lstrip("#")
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return 13, 16, 29


def _safe_draw_color(hex_color: str | None, fallback: str = "#0d101d") -> str:
    r, g, b = _hex_to_rgb(hex_color, fallback)
    # Niemals exakt den transparenten Farbkey verwenden, sonst stanzt Windows das
    # Element komplett aus. Auch sehr nahe Farben vermeiden wir, weil manche
    # Treiber/Web-Captures das sonst wie Schwarz/Flackern behandeln.
    if (r, g, b) in ((1, 2, 3), (2, 3, 4), (0, 0, 0)):
        r, g, b = (13, 16, 29)
    return f"#{r:02x}{g:02x}{b:02x}"



def _opacity_to_window_alpha(opacity_percent: int | float | None) -> float:
    try:
        value = float(opacity_percent)
    except Exception:
        value = 82.0
    # Tkinter kann keine echte Alpha-Transparenz pro Canvas-Rechteck.
    # Deshalb nutzen wir hier stabile globale Fenster-Alpha: keine Muster,
    # kein Weiss/Schwarz-Kippen, dafuer wird auch Text leicht transparent.
    value = max(18.0, min(100.0, value))
    return value / 100.0

def _opacity_stipple(_opacity_percent: int | float | None) -> str | None:
    # Wichtig: Tkinter kann auf Canvas-Rechtecken keine saubere, weiche
    # Alpha-Transparenz rendern. Stipple erzeugt ein sichtbares Muster,
    # Farbmischung gegen den Transparent-Key kippt je nach Wert nach Schwarz/Weiss.
    # Deshalb wird die Box-Opacity im nativen Desktop-Overlay bewusst ignoriert.
    # Die Flaeche ausserhalb der Boxen bleibt weiterhin echt transparent.
    return None

def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", str(value), flags=re.I)
    text = re.sub(r"<img[^>]*alt=['\"]?([^'\" >]+).*?>", r"\1", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _user_color(platform: str, user: str) -> str:
    h = 2166136261
    for ch in f"{platform}:{user}":
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    # einfache HSL->RGB Annäherung via colorsys
    import colorsys

    r, g, b = colorsys.hls_to_rgb((abs(h) % 360) / 360.0, 0.68, 0.78)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _fetch_json(url: str, timeout: float = 0.8) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _post_json(url: str, payload: Any, timeout: float = 1.2) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).read()


def _ping_url(url: str, timeout: float = 0.55) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            res.read(1)
        return True
    except Exception:
        return False


@dataclass
class DragState:
    mode: str = ""
    target: str = ""
    start_x: int = 0
    start_y: int = 0
    start_box: dict[str, int] | None = None
    start_win_w: int = 0
    start_win_h: int = 0
    start_win_x: int = 0
    start_win_y: int = 0


class DesktopTkOverlay:
    def __init__(self, url: str):
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk = tk
        self.tkfont = tkfont
        self.url = url
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme or 'http'}://{parsed.netloc}"
        self.runtime_url = f"{base}/api/runtime"
        self.layout_url = f"{base}/api/desktop-chat/layout"
        self.state_url = f"{base}/api/desktop-chat/state"
        self.chat_url = f"{base}/api/chat-state"

        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception as exc:
            _log(f"transparentcolor nicht verfuegbar: {exc}")
        self.root.geometry(f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}+80+80")
        self.root.minsize(*MIN_SIZE)

        # Zwei native Fenster:
        # 1) bg_root rendert nur die halbtransparenten Box-Hintergruende.
        # 2) root rendert Text/Symbole/Edit-Griffe voll deckend darueber.
        # Damit wird nur der Chathintergrund transparent, nicht der Inhalt.
        self.bg_root = tk.Toplevel(self.root)
        self.bg_root.title(WINDOW_TITLE + " Background")
        self.bg_root.overrideredirect(True)
        self.bg_root.attributes("-topmost", True)
        self.bg_root.configure(bg=TRANSPARENT_KEY)
        try:
            self.bg_root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception as exc:
            _log(f"background transparentcolor nicht verfuegbar: {exc}")
        self.bg_root.geometry(f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}+80+80")

        self.bg_canvas = tk.Canvas(self.bg_root, highlightthickness=0, bd=0, bg=TRANSPARENT_KEY)
        self.bg_canvas.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=TRANSPARENT_KEY)
        self.canvas.pack(fill="both", expand=True)

        self.layout: dict[str, Any] = {}
        self.editing = False
        self.hwnd: int | None = None
        self.bg_hwnd: int | None = None
        self.drag = DragState()
        self.last_chat_state: dict[str, Any] = {}
        self.last_runtime_ok = True
        self.runtime_fail_count = 0
        self._save_after_id: str | None = None
        self._last_render_key = ""
        self._last_clickthrough_state: bool | None = None
        self._last_window_geometry: tuple[int, int, int, int] | None = None
        self._z_order_done = False
        self._last_bg_alpha: float | None = None
        self._platform_images: dict[str, Any] = {}

        self.canvas.bind("<ButtonPress-1>", self._pointer_down)
        self.canvas.bind("<B1-Motion>", self._pointer_move)
        self.canvas.bind("<ButtonRelease-1>", self._pointer_up)
        self.canvas.bind("<Configure>", self._on_configure)
        self.root.bind("<Escape>", lambda _e: self._set_remote_editing(False))
        self.root.bind("<F8>", lambda _e: self._set_remote_editing(not self.editing))

    def _on_configure(self, _event=None) -> None:
        geometry = (
            int(self.root.winfo_x()),
            int(self.root.winfo_y()),
            int(self.root.winfo_width()),
            int(self.root.winfo_height()),
        )
        if self._last_window_geometry == geometry:
            return
        self._last_window_geometry = geometry
        # Tk applies geometry changes asynchronously. Sync on the next idle
        # turn so the transparent background uses the final x/y as well as size.
        self.root.after_idle(self._sync_background_window)
        self.render()

    def run(self) -> int:
        self.root.after(100, self._init_window)
        self.root.after(150, self._poll)
        self.root.mainloop()
        return 0

    def _init_window(self) -> None:
        try:
            self.hwnd = int(self.root.winfo_id())
            self.bg_hwnd = int(self.bg_root.winfo_id())
        except Exception as exc:
            _log(f"hwnd init fehlgeschlagen: {exc}")
        self._load_layout()
        self._restore_window_geometry()
        self._sync_background_window()
        self._ensure_z_order()
        self.render()
        # Erst nach dem ersten Rendern click-through setzen. Hintergrundfenster
        # bleibt immer durchklickbar, Eingaben laufen nur ueber das Vorderfenster.
        self.root.after(250, lambda: self._apply_clickthrough_state(True))

    def _sync_background_window(self) -> None:
        try:
            self.root.update_idletasks()
            geom = f"{self.root.winfo_width()}x{self.root.winfo_height()}+{self.root.winfo_x()}+{self.root.winfo_y()}"
            if self.bg_root.winfo_geometry() != geom:
                self.bg_root.geometry(geom)
        except Exception:
            pass

    def _ensure_z_order(self) -> None:
        # Z-Reihenfolge nur gezielt setzen, nicht in jeder Poll-/Render-Runde.
        # Das staendige lower/lift war bei zwei transparenten Fenstern sichtbar am Zucken beteiligt.
        try:
            self.bg_root.lower(self.root)
            self.root.lift(self.bg_root)
            self._z_order_done = True
        except Exception:
            try:
                self.bg_root.lift()
                self.root.lift()
                self._z_order_done = True
            except Exception:
                pass

    def _apply_clickthrough_state(self, force: bool = False) -> None:
        # Style-Aenderungen an transparenten Tk-Fenstern sind teuer und koennen sichtbar flackern.
        # Darum nur anwenden, wenn sich der Modus wirklich geaendert hat oder explizit erzwungen wird.
        through = not self.editing
        if not force and self._last_clickthrough_state == through:
            return
        self._last_clickthrough_state = through

        # Hintergrundfenster darf niemals Maus fressen.
        _set_widget_clickthrough(self.bg_root, True)
        _set_widget_clickthrough(self.bg_canvas, True)

        # Vorderfenster: im Normalmodus komplett durchklickbar, im Editmode klickbar.
        _set_widget_clickthrough(self.root, through)
        _set_widget_clickthrough(self.canvas, through)

    def _load_layout(self) -> None:
        try:
            data = _fetch_json(self.layout_url)
            if isinstance(data, dict):
                self.layout = data
        except Exception as exc:
            _log(f"layout konnte nicht geladen werden: {exc}")
        self.layout.setdefault("viewerBar", {"x": 20, "y": 20, "w": 700, "h": 58})
        self.layout.setdefault("chatPanel", {"x": 20, "y": 90, "w": 700, "h": 590})
        self.layout.setdefault(
            "style",
            {
                "background": "#0d101d",
                "opacity": 82,
                "radius": 16,
                "fontFamily": "Segoe UI",
                "fontSize": 16,
                "textColor": "#ffffff",
            },
        )
        self.layout.setdefault("window", {"x": 80, "y": 80, "w": DEFAULT_SIZE[0], "h": DEFAULT_SIZE[1]})

    def _restore_window_geometry(self) -> None:
        window = self.layout.get("window") or {}
        try:
            x = max(-4000, min(4000, int(window.get("x", 80))))
            y = max(-4000, min(4000, int(window.get("y", 80))))
            w = max(MIN_SIZE[0], min(4000, int(window.get("w", DEFAULT_SIZE[0]))))
            h = max(MIN_SIZE[1], min(4000, int(window.get("h", DEFAULT_SIZE[1]))))
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception as exc:
            _log(f"Fensterposition konnte nicht geladen werden: {exc}")

    def _capture_window_geometry(self) -> None:
        self.layout["window"] = {
            "x": int(self.root.winfo_x()),
            "y": int(self.root.winfo_y()),
            "w": int(self.root.winfo_width()),
            "h": int(self.root.winfo_height()),
        }

    def _stable_json_key(self, value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(value)

    def _close_due_to_runtime_loss(self) -> None:
        try:
            _log("runtime nicht mehr erreichbar, Desktopfenster wird geschlossen")
            self.bg_root.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _poll(self) -> None:
        # Wenn der Browser/Main-Host geschlossen wurde, muss das Overlay auch weg.
        # Ein einzelner Timeout kann aber beim Build/Reload kurz passieren, deshalb
        # schliessen wir nach zwei direkten Fehlschlaegen (~1-1.5s) statt endlos
        # offen zu bleiben wie vorher.
        runtime = None
        try:
            runtime = _fetch_json(self.runtime_url, timeout=0.55)
        except Exception:
            runtime = None

        if not isinstance(runtime, dict):
            self.runtime_fail_count += 1
            if self.runtime_fail_count >= 2:
                self._close_due_to_runtime_loss()
                return
            self.root.after(500, self._poll)
            return

        # Wenn das eigentliche Browserfenster geschlossen wurde, endet der Main-UI-Heartbeat.
        # Der Server bleibt je nach Timing noch einige Sekunden offen; das Overlay soll aber direkt mitgehen.
        try:
            if bool(runtime.get("ui_heartbeat_enabled")):
                age = float(runtime.get("ui_heartbeat_age", 0.0))
                if age > 5.5:
                    _log("main ui heartbeat verloren, Desktopfenster wird geschlossen")
                    self._close_due_to_runtime_loss()
                    return
        except Exception:
            pass

        self.runtime_fail_count = 0
        self.last_runtime_ok = True
        needs_render = False

        try:
            state = _fetch_json(self.state_url, timeout=0.5)
            if isinstance(state, dict):
                new_editing = bool(state.get("editing", False))
                if self.editing != new_editing:
                    self.editing = new_editing
                    self._apply_clickthrough_state()
                    if self.editing:
                        self._ensure_z_order()
                        try:
                            self.root.focus_force()
                        except Exception:
                            pass
                    needs_render = True
        except Exception as exc:
            _log(f"edit-state konnte nicht gelesen werden: {exc}")

        try:
            chat = _fetch_json(self.chat_url, timeout=0.65)
            if isinstance(chat, dict):
                new_key = self._stable_json_key(chat)
                old_key = self._stable_json_key(self.last_chat_state)
                if new_key != old_key:
                    self.last_chat_state = chat
                    needs_render = True
        except Exception as exc:
            _log(f"chat-state konnte nicht gelesen werden: {exc}")

        try:
            layout = _fetch_json(self.layout_url, timeout=0.65)
            if isinstance(layout, dict) and not self.drag.mode:
                layout.setdefault("style", {})
                new_key = self._stable_json_key(layout)
                old_key = self._stable_json_key(self.layout)
                if new_key != old_key:
                    self.layout = layout
                    needs_render = True
        except Exception as exc:
            _log(f"layout konnte nicht aktualisiert werden: {exc}")

        if needs_render:
            self.render()

        self.root.after(900, self._poll)

    def set_editing(self, editing: bool) -> None:
        changed = self.editing != editing
        self.editing = editing
        self._apply_clickthrough_state(True)
        if editing:
            self._ensure_z_order()
            try:
                self.root.focus_force()
            except Exception:
                pass
        if changed:
            self.render()

    def _set_remote_editing(self, editing: bool) -> None:
        try:
            _post_json(self.state_url.rsplit("/", 1)[0] + "/edit", {"editing": editing})
        except Exception:
            pass
        self.set_editing(editing)

    def _box_at(self, x: int, y: int) -> tuple[str, str] | None:
        # Native Resize-Griff fuer das komplette Fenster
        if self.editing and x >= self.root.winfo_width() - 34 and y >= self.root.winfo_height() - 34:
            return ("window-resize", "window")
        for box_id in ("viewerBar", "chatPanel"):
            box = self.layout.get(box_id) or {}
            bx, by, bw, bh = int(box.get("x", 0)), int(box.get("y", 0)), int(box.get("w", 0)), int(box.get("h", 0))
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if self.editing and x >= bx + bw - 28 and y >= by + bh - 28:
                    return ("box-resize", box_id)
                return ("box-move", box_id)
        if self.editing:
            return ("window-move", "window")
        return None

    def _pointer_down(self, event) -> None:
        if not self.editing:
            return
        hit = self._box_at(int(event.x), int(event.y))
        if not hit:
            return
        mode, target = hit
        self.drag = DragState(
            mode=mode,
            target=target,
            start_x=int(event.x_root),
            start_y=int(event.y_root),
            start_box=dict(self.layout.get(target, {})) if target in self.layout else None,
            start_win_w=self.root.winfo_width(),
            start_win_h=self.root.winfo_height(),
            start_win_x=self.root.winfo_x(),
            start_win_y=self.root.winfo_y(),
        )

    def _pointer_move(self, event) -> None:
        if not self.drag.mode:
            return
        dx = int(event.x_root) - self.drag.start_x
        dy = int(event.y_root) - self.drag.start_y
        if self.drag.mode == "window-move":
            self.root.geometry(f"+{self.drag.start_win_x + dx}+{self.drag.start_win_y + dy}")
            self._sync_background_window()
        elif self.drag.mode == "window-resize":
            w = max(MIN_SIZE[0], self.drag.start_win_w + dx)
            h = max(MIN_SIZE[1], self.drag.start_win_h + dy)
            self.root.geometry(f"{w}x{h}")
            self._sync_background_window()
        elif self.drag.target in self.layout and self.drag.start_box:
            box = self.layout[self.drag.target]
            start = self.drag.start_box
            if self.drag.mode == "box-resize":
                box["w"] = max(140, int(start.get("w", 200)) + dx)
                box["h"] = max(42, int(start.get("h", 80)) + dy)
            else:
                box["x"] = max(0, int(start.get("x", 0)) + dx)
                box["y"] = max(0, int(start.get("y", 0)) + dy)
            self.render()

    def _pointer_up(self, _event) -> None:
        if self.drag.mode in ("box-move", "box-resize", "window-move", "window-resize"):
            if self.drag.mode in ("window-move", "window-resize"):
                self.drag = DragState()
                # Capture after Tk has committed the final mouse geometry.
                self.root.after_idle(self._capture_and_save_window_layout)
                return
            self._schedule_layout_save()
        self.drag = DragState()

    def _capture_and_save_window_layout(self) -> None:
        self._sync_background_window()
        self._capture_window_geometry()
        self._save_layout()

    def _schedule_layout_save(self) -> None:
        if self._save_after_id:
            try:
                self.root.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.root.after(150, self._save_layout)

    def _save_layout(self) -> None:
        self._save_after_id = None
        try:
            # The dashboard can change AutoStart/style while this native window
            # is open. Merge only the geometry owned by this window into the
            # newest server layout, otherwise an old local snapshot resets the
            # checkbox or other settings on every drag.
            latest = _fetch_json(self.layout_url, timeout=1.0)
            if not isinstance(latest, dict):
                latest = {}
            for key in ("viewerBar", "chatPanel", "window"):
                if isinstance(self.layout.get(key), dict):
                    latest[key] = dict(self.layout[key])
            self.layout = latest
            _post_json(self.layout_url, latest)
        except Exception as exc:
            _log(f"layout speichern fehlgeschlagen: {exc}")

    def _rounded_rect(self, x: int, y: int, w: int, h: int, r: int, canvas=None, **kwargs) -> None:
        c = canvas or self.canvas
        r = max(0, min(int(r), int(w / 2), int(h / 2)))
        if r <= 0:
            c.create_rectangle(x, y, x + w, y + h, **kwargs)
            return
        points = [
            x + r,
            y,
            x + w - r,
            y,
            x + w,
            y,
            x + w,
            y + r,
            x + w,
            y + h - r,
            x + w,
            y + h,
            x + w - r,
            y + h,
            x + r,
            y + h,
            x,
            y + h,
            x,
            y + h - r,
            x,
            y + r,
            x,
            y,
        ]
        c.create_polygon(points, smooth=True, splinesteps=12, **kwargs)

    def _platform_image(self, platform: str, blocked: bool = False, size: int = 16):
        asset_key = "no_entry" if blocked else platform
        key = f"{asset_key}:{size}"
        if key in self._platform_images:
            return self._platform_images[key]
        try:
            root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
            image = self.tk.PhotoImage(file=str(root / "assets" / "pics" / f"{asset_key}.png"))
            scale = max(1, (max(image.width(), image.height()) + size - 1) // size)
            image = image.subsample(scale, scale)
            self._platform_images[key] = image
            return image
        except Exception:
            self._platform_images[key] = None
            return None

    def _draw_platform_badge(self, x: int, y: int, platform: str, text: str | None = None, blocked: bool = False, size: int = 21) -> int:
        icon = PLATFORM_ICONS.get(platform, "•")
        image = self._platform_image(platform, blocked, size=size)
        if image:
            self.canvas.create_image(x + int((size + 1) / 2), y + 12, image=image, anchor="center")
        else:
            self.canvas.create_text(x + int((size + 1) / 2), y + 12, text=icon, fill="#ffffff", font=("Segoe UI", 12, "bold"))
        return size + 1

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        text = text.replace("\r", "").strip()
        if not text:
            return [""]
        lines: list[str] = []
        for raw in text.split("\n"):
            words = raw.split(" ")
            cur = ""
            for word in words:
                candidate = word if not cur else cur + " " + word
                if len(candidate) <= max_chars:
                    cur = candidate
                else:
                    if cur:
                        lines.append(cur)
                    while len(word) > max_chars:
                        lines.append(word[:max_chars])
                        word = word[max_chars:]
                    cur = word
            if cur:
                lines.append(cur)
        return lines[-3:] if len(lines) > 3 else lines

    def render(self) -> None:
        c = self.canvas
        bgc = self.bg_canvas
        c.delete("all")
        bgc.delete("all")
        style = self.layout.get("style") or {}
        bg = _safe_draw_color(style.get("background"))
        bg_stipple = None
        try:
            # Nur das Hintergrundfenster bekommt Alpha. Das Vorderfenster mit
            # Text/Symbolen bleibt voll deckend. Alpha nur setzen, wenn es sich aendert.
            alpha = _opacity_to_window_alpha(style.get("opacity", 82))
            if self._last_bg_alpha != alpha:
                self.root.attributes("-alpha", 1.0)
                self.bg_root.attributes("-alpha", alpha)
                self._last_bg_alpha = alpha
        except Exception:
            pass
        radius = int(style.get("radius", 16) or 16)
        font_family = str(style.get("fontFamily") or "Segoe UI")
        font_size = int(style.get("fontSize") or 16)
        text_color = str(style.get("textColor") or "#ffffff")

        # Im Editmode braucht das komplette Fenster eine nicht-transparente
        # Trefferflaeche, sonst klickt Windows durch transparente Pixel durch.
        # Sehr dunkler Hilfshintergrund, nur waehrend Bearbeitung sichtbar.
        if self.editing:
            c.create_rectangle(0, 0, self.root.winfo_width(), self.root.winfo_height(), fill="#020304", outline="")

        self._draw_viewer_bar(bg, bg_stipple, radius, font_family, text_color)
        self._draw_chat_panel(bg, bg_stipple, radius, font_family, font_size, text_color)

        if not self.last_chat_state and self.editing:
            c.create_text(18, 18, anchor="nw", text="Desktop-Overlay aktiv · F8 toggelt Editmode", fill="#b9c2e2", font=(font_family, 10))

        if self.editing:
            w, h = self.root.winfo_width(), self.root.winfo_height()
            c.create_text(
                12,
                h - 18,
                anchor="w",
                text="Elemente mit der Maus verschieben. Unten rechts skalieren. ESC beendet Bearbeitung.",
                fill="#b9c2e2",
                font=("Segoe UI", 10),
            )
            c.create_polygon(w, h - 34, w, h, w - 34, h, fill="#936cff", outline="")

        # Click-through nicht in jedem Render neu setzen; das verursacht bei transparenten
        # Fenstern sichtbar Flicker. Nur Moduswechsel erzwingen den Style neu.

    def _draw_viewer_bar(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, text_color: str) -> None:
        box = self.layout.get("viewerBar") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)
        px = x + 12
        py = y + max(8, int((h - 28) / 2))
        platforms = self.last_chat_state.get("platforms", []) if isinstance(self.last_chat_state, dict) else []
        if not platforms and self.editing:
            platforms = [{"platform":"twitch","viewer_count":"-"},{"platform":"tiktok","viewer_count":"-"},{"platform":"youtube","viewer_count":"-"},{"platform":"kick","viewer_count":"-"}]
        for item in platforms or []:
            platform = str(item.get("platform") or "")
            blocked = bool(item.get("blocked"))
            raw_count = item.get("viewer_count", "-")
            unavailable = blocked or raw_count is None or str(raw_count).strip().lower() in ("", "none", "null", "-")
            bw = self._draw_platform_badge(px, py, platform, size=27)
            if unavailable:
                status_icon = self._platform_image("no_entry", True, size=27)
                if status_icon:
                    self.canvas.create_image(px + bw + 20, py + 12, image=status_icon, anchor="center")
                else:
                    self.canvas.create_text(px + bw + 12, py + 12, text="⛔", fill="#ff4b60", font=(font_family, 10, "bold"), anchor="w")
            else:
                self.canvas.create_text(px + bw + 12, py + 12, text=str(raw_count), fill=text_color, font=(font_family, 10, "bold"), anchor="w")
            px += bw + 44
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")

    def _draw_chat_panel(self, bg: str, bg_stipple: str | None, radius: int, font_family: str, font_size: int, text_color: str) -> None:
        box = self.layout.get("chatPanel") or {}
        x, y, w, h = [int(box.get(k, 0)) for k in ("x", "y", "w", "h")]
        self._rounded_rect(x, y, w, h, radius, fill=bg, outline="", stipple=bg_stipple, canvas=self.bg_canvas)
        messages = [
            m for m in (self.last_chat_state.get("messages", []) or [])
            if m.get("message_type") in {"chat", "moderation_notice"}
        ][-40:]
        # Die Badge ist 24px hoch. Mit mindestens 34px pro Zeile bleibt sichtbar
        # Luft zwischen den farbigen Bereichen, auch bei kleiner Schrift.
        line_h = max(34, int(font_size * 1.8))
        rows: list[tuple[str, str, str, str]] = []
        text_font = self.tkfont.Font(family=font_family, size=font_size)
        name_font = self.tkfont.Font(family=font_family, size=font_size, weight="bold")
        for msg in messages:
            platform = str(msg.get("platform") or "")
            user = str(msg.get("user") or "?")
            text = _strip_html(msg.get("html")) or str(msg.get("text") or "")
            badge_w = 22
            first_line_width = max(80, w - 24 - badge_w - 8 - name_font.measure(user) - 10)
            char_width = max(7, int(font_size * 0.55))
            wrapped = self._wrap_text(text, max(8, int(first_line_width / char_width)))
            for i, line in enumerate(wrapped):
                rows.append((platform if i == 0 else "", user if i == 0 else "", line, platform))
        max_rows = max(1, int((h - 24) / line_h))
        rows = rows[-max_rows:]
        cy = y + h - 12 - len(rows) * line_h
        for platform, user, line, color_platform in rows:
            px = x + 12
            if platform:
                badge_y = cy + int((line_h - 24) / 2)
                bw = self._draw_platform_badge(px, badge_y, platform)
                px += bw + 8
                self.canvas.create_text(px, cy + line_h / 2, text=user, fill=_user_color(platform, user), font=name_font, anchor="w")
                # Tk misst die echte Glyphenbreite (statt einer Schaetzung nach
                # Zeichenanzahl). Dadurch beginnt die Nachricht stets hinter dem Namen.
                px += name_font.measure(user) + 10
            else:
                px = x + 92
            self.canvas.create_text(px, cy + line_h / 2, text=line, fill=text_color, font=text_font, anchor="w")
            cy += line_h
        if self.editing:
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#936cff", dash=(4, 3))
            self.canvas.create_polygon(x + w, y + h - 24, x + w, y + h, x + w - 24, y + h, fill="#936cff")


def run_desktop_chat(url: str) -> int:
    if os.name != "nt":
        _message_box("Das Desktop-Overlay ist aktuell nur fuer Windows gebaut.")
        return 1
    try:
        overlay = DesktopTkOverlay(url)
        return overlay.run()
    except Exception as exc:
        try:
            log_dir = Path(sys.executable).resolve().parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            import traceback
            (log_dir / "desktop_chat_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        _message_box(f"Desktopfenster konnte nicht gestartet werden:\n\n{exc}", WINDOW_TITLE)
        return 1
