from __future__ import annotations
from collections import defaultdict, deque
from threading import RLock

class ContextMemory:
    """Small in-memory chat context.

    botalot reads every platform, but AI context must stay per chatter so one
    user's Ursula running gag can not leak into another user's normal question.
    """

    def __init__(self, maxlen: int = 10) -> None:
        self._lock = RLock()
        self._maxlen = max(1, int(maxlen or 10))
        self._global: deque[dict[str, str]] = deque(maxlen=self._maxlen)
        self._by_user: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=self._maxlen))

    def _key(self, platform: str, username: str) -> str:
        return f'{str(platform or "").strip().lower()}::{str(username or "").strip().lstrip("@").lower()}'

    def resize(self, maxlen: int) -> None:
        maxlen = max(1, int(maxlen or 10))
        with self._lock:
            self._maxlen = maxlen
            self._global = deque(list(self._global)[-maxlen:], maxlen=maxlen)
            rebuilt: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=maxlen))
            for key, items in self._by_user.items():
                rebuilt[key] = deque(list(items)[-maxlen:], maxlen=maxlen)
            self._by_user = rebuilt

    def add(self, platform: str, username: str, text: str) -> None:
        item = {'platform': str(platform or ''), 'username': str(username or ''), 'text': str(text or '')}
        with self._lock:
            self._global.append(item)
            self._by_user[self._key(platform, username)].append(item)

    def recent(self, count: int) -> list[dict[str, str]]:
        with self._lock:
            return list(self._global)[-count:]

    def recent_for_user(self, platform: str, username: str, count: int) -> list[dict[str, str]]:
        with self._lock:
            return list(self._by_user.get(self._key(platform, username), []))[-count:]

    def format_recent(self, count: int) -> str:
        return self._format(self.recent(count))

    def format_recent_for_user(self, platform: str, username: str, count: int) -> str:
        return self._format(self.recent_for_user(platform, username, count))

    def _format(self, items: list[dict[str, str]]) -> str:
        return '\n'.join(f'[{m["platform"]}] {m["username"]}: {m["text"]}' for m in items)
