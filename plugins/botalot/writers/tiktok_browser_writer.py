
from __future__ import annotations
import ctypes
import json
import os
import subprocess
import time
import urllib.request
import shutil
import webbrowser
import socket
import base64
import struct
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'plugins':
            return parent.parent / 'data' / plugin_name
    return Path(__file__).resolve().parent / 'data'

from PySide6 import QtWidgets
from common import as_bool, to_int

class TikTokBrowserWriter:
    """
    TikTok has no reliable public chat-send API for this setup.
    This writer therefore uses a dedicated browser profile for the second account.

    Flow:
    1. Open TikTok Live with this writer button.
    2. Log into the second TikTok account in that browser profile once.
    3. Put the cursor into TikTok's chat input.
    4. botalot pastes the prepared answer and presses Enter.

    Optional login check is done through Chrome/Edge remote-debugging page titles/URLs.
    The actual send remains focus-based on purpose because TikTok changes DOM selectors often.
    """
    def __init__(self, plugin_dir: Path, logger) -> None:
        self.plugin_dir = plugin_dir
        self._log = logger
        # Do NOT keep the login profile inside the plugin folder.
        # godisalotachat plugin updates replace this folder, which would also
        # wipe TikTok cookies and force a fresh login after every botalot update.
        # The real profile path is resolved from settings / AppData at runtime.
        self.profile_dir = self._default_profile_dir()
        self._processes: list[subprocess.Popen] = []

    def _default_profile_dir(self) -> Path:
        """Stable browser profile folder for the TikTok bot account.

        This is intentionally outside the plugin directory so TikTok login
        cookies survive plugin updates/reinstalls. It does not know the TikTok
        password and does not auto-fill credentials; it only reuses the browser
        session after the user logged in once.
        """
        return _main_data_dir('botalot') / 'tiktok_bot_profile'

    def _resolve_profile_dir(self, settings: dict | None = None) -> Path:
        settings = dict(settings or {})
        custom = str(settings.get('tiktok_profile_dir') or '').strip().strip('\"')
        if custom:
            custom = os.path.expandvars(custom)
        profile = Path(custom).expanduser() if custom else self._default_profile_dir()

        # One-time migration from old versions where the profile lived inside
        # plugins/botalot. This saves the existing login when possible.
        old_profile = self.plugin_dir / 'browser_profile_tiktok_second_account'
        try:
            if old_profile.exists() and not profile.exists():
                profile.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(old_profile, profile, dirs_exist_ok=True)
                self._log(f'TikTok Botprofil aus altem Pluginordner übernommen: {profile}')
        except Exception as exc:
            self._log(f'TikTok Botprofil konnte nicht migriert werden: {exc}')
        return profile

    def _profile_login_marker(self, settings: dict | None = None) -> Path:
        return self._resolve_profile_dir(settings or {}) / 'botalot_tiktok_login_ok.json'

    def _mark_profile_logged_in(self, settings: dict | None = None, reason: str = '') -> None:
        try:
            marker = self._profile_login_marker(settings or {})
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                'logged_in_hint': True,
                'reason': str(reason or 'tiktok tab without login page'),
                'updated_at': time.time(),
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def _profile_has_tiktok_storage(self, profile: Path) -> bool:
        """Best-effort fallback for old profiles that were logged in before
        botalot had a login marker. We do not read passwords; this only checks
        whether the dedicated Chromium profile already contains TikTok cookies
        or storage files.
        """
        try:
            if not profile.exists():
                return False
            roots = [
                profile / 'Default' / 'Network',
                profile / 'Default' / 'Local Storage',
                profile / 'Default' / 'IndexedDB',
                profile / 'Default' / 'Session Storage',
                profile / 'Default' / 'Service Worker',
            ]
            for root in roots:
                if not root.exists():
                    continue
                for f in root.rglob('*'):
                    try:
                        if not f.is_file() or f.stat().st_size <= 0:
                            continue
                        name = f.name.lower()
                        parent = str(f.parent).lower()
                        if 'tiktok' in name or 'tiktok' in parent:
                            return True
                        if name in ('cookies', 'cookies-journal') and f.stat().st_size > 2048:
                            with f.open('rb') as fh:
                                chunk = fh.read(2 * 1024 * 1024).lower()
                            if b'tiktok' in chunk:
                                return True
                        if f.suffix.lower() in ('.ldb', '.log', '.sqlite', '.db') and f.stat().st_size > 128:
                            with f.open('rb') as fh:
                                chunk = fh.read(512 * 1024).lower()
                            if b'tiktok' in chunk:
                                return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False

    def _account_name(self, value: Any) -> str:
        raw = str(value or '').strip()
        if raw.startswith('http://') or raw.startswith('https://'):
            # Accept old/full URLs, but extract the @name when possible.
            marker = 'tiktok.com/@'
            low = raw.lower()
            idx = low.find(marker)
            if idx >= 0:
                tail = raw[idx + len(marker):].split('?', 1)[0].split('#', 1)[0]
                return tail.strip('/').split('/', 1)[0].lstrip('@')
        return raw.lstrip('@').strip().strip('/')

    def build_live_url(self, settings: dict) -> str:
        """Build TikTok live URL from the main/live account name.

        User only has to enter the main account name, without @. The browser
        profile itself is the bot account profile, so this URL is intentionally
        the MAIN live page while the logged-in browser user is the BOT.
        """
        raw = str(settings.get('tiktok_main_account') or settings.get('tiktok_live_url') or '').strip()
        if raw.startswith('http://') or raw.startswith('https://'):
            return raw
        name = self._account_name(raw)
        if not name:
            return 'https://www.tiktok.com/live'
        return f'https://www.tiktok.com/@{name}/live'

    def build_bot_login_url(self, settings: dict) -> str:
        # Important: this opens a DEDICATED browser profile for the BOT account.
        # TikTok does not support a useful login_hint here, so the user still
        # chooses/logs into the bot account manually inside this separate profile.
        return 'https://www.tiktok.com/login'

    def _find_browser_exes(self, preferred: str = '') -> list[str]:
        """Return Chrome/Edge executables. We avoid webbrowser.open here because
        the normal browser cannot give us a remote-debugging port reliably.
        """
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

    def _open_new_tab_via_debugger(self, settings: dict, url: str) -> bool:
        """If our bot browser is already running, open the URL inside that exact
        debug instance. This prevents accidentally using the normal Chrome.
        """
        try:
            req = urllib.request.Request(self._debug_json_url(settings, 'json/new?' + urllib.request.quote(url, safe=':/?&=%@._-')), method='PUT')
            with urllib.request.urlopen(req, timeout=2) as resp:
                return 200 <= getattr(resp, 'status', 200) < 300
        except Exception:
            try:
                # Older Chromium builds accepted GET here.
                with urllib.request.urlopen(self._debug_json_url(settings, 'json/new?' + urllib.request.quote(url, safe=':/?&=%@._-')), timeout=2) as resp:
                    return 200 <= getattr(resp, 'status', 200) < 300
            except Exception:
                return False

    def _debug_tabs(self, settings: dict) -> list[dict]:
        try:
            with urllib.request.urlopen(self._debug_json_url(settings, 'json'), timeout=1.5) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace'))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _tab_matches_mode(self, tab: dict, mode: str, url: str) -> bool:
        tab_url = str(tab.get('url') or '').lower()
        wanted = str(url or '').lower()
        if not tab_url:
            return False
        if mode == 'bot':
            return 'tiktok.com/login' in tab_url or ('tiktok.com' in tab_url and '/@' not in tab_url)
        # live mode: avoid duplicate main-live tabs. Match exact account/live when possible.
        if wanted and wanted in tab_url:
            return True
        if '/live' in wanted and '/live' in tab_url and 'tiktok.com/@' in wanted:
            wanted_name = wanted.split('tiktok.com/@', 1)[1].split('/', 1)[0]
            return f'tiktok.com/@{wanted_name}/live' in tab_url
        return False

    def _has_matching_tab(self, settings: dict, mode: str, url: str) -> bool:
        return any(self._tab_matches_mode(t, mode, url) for t in self._debug_tabs(settings))

    def _minimize_tracked_windows(self) -> None:
        if os.name != 'nt':
            return
        try:
            user32 = ctypes.windll.user32
            SW_MINIMIZE = 6
            pids = {p.pid for p in self._processes if p and p.poll() is None}
            if not pids:
                return
            EnumWindows = user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            IsWindowVisible = user32.IsWindowVisible
            ShowWindow = user32.ShowWindow

            def callback(hwnd, lparam):
                pid = ctypes.c_ulong()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids and IsWindowVisible(hwnd):
                    ShowWindow(hwnd, SW_MINIMIZE)
                return True
            EnumWindows(EnumWindowsProc(callback), 0)
        except Exception:
            pass

    def _popen_browser(self, exe: str, args: list[str]) -> subprocess.Popen:
        kwargs = {
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'stdin': subprocess.DEVNULL,
            'close_fds': True,
        }
        # Keep the bot browser as its own process group. That way it does not
        # attach to a currently running normal Chrome/Edge session.
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
        else:
            kwargs['start_new_session'] = True
        proc = subprocess.Popen([exe] + args, **kwargs)
        self._processes.append(proc)
        return proc


    def profile_looks_logged_in(self, settings: dict | None = None) -> bool:
        """Best-effort check whether the persistent bot browser profile has cookies.

        We cannot know the TikTok password and we do not scrape credentials. This
        only checks whether Chromium has an existing cookie DB in the configured
        profile, which usually means the bot account can stay logged in.
        """
        try:
            profile = self._resolve_profile_dir(settings or {})
            marker = self._profile_login_marker(settings or {})
            if marker.exists() and marker.stat().st_size > 0:
                return True
            candidates = [
                profile / 'Default' / 'Network' / 'Cookies',
                profile / 'Default' / 'Cookies',
                profile / 'Network' / 'Cookies',
                profile / 'Cookies',
            ]
            for p in candidates:
                if p.exists() and p.stat().st_size > 4096:
                    try:
                        with p.open('rb') as fh:
                            if b'tiktok' in fh.read(2 * 1024 * 1024).lower():
                                return True
                    except Exception:
                        return True
            if self._profile_has_tiktok_storage(profile):
                return True
        except Exception:
            pass
        return False

    def open_browser(self, settings: dict, mode: str = 'live', minimized: bool = False) -> bool:
        url = self.build_bot_login_url(settings) if mode == 'bot' else self.build_live_url(settings)
        browser_path = str(settings.get('tiktok_browser_path') or '').strip().strip('"')
        port = to_int(settings.get('tiktok_remote_debug_port'), 9229, 1024, 65535)
        self.profile_dir = self._resolve_profile_dir(settings)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # If the dedicated debug browser is already running, reuse it.
        # Do not create duplicate login/live tabs on autoconnect/reload.
        ready, _ = self.wait_for_debugger(settings, timeout_seconds=0.6)
        if ready:
            if self._has_matching_tab(settings, mode, url):
                if minimized:
                    self._minimize_tracked_windows()
                self._log('TikTok Botaccount-Browser läuft bereits; vorhandener passender Tab wird genutzt.')
                return True
            if self._open_new_tab_via_debugger(settings, url):
                if minimized:
                    self._minimize_tracked_windows()
                self._log('TikTok Seite im bereits laufenden Botaccount-Browser geöffnet.')
                return True

        args = [
            f'--remote-debugging-port={port}',
            '--remote-debugging-address=127.0.0.1',
            f'--user-data-dir={str(self.profile_dir)}',
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
            '--new-window',
            '--disable-features=Translate',
        ]
        if minimized:
            args.append('--start-minimized')
        args.append(url)

        exes = self._find_browser_exes(browser_path)
        if not exes:
            self._log('Kein Chrome/Edge gefunden. Bitte Chrome/Edge Pfad manuell im Plugin setzen. Der normale Standardbrowser reicht für TikTok-Connect nicht.')
            return False

        last_error = ''
        for exe in exes:
            try:
                self._popen_browser(exe, args)
                ready, msg = self.wait_for_debugger(settings, timeout_seconds=8.0)
                if ready:
                    if minimized:
                        time.sleep(0.4)
                        self._minimize_tracked_windows()
                    if mode == 'bot':
                        self._log(f'TikTok Botaccount-Browser geöffnet. Profil bleibt gespeichert: {self.profile_dir}. Falls noch nicht angemeldet: einmal mit BOTACCOUNT einloggen.')
                    else:
                        self._log('TikTok Main-Live in der eigenen Botaccount-Browser-Instanz geöffnet. Du schreibst dort als Botaccount in den Main-Livechat.')
                    return True
                last_error = msg
            except Exception as exc:
                last_error = str(exc)

        self._log('TikTok Browser konnte nicht als eigene Debug-Instanz gestartet werden. ' + last_error)
        return False



    def _live_tabs(self, settings: dict) -> list[dict]:
        live_url = self.build_live_url(settings).lower()
        main_account = self._account_name(settings.get('tiktok_main_account') or settings.get('tiktok_live_url')).lower()
        tabs: list[dict] = []
        for tab in self._debug_tabs(settings):
            url = str(tab.get('url') or '').lower()
            if 'tiktok.com' not in url:
                continue
            if live_url and live_url in url:
                tabs.append(tab)
                continue
            if main_account and f'tiktok.com/@{main_account}/live' in url:
                tabs.append(tab)
                continue
            if '/live' in url and 'tiktok.com/@' in url:
                tabs.append(tab)
        return tabs

    def reload_live_tab(self, settings: dict) -> tuple[bool, str]:
        """Reload the existing TikTok live tab in the dedicated bot browser.

        Used when tiktok_live reports offline -> live. This avoids continuous
        polling/reloading and only refreshes the browser once per live session.
        """
        settings = dict(settings or {})
        ready, msg = self.wait_for_debugger(settings, timeout_seconds=1.5)
        if not ready:
            started = self.open_browser(settings, mode='live', minimized=True)
            if not started:
                return False, msg
            ready, msg = self.wait_for_debugger(settings, timeout_seconds=5.0)
            if not ready:
                return False, msg

        tabs = self._live_tabs(settings)
        if not tabs:
            if self.open_browser(settings, mode='live', minimized=True):
                return True, 'Kein vorhandener Live-Tab gefunden; Live-Seite wurde im Botbrowser geöffnet.'
            return False, 'Kein TikTok Live-Tab im Botbrowser gefunden.'

        last_error = ''
        for tab in tabs:
            ws_url = str(tab.get('webSocketDebuggerUrl') or '')
            if not ws_url:
                last_error = 'Live-Tab hat keine DevTools-WebSocket-URL.'
                continue
            try:
                self._cdp_call(ws_url, 'Page.reload', {'ignoreCache': True}, timeout=5.0)
                return True, 'TikTok Live-Tab wurde per DevTools neu geladen.'
            except Exception as exc:
                last_error = str(exc)

        return False, last_error or 'TikTok Live-Tab konnte nicht neu geladen werden.'

    def _debug_json_url(self, settings: dict, suffix: str = 'json') -> str:
        port = to_int(settings.get('tiktok_remote_debug_port'), 9229, 1024, 65535)
        return f'http://127.0.0.1:{port}/{suffix}'

    def is_debug_unreachable_message(self, message: str) -> bool:
        low = str(message or '').lower()
        return ('nicht erreichbar' in low) or ('timed out' in low) or ('connection refused' in low) or ('urlopen error' in low)

    def wait_for_debugger(self, settings: dict, timeout_seconds: float = 8.0) -> tuple[bool, str]:
        end = time.time() + max(1.0, timeout_seconds)
        last_exc = ''
        while time.time() < end:
            try:
                with urllib.request.urlopen(self._debug_json_url(settings, 'json/version'), timeout=1) as resp:
                    data = json.loads(resp.read().decode('utf-8', errors='replace'))
                browser = str(data.get('Browser') or 'Chrome/Edge')
                return True, f'TikTok Bot-Browser Debug-Port erreichbar: {browser}'
            except Exception as exc:
                last_exc = str(exc)
                time.sleep(0.35)
        return False, ('TikTok-Browser gestartet, aber Debug-Port ist nicht erreichbar. '
                       'Prüfe ob Chrome/Edge wirklich mit diesem Profil geöffnet wurde, ob der Port frei ist, '
                       'oder setze den Chrome/Edge Pfad manuell. Detail: ' + last_exc)

    def check_login_hint(self, settings: dict) -> tuple[bool, str]:
        port = to_int(settings.get('tiktok_remote_debug_port'), 9229, 1024, 65535)
        expected = self._account_name(settings.get('tiktok_second_account')).lower()
        main_account = self._account_name(settings.get('tiktok_main_account') or settings.get('tiktok_live_url')).lower()
        try:
            with urllib.request.urlopen(self._debug_json_url(settings, 'json'), timeout=2) as resp:
                tabs = json.loads(resp.read().decode('utf-8', errors='replace'))
            combined = '\n'.join((str(t.get('title','')) + ' ' + str(t.get('url',''))) for t in tabs).lower()
            if 'tiktok.com' not in combined:
                return False, 'Remote-Browser läuft, aber kein TikTok-Tab gefunden.'
            if 'login' in combined:
                return False, 'TikTok-Tab gefunden, sieht aber noch nach Login-Seite aus.'
            self._mark_profile_logged_in(settings, 'debug tab is on TikTok and not on login page')
            live_ok = True
            if main_account and not main_account.startswith('http'):
                live_ok = main_account in combined
            if not live_ok:
                return False, f'TikTok läuft, aber Live-Kanal @{main_account} wurde im Browser nicht erkannt.'
            if expected and expected in combined:
                return True, f'TikTok bereit: Botprofil @{expected} im separaten Browser erkannt.'
            return True, f'TikTok-Tab gefunden. Wichtig: Dieser separate Browser muss mit dem Botaccount @{expected or "?"} eingeloggt sein, nicht mit dem Mainaccount.'
        except Exception as exc:
            return False, f'TikTok-Browser nicht erreichbar. Erst "Botaccount-Browser öffnen" klicken und dort mit dem Botaccount einloggen. Detail: {exc}'


    def close_browser(self, settings: dict | None = None) -> tuple[bool, str]:
        """Close only the dedicated TikTok browser instance opened by botalot.

        We first ask the remote-debugging instance to close its TikTok tabs, then
        terminate the processes we started. This avoids touching the user's normal
        Chrome/Edge windows.
        """
        settings = dict(settings or {})
        closed_tabs = 0
        process_hits = 0
        errors: list[str] = []

        # Ask Chromium to shut down gracefully first, so cookies and
        # local/session storage are flushed to the persistent bot profile.
        try:
            with urllib.request.urlopen(self._debug_json_url(settings, 'json/version'), timeout=1.5) as resp:
                version = json.loads(resp.read().decode('utf-8', errors='replace'))
            browser_ws = str(version.get('webSocketDebuggerUrl') or '').strip()
            if browser_ws:
                try:
                    self._cdp_call(browser_ws, 'Browser.close', {}, timeout=3.0)
                    closed_tabs += 1
                    time.sleep(1.2)
                except Exception as exc:
                    errors.append(str(exc))
        except Exception:
            pass

        # Fallback: close tabs in the dedicated debug instance. Chromium exposes
        # one /json/close/<tabId> endpoint per target.
        try:
            with urllib.request.urlopen(self._debug_json_url(settings, 'json'), timeout=1.5) as resp:
                tabs = json.loads(resp.read().decode('utf-8', errors='replace'))
            for tab in tabs if isinstance(tabs, list) else []:
                tab_id = str(tab.get('id') or '').strip()
                if not tab_id:
                    continue
                try:
                    with urllib.request.urlopen(self._debug_json_url(settings, 'json/close/' + tab_id), timeout=1.0) as _resp:
                        pass
                    closed_tabs += 1
                except Exception as exc:
                    errors.append(str(exc))
        except Exception:
            # Debugger may already be gone. That's fine; still clean tracked proc list.
            pass

        # Stop only leftovers. Avoid /F first because forced kills can lose the
        # TikTok cookie/session write on Chromium shutdown.
        alive: list[subprocess.Popen] = []
        for proc in list(self._processes):
            try:
                if proc.poll() is not None:
                    continue
                process_hits += 1
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                    continue
                except Exception:
                    pass
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
                else:
                    proc.kill()
            except Exception as exc:
                alive.append(proc)
                errors.append(str(exc))
        self._processes = alive

        if closed_tabs or process_hits:
            return True, f'TikTok Zusatzbrowser geschlossen. Tabs: {closed_tabs}, Prozesse: {process_hits}'
        return True, 'Kein von botalot gestarteter TikTok-Zusatzbrowser mehr offen.'


    def ban_user(self, settings: dict, username: str, reason: str = '') -> bool:
        user = str(username or '').strip().lstrip('@')
        if not user:
            self._log('TikTok Ban übersprungen: Nutzer fehlt.')
            return False
        # TikTok hat keine stabile öffentliche Ban-API in diesem Browser-Writer.
        # Best effort: falls TikTok einen Mod-Chatbefehl im Livechat akzeptiert,
        # wird er über den Botaccount-Browser auf der Ursprungsplattform abgesetzt.
        ok = self.send(settings, f'/block @{user}')
        if ok:
            self._log(f'TikTok Moderation Ban-Befehl gesendet: @{user}')
        else:
            self._log(f'TikTok Moderation Ban-Befehl konnte nicht gesendet werden: @{user}')
        return ok

    def unban_user(self, settings: dict, username: str) -> bool:
        user = str(username or '').strip().lstrip('@')
        if not user:
            self._log('TikTok Unban übersprungen: Nutzer fehlt.')
            return False
        ok = self.send(settings, f'/unblock @{user}')
        if ok:
            self._log(f'TikTok Moderation Unban-Befehl gesendet: @{user}')
        else:
            self._log(f'TikTok Moderation Unban-Befehl konnte nicht gesendet werden: @{user}')
        return ok

    def send(self, settings: dict, message: str) -> bool:
        if not as_bool(settings.get('tiktok_clipboard_focus_send'), False):
            self._log('TikTok Senden ist aus. Aktiviere "TikTok per Zweitaccount-Browser senden".')
            return False

        ok, detail = self._send_via_devtools(settings, message)
        if ok:
            self._log('TikTok DevTools-Senden OK: ' + detail)
            return True
        self._log('TikTok DevTools-Senden fehlgeschlagen: ' + detail)

        if as_bool(settings.get('tiktok_disable_focus_fallback'), False):
            self._log('TikTok Fokus-Fallback fuer diese Nachricht deaktiviert, damit nichts in Twitch landet.')
            return False

        try:
            app = QtWidgets.QApplication.instance()
            if app is None:
                self._log('TikTok Fokus-Fallback: QApplication nicht verfügbar.')
                return False
            app.clipboard().setText(message)
            delay = to_int(settings.get('tiktok_send_delay_ms'), 150, 0, 3000) / 1000.0
            if delay > 0:
                time.sleep(delay)
            if not self._windows_ctrl_v_enter():
                self._log('TikTok Fokus-Fallback: SendInput fehlgeschlagen. Das geht nur unter Windows mit fokussiertem Chatfeld.')
                return False
            self._log('TikTok Fokus-Fallback ausgelöst. Wenn nichts im Chat erscheint, war das Chatfeld nicht fokussiert oder TikTok hat Enter blockiert.')
            return True
        except Exception as exc:
            self._log(f'TikTok Fokus-Fallback fehlgeschlagen: {exc}')
            return False

    def _send_via_devtools(self, settings: dict, message: str) -> tuple[bool, str]:
        try:
            tab = self._find_tiktok_live_tab(settings)
            if not tab:
                return False, 'kein TikTok-Live-Tab im Botbrowser gefunden'
            ws_url = str(tab.get('webSocketDebuggerUrl') or '').strip()
            if not ws_url:
                return False, 'TikTok-Tab hat keine webSocketDebuggerUrl'
            js = self._build_tiktok_send_js(message)
            result = self._cdp_runtime_evaluate(ws_url, js, timeout=4.0)
            value = (((result.get('result') or {}).get('result') or {}).get('value'))
            if isinstance(value, dict):
                if value.get('ok'):
                    return True, str(value.get('detail') or 'gesendet')
                detail = str(value.get('detail') or value)
                # If TikTok changed the DOM so no input is discoverable, try a
                # low-level CDP click/type fallback in the live chat area.
                if 'kein sichtbares Chat-Eingabefeld' in detail:
                    ok2, detail2 = self._send_via_cdp_click_type(ws_url, message)
                    if ok2:
                        return True, detail2
                    return False, detail + ' | CDP-Fallback: ' + detail2
                return False, detail
            return False, 'unerwartete DevTools-Antwort: ' + str(result)[:500]
        except Exception as exc:
            return False, str(exc)

    def _find_tiktok_live_tab(self, settings: dict) -> dict | None:
        try:
            with urllib.request.urlopen(self._debug_json_url(settings, 'json'), timeout=2) as resp:
                tabs = json.loads(resp.read().decode('utf-8', errors='replace'))
        except Exception:
            return None
        if not isinstance(tabs, list):
            return None
        main = self._account_name(settings.get('tiktok_main_account') or settings.get('tiktok_live_url')).lower()
        best = None
        for tab in tabs:
            url = str(tab.get('url') or '').lower()
            title = str(tab.get('title') or '').lower()
            if 'tiktok.com' not in (url + title):
                continue
            if '/live' in url and (not main or main in url or main in title):
                return tab
            if best is None:
                best = tab
        return best

    def _build_tiktok_send_js(self, message: str) -> str:
        payload = json.dumps(str(message or ''))
        js = """
(() => {
  const msg = __MSG__;
  const lower = v => String(v || '').toLowerCase();
  const info = el => lower([
    el.tagName,
    el.id,
    el.className,
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('data-e2e'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText
  ].join(' '));
  const isVisible = el => {
    if (!el || !el.getBoundingClientRect) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const allNodes = [];
  const walk = root => {
    try {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let n;
      while ((n = w.nextNode())) {
        allNodes.push(n);
        if (n.shadowRoot) walk(n.shadowRoot);
      }
    } catch (e) {}
  };
  walk(document);
  for (const fr of Array.from(document.querySelectorAll('iframe'))) {
    try { if (fr.contentDocument) walk(fr.contentDocument); } catch (e) {}
  }

  const wanted = el => {
    const ce = lower(el.getAttribute && el.getAttribute('contenteditable'));
    const role = lower(el.getAttribute && el.getAttribute('role'));
    const t = info(el);
    if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && (!el.type || /text|search/.test(lower(el.type))))) return true;
    if (ce === 'true' || ce === 'plaintext-only') return true;
    if (role === 'textbox') return true;
    if (/comment|chat|message|nachricht|kommentar|input|editor|drafteditor|send/.test(t) && (el.matches('div,span,p,[data-e2e],[class],[role]'))) return true;
    return false;
  };

  let candidates = allNodes.filter(el => wanted(el) && isVisible(el));
  // Prefer real editable/textbox nodes, then nodes that sit low/right where TikTok usually places live chat.
  candidates.sort((a,b) => {
    const ae = (lower(a.getAttribute && a.getAttribute('contenteditable')) === 'true' || lower(a.getAttribute && a.getAttribute('contenteditable')) === 'plaintext-only' || a.tagName === 'TEXTAREA' || a.tagName === 'INPUT' || lower(a.getAttribute && a.getAttribute('role')) === 'textbox') ? 1 : 0;
    const be = (lower(b.getAttribute && b.getAttribute('contenteditable')) === 'true' || lower(b.getAttribute && b.getAttribute('contenteditable')) === 'plaintext-only' || b.tagName === 'TEXTAREA' || b.tagName === 'INPUT' || lower(b.getAttribute && b.getAttribute('role')) === 'textbox') ? 1 : 0;
    if (ae !== be) return be - ae;
    const ar = a.getBoundingClientRect(); const br = b.getBoundingClientRect();
    return (br.bottom + br.right * 0.15) - (ar.bottom + ar.right * 0.15);
  });

  let input = candidates[0];
  if (!input) {
    return {ok:false, detail:'kein sichtbares Chat-Eingabefeld gefunden; Kandidaten=' + allNodes.filter(wanted).length};
  }

  // If the matched wrapper contains a real editable child, use that child.
  const child = input.querySelector && input.querySelector('div[contenteditable="true"], div[contenteditable="plaintext-only"], textarea, input[type="text"], [role="textbox"], .public-DraftEditor-content');
  if (child && isVisible(child)) input = child;

  input.scrollIntoView({block:'center', inline:'nearest'});
  input.click();
  input.focus();

  const setNativeValue = (el, val) => {
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(el, val); else el.value = val;
      return true;
    }
    return false;
  };

  let setOk = setNativeValue(input, msg);
  if (!setOk) {
    try {
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, msg);
    } catch(e) {}
    if (!String(input.innerText || input.textContent || '').includes(msg)) {
      input.textContent = msg;
    }
  }

  for (const ev of ['beforeinput','input','change','keyup']) {
    try {
      input.dispatchEvent(new InputEvent(ev, {bubbles:true, cancelable:true, inputType:'insertText', data:msg}));
    } catch(e) {
      input.dispatchEvent(new Event(ev, {bubbles:true, cancelable:true}));
    }
  }

  const nowText = String(input.value || input.innerText || input.textContent || '').trim();
  if (!nowText) return {ok:false, detail:'Chatfeld gefunden (' + info(input).slice(0,120) + '), aber Text wurde nicht gesetzt'};

  const buttons = allNodes.filter(el => isVisible(el) && (el.tagName === 'BUTTON' || lower(el.getAttribute && el.getAttribute('role')) === 'button'));
  let btn = buttons.find(b => /send|senden|post|posten|comment|kommentieren/.test(info(b)) && !b.disabled && b.getAttribute('aria-disabled') !== 'true');
  if (!btn) {
    // often the send button sits directly beside/above the input; pick the nearest small button to the right/below.
    const r = input.getBoundingClientRect();
    btn = buttons
      .map(b => ({b, r:b.getBoundingClientRect()}))
      .filter(x => x.r.left >= r.left - 20 && x.r.top >= r.top - 80 && x.r.bottom <= r.bottom + 120)
      .sort((x,y) => Math.abs(x.r.left-r.right)+Math.abs(x.r.top-r.top) - (Math.abs(y.r.left-r.right)+Math.abs(y.r.top-r.top)))[0]?.b;
  }
  if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
    btn.click();
    return {ok:true, detail:'Chatfeld gefunden (' + info(input).slice(0,80) + '), Text gesetzt, Button geklickt'};
  }

  const evOpts = {bubbles:true, cancelable:true, key:'Enter', code:'Enter', keyCode:13, which:13};
  input.dispatchEvent(new KeyboardEvent('keydown', evOpts));
  input.dispatchEvent(new KeyboardEvent('keypress', evOpts));
  input.dispatchEvent(new KeyboardEvent('keyup', evOpts));
  return {ok:true, detail:'Chatfeld gefunden (' + info(input).slice(0,80) + '), Text gesetzt, Enter gesendet'};
})()
"""
        return js.replace('__MSG__', payload)

    def _send_via_cdp_click_type(self, ws_url: str, message: str) -> tuple[bool, str]:
        """Last-resort TikTok send method.

        Some TikTok live layouts hide the real editor from normal DOM queries.
        This uses DevTools input events: click likely chat-input positions,
        insert text, press Enter. It still uses the dedicated bot browser only.
        """
        points = []
        try:
            metrics = self._cdp_call(ws_url, 'Page.getLayoutMetrics', {}, timeout=4.0)
            viewport = (((metrics.get('result') or {}).get('cssVisualViewport')) or {})
            width = int(float(viewport.get('clientWidth') or 1280))
            height = int(float(viewport.get('clientHeight') or 720))
        except Exception:
            width, height = 1280, 720
        # TikTok web live chat is usually on the right and low; also try center-low.
        points.extend([
            (max(40, width - 260), max(40, height - 88)),
            (max(40, width - 360), max(40, height - 78)),
            (max(40, width - 180), max(40, height - 118)),
            (width // 2, max(40, height - 70)),
        ])
        last = ''
        for x, y in points:
            try:
                self._cdp_call(ws_url, 'Input.dispatchMouseEvent', {'type':'mouseMoved','x':x,'y':y}, timeout=3.0)
                self._cdp_call(ws_url, 'Input.dispatchMouseEvent', {'type':'mousePressed','x':x,'y':y,'button':'left','clickCount':1}, timeout=3.0)
                self._cdp_call(ws_url, 'Input.dispatchMouseEvent', {'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1}, timeout=3.0)
                time.sleep(0.08)
                self._cdp_call(ws_url, 'Input.insertText', {'text': str(message or '')}, timeout=3.0)
                time.sleep(0.05)
                self._cdp_call(ws_url, 'Input.dispatchKeyEvent', {'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13}, timeout=3.0)
                self._cdp_call(ws_url, 'Input.dispatchKeyEvent', {'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'nativeVirtualKeyCode':13}, timeout=3.0)
                return True, f'CDP-Fallback: bei x={x}, y={y} geklickt, Text eingefügt, Enter gesendet'
            except Exception as exc:
                last = str(exc)
        return False, last or 'CDP-Fallback konnte nicht tippen'

    def _cdp_call(self, ws_url: str, method: str, params: dict | None = None, timeout: float = 4.0) -> dict:
        parsed = urlparse(ws_url)
        host = parsed.hostname or '127.0.0.1'
        port = int(parsed.port or 80)
        path = (parsed.path or '/') + (('?' + parsed.query) if parsed.query else '')
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            key = base64.b64encode(os.urandom(16)).decode('ascii')
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

    def _cdp_runtime_evaluate(self, ws_url: str, expression: str, timeout: float = 4.0) -> dict:
        parsed = urlparse(ws_url)
        host = parsed.hostname or '127.0.0.1'
        port = int(parsed.port or 80)
        path = (parsed.path or '/') + (('?' + parsed.query) if parsed.query else '')
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
            key = base64.b64encode(os.urandom(16)).decode('ascii')
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
            msg = {'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': expression, 'returnByValue': True, 'awaitPromise': True}}
            self._ws_send_text(sock, json.dumps(msg, ensure_ascii=False))
            end_time = time.time() + timeout
            while time.time() < end_time:
                frame = self._ws_recv_text(sock)
                if not frame:
                    continue
                data = json.loads(frame)
                if data.get('id') == 1:
                    return data
            raise TimeoutError('keine Runtime.evaluate Antwort vom Browser')
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _ws_send_text(self, sock: socket.socket, text: str) -> None:
        data = text.encode('utf-8')
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack('!H', n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('!Q', n))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        sock.sendall(bytes(header) + masked)

    def _ws_recv_text(self, sock: socket.socket) -> str:
        first = sock.recv(2)
        if len(first) < 2:
            return ''
        b1, b2 = first
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack('!H', sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', sock.recv(8))[0]
        mask = sock.recv(4) if masked else b''
        payload = b''
        while len(payload) < length:
            payload += sock.recv(length - len(payload))
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 8:
            return ''
        if opcode == 1:
            return payload.decode('utf-8', 'replace')
        return ''

    def _windows_ctrl_v_enter(self) -> bool:
        if not hasattr(ctypes, 'windll'):
            return False
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_V = 0x56
        VK_RETURN = 0x0D
        def key(vk: int, up: bool = False) -> None:
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if up else 0, 0)
        key(VK_CONTROL); key(VK_V); key(VK_V, True); key(VK_CONTROL, True)
        time.sleep(0.05)
        key(VK_RETURN); key(VK_RETURN, True)
        return True
