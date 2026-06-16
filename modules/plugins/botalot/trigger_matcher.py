from __future__ import annotations

import difflib
import re
from pathlib import Path

from common import WORD_RE, as_bool, collapse_repeats, norm

_URSULA_RE_LIST = [
    re.compile(r"u+r+s+u+h*l+a+", re.IGNORECASE),
    re.compile(r"u+h*r+s+u+l+a+", re.IGNORECASE),
    re.compile(r"u+r+s+e+l+a+", re.IGNORECASE),
    re.compile(r"u+r+s+l+a+", re.IGNORECASE),
    re.compile(r"u+r+s+u+l+l+a+", re.IGNORECASE),
    re.compile(r"s+u+l+a+", re.IGNORECASE),
]


class TriggerMatcher:
    def __init__(self, trigger_file: Path) -> None:
        self.trigger_file = trigger_file
        self.words: set[str] = set()
        self.reload()

    def reload(self) -> int:
        self.trigger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.trigger_file.exists():
            self.trigger_file.write_text("ursula\nursu\nursul\nursla\nursela\nursuhla\nursulla\nsula\n", encoding="utf-8")
        words: set[str] = {"ursula", "ursla", "ursela", "ursuhla", "ursul", "ursu", "sula", "rsula"}
        try:
            for line in self.trigger_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                word = norm(line)
                if len(word) >= 4:
                    words.add(word)
                    words.add(collapse_repeats(word))
        except Exception:
            pass
        self.words = words
        return len(words)

    def match(self, settings: dict, text: str) -> tuple[bool, str]:
        n = norm(text)
        c = collapse_repeats(n)
        if as_bool(settings.get("trigger_botis3mpty"), True):
            hit_bot = "botis3mpty" in n or "botisempty" in n or "botis3mpty" in c or "botisempty" in c
            if hit_bot:
                if as_bool(settings.get("only_answer_questions_for_botis3mpty"), False) and "?" not in text:
                    return False, ""
                return True, "botis3mpty"
        if as_bool(settings.get("trigger_at_bot"), True) and re.search(r"(?<![\w@])@(bot|botis3mpty)(?![\w])", text or "", re.IGNORECASE):
            return True, "@bot/@botis3mpty"
        if as_bool(settings.get("trigger_ursula"), True) and self._looks_like_ursula(text, n, c):
            return True, "ursula"
        return False, ""

    def _looks_like_ursula(self, text: str, normalized: str, collapsed: str) -> bool:
        if len(normalized) < 4:
            return False
        if any(rx.search(normalized) or rx.search(collapsed) for rx in _URSULA_RE_LIST):
            return True
        words = [norm(w) for w in WORD_RE.findall(text)]
        for word in words:
            if len(word) < 4:
                continue
            compact = collapse_repeats(word)
            if word in self.words or compact in self.words:
                return True
            if len(compact) >= 5 and difflib.SequenceMatcher(None, compact, "ursula").ratio() >= 0.76:
                return True
        return False
