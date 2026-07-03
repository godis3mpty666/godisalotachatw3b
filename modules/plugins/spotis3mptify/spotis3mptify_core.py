# File: spotis3mptify_core.py
from __future__ import annotations
import http.server, socketserver, threading, time, os, re, urllib.parse, urllib.request, urllib.error
import json, random, sys, socket, ssl, select, base64, hashlib, shutil, subprocess
from typing import Callable, Optional, Dict, Any, Tuple

# ======================= PORTABLE PATHS =======================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
def _detect_app_dir() -> str:
    # Runtime data belongs next to the portable app, never inside modules.
    try:
        if getattr(sys, "frozen", False) and getattr(sys, "executable", None):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    try:
        current = _SCRIPT_DIR
        while current and os.path.dirname(current) != current:
            if os.path.basename(current).lower() == "modules":
                return os.path.dirname(current)
            current = os.path.dirname(current)
    except Exception:
        pass
    return os.path.dirname(_SCRIPT_DIR)

APP_DIR = _detect_app_dir()
DATA_DIR = os.path.join(APP_DIR, "data", "spotis3mptify")
AUTH_DIR = os.path.join(DATA_DIR, "auth")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
NOWPLAYING_DIR = os.path.join(DATA_DIR, "nowplaying")
COVERS_DIR = os.path.join(DATA_DIR, "covers")
PLAYLISTS_DIR = os.path.join(DATA_DIR, "playlists")
STATE_DIR = os.path.join(DATA_DIR, "state")
EXPORT_DIR = os.path.join(DATA_DIR, "export")
CERTS_DIR = os.path.join(DATA_DIR, "certs")
YOUTUBE_DIR = os.path.join(DATA_DIR, "youtube")
for _d in (DATA_DIR, AUTH_DIR, CONFIG_DIR, NOWPLAYING_DIR, COVERS_DIR, PLAYLISTS_DIR, STATE_DIR, EXPORT_DIR, CERTS_DIR, YOUTUBE_DIR):
    os.makedirs(_d, exist_ok=True)
CUSTOM_OVERLAY_JSON = os.path.join(CONFIG_DIR, "custom_overlay.json")

def _legacy_internal_data_dir() -> str:
    return os.path.join(_SCRIPT_DIR, "spotis3mptify_data")

def _normalize_tokens_dir(path: str) -> str:
    p = (path or "").strip()
    # Broken test builds could write ...\_internal\spotis3mptify_data into ui_settings.json.
    # Always move that back to the portable data folder next to the EXE.
    if (not p) or ("_internal" in p.replace("/", "\\").lower() and "spotis3mptify_data" in p.lower()):
        p = DATA_DIR
    p = os.path.expandvars(os.path.expanduser(p))
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(APP_DIR, p))
    return p

def _migrate_legacy_data_dir():
    # v4/v5 test builds accidentally used _internal/spotis3mptify_data.
    # Copy anything found there back to the normal portable data folder.
    old_dir = _legacy_internal_data_dir()
    new_dir = DATA_DIR
    try:
        if os.path.abspath(old_dir) == os.path.abspath(new_dir):
            return
        if not os.path.isdir(old_dir):
            return
        os.makedirs(new_dir, exist_ok=True)
        for name in os.listdir(old_dir):
            src = os.path.join(old_dir, name)
            dst = os.path.join(new_dir, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass
    except Exception:
        pass

_migrate_legacy_data_dir()

def _move_legacy_file(src: str, dst: str) -> None:
    """Move old root-level runtime files into their real data subfolders.
    If moving fails, fall back to copying so credentials are not lost.
    """
    try:
        if not src or not os.path.isfile(src):
            return
        if os.path.abspath(src) == os.path.abspath(dst):
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                return
            except Exception:
                shutil.copy2(src, dst)
        try:
            if os.path.exists(dst) and os.path.exists(src):
                os.remove(src)
        except Exception:
            pass
    except Exception:
        pass

def _migrate_root_data_files_to_subdirs() -> None:
    mappings = {
        AUTH_DIR: (
            "spotis3mptify_tokens.json", "twitch_state_main.json", "twitch_state_bot.json",
        ),
        CONFIG_DIR: (
            "custom_overlay.json", "spotis3mptify_plugin_config.json",
        ),
        NOWPLAYING_DIR: (
            "nowplaying.json", "nowplaying.txt", "nowplaying_artist.txt", "nowplaying_title.txt",
            "nowplaying_album.txt", "nowplaying_url.txt", "nowplaying_provider.txt", "nowplaying_color.txt",
        ),
        COVERS_DIR: (
            "cover_latest_64.jpg", "cover_latest_64.src", "cover_latest_300.jpg", "cover_latest_300.src",
            "cover_latest_640.jpg", "cover_latest_640.src", "youtube_thumbnail.jpg", "youtube_thumbnail.src",
        ),
        PLAYLISTS_DIR: ("spotis3mptify_playlists.json",),
        STATE_DIR: ("spotis3mptify_recent.json", "spotis3mptify_takeover.json", "spotis3mptify_guard.json"),
        EXPORT_DIR: ("songrequests.txt",),
        CERTS_DIR: (
            "spotis3mptify_local_root_ca.crt", "spotis3mptify_local_root_ca.key",
            "localhost_https_cert.pem", "localhost_https_key.pem",
        ),
        YOUTUBE_DIR: ("youtube_debug.log", "youtube_queue.json"),
    }
    for target_dir, names in mappings.items():
        for name in names:
            _move_legacy_file(os.path.join(DATA_DIR, name), os.path.join(target_dir, name))
    # Also catch files accidentally placed directly beside plugin.py in old/plugin-only ZIPs.
    for target_dir, names in mappings.items():
        for name in names:
            _move_legacy_file(os.path.join(_SCRIPT_DIR, name), os.path.join(target_dir, name))

_migrate_root_data_files_to_subdirs()

# ======================= DEFAULTS =======================
CLIENT_ID_DEFAULT              = "YOUR_SPOTIFY_CLIENT_ID_HERE"
CLIENT_SECRET_DEFAULT          = "YOUR_SPOTIFY_CLIENT_SECRET_HERE"
PORT_DEFAULT                   = 17891
SHARED_SECRET_DEFAULT          = ""   # optional header X-Auth for POSTs
REDIRECT_URI_DEFAULT           = ""

TOKENS_DIR_DEFAULT             = AUTH_DIR

COOLDOWN_MINUTES_DEFAULT       = 60
PLAYLIST_PREFIX_DEFAULT        = "Spotis3mptify - "
PLAYLIST_COVER_ENABLED_DEFAULT = True
PLAYLIST_COVER_FILE_DEFAULT    = ""

SRPLUS_DURATION_MIN_DEFAULT    = 15
SRPLUS_ONCE_PER_STREAM_DEFAULT = True
SRPLUS_SHUFFLE_DEFAULT         = True
SRPLUS_DEFER_START_DEFAULT     = True
SRPLUS_MAX_WAIT_SEC_DEFAULT    = 1800
SRPLUS_SUBSCRIBERS_ONLY_DEFAULT = False

ENABLED_DEFAULT                = True
AUTO_STOP_ON_DISABLE_DEFAULT   = True

REPEAT_GUARD_DEFAULT           = True
PLAY_NOW_DEFAULT               = False
QUEUE_THEN_SKIP_DEFAULT        = False

ASYNC_PLAYLIST_ADD_DEFAULT     = True
ASYNC_COVER_FETCH_DEFAULT      = True

LOG_VERBOSE_DEFAULT            = True
LOG_SLOW_MS_DEFAULT            = 500
LOG_DEDUP_SEC_DEFAULT          = 30
LOG_NP_ON_CHANGE_DEFAULT       = False  # keine NP-Change-Logs, auÃŸer man will sie

NOWPLAYING_ENABLE_FILES_DEFAULT = True
NOWPLAYING_POLL_MS_DEFAULT     = 2000
YOUTUBE_ENABLED_DEFAULT        = True
YOUTUBE_MAX_DURATION_SEC_DEFAULT = 600
YOUTUBE_AUTOPLAY_DEFAULT       = True
YOUTUBE_PLAYER_MODE_DEFAULT    = "ytmusic"
YOUTUBE_AUDIO_OUTPUT_NAME_DEFAULT = "Default"

# ---------- TWITCH defaults ----------
TWITCH_LISTEN_DEFAULT          = False
TWITCH_REPLY_DEFAULT           = True
TWITCH_CHANNEL_DEFAULT         = ""   # main channel
TWITCH_BOT_CHANNEL_DEFAULT     = ""   # optional separate bot channel
TWITCH_MAIN_CLIENT_ID_DEFAULT  = ""
TWITCH_MAIN_CLIENT_SECRET_DEFAULT = ""
TWITCH_MAIN_SCOPES_DEFAULT     = "chat:read chat:edit"
TWITCH_MAIN_REDIRECT_URI_DEFAULT = ""
TWITCH_BOT_CLIENT_ID_DEFAULT   = ""
TWITCH_BOT_CLIENT_SECRET_DEFAULT  = ""
TWITCH_BOT_SCOPES_DEFAULT      = "chat:read chat:edit"
TWITCH_BOT_REDIRECT_URI_DEFAULT = ""
TWITCH_CMD_SR_DEFAULT          = "!sr"
TWITCH_CMD_SRPLUS_DEFAULT      = "!sr+"
TWITCH_CMD_YT_DEFAULT          = "!yt"
SR_SOURCE_DEFAULT             = "twitch"   # "twitch" or "external_file"
EXTERNAL_SR_FILE_DEFAULT      = os.path.join(EXPORT_DIR, "songrequests.txt")
TWITCH_REPLY_SUFFIX            = " - powered by spotis3mptify"
TWITCH_REPLY_SENDER_DEFAULT    = "main"  # "main" or "bot"

# Twitch manual overrides (optional)
TWITCH_MAIN_LOGIN_OVERRIDE_DEFAULT = ""
TWITCH_MAIN_TOKEN_OVERRIDE_DEFAULT = ""   # raw token w/o "oauth:" prefix
TWITCH_BOT_LOGIN_OVERRIDE_DEFAULT  = ""
TWITCH_BOT_TOKEN_OVERRIDE_DEFAULT  = ""

# --- Twitch NowPlaying announce defaults (NEU) ---
TWITCH_NP_ON_CHANGE_DEFAULT      = False
TWITCH_NP_FORMAT_DEFAULT         = "ðŸŽ¶ Now Playing: {artist} â€” {title}"
TWITCH_NP_COOLDOWN_SEC_DEFAULT   = 60

# ---------- OBS WebSocket v5 defaults ----------
OBS_WS_ENABLED_DEFAULT         = False
OBS_WS_HOST_DEFAULT            = "localhost"
OBS_WS_PORT_DEFAULT            = 4455
OBS_WS_PASSWORD_DEFAULT        = ""
OBS_FILTER1_SOURCE_DEFAULT     = ""
OBS_FILTER1_NAME_DEFAULT       = ""
OBS_FILTER1_ENABLE_DEFAULT     = True
OBS_FILTER2_SOURCE_DEFAULT     = ""
OBS_FILTER2_NAME_DEFAULT       = ""
OBS_FILTER2_ENABLE_DEFAULT     = False
OBS_FILTER_DELAY_SEC_DEFAULT   = 0
OBS_FILTER_AUTO_ON_NP_CHANGE_DEFAULT = False
OBS_COVER_BROWSER_SOURCE_DEFAULT = ""
OBS_COVER_IMAGE_SOURCE_DEFAULT   = ""
COVER_IMAGE_SIZE_DEFAULT       = 300   # 64/300/640
OVERLAY_MARQUEE_MODE_DEFAULT    = "bounce"  # bounce | scroll-ltr | scroll-rtl | off
OVERLAY_MARQUEE_SPEED_DEFAULT   = 45        # px/sec

# ======================= RUNTIME =======================
CLIENT_ID       = CLIENT_ID_DEFAULT
CLIENT_SECRET   = CLIENT_SECRET_DEFAULT
PORT            = PORT_DEFAULT
UI_LANGUAGE     = "de"
MAIN_UI_BASE    = ""
SHARED_SECRET   = SHARED_SECRET_DEFAULT
TOKENS_DIR      = TOKENS_DIR_DEFAULT
REDIRECT_URI_OV = REDIRECT_URI_DEFAULT
CENTRAL_SPOTIFY_TOKENS: dict[str, Any] = {}
CENTRAL_SPOTIFY_TOKEN_FILE = ""

COOLDOWN_MINUTES        = COOLDOWN_MINUTES_DEFAULT
PLAYLIST_PREFIX         = PLAYLIST_PREFIX_DEFAULT
PLAYLIST_COVER_ENABLED  = PLAYLIST_COVER_ENABLED_DEFAULT
PLAYLIST_COVER_FILE     = PLAYLIST_COVER_FILE_DEFAULT
_PLAYLIST_COVER_DISABLED_THIS_SESSION = False
SRPLUS_DURATION_MIN     = SRPLUS_DURATION_MIN_DEFAULT
SRPLUS_ONCE_PER_STREAM  = SRPLUS_ONCE_PER_STREAM_DEFAULT
SRPLUS_SHUFFLE          = SRPLUS_SHUFFLE_DEFAULT
SRPLUS_DEFER_START      = SRPLUS_DEFER_START_DEFAULT
SRPLUS_MAX_WAIT_SEC     = SRPLUS_MAX_WAIT_SEC_DEFAULT
SRPLUS_SUBSCRIBERS_ONLY = SRPLUS_SUBSCRIBERS_ONLY_DEFAULT

ENABLED                 = ENABLED_DEFAULT
AUTO_STOP_ON_DISABLE    = AUTO_STOP_ON_DISABLE_DEFAULT

REPEAT_GUARD            = REPEAT_GUARD_DEFAULT
PLAY_NOW                = PLAY_NOW_DEFAULT
QUEUE_THEN_SKIP         = QUEUE_THEN_SKIP_DEFAULT
ASYNC_PLAYLIST_ADD      = ASYNC_PLAYLIST_ADD_DEFAULT
ASYNC_COVER_FETCH       = ASYNC_COVER_FETCH_DEFAULT

LOG_VERBOSE             = LOG_VERBOSE_DEFAULT
LOG_SLOW_MS             = LOG_SLOW_MS_DEFAULT
LOG_DEDUP_SEC           = LOG_DEDUP_SEC_DEFAULT
LOG_NP_ON_CHANGE        = LOG_NP_ON_CHANGE_DEFAULT

NOWPLAYING_ENABLE_FILES = NOWPLAYING_ENABLE_FILES_DEFAULT
NOWPLAYING_POLL_MS      = NOWPLAYING_POLL_MS_DEFAULT
YOUTUBE_ENABLED      = YOUTUBE_ENABLED_DEFAULT
YOUTUBE_MAX_DURATION_SEC = YOUTUBE_MAX_DURATION_SEC_DEFAULT
YOUTUBE_AUTOPLAY     = YOUTUBE_AUTOPLAY_DEFAULT
YOUTUBE_PLAYER_MODE = YOUTUBE_PLAYER_MODE_DEFAULT
YOUTUBE_AUDIO_OUTPUT_NAME = YOUTUBE_AUDIO_OUTPUT_NAME_DEFAULT

# ---- Twitch runtime (main + bot) ----
TWITCH_LISTEN           = TWITCH_LISTEN_DEFAULT
TWITCH_REPLY            = TWITCH_REPLY_DEFAULT
TWITCH_CHANNEL          = TWITCH_CHANNEL_DEFAULT
TWITCH_BOT_CHANNEL      = TWITCH_BOT_CHANNEL_DEFAULT

TWITCH_MAIN_CLIENT_ID     = TWITCH_MAIN_CLIENT_ID_DEFAULT
TWITCH_MAIN_CLIENT_SECRET = TWITCH_MAIN_CLIENT_SECRET_DEFAULT
TWITCH_MAIN_SCOPES        = TWITCH_MAIN_SCOPES_DEFAULT
TWITCH_MAIN_REDIRECT_OV   = TWITCH_MAIN_REDIRECT_URI_DEFAULT

TWITCH_BOT_CLIENT_ID      = TWITCH_BOT_CLIENT_ID_DEFAULT
TWITCH_BOT_CLIENT_SECRET  = TWITCH_BOT_CLIENT_SECRET_DEFAULT
TWITCH_BOT_SCOPES         = TWITCH_BOT_SCOPES_DEFAULT
TWITCH_BOT_REDIRECT_OV    = TWITCH_BOT_REDIRECT_URI_DEFAULT

TWITCH_CMD_SR        = TWITCH_CMD_SR_DEFAULT
TWITCH_CMD_SRPLUS    = TWITCH_CMD_SRPLUS_DEFAULT
TWITCH_CMD_YT        = TWITCH_CMD_YT_DEFAULT
SR_SOURCE            = SR_SOURCE_DEFAULT
EXTERNAL_SR_FILE     = EXTERNAL_SR_FILE_DEFAULT
TWITCH_REPLY_SENDER  = TWITCH_REPLY_SENDER_DEFAULT  # "main"|"bot"

# Manual overrides
TWITCH_MAIN_LOGIN_OVERRIDE = TWITCH_MAIN_LOGIN_OVERRIDE_DEFAULT
TWITCH_MAIN_TOKEN_OVERRIDE = TWITCH_MAIN_TOKEN_OVERRIDE_DEFAULT
TWITCH_BOT_LOGIN_OVERRIDE  = TWITCH_BOT_LOGIN_OVERRIDE_DEFAULT
TWITCH_BOT_TOKEN_OVERRIDE  = TWITCH_BOT_TOKEN_OVERRIDE_DEFAULT

# --- Twitch NowPlaying announce runtime (NEU) ---
TWITCH_NP_ON_CHANGE    = TWITCH_NP_ON_CHANGE_DEFAULT
TWITCH_NP_FORMAT       = TWITCH_NP_FORMAT_DEFAULT
TWITCH_NP_COOLDOWN_SEC = TWITCH_NP_COOLDOWN_SEC_DEFAULT

# ---- OBS WebSocket runtime ----
OBS_WS_ENABLED       = OBS_WS_ENABLED_DEFAULT
OBS_WS_HOST          = OBS_WS_HOST_DEFAULT
OBS_WS_PORT          = OBS_WS_PORT_DEFAULT
OBS_WS_PASSWORD      = OBS_WS_PASSWORD_DEFAULT
OBS_FILTER1_SOURCE   = OBS_FILTER1_SOURCE_DEFAULT
OBS_FILTER1_NAME     = OBS_FILTER1_NAME_DEFAULT
OBS_FILTER1_ENABLE   = OBS_FILTER1_ENABLE_DEFAULT
OBS_FILTER2_SOURCE   = OBS_FILTER2_SOURCE_DEFAULT
OBS_FILTER2_NAME     = OBS_FILTER2_NAME_DEFAULT
OBS_FILTER2_ENABLE   = OBS_FILTER2_ENABLE_DEFAULT
OBS_FILTER_DELAY_SEC = OBS_FILTER_DELAY_SEC_DEFAULT
OBS_FILTER_AUTO_ON_NP_CHANGE = OBS_FILTER_AUTO_ON_NP_CHANGE_DEFAULT
OBS_COVER_BROWSER_SOURCE = OBS_COVER_BROWSER_SOURCE_DEFAULT
OBS_COVER_IMAGE_SOURCE   = OBS_COVER_IMAGE_SOURCE_DEFAULT
COVER_IMAGE_SIZE         = COVER_IMAGE_SIZE_DEFAULT
OVERLAY_MARQUEE_MODE   = OVERLAY_MARQUEE_MODE_DEFAULT
OVERLAY_MARQUEE_SPEED  = OVERLAY_MARQUEE_SPEED_DEFAULT

# ======================= THREADING & LOG =======================
LOG_CB: Optional[Callable[[str,str], None]] = None  # (level, message)
def set_logger(cb: Optional[Callable[[str,str], None]]):
    global LOG_CB
    LOG_CB = cb

def _ts():
    t = time.time(); lt = time.localtime(t); ms = int((t - int(t))*1000)
    return time.strftime("%H:%M:%S", lt) + f".{ms:03d}"

def _log(level: str, msg: str):
    line = f"[{_ts()}] [spotis3mptify] {msg}"
    if LOG_CB:
        try: LOG_CB(level, line)
        except: pass
    else:
        print(f"{level}: {line}")

def logi(m): _log("INFO", m)
def logw(m): _log("WARN", m)
def loge(m): _log("ERROR", m)

_LAST_LOG_BY_KEY: Dict[str,int] = {}
def _now_s():
    try: return time.perf_counter()
    except: return time.time()
def _now(): return int(time.time())
def _fmt_ms(ms): return f"{ms}ms" if ms < 1000 else f"{ms/1000.0:.3f}s"

def _log_throttled(level, key, msg, window_sec=None):
    if window_sec is None: window_sec = LOG_DEDUP_SEC
    now_ms = int(_now_s()*1000)
    last = _LAST_LOG_BY_KEY.get(key, 0)
    if now_ms - last < int(window_sec*1000): return
    _LAST_LOG_BY_KEY[key] = now_ms
    _log(level, msg)

# ======================= HELPERS: PATHS & IO =======================
def _ensure_dir(p):
    try: os.makedirs(p, exist_ok=True)
    except: pass

def _p_tokens(): _ensure_dir(TOKENS_DIR); return os.path.join(TOKENS_DIR, "spotis3mptify_tokens.json")
def _p_recent(): _ensure_dir(STATE_DIR); return os.path.join(STATE_DIR, "spotis3mptify_recent.json")
def _p_plmap():  _ensure_dir(PLAYLISTS_DIR); return os.path.join(PLAYLISTS_DIR, "spotis3mptify_playlists.json")
def _p_state():  _ensure_dir(STATE_DIR); return os.path.join(STATE_DIR, "spotis3mptify_takeover.json")
def _p_guard():  _ensure_dir(STATE_DIR); return os.path.join(STATE_DIR, "spotis3mptify_guard.json")

# Twitch tokens (main/bot)
def _p_twitch_main(): _ensure_dir(AUTH_DIR); return os.path.join(AUTH_DIR, "twitch_state_main.json")
def _p_twitch_bot():  _ensure_dir(AUTH_DIR); return os.path.join(AUTH_DIR, "twitch_state_bot.json")

# Now Playing files
def _p_cover(size): _ensure_dir(COVERS_DIR); return os.path.join(COVERS_DIR, f"cover_latest_{size}.jpg")
def _p_np_json():   _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying.json")
def _p_np_artist(): _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_artist.txt")
def _p_np_title():  _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_title.txt")
def _p_np_album():  _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_album.txt")
def _p_np_combo():  _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying.txt")
def _p_np_url():    _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_url.txt")
def _p_np_provider(): _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_provider.txt")
def _p_np_color():    _ensure_dir(NOWPLAYING_DIR); return os.path.join(NOWPLAYING_DIR, "nowplaying_color.txt")
def _p_yt_thumb():    _ensure_dir(COVERS_DIR); return os.path.join(COVERS_DIR, "youtube_thumbnail.jpg")
def _p_yt_thumb_src(): _ensure_dir(COVERS_DIR); return os.path.join(COVERS_DIR, "youtube_thumbnail.src")
def _p_cover_src(size):
    _ensure_dir(COVERS_DIR)
    return os.path.join(COVERS_DIR, f"cover_latest_{size}.src")

def _atomic_write_bytes(path, data: bytes):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f: f.write(data)
    os.replace(tmp, path)
def _atomic_write_text(path, s: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(s or "")
    os.replace(tmp, path)
def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default
def _save_json(path, data):
    try: _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e: logw(f"write {os.path.basename(path)} failed: {e}")

# ======================= SIMPLE THREAD-POOL =======================
import concurrent.futures
_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=3)

# ======================= OBS WEBSOCKET v5 =======================
try:
    import websocket  # websocket-client
    _HAS_WEBSOCKET = True
except ImportError:
    _HAS_WEBSOCKET = False
    logw("websocket-client not installed. OBS features disabled.")

class OBSWebSocketV5:
    def __init__(self):
        self.ws = None
        self.connected = False
        self._req_id = 1
        self._rpc_version = 1

    def _recv_json(self, timeout=5.0):
        if not self.ws: return None
        self.ws.settimeout(timeout)
        raw = self.ws.recv()
        return json.loads(raw) if isinstance(raw, (str, bytes)) else None

    def _send_json(self, obj):
        if not self.ws: return
        self.ws.send(json.dumps(obj))

    def _compute_auth(self, password, challenge, salt):
        secret = hashlib.sha256((password + salt).encode("utf-8")).digest()
        secret_b64 = base64.b64encode(secret).decode("utf-8")
        auth = hashlib.sha256((secret_b64 + challenge).encode("utf-8")).digest()
        return base64.b64encode(auth).decode("utf-8")

    def connect(self):
        if not _HAS_WEBSOCKET or not OBS_WS_ENABLED:
            return False
        try:
            url = f"ws://{OBS_WS_HOST}:{OBS_WS_PORT}"
            self.ws = websocket.create_connection(url, timeout=5)
            hello = self._recv_json(timeout=5.0) or {}
            if hello.get("op") != 0:
                raise RuntimeError("Unexpected OBS WS hello.")
            d = hello.get("d", {}) or {}
            auth = d.get("authentication") or {}
            identify = {"op": 1, "d": {"rpcVersion": self._rpc_version, "eventSubscriptions": 0}}
            if OBS_WS_PASSWORD and auth:
                identify["d"]["authentication"] = self._compute_auth(OBS_WS_PASSWORD, auth.get("challenge",""), auth.get("salt",""))
            self._send_json(identify)
            ident = self._recv_json(timeout=5.0) or {}
            if ident.get("op") != 2:
                raise RuntimeError("OBS WS identify failed.")
            self.connected = True
            _log_throttled("INFO","obs_connected","OBS WebSocket v5 connected.", 10)
            return True
        except Exception as e:
            _log_throttled("WARN","obs_connect_failed",f"OBS WebSocket connect failed: {e}", 5)
            self.connected = False
            try:
                if self.ws: self.ws.close()
            except: pass
            self.ws = None
            return False

    def _req(self, requestType, requestData=None, timeout=5.0) -> bool:
        if not self.connected: return False
        rid = str(self._req_id); self._req_id += 1
        self._send_json({"op": 6, "d": {"requestType": requestType, "requestId": rid, "requestData": requestData or {}}})
        # wait for response
        end = time.time() + timeout
        while time.time() < end:
            msg = self._recv_json(timeout=max(0.1, end - time.time()))
            if not msg: continue
            if msg.get("op") == 7 and (msg.get("d") or {}).get("requestId") == rid:
                st = (msg["d"].get("requestStatus") or {})
                return bool(st.get("result", False))
        return False

    def set_filter_visibility(self, source_name: str, filter_name: str, enabled: bool) -> bool:
        return self._req("SetSourceFilterEnabled", {"sourceName": source_name, "filterName": filter_name, "filterEnabled": bool(enabled)})

    def set_browser_source_url(self, input_name: str, url: str) -> bool:
        return self._req("SetInputSettings", {"inputName": input_name, "inputSettings": {"url": url}, "overlay": True})

    def set_image_source_file(self, input_name: str, file_path: str) -> bool:
        return self._req("SetInputSettings", {"inputName": input_name, "inputSettings": {"file": file_path}, "overlay": True})

    def disconnect(self):
        try:
            if self.ws: self.ws.close()
        except: pass
        self.ws = None
        self.connected = False

_OBS_CLIENT = OBSWebSocketV5()

def _obs_connect() -> bool:
    if not OBS_WS_ENABLED:
        return False
    if _OBS_CLIENT.connected:
        return True
    return _OBS_CLIENT.connect()

def _obs_trigger_filter_sequence(delay_override: Optional[int] = None) -> bool:
    if not _obs_connect():
        _log_throttled("WARN","obs_no_conn","OBS not connected, cannot trigger filter sequence", 5)
        return False
    ok = True
    if OBS_FILTER1_SOURCE and OBS_FILTER1_NAME:
        if not _OBS_CLIENT.set_filter_visibility(OBS_FILTER1_SOURCE, OBS_FILTER1_NAME, OBS_FILTER1_ENABLE):
            ok = False; _log_throttled("WARN","obs_f1_fail",f"Failed filter1 {OBS_FILTER1_NAME} on {OBS_FILTER1_SOURCE}", 10)
    delay = OBS_FILTER_DELAY_SEC if delay_override is None else int(delay_override or 0)
    if delay > 0:
        time.sleep(delay)
    if OBS_FILTER2_SOURCE and OBS_FILTER2_NAME:
        if not _OBS_CLIENT.set_filter_visibility(OBS_FILTER2_SOURCE, OBS_FILTER2_NAME, OBS_FILTER2_ENABLE):
            ok = False; _log_throttled("WARN","obs_f2_fail",f"Failed filter2 {OBS_FILTER2_NAME} on {OBS_FILTER2_SOURCE}", 10)
    return ok

def _obs_update_cover_display() -> bool:
    if not _obs_connect():
        return False
    ok = True
    bust = f"{_now()}"
    cover_url = f"http://127.0.0.1:{PORT}/cover/latest?size={COVER_IMAGE_SIZE}&t={bust}"
    if OBS_COVER_BROWSER_SOURCE:
        if not _OBS_CLIENT.set_browser_source_url(OBS_COVER_BROWSER_SOURCE, cover_url):
            ok = False; _log_throttled("WARN","obs_br_fail",f"Failed to update browser source {OBS_COVER_BROWSER_SOURCE}", 10)
    if OBS_COVER_IMAGE_SOURCE:
        path = _p_cover(COVER_IMAGE_SIZE)
        if os.path.exists(path):
            if not _OBS_CLIENT.set_image_source_file(OBS_COVER_IMAGE_SOURCE, path):
                ok = False; _log_throttled("WARN","obs_img_fail",f"Failed to update image source {OBS_COVER_IMAGE_SOURCE}", 10)
    return ok

# ======================= API CACHE =======================
_API_CACHE: Dict[str, Tuple[Any,int]] = {}
_API_CACHE_TTL = 30
def _cached_api_call(cache_key, func, *args, **kwargs):
    now = _now()
    if cache_key in _API_CACHE:
        data, ts = _API_CACHE[cache_key]
        if now - ts < _API_CACHE_TTL:
            return data
    res = func(*args, **kwargs)
    _API_CACHE[cache_key] = (res, now)
    return res

# ======================= Spotify API auth from central platform settings =======================
def _read_tokens():
    if CENTRAL_SPOTIFY_TOKENS:
        return dict(CENTRAL_SPOTIFY_TOKENS)
    return {"access_token": None, "refresh_token": None, "expires_at": 0}

def _write_tokens(tok):
    CENTRAL_SPOTIFY_TOKENS.clear()
    token = dict(tok or {})
    CENTRAL_SPOTIFY_TOKENS.update(token)
    if CENTRAL_SPOTIFY_TOKEN_FILE:
        try:
            saved = dict(token)
            saved.setdefault("platform", "spotify")
            saved.setdefault("account", "main")
            saved.setdefault("saved_at", time.time())
            if saved.get("expires_at") and not saved.get("expires_in"):
                try:
                    saved["expires_in"] = max(0, int(float(saved.get("expires_at") or 0) - time.time()))
                except Exception:
                    pass
            _ensure_dir(os.path.dirname(CENTRAL_SPOTIFY_TOKEN_FILE))
            _save_json(CENTRAL_SPOTIFY_TOKEN_FILE, saved)
        except Exception as exc:
            logw(f"central spotify token write failed: {exc}")

def _is_authorized(): t = _read_tokens(); return bool(t.get("refresh_token") or t.get("access_token"))

def _ensure_access_token():
    tok = _read_tokens()
    if tok.get("access_token") and (tok.get("expires_at", 0) - 30) > _now():
        return tok["access_token"]
    if tok.get("access_token") and not tok.get("expires_at"):
        return tok["access_token"]
    if not tok.get("refresh_token"):
        raise RuntimeError("Spotify is not authorized in the core Platforms page.")
    try:
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }).encode("utf-8")
        req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        tok["access_token"] = r["access_token"]
        if "refresh_token" in r: tok["refresh_token"] = r["refresh_token"]
        if "scope" in r: tok["scope"] = r.get("scope", "")
        tok["expires_at"] = _now() + int(r.get("expires_in", 3600))
        _write_tokens(tok)
        _log_throttled("INFO", "auth:refresh_ok", "auth: token refreshed", 300)
        return tok["access_token"]
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8", "ignore")
        except: body = ""
        code = getattr(e, "code", 0)
        loge(f"auth refresh failed {code}: {body[:200]}")
        if code in (400,401):
            _write_tokens({"access_token": None, "refresh_token": None, "expires_at": 0})
            if tok.get("access_token"):
                return tok["access_token"]
        raise

# ---------------- Spotify API helpers (search, meta, playback, playlists) ----------------
_BACKOFF_UNTIL = 0
def _api(method, url, at, params=None, body=None, headers=None, quiet=False, quiet_codes=None):
    global _BACKOFF_UNTIL
    start = _now_s()
    base = url.split("?")[0]
    if params: url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Authorization", f"Bearer {at}")
    if body is not None: req.add_header("Content-Type", "application/json")
    if headers:
        for k,v in headers.items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", 0)
        retry_secs = None
        try:
            if code == 429:
                ra = e.headers.get("Retry-After")
                retry_secs = int(ra) if ra and str(ra).isdigit() else 5
                _BACKOFF_UNTIL = max(_BACKOFF_UNTIL, _now() + retry_secs)
        except: pass
        try: msg = e.read().decode("utf-8","ignore")
        except: msg = ""
        if quiet or (quiet_codes and code in quiet_codes):
            return {"_http_error_code": code, "_error": msg, "_retry_after": retry_secs}
        if code == 429:
            _log_throttled("WARN", "api_429", f"Rate limited (429), backoff {retry_secs or '?'}s", 5)
            return {"_http_error_code": code, "_error": msg, "_retry_after": retry_secs}
        loge(f"API {method} {base} -> {code} {msg[:200]}")
        raise
    finally:
        dur_ms = int((_now_s()-start)*1000)
        if LOG_VERBOSE and dur_ms >= int(LOG_SLOW_MS):
            _log_throttled("WARN", f"slow:{method}:{base}", f"SLOW API {method} {base} took {_fmt_ms(dur_ms)}", LOG_DEDUP_SEC)

_SPOTIFY_TRACK_RE = re.compile(r'(?:spotify:track:|open\.spotify\.com/(?:intl-[a-z]{2}/)?track/)([A-Za-z0-9]{22})', re.IGNORECASE)

def _pick_image_url(imgs, target_width):
    if not imgs: return ""
    best, best_score = None, 10**9
    for im in imgs:
        try: w = int(im.get("width") or 0)
        except: w = 0
        url = im.get("url") or ""
        if not url: continue
        score = abs((w or target_width) - target_width)
        if score < best_score:
            best, best_score = url, score
    return best or imgs[0].get("url","")

def _extract_cover_urls_from_album_obj(album_obj):
    imgs = (album_obj or {}).get("images") or []
    return {"url_640": _pick_image_url(imgs, 640),
            "url_300": _pick_image_url(imgs, 300),
            "url_64":  _pick_image_url(imgs, 64),
            "album":   (album_obj or {}).get("name","")}

_ME_ID = None
def _get_me_id(at):
    global _ME_ID
    if _ME_ID: return _ME_ID
    r = _cached_api_call("me_info", _api, "GET", "https://api.spotify.com/v1/me", at)
    _ME_ID = r.get("id")
    return _ME_ID

def _get_track_meta_by_id(at, track_id):
    r = _cached_api_call(f"track_{track_id}", _api, "GET", f"https://api.spotify.com/v1/tracks/{track_id}", at)
    title   = r.get("name","")
    artists = ", ".join([a.get("name","") for a in (r.get("artists") or [])]) or ""
    url     = ((r.get("external_urls") or {}).get("spotify")) or f"https://open.spotify.com/track/{track_id}"
    uri     = r.get("uri", f"spotify:track:{track_id}")
    covers  = _extract_cover_urls_from_album_obj(r.get("album") or {})
    return {"id": track_id, "title": title, "artist": artists, "album": covers.get("album",""),
            "url": url, "uri": uri, "covers": covers}

def _track_from_search_item(t):
    if not t:
        return None
    tid = t.get("id","")
    title = t.get("name","")
    artists = ", ".join([a.get("name","") for a in (t.get("artists") or [])]) or ""
    url = ((t.get("external_urls") or {}).get("spotify")) or (f"https://open.spotify.com/track/{tid}" if tid else "")
    uri = t.get("uri", f"spotify:track:{tid}")
    covers = _extract_cover_urls_from_album_obj((t.get("album") or {}))
    return {"id": tid, "title": title, "artist": artists, "album": covers.get("album",""),
            "url": url, "uri": uri, "covers": covers}

def _search_tracks(at, query, limit=5):
    q = (query or "").strip()
    if not q:
        return []
    cache_key = f"search_track::{q.lower()}::{int(limit)}"
    r = _cached_api_call(cache_key, _api, "GET", "https://api.spotify.com/v1/search", at,
                         params={"q": q, "type": "track", "limit": max(1, min(int(limit or 1), 50))})
    items = (((r or {}).get("tracks") or {}).get("items") or [])
    return items or []

def _search_first_track(at, query):
    items = _search_tracks(at, query, limit=1)
    if not items:
        return None
    return _track_from_search_item(items[0])

def _build_text_search_variants(user_input):
    q = _clean_sr_query(user_input)
    if not q:
        return []
    variants = []
    seen = set()
    def add(v):
        vv = _clean_sr_query(v)
        if not vv:
            return
        key = vv.lower()
        if key in seen:
            return
        seen.add(key)
        variants.append(vv)
    add(q)
    add(f'"{q}"')
    tokens = [t for t in q.split(" ") if t]
    if len(tokens) >= 2:
        preferred_counts = [2, 1, 3, 4]
        counts = []
        for c in preferred_counts:
            if 1 <= c < len(tokens) and c not in counts:
                counts.append(c)
        for c in range(1, len(tokens)):
            if c not in counts:
                counts.append(c)
        for c in counts:
            artist = " ".join(tokens[:c]).strip()
            title = " ".join(tokens[c:]).strip()
            if artist and title:
                add(f'artist:"{artist}" track:"{title}"')
                add(f'{artist} {title}')
    return variants

def _input_to_uri_and_id(text):
    s = (text or "").strip()
    low = s.lower()
    if low.startswith("spotify:track:"):
        tid = s.split(":")[-1].strip()
        return (f"spotify:track:{tid}", tid) if tid else (None,None)
    try: u = urllib.parse.urlparse(s)
    except: return (None,None)
    host = (u.netloc or "").lower(); path = u.path or ""
    if host in ("spoti.fi","www.spoti.fi","spotify.link","www.spotify.link"):
        try:
            req = urllib.request.Request(s, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                final = resp.geturl() or s
            u = urllib.parse.urlparse(final); host = (u.netloc or "").lower(); path = u.path or ""
        except: return (None,None)
    if host not in ("open.spotify.com","www.open.spotify.com"): return (None,None)
    parts = [p for p in (path or "").split("/") if p]
    for i, part in enumerate(parts):
        if part.lower() == "track" and (i+1) < len(parts):
            tid = parts[i+1].split("?")[0].split("#")[0].strip()
            if tid and _SPOTIFY_TRACK_RE.match(f"open.spotify.com/track/{tid}"):
                return (f"spotify:track:{tid}", tid)
    return (None,None)

def _resolve_track(at, user_input):
    uri, tid = _input_to_uri_and_id(user_input)
    if uri and tid:
        return _get_track_meta_by_id(at, tid)
    for variant in _build_text_search_variants(user_input):
        meta = _search_first_track(at, variant)
        if meta and meta.get("uri"):
            return meta
    return None

# ---- Playlists ----
def _plmap_load(): return _load_json(_p_plmap(), {"me_id": None, "users": {}, "prefix": PLAYLIST_PREFIX})
def _plmap_save(d): _save_json(_p_plmap(), d)
def _playlist_name_for(user_display): return f"{PLAYLIST_PREFIX}{user_display}"

def _create_playlist(at, name, desc):
    me = _get_me_id(at)
    r = _api("POST", f"https://api.spotify.com/v1/users/{me}/playlists", at, body={"name": name, "public": False, "description": desc})
    pid = r.get("id")
    if pid:
        try:
            url = ((r.get("external_urls") or {}).get("spotify")) or f"https://open.spotify.com/playlist/{pid}"
            logi(f"Spotify created playlist confirmed: '{name}' Â· {url}")
        except Exception:
            pass
    return pid

def _playlist_get_info(at, playlist_id):
    if not playlist_id:
        return {}
    try:
        return _api("GET", f"https://api.spotify.com/v1/playlists/{playlist_id}", at,
                    params={"fields": "id,name,owner(id,display_name),external_urls,tracks(total)"},
                    quiet=True, quiet_codes={401,403,404}) or {}
    except Exception:
        return {}

def _follow_playlist_for_visibility(at, playlist_id):
    """Best-effort: make sure Spotify adds the playlist to the current user's library/sidebar.

    New playlists created by the authenticated user should already be visible, but this extra
    call fixes cases where Spotify's UI/library cache does not immediately list API-created
    private playlists. It must never block SR.
    """
    if not playlist_id:
        return False
    try:
        _api("PUT", f"https://api.spotify.com/v1/playlists/{playlist_id}/followers", at,
             body={"public": False}, quiet=True, quiet_codes={400,401,403,404,429})
        return True
    except Exception:
        return False

def _playlist_cover_path():
    path = (PLAYLIST_COVER_FILE or "").strip()
    if not path:
        return ""
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        if os.path.isfile(path) and path.lower().endswith((".jpg", ".jpeg")):
            return path
    except Exception:
        pass
    return ""

def _playlist_cover_key():
    path = _playlist_cover_path()
    if not PLAYLIST_COVER_ENABLED or not path:
        return ""
    try:
        st = os.stat(path)
        return f"{os.path.basename(path)}:{int(st.st_mtime)}:{int(st.st_size)}"
    except Exception:
        return os.path.basename(path)

def _set_playlist_cover(at, playlist_id):
    global _PLAYLIST_COVER_DISABLED_THIS_SESSION
    if not PLAYLIST_COVER_ENABLED or not playlist_id or _PLAYLIST_COVER_DISABLED_THIS_SESSION:
        return False
    path = _playlist_cover_path()
    if not path:
        return False
    try:
        raw = open(path, "rb").read()
        if len(raw) > 256 * 1024:
            _log_throttled("WARN", "playlist_cover_too_large", f"Playlist cover skipped, file is larger than 256 KB: {os.path.basename(path)}", 300)
            return False
        data = base64.b64encode(raw)
        req = urllib.request.Request(f"https://api.spotify.com/v1/playlists/{playlist_id}/images", data=data, method="PUT")
        req.add_header("Authorization", f"Bearer {at}")
        req.add_header("Content-Type", "image/jpeg")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        logi(f"Set playlist cover: {os.path.basename(path)}")
        return True
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", 0)
        try: msg = e.read().decode("utf-8", "ignore")
        except Exception: msg = ""
        if code in (401, 403):
            _PLAYLIST_COVER_DISABLED_THIS_SESSION = True
            _log_throttled("WARN", "playlist_cover_auth", "Playlist cover upload disabled for this session: Spotify login/token does not allow image upload. Reconnect Spotify in the main tool with scope ugc-image-upload. Requests and playlist creation continue normally.", 300)
        else:
            _log_throttled("WARN", "playlist_cover_http", f"Playlist cover upload skipped: HTTP {code} {msg[:180]}", 300)
    except Exception as e:
        _log_throttled("WARN", "playlist_cover_failed", f"Playlist cover upload skipped: {e}", 300)
    return False

def _playlist_cache_entry_is_valid(at, playlist_id, expected_name=""):
    if not playlist_id:
        return False
    r = _playlist_get_info(at, playlist_id)
    code = int((r or {}).get("_http_error_code") or 0)
    if code in (401, 403, 404) or not r.get("id"):
        return False
    try:
        current_me = _get_me_id(at)
        owner_id = str(((r.get("owner") or {}).get("id")) or "")
        if current_me and owner_id and owner_id != current_me:
            return False
    except Exception:
        pass
    if expected_name and (r.get("name") or "") != expected_name:
        return False
    return True

def _find_and_adopt_existing_playlist(at, desired_name, user_display):
    try:
        url = "https://api.spotify.com/v1/me/playlists"
        params = {"limit": 50}
        current_me = _get_me_id(at)
        targets = {desired_name.strip().lower(),
                   f"Spotis3mptify - {user_display}".lower(),
                   f"Spotis3mptify â€“ {user_display}".lower()}
        while url:
            r = _api("GET", url, at, params=params if url.endswith("/me/playlists") else None, quiet=True, quiet_codes={401,403,404})
            if int((r or {}).get("_http_error_code") or 0):
                break
            for it in (r.get("items") or []):
                name = (it.get("name") or "").strip()
                pid = it.get("id") or ""
                owner_id = str(((it.get("owner") or {}).get("id")) or "")
                if name.lower() in targets and pid and (not current_me or not owner_id or owner_id == current_me):
                    if name != desired_name:
                        try:
                            _api("PUT", f"https://api.spotify.com/v1/playlists/{pid}", at,
                                 body={"name": desired_name, "public": False, "description": "Auto-managed request playlist (spotis3mptify)"},
                                 quiet=True, quiet_codes={400,403,404})
                        except Exception:
                            pass
                    _follow_playlist_for_visibility(at, pid)
                    return pid
            url = r.get("next")
            params = None
    except Exception as e:
        _log_throttled("WARN", "scan_playlists_failed", f"scan playlists failed: {e}", 300)
    return None

def _playlist_has_track(at, playlist_id, track_id):
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    params = {"fields": "items(track(id)),next", "limit": 100}
    next_url = None
    while True:
        r = _api("GET", next_url if next_url else url, at, params=None if next_url else params)
        for it in (r.get("items") or []):
            t = (it.get("track") or {})
            if (t.get("id") or "") == track_id: return True
        next_url = r.get("next")
        if not next_url: return False

def _get_or_create_user_playlist(at, user_display_raw):
    user = _normalize_user(user_display_raw)
    desired = _playlist_name_for(user)
    mp = _plmap_load()
    current_me = _get_me_id(at)
    if not isinstance(mp.get("users"), dict):
        mp["users"] = {}
    if mp.get("me_id") and mp.get("me_id") != current_me:
        _log_throttled("WARN", "playlist_cache_account_changed", "Playlist cache belonged to a different Spotify account; rebuilding user playlist cache.", 300)
        mp = {"me_id": current_me, "users": {}, "prefix": PLAYLIST_PREFIX}
        _plmap_save(mp)
    if not mp.get("me_id"):
        mp["me_id"] = current_me

    key = _playlist_key_for_user(user)
    entry = (mp.get("users") or {}).get(key)
    cover_key = _playlist_cover_key()

    # Existing cached playlist: only trust it if the playlist still exists.
    if isinstance(entry, dict):
        pid = entry.get("id") or ""
        name = entry.get("name") or ""
        prefix = entry.get("prefix") or ""
        old_cover_key = entry.get("cover_key") or ""
        if pid and name == desired and prefix == PLAYLIST_PREFIX and _playlist_cache_entry_is_valid(at, pid, desired):
            # Cover is optional. Never let cover upload block returning the playlist id.
            if cover_key and old_cover_key != cover_key:
                if _set_playlist_cover(at, pid):
                    entry["cover_key"] = cover_key
                    mp["users"][key] = entry
                    _plmap_save(mp)
            return pid
        if pid:
            _log_throttled("WARN", f"playlist_cache_refresh:{key}", f"Cached playlist for @{user} is outdated or invalid; searching/creating again.", 120)
    elif isinstance(entry, str) and entry and mp.get("prefix") == PLAYLIST_PREFIX:
        if _playlist_cache_entry_is_valid(at, entry, desired):
            if cover_key:
                if _set_playlist_cover(at, entry):
                    mp["users"][key] = {"id": entry, "name": desired, "prefix": PLAYLIST_PREFIX, "display": user, "cover_key": cover_key}
                    _plmap_save(mp)
            return entry
        _log_throttled("WARN", f"playlist_cache_refresh:{key}", f"Cached playlist for @{user} is outdated or invalid; searching/creating again.", 120)

    # Prefix changed, old cache entry, or missing/deleted playlist: adopt/create current desired playlist.
    pid = _find_and_adopt_existing_playlist(at, desired, user)
    action = "Adopted"
    if not pid:
        pid = _create_playlist(at, desired, "Auto-managed request playlist (spotis3mptify)")
        action = "Created"
    if not pid:
        raise RuntimeError(f"Spotify did not return a playlist id for '{desired}'")

    mp["prefix"] = PLAYLIST_PREFIX
    mp["users"][key] = {"id": pid, "name": desired, "prefix": PLAYLIST_PREFIX, "display": user, "cover_key": ""}
    _plmap_save(mp)
    _follow_playlist_for_visibility(at, pid)
    info = _playlist_get_info(at, pid)
    url = (((info.get("external_urls") or {}).get("spotify")) or f"https://open.spotify.com/playlist/{pid}")
    total = ((info.get("tracks") or {}).get("total"))
    logi(f"{action} playlist '{desired}' for @{user} Â· id={pid} Â· tracks={total if total is not None else '?'} Â· {url}")

    # Cover upload happens AFTER saving the playlist mapping. If Spotify rejects the image
    # upload, requests and playlist creation must still work.
    if cover_key:
        try:
            if _set_playlist_cover(at, pid):
                mp = _plmap_load()
                if not isinstance(mp.get("users"), dict):
                    mp["users"] = {}
                e = mp["users"].get(key) if isinstance(mp["users"].get(key), dict) else {}
                e.update({"id": pid, "name": desired, "prefix": PLAYLIST_PREFIX, "display": user, "cover_key": cover_key})
                mp["users"][key] = e
                _plmap_save(mp)
        except Exception as e:
            _log_throttled("WARN", "playlist_cover_optional_failed", f"Optional playlist cover step skipped: {e}", 300)
    return pid

def _playlist_add_tracks(at, playlist_id, uris):
    if not uris:
        return {}
    r = _api("POST", f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", at, body={"uris": uris})
    return r or {}

# ---- Player ----
def _get_player_state(at):
    r = _api("GET","https://api.spotify.com/v1/me/player", at, quiet=True, quiet_codes={429})
    if isinstance(r, dict) and r.get("_http_error_code"): return {}
    return r or {}
def _get_queue(at):
    r = _api("GET","https://api.spotify.com/v1/me/player/queue", at, quiet=True, quiet_codes={429})
    if isinstance(r, dict) and r.get("_http_error_code"): return {}
    return r or {}
def _apply_shuffle(at, state): _api("PUT","https://api.spotify.com/v1/me/player/shuffle", at, params={"state": str(state).lower()}, quiet=True, quiet_codes={400,403,404,429})
def _apply_repeat(at, mode):   _api("PUT","https://api.spotify.com/v1/me/player/repeat",  at, params={"state": mode}, quiet=True, quiet_codes={400,403,404,429})
def _play_now(at, item_uri, pos_ms=0):
    if not item_uri: return
    _api("PUT","https://api.spotify.com/v1/me/player/play", at, body={"uris":[item_uri], "position_ms": max(0,int(pos_ms))}, quiet=True, quiet_codes={400,403,404,429})
def _skip_next(at): _api("POST","https://api.spotify.com/v1/me/player/next", at, quiet=True, quiet_codes={400,403,404,429})
def _pause_player(at): _api("PUT","https://api.spotify.com/v1/me/player/pause", at, quiet=True, quiet_codes={400,403,404,429})
def _resume_player(at): _api("PUT","https://api.spotify.com/v1/me/player/play", at, quiet=True, quiet_codes={400,403,404,429})

_YT_SPOTIFY_STATE = {"paused_by_us": False, "was_playing": False, "paused_at": 0}
_YT_BOOTSTRAPPED = False

def _yt_live_spotify_snapshot():
    """Return live Spotify playback info used for YouTube handoff.

    Important: a queued YouTube request must NOT pause Spotify immediately.
    It may start only when the song that was playing at request time is over,
    the Spotify player is stopped/paused, or the remaining time is inside the
    handoff window. This also fixes the case where Spotify auto-advances to the
    next song before our polling tick hits exactly 0 ms.
    """
    try:
        if not _is_authorized():
            return {"ok": False, "authorized": False, "is_playing": False, "remaining_ms": 0}
        at = _ensure_access_token()
        st = _get_player_state(at) or {}
        item = st.get("item") or {}
        dur = int(item.get("duration_ms") or 0)
        prog = int(st.get("progress_ms") or 0)
        rem = max(0, dur - prog) if dur > 0 else (999999 if st.get("is_playing") else 0)
        return {
            "ok": True,
            "authorized": True,
            "is_playing": bool(st.get("is_playing")),
            "item_id": item.get("id") or "",
            "item_uri": item.get("uri") or "",
            "duration_ms": dur,
            "progress_ms": prog,
            "remaining_ms": rem,
        }
    except Exception as e:
        _log_throttled("WARN", "yt_live_spotify_snapshot_failed", f"Spotify live snapshot failed: {e}", 20)
        return {"ok": False, "error": str(e), "remaining_ms": None}

def _yt_live_spotify_remaining_ms():
    snap = _yt_live_spotify_snapshot()
    return snap.get("remaining_ms")

def _yt_spotify_remaining_ms():
    live = _yt_live_spotify_remaining_ms()
    if live is not None:
        return live
    try:
        with _NP_LOCK:
            cur = dict(NOWPLAYING)
        if (cur.get("provider") or "spotify").lower() != "spotify":
            return 999999
        if not cur.get("is_playing"):
            return 0
        dur = int(cur.get("duration_ms") or 0)
        prog = int(cur.get("progress_ms") or 0)
        if dur <= 0:
            return 999999
        return max(0, dur - prog)
    except Exception:
        return 999999

def _yt_attach_spotify_wait_marker(item: dict) -> dict:
    try:
        snap = _yt_live_spotify_snapshot()
        item["wait_spotify_item_id"] = snap.get("item_id") or ""
        item["wait_spotify_item_uri"] = snap.get("item_uri") or ""
        item["wait_spotify_was_playing"] = bool(snap.get("is_playing"))
        item["wait_spotify_remaining_ms"] = snap.get("remaining_ms")
        if item.get("wait_spotify_item_id"):
            _yt_log(f"YouTube request will wait for Spotify track id {item.get('wait_spotify_item_id')} to finish ({item.get('wait_spotify_remaining_ms')}ms left)")
    except Exception as e:
        _yt_log(f"Could not attach Spotify wait marker: {e}", "WARN")
    return item

def _yt_can_start_item_now(item=None):
    # YouTube may start only at the handoff point. Queueing a !yt request must
    # never pause/steal Spotify immediately. If the live Spotify snapshot is
    # temporarily unavailable, fall back to the cached NOWPLAYING state and keep
    # waiting when Spotify still looks active.
    item = item or {}
    snap = _yt_live_spotify_snapshot()
    rem = snap.get("remaining_ms")

    if not snap.get("ok", False):
        try:
            with _NP_LOCK:
                cur = dict(NOWPLAYING)
            if (cur.get("provider") or "spotify").lower() == "spotify" and bool(cur.get("is_playing")):
                dur = int(cur.get("duration_ms") or 0)
                prog = int(cur.get("progress_ms") or 0)
                cached_rem = max(0, dur - prog) if dur > 0 else 999999
                if cached_rem > 3500:
                    _yt_log(f"Spotify snapshot unavailable; keeping YouTube handoff waiting ({cached_rem}ms cached)")
                    return False
        except Exception:
            pass
        # No reliable evidence that Spotify is playing; allow YouTube to take over.
        return True

    if not snap.get("authorized", True):
        return True
    if not snap.get("is_playing"):
        return True

    wait_was_playing = bool(item.get("wait_spotify_was_playing"))
    wait_id = item.get("wait_spotify_item_id") or ""
    current_id = snap.get("item_id") or ""

    # If the request was made while Spotify was playing, wait for THAT song.
    # If Spotify already advanced to a different song, start YouTube and pause
    # the new Spotify song immediately.
    if wait_was_playing:
        if wait_id and current_id and current_id != wait_id:
            _yt_log(f"Spotify moved from queued track {wait_id} to {current_id}; starting YouTube handoff now")
            return True
        try:
            return int(rem if rem is not None else 999999) <= 3500
        except Exception:
            return False

    # If the request had no marker but Spotify is playing, still do not steal it.
    try:
        return int(rem if rem is not None else 999999) <= 3500
    except Exception:
        return False

def _yt_can_start_now():
    return _yt_can_start_item_now(None)

def _refresh_spotify_nowplaying_after_youtube():
    try:
        if not _is_authorized():
            return False
        at = _ensure_access_token()
        _np_poll_once(at, force=True)
        return True
    except Exception as e:
        _yt_log(f"Spotify nowplaying refresh after YouTube failed: {e}", "WARN")
        return False

def _spotify_pause_for_youtube():
    try:
        at = _ensure_access_token()
        st = _get_player_state(at) or {}
        was_playing = bool(st.get("is_playing"))
        if was_playing:
            _pause_player(at)
            _YT_SPOTIFY_STATE.update({"paused_by_us": True, "was_playing": True, "paused_at": _now()})
            _yt_log("Spotify paused for YouTube request handoff")
        else:
            _YT_SPOTIFY_STATE.update({"paused_by_us": False, "was_playing": False, "paused_at": _now()})
    except Exception as e:
        _yt_log(f"Spotify pause handoff failed: {e}", "WARN")

def _spotify_resume_after_youtube(force=False):
    """Return control to Spotify after YouTube.

    Spotify is the main source. When a YouTube item finishes/skips and no more
    YouTube requests are queued, we should try to start Spotify again even if
    the in-memory paused_by_us flag was lost or stale (for example after a
    restart or a missed pause state).
    """
    try:
        should_resume = bool(force or _YT_SPOTIFY_STATE.get("paused_by_us") or _YT_SPOTIFY_STATE.get("was_playing"))
        if not should_resume:
            _refresh_spotify_nowplaying_after_youtube()
            return
        at = _ensure_access_token()
        _resume_player(at)
        _YT_SPOTIFY_STATE.update({"paused_by_us": False, "was_playing": False, "paused_at": 0})
        _yt_log("Spotify resumed after YouTube queue finished")
        time.sleep(0.35)
        _refresh_spotify_nowplaying_after_youtube()
    except Exception as e:
        _yt_log(f"Spotify resume after YouTube failed: {e}", "WARN")

def _play_context_or_item(at, ctx, item, pos_ms):
    allow_offset = ctx and (ctx.startswith("spotify:playlist:") or ctx.startswith("spotify:album:") or ctx.startswith("spotify:show:"))
    if ctx:
        body = {"context_uri": ctx}
        if allow_offset and item: body["offset"] = {"uri": item}
        if pos_ms > 0: body["position_ms"] = pos_ms
        r = _api("PUT","https://api.spotify.com/v1/me/player/play", at, body=body, quiet=True, quiet_codes={400,403,404,429})
        if not (isinstance(r, dict) and r.get("_http_error_code")): return
    if item:
        _api("PUT","https://api.spotify.com/v1/me/player/play", at, body={"uris":[item], "position_ms": max(0,int(pos_ms))}, quiet=True, quiet_codes={400,403,404,429})

def _snapshot_playback(at):
    st, que = _get_player_state(at) or {}, _get_queue(at) or {}
    return {"shuffle": st.get("shuffle_state", False),
            "repeat":  st.get("repeat_state", "off"),
            "context_uri": ((st.get("context") or {}).get("uri") or None),
            "item_uri": ((st.get("item") or {}).get("uri") or None),
            "position_ms": st.get("progress_ms", 0),
            "queue": [ (t or {}).get("uri") for t in (que.get("queue") or []) if (t or {}).get("uri")]}

def _restore_playback(at, snap):
    if not snap: return
    try: _apply_shuffle(at, bool(snap.get("shuffle", False)))
    except: pass
    try: _apply_repeat(at, snap.get("repeat", "off"))
    except: pass
    _play_context_or_item(at, snap.get("context_uri"), snap.get("item_uri"), int(snap.get("position_ms") or 0))
    for uri in (snap.get("queue") or []):
        try: _api("POST","https://api.spotify.com/v1/me/player/queue", at, params={"uri": uri}, quiet=True, quiet_codes={400,403,404,429})
        except: pass

# ---- Takeover state & guard ----
TAKEOVER = _load_json(_p_state(), {"active": False, "pending": False, "pending_since": 0, "owner": "", "playlist_id": "", "backlog": [], "snapshot": {}, "ends_at": 0})
GUARD    = _load_json(_p_guard(), {"srplus_used_this_stream": False, "last_stream_started_at": 0})
def _save_takeover(): _save_json(_p_state(), TAKEOVER)
def _save_guard():    _save_json(_p_guard(), GUARD)

def _start_takeover(at, user=""):
    if SRPLUS_ONCE_PER_STREAM and GUARD.get("srplus_used_this_stream"):
        return {"ok": False, "error": "SR+ already used this stream."}
    snap = _snapshot_playback(at)
    TAKEOVER.update({"active": True, "pending": True, "pending_since": _now(), "owner": (user or ""), "playlist_id": "", "snapshot": snap, "backlog": [], "ends_at": 0})
    pid = _get_or_create_user_playlist(at, (user or "requests"))
    TAKEOVER["playlist_id"] = pid; _save_takeover()
    GUARD["srplus_used_this_stream"] = True; _save_guard()
    return {"ok": True, "pending": True, "owner": user, "playlist_id": pid}

# ---------- Now Playing ----------
NOWPLAYING = {"ok": False, "provider": "spotify", "accent": "#1DB954", "is_playing": False, "id": "", "title": "", "artist": "", "album": "", "url": "", "progress_ms": 0, "duration_ms": 0, "covers": {"url_640":"", "url_300":"", "url_64":""}, "files": {"artist":"", "title":"", "album":"", "combo":"", "url":"", "cover_640":"", "cover_300":"", "provider":"", "color":""}, "updated_at": 0}
_NP_LOCK = threading.Lock()
_NP_LAST_ID = ""
_NP_LAST_PROGRESS = 0

def _download_to(path, url):
    if not url: return False
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        _atomic_write_bytes(path, data)
        return True
    except Exception as e:
        _log_throttled("WARN", "cover_download_failed", f"cover download failed: {e}", 300)
        return False

def _download_cover_with_marker(size, url):
    try:
        if url and _download_to(_p_cover(size), url):
            _atomic_write_text(_p_cover_src(size), url)
            return True
    except Exception:
        pass
    return False

def _download_to_if_source_changed(path, src_path, url, min_size=512):
    if not url:
        return False
    old_src = ""
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            old_src = f.read().strip()
    except Exception:
        pass
    try:
        file_ok = os.path.exists(path) and os.path.getsize(path) >= int(min_size)
    except Exception:
        file_ok = False
    if old_src == url and file_ok:
        return False
    if _download_to(path, url):
        try:
            _atomic_write_text(src_path, url)
        except Exception:
            pass
        return True
    return False

def _ensure_current_spotify_cover_file(size=None):
    try:
        size = int(size or COVER_IMAGE_SIZE)
        if size not in (64, 300, 640):
            size = COVER_IMAGE_SIZE if COVER_IMAGE_SIZE in (64, 300, 640) else 300
        with _NP_LOCK:
            cur = dict(NOWPLAYING)
        if (cur.get("provider") or "spotify").lower() != "spotify":
            return _p_cover(size)
        cov = cur.get("covers") or {}
        url = cov.get(f"url_{size}") or cov.get("url_640") or cov.get("url_300") or cov.get("url_64") or ""
        if not url:
            return _p_cover(size)
        path = _p_cover(size)
        src_path = _p_cover_src(size)
        old_src = ""
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                old_src = f.read().strip()
        except Exception:
            pass
        if old_src != url or not os.path.exists(path) or os.path.getsize(path) < 512:
            _download_cover_with_marker(size, url)
        return path
    except Exception:
        return _p_cover(size or COVER_IMAGE_SIZE)

def _update_nowplaying_files(meta, download_cover: bool):
    if not NOWPLAYING_ENABLE_FILES: 
        return
    try:
        _atomic_write_text(_p_np_artist(), meta.get("artist",""))
        _atomic_write_text(_p_np_title(),  meta.get("title",""))
        _atomic_write_text(_p_np_album(),  meta.get("album",""))
        _atomic_write_text(_p_np_combo(),  f"{meta.get('artist','')} â€” {meta.get('title','')}")
        provider = (meta.get("provider") or "spotify").strip().lower()
        accent = meta.get("accent") or ("#FF0033" if provider in ("youtube", "ytmusic") else "#1DB954")
        _atomic_write_text(_p_np_url(),    meta.get("url",""))
        _atomic_write_text(_p_np_provider(), provider)
        _atomic_write_text(_p_np_color(), accent)
        
        cov = (meta.get("covers") or {})
        
        # VERBESSERUNG: Synchroner Download des Covers fÃ¼r sofortige VerfÃ¼gbarkeit
        if download_cover:
            cover_url_640 = cov.get("url_640","")
            cover_url_target = cov.get(f"url_{COVER_IMAGE_SIZE}","") or cov.get("url_300","")
            
            # Priorisiere das aktuelle Cover fÃ¼r sofortigen Download
            if cover_url_target:
                # Synchroner Download fÃ¼r das Haupt-Cover
                try:
                    if _download_cover_with_marker(COVER_IMAGE_SIZE, cover_url_target):
                        logi(f"Cover downloaded synchron: {cover_url_target}")
                except Exception as e:
                    logw(f"Sync cover download failed: {e}")
                    # Fallback: Asynchron versuchen
                    _THREAD_POOL.submit(_download_to, _p_cover(COVER_IMAGE_SIZE), cover_url_target)
            
            # 640px Cover asynchron (wird weniger dringend benÃ¶tigt)
            if cover_url_640:
                _THREAD_POOL.submit(_download_cover_with_marker, 640, cover_url_640)
        
        files = {"artist": _p_np_artist(), "title": _p_np_title(), "album": _p_np_album(), "combo": _p_np_combo(), "url": _p_np_url(), "provider": _p_np_provider(), "color": _p_np_color(), "cover_640": _p_cover(640), f"cover_{COVER_IMAGE_SIZE}": _p_cover(COVER_IMAGE_SIZE)}
        out = dict(meta); out["files"] = files; out["ok"] = True; out["updated_at"] = _now()
        _save_json(_p_np_json(), out)
        
    except Exception as e:
        _log_throttled("WARN", "np_file_export_failed", f"nowplaying file export failed: {e}", 30)

def _extract_nowplaying_from_state(st):
    item = st.get("item") or {}
    track_id = item.get("id","") or ""
    title = item.get("name","") or ""
    artist = ", ".join([a.get("name","") for a in (item.get("artists") or [])]) or ""
    album_obj = item.get("album") or {}
    cov = _extract_cover_urls_from_album_obj(album_obj)
    url = ((item.get("external_urls") or {}).get("spotify")) or (f"https://open.spotify.com/track/{track_id}" if track_id else "")
    return {"ok": True, "provider": "spotify", "accent": "#1DB954", "is_playing": bool(st.get("is_playing", False)), "id": track_id, "title": title, "artist": artist, "album": cov.get("album",""), "url": url, "progress_ms": int(st.get("progress_ms") or 0), "duration_ms": int(item.get("duration_ms") or 0), "covers": {"url_640": cov.get("url_640",""), "url_300": cov.get("url_300",""), "url_64":""}}


def _yt_thumb_url(video_id: str) -> str:
    vid = (video_id or "").strip()
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""

def _set_youtube_nowplaying(meta: dict):
    global NOWPLAYING, _NP_LAST_ID, _NP_LAST_PROGRESS
    try:
        # Only an actively popped YouTube queue item may own the overlay.
        # After skip/finish the WebView may still show an old title for a moment;
        # ignore that stale sync so the overlay can return to Spotify cleanly.
        with _YT_QUEUE_LOCK:
            active_yt = dict(_YT_CURRENT or {})
        if not active_yt:
            return {"ok": True, "ignored": True, "reason": "no_active_youtube_current"}
        title = (meta.get("title") or "").strip()
        artist = (meta.get("artist") or meta.get("subtitle") or "").strip()
        url = (meta.get("url") or "").strip()
        vid = (meta.get("video_id") or _yt_extract_video_id(url) or "").strip()
        # If the WebView could not read player-bar metadata yet, fall back to the
        # active queue item. This keeps Artist/Song visible immediately in the
        # custom overlay instead of showing an empty YouTube state.
        if not title or title.lower() in ("youtube music", "music.youtube.com"):
            try:
                with _YT_QUEUE_LOCK:
                    ytc = dict(_YT_CURRENT or {})
                qtitle = (ytc.get("title") or ytc.get("query") or "").strip()
                # Do not show raw URLs as song text in the overlay.
                if qtitle.startswith("http://") or qtitle.startswith("https://"):
                    qtitle = "YouTube Music"
                title = title or qtitle
                artist = artist or (ytc.get("artist") or "YouTube Music").strip()
                url = url or (ytc.get("url") or ytc.get("query") or "").strip()
                vid = vid or (ytc.get("video_id") or _yt_extract_video_id(url) or "").strip()
            except Exception:
                pass
        if not artist or artist.lower() in ("youtube", "youtube music", "music.youtube.com"):
            artist = "powered by spotis3mptify"
        progress_ms = int(float(meta.get("progress_ms") or 0))
        duration_ms = int(float(meta.get("duration_ms") or 0))
        thumb = (meta.get("thumbnail") or _yt_thumb_url(vid)).strip()
        item_id = vid or url or title
        out = {
            "ok": bool(title or artist or url),
            "provider": "youtube",
            "accent": "#FF0033",
            "is_playing": bool(meta.get("is_playing", True)),
            "id": item_id,
            "video_id": vid,
            "title": (title if not str(title).startswith(("http://", "https://")) else "YouTube Music") or "YouTube Music",
            "artist": artist or "powered by spotis3mptify",
            "album": "YouTube Music",
            "url": url,
            "progress_ms": progress_ms,
            "duration_ms": duration_ms,
            "covers": {"url_640": thumb, "url_300": thumb, "url_64": thumb},
            "thumbnail": thumb,
            "updated_at": _now(),
        }
        with _NP_LOCK:
            NOWPLAYING.update(out)
            _NP_LAST_ID = item_id
            _NP_LAST_PROGRESS = progress_ms
        _update_nowplaying_files(out, download_cover=False)
        if thumb:
            try:
                _download_to_if_source_changed(_p_yt_thumb(), _p_yt_thumb_src(), thumb)
            except Exception:
                _THREAD_POOL.submit(_download_to_if_source_changed, _p_yt_thumb(), _p_yt_thumb_src(), thumb)
        _log_throttled("INFO", "yt_np_changed", f"youtube nowplaying: {out.get('artist','')} â€” {out.get('title','')}", 10)
        return {"ok": True, "nowplaying": out}
    except Exception as e:
        _yt_log(f"YouTube nowplaying sync failed: {e}", "WARN")
        return {"ok": False, "error": str(e)}

def _spotify_live_meta_if_playing():
    """Return live Spotify metadata only when Spotify is actually playing.

    This is intentionally used as a source-of-truth guard for the overlay: a
    stale YouTube current item must never keep the browser/dashboard red while
    Spotify is the source that is really playing.
    """
    try:
        if not _is_authorized():
            return None
        at = _ensure_access_token()
        st = _get_player_state(at) or {}
        if not bool(st.get("is_playing")):
            return None
        item = st.get("item") or {}
        if not item.get("id"):
            return None
        return _extract_nowplaying_from_state(st)
    except Exception as e:
        _log_throttled("WARN", "spotify_live_source_guard_failed", f"Spotify live source guard failed: {e}", 20)
        return None

def _promote_spotify_if_really_playing(reason="source_guard"):
    global NOWPLAYING, _NP_LAST_ID, _NP_LAST_PROGRESS, _YT_CURRENT
    try:
        with _YT_QUEUE_LOCK:
            _yt_load()
            if _YT_CURRENT:
                return False
    except Exception:
        pass
    meta = _spotify_live_meta_if_playing()
    if not meta:
        return False
    with _NP_LOCK:
        current_provider = (NOWPLAYING.get("provider") or "spotify").lower()
        current_id = NOWPLAYING.get("id") or ""
    changed = current_provider != "spotify" or current_id != (meta.get("id") or "")
    with _NP_LOCK:
        NOWPLAYING.update(meta)
        NOWPLAYING["updated_at"] = _now()
        NOWPLAYING["files"] = {"artist": _p_np_artist(), "title": _p_np_title(), "album": _p_np_album(), "combo": _p_np_combo(), "url": _p_np_url(), f"cover_{COVER_IMAGE_SIZE}": _p_cover(COVER_IMAGE_SIZE)}
        _NP_LAST_ID = meta.get("id") or ""
        _NP_LAST_PROGRESS = int(meta.get("progress_ms") or 0)
    if changed:
        try:
            _update_nowplaying_files(meta, download_cover=True)
        except Exception:
            pass
        with _YT_QUEUE_LOCK:
            try:
                _yt_load()
                if _YT_CURRENT:
                    old = dict(_YT_CURRENT)
                    old["status"] = "superseded_by_spotify"
                    _YT_HISTORY.append(old); del _YT_HISTORY[:-30]
                    _YT_CURRENT = None
                    _yt_save()
                    _yt_log("Spotify is playing again; cleared stale YouTube current and switched overlay back to Spotify")
            except Exception:
                pass
        _log_throttled("INFO", "source_guard_spotify", "active source switched to Spotify", 5)
    return True

def _overlay_current():
    # YouTube owns the overlay while a YouTube queue item is active. Spotify may
    # still report a playing state for a moment during handoff, but that must
    # not overwrite the visible provider.
    yt_active_for_overlay = False
    try:
        with _YT_QUEUE_LOCK:
            _yt_load()
            yt_active_for_overlay = bool(_YT_CURRENT)
    except Exception:
        yt_active_for_overlay = False
    if not yt_active_for_overlay:
        _promote_spotify_if_really_playing("overlay_current")
    with _NP_LOCK:
        cur = dict(NOWPLAYING)
    try:
        with _YT_QUEUE_LOCK:
            _yt_load()
            ytc = dict(_YT_CURRENT or {})
        if ytc and (ytc.get("player_mode") == "ytmusic"):
            title = (cur.get("title") or "").strip()
            if (cur.get("provider") != "youtube") or not title:
                q = (ytc.get("query") or ytc.get("title") or "YouTube Music").strip()
                display_q = "YouTube Music" if q.startswith(("http://", "https://")) else (q or "YouTube Music")
                cur.update({"ok": True, "provider": "youtube", "accent": "#FF0033", "title": display_q, "artist": "powered by spotis3mptify", "album": "YouTube Music", "url": ytc.get("url") or q, "video_id": ytc.get("video_id") or ""})
    except Exception:
        pass
    cur.setdefault("provider", "spotify")
    cur.setdefault("accent", "#1DB954" if cur.get("provider") == "spotify" else "#FF0033")
    try:
        prov = (cur.get("provider") or "spotify").lower()
        if prov == "youtube":
            thumb = cur.get("thumbnail") or (cur.get("covers") or {}).get("url_640") or ""
            cover_identity = cur.get("video_id") or cur.get("id") or cur.get("url") or thumb or ""
            cur["cover_version"] = f"youtube:{cover_identity}:{thumb}"
            cur["cover_url"] = thumb or f"/cover/latest?size=640&v={urllib.parse.quote(cur['cover_version'], safe='')}"
        else:
            cov = cur.get("covers") or {}
            cover_src = cov.get(f"url_{COVER_IMAGE_SIZE}") or cov.get("url_640") or cov.get("url_300") or cov.get("url_64") or ""
            cover_identity = cur.get("id") or cur.get("url") or cover_src or ""
            cur["cover_version"] = f"spotify:{cover_identity}:{cover_src}"
            cur["cover_url"] = f"/cover/latest?size={int(COVER_IMAGE_SIZE)}&v={urllib.parse.quote(cur['cover_version'], safe='')}"
    except Exception:
        pass
    return cur

def _overlay_text_html(kind: str) -> str:
    import html as _html
    kind = (kind or "song").lower()
    cur = _overlay_current()
    value = cur.get("artist") if kind == "artist" else cur.get("title")
    value = value or ""
    weight = "900" if kind == "artist" else "400"
    mode = (OVERLAY_MARQUEE_MODE or "bounce").strip().lower()
    if mode not in ("bounce", "scroll-ltr", "scroll-rtl", "off"):
        mode = "bounce"
    try:
        speed = max(10, min(400, int(OVERLAY_MARQUEE_SPEED)))
    except Exception:
        speed = 45
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{{margin:0;width:100%;height:100%;background:transparent;overflow:hidden;}}
body{{display:flex;align-items:center;justify-content:center;color:#fff;font-family:Nuishock,Nulshock,Square,"Arial Black",Impact,sans-serif;font-size:54px;font-weight:{weight};line-height:1;text-align:center;text-shadow:none;}}
#box{{width:100vw;max-width:100vw;overflow:hidden;white-space:nowrap;}}
#txt{{display:inline-block;white-space:nowrap;will-change:transform;}}
@keyframes s3bounce{{from{{transform:translateX(0)}}to{{transform:translateX(calc(-1 * var(--marquee-distance,0px)))}}}}
@keyframes s3scrollltr{{from{{transform:translateX(calc(-1 * var(--text-width,0px)))}}to{{transform:translateX(var(--box-width,100vw))}}}}
@keyframes s3scrollrtl{{from{{transform:translateX(var(--box-width,100vw))}}to{{transform:translateX(calc(-1 * var(--text-width,0px)))}}}}
</style></head><body><div id="box"><span id="txt">{_html.escape(str(value))}</span></div><script>
const KIND={kind!r};const MODE={mode!r};const SPEED={speed};let lastValue={_html.escape(str(value)).__repr__()};let lastSig='';
function applyMarquee(force=false){{
  const box=document.getElementById('box'), txt=document.getElementById('txt');
  const boxW=box.clientWidth||window.innerWidth||1, textW=txt.scrollWidth||1, overflow=Math.max(0,textW-boxW);
  const sig=[MODE,SPEED,boxW,textW,overflow,txt.textContent].join('|');
  if(!force&&sig===lastSig)return;
  lastSig=sig;
  txt.style.animation='none'; txt.style.transform='translateX(0)';
  txt.style.setProperty('--box-width',boxW+'px'); txt.style.setProperty('--text-width',textW+'px'); txt.style.setProperty('--marquee-distance',overflow+'px');
  if(MODE==='off'||overflow<2)return;
  const sp=Math.max(10,Number(SPEED)||45);
  if(MODE==='bounce'){{ const dur=Math.max(2.2, overflow/sp); txt.style.animation='s3bounce '+dur+'s ease-in-out infinite alternate'; }}
  else if(MODE==='scroll-rtl'){{ const dur=Math.max(3,(textW+boxW)/sp); txt.style.animation='s3scrollrtl '+dur+'s linear infinite'; }}
  else {{ const dur=Math.max(3,(textW+boxW)/sp); txt.style.animation='s3scrollltr '+dur+'s linear infinite'; }}
}}
async function pollNowPlaying(){{
  try{{
    const r=await fetch('/nowplaying?_='+Date.now(),{{cache:'no-store'}});
    const d=await r.json();
    const v=String((KIND==='artist'?d.artist:d.title)||'');
    if(v!==lastValue){{lastValue=v;document.getElementById('txt').textContent=v;lastSig='';requestAnimationFrame(()=>applyMarquee(true));}}
  }}catch(e){{}}
  setTimeout(pollNowPlaying,1500);
}}
window.addEventListener('load',()=>applyMarquee(true));window.addEventListener('resize',()=>{{lastSig='';applyMarquee(true)}});setTimeout(()=>applyMarquee(true),80);pollNowPlaying();
</script></body></html>'''

def _overlay_cover_html() -> str:
    cur = _overlay_current()
    try:
        version = str(cur.get("cover_version") or cur.get("id") or cur.get("video_id") or cur.get("url") or int(time.time()))
    except Exception:
        version = str(int(time.time()))
    img_src = "/browser/cover?raw=1&v=" + urllib.parse.quote(version, safe="")
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{{margin:0;width:100%;height:100%;background:transparent;overflow:hidden;}}
.wrap{{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;background:transparent;}}
img{{width:100%;height:100%;object-fit:cover;border-radius:50%;display:block;animation:spin 9s linear infinite;}}
.fallback{{width:100%;height:100%;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#111;color:#fff;font:900 28px Nuishock,Nulshock,Square,"Arial Black",Impact,sans-serif;animation:spin 9s linear infinite;}}
@keyframes spin{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}
</style></head><body><div class="wrap"><img id="cover" src="{img_src}" onerror="this.style.display='none';document.getElementById('fallback').style.display='flex'"><div id="fallback" class="fallback" style="display:none">â™ª</div></div><script>
let lastVersion={version!r};
async function pollCover(){{
  try{{
    const r=await fetch('/nowplaying?_='+Date.now(),{{cache:'no-store'}});
    const d=await r.json();
    const v=String(d.cover_version||d.id||d.video_id||d.url||'');
    if(v && v!==lastVersion){{
      lastVersion=v;
      const img=document.getElementById('cover');
      const fb=document.getElementById('fallback');
      img.onload=()=>{{img.style.display='block';fb.style.display='none';}};
      img.src='/browser/cover?raw=1&v='+encodeURIComponent(v);
    }}
  }}catch(e){{}}
  setTimeout(pollCover,1500);
}}
pollCover();
</script></body></html>'''

def _overlay_line_html(kind: str, qd: dict) -> str:
    cur = _overlay_current()
    provider = (cur.get("provider") or "spotify").lower()
    color = "#FF0033" if provider == "youtube" else "#1DB954"
    try: w = int((qd.get("w") or qd.get("width") or ["780"])[0])
    except Exception: w = 780
    try: h = int((qd.get("h") or qd.get("height") or ["10"])[0])
    except Exception: h = 10
    w = max(1, min(w, 4000)); h = max(1, min(h, 500))
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{{margin:0;width:100%;height:100%;background:transparent;overflow:hidden;}}
.line{{width:{w}px;height:{h}px;background:{color};border-radius:{max(1,h//2)}px;box-shadow:none;}}
body{{display:flex;align-items:center;justify-content:center;}}
</style></head><body><div class="line"></div><script>setTimeout(()=>location.reload(),1000)</script></body></html>'''

# --- Twitch NowPlaying announce helpers (NEU) ---
_LAST_NP_ANNOUNCE = {"id": "", "ts": 0}

def _twitch_say_sys(msg: str) -> bool:
    try:
        if not (TWITCH_LISTEN and msg):
            return False
        ch = TWITCH_CHANNEL if TWITCH_REPLY_SENDER == "main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)
        if not ch:
            return False
        thr = _TWITCH_THREAD
        if not thr or not thr.is_alive():
            return False
        if not TWITCH_REPLY:
            return False
        out = f"{msg}{TWITCH_REPLY_SUFFIX}"
        thr.send(f"PRIVMSG #{ch} :{out}")
        return True
    except Exception:
        return False

def _announce_nowplaying_to_twitch(meta: dict):
    if not (TWITCH_NP_ON_CHANGE and meta and meta.get("id")):
        return
    tid = meta.get("id","")
    now = _now()
    last_id = _LAST_NP_ANNOUNCE.get("id","")
    last_ts = int(_LAST_NP_ANNOUNCE.get("ts", 0) or 0)
    if tid == last_id and (now - last_ts) < max(1, int(TWITCH_NP_COOLDOWN_SEC)):
        return
    text = (TWITCH_NP_FORMAT or "").format(
        artist=meta.get("artist","").strip(),
        title=meta.get("title","").strip(),
        album=meta.get("album","").strip(),
        url=meta.get("url","").strip()
    ).strip()
    if _twitch_say_sys(text):
        _LAST_NP_ANNOUNCE.update({"id": tid, "ts": now})

def _np_poll_once(at, force=False):
    global _NP_LAST_ID, _NP_LAST_PROGRESS, NOWPLAYING, _BACKOFF_UNTIL
    remaining_backoff = max(0, _BACKOFF_UNTIL - _now())
    if remaining_backoff > 0 and not force:
        _log_throttled("INFO", "np_backoff", f"rate-limited; waiting {remaining_backoff}s before next poll", 2)
        return False
    try:
        st = _get_player_state(at) or {}
        try:
            with _YT_QUEUE_LOCK:
                _yt_load()
                yt_current_active = bool(_YT_CURRENT)
            # YouTube owns the overlay only while Spotify is not actually playing.
            # If Spotify is playing, it is the real active source and may update
            # NOWPLAYING even when a stale YouTube current is still stored.
            if yt_current_active:
                return False
        except Exception:
            pass
        item = st.get("item") or {}
        if not item.get("id"): 
            if _NP_LAST_ID:
                _NP_LAST_ID = ""
                _NP_LAST_PROGRESS = 0
            return False
            
        meta = _extract_nowplaying_from_state(st)
        prev_id, prev_prog = _NP_LAST_ID, _NP_LAST_PROGRESS
        id_changed = (meta["id"] != prev_id)
        restarted = (not id_changed) and (meta["progress_ms"] < max(1000, prev_prog - 500))
        track_changed = id_changed or restarted
        
        with _NP_LOCK:
            old_cov = (NOWPLAYING.get("covers") or {})
        cover_changed = (meta["covers"].get("url_640") != old_cov.get("url_640") or meta["covers"].get("url_300") != old_cov.get("url_300"))
        
        # VERBESSERUNG: Immer Cover aktualisieren bei Track-Wechsel
        need_cover = track_changed or cover_changed or force
        
        with _NP_LOCK:
            NOWPLAYING.update(meta)
            NOWPLAYING["updated_at"] = _now()
            NOWPLAYING["files"] = {"artist": _p_np_artist(), "title": _p_np_title(), "album": _p_np_album(), "combo": _p_np_combo(), "url": _p_np_url(), f"cover_{COVER_IMAGE_SIZE}": _p_cover(COVER_IMAGE_SIZE)}
        
        # VERBESSERUNG: Bei JEDER Ã„nderung oder force die Files updaten
        if track_changed or cover_changed or force:
            _update_nowplaying_files(meta, download_cover=need_cover)
            if LOG_NP_ON_CHANGE:
                _log_throttled("INFO", "nowplaying_changed", f"nowplaying: {meta.get('artist','')} â€” {meta.get('title','')}", 10)
            
            # VERBESSERUNG: OBS Cover immer bei Track-Wechsel aktualisieren, aber mit VerzÃ¶gerung fÃ¼r Cover-Download
            if track_changed and OBS_WS_ENABLED:
                def _delayed_obs_update():
                    # Kurze VerzÃ¶gerung um Cover-Download zu ermÃ¶glichen
                    time.sleep(0.5)
                    try:
                        _obs_update_cover_display()
                        logi("OBS cover updated after track change")
                    except Exception as e:
                        logw(f"OBS cover update failed: {e}")
                _THREAD_POOL.submit(_delayed_obs_update)
            
            # VERBESSERUNG: Twitch Announcement bei Track-Wechsel
            if track_changed and TWITCH_NP_ON_CHANGE:
                _announce_nowplaying_to_twitch(meta)
                
            # VERBESSERUNG: Auto Filter Sequence mit etwas mehr VerzÃ¶gerung
            if OBS_FILTER_AUTO_ON_NP_CHANGE and track_changed:
                def _auto_obs_sequence():
                    try:
                        # Zuerst Cover aktualisieren
                        time.sleep(0.8)
                        _obs_update_cover_display()
                        # Dann Filter-Sequenz
                        _obs_trigger_filter_sequence(None)
                        logi("OBS auto sequence triggered via NP change")
                    except Exception as e:
                        logw(f"OBS auto sequence failed: {e}")
                _THREAD_POOL.submit(_auto_obs_sequence)
        
        _NP_LAST_ID = meta["id"]
        _NP_LAST_PROGRESS = meta["progress_ms"]
        return track_changed or cover_changed
        
    except Exception as e:
        _log_throttled("WARN", "np_poll_failed", f"nowplaying poll failed: {e}", 60)
        return False

# --------- Poller Thread ---------
_POLLERS_ACTIVE = False
_POLL_THREAD = None
def _poll_loop():
    global _POLLERS_ACTIVE
    logi("poller thread started.")
    while _POLLERS_ACTIVE:
        try:
            at = _ensure_access_token()
            _np_poll_once(at)
        except RuntimeError as e:
            _log_throttled("WARN", "auth_missing_timer", str(e), 60)
        except Exception as e:
            _log_throttled("WARN", "timer_np_err", f"timer np: {e}", 60)
        time.sleep(max(0.3, NOWPLAYING_POLL_MS/1000.0))
    logi("poller thread stopped.")

def _maybe_enable_pollers():
    global _POLLERS_ACTIVE, _POLL_THREAD
    if _POLLERS_ACTIVE or not _is_authorized(): return
    _POLLERS_ACTIVE = True
    _POLL_THREAD = threading.Thread(target=_poll_loop, daemon=True)
    _POLL_THREAD.start()
    try:
        at = _ensure_access_token()
        _np_poll_once(at, force=True)
    except: pass

def _disable_pollers():
    global _POLLERS_ACTIVE
    _POLLERS_ACTIVE = False

# ======================= Rate limit (link-only) =======================
def _recent_load(): return _load_json(_p_recent(), {"tracks": {}})
def _recent_save(d): _save_json(_p_recent(), d)
def _recent_cleanup(d, window):
    now=_now()
    for tid, ts in list(d["tracks"].items()):
        if now - int(ts or 0) >= window: del d["tracks"][tid]
def _check_link_ratelimit(track_id, window):
    if not track_id: return (True, 0)
    d = _recent_load(); _recent_cleanup(d, window)
    last = int((d["tracks"].get(track_id) or 0))
    if last <= 0: return (True, 0)
    delta = _now() - last
    if delta >= window: return (True, 0)
    return (False, window - delta)
def _mark_link_played(track_id):
    if not track_id: return
    d = _recent_load(); d["tracks"][track_id] = _now(); _recent_save(d)

# ---------- Async playlist add ----------
def _async_add_to_user_playlist(user_norm, track_id, track_uri, rid="sr#"):
    try:
        at = _ensure_access_token()
        pid = _get_or_create_user_playlist(at, user_norm)
        if not _playlist_has_track(at, pid, track_id):
            add_res = _playlist_add_tracks(at, pid, [track_uri])
            info = _playlist_get_info(at, pid)
            url = (((info.get("external_urls") or {}).get("spotify")) or f"https://open.spotify.com/playlist/{pid}")
            total = ((info.get("tracks") or {}).get("total"))
            snap = (add_res or {}).get("snapshot_id") or ""
            logi(f"{rid} saved to user playlist for @{user_norm} Â· tracks={total if total is not None else '?'} Â· snapshot={snap[:10]} Â· {url}")
        else:
            _log_throttled("INFO", f"playlist_track_exists:{track_id}", f"{rid} track already exists in playlist for @{user_norm}", 300)
    except Exception as e:
        _log_throttled("WARN", "async_add_failed", f"{rid} async add failed: {e}", 120)

def _spawn_async_add(user_norm, track_id, track_uri, rid="sr#"):
    if ASYNC_PLAYLIST_ADD:
        _THREAD_POOL.submit(_async_add_to_user_playlist, user_norm, track_id, track_uri, rid)
    else:
        _async_add_to_user_playlist(user_norm, track_id, track_uri, rid)


def _format_sr_cooldown_message(seconds):
    try:
        total = max(0, int(float(str(seconds).strip())))
    except Exception:
        total = 0
    minutes = total // 60
    secs = total % 60
    return f"This song is on cooldown for {minutes}:{secs:02d} min. Please choose another song."

# ======================= Core /sr handler =======================
def _normalize_user(raw_user):
    s = str(raw_user or "").strip()
    if not s:
        return "someone"
    s = re.sub(r"[\u200b-\u200f\u2060\ufeff\u034f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s.startswith("@"):
        s = s[1:].strip()
    # Do not let bridge/display suffixes create separate playlists for the same user.
    s = re.sub(r"\s*@\s*(?:tw|tt|yt|twitch|tiktok|youtube|kick)$", "", s, flags=re.I).strip()
    s = re.sub(r"\s*[-_/|]\s*(?:tw|tt|yt|twitch|tiktok|youtube|kick)$", "", s, flags=re.I).strip()
    return s[:50] if s else "someone"

def _playlist_key_for_user(user_display):
    return re.sub(r"\s+", " ", _normalize_user(user_display)).strip().lower()

def _clean_sr_query(text):
    s = (text or "")
    # Entfernt unsichtbare Unicode-Format-/Steuerzeichen, die aus Chat-Exports mitkommen kÃ¶nnen.
    s = "".join(ch for ch in s if ((ch >= " " and ch != "\x7f") or ch in "\t\r\n"))
    s = re.sub(r"[\u200b-\u200f\u2060\ufeff\u034f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _handle_sr(q_raw, user):
    rid = f"sr#{random.randint(100000,999999)}"
    at = _ensure_access_token()
    q = _clean_sr_query(urllib.parse.unquote_plus((q_raw or "").strip()))
    meta = _resolve_track(at, q)
    if not meta or not meta.get("uri"):
        logw(f"SR resolve failed for query: {q}")
        return None, "No track found"

    looks_like_link = "open.spotify.com" in q.lower() or "spoti.fi" in q.lower() or "spotify.link" in q.lower() or q.lower().startswith("spotify:track:")
    if looks_like_link:
        window = max(0,int(COOLDOWN_MINUTES))*60
        if window > 0:
            ok, retry = _check_link_ratelimit(meta["id"], window)
            if not ok: return None, f"RATELIMIT:{retry}"

    if REPEAT_GUARD:
        try:
            st = _get_player_state(at) or {}
            if (st.get("repeat_state") or "off") == "track":
                _apply_repeat(at,"off")
        except: pass

    if TAKEOVER.get("active") and not TAKEOVER.get("pending"):
        TAKEOVER["backlog"].append(meta["uri"]); _save_takeover()
        if user:
            user_norm = _normalize_user(user)
            _spawn_async_add(user_norm, meta["id"], meta["uri"], rid)
        return {"ok": True, "deferred": True, "queued": None, "id": meta["id"], "title": meta["title"], "artist": meta["artist"], "album": meta.get("album",""), "url": meta["url"], "by": user, "takeover_owner": TAKEOVER.get("owner"), "covers": meta.get("covers", {})}, None

    played_now = False
    try:
        if PLAY_NOW:
            _play_now(at, meta["uri"]); played_now = True
        else:
            url = "https://api.spotify.com/v1/me/player/queue?" + urllib.parse.urlencode({"uri": meta["uri"]})
            req = urllib.request.Request(url, method="POST"); req.add_header("Authorization", f"Bearer {at}")
            with urllib.request.urlopen(req, timeout=10): pass
            if QUEUE_THEN_SKIP:
                _skip_next(at); played_now = True
    except urllib.error.HTTPError as e:
        try: body_txt = e.read().decode("utf-8","ignore"); body = json.loads(body_txt) if body_txt else {}
        except: body = {}
        reason  = ((body.get("error") or {}).get("reason") or "").upper()
        message = (body.get("error") or {}).get("message") or "Spotify error"
        if reason == "NO_ACTIVE_DEVICE":
            return None, "No active Spotify device. Open Spotify and press Play once."
        if reason == "RESTRICTED_CONTENT":
            return None, "This content cannot be queued/played on the current device."
        code = getattr(e, "code", 0)
        return None, (message or f"Playback/Queue failed (HTTP {code})")
    except Exception as e:
        return None, f"Playback/Queue request failed: {e}"

    if looks_like_link: _mark_link_played(meta["id"])
    try:
        if user:
            user_norm = _normalize_user(user)
            _spawn_async_add(user_norm, meta["id"], meta["uri"], rid)
    except Exception as e:
        _log_throttled("WARN", "add_to_playlist_failed", f"{rid} add to user playlist failed: {e}", 120)

    return {"ok": True, "queued": (None if played_now else meta["uri"]), "playing_now": bool(played_now),
            "id": meta["id"], "title": meta["title"], "artist": meta["artist"], "album": meta.get("album",""), "url": meta["url"], "by": user, "covers": meta.get("covers", {})}, None


# ======================= YouTube request queue / player =======================
_YT_WEBVIEW_STATUS = {"running": False, "ts": 0, "logged_in": False, "consent_visible": False, "sign_in_visible": False, "reason": "not_started", "audio_devices": [], "audio_selected": "Default", "audio_applied": ""}

_YT_QUEUE_LOCK = threading.RLock()
_YT_QUEUE = []
_YT_CURRENT = None
_YT_HISTORY = []
_YT_CONTROL = {"skip_seq": 0, "clear_seq": 0}
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_LOG_LOCK = threading.RLock()
_YT_LOG = []
_YT_LAST_PLAYER_STATE = {"current_id": "", "queue_len": -1, "ts": 0}

def _yt_log_file_path(): _ensure_dir(YOUTUBE_DIR); return os.path.join(YOUTUBE_DIR, "youtube_debug.log")
def _yt_log(msg, level="INFO"):
    line = f"[{_ts()}] [YouTube] {msg}"
    with _YT_LOG_LOCK:
        _YT_LOG.append(line)
        del _YT_LOG[:-500]
    try:
        _ensure_dir(YOUTUBE_DIR)
        with open(_yt_log_file_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        _log(level, f"[YouTube] {msg}")
    except Exception:
        pass

def _yt_get_logs(limit=250):
    with _YT_LOG_LOCK:
        rows = list(_YT_LOG[-max(1, min(int(limit or 250), 500)):])
    return {"ok": True, "lines": rows, "text": "\n".join(rows), "count": len(rows), "file": _yt_log_file_path()}

def _yt_clear_logs():
    with _YT_LOG_LOCK:
        _YT_LOG.clear()
    try:
        with open(_yt_log_file_path(), "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass
    _yt_log("Log cleared from UI")
    return _yt_get_logs()

def _yt_audio_state():
    return {
        "ok": True,
        "selected": (YOUTUBE_AUDIO_OUTPUT_NAME or "Default"),
        "devices": list(_YT_WEBVIEW_STATUS.get("audio_devices") or []),
        "applied": str(_YT_WEBVIEW_STATUS.get("audio_applied") or ""),
        "webview_running": bool(_YT_WEBVIEW_STATUS.get("running") and (_now() - float(_YT_WEBVIEW_STATUS.get("ts") or 0) < 6)),
    }

def _yt_storage_path(): _ensure_dir(YOUTUBE_DIR); return os.path.join(YOUTUBE_DIR, "youtube_queue.json")
def _yt_public(item): return None if not item else {k:item.get(k) for k in ("id","video_id","title","artist","url","by","duration_sec","requested_at","status","query","player_mode","source")}
def _yt_save():
    try: _save_json(_yt_storage_path(), {"queue":_YT_QUEUE,"current":_YT_CURRENT,"history":_YT_HISTORY[-30:],"control":_YT_CONTROL})
    except Exception as e: _log_throttled("WARN","yt_save",f"YouTube queue save failed: {e}",30)
def _yt_load():
    global _YT_QUEUE,_YT_CURRENT,_YT_HISTORY,_YT_BOOTSTRAPPED
    try:
        d=_load_json(_yt_storage_path(),{})
        if isinstance(d.get("queue"),list): _YT_QUEUE=d["queue"][-100:]
        loaded_current = d.get("current") if isinstance(d.get("current"), dict) else None
        if isinstance(d.get("history"),list): _YT_HISTORY=d["history"][-30:]
        if isinstance(d.get("control"),dict): _YT_CONTROL.update(d.get("control") or {})

        # Spotify is the main source on app start. A YouTube item saved as
        # "current" from a previous run must not keep blocking Spotify polling
        # or pin the overlay to YouTube after a restart. Keep queued items, but
        # discard stale current playback state once per process.
        if not _YT_BOOTSTRAPPED:
            _YT_BOOTSTRAPPED = True
            if loaded_current:
                old = dict(loaded_current)
                old["status"] = "abandoned_on_restart"
                _YT_HISTORY.append(old); del _YT_HISTORY[:-30]
                _YT_CURRENT = None
                try:
                    _save_json(_yt_storage_path(), {"queue":_YT_QUEUE,"current":None,"history":_YT_HISTORY[-30:],"control":_YT_CONTROL})
                except Exception:
                    pass
                _yt_log("Cleared stale YouTube current on startup; Spotify remains the main source")
                return
        _YT_CURRENT = loaded_current
    except Exception as e:
        _yt_log(f"Queue load failed: {e}", "WARN")

def _yt_extract_video_id(text):
    text=(text or '').strip()
    if _YT_ID_RE.match(text): return text
    try:
        u=urllib.parse.urlparse(text); host=(u.netloc or '').lower()
        if 'youtu.be' in host:
            vid=(u.path or '').strip('/').split('/')[0]
            return vid if _YT_ID_RE.match(vid) else None
        if 'youtube.com' in host or 'music.youtube.com' in host:
            qs=urllib.parse.parse_qs(u.query or ''); vid=(qs.get('v') or [None])[0]
            if vid and _YT_ID_RE.match(vid): return vid
            parts=[x for x in (u.path or '').split('/') if x]
            for key in ('shorts','embed','live'):
                if key in parts:
                    i=parts.index(key)
                    if i+1<len(parts) and _YT_ID_RE.match(parts[i+1]): return parts[i+1]
    except Exception: pass
    return None

def _yt_embed_allowed(video_id):
    _yt_log(f"Checking embed permission for {video_id}")
    """Return True/False when YouTube oEmbed can tell us if the clip is embeddable.
    Return None on network/temporary errors so links are not blocked too aggressively.
    """
    if not video_id or not _YT_ID_RE.match(video_id):
        return False
    try:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": watch_url, "format": "json"})
        req = urllib.request.Request(url, method='GET')
        req.add_header('User-Agent', 'Mozilla/5.0 Chrome/124 Safari/537.36')
        with urllib.request.urlopen(req, timeout=6) as r:
            ok = 200 <= int(getattr(r, 'status', 200)) < 300
            _yt_log(f"Embed check {video_id}: {ok}")
            return ok
    except urllib.error.HTTPError as e:
        code = int(getattr(e, 'code', 0) or 0)
        if code in (401, 403, 404):
            _yt_log(f"Embed check {video_id}: blocked HTTP {code}", "WARN")
            return False
        _yt_log(f"Embed check {video_id}: unknown HTTP {code}", "WARN")
        return None
    except Exception as e:
        _log_throttled('WARN', 'yt_oembed', f'YouTube embeddable check failed: {e}', 30)
        return None

def _yt_fetch_video(video_id, check_embed=False):
    _yt_log(f"Fetching metadata for {video_id} (check_embed={bool(check_embed)})")
    item={"video_id":video_id,"title":f"YouTube {video_id}","artist":"YouTube","duration_sec":0,"url":f"https://www.youtube.com/watch?v={video_id}","embed_ok":None}
    if check_embed:
        item['embed_ok'] = _yt_embed_allowed(video_id)
    try:
        req=urllib.request.Request(item['url'],method='GET')
        req.add_header('User-Agent','Mozilla/5.0 Chrome/124 Safari/537.36')
        req.add_header('Accept-Language','de-DE,de;q=0.9,en;q=0.8')
        with urllib.request.urlopen(req,timeout=8) as r: page=r.read().decode('utf-8','ignore')
        m=re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"',page)
        if m:
            import html as _html; item['title']=_html.unescape(m.group(1)).strip()
        a=re.search(r'"author":"([^"]+)"',page)
        if a: item['artist']=a.group(1)
        d=re.search(r'"lengthSeconds":"?(\d+)"?',page)
        if d: item['duration_sec']=int(d.group(1))
        _yt_log(f"Metadata resolved {video_id}: title='{item.get('title','')}', artist='{item.get('artist','')}', duration={item.get('duration_sec',0)}s, embed={item.get('embed_ok')}")
    except Exception as e:
        _log_throttled('WARN','yt_meta',f'YouTube metadata fetch failed: {e}',30)
        _yt_log(f"Metadata fetch failed for {video_id}: {e}", "WARN")
    return item

def _yt_search_web(query):
    q=_clean_sr_query(query)
    if not q: return None
    _yt_log(f"Searching YouTube for: {q}")
    url='https://www.youtube.com/results?'+urllib.parse.urlencode({'search_query':q})
    req=urllib.request.Request(url,method='GET')
    req.add_header('User-Agent','Mozilla/5.0 Chrome/124 Safari/537.36')
    req.add_header('Accept-Language','de-DE,de;q=0.9,en;q=0.8')
    with urllib.request.urlopen(req,timeout=8) as r: page=r.read().decode('utf-8','ignore')
    seen=set(); first_unknown=None
    for m in re.finditer(r'"videoId":"([A-Za-z0-9_-]{11})"',page):
        vid=m.group(1)
        if vid in seen: continue
        seen.add(vid)
        meta=_yt_fetch_video(vid, check_embed=True)
        if not meta: continue
        if meta.get('embed_ok') is True:
            _yt_log(f"Search picked embeddable result: {vid} â€” {meta.get('title','')}")
            return meta
        if meta.get('embed_ok') is False:
            _yt_log(f"Search skipped blocked result: {vid} â€” {meta.get('title','')}", "WARN")
        if meta.get('embed_ok') is None and first_unknown is None:
            first_unknown=meta
        if len(seen) >= 15:
            break
    if first_unknown:
        _yt_log(f"Search fallback picked unchecked result: {first_unknown.get('video_id')} â€” {first_unknown.get('title','')}", "WARN")
    else:
        _yt_log("Search found no usable YouTube result", "WARN")
    return first_unknown

def _yt_resolve(qraw):
    q=_clean_sr_query(urllib.parse.unquote_plus((qraw or '').strip()))
    if not q:
        _yt_log("Resolve failed: missing query", "WARN")
        return None,'Missing YouTube query'
    _yt_log(f"Resolve request: {q}")
    vid=_yt_extract_video_id(q)
    if vid:
        _yt_log(f"Detected direct YouTube video id: {vid}")
    else:
        _yt_log("No direct video id detected, using search")
    try:
        meta=_yt_fetch_video(vid, check_embed=True) if vid else _yt_search_web(q)
    except Exception as e:
        return None,f'YouTube search failed: {e}'
    if not meta or not meta.get('video_id'):
        _yt_log("Resolve failed: no YouTube result found", "WARN")
        return None,'No YouTube result found'
    if meta.get('embed_ok') is False:
        _yt_log(f"Resolve blocked: {meta.get('video_id')} is not embeddable", "WARN")
        return None,'This YouTube video cannot be embedded/played in the local player. Try another upload or a YouTube Music/search request.'
    dur=int(meta.get('duration_sec') or 0); mx=max(0,int(YOUTUBE_MAX_DURATION_SEC or 0))
    if mx and dur and dur>mx:
        _yt_log(f"Resolve blocked by duration: {dur}s > max {mx}s", "WARN")
        return None,f'Video too long ({dur//60}:{dur%60:02d}, max {mx//60}:{mx%60:02d})'
    _yt_log(f"Resolve OK: {meta.get('video_id')} â€” {meta.get('title','')}")
    return meta,None



def _yt_music_url_from_query(raw: str) -> str:
    q = _clean_sr_query(urllib.parse.unquote_plus((raw or '').strip()))
    if not q:
        return ''
    vid = _yt_extract_video_id(q) or ''
    if vid:
        return 'https://music.youtube.com/watch?v=' + vid
    return q

def _yt_display_title_from_query(raw: str) -> str:
    q = _clean_sr_query(urllib.parse.unquote_plus((raw or '').strip()))
    if not q:
        return 'YouTube Music'
    vid = _yt_extract_video_id(q) or ''
    if vid:
        return 'YouTube ' + vid
    return q

def _handle_yt(qraw,user='someone'):
    _yt_log(f"Incoming request from @{_normalize_user(user)}: {qraw}")
    if not YOUTUBE_ENABLED:
        _yt_log("Request rejected: YouTube requests disabled", "WARN")
        return None,'YouTube requests are disabled'
    raw_query=_clean_sr_query(urllib.parse.unquote_plus((qraw or '').strip()))
    if not raw_query:
        _yt_log("Request rejected: missing YouTube query", "WARN")
        return None,'Missing YouTube query'

    mode=(YOUTUBE_PLAYER_MODE or 'ytmusic').strip().lower()
    if mode in ('ytmusic','music','youtube_music','webview'):
        # YouTube-Music mode does NOT resolve to an embed video id.
        # The request is kept as the original song/link text and the local WebView
        # controls music.youtube.com directly, which avoids iframe error 150.
        vid=_yt_extract_video_id(raw_query) or ''
        play_query = _yt_music_url_from_query(raw_query)
        item={
            "id":f"ytm#{random.randint(100000,999999)}",
            "video_id":vid,
            "query":play_query,
            "original_query":raw_query,
            "title":_yt_display_title_from_query(raw_query),
            "artist":"YouTube Music",
            "duration_sec":0,
            "url":play_query if play_query.startswith('http') else '',
            "by":_normalize_user(user),
            "requested_at":_now(),
            "status":"queued",
            "player_mode":"ytmusic",
            "source":"ytmusic"
        }
        item = _yt_attach_spotify_wait_marker(item)
        _yt_log(f"Queued for YouTube Music WebView: {raw_query} (by @{item['by']})")
    else:
        meta,err=_yt_resolve(qraw)
        if err:
            _yt_log(f"Request failed for @{_normalize_user(user)}: {err}", "WARN")
            return None,err
        item={"id":f"yt#{random.randint(100000,999999)}","video_id":meta['video_id'],"query":raw_query,"title":meta.get('title') or meta['video_id'],"artist":meta.get('artist') or 'YouTube',"duration_sec":int(meta.get('duration_sec') or 0),"url":meta.get('url') or f"https://www.youtube.com/watch?v={meta['video_id']}","by":_normalize_user(user),"requested_at":_now(),"status":"queued","player_mode":"iframe","source":"youtube"}
        item = _yt_attach_spotify_wait_marker(item)
    with _YT_QUEUE_LOCK:
        _yt_load(); _YT_QUEUE.append(item); del _YT_QUEUE[:-100]; _yt_save()
    _yt_log(f"Queued: {item['artist']} â€” {item['title']} (by @{item['by']}); queue_len={len(_YT_QUEUE)}")
    logi(f"YouTube queued: {item['artist']} â€” {item['title']} (by @{item['by']})")
    r={"ok":True,"queued":True}; r.update(_yt_public(item)); return r,None

def _yt_state(pop_next=False):
    global _YT_CURRENT
    with _YT_QUEUE_LOCK:
        _yt_load()
        if pop_next and _YT_QUEUE:
            next_item = _YT_QUEUE[0] if _YT_QUEUE else None
            if not _yt_can_start_item_now(next_item) and not _YT_CURRENT:
                return {"ok":True,"enabled":YOUTUBE_ENABLED,"autoplay":YOUTUBE_AUTOPLAY,"command":TWITCH_CMD_YT,"player_mode":YOUTUBE_PLAYER_MODE,"can_start":False,"wait_for_spotify":True,"spotify_remaining_ms":_yt_spotify_remaining_ms(),"current":_yt_public(_YT_CURRENT),"queue":[_yt_public(x) for x in _YT_QUEUE],"history":[_yt_public(x) for x in _YT_HISTORY[-10:]],"control":dict(_YT_CONTROL)}
            if _YT_CURRENT:
                old=dict(_YT_CURRENT); old['status']='played'; _YT_HISTORY.append(old); del _YT_HISTORY[:-30]
                _yt_log(f"Marked played: {old.get('title','')} ({old.get('video_id','')})")
            _spotify_pause_for_youtube()
            _YT_CURRENT=_YT_QUEUE.pop(0); _YT_CURRENT['status']='playing'; _yt_save()
            _yt_log(f"Now playing: {_YT_CURRENT.get('artist','YouTube')} â€” {_YT_CURRENT.get('title','')} ({_YT_CURRENT.get('video_id','')}); queue_len={len(_YT_QUEUE)}")
            try:
                _set_youtube_nowplaying(_YT_CURRENT)
            except Exception:
                pass
        next_item = _YT_QUEUE[0] if _YT_QUEUE else None
        can_start = _yt_can_start_item_now(next_item)
        return {"ok":True,"enabled":YOUTUBE_ENABLED,"autoplay":YOUTUBE_AUTOPLAY,"command":TWITCH_CMD_YT,"player_mode":YOUTUBE_PLAYER_MODE,"can_start":can_start,"wait_for_spotify":(not can_start and bool(_YT_QUEUE) and not _YT_CURRENT),"spotify_remaining_ms":_yt_spotify_remaining_ms(),"current":_yt_public(_YT_CURRENT),"queue":[_yt_public(x) for x in _YT_QUEUE],"history":[_yt_public(x) for x in _YT_HISTORY[-10:]],"control":dict(_YT_CONTROL)}

def _yt_finished():
    global _YT_CURRENT
    should_resume = False
    with _YT_QUEUE_LOCK:
        _yt_load()
        if _YT_CURRENT:
            old=dict(_YT_CURRENT); old['status']='played'; _YT_HISTORY.append(old); del _YT_HISTORY[:-30]
            _yt_log(f"Finished: {old.get('title','')} ({old.get('video_id','')})")
        _YT_CURRENT=None
        should_resume = not bool(_YT_QUEUE)
        _yt_save()
    if should_resume:
        _spotify_resume_after_youtube(force=True)
    return _yt_state(False)

def _yt_skip():
    global _YT_CURRENT
    should_resume = False
    with _YT_QUEUE_LOCK:
        _yt_load()
        if _YT_CURRENT:
            old=dict(_YT_CURRENT); old['status']='skipped'; _YT_HISTORY.append(old); del _YT_HISTORY[:-30]
            _yt_log(f"Skipped: {old.get('title','')} ({old.get('video_id','')})")
        else:
            _yt_log("Skip requested, but no current video")
        _YT_CURRENT=None
        should_resume = not bool(_YT_QUEUE)
        _YT_CONTROL['skip_seq']=int(_YT_CONTROL.get('skip_seq') or 0)+1
        _yt_save()
    if should_resume:
        _spotify_resume_after_youtube(force=True)
    return _yt_state(False)

def _yt_clear():
    global _YT_CURRENT
    with _YT_QUEUE_LOCK:
        old_len=len(_YT_QUEUE); had_current=bool(_YT_CURRENT)
        _YT_QUEUE.clear(); _YT_CURRENT=None; _YT_CONTROL['clear_seq']=int(_YT_CONTROL.get('clear_seq') or 0)+1; _yt_save(); _yt_log(f"Queue cleared: removed {old_len} queued item(s), had_current={had_current}"); _spotify_resume_after_youtube(force=True); return _yt_state(False)

def _yt_player_html():
    return r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>spotis3mptify YouTube Player</title><script src="https://www.youtube.com/iframe_api"></script><style>body{margin:0;background:#06070c;color:#fff;font-family:Segoe UI,Arial,sans-serif;overflow:hidden}#wrap{position:fixed;inset:0;display:grid;grid-template-rows:1fr auto;background:radial-gradient(circle at 18% 8%,#2b1759 0,#090a12 42%,#050507 100%)}#player{width:100%;height:100%}.bar{padding:14px 18px;background:rgba(0,0,0,.55);backdrop-filter:blur(14px);display:flex;gap:14px;align-items:center;border-top:1px solid rgba(255,255,255,.1)}.pill{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.15);border-radius:999px;padding:7px 11px;font-size:12px;white-space:nowrap}.meta{min-width:0;flex:1}.title{font-size:18px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sub{font-size:12px;color:#b8bad0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.notice{position:fixed;left:24px;top:24px;max-width:520px;padding:14px 16px;border-radius:18px;background:rgba(0,0,0,.68);border:1px solid rgba(255,255,255,.16);box-shadow:0 18px 60px rgba(0,0,0,.35);display:none}.notice b{display:block;margin-bottom:4px}button{background:#8b5cf6;color:white;border:0;border-radius:13px;padding:10px 14px;font-weight:800;cursor:pointer}button:hover{filter:brightness(1.08)}</style></head><body><div id="wrap"><div id="player"></div><div class="notice" id="notice"><b>Video nicht im Player verfÃ¼gbar</b><span id="noticeText">Ich Ã¼berspringe automatisch zum nÃ¤chsten Request.</span></div><div class="bar"><span class="pill" id="count">Queue: 0</span><div class="meta"><div class="title" id="title">Warte auf !yt â€¦</div><div class="sub" id="sub">Browser Source offen lassen.</div></div><button onclick="skip()">Skip</button><button onclick="clearQ()">Clear</button></div></div><script>let player=null,playingId='',lastSkip=0,lastClear=0,lastErrorFor='';async function ytlog(message,level){try{await fetch('/yt/log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,level:level||'INFO'})})}catch(e){}}function onYouTubeIframeAPIReady(){ytlog('IFrame API ready, creating player');player=new YT.Player('player',{height:'100%',width:'100%',playerVars:{autoplay:1,controls:1,rel:0,modestbranding:1,origin:location.origin,playsinline:1},events:{onReady:e=>{ytlog('Player ready');tick()},onStateChange:e=>{ytlog('Player state changed: '+e.data);if(e.data===YT.PlayerState.ENDED)next(true)},onError:onPlayerError}})}async function api(p,o){let r=await fetch(p,o||{});return await r.json()}function showNotice(msg){let n=document.getElementById('notice'),t=document.getElementById('noticeText');t.textContent=msg||'Ich Ã¼berspringe automatisch zum nÃ¤chsten Request.';n.style.display='block';setTimeout(()=>{n.style.display='none'},5500)}async function onPlayerError(e){let code=e&&e.data;let id=playingId;if(id&&id!==lastErrorFor){lastErrorFor=id;ytlog('Player error code '+code+' for '+id,'WARN');showNotice('YouTube blockt dieses Video im eingebetteten Player (Code '+code+'). Ich nehme den nÃ¤chsten Song.');await api('/yt/skip',{method:'POST'});setTimeout(()=>next(true),700)}}async function next(pop){apply(await api('/yt/next?pop='+(pop?'1':'0')))}function apply(s){document.getElementById('count').textContent='Queue: '+((s.queue||[]).length);let c=s.current;if(c){document.getElementById('title').textContent=c.title||c.video_id;document.getElementById('sub').textContent=(c.artist||'YouTube')+' Â· requested by '+(c.by||'someone');if((c.player_mode||'iframe')==='ytmusic'){if(player)player.stopVideo();playingId='';document.getElementById('sub').textContent='Wird von der YouTube Music App/WebView abgespielt.';}else if(player&&c.video_id&&c.video_id!==playingId){playingId=c.video_id;lastErrorFor='';ytlog('Loading video '+c.video_id+' â€” '+(c.title||''));player.loadVideoById(c.video_id)}}else{document.getElementById('title').textContent='Warte auf !yt â€¦';document.getElementById('sub').textContent='Queue leer';playingId='';lastErrorFor=''}if(s.control){if(s.control.skip_seq!==lastSkip){lastSkip=s.control.skip_seq;next(true)}if(s.control.clear_seq!==lastClear){lastClear=s.control.clear_seq;if(player)player.stopVideo();playingId='';lastErrorFor=''}}}async function tick(){try{let s=await api('/yt/state');let q=s.queue||[];if(!s.current&&q.length){let first=q[0]||{};if((first.player_mode||'iframe')==='ytmusic'){document.getElementById('count').textContent='Queue: '+q.length;document.getElementById('title').textContent='YouTube Music WebView wartet';document.getElementById('sub').textContent='Diese Queue wird von der YouTube Music App abgespielt, nicht vom IFrame-Fallback.';}else await next(true);}else apply(s)}catch(e){}setTimeout(tick,1500)}async function skip(){await api('/yt/skip',{method:'POST'});await next(true)}async function clearQ(){await api('/yt/clear',{method:'POST'});if(player)player.stopVideo();playingId='';lastErrorFor=''}</script></body></html>'''

# ======================= EXTERNAL SR FILE WATCHER =======================
_EXTERNAL_SR_THREAD: Optional[threading.Thread] = None
_EXTERNAL_SR_STOP = threading.Event()
_EXTERNAL_SR_OFFSET = 0
_EXTERNAL_SR_BOOTSTRAP_LINES = 25

def _sr_source_is_external():
    return (SR_SOURCE or "").strip().lower() == "external_file"

def _normalize_external_sr_file(path: str) -> str:
    p = (path or "").strip()
    if not p:
        p = EXTERNAL_SR_FILE_DEFAULT
    p = os.path.expandvars(os.path.expanduser(p))
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(APP_DIR, p))
    return p

def _parse_external_sr_line(line: str):
    raw = _clean_sr_query(line)
    if not raw:
        return None, None, None

    user = "someone"
    text = raw

    # Support both the old plain format and newer JSON/JSONL export formats.
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            user = _normalize_user(obj.get("user") or obj.get("username") or obj.get("display_name") or obj.get("author") or obj.get("name") or "someone")
            text = str(obj.get("message") or obj.get("text") or obj.get("body") or obj.get("content") or obj.get("raw") or "").strip()
    except Exception:
        m = re.match(r"^(?:\[[^\]]+\]\s*)?([^:]+):\s*(.+)$", raw)
        if m:
            user = _normalize_user(m.group(1) or "someone")
            text = (m.group(2) or "").strip()
        else:
            # Some bridges write the whole chat line without a clean colon. Keep it usable.
            text = raw

    if not text:
        return None, None, None

    yt_cmd = (TWITCH_CMD_YT or "!yt").strip() or "!yt"
    sr_cmd = (TWITCH_CMD_SR or "!sr").strip() or "!sr"
    low = text.lower()

    def _extract_command_query(cmd: str):
        cmd_l = (cmd or "").lower()
        if not cmd_l:
            return ""
        # Prefer command at message start, but also accept exported lines where platform/user prefixes survived.
        idx = low.find(cmd_l)
        if idx < 0:
            return ""
        before = low[:idx].strip()
        if before and not (before.endswith(":") or before.endswith("]") or " " in before or before.startswith("[")):
            return ""
        return _clean_sr_query(text[idx + len(cmd):].strip())

    q = _extract_command_query(yt_cmd)
    if YOUTUBE_ENABLED and q:
        return "yt", user, q

    q = _extract_command_query(sr_cmd)
    if q:
        return "sr", user, q

    return None, None, None

def _read_external_sr_bootstrap_lines(path: str, max_lines: int = _EXTERNAL_SR_BOOTSTRAP_LINES):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        if max_lines <= 0:
            return lines
        return lines[-max_lines:]
    except Exception as e:
        _log_throttled("WARN", "external_sr_bootstrap_read_err", f"external SR bootstrap read failed: {e}", 10)
        return []

def _process_external_sr_line(line: str):
    kind, user, q = _parse_external_sr_line(line)
    if not q: return
    try:
        if kind == "yt":
            result, err = _handle_yt(q, user)
            if err: logw(f"external YT failed for {user}: {err}")
            else: logi(f"external YT queued: {result['title']} (by @{user})")
            return
        result, err = _handle_sr(q, user)
        if err:
            if err.startswith("RATELIMIT:"):
                retry = int(err.split(":",1)[1]); logi(f"external SR ratelimited for {user}: retry in {retry}s")
            else: logw(f"external SR failed for {user}: {err}")
            return
        if result.get("playing_now"): logi(f"external SR playing now: {result['artist']} â€” {result['title']} (by @{user})")
        else: logi(f"external SR queued: {result['artist']} â€” {result['title']} (by @{user})")
    except Exception as e:
        logw(f"external request exception for {user}: {e}")


def _external_sr_candidate_files():
    """Return all plausible songrequests.txt files.
    The configured path stays first. Extra candidates make godisalotachat ->
    Spotis3mptify work even when both apps live in sibling dist folders.
    """
    candidates=[]
    def add(x):
        try:
            if not x: return
            x=_normalize_external_sr_file(str(x))
            if x not in candidates:
                candidates.append(x)
        except Exception:
            pass
    add(EXTERNAL_SR_FILE)
    add(EXTERNAL_SR_FILE_DEFAULT)
    try:
        from pathlib import Path as _Path
        app=_Path(APP_DIR).resolve()
        parent=app.parent
        # Current godisalotachat layout only: <app>/data/spotis3mptify/export/songrequests.txt.
        # Old legacy export folders are intentionally not created or watched anymore.
        for base in (app, parent, parent.parent):
            for name in ("godisalotachat", "godischatalot", "godisalotachatstable"):
                add(base / name / "data" / "spotis3mptify" / "export" / "songrequests.txt")
    except Exception:
        pass
    return candidates

def _external_sr_loop():
    global _EXTERNAL_SR_OFFSET
    offsets = {}
    logged = set()
    logi("external SR watcher active")
    while not _EXTERNAL_SR_STOP.is_set():
        try:
            paths = _external_sr_candidate_files()
            any_found = False
            for path in paths:
                if _EXTERNAL_SR_STOP.is_set():
                    break
                try:
                    if not os.path.exists(path):
                        continue
                    any_found = True
                    if path not in logged:
                        logged.add(path)
                        logi(f"external SR watcher file: {path}")
                    size = os.path.getsize(path)
                    off = int(offsets.get(path, 0) or 0)
                    if off == 0:
                        bootstrap_lines = _read_external_sr_bootstrap_lines(path, _EXTERNAL_SR_BOOTSTRAP_LINES)
                        if bootstrap_lines:
                            logi(f"external SR bootstrap from {os.path.basename(path)}: checking last {len(bootstrap_lines)} line(s)")
                            for line in bootstrap_lines:
                                if _EXTERNAL_SR_STOP.is_set():
                                    break
                                _process_external_sr_line(line)
                        offsets[path] = size
                        continue
                    if size < off:
                        offsets[path] = 0
                        continue
                    if size == off:
                        continue
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(off)
                        new_lines = f.readlines()
                        offsets[path] = f.tell()
                    for line in new_lines:
                        if _EXTERNAL_SR_STOP.is_set():
                            break
                        _process_external_sr_line(line)
                except Exception as inner:
                    _log_throttled("WARN", "external_sr_file_loop_err_"+str(abs(hash(path))), f"external SR watcher file {path}: {inner}", 10)
            if not any_found:
                _log_throttled("INFO", "external_sr_waiting_files", "external SR watcher waiting for songrequests.txt", 15)
            time.sleep(0.35)
        except Exception as e:
            _log_throttled("WARN", "external_sr_loop_err", f"external SR watcher: {e}", 10)
            time.sleep(0.75)

def _restart_external_sr_thread_if_needed(force=False):
    global _EXTERNAL_SR_THREAD, _EXTERNAL_SR_OFFSET
    need = _sr_source_is_external()
    running = bool(_EXTERNAL_SR_THREAD and _EXTERNAL_SR_THREAD.is_alive())
    if running and (force or not need):
        _EXTERNAL_SR_STOP.set()
        try:
            _EXTERNAL_SR_THREAD.join(timeout=2.0)
        except Exception:
            pass
        _EXTERNAL_SR_THREAD = None
        _EXTERNAL_SR_STOP.clear()
        _EXTERNAL_SR_OFFSET = 0
        running = False
    if need and (force or not running):
        _EXTERNAL_SR_STOP.clear()
        _EXTERNAL_SR_OFFSET = 0
        _EXTERNAL_SR_THREAD = threading.Thread(target=_external_sr_loop, daemon=True)
        _EXTERNAL_SR_THREAD.start()

# ======================= TWITCH OAuth & IRC =======================
def _read_twitch_tokens(which="main"):
    return _load_json(_p_twitch_main() if which=="main" else _p_twitch_bot(), {"access_token": None, "refresh_token": None, "expires_at": 0})
def _write_twitch_tokens(tok, which="main"):
    _save_json(_p_twitch_main() if which=="main" else _p_twitch_bot(), tok)
def _twitch_is_authorized(which="main"):
    t = _read_twitch_tokens(which)
    return bool(t.get("refresh_token") or t.get("access_token"))

def _twitch_redirect_uri(which="main"):
    return ""

def _twitch_client_info(which="main"):
    if which == "bot":
        return (TWITCH_BOT_CLIENT_ID, TWITCH_BOT_CLIENT_SECRET, TWITCH_BOT_SCOPES)
    return (TWITCH_MAIN_CLIENT_ID, TWITCH_MAIN_CLIENT_SECRET, TWITCH_MAIN_SCOPES)

def _twitch_ensure_access_token(which="main"):
    tok = _read_twitch_tokens(which)
    if tok.get("access_token") and (tok.get("expires_at", 0) - 30) > _now():
        return tok["access_token"]
    if not tok.get("refresh_token"):
        raise RuntimeError("Twitch is not authorized in the core Platforms page.")
    cid, csec, _sc = _twitch_client_info(which)
    data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": cid, "client_secret": csec}).encode("utf-8")
    req = urllib.request.Request("https://id.twitch.tv/oauth2/token", data=data, method="POST")
    req.add_header("Content-Type","application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    tok["access_token"] = r["access_token"]
    if "refresh_token" in r: tok["refresh_token"] = r["refresh_token"]
    tok["expires_at"] = _now() + int(r.get("expires_in", 3600))
    _write_twitch_tokens(tok, which)
    return tok["access_token"]

def _twitch_get_login_from_token(token):
    try:
        req = urllib.request.Request("https://id.twitch.tv/oauth2/validate", method="GET")
        req.add_header("Authorization", f"OAuth {token}")
        with urllib.request.urlopen(req, timeout=8) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        return (r.get("login") or "").strip().lower()
    except Exception:
        return ""

class _TwitchIRC(threading.Thread):
    def __init__(self, channel, token, nick_login, label):
        super().__init__(daemon=True)
        self.channel = (channel or "").strip().lstrip("#").lower()
        self.nick = (nick_login or "").strip().lower()
        self.token = token  # raw token w/o "oauth:" prefix
        self._stop = threading.Event()
        self.sock = None
        self.label = label  # "main"/"bot"
    def stop(self):
        self._stop.set()
        try:
            if self.sock:
                try: self.sock.shutdown(socket.SHUT_RDWR)
                except: pass
                self.sock.close()
        except: pass
        self.sock = None
    def send(self, line):
        try:
            if self.sock:
                self.sock.sendall((line + "\r\n").encode("utf-8"))
        except: pass
    def _reply(self, msg):
        if not TWITCH_REPLY: return
        out = f"{msg}{TWITCH_REPLY_SUFFIX}"
        self.send(f"PRIVMSG #{self.channel} :{out}")
    def run(self):
        try:
            raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=10)
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
            self.send(f"PASS oauth:{self.token}")
            self.send(f"NICK {self.nick}")
            self.send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership")
            self.send(f"JOIN #{self.channel}")
            _irc_debug_push(f">>> CONNECTED ({self.label}) nick={self.nick} join=#{self.channel}")
            buf = b""; last_ping = _now()
            while not self._stop.is_set():
                try:
                    if not self.sock: break
                    r,_,_ = select.select([self.sock], [], [], 0.5)
                except OSError: break
                if r:
                    try: chunk = self.sock.recv(4096)
                    except OSError: break
                    if not chunk: break
                    buf += chunk
                    while b"\r\n" in buf:
                        line, buf = buf.split(b"\r\n", 1)
                        txt = line.decode("utf-8", "ignore")
                        _irc_debug_push(f"[{self.label}] {txt}")
                        self._handle_line(txt)
                if _now() - last_ping > 240:
                    self.send("PING :keepalive"); last_ping = _now()
        except Exception as e:
            _irc_debug_push(f"!! IRC({self.label}) ERROR: {e}")
            _log_throttled("WARN", f"twitch_loop_err_{self.label}", f"twitch({self.label}) loop: {e}", 60)
    def _handle_line(self, line):
        if line.startswith("PING"):
            self.send("PONG :tmi.twitch.tv"); return
        if " PRIVMSG #" in line:
            try:
                tags_part = ""; rest = line
                if rest.startswith("@"): tags_part, rest = rest.split(" ", 1)
                msg_text = rest.split(" :", 1)[1] if " :" in rest else ""
                msg_text = msg_text.strip()
                display = ""
                if tags_part:
                    for kv in tags_part[1:].split(";"):
                        if kv.startswith("display-name="):
                            display = urllib.parse.unquote(kv.split("=",1)[1] or "")
                            break
                user = display or "someone"
                is_sub = False; is_mod = False
                if tags_part:
                    for kv in tags_part[1:].split(";"):
                        if kv.startswith("subscriber="): is_sub = (kv.split("=",1)[1] == "1")
                        elif kv.startswith("mod="): is_mod = (kv.split("=",1)[1] == "1")
                        elif kv.startswith("badges="):
                            badges = kv.split("=",1)[1] or ""
                            if "broadcaster" in badges or "moderator" in badges: is_mod = True
                self._handle_chat_message(user, msg_text, is_sub, is_mod)
            except Exception as e:
                _log_throttled("WARN", "twitch_parse_err", f"twitch parse: {e}", 30)
    def _handle_chat_message(self, user, text, is_subscriber=False, is_moderator=False):
        if TWITCH_REPLY_SENDER != self.label: return
        low = text.strip()
        if not low: return
        if _sr_source_is_external():
            return
        if TWITCH_CMD_SRPLUS and low.lower().startswith(TWITCH_CMD_SRPLUS.lower()):
            if SRPLUS_SUBSCRIBERS_ONLY and not is_subscriber and not is_moderator:
                self._reply(f"@{user} SR+ is only available for subscribers."); return
            try:
                at = _ensure_access_token()
                r = _start_takeover(at, user)
                if r.get("ok"):
                    if r.get("pending"): self._reply(f"@{user} takeover queued, starting after current track.")
                    else:                self._reply(f"@{user} takeover started.")
                else:
                    self._reply(f"SR+ unavailable: {r.get('error','')}")
            except Exception:
                self._reply("SR+ failed.")
            return
        if YOUTUBE_ENABLED and TWITCH_CMD_YT and low.lower().startswith(TWITCH_CMD_YT.lower()):
            q = text[len(TWITCH_CMD_YT):].strip()
            if not q:
                self._reply("Usage: " + TWITCH_CMD_YT + " <YouTube link or search>"); return
            try:
                result, err = _handle_yt(q, user)
                if err:
                    self._reply("YouTube request failed: " + err); return
                self._reply(f"Queued YouTube: {result['title']} (by @{user})")
            except Exception:
                self._reply("YouTube request failed.")
            return

        if TWITCH_CMD_SR and low.lower().startswith(TWITCH_CMD_SR.lower()):
            q = text[len(TWITCH_CMD_SR):].strip()
            if not q:
                self._reply("Usage: " + TWITCH_CMD_SR + " <search or Spotify link>"); return
            try:
                result, err = _handle_sr(q, user)
                if err:
                    if err.startswith("RATELIMIT:"):
                        retry = int(err.split(":",1)[1]); self._reply(f"@{user} {_format_sr_cooldown_message(retry)}")
                    else:
                        self._reply("Request failed: " + err)
                    return
                if result.get("playing_now"):
                    self._reply(f"â–¶ {result['artist']} â€” {result['title']} (by @{user})")
                else:
                    self._reply(f"Queued: {result['artist']} â€” {result['title']} (by @{user})")
            except Exception:
                self._reply("SR failed.")

# IRC debug ringbuffer
_IRC_DEBUG_LAST = []
def _irc_debug_push(line):
    try:
        if not line: return
        s = str(line)
        _IRC_DEBUG_LAST.append(s[:500])
        if len(_IRC_DEBUG_LAST) > 100:
            del _IRC_DEBUG_LAST[:len(_IRC_DEBUG_LAST)-100]
    except: pass

_TWITCH_THREAD: Optional[_TwitchIRC] = None
_TWITCH_LAST_ACC = None   # "main"|"bot"|None

def _restart_twitch_thread_if_needed(force=False):
    global _TWITCH_THREAD, _TWITCH_LAST_ACC
    channel = TWITCH_CHANNEL if TWITCH_REPLY_SENDER == "main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)
    need = TWITCH_LISTEN and not _sr_source_is_external() and bool(channel)
    running = bool(_TWITCH_THREAD and _TWITCH_THREAD.is_alive())
    desired = TWITCH_REPLY_SENDER if need else None

    if running and (force or (desired != _TWITCH_LAST_ACC) or not need):
        try: _TWITCH_THREAD.stop()
        except: pass
        _TWITCH_THREAD = None
        _TWITCH_LAST_ACC = None
        _log_throttled("INFO","twitch_stop","twitch listener stopped",5)

    if need and (_TWITCH_THREAD is None):
        try:
            if TWITCH_REPLY_SENDER == "main":
                tok_override = (TWITCH_MAIN_TOKEN_OVERRIDE or "").strip()
                login_override = (TWITCH_MAIN_LOGIN_OVERRIDE or "").strip().lower()
            else:
                tok_override = (TWITCH_BOT_TOKEN_OVERRIDE or "").strip()
                login_override = (TWITCH_BOT_LOGIN_OVERRIDE or "").strip().lower()

            if tok_override:
                token = tok_override
            else:
                token = _twitch_ensure_access_token(TWITCH_REPLY_SENDER)

            nick = login_override or _twitch_get_login_from_token(token) or (channel.strip().lstrip("#").lower())
            if token.lower().startswith("oauth:"):
                token = token.split(":",1)[1]

            thr = _TwitchIRC(channel, token, nick, TWITCH_REPLY_SENDER)
            _TWITCH_THREAD = thr; _TWITCH_LAST_ACC = TWITCH_REPLY_SENDER
            thr.start()
            _log_throttled("INFO","twitch_start",f"twitch listener started for #{channel} ({TWITCH_REPLY_SENDER})",2)
        except Exception as e:
            _TWITCH_THREAD = None; _TWITCH_LAST_ACC = None
            _log_throttled("WARN","twitch_start_err",f"twitch start failed: {e}",5)

_LOCAL_CA_CERT = os.path.join(CERTS_DIR, "spotis3mptify_local_root_ca.crt")
_LOCAL_CA_KEY  = os.path.join(CERTS_DIR, "spotis3mptify_local_root_ca.key")
_LOCAL_TLS_CERT = os.path.join(CERTS_DIR, "localhost_https_cert.pem")
_LOCAL_TLS_KEY  = os.path.join(CERTS_DIR, "localhost_https_key.pem")
_CERT_RENEW_DAYS = 30


def _cert_not_after(cert_path: str):
    try:
        from cryptography import x509
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        return cert.not_valid_after
    except Exception:
        return None


def _cert_valid_for(cert_path: str, min_days: int = _CERT_RENEW_DAYS) -> bool:
    try:
        import datetime
        not_after = _cert_not_after(cert_path)
        if not not_after:
            return False
        return not_after > (datetime.datetime.utcnow() + datetime.timedelta(days=min_days))
    except Exception:
        return False


def _load_or_create_local_ca():
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        _ensure_dir(CERTS_DIR)
        if os.path.exists(_LOCAL_CA_CERT) and os.path.exists(_LOCAL_CA_KEY) and _cert_valid_for(_LOCAL_CA_CERT, 180):
            with open(_LOCAL_CA_KEY, "rb") as f:
                ca_key = serialization.load_pem_private_key(f.read(), password=None)
            with open(_LOCAL_CA_CERT, "rb") as f:
                ca_cert = x509.load_pem_x509_certificate(f.read())
            return ca_key, ca_cert

        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "spotis3mptify local trusted root"),
            x509.NameAttribute(NameOID.COMMON_NAME, "spotis3mptify Local Root CA"),
        ])
        ca_cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                key_cert_sign=True,
                key_agreement=False,
                content_commitment=False,
                data_encipherment=False,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ), critical=True)
            .sign(ca_key, hashes.SHA256()))

        with open(_LOCAL_CA_KEY, "wb") as f:
            f.write(ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(_LOCAL_CA_CERT, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
        return ca_key, ca_cert
    except Exception as e:
        logw(f"Local CA setup failed: {e}")
        return None, None


def _localhost_cert_matches_ca(cert_path: str, ca_cert) -> bool:
    """Return True only for our current CA-signed localhost/127.0.0.1 server cert.

    Older spotis3mptify builds created a plain self-signed server certificate.
    That file can still be valid by date, but Chrome will always show
    NET::ERR_CERT_AUTHORITY_INVALID for it. So expiry alone is not enough.
    """
    try:
        from cryptography import x509
        import ipaddress
        if not os.path.exists(cert_path):
            return False
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        if cert.issuer != ca_cert.subject:
            return False
        if not _cert_valid_for(cert_path, _CERT_RENEW_DAYS):
            return False
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            dns_names = set(san.get_values_for_type(x509.DNSName))
            ip_names = set(str(x) for x in san.get_values_for_type(x509.IPAddress))
            return ("localhost" in dns_names and "127.0.0.1" in ip_names)
        except Exception:
            return False
    except Exception:
        return False


def _remove_stale_localhost_cert():
    for path in (_LOCAL_TLS_CERT, _LOCAL_TLS_KEY):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _ensure_localhost_cert(force_renew: bool = False) -> Optional[Tuple[str, str]]:
    try:
        _ensure_dir(DATA_DIR)
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime, ipaddress
        except Exception as e:
            logw(f"HTTPS disabled: cryptography missing ({e})")
            return None

        ca_key, ca_cert = _load_or_create_local_ca()
        if not ca_key or not ca_cert:
            return None

        if (not force_renew
            and os.path.exists(_LOCAL_TLS_CERT)
            and os.path.exists(_LOCAL_TLS_KEY)
            and _localhost_cert_matches_ca(_LOCAL_TLS_CERT, ca_cert)):
            return _LOCAL_TLS_CERT, _LOCAL_TLS_KEY

        # Important: remove old self-signed/foreign certs from earlier builds.
        _remove_stale_localhost_cert()

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "spotis3mptify local"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=False,
                key_agreement=False,
                content_commitment=False,
                data_encipherment=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("spotis3mptify.local"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.IPAddress(ipaddress.ip_address("::1")),
            ]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        with open(_LOCAL_TLS_KEY, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(_LOCAL_TLS_CERT, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        logi("local HTTPS certificate created/renewed with trusted local CA issuer")
        return _LOCAL_TLS_CERT, _LOCAL_TLS_KEY
    except Exception as e:
        logw(f"HTTPS cert setup failed: {e}")
        return None


def install_local_https_root_ca() -> Dict[str, Any]:
    """Install the local Root CA into the current Windows user's trusted Root store."""
    try:
        ca_key, ca_cert = _load_or_create_local_ca()
        _ensure_localhost_cert(force_renew=True)
        if not ca_cert or not os.path.exists(_LOCAL_CA_CERT):
            return {"ok": False, "error": "Local CA could not be created."}
        if os.name != "nt":
            return {"ok": False, "error": "Automatic certificate install is only implemented for Windows.", "cert": _LOCAL_CA_CERT}
        cmd = ["certutil", "-user", "-addstore", "-f", "Root", _LOCAL_CA_CERT]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            logi("local HTTPS Root CA installed into Current User Root store")
            return {"ok": True, "cert": _LOCAL_CA_CERT, "message": "Installed into Current User Root store and renewed the HTTPS server certificate. Fully close Chrome/Meld and restart the spotis3mptify server."}
        return {"ok": False, "cert": _LOCAL_CA_CERT, "error": out.strip() or f"certutil failed with code {proc.returncode}"}
    except Exception as e:
        return {"ok": False, "cert": _LOCAL_CA_CERT, "error": str(e)}


def get_local_https_cert_info() -> Dict[str, Any]:
    _ensure_localhost_cert()
    not_after = _cert_not_after(_LOCAL_TLS_CERT)
    ca_not_after = _cert_not_after(_LOCAL_CA_CERT)
    return {
        "ok": bool(os.path.exists(_LOCAL_TLS_CERT) and os.path.exists(_LOCAL_TLS_KEY)),
        "https_port": _https_port(),
        "cert": _LOCAL_TLS_CERT,
        "key": _LOCAL_TLS_KEY,
        "root_ca": _LOCAL_CA_CERT,
        "cert_not_after": str(not_after) if not_after else "",
        "root_ca_not_after": str(ca_not_after) if ca_not_after else "",
    }


def _https_port() -> int:
    try:
        return int(PORT) + 1
    except Exception:
        return 5174


# ======================= CUSTOM OVERLAY =======================
def _custom_overlay_default_state() -> Dict[str, Any]:
    return {
        "version": 3,
        "canvas": {"width": 900, "height": 360, "transparent": True, "marqueeMode": "bounce", "marqueeSpeed": 45},
        "colors": {"spotify": "#1DB954", "youtube": "#FF0033"},
        "elements": [
            {"id":"line_up","type":"line","label":"Line Up","x":110,"y":66,"w":680,"h":10,"radius":8,"opacity":1,"bind":"providerColor","color":"#1DB954","z":1,"effect":"fade"},
            {"id":"cover","type":"cover","label":"Cover","x":115,"y":92,"w":176,"h":176,"radius":88,"opacity":1,"shape":"circle","rotate":True,"rotationSpeed":18,"effect":"pop","z":2},
            {"id":"artist","type":"text","label":"Artist","bind":"artist","x":320,"y":106,"w":540,"h":76,"font":"Nuishock, Nulshock, SquareLocal, Arial, sans-serif","fontSize":55,"bold":True,"color":"#FFFFFF","opacity":1,"align":"left","effect":"glitch","z":3,"marqueeMode":"global","marqueeSpeed":45},
            {"id":"song","type":"text","label":"Song","bind":"song","x":322,"y":186,"w":540,"h":64,"font":"Nuishock, Nulshock, SquareLocal, Arial, sans-serif","fontSize":42,"bold":False,"color":"#FFFFFF","opacity":1,"align":"left","effect":"fade","z":4,"marqueeMode":"global","marqueeSpeed":45},
            {"id":"line_down","type":"line","label":"Line Down","x":110,"y":284,"w":680,"h":10,"radius":8,"opacity":1,"bind":"providerColor","color":"#1DB954","z":5,"effect":"fade"}
        ]
    }

def _upgrade_custom_overlay_state(st: Dict[str, Any]) -> Dict[str, Any]:
    """Bring older saved overlay layouts to the current readable default.

    Version 3 only touches the standard element IDs from the shipped layout:
    text is 30% larger and the upper green line uses the same cover gap as
    the lower line. Custom extra elements are left alone.
    """
    try:
        version = int(st.get("version") or 0)
    except Exception:
        version = 0
    if version >= 3:
        return st

    updates = {
        "line_up": {"y": 66, "h": 10, "w": 680},
        "artist": {"x": 320, "y": 106, "w": 540, "h": 76, "fontSize": 55},
        "song": {"x": 322, "y": 186, "w": 540, "h": 64, "fontSize": 42},
        "line_down": {"y": 284, "h": 10, "w": 680},
    }
    elements = st.get("elements")
    if isinstance(elements, list):
        for el in elements:
            if isinstance(el, dict):
                patch = updates.get(str(el.get("id") or ""))
                if patch:
                    el.update(patch)
    st["version"] = 3
    return st

def _load_custom_overlay_state() -> Dict[str, Any]:
    try:
        st = _load_json(CUSTOM_OVERLAY_JSON, None)
        if isinstance(st, dict) and isinstance(st.get("elements"), list):
            base = _custom_overlay_default_state()
            base.update(st)
            if not isinstance(base.get("colors"), dict):
                base["colors"] = {"spotify":"#1DB954", "youtube":"#FF0033"}
            return _upgrade_custom_overlay_state(base)
    except Exception:
        pass
    return _custom_overlay_default_state()

def _save_custom_overlay_state(st: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(st, dict):
        raise ValueError("invalid custom overlay state")
    if not isinstance(st.get("elements"), list):
        raise ValueError("custom overlay state needs elements[]")
    _ensure_dir(DATA_DIR)
    _save_json(CUSTOM_OVERLAY_JSON, st)
    return {"ok": True, "path": CUSTOM_OVERLAY_JSON}

def _custom_overlay_html() -> str:
    initial_state = json.dumps(_load_custom_overlay_state(), ensure_ascii=False)
    html = r"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>spotis3mptify Custom Overlay</title>
<style>
@font-face{font-family:SquareLocal;src:url('/font/square')} @font-face{font-family:RobotHeroes;src:url('/font/robot-heroes')}
*{box-sizing:border-box} html,body{margin:0;width:100%;height:100%;background:transparent!important;overflow:hidden;font-family:Inter,Segoe UI,Arial,sans-serif;color:white}#stageWrap{position:relative;width:100vw;height:100vh;background:transparent;overflow:hidden;user-select:none}#stage{position:absolute;left:0;top:0;width:900px;height:360px;transform-origin:left top;background:transparent;overflow:visible}.el{position:absolute;min-width:8px;min-height:8px;transform-origin:center center;touch-action:none;outline:0 solid transparent}.editing .el.selected{outline:2px solid #8b5cf6;box-shadow:0 0 0 2px rgba(139,92,246,.25)}.el.text{display:flex;align-items:center;white-space:nowrap;overflow:hidden;line-height:1.05;text-shadow:none;background:transparent}.el.text .textInner{display:inline-block;white-space:nowrap;will-change:transform;max-width:none}.el.text.marquee-on{justify-content:flex-start!important}.el.shape,.el.line{background:rgba(255,255,255,.3)}.el.cover{overflow:hidden;background:transparent}.el.cover img{width:100%;height:100%;object-fit:cover;display:block}.cover img.youtube-cover{object-fit:cover;border-radius:0!important;}.el.cover.circle,img.circle{border-radius:9999px}.el.cover.rotate img{animation:spin var(--spin,18s) linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes s3bounce{from{transform:translateX(0)}to{transform:translateX(calc(-1 * var(--marquee-distance,0px)))}}@keyframes s3scrollltr{from{transform:translateX(calc(-1 * var(--text-width,0px)))}to{transform:translateX(var(--box-width,100%))}}@keyframes s3scrollrtl{from{transform:translateX(var(--box-width,100%))}to{transform:translateX(calc(-1 * var(--text-width,0px)))}}.handle{display:none;position:absolute;right:-7px;bottom:-7px;width:15px;height:15px;border-radius:50%;background:#8b5cf6;border:2px solid #fff;cursor:nwse-resize;z-index:10}.editing .selected .handle{display:block}#editBtn{position:fixed;right:14px;bottom:14px;z-index:99999;border:1px solid rgba(255,255,255,.25);background:rgba(12,12,16,.72);backdrop-filter:blur(10px);color:white;border-radius:12px;padding:10px 16px;font-weight:900;cursor:pointer}#editBtn:hover{background:#8b5cf6}#panel{position:fixed;right:0;top:0;bottom:0;width:390px;z-index:99998;background:rgba(12,12,16,.95);backdrop-filter:blur(14px);border-left:1px solid #333341;padding:12px;transform:translateX(100%);transition:transform .22s ease;overflow:auto}.editing #panel{transform:translateX(0)}#panel h2{margin:0 0 8px;font-size:18px}.row{display:grid;grid-template-columns:132px 1fr;gap:8px;align-items:center;margin:7px 0}.row label{font-size:12px;color:#aaaab6}input,select,button{background:#1d1d27;color:#fff;border:1px solid #414152;border-radius:8px;padding:7px}input[type=color]{padding:2px;height:34px}.btns{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.btns button{cursor:pointer}.primary{background:#7c3aed}.danger{background:#7f1d1d}.hint{font-size:12px;color:#aaa;line-height:1.35;border-top:1px solid #333;padding-top:8px;margin-top:8px}.list{max-height:150px;overflow:auto;border:1px solid #333;border-radius:8px}.item{padding:6px 8px;border-bottom:1px solid #2b2b34;cursor:pointer}.item:hover,.item.active{background:#2b2146}.fx-fade{animation:fadeIn .45s ease}.fx-slide-left{animation:slideLeft .45s ease}.fx-slide-right{animation:slideRight .45s ease}.fx-pop{animation:popIn .42s cubic-bezier(.2,1.5,.35,1)}.fx-glitch{animation:glitch .45s steps(2,end)}.fx-flip{animation:flipIn .55s ease}.fx-bounce{animation:bounceIn .6s ease}@keyframes fadeIn{from{opacity:0;filter:blur(5px)}to{opacity:1;filter:blur(0)}}@keyframes slideLeft{from{opacity:0;transform:translateX(-35px)}to{opacity:1;transform:translateX(0)}}@keyframes slideRight{from{opacity:0;transform:translateX(35px)}to{opacity:1;transform:translateX(0)}}@keyframes popIn{0%{opacity:0;transform:scale(.55)}70%{opacity:1;transform:scale(1.08)}100%{transform:scale(1)}}@keyframes glitch{0%{transform:translate(0);filter:hue-rotate(0)}20%{transform:translate(-4px,2px)}40%{transform:translate(4px,-1px)}60%{transform:translate(-2px,-2px)}80%{transform:translate(2px,1px)}100%{transform:translate(0)}}@keyframes flipIn{from{opacity:0;transform:perspective(400px) rotateX(70deg)}to{opacity:1;transform:none}}@keyframes bounceIn{0%{opacity:0;transform:scale(.3)}50%{opacity:1;transform:scale(1.08)}70%{transform:scale(.95)}100%{transform:scale(1)}}
</style></head><body><div id='stageWrap'><div id='stage'></div></div><button id='editBtn'>Edit</button><aside id='panel'><h2>Custom Overlay</h2><div class='btns'><button onclick="addText('artist')">+ Artist</button><button onclick="addText('song')">+ Song</button><button onclick='addCover()'>+ Cover</button><button onclick='addRect()'>+ Rechteck</button><button onclick='addCircle()'>+ Kreis</button><button onclick="addLine('up')">+ Line Up</button><button onclick="addLine('down')">+ Line Down</button></div><div class='list' id='elist'></div><div id='props'></div><div class='btns'><button class='primary' onclick='saveLayout()'>Save</button><button onclick='loadLayout()'>Reload</button><button onclick='resetLayout()'>Reset</button><button class='danger' onclick='deleteSelected()'>Delete</button></div><div class='hint'>Kein Full-Reload: Artist/Song/Cover werden live aktualisiert. Cover-Cache wird nur bei echtem Wechsel erneuert. FÃ¼r Meld am besten Browserquelle auf Canvas-GrÃ¶ÃŸe setzen. Lange Texte laufen automatisch als Band.</div></aside>
<script>
let state=__STATE__;let selected=null,editing=false,np={},lastVals={},nodes=new Map(),scale=1;const stage=document.getElementById('stage'),wrap=document.getElementById('stageWrap');
function uid(p){return p+'_'+Math.random().toString(36).slice(2,8)}
function canvas(){state.canvas=state.canvas||{};state.canvas.width=+(state.canvas.width||900);state.canvas.height=+(state.canvas.height||360);return state.canvas}
function fitStage(){let c=canvas();stage.style.width=c.width+'px';stage.style.height=c.height+'px';scale=Math.min(wrap.clientWidth/c.width,wrap.clientHeight/c.height);if(!isFinite(scale)||scale<=0)scale=1;stage.style.transform='scale('+scale+')'}
window.addEventListener('resize',fitStage);
function provider(){return String(np.provider||np.source||'spotify').toLowerCase().includes('youtube')?'youtube':'spotify'}
function providerColor(){return state.colors?.[provider()]||(provider()==='youtube'?'#FF0033':'#1DB954')}
function bindValue(el){if(el.bind==='artist')return provider()==='youtube'?(np.artist||'powered by spotis3mptify'):(np.artist||'');if(el.bind==='song'||el.bind==='title')return provider()==='youtube'?(np.title||np.song||'YouTube Music'):(np.title||np.song||'');if(el.bind==='providerColor')return providerColor();return el.text||''}
function fitText(n,el,force=false){if(!n||el.type!=='text')return;let sp=n.querySelector('.textInner');if(!sp)return;let boxW=n.clientWidth||(+el.w||1), textW=sp.scrollWidth||1, overflow=Math.max(0,textW-boxW);let c=canvas();let mode=(el.marqueeMode&&el.marqueeMode!=='global')?el.marqueeMode:(c.marqueeMode||'bounce');let speed=+(el.marqueeSpeed||c.marqueeSpeed||45);if(!isFinite(speed)||speed<10)speed=45;let sig=[sp.textContent,boxW,textW,overflow,mode,speed,el.font,el.fontSize,el.align].join('|');if(!force&&sp.dataset.marqueeSig===sig)return;sp.dataset.marqueeSig=sig;sp.style.animation='none';sp.style.transform='translateX(0)';n.classList.remove('marquee-on');sp.style.setProperty('--box-width',boxW+'px');sp.style.setProperty('--text-width',textW+'px');sp.style.setProperty('--marquee-distance',overflow+'px');if(mode==='off'||overflow<2)return;n.classList.add('marquee-on');if(mode==='scroll-rtl'){let dur=Math.max(3,(textW+boxW)/speed);sp.style.animation='s3scrollrtl '+dur+'s linear infinite'}else if(mode==='scroll-ltr'){let dur=Math.max(3,(textW+boxW)/speed);sp.style.animation='s3scrollltr '+dur+'s linear infinite'}else{let dur=Math.max(2.2,overflow/speed);sp.style.animation='s3bounce '+dur+'s ease-in-out infinite alternate'}}
function coverKey(){return String(np.cover_version||np.id||np.video_id||np.url||np.updated_at||'none')}
function coverUrl(){let key=encodeURIComponent(coverKey());return '/cover/latest?size=640&s3v='+key}
function applyStyle(n,el){n.style.left=(+el.x||0)+'px';n.style.top=(+el.y||0)+'px';n.style.width=(+el.w||80)+'px';n.style.height=(+el.h||30)+'px';n.style.opacity=el.opacity??1;n.style.zIndex=el.z||1;n.style.borderRadius=(+el.radius||0)+'px';if(el.type==='text'){n.style.fontFamily=el.font||'Arial';n.style.fontSize=(+el.fontSize||32)+'px';n.style.fontWeight=el.bold?'900':'400';n.style.color=el.color||'#fff';n.style.justifyContent=el.align==='center'?'center':el.align==='right'?'flex-end':'flex-start'}if(el.type==='shape'||el.type==='line'){n.style.background=el.bind==='providerColor'?providerColor():(el.color||'#fff')}} 
function animate(n,fx){if(!fx||fx==='none')return;n.classList.remove('fx-'+fx);void n.offsetWidth;n.classList.add('fx-'+fx);setTimeout(()=>n.classList.remove('fx-'+fx),700)}
function createNode(el){let n=document.createElement('div');n.className='el '+(el.type||'shape');n.dataset.id=el.id;if(el.type==='text'){let sp=document.createElement('span');sp.className='textInner';n.appendChild(sp)}if(el.type==='cover'){let img=document.createElement('img');n.appendChild(img)}let h=document.createElement('div');h.className='handle';n.appendChild(h);n.onpointerdown=e=>startDrag(e,el,false);h.onpointerdown=e=>startDrag(e,el,true);n.onclick=e=>{e.stopPropagation();select(el.id)};stage.appendChild(n);nodes.set(el.id,n);return n}
function updateNode(el,changed=false){let n=nodes.get(el.id)||createNode(el);n.className='el '+(el.type||'shape')+(el.id===selected?' selected':'');applyStyle(n,el);if(el.type==='text'){let v=bindValue(el)||'';let sp=n.querySelector('.textInner');if(!sp){sp=document.createElement('span');sp.className='textInner';n.insertBefore(sp,n.firstChild)}let textChanged=false;if(sp.textContent!==v){sp.textContent=v;textChanged=true;sp.dataset.marqueeSig=''}fitText(n,el,textChanged||changed)}else if(el.type==='cover'){let img=n.querySelector('img');let u=coverUrl();if(img && img.dataset.src!==u){img.dataset.src=u;img.src=u}if(img)img.className=el.shape==='circle'?'circle':'';n.classList.toggle('circle',el.shape==='circle');n.style.borderRadius=(+el.radius||0)+'px';n.classList.toggle('rotate',!!el.rotate);n.style.setProperty('--spin',(el.rotationSpeed||18)+'s')}if(changed)animate(n,el.effect)}
function render(changed=[]){fitStage();let wanted=new Set((state.elements||[]).map(e=>e.id));for(const [id,n] of nodes){if(!wanted.has(id)){n.remove();nodes.delete(id)}}(state.elements||[]).sort((a,b)=>(a.z||1)-(b.z||1)).forEach(el=>updateNode(el,changed.includes(el.id)));refreshList();refreshProps()}
function liveUpdate(){let changed=[];for(const el of state.elements||[]){let v=el.type==='cover'?coverUrl():bindValue(el);if(lastVals[el.id]!==undefined&&lastVals[el.id]!==v)changed.push(el.id);lastVals[el.id]=v;updateNode(el,changed.includes(el.id))}if(changed.length){refreshList(); if(selected)refreshProps()}}
function refreshData(){fetch('/nowplaying?_='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(d=>{let old=provider();np=d||{};liveUpdate(); if(old!==provider()) liveUpdate()}).catch(()=>{});setTimeout(refreshData,1000)}
function select(id){selected=id;render()}stage.onclick=()=>{selected=null;render()};document.getElementById('editBtn').onclick=()=>{editing=!editing;document.body.classList.toggle('editing',editing)};
function startDrag(e,el,resize){if(!editing)return;e.stopPropagation();select(el.id);let sx=e.clientX,sy=e.clientY,ox=+el.x||0,oy=+el.y||0,ow=+el.w||80,oh=+el.h||30;function mv(ev){let dx=(ev.clientX-sx)/scale,dy=(ev.clientY-sy)/scale;if(resize){el.w=Math.max(8,Math.round(ow+dx));el.h=Math.max(8,Math.round(oh+dy))}else{el.x=Math.round(ox+dx);el.y=Math.round(oy+dy)}render()}function up(){window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)}window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)}
function center(o){let c=canvas();o.x=Math.round(c.width/2-(o.w||120)/2);o.y=Math.round(c.height/2-(o.h||40)/2);return o}
function addText(b){let el=center({id:uid(b),type:'text',label:b==='artist'?'Artist':'Song',bind:b==='artist'?'artist':'song',w:420,h:54,font:'Nuishock, Nulshock, SquareLocal, Arial, sans-serif',fontSize:b==='artist'?40:30,bold:b==='artist',color:'#fff',opacity:1,align:'left',effect:'fade',z:10,marqueeMode:'global',marqueeSpeed:45});state.elements.push(el);select(el.id)}
function addCover(){let el=center({id:uid('cover'),type:'cover',label:'Cover',w:170,h:170,radius:85,opacity:1,shape:'circle',rotate:true,rotationSpeed:18,effect:'pop',z:5});state.elements.push(el);select(el.id)}
function addRect(){let el=center({id:uid('rect'),type:'shape',label:'Rechteck',w:220,h:80,radius:16,opacity:.6,color:'#ffffff',effect:'fade',z:1});state.elements.push(el);select(el.id)}
function addCircle(){let el=center({id:uid('circle'),type:'shape',label:'Kreis',w:140,h:140,radius:999,opacity:.7,color:'#ffffff',effect:'pop',z:1});state.elements.push(el);select(el.id)}
function addLine(pos){let el=center({id:uid('line'),type:'line',label:pos==='up'?'Line Up':'Line Down',w:680,h:10,radius:8,opacity:1,bind:'providerColor',color:'#fff',effect:'fade',z:2});state.elements.push(el);select(el.id)}
function refreshList(){let e=document.getElementById('elist');e.innerHTML=(state.elements||[]).map(el=>`<div class='item ${el.id===selected?'active':''}' onclick="select('${el.id}')">${el.label||el.id} <small>${el.type}</small></div>`).join('')}
function inp(l,v,k,t='text'){return `<div class='row'><label>${l}</label><input type='${t}' value='${String(v??'').replaceAll('"','&quot;')}' onchange="setSel('${k}',this.value)"></div>`}
function setSel(k,v){let el=state.elements.find(x=>x.id===selected);if(!el)return;if(['x','y','w','h','radius','opacity','z','fontSize','rotationSpeed','marqueeSpeed'].includes(k))v=Number(v);if(['bold','rotate'].includes(k))v=(v==='true'||v===true);el[k]=v;render()}
function setCanvas(k,v){state.canvas=state.canvas||{};if(['width','height','marqueeSpeed'].includes(k))v=Number(v);state.canvas[k]=v;render()}
function setColor(k,v){state.colors=state.colors||{};state.colors[k]=v;render()}
function refreshProps(){let p=document.getElementById('props');let c=canvas();let el=state.elements.find(x=>x.id===selected);let html=`<h2>Canvas</h2>`+`<div class='row'><label>Breite</label><input type='number' value='${c.width}' onchange="setCanvas('width',this.value)"></div><div class='row'><label>HÃ¶he</label><input type='number' value='${c.height}' onchange="setCanvas('height',this.value)"></div><div class='row'><label>Laufband</label><select onchange="setCanvas('marqueeMode',this.value)"><option value='bounce' ${(c.marqueeMode||'bounce')==='bounce'?'selected':''}>Bounce</option><option value='scroll-ltr' ${c.marqueeMode==='scroll-ltr'?'selected':''}>Links â†’ rechts</option><option value='scroll-rtl' ${c.marqueeMode==='scroll-rtl'?'selected':''}>Rechts â†’ links</option><option value='off' ${c.marqueeMode==='off'?'selected':''}>Aus</option></select></div><div class='row'><label>Tempo px/s</label><input type='number' value='${c.marqueeSpeed||45}' onchange="setCanvas('marqueeSpeed',this.value)"></div>`+`<h2>Provider-Farben</h2><div class='row'><label>Spotify</label><input type='color' value='${state.colors?.spotify||'#1DB954'}' oninput="setColor('spotify',this.value)"></div><div class='row'><label>YouTube</label><input type='color' value='${state.colors?.youtube||'#FF0033'}' oninput="setColor('youtube',this.value)"></div>`;if(!el){p.innerHTML=html+'<div class="hint">Element anklicken, dann Optionen Ã¤ndern.</div>';return}html+=`<h2>Auswahl</h2>`+inp('Label',el.label||'','label')+inp('X',el.x,'x','number')+inp('Y',el.y,'y','number')+inp('Breite',el.w,'w','number')+inp('HÃ¶he',el.h,'h','number')+inp('Radius',el.radius||0,'radius','number')+inp('Deckkraft 0-1',el.opacity??1,'opacity','number')+inp('Z',el.z||1,'z','number');if(el.type==='text'){html+=inp('Schrift',el.font||'','font')+inp('GrÃ¶ÃŸe',el.fontSize||32,'fontSize','number')+`<div class='row'><label>Fett</label><select onchange="setSel('bold',this.value)"><option value='true' ${el.bold?'selected':''}>Ja</option><option value='false' ${!el.bold?'selected':''}>Nein</option></select></div><div class='row'><label>Farbe</label><input type='color' value='${el.color||'#ffffff'}' oninput="setSel('color',this.value)"></div><div class='row'><label>Ausrichtung</label><select onchange="setSel('align',this.value)"><option value='left' ${el.align==='left'?'selected':''}>left</option><option value='center' ${el.align==='center'?'selected':''}>center</option><option value='right' ${el.align==='right'?'selected':''}>right</option></select></div><div class='row'><label>Laufband</label><select onchange="setSel('marqueeMode',this.value)"><option value='global' ${(el.marqueeMode||'global')==='global'?'selected':''}>Global</option><option value='bounce' ${el.marqueeMode==='bounce'?'selected':''}>Bounce</option><option value='scroll-ltr' ${el.marqueeMode==='scroll-ltr'?'selected':''}>Links â†’ rechts</option><option value='scroll-rtl' ${el.marqueeMode==='scroll-rtl'?'selected':''}>Rechts â†’ links</option><option value='off' ${el.marqueeMode==='off'?'selected':''}>Aus</option></select></div>`+inp('Tempo px/s',el.marqueeSpeed||45,'marqueeSpeed','number')}if(el.type==='shape'||el.type==='line'){html+=`<div class='row'><label>Farbe</label><input type='color' value='${el.color||'#ffffff'}' oninput="setSel('color',this.value)"></div><div class='row'><label>Provider-Farbe</label><select onchange="setSel('bind',this.value)"><option value='' ${!el.bind?'selected':''}>Nein</option><option value='providerColor' ${el.bind==='providerColor'?'selected':''}>Ja</option></select></div>`}if(el.type==='cover'){html+=`<div class='row'><label>Form</label><select onchange="setSel('shape',this.value)"><option value='circle' ${el.shape==='circle'?'selected':''}>Kreis</option><option value='square' ${el.shape!=='circle'?'selected':''}>Quadrat</option></select></div><div class='row'><label>Drehen</label><select onchange="setSel('rotate',this.value)"><option value='true' ${el.rotate?'selected':''}>Ja</option><option value='false' ${!el.rotate?'selected':''}>Nein</option></select></div>`+inp('Drehdauer s',el.rotationSpeed||18,'rotationSpeed','number')}html+=`<div class='row'><label>Effekt bei Wechsel</label><select onchange="setSel('effect',this.value)">${['none','fade','slide-left','slide-right','pop','glitch','flip','bounce'].map(f=>`<option value='${f}' ${el.effect===f?'selected':''}>${f}</option>`).join('')}</select></div>`;p.innerHTML=html}
function deleteSelected(){if(!selected)return;state.elements=state.elements.filter(e=>e.id!==selected);selected=null;render()}function resetLayout(){if(confirm('Layout zurÃ¼cksetzen?'))fetch('/customoverlay/state?default=1').then(r=>r.json()).then(d=>{state=d;selected=null;nodes.clear();stage.innerHTML='';render();refreshData()})}function saveLayout(){fetch('/customoverlay/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state)}).then(r=>r.json()).then(d=>alert(d.ok?'Gespeichert':'Fehler: '+(d.error||'?'))).catch(e=>alert(e))}function loadLayout(){fetch('/customoverlay/state?_='+Date.now()).then(r=>r.json()).then(d=>{state=d;selected=null;nodes.clear();stage.innerHTML='';render();refreshData()})}
loadLayout();refreshData();
</script></body></html>"""
    return html.replace('__STATE__', initial_state)

def _with_main_i18n(html: str) -> str:
    if not MAIN_UI_BASE or "i18n.js" in html or "</head>" not in html:
        return html
    base = MAIN_UI_BASE.rstrip("/")
    head = f'<script>window.APP_LANGUAGE={json.dumps(UI_LANGUAGE)};</script><script src="{base}/static/js/i18n.js"></script>'
    return html.replace("</head>", head + "</head>", 1)

# ======================= HTTP SERVER =======================

# Meld Elements links are user-configurable.
# Keep these as display/template links only; the data itself still comes from the
# local nowplaying/text/cover endpoints, exactly like the old working build.
MELD_SPOTIFY_ANIMATED_BASE_URL = "https://elements.meldstudio.co/c3b18f4b745841838d3da6b9606a7237/fv4g8dmvpvmkrf3b/spotify-animated.html"
MELD_ARTIST_URL = ""
MELD_SONG_URL = ""
MELD_COVER_URL = ""

def _default_meld_spotify_animated_url(kind: str):
    kind = (kind or "").lower().strip()
    if kind in ("title", "song"):
        kind = "song"
    if kind not in ("artist", "song", "cover"):
        return None
    return MELD_SPOTIFY_ANIMATED_BASE_URL + "?" + urllib.parse.urlencode({"type": kind})

def _meld_spotify_animated_url(kind: str):
    kind = (kind or "").lower().strip()
    if kind in ("title", "song"):
        kind = "song"
    if kind == "artist" and MELD_ARTIST_URL.strip():
        return MELD_ARTIST_URL.strip()
    if kind == "song" and MELD_SONG_URL.strip():
        return MELD_SONG_URL.strip()
    if kind == "cover" and MELD_COVER_URL.strip():
        return MELD_COVER_URL.strip()
    return _default_meld_spotify_animated_url(kind)

def _np_value_for_meld(kind: str) -> str:
    kind = (kind or "").lower().strip()
    cur = _overlay_current()
    if kind in ("song", "title"):
        return cur.get("title", "") or ""
    if kind == "artist":
        return cur.get("artist", "") or ""
    if kind == "album":
        return cur.get("album", "") or ""
    if kind == "combo":
        artist = cur.get("artist", "") or ""
        title = cur.get("title", "") or ""
        return (artist + " - " + title).strip(" -")
    if kind == "provider":
        return cur.get("provider", "") or ""
    if kind == "color" or kind == "accent":
        return cur.get("accent", "") or ("#FF0033" if cur.get("provider") == "youtube" else "#1DB954")
    return cur.get(kind, "") or ""

def _overlay_endpoint_urls() -> Dict[str, Dict[str, str]]:
    try:
        https_port = int(PORT) + 1
    except Exception:
        https_port = 5174
    bases = {
        "http": f"http://127.0.0.1:{PORT}",
        "https": f"https://127.0.0.1:{https_port}",
    }
    paths = {
        "artist": "/browser/artist",
        "song": "/browser/song",
        "title": "/browser/title",
        "album": "/text/album",
        "combo": "/text/combo",
        "cover": f"/browser/cover?size={COVER_IMAGE_SIZE}",
        "cover_image": f"/cover/latest?size={COVER_IMAGE_SIZE}",
        "json": "/nowplaying",
        "line_up": "/browser/line-up",
        "line_down": "/browser/line-down",
    }
    urls = {name: {scheme: base + path for scheme, base in bases.items()} for name, path in paths.items()}
    for name in ("artist", "song", "title", "cover"):
        target = _meld_spotify_animated_url(name)
        if target:
            urls.setdefault(name, {})["meld"] = target
    return urls

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "spotis3mptify/portable-1.0"

    def _cors_origin(self):
        origin = self.headers.get("Origin", "")
        if origin in ("https://elements.meldstudio.co", "http://elements.meldstudio.co"):
            return origin
        return "*"

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth, Cache-Control")
        self.send_header("Access-Control-Max-Age", "86400")

    def _ok(self, obj):
        self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8")
        self._cors_headers()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers(); self.wfile.write(json.dumps(obj).encode("utf-8"))
    def _html(self, code, html):
        self.send_response(code); self.send_header("Content-Type","text/html; charset=utf-8")
        self._cors_headers()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers(); self.wfile.write(html.encode("utf-8"))
    def _text(self, text):
        self.send_response(200); self.send_header("Content-Type","text/plain; charset=utf-8")
        self._cors_headers()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers(); self.wfile.write(str(text or "").encode("utf-8"))
    def _redirect(self, location, code=302):
        self.send_response(code)
        self.send_header("Location", location)
        self._cors_headers()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
    def _img(self, path):
        try:
            with open(path, "rb") as f: data = f.read()
            self.send_response(200); self.send_header("Content-Type","image/jpeg")
            self._cors_headers()
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.end_headers(); self.wfile.write(data)
        except:
            self.send_response(404); self._cors_headers(); self.end_headers()
    def _fail(self, code, msg):
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self._cors_headers()
        self.end_headers(); self.wfile.write(json.dumps({"ok":False,"error":msg}).encode("utf-8"))
    def _from_localhost(self): return self.client_address[0] in ("127.0.0.1","::1")
    def _check_secret(self): return True if not SHARED_SECRET else (self.headers.get("X-Auth","") == SHARED_SECRET)

    def log_message(self, fmt, *args):
        # suppress BaseHTTPRequestHandler default console noise
        return

    def do_OPTIONS(self):
        if not self._from_localhost():
            return self._fail(403, "Forbidden")
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _is_top_level_document_request(self) -> bool:
        origin = self.headers.get("Origin", "")
        sec_dest = (self.headers.get("Sec-Fetch-Dest", "") or "").lower()
        sec_mode = (self.headers.get("Sec-Fetch-Mode", "") or "").lower()
        accept = (self.headers.get("Accept", "") or "").lower()
        if origin:
            return False
        if sec_dest and sec_dest != "document":
            return False
        if sec_mode in ("cors", "no-cors"):
            return False
        return (sec_dest == "document") or ("text/html" in accept and "image/" not in accept)

    def do_GET(self):
        try:
            if not self._from_localhost(): return self._fail(403,"Forbidden")
            path, _, qs = self.path.partition("?")
            qd = urllib.parse.parse_qs(qs)

            if path == "/customoverlay":
                return self._html(200, _with_main_i18n(_custom_overlay_html()))
            if path == "/customoverlay/state":
                if ((qd.get("default") or ["0"])[0] in ("1", "true", "yes")):
                    return self._ok(_custom_overlay_default_state())
                return self._ok(_load_custom_overlay_state())
            if path == "/font/square":
                fp = os.path.join(_SCRIPT_DIR, "Square.ttf")
                if os.path.exists(fp):
                    with open(fp, "rb") as f: data = f.read()
                    self.send_response(200); self.send_header("Content-Type", "font/ttf"); self._cors_headers(); self.end_headers(); self.wfile.write(data); return
            if path == "/font/robot-heroes":
                fp = os.path.join(_SCRIPT_DIR, "Robot Heroes.ttf")
                if os.path.exists(fp):
                    with open(fp, "rb") as f: data = f.read()
                    self.send_response(200); self.send_header("Content-Type", "font/ttf"); self._cors_headers(); self.end_headers(); self.wfile.write(data); return

            if path == "/health":
                channel = TWITCH_CHANNEL if TWITCH_REPLY_SENDER == "main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)
                return self._ok({"ok":True, "project":"spotis3mptify", "enabled": ENABLED,
                                 "authorized_spotify": _is_authorized(),
                                 "spotify_token_scope": str(_read_tokens().get("scope") or ""),
                                 "authorized_twitch_main": _twitch_is_authorized("main"),
                                 "authorized_twitch_bot": _twitch_is_authorized("bot"),
                                 "twitch_listen": TWITCH_LISTEN,
                                 "twitch_channel": channel,
                                 "reply_sender": TWITCH_REPLY_SENDER,
                                 "np_files_dir": TOKENS_DIR,
                                 "np_updated_at": NOWPLAYING.get("updated_at",0),
                                 "obs_ws_enabled": OBS_WS_ENABLED,
                                 "obs_ws_connected": _OBS_CLIENT.connected if OBS_WS_ENABLED else False,
                                 "youtube_enabled": YOUTUBE_ENABLED, "youtube_cmd": TWITCH_CMD_YT, "youtube_player_mode": YOUTUBE_PLAYER_MODE, "youtube_queue_len": len(_YT_QUEUE), "youtube_webview": dict(_YT_WEBVIEW_STATUS), "youtube_webview_running": bool(_YT_WEBVIEW_STATUS.get("running") and (_now() - float(_YT_WEBVIEW_STATUS.get("ts") or 0) < 6)),
                                 "endpoints": _overlay_endpoint_urls()})

            # ---------- Browser / overlay endpoint discovery ----------
            if path == "/endpoints":
                return self._ok({"ok": True, "http_port": PORT, "https_port": _https_port(), "urls": _overlay_endpoint_urls(), "note": "HTTPS uses a local certificate signed by the spotis3mptify Local Root CA. Install the Root CA once to remove browser warnings."})

            if path == "/cert/info":
                return self._ok(get_local_https_cert_info())

            if path == "/cert/install":
                return self._ok(install_local_https_root_ca())

            if path == "/cert/root-ca":
                if os.path.exists(_LOCAL_CA_CERT):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-x509-ca-cert")
                    self.send_header("Content-Disposition", "attachment; filename=spotis3mptify_local_root_ca.crt")
                    self.end_headers()
                    with open(_LOCAL_CA_CERT, "rb") as f:
                        self.wfile.write(f.read())
                    return
                return self._fail(404, "Root CA not found")

            if path.startswith("/text/"):
                kind = path.split("/", 2)[2]
                if kind == "song": kind = "title"
                return self._text(_np_value_for_meld(kind))
            if path == "/twitch/status":
                running = bool(_TWITCH_THREAD and _TWITCH_THREAD.is_alive())
                ch = TWITCH_CHANNEL if TWITCH_REPLY_SENDER == "main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)
                st = {"authorized_main": _twitch_is_authorized("main"), "authorized_bot": _twitch_is_authorized("bot"),
                      "listen": TWITCH_LISTEN, "channel": ch, "running": running, "active_sender": _TWITCH_LAST_ACC}
                return self._ok(st)
            if path == "/twitch/debug":
                running = bool(_TWITCH_THREAD and _TWITCH_THREAD.is_alive())
                st = {"authorized_main": _twitch_is_authorized("main"), "authorized_bot": _twitch_is_authorized("bot"),
                      "listen": TWITCH_LISTEN, "channel": (TWITCH_CHANNEL if TWITCH_REPLY_SENDER=="main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)),
                      "running": running, "active_sender": _TWITCH_LAST_ACC,
                      "last_lines": _IRC_DEBUG_LAST[-20:]}
                return self._ok(st)

            # ---------- SR ----------
            if path == "/sr":
                if not ENABLED: return self._fail(503,"DISABLED")
                if not _is_authorized(): return self._fail(401,"Spotify is not authorized in the core Platforms page")
                raw_q = ((qd.get("q") or [""])[0]); raw_user = ((qd.get("user") or [""])[0])
                if not raw_q: return self._fail(400,"Missing q")
                try:
                    result, err = _handle_sr(raw_q, raw_user)
                    if err: return self._ok({"ok":False,"error":err})
                    return self._ok(result)
                except Exception as e:
                    return self._fail(500,str(e))

            # ---------- YouTube requests ----------
            if path == "/youtube-player" or path == "/yt/player":
                _yt_log("Player page opened")
                return self._html(200, _yt_player_html())
            if path == "/yt/logs":
                lim = ((qd.get("limit") or ["250"])[0])
                try: lim = int(lim)
                except Exception: lim = 250
                return self._ok(_yt_get_logs(lim))
            if path == "/yt/audio-output":
                return self._ok(_yt_audio_state())
            if path == "/yt/state" or path == "/yt/queue":
                return self._ok(_yt_state(False))
            if path == "/yt/info":
                with _YT_QUEUE_LOCK:
                    _yt_load()
                    return self._ok({"ok": True, "current": _yt_public(_YT_CURRENT), "queue": [_yt_public(x) for x in _YT_QUEUE], "nowplaying": _overlay_current()})
            if path == "/yt/webview/status":
                return self._ok({"ok": True, **dict(_YT_WEBVIEW_STATUS), "recent": bool(_YT_WEBVIEW_STATUS.get("running") and (_now() - float(_YT_WEBVIEW_STATUS.get("ts") or 0) < 6))})
            if path == "/yt/next":
                pop = ((qd.get("pop") or ["0"])[0] in ("1","true","yes"))
                return self._ok(_yt_state(pop))
            if path == "/yt/request":
                if not ENABLED: return self._fail(503,"DISABLED")
                raw_q=((qd.get("q") or [""])[0]); raw_user=((qd.get("user") or ["browser"])[0])
                if not raw_q: return self._fail(400,"Missing q")
                result, err = _handle_yt(raw_q, raw_user)
                if err: return self._ok({"ok":False,"error":err})
                return self._ok(result)

            if path == "/srplus/state":
                remaining = 0; phase = "idle"
                if not ENABLED: phase = "disabled"
                elif TAKEOVER.get("active"):
                    phase = "pending" if TAKEOVER.get("pending") else "playing"
                    if not TAKEOVER.get("pending"):
                        remaining = max(0, int(TAKEOVER.get("ends_at",0) - _now()))
                state = dict(TAKEOVER); state["backlog_len"] = len(state.get("backlog") or []); state["remaining_sec"] = remaining; state["phase"] = phase; state.pop("snapshot", None)
                est = int(TAKEOVER.get("ends_at") or 0) if TAKEOVER.get("active") and not TAKEOVER.get("pending") else 0
                return self._ok({"ok":True, "enabled": ENABLED, "authorized": _is_authorized(),
                                 "state":state, "guard":GUARD, "duration_min": SRPLUS_DURATION_MIN,
                                 "estimated_ends_at": est})

            if path == "/yt/request":
                if not ENABLED: return self._fail(503,"DISABLED")
                raw_q=(body.get("q") or ""); raw_user=(body.get("user") or "browser")
                if not raw_q: return self._fail(400,"Missing q")
                result, err = _handle_yt(raw_q, raw_user)
                if err: return self._ok({"ok":False,"error":err})
                return self._ok(result)
            if path == "/yt/finished": return self._ok(_yt_finished())
            if path == "/yt/skip": return self._ok(_yt_skip())
            if path == "/yt/clear": return self._ok(_yt_clear())

            if path == "/srplus/start":
                if not ENABLED: return self._fail(503,"DISABLED")
                if not _is_authorized(): return self._fail(401,"Spotify is not authorized in the core Platforms page")
                user = ((qd.get("user") or [""])[0]).strip()
                try:
                    at = _ensure_access_token()
                    r = _start_takeover(at, user)
                    resp = dict(r); resp["duration_min"] = SRPLUS_DURATION_MIN
                    if resp.get("pending"):
                        st = _get_player_state(at) or {}
                        dur = int(((st.get("item") or {}).get("duration_ms") or 0))
                        prog = int(st.get("progress_ms") or 0)
                        remain = max(0, (dur - prog + 999) // 1000)
                        est_ends = _now() + remain + max(1,int(SRPLUS_DURATION_MIN))*60
                        resp["est_starts_in_sec"] = remain
                        resp["estimated_ends_at"] = est_ends
                        resp["ends_at"] = est_ends
                    return self._ok(resp)
                except Exception as e:
                    return self._fail(500, str(e))

            if path == "/srplus/clear":
                TAKEOVER.update({"active": False, "pending": False, "pending_since": 0, "owner":"", "playlist_id":"", "backlog": [], "snapshot": {}, "ends_at": 0})
                _save_takeover()
                return self._ok({"ok": True, "cleared": True})

            # ---------- FILTER sequence ----------
            if path == "/filters/sequence":
                delay_override = None
                if "delay" in qd:
                    try: delay_override = int((qd.get("delay") or [""])[0])
                    except: delay_override = None
                success = _obs_trigger_filter_sequence(delay_override=delay_override)
                _log_throttled("INFO","filter_seq",f"OBS filter sequence triggered (success: {success})",5)
                return self._ok({"ok": True, "triggered": True, "delay_sec": delay_override, "obs_success": success})

            # ---------- NOWPLAYING ----------
            if path == "/nowplaying":
                # Browser/dashboard should always receive the source that is
                # really active, not a stale YouTube handoff state.
                return self._ok(dict(_overlay_current()))
            if path == "/nowplaying/refresh":
                if not _is_authorized(): return self._fail(401,"Spotify is not authorized in the core Platforms page")
                try:
                    at = _ensure_access_token(); _np_poll_once(at, force=True)
                    with _NP_LOCK:
                        return self._ok(dict(NOWPLAYING))
                except Exception as e:
                    return self._fail(500, f"refresh failed: {e}")

            if path in ("/api/nowplaying", "/api/current", "/spotify"):
                with _NP_LOCK:
                    return self._ok(dict(_overlay_current()))
            if path in ("/artist", "/song", "/title", "/album", "/combo", "/provider", "/color"):
                kind = path.strip("/")
                if kind == "song": kind = "title"
                return self._text(_np_value_for_meld(kind))
            if path == "/cover":
                cur = _overlay_current()
                if (cur.get("provider") or "spotify").lower() == "youtube":
                    return self._img(_p_yt_thumb())
                return self._img(_ensure_current_spotify_cover_file(COVER_IMAGE_SIZE))

            if path == "/browser/artist":
                if self._is_top_level_document_request():
                    target = _meld_spotify_animated_url("artist")
                    if target: return self._redirect(target)
                    return self._html(200, _overlay_text_html("artist"))
                return self._text(_np_value_for_meld("artist"))
            if path == "/browser/song" or path == "/browser/title":
                if self._is_top_level_document_request():
                    target = _meld_spotify_animated_url("song")
                    if target: return self._redirect(target)
                    return self._html(200, _overlay_text_html("song"))
                return self._text(_np_value_for_meld("title"))
            if path == "/browser/cover":
                if self._is_top_level_document_request():
                    target = _meld_spotify_animated_url("cover")
                    if target: return self._redirect(target)
                    return self._html(200, _overlay_cover_html())
                # Data/image request from the remote Meld Elements page. Never return the HTML wrapper here.
                cur = _overlay_current()
                if (cur.get("provider") or "spotify").lower() == "youtube":
                    return self._img(_p_yt_thumb())
                size = COVER_IMAGE_SIZE
                try: size = int((qd.get("size") or [str(COVER_IMAGE_SIZE)])[0])
                except Exception: pass
                if size not in (64, 300, 640): size = COVER_IMAGE_SIZE if COVER_IMAGE_SIZE in (64, 300, 640) else 300
                return self._img(_ensure_current_spotify_cover_file(size))
            if path == "/browser/line-up" or path == "/browser/line-down":
                return self._html(200, _overlay_line_html(path.rsplit("/", 1)[-1], qd))
            if path == "/browser/provider":
                return self._ok({"ok": True, "nowplaying": _overlay_current()})

            if path == "/cover/latest":
                cur = _overlay_current()
                if (cur.get("provider") or "spotify").lower() == "youtube":
                    return self._img(_p_yt_thumb())
                size = COVER_IMAGE_SIZE
                try: size = int((qd.get("size") or [str(COVER_IMAGE_SIZE)])[0])
                except: pass
                if size not in (64,300,640): size = COVER_IMAGE_SIZE
                return self._img(_ensure_current_spotify_cover_file(size))

            if path == "/cover/info":
                info = {"files": {"cover_640": _p_cover(640), f"cover_{COVER_IMAGE_SIZE}": _p_cover(COVER_IMAGE_SIZE)}, "nowplaying_json": _p_np_json(),
                        "texts": {"artist":_p_np_artist(),"title":_p_np_title(),"album":_p_np_album(),"combo":_p_np_combo(),"url":_p_np_url()},
                        "updated_at": NOWPLAYING.get("updated_at", 0), "authorized": _is_authorized()}
                return self._ok(info)

            if path == "/cover/url":
                cur = _overlay_current()
                url_640 = (cur.get("thumbnail") or (cur.get("covers") or {}).get("url_640", ""))
                return self._ok({"url": url_640, "ok": bool(url_640), "provider": (cur.get("provider") or "spotify")})

            return self._fail(404,"Not found")
        except Exception as e:
            return self._fail(500,str(e))

    def do_POST(self):
        global YOUTUBE_AUDIO_OUTPUT_NAME
        try:
            if not self._from_localhost(): return self._fail(403,"Forbidden")
            if not self._check_secret():  return self._fail(401,"Unauthorized")
            length = int(self.headers.get("Content-Length","0"))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
            path = self.path

            if path == "/customoverlay/save":
                try:
                    return self._ok(_save_custom_overlay_state(body))
                except Exception as e:
                    return self._fail(400, str(e))

            if path == "/yt/webview/status":
                try:
                    incoming = body if isinstance(body, dict) else {}
                    _YT_WEBVIEW_STATUS.update({
                        "running": bool(incoming.get("running", True)),
                        "ts": float(incoming.get("ts") or _now()),
                        "logged_in": bool(incoming.get("logged_in", False)),
                        "consent_visible": bool(incoming.get("consent_visible", False)),
                        "sign_in_visible": bool(incoming.get("sign_in_visible", False)),
                        "reason": str(incoming.get("reason") or "running"),
                        "url": str(incoming.get("url") or ""),
                        "host": str(incoming.get("host") or ""),
                        "audio_devices": incoming.get("audio_devices") if isinstance(incoming.get("audio_devices"), list) else _YT_WEBVIEW_STATUS.get("audio_devices", []),
                        "audio_selected": str(incoming.get("audio_selected") or YOUTUBE_AUDIO_OUTPUT_NAME or "Default"),
                        "audio_applied": str(incoming.get("audio_applied") or _YT_WEBVIEW_STATUS.get("audio_applied") or ""),
                    })
                except Exception:
                    pass
                return self._ok({"ok": True, **dict(_YT_WEBVIEW_STATUS)})

            if path == "/yt/audio-output":
                try:
                    name = str(body.get("selected") or body.get("name") or "Default").strip() or "Default"
                    YOUTUBE_AUDIO_OUTPUT_NAME = name
                    _YT_WEBVIEW_STATUS["audio_selected"] = name
                    _yt_log(f"Audio output selected: {name}")
                    return self._ok(_yt_audio_state())
                except Exception as e:
                    return self._fail(500, str(e))

            if path == "/yt/log":
                msg = str(body.get("message") or body.get("msg") or "")[:500]
                level = str(body.get("level") or "INFO").upper()
                if not msg: msg = "Player event"
                _yt_log("Player: " + msg, level if level in ("INFO","WARN","ERROR") else "INFO")
                return self._ok({"ok": True})
            if path == "/yt/logs/clear":
                return self._ok(_yt_clear_logs())
            if path == "/yt/webview/nowplaying":
                return self._ok(_set_youtube_nowplaying(body if isinstance(body, dict) else {}))
            if path == "/yt/request":
                if not ENABLED: return self._fail(503,"DISABLED")
                raw_q=(body.get("q") or ""); raw_user=(body.get("user") or "browser")
                if not raw_q: return self._fail(400,"Missing q")
                result, err = _handle_yt(raw_q, raw_user)
                if err: return self._ok({"ok":False,"error":err})
                return self._ok(result)
            if path == "/yt/finished": return self._ok(_yt_finished())
            if path == "/yt/skip": return self._ok(_yt_skip())
            if path == "/yt/clear": return self._ok(_yt_clear())

            if path == "/sr":
                if not ENABLED: return self._fail(503,"DISABLED")
                if not _is_authorized(): return self._fail(401,"Spotify is not authorized in the core Platforms page")
                raw_q = (body.get("q") or ""); raw_user = (body.get("user") or "")
                if not raw_q: return self._fail(400,"Missing q")
                try:
                    result, err = _handle_sr(raw_q, raw_user)
                    if err: return self._ok({"ok":False,"error":err})
                    return self._ok(result)
                except Exception as e:
                    return self._fail(500,str(e))

            if path == "/srplus/start":
                if not ENABLED: return self._fail(503,"DISABLED")
                if not _is_authorized(): return self._fail(401,"Spotify is not authorized in the core Platforms page")
                user = (body.get("user") or "").strip()
                try:
                    at = _ensure_access_token()
                    r = _start_takeover(at, user)
                    resp = dict(r); resp["duration_min"] = SRPLUS_DURATION_MIN
                    if resp.get("pending"):
                        st = _get_player_state(at) or {}
                        dur = int(((st.get("item") or {}).get("duration_ms") or 0))
                        prog = int(st.get("progress_ms") or 0)
                        remain = max(0, (dur - prog + 999) // 1000)
                        est_ends = _now() + remain + max(1,int(SRPLUS_DURATION_MIN))*60
                        resp["est_starts_in_sec"] = remain
                        resp["estimated_ends_at"] = est_ends
                        resp["ends_at"] = est_ends
                    return self._ok(resp)
                except Exception as e:
                    return self._fail(500, str(e))

            if path == "/srplus/reset":
                GUARD["srplus_used_this_stream"] = False; _save_guard()
                return self._ok({"ok": True, "reset": True})

            return self._fail(404,"Not found")
        except Exception as e:
            return self._fail(500,str(e))

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 20
    timeout = 1.0

_httpd = None
_server_thread = None
_httpsd = None
_https_thread = None

def start_server():
    global _httpd, _server_thread, _httpsd, _https_thread
    if _httpd: return
    try:
        _httpd = ThreadingTCPServer(("127.0.0.1", PORT), Handler)
        _server_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
        _server_thread.start()

        cert_pair = _ensure_localhost_cert()
        if cert_pair:
            try:
                cert_path, key_path = cert_pair
                _httpsd = ThreadingTCPServer(("127.0.0.1", _https_port()), Handler)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                _httpsd.socket = ctx.wrap_socket(_httpsd.socket, server_side=True)
                _https_thread = threading.Thread(target=_httpsd.serve_forever, daemon=True)
                _https_thread.start()
                logi(f"listening on https://127.0.0.1:{_https_port()} (local CA-signed cert)")
            except Exception as e:
                _httpsd = None; _https_thread = None
                logw(f"HTTPS server failed: {e}")

        _yt_load()
        if _is_authorized(): _maybe_enable_pollers()
        _restart_twitch_thread_if_needed(force=True)
        _restart_external_sr_thread_if_needed(force=True)
        logi(f"listening on http://127.0.0.1:{PORT}")
    except Exception as e:
        loge(f"HTTP server failed: {e}")

def stop_server():
    global _httpd, _server_thread, _httpsd, _https_thread, _TWITCH_THREAD, _EXTERNAL_SR_THREAD
    try:
        if _httpd:
            _httpd.shutdown(); _httpd.server_close()
    except: pass
    try:
        if _httpsd:
            _httpsd.shutdown(); _httpsd.server_close()
    except: pass
    _httpd = None; _server_thread = None
    _httpsd = None; _https_thread = None
    _disable_pollers()
    if _TWITCH_THREAD:
        try: _TWITCH_THREAD.stop()
        except: pass
        _TWITCH_THREAD = None
    if _EXTERNAL_SR_THREAD:
        try:
            _EXTERNAL_SR_STOP.set()
            _EXTERNAL_SR_THREAD.join(timeout=2.0)
        except:
            pass
        _EXTERNAL_SR_THREAD = None
        _EXTERNAL_SR_STOP.clear()
    _OBS_CLIENT.disconnect()

# ============== PUBLIC SETTERS (fÃ¼r UI) ==============
def apply_settings(cfg: Dict[str, Any]):
    global CLIENT_ID, CLIENT_SECRET, PORT, UI_LANGUAGE, MAIN_UI_BASE, SHARED_SECRET, DATA_DIR, AUTH_DIR, CONFIG_DIR, NOWPLAYING_DIR, COVERS_DIR, PLAYLISTS_DIR, STATE_DIR, EXPORT_DIR, CERTS_DIR, YOUTUBE_DIR, TOKENS_DIR, CENTRAL_SPOTIFY_TOKEN_FILE, REDIRECT_URI_OV, CENTRAL_SPOTIFY_TOKENS, CUSTOM_OVERLAY_JSON, _LOCAL_CA_CERT, _LOCAL_CA_KEY, _LOCAL_TLS_CERT, _LOCAL_TLS_KEY
    global COOLDOWN_MINUTES, PLAYLIST_PREFIX, PLAYLIST_COVER_ENABLED, PLAYLIST_COVER_FILE, SRPLUS_DURATION_MIN, SRPLUS_ONCE_PER_STREAM, SRPLUS_SHUFFLE, SRPLUS_SUBSCRIBERS_ONLY
    global ENABLED, AUTO_STOP_ON_DISABLE, REPEAT_GUARD, PLAY_NOW, QUEUE_THEN_SKIP, ASYNC_PLAYLIST_ADD, ASYNC_COVER_FETCH
    global LOG_VERBOSE, LOG_SLOW_MS, LOG_DEDUP_SEC, LOG_NP_ON_CHANGE, NOWPLAYING_ENABLE_FILES, NOWPLAYING_POLL_MS
    global TWITCH_LISTEN, TWITCH_REPLY, TWITCH_CHANNEL, TWITCH_BOT_CHANNEL
    global TWITCH_MAIN_CLIENT_ID, TWITCH_MAIN_CLIENT_SECRET, TWITCH_MAIN_SCOPES, TWITCH_MAIN_REDIRECT_OV
    global TWITCH_BOT_CLIENT_ID, TWITCH_BOT_CLIENT_SECRET, TWITCH_BOT_SCOPES, TWITCH_BOT_REDIRECT_OV
    global TWITCH_CMD_SR, TWITCH_CMD_SRPLUS, TWITCH_CMD_YT, SR_SOURCE, EXTERNAL_SR_FILE, TWITCH_REPLY_SENDER
    global TWITCH_MAIN_LOGIN_OVERRIDE, TWITCH_MAIN_TOKEN_OVERRIDE, TWITCH_BOT_LOGIN_OVERRIDE, TWITCH_BOT_TOKEN_OVERRIDE
    global OBS_WS_ENABLED, OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD
    global OBS_FILTER1_SOURCE, OBS_FILTER1_NAME, OBS_FILTER1_ENABLE
    global OBS_FILTER2_SOURCE, OBS_FILTER2_NAME, OBS_FILTER2_ENABLE
    global OBS_FILTER_DELAY_SEC, OBS_FILTER_AUTO_ON_NP_CHANGE
    global OBS_COVER_BROWSER_SOURCE, OBS_COVER_IMAGE_SOURCE, COVER_IMAGE_SIZE
    # NEU:
    global TWITCH_NP_ON_CHANGE, TWITCH_NP_FORMAT, TWITCH_NP_COOLDOWN_SEC
    global YOUTUBE_ENABLED, YOUTUBE_MAX_DURATION_SEC, YOUTUBE_AUTOPLAY, YOUTUBE_PLAYER_MODE, YOUTUBE_AUDIO_OUTPUT_NAME
    global MELD_ARTIST_URL, MELD_SONG_URL, MELD_COVER_URL
    global OVERLAY_MARQUEE_MODE, OVERLAY_MARQUEE_SPEED

    CLIENT_ID       = cfg.get("client_id", CLIENT_ID)
    CLIENT_SECRET   = cfg.get("client_secret", CLIENT_SECRET)
    PORT            = int(cfg.get("port", PORT))
    UI_LANGUAGE     = "en" if str(cfg.get("ui_language") or "de").lower().startswith("en") else "de"
    MAIN_UI_BASE    = str(cfg.get("main_ui_base") or MAIN_UI_BASE).strip()
    SHARED_SECRET   = cfg.get("shared_secret", SHARED_SECRET)
    DATA_DIR        = _normalize_tokens_dir(cfg.get("data_dir", DATA_DIR) or DATA_DIR)
    AUTH_DIR        = _normalize_tokens_dir(cfg.get("auth_dir", os.path.join(DATA_DIR, "auth")))
    CONFIG_DIR      = _normalize_tokens_dir(cfg.get("config_dir", os.path.join(DATA_DIR, "config")))
    NOWPLAYING_DIR  = _normalize_tokens_dir(cfg.get("nowplaying_dir", os.path.join(DATA_DIR, "nowplaying")))
    COVERS_DIR      = _normalize_tokens_dir(cfg.get("cover_dir", os.path.join(DATA_DIR, "covers")))
    PLAYLISTS_DIR   = _normalize_tokens_dir(cfg.get("playlist_dir", os.path.join(DATA_DIR, "playlists")))
    STATE_DIR       = _normalize_tokens_dir(cfg.get("state_dir", os.path.join(DATA_DIR, "state")))
    EXPORT_DIR      = _normalize_tokens_dir(cfg.get("export_dir", os.path.join(DATA_DIR, "export")))
    CERTS_DIR       = _normalize_tokens_dir(cfg.get("cert_dir", os.path.join(DATA_DIR, "certs")))
    YOUTUBE_DIR     = _normalize_tokens_dir(cfg.get("youtube_dir", os.path.join(DATA_DIR, "youtube")))
    for _d in (DATA_DIR, AUTH_DIR, CONFIG_DIR, NOWPLAYING_DIR, COVERS_DIR, PLAYLISTS_DIR, STATE_DIR, EXPORT_DIR, CERTS_DIR, YOUTUBE_DIR):
        _ensure_dir(_d)
    CUSTOM_OVERLAY_JSON = os.path.join(CONFIG_DIR, "custom_overlay.json")
    _LOCAL_CA_CERT = os.path.join(CERTS_DIR, "spotis3mptify_local_root_ca.crt")
    _LOCAL_CA_KEY  = os.path.join(CERTS_DIR, "spotis3mptify_local_root_ca.key")
    _LOCAL_TLS_CERT = os.path.join(CERTS_DIR, "localhost_https_cert.pem")
    _LOCAL_TLS_KEY  = os.path.join(CERTS_DIR, "localhost_https_key.pem")
    TOKENS_DIR      = _normalize_tokens_dir(cfg.get("tokens_dir", AUTH_DIR) or AUTH_DIR)
    CENTRAL_SPOTIFY_TOKEN_FILE = os.path.expandvars(os.path.expanduser(str(cfg.get("central_spotify_token_file") or ""))).strip()
    CENTRAL_SPOTIFY_TOKENS = {
        "access_token": cfg.get("spotify_access_token") or None,
        "refresh_token": cfg.get("spotify_refresh_token") or None,
        "expires_at": cfg.get("spotify_expires_at") or 0,
        "scope": cfg.get("spotify_scope") or "",
    }
    _migrate_root_data_files_to_subdirs()
    REDIRECT_URI_OV = cfg.get("redirect_uri", REDIRECT_URI_OV)

    COOLDOWN_MINUTES        = int(cfg.get("cooldown_minutes", COOLDOWN_MINUTES))
    PLAYLIST_PREFIX         = cfg.get("playlist_prefix", PLAYLIST_PREFIX)
    PLAYLIST_COVER_ENABLED  = bool(cfg.get("playlist_cover_enabled", PLAYLIST_COVER_ENABLED))
    PLAYLIST_COVER_FILE     = str(cfg.get("playlist_cover_file", PLAYLIST_COVER_FILE) or "")
    SRPLUS_DURATION_MIN     = int(cfg.get("srplus_duration_min", SRPLUS_DURATION_MIN))
    SRPLUS_ONCE_PER_STREAM  = bool(cfg.get("srplus_once_per_stream", SRPLUS_ONCE_PER_STREAM))
    SRPLUS_SHUFFLE          = bool(cfg.get("srplus_shuffle", SRPLUS_SHUFFLE))
    SRPLUS_SUBSCRIBERS_ONLY = bool(cfg.get("srplus_subscribers_only", SRPLUS_SUBSCRIBERS_ONLY))

    ENABLED               = bool(cfg.get("enabled", ENABLED))
    AUTO_STOP_ON_DISABLE  = bool(cfg.get("auto_stop_on_disable", AUTO_STOP_ON_DISABLE))

    REPEAT_GUARD      = bool(cfg.get("repeat_guard", REPEAT_GUARD))
    PLAY_NOW          = bool(cfg.get("play_now", PLAY_NOW))
    QUEUE_THEN_SKIP   = bool(cfg.get("queue_then_skip", QUEUE_THEN_SKIP))
    ASYNC_PLAYLIST_ADD= bool(cfg.get("async_playlist_add", ASYNC_PLAYLIST_ADD))
    ASYNC_COVER_FETCH = bool(cfg.get("async_cover_fetch", ASYNC_COVER_FETCH))

    LOG_VERBOSE       = bool(cfg.get("log_verbose", LOG_VERBOSE))
    LOG_SLOW_MS       = int(cfg.get("log_slow_ms", LOG_SLOW_MS))
    LOG_DEDUP_SEC     = int(cfg.get("log_dedup_sec", LOG_DEDUP_SEC))
    LOG_NP_ON_CHANGE  = bool(cfg.get("log_np_on_change", LOG_NP_ON_CHANGE))

    NOWPLAYING_ENABLE_FILES = bool(cfg.get("nowplaying_enable_files", NOWPLAYING_ENABLE_FILES))
    NOWPLAYING_POLL_MS      = int(cfg.get("poll_ms", NOWPLAYING_POLL_MS))

    # Twitch main/bot settings
    TWITCH_LISTEN        = bool(cfg.get("twitch_listen", TWITCH_LISTEN))
    TWITCH_REPLY         = bool(cfg.get("twitch_reply", TWITCH_REPLY))
    TWITCH_CHANNEL       = (cfg.get("twitch_channel", TWITCH_CHANNEL) or "").strip().lstrip("#")
    TWITCH_BOT_CHANNEL   = (cfg.get("twitch_bot_channel", TWITCH_BOT_CHANNEL) or "").strip().lstrip("#")
    TWITCH_MAIN_CLIENT_ID     = cfg.get("twitch_main_client_id", TWITCH_MAIN_CLIENT_ID)
    TWITCH_MAIN_CLIENT_SECRET = cfg.get("twitch_main_client_secret", TWITCH_MAIN_CLIENT_SECRET)
    TWITCH_MAIN_SCOPES        = cfg.get("twitch_main_scopes", TWITCH_MAIN_SCOPES)
    TWITCH_MAIN_REDIRECT_OV   = cfg.get("twitch_main_redirect_uri", TWITCH_MAIN_REDIRECT_OV)
    TWITCH_BOT_CLIENT_ID      = cfg.get("twitch_bot_client_id", TWITCH_BOT_CLIENT_ID)
    TWITCH_BOT_CLIENT_SECRET  = cfg.get("twitch_bot_client_secret", TWITCH_BOT_CLIENT_SECRET)
    TWITCH_BOT_SCOPES         = cfg.get("twitch_bot_scopes", TWITCH_BOT_SCOPES)
    TWITCH_BOT_REDIRECT_OV    = cfg.get("twitch_bot_redirect_uri", TWITCH_BOT_REDIRECT_OV)
    TWITCH_CMD_SR             = cfg.get("twitch_cmd_sr", TWITCH_CMD_SR)
    TWITCH_CMD_SRPLUS         = cfg.get("twitch_cmd_srplus", TWITCH_CMD_SRPLUS)
    TWITCH_CMD_YT             = cfg.get("youtube_cmd", cfg.get("twitch_cmd_yt", TWITCH_CMD_YT)) or "!yt"
    YOUTUBE_ENABLED           = bool(cfg.get("youtube_enabled", YOUTUBE_ENABLED))
    YOUTUBE_MAX_DURATION_SEC  = int(cfg.get("youtube_max_duration_sec", YOUTUBE_MAX_DURATION_SEC))
    YOUTUBE_AUTOPLAY          = bool(cfg.get("youtube_autoplay", YOUTUBE_AUTOPLAY))
    YOUTUBE_PLAYER_MODE       = (cfg.get("youtube_player_mode", YOUTUBE_PLAYER_MODE) or "ytmusic").strip().lower()
    if YOUTUBE_PLAYER_MODE not in ("ytmusic", "iframe"):
        YOUTUBE_PLAYER_MODE = "ytmusic"
    YOUTUBE_AUDIO_OUTPUT_NAME = str(cfg.get("youtube_audio_output_name", YOUTUBE_AUDIO_OUTPUT_NAME) or "Default").strip() or "Default"
    _YT_WEBVIEW_STATUS["audio_selected"] = YOUTUBE_AUDIO_OUTPUT_NAME

    # Manually saved Meld Elements links from the UI.
    # These must be the same links the user enters; do not force-generate or replace them.
    MELD_ARTIST_URL = (cfg.get("meld_artist_url", MELD_ARTIST_URL) or "").strip()
    MELD_SONG_URL = (cfg.get("meld_song_url", MELD_SONG_URL) or "").strip()
    MELD_COVER_URL = (cfg.get("meld_cover_url", MELD_COVER_URL) or "").strip()
    OVERLAY_MARQUEE_MODE = (cfg.get("overlay_marquee_mode", OVERLAY_MARQUEE_MODE) or "bounce").strip().lower()
    if OVERLAY_MARQUEE_MODE not in ("bounce", "scroll-ltr", "scroll-rtl", "off"):
        OVERLAY_MARQUEE_MODE = "bounce"
    try:
        OVERLAY_MARQUEE_SPEED = max(10, min(400, int(cfg.get("overlay_marquee_speed", OVERLAY_MARQUEE_SPEED))))
    except Exception:
        OVERLAY_MARQUEE_SPEED = 45

    SR_SOURCE                 = (cfg.get("sr_source", SR_SOURCE) or "twitch").strip().lower()
    if SR_SOURCE not in ("twitch", "external_file"):
        SR_SOURCE = "twitch"
    EXTERNAL_SR_FILE          = _normalize_external_sr_file(cfg.get("external_sr_file", EXTERNAL_SR_FILE))
    TWITCH_REPLY_SENDER       = cfg.get("twitch_reply_sender", TWITCH_REPLY_SENDER)

    # Twitch manual overrides
    TWITCH_MAIN_LOGIN_OVERRIDE = cfg.get("twitch_main_login_override", TWITCH_MAIN_LOGIN_OVERRIDE)
    TWITCH_MAIN_TOKEN_OVERRIDE = cfg.get("twitch_main_token_override", TWITCH_MAIN_TOKEN_OVERRIDE)
    TWITCH_BOT_LOGIN_OVERRIDE  = cfg.get("twitch_bot_login_override", TWITCH_BOT_LOGIN_OVERRIDE)
    TWITCH_BOT_TOKEN_OVERRIDE  = cfg.get("twitch_bot_token_override", TWITCH_BOT_TOKEN_OVERRIDE)

    # Twitch NowPlaying announce (NEU)
    TWITCH_NP_ON_CHANGE    = bool(cfg.get("twitch_np_on_change", TWITCH_NP_ON_CHANGE))
    TWITCH_NP_FORMAT       = cfg.get("twitch_np_format", TWITCH_NP_FORMAT) or TWITCH_NP_FORMAT
    TWITCH_NP_COOLDOWN_SEC = int(cfg.get("twitch_np_cooldown_sec", TWITCH_NP_COOLDOWN_SEC))

    # OBS WebSocket settings (accept both keys; UI sends obs_ws_enabled)
    OBS_WS_ENABLED       = bool(cfg.get("obs_ws_enabled", cfg.get("obs_enable", OBS_WS_ENABLED)))
    OBS_WS_HOST          = cfg.get("obs_ws_host", cfg.get("obs_host", OBS_WS_HOST))
    OBS_WS_PORT          = int(cfg.get("obs_ws_port", cfg.get("obs_port", OBS_WS_PORT)))
    OBS_WS_PASSWORD      = cfg.get("obs_ws_password", cfg.get("obs_password", OBS_WS_PASSWORD))
    OBS_FILTER1_SOURCE   = cfg.get("obs_filter1_source", cfg.get("filter1_source", OBS_FILTER1_SOURCE))
    OBS_FILTER1_NAME     = cfg.get("obs_filter1_name",   cfg.get("filter1_name",   OBS_FILTER1_NAME))
    OBS_FILTER1_ENABLE   = bool(cfg.get("obs_filter1_enable", cfg.get("filter1_enable", OBS_FILTER1_ENABLE)))
    OBS_FILTER2_SOURCE   = cfg.get("obs_filter2_source", cfg.get("filter2_source", OBS_FILTER2_SOURCE))
    OBS_FILTER2_NAME     = cfg.get("obs_filter2_name",   cfg.get("filter2_name",   OBS_FILTER2_NAME))
    OBS_FILTER2_ENABLE   = bool(cfg.get("obs_filter2_enable", cfg.get("filter2_enable", OBS_FILTER2_ENABLE)))
    OBS_FILTER_DELAY_SEC = int(cfg.get("obs_filter_delay_sec", cfg.get("filter_delay_sec", OBS_FILTER_DELAY_SEC)))
    OBS_FILTER_AUTO_ON_NP_CHANGE = bool(cfg.get("obs_filter_auto_on_np_change", cfg.get("filter_auto_on_np_change", OBS_FILTER_AUTO_ON_NP_CHANGE)))
    OBS_COVER_BROWSER_SOURCE = cfg.get("obs_cover_browser_source", cfg.get("cover_browser_source", OBS_COVER_BROWSER_SOURCE))
    OBS_COVER_IMAGE_SOURCE   = cfg.get("obs_cover_image_source",   cfg.get("cover_image_source",   OBS_COVER_IMAGE_SOURCE))
    COVER_IMAGE_SIZE         = int(cfg.get("cover_image_size", COVER_IMAGE_SIZE))
    COVER_IMAGE_SIZE         = COVER_IMAGE_SIZE if COVER_IMAGE_SIZE in (64,300,640) else 300

    _restart_twitch_thread_if_needed()
    _restart_external_sr_thread_if_needed()

def get_health() -> Dict[str,Any]:
    channel = TWITCH_CHANNEL if TWITCH_REPLY_SENDER == "main" else (TWITCH_BOT_CHANNEL or TWITCH_CHANNEL)
    return {"enabled": ENABLED, "spotify": _is_authorized(),
            "spotify_token_scope": str(_read_tokens().get("scope") or ""),
            "twitch_main": _twitch_is_authorized("main"),
            "twitch_bot": _twitch_is_authorized("bot"),
            "reply_sender": TWITCH_REPLY_SENDER,
            "twitch_listen": TWITCH_LISTEN, "channel": channel,
            "sr_source": SR_SOURCE, "external_sr_file": _normalize_external_sr_file(EXTERNAL_SR_FILE),
            "np_updated_at": NOWPLAYING.get("updated_at",0),
            "active_provider": (_overlay_current().get("provider") or "spotify"),
            "data_dir": TOKENS_DIR, "obs_ws_enabled": OBS_WS_ENABLED,
            "obs_ws_connected": _OBS_CLIENT.connected if OBS_WS_ENABLED else False,
            "youtube_enabled": YOUTUBE_ENABLED, "youtube_cmd": TWITCH_CMD_YT, "youtube_player_mode": YOUTUBE_PLAYER_MODE, "youtube_audio_output_name": YOUTUBE_AUDIO_OUTPUT_NAME, "youtube_queue_len": len(_YT_QUEUE), "youtube_webview": dict(_YT_WEBVIEW_STATUS), "youtube_webview_running": bool(_YT_WEBVIEW_STATUS.get("running") and (_now() - float(_YT_WEBVIEW_STATUS.get("ts") or 0) < 6))}

def get_cover_path(size=300) -> str:
    return _p_cover(size)

# ---- Public OBS helpers for UI ----
def obs_test_connection() -> Dict[str, Any]:
    ok = _obs_connect()
    return {"ok": ok, "connected": _OBS_CLIENT.connected, "error": (None if ok else "connect failed")}

def obs_set_filter(source_name: str, filter_name: str, enabled: bool) -> Dict[str, Any]:
    ok = _obs_connect() and _OBS_CLIENT.set_filter_visibility(source_name, filter_name, enabled)
    return {"ok": bool(ok)}

def obs_trigger_filter_sequence(delay_override: Optional[int] = None) -> Dict[str, Any]:
    def _runner():
        _obs_trigger_filter_sequence(delay_override=delay_override)
    _THREAD_POOL.submit(_runner)
    return {"ok": True, "queued": True}

def obs_update_cover() -> Dict[str, Any]:
    ok = _obs_update_cover_display()
    return {"ok": bool(ok)}

# ---- Start/Stop ----
def start(): start_server()
def stop():
    stop_server()
    try: _THREAD_POOL.shutdown(wait=False)
    except: pass

# ---- Compatibility snapshot for older UIs / runners ----
DATA = {
    "port": PORT,
    "tokens_dir": TOKENS_DIR,
    "redirect_uri": REDIRECT_URI_OV
}

# UI helper: keep old overlay endpoint discovery available for the app.
def get_endpoint_urls():
    return _overlay_endpoint_urls()
