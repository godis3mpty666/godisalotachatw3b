from __future__ import annotations

import html
import json
import re
import threading
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin

TOKEN_URL = 'https://oauth2.googleapis.com/token'
CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'
LIVE_BROADCASTS_URL = 'https://www.googleapis.com/youtube/v3/liveBroadcasts'
LIVE_CHAT_MESSAGES_URL = 'https://www.googleapis.com/youtube/v3/liveChat/messages'
VIDEOS_URL = 'https://www.googleapis.com/youtube/v3/videos'
SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'


class YouTubeChatPlugin(ThreadedPlugin):
    plugin_id = 'youtube_chat'
    display_name = 'YouTube Chat'
    version = '1.0.17'
    description = 'YouTube Live chat reader/writer using central OAuth with slow live detection.'

    def __init__(self) -> None:
        super().__init__()
        self._connected = False
        self._live_chat_id = ''
        self._next_page_token = ''
        self._seen_message_ids: set[str] = set()
        self._runtime_tokens: dict[str, str] = {}
        self._send_lock = threading.Lock()
        self._broadcast_video_id = ''
        self._broadcast_debug = ''
        self._last_viewer_count: int | None = None
        self._last_metrics_poll = 0.0
        self._connect_started_at = 0.0
        self._last_lookup_error = ''
        self._web_video_id = ''
        self._web_api_key = ''
        self._web_continuation = ''
        self._web_client_version = '2.20240601.00.00'

    def settings_schema(self):
        # Login/auth is intentionally only in the main tool under Platforms -> YouTube.
        return [
            {
                'key': 'startup_skip_backlog',
                'label': 'Start alte Chatzeilen überspringen',
                'label_en': 'Skip old chat lines on start',
                'type': 'checkbox',
                'help': 'Verhindert, dass alte YouTube-Chat-History beim Verbinden nochmal in Bridge/Desktop läuft.',
                'help_en': 'Prevents old YouTube chat history from being emitted again when connecting.',
            },
            {
                'key': 'viewer_count_enabled',
                'label': 'Zuschauerzahl anzeigen',
                'label_en': 'Show viewer count',
                'type': 'checkbox',
                'help': 'Gibt die YouTube-Zuschauerzahl an Overlays/Tools weiter.',
                'help_en': 'Sends the YouTube viewer count to overlays/tools.',
            },
            {
                'key': 'live_check_interval_seconds',
                'label': 'Live-Check Intervall (Sekunden)',
                'label_en': 'Live check interval (seconds)',
                'type': 'number',
                'min': 60,
                'max': 300,
                'help': 'Wie oft YouTube gefragt wird, ob ein Livestream aktiv ist. Niedriger belastet API/Quota stärker.',
                'help_en': 'How often YouTube is checked for an active livestream. Lower values use more API/quota.',
            },
        ]

    def default_settings(self):
        return {
            'startup_skip_backlog': True,
            'viewer_count_enabled': False,
            'live_check_interval_seconds': 90,
            'autoconnect': False,
        }

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
    def _clean_account(value: Any) -> str:
        return str(value or '').strip().lstrip('@').strip()

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or '').replace('\r', ' ').replace('\n', ' ')
        return ' '.join(text.split()).strip()

    @staticmethod
    def _yt_time_to_epoch(value: Any) -> float:
        text = str(value or '').strip()
        if not text:
            return 0.0
        try:
            if text.endswith('Z'):
                text = text[:-1] + '+00:00'
            return datetime.fromisoformat(text).timestamp()
        except Exception:
            return 0.0

    def _host_platform_settings(self, host: PluginHost | None, platform: str = 'youtube') -> dict[str, Any]:
        if host is None:
            return {}
        for name in ('platform_settings', 'get_platform_settings'):
            fn = getattr(host, name, None)
            if callable(fn):
                try:
                    data = fn(platform)
                except TypeError:
                    try:
                        all_data = fn()
                        data = all_data.get(platform, {}) if isinstance(all_data, dict) else {}
                    except Exception:
                        data = {}
                except Exception:
                    data = {}
                if isinstance(data, dict):
                    return dict(data)
        return {}

    def _merge_platform_settings(self, settings: dict | None, host: PluginHost | None = None) -> dict[str, Any]:
        merged = dict(settings or {})
        platform = self._host_platform_settings(host, 'youtube')
        if not platform:
            return merged

        merged['read_enabled'] = self._as_bool(platform.get('read_enabled'), self._as_bool(platform.get('read'), True))
        merged['write_enabled'] = self._as_bool(platform.get('write_enabled'), self._as_bool(platform.get('write'), True))
        merged['autoconnect'] = self._as_bool(platform.get('autoconnect'), self._as_bool(merged.get('autoconnect'), False))
        merged['main_account'] = self._clean_account(platform.get('main_account') or platform.get('channel') or platform.get('live_channel') or merged.get('main_account') or '')
        merged['bot_account'] = self._clean_account(platform.get('bot_account') or platform.get('bot_username') or platform.get('username') or merged.get('bot_account') or '')
        for key in (
            'client_id', 'client_secret',
            'access_token', 'refresh_token',
            'main_access_token', 'main_refresh_token',
            'main_channel_id', 'broadcaster_channel_id', 'bot_channel_id',
            'live_chat_id',
        ):
            value = platform.get(key)
            if value not in (None, ''):
                merged[key] = str(value).strip()
        return merged

    def _token_for(self, settings: dict[str, Any], kind: str) -> str:
        if kind == 'main':
            # Main/Broadcaster token is mandatory for reading and broadcast lookup.
            # Never silently fall back to the bot token, otherwise the plugin searches
            # the wrong channel while the Platform tab still says OAuth is OK.
            return self._runtime_tokens.get('main_access_token') or str(settings.get('main_access_token') or '').strip()
        return self._runtime_tokens.get('access_token') or str(settings.get('access_token') or settings.get('bot_access_token') or '').strip()

    def _refresh_token(self, settings: dict[str, Any], kind: str) -> str:
        client_id = str(settings.get('client_id') or '').strip()
        client_secret = str(settings.get('client_secret') or '').strip()
        refresh_key = 'main_refresh_token' if kind == 'main' else 'refresh_token'
        access_key = 'main_access_token' if kind == 'main' else 'access_token'
        refresh_token = str(settings.get(refresh_key) or (settings.get('bot_refresh_token') if kind != 'main' else '') or '').strip()
        if not client_id or not refresh_token:
            return ''
        data = {
            'client_id': client_id,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }
        if client_secret:
            data['client_secret'] = client_secret
        payload = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(TOKEN_URL, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            token = str((json.loads(raw or '{}') or {}).get('access_token') or '').strip()
            if token:
                self._runtime_tokens[access_key] = token
                return token
        except Exception:
            return ''
        return ''

    def _request_json(self, url: str, *, token: str, method: str = 'GET', params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, timeout: float = 7.0) -> dict[str, Any]:
        final_url = url
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
            final_url = final_url + ('&' if '?' in final_url else '?') + qs
        payload = None
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'User-Agent': 'godisalotachat-youtube-chat/1.0'}
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(final_url, data=payload, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        return json.loads(raw or '{}')

    def _request_json_auth(self, settings: dict[str, Any], kind: str, url: str, *, method: str = 'GET', params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, timeout: float = 7.0) -> dict[str, Any]:
        token = self._token_for(settings, kind)
        if not token:
            token = self._refresh_token(settings, kind)
        if not token:
            raise RuntimeError(f'Missing YouTube {kind} OAuth token from main tool.')
        try:
            return self._request_json(url, token=token, method=method, params=params, body=body, timeout=timeout)
        except urllib.error.HTTPError as exc:
            code = int(getattr(exc, 'code', 0) or 0)
            if code == 401:
                token = self._refresh_token(settings, kind)
                if token:
                    return self._request_json(url, token=token, method=method, params=params, body=body, timeout=timeout)
            # Keep the original HTTP status for control flow, but attach the API body
            # so the plugin status/log is no longer a useless bare "Bad Request".
            try:
                body_text = exc.read().decode('utf-8', errors='replace')
                if body_text:
                    exc.reason = f'{getattr(exc, "reason", "")} | {body_text[:600]}'
            except Exception:
                pass
            raise

    def _channel_info(self, settings: dict[str, Any], kind: str = 'main') -> tuple[bool, str, str]:
        if kind == 'main':
            cached_id = str(settings.get('main_channel_id') or settings.get('broadcaster_channel_id') or '').strip()
            cached_title = str(settings.get('main_channel_title') or settings.get('main_account') or '').strip()
            if cached_id:
                return True, cached_id, cached_title or 'main'
        elif kind == 'bot':
            cached_id = str(settings.get('bot_channel_id') or '').strip()
            cached_title = str(settings.get('bot_channel_title') or settings.get('bot_account') or '').strip()
            if cached_id:
                return True, cached_id, cached_title or 'bot'
        data = self._request_json_auth(settings, kind, CHANNELS_URL, params={'part': 'snippet', 'mine': 'true', 'maxResults': 1}, timeout=6.0)
        items = data.get('items') if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            return False, '', f'YouTube {kind} token ok, but no channel found.'
        item = items[0] if isinstance(items[0], dict) else {}
        snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
        channel_id = str(item.get('id') or '').strip()
        title = str((snippet or {}).get('title') or '').strip()
        return True, channel_id, title or kind

    def _validate_channel(self, settings: dict[str, Any], kind: str = 'main') -> tuple[bool, str]:
        ok, _channel_id, title = self._channel_info(settings, kind)
        return ok, title

    def _broadcast_sort_key(self, item: dict[str, Any]) -> tuple[int, float]:
        status = item.get('status') if isinstance(item.get('status'), dict) else {}
        snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
        life = str((status or {}).get('lifeCycleStatus') or '').strip().lower()
        actual_start = str((snippet or {}).get('actualStartTime') or '').strip()
        scheduled_start = str((snippet or {}).get('scheduledStartTime') or '').strip()
        if life == 'live' or actual_start:
            rank = 0
        elif life in {'testing', 'ready', 'created', 'liveStarting'}:
            rank = 1
        elif life == 'complete':
            rank = 9
        else:
            rank = 2
        # Bei mehreren geplanten/alten Streams den neuesten Kandidaten nehmen.
        return rank, -self._yt_time_to_epoch(actual_start or scheduled_start)

    def _http_error_short(self, exc: Exception) -> str:
        if isinstance(exc, urllib.error.HTTPError):
            code = int(getattr(exc, 'code', 0) or 0)
            reason = str(getattr(exc, 'reason', '') or '').strip()
            return f'HTTP {code}: {reason or exc}'
        return str(exc)

    def _broadcasts_for_status(self, settings: dict[str, Any], status: str) -> list[dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        base = {
            'part': 'snippet,contentDetails,status',
            'broadcastStatus': status,
            'mine': 'true',
            'maxResults': 10,
        }
        # broadcastType=all is useful, but some YouTube projects reject it with
        # HTTP 400. Try it once, then retry the clean minimal request. Never use
        # a request without broadcastStatus; YouTube rejects that and it caused
        # the old Bad Request loop.
        with_type = dict(base)
        with_type['broadcastType'] = 'all'
        attempts.append(with_type)
        attempts.append(base)

        last_error = ''
        for params in attempts:
            try:
                data = self._request_json_auth(settings, 'main', LIVE_BROADCASTS_URL, params=params, timeout=7.0)
                rows = data.get('items') if isinstance(data, dict) else None
                self._last_lookup_error = ''
                return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
            except urllib.error.HTTPError as exc:
                last_error = self._http_error_short(exc)
                continue
            except Exception as exc:
                last_error = str(exc)
                break
        self._last_lookup_error = f'liveBroadcasts.list failed for status={status}: {last_error}' if last_error else ''
        return []

    def _get_broadcast_video_id(self, item: dict[str, Any]) -> str:
        # For YouTube liveBroadcast resources the resource id is normally the watch/video id,
        # but keep the helper separate so we never mix it up with liveChatId.
        return str((item or {}).get('id') or '').strip()

    def _broadcast_live_chat_id(self, item: dict[str, Any]) -> str:
        snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
        return str((snippet or {}).get('liveChatId') or '').strip()

    def _video_live_details(self, settings: dict[str, Any], video_id: str) -> tuple[str, int | None, str]:
        video_id = str(video_id or '').strip()
        if not video_id:
            return '', None, ''
        data = self._request_json_auth(settings, 'main', VIDEOS_URL, params={
            'part': 'snippet,liveStreamingDetails',
            'id': video_id,
        })
        rows = data.get('items') if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            return '', None, ''
        row = rows[0] if isinstance(rows[0], dict) else {}
        snippet = row.get('snippet') if isinstance(row.get('snippet'), dict) else {}
        details = row.get('liveStreamingDetails') if isinstance(row.get('liveStreamingDetails'), dict) else {}
        chat_id = str((details or {}).get('activeLiveChatId') or '').strip()
        raw_viewers = (details or {}).get('concurrentViewers')
        viewers: int | None = None
        if raw_viewers not in (None, ''):
            try:
                viewers = max(int(str(raw_viewers).strip()), 0)
            except Exception:
                viewers = None
        title = str((snippet or {}).get('title') or '').strip()
        return chat_id, viewers, title

    def _video_viewers_only(self, settings: dict[str, Any], video_id: str) -> int | None:
        try:
            _chat_id, viewers, _title = self._video_live_details(settings, video_id)
            return viewers
        except Exception:
            return None

    def _video_id_from_text(self, value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        # Plain video id.
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', text):
            return text
        # Normal YouTube URLs.
        try:
            parsed = urllib.parse.urlparse(text)
            qs = urllib.parse.parse_qs(parsed.query or '')
            if qs.get('v') and qs['v'][0]:
                vid = str(qs['v'][0]).strip()
                if re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
                    return vid
            parts = [p for p in (parsed.path or '').split('/') if p]
            for part in parts:
                if re.fullmatch(r'[A-Za-z0-9_-]{11}', part):
                    return part
        except Exception:
            pass
        return ''

    def _extract_video_id_from_html(self, html_text: str) -> str:
        text = str(html_text or '')
        if not text:
            return ''
        patterns = [
            r'watch\?v=([A-Za-z0-9_-]{11})',
            r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"',
            r'"video_id"\s*:\s*"([A-Za-z0-9_-]{11})"',
            r'/live/([A-Za-z0-9_-]{11})',
            r'/shorts/([A-Za-z0-9_-]{11})',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        return ''

    def _extract_innertube_api_key(self, html_text: str) -> str:
        text = str(html_text or '')
        for pattern in (
            r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"',
            r'"innertubeApiKey"\s*:\s*"([^"]+)"',
        ):
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()
        return ''

    def _extract_innertube_client_version(self, html_text: str) -> str:
        text = str(html_text or '')
        for pattern in (
            r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"',
            r'"clientVersion"\s*:\s*"([^"]+)"',
        ):
            m = re.search(pattern, text)
            if m:
                value = m.group(1).strip()
                if value:
                    return value
        return self._web_client_version

    def _extract_live_chat_continuation(self, html_text: str) -> str:
        text = str(html_text or '')
        if not text:
            return ''
        live_idx = text.find('liveChatRenderer')
        windows: list[str] = []
        if live_idx >= 0:
            windows.append(text[live_idx:live_idx + 250000])
        windows.append(text)
        patterns = [
            r'"reloadContinuationData"\s*:\s*\{[^{}]*"continuation"\s*:\s*"([^"]+)"',
            r'"invalidationContinuationData"\s*:\s*\{[^{}]*"continuation"\s*:\s*"([^"]+)"',
            r'"timedContinuationData"\s*:\s*\{[^{}]*"continuation"\s*:\s*"([^"]+)"',
            r'"continuation"\s*:\s*"([^"]+)"',
        ]
        for window in windows:
            for pattern in patterns:
                for m in re.finditer(pattern, window, flags=re.DOTALL):
                    token = m.group(1).strip()
                    if token and len(token) > 20:
                        return token
        return ''

    def _extract_text_runs(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return ''
        if value.get('simpleText') is not None:
            return str(value.get('simpleText') or '')
        runs = value.get('runs')
        if isinstance(runs, list):
            return ''.join(str(run.get('text') or '') for run in runs if isinstance(run, dict))
        return ''

    def _resolve_active_broadcast_from_web_live_chat(self, settings: dict[str, Any]) -> tuple[str, str, int | None, str]:
        # Last fallback for reading only: avoid Data API videos.list/liveChatId when
        # Google answers 403 although the public stream is clearly live.
        # The normal watch page often no longer contains the chat continuation. In
        # that case try YouTube's public popout chat page for the exact live video.
        last_error = ''
        for url in self._channel_live_urls(settings):
            try:
                final_url, html_text = self._public_get_text(url, timeout=6.0)
                video_id = self._video_id_from_text(final_url) or self._extract_video_id_from_html(html_text)
                if not video_id:
                    continue

                pages: list[tuple[str, str]] = [('channel-live-page', html_text)]
                try:
                    _watch_final, watch_html = self._public_get_text(f'https://www.youtube.com/watch?v={video_id}', timeout=6.0)
                    pages.append(('watch-page', watch_html))
                except Exception as exc:
                    last_error = f'watch page for {video_id}: {self._http_error_short(exc)}'

                # This is the important part: live_chat/popout is where YouTube usually
                # keeps the innertube key + continuation now. Without this the fallback
                # can find the live video but has no way to poll chat messages.
                for chat_url in (
                    f'https://www.youtube.com/live_chat?is_popout=1&v={video_id}',
                    f'https://www.youtube.com/live_chat?v={video_id}',
                ):
                    try:
                        _chat_final, chat_html = self._public_get_text(chat_url, timeout=6.0)
                        pages.append((chat_url, chat_html))
                    except Exception as exc:
                        last_error = f'{chat_url}: {self._http_error_short(exc)}'

                best_api_key = ''
                best_continuation = ''
                best_client_version = ''
                best_source = ''
                for source_name, page_html in pages:
                    api_key = self._extract_innertube_api_key(page_html)
                    continuation = self._extract_live_chat_continuation(page_html)
                    client_version = self._extract_innertube_client_version(page_html)
                    if api_key and not best_api_key:
                        best_api_key = api_key
                    if client_version and not best_client_version:
                        best_client_version = client_version
                    if continuation:
                        best_continuation = continuation
                        best_source = source_name
                    if best_api_key and best_continuation:
                        break

                if best_api_key and best_continuation:
                    self._web_video_id = video_id
                    self._web_api_key = best_api_key
                    self._web_continuation = best_continuation
                    self._web_client_version = best_client_version or self._web_client_version
                    return '__web_chat__', video_id, None, f'videoId={video_id}, status=web-live-chat, source={best_source or url}'
                last_error = f'found video {video_id}, but no live chat continuation/api key was present on /watch or /live_chat'
            except Exception as exc:
                last_error = f'{url}: {self._http_error_short(exc)}'
                continue
        if last_error:
            self._last_lookup_error = f'web live-chat fallback failed: {last_error}'
        return '', '', None, ''

    def _youtubei_request_live_chat(self) -> dict[str, Any]:
        if not self._web_api_key or not self._web_continuation:
            raise RuntimeError('Missing YouTube web live-chat continuation.')
        url = 'https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?' + urllib.parse.urlencode({'key': self._web_api_key, 'prettyPrint': 'false'})
        body = {
            'context': {
                'client': {
                    'clientName': 'WEB',
                    'clientVersion': self._web_client_version or '2.20240601.00.00',
                    'hl': 'de',
                    'gl': 'DE',
                }
            },
            'continuation': self._web_continuation,
        }
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36',
            'Origin': 'https://www.youtube.com',
            'Referer': f'https://www.youtube.com/watch?v={self._web_video_id}',
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        return json.loads(raw or '{}')

    def _list_web_chat_messages(self) -> dict[str, Any]:
        data = self._youtubei_request_live_chat()
        root = data.get('continuationContents') if isinstance(data.get('continuationContents'), dict) else {}
        live_cont = root.get('liveChatContinuation') if isinstance(root.get('liveChatContinuation'), dict) else {}
        for cont in live_cont.get('continuations') or []:
            if not isinstance(cont, dict):
                continue
            for key in ('invalidationContinuationData', 'timedContinuationData', 'reloadContinuationData'):
                payload = cont.get(key)
                if isinstance(payload, dict) and payload.get('continuation'):
                    self._web_continuation = str(payload.get('continuation') or '').strip()
                    break
        items: list[dict[str, Any]] = []
        actions = live_cont.get('actions')
        if isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict):
                    continue
                add = action.get('addChatItemAction') if isinstance(action.get('addChatItemAction'), dict) else {}
                item = add.get('item') if isinstance(add.get('item'), dict) else {}
                renderer = item.get('liveChatTextMessageRenderer') if isinstance(item.get('liveChatTextMessageRenderer'), dict) else None
                if renderer is None:
                    renderer = item.get('liveChatPaidMessageRenderer') if isinstance(item.get('liveChatPaidMessageRenderer'), dict) else None
                if not isinstance(renderer, dict):
                    continue
                msg_id = str(renderer.get('id') or action.get('clientId') or '').strip()
                message = self._normalize_text(self._extract_text_runs(renderer.get('message')))
                author = self._normalize_text(self._extract_text_runs(renderer.get('authorName'))) or 'YouTube'
                timestamp = str(renderer.get('timestampUsec') or '').strip()
                published = ''
                if timestamp.isdigit():
                    try:
                        published = datetime.fromtimestamp(int(timestamp) / 1000000.0, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
                    except Exception:
                        published = ''
                if not msg_id:
                    msg_id = f'web-{hash((author, message, timestamp))}'
                if message:
                    items.append({
                        'id': msg_id,
                        'snippet': {
                            'displayMessage': message,
                            'publishedAt': published,
                            'textMessageDetails': {'messageText': message},
                        },
                        'authorDetails': {'displayName': author},
                    })
        return {'items': items, 'pollingIntervalMillis': 2500}

    def _public_get_text(self, url: str, timeout: float = 6.0) -> tuple[str, str]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = str(getattr(resp, 'url', url) or url)
            raw = resp.read(900000).decode('utf-8', errors='replace')
        return final_url, raw

    def _channel_live_urls(self, settings: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        refs = [
            settings.get('live_reference'),
            settings.get('live_url'),
            settings.get('stream_url'),
        ]
        handle_values = [
            settings.get('main_account'),
            settings.get('channel'),
            settings.get('main_channel_custom_url'),
        ]
        channel_values = [
            settings.get('broadcaster_channel_id'),
            settings.get('main_channel_id'),
        ]
        for ref in refs:
            ref_text = str(ref or '').strip()
            if ref_text.startswith('http'):
                urls.append(ref_text)
        for handle in handle_values:
            h = str(handle or '').strip().strip('/')
            if not h:
                continue
            if h.startswith('http'):
                urls.append(h.rstrip('/') + '/live')
                continue
            h = h.lstrip('@').strip()
            if h:
                urls.append(f'https://www.youtube.com/@{h}/live')
        for channel_id in channel_values:
            cid = str(channel_id or '').strip()
            if cid:
                urls.append(f'https://www.youtube.com/channel/{cid}/live')
        # stable order, no duplicates
        out: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out

    def _resolve_active_broadcast_from_public_live_page(self, settings: dict[str, Any]) -> tuple[str, str, int | None, str]:
        # Robust fallback: YouTube's /live page is often updated before
        # liveBroadcasts.list/search.list expose the activeLiveChatId reliably.
        # It is public, cheap, and then we still use the OAuth API for the real chat id.
        last_error = ''
        explicit_ref = str(settings.get('live_reference') or settings.get('live_url') or settings.get('stream_url') or '').strip()
        explicit_video = self._video_id_from_text(explicit_ref)
        candidates: list[tuple[str, str]] = []
        if explicit_video:
            candidates.append((explicit_video, 'configured-live-reference'))
        for url in self._channel_live_urls(settings):
            try:
                final_url, html_text = self._public_get_text(url, timeout=6.0)
                video_id = self._video_id_from_text(final_url) or self._extract_video_id_from_html(html_text)
                if video_id:
                    candidates.append((video_id, url))
            except Exception as exc:
                last_error = f'{url}: {self._http_error_short(exc)}'
                continue
        seen: set[str] = set()
        for video_id, source in candidates:
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            try:
                chat_id, viewers, title = self._video_live_details(settings, video_id)
            except Exception as exc:
                last_error = f'videos.list failed for public live candidate {video_id}: {self._http_error_short(exc)}'
                continue
            if chat_id:
                return chat_id, video_id, viewers, f'videoId={video_id}, status=public-live-page, source={source}, title={title or "?"}'
        if last_error:
            self._last_lookup_error = f'public /live lookup failed: {last_error}'
        return '', '', None, ''

    def _resolve_active_broadcast_from_live_broadcasts(self, settings: dict[str, Any], *, allow_fallback_all: bool = False) -> tuple[str, str, int | None, str]:
        # Main path: this is the broadcaster-owned live endpoint and it usually exposes
        # snippet.liveChatId directly. Never turn lookup 400s into plugin errors; OAuth
        # can be valid while no current chat is resolvable yet.
        rows = self._broadcasts_for_status(settings, 'active')
        if not rows and allow_fallback_all:
            # Manual send fallback only: ask for all broadcasts and filter live/testing rows locally.
            rows = self._broadcasts_for_status(settings, 'all')

        candidates = sorted(rows, key=self._broadcast_sort_key)
        for item in candidates:
            if not isinstance(item, dict):
                continue
            status = item.get('status') if isinstance(item.get('status'), dict) else {}
            snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
            life = str((status or {}).get('lifeCycleStatus') or '').strip().lower()
            # Only real/current live-ish candidates may start the chat reader. Old/complete
            # or pure ready rows must not create stale liveChatId/pageToken loops.
            if life and life not in {'live', 'testing', 'liveStarting'}:
                continue
            video_id = self._get_broadcast_video_id(item)
            title = str((snippet or {}).get('title') or '').strip()
            chat_id = self._broadcast_live_chat_id(item)
            if chat_id:
                viewers = self._video_viewers_only(settings, video_id) if video_id else None
                return chat_id, video_id, viewers, f'videoId={video_id or "?"}, status={life or "active"}, source=liveBroadcasts, title={title or "?"}'
            if video_id:
                try:
                    video_chat_id, viewers, video_title = self._video_live_details(settings, video_id)
                    if video_chat_id:
                        return video_chat_id, video_id, viewers, f'videoId={video_id}, status={life or "active"}, source=videos, title={video_title or title or "?"}'
                except urllib.error.HTTPError as exc:
                    self._last_lookup_error = f'videos.list failed for broadcast {video_id}: {self._http_error_short(exc)}'
                    continue
                except Exception as exc:
                    self._last_lookup_error = f'videos.list failed for broadcast {video_id}: {exc}'
                    continue
        return '', '', None, ''

    def _resolve_active_broadcast_from_search(self, settings: dict[str, Any]) -> tuple[str, str, int | None, str]:
        try:
            ok, channel_id, channel_title = self._channel_info(settings, 'main')
        except Exception as exc:
            self._last_lookup_error = f'channels.list failed during live search: {self._http_error_short(exc)}'
            return '', '', None, ''
        if not ok or not channel_id:
            return '', '', None, ''
        try:
            data = self._request_json_auth(settings, 'main', SEARCH_URL, params={
                'part': 'snippet',
                'channelId': channel_id,
                'eventType': 'live',
                'type': 'video',
                'order': 'date',
                'maxResults': 5,
            })
        except Exception as exc:
            self._last_lookup_error = f'search.list live failed: {self._http_error_short(exc)}'
            return '', '', None, ''
        rows = data.get('items') if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return '', '', None, ''
        for item in rows:
            if not isinstance(item, dict):
                continue
            ident = item.get('id') if isinstance(item.get('id'), dict) else {}
            snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
            video_id = str((ident or {}).get('videoId') or '').strip()
            title = str((snippet or {}).get('title') or '').strip()
            if not video_id:
                continue
            try:
                chat_id, viewers, video_title = self._video_live_details(settings, video_id)
            except urllib.error.HTTPError:
                continue
            if chat_id:
                return chat_id, video_id, viewers, f'videoId={video_id}, status=live-search, channel={channel_title}, title={video_title or title or "?"}'
        return '', '', None, ''

    def _resolve_live_chat_id(self, settings: dict[str, Any], *, force: bool = False, background: bool = True) -> str:
        if self._live_chat_id and not force:
            return self._live_chat_id
        # Normal autoconnect/live-wait path must stay cheap: one official
        # liveBroadcasts(active) check per interval. No search.list, no "all"
        # broadcast sweep, and no repeated videos.list when we are simply offline.
        chat_id, video_id, viewers, debug = self._resolve_active_broadcast_from_live_broadcasts(settings, allow_fallback_all=not background)

        if not chat_id and not background:
            chat_id, video_id, viewers, debug = self._resolve_active_broadcast_from_public_live_page(settings)
        if not chat_id and not background:
            chat_id, video_id, viewers, debug = self._resolve_active_broadcast_from_search(settings)
        if not chat_id and not background:
            chat_id, video_id, viewers, debug = self._resolve_active_broadcast_from_web_live_chat(settings)

        if chat_id:
            self._live_chat_id = chat_id
            if chat_id != '__web_chat__':
                self._api_live_chat_id = chat_id
            self._broadcast_video_id = video_id
            self._broadcast_debug = debug
            if viewers is not None:
                self._last_viewer_count = None
            return chat_id

        self._live_chat_id = ''
        self._api_live_chat_id = ''
        self._broadcast_video_id = ''
        self._broadcast_debug = ''
        detail = f' Last lookup: {self._last_lookup_error}' if self._last_lookup_error else ''
        raise RuntimeError('No active YouTube livestream chat found yet.' + detail)

    def _fetch_viewer_count(self, settings: dict[str, Any]) -> int | None:
        if self._live_chat_id == '__web_chat__':
            return None
        video_id = str(self._broadcast_video_id or '').strip()
        if not video_id:
            try:
                self._resolve_live_chat_id(settings, force=True)
                video_id = str(self._broadcast_video_id or '').strip()
            except Exception:
                return None
        if not video_id:
            return None
        try:
            _chat_id, viewers, _title = self._video_live_details(settings, video_id)
            return 0 if viewers is None else max(int(viewers), 0)
        except Exception:
            return None

    def _emit_viewer_count(self, host: PluginHost, channel: str, viewer_count: int) -> None:
        viewer_count = int(viewer_count or 0)
        if self._last_viewer_count == viewer_count:
            return
        self._last_viewer_count = viewer_count
        payload = {
            'platform': 'youtube',
            'username': '',
            'text': str(viewer_count),
            'channel': channel or 'youtube',
            'message_type': 'viewer_count',
            'type': 'viewer_count',
            'event_type': 'viewer_count',
            'source_plugin_id': self.plugin_id,
            'source': self.plugin_id,
            'show_in_desktop': False,
            'show_in_obs': True,
            'metric_only': True,
            'viewer_count': viewer_count,
        }
        try:
            host.emit_message(self.plugin_id, payload)
        except Exception:
            pass
        try:
            host.emit_metric(self.plugin_id, payload)
        except Exception:
            pass
        try:
            host.log(self.plugin_id, f'YouTube viewer_count: {viewer_count}')
        except Exception:
            pass

    def _maybe_poll_metrics(self, host: PluginHost, settings: dict[str, Any], channel: str, *, force: bool = False) -> None:
        if not self._as_bool(settings.get('viewer_count_enabled'), True):
            return
        now = time.monotonic()
        if not force and (now - self._last_metrics_poll) < 120.0:
            return
        self._last_metrics_poll = now
        viewer_count = self._fetch_viewer_count(settings)
        if viewer_count is None:
            return
        self._emit_viewer_count(host, channel, viewer_count)

    def _list_messages(self, settings: dict[str, Any], live_chat_id: str, page_token: str = '') -> dict[str, Any]:
        if live_chat_id == '__web_chat__':
            return self._list_web_chat_messages()
        params = {
            'part': 'id,snippet,authorDetails',
            'liveChatId': live_chat_id,
            'maxResults': 200,
        }
        if page_token:
            params['pageToken'] = page_token
        return self._request_json_auth(settings, 'main', LIVE_CHAT_MESSAGES_URL, params=params)

    def _extract_poll_seconds(self, payload: dict[str, Any], fallback: float = 3.0) -> float:
        try:
            ms = int(payload.get('pollingIntervalMillis') or 0)
            if ms > 0:
                return max(ms / 1000.0, 1.0)
        except Exception:
            pass
        return max(float(fallback), 1.0)

    def _message_payload(self, item: dict[str, Any], channel: str) -> dict[str, Any] | None:
        msg_id = str(item.get('id') or '').strip()
        snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
        author = item.get('authorDetails') if isinstance(item.get('authorDetails'), dict) else {}
        text_details = snippet.get('textMessageDetails') if isinstance(snippet.get('textMessageDetails'), dict) else {}
        text = self._normalize_text(snippet.get('displayMessage') or text_details.get('messageText') or '')
        if not text:
            return None
        name = str(author.get('displayName') or 'YouTube').strip().lstrip('@').strip()
        safe_text = html.escape(text)
        return {
            'platform': 'youtube',
            'username': name,
            'display_name': name,
            'text': text,
            'message': text,
            'content': text,
            'comment': text,
            'overlay_html': f'<div style="text-align:left;white-space:normal;line-height:1.08;margin:0;padding:0;">{safe_text}</div>',
            'channel': channel,
            'message_id': msg_id,
            'message_type': 'chat',
            'type': 'chat',
            'event_type': 'chat',
            'source_plugin_id': self.plugin_id,
            'source': self.plugin_id,
            'published_at': str((snippet or {}).get('publishedAt') or '').strip(),
            'show_in_desktop': True,
            'show_in_obs': True,
        }

    def _is_startup_backlog(self, item: dict[str, Any]) -> bool:
        snippet = item.get('snippet') if isinstance(item.get('snippet'), dict) else {}
        published = self._yt_time_to_epoch((snippet or {}).get('publishedAt'))
        if published <= 0 or self._connect_started_at <= 0:
            return True
        # Kleine Toleranz, damit Nachrichten direkt beim Verbinden nicht versehentlich verschwinden.
        return published < (self._connect_started_at - 2.0)

    def send_message(self, text: str, settings: dict | None = None, host: PluginHost | None = None) -> tuple[bool, str]:
        msg = self._normalize_text(text)
        if not msg:
            return False, 'YouTube message is empty.'
        final_settings = self._merge_platform_settings(settings or {}, host or getattr(self, '_host', None))
        if not self._as_bool(final_settings.get('write_enabled'), True):
            return False, 'YouTube writing is disabled in the main tool.'
        try:
            with self._send_lock:
                live_chat_id = self._resolve_live_chat_id(final_settings)
                body = {
                    'snippet': {
                        'liveChatId': live_chat_id,
                        'type': 'textMessageEvent',
                        'textMessageDetails': {'messageText': msg},
                    }
                }
                self._request_json_auth(final_settings, 'bot', LIVE_CHAT_MESSAGES_URL, method='POST', params={'part': 'snippet'}, body=body)
            return True, 'YouTube message sent.'
        except Exception as exc:
            return False, f'YouTube send failed: {exc}'

    def is_connected(self) -> bool:
        return bool(self._connected)

    def test_connection(self, settings):
        host = getattr(self, '_host', None)
        settings = self._merge_platform_settings(settings, host)
        if not self._as_bool(settings.get('read_enabled'), True) and not self._as_bool(settings.get('write_enabled'), True):
            return False, 'YouTube reading/writing is disabled in the main tool.'
        main_token = self._token_for(settings, 'main')
        bot_token = self._token_for(settings, 'bot')
        if not main_token:
            return False, 'Missing YouTube main OAuth token from main tool.'
        if self._as_bool(settings.get('write_enabled'), True) and not bot_token:
            return False, 'Missing YouTube bot OAuth token from main tool.'
        main_name = self._clean_account(settings.get('main_account') or settings.get('channel') or 'main')
        bot_name = self._clean_account(settings.get('bot_account') or settings.get('bot_username') or 'bot')
        return True, f'YouTube OAuth data available · main={main_name or "main"} · bot={bot_name or "bot"}'

    def stop(self, *args, **kwargs) -> None:
        self._connected = False
        try:
            super().stop(*args, **kwargs)
        except TypeError:
            super().stop()

    def _set_waiting_status(self, host: PluginHost, detail: str = '') -> None:
        text = 'YouTube OAuth OK · waiting for active livestream chat'
        if detail:
            text += f' · {detail}'
        host.set_status(self.plugin_id, PluginStatus('connected', text))

    def _emit_live_state(self, host: PluginHost, channel: str, is_live: bool) -> None:
        payload = {
            'platform': 'youtube',
            'channel': channel or 'youtube',
            'message_type': 'is_live',
            'is_live': bool(is_live),
            'metric_only': True,
            'source_plugin_id': self.plugin_id,
            'source': self.plugin_id,
        }
        try:
            host.emit_metric(self.plugin_id, payload)
        except Exception:
            pass

    def _reset_chat_runtime(self) -> None:
        self._live_chat_id = ''
        self._broadcast_video_id = ''
        self._broadcast_debug = ''
        self._next_page_token = ''
        self._seen_message_ids = set()
        self._last_viewer_count = None
        self._last_metrics_poll = 0.0
        self._web_video_id = ''
        self._web_api_key = ''
        self._web_continuation = ''

    def _format_wait_log(self, exc: Exception) -> str:
        if isinstance(exc, urllib.error.HTTPError):
            code = int(getattr(exc, 'code', 0) or 0)
            reason = str(getattr(exc, 'reason', '') or '').strip()
            if reason:
                return f'Waiting for YouTube live chat: HTTP {code} · {reason[:500]}'
            return f'Waiting for YouTube live chat: HTTP {code}'
        
        text = str(exc)
        if 'handshake operation timed out' in text or 'timed out' in text or 'timeout' in text.lower():
            return 'Waiting for YouTube live chat: network timeout while contacting YouTube API'
        return f'Waiting for YouTube live chat: {exc}'

    def run(self, settings, host: PluginHost):
        self._host = host
        settings = self._merge_platform_settings(settings, host)
        channel = self._clean_account(settings.get('main_account') or settings.get('channel') or 'youtube') or 'youtube'
        if not self._as_bool(settings.get('read_enabled'), True):
            raise RuntimeError('YouTube reading is disabled in the main tool.')

        main_token = self._token_for(settings, 'main')
        if not main_token:
            raise RuntimeError('Missing YouTube main OAuth token from main tool.')
        if self._as_bool(settings.get('write_enabled'), True) and not self._token_for(settings, 'bot'):
            host.log(self.plugin_id, 'YouTube bot token is missing; reading can still run, writing will fail until Bot OAuth exists.')

        self._connected = True
        self._reset_chat_runtime()
        self._connect_started_at = time.time()
        skip_backlog = self._as_bool(settings.get('startup_skip_backlog'), True)
        poll_seconds = 3.0
        try:
            resolve_retry_seconds = max(60.0, min(300.0, float(settings.get('live_check_interval_seconds') or 90)))
        except Exception:
            resolve_retry_seconds = 90.0
        next_resolve_at = 0.0
        live_chat_id = ''
        first_poll = True
        last_wait_log = -9999.0

        self._set_waiting_status(host)
        self._emit_live_state(host, channel, False)
        host.log(self.plugin_id, f'YouTube plugin enabled v{self.version}. OAuth ready; live check every {int(resolve_retry_seconds)}s until a stream is active.')

        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if not live_chat_id:
                    if now < next_resolve_at:
                        time.sleep(0.25)
                        continue
                    next_resolve_at = now + resolve_retry_seconds
                    try:
                        live_chat_id = self._resolve_live_chat_id(settings, force=True, background=True)
                    except Exception as resolve_exc:
                        # No active stream is not an error for the plugin. The OAuth connection is fine;
                        # the chat reader simply waits until YouTube exposes an activeLiveChatId.
                        self._reset_chat_runtime()
                        self._connected = True
                        self._set_waiting_status(host)
                        self._emit_live_state(host, channel, False)
                        if (now - last_wait_log) > max(120.0, resolve_retry_seconds):
                            host.log(self.plugin_id, self._format_wait_log(resolve_exc))
                            last_wait_log = now
                        time.sleep(0.25)
                        continue

                    self._connected = True
                    first_poll = True
                    self._connect_started_at = time.time()
                    host.set_status(self.plugin_id, PluginStatus('connected', 'Reading YouTube live chat'))
                    self._emit_live_state(host, channel, True)
                    if self._broadcast_debug:
                        host.log(self.plugin_id, f'Resolved YouTube broadcast: {self._broadcast_debug}')
                    if live_chat_id == '__web_chat__':
                        host.log(self.plugin_id, 'Found YouTube web live-chat fallback. Reading chat without videos.list.')
                    else:
                        host.log(self.plugin_id, f'Found YouTube liveChatId: {live_chat_id[:10]}...')
                    self._maybe_poll_metrics(host, settings, channel, force=True)

                payload = self._list_messages(settings, live_chat_id, self._next_page_token)
                self._next_page_token = str(payload.get('nextPageToken') or self._next_page_token or '')
                poll_seconds = self._extract_poll_seconds(payload, poll_seconds)
                rows = payload.get('items') if isinstance(payload, dict) else []
                self._maybe_poll_metrics(host, settings, channel)
                if isinstance(rows, list):
                    for item in rows:
                        if not isinstance(item, dict):
                            continue
                        msg_id = str(item.get('id') or '').strip()
                        if msg_id and msg_id in self._seen_message_ids:
                            continue
                        if msg_id:
                            self._seen_message_ids.add(msg_id)
                        if first_poll and skip_backlog and self._is_startup_backlog(item):
                            continue
                        out = self._message_payload(item, channel)
                        if out:
                            host.emit_message(self.plugin_id, out)
                            host.log(self.plugin_id, f'YouTube chat message: {out.get("username", "?")}: {str(out.get("text", ""))[:120]}')
                first_poll = False
                time.sleep(min(max(poll_seconds, 1.0), 10.0))

            except urllib.error.HTTPError as exc:
                if self._stop.is_set():
                    break
                code = int(getattr(exc, 'code', 0) or 0)
                host.log(self.plugin_id, f'YouTube chat warning HTTP {code}: {exc}')
                if code in (400, 404):
                    # Stale liveChatId/pageToken or stream restart. Keep plugin green and re-resolve in background.
                    live_chat_id = ''
                    self._reset_chat_runtime()
                    self._set_waiting_status(host, 'refreshing chat')
                    self._emit_live_state(host, channel, False)
                    next_resolve_at = 0.0
                    time.sleep(1.0)
                    continue
                if code in (401, 403):
                    try:
                        self._refresh_token(settings, 'main')
                    except Exception:
                        pass
                    time.sleep(3.0)
                    continue
                time.sleep(max(poll_seconds, 5.0))

            except Exception as exc:
                if self._stop.is_set():
                    break
                host.log(self.plugin_id, f'YouTube chat warning: {exc}')
                live_chat_id = ''
                self._reset_chat_runtime()
                self._set_waiting_status(host, 'retrying')
                self._emit_live_state(host, channel, False)
                next_resolve_at = time.monotonic() + 5.0
                time.sleep(1.0)

        self._connected = False
        host.set_status(self.plugin_id, PluginStatus('disconnected', 'YouTube chat stopped.'))


def create_plugin():
    return YouTubeChatPlugin()
