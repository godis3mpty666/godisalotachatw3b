
from __future__ import annotations

import json
import secrets
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'plugins':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'
from typing import Any

from common import as_bool

IRC_HOST = 'irc.chat.twitch.tv'
IRC_PORT_SSL = 6697
AUTHORIZE_URL = 'https://id.twitch.tv/oauth2/authorize'
TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
VALIDATE_URL = 'https://id.twitch.tv/oauth2/validate'
DEFAULT_SCOPES = 'chat:read chat:edit moderator:manage:banned_users moderator:manage:chat_messages channel:manage:broadcast'


class TwitchWriter:
    def __init__(self, host_getter, logger) -> None:
        self._host_getter = host_getter
        self._log = logger
        # botalot owns no Twitch login/cache anymore. Tokens come from the main tool.
        self._legacy_cache_path = None
        self._cache_path = None
        self._send_lock = threading.Lock()
        self._send_sock = None
        self._send_context = ('', '', '')
        self._auth_memory = None
        self._auth_memory_until = 0.0
        self._auth_memory_key = ''

    @staticmethod
    def _clean_token(value: str) -> str:
        token = (value or '').strip()
        if token.startswith('oauth:'):
            token = token[6:]
        return token.strip()

    @staticmethod
    def _clean_username(value: str) -> str:
        return (value or '').strip().lstrip('@').lower()

    @staticmethod
    def _default_cache_path() -> Path:
        # Kept only for compatibility with older imports; not used anymore.
        return Path()

    @staticmethod
    def _redirect_uri(port: int) -> str:
        return f'http://localhost:{port}/callback/'

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding='utf-8') or '{}')
        except Exception as exc:
            self._log(f'Twitch OAuth Cache konnte nicht gelesen werden ({path}): {exc}')
        return {}

    def _cache_score(self, cache: dict[str, Any]) -> int:
        score = 0
        if self._clean_token(cache.get('access_token') or ''):
            score += 10
        if str(cache.get('refresh_token') or '').strip():
            score += 20
        if self._clean_username(cache.get('username') or ''):
            score += 2
        try:
            score += min(int(cache.get('saved_at') or 0) // 1000000000, 9)
        except Exception:
            pass
        return score

    def _load_cache(self) -> dict[str, Any]:
        # No plugin-local OAuth cache. The main tool is the only source of Twitch auth.
        return {}

    def _save_cache(self, cache: dict[str, Any]) -> None:
        # No plugin-local OAuth writes. The main tool persists Twitch auth.
        return

    def _http_json(self, url: str, *, method: str = 'GET', data: dict[str, str] | None = None, headers: dict[str, str] | None = None, timeout: float = 12.0) -> dict[str, Any]:
        body = None
        final_headers = dict(headers or {})
        if data is not None:
            body = urllib.parse.urlencode(data).encode('utf-8')
            final_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(url, data=body, headers=final_headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw or '{}')

    def _http_json_body(self, url: str, *, method: str = 'POST', body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 12.0) -> dict[str, Any]:
        final_headers = dict(headers or {})
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
            final_headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=payload, headers=final_headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw or '{}')

    def _twitch_api_headers(self, token: str, client_id: str) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {self._clean_token(token)}',
            'Client-Id': str(client_id or '').strip(),
        }

    def _validate_token_data(self, token: str) -> dict[str, Any]:
        return self._http_json(VALIDATE_URL, headers={'Authorization': f'OAuth {self._clean_token(token)}'})

    def _validate_token(self, token: str) -> tuple[bool, str, str, list[str]]:
        token = self._clean_token(token)
        if not token:
            return False, '', 'Missing access token.', []
        try:
            data = self._validate_token_data(token)
            login = self._clean_username(data.get('login') or '')
            scopes = list(data.get('scopes') or [])
            missing = [scope for scope in ('chat:read', 'chat:edit', 'moderator:manage:banned_users', 'moderator:manage:chat_messages') if scope not in scopes]
            if missing:
                return False, login, f'Token vorhanden, aber Scope fehlt: {", ".join(missing)}.', scopes
            return True, login, f'Twitch Token gültig für @{login}.', scopes
        except Exception as exc:
            return False, '', f'Token validation failed: {exc}', []

    def _refresh_token_if_possible(self, settings: dict, cache: dict) -> tuple[bool, str, dict]:
        # Refresh is owned by TwitchCore in the main tool. botalot must not create
        # or persist its own token state.
        return False, 'Twitch Token-Refresh läuft nur über das Haupttool.', dict(cache or {})

    def _start_oauth_flow(self, settings: dict, *, save_primary: bool = True) -> tuple[bool, str, dict]:
        client_id = (settings.get('twitch_client_id') or '').strip()
        client_secret = (settings.get('twitch_client_secret') or '').strip()
        if not client_id or not client_secret:
            return False, 'Twitch Client ID oder Client Secret fehlt.', {}
        try:
            port = int(str(settings.get('twitch_redirect_port') or '17564').strip())
        except Exception:
            return False, 'Twitch Redirect Port ist ungültig.', {}
        redirect_uri = self._redirect_uri(port)
        state = secrets.token_urlsafe(18)
        code_box = {'code': '', 'state': '', 'error': ''}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path not in ('/callback', '/callback/'):
                    self.send_response(404)
                    self.end_headers()
                    return
                qs = urllib.parse.parse_qs(parsed.query or '')
                code_box['code'] = (qs.get('code', ['']) or [''])[0]
                code_box['state'] = (qs.get('state', ['']) or [''])[0]
                code_box['error'] = (qs.get('error', ['']) or [''])[0]
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b'<html><body style="font-family:sans-serif;background:#111;color:#eee"><h3>botalot Twitch login complete</h3><p>You can close this window.</p></body></html>')

        try:
            httpd = HTTPServer(('127.0.0.1', port), Handler)
        except Exception as exc:
            return False, f'Twitch Callback-Server konnte Port {port} nicht öffnen: {exc}', {}

        def run_srv():
            try:
                httpd.handle_request()
            except Exception:
                pass

        threading.Thread(target=run_srv, daemon=True, name='botalot-twitch-oauth').start()
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': DEFAULT_SCOPES,
            'state': state,
            'force_verify': 'true',
        }
        wanted_login = self._clean_username(settings.get('twitch_oauth_login_override') or settings.get('twitch_bot_username') or '')
        if wanted_login:
            params['login'] = wanted_login
        url = AUTHORIZE_URL + '?' + urllib.parse.urlencode(params)
        self._log(f'Twitch OAuth: Browser wird geöffnet für @{wanted_login or "aktuellen Account"}.')
        opened = False
        try:
            opened = bool(webbrowser.open(url, new=2, autoraise=True))
        except Exception as exc:
            self._log(f'Twitch OAuth Browserstart via webbrowser fehlgeschlagen: {exc}')
        if not opened:
            try:
                os.startfile(url)  # type: ignore[attr-defined]
                opened = True
            except Exception as exc:
                self._log(f'Twitch OAuth Browserstart via Windows-Fallback fehlgeschlagen: {exc}')
                self._log(f'Twitch OAuth URL zum manuellen Öffnen: {url}')

        deadline = time.time() + 180.0
        while time.time() < deadline:
            if code_box['error']:
                try:
                    httpd.server_close()
                except Exception:
                    pass
                return False, f'Twitch OAuth abgebrochen: {code_box["error"]}', {}
            if code_box['code']:
                break
            time.sleep(0.15)
        try:
            httpd.server_close()
        except Exception:
            pass
        if not code_box['code']:
            return False, 'Twitch OAuth Timeout: Browser Callback kam nicht an.', {}
        if code_box['state'] != state:
            return False, 'Twitch OAuth State mismatch.', {}

        try:
            token_data = self._http_json(TOKEN_URL, method='POST', data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code_box['code'],
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            })
        except Exception as exc:
            return False, f'Twitch Token Exchange fehlgeschlagen: {exc}', {}

        access = self._clean_token(token_data.get('access_token') or '')
        refresh = (token_data.get('refresh_token') or '').strip()
        if not access:
            return False, 'Twitch Token Exchange lieferte keinen Access Token.', {}
        ok, login, msg, scopes = self._validate_token(access)
        if not ok:
            return False, msg, {}
        token_info = self._validate_token_data(access)
        cache = {
            'access_token': access,
            'refresh_token': refresh,
            'username': login,
            'user_id': str(token_info.get('user_id') or '').strip(),
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_port': str(port),
            'scopes': scopes,
            'saved_at': int(time.time()),
        }
        if save_primary:
            self._save_cache(cache)
        return True, f'Twitch OAuth verbunden: @{login} mit chat:read + chat:edit + moderator:manage:banned_users + moderator:manage:chat_messages + channel:manage:broadcast.', cache

    @staticmethod
    def _broadcast_cache_paths() -> list[Path]:
        return [_main_data_dir('gam3pick3r') / 'twitch_broadcast_oauth_cache.json']

    def _save_broadcast_cache(self, cache: dict[str, Any]) -> None:
        payload = dict(cache or {})
        payload['purpose'] = 'broadcast_update'
        wrote = False
        for path in self._broadcast_cache_paths():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
                wrote = True
            except Exception as exc:
                self._log(f'Twitch Streamtitel-Cache konnte nicht geschrieben werden ({path}): {exc}')
        if wrote:
            self._log('Twitch Streamtitel-Token zentral gespeichert. Plugins wie gam3pick3r können ihn jetzt nutzen.')

    def force_broadcast_oauth(self, settings: dict) -> tuple[bool, str, dict]:
        return True, 'Twitch OAuth wird nur noch im Haupttool unter Plattformen verwaltet.', {}

    def force_oauth(self, settings: dict) -> tuple[bool, str, dict]:
        return True, 'Twitch OAuth wird nur noch im Haupttool unter Plattformen verwaltet.', {}

    def resolve_auth(self, settings: dict, *, allow_oauth: bool) -> tuple[bool, str, str, dict]:
        """Resolve Twitch auth strictly from main-tool platform settings.

        botalot must not read plugin-local oauth_cache files and must not start
        its own OAuth flow. The main tool owns auth/refresh/persistence.
        """
        local = dict(settings or {})
        token = self._clean_token(local.get('twitch_oauth_token') or local.get('access_token') or '')
        username = self._clean_username(
            local.get('twitch_oauth_login')
            or local.get('oauth_login')
            or local.get('twitch_bot_username')
            or local.get('bot_account')
            or local.get('username')
            or ''
        )
        if not token:
            return False, username, 'Twitch nicht verbunden: Haupttool-OAuth Token fehlt.', {}
        ok, login, msg, scopes = self._validate_token(token)
        if not ok:
            return False, username or login, msg, {}
        if login:
            username = login
        cache = {
            'access_token': token,
            'username': username,
            'user_id': str(local.get('twitch_oauth_user_id') or local.get('oauth_user_id') or local.get('user_id') or '').strip(),
            'client_id': str(local.get('twitch_client_id') or local.get('client_id') or '').strip(),
            'client_secret': str(local.get('twitch_client_secret') or local.get('client_secret') or '').strip(),
            'refresh_token': str(local.get('twitch_refresh_token') or local.get('refresh_token') or '').strip(),
            'scopes': scopes,
            'saved_at': int(time.time()),
        }
        if not cache['user_id']:
            try:
                cache['user_id'] = str(self._validate_token_data(token).get('user_id') or '').strip()
            except Exception:
                pass
        return True, username, f'Twitch verbunden über Haupttool: @{username} kann lesen, schreiben und Mod-Aktionen nutzen.', cache

    def _oauth_result(self, settings: dict) -> tuple[bool, str, str, dict]:
        username = self._clean_username(settings.get('twitch_bot_username') or '')
        return False, username, 'Twitch OAuth wird nur noch im Haupttool unter Plattformen verwaltet.', {}

    def connect_oauth(self, settings: dict) -> tuple[bool, str, dict]:
        ok, username, msg, cache = self.resolve_auth(settings, allow_oauth=False)
        return ok, msg, cache

    def _plugin_truthy_attr(self, plugin: Any, names: tuple[str, ...]) -> bool:
        for name in names:
            try:
                value = getattr(plugin, name, None)
                if isinstance(value, bool):
                    if value:
                        return True
                elif value:
                    return True
            except Exception:
                pass
        return False

    def _plugin_thread_alive(self, plugin: Any) -> bool:
        for name in ('_thread', '_worker', '_chat_thread', 'thread', 'worker_thread'):
            try:
                obj = getattr(plugin, name, None)
                if obj is not None and hasattr(obj, 'is_alive') and obj.is_alive():
                    return True
            except Exception:
                pass
        return False

    def check_reader_status(self, settings: dict) -> tuple[bool, str]:
        """Check whether the incoming Twitch chat path for botalot is alive.

        OAuth only proves that the bot can authenticate. GPT replies also need
        the separate twitch_chat plugin to be running and joined, because that is
        where botalot receives @bot messages from. This intentionally does not
        return green just because a token exists.
        """
        try:
            host = self._host_getter()
        except Exception as exc:
            return False, f'Twitch Chat-Empfang unbekannt: Host nicht erreichbar ({exc}).'
        if host is None:
            return False, 'Twitch Chat-Empfang unbekannt: Host fehlt.'
        try:
            twitch_plugin = getattr(host, 'get_plugin', lambda _pid: None)('twitch_chat')
        except Exception as exc:
            return False, f'Twitch Chat-Empfang unbekannt: twitch_chat konnte nicht gelesen werden ({exc}).'
        if twitch_plugin is None:
            return False, 'Twitch Chat-Empfang aus: twitch_chat Plugin ist nicht geladen.'

        ps = getattr(twitch_plugin, '_settings', {}) or {}
        channel = str(settings.get('twitch_channel') or ps.get('channel') or ps.get('twitch_channel') or '').strip().lstrip('#')
        sock = getattr(twitch_plugin, '_sock', None)
        has_sock = sock is not None
        alive = self._plugin_thread_alive(twitch_plugin)
        connected_flag = self._plugin_truthy_attr(twitch_plugin, ('_connected', 'connected', '_is_connected', '_running', 'running', '_enabled', 'enabled'))
        status_obj = getattr(twitch_plugin, '_status', None)
        status_text = str(status_obj or '').lower()
        status_connected = any(x in status_text for x in ('connected', 'verbunden', 'running', 'läuft'))

        if channel and (has_sock or alive or connected_flag or status_connected):
            details = []
            if has_sock:
                details.append('Socket aktiv')
            if alive:
                details.append('Worker läuft')
            if connected_flag or status_connected:
                details.append('Plugin meldet verbunden')
            return True, f'Twitch Chat-Empfang aktiv über twitch_chat in #{channel} ({", ".join(details) or "aktiv"}).'

        if not channel:
            return False, 'Twitch Chat-Empfang nicht sicher: Ziel-Kanal fehlt in botalot/twitch_chat.'
        return False, f'Twitch Chat-Empfang nicht aktiv: twitch_chat ist geladen, aber kein aktiver Socket/Worker für #{channel} erkennbar.'

    def check_status(self, settings: dict) -> tuple[bool, str]:
        if as_bool(settings.get('prefer_existing_twitch_socket'), False):
            try:
                host = self._host_getter()
                twitch_plugin = getattr(host, 'get_plugin', lambda _pid: None)('twitch_chat') if host is not None else None
                sock = getattr(twitch_plugin, '_sock', None)
                channel = str(settings.get('twitch_channel') or getattr(twitch_plugin, '_settings', {}).get('channel') or '').strip().lstrip('#')
                if sock is not None and channel:
                    return True, f'Twitch bereit über vorhandenes twitch_chat Plugin: #{channel}'
            except Exception as exc:
                self._log(f'Twitch Status über vorhandenen Socket fehlgeschlagen: {exc}')
        ok, username, msg, _cache = self.resolve_auth(settings, allow_oauth=False)
        channel = str(settings.get('twitch_channel') or '').strip().lstrip('#')
        if ok and channel:
            return True, f'{msg} Ziel: #{channel}'
        if ok:
            return False, 'Twitch OAuth ist gültig, aber Twitch Kanal fehlt.'
        return False, msg

    def check_auth(self, settings: dict) -> tuple[bool, str]:
        if as_bool(settings.get('prefer_existing_twitch_socket'), False):
            ok, msg = self.check_status(settings)
            if ok and 'vorhandenes twitch_chat Plugin' in msg:
                return True, 'Twitch verbunden: vorhandenes twitch_chat Plugin ist aktiv.'
        ok, username, msg, cache = self.resolve_auth(settings, allow_oauth=False)
        if not ok:
            return False, msg
        channel = self._clean_username(settings.get('twitch_channel') or '')
        if not channel:
            return False, 'Twitch verbunden, aber Ziel-Kanal fehlt.'
        ok_join, join_msg = self._irc_join_check(username, cache.get('access_token') or settings.get('twitch_oauth_token') or '', channel)
        if ok_join:
            return True, join_msg
        if 'token ungültig' in str(join_msg).lower() or 'authentication failed' in str(join_msg).lower():
            ok_refresh, refresh_msg, refreshed = self._refresh_token_if_possible(settings, cache)
            if ok_refresh:
                return self._irc_join_check(username or self._clean_username(refreshed.get('username') or ''), refreshed.get('access_token') or '', channel)
            return False, refresh_msg
        return False, join_msg

    def _irc_join_check(self, username: str, token: str, channel: str) -> tuple[bool, str]:
        token = self._clean_token(token)
        if not username or not token or not channel:
            return False, 'Twitch nicht verbunden: Kanal, Bot-Login oder OAuth-Token fehlt.'
        try:
            context = ssl.create_default_context()
            with socket.create_connection((IRC_HOST, IRC_PORT_SSL), timeout=8) as raw:
                with context.wrap_socket(raw, server_hostname=IRC_HOST) as sock:
                    sock.settimeout(8)
                    sock.sendall(f'PASS oauth:{token}\r\nNICK {username}\r\nJOIN #{channel}\r\n'.encode('utf-8'))
                    data = b''
                    end = time.time() + 5
                    while time.time() < end:
                        try:
                            chunk = sock.recv(4096)
                        except socket.timeout:
                            break
                        if not chunk:
                            break
                        data += chunk
                        text = data.decode('utf-8', errors='replace').lower()
                        if 'login authentication failed' in text or 'improperly formatted auth' in text:
                            return False, 'Twitch Fehler: OAuth-Token ungültig.'
                        if ' 001 ' in text or f'join #{channel.lower()}' in text:
                            return True, f'Twitch verbunden: @{username} kann #{channel} lesen/schreiben.'
                    text = data.decode('utf-8', errors='replace').strip()
                    if text:
                        return True, f'Twitch Auth erreichbar: @{username} -> #{channel}'
                    return False, 'Twitch keine Antwort vom IRC-Server erhalten.'
        except Exception as exc:
            return False, f'Twitch Verbindung fehlgeschlagen: {exc}'


    def _get_twitch_user_id(self, login: str, token: str, client_id: str) -> str:
        clean = self._clean_username(login)
        if not clean:
            return ''
        url = 'https://api.twitch.tv/helix/users?' + urllib.parse.urlencode({'login': clean})
        data = self._http_json(url, headers=self._twitch_api_headers(token, client_id), timeout=10.0)
        users = list(data.get('data') or [])
        if not users:
            return ''
        return str(users[0].get('id') or '').strip()

    def _resolve_moderation_ids(self, settings: dict, target_user: str) -> tuple[bool, str, str, str, str, str]:
        ok, bot_login, msg, cache = self.resolve_auth(settings, allow_oauth=False)
        token = self._clean_token(cache.get('access_token') or settings.get('twitch_oauth_token') or '')
        client_id = str(settings.get('twitch_client_id') or cache.get('client_id') or '').strip()
        channel = self._clean_username(settings.get('twitch_channel') or '')
        target_login = self._clean_username(target_user)
        if not ok or not token or not client_id:
            return False, msg, '', '', '', ''
        if not channel:
            return False, 'Twitch Ban fehlgeschlagen: Ziel-Kanal fehlt.', '', '', '', ''
        if not target_login:
            return False, 'Twitch Ban fehlgeschlagen: Ziel-User fehlt.', '', '', '', ''
        moderator_id = str(cache.get('user_id') or '').strip()
        if not moderator_id:
            try:
                moderator_id = str(self._validate_token_data(token).get('user_id') or '').strip()
            except Exception:
                moderator_id = ''
        broadcaster_id = self._get_twitch_user_id(channel, token, client_id)
        target_id = self._get_twitch_user_id(target_login, token, client_id)
        if not moderator_id:
            return False, 'Twitch Ban fehlgeschlagen: Moderator-ID konnte nicht ermittelt werden.', '', '', '', ''
        if not broadcaster_id:
            return False, f'Twitch Ban fehlgeschlagen: Kanal-ID für #{channel} nicht gefunden.', '', '', '', ''
        if not target_id:
            return False, f'Twitch Ban fehlgeschlagen: User-ID für @{target_login} nicht gefunden.', '', '', '', ''
        return True, '', token, client_id, broadcaster_id, moderator_id + ':' + target_id


    def delete_message(self, settings: dict, message_id: str, channel: str = '') -> bool:
        msg_id = str(message_id or '').strip()
        if not msg_id:
            self._log('Twitch Nachricht löschen übersprungen: Message-ID fehlt.')
            return False
        ok, bot_login, msg, cache = self.resolve_auth(settings, allow_oauth=False)
        token = self._clean_token(cache.get('access_token') or settings.get('twitch_oauth_token') or '')
        client_id = str(settings.get('twitch_client_id') or cache.get('client_id') or '').strip()
        target_channel = self._clean_username(channel or settings.get('twitch_channel') or '')
        if not ok or not token or not client_id:
            self._log(f'Twitch Nachricht löschen fehlgeschlagen: {msg}')
            return False
        if not target_channel:
            self._log('Twitch Nachricht löschen fehlgeschlagen: Ziel-Kanal fehlt.')
            return False
        moderator_id = str(cache.get('user_id') or '').strip()
        if not moderator_id:
            try:
                moderator_id = str(self._validate_token_data(token).get('user_id') or '').strip()
            except Exception:
                moderator_id = ''
        broadcaster_id = self._get_twitch_user_id(target_channel, token, client_id)
        if not moderator_id:
            self._log('Twitch Nachricht löschen fehlgeschlagen: Moderator-ID konnte nicht ermittelt werden.')
            return False
        if not broadcaster_id:
            self._log(f'Twitch Nachricht löschen fehlgeschlagen: Kanal-ID für #{target_channel} nicht gefunden.')
            return False
        url = 'https://api.twitch.tv/helix/moderation/chat?' + urllib.parse.urlencode({
            'broadcaster_id': broadcaster_id,
            'moderator_id': moderator_id,
            'message_id': msg_id,
        })
        try:
            req = urllib.request.Request(url, headers=self._twitch_api_headers(token, client_id), method='DELETE')
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                resp.read()
            self._log(f'Twitch Nachricht gelöscht: {msg_id}')
            return True
        except Exception as exc:
            self._log(f'Twitch Nachricht löschen fehlgeschlagen ({msg_id}): {exc}')
            return False

    def ban_user(self, settings: dict, username: str, reason: str = '') -> bool:
        user = self._clean_username(username)
        if not user:
            self._log('Twitch Ban übersprungen: Nutzer fehlt.')
            return False
        safe_reason = str(reason or 'Blocked by botalot moderation').replace('\r', ' ').replace('\n', ' ').strip()[:500]
        ok, err, token, client_id, broadcaster_id, ids = self._resolve_moderation_ids(settings, user)
        if not ok:
            self._log(err)
            return False
        moderator_id, target_id = ids.split(':', 1)
        url = 'https://api.twitch.tv/helix/moderation/bans?' + urllib.parse.urlencode({
            'broadcaster_id': broadcaster_id,
            'moderator_id': moderator_id,
        })
        try:
            self._http_json_body(url, method='POST', body={'data': {'user_id': target_id, 'reason': safe_reason}}, headers=self._twitch_api_headers(token, client_id), timeout=12.0)
            self._log(f'Twitch Moderation Ban erfolgreich: @{user}')
            return True
        except Exception as exc:
            self._log(f'Twitch Moderation Ban fehlgeschlagen für @{user}: {exc}')
            return False

    def unban_user(self, settings: dict, username: str) -> bool:
        user = self._clean_username(username)
        if not user:
            self._log('Twitch Unban übersprungen: Nutzer fehlt.')
            return False
        ok, err, token, client_id, broadcaster_id, ids = self._resolve_moderation_ids(settings, user)
        if not ok:
            self._log(err.replace('Ban', 'Unban'))
            return False
        moderator_id, target_id = ids.split(':', 1)
        url = 'https://api.twitch.tv/helix/moderation/bans?' + urllib.parse.urlencode({
            'broadcaster_id': broadcaster_id,
            'moderator_id': moderator_id,
            'user_id': target_id,
        })
        try:
            req = urllib.request.Request(url, headers=self._twitch_api_headers(token, client_id), method='DELETE')
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                resp.read()
            self._log(f'Twitch Moderation Unban erfolgreich: @{user}')
            return True
        except Exception as exc:
            self._log(f'Twitch Moderation Unban fehlgeschlagen für @{user}: {exc}')
            return False

    def _split_twitch_message(self, message: str, limit: int = 450) -> list[str]:
        safe = str(message or '').replace('\r', ' ').replace('\n', ' ').strip()
        if not safe:
            return []
        limit = max(20, int(limit or 450))
        if len(safe) <= limit:
            return [safe]

        parts: list[str] = []
        current = ''
        for word in safe.split():
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= limit:
                current += ' ' + word
            else:
                parts.append(current)
                current = word
        if current:
            parts.append(current)

        fixed: list[str] = []
        for part in parts:
            if len(part) <= limit:
                fixed.append(part)
            else:
                for i in range(0, len(part), limit):
                    fixed.append(part[i:i + limit])
        return [part for part in fixed if part]

    def send(self, settings: dict, message: str) -> bool:
        parts = self._split_twitch_message(message, 450)
        if not parts:
            self._log('Twitch senden übersprungen: leere Nachricht.')
            return False

        # First choice: central main-tool sender. This guarantees the same bot
        # account/token as Plattformen -> Twitch.
        try:
            host = self._host_getter()
            fn = getattr(host, 'send_platform_message', None) if host is not None else None
            if callable(fn):
                sent_any = True
                for idx, part in enumerate(parts, 1):
                    try:
                        result = fn('twitch', part, account='bot', use_bot=True, sender='botalot')
                    except TypeError:
                        result = fn('twitch', part)
                    # Einige Haupttool-Sender senden erfolgreich, liefern aber None
                    # statt True zurueck. Das darf botalot nicht als Fehler werten,
                    # sonst wird die GPT-Antwort nicht ins Desktopwindow gespiegelt.
                    ok = True if result is None else bool(result)
                    if not ok:
                        sent_any = False
                        break
                    if len(parts) > 1 and idx < len(parts):
                        time.sleep(0.25)
                if sent_any:
                    self._log('Twitch Nachricht über Haupttool gesendet.')
                    return True
                self._log('Twitch Haupttool-Sender meldete Fehler, direkter Fallback wird versucht.')
        except Exception as exc:
            self._log(f'Twitch Haupttool-Sender nicht nutzbar: {exc}')

        # Fallback only uses the token copied from main-tool platform settings;
        # never plugin-owned cache/OAuth.
        return self._send_direct(settings, message)

    def _auth_key_for_settings(self, settings: dict) -> str:
        token = self._clean_token(settings.get('twitch_oauth_token') or settings.get('access_token') or '')
        username = self._clean_username(settings.get('twitch_oauth_login') or settings.get('twitch_bot_username') or '')
        channel = self._clean_username(settings.get('twitch_channel') or '')
        return f'{username}|{channel}|{token[:10]}|{len(token)}'

    def _resolve_auth_for_send(self, settings: dict) -> tuple[bool, str, str, dict]:
        """Resolve Twitch auth with a short memory cache for chat sending.

        Older versions validated the OAuth token through HTTPS before every
        single chat line. That is safe but painfully slow during live chat and
        makes GPT look late. OAuth is still validated on Connect/status checks;
        for actual sends we reuse the last good result for a few minutes.
        """
        key = self._auth_key_for_settings(settings)
        now = time.time()
        if self._auth_memory is not None and self._auth_memory_key == key and now < self._auth_memory_until:
            return self._auth_memory
        result = self.resolve_auth(settings, allow_oauth=False)
        if result[0]:
            self._auth_memory = result
            self._auth_memory_key = key
            self._auth_memory_until = now + 300.0
        return result

    def _close_send_socket(self) -> None:
        sock = self._send_sock
        self._send_sock = None
        self._send_context = ('', '', '')
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass

    def _pump_send_socket(self, sock) -> bool:
        try:
            old_timeout = sock.gettimeout()
        except Exception:
            old_timeout = 0.05
        try:
            sock.settimeout(0.02)
            for _ in range(8):
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    break
                except ssl.SSLWantReadError:
                    break
                if not data:
                    return False
                for line in data.decode('utf-8', errors='replace').split('\r\n'):
                    if line.startswith('PING'):
                        try:
                            sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                        except Exception:
                            return False
                    low = line.lower()
                    if 'authentication failed' in low or 'improperly formatted auth' in low or 'login authentication failed' in low:
                        self._log('Twitch Send-Socket wurde abgelehnt: OAuth-Login fehlgeschlagen.')
                        return False
        finally:
            try:
                sock.settimeout(old_timeout)
            except Exception:
                pass
        return True

    def _connect_send_socket(self, username: str, token: str, channel: str):
        context = ssl.create_default_context()
        raw = socket.create_connection((IRC_HOST, IRC_PORT_SSL), timeout=6.0)
        sock = context.wrap_socket(raw, server_hostname=IRC_HOST)
        sock.settimeout(1.0)
        sock.sendall(b'CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n')
        sock.sendall(f'PASS oauth:{token}\r\nNICK {username}\r\nJOIN #{channel}\r\n'.encode('utf-8'))
        buffer = ''
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError('IRC closed connection during join.')
            buffer += data.decode('utf-8', errors='replace')
            while '\r\n' in buffer:
                line, buffer = buffer.split('\r\n', 1)
                if not line:
                    continue
                low = line.lower()
                if line.startswith('PING'):
                    sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                    continue
                if 'authentication failed' in low or 'improperly formatted auth' in low or 'login authentication failed' in low:
                    raise RuntimeError('OAuth-Login wurde vom IRC abgelehnt.')
                if ' no such nick/channel' in low or ' no such channel' in low:
                    raise RuntimeError(f'Kanal nicht gefunden #{channel}.')
                if f'join #{channel.lower()}' in low or ' 001 ' in low or ' 366 ' in low:
                    sock.settimeout(0.2)
                    return sock
        # Twitch liefert nicht immer den erwarteten JOIN-Ack schnell genug.
        # Wenn kein klarer Fehler kam, behalten wir den Socket und senden trotzdem.
        sock.settimeout(0.2)
        return sock

    def _ensure_send_socket(self, username: str, token: str, channel: str):
        ctx = (username, token[:16], channel)
        if self._send_sock is not None and self._send_context == ctx:
            if self._pump_send_socket(self._send_sock):
                return self._send_sock
            self._close_send_socket()
        sock = self._connect_send_socket(username, token, channel)
        self._send_sock = sock
        self._send_context = ctx
        return sock

    def _send_direct(self, settings: dict, message: str) -> bool:
        ok, username, msg, cache = self._resolve_auth_for_send(settings)
        channel = self._clean_username(settings.get('twitch_channel') or '')
        token = self._clean_token(cache.get('access_token') or settings.get('twitch_oauth_token') or '')
        if not ok or not channel or not username or not token:
            self._log(f'Twitch senden übersprungen: {msg} Kanal=#{channel or "<leer>"} Bot=@{username or "<leer>"}')
            return False

        parts = self._split_twitch_message(message, 450)
        if not parts:
            self._log('Twitch senden übersprungen: leere Nachricht.')
            return False

        with self._send_lock:
            for idx, part in enumerate(parts, 1):
                sent = False
                for attempt in range(2):
                    try:
                        sock = self._ensure_send_socket(username, token, channel)
                        sock.sendall(f'PRIVMSG #{channel} :{part}\r\n'.encode('utf-8'))
                        if len(parts) > 1:
                            self._log(f'Twitch PRIVMSG gesendet als @{username} nach #{channel} ({idx}/{len(parts)}): {part}')
                        else:
                            self._log(f'Twitch PRIVMSG gesendet als @{username} nach #{channel}: {part}')
                        sent = True
                        break
                    except Exception as exc:
                        self._close_send_socket()
                        if attempt == 0:
                            self._log(f'Twitch Send-Socket reconnect nach Fehler: {exc}')
                            continue
                        self._log(f'Twitch senden fehlgeschlagen: {exc}')
                        return False
                if not sent:
                    return False
                if len(parts) > 1 and idx < len(parts):
                    time.sleep(0.25)
            return True
        return False
