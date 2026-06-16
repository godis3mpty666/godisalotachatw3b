from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock


class ContextMemory:
    def __init__(self, maxlen: int = 10) -> None:
        self._lock = RLock()
        self._maxlen = max(1, int(maxlen or 10))
        self._by_user: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=self._maxlen))

    def _key(self, platform: str, username: str) -> str:
        return f"{str(platform or '').strip().lower()}::{str(username or '').strip().lstrip('@').lower()}"

    def resize(self, maxlen: int) -> None:
        maxlen = max(1, int(maxlen or 10))
        with self._lock:
            self._maxlen = maxlen
            rebuilt: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=maxlen))
            for key, items in self._by_user.items():
                rebuilt[key] = deque(list(items)[-maxlen:], maxlen=maxlen)
            self._by_user = rebuilt

    def add(self, platform: str, username: str, text: str) -> None:
        with self._lock:
            self._by_user[self._key(platform, username)].append({
                "platform": str(platform or ""),
                "username": str(username or ""),
                "text": str(text or ""),
            })

    def format_recent_for_user(self, platform: str, username: str, count: int) -> str:
        with self._lock:
            items = list(self._by_user.get(self._key(platform, username), []))[-max(1, int(count or 1)):]
        return "\n".join(f"[{m['platform']}] {m['username']}: {m['text']}" for m in items)
