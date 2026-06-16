from __future__ import annotations

import re
from typing import Any

SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z0-9äöüß]+", re.IGNORECASE)


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ja", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "nein", "off", "disabled", ""}:
        return False
    return default


def to_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        out = int(float(str(value).strip()))
    except Exception:
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def norm(value: Any) -> str:
    text = clean_text(value).lower()
    for src, dst in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "4": "a", "5": "s", "0": "o", "1": "l", "3": "e", "$": "s"}.items():
        text = text.replace(src, dst)
    return "".join(ch for ch in text if ch.isalnum())


def collapse_repeats(value: str) -> str:
    out: list[str] = []
    last = ""
    for ch in value:
        if ch != last:
            out.append(ch)
            last = ch
    return "".join(out)


def strip_response(text: str, max_chars: int) -> str:
    text = clean_text(text).strip('"').strip("'").strip().replace("`", "")
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip(" ,.;:-") + "..."
    return text
