
from __future__ import annotations
import difflib
import re
from pathlib import Path
from common import as_bool, collapse_repeats, norm, WORD_RE

_URSULA_RE_LIST = [
    re.compile(r'u+r+s+u+h*l+a+', re.IGNORECASE),
    re.compile(r'u+h*r+s+u+l+a+', re.IGNORECASE),
    re.compile(r'u+r+s+e+l+a+', re.IGNORECASE),
    re.compile(r'u+r+s+l+a+', re.IGNORECASE),
    re.compile(r'u+r+s+u+l+l+a+', re.IGNORECASE),
    re.compile(r's+u+l+a+', re.IGNORECASE),
]

class TriggerMatcher:
    def __init__(self, trigger_file: Path) -> None:
        self.trigger_file = trigger_file
        self.words: set[str] = set()
        self.reload()

    def reload(self) -> int:
        self.trigger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.trigger_file.exists():
            self.trigger_file.write_text('ursula\nursu\nursul\nursla\nursela\nursuhla\nursulla\nsula\n', encoding='utf-8')
        words: set[str] = set()
        try:
            for line in self.trigger_file.read_text(encoding='utf-8', errors='ignore').splitlines():
                w = norm(line)
                if len(w) >= 4:
                    words.add(w)
                    words.add(collapse_repeats(w))
        except Exception:
            pass
        words.update({'ursula', 'ursla', 'ursela', 'ursuhla', 'ursul', 'ursu', 'sula', 'rsula'})
        self.words = words
        return len(words)

    def match(self, settings: dict, text: str) -> tuple[bool, str]:
        n = norm(text)
        c = collapse_repeats(n)
        if as_bool(settings.get('trigger_botis3mpty'), True):
            hit_bot = 'botis3mpty' in n or 'botisempty' in n or 'botis3mpty' in c or 'botisempty' in c
            if hit_bot:
                if as_bool(settings.get('only_answer_questions_for_botis3mpty'), False) and '?' not in text:
                    return False, ''
                return True, 'botis3mpty'
        if as_bool(settings.get('trigger_at_bot'), True) and self._mentions_bot(text):
            return True, '@bot/@botis3mpty'
        if as_bool(settings.get('trigger_ursula'), True) and self._looks_like_ursula(text, n, c):
            return True, 'ursula'
        return False, ''


    def _mentions_bot(self, text: str) -> bool:
        # Match @bot or @botis3mpty as real mentions/prefixes, not inside another word like @botaccount or robot.
        # Examples: '@bot wie ist das Wetter?', '@Bot, hallo', 'ey @bot?', '@botis3mpty, test'
        return re.search(r'(?<![\w@])@(bot|botis3mpty)(?![\w])', text or '', re.IGNORECASE) is not None

    def _looks_like_ursula(self, text: str, n: str, c: str) -> bool:
        if len(n) < 4:
            return False
        for rx in _URSULA_RE_LIST:
            if rx.search(n) or rx.search(c):
                return True
        if 'sula' in n or 'sula' in c:
            return True
        words = [norm(w) for w in WORD_RE.findall(text)]
        for w in words:
            if len(w) < 4:
                continue
            wc = collapse_repeats(w)
            if w in self.words or wc in self.words:
                return True
            if len(wc) >= 5 and difflib.SequenceMatcher(None, wc, 'ursula').ratio() >= 0.76:
                return True
        return False
