from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any

PLATFORMS = ("twitch", "tiktok", "youtube", "kick")
PLATFORM_LABELS = {
    "twitch": "Twitch",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "kick": "Kick",
}
EVENT_LABELS = {
    "chat": "Chat",
    "follow": "Follow",
    "join": "Join",
    "like": "Like",
    "gift": "Gift",
    "share": "Share",
    "subscribe": "Sub",
    "raid": "Raid",
    "donation": "Donation",
    "bits": "Bits",
    "member": "Member",
    "superchat": "Superchat",
    "supersticker": "Supersticker",
    "live_status": "Live-Status",
}


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ja", "on", "enabled", "aktiv"}:
        return True
    if text in {"0", "false", "no", "nein", "off", "disabled", "aus"}:
        return False
    return default


def to_int(value: Any, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        out = int(float(str(value).strip()))
    except Exception:
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def clean_name(value: Any) -> str:
    return str(value or "").strip().lstrip("@#").strip()


def split_names(value: Any) -> set[str]:
    names: set[str] = set()
    for raw in re.split(r"[\n,;]+", str(value or "")):
        name = clean_name(raw).lower()
        if name:
            names.add(name)
    return names


def render_template(template: Any, data: dict[str, Any]) -> str:
    text = str(template or "")
    for key, value in data.items():
        text = text.replace("{" + str(key) + "}", str(value if value is not None else ""))
    return clean_text(text)


def alert_html(title: str, line: str, *, platform: str, color: str = "#ff2d55") -> str:
    title_e = html.escape(title or "Alert")
    line_e = html.escape(line or "")
    platform_e = html.escape(PLATFORM_LABELS.get(platform, platform.title()))
    color_e = html.escape(color or "#ff2d55")
    return (
        f'<div class="al3rtalot-alert" style="--accent:{color_e}">'
        f'<div class="al3rtalot-badge">{platform_e}</div>'
        f'<div class="al3rtalot-title">{title_e}</div>'
        f'<div class="al3rtalot-line">{line_e}</div>'
        f'</div>'
    )


def main_data_dir(plugin_name: str, file_path: str) -> Path:
    current = Path(file_path).resolve()
    for parent in current.parents:
        if parent.name.lower() == "modules":
            return parent.parent / "data" / plugin_name
    return current.parent / "data"


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def now_ms() -> int:
    return int(time.time() * 1000)
