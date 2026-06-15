from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any


class KickWriter:
    KICK_CHAT_URL = 'https://api.kick.com/public/v1/chat'

    def __init__(self, host_getter, logger) -> None:
        self._host_getter = host_getter
        self._log = logger
        self._send_lock = threading.Lock()

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = str(value or '').replace('\r', ' ').replace('\n', ' ')
        return ' '.join(text.split()).strip()

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {'1', 'true', 'yes', 'ja', 'on', 'enabled'}:
            return True
        if text in {'0', 'false', 'no', 'nein', 'off', 'disabled'}:
            return False
        return default

    @staticmethod
    def _result_ok(value: Any) -> bool:
        if isinstance(value, tuple):
            return bool(value[0]) if value else False
        if isinstance(value, dict):
            if 'ok' in value:
                return bool(value.get('ok'))
            if 'success' in value:
                return bool(value.get('success'))
        if value is None:
            return True
        return bool(value)

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or '').strip()
            if text:
                return text
        return ''

    def _host(self) -> Any:
        try:
            return self._host_getter() if callable(self._host_getter) else None
        except Exception:
            return None

    def _host_platform_settings(self) -> dict[str, Any]:
        host = self._host()
        if host is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn('kick')
                except TypeError:
                    try:
                        all_data = fn()
                        data = all_data.get('kick', {}) if isinstance(all_data, dict) else {}
                    except Exception:
                        data = {}
                except Exception:
                    data = {}
                if isinstance(data, dict):
                    return dict(data)
        return {}

    def _host_plugin(self, *plugin_ids: str) -> Any:
        host = self._host()
        if host is None:
            return None
        for plugin_id in plugin_ids:
            try:
                getter = getattr(host, 'get_plugin', None)
                plugin = getter(plugin_id) if callable(getter) else None
            except Exception:
                plugin = None
            if plugin is None:
                try:
                    plugins = getattr(host, 'plugins', {})
                    plugin = plugins.get(plugin_id) if isinstance(plugins, dict) else None
                except Exception:
                    plugin = None
            if plugin is not None:
                return plugin
        return None

    def _send_via_host(self, msg: str) -> bool:
        host = self._host()
        if host is None:
            return False
        fn = getattr(host, 'send_platform_message', None)
        if not callable(fn):
            return False
        attempts = (
            lambda: fn('kick', msg, use_bot=True, sender='botalot'),
            lambda: fn(platform='kick', message=msg, use_bot=True, sender='botalot'),
            lambda: fn('kick_chat', msg, use_bot=True, sender='botalot'),
            lambda: fn('kick', msg),
        )
        last_exc: Exception | None = None
        for attempt in attempts:
            try:
                result = attempt()
                if self._result_ok(result):
                    return True
                last_exc = RuntimeError(f'host returned {result!r}')
                continue
            except TypeError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                self._log(f'Kick senden über Haupttool fehlgeschlagen: {exc}')
                return False
        if last_exc is not None:
            self._log(f'Kick senden über Haupttool nicht erfolgreich: {last_exc}')
        return False

    def _send_via_kick_chat_plugin(self, msg: str) -> bool:
        plugin = self._host_plugin('kick_chat')
        if plugin is None:
            return False
        host = self._host()
        for name in ('send_message', 'send_chat_message', 'send', 'write_message'):
            fn = getattr(plugin, name, None)
            if callable(fn):
                attempts = (
                    lambda: fn(msg, None, host),
                    lambda: fn(msg, host=host),
                    lambda: fn(msg),
                    lambda: fn(message=msg),
                    lambda: fn('kick', msg),
                )
                for attempt in attempts:
                    try:
                        result = attempt()
                        if self._result_ok(result):
                            return True
                        self._log(f'Kick senden über kick_chat.{name} nicht erfolgreich: {result!r}')
                        continue
                    except TypeError:
                        continue
                    except Exception as exc:
                        self._log(f'Kick senden über kick_chat.{name} fehlgeschlagen: {exc}')
                        return False
        return False

    def _direct_send_with_host_token(self, settings: dict[str, Any] | None, msg: str) -> bool:
        platform = self._host_platform_settings()
        local = settings if isinstance(settings, dict) else {}
        token = self._first_text(
            platform.get('access_token'), platform.get('bot_access_token'),
            local.get('kick_access_token'), local.get('access_token'), local.get('bot_access_token'),
        )
        if not token:
            return False
        broadcaster_id = self._first_text(
            platform.get('broadcaster_user_id'), platform.get('channel_id'), platform.get('main_user_id'),
            local.get('kick_broadcaster_user_id'), local.get('kick_channel_id'), local.get('broadcaster_user_id'), local.get('channel_id'),
        )
        content = msg[:500]
        payloads: list[tuple[str, dict[str, Any]]] = []
        if str(broadcaster_id).strip().isdigit():
            bid = int(str(broadcaster_id).strip())
            payloads.append(('user-with-broadcaster', {'content': content, 'type': 'user', 'broadcaster_user_id': bid}))
            payloads.append(('bot-with-broadcaster', {'content': content, 'type': 'bot', 'broadcaster_user_id': bid}))
            payloads.append(('minimal-with-broadcaster', {'content': content, 'broadcaster_user_id': bid}))
        else:
            payloads.append(('user-minimal', {'content': content, 'type': 'user'}))
            payloads.append(('bot-minimal', {'content': content, 'type': 'bot'}))

        errors: list[str] = []
        for variant, payload in payloads:
            try:
                req = urllib.request.Request(
                    self.KICK_CHAT_URL,
                    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                    headers={
                        'Accept': 'application/json',
                        'Authorization': f'Bearer {token.strip()}',
                        'Content-Type': 'application/json',
                    },
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
                self._log(f'Kick Direkt-Senden OK: {variant}')
                return True
            except urllib.error.HTTPError as exc:
                detail = ''
                try:
                    detail = exc.read().decode('utf-8', errors='replace')[:300]
                except Exception:
                    detail = str(exc)
                errors.append(f'{variant}: HTTP {exc.code} {detail}')
            except Exception as exc:
                errors.append(f'{variant}: {exc}')
        self._log('Kick Direkt-Senden fehlgeschlagen: ' + ' | '.join(errors)[:900])
        return False

    def send(self, settings: dict[str, Any] | None, message: str) -> bool:
        msg = self._clean_text(message)
        if not msg:
            self._log('Kick Nachricht leer, nicht gesendet.')
            return False

        platform = self._host_platform_settings()
        # Bei Kick gehört OAuth dem Haupttool. In alten botalot-Settings steht
        # write_kick oft noch auf False, obwohl Main+Bot schon verbunden sind.
        # Deshalb blocken wir hier nicht mehr lokal, sondern versuchen zuerst
        # die echte Haupttool-/kick_chat-Sendebrücke.
        with self._send_lock:
            if self._send_via_host(msg):
                return True
            if self._send_via_kick_chat_plugin(msg):
                return True
            if self._direct_send_with_host_token(settings, msg):
                return True

        self._log('Kick senden fehlgeschlagen: Haupttool, kick_chat und Direkt-Fallback konnten nicht senden.')
        return False
