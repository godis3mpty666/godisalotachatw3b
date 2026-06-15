from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TOKEN_URL = 'https://oauth2.googleapis.com/token'
CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'
LIVE_BROADCASTS_URL = 'https://www.googleapis.com/youtube/v3/liveBroadcasts'
LIVE_CHAT_MESSAGES_URL = 'https://www.googleapis.com/youtube/v3/liveChat/messages'


class YouTubeWriter:
    def __init__(self, host_getter, logger) -> None:
        self._host_getter = host_getter
        self._log = logger
        self._send_lock = threading.Lock()
        self._live_chat_id = ''
        self._runtime_tokens: dict[str, str] = {}

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
    def _clean_text(value: Any) -> str:
        text = str(value or '').replace('\r', ' ').replace('\n', ' ')
        return ' '.join(text.split()).strip()

    def _host_platform_settings(self) -> dict[str, Any]:
        host = self._host_getter() if callable(self._host_getter) else None
        if host is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn('youtube')
                except TypeError:
                    try:
                        all_data = fn()
                        data = all_data.get('youtube', {}) if isinstance(all_data, dict) else {}
                    except Exception:
                        data = {}
                except Exception:
                    data = {}
                if isinstance(data, dict):
                    return dict(data)
        return {}

    def _settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        out = dict(settings or {})
        platform = self._host_platform_settings()
        if platform:
            out['youtube_read_enabled'] = self._as_bool(platform.get('read_enabled'), self._as_bool(platform.get('read'), True))
            out['youtube_write_enabled'] = self._as_bool(platform.get('write_enabled'), self._as_bool(platform.get('write'), True))
            for key in (
                'client_id', 'client_secret', 'access_token', 'refresh_token',
                'main_access_token', 'main_refresh_token', 'live_chat_id', 'main_account', 'bot_account'
            ):
                value = platform.get(key)
                if value not in (None, ''):
                    out[f'youtube_{key}'] = str(value).strip()
        return out

    def _token_for(self, settings: dict[str, Any], kind: str) -> str:
        if kind == 'main':
            return self._runtime_tokens.get('main_access_token') or str(settings.get('youtube_main_access_token') or settings.get('youtube_access_token') or '').strip()
        return self._runtime_tokens.get('access_token') or str(settings.get('youtube_access_token') or '').strip()

    def _refresh_token(self, settings: dict[str, Any], kind: str) -> str:
        client_id = str(settings.get('youtube_client_id') or '').strip()
        client_secret = str(settings.get('youtube_client_secret') or '').strip()
        refresh_key = 'youtube_main_refresh_token' if kind == 'main' else 'youtube_refresh_token'
        access_key = 'main_access_token' if kind == 'main' else 'access_token'
        refresh_token = str(settings.get(refresh_key) or '').strip()
        if not client_id or not refresh_token:
            return ''
        data = {'client_id': client_id, 'refresh_token': refresh_token, 'grant_type': 'refresh_token'}
        if client_secret:
            data['client_secret'] = client_secret
        payload = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(TOKEN_URL, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            token = str((json.loads(raw or '{}') or {}).get('access_token') or '').strip()
            if token:
                self._runtime_tokens[access_key] = token
                return token
        except Exception as exc:
            self._log(f'YouTube Token-Refresh fehlgeschlagen: {exc}')
        return ''

    def _request_json(self, url: str, *, token: str, method: str = 'GET', params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
        final_url = url
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
            final_url = final_url + ('&' if '?' in final_url else '?') + query
        payload = None
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(final_url, data=payload, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        return json.loads(raw or '{}')

    def _request_json_auth(self, settings: dict[str, Any], kind: str, url: str, *, method: str = 'GET', params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._token_for(settings, kind) or self._refresh_token(settings, kind)
        if not token:
            raise RuntimeError(f'Missing YouTube {kind} OAuth token from main tool.')
        try:
            return self._request_json(url, token=token, method=method, params=params, body=body)
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, 'code', 0) or 0) == 401:
                token = self._refresh_token(settings, kind)
                if token:
                    return self._request_json(url, token=token, method=method, params=params, body=body)
            raise

    def _resolve_live_chat_id(self, settings: dict[str, Any], *, force: bool = False) -> str:
        if self._live_chat_id and not force:
            return self._live_chat_id
        override = str(settings.get('youtube_live_chat_id') or '').strip()
        if override:
            self._live_chat_id = override
            return override
        data = self._request_json_auth(settings, 'main', LIVE_BROADCASTS_URL, params={
            'part': 'snippet,contentDetails,status',
            'broadcastStatus': 'active',
            'broadcastType': 'all',
            'mine': 'true',
            'maxResults': 5,
        })
        rows = data.get('items') if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise RuntimeError('Kein aktiver YouTube-Livestream beim Mainaccount gefunden.')
        for row in rows:
            snippet = row.get('snippet') if isinstance(row, dict) else {}
            chat_id = str((snippet or {}).get('liveChatId') or '').strip()
            if chat_id:
                self._live_chat_id = chat_id
                return chat_id
        raise RuntimeError('YouTube-Livestream gefunden, aber keine LiveChatId verfügbar.')


    def _host_send_via_plugin(self, message: str) -> tuple[bool, str]:
        """Prefer the running youtube_chat plugin/main-tool send path.

        The reader plugin already knows the currently active stream. The old
        botalot writer did a second liveChat lookup and often failed with 403 or
        stale ids while youtube_chat was reading fine. Keep this first so bridge
        output uses the same central host path as Kick.
        """
        host = self._host_getter() if callable(self._host_getter) else None
        if host is None:
            return False, 'host missing'
        fn = getattr(host, 'send_platform_message', None)
        if not callable(fn):
            return False, 'host.send_platform_message missing'
        try:
            ok = bool(fn('youtube', message, use_bot=True, sender='botalot'))
            return ok, 'host.send_platform_message("youtube") returned ' + str(ok)
        except TypeError:
            try:
                ok = bool(fn('youtube', message))
                return ok, 'host.send_platform_message("youtube") returned ' + str(ok)
            except Exception as exc:
                return False, str(exc)
        except Exception as exc:
            return False, str(exc)

    def has_send_access(self, settings: dict[str, Any] | None = None) -> bool:
        final = self._settings(settings)
        if self._as_bool(final.get('youtube_write_enabled'), False):
            return True
        if str(final.get('youtube_access_token') or '').strip() or str(final.get('youtube_refresh_token') or '').strip():
            return True
        host = self._host_getter() if callable(self._host_getter) else None
        if host is not None:
            try:
                plugin = host.get_plugin('youtube_chat') if hasattr(host, 'get_plugin') else None
                if plugin is not None and hasattr(plugin, 'send_message'):
                    return True
            except Exception:
                pass
        return False

    def check_auth(self, settings: dict[str, Any] | None = None) -> tuple[bool, str]:
        final = self._settings(settings)
        try:
            main = self._request_json_auth(final, 'main', CHANNELS_URL, params={'part': 'snippet', 'mine': 'true', 'maxResults': 1})
            bot = self._request_json_auth(final, 'bot', CHANNELS_URL, params={'part': 'snippet', 'mine': 'true', 'maxResults': 1})
            main_title = (((main.get('items') or [{}])[0].get('snippet') or {}).get('title') if isinstance(main, dict) else '') or 'Main'
            bot_title = (((bot.get('items') or [{}])[0].get('snippet') or {}).get('title') if isinstance(bot, dict) else '') or 'Bot'
            chat_id = self._resolve_live_chat_id(final, force=True)
            return True, f'YouTube OK: Main={main_title}, Bot={bot_title}, Chat={chat_id[:10]}...'
        except Exception as exc:
            return False, f'YouTube Prüfung fehlgeschlagen: {exc}'

    def send(self, settings: dict[str, Any] | None, message: str) -> bool:
        msg = self._clean_text(message)
        if not msg:
            self._log('YouTube Nachricht leer, nicht gesendet.')
            return False

        # First use the central host/youtube_chat path. This keeps botalot from
        # doing its own stale liveChat lookup. It also matches the Kick design.
        host_ok, host_msg = self._host_send_via_plugin(msg)
        if host_ok:
            return True
        self._log(f'YouTube Host-Senden nicht erfolgreich: {host_msg}')

        final = self._settings(settings)
        if not self.has_send_access(final):
            self._log('YouTube schreiben ist im Haupttool deaktiviert oder kein Bot-OAuth vorhanden.')
            return False
        try:
            with self._send_lock:
                chat_id = self._resolve_live_chat_id(final)
                body = {
                    'snippet': {
                        'liveChatId': chat_id,
                        'type': 'textMessageEvent',
                        'textMessageDetails': {'messageText': msg},
                    }
                }
                self._request_json_auth(final, 'bot', LIVE_CHAT_MESSAGES_URL, method='POST', params={'part': 'snippet'}, body=body)
            return True
        except Exception as exc:
            self._log(f'YouTube Direkt-Fallback fehlgeschlagen: {exc}')
            return False
