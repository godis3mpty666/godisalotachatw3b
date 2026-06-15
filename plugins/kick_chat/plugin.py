from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
import urllib.parse
from html import escape as _html_escape
from pathlib import Path
from typing import Any

import requests

from godisalotachat.models import PluginStatus
from godisalotachat.plugin_base import PluginHost
from plugins.plugin_common import ThreadedPlugin

try:
    import websocket  # websocket-client
except Exception:  # pragma: no cover
    websocket = None

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


class KickChatPlugin(ThreadedPlugin):
    plugin_id = 'kick_chat'
    display_name = 'Kick Chat'
    version = '2.1.3'
    description = 'Kick chat reader/writer. OAuth and tokens are provided only by godisalotachat.'

    DEFAULT_WS_URL = 'wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false'
    KICK_API_BASE = 'https://api.kick.com/public/v1'
    KICK_CHAT_URL = 'https://api.kick.com/public/v1/chat'
    KICK_EMOTE_TOKEN_RE = re.compile(r'\[emote:(?P<id>\d+):(?P<name>[^\]]+)\]')

    def __init__(self):
        super().__init__()
        self._diag_text = ''
        self._last_viewer_count: int | None = None
        self._last_followers_count: int | None = None
        self._last_viewer_emit_monotonic = 0.0
        self._current_viewer_count: int | None = None
        self._current_followers_count: int | None = None
        self._is_live: bool | None = None
        self._diag_last_line = ''
        self._diag_repeat_count = 0
        self._host: PluginHost | None = None

    # Wichtig: Keine OAuth-/Token-/Client-Felder mehr im Plugin-Dialog.
    # Das Maintool verwaltet Kick Main/Bot OAuth zentral und spiegelt nur die nötigen Werte.
    def settings_schema(self):
        return [
            {'key': 'channel', 'label': 'Kick Channel', 'placeholder': 'godis3mpty'},
            {'key': 'diag_log', 'label': 'Diagnosis Log', 'type': 'multiline', 'placeholder': ''},
            {'key': 'diag_path', 'label': 'Diagnosis file path', 'placeholder': ''},
        ]

    def default_settings(self):
        return {
            'channel': '',
            'diag_log': self._read_diag() or 'No diagnosis yet. Press Test or Connect once.',
            'diag_path': str(self._diag_path()),
            'autoconnect': False,
        }

    def _data_dir(self) -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if parent.name.lower() == 'plugins':
                return parent.parent / 'data' / self.plugin_id
        return current.parent / 'data'

    def _diag_path(self) -> Path:
        return self._data_dir() / 'kick_chat_last_diag.txt'

    def _read_diag(self) -> str:
        if self._diag_text:
            return self._diag_text
        try:
            return self._diag_path().read_text(encoding='utf-8').strip()
        except Exception:
            return ''

    def _set_diag(self, text: str):
        self._diag_text = (text or '').strip()
        try:
            self._diag_path().write_text(self._diag_text, encoding='utf-8')
        except Exception:
            pass

    def _append_diag(self, text: str):
        line = (text or '').strip()
        if not line:
            return

        base = self._read_diag()
        if line == self._diag_last_line:
            self._diag_repeat_count += 1
            if self._diag_repeat_count not in (2, 5, 10) and (self._diag_repeat_count % 25) != 0:
                return
            line = f'{line} [x{self._diag_repeat_count}]'
        else:
            self._diag_last_line = line
            self._diag_repeat_count = 1

        merged = f'{base}\n{line}'.strip() if base else line
        lines = merged.splitlines()
        self._set_diag('\n'.join(lines[-160:])[-18000:])

    def _host_platform_settings(self, host: PluginHost | None = None) -> dict[str, Any]:
        host = host or self._host
        if host is None:
            return {}
        for name in ('get_platform_settings', 'platform_settings'):
            fn = getattr(host, name, None)
            if not callable(fn):
                continue
            try:
                data = fn('kick')
                if isinstance(data, dict):
                    return dict(data)
            except Exception:
                pass
        return {}

    def _effective_settings(self, settings: dict[str, Any] | None, host: PluginHost | None = None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self._host_platform_settings(host))
        if isinstance(settings, dict):
            # Plugin-local values win only when filled. Empty plugin settings must not erase host OAuth values.
            for key, value in settings.items():
                if value not in (None, ''):
                    merged[key] = value
        return merged

    def _clean_login(self, value: Any) -> str:
        return str(value or '').strip().lstrip('@#').strip().lower()

    def _clean_token(self, value: Any) -> str:
        token = str(value or '').strip()
        if token.lower().startswith('bearer '):
            token = token[7:]
        return token.strip()

    def _channel_from_settings(self, settings: dict[str, Any]) -> str:
        return self._clean_login(
            settings.get('channel')
            or settings.get('main_account')
            or settings.get('channel_slug')
            or settings.get('main_username')
        )

    def _browser_headers(self, channel: str = '') -> dict[str, str]:
        referer_channel = self._clean_login(channel) or 'kick'
        return {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/133.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': f'https://kick.com/{referer_channel}',
            'Origin': 'https://kick.com',
        }

    def _api_headers(self, settings: dict[str, Any], *, prefer_main: bool = True) -> dict[str, str] | None:
        token = ''
        if prefer_main:
            token = self._clean_token(settings.get('main_access_token'))
        if not token:
            token = self._clean_token(settings.get('access_token'))
        if not token:
            return None
        return {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}',
        }

    def _safe_json(self, resp: requests.Response):
        try:
            return resp.json()
        except Exception:
            return None

    def _parse_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            if isinstance(value, bool):
                return int(value)
            s = str(value).strip().replace(',', '')
            if not s:
                return None
            if '.' in s:
                return int(float(s))
            return int(s)
        except Exception:
            return None

    def _to_bool(self, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ('1', 'true', 'yes', 'on', 'live'):
            return True
        if s in ('0', 'false', 'no', 'off', 'offline'):
            return False
        return None

    def _search_value(self, obj: Any, keys: tuple[str, ...]) -> Any:
        if isinstance(obj, dict):
            for key in keys:
                if key in obj and obj[key] not in (None, ''):
                    return obj[key]
            for value in obj.values():
                found = self._search_value(value, keys)
                if found not in (None, ''):
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._search_value(item, keys)
                if found not in (None, ''):
                    return found
        return None

    def _extract_first_json_blob(self, html: str) -> dict[str, Any] | None:
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;</script>',
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if not match:
                continue
            with contextlib.suppress(Exception):
                data = json.loads(match.group(1))
                if isinstance(data, dict):
                    return data
        return None

    def _extract_channel_data_from_any(self, obj: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if not isinstance(obj, (dict, list)):
            return data

        # Known legacy channel shape: {id, user_id, slug, chatroom:{id}, livestream:{viewer_count,...}}
        if isinstance(obj, dict):
            if obj.get('chatroom') and isinstance(obj.get('chatroom'), dict):
                data['chatroom_id'] = obj['chatroom'].get('id')
            if obj.get('livestream') and isinstance(obj.get('livestream'), dict):
                stream = obj['livestream']
                data['viewer_count'] = stream.get('viewer_count') or stream.get('viewers')
                data['is_live'] = True
            elif 'livestream' in obj:
                data['is_live'] = False
            for src_key, dst_key in (
                ('broadcaster_user_id', 'broadcaster_user_id'),
                ('user_id', 'broadcaster_user_id'),
                ('channel_id', 'channel_id'),
                ('id', 'channel_id'),
                ('followers_count', 'followers_count'),
                ('followersCount', 'followers_count'),
                ('slug', 'slug'),
            ):
                if obj.get(src_key) not in (None, '') and dst_key not in data:
                    data[dst_key] = obj.get(src_key)

        for src_key, dst_key in (
            ('broadcaster_user_id', 'broadcaster_user_id'),
            ('user_id', 'broadcaster_user_id'),
            ('channel_id', 'channel_id'),
            ('chatroom_id', 'chatroom_id'),
            ('viewer_count', 'viewer_count'),
            ('current_viewers', 'viewer_count'),
            ('viewers', 'viewer_count'),
            ('followers_count', 'followers_count'),
            ('followersCount', 'followers_count'),
            ('is_live', 'is_live'),
            ('slug', 'slug'),
        ):
            if dst_key not in data:
                found = self._search_value(obj, (src_key,))
                if found not in (None, ''):
                    data[dst_key] = found

        chatroom = self._search_value(obj, ('chatroom',))
        if isinstance(chatroom, dict) and 'chatroom_id' not in data:
            data['chatroom_id'] = chatroom.get('id')
        return data

    def _extract_channel_data_from_html(self, html: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if not html:
            return data

        state = self._extract_first_json_blob(html)
        if isinstance(state, dict):
            data.update(self._extract_channel_data_from_any(state))

        regexes = {
            'broadcaster_user_id': [
                r'"broadcaster_user_id"\s*:\s*"?(?P<v>\d+)"?',
                r'"user_id"\s*:\s*"?(?P<v>\d+)"?',
            ],
            'channel_id': [
                r'"channel_id"\s*:\s*"?(?P<v>\d+)"?',
                r'"id"\s*:\s*"?(?P<v>\d+)"?',
            ],
            'chatroom_id': [
                r'"chatroom_id"\s*:\s*"?(?P<v>\d+)"?',
                r'"chatroom"\s*:\s*\{[^{}]*"id"\s*:\s*"?(?P<v>\d+)"?',
            ],
            'viewer_count': [
                r'"viewer_count"\s*:\s*"?(?P<v>\d+)"?',
                r'"current_viewers"\s*:\s*"?(?P<v>\d+)"?',
            ],
            'followers_count': [
                r'"followers_count"\s*:\s*"?(?P<v>\d+)"?',
                r'"followersCount"\s*:\s*"?(?P<v>\d+)"?',
            ],
            'is_live': [
                r'"is_live"\s*:\s*(?P<v>true|false|1|0)',
            ],
        }
        for key, patterns in regexes.items():
            if key in data:
                continue
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    data[key] = match.group('v')
                    break
        return data

    def _fetch_legacy_channel_json(self, channel: str) -> dict[str, Any]:
        url = f'https://kick.com/api/v2/channels/{urllib.parse.quote(channel)}'
        resp = requests.get(url, timeout=12, headers=self._browser_headers(channel), allow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f'legacy channel HTTP {resp.status_code}')
        payload = self._safe_json(resp)
        if not isinstance(payload, dict):
            raise RuntimeError('legacy channel returned no JSON')
        data = self._extract_channel_data_from_any(payload)
        self._append_diag(
            'LEGACY JSON '
            f'broadcaster_user_id={data.get("broadcaster_user_id")} '
            f'channel_id={data.get("channel_id")} '
            f'chatroom_id={data.get("chatroom_id")} '
            f'viewer_count={data.get("viewer_count")} '
            f'followers_count={data.get("followers_count")} '
            f'is_live={data.get("is_live")}'
        )
        return data

    def _fetch_html_page(self, channel: str) -> str:
        url = f'https://kick.com/{urllib.parse.quote(channel)}'
        response = requests.get(url, timeout=12, headers=self._browser_headers(channel), allow_redirects=True)
        if response.status_code != 200:
            raise RuntimeError(f'HTML HTTP {response.status_code}')
        return response.text

    def _fetch_html_channel_data(self, channel: str) -> dict[str, Any]:
        html = self._fetch_html_page(channel)
        data = self._extract_channel_data_from_html(html)
        self._append_diag(
            'HTML '
            f'broadcaster_user_id={data.get("broadcaster_user_id")} '
            f'channel_id={data.get("channel_id")} '
            f'chatroom_id={data.get("chatroom_id")} '
            f'viewer_count={data.get("viewer_count")} '
            f'followers_count={data.get("followers_count")} '
            f'is_live={data.get("is_live")}'
        )
        return data

    def _fetch_official_channel_bundle(self, settings: dict[str, Any], channel: str) -> dict[str, Any]:
        headers = self._api_headers(settings, prefer_main=True)
        if headers is None:
            raise RuntimeError('missing main/bot access token from host')

        sess = requests.Session()
        channels_url = f'{self.KICK_API_BASE}/channels?slug={urllib.parse.quote(channel)}'
        channel_resp = sess.get(channels_url, headers=headers, timeout=12)
        channel_json = self._safe_json(channel_resp)
        if channel_resp.status_code >= 400:
            raise RuntimeError(f'official channels HTTP {channel_resp.status_code} | {channel_resp.text[:300]}')

        row = None
        if isinstance(channel_json, dict):
            rows = channel_json.get('data')
            if isinstance(rows, list) and rows:
                row = rows[0]
            elif isinstance(rows, dict):
                row = rows
        if not isinstance(row, dict):
            raise RuntimeError('official channels returned no channel row')

        broadcaster_user_id = self._parse_int(row.get('broadcaster_user_id') or row.get('user_id'))
        channel_id = self._parse_int(row.get('channel_id') or row.get('id'))
        stream = row.get('stream') if isinstance(row.get('stream'), dict) else {}
        viewer_count = self._parse_int(stream.get('viewer_count') or stream.get('viewers'))
        live_status = self._to_bool(stream.get('is_live'))

        if broadcaster_user_id is not None:
            livestream_url = f'{self.KICK_API_BASE}/livestreams?broadcaster_user_id={broadcaster_user_id}'
            livestream_resp = sess.get(livestream_url, headers=headers, timeout=12)
            livestream_json = self._safe_json(livestream_resp)
            if livestream_resp.status_code == 200 and isinstance(livestream_json, dict):
                items = livestream_json.get('data')
                if isinstance(items, list) and items:
                    item = items[0] if isinstance(items[0], dict) else {}
                    viewer_count = self._parse_int(item.get('viewer_count') or item.get('viewers')) or viewer_count
                    channel_id = self._parse_int(item.get('channel_id') or item.get('id')) or channel_id
                    if live_status is None:
                        live_status = True
                elif live_status is None:
                    live_status = False

        return {
            'broadcaster_user_id': broadcaster_user_id,
            'channel_id': channel_id,
            'viewer_count': viewer_count,
            'is_live': live_status,
        }

    def _effective_ids(self, settings: dict[str, Any]) -> tuple[str, int | None, int | None, int | None, bool | None, int | None, int | None, str]:
        channel = self._channel_from_settings(settings)
        manual_broadcaster_user_id = self._parse_int(settings.get('broadcaster_user_id'))
        manual_channel_id = self._parse_int(settings.get('channel_id'))
        # Falls ein alter Wert noch in settings.json liegt, nutzen wir ihn, zeigen ihn aber nicht mehr im UI.
        manual_chatroom_id = self._parse_int(settings.get('chatroom_id'))

        broadcaster_user_id = manual_broadcaster_user_id
        channel_id = manual_channel_id
        chatroom_id = manual_chatroom_id
        is_live = None
        viewer_count = None
        followers_count = None
        source_parts: list[str] = []

        if broadcaster_user_id is not None:
            source_parts.append('settings_broadcaster_user_id')
        if channel_id is not None:
            source_parts.append('settings_channel_id')
        if chatroom_id is not None:
            source_parts.append('cached_chatroom_id')

        try:
            bundle = self._fetch_official_channel_bundle(settings, channel)
            broadcaster_user_id = bundle.get('broadcaster_user_id') or broadcaster_user_id
            channel_id = bundle.get('channel_id') or channel_id
            viewer_count = bundle.get('viewer_count')
            is_live = bundle.get('is_live')
            source_parts.append('official_api')
        except Exception as exc:
            self._append_diag(f'Official API unavailable: {exc}')

        for loader_name, loader in (
            ('legacy_json', self._fetch_legacy_channel_json),
            ('html_fallback', self._fetch_html_channel_data),
        ):
            try:
                data = loader(channel)
            except Exception as exc:
                self._append_diag(f'{loader_name} unavailable: {exc}')
                continue

            broadcaster_user_id = self._parse_int(data.get('broadcaster_user_id')) or broadcaster_user_id
            channel_id = self._parse_int(data.get('channel_id')) or channel_id
            chatroom_id = self._parse_int(data.get('chatroom_id')) or chatroom_id
            followers_count = self._parse_int(data.get('followers_count')) or followers_count
            if viewer_count is None:
                viewer_count = self._parse_int(data.get('viewer_count'))
            if is_live is None:
                is_live = self._to_bool(data.get('is_live'))
            if data:
                source_parts.append(loader_name)
            if chatroom_id:
                break

        source = ' + '.join(source_parts) if source_parts else 'unknown'
        self._append_diag(
            f'RESOLVED channel={channel} '
            f'broadcaster_user_id={broadcaster_user_id} '
            f'channel_id={channel_id} '
            f'chatroom_id={chatroom_id} '
            f'viewer_count={viewer_count} '
            f'followers_count={followers_count} '
            f'is_live={is_live} '
            f'source={source}'
        )
        return channel, broadcaster_user_id, channel_id, chatroom_id, is_live, viewer_count, followers_count, source

    def _status_short(self, host: PluginHost, state: str, text: str):
        safe = (text or '').strip()
        self._append_diag(f'STATUS [{state}] {safe}')
        host.set_status(self.plugin_id, PluginStatus(state, safe[:180]))

    def _kick_emote_url(self, emote_id: str | int) -> str:
        return f'https://files.kick.com/emotes/{emote_id}/fullsize'

    def _build_overlay_html_from_fragments(self, fragments: list[dict[str, Any]]) -> str:
        html_parts: list[str] = []
        for fragment in fragments or []:
            frag_type = str(fragment.get('type') or '').strip().lower()
            if frag_type == 'emote':
                src = str(fragment.get('image_url') or fragment.get('url') or '').strip()
                alt = str(fragment.get('text') or fragment.get('name') or '').strip()
                if src:
                    html_parts.append(f'<img src="{_html_escape(src, quote=True)}" alt="{_html_escape(alt or "emote")}">')
                elif alt:
                    html_parts.append(_html_escape(alt))
            else:
                html_parts.append(_html_escape(str(fragment.get('text') or '')))
        return ''.join(html_parts).strip()

    def _normalize_chat_text(self, value: Any) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            text = value
        elif isinstance(value, dict):
            for key in ('content', 'text', 'body', 'message', 'value'):
                if key in value:
                    inner = self._normalize_chat_text(value.get(key))
                    if inner:
                        return inner
            return ''
        elif isinstance(value, list):
            parts = [self._normalize_chat_text(part) for part in value]
            text = ' '.join(part for part in parts if part)
        else:
            text = str(value)
        text = str(text).replace('\r', ' ').replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        if text in ('[]', '{}', ':', '-', 'null', 'None'):
            return ''
        return text

    def _parse_kick_content_with_emotes(self, value: Any) -> dict[str, Any]:
        raw_text = self._normalize_chat_text(value)
        if not raw_text:
            return {'raw_text': '', 'text': '', 'emotes': [], 'fragments': [], 'overlay_html': ''}

        emotes: list[dict[str, Any]] = []
        fragments: list[dict[str, Any]] = []
        cursor = 0
        for match in self.KICK_EMOTE_TOKEN_RE.finditer(raw_text):
            start, end = match.span()
            if start > cursor:
                text_part = raw_text[cursor:start]
                if text_part:
                    fragments.append({'type': 'text', 'text': text_part})
            emote_id = str(match.group('id') or '').strip()
            emote_name = str(match.group('name') or '').strip()
            emote_url = self._kick_emote_url(emote_id) if emote_id else ''
            entry = {
                'type': 'emote',
                'id': emote_id,
                'name': emote_name,
                'code': emote_name,
                'text': emote_name,
                'url': emote_url,
                'image_url': emote_url,
                'provider': 'kick',
                'source': 'kick',
            }
            emotes.append(dict(entry))
            fragments.append(entry)
            cursor = end
        if cursor < len(raw_text):
            tail = raw_text[cursor:]
            if tail:
                fragments.append({'type': 'text', 'text': tail})

        display_parts: list[str] = []
        for fragment in fragments:
            if fragment.get('type') == 'emote':
                display_parts.append(str(fragment.get('text') or fragment.get('name') or '').strip())
            else:
                display_parts.append(str(fragment.get('text') or ''))
        display_text = re.sub(r'\s+', ' ', ''.join(display_parts)).strip()
        return {
            'raw_text': raw_text,
            'text': display_text,
            'emotes': emotes,
            'fragments': fragments,
            'overlay_html': self._build_overlay_html_from_fragments(fragments),
        }

    def _coerce_viewer_count(self, candidate: int | None, *, is_live_hint: bool | None, source: str) -> int | None:
        # Kick can expose stale/last livestream viewer_count values via legacy/HTML data even
        # when the channel is offline. Offline must always win, otherwise the tool can show
        # a fantasy viewer count (for example 1500) while no livestream exists.
        if is_live_hint is False:
            if candidate not in (None, 0):
                self._append_diag(f'IGNORE stale offline viewer_count={candidate} source={source}')
            return 0
        if candidate is None:
            return self._current_viewer_count
        if candidate < 0:
            return self._current_viewer_count
        if candidate == 0 and is_live_hint is True and isinstance(self._current_viewer_count, int) and self._current_viewer_count > 0:
            self._append_diag(f'IGNORE viewer_count=0 source={source} cached={self._current_viewer_count}')
            return self._current_viewer_count
        return candidate

    def _log_viewer_count(self, count: int | None, *, source: str) -> None:
        if count is None or self._last_viewer_count == count:
            return
        self._last_viewer_count = count
        self._append_diag(f'VIEWERS {count} source={source}')

    def _emit_viewer_snapshot(self, host: PluginHost, channel: str, count: int | None, *, force: bool = False) -> None:
        if count is None:
            return
        now = time.monotonic()
        if not force and self._last_viewer_count == count and (now - self._last_viewer_emit_monotonic) < 20:
            return
        self._last_viewer_emit_monotonic = now
        host.emit_message(self.plugin_id, {
            'platform': 'kick',
            'username': '',
            'text': str(count),
            'channel': channel,
            'message_type': 'viewer_count',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': False,
            'show_in_obs': False,
            'viewer_count': count,
        })

    def _emit_followers_snapshot(self, host: PluginHost, channel: str, count: int | None, *, force: bool = False) -> None:
        if count is None:
            return
        if not force and self._last_followers_count == count:
            return
        self._last_followers_count = count
        host.emit_message(self.plugin_id, {
            'platform': 'kick',
            'username': '',
            'text': str(count),
            'channel': channel,
            'message_type': 'followers_count',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': False,
            'show_in_obs': False,
            'followers_count': count,
            'follower_count': count,
        })

    def _emit_is_live(self, host: PluginHost, channel: str, value: bool | None) -> None:
        if value is None:
            return
        live = bool(value)
        if self._is_live is live:
            return
        self._is_live = live
        self._append_diag(f'IS_LIVE {self._is_live}')
        state = 'connected' if self._is_live else 'warning'
        host.set_status(self.plugin_id, PluginStatus(state, f'Watching #{channel} | live={str(self._is_live).lower()}'))

    def _refresh_metrics(self, host: PluginHost, settings: dict[str, Any], channel: str, *, force: bool = False) -> None:
        viewer_count = None
        followers_count = None
        is_live = None

        try:
            bundle = self._fetch_official_channel_bundle(settings, channel)
            viewer_count = bundle.get('viewer_count')
            is_live = bundle.get('is_live')
            self._append_diag(f'Official metrics viewer_count={viewer_count} is_live={is_live}')
        except Exception as e:
            self._append_diag(f'Failed official metrics refresh: {e}')

        try:
            data = self._fetch_legacy_channel_json(channel)
            followers_count = self._parse_int(data.get('followers_count'))
            if viewer_count is None:
                viewer_count = self._parse_int(data.get('viewer_count'))
            if is_live is None:
                is_live = self._to_bool(data.get('is_live'))
        except Exception as e:
            self._append_diag(f'Failed legacy metrics refresh: {e}')

        if is_live is False:
            viewer_count = 0
        viewer_count = self._coerce_viewer_count(viewer_count, is_live_hint=is_live, source='metrics')
        if viewer_count is not None:
            self._current_viewer_count = viewer_count
            self._log_viewer_count(viewer_count, source='metrics')
            self._emit_viewer_snapshot(host, channel, viewer_count, force=force)
        if followers_count is not None:
            self._current_followers_count = followers_count
            self._append_diag(f'FOLLOWERS {followers_count}')
            self._emit_followers_snapshot(host, channel, followers_count, force=force)
        if is_live is not None:
            self._emit_is_live(host, channel, is_live)

    def _emit_chat_item(self, host: PluginHost, channel: str, item: dict[str, Any], seen: set[str]):
        mid = str(item.get('id') or item.get('message_id') or item.get('uuid') or '')
        if mid and mid in seen:
            return

        sender = item.get('sender') or item.get('user') or item.get('chat_sender') or {}
        if not isinstance(sender, dict):
            sender = {}
        username = self._normalize_chat_text(sender.get('username') or sender.get('slug') or sender.get('name') or item.get('username') or 'unknown') or 'unknown'
        parsed_content = self._parse_kick_content_with_emotes(item.get('content') or item.get('message') or item.get('text') or '')
        content = parsed_content.get('text') or ''
        raw_content = parsed_content.get('raw_text') or ''
        emotes = parsed_content.get('emotes') or []
        fragments = parsed_content.get('fragments') or []
        overlay_html = parsed_content.get('overlay_html') or ''

        if not content and not emotes:
            return
        if mid:
            seen.add(mid)

        self._append_diag(f'MESSAGE {username}: {(raw_content or content)[:220]}')
        host.emit_message(self.plugin_id, {
            'platform': 'kick',
            'username': username,
            'text': content,
            'raw_text': raw_content,
            'channel': channel,
            'message_type': 'chat',
            'source_plugin_id': self.plugin_id,
            'show_in_desktop': True,
            'show_in_obs': True,
            'overlay_html': overlay_html,
            'emotes': emotes,
            'fragments': fragments,
            'parts': fragments,
        })

    def _handle_ws_message(self, raw: str, host: PluginHost, channel: str, seen: set[str], ws_send=None):
        try:
            msg = json.loads(raw)
        except Exception:
            self._append_diag(f'RAW(non-json) {raw[:500]}')
            return

        event = str(msg.get('event') or '')
        if event == 'pusher:ping' and ws_send is not None:
            with contextlib.suppress(Exception):
                ws_send(json.dumps({'event': 'pusher:pong', 'data': {}}))
            return

        raw_data = msg.get('data')
        data = raw_data
        if isinstance(raw_data, str):
            with contextlib.suppress(Exception):
                data = json.loads(raw_data)
        payload = data if isinstance(data, dict) else {}

        if event == 'pusher_internal:subscription_succeeded':
            self._append_diag(f'SUBSCRIBED {raw[:300]}')
            return

        if event == 'App\\Events\\ChatMessageEvent':
            if self._is_live is None:
                self._emit_is_live(host, channel, True)
            self._emit_chat_item(host, channel, payload, seen)
            return

        viewer_count = None
        if isinstance(payload, dict):
            viewer_count = self._parse_int(payload.get('viewers') or payload.get('viewer_count'))
        viewer_count = self._coerce_viewer_count(viewer_count, is_live_hint=self._is_live, source=f'ws:{event or "unknown"}')
        if viewer_count is not None:
            self._current_viewer_count = viewer_count
            self._log_viewer_count(viewer_count, source=f'ws:{event or "unknown"}')
            self._emit_viewer_snapshot(host, channel, viewer_count)

        if event == 'App\\Events\\StreamerIsLiveEvent':
            self._emit_is_live(host, channel, True)
        elif event == 'App\\Events\\StreamEndEvent':
            self._emit_is_live(host, channel, False)

        message = payload.get('message') if isinstance(payload.get('message'), dict) else None
        if message is not None:
            if self._is_live is None:
                self._emit_is_live(host, channel, True)
            merged = dict(message)
            sender = payload.get('sender') if isinstance(payload.get('sender'), dict) else payload.get('user') if isinstance(payload.get('user'), dict) else None
            if sender is not None and 'sender' not in merged:
                merged['sender'] = sender
            self._emit_chat_item(host, channel, merged, seen)
            return

        if isinstance(payload, dict) and (payload.get('content') or isinstance(payload.get('message'), str)):
            if self._is_live is None:
                self._emit_is_live(host, channel, True)
            self._emit_chat_item(host, channel, payload, seen)
            return

        if isinstance(payload, dict) and payload.get('messages'):
            for item in payload.get('messages') or []:
                if isinstance(item, dict):
                    self._emit_chat_item(host, channel, item, seen)

    def _subscribe_channels(self, chatroom_id: int, channel_id: int | None = None) -> list[str]:
        channels = [
            f'chatrooms.{chatroom_id}.v2',
            f'chatrooms.{chatroom_id}',
            f'chatroom.{chatroom_id}',
            f'chatroom.{chatroom_id}.v2',
        ]
        if channel_id:
            for extra in (
                f'channel.{channel_id}',
                f'channels.{channel_id}',
                f'livestream.{channel_id}',
                f'livestreams.{channel_id}',
                f'stream.{channel_id}',
                f'streams.{channel_id}',
            ):
                if extra not in channels:
                    channels.append(extra)
        return channels

    def _run_with_websocket_client(self, ws_url: str, chatroom_id: int, host: PluginHost, settings: dict[str, Any], channel: str, viewer_poll_interval: float, channel_id: int | None = None):
        seen: set[str] = set()
        ws = websocket.create_connection(ws_url, timeout=15)
        ws.settimeout(10)
        raw_frame_count = 0
        try:
            self._status_short(host, 'connecting', f'Kick websocket connected | room {chatroom_id}')
            try:
                first = ws.recv()
                if first:
                    self._append_diag(f'FIRST FRAME {str(first)[:700]}')
            except Exception as exc:
                self._append_diag(f'FIRST FRAME read failed: {exc}')

            for subscribe_channel in self._subscribe_channels(chatroom_id, channel_id):
                ws.send(json.dumps({'event': 'pusher:subscribe', 'data': {'auth': '', 'channel': subscribe_channel}}))
                self._append_diag(f'SUBSCRIBE {subscribe_channel}')

            self._status_short(host, 'connected', f'Watching #{channel} | room {chatroom_id}')
            self._refresh_metrics(host, settings, channel, force=True)
            last_ping = time.time()
            last_metrics_poll = time.time()

            while not self._stop.is_set():
                try:
                    raw = ws.recv()
                    if raw:
                        raw_frame_count += 1
                        if raw_frame_count <= 25:
                            self._append_diag(f'RAW FRAME #{raw_frame_count} {str(raw)[:900]}')
                        self._handle_ws_message(raw, host, channel, seen, ws.send)
                except websocket.WebSocketTimeoutException:
                    pass

                now = time.time()
                if now - last_ping >= 12:
                    ws.send(json.dumps({'event': 'pusher:ping', 'data': {}}))
                    last_ping = now
                if now - last_metrics_poll >= viewer_poll_interval:
                    self._refresh_metrics(host, settings, channel)
                    last_metrics_poll = now
        finally:
            with contextlib.suppress(Exception):
                ws.close()

    async def _run_with_websockets_async(self, ws_url: str, chatroom_id: int, host: PluginHost, settings: dict[str, Any], channel: str, viewer_poll_interval: float, channel_id: int | None = None):
        seen: set[str] = set()
        async with websockets.connect(ws_url, ping_interval=None, close_timeout=5) as ws:
            self._status_short(host, 'connecting', f'Kick websocket connected | room {chatroom_id}')
            raw_frame_count = 0
            try:
                first = await asyncio.wait_for(ws.recv(), timeout=10)
                if isinstance(first, bytes):
                    first = first.decode('utf-8', errors='ignore')
                if first:
                    self._append_diag(f'FIRST FRAME {first[:700]}')
            except Exception as exc:
                self._append_diag(f'FIRST FRAME read failed: {exc}')

            for subscribe_channel in self._subscribe_channels(chatroom_id, channel_id):
                await ws.send(json.dumps({'event': 'pusher:subscribe', 'data': {'auth': '', 'channel': subscribe_channel}}))
                self._append_diag(f'SUBSCRIBE {subscribe_channel}')

            self._status_short(host, 'connected', f'Watching #{channel} | room {chatroom_id}')
            self._refresh_metrics(host, settings, channel, force=True)
            last_ping = time.time()
            last_metrics_poll = time.time()

            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8', errors='ignore')
                    if raw:
                        raw_frame_count += 1
                        if raw_frame_count <= 25:
                            self._append_diag(f'RAW FRAME #{raw_frame_count} {str(raw)[:900]}')
                        self._handle_ws_message(raw, host, channel, seen, ws.send)
                except TimeoutError:
                    pass

                now = time.time()
                if now - last_ping >= 12:
                    await ws.send(json.dumps({'event': 'pusher:ping', 'data': {}}))
                    last_ping = now
                if now - last_metrics_poll >= viewer_poll_interval:
                    self._refresh_metrics(host, settings, channel)
                    last_metrics_poll = now

    def test_connection(self, settings):
        effective = self._effective_settings(settings, self._host)
        channel = self._channel_from_settings(effective)
        if not channel:
            return False, 'Missing Kick channel. Set Main account in the Kick platform tab.'

        channel, broadcaster_user_id, channel_id, chatroom_id, is_live, viewer_count, followers_count, source = self._effective_ids(effective)
        settings['diag_log'] = self._read_diag()
        settings['diag_path'] = str(self._diag_path())
        live_txt = 'live=yes' if is_live else 'live=no' if is_live is not None else 'live=unknown'
        viewer_txt = f'viewers={viewer_count}' if viewer_count is not None else 'viewers=unknown'
        followers_txt = f'followers={followers_count}' if followers_count is not None else 'followers=unknown'

        if chatroom_id:
            return True, f'Kick ready: room {chatroom_id} | {live_txt} | {viewer_txt} | {followers_txt} | source={source}'
        # No manual chatroom setting anymore. OAuth belongs to the maintool and
        # the plugin keeps resolving/retrying from Kick itself.
        return False, f'Kick channel found, but realtime chatroom ID is not available yet | {live_txt} | {viewer_txt} | {followers_txt} | source={source}'

    def run(self, settings, host: PluginHost):
        self._host = host
        effective = self._effective_settings(settings, host)
        channel = self._channel_from_settings(effective)
        if not channel:
            raise RuntimeError('Missing Kick channel. Set Main account in the Kick platform tab.')

        reconnect_delay = 3.0
        viewer_poll_interval = 20.0
        ws_url = self.DEFAULT_WS_URL

        self._last_viewer_count = None
        self._last_followers_count = None
        self._last_viewer_emit_monotonic = 0.0
        self._current_viewer_count = None
        self._current_followers_count = None
        self._is_live = None

        channel, broadcaster_user_id, channel_id, chatroom_id, is_live, viewer_count, followers_count, source = self._effective_ids(effective)

        self._set_diag(
            f'Kick host-auth mode\n'
            f'channel={channel}\n'
            f'broadcaster_user_id={broadcaster_user_id}\n'
            f'channel_id={channel_id}\n'
            f'chatroom_id={chatroom_id}\n'
            f'is_live={is_live}\n'
            f'viewer_count={viewer_count}\n'
            f'followers_count={followers_count}\n'
            f'source={source}\n'
            f'ws={ws_url}\n'
            f'Note: OAuth/tokens are owned by godisalotachat. Chat reading uses Kick realtime websocket. Writing uses host.send_platform_message("kick", ...).'
        )

        while not self._stop.is_set():
            try:
                # Refresh host-provided settings before each reconnect, because tokens/accounts can change in the maintool.
                effective = self._effective_settings(settings, host)
                channel, broadcaster_user_id, channel_id, chatroom_id, is_live, viewer_count, followers_count, source = self._effective_ids(effective)
                if not chatroom_id:
                    # Do not crash into an obsolete manual-chatroom-id message. Kick
                    # sometimes hides the realtime room id for a few seconds after
                    # stream start or behind a flaky website/API response. Keep
                    # retrying silently with a useful status.
                    self._status_short(host, 'warning', f'Kick chatroom not ready for #{channel}; retrying in {int(reconnect_delay)}s')
                    self._append_diag(f'WAIT no chatroom_id channel={channel} broadcaster_user_id={broadcaster_user_id} channel_id={channel_id} source={source}')
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.5, 30.0)
                    continue

                reconnect_delay = 3.0
                if websocket is not None:
                    self._run_with_websocket_client(ws_url, int(chatroom_id), host, effective, channel, viewer_poll_interval, channel_id)
                elif websockets is not None:
                    asyncio.run(self._run_with_websockets_async(ws_url, int(chatroom_id), host, effective, channel, viewer_poll_interval, channel_id))
                else:
                    raise RuntimeError('No websocket library available in host app.')
            except Exception as exc:
                self._append_diag(f'ws_error={exc}')
                self._status_short(host, 'error', f'Kick reconnect in {int(reconnect_delay)}s | {exc}')
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 30.0)
            else:
                break

        self._status_short(host, 'disconnected', 'Stopped')

    def _send_direct_with_token(self, message: str, settings: dict[str, Any], *, use_bot: bool = True) -> tuple[bool, str]:
        content = str(message or '').strip()
        if not content:
            return False, 'Kick message is empty.'
        if len(content) > 500:
            content = content[:500]
        token = self._clean_token(settings.get('access_token') if use_bot else settings.get('main_access_token'))
        if not token:
            return False, 'Kick token missing from host settings.'
        broadcaster_id = str(settings.get('broadcaster_user_id') or settings.get('channel_id') or settings.get('main_user_id') or '').strip()
        payloads: list[tuple[str, dict[str, Any]]] = []
        if broadcaster_id.isdigit():
            bid = int(broadcaster_id)
            payloads.append(('user-with-broadcaster', {'content': content, 'type': 'user', 'broadcaster_user_id': bid}))
            if use_bot:
                payloads.append(('bot-with-broadcaster', {'content': content, 'type': 'bot', 'broadcaster_user_id': bid}))
            payloads.append(('minimal-with-broadcaster', {'content': content, 'broadcaster_user_id': bid}))
        else:
            payloads.append(('user-minimal', {'content': content, 'type': 'user'}))
            if use_bot:
                payloads.append(('bot-minimal', {'content': content, 'type': 'bot'}))

        errors: list[str] = []
        for variant, payload in payloads:
            try:
                resp = requests.post(
                    self.KICK_CHAT_URL,
                    headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                    json=payload,
                    timeout=15,
                )
                if resp.status_code < 400:
                    return True, f'Kick message sent direct ({variant}).'
                errors.append(f'{variant}: HTTP {resp.status_code} {resp.text[:300]}')
            except Exception as exc:
                errors.append(f'{variant}: {exc}')
        return False, 'Kick send failed: ' + ' | '.join(errors)[:900]

    def send_message(self, message: str, settings: dict[str, Any] | None = None, host: PluginHost | None = None):
        host = host or self._host
        effective = self._effective_settings(settings, host)
        # Preferred path: Maintool owns writing, refresh and bot/main selection.
        if host is not None and callable(getattr(host, 'send_platform_message', None)):
            try:
                ok = bool(host.send_platform_message('kick', message, use_bot=True, sender=self.plugin_id))
                return ok, 'Kick message sent via host.' if ok else 'Kick host send failed.'
            except Exception as exc:
                self._append_diag(f'Host send failed, trying direct token fallback: {exc}')
        return self._send_direct_with_token(message, effective, use_bot=True)


def create_plugin():
    return KickChatPlugin()
