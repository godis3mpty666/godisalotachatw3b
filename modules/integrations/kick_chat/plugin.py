from __future__ import annotations

import asyncio
import base64
import hashlib
import contextlib
import json
import os
import re
import socket
import struct
import subprocess
import time
import tempfile
import urllib.parse
import urllib.request
from html import escape as _html_escape
from pathlib import Path
from typing import Any

import requests

from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin

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
    version = '2.1.4'
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
        self._connected = False
        self._write_ready = False
        self._active_account = ''

    # Wichtig: Keine OAuth-/Token-/Client-Felder mehr im Plugin-Dialog.
    # Das Maintool verwaltet Kick Main/Bot OAuth zentral und spiegelt nur die nötigen Werte.
    def settings_schema(self):
        return [
            {'key': 'channel', 'label': 'Kick Channel', 'placeholder': 'godis3mpty'},
            {'key': 'enable_browser_chatroom_resolver', 'label': 'Browser-Resolver fuer Chatroom-ID nutzen', 'type': 'checkbox'},
            {'key': 'diag_log', 'label': 'Diagnosis Log', 'type': 'multiline', 'placeholder': ''},
            {'key': 'diag_path', 'label': 'Diagnosis file path', 'placeholder': ''},
        ]

    def default_settings(self):
        return {
            'channel': '',
            'enable_browser_chatroom_resolver': False,
            'diag_log': self._read_diag() or 'No diagnosis yet. Press Test or Connect once.',
            'diag_path': str(self._diag_path()),
            'autoconnect': False,
        }

    def _data_dir(self) -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if parent.name.lower() == 'modules':
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
            self._diag_path().parent.mkdir(parents=True, exist_ok=True)
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
        # Core/platform settings own OAuth, account names and the watched channel.
        # Plugin-local settings are only behavior/diagnostic knobs; stale local
        # channel/token values must not redirect Kick away from the main channel.
        merged: dict[str, Any] = dict(self._host_platform_settings(host))
        if isinstance(settings, dict):
            local_keys = {'enable_browser_chatroom_resolver', 'diag_log', 'diag_path', 'autoconnect'}
            for key in local_keys:
                value = settings.get(key)
                if value not in (None, ''):
                    merged[key] = value
            fallback_keys = {
                'main_access_token',
                'main_refresh_token',
                'access_token',
                'refresh_token',
                'main',
                'main_account',
                'channel',
                'main_username',
                'main_user_id',
                'channel_slug',
                'broadcaster_user_id',
                'broadcaster_id',
                'channel_id',
                'chatroom_id',
                'chatroom_channel',
                'bot',
                'bot_account',
                'bot_username',
                'bot_user_id',
                'read_enabled',
                'write_enabled',
                'enabled',
                'scopes',
                'main_scopes',
            }
            for key in fallback_keys:
                value = settings.get(key)
                if value not in (None, '') and merged.get(key) in (None, ''):
                    merged[key] = value
        return merged

    def _clean_login(self, value: Any) -> str:
        return str(value or '').strip().lstrip('@#').strip().lower()

    def _clean_token(self, value: Any) -> str:
        token = str(value or '').strip()
        if token.lower().startswith('bearer '):
            token = token[7:]
        return token.strip()

    def _token_for_send(self, settings: dict[str, Any]) -> tuple[str, str]:
        bot_token = self._clean_token(settings.get('access_token'))
        if bot_token:
            return bot_token, 'bot'
        main_token = self._clean_token(settings.get('main_access_token'))
        if main_token:
            return main_token, 'main'
        return '', ''

    def _tokens_for_send(self, settings: dict[str, Any]) -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []
        bot_token = self._clean_token(settings.get('access_token'))
        main_token = self._clean_token(settings.get('main_access_token'))
        if bot_token:
            tokens.append((bot_token, 'bot'))
        if main_token and main_token != bot_token:
            tokens.append((main_token, 'main'))
        return tokens

    def _channel_from_settings(self, settings: dict[str, Any]) -> str:
        return self._clean_login(
            settings.get('channel')
            or settings.get('main')
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

    def _find_browser_exe(self, settings: dict[str, Any]) -> str:
        raw = str(settings.get('browser_path') or '').strip().strip('"')
        candidates = []
        if raw:
            candidates.append(raw)
        for env_key in ('ProgramFiles', 'ProgramFiles(x86)', 'LocalAppData'):
            base = os.environ.get(env_key)
            if not base:
                continue
            candidates.extend([
                str(Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'),
                str(Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'),
                str(Path(base) / 'Chromium' / 'Application' / 'chrome.exe'),
            ])
        for item in candidates:
            if item and Path(item).exists():
                return item
        return ''

    def _free_local_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', 0))
            return int(sock.getsockname()[1])

    def _cdp_json(self, port: int, path: str, timeout: float = 2.0) -> Any:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
        return json.loads(raw or '{}')

    class _MiniWebSocket:
        def __init__(self, url: str, timeout: float = 5.0):
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'ws' or not parsed.hostname:
                raise RuntimeError(f'unsupported websocket url: {url}')
            self._sock = socket.create_connection((parsed.hostname, int(parsed.port or 80)), timeout=timeout)
            self._sock.settimeout(timeout)
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            key = base64.b64encode(os.urandom(16)).decode('ascii')
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {parsed.hostname}:{int(parsed.port or 80)}\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\n'
                'Sec-WebSocket-Version: 13\r\n'
                f'Origin: http://{parsed.hostname}:{int(parsed.port or 80)}\r\n'
                '\r\n'
            ).encode('ascii')
            self._sock.sendall(req)
            response = b''
            while b'\r\n\r\n' not in response:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            head = response.decode('iso-8859-1', 'replace')
            if ' 101 ' not in head.split('\r\n', 1)[0]:
                raise RuntimeError('DevTools websocket handshake failed: ' + head.split('\r\n', 1)[0])
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
            if expected not in head:
                raise RuntimeError('DevTools websocket accept key mismatch')

        def gettimeout(self):
            return self._sock.gettimeout()

        def settimeout(self, value):
            self._sock.settimeout(value)

        def close(self):
            with contextlib.suppress(Exception):
                self._sock.close()

        def _read_exact(self, size: int) -> bytes:
            data = b''
            while len(data) < size:
                chunk = self._sock.recv(size - len(data))
                if not chunk:
                    raise RuntimeError('DevTools websocket closed')
                data += chunk
            return data

        def send(self, text: str) -> None:
            payload = str(text or '').encode('utf-8')
            first = 0x81
            if len(payload) < 126:
                header = bytes([first, 0x80 | len(payload)])
            elif len(payload) < 65536:
                header = bytes([first, 0x80 | 126]) + struct.pack('!H', len(payload))
            else:
                header = bytes([first, 0x80 | 127]) + struct.pack('!Q', len(payload))
            mask = os.urandom(4)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            self._sock.sendall(header + mask + masked)

        def recv(self) -> str:
            while True:
                b1, b2 = self._read_exact(2)
                opcode = b1 & 0x0F
                length = b2 & 0x7F
                if length == 126:
                    length = struct.unpack('!H', self._read_exact(2))[0]
                elif length == 127:
                    length = struct.unpack('!Q', self._read_exact(8))[0]
                mask = self._read_exact(4) if (b2 & 0x80) else b''
                payload = self._read_exact(length) if length else b''
                if mask:
                    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                if opcode == 0x1:
                    return payload.decode('utf-8', 'replace')
                if opcode == 0x8:
                    raise RuntimeError('DevTools websocket closed')
                if opcode == 0x9:
                    self._sock.sendall(bytes([0x8A, len(payload)]) + payload)

    def _cdp_connect(self, ws_url: str):
        if websocket is not None:
            try:
                return websocket.create_connection(ws_url, timeout=5)
            except Exception as exc:
                self._append_diag(f'DevTools websocket-client failed, using builtin client: {exc}')
        return self._MiniWebSocket(ws_url, timeout=5)

    def _cdp_call(self, ws, method: str, params: dict[str, Any] | None = None, *, timeout: float = 8.0) -> dict[str, Any]:
        msg_id = int(time.time() * 1000) % 1000000000
        ws.send(json.dumps({'id': msg_id, 'method': method, 'params': params or {}}))
        end = time.time() + max(0.5, timeout)
        old_timeout = None
        with contextlib.suppress(Exception):
            old_timeout = ws.gettimeout()
            ws.settimeout(0.5)
        try:
            while time.time() < end:
                try:
                    raw = ws.recv()
                except Exception:
                    continue
                with contextlib.suppress(Exception):
                    payload = json.loads(raw)
                    if payload.get('id') == msg_id:
                        return payload
        finally:
            with contextlib.suppress(Exception):
                ws.settimeout(old_timeout)
        return {}

    def _extract_chatroom_from_text(self, text: str, *, chatroom_url: bool = False) -> dict[str, Any]:
        body = str(text or '')
        if not body:
            return {}
        with contextlib.suppress(Exception):
            obj = json.loads(body)
            data = self._extract_channel_data_from_any(obj)
            if chatroom_url and 'chatroom_id' not in data:
                found = self._search_value(obj, ('id',))
                if found not in (None, ''):
                    data['chatroom_id'] = found
            if data:
                return data
        data = self._extract_channel_data_from_html(body)
        if chatroom_url and 'chatroom_id' not in data:
            match = re.search(r'"id"\s*:\s*"?(?P<v>\d+)"?', body, re.IGNORECASE)
            if match:
                data['chatroom_id'] = match.group('v')
        return data

    def _collect_browser_network_chatroom(self, ws, channel: str, *, seconds: float = 12.0) -> dict[str, Any]:
        candidates: dict[str, str] = {}
        end = time.time() + max(2.0, seconds)
        with contextlib.suppress(Exception):
            ws.settimeout(0.5)
        while time.time() < end:
            try:
                raw = ws.recv()
            except Exception:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            method = str(msg.get('method') or '')
            params = msg.get('params') if isinstance(msg.get('params'), dict) else {}
            if method == 'Network.responseReceived':
                resp = params.get('response') if isinstance(params.get('response'), dict) else {}
                url = str(resp.get('url') or '')
                low = url.lower()
                if 'kick.com' in low and ('chatroom' in low or f'/channels/{channel.lower()}' in low):
                    rid = str(params.get('requestId') or '')
                    if rid:
                        candidates[rid] = url
                        self._append_diag(f'BROWSER NETWORK candidate {url}')
            elif method == 'Network.loadingFinished':
                rid = str(params.get('requestId') or '')
                url = candidates.pop(rid, '')
                if not url:
                    continue
                body_resp = self._cdp_call(ws, 'Network.getResponseBody', {'requestId': rid}, timeout=2)
                body = str(((body_resp.get('result') or {}).get('body') or ''))
                data = self._extract_chatroom_from_text(body, chatroom_url='chatroom' in url.lower())
                self._append_diag(f'BROWSER NETWORK body url={url} chatroom_id={data.get("chatroom_id")} channel_id={data.get("channel_id")}')
                if data.get('chatroom_id'):
                    return data
        return {}

    def _fetch_browser_chatroom_data(self, settings: dict[str, Any], channel: str) -> dict[str, Any]:
        browser = self._find_browser_exe(settings)
        if not browser:
            raise RuntimeError('Chrome/Edge not found for browser resolver')

        port = self._free_local_port()
        profile = Path(tempfile.mkdtemp(prefix='gla_kick_chatroom_'))
        proc = None
        ws = None
        try:
            visible = str(settings.get('browser_resolver_visible') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
            args = [
                browser,
                f'--remote-debugging-port={port}',
                '--remote-allow-origins=*',
                f'--user-data-dir={profile}',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                f'https://kick.com/{urllib.parse.quote(channel)}',
            ]
            if not visible:
                args.insert(4, '--headless=new')
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + 12.0
            version = None
            while time.time() < deadline:
                with contextlib.suppress(Exception):
                    version = self._cdp_json(port, '/json/version', timeout=1.0)
                    if isinstance(version, dict):
                        break
                time.sleep(0.25)
            if not isinstance(version, dict):
                raise RuntimeError('browser debugger did not start')

            tabs = self._cdp_json(port, '/json', timeout=2.0)
            page = next((t for t in tabs if isinstance(t, dict) and t.get('webSocketDebuggerUrl')), None) if isinstance(tabs, list) else None
            if not page:
                raise RuntimeError('browser debugger has no page target')
            ws = self._cdp_connect(page['webSocketDebuggerUrl'])
            self._cdp_call(ws, 'Page.enable', timeout=2)
            self._cdp_call(ws, 'Network.enable', timeout=2)
            self._cdp_call(ws, 'Runtime.enable', timeout=2)
            self._cdp_call(ws, 'Page.navigate', {'url': f'https://kick.com/{urllib.parse.quote(channel)}'}, timeout=2)
            network_data = self._collect_browser_network_chatroom(ws, channel, seconds=12.0)
            if network_data.get('chatroom_id'):
                return network_data
            for _ in range(40):
                loc = self._cdp_call(ws, 'Runtime.evaluate', {'expression': 'location.href', 'returnByValue': True}, timeout=1)
                href = str((((loc.get('result') or {}).get('result') or {}).get('value') or ''))
                if 'kick.com' in href:
                    break
                time.sleep(0.25)
            time.sleep(3.0)

            js = """
            (async () => {
              const urls = [
                `https://kick.com/api/v2/channels/${CHANNEL}/chatroom`,
                `https://kick.com/api/v1/channels/${CHANNEL}/chatroom`,
                `https://kick.com/api/v2/channels/${CHANNEL}`,
                `https://kick.com/${CHANNEL}`
              ];
              let last = null;
              for (const url of urls) {
                try {
                  const r = await fetch(url, {credentials: 'include', headers: {'accept': 'application/json,text/plain,*/*'}});
                  const text = await r.text();
                  last = {url, status: r.status, text: text.slice(0, 120000)};
                  if (r.ok && /chatroom|chatroom_id/i.test(text)) return JSON.stringify(last);
                } catch (e) {
                  last = {url, status: 0, text: String(e)};
                }
              }
              return JSON.stringify(last || {});
            })()
            """.replace('CHANNEL', json.dumps(channel))
            result = self._cdp_call(ws, 'Runtime.evaluate', {'expression': js, 'awaitPromise': True, 'returnByValue': True}, timeout=20)
            value = (((result.get('result') or {}).get('result') or {}).get('value') or '')
            payload = json.loads(value or '{}') if isinstance(value, str) else {}
            text = str(payload.get('text') or '')
            url = str(payload.get('url') or '')
            data = self._extract_chatroom_from_text(text, chatroom_url='chatroom' in url.lower())
            self._append_diag(f'BROWSER CHATROOM url={url} status={payload.get("status")} chatroom_id={data.get("chatroom_id")} channel_id={data.get("channel_id")} text={text[:240]}')
            if data.get('chatroom_id'):
                return data
            raise RuntimeError(f'browser resolver found no chatroom_id; last_url={url} status={payload.get("status")}')
        finally:
            with contextlib.suppress(Exception):
                if ws is not None:
                    ws.close()
            with contextlib.suppress(Exception):
                if proc is not None:
                    proc.terminate()
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(profile, ignore_errors=True)

    def _has_write_credentials(self, settings: dict[str, Any]) -> bool:
        token, _account = self._token_for_send(settings)
        broadcaster_id = self._parse_int(settings.get('broadcaster_user_id') or settings.get('channel_id') or settings.get('main_user_id'))
        return bool(token and broadcaster_id)

    def is_connected(self) -> bool:
        return bool(self._connected or self._write_ready)

    def active_account(self) -> str:
        return self._active_account or 'main'

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
        manual_chatroom_channel = self._clean_login(settings.get('chatroom_channel') or settings.get('chatroom_slug'))
        if manual_chatroom_id is not None and manual_chatroom_channel and manual_chatroom_channel != channel:
            self._append_diag(f'Ignoring cached chatroom_id={manual_chatroom_id} for old channel={manual_chatroom_channel}; current channel={channel}')
            manual_chatroom_id = None

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
            broadcaster_user_id = broadcaster_user_id or bundle.get('broadcaster_user_id')
            channel_id = channel_id or bundle.get('channel_id')
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

        if not chatroom_id and self._as_bool(settings.get('enable_browser_chatroom_resolver'), False):
            try:
                data = self._fetch_browser_chatroom_data(settings, channel)
                broadcaster_user_id = self._parse_int(data.get('broadcaster_user_id')) or broadcaster_user_id
                channel_id = self._parse_int(data.get('channel_id')) or channel_id
                chatroom_id = self._parse_int(data.get('chatroom_id')) or chatroom_id
                if data:
                    source_parts.append('browser_chatroom')
            except Exception as exc:
                self._append_diag(f'browser_chatroom unavailable: {exc}')
        elif not chatroom_id:
            self._append_diag('browser_chatroom skipped: browser resolver disabled')

        source = ' + '.join(source_parts) if source_parts else 'unknown'
        if broadcaster_user_id is not None:
            settings['broadcaster_user_id'] = str(broadcaster_user_id)
        if channel_id is not None:
            settings['channel_id'] = str(channel_id)
        if chatroom_id is not None:
            settings['chatroom_id'] = str(chatroom_id)
            settings['chatroom_channel'] = channel
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
        state = 'connected'
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

    def _emit_chat_item(self, host: PluginHost, channel: str, item: dict[str, Any], seen: dict[str, float]):
        # Kick/Pusher can deliver the same chat line more than once when we subscribe
        # to multiple legacy/realtime channel names for compatibility. Dedupe both
        # by the official message id and by a short-lived normalized fallback
        # signature, because not every payload variant carries the same id field.
        now = time.time()
        try:
            for key, ts in list(seen.items()):
                if now - float(ts or 0.0) > 30.0:
                    seen.pop(key, None)
        except Exception:
            pass

        mid = str(item.get('id') or item.get('message_id') or item.get('uuid') or '').strip()

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

        text_key = re.sub(r'\s+', ' ', (raw_content or content or '').strip().lower())
        keys: list[str] = []
        if mid:
            keys.append(f'id:{mid}')
        if username and text_key:
            keys.append(f'sig:{self._clean_login(username)}:{text_key}')

        for key in keys:
            old_ts = seen.get(key)
            if old_ts is not None and now - float(old_ts or 0.0) <= 10.0:
                return
        for key in keys:
            seen[key] = now

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

    def _handle_ws_message(self, raw: str, host: PluginHost, channel: str, seen: dict[str, float], ws_send=None):
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

        if event in {'pusher:error', 'pusher_internal:subscription_error'}:
            self._append_diag(f'PUSHER ERROR {raw[:700]}')
            with contextlib.suppress(Exception):
                host.log(self.plugin_id, f'pusher error {raw[:500]}')
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
        seen: dict[str, float] = {}
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
        seen: dict[str, float] = {}
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
            self._write_ready = self._has_write_credentials(effective)
            _token, self._active_account = self._token_for_send(effective)
            return True, f'Kick ready: room {chatroom_id} | {live_txt} | {viewer_txt} | {followers_txt} | source={source}'
        if self._has_write_credentials(effective):
            self._write_ready = True
            _token, self._active_account = self._token_for_send(effective)
            return True, f'Kick write ready; realtime chatroom is not available yet | {live_txt} | {viewer_txt} | {followers_txt} | source={source}'
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
        self._connected = False
        self._write_ready = self._has_write_credentials(effective)
        _token, self._active_account = self._token_for_send(effective)

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
                self._write_ready = self._has_write_credentials(effective)
                _token, self._active_account = self._token_for_send(effective)
                if not chatroom_id:
                    # Do not crash into an obsolete manual-chatroom-id message. Kick
                    # sometimes hides the realtime room id for a few seconds after
                    # stream start or behind a flaky website/API response. Keep
                    # retrying silently with a useful status.
                    if self._write_ready:
                        self._status_short(host, 'connected', f'Kick write ready for #{channel}; realtime chatroom pending, retrying in {int(reconnect_delay)}s')
                    else:
                        self._status_short(host, 'warning', f'Kick chatroom not ready for #{channel}; retrying in {int(reconnect_delay)}s')
                    self._append_diag(f'WAIT no chatroom_id channel={channel} broadcaster_user_id={broadcaster_user_id} channel_id={channel_id} source={source}')
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.5, 30.0)
                    continue

                reconnect_delay = 3.0
                self._connected = True
                if websocket is not None:
                    self._run_with_websocket_client(ws_url, int(chatroom_id), host, effective, channel, viewer_poll_interval, channel_id)
                elif websockets is not None:
                    asyncio.run(self._run_with_websockets_async(ws_url, int(chatroom_id), host, effective, channel, viewer_poll_interval, channel_id))
                else:
                    raise RuntimeError('No websocket library available in host app.')
            except Exception as exc:
                self._connected = False
                self._append_diag(f'ws_error={exc}')
                self._status_short(host, 'error', f'Kick reconnect in {int(reconnect_delay)}s | {exc}')
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 30.0)
            else:
                break

        self._connected = False
        self._write_ready = False
        self._status_short(host, 'disconnected', 'Stopped')

    def _send_direct_with_token(self, message: str, settings: dict[str, Any]) -> tuple[bool, str]:
        content = str(message or '').strip()
        if not content:
            return False, 'Kick message is empty.'
        if len(content) > 500:
            content = content[:500]
        tokens = self._tokens_for_send(settings)
        if not tokens:
            return False, 'Kick token missing from host settings.'
        broadcaster_id = str(settings.get('broadcaster_user_id') or settings.get('channel_id') or settings.get('main_user_id') or '').strip()
        errors: list[str] = []
        for token, account in tokens:
            payloads: list[tuple[str, dict[str, Any]]] = []
            if broadcaster_id.isdigit():
                bid = int(broadcaster_id)
                payloads.append((f'{account}-user-with-broadcaster', {'content': content, 'type': 'user', 'broadcaster_user_id': bid}))
                if account == 'bot':
                    payloads.append((f'{account}-bot-with-broadcaster', {'content': content, 'type': 'bot', 'broadcaster_user_id': bid}))
                payloads.append((f'{account}-minimal-with-broadcaster', {'content': content, 'broadcaster_user_id': bid}))
            else:
                payloads.append((f'{account}-user-minimal', {'content': content, 'type': 'user'}))
                if account == 'bot':
                    payloads.append((f'{account}-bot-minimal', {'content': content, 'type': 'bot'}))
            for variant, payload in payloads:
                try:
                    resp = requests.post(
                        self.KICK_CHAT_URL,
                        headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                        json=payload,
                        timeout=15,
                    )
                    if resp.status_code < 400:
                        return True, f'Kick message sent direct as {account} ({variant}).'
                    errors.append(f'{variant}: HTTP {resp.status_code} {resp.text[:300]}')
                except Exception as exc:
                    errors.append(f'{variant}: {exc}')
        return False, 'Kick send failed: ' + ' | '.join(errors)[:900]

    def send_message(self, message: str, settings: dict[str, Any] | None = None, host: PluginHost | None = None):
        host = host or self._host
        effective = self._effective_settings(settings, host)

        # Important: this method is the endpoint that WebbasedPluginHost.send_platform_message()
        # calls for Kick. Calling host.send_platform_message('kick', ...) from here
        # recurses back into this same method and blocks bridge messages from Twitch,
        # YouTube or TikTok. So Kick writes directly with the central OAuth token
        # mirrored through host.platform_settings().
        ok, detail = self._send_direct_with_token(message, effective)
        self._append_diag(detail)
        return ok, detail


def create_plugin():
    return KickChatPlugin()
