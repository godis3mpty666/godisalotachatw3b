from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from urllib.parse import urlparse
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover
    QtCore = None
    QtGui = None
    QtWidgets = None

from data.paths import data_dir
from shared.models import PluginStatus
from shared.plugin_base import PluginHost
from shared.plugin_common import ThreadedPlugin


PLUGIN_ID = 'info3ditor'
SUPPORTED_PLATFORMS = ('twitch', 'youtube', 'kick', 'tiktok')
YOUTUBE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
KICK_TOKEN_URL = 'https://id.kick.com/oauth/token'
KICK_CHANNELS_URL = 'https://api.kick.com/public/v1/channels'
KICK_CATEGORIES_URL = 'https://api.kick.com/public/v2/categories'
TIKTOK_LIVE_CENTER_URL = 'https://livecenter.tiktok.com/'



def _clean_text(value: Any) -> str:
    return str(value or '').strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {'0', 'false', 'no', 'off', ''}
    return bool(value)


def _slug(value: str) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r'[^a-z0-9äöüß_-]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text or f'preset_{int(time.time())}'


def _split_tags(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        parts = re.split(r'[,;\n]+', str(raw or ''))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = part.strip().lstrip('#')
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


class PresetStore:
    def __init__(self) -> None:
        self.folder = data_dir() / PLUGIN_ID
        self.file = self.folder / 'presets.json'
        self.folder.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self.file.exists():
            self.save([])
            return []
        try:
            raw = json.loads(self.file.read_text(encoding='utf-8'))
            presets = raw.get('presets') if isinstance(raw, dict) else raw
            if not isinstance(presets, list):
                return []
            return [self._normalize(p) for p in presets if isinstance(p, dict)]
        except Exception:
            return []

    def save(self, presets: list[dict[str, Any]]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        normalized = [self._normalize(p) for p in presets if isinstance(p, dict)]
        payload = {
            'version': 1,
            'updated_at': int(time.time()),
            'presets': normalized,
        }
        self.file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _normalize(self, preset: dict[str, Any]) -> dict[str, Any]:
        name = _clean_text(preset.get('name')) or _clean_text(preset.get('title')) or 'Neues Preset'
        pid = _clean_text(preset.get('id')) or _slug(name)
        platforms = preset.get('platforms') if isinstance(preset.get('platforms'), dict) else {}
        out = {'id': pid, 'name': name, 'platforms': {}}
        for platform in SUPPORTED_PLATFORMS:
            pdata = platforms.get(platform) if isinstance(platforms.get(platform), dict) else {}
            out['platforms'][platform] = self._default_platform(platform, pdata)
        return out

    def _default_platform(self, platform: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = dict(data or {})
        base: dict[str, Any] = {'enabled': _as_bool(data.get('enabled'), False)}
        if platform == 'twitch':
            base.update({
                'title': _clean_text(data.get('title')),
                'category': _clean_text(data.get('category')),
                'game_id': _clean_text(data.get('game_id')),
                'tags': _clean_text(data.get('tags')),
                'description': _clean_text(data.get('description')),
            })
        elif platform == 'youtube':
            base.update({
                'title': _clean_text(data.get('title')),
                'description': _clean_text(data.get('description')),
                'tags': _clean_text(data.get('tags')),
                'category': _clean_text(data.get('category')),
            })
        elif platform == 'tiktok':
            base['enabled'] = False
            base.update({
                'title': _clean_text(data.get('title')),
                'category': _clean_text(data.get('category')),
                'description': 'TIK TOK ist momentan noch nicht nutzbar.',
            })
        elif platform == 'kick':
            base.update({
                'title': _clean_text(data.get('title')),
                'category': _clean_text(data.get('category')),
                'description': _clean_text(data.get('description')),
                'tags': _clean_text(data.get('tags')),
            })
        return base


class Info3ditorPlugin(ThreadedPlugin):
    plugin_id = PLUGIN_ID
    display_name = 'info3ditor'
    version = '0.12'
    description = 'Streamtitel/Streaminfo-Presets speichern und per Klick senden.'

    def __init__(self) -> None:
        super().__init__()
        self.store = PresetStore()
        self.ui_language = 'de'
        self._dialogs: list[Any] = []
        self._send_lock = threading.Lock()
        self._youtube_quota_blocked_until = 0.0
        self._tiktok_last_browser_was_launched = False
        self._tiktok_last_producer_port = 0
        self._tiktok_last_browser_process = None
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}

    def set_ui_language(self, language: str) -> None:
        lang = _clean_text(language).lower()
        self.ui_language = lang if lang in {'de', 'en'} else 'de'

    def settings_schema(self, language: str | None = None, ui_language: str | None = None) -> list[dict[str, Any]]:
        lang = _clean_text(language or ui_language or self.ui_language or 'de').lower()
        self.set_ui_language(lang)
        return [
            {'key': '__info3ditor_embedded__', 'type': 'hidden', 'default': True},
            {'key': 'autoconnect', 'type': 'hidden', 'default': True},
            {
                'key': 'presets_json',
                'type': 'textarea',
                'tab': 'Presets',
                'label': 'Info3ditor-Presets',
                'help': 'Hier werden alle Presets mit den Einstellungen für Twitch, YouTube, Kick und TikTok angezeigt. Änderungen im JSON-Format werden beim Speichern übernommen.',
                'placeholder': '{"presets": []}',
            },
        ]

    def default_settings(self) -> dict[str, Any]:
        return {'autoconnect': True, 'presets_json': self._presets_json()}

    def _presets_json(self) -> str:
        return json.dumps({'presets': self.store.load()}, ensure_ascii=False, indent=2)

    def _import_presets_json(self, value: Any) -> bool:
        raw = _clean_text(value)
        if not raw:
            return False
        try:
            parsed = json.loads(raw)
            presets = parsed.get('presets') if isinstance(parsed, dict) else parsed
            if not isinstance(presets, list):
                return False
            self.store.save(presets)
            return True
        except Exception:
            return False

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        return True, 'info3ditor ist lokal bereit. Gesendet wird über die zentralen Plattform-Verbindungen vom Haupttool.'

    def run(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._host = host
        self._settings = dict(settings or {})
        if settings.get('presets_json') and not self._import_presets_json(settings.get('presets_json')):
            host.log(self.plugin_id, 'Info3ditor-Presets konnten nicht aus den Settings gelesen werden; vorhandene Presets bleiben erhalten.')
        host.set_status(self.plugin_id, PluginStatus('connected', 'Bereit'))
        while not self._stop.wait(2.0):
            self._host = host

    def _replace_settings_dialog_with_panel(self, dialog: Any) -> None:
        if QtWidgets is None:
            return
        try:
            layout = dialog.layout()
            if layout is None:
                layout = QtWidgets.QVBoxLayout(dialog)
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
                elif child_layout is not None:
                    self._clear_layout(child_layout)
            dialog.setWindowTitle('info3ditor')
            dialog.resize(1180, 620)
            panel = _PresetPanelWidget(self, self._host, settings_dialog=dialog, parent=dialog, language=self.ui_language)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(10)
            layout.addWidget(panel, 1)
        except Exception:
            pass

    def _clear_layout(self, layout: Any) -> None:
        try:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
                elif child_layout is not None:
                    self._clear_layout(child_layout)
        except Exception:
            pass

    def _update_settings_dialog_fields(self, settings_dialog: Any | None) -> None:
        if settings_dialog is None:
            return
        try:
            widgets = getattr(settings_dialog, '_widgets', {})
            presets_widget = widgets.get('presets_info') if isinstance(widgets, dict) else None
            if presets_widget is not None and hasattr(presets_widget, 'setText'):
                presets_widget.setText(str(len(self.store.load())))
            path_widget = widgets.get('storage_path') if isinstance(widgets, dict) else None
            if path_widget is not None and hasattr(path_widget, 'setText'):
                path_widget.setText(str(self.store.file))
        except Exception:
            pass

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent=None) -> bool:
        if key == 'send_web_preset':
            self._import_presets_json(self._settings.get('presets_json'))
            wanted = _clean_text(self._settings.get('selected_preset_id'))
            preset = next((item for item in self.store.load() if _clean_text(item.get('id')) == wanted), None)
            if preset is None:
                if host is not None:
                    host.log(self.plugin_id, 'Ausgewähltes Info3ditor-Preset wurde nicht gefunden.')
                return False
            self.send_preset_async(preset, host or self._host)
            return True
        if key != 'open_editor':
            return False
        if QtWidgets is None:
            if host is not None:
                host.log(self.plugin_id, 'PySide6 ist nicht verfügbar, Editor kann nicht geöffnet werden.')
            return True
        self._update_settings_dialog_fields(parent)
        dlg = _PresetListDialog(self, host, settings_dialog=parent, parent=parent, language=self.ui_language)
        dlg.setModal(False)
        dlg.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._dialogs.append(dlg)
        dlg.destroyed.connect(lambda *_: self._forget_dialog(dlg))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return True

    def _forget_dialog(self, dlg: Any) -> None:
        try:
            self._dialogs.remove(dlg)
        except ValueError:
            pass

    def send_preset_async(self, preset: dict[str, Any], host: PluginHost | None) -> None:
        if host is None:
            return
        snapshot = deepcopy(preset)
        thread = threading.Thread(target=self._send_preset_worker, args=(snapshot, host), daemon=True, name='info3ditor-send')
        thread.start()

    def _send_preset_worker(self, preset: dict[str, Any], host: PluginHost) -> None:
        if not self._send_lock.acquire(blocking=False):
            host.log(self.plugin_id, 'Es läuft schon ein Sendevorgang.')
            return
        try:
            name = _clean_text(preset.get('name')) or 'Preset'
            host.log(self.plugin_id, f'Sende Preset: {name}')
            platforms = preset.get('platforms') if isinstance(preset.get('platforms'), dict) else {}
            did_any = False
            for platform in SUPPORTED_PLATFORMS:
                pdata = platforms.get(platform) if isinstance(platforms.get(platform), dict) else {}
                if not _as_bool(pdata.get('enabled'), False):
                    continue
                did_any = True
                host.log(self.plugin_id, f'Sende an {platform} …')
                try:
                    if platform == 'twitch':
                        ok, msg = self._send_twitch(pdata, host)
                    elif platform == 'youtube':
                        ok, msg = self._send_youtube(pdata, host)
                    elif platform == 'tiktok':
                        ok, msg = self._send_tiktok(pdata, host)
                    elif platform == 'kick':
                        ok, msg = self._send_kick(pdata, host)
                    else:
                        ok, msg = False, 'Unbekannte Plattform.'
                except Exception as exc:
                    ok, msg = False, f'Unerwarteter Fehler: {exc}'
                host.log(self.plugin_id, ('✅ ' if ok else '❌ ') + f'{platform}: {msg}')
            if not did_any:
                host.log(self.plugin_id, 'Keine Plattform im Preset aktiviert.')
        finally:
            self._send_lock.release()

    def _send_twitch(self, pdata: dict[str, Any], host: PluginHost) -> tuple[bool, str]:
        title = _clean_text(pdata.get('title'))
        category = _clean_text(pdata.get('category'))
        game_id = _clean_text(pdata.get('game_id'))
        tags = _split_tags(pdata.get('tags'))
        if not game_id and category:
            game_id = self._resolve_twitch_category_id(category, host)
        settings = host.platform_settings('twitch') if host is not None else {}
        token = _clean_text(settings.get('main_access_token') or settings.get('access_token'))
        client_id = _clean_text(settings.get('client_id'))
        broadcaster_id = _clean_text(settings.get('broadcaster_user_id') or settings.get('broadcaster_id') or settings.get('main_oauth_user_id') or settings.get('main_user_id') or settings.get('channel_id'))
        if not token or not client_id or not broadcaster_id:
            return False, 'Twitch Main-OAuth oder Broadcaster-ID fehlt. Bitte Twitch Main im Haupttool neu anmelden.'
        headers = {'Client-Id': client_id, 'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        try:
            payload = {}
            if title:
                payload['title'] = title
            if game_id:
                payload['game_id'] = game_id
            if payload:
                req = urllib.request.Request('https://api.twitch.tv/helix/channels?' + urllib.parse.urlencode({'broadcaster_id': broadcaster_id}), data=json.dumps(payload).encode('utf-8'), headers=headers, method='PATCH')
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
            if tags:
                req = urllib.request.Request('https://api.twitch.tv/helix/streams/tags?' + urllib.parse.urlencode({'broadcaster_id': broadcaster_id}), data=json.dumps({'tags': tags[:10]}).encode('utf-8'), headers=headers, method='PUT')
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
            ok = bool(payload or tags)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                detail = ''
            return False, f'Twitch HTTP {exc.code}: {detail}'
        except Exception as exc:
            return False, f'Twitch-Update fehlgeschlagen: {exc}'
        detail_parts = []
        if title:
            detail_parts.append('Titel')
        if game_id:
            detail_parts.append(f'Kategorie-ID {game_id}')
        elif category:
            detail_parts.append(f'Kategorie nicht aufgelöst: {category}')
        if tags:
            detail_parts.append('Tags')
        return ok, ', '.join(detail_parts) if detail_parts else 'Keine Twitch-Felder gesetzt.'

    def _resolve_twitch_category_id(self, query: str, host: PluginHost) -> str:
        settings = host.platform_settings('twitch') if host is not None else {}
        token = _clean_text(settings.get('main_access_token') or settings.get('access_token'))
        client_id = _clean_text(settings.get('client_id'))
        if not token or not client_id:
            return ''
        url = 'https://api.twitch.tv/helix/search/categories?' + urllib.parse.urlencode({'query': query, 'first': 10})
        req = urllib.request.Request(url, headers={'Client-Id': client_id, 'Authorization': f'Bearer {token}'})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
            rows = data.get('data') if isinstance(data, dict) else []
            if not isinstance(rows, list):
                return ''
            q = query.strip().lower()
            for row in rows:
                name = _clean_text((row or {}).get('name')).lower()
                if name == q:
                    return _clean_text((row or {}).get('id'))
            if rows:
                return _clean_text((rows[0] or {}).get('id'))
        except Exception:
            return ''
        return ''


    def _send_tiktok(self, pdata: dict[str, Any], host: PluginHost) -> tuple[bool, str]:
        title = _clean_text(pdata.get('title'))
        category = _clean_text(pdata.get('category'))
        description = _clean_text(pdata.get('description'))
        if not title and not category and not description:
            return False, 'Keine TikTok-Felder gesetzt.'

        return False, (
            'TikTok ist zurzeit in Arbeit. '
            'Twitch, YouTube und Kick werden gesendet; TikTok wird aktuell bewusst übersprungen, '
            'weil TikTok im Web-Livecenter keine bestätigte Titel/Kategorie-Update-Seite für diesen Account anbietet.'
        )

    def _tiktok_prepare_main_browser(self, settings: dict[str, Any], target_url: str) -> tuple[bool, str, dict[str, Any] | None]:
        settings = dict(settings or {})
        main_account = _clean_text(settings.get('main_account') or settings.get('unique_id')).lstrip('@')
        profile_dir = self._tiktok_main_profile_dir(settings)
        port = self._tiktok_main_debug_port(settings)
        self._tiktok_last_browser_was_launched = False
        self._tiktok_last_producer_port = port
        self._tiktok_last_browser_process = None
        self._host: PluginHost | None = None
        browser_path = _clean_text(settings.get('browser_path')).strip('"')
        profile_dir.mkdir(parents=True, exist_ok=True)
        can_start_minimized = self._tiktok_profile_has_login_hint(profile_dir)

        ready, _ = self._tiktok_wait_for_debugger(port, timeout_seconds=0.7)
        if ready:
            tab = self._tiktok_find_livecenter_tab(port)
            if tab:
                return True, 'TikTok Main-Browser im vorhandenen Debug-Browser gefunden.', tab
            self._tiktok_open_new_tab(port, target_url)
            tab = self._tiktok_wait_for_livecenter_tab(port, timeout_seconds=6.0)
            if tab:
                return True, 'TikTok Main-Browser im vorhandenen Debug-Browser geöffnet.', tab

        exes = self._tiktok_find_browser_exes(browser_path)
        if not exes:
            return False, 'Kein Chrome/Edge gefunden. Bitte Browser-Pfad im Haupttool setzen.', None

        args = [
            f'--remote-debugging-port={port}',
            '--remote-debugging-address=127.0.0.1',
            f'--user-data-dir={str(profile_dir)}',
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
            '--new-window',
            '--disable-background-mode',
            '--disable-features=Translate',
        ]
        # Für TikTok bleibt das Fenster sichtbar, bis eine echte Zielseite bestätigt ist.
        args.append(target_url)
        last_error = ''
        for exe in exes:
            try:
                kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'stdin': subprocess.DEVNULL, 'close_fds': True}
                if os.name == 'nt':
                    kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
                else:
                    kwargs['start_new_session'] = True
                proc = subprocess.Popen([exe] + args, **kwargs)
                self._tiktok_last_browser_process = proc
                self._tiktok_last_browser_was_launched = True
                ready, msg = self._tiktok_wait_for_debugger(port, timeout_seconds=14.0)
                if not ready:
                    last_error = msg + ' | Häufige Ursache: Chrome/Edge läuft bereits mit demselben Profil ohne Remote-Debug-Port.'
                    self._tiktok_cleanup_failed_start()
                    continue
                tab = self._tiktok_wait_for_livecenter_tab(port, timeout_seconds=12.0)
                if tab:
                    suffix = f' Main @{main_account} muss in diesem Browser eingeloggt sein.' if main_account else ' Main-Account muss in diesem Browser eingeloggt sein.'
                    return True, 'TikTok Main-Browser geöffnet.' + suffix, tab
                last_error = 'TikTok-Livecenter-Tab wurde nicht gefunden.'
            except Exception as exc:
                last_error = str(exc)
        return False, 'TikTok Main-Browser konnte nicht gestartet werden: ' + last_error, None

    def _tiktok_main_profile_dir(self, settings: dict[str, Any]) -> Path:
        custom = _clean_text(settings.get('main_profile_dir') or settings.get('profile_dir') or settings.get('browser_profile_dir')).strip('"')
        if custom:
            return Path(custom).expanduser()
        return data_dir() / 'tiktok' / 'main_profile'

    def _tiktok_profile_has_login_hint(self, profile_dir: Path) -> bool:
        try:
            default_dir = profile_dir / 'Default'
            if not default_dir.exists():
                return False
            hints = [
                default_dir / 'Cookies',
                default_dir / 'Network' / 'Cookies',
                default_dir / 'Local Storage' / 'leveldb',
                default_dir / 'Session Storage',
            ]
            for item in hints:
                if item.exists():
                    try:
                        if item.is_dir():
                            if any(item.iterdir()):
                                return True
                        elif item.stat().st_size > 0:
                            return True
                    except Exception:
                        return True
        except Exception:
            pass
        return False

    def _tiktok_main_debug_port(self, settings: dict[str, Any]) -> int:
        for key in ('main_remote_debug_port', 'main_debug_port', 'producer_debug_port'):
            try:
                value = int(settings.get(key) or 0)
                if 1024 <= value <= 65535:
                    return value
            except Exception:
                pass
        try:
            base = int(settings.get('remote_debug_port') or 9229)
        except Exception:
            base = 9229
        port = base + 1
        return port if 1024 <= port <= 65535 else 9230

    def _tiktok_find_browser_exes(self, preferred: str = '') -> list[str]:
        out: list[str] = []
        if preferred and os.path.exists(preferred):
            out.append(preferred)
        candidates = [
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%LocalAppData%\Microsoft\Edge\Application\msedge.exe'),
        ]
        for name in ('chrome', 'chrome.exe', 'msedge', 'msedge.exe', 'chromium', 'chromium.exe'):
            found = shutil.which(name)
            if found:
                candidates.append(found)
        for c in candidates:
            if c and os.path.exists(c) and c not in out:
                out.append(c)
        return out

    def _tiktok_debug_url(self, port: int, suffix: str = 'json') -> str:
        return f'http://127.0.0.1:{port}/{suffix}'

    def _tiktok_wait_for_debugger(self, port: int, timeout_seconds: float = 8.0) -> tuple[bool, str]:
        end = time.time() + max(0.5, timeout_seconds)
        last_exc = ''
        while time.time() < end:
            try:
                with urllib.request.urlopen(self._tiktok_debug_url(port, 'json/version'), timeout=1) as resp:
                    data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
                return True, 'TikTok Main-Browser Debug-Port erreichbar: ' + _clean_text(data.get('Browser') or 'Chrome/Edge')
            except Exception as exc:
                last_exc = str(exc)
                time.sleep(0.25)
        return False, 'TikTok Main-Browser Debug-Port nicht erreichbar: ' + last_exc

    def _tiktok_tabs(self, port: int) -> list[dict[str, Any]]:
        try:
            with urllib.request.urlopen(self._tiktok_debug_url(port, 'json'), timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '[]')
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _tiktok_open_new_tab(self, port: int, url: str) -> bool:
        suffix = 'json/new?' + urllib.request.quote(url, safe=':/?&=%@._-')
        for method in ('PUT', 'GET'):
            try:
                req = urllib.request.Request(self._tiktok_debug_url(port, suffix), method=method)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    return 200 <= getattr(resp, 'status', 200) < 300
            except Exception:
                pass
        return False

    def _tiktok_find_livecenter_tab(self, port: int) -> dict[str, Any] | None:
        best = None
        for tab in self._tiktok_tabs(port):
            url = _clean_text(tab.get('url')).lower()
            title = _clean_text(tab.get('title')).lower()
            combined = url + ' ' + title
            if 'livecenter.tiktok.com' in combined:
                return tab
            if 'tiktok.com' in combined or 'tiktok' in combined:
                best = tab
        return best

    def _tiktok_wait_for_livecenter_tab(self, port: int, timeout_seconds: float = 8.0) -> dict[str, Any] | None:
        end = time.time() + max(1.0, timeout_seconds)
        while time.time() < end:
            tab = self._tiktok_find_livecenter_tab(port)
            if tab:
                return tab
            time.sleep(0.35)
        return None

    def _save_tiktok_diagnostic(self, data: dict[str, Any], title: str = '', category: str = '', description: str = '') -> str:
        folder = data_dir() / PLUGIN_ID
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'tiktok_page_diagnostic.json'
        payload = {
            'created_at': int(time.time()),
            'wanted': {'title': title, 'category': category, 'description': description},
            'page': data,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path)

    def _tiktok_cleanup_failed_start(self) -> None:
        proc = getattr(self, '_tiktok_last_browser_process', None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        except Exception:
            pass
        finally:
            self._tiktok_last_browser_process = None
            self._tiktok_last_browser_was_launched = False

    def _tiktok_build_diagnostic_js(self, title: str = '', category: str = '', description: str = '') -> str:
        payload = json.dumps({'title': title, 'category': category, 'description': description}, ensure_ascii=False)
        js = '''
(() => {
  const wanted = __PAYLOAD__;
  const lower = v => String(v || '').toLowerCase();
  const trim = v => String(v || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0 && r.width > 2 && r.height > 2 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const textOf = el => trim([
    el.tagName, el.id, el.className,
    el.getAttribute && el.getAttribute('name'),
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('data-e2e'),
    el.getAttribute && el.getAttribute('data-testid'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText
  ].join(' ')).slice(0, 500);
  const valOf = el => {
    const tag = lower(el.tagName);
    if (tag === 'input' || tag === 'textarea') return String(el.value || '').slice(0, 300);
    return String(el.innerText || el.textContent || '').slice(0, 300);
  };
  const all = [];
  const walk = root => {
    try {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while ((n = w.nextNode())) {
        all.push(n);
        if (n.shadowRoot) walk(n.shadowRoot);
      }
    } catch(e) {}
  };
  walk(document);
  const frames = [];
  for (const fr of Array.from(document.querySelectorAll('iframe'))) {
    const info = {src: fr.src || '', title: fr.title || '', accessible: false};
    try { if (fr.contentDocument) { info.accessible = true; walk(fr.contentDocument); } } catch(e) { info.error = String(e).slice(0,200); }
    frames.push(info);
  }
  const isEditable = el => {
    const tag = lower(el.tagName);
    const ce = lower(el.getAttribute && el.getAttribute('contenteditable'));
    const role = lower(el.getAttribute && el.getAttribute('role'));
    return tag === 'textarea' || tag === 'input' || ce === 'true' || ce === 'plaintext-only' || role === 'textbox' || role === 'combobox';
  };
  const rectObj = el => {
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
  };
  const fields = all.filter(el => visible(el) && isEditable(el)).slice(0, 80).map((el, idx) => ({
    idx,
    tag: el.tagName,
    type: el.getAttribute && el.getAttribute('type'),
    role: el.getAttribute && el.getAttribute('role'),
    placeholder: el.getAttribute && el.getAttribute('placeholder'),
    ariaLabel: el.getAttribute && el.getAttribute('aria-label'),
    name: el.getAttribute && el.getAttribute('name'),
    id: el.id || '',
    className: String(el.className || '').slice(0,200),
    value: valOf(el),
    nearby: textOf(el),
    rect: rectObj(el)
  }));
  const buttons = all.filter(el => visible(el) && (lower(el.tagName) === 'button' || lower(el.getAttribute && el.getAttribute('role')) === 'button')).slice(0, 120).map((el, idx) => ({
    idx,
    tag: el.tagName,
    role: el.getAttribute && el.getAttribute('role'),
    text: trim(el.innerText || el.textContent || el.getAttribute('aria-label') || '').slice(0,300),
    ariaLabel: el.getAttribute && el.getAttribute('aria-label'),
    disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
    id: el.id || '',
    className: String(el.className || '').slice(0,200),
    rect: rectObj(el)
  }));
  const interestingText = all.filter(el => visible(el)).map(el => trim(el.innerText || el.textContent || '')).filter(t => /titel|title|kategorie|category|game|spiel|thema|topic|live|stream|save|speichern|update|bearbeiten|edit/i.test(t)).slice(0, 120);
  return {
    ok: true,
    wanted,
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    language: document.documentElement.lang || navigator.language || '',
    fields,
    buttons,
    frames,
    interestingText,
    bodyTextStart: trim(document.body ? document.body.innerText : '').slice(0, 3000)
  };
})()
'''
        return js.replace('__PAYLOAD__', payload)

    def _tiktok_build_update_js(self, title: str = '', category: str = '', description: str = '') -> str:
        payload = json.dumps({'title': title, 'category': category, 'description': description}, ensure_ascii=False)
        js = r'''
(async () => {
  const wanted = __PAYLOAD__;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const lower = v => String(v || '').toLowerCase();
  const isEditable = el => {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    const ce = lower(el.getAttribute && el.getAttribute('contenteditable'));
    const role = lower(el.getAttribute && el.getAttribute('role'));
    return tag === 'textarea' || tag === 'input' || ce === 'true' || ce === 'plaintext-only' || role === 'textbox' || role === 'combobox';
  };
  const visible = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return st.display !== 'none' && st.visibility !== 'hidden' && Number(st.opacity) !== 0 && r.width > 2 && r.height > 2 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const textOf = el => lower([
    el.tagName, el.id, el.className,
    el.getAttribute && el.getAttribute('name'),
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('data-e2e'),
    el.getAttribute && el.getAttribute('data-testid'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText
  ].join(' '));
  const all = [];
  const walk = root => {
    try {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while ((n = w.nextNode())) {
        all.push(n);
        if (n.shadowRoot) walk(n.shadowRoot);
      }
    } catch(e) {}
  };
  walk(document);
  for (const fr of Array.from(document.querySelectorAll('iframe'))) {
    try { if (fr.contentDocument) walk(fr.contentDocument); } catch(e) {}
  }
  const editables = all.filter(el => visible(el) && isEditable(el));
  const labelsNearAncestors = el => {
    let out = '';
    let p = el.parentElement;
    for (let i = 0; p && i < 4; i++, p = p.parentElement) out += ' ' + textOf(p);
    return out;
  };
  const labelsNear = el => {
    const r = el.getBoundingClientRect();
    const near = all.filter(x => visible(x) && !isEditable(x)).map(x => {
      const xr = x.getBoundingClientRect();
      const dy = Math.abs((xr.top + xr.bottom) / 2 - (r.top + r.bottom) / 2);
      const dx = Math.abs(xr.left - r.left);
      const before = xr.bottom <= r.top + 10 || xr.right <= r.left + 20;
      return {x, score: dy + dx * 0.2 + (before ? 0 : 120)};
    }).sort((a,b) => a.score - b.score).slice(0, 8).map(o => textOf(o.x)).join(' ');
    return textOf(el) + ' ' + labelsNearAncestors(el) + ' ' + near;
  };
  const setVal = (el, val) => {
    el.scrollIntoView({block:'center', inline:'nearest'});
    el.click(); el.focus();
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea') {
      const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(el, val); else el.value = val;
    } else {
      try { document.execCommand('selectAll', false, null); document.execCommand('insertText', false, val); } catch(e) {}
      if (!String(el.innerText || el.textContent || '').includes(val)) el.textContent = val;
    }
    for (const ev of ['beforeinput','input','change','keyup','blur']) {
      try { el.dispatchEvent(new InputEvent(ev, {bubbles:true, cancelable:true, inputType:'insertText', data:val})); }
      catch(e) { el.dispatchEvent(new Event(ev, {bubbles:true, cancelable:true})); }
    }
    return true;
  };
  const getVal = el => {
    if (!el) return '';
    const tag = lower(el.tagName);
    if (tag === 'input' || tag === 'textarea') return String(el.value || '').trim();
    return String(el.innerText || el.textContent || '').trim();
  };
  const norm = v => String(v || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const pickField = keys => {
    let scored = editables.map((el, idx) => {
      const info = labelsNear(el);
      let score = 0;
      for (const k of keys) if (info.includes(k)) score += 100;
      if (lower(el.tagName) === 'textarea') score += 12;
      if (lower(el.getAttribute && el.getAttribute('role')) === 'combobox') score += 8;
      const r = el.getBoundingClientRect();
      score -= Math.max(0, r.top) * 0.01;
      return {el, score, info, idx};
    }).sort((a,b) => b.score - a.score);
    return scored.length && scored[0].score >= 90 ? scored[0] : null;
  };
  const changed = [];
  const notes = [];
  let titleField = null;
  let descriptionField = null;
  let categoryField = null;
  if (wanted.title) {
    const f = pickField(['live title','stream title','titel','title','live-titel','livestream title']);
    if (f && setVal(f.el, String(wanted.title).slice(0, 80))) { titleField = f.el; changed.push('Titel'); }
    else notes.push('Titelfeld nicht gefunden');
  }
  if (wanted.description) {
    const f = pickField(['description','beschreibung','desc']);
    if (f && setVal(f.el, String(wanted.description))) { descriptionField = f.el; changed.push('Beschreibung'); }
    else notes.push('Beschreibungsfeld nicht gefunden');
  }
  if (wanted.category) {
    const f = pickField(['category','kategorie','game','spiel','topic','thema']);
    if (f) {
      categoryField = f.el;
      setVal(f.el, String(wanted.category));
      await sleep(700);
      const catLow = lower(wanted.category);
      const option = all.concat(Array.from(document.querySelectorAll('*'))).filter(visible).find(el => {
        const role = lower(el.getAttribute && el.getAttribute('role'));
        const t = lower(el.innerText || el.textContent || '');
        return (role === 'option' || role === 'menuitem' || role === 'button' || /option|item|select/.test(textOf(el))) && t && (t === catLow || t.includes(catLow));
      });
      if (option) { option.click(); changed.push('Kategorie'); }
      else { changed.push('Kategorie-Feld'); notes.push('Kategorie eingetragen, aber keine Dropdown-Option bestätigt'); }
    } else notes.push('Kategoriefeld nicht gefunden');
  }
  await sleep(400);
  window.scrollTo(0, document.body.scrollHeight);
  await sleep(500);
  const buttonCandidates = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
  let save = buttonCandidates.find(b => {
    const t = lower(b.innerText || b.textContent || b.getAttribute('aria-label') || '');
    if (!t) return false;
    if (/copy|kopieren|login|log in|cancel|abbrechen|delete|löschen/.test(t)) return false;
    if (t.trim() === 'go live' || t.trim() === 'live gehen') return false;
    return /save|speichern|update|aktualisieren|done|fertig|save & go live|save and go live/.test(t);
  });
  if (save && !save.disabled && save.getAttribute('aria-disabled') !== 'true') {
    save.scrollIntoView({block:'center', inline:'nearest'});
    save.click();
    await sleep(1800);
    const verifyNotes = [];
    if (wanted.title) {
      // Re-read the visible field after saving. Never report success only because a button was clicked.
      let readTitle = getVal(titleField);
      if (!readTitle) {
        const reread = pickField(['live title','stream title','titel','title','live-titel','livestream title']);
        readTitle = getVal(reread && reread.el);
      }
      const expected = norm(String(wanted.title).slice(0, 80));
      const got = norm(readTitle);
      if (!got || got !== expected) verifyNotes.push('Titel nicht bestätigt. Gelesen: ' + (readTitle || '<leer>'));
      else notes.push('Titel bestätigt: ' + readTitle);
    }
    if (wanted.description && descriptionField) {
      const readDesc = getVal(descriptionField);
      if (readDesc && !norm(readDesc).includes(norm(String(wanted.description)).slice(0, 40))) verifyNotes.push('Beschreibung eventuell nicht bestätigt.');
    }
    if (verifyNotes.length) return {ok:false, changed, detail:verifyNotes.join(' | ') + (notes.length ? ' | Hinweise: ' + notes.join(' | ') : '')};
    return {ok:true, changed, detail:(notes.length ? 'Hinweise: ' + notes.join(' | ') : 'TikTok Änderung wurde im Browser bestätigt.')};
  }
  if (changed.length) return {ok:false, changed, detail:'Felder gesetzt, aber kein Speichern/Update-Button gefunden. Hinweise: ' + notes.join(' | ')};
  return {ok:false, changed, detail:'Keine TikTok-Felder gefunden. Vermutlich nicht im Mainaccount eingeloggt oder TikTok Producer-Layout anders. Hinweise: ' + notes.join(' | ')};
})()
'''
        return js.replace('__PAYLOAD__', payload)

    def _tiktok_close_after_success(self, ws_url: str, tab: dict[str, Any] | None) -> None:
        try:
            if self._tiktok_last_browser_was_launched:
                self._cdp_call(ws_url, 'Browser.close', {}, timeout=3.0)
                return
            target_id = _clean_text((tab or {}).get('id'))
            if target_id:
                self._cdp_call(ws_url, 'Target.closeTarget', {'targetId': target_id}, timeout=3.0)
        except Exception:
            pass

    def _tiktok_show_browser_for_login(self, ws_url: str) -> None:
        try:
            win = self._cdp_call(ws_url, 'Browser.getWindowForTarget', {}, timeout=3.0)
            wid = (((win.get('result') or {}).get('windowId')))
            if wid is not None:
                self._cdp_call(ws_url, 'Browser.setWindowBounds', {'windowId': wid, 'bounds': {'windowState': 'normal'}}, timeout=3.0)
        except Exception:
            pass

    def _cdp_runtime_evaluate(self, ws_url: str, expression: str, timeout: float = 8.0) -> dict[str, Any]:
        return self._cdp_call(ws_url, 'Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True}, timeout=timeout)

    def _cdp_call(self, ws_url: str, method: str, params: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
        parsed = urlparse(ws_url)
        host = parsed.hostname or '127.0.0.1'
        port = int(parsed.port or 80)
        path = (parsed.path or '/') + (('?' + parsed.query) if parsed.query else '')
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            key = __import__('base64').b64encode(os.urandom(16)).decode('ascii')
            req = (
                f'GET {path} HTTP/1.1\r\n'
                f'Host: {host}:{port}\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\n'
                'Sec-WebSocket-Version: 13\r\n\r\n'
            )
            sock.sendall(req.encode('ascii'))
            header = b''
            while b'\r\n\r\n' not in header:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                header += chunk
            if b' 101 ' not in header.split(b'\r\n', 1)[0]:
                raise RuntimeError('WebSocket Handshake fehlgeschlagen: ' + header[:200].decode('utf-8', 'replace'))
            msg = {'id': 1, 'method': method, 'params': params or {}}
            self._ws_send_text(sock, json.dumps(msg, ensure_ascii=False))
            end_time = time.time() + timeout
            while time.time() < end_time:
                frame = self._ws_recv_text(sock)
                if not frame:
                    continue
                data = json.loads(frame)
                if data.get('id') == 1:
                    if data.get('error'):
                        raise RuntimeError(str(data.get('error')))
                    return data
            raise TimeoutError('keine CDP Antwort vom Browser')
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _ws_send_text(self, sock: socket.socket, text: str) -> None:
        payload = text.encode('utf-8')
        header = bytearray([0x81])
        ln = len(payload)
        if ln < 126:
            header.append(0x80 | ln)
        elif ln < 65536:
            header.append(0x80 | 126)
            header += struct.pack('!H', ln)
        else:
            header.append(0x80 | 127)
            header += struct.pack('!Q', ln)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        sock.sendall(bytes(header) + masked)

    def _ws_recv_text(self, sock: socket.socket) -> str:
        h = sock.recv(2)
        if len(h) < 2:
            return ''
        b1, b2 = h[0], h[1]
        opcode = b1 & 0x0F
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack('!H', sock.recv(2))[0]
        elif ln == 127:
            ln = struct.unpack('!Q', sock.recv(8))[0]
        if b2 & 0x80:
            mask = sock.recv(4)
            data = sock.recv(ln)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        else:
            data = b''
            while len(data) < ln:
                chunk = sock.recv(ln - len(data))
                if not chunk:
                    break
                data += chunk
        if opcode == 8:
            return ''
        return data.decode('utf-8', errors='replace')


    def _send_kick(self, pdata: dict[str, Any], host: PluginHost) -> tuple[bool, str]:
        title = _clean_text(pdata.get('title'))
        category = _clean_text(pdata.get('category'))
        description = _clean_text(pdata.get('description'))
        tags = _split_tags(pdata.get('tags'))
        if not title and not category and not tags and not description:
            return False, 'Keine Kick-Felder gesetzt.'

        settings = host.platform_settings('kick') if host is not None else {}
        token, token_msg = self._kick_get_main_token(settings)
        if not token:
            return False, token_msg or 'Kick Main-OAuth fehlt.'

        changed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        def do_patch(payload: dict[str, Any]) -> tuple[bool, str]:
            nonlocal token, token_msg
            try:
                self._kick_patch_channel(token, payload)
                return True, ''
            except urllib.error.HTTPError as exc:
                if getattr(exc, 'code', 0) == 401:
                    new_token, refresh_msg = self._kick_refresh_main_token(settings)
                    if new_token:
                        token = new_token
                        token_msg = refresh_msg or token_msg
                        try:
                            self._kick_patch_channel(token, payload)
                            return True, ''
                        except urllib.error.HTTPError as exc2:
                            return False, self._kick_format_http_error(exc2)
                    return False, refresh_msg or 'Kick Main-OAuth ist abgelaufen und konnte nicht erneuert werden.'
                return False, self._kick_format_http_error(exc)
            except Exception as exc:
                return False, str(exc)

        if title:
            ok, msg = do_patch({'stream_title': title[:120]})
            if ok:
                changed.append('Titel')
            else:
                errors.append('Titel: ' + msg)

        category_id = ''
        if category:
            if category.isdigit():
                category_id = category
            else:
                try:
                    category_id = self._kick_resolve_category_id(token, category)
                except urllib.error.HTTPError as exc:
                    if getattr(exc, 'code', 0) == 401:
                        token, token_msg = self._kick_refresh_main_token(settings)
                        if token:
                            try:
                                category_id = self._kick_resolve_category_id(token, category)
                            except urllib.error.HTTPError as exc2:
                                errors.append('Kategorie: ' + self._kick_format_http_error(exc2))
                        else:
                            errors.append('Kategorie: Kick Main-OAuth ist abgelaufen und konnte nicht erneuert werden.')
                    else:
                        errors.append('Kategorie: ' + self._kick_format_http_error(exc))
                except Exception as exc:
                    errors.append('Kategorie: ' + str(exc))

            if category_id:
                ok, msg = do_patch({'category_id': int(category_id)})
                if ok:
                    changed.append(f'Kategorie-ID {category_id}')
                else:
                    errors.append('Kategorie: ' + msg)
            elif category:
                skipped.append(f'Kategorie nicht aufgelöst: {category}')

        if tags:
            ok, msg = do_patch({'custom_tags': tags[:10]})
            if ok:
                changed.append('Tags')
            else:
                errors.append('Tags: ' + msg)

        if description:
            skipped.append('Beschreibung bei Kick nicht unterstützt/vorerst nur lokal gespeichert')

        suffix = f' ({token_msg})' if token_msg else ''
        if errors:
            base = ', '.join(changed) + ' aktualisiert. ' if changed else ''
            if skipped:
                base += ' | Übersprungen: ' + ', '.join(skipped)
            return False, (base + ' | Fehler: ' + ' | '.join(errors))[:1200]
        if changed:
            msg = ', '.join(changed) + ' aktualisiert.'
            if skipped:
                msg += ' | Übersprungen: ' + ', '.join(skipped)
            return True, msg + suffix
        if skipped:
            return False, 'Keine sendbaren Kick-Felder geändert. ' + ' | '.join(skipped)
        return False, 'Keine Kick-Änderung gesendet.'

    def _kick_get_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        main_token = _clean_text(settings.get('main_access_token'))
        if main_token:
            return main_token, 'Main-Token genutzt'
        if _clean_text(settings.get('main_refresh_token')):
            return self._kick_refresh_main_token(settings)
        token = _clean_text(settings.get('access_token'))
        if token:
            return token, 'Fallback-Access-Token genutzt, Main-OAuth fehlt'
        return '', 'Kick Main-OAuth fehlt. Bitte im Haupttool Kick Main neu anmelden.'

    def _kick_refresh_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        refresh = _clean_text(settings.get('main_refresh_token'))
        client_id = _clean_text(settings.get('client_id'))
        client_secret = _clean_text(settings.get('client_secret'))
        if not refresh:
            return '', 'Kick Main-Refresh-Token fehlt. Bitte im Haupttool Kick Main neu anmelden.'
        if not client_id or not client_secret:
            return '', 'Kick Client ID oder Client Secret fehlt.'
        payload = {
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh,
        }
        req = urllib.request.Request(
            KICK_TOKEN_URL,
            data=urllib.parse.urlencode(payload).encode('utf-8'),
            headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
            access = _clean_text(data.get('access_token')) if isinstance(data, dict) else ''
            if not access:
                return '', 'Kick Refresh lieferte keinen Access Token.'
            return access, 'Token per Refresh erneuert'
        except urllib.error.HTTPError as exc:
            return '', self._kick_format_http_error(exc)
        except Exception as exc:
            return '', f'Kick Refresh fehlgeschlagen: {exc}'

    def _kick_patch_channel(self, token: str, payload: dict[str, Any]) -> None:
        req = urllib.request.Request(
            KICK_CHANNELS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            method='PATCH',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()

    def _kick_resolve_category_id(self, token: str, category: str) -> str:
        query = _clean_text(category)
        if not query:
            return ''
        params = {'name': query, 'limit': '10'}
        url = KICK_CATEGORIES_URL + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
        rows = data.get('data') if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return ''
        wanted = query.strip().lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _clean_text(row.get('name')).lower()
            if name == wanted:
                cid = _clean_text(row.get('id'))
                return cid if cid.isdigit() else ''
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = _clean_text(row.get('id'))
            if cid.isdigit():
                return cid
        return ''

    def _kick_format_http_error(self, exc: urllib.error.HTTPError) -> str:
        try:
            raw = exc.read().decode('utf-8', errors='replace')
        except Exception:
            raw = str(exc)
        code = getattr(exc, 'code', '?')
        low = raw.lower()
        try:
            status_code = int(code or 0)
        except Exception:
            status_code = 0
        if status_code == 403 and ('channel:write' in low or 'scope' in low or 'forbidden' in low):
            return 'HTTP 403 · Kick Main-OAuth braucht vermutlich channel:write. Im Haupttool Kick Main neu anmelden, nachdem die Scopes channel:write enthalten.'
        return f'HTTP {code} {raw[:500]}'

    def _send_youtube(self, pdata: dict[str, Any], host: PluginHost) -> tuple[bool, str]:
        if time.time() < getattr(self, '_youtube_quota_blocked_until', 0.0):
            return False, 'YouTube API-Quota ist aufgebraucht. Senden wird vorerst übersprungen, damit nicht weiter sinnlos API-Requests verbraten werden.'
        title = _clean_text(pdata.get('title'))
        description = _clean_text(pdata.get('description'))
        tags = _split_tags(pdata.get('tags'))
        category = _clean_text(pdata.get('category'))
        if not title and not description and not tags and not category:
            return False, 'Keine YouTube-Felder gesetzt.'
        settings = host.platform_settings('youtube') if host is not None else {}
        token, token_msg = self._youtube_get_main_token(settings)
        if not token:
            return False, token_msg or 'YouTube Main-OAuth fehlt.'
        try:
            broadcast = self._youtube_active_broadcast(token)
        except urllib.error.HTTPError as exc:
            if getattr(exc, 'code', 0) == 401:
                token, token_msg = self._youtube_refresh_main_token(settings)
                if not token:
                    return False, token_msg or 'YouTube Main-OAuth ist abgelaufen und konnte nicht erneuert werden.'
                try:
                    broadcast = self._youtube_active_broadcast(token)
                except urllib.error.HTTPError as exc2:
                    if getattr(exc2, 'code', 0) == 401:
                        return False, 'YouTube OAuth ist trotz Refresh ungültig. Bitte im Haupttool YouTube Main neu anmelden.'
                    return False, self._format_http_error(exc2)
            else:
                return False, self._format_http_error(exc)
        except Exception as exc:
            return False, str(exc)

        if not broadcast:
            return False, 'Kein aktiver/kommender YouTube-Livestream gefunden.'

        video_id = _clean_text(broadcast.get('id'))
        if not video_id:
            return False, 'YouTube Video-/Broadcast-ID fehlt.'

        # Wichtig: NICHT liveBroadcasts.update mit dem kompletten snippet benutzen.
        # YouTube blockt bei laufenden/geplanten Streams sonst scheduledStartTime.
        # Für Titel/Beschreibung/Tags/Kategorie ist videos.update der sauberere Weg.
        try:
            ok_msg = self._youtube_update_video_snippet(
                token=token,
                video_id=video_id,
                title=title,
                description=description,
                tags=tags,
                category=category,
            )
            suffix = f' ({token_msg})' if token_msg else ''
            return True, ok_msg + suffix
        except urllib.error.HTTPError as exc:
            if getattr(exc, 'code', 0) == 401:
                token, token_msg = self._youtube_refresh_main_token(settings)
                if not token:
                    return False, token_msg or 'YouTube Main-OAuth ist abgelaufen und konnte nicht erneuert werden.'
                try:
                    ok_msg = self._youtube_update_video_snippet(
                        token=token,
                        video_id=video_id,
                        title=title,
                        description=description,
                        tags=tags,
                        category=category,
                    )
                    return True, ok_msg + ' (Token per Refresh erneuert)'
                except urllib.error.HTTPError as exc2:
                    if getattr(exc2, 'code', 0) == 401:
                        return False, 'YouTube OAuth ist trotz Refresh ungültig. Bitte im Haupttool YouTube Main neu anmelden.'
                    return False, self._format_http_error(exc2)
            return False, self._format_http_error(exc)
        except Exception as exc:
            return False, str(exc)

    def _youtube_update_video_snippet(self, token: str, video_id: str, title: str = '', description: str = '', tags: list[str] | None = None, category: str = '') -> str:
        url_get = 'https://www.googleapis.com/youtube/v3/videos?' + urllib.parse.urlencode({'part': 'snippet', 'id': video_id})
        req_get = urllib.request.Request(url_get, headers={'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(req_get, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
        items = data.get('items') if isinstance(data, dict) else []
        if not isinstance(items, list) or not items:
            raise RuntimeError('YouTube Video-Snippet zum Livestream wurde nicht gefunden.')

        old_snippet = dict((items[0] or {}).get('snippet') or {})
        new_snippet: dict[str, Any] = {
            'title': title[:100] if title else _clean_text(old_snippet.get('title')),
            'description': description if description else _clean_text(old_snippet.get('description')),
            'categoryId': _clean_text(old_snippet.get('categoryId')) or '20',
        }

        old_tags = old_snippet.get('tags')
        if tags:
            new_snippet['tags'] = tags
        elif isinstance(old_tags, list):
            new_snippet['tags'] = [str(t) for t in old_tags if str(t).strip()]

        # YouTube erwartet bei videos.update eine categoryId im snippet.
        # Wenn der Nutzer direkt eine numerische YouTube-Kategorie-ID einträgt, übernehmen wir sie.
        # Text wie "Gaming" bleibt lokal/vorbereitet und überschreibt die vorhandene ID nicht blind.
        category = _clean_text(category)
        if category.isdigit():
            new_snippet['categoryId'] = category

        payload = {'id': video_id, 'snippet': new_snippet}
        req_put = urllib.request.Request(
            'https://www.googleapis.com/youtube/v3/videos?part=snippet',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            method='PUT',
        )
        with urllib.request.urlopen(req_put, timeout=20) as resp:
            resp.read()

        changed = []
        if title:
            changed.append('Titel')
        if description:
            changed.append('Beschreibung')
        if tags:
            changed.append('Tags')
        if category.isdigit():
            changed.append(f'Kategorie-ID {category}')
        return ', '.join(changed) + ' aktualisiert.' if changed else 'YouTube Video-Snippet aktualisiert.'

    def _youtube_get_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        # YouTube Access Tokens are short lived. For info3ditor we need the
        # broadcaster/main account and stale cached tokens caused HTTP 401.
        # So when a Main Refresh Token exists, always create a fresh access
        # token for this send operation instead of trusting the cached one.
        main_refresh = _clean_text(settings.get('main_refresh_token'))
        if main_refresh:
            return self._youtube_refresh_main_token(settings, main_only=True)

        token = _clean_text(settings.get('main_access_token'))
        if token:
            return token, 'Main-Token genutzt, aber kein Main-Refresh-Token gefunden'

        # Last compatibility fallback only. This is usually the bot token and
        # cannot update the broadcaster stream, but older test builds stored
        # the main login here. Prefer a refresh token when possible.
        refresh = _clean_text(settings.get('refresh_token'))
        if refresh:
            return self._youtube_refresh_main_token(settings, main_only=False)

        token = _clean_text(settings.get('access_token'))
        if token:
            return token, 'Fallback-Access-Token genutzt, Main-OAuth fehlt'

        return '', 'YouTube Main-OAuth fehlt. Bitte im Haupttool YouTube Main neu anmelden.'

    def _youtube_refresh_main_token(self, settings: dict[str, Any], main_only: bool = True) -> tuple[str, str]:
        refresh = _clean_text(settings.get('main_refresh_token'))
        if not refresh and not main_only:
            refresh = _clean_text(settings.get('refresh_token'))
        client_id = _clean_text(settings.get('client_id'))
        client_secret = _clean_text(settings.get('client_secret'))
        if not refresh:
            return '', 'YouTube Main-Refresh-Token fehlt. Bitte im Haupttool YouTube Main neu anmelden.'
        if not client_id:
            return '', 'YouTube Client ID fehlt.'
        payload = {
            'client_id': client_id,
            'grant_type': 'refresh_token',
            'refresh_token': refresh,
        }
        if client_secret:
            payload['client_secret'] = client_secret
        req = urllib.request.Request(
            YOUTUBE_TOKEN_URL,
            data=urllib.parse.urlencode(payload).encode('utf-8'),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
            access = _clean_text(data.get('access_token')) if isinstance(data, dict) else ''
            if not access:
                return '', 'YouTube Refresh lieferte keinen Access Token.'
            return access, 'Token per Refresh erneuert'
        except urllib.error.HTTPError as exc:
            return '', self._format_http_error(exc)
        except Exception as exc:
            return '', f'YouTube Refresh fehlgeschlagen: {exc}'

    def _format_http_error(self, exc: urllib.error.HTTPError) -> str:
        try:
            raw_detail = exc.read().decode('utf-8', errors='replace')
        except Exception:
            raw_detail = str(exc)
        detail = raw_detail[:500]
        if getattr(exc, 'code', 0) == 403 and ('quotaExceeded' in raw_detail or 'youtube.quota' in raw_detail or 'exceeded your' in raw_detail):
            self._youtube_quota_blocked_until = time.time() + 3600.0
            return 'YouTube API-Quota ist aufgebraucht. OAuth funktioniert jetzt, aber Google blockt weitere YouTube-API-Updates wegen quotaExceeded. Warte bis zum Quota-Reset oder nutze ein anderes/erhöhtes Google-API-Projekt.'
        return f'HTTP {getattr(exc, "code", "?")} {detail}'

    def _youtube_active_broadcast(self, token: str) -> dict[str, Any] | None:
        for status in ('active', 'upcoming'):
            params = {'part': 'id,snippet,status', 'broadcastStatus': status, 'broadcastType': 'all', 'maxResults': '5'}
            url = 'https://www.googleapis.com/youtube/v3/liveBroadcasts?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
            items = data.get('items') if isinstance(data, dict) else []
            if isinstance(items, list) and items:
                return dict(items[0] or {})
        return None

if QtWidgets is not None:
    class _PresetEditDialog(QtWidgets.QDialog):
        def __init__(self, preset: dict[str, Any] | None = None, parent=None, language: str = 'de') -> None:
            super().__init__(parent)
            self.language = language if language in {'de', 'en'} else 'de'
            self.setWindowTitle('info3ditor - Preset bearbeiten')
            self.resize(760, 620)
            self._preset = deepcopy(preset or {'id': '', 'name': '', 'platforms': {}})
            self._widgets: dict[str, Any] = {}
            self._build_ui()
            self._load_values()

        def _build_ui(self) -> None:
            root = QtWidgets.QVBoxLayout(self)
            form = QtWidgets.QFormLayout()
            self.name_edit = QtWidgets.QLineEdit()
            self.name_edit.setPlaceholderText('z.B. Arc Raiders')
            form.addRow('Preset-Titel / Gamename', self.name_edit)
            root.addLayout(form)

            tabs = QtWidgets.QTabWidget()
            tabs.addTab(self._platform_tab('twitch', [
                ('enabled', 'Twitch aktiv', 'bool'),
                ('title', 'Streamtitel', 'text'),
                ('category', 'Kategorie/Game Name', 'text'),
                ('game_id', 'Kategorie/Game ID optional', 'text'),
                ('tags', 'Tags, Komma getrennt', 'text'),
                ('description', 'Notiz/Beschreibung lokal', 'multiline'),
            ]), 'Twitch')
            tabs.addTab(self._platform_tab('youtube', [
                ('enabled', 'YouTube aktiv', 'bool'),
                ('title', 'Titel', 'text'),
                ('description', 'Beschreibung', 'multiline'),
                ('category', 'Kategorie lokal/vorbereitet', 'text'),
                ('tags', 'Tags lokal/vorbereitet', 'text'),
            ]), 'YouTube')
            tabs.addTab(self._platform_tab('kick', [
                ('enabled', 'Kick aktiv', 'bool'),
                ('title', 'Titel', 'text'),
                ('category', 'Kategorie', 'text'),
                ('description', 'Beschreibung/Notiz lokal', 'multiline'),
                ('tags', 'Tags, Komma getrennt', 'text'),
            ]), 'Kick')
            tabs.addTab(self._platform_tab('tiktok', [
                ('enabled', 'TikTok aktiv', 'bool'),
                ('title', 'Live-Titel', 'text'),
                ('description', 'Beschreibung/Notiz', 'multiline'),
            ]), 'TikTok')
            root.addWidget(tabs, 1)

            note = QtWidgets.QLabel('Hinweis: Gespeichert wird in data/info3ditor/presets.json. Twitch wird zentral gesendet; YouTube nutzt den Main-OAuth, wenn ein aktiver/kommender Livestream gefunden wird. TikTok ist aktuell in Arbeit und wird beim Senden bewusst übersprungen, bis ein stabiler offizieller oder bestätigter Browser-Weg vorhanden ist. Kick sendet Titel/Kategorie/Tags über den zentralen Main-OAuth; Beschreibung bleibt dort lokal.')
            note.setWordWrap(True)
            root.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def _platform_tab(self, platform: str, fields: list[tuple[str, str, str]]) -> QtWidgets.QWidget:
            page = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(page)
            layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            for key, label, ftype in fields:
                full_key = f'{platform}.{key}'
                if ftype == 'bool':
                    widget = QtWidgets.QCheckBox()
                elif ftype == 'multiline':
                    widget = QtWidgets.QPlainTextEdit()
                    widget.setMinimumHeight(100)
                else:
                    widget = QtWidgets.QLineEdit()
                self._widgets[full_key] = widget
                layout.addRow(label, widget)
            return page

        def _load_values(self) -> None:
            self.name_edit.setText(_clean_text(self._preset.get('name')))
            platforms = self._preset.get('platforms') if isinstance(self._preset.get('platforms'), dict) else {}
            for full_key, widget in self._widgets.items():
                platform, key = full_key.split('.', 1)
                pdata = platforms.get(platform) if isinstance(platforms.get(platform), dict) else {}
                value = pdata.get(key)
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(_as_bool(value, False))
                elif isinstance(widget, QtWidgets.QPlainTextEdit):
                    widget.setPlainText(_clean_text(value))
                else:
                    widget.setText(_clean_text(value))
            self._lock_tiktok_tab()

        def _lock_tiktok_tab(self) -> None:
            notice = 'TIK TOK ist momentan noch nicht nutzbar.'
            enabled = self._widgets.get('tiktok.enabled')
            if enabled is not None:
                enabled.setChecked(False)
                enabled.setEnabled(False)
                enabled.setToolTip(notice)
            title = self._widgets.get('tiktok.title')
            if title is not None:
                title.setEnabled(False)
                title.setToolTip(notice)
            description = self._widgets.get('tiktok.description')
            if description is not None:
                description.setPlainText(notice)
                description.setEnabled(False)
                description.setToolTip(notice)

        def preset(self) -> dict[str, Any]:
            name = _clean_text(self.name_edit.text()) or 'Neues Preset'
            pid = _clean_text(self._preset.get('id')) or _slug(name)
            out: dict[str, Any] = {'id': pid, 'name': name, 'platforms': {}}
            for platform in SUPPORTED_PLATFORMS:
                out['platforms'][platform] = {}
            for full_key, widget in self._widgets.items():
                platform, key = full_key.split('.', 1)
                if platform == 'tiktok' and key == 'enabled':
                    value = False
                elif isinstance(widget, QtWidgets.QCheckBox):
                    value = widget.isChecked()
                elif isinstance(widget, QtWidgets.QPlainTextEdit):
                    value = widget.toPlainText().strip()
                else:
                    value = widget.text().strip()
                out['platforms'][platform][key] = value
            return PresetStore()._normalize(out)


    class _PresetPanelWidget(QtWidgets.QWidget):
        def __init__(self, plugin: Info3ditorPlugin, host: PluginHost | None, settings_dialog: Any | None = None, parent=None, language: str = 'de') -> None:
            super().__init__(parent)
            self.plugin = plugin
            self.host = host or getattr(plugin, '_host', None)
            self.settings_dialog = settings_dialog
            self.language = language if language in {'de', 'en'} else 'de'
            self.presets: list[dict[str, Any]] = []
            self._build_ui()
            self.reload()

        def _build_ui(self) -> None:
            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(10)

            top = QtWidgets.QHBoxLayout()
            self.add_btn = QtWidgets.QPushButton('Neuer Eintrag')
            self.add_btn.clicked.connect(self.add_preset)
            top.addWidget(self.add_btn)
            top.addStretch(1)
            root.addLayout(top)

            hint = QtWidgets.QLabel('Alle gespeicherten Einträge sind direkt sichtbar. Über „Senden“ wird der jeweilige Eintrag sofort an alle darin aktivierten Plattformen geschickt.')
            hint.setWordWrap(True)
            root.addWidget(hint)

            self.table_widget = QtWidgets.QTableWidget()
            self.table_widget.setColumnCount(2)
            self.table_widget.setHorizontalHeaderLabels(['Eintrag', 'Aktion'])
            self.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table_widget.setAlternatingRowColors(True)
            self.table_widget.setWordWrap(False)
            self.table_widget.verticalHeader().setVisible(False)
            self.table_widget.verticalHeader().setDefaultSectionSize(62)
            self.table_widget.itemDoubleClicked.connect(lambda _item: self.edit_preset())

            header = self.table_widget.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            root.addWidget(self.table_widget, 1)

            row = QtWidgets.QHBoxLayout()
            self.close_btn = QtWidgets.QPushButton('Schließen')
            self.close_btn.clicked.connect(self._close_parent_dialog)
            row.addStretch(1)
            row.addWidget(self.close_btn)
            root.addLayout(row)

            self.info_label = QtWidgets.QLabel('')
            self.info_label.setWordWrap(True)
            root.addWidget(self.info_label)

        def _close_parent_dialog(self) -> None:
            try:
                if self.settings_dialog is not None and hasattr(self.settings_dialog, 'close'):
                    self.settings_dialog.close()
                    return
            except Exception:
                pass
            self.close()

        def _platform_line(self, preset: dict[str, Any], platform: str) -> tuple[str, str]:
            platforms = preset.get('platforms') if isinstance(preset.get('platforms'), dict) else {}
            pdata = platforms.get(platform) if isinstance(platforms.get(platform), dict) else {}
            if platform == 'twitch':
                parts = [('Titel', pdata.get('title')), ('Kategorie', pdata.get('category') or pdata.get('game_id')), ('Tags', pdata.get('tags')), ('Notiz', pdata.get('description'))]
            elif platform == 'youtube':
                parts = [('Titel', pdata.get('title')), ('Beschreibung', pdata.get('description')), ('Kategorie', pdata.get('category')), ('Tags', pdata.get('tags'))]
            elif platform == 'kick':
                parts = [('Titel', pdata.get('title')), ('Kategorie', pdata.get('category')), ('Beschreibung', pdata.get('description')), ('Tags', pdata.get('tags'))]
            else:
                parts = [('Titel', pdata.get('title')), ('Notiz', pdata.get('description'))]

            enabled = _as_bool(pdata.get('enabled'), False)
            if platform == 'tiktok':
                enabled = False
            visible_parts = [f'{label}: {_clean_text(value)}' for label, value in parts if _clean_text(value)]
            text = ' | '.join(visible_parts) if visible_parts else '—'
            if not enabled:
                text = 'Aus | ' + text if text != '—' else 'Aus'
            tooltip = '\n'.join(visible_parts) if visible_parts else text
            return text, tooltip

        def _make_item(self, text: str, tooltip: str = '') -> QtWidgets.QTableWidgetItem:
            item = QtWidgets.QTableWidgetItem(text)
            item.setToolTip(tooltip or text)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = item.font()
            font.setPointSize(max(font.pointSize() + 3, 12))
            font.setBold(True)
            item.setFont(font)
            return item

        def _make_action_widget(self, row_index: int) -> QtWidgets.QWidget:
            box = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(box)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)
            send_btn = QtWidgets.QPushButton('Senden')
            edit_btn = QtWidgets.QPushButton('Bearbeiten')
            delete_btn = QtWidgets.QPushButton('Löschen')
            send_btn.clicked.connect(lambda _checked=False, idx=row_index: self.send_preset(idx))
            edit_btn.clicked.connect(lambda _checked=False, idx=row_index: self.edit_preset(idx))
            delete_btn.clicked.connect(lambda _checked=False, idx=row_index: self.delete_preset(idx))
            for btn in (send_btn, edit_btn, delete_btn):
                btn.setMinimumHeight(34)
                btn.setMinimumWidth(88)
                layout.addWidget(btn)
            return box

        def reload(self) -> None:
            self.presets = self.plugin.store.load()
            self.table_widget.setRowCount(0)
            self.table_widget.setRowCount(len(self.presets))
            for row, preset in enumerate(self.presets):
                name = _clean_text(preset.get('name')) or 'Neues Preset'
                self.table_widget.setItem(row, 0, self._make_item(name))
                self.table_widget.setCellWidget(row, 1, self._make_action_widget(row))
                self.table_widget.setRowHeight(row, 62)
            self.info_label.setText('Bereit.')
            self.plugin._update_settings_dialog_fields(self.settings_dialog)

        def _selected_index(self) -> int:
            row = self.table_widget.currentRow()
            return row if 0 <= row < len(self.presets) else -1

        def add_preset(self) -> None:
            dlg = _PresetEditDialog(parent=self, language=self.language)
            if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
                return
            preset = dlg.preset()
            existing_ids = {_clean_text(p.get('id')) for p in self.presets}
            base_id = _slug(preset.get('name'))
            pid = base_id
            n = 2
            while pid in existing_ids:
                pid = f'{base_id}_{n}'
                n += 1
            preset['id'] = pid
            self.presets.append(preset)
            self.plugin.store.save(self.presets)
            self.reload()
            self.table_widget.setCurrentCell(len(self.presets) - 1, 0)

        def edit_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            dlg = _PresetEditDialog(self.presets[idx], parent=self, language=self.language)
            if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
                return
            self.presets[idx] = dlg.preset()
            self.plugin.store.save(self.presets)
            self.reload()
            self.table_widget.setCurrentCell(idx, 0)

        def delete_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            name = _clean_text(self.presets[idx].get('name'))
            reply = QtWidgets.QMessageBox.question(self, 'info3ditor', f'Preset "{name}" wirklich löschen?')
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self.presets.pop(idx)
            self.plugin.store.save(self.presets)
            self.reload()
            if self.presets:
                self.table_widget.setCurrentCell(min(idx, len(self.presets) - 1), 0)

        def send_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            self.host = self.host or getattr(self.plugin, '_host', None)
            self.table_widget.setCurrentCell(idx, 0)
            self.plugin.send_preset_async(self.presets[idx], self.host)
            self.info_label.setText(f'Sende "{_clean_text(self.presets[idx].get("name"))}" ... Log im Hauptfenster beachten.')

        def open_data_folder(self) -> None:
            try:
                if QtGui is not None:
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.plugin.store.folder)))
            except Exception:
                pass


    class _PresetListDialog(QtWidgets.QDialog):
        def __init__(self, plugin: Info3ditorPlugin, host: PluginHost | None, settings_dialog: Any | None = None, parent=None, language: str = 'de') -> None:
            super().__init__(parent)
            self.plugin = plugin
            self.host = host
            self.settings_dialog = settings_dialog
            self.language = language if language in {'de', 'en'} else 'de'
            self.setWindowTitle('info3ditor')
            self.resize(1180, 620)
            self.presets: list[dict[str, Any]] = []
            self._build_ui()
            self.reload()

        def _build_ui(self) -> None:
            root = QtWidgets.QVBoxLayout(self)

            top = QtWidgets.QHBoxLayout()
            self.add_btn = QtWidgets.QPushButton('Neuer Eintrag')
            self.add_btn.clicked.connect(self.add_preset)
            top.addWidget(self.add_btn)
            top.addStretch(1)
            root.addLayout(top)

            hint = QtWidgets.QLabel('Alle gespeicherten Einträge sind direkt sichtbar. Über „Senden“ wird der jeweilige Eintrag sofort an alle darin aktivierten Plattformen geschickt.')
            hint.setWordWrap(True)
            root.addWidget(hint)

            self.table_widget = QtWidgets.QTableWidget()
            self.table_widget.setColumnCount(2)
            self.table_widget.setHorizontalHeaderLabels(['Eintrag', 'Aktion'])
            self.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table_widget.setAlternatingRowColors(True)
            self.table_widget.setWordWrap(False)
            self.table_widget.verticalHeader().setVisible(False)
            self.table_widget.verticalHeader().setDefaultSectionSize(62)
            self.table_widget.itemDoubleClicked.connect(lambda _item: self.edit_preset())

            header = self.table_widget.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            root.addWidget(self.table_widget, 1)

            row = QtWidgets.QHBoxLayout()
            self.close_btn = QtWidgets.QPushButton('Schließen')
            self.close_btn.clicked.connect(self.close)
            row.addStretch(1)
            row.addWidget(self.close_btn)
            root.addLayout(row)

            self.info_label = QtWidgets.QLabel('')
            self.info_label.setWordWrap(True)
            root.addWidget(self.info_label)

        def _platform_line(self, preset: dict[str, Any], platform: str) -> tuple[str, str]:
            platforms = preset.get('platforms') if isinstance(preset.get('platforms'), dict) else {}
            pdata = platforms.get(platform) if isinstance(platforms.get(platform), dict) else {}
            if platform == 'twitch':
                parts = [
                    ('Titel', pdata.get('title')),
                    ('Kategorie', pdata.get('category') or pdata.get('game_id')),
                    ('Tags', pdata.get('tags')),
                    ('Notiz', pdata.get('description')),
                ]
            elif platform == 'youtube':
                parts = [
                    ('Titel', pdata.get('title')),
                    ('Beschreibung', pdata.get('description')),
                    ('Kategorie', pdata.get('category')),
                    ('Tags', pdata.get('tags')),
                ]
            elif platform == 'kick':
                parts = [
                    ('Titel', pdata.get('title')),
                    ('Kategorie', pdata.get('category')),
                    ('Beschreibung', pdata.get('description')),
                    ('Tags', pdata.get('tags')),
                ]
            else:
                parts = [
                    ('Titel', pdata.get('title')),
                    ('Notiz', pdata.get('description')),
                ]

            enabled = _as_bool(pdata.get('enabled'), False)
            visible_parts = [f'{label}: {_clean_text(value)}' for label, value in parts if _clean_text(value)]
            text = ' | '.join(visible_parts) if visible_parts else '—'
            if not enabled:
                text = 'Aus | ' + text if text != '—' else 'Aus'
            tooltip = '\n'.join(visible_parts) if visible_parts else text
            return text, tooltip

        def _make_item(self, text: str, tooltip: str = '') -> QtWidgets.QTableWidgetItem:
            item = QtWidgets.QTableWidgetItem(text)
            item.setToolTip(tooltip or text)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = item.font()
            font.setPointSize(max(font.pointSize() + 3, 12))
            font.setBold(True)
            item.setFont(font)
            return item

        def _make_action_widget(self, row_index: int) -> QtWidgets.QWidget:
            box = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(box)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)

            send_btn = QtWidgets.QPushButton('Senden')
            edit_btn = QtWidgets.QPushButton('Bearbeiten')
            delete_btn = QtWidgets.QPushButton('Löschen')
            send_btn.clicked.connect(lambda _checked=False, idx=row_index: self.send_preset(idx))
            edit_btn.clicked.connect(lambda _checked=False, idx=row_index: self.edit_preset(idx))
            delete_btn.clicked.connect(lambda _checked=False, idx=row_index: self.delete_preset(idx))
            for btn in (send_btn, edit_btn, delete_btn):
                btn.setMinimumHeight(34)
                btn.setMinimumWidth(88)
                layout.addWidget(btn)
            return box

        def reload(self) -> None:
            self.presets = self.plugin.store.load()
            self.table_widget.setRowCount(0)
            self.table_widget.setRowCount(len(self.presets))

            for row, preset in enumerate(self.presets):
                name = _clean_text(preset.get('name')) or 'Neues Preset'

                self.table_widget.setItem(row, 0, self._make_item(name))
                self.table_widget.setCellWidget(row, 1, self._make_action_widget(row))
                self.table_widget.setRowHeight(row, 62)

            self.info_label.setText('Bereit.')
            self.plugin._update_settings_dialog_fields(self.settings_dialog)

        def _selected_index(self) -> int:
            row = self.table_widget.currentRow()
            return row if 0 <= row < len(self.presets) else -1

        def add_preset(self) -> None:
            dlg = _PresetEditDialog(parent=self, language=self.language)
            if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
                return
            preset = dlg.preset()
            existing_ids = {_clean_text(p.get('id')) for p in self.presets}
            base_id = _slug(preset.get('name'))
            pid = base_id
            n = 2
            while pid in existing_ids:
                pid = f'{base_id}_{n}'
                n += 1
            preset['id'] = pid
            self.presets.append(preset)
            self.plugin.store.save(self.presets)
            self.reload()
            self.table_widget.setCurrentCell(len(self.presets) - 1, 0)

        def edit_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            dlg = _PresetEditDialog(self.presets[idx], parent=self, language=self.language)
            if dlg.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
                return
            self.presets[idx] = dlg.preset()
            self.plugin.store.save(self.presets)
            self.reload()
            self.table_widget.setCurrentCell(idx, 0)

        def delete_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            name = _clean_text(self.presets[idx].get('name'))
            reply = QtWidgets.QMessageBox.question(self, 'info3ditor', f'Preset "{name}" wirklich löschen?')
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self.presets.pop(idx)
            self.plugin.store.save(self.presets)
            self.reload()
            if self.presets:
                self.table_widget.setCurrentCell(min(idx, len(self.presets) - 1), 0)

        def send_preset(self, idx: int | None = None) -> None:
            if idx is None:
                idx = self._selected_index()
            if idx < 0 or idx >= len(self.presets):
                return
            self.table_widget.setCurrentCell(idx, 0)
            self.plugin.send_preset_async(self.presets[idx], self.host)
            self.info_label.setText(f'Sende "{_clean_text(self.presets[idx].get("name"))}" ... Log im Hauptfenster beachten.')

        def open_data_folder(self) -> None:
            try:
                if QtGui is not None:
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.plugin.store.folder)))
            except Exception:
                pass


def create_plugin() -> Info3ditorPlugin:
    return Info3ditorPlugin()
