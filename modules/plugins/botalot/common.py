
from __future__ import annotations

import re
from typing import Any

SPACE_RE = re.compile(r'\s+')
WORD_RE = re.compile(r'[a-z0-9äöüß]+', re.IGNORECASE)


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {'0', 'false', 'no', 'off', ''}
    return bool(value)


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


def to_float(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        out = float(str(value).strip())
    except Exception:
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def clean_text(value: Any) -> str:
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    return SPACE_RE.sub(' ', text).strip()


def norm(value: Any) -> str:
    text = clean_text(value).lower()
    repl = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', '4': 'a', '5': 's', '0': 'o', '1': 'l', '3': 'e', '$': 's'}
    for a, b in repl.items():
        text = text.replace(a, b)
    return ''.join(ch for ch in text if ch.isalnum())


def collapse_repeats(value: str) -> str:
    out=[]; last=''
    for ch in value:
        if ch != last:
            out.append(ch); last=ch
    return ''.join(out)


def strip_response(text: str, max_chars: int) -> str:
    text = clean_text(text).strip('"').strip("'").strip().replace('`', '')
    text = SPACE_RE.sub(' ', text).strip()
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip(' ,.;:-') + '…'
    return text
