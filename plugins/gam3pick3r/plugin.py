from __future__ import annotations

import html
import json
import os
import random
import re
import socket
import ssl
import shutil
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional

try:
    from PySide6 import QtWidgets
except Exception:  # pragma: no cover
    QtWidgets = None  # type: ignore

from godisalotachat.models import PluginStatus
from godisalotachat.plugin_base import PluginHost
from plugins.plugin_common import ThreadedPlugin

PLUGIN_DIR = Path(__file__).resolve().parent

def _main_data_dir(plugin_name: str) -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name.lower() == 'plugins':
            return parent.parent / 'data' / plugin_name
    return PLUGIN_DIR / 'data'

DATA_DIR = _main_data_dir('gam3pick3r')
COVERS_DIR = DATA_DIR / 'covers'
BACKGROUNDS_DIR = DATA_DIR / 'backgrounds'
GAMES_FILE = DATA_DIR / 'games.json'
STATE_FILE = DATA_DIR / 'state.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'
TWITCH_BROADCAST_CACHE_FILE = DATA_DIR / 'twitch_broadcast_oauth_cache.json'
GAM3PICK3R_SYSTEM_MARKER = '\u2063\u200b\u2063\u200b\u2063'

TWITCH_IRC_HOST = 'irc.chat.twitch.tv'
TWITCH_IRC_PORT_SSL = 6697
TWITCH_TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
TWITCH_VALIDATE_URL = 'https://id.twitch.tv/oauth2/validate'
TWITCH_HELIX_URL = 'https://api.twitch.tv/helix'
STEAMGRIDDB_API = 'https://www.steamgriddb.com/api/v2'
YOUTUBE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
KICK_TOKEN_URL = 'https://id.kick.com/oauth/token'
KICK_CHANNELS_URL = 'https://api.kick.com/public/v1/channels'
KICK_CATEGORIES_URL = 'https://api.kick.com/public/v2/categories'



def secrets_token() -> str:
    try:
        import secrets
        return secrets.token_urlsafe(12)
    except Exception:
        return str(int(time.time() * 1000))

def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'ja', 'on', 'enabled', 'aktiv'}:
        return True
    if text in {'0', 'false', 'no', 'nein', 'off', 'disabled', 'aus'}:
        return False
    return default


def _to_int(value: Any, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        n = int(float(str(value).strip()))
    except Exception:
        n = default
    if min_value is not None:
        n = max(min_value, n)
    if max_value is not None:
        n = min(max_value, n)
    return n


def _clean_platform(value: Any) -> str:
    p = str(value or '').strip().lower()
    if p in {'tt', 'tiktok_live'}:
        return 'tiktok'
    if p in {'tw', 'twitch_chat'}:
        return 'twitch'
    if p in {'yt', 'youtube_live'}:
        return 'youtube'
    if p in {'kick_chat'}:
        return 'kick'
    return p


def _safe_text(value: Any) -> str:
    return str(value or '').strip()


def _split_tags(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        parts = re.split(r'[,;\n]+', str(raw or ''))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = str(part or '').strip().lstrip('#')
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _msg_get(msg: Any, *names: str, default: Any = '') -> Any:
    if isinstance(msg, dict):
        for name in names:
            if name in msg and msg.get(name) is not None:
                return msg.get(name)
        return default
    for name in names:
        try:
            value = getattr(msg, name)
            if value is not None:
                return value
        except Exception:
            pass
    return default


def _safe_asset_name(name: str, fallback: str = 'asset') -> str:
    raw = Path(str(name or fallback)).name.strip() or fallback
    stem = re.sub(r'[^A-Za-z0-9._ -]+', '_', raw).strip(' ._') or fallback
    return stem


class _OverlayState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {
            'ts': time.time(),
            'mode': 'idle',
            'title': 'gam3pick3r',
            'greenscreen': '#00FF00',
            'games': [],
            'picked': None,
            'rolling_until': 0.0,
            'vote_active': False,
            'vote_end_at': 0.0,
            'vote_games': [],
            'vote_votes': {},
        }

    def set(self, **kwargs: Any) -> None:
        with self._lock:
            self.data.update(kwargs)
            self.data['ts'] = time.time()

    def get(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self.data)
            out['server_now'] = time.time()
            return out


class _OverlayHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        srv: '_OverlayServer' = self.server  # type: ignore[assignment]
        if self.path == '/' or self.path.startswith('/index.html'):
            self._send_html(srv.index_html())
            return
        if self.path.startswith('/state'):
            payload = json.dumps(srv.state.get(), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.startswith('/covers/'):
            rel = urllib.parse.unquote(self.path[len('/covers/'):]).replace('\\', '/').split('?', 1)[0]
            path = (COVERS_DIR / rel).resolve()
            if not str(path).startswith(str(COVERS_DIR.resolve())) or not path.exists() or not path.is_file():
                self.send_response(404); self.end_headers(); return
            mime = 'image/png'
            ext = path.suffix.lower()
            if ext in {'.jpg', '.jpeg'}:
                mime = 'image/jpeg'
            elif ext == '.webp':
                mime = 'image/webp'
            elif ext == '.bmp':
                mime = 'image/bmp'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(path.read_bytes())
            return
        if self.path.startswith('/background'):
            path_value = str(srv.state.get().get('bg_image_path') or '')
            path = srv.resolve_background(path_value)
            if not path or not path.exists() or not path.is_file():
                self.send_response(404); self.end_headers(); return
            ext = path.suffix.lower()
            mime = 'image/png'
            if ext in {'.jpg', '.jpeg'}:
                mime = 'image/jpeg'
            elif ext == '.webp':
                mime = 'image/webp'
            elif ext == '.bmp':
                mime = 'image/bmp'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(path.read_bytes())
            return

        self.send_response(404)
        self.end_headers()

    def _send_html(self, text: str) -> None:
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(text.encode('utf-8'))


class _OverlayServer(HTTPServer):
    def __init__(self, port: int, state: _OverlayState):
        self.state = state
        super().__init__(('127.0.0.1', self._free_port(port)), _OverlayHandler)
        self._thread: threading.Thread | None = None

    @staticmethod
    def _free_port(preferred: int) -> int:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', int(preferred)))
                return int(preferred)
        except Exception:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', 0))
                return int(s.getsockname()[1])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.serve_forever, daemon=True, name='gam3pick3r-overlay')
        self._thread.start()

    def stop(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            self.server_close()
        except Exception:
            pass

    def resolve_background(self, value: str) -> Path | None:
        raw = str(value or '').strip().strip('"')
        if not raw:
            return None
        candidates: list[Path] = []
        p = Path(raw)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.extend([BACKGROUNDS_DIR / raw, COVERS_DIR / raw, PLUGIN_DIR / raw, DATA_DIR / raw])
        try:
            for c in candidates:
                r = c.resolve()
                allowed = [BACKGROUNDS_DIR.resolve(), COVERS_DIR.resolve(), PLUGIN_DIR.resolve(), DATA_DIR.resolve()]
                if p.is_absolute() or any(str(r).startswith(str(a)) for a in allowed):
                    if r.exists() and r.is_file():
                        return r
        except Exception:
            return None
        return None

    def index_html(self) -> str:
        return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>gam3pick3r</title><style>
*{box-sizing:border-box;margin:0;padding:0}html,body{width:100%;height:100%;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#00ff00;background-size:cover;background-position:center;background-repeat:no-repeat;color:white}.screen{position:fixed;inset:0;display:none}.screen.show{display:flex}.vote-screen{flex-direction:column;padding:46px 24px 40px;min-height:0}.top{flex:0 0 auto;text-align:center;margin-bottom:0;display:flex;gap:22px;align-items:center;justify-content:center;flex-wrap:wrap}.pill{display:inline-block;background:rgba(0,0,0,.72);color:white;font-size:28px;font-weight:850;padding:10px 30px;border-radius:50px;border:2px solid rgba(255,255,255,.2);backdrop-filter:blur(5px);box-shadow:0 4px 20px rgba(0,0,0,.5)}.pill span{color:#a85eff;margin-right:8px}.leader{max-width:min(900px,80vw);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.leader small{opacity:.7;font-size:.72em;margin-right:8px}.spacer{flex:1 1 auto;min-height:20px}.games-section{flex:0 1 auto;display:flex;flex-wrap:wrap;gap:17px;justify-content:center;align-content:flex-end;align-items:flex-end;overflow:visible;padding:0 0 28px;min-height:0;max-height:calc(100vh - 155px)}.vote-card{background:rgba(20,20,20,.78);border-radius:14px;padding:11px;width:clamp(180px,12vw,210px);min-width:180px;height:min(372px,calc(100vh - 190px));min-height:300px;flex:0 0 auto;display:flex;flex-direction:column;box-shadow:0 5px 19px rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(5px);overflow:hidden}.vote-card.fadeout{opacity:0;transform:translateY(10px) scale(.98);transition:opacity 900ms ease,transform 900ms ease}.cover-container{width:100%;flex:1 1 auto;min-height:0;border-radius:9px;overflow:hidden;background:transparent;margin-bottom:10px;border:0;display:flex;align-items:flex-start;justify-content:center}.cover-image{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;object-position:top center;background:transparent;display:block;image-rendering:auto}.no-cover{width:100%;height:100%;background:linear-gradient(135deg,#2a2a2a,#1a1a1a);display:flex;align-items:center;justify-content:center;color:#777;font-size:14px}.title{flex:0 0 auto;color:white;font-size:15px;font-weight:780;margin:0 0 9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}.vote-stats{flex:0 0 auto;display:flex;align-items:flex-end;justify-content:space-between;gap:9px;margin-top:auto;padding-top:1px}.vote-left{display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-end;gap:4px;min-width:0}.vote-command{color:rgba(255,255,255,.76);font-size:16px;font-weight:900;line-height:1;text-shadow:0 1px 5px rgba(0,0,0,.55);white-space:nowrap}.vote-count{color:#aaa;font-size:12px;font-weight:650;white-space:nowrap}.vote-count span{color:#a85eff;font-size:18px;font-weight:850;margin-right:3px}.bar-container{width:18px;height:55px;background:rgba(0,0,0,.5);border-radius:9px;overflow:hidden;display:flex;flex-direction:column-reverse;border:1px solid rgba(255,255,255,.1)}.bar-fill{width:100%;height:0%;background:linear-gradient(180deg,#a85eff,#7c3aed);transition:height .3s ease}.picker-screen{align-items:center;justify-content:center}.picker-card{width:min(780px,calc(100% - 80px));height:min(980px,calc(100% - 80px));border-radius:22px;background:rgba(18,18,18,.82);border:1px solid rgba(255,255,255,.12);box-shadow:0 18px 60px rgba(0,0,0,.55);padding:22px;display:flex;flex-direction:column;gap:16px}.picker-cover{flex:1;border-radius:16px;overflow:hidden;position:relative;background:rgba(0,0,0,.35)}.picker-cover .bg,.winner-card .bg{position:absolute;inset:-18px;width:calc(100% + 36px);height:calc(100% + 36px);object-fit:cover;filter:blur(18px);transform:scale(1.08);opacity:.95}.picker-cover .shade,.winner-card .bgShade{position:absolute;inset:0;background:radial-gradient(ellipse at center,rgba(0,0,0,.1) 0%,rgba(0,0,0,.58) 100%)}.picker-cover .fgWrap,.winner-card .fgWrap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:18px}.picker-cover .fg,.winner-card .fg{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.18);background:rgba(0,0,0,.18);display:block}.picker-row{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:-6px}.picker-title{flex:1;font-size:22px;font-weight:750;color:rgba(255,255,255,.95);letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.picker-timer{font-size:14px;font-weight:700;color:rgba(255,255,255,.8)}.picker-sub{font-size:14px;color:rgba(255,255,255,.65)}.count{position:absolute;inset:0;display:none;align-items:center;justify-content:center;font-size:46px;font-weight:900;color:rgba(255,255,255,.92);text-shadow:0 8px 30px rgba(0,0,0,.8);background:rgba(0,0,0,.18);backdrop-filter:blur(6px)}.win{position:absolute;inset:0;pointer-events:none;display:none;z-index:10}.win.show{display:block}.win .winText{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:46px;font-weight:950;letter-spacing:1px;color:rgba(255,255,255,.92);text-shadow:0 0 18px rgba(170,120,255,.55),0 10px 40px rgba(0,0,0,.75);animation:winnerPulse 1400ms ease-in-out infinite}@keyframes winnerPulse{0%{opacity:.35;transform:scale(.98)}50%{opacity:1;transform:scale(1.03)}100%{opacity:.45;transform:scale(.99)}}.win:before{content:"";position:absolute;left:50%;top:50%;width:32px;height:32px;border-radius:999px;transform:translate(-50%,-50%) scale(.2);box-shadow:0 0 0 2px rgba(170,120,255,.65),0 0 28px rgba(170,120,255,.35),0 0 80px rgba(170,120,255,.22);animation:pop 900ms cubic-bezier(.2,.9,.2,1) forwards}.win:after{content:"";position:absolute;inset:-12px;background:radial-gradient(circle at center,rgba(170,120,255,.18) 0%,rgba(0,0,0,0) 55%);animation:fade 1200ms ease-out forwards}@keyframes pop{0%{transform:translate(-50%,-50%) scale(.2);opacity:0}20%{opacity:1}100%{transform:translate(-50%,-50%) scale(8);opacity:0}}@keyframes fade{0%{opacity:0}15%{opacity:1}100%{opacity:0}}.winner-overlay{position:fixed;inset:0;display:none;align-items:center;justify-content:center;z-index:2000;pointer-events:none;background:rgba(0,0,0,0);transition:background 900ms ease}.winner-overlay.show{display:flex;background:rgba(0,0,0,.55)}.winner-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;width:min(92vw,920px)}.winner-title{position:relative;z-index:4000;top:-60px;text-align:center;color:rgba(255,255,255,.95);font-weight:900;font-size:44px;text-shadow:0 8px 26px rgba(0,0,0,.78);padding:0 22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}.winner-card{width:min(760px,70vw);aspect-ratio:16/9;border-radius:18px;overflow:hidden;border:2px solid rgba(255,255,255,.35);box-shadow:0 18px 70px rgba(0,0,0,.75);transform:scale(1);transition:transform 2200ms ease;background:rgba(18,18,18,.9);position:relative}.winner-overlay.show .winner-card{transform:scale(1.14)}.status-message{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);color:white;font-size:24px;font-weight:650;text-shadow:0 2px 10px rgba(0,0,0,.5);background:rgba(0,0,0,.7);padding:16px 32px;border-radius:40px;border:1px solid rgba(255,255,255,.2);z-index:1000}
</style></head><body>
<div id='voteScreen' class='screen vote-screen'><div class='top'><div class='pill' id='timer'><span>⏱</span> 00:00</div><div class='pill leader' id='leader'><small>Führend</small>-</div></div><div class='spacer'></div><div class='games-section' id='gamesContainer'></div></div>
<div id='pickerScreen' class='screen picker-screen'><div class='picker-card'><div class='picker-cover'><img id='pickBg' class='bg' style='display:none'/><div id='pickShade' class='shade' style='display:none'></div><div class='fgWrap'><img id='pickFg' class='fg' style='display:none'/></div><div id='pickCount' class='count'></div><div id='pickWin' class='win'><div class='winText'>WINNER</div></div></div><div class='picker-row'><div id='pickTitle' class='picker-title'>gam3pick3r</div><div id='pickTimer' class='picker-timer'></div></div><div id='pickSub' class='picker-sub'></div></div></div>
<div id='winnerOverlay' class='winner-overlay'><div class='winner-wrap'><div id='winnerTitle' class='winner-title'></div><div class='winner-card'><img id='winnerBg' class='bg'/><div class='bgShade'></div><div class='fgWrap'><img id='winnerFg' class='fg'/></div></div></div></div><div id='status' class='status-message' style='display:none'>Overlay wird geladen...</div>
<script>
const voteScreen=document.getElementById('voteScreen'),pickerScreen=document.getElementById('pickerScreen'),gamesContainer=document.getElementById('gamesContainer'),timerEl=document.getElementById('timer'),leaderEl=document.getElementById('leader'),statusEl=document.getElementById('status'),winnerOverlay=document.getElementById('winnerOverlay'),winnerBg=document.getElementById('winnerBg'),winnerFg=document.getElementById('winnerFg'),winnerTitle=document.getElementById('winnerTitle'),pickBg=document.getElementById('pickBg'),pickFg=document.getElementById('pickFg'),pickShade=document.getElementById('pickShade'),pickTitle=document.getElementById('pickTitle'),pickTimer=document.getElementById('pickTimer'),pickSub=document.getElementById('pickSub'),pickWin=document.getElementById('pickWin');let prevVote=false,endAnim=false,lastPicked='';function esc(t){return String(t||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}function fmt(seconds){seconds=Math.max(0,Math.floor(Number(seconds||0)));let m=Math.floor(seconds/60),s=seconds%60;return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')}function coverUrl(g){if(!g)return'';if(g.cover_url)return g.cover_url;if(g.cover)return'/covers/'+encodeURIComponent(g.cover);return''}function voteWinner(s){let gs=s&&s.vote_games?s.vote_games:[],vs=s&&s.vote_votes?s.vote_votes:{};if(!gs.length)return null;let best=null,bv=-999999;for(const g of gs){let v=Number(vs[String(g.id)]||0);if(best===null||v>bv){best=g;bv=v}}return best}function showScreen(which){voteScreen.classList.toggle('show',which==='vote');pickerScreen.classList.toggle('show',which==='picker')}function applyBg(s){let col=s&&s.greenscreen?String(s.greenscreen):'#00ff00';document.body.style.backgroundColor=col;let bg=s&&s.bg_image?s.bg_image:null;if(bg&&bg.enabled&&bg.url){document.body.style.backgroundImage=`url('${bg.url}')`;let mode=String(bg.mode||'cover');document.body.style.backgroundSize=mode==='contain'?'contain':(mode==='stretch'?'100% 100%':'cover');document.body.style.backgroundPosition='center';document.body.style.backgroundRepeat='no-repeat'}else document.body.style.backgroundImage='none'}function show(m,e=false){statusEl.style.display='block';statusEl.textContent=m;statusEl.style.background=e?'rgba(180,40,40,.9)':'rgba(0,0,0,.7)'}function hide(){statusEl.style.display='none'}function setPicker(g){let c=coverUrl(g);pickTitle.textContent=g&&g.title?g.title:'gam3pick3r';if(c){pickBg.src=c;pickFg.src=c;pickBg.style.display='block';pickFg.style.display='block';pickShade.style.display='block'}else{pickBg.style.display='none';pickFg.style.display='none';pickShade.style.display='none'}}function renderPicker(d){showScreen('picker');winnerOverlay.classList.remove('show');let mode=String(d&&d.mode||'idle'),gs=(d&&d.games)||[];if(mode==='rolling'&&gs.length){hide();let start=Number(d.roll_start||0),dur=Math.max(1,Number(d.roll_duration_sec||d.roll_duration||1)),step=Math.max(0.15,Number(d.roll_step_sec||d.random_switch_interval_sec||1)),now=Date.now()/1000,t=Math.max(0,Math.min(1,(now-start)/dur));let idx=Math.floor(Math.max(0,now-start)/step)%gs.length;setPicker(gs[idx]);pickTimer.textContent='⏱ '+fmt(Math.ceil((Number(d.rolling_until||0)||now)-now));pickSub.textContent='Random Picker läuft';pickWin.classList.remove('show');return}if((mode==='picked'||d.picked)&&d.picked){hide();setPicker(d.picked);pickTimer.textContent='';pickSub.textContent='';let gid=String(d.picked.id||'');if(gid&&gid!==lastPicked){lastPicked=gid;pickWin.classList.remove('show');void pickWin.offsetWidth;pickWin.classList.add('show');setTimeout(()=>pickWin.classList.remove('show'),Number(d.winner_anim_ms||5200))}return}if(gs.length){hide();setPicker(gs[0]);pickTimer.textContent='';pickSub.textContent='Bereit';}else{setPicker(null);show('Keine Spiele verfügbar')}}function runEnd(s){if(endAnim)return;endAnim=true;let w=voteWinner(s);try{gamesContainer.querySelectorAll('.vote-card').forEach(c=>c.classList.add('fadeout'))}catch(e){}if(w){winnerTitle.textContent=w.title||'';let c=coverUrl(w);winnerBg.src=c;winnerFg.src=c;if(c)winnerOverlay.classList.add('show')}setTimeout(()=>{endAnim=false},5200)}function renderVote(d){showScreen('vote');applyBg(d);let end=d&&d.vote_end_at?d.vote_end_at:0,now=Date.now()/1000;timerEl.innerHTML='<span>⏱</span> '+fmt(Math.ceil(end-now));if(!d||!d.vote_active){if(prevVote){hide();runEnd(d);prevVote=false;return}show('Kein aktiver Vote');return}prevVote=true;winnerOverlay.classList.remove('show');let voteCmd=String((d&&d.vote_command)||'!vote').trim()||'!vote';let gs=d.vote_games||[],vs=d.vote_votes||{};if(!gs.length){gamesContainer.innerHTML='';show('Keine Spiele verfügbar');return}hide();let lead=voteWinner(d);leaderEl.innerHTML='<small>Führend</small>'+esc(lead&&lead.title?lead.title:'-');let max=1;gs.forEach(g=>max=Math.max(max,Number(vs[String(g.id)]||0)));let html='';gs.forEach(g=>{let id=String(g.id),vc=Number(vs[id]||0),pct=(vc/max)*100,c=coverUrl(g);let num=(g.num&&Number(g.num)>0)?Number(g.num):0;html+=`<div class='vote-card'><div class='title' title='${esc(g.title)}'>${esc(g.title)}</div><div class='cover-container'>${c?`<img class='cover-image' src='${c}' onerror="this.style.display='none';this.parentNode.innerHTML='<div class=\'no-cover\'>Kein Cover</div>';">`:`<div class='no-cover'>Kein Cover</div>`}</div><div class='vote-stats'><div class='vote-left'>${num?`<div class='vote-command'>${esc(voteCmd)} #${num}</div>`:''}<div class='vote-count'><span>${vc}</span> ${vc===1?'Stimme':'Stimmen'}</div></div><div class='bar-container'><div class='bar-fill' style='height:${pct}%;'></div></div></div></div>`});gamesContainer.innerHTML=html}function render(d){applyBg(d);let mode=String(d&&d.mode||'idle');if((d&&d.vote_active)||mode==='vote'){renderVote(d);return}renderPicker(d)}async function tick(){try{let d=await fetch('/state?t='+Date.now(),{cache:'no-store'}).then(r=>r.json());render(d)}catch(e){show('Verbindungsfehler…',true)}setTimeout(tick,200)}tick();
</script></body></html>"""


class _PopupWindow:
    def __init__(self, state: _OverlayState, title: str = 'gam3pick3r') -> None:
        self.state = state
        self.title = title
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._root = None
        self._labels: dict[str, Any] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name='gam3pick3r-window')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._root is not None:
                self._root.after(0, self._root.destroy)
        except Exception:
            pass

    def _run(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
            self._root = root
            root.title(self.title)
            root.geometry('520x620')
            root.configure(bg='#101018')
            root.attributes('-topmost', True)
            title = tk.Label(root, text='gam3pick3r', bg='#101018', fg='white', font=('Segoe UI', 24, 'bold'))
            mode = tk.Label(root, text='Bereit', bg='#101018', fg='#dddddd', font=('Segoe UI', 14))
            picked = tk.Label(root, text='', bg='#101018', fg='white', font=('Segoe UI', 22, 'bold'), wraplength=480)
            games = tk.Text(root, bg='#161622', fg='white', insertbackground='white', relief='flat', font=('Consolas', 12), height=22)
            title.pack(pady=(18, 4), padx=16, fill='x')
            mode.pack(pady=(0, 10), padx=16, fill='x')
            picked.pack(pady=(0, 14), padx=16, fill='x')
            games.pack(padx=16, pady=(0, 16), fill='both', expand=True)
            self._labels = {'title': title, 'mode': mode, 'picked': picked, 'games': games}

            def update() -> None:
                if self._stop.is_set():
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    return
                try:
                    data = self.state.get()
                    mode_name = str(data.get('mode') or 'idle')
                    title.configure(text=str(data.get('title') or 'gam3pick3r'))
                    mode.configure(text={'vote': 'Vote läuft', 'rolling': 'Random Picker läuft', 'picked': 'Gewinner', 'idle': 'Bereit'}.get(mode_name, mode_name))
                    p = data.get('picked') if isinstance(data.get('picked'), dict) else None
                    picked.configure(text=(p or {}).get('title', '') if p else '')
                    rows = []
                    src = data.get('vote_games') if data.get('vote_active') else data.get('games')
                    votes = data.get('vote_votes') if isinstance(data.get('vote_votes'), dict) else {}
                    for g in (src or []):
                        if not isinstance(g, dict):
                            continue
                        num = int(g.get('num') or 0)
                        prefix = f'{num}. ' if num else '- '
                        rows.append(f"{prefix}{g.get('title','')}   [{votes.get(str(g.get('id') or ''), 0)}]")
                    games.configure(state='normal')
                    games.delete('1.0', 'end')
                    games.insert('1.0', '\n'.join(rows))
                    games.configure(state='disabled')
                except Exception:
                    pass
                try:
                    root.after(500, update)
                except Exception:
                    pass
            update()
            root.mainloop()
        except Exception:
            return


class Gam3Pick3rPlugin(ThreadedPlugin):
    plugin_id = 'gam3pick3r'
    display_name = 'gam3pick3r'
    version = '0.17'
    description = 'Game picker / voting plugin. Reads chat messages from the main tool platforms; platform login stays in the main tool.'

    def __init__(self) -> None:
        super().__init__()
        self._host: PluginHost | None = None
        self._settings: dict[str, Any] = {}
        self._state = _OverlayState()
        self._server: _OverlayServer | None = None
        self._games: list[dict[str, Any]] = []
        self._votes: dict[str, int] = {}
        self._voted_users: dict[str, str] = {}
        self._vote_candidates: list[str] = []
        self._vote_num_map: dict[int, str] = {}
        self._vote_active = False
        self._vote_end_at = 0.0
        self._last_winner_id = ''
        self._picker_active = False
        self._picker_end_at = 0.0
        self._pending_pick_id = ''
        self._popup: _PopupWindow | None = None
        self._last_overlay_open_at = 0.0
        self._app_token_cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._recent_msg_keys: dict[str, float] = {}
        self._host_signal_connected = False

    def _load_plugin_settings(self) -> dict[str, Any]:
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._log(f'Plugin-Settings konnten nicht gelesen werden: {exc}')
        return {}

    def _save_plugin_settings(self, updates: dict[str, Any]) -> None:
        try:
            _ensure_dirs()
            data = self._load_plugin_settings()
            for k, v in dict(updates or {}).items():
                data[str(k)] = v
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            self._log(f'Plugin-Settings konnten nicht gespeichert werden: {exc}')

    def _stored_steamgriddb_key(self) -> str:
        key = _safe_text((self._settings or {}).get('steamgriddb_api_key'))
        if key:
            return key
        data = self._load_plugin_settings()
        return _safe_text(data.get('steamgriddb_api_key'))

    def settings_schema(self) -> list[dict[str, Any]]:
        games = self._load_games()
        schema: list[dict[str, Any]] = []

        schema.extend([
            {'key': 'enabled', 'tab': 'Main', 'label': 'Plugin aktiv', 'label_en': 'Plugin enabled', 'type': 'bool'},
        ])

        schema.extend([
            {'key': 'games_text', 'tab': 'Games', 'label': 'Spiele', 'label_en': 'Games', 'type': 'multiline', 'help': 'Eine Zeile pro Spiel: Titel | num=1 | steam=https://... | epic=https://... | cover=datei.png. Cover-Dateien liegen im Pluginordner covers/.', 'help_en': 'One game per line: Title | num=1 | steam=https://... | cover=file.png. Cover files stay in the plugin covers folder.'},
            {'key': 'game_search_name', 'tab': 'Games', 'label': 'Spiel per Name hinzufügen', 'label_en': 'Add game by name', 'placeholder': 'z.B. Schedule I'},
            {'key': 'button_add_game_by_name', 'tab': 'Games', 'type': 'button', 'label': 'Spielsuche', 'button_text': 'Spiel suchen + hinzufügen', 'button_text_en': 'Search + add game'},
            {'key': 'steamgriddb_api_key', 'tab': 'Games', 'label': 'SteamGridDB API Key optional', 'label_en': 'SteamGridDB API key optional', 'secret': True},
            {'key': 'button_load_games_to_field', 'tab': 'Games', 'type': 'button', 'label': 'Spiele laden', 'button_text': 'Aus Datei ins Feld laden', 'button_text_en': 'Load file into field'},
        ])

        if games:
            for idx, g in enumerate(games[:120], start=1):
                gid = str(g.get('id') or '').strip()
                title = self._game_title(g, idx, gid)
                if gid:
                    # Button text contains the title too, because the host can sometimes render
                    # button labels without the left label after a settings refresh.
                    schema.append({'key': f'button_delete_game__{gid}', 'tab': 'Delete', 'type': 'button', 'label': '', 'button_text': f'{title} löschen', 'button_text_en': f'Delete {title}', 'show_label': False})
        else:
            schema.append({'key': 'delete_empty', 'tab': 'Delete', 'type': 'separator', 'label': 'Keine Spiele gespeichert.'})

        if games:
            for idx, g in enumerate(games[:120], start=1):
                gid = str(g.get('id') or '').strip()
                title = self._game_title(g, idx, gid)
                if not gid:
                    continue
                schema.extend([
                    {'key': f'stream_title__{gid}', 'tab': 'Stream', 'label': f'{title} · Streamtitel', 'label_en': f'{title} · Stream title', 'placeholder': 'z.B. Jetzt: {game}', 'default': str(g.get('stream_title') or '')},
                    {'key': f'twitch_game_name__{gid}', 'tab': 'Stream', 'label': f'{title} · Twitch-Kategorie', 'label_en': f'{title} · Twitch category', 'placeholder': title, 'default': str(g.get('twitch_game_name') or title)},
                    {'key': f'kick_category__{gid}', 'tab': 'Stream', 'label': f'{title} · Kick-Kategorie', 'label_en': f'{title} · Kick category', 'placeholder': title, 'default': str(g.get('kick_category') or g.get('twitch_game_name') or title)},
                    {'key': f'youtube_category__{gid}', 'tab': 'Stream', 'label': f'{title} · YouTube Kategorie-ID', 'label_en': f'{title} · YouTube category ID', 'placeholder': '20 = Gaming', 'default': str(g.get('youtube_category') or '')},
                    {'key': f'tags__{gid}', 'tab': 'Stream', 'label': f'{title} · Tags', 'label_en': f'{title} · Tags', 'placeholder': 'tag1, tag2', 'default': ', '.join([str(x) for x in (g.get('tags') or [])])},
                ])
        else:
            schema.append({'key': 'streaminfo_empty', 'tab': 'Stream', 'type': 'separator', 'label': 'Noch keine Spiele gespeichert.'})

        schema.extend([
            {'key': 'vote_command', 'tab': 'Vote', 'label': 'Vote-Befehl', 'label_en': 'Vote command', 'placeholder': '!vote'},
            {'key': 'vote_duration_sec', 'tab': 'Vote', 'label': 'Vote-Dauer Sekunden', 'label_en': 'Vote duration seconds', 'type': 'number', 'min': 5, 'max': 7200},
            {'key': 'vote_use_all_enabled_games', 'tab': 'Vote', 'label': 'Alle Spiele als Vote-Kandidaten nutzen', 'label_en': 'Use all games as vote candidates', 'type': 'bool'},
            {'key': 'vote_candidate_count', 'tab': 'Vote', 'label': 'Kandidatenanzahl falls nicht alle', 'label_en': 'Candidate count if not all', 'type': 'number', 'min': 2, 'max': 100},
            {'key': 'vote_winner_chat_template', 'tab': 'Vote', 'label': 'Gewinnernachricht', 'label_en': 'Winner message', 'placeholder': 'The community has crowned {game} as the winner!'},
            {'key': 'button_start_vote', 'tab': 'Vote', 'type': 'button', 'label': 'Vote', 'button_text': 'Vote starten', 'button_text_en': 'Start vote'},
            {'key': 'button_stop_vote', 'tab': 'Vote', 'type': 'button', 'label': 'Vote', 'button_text': 'Vote stoppen', 'button_text_en': 'Stop vote'},
        ])

        schema.extend([
            {'key': 'random_pick_duration_sec', 'tab': 'Picker', 'label': 'Roll-Dauer Sekunden', 'label_en': 'Roll duration seconds', 'type': 'number', 'min': 1, 'max': 600},
            {'key': 'random_switch_interval_sec', 'tab': 'Picker', 'label': 'Spielwechsel alle Sekunden', 'label_en': 'Switch game every seconds', 'type': 'float', 'min': 0.2, 'max': 60, 'step': 0.1, 'decimals': 1},
            {'key': 'picker_winner_chat_template', 'tab': 'Picker', 'label': 'Gewinnernachricht', 'label_en': 'Winner message', 'placeholder': 'The random picker chose {game}!'},
            {'key': 'button_start_picker', 'tab': 'Picker', 'type': 'button', 'label': 'Random Picker', 'button_text': 'Random Picker starten', 'button_text_en': 'Start random picker'},
        ])

        schema.extend([
            {'key': 'link_command_general', 'tab': 'Chat', 'label': 'Link-Befehl', 'label_en': 'Link command', 'placeholder': '!link'},
            {'key': 'chat_send_links', 'tab': 'Chat', 'label': 'Links auf Befehl in Chat senden', 'label_en': 'Send links to chat on command', 'type': 'bool'},
            {'key': 'send_winner_to_chat', 'tab': 'Chat', 'label': 'Gewinner in Eingangsplattform schreiben', 'label_en': 'Send winner to source platform', 'type': 'bool'},
            {'key': 'accept_plain_votes', 'tab': 'Chat', 'label': 'Während Vote auch reine Zahl/Spielname akzeptieren', 'label_en': 'Accept plain number/name during vote', 'type': 'bool'},
            {'key': 'platforms_csv', 'tab': 'Chat', 'label': 'Plattformen', 'label_en': 'Platforms', 'placeholder': 'twitch,tiktok,youtube,kick', 'help': 'Leer = alle eingehenden Chatplattformen.', 'help_en': 'Empty = all incoming chat platforms.'},
        ])

        schema.extend([
            {'key': 'twitch_update_on_winner', 'tab': 'Twitch', 'label': 'Bei Gewinner Twitch Kategorie/Titel setzen', 'label_en': 'Set Twitch category/title on winner', 'type': 'bool'},
            {'key': 'twitch_update_tags', 'tab': 'Twitch', 'label': 'Tags aus Spieldaten setzen', 'label_en': 'Set tags from game data', 'type': 'bool'},
        ])

        schema.extend([
            {'key': 'youtube_update_on_winner', 'tab': 'YouTube', 'label': 'Bei Gewinner YouTube Titel setzen', 'label_en': 'Set YouTube title on winner', 'type': 'bool'},
            {'key': 'youtube_update_tags', 'tab': 'YouTube', 'label': 'Tags aus Spieldaten setzen', 'label_en': 'Set tags from game data', 'type': 'bool'},
            {'key': 'youtube_default_category', 'tab': 'YouTube', 'label': 'Standard Kategorie-ID', 'label_en': 'Default category ID', 'placeholder': '20 = Gaming'},
        ])

        schema.extend([
            {'key': 'kick_update_on_winner', 'tab': 'Kick', 'label': 'Bei Gewinner Kick Titel/Kategorie setzen', 'label_en': 'Set Kick title/category on winner', 'type': 'bool'},
            {'key': 'kick_update_tags', 'tab': 'Kick', 'label': 'Tags aus Spieldaten setzen', 'label_en': 'Set tags from game data', 'type': 'bool'},
        ])

        schema.extend([
            {'key': 'browser_overlay_enabled', 'tab': 'Overlay', 'label': 'Browser-Overlay aktiv', 'label_en': 'Browser overlay enabled', 'type': 'bool'},
            {'key': 'open_browser_on_action', 'tab': 'Overlay', 'label': 'Browser bei Vote/Picker öffnen', 'label_en': 'Open browser on vote/picker', 'type': 'bool'},
            {'key': 'open_window_on_action', 'tab': 'Overlay', 'label': 'Plugin-Fenster bei Vote/Picker öffnen', 'label_en': 'Open plugin window on vote/picker', 'type': 'bool'},
            {'key': 'button_open_overlay', 'tab': 'Overlay', 'type': 'button', 'label': 'Overlay', 'button_text': 'Browser-Overlay öffnen', 'button_text_en': 'Open browser overlay'},
            {'key': 'browser_overlay_port', 'tab': 'Overlay', 'label': 'Browser-Overlay Port', 'label_en': 'Browser overlay port', 'type': 'number', 'min': 1024, 'max': 65535},
            {'key': 'overlay_title', 'tab': 'Overlay', 'label': 'Overlay-Titel', 'label_en': 'Overlay title', 'placeholder': 'gam3pick3r'},
            {'key': 'greenscreen_hex', 'tab': 'Overlay', 'label': 'Greenscreen-Farbe', 'label_en': 'Greenscreen color', 'type': 'color'},
            {'key': 'overlay_background_enabled', 'tab': 'Overlay', 'label': 'Hintergrundbild aktiv', 'label_en': 'Background image enabled', 'type': 'bool'},
            {'key': 'overlay_background_image', 'tab': 'Overlay', 'label': 'Hintergrundbild Datei/Pfad', 'label_en': 'Background image file/path', 'placeholder': 'backgrounds/meinbild.png oder C:/.../bild.png'},
            {'key': 'button_choose_background', 'tab': 'Overlay', 'type': 'button', 'label': 'Hintergrundbild', 'button_text': 'Bild auswählen + ins Plugin kopieren', 'button_text_en': 'Choose image + copy into plugin'},
            {'key': 'overlay_background_mode', 'tab': 'Overlay', 'label': 'Hintergrundbild-Modus', 'label_en': 'Background mode', 'placeholder': 'cover, contain oder stretch'},
        ])
        return schema

    def _tab_key(self, tab: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', str(tab or '').strip().lower()).strip('_') or 'tab'

    def default_settings(self) -> dict[str, Any]:
        return {
            'enabled': True,
            'games_text': '',
            'game_search_name': '',
            'steamgriddb_api_key': '',
            'vote_command': '!vote',
            'vote_duration_sec': 60,
            'vote_use_all_enabled_games': True,
            'vote_candidate_count': 6,
            'vote_winner_chat_template': 'The community has crowned {game} as the winner!',
            'random_pick_duration_sec': 20,
            'random_switch_interval_sec': 1.0,
            'picker_winner_chat_template': 'The random picker chose {game}!',
            'link_command_general': '!link',
            'chat_send_links': False,
            'send_winner_to_chat': True,
            'accept_plain_votes': True,
            'platforms_csv': '',
            'twitch_update_on_winner': True,
            'twitch_update_tags': False,
            'youtube_update_on_winner': False,
            'youtube_update_tags': False,
            'youtube_default_category': '20',
            'kick_update_on_winner': False,
            'kick_update_tags': False,
            'browser_overlay_enabled': True,
            'open_browser_on_action': True,
            'open_window_on_action': True,
            'browser_overlay_port': 17623,
            'overlay_title': 'gam3pick3r',
            'greenscreen_hex': '#00FF00',
            'overlay_background_enabled': False,
            'overlay_background_image': '',
            'overlay_background_mode': 'cover',
            'autoconnect': True,
        }

    def _fix_settings_tabs(self, parent: Any = None) -> None:
        if QtWidgets is None or parent is None:
            return
        try:
            from PySide6 import QtCore
            tabs = parent.findChild(QtWidgets.QTabWidget)
            if tabs is None:
                return
            tabs.setUsesScrollButtons(True)
            bar = tabs.tabBar()
            if bar is None:
                return
            try:
                bar.setExpanding(False)
            except Exception:
                pass
            try:
                bar.setElideMode(QtCore.Qt.TextElideMode.ElideNone)
            except Exception:
                try:
                    bar.setElideMode(QtCore.Qt.ElideNone)
                except Exception:
                    pass
            try:
                fm = bar.fontMetrics()
                for i in range(tabs.count()):
                    text = str(tabs.tabText(i) or '').strip()
                    if text:
                        bar.setTabToolTip(i, text)
                        bar.setTabData(i, max(70, fm.horizontalAdvance(text) + 34))
                bar.setStyleSheet('QTabBar::tab { min-width: 0px; padding-left: 10px; padding-right: 10px; } QTabBar::scroller { width: 24px; }')
            except Exception:
                pass
        except Exception:
            pass

    def _delete_game_button_schema(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            games = self._load_games()
        except Exception:
            games = []
        if not games:
            out.append({'key': 'delete_empty', 'tab': 'Delete', 'type': 'separator', 'label': 'Keine Spiele gespeichert.'})
            return out
        for idx, g in enumerate(games[:120], start=1):
            gid = str(g.get('id') or '').strip()
            title = self._game_title(g, idx, gid)
            if gid:
                out.append({'key': f'button_delete_game__{gid}', 'tab': 'Delete', 'type': 'button', 'label': '', 'button_text': f'{title} löschen', 'button_text_en': f'Delete {title}', 'show_label': False})
        return out

    def on_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        self._fix_settings_tabs(parent)
        vals = dict(self._settings or {})
        try:
            if parent is not None and hasattr(parent, 'values'):
                vals.update(parent.values())
        except Exception:
            pass
        self._settings = vals
        if key == 'button_save' or key.startswith('button_save__'):
            self._save_visible_settings(vals)
            # Ein einziger Speichern-Button: Einstellungen sichern, Fenster bleibt offen.
            # Wenn das Spielefeld Inhalt hat, wird es ebenfalls als Spieleliste übernommen.
            txt_games = str(vals.get('games_text') or '').strip()
            if txt_games:
                games = self._parse_games_text(txt_games)
            else:
                games = self._load_current_games(vals)
            games = self._apply_per_game_fields(vals, games)
            self._save_games(games)
            self._games = games
            self._prune_runtime_game_state()
            self._push_state()
            self._update_games_widgets(parent)
            self._log('Plugin-Einstellungen gespeichert. Fenster bleibt offen.')
            return True
        if key == 'button_close' or key.startswith('button_close__'):
            try:
                if parent is not None and hasattr(parent, 'close'):
                    parent.close()
            except Exception:
                pass
            return True
        if key == 'button_cancel' or key.startswith('button_cancel__'):
            try:
                if parent is not None and hasattr(parent, 'reject'):
                    parent.reject()
                elif parent is not None and hasattr(parent, 'close'):
                    parent.close()
            except Exception:
                pass
            return True
        if key == 'button_refresh_covers':
            sgdb_key = str(vals.get('steamgriddb_api_key') or '').strip() or self._stored_steamgriddb_key()
            if sgdb_key:
                self._save_plugin_settings({'steamgriddb_api_key': sgdb_key})
            count = self._refresh_all_covers(sgdb_key)
            self._games = self._load_games()
            self._push_state()
            self._update_games_widgets(parent)
            self._log(f'Cover neu geladen: {count}')
            return True
        if key == 'button_delete_game_by_text':
            raw = str(vals.get('delete_game_text') or '').strip()
            ok, msg = self._delete_game_by_text(raw)
            self._games = self._load_games()
            self._prune_runtime_game_state()
            self._push_state()
            self._update_games_widgets(parent)
            self._log(msg)
            return True
        if key == 'button_add_game_by_name':
            name = str(vals.get('game_search_name') or '').strip()
            if not name:
                self._log('Kein Spielname angegeben.')
                return True
            sgdb_key = str(vals.get('steamgriddb_api_key') or '').strip() or self._stored_steamgriddb_key()
            if sgdb_key:
                self._save_plugin_settings({'steamgriddb_api_key': sgdb_key})
            ok, msg = self._add_game_by_name(name, sgdb_key)
            self._games = self._load_games()
            self._push_state()
            self._log(msg)
            self._update_games_widgets(parent)
            return True
        if key == 'button_open_overlay':
            self._open_overlay_browser(force=True)
            return True
        if key == 'button_load_games_to_field':
            text = self._games_to_text(self._load_games())
            try:
                if parent is not None and hasattr(parent, '_widgets') and 'games_text' in parent._widgets:
                    parent._widgets['games_text'].setPlainText(text)
            except Exception:
                pass
            self._log(f'Spiele aus {GAMES_FILE} geladen.')
            return True
        if key == 'button_save_games_from_field':
            games = self._parse_games_text(str(vals.get('games_text') or ''))
            self._save_games(games)
            self._games = games
            self._prune_runtime_game_state()
            self._push_state()
            self._log(f'{len(games)} Spiele gespeichert: {GAMES_FILE}')
            return True
        if key.startswith('button_delete_game__'):
            gid = key.split('__', 1)[1].strip()
            ok, msg = self._delete_game(gid)
            self._games = self._load_games()
            if ok:
                self._remove_game_controls(parent, gid)
            self._prune_runtime_game_state()
            self._push_state()
            self._update_games_widgets(parent)
            self._settings['games_text'] = self._games_to_text(self._games)
            self._log(msg)
            return True
        if key == 'button_choose_background':
            ok, msg, rel = self._choose_background_file(parent)
            if ok and rel:
                self._settings['overlay_background_image'] = rel
                self._settings['overlay_background_enabled'] = True
                try:
                    if parent is not None and hasattr(parent, '_widgets'):
                        w = parent._widgets.get('overlay_background_image')
                        if w is not None and hasattr(w, 'setText'):
                            w.setText(rel)
                        cb = parent._widgets.get('overlay_background_enabled')
                        if cb is not None and hasattr(cb, 'setChecked'):
                            cb.setChecked(True)
                except Exception:
                    pass
                self._save_plugin_settings({'overlay_background_image': rel, 'overlay_background_enabled': True})
                self._push_state()
            self._log(msg)
            return True
        if key == 'button_start_vote':
            self._start_vote(vals)
            return True
        if key == 'button_stop_vote':
            self._stop_vote(send_winner=True, source_platform='')
            return True
        if key == 'button_start_picker':
            self._start_picker(vals)
            return True
        return False

    def handle_settings_button(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host, parent)

    def on_settings_action(self, key: str, host: PluginHost | None = None, parent: Any = None) -> bool:
        return self.on_settings_button(key, host, parent)

    def start(self, settings: dict[str, Any], host: PluginHost) -> None:
        self._settings = dict(settings or {})
        stored = self._load_plugin_settings()
        # Keep private plugin data inside the plugin folder, like the original portable app did in its data folder.
        # The host settings field may override it, but the stored fallback survives plugin reloads/exports.
        if not _safe_text(self._settings.get('steamgriddb_api_key')) and _safe_text(stored.get('steamgriddb_api_key')):
            self._settings['steamgriddb_api_key'] = _safe_text(stored.get('steamgriddb_api_key'))
        for _k in ['random_switch_interval_sec', 'random_pick_duration_sec', 'overlay_background_image', 'overlay_background_enabled', 'overlay_background_mode', 'twitch_update_on_winner', 'twitch_update_tags', 'youtube_update_on_winner', 'youtube_update_tags', 'youtube_default_category', 'kick_update_on_winner', 'kick_update_tags']:
            if self._settings.get(_k) in (None, '') and stored.get(_k) not in (None, ''):
                self._settings[_k] = stored.get(_k)
        self._host = host
        self._games = self._load_games()
        try:
            sgdb_key = self._stored_steamgriddb_key()
            if sgdb_key and any(self._cover_is_bad_or_missing(str(g.get('cover') or '')) for g in (self._games or [])):
                cnt = self._refresh_bad_covers(sgdb_key)
                if cnt:
                    self._log(f'Schlechte/fehlende Cover automatisch neu geladen: {cnt}')
        except Exception as exc:
            self._log(f'Automatischer Cover-Fix fehlgeschlagen: {exc}')
        if not self._games and str(self._settings.get('games_text') or '').strip():
            self._games = self._parse_games_text(str(self._settings.get('games_text') or ''))
            self._save_games(self._games)
        self._connect_host_message_signal(host)
        self._start_overlay_if_needed()
        self._push_state()
        super().start(settings, host)

    def stop(self, wait: bool = False, timeout: float = 3.0) -> None:
        try:
            if self._popup is not None:
                self._popup.stop()
                self._popup = None
            if self._server is not None:
                self._server.stop()
                self._server = None
        except Exception:
            pass
        super().stop(wait=wait, timeout=timeout)

    def run(self, settings: dict[str, Any], host: PluginHost) -> None:
        if not _as_bool(settings.get('enabled'), True):
            host.set_status(self.plugin_id, PluginStatus('idle', 'Disabled'))
            while not self._stop.is_set():
                time.sleep(0.5)
            return
        msg = 'Ready'
        if self._server is not None:
            msg = f'Ready · Overlay http://127.0.0.1:{self._server.port}/'
        host.set_status(self.plugin_id, PluginStatus('connected', msg))
        self._log(msg)
        while not self._stop.is_set():
            now = time.time()
            with self._lock:
                if self._vote_active and self._vote_end_at and now >= self._vote_end_at:
                    pass_stop = True
                else:
                    pass_stop = False
                if self._picker_active and self._picker_end_at and now >= self._picker_end_at:
                    pick_id = self._pending_pick_id
                else:
                    pick_id = ''
            if pass_stop:
                try:
                    self._stop_vote(send_winner=True, source_platform='')
                except Exception as exc:
                    self._log(f'Vote-Abschluss fehlgeschlagen: {exc}')
                    # Timer darf nie hängen bleiben, nur weil ein Stream-/Chat-Update scheitert.
                    with self._lock:
                        self._vote_active = False
                        self._vote_end_at = 0.0
                    self._push_state()
            if pick_id:
                try:
                    self._finish_picker(pick_id)
                except Exception as exc:
                    self._log(f'Random-Picker-Abschluss fehlgeschlagen: {exc}')
                    # Picker darf nach Ablauf nie weiterrollen.
                    with self._lock:
                        self._picker_active = False
                        self._pending_pick_id = ''
                        self._picker_end_at = 0.0
                    self._push_state(winner_id=pick_id)
            time.sleep(0.25)

    def test_connection(self, settings: dict[str, Any]) -> tuple[bool, str]:
        games = self._load_games()
        if self._server is not None:
            return True, f'OK · {len(games)} Spiele · v0.17 · Overlay http://127.0.0.1:{self._server.port}/'
        return True, f'OK · {len(games)} Spiele · v0.17'

    def on_message(self, msg: Any) -> None:
        settings = dict(self._settings or {})
        if not _as_bool(settings.get('enabled'), True):
            return
        platform = _clean_platform(_msg_get(msg, 'platform', 'source_platform', default=''))
        username = _safe_text(_msg_get(msg, 'username', 'user', 'display_name', default=''))
        text = _safe_text(_msg_get(msg, 'text', 'message', 'content', default=''))
        msg_type = _safe_text(_msg_get(msg, 'message_type', 'type', default='')).lower()
        if not text:
            return
        # Keep this intentionally permissive: Twitch/TikTok/YT/Kick plugins do not all name
        # chat payloads exactly the same way. Metrics/status messages still get ignored.
        if msg_type and msg_type in {'viewer_count', 'followers_count', 'metric', 'stats', 'status', 'live_status'}:
            return
        if msg_type and msg_type not in {'chat', 'message', 'comment', 'twitch_chat', 'tiktok_comment', 'youtube_chat', 'kick_chat'}:
            # Unknown message types may still be real chat from another platform, but do not
            # process obvious alert/sub/join texts as votes.
            if 'alert' in msg_type or 'join' in msg_type or 'follow' in msg_type or 'sub' in msg_type:
                return
        allowed = self._allowed_platforms(settings)
        if allowed and platform and platform not in allowed:
            return
        if not platform:
            platform = _clean_platform(_msg_get(msg, 'source_plugin_id', default='')) or 'unknown'
        # Host flush + direct signal can both call us. De-dupe briefly so one chat line is one vote.
        ts = _safe_text(_msg_get(msg, 'timestamp', default=''))
        key = f'{platform}|{username.lower()}|{text}|{ts}'
        now = time.time()
        with self._lock:
            self._recent_msg_keys = {k: v for k, v in self._recent_msg_keys.items() if now - v < 8.0}
            if key in self._recent_msg_keys:
                return
            self._recent_msg_keys[key] = now
        self._handle_chat(platform, username or 'unknown', text)

    def _handle_chat(self, platform: str, username: str, text: str) -> None:
        raw = text.strip()
        low = raw.lower()
        cmd = str(self._settings.get('vote_command') or '!vote').strip() or '!vote'
        cmd_low = cmd.lower()
        with self._lock:
            vote_active = self._vote_active
        if vote_active:
            choice = ''
            if low.startswith(cmd_low):
                parts = raw.split(' ', 1)
                if len(parts) < 2:
                    return
                choice = parts[1].strip()
            elif _as_bool(self._settings.get('accept_plain_votes'), True):
                choice = raw
            if choice:
                self._register_vote(platform, username, choice, used_command=low.startswith(cmd_low))
                return
        link_cmd = str(self._settings.get('link_command_general') or '!link').strip() or '!link'
        if low == link_cmd.lower() or low == '!stream':
            self._send_winner_link(platform, username)

    def _register_vote(self, platform: str, username: str, choice: str, used_command: bool = False) -> None:
        gid = self._match_game(choice)
        if not gid:
            if used_command or choice.strip().lstrip('#').isdigit():
                self._log(f'Vote nicht gefunden: {username}@{platform} -> {choice}')
            return
        voter_key = f'{(_clean_platform(platform) or "unknown")}:{str(username or "").strip().lstrip("@").lower()}'
        with self._lock:
            old = self._voted_users.get(voter_key)
            if old:
                self._votes[old] = max(0, int(self._votes.get(old, 0)) - 1)
            self._voted_users[voter_key] = gid
            self._votes[gid] = int(self._votes.get(gid, 0)) + 1
        game = self._game_by_id(gid)
        self._log(f'Vote: {username}@{platform} -> {game.get("title", gid) if game else gid}')
        self._push_state()

    def _start_vote(self, settings: dict[str, Any] | None = None) -> None:
        settings = dict(settings or self._settings or {})
        self._settings = settings
        self._games = self._load_current_games(settings)
        self._prune_runtime_game_state()
        enabled = [g for g in self._games if _as_bool(g.get('enabled'), True)]
        if not enabled:
            self._log('Vote nicht gestartet: keine Spiele vorhanden.')
            return
        candidates = list(enabled)
        if not _as_bool(settings.get('vote_use_all_enabled_games'), True):
            random.shuffle(candidates)
            candidates = candidates[:_to_int(settings.get('vote_candidate_count'), 6, 2, 100)]
        # assign temporary numbers if none exist, keeping saved numbers when present
        used_nums = {int(g.get('num') or 0) for g in candidates if int(g.get('num') or 0) > 0}
        next_num = 1
        for g in candidates:
            if int(g.get('num') or 0) <= 0:
                while next_num in used_nums:
                    next_num += 1
                g['num'] = next_num
                used_nums.add(next_num)
        with self._lock:
            self._votes = {}
            self._voted_users = {}
            self._vote_candidates = [str(g['id']) for g in candidates]
            self._vote_num_map = {int(g.get('num') or 0): str(g.get('id') or '') for g in candidates if int(g.get('num') or 0) > 0}
            self._vote_active = True
            self._vote_end_at = time.time() + _to_int(settings.get('vote_duration_sec'), 60, 5, 7200)
        self._log(f'Vote gestartet: {len(candidates)} Kandidaten · Befehl {settings.get("vote_command") or "!vote"}')
        self._push_state()
        self._show_action_outputs('vote')

    def _stop_vote(self, send_winner: bool = True, source_platform: str = '') -> None:
        with self._lock:
            if not self._vote_active:
                return
            self._vote_active = False
            winner = self._compute_vote_winner()
            self._last_winner_id = winner or self._last_winner_id
        self._push_state(winner_id=winner)
        if winner:
            game = self._game_by_id(winner)
            title = game.get('title', 'this game') if game else 'this game'
            self._log(f'Vote beendet: Gewinner {title}')
            self._apply_winner_stream_info(game, 'Vote')
            if send_winner and _as_bool(self._settings.get('send_winner_to_chat'), True):
                text = self._format_template(str(self._settings.get('vote_winner_chat_template') or ''), title, 'The community has crowned {game} as the winner!')
                self._send_winner_announcement(text, preferred_platform=source_platform)
        else:
            self._log('Vote beendet: keine Stimmen.')

    def _start_picker(self, settings: dict[str, Any] | None = None) -> None:
        settings = dict(settings or self._settings or {})
        self._settings = settings
        self._games = self._load_current_games(settings)
        self._prune_runtime_game_state()
        enabled = [g for g in self._games if _as_bool(g.get('enabled'), True)]
        if not enabled:
            self._log('Random Picker nicht gestartet: keine Spiele vorhanden.')
            return
        pick = random.choice(enabled)
        dur = _to_int(settings.get('random_pick_duration_sec'), 20, 1, 600)
        step = max(0.2, min(60.0, float(settings.get('random_switch_interval_sec') or 1.0)))
        with self._lock:
            self._picker_active = True
            self._pending_pick_id = str(pick.get('id') or '')
            self._picker_end_at = time.time() + dur
        self._state.set(mode='rolling', picked=None, rolling_until=self._picker_end_at, roll_duration=dur, roll_duration_sec=dur, roll_step_sec=step, random_switch_interval_sec=step, roll_start=time.time(), active_index=0, vote_active=False, games=self._overlay_games(enabled))
        self._log(f'Random Picker gestartet: {dur}s, Wechsel alle {step:g}s')
        self._show_action_outputs('picker')

    def _finish_picker(self, game_id: str) -> None:
        with self._lock:
            if not self._picker_active or self._pending_pick_id != game_id:
                return
            self._picker_active = False
            self._pending_pick_id = ''
            self._picker_end_at = 0.0
            self._last_winner_id = game_id
        game = self._game_by_id(game_id)
        title = game.get('title', 'this game') if game else 'this game'
        self._push_state(winner_id=game_id)
        self._log(f'Random Picker Gewinner: {title}')
        self._apply_winner_stream_info(game, 'Random Picker')
        if _as_bool(self._settings.get('send_winner_to_chat'), True):
            text = self._format_template(str(self._settings.get('picker_winner_chat_template') or ''), title, 'The random picker chose {game}!')
            self._send_winner_announcement(text)

    def _compute_vote_winner(self) -> str:
        if not self._votes:
            return ''
        items = sorted(self._votes.items(), key=lambda kv: (-int(kv[1]), (self._game_by_id(kv[0]) or {}).get('title', '')))
        return str(items[0][0]) if items else ''

    def _match_game(self, query: str) -> str:
        q = query.strip().lower()
        if not q:
            return ''
        if q.startswith('#'):
            q = q[1:].strip()
        if q.isdigit():
            gid = self._vote_num_map.get(int(q))
            if gid:
                return gid
        candidates = self._vote_candidates if self._vote_active else [str(g.get('id')) for g in self._games]
        # exact title
        for gid in candidates:
            g = self._game_by_id(gid)
            if g and str(g.get('title') or '').strip().lower() == q:
                return gid
        # contains/startswith fallback
        for gid in candidates:
            g = self._game_by_id(gid)
            title = str(g.get('title') or '').strip().lower() if g else ''
            if title and (title.startswith(q) or q in title):
                return gid
        return ''

    def _show_action_outputs(self, reason: str = '') -> None:
        if _as_bool(self._settings.get('open_browser_on_action'), True):
            self._open_overlay_browser()
        if _as_bool(self._settings.get('open_window_on_action'), True):
            self._open_popup_window()

    def _connect_host_message_signal(self, host: PluginHost | None) -> None:
        if self._host_signal_connected or host is None:
            return
        sig = getattr(host, 'message_received', None)
        if sig is None or not hasattr(sig, 'connect'):
            return
        try:
            sig.connect(self.on_message)
            self._host_signal_connected = True
            self._log('Direkter Chat-Signal-Eingang verbunden.')
        except Exception as exc:
            self._log(f'Direkter Chat-Signal-Eingang nicht verfügbar: {exc}')

    def _save_visible_settings(self, vals: dict[str, Any]) -> None:
        keep: dict[str, Any] = {}
        for k in ['steamgriddb_api_key', 'overlay_background_image', 'overlay_background_enabled', 'overlay_background_mode', 'random_pick_duration_sec', 'random_switch_interval_sec', 'vote_duration_sec', 'twitch_update_on_winner', 'twitch_update_tags']:
            if k in vals:
                keep[k] = vals.get(k)
        if keep:
            self._save_plugin_settings(keep)
        sgdb_key = _safe_text(vals.get('steamgriddb_api_key'))
        if sgdb_key:
            self._save_plugin_settings({'steamgriddb_api_key': sgdb_key})


    def _apply_per_game_fields(self, vals: dict[str, Any], games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for g in list(games or []):
            ng = dict(g)
            gid = str(ng.get('id') or '').strip()
            if gid:
                st_key = f'stream_title__{gid}'
                cat_key = f'twitch_game_name__{gid}'
                kick_cat_key = f'kick_category__{gid}'
                yt_cat_key = f'youtube_category__{gid}'
                tags_key = f'tags__{gid}'
                if st_key in vals:
                    ng['stream_title'] = str(vals.get(st_key) or '').strip()
                if cat_key in vals:
                    ng['twitch_game_name'] = str(vals.get(cat_key) or '').strip()
                if kick_cat_key in vals:
                    ng['kick_category'] = str(vals.get(kick_cat_key) or '').strip()
                if yt_cat_key in vals:
                    ng['youtube_category'] = str(vals.get(yt_cat_key) or '').strip()
                if tags_key in vals:
                    raw_tags = str(vals.get(tags_key) or '').strip()
                    ng['tags'] = [x.strip() for x in raw_tags.replace(';', ',').split(',') if x.strip()]
            updated.append(self._normalize_game(ng))
        return updated

    def _current_games_list_text(self, games: list[dict[str, Any]] | None = None) -> str:
        games = list(games if games is not None else (self._games or self._load_games()))
        if not games:
            return ''
        lines: list[str] = []
        for idx, g in enumerate(games, start=1):
            num = int(g.get('num') or 0)
            prefix = f'{num}. ' if num > 0 else f'{idx}. '
            cover = str(g.get('cover') or '').strip()
            suffix = f'  [{cover}]' if cover else ''
            lines.append(prefix + str(g.get('title') or '').strip() + suffix)
        return '\n'.join(lines)

    def _remove_widget_key(self, parent: Any, key: str) -> None:
        if QtWidgets is None or parent is None or not hasattr(parent, '_widgets'):
            return
        key = str(key or '').strip()
        if not key:
            return
        try:
            parent._schema = [f for f in getattr(parent, '_schema', []) if str(f.get('key')) != key]
        except Exception:
            pass
        widget = parent._widgets.pop(key, None)
        if widget is None:
            return
        try:
            lay = None
            obj = widget.parent()
            while obj is not None:
                l = obj.layout() if hasattr(obj, 'layout') else None
                if isinstance(l, QtWidgets.QFormLayout):
                    lay = l
                    break
                obj = obj.parent() if hasattr(obj, 'parent') else None
            if lay is not None:
                lay.removeRow(widget)
            widget.setParent(None)
            widget.deleteLater()
        except Exception:
            try:
                widget.hide()
            except Exception:
                pass

    def _remove_game_controls(self, parent: Any, gid: str) -> None:
        if QtWidgets is None or parent is None or not hasattr(parent, '_widgets'):
            return
        gid = str(gid or '').strip()
        keys = [
            f'button_delete_game__{gid}',
            f'stream_title__{gid}',
            f'twitch_game_name__{gid}',
            f'tags__{gid}',
        ]
        try:
            parent._schema = [f for f in getattr(parent, '_schema', []) if str(f.get('key')) not in set(keys)]
        except Exception:
            pass
        for key in keys:
            widget = parent._widgets.pop(key, None)
            if widget is None:
                continue
            try:
                lay = None
                obj = widget.parent()
                while obj is not None:
                    l = obj.layout() if hasattr(obj, 'layout') else None
                    if isinstance(l, QtWidgets.QFormLayout):
                        lay = l
                        break
                    obj = obj.parent() if hasattr(obj, 'parent') else None
                if lay is not None:
                    lay.removeRow(widget)
                widget.setParent(None)
                widget.deleteLater()
            except Exception:
                try:
                    widget.hide()
                except Exception:
                    pass

    def _update_games_widgets(self, parent: Any = None) -> None:
        try:
            self._fix_settings_tabs(parent)
            if parent is None or not hasattr(parent, '_widgets'):
                return
            games = self._games or self._load_games()
            w = parent._widgets.get('games_text')
            new_text = self._games_to_text(games)
            if w is not None and hasattr(w, 'setPlainText'):
                w.setPlainText(new_text)
            self._settings['games_text'] = new_text
            if games:
                self._remove_widget_key(parent, 'delete_empty')
                self._remove_widget_key(parent, 'streaminfo_empty')
            self._remove_stale_game_controls(parent, games)
            self._append_missing_game_controls(parent, games)
        except Exception:
            pass



    def _remove_stale_game_controls(self, parent: Any, games: list[dict[str, Any]]) -> None:
        if QtWidgets is None or parent is None or not hasattr(parent, '_widgets'):
            return
        valid = {str(g.get('id') or '').strip() for g in (games or []) if str(g.get('id') or '').strip()}
        try:
            for key in list(parent._widgets.keys()):
                skey = str(key)
                if not (skey.startswith('button_delete_game__') or skey.startswith('stream_title__') or skey.startswith('twitch_game_name__') or skey.startswith('tags__')):
                    continue
                gid = skey.split('__', 1)[1].strip() if '__' in skey else ''
                if gid and gid not in valid:
                    widget = parent._widgets.pop(skey, None)
                    if widget is not None:
                        try:
                            widget.setParent(None)
                            widget.deleteLater()
                        except Exception:
                            try:
                                widget.hide()
                            except Exception:
                                pass
            if hasattr(parent, '_schema'):
                parent._schema = [f for f in getattr(parent, '_schema', []) if not (
                    str(f.get('key') or '').startswith('button_delete_game__') or
                    str(f.get('key') or '').startswith('stream_title__') or
                    str(f.get('key') or '').startswith('twitch_game_name__') or
                    str(f.get('key') or '').startswith('tags__')
                ) or str(f.get('key') or '').split('__', 1)[-1].strip() in valid]
        except Exception:
            pass

    def _find_tab_form(self, parent: Any, tab_name: str) -> Any:
        if QtWidgets is None or parent is None:
            return None
        try:
            tabs = parent.findChild(QtWidgets.QTabWidget)
            if tabs is None:
                return None
            wanted = str(tab_name or '').strip().lower()
            aliases = {
                'löschen': ['löschen', 'loschen', 'delete', 'del'],
                'delete': ['löschen', 'loschen', 'delete', 'del'],
                'streaminfos': ['streaminfos', 'streaminfo', 'stream', 'streaminf'],
                'stream': ['streaminfos', 'streaminfo', 'stream', 'streaminf'],
            }.get(wanted, [wanted])
            for i in range(tabs.count()):
                text = str(tabs.tabText(i) or '').strip().lower().replace('…', '').replace('...', '')
                if any(a and (text == a or text.startswith(a) or a.startswith(text)) for a in aliases):
                    scroll = tabs.widget(i)
                    body = scroll.widget() if hasattr(scroll, 'widget') else None
                    layout = body.layout() if body is not None and hasattr(body, 'layout') else None
                    return layout if isinstance(layout, QtWidgets.QFormLayout) else None
        except Exception:
            return None
        return None

    def _schema_has_key(self, parent: Any, key: str) -> bool:
        try:
            return any(str(f.get('key')) == key for f in getattr(parent, '_schema', []))
        except Exception:
            return False

    def _append_schema(self, parent: Any, field: dict[str, Any]) -> None:
        try:
            if not self._schema_has_key(parent, str(field.get('key'))):
                parent._schema.append(field)
        except Exception:
            pass

    def _append_missing_game_controls(self, parent: Any, games: list[dict[str, Any]]) -> None:
        if QtWidgets is None or parent is None or not hasattr(parent, '_widgets'):
            return
        delete_form = self._find_tab_form(parent, 'Delete')
        stream_form = self._find_tab_form(parent, 'Stream')
        for idx, g in enumerate(games or [], start=1):
            gid = str(g.get('id') or '').strip()
            title = str(g.get('title') or f'Spiel {idx}').strip()
            if not gid:
                continue
            del_key = f'button_delete_game__{gid}'
            if del_key not in parent._widgets and delete_form is not None:
                self._remove_widget_key(parent, 'delete_empty')
                btn = QtWidgets.QPushButton(f'{title} löschen')
                btn.clicked.connect(lambda _checked=False, k=del_key: parent._handle_button_click(k))
                parent._widgets[del_key] = btn
                self._append_schema(parent, {'key': del_key, 'tab': 'Delete', 'type': 'button', 'label': '', 'button_text': f'{title} löschen', 'show_label': False})
                delete_form.addRow(btn)
            for key, label, val, placeholder in [
                (f'stream_title__{gid}', f'{title} · Streamtitel', str(g.get('stream_title') or ''), 'z.B. Jetzt: {game}'),
                (f'twitch_game_name__{gid}', f'{title} · Twitch-Kategorie', str(g.get('twitch_game_name') or title), title),
                (f'tags__{gid}', f'{title} · Tags', ', '.join([str(x) for x in (g.get('tags') or [])]), 'tag1, tag2'),
            ]:
                if key not in parent._widgets and stream_form is not None:
                    edit = QtWidgets.QLineEdit(val)
                    edit.setPlaceholderText(placeholder)
                    parent._widgets[key] = edit
                    self._append_schema(parent, {'key': key, 'tab': 'Stream', 'label': label})
                    stream_form.addRow(QtWidgets.QLabel(label), edit)

    def _delete_game_by_text(self, raw: str) -> tuple[bool, str]:
        q = str(raw or '').strip()
        if not q:
            return False, 'Kein Spiel zum Löschen angegeben.'
        games = self._load_games()
        if q.isdigit():
            n = int(q)
            for idx, g in enumerate(games, start=1):
                if int(g.get('num') or 0) == n or idx == n:
                    return self._delete_game(str(g.get('id') or ''))
        ql = q.lower()
        for g in games:
            title = str(g.get('title') or '').strip().lower()
            if title == ql:
                return self._delete_game(str(g.get('id') or ''))
        for g in games:
            title = str(g.get('title') or '').strip().lower()
            if ql in title:
                return self._delete_game(str(g.get('id') or ''))
        return False, f'Spiel nicht gefunden: {q}'

    def _cover_is_bad_or_missing(self, cover: str) -> bool:
        name = str(cover or '').strip()
        if not name:
            return True
        try:
            path = (COVERS_DIR / name).resolve()
            if not str(path).startswith(str(COVERS_DIR.resolve())) or not path.exists() or not path.is_file():
                return True
            if path.stat().st_size < 20 * 1024:
                return True
            try:
                from PIL import Image
                with Image.open(path) as img:
                    w, h = img.size
                if w < 300 or h < 420:
                    return True
            except Exception:
                pass
        except Exception:
            return True
        return False

    def _refresh_bad_covers(self, sgdb_key: str = '') -> int:
        games = self._load_games()
        if not games:
            return 0
        count = 0
        for g in games:
            if not self._cover_is_bad_or_missing(str(g.get('cover') or '')):
                continue
            title = str(g.get('title') or '').strip()
            if not title:
                continue
            self._log(f'Cover fehlt/ist zu schlecht: {title}. Lade neu...')
            twitch_id, found_name, cover_url = self._search_game_metadata(title, sgdb_key)
            if not cover_url:
                continue
            new_cover = self._download_cover(str(g.get('id') or _safe_asset_name(title)), cover_url)
            if not new_cover:
                continue
            old = str(g.get('cover') or '').strip()
            g['cover'] = new_cover
            if twitch_id:
                g['twitch_id'] = twitch_id
            if found_name and not str(g.get('twitch_game_name') or '').strip():
                g['twitch_game_name'] = found_name
            if old and old != new_cover:
                try:
                    old_path = (COVERS_DIR / old).resolve()
                    if str(old_path).startswith(str(COVERS_DIR.resolve())) and old_path.exists():
                        old_path.unlink()
                except Exception:
                    pass
            count += 1
        if count:
            self._save_games(games)
            self._games = games
        return count

    def _refresh_all_covers(self, sgdb_key: str = '') -> int:
        games = self._load_games()
        if not games:
            return 0
        count = 0
        for g in games:
            title = str(g.get('title') or '').strip()
            if not title:
                continue
            twitch_id, found_name, cover_url = self._search_game_metadata(title, sgdb_key)
            if not cover_url:
                continue
            new_cover = self._download_cover(str(g.get('id') or _safe_asset_name(title)), cover_url)
            if new_cover:
                old = str(g.get('cover') or '').strip()
                g['cover'] = new_cover
                if twitch_id:
                    g['twitch_id'] = twitch_id
                if found_name:
                    g['title'] = found_name
                if old and old != new_cover:
                    try:
                        old_path = (COVERS_DIR / old).resolve()
                        if str(old_path).startswith(str(COVERS_DIR.resolve())) and old_path.exists():
                            old_path.unlink()
                    except Exception:
                        pass
                count += 1
        self._save_games(games)
        self._games = games
        return count

    def _delete_game(self, gid: str) -> tuple[bool, str]:
        gid = str(gid or '').strip()
        games = self._load_games()
        target = None
        kept = []
        for g in games:
            if str(g.get('id') or '') == gid:
                target = g
            else:
                kept.append(g)
        if not target:
            return False, 'Spiel nicht gefunden.'
        cover = str(target.get('cover') or '').strip()
        if cover:
            try:
                path = (COVERS_DIR / cover).resolve()
                if str(path).startswith(str(COVERS_DIR.resolve())) and path.exists():
                    path.unlink()
            except Exception:
                pass
        self._save_games(kept)
        self._games = kept
        return True, f'Spiel gelöscht und games.json aktualisiert: {self._game_title(target, fallback=gid)} · übrig: {len(kept)}'

    def _choose_background_file(self, parent: Any = None) -> tuple[bool, str, str]:
        try:
            from PySide6 import QtWidgets
            file_path, _filter = QtWidgets.QFileDialog.getOpenFileName(
                parent,
                'Hintergrundbild auswählen',
                str(Path.home()),
                'Bilder (*.png *.jpg *.jpeg *.webp *.bmp);;Alle Dateien (*.*)'
            )
        except Exception as exc:
            return False, f'Bildauswahl nicht verfügbar: {exc}', ''
        if not file_path:
            return False, 'Keine Datei ausgewählt.', ''
        src = Path(file_path)
        if not src.exists() or not src.is_file():
            return False, 'Datei nicht gefunden.', ''
        if src.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            return False, 'Nicht unterstütztes Bildformat.', ''
        try:
            _ensure_dirs()
            name = _safe_asset_name(src.name, 'background' + src.suffix.lower())
            dest = BACKGROUNDS_DIR / name
            if dest.exists():
                dest = BACKGROUNDS_DIR / f'{src.stem}_{int(time.time())}{src.suffix.lower()}'
            shutil.copy2(str(src), str(dest))
            rel = dest.name
            return True, f'Hintergrundbild kopiert: {rel}', rel
        except Exception as exc:
            return False, f'Hintergrundbild konnte nicht kopiert werden: {exc}', ''

    def _open_overlay_browser(self, force: bool = False) -> bool:
        if self._server is None:
            self._start_overlay_if_needed()
        if self._server is None:
            self._log('Browser-Overlay nicht verfügbar.')
            return False
        now = time.time()
        if not force and now - self._last_overlay_open_at < 2.0:
            return True
        self._last_overlay_open_at = now
        url = f'http://127.0.0.1:{self._server.port}/'
        try:
            webbrowser.open(url)
            self._log(f'Browser-Overlay geöffnet: {url}')
            return True
        except Exception as exc:
            self._log(f'Browser konnte nicht geöffnet werden: {exc}')
            return False

    def _open_popup_window(self) -> bool:
        try:
            if self._popup is None:
                self._popup = _PopupWindow(self._state, str(self._settings.get('overlay_title') or 'gam3pick3r'))
            self._popup.start()
            return True
        except Exception as exc:
            self._log(f'Plugin-Fenster konnte nicht geöffnet werden: {exc}')
            return False

    def _add_game_by_name(self, name: str, sgdb_key: str = '') -> tuple[bool, str]:
        title = str(name or '').strip()
        if not title:
            return False, 'Kein Spielname angegeben.'
        self._games = self._load_games()
        for g in self._games:
            if str(g.get('title') or '').strip().lower() == title.lower():
                return True, f'Spiel ist schon vorhanden: {g.get("title")}'
        import uuid
        twitch_id, found_name, cover_url = self._search_game_metadata(title, sgdb_key)
        final_title = found_name or title
        gid = str(uuid.uuid4())
        cover_file = ''
        if cover_url:
            self._log(f'Cover-Quelle gefunden für {final_title}. Download startet...')
            cover_file = self._download_cover(gid, cover_url)
        else:
            self._log(f'Kein Cover gefunden für {final_title}.')
        game = self._normalize_game({
            'id': gid,
            'title': final_title,
            'cover': cover_file,
            'enabled': True,
            'links': {},
            'twitch_id': twitch_id,
            'twitch_game_name': final_title,
        })
        # keep twitch id even if normalize does not expose it later through old text format
        game['twitch_id'] = twitch_id
        self._games.append(game)
        self._save_games(self._games)
        extra = []
        if twitch_id:
            extra.append(f'Twitch-ID {twitch_id}')
        if cover_file:
            extra.append(f'Cover {cover_file}')
        return True, f'Spiel hinzugefügt: {final_title}' + (f' ({", ".join(extra)})' if extra else '')

    def _search_game_metadata(self, query: str, sgdb_key: str = '') -> tuple[str, str, str]:
        q = str(query or '').strip()
        twitch_id = ''
        name = ''
        cover_url = ''

        sgdb_key = self._clean_bearer_token(sgdb_key or self._stored_steamgriddb_key())
        self._log(f'Cover-Suche Diagnose: Spiel="{q}", SteamGridDB-Key={self._mask_secret(sgdb_key)}.')

        # Cover: SteamGridDB zuerst. Genau dafür ist der Key da; Twitch liefert oft nur 52x72-Müll.
        if sgdb_key:
            try:
                cover_url = self._steamgriddb_cover(q, sgdb_key)
            except Exception as exc:
                self._log(f'SteamGridDB-Cover fehlgeschlagen: {exc}')
        else:
            self._log('SteamGridDB übersprungen: kein Key in Plugin-Settings gefunden.')

        try:
            ps = self._platform_settings('twitch')
            raw_client_id = _safe_text(ps.get('client_id') or ps.get('twitch_client_id'))
            raw_token = self._clean_bearer_token(ps.get('access_token') or ps.get('oauth_token') or ps.get('token'))
            self._log(f'Twitch-Fallback Diagnose: Host-Settings client_id={self._mask_secret(raw_client_id)}, host_token={self._mask_secret(raw_token)}, gespeicherte Caches={len(self._load_twitch_caches())}.')
            client_id, token, source = self._get_twitch_search_auth(ps)
            self._log(f'Twitch-Fallback Diagnose: auth_source={source}, client_id={self._mask_secret(client_id)}, token={self._mask_secret(token)}.')
            if client_id and token:
                url = f'{TWITCH_HELIX_URL}/search/categories?' + urllib.parse.urlencode({'query': q, 'first': '1'})
                data = self._http_json(url, headers={
                    'Client-ID': client_id,
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                    'User-Agent': 'gam3pick3r/0.10 (+godisalotachat)',
                })
                items = data.get('data') if isinstance(data, dict) else []
                self._log(f'Twitch-Fallback: Kategorie-Treffer für "{q}": {len(items or [])}.')
                if items:
                    it = items[0]
                    twitch_id = _safe_text(it.get('id'))
                    name = _safe_text(it.get('name')) or q
                    self._log(f'Twitch-Fallback: Kategorie gefunden: {name} (id={twitch_id or "leer"}).')
                    if not cover_url:
                        box = _safe_text(it.get('box_art_url'))
                        if box:
                            cover_url = self._expand_twitch_box_art_url(box)
                            self._log('Cover-Fallback: Twitch Box-Art wird genutzt, SteamGridDB hatte keinen Treffer.')
                else:
                    self._log(f'Twitch-Fallback: keine Kategorie gefunden für "{q}".')
            else:
                self._log('Twitch-Fallback übersprungen: Client-ID oder Token fehlt. Prüfe, ob gam3pick3r den Twitch-OAuth vom Haupttool lesen darf.')
        except Exception as exc:
            self._log(f'Twitch-Spielsuche fehlgeschlagen: {exc}')

        if sgdb_key and not cover_url and name and name.lower() != q.lower():
            try:
                self._log(f'SteamGridDB: zweiter Versuch mit Twitch-Namen "{name}".')
                cover_url = self._steamgriddb_cover(name, sgdb_key)
            except Exception as exc:
                self._log(f'SteamGridDB-Cover für Twitch-Namen fehlgeschlagen: {exc}')
        return twitch_id, name or q, cover_url

    def _mask_secret(self, value: Any) -> str:
        raw = _safe_text(value)
        if not raw:
            return 'no'
        if len(raw) <= 8:
            return f'yes, len={len(raw)}'
        return f'yes, len={len(raw)}, {raw[:4]}...{raw[-4:]}'

    def _clean_bearer_token(self, value: Any) -> str:
        token = _safe_text(value)
        if token.lower().startswith('bearer '):
            token = token[7:].strip()
        if token.lower().startswith('oauth:'):
            token = token[6:].strip()
        return token.strip()

    def _get_twitch_app_token(self, ps: dict[str, Any]) -> str:
        _cid, token, _source = self._get_twitch_search_auth(ps)
        return token

    def _get_twitch_search_auth(self, ps: dict[str, Any]) -> tuple[str, str, str]:
        client_id = _safe_text(ps.get('client_id') or ps.get('twitch_client_id'))
        client_secret = _safe_text(ps.get('client_secret') or ps.get('twitch_client_secret'))
        cached_token = self._clean_bearer_token(self._app_token_cache.get('access_token'))
        expires_at = float(self._app_token_cache.get('expires_at') or 0)
        cached_cid = _safe_text(self._app_token_cache.get('client_id') or client_id)
        if cached_token and cached_cid and time.time() < expires_at - 60:
            return cached_cid, cached_token, 'app-cache'

        candidates: list[dict[str, Any]] = []
        if _safe_text(ps.get('access_token') or ps.get('oauth_token') or ps.get('refresh_token')):
            row = dict(ps)
            row['_cache_path'] = 'host.platform_settings(twitch)'
            candidates.append(row)
        candidates.extend(self._load_twitch_caches())

        for cache in candidates:
            source = _safe_text(cache.get('_cache_path')) or 'unknown-cache'
            cid = _safe_text(cache.get('client_id') or client_id)
            csec = _safe_text(cache.get('client_secret') or client_secret)
            token = self._clean_bearer_token(cache.get('access_token') or cache.get('oauth_token') or cache.get('token'))
            if not token and cache.get('refresh_token') and cid and csec:
                self._log(f'Twitch-Fallback: versuche Token-Refresh aus {source}.')
                token = self._refresh_twitch_token(cache, cid, csec)
            if not token or not cid:
                continue
            meta = self._validate_twitch_token(token, cid)
            if meta:
                login = _safe_text(meta.get('login') or cache.get('username') or cache.get('login'))
                self._log(f'Twitch-Fallback Auth OK: user-token aus {source} ({login or "unbekannt"}), Client-ID {self._mask_secret(cid)}.')
                return cid, token, source
            self._log(f'Twitch-Fallback: Token aus {source} ist nicht gültig oder passt nicht zur Client-ID.')

        if client_id and client_secret:
            try:
                data = self._http_json(TWITCH_TOKEN_URL, method='POST', data={
                    'grant_type': 'client_credentials',
                    'client_id': client_id,
                    'client_secret': client_secret,
                })
                token = self._clean_bearer_token(data.get('access_token'))
                if token:
                    self._app_token_cache = {
                        'access_token': token,
                        'client_id': client_id,
                        'expires_at': time.time() + float(data.get('expires_in') or 3600),
                    }
                    self._log(f'Twitch-Fallback Auth OK: App-Token erstellt, Client-ID {self._mask_secret(client_id)}.')
                    return client_id, token, 'client-credentials'
            except Exception as exc:
                self._log(f'Twitch-Fallback: App-Token konnte nicht erstellt werden: {exc}')

        return client_id, '', 'none'

    def _steamgriddb_cover(self, name: str, api_key: str) -> str:
        q = str(name or '').strip()
        safe = urllib.parse.quote(q)
        api_key = self._clean_bearer_token(api_key)
        if not safe:
            return ''
        self._log(f'SteamGridDB Diagnose: Key geladen: {self._mask_secret(api_key)}; Auth=Bearer; Query="{q}".')
        if not _safe_text(api_key):
            self._log('SteamGridDB übersprungen: kein API-Key geladen.')
            return ''
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
            'User-Agent': 'gam3pick3r/0.10 (+godisalotachat)',
        }
        try:
            self._log(f'SteamGridDB: Suche Cover für {q}...')
            data = self._http_json(f'{STEAMGRIDDB_API}/search/autocomplete/{safe}', headers=headers)
        except Exception as exc:
            self._log(f'SteamGridDB-Suche fehlgeschlagen: {exc}')
            return ''
        items = data.get('data') if isinstance(data, dict) else []
        self._log(f'SteamGridDB: Suchtreffer für {q}: {len(items or [])}.')
        sgid = 0
        picked_name = ''
        for it in items or []:
            try:
                if str(it.get('type') or '').lower() == 'game' and it.get('id'):
                    sgid = int(it.get('id'))
                    picked_name = _safe_text(it.get('name'))
                    break
            except Exception:
                pass
        if not sgid:
            for it in items or []:
                try:
                    if it.get('id'):
                        sgid = int(it.get('id'))
                        picked_name = _safe_text(it.get('name'))
                        break
                except Exception:
                    pass
        if not sgid:
            self._log(f'SteamGridDB: kein Spiel gefunden für {q}.')
            return ''
        self._log(f'SteamGridDB: nutze Game-ID {sgid}' + (f' ({picked_name})' if picked_name else '') + '.')

        params = urllib.parse.urlencode({
            'dimensions': '600x900,342x482,660x930',
            'types': 'static',
            'mime': 'image/png,image/jpeg,image/webp',
        })
        try:
            grids = self._http_json(f'{STEAMGRIDDB_API}/grids/game/{sgid}?{params}', headers=headers)
        except Exception as exc:
            self._log(f'SteamGridDB-Coverliste fehlgeschlagen: {exc}')
            return ''
        arr = grids.get('data') if isinstance(grids, dict) else []
        self._log(f'SteamGridDB: Cover-Treffer für {q}: {len(arr or [])}.')
        if not arr:
            self._log(f'SteamGridDB: keine Portrait-Cover gefunden für {q}.')
            return ''
        first_url = _safe_text((arr[0] or {}).get('url'))
        best_url = first_url
        best_score = -1
        best_size = ''
        for it in arr or []:
            url = _safe_text(it.get('url'))
            if not url:
                continue
            try:
                w = int(it.get('width') or 0)
                h = int(it.get('height') or 0)
            except Exception:
                w, h = 0, 0
            score = w * h
            if w and h and h <= w:
                score -= 10_000_000
            if score > best_score:
                best_score = score
                best_url = url
                best_size = f'{w}x{h}' if w and h else ''
        out = best_url or first_url
        if out:
            self._log('SteamGridDB: gutes Cover gefunden' + (f' ({best_size}).' if best_size else '.'))
        return out

    def _expand_twitch_box_art_url(self, url: str) -> str:
        u = str(url or '').strip()
        if not u:
            return ''
        u = (u.replace('{width}', '1440').replace('{height}', '1920')
               .replace('%7Bwidth%7D', '1440').replace('%7Bheight%7D', '1920')
               .replace('%7bwidth%7d', '1440').replace('%7bheight%7d', '1920'))
        u = re.sub(r'-(?:52|136|188|285|300)x(?:72|190|250|380|400)(?=\.)', '-1440x1920', u)
        return u

    def _download_cover(self, game_id: str, url: str) -> str:
        first = str(url or '').strip()
        if not first:
            return ''
        candidates: list[str] = []
        for u in [first, self._expand_twitch_box_art_url(first)]:
            if u and u not in candidates:
                candidates.append(u)
        last_reason = ''
        for u in candidates:
            try:
                req = urllib.request.Request(u, headers={
                    'User-Agent': 'gam3pick3r/0.10',
                    'Accept': 'image/png,image/jpeg,image/webp,image/*,*/*;q=0.8',
                })
                with urllib.request.urlopen(req, timeout=20) as resp:
                    ctype = (resp.headers.get('Content-Type') or '').lower()
                    data = resp.read(20 * 1024 * 1024)
                path_ext = Path(urllib.parse.urlparse(u).path).suffix.lower()
                if 'image' not in ctype and path_ext not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                    last_reason = f'Antwort ist kein Bild ({ctype or "unbekannt"})'
                    continue
                width = height = 0
                try:
                    from io import BytesIO
                    from PIL import Image
                    with Image.open(BytesIO(data)) as img:
                        width, height = img.size
                except Exception:
                    pass
                if len(data) < 20 * 1024 or (width and height and (width < 300 or height < 420)):
                    wh = f' {width}x{height}' if width and height else ''
                    last_reason = f'Datei zu klein/schlecht ({len(data)} Bytes{wh})'
                    continue
                ext = mimetypes.guess_extension(ctype.split(';', 1)[0].strip()) or ''
                if ext == '.jpe':
                    ext = '.jpg'
                if ext not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                    ext = path_ext if path_ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'} else '.jpg'
                filename = f'{game_id}{ext}'
                _ensure_dirs()
                (COVERS_DIR / filename).write_bytes(data)
                size_info = f'{width}x{height}, ' if width and height else ''
                self._log(f'Cover gespeichert: {filename} ({size_info}{len(data)} Bytes).')
                return filename
            except Exception as exc:
                last_reason = f'{type(exc).__name__}: {exc}'
        if last_reason:
            self._log(f'Cover-Download fehlgeschlagen/verworfen: {last_reason}')
        return ''


    def _cover_url(self, cover: str) -> str:
        name = str(cover or '').strip()
        if not name:
            return ''
        url = '/covers/' + urllib.parse.quote(name)
        try:
            path = (COVERS_DIR / name).resolve()
            if str(path).startswith(str(COVERS_DIR.resolve())) and path.exists():
                url += '?v=' + str(int(path.stat().st_mtime))
        except Exception:
            url += '?v=' + str(int(time.time()))
        return url

    def _apply_winner_stream_info(self, game: dict[str, Any] | None, reason: str = '') -> bool:
        if not game:
            return False
        ok_any = False
        if _as_bool(self._settings.get('twitch_update_on_winner'), True):
            ok_any = self._apply_winner_twitch_info(game, reason) or ok_any
        if _as_bool(self._settings.get('youtube_update_on_winner'), False):
            ok_any = self._apply_winner_youtube_info(game, reason) or ok_any
        if _as_bool(self._settings.get('kick_update_on_winner'), False):
            ok_any = self._apply_winner_kick_info(game, reason) or ok_any
        return ok_any

    def _winner_stream_payload(self, game: dict[str, Any]) -> tuple[str, str, list[str]]:
        title_name = str(game.get('title') or '').strip()
        title_template = str(game.get('stream_title') or '').strip()
        stream_title = self._format_template(title_template, title_name, title_name) if title_template else title_name
        tags = game.get('tags') if isinstance(game.get('tags'), list) else []
        return title_name, stream_title, [str(t).strip() for t in tags if str(t).strip()]

    def _apply_winner_twitch_info(self, game: dict[str, Any] | None, reason: str = '') -> bool:
        # Twitch wird zentral vom Haupttool gehandelt. Dieses Plugin liefert nur
        # Titel/Kategorie/Tags an den Host und liest keine eigenen OAuth-Caches mehr.
        if not game:
            return False
        host = self._host
        if host is None or not hasattr(host, 'update_twitch_channel'):
            self._log('Twitch-Update übersprungen: Host bietet update_twitch_channel nicht an.')
            return False

        title_name, stream_title, tags = self._winner_stream_payload(game)
        game_name = str(game.get('twitch_game_name') or title_name).strip()
        game_id = str(game.get('twitch_id') or game.get('twitch_game_id') or '').strip()
        if not game_id and game_name:
            try:
                game_id, found_name, _cover = self._search_game_metadata(game_name, self._stored_steamgriddb_key())
                if game_id:
                    game['twitch_id'] = game_id
                    if found_name and not game.get('twitch_game_name'):
                        game['twitch_game_name'] = found_name
                    self._save_games(self._games)
            except Exception as exc:
                self._log(f'Twitch-Kategorie konnte nicht gesucht werden: {exc}')

        out_tags = tags if _as_bool(self._settings.get('twitch_update_tags'), False) else None
        try:
            ok = bool(host.update_twitch_channel(title=stream_title, game_id=game_id, tags=out_tags))
            self._log(f'{reason or "Gewinner"}: Twitch Titel/Kategorie ' + ('aktualisiert' if ok else 'nicht aktualisiert'))
            return ok
        except Exception as exc:
            self._log(f'Twitch-Update über Haupttool fehlgeschlagen: {exc}')
            return False

    def _apply_winner_youtube_info(self, game: dict[str, Any] | None, reason: str = '') -> bool:
        if not game:
            return False
        if time.time() < getattr(self, '_youtube_quota_blocked_until', 0.0):
            self._log('YouTube-Update übersprungen: API-Quota ist aktuell blockiert.')
            return False
        _title_name, stream_title, tags = self._winner_stream_payload(game)
        out_tags = tags if _as_bool(self._settings.get('youtube_update_tags'), False) else []
        category = str(game.get('youtube_category') or self._settings.get('youtube_default_category') or '').strip()
        settings = self._platform_settings('youtube')
        token, token_msg = self._youtube_get_main_token(settings)
        if not token:
            self._log(f'YouTube-Update übersprungen: {token_msg or "YouTube Main-OAuth fehlt."}')
            return False
        try:
            broadcast = self._youtube_active_broadcast(token)
        except urllib.error.HTTPError as exc:
            if getattr(exc, 'code', 0) == 401:
                token, token_msg = self._youtube_refresh_main_token(settings)
                if not token:
                    self._log(f'YouTube-Update fehlgeschlagen: {token_msg or "Token Refresh fehlgeschlagen."}')
                    return False
                try:
                    broadcast = self._youtube_active_broadcast(token)
                except urllib.error.HTTPError as exc2:
                    self._log('YouTube-Update fehlgeschlagen: ' + self._format_youtube_http_error(exc2))
                    return False
            else:
                self._log('YouTube-Update fehlgeschlagen: ' + self._format_youtube_http_error(exc))
                return False
        except Exception as exc:
            self._log(f'YouTube-Update fehlgeschlagen: {exc}')
            return False

        if not broadcast:
            self._log('YouTube-Update übersprungen: kein aktiver/kommender Livestream gefunden.')
            return False
        video_id = str(broadcast.get('id') or '').strip()
        if not video_id:
            self._log('YouTube-Update fehlgeschlagen: Video-/Broadcast-ID fehlt.')
            return False

        try:
            msg = self._youtube_update_video_snippet(token, video_id, title=stream_title, tags=out_tags, category=category)
            suffix = f' ({token_msg})' if token_msg else ''
            self._log(f'{reason or "Gewinner"}: YouTube {msg}{suffix}')
            return True
        except urllib.error.HTTPError as exc:
            if getattr(exc, 'code', 0) == 401:
                token, token_msg = self._youtube_refresh_main_token(settings)
                if token:
                    try:
                        msg = self._youtube_update_video_snippet(token, video_id, title=stream_title, tags=out_tags, category=category)
                        self._log(f'{reason or "Gewinner"}: YouTube {msg} (Token per Refresh erneuert)')
                        return True
                    except urllib.error.HTTPError as exc2:
                        self._log('YouTube-Update fehlgeschlagen: ' + self._format_youtube_http_error(exc2))
                        return False
                self._log(f'YouTube-Update fehlgeschlagen: {token_msg or "Token Refresh fehlgeschlagen."}')
                return False
            self._log('YouTube-Update fehlgeschlagen: ' + self._format_youtube_http_error(exc))
            return False
        except Exception as exc:
            self._log(f'YouTube-Update fehlgeschlagen: {exc}')
            return False

    def _apply_winner_kick_info(self, game: dict[str, Any] | None, reason: str = '') -> bool:
        if not game:
            return False
        title_name, stream_title, tags = self._winner_stream_payload(game)
        category = str(game.get('kick_category') or game.get('twitch_game_name') or title_name).strip()
        out_tags = tags if _as_bool(self._settings.get('kick_update_tags'), False) else []
        settings = self._platform_settings('kick')
        token, token_msg = self._kick_get_main_token(settings)
        if not token:
            self._log(f'Kick-Update übersprungen: {token_msg or "Kick Main-OAuth fehlt."}')
            return False

        changed: list[str] = []
        errors: list[str] = []
        skipped: list[str] = []

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

        if stream_title:
            ok, msg = do_patch({'stream_title': stream_title[:120]})
            if ok:
                changed.append('Titel')
            else:
                errors.append('Titel: ' + msg)

        if category:
            category_id = category if category.isdigit() else ''
            if not category_id:
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
            else:
                skipped.append(f'Kategorie nicht aufgelöst: {category}')

        if out_tags:
            ok, msg = do_patch({'custom_tags': out_tags[:10]})
            if ok:
                changed.append('Tags')
            else:
                errors.append('Tags: ' + msg)

        suffix = f' ({token_msg})' if token_msg else ''
        if errors:
            self._log(f'{reason or "Gewinner"}: Kick teilweise/gar nicht aktualisiert: ' + ' | '.join(errors) + ((' | Übersprungen: ' + ', '.join(skipped)) if skipped else ''))
            return False
        if changed:
            self._log(f'{reason or "Gewinner"}: Kick ' + ', '.join(changed) + ' aktualisiert.' + ((' | Übersprungen: ' + ', '.join(skipped)) if skipped else '') + suffix)
            return True
        self._log(f'{reason or "Gewinner"}: Kick keine Änderung gesendet.' + ((' | Übersprungen: ' + ', '.join(skipped)) if skipped else ''))
        return False

    def _youtube_get_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        main_refresh = str(settings.get('main_refresh_token') or '').strip()
        if main_refresh:
            return self._youtube_refresh_main_token(settings, main_only=True)
        token = self._clean_bearer_token(settings.get('main_access_token'))
        if token:
            return token, 'Main-Token genutzt, aber kein Main-Refresh-Token gefunden'
        refresh = str(settings.get('refresh_token') or '').strip()
        if refresh:
            return self._youtube_refresh_main_token(settings, main_only=False)
        token = self._clean_bearer_token(settings.get('access_token'))
        if token:
            return token, 'Fallback-Access-Token genutzt, Main-OAuth fehlt'
        return '', 'YouTube Main-OAuth fehlt. Bitte im Haupttool YouTube Main neu anmelden.'

    def _youtube_refresh_main_token(self, settings: dict[str, Any], main_only: bool = True) -> tuple[str, str]:
        refresh = str(settings.get('main_refresh_token') or '').strip()
        if not refresh and not main_only:
            refresh = str(settings.get('refresh_token') or '').strip()
        client_id = str(settings.get('client_id') or '').strip()
        client_secret = str(settings.get('client_secret') or '').strip()
        if not refresh:
            return '', 'YouTube Main-Refresh-Token fehlt. Bitte im Haupttool YouTube Main neu anmelden.'
        if not client_id:
            return '', 'YouTube Client ID fehlt.'
        payload = {'client_id': client_id, 'grant_type': 'refresh_token', 'refresh_token': refresh}
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
            access = str((data or {}).get('access_token') or '').strip() if isinstance(data, dict) else ''
            if not access:
                return '', 'YouTube Refresh lieferte keinen Access Token.'
            return access, 'Token per Refresh erneuert'
        except urllib.error.HTTPError as exc:
            return '', self._format_youtube_http_error(exc)
        except Exception as exc:
            return '', f'YouTube Refresh fehlgeschlagen: {exc}'

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
            'title': title[:100] if title else str(old_snippet.get('title') or '').strip(),
            'description': description if description else str(old_snippet.get('description') or '').strip(),
            'categoryId': str(old_snippet.get('categoryId') or '').strip() or '20',
        }
        old_tags = old_snippet.get('tags')
        if tags:
            new_snippet['tags'] = tags
        elif isinstance(old_tags, list):
            new_snippet['tags'] = [str(t) for t in old_tags if str(t).strip()]
        category = str(category or '').strip()
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
        if tags:
            changed.append('Tags')
        if category.isdigit():
            changed.append(f'Kategorie-ID {category}')
        return ', '.join(changed) + ' aktualisiert.' if changed else 'Video-Snippet aktualisiert.'

    def _format_youtube_http_error(self, exc: urllib.error.HTTPError) -> str:
        try:
            raw_detail = exc.read().decode('utf-8', errors='replace')
        except Exception:
            raw_detail = str(exc)
        detail = raw_detail[:500]
        if getattr(exc, 'code', 0) == 403 and ('quotaExceeded' in raw_detail or 'youtube.quota' in raw_detail or 'exceeded your' in raw_detail):
            self._youtube_quota_blocked_until = time.time() + 3600.0
            return 'YouTube API-Quota ist aufgebraucht. Senden wird vorerst übersprungen, damit nicht weiter sinnlos API-Requests verbraten werden.'
        return f'HTTP {getattr(exc, "code", "?")} {detail}'

    def _kick_get_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        main_token = self._clean_bearer_token(settings.get('main_access_token'))
        if main_token:
            return main_token, 'Main-Token genutzt'
        if str(settings.get('main_refresh_token') or '').strip():
            return self._kick_refresh_main_token(settings)
        token = self._clean_bearer_token(settings.get('access_token'))
        if token:
            return token, 'Fallback-Access-Token genutzt, Main-OAuth fehlt'
        return '', 'Kick Main-OAuth fehlt. Bitte im Haupttool Kick Main neu anmelden.'

    def _kick_refresh_main_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        refresh = str(settings.get('main_refresh_token') or '').strip()
        client_id = str(settings.get('client_id') or '').strip()
        client_secret = str(settings.get('client_secret') or '').strip()
        if not refresh:
            return '', 'Kick Main-Refresh-Token fehlt. Bitte im Haupttool Kick Main neu anmelden.'
        if not client_id or not client_secret:
            return '', 'Kick Client ID oder Client Secret fehlt.'
        payload = {'grant_type': 'refresh_token', 'client_id': client_id, 'client_secret': client_secret, 'refresh_token': refresh}
        req = urllib.request.Request(
            KICK_TOKEN_URL,
            data=urllib.parse.urlencode(payload).encode('utf-8'),
            headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
            access = str((data or {}).get('access_token') or '').strip() if isinstance(data, dict) else ''
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
            headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            method='PATCH',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()

    def _kick_resolve_category_id(self, token: str, category: str) -> str:
        query = str(category or '').strip()
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
        wanted = query.lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name') or '').strip().lower()
            if name == wanted:
                cid = str(row.get('id') or '').strip()
                return cid if cid.isdigit() else ''
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = str(row.get('id') or '').strip()
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

    def _get_twitch_user_id(self, login: str, client_id: str, token: str) -> str:
        login = str(login or '').strip().lstrip('@#').lower()
        if not client_id or not token:
            return ''
        try:
            if login:
                url = f'{TWITCH_HELIX_URL}/users?' + urllib.parse.urlencode({'login': login})
            else:
                url = f'{TWITCH_HELIX_URL}/users'
            data = self._http_json(url, headers={'Client-ID': client_id, 'Authorization': f'Bearer {token}'})
            arr = data.get('data') if isinstance(data, dict) else []
            if arr:
                return _safe_text(arr[0].get('id'))
        except Exception as exc:
            self._log(f'Twitch Broadcaster-ID Suche fehlgeschlagen: {exc}')
        return ''

    def _patch_twitch_channel_info(self, broadcaster_id: str, client_id: str, token: str, *, title: str = '', game_id: str = '', tags: list[str] | None = None) -> tuple[bool, str]:
        payload: dict[str, Any] = {}
        if title is not None and str(title).strip():
            payload['title'] = str(title).strip()[:140]
        if game_id:
            payload['game_id'] = str(game_id).strip()

        if tags is not None:
            import unicodedata
            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in (tags or []):
                s = str(raw or '').strip()
                if not s:
                    continue
                if s.startswith('#'):
                    s = s[1:].strip()
                s = (s.replace('ß', 'ss')
                       .replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue')
                       .replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue'))
                try:
                    s = unicodedata.normalize('NFKD', s)
                    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
                except Exception:
                    pass
                if ' ' in s:
                    parts = [p for p in s.replace('\t', ' ').split(' ') if p]
                    s = ''.join(p[:1].upper() + p[1:] for p in parts)
                s = ''.join(ch for ch in s if ('0' <= ch <= '9') or ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))[:25]
                if not s or s.lower() in seen:
                    continue
                seen.add(s.lower())
                cleaned.append(s)
                if len(cleaned) >= 10:
                    break
            if cleaned:
                payload['tags'] = cleaned
            elif len(tags or []) == 0:
                payload['tags'] = []

        if not payload:
            return False, 'kein Titel/Kategorie/Tag gesetzt'
        url = f'{TWITCH_HELIX_URL}/channels?' + urllib.parse.urlencode({'broadcaster_id': broadcaster_id})

        def _do_patch(body: dict[str, Any]) -> tuple[int, str]:
            raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(url, data=raw, method='PATCH', headers={
                'Client-ID': client_id,
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    txt = resp.read().decode('utf-8', errors='replace')
                    return int(resp.status), txt
            except urllib.error.HTTPError as e:
                try:
                    txt = e.read().decode('utf-8', errors='replace')[:600].replace('\r', ' ').replace('\n', ' ')
                except Exception:
                    txt = str(e)
                return int(getattr(e, 'code', 0) or 0), txt

        try:
            code, txt = _do_patch(payload)
            if code in (200, 204):
                return True, ', '.join(payload.keys())
            if code == 400 and 'tags' in payload:
                retry = dict(payload)
                retry.pop('tags', None)
                rcode, rtxt = _do_patch(retry)
                if rcode in (200, 204):
                    return True, 'tags abgelehnt, Titel/Kategorie ohne Tags gesetzt'
                return False, f'HTTP {code} {txt} | retry(no-tags)-> HTTP {rcode} {rtxt}'
            return False, f'HTTP {code} {txt}'
        except Exception as exc:
            return False, f'{type(exc).__name__}: {exc}'

    def _send_winner_link(self, platform: str, username: str) -> None:
        if not _as_bool(self._settings.get('chat_send_links'), False):
            return
        game = self._game_by_id(self._last_winner_id)
        if not game:
            self._send_to_platform(platform, 'Sorry, no link found.')
            return
        url = self._best_link(game)
        if not url:
            self._send_to_platform(platform, 'Sorry, no link found.')
            return
        self._send_to_platform(platform, f'{game.get("title", "Game")}: {url}')

    def _send_to_all_write_enabled(self, message: str) -> None:
        sent_any = False
        for p in ['twitch', 'tiktok', 'youtube', 'kick']:
            ps = self._platform_settings(p)
            if _as_bool(ps.get('write_enabled'), False):
                sent_any = True
                self._send_to_platform(p, message)
        if not sent_any:
            # Gewinnernachricht darf nicht still verschwinden, wenn die zentrale
            # Plattform-Schreibflagge fehlt oder nicht geladen wurde. Twitch ist
            # für gam3pick3r der Hauptpfad und wird über das Haupttool gesendet.
            self._send_to_platform('twitch', message)

    def _send_winner_announcement(self, message: str, preferred_platform: str = '') -> None:
        if not str(message or '').strip():
            return
        targets: list[str] = []
        pref = _clean_platform(preferred_platform)
        if pref:
            targets.append(pref)
        for p in ['twitch', 'youtube', 'kick', 'tiktok']:
            ps = self._platform_settings(p)
            if _as_bool(ps.get('write_enabled'), False) and p not in targets:
                targets.append(p)
        if 'twitch' not in targets:
            # Sichere Rückfallebene: bei gam3pick3r muss die Gewinnernachricht
            # mindestens im Twitch-Chat landen, auch wenn die zentralen
            # write_enabled-Flags gerade nicht sauber geladen wurden.
            targets.append('twitch')

        # Invisible-only marker: botalot can identify this as a plugin/system announcement
        # and must not bridge it again after each chat plugin reads it back.
        out_message = GAM3PICK3R_SYSTEM_MARKER + str(message or '').strip()

        ok_any = False
        for p in targets:
            if self._send_to_platform(p, out_message):
                ok_any = True
        if not ok_any:
            self._log('Gewinnernachricht konnte auf keiner Plattform gesendet werden.')

    def _send_to_platform(self, platform: str, message: str) -> bool:
        p = _clean_platform(platform)
        if not message:
            return False
        host = self._host
        if host is not None and hasattr(host, 'send_platform_message'):
            try:
                if p == 'twitch':
                    try:
                        ok = bool(host.send_platform_message(p, message, account='bot', use_bot=True, sender='bot'))
                    except TypeError:
                        ok = bool(host.send_platform_message(p, message))
                else:
                    ok = bool(host.send_platform_message(p, message))
                self._log(('Chat-Ausgabe gesendet: ' if ok else 'Chat-Ausgabe fehlgeschlagen: ') + f'{p or platform} -> {message}')
                return ok
            except Exception as exc:
                self._log(f'Chat-Ausgabe über Haupttool fehlgeschlagen ({p or platform}): {exc}')
                return False
        self._log(f'Chat-Ausgabe für {p or platform} nicht möglich: Host bietet send_platform_message nicht an.')
        return False

    def _send_twitch(self, message: str) -> bool:
        return self._send_to_platform('twitch', message)

    def _broadcast_cache_paths(self) -> list[Path]:
        return [TWITCH_BROADCAST_CACHE_FILE]

    def _save_twitch_broadcast_cache(self, cache: dict[str, Any]) -> None:
        clean = dict(cache or {})
        clean.pop('_cache_path', None)
        wrote = False
        for path in self._broadcast_cache_paths():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding='utf-8')
                wrote = True
            except Exception:
                pass
        if not wrote:
            self._log('Twitch Streamtitel-OAuth konnte nicht gespeichert werden.')

    def _connect_twitch_broadcast_account(self) -> bool:
        ps = self._platform_settings('twitch')
        channel = _safe_text(
            ps.get('channel') or ps.get('main_account') or ps.get('broadcaster_login') or
            ps.get('broadcaster_name') or ps.get('username')
        ).lstrip('@#').lower()
        ok, msg, cache = self._start_twitch_broadcast_oauth(ps, channel)
        self._log(msg)
        if ok and cache:
            self._save_twitch_broadcast_cache(cache)
            return True
        return False

    def _start_twitch_broadcast_oauth(self, ps: dict[str, Any], channel: str) -> tuple[bool, str, dict[str, Any]]:
        client_id = _safe_text(ps.get('client_id'))
        client_secret = _safe_text(ps.get('client_secret'))
        if not client_id or not client_secret:
            return False, 'Twitch Streamtitel-OAuth fehlgeschlagen: Client-ID oder Secret fehlt.', {}
        try:
            port = int(ps.get('redirect_port') or 17564)
        except Exception:
            port = 17564
        redirect_uri = f'http://localhost:{port}/callback/'
        state = str(random.randint(100000, 999999)) + secrets_token()
        code_box = {'code': '', 'state': '', 'error': ''}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != '/callback':
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
                html_done = '<html><body style="font-family:sans-serif;background:#111;color:#eee"><h3>gam3pick3r Twitch fertig</h3><p>Wenn hier der Hauptaccount verbunden wurde, kannst du das Fenster schließen.</p></body></html>'
                self.wfile.write(html_done.encode('utf-8'))
        try:
            httpd = HTTPServer(('127.0.0.1', port), Handler)
        except Exception as exc:
            return False, f'Twitch Streamtitel-OAuth fehlgeschlagen: Callback-Port {port} konnte nicht geöffnet werden: {exc}', {}
        threading.Thread(target=lambda: httpd.handle_request(), daemon=True).start()
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'channel:manage:broadcast',
            'state': state,
            'force_verify': 'true',
        }
        self._log(f'Twitch Streamtitel-OAuth gestartet. Bitte im Browser als {channel or "Hauptaccount"} anmelden, nicht als Bot.')
        try:
            webbrowser.open('https://id.twitch.tv/oauth2/authorize?' + urllib.parse.urlencode(params), new=2, autoraise=True)
        except Exception:
            pass
        deadline = time.time() + 180.0
        while time.time() < deadline:
            if code_box['error']:
                try:
                    httpd.server_close()
                except Exception:
                    pass
                return False, f'Twitch Streamtitel-OAuth abgebrochen: {code_box["error"]}', {}
            if code_box['code']:
                break
            time.sleep(0.15)
        try:
            httpd.server_close()
        except Exception:
            pass
        if not code_box['code']:
            return False, 'Twitch Streamtitel-OAuth abgebrochen: kein Browser-Callback angekommen.', {}
        if code_box['state'] != state:
            return False, 'Twitch Streamtitel-OAuth abgebrochen: State passt nicht.', {}
        try:
            token_data = self._http_json(TWITCH_TOKEN_URL, method='POST', data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code_box['code'],
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            })
        except Exception as exc:
            return False, f'Twitch Streamtitel-OAuth fehlgeschlagen: Token-Austausch fehlgeschlagen: {exc}', {}
        access = _safe_text(token_data.get('access_token')).replace('oauth:', '')
        refresh = _safe_text(token_data.get('refresh_token'))
        if not access:
            return False, 'Twitch Streamtitel-OAuth fehlgeschlagen: kein Access Token erhalten.', {}
        meta = self._validate_twitch_token(access, client_id)
        login = _safe_text(meta.get('login')).lstrip('@#').lower()
        scopes = self._scope_set(meta.get('scopes') or meta.get('scope'))
        if 'channel:manage:broadcast' not in scopes:
            return False, f'Twitch Streamtitel-OAuth ungültig: channel:manage:broadcast fehlt für {login or "?"}.', {}
        if channel and login and login != channel:
            return False, f'Twitch Streamtitel-OAuth gehört zu {login}, Zielkanal ist {channel}. Bitte wirklich mit dem Hauptaccount verbinden.', {}
        cache = {
            'access_token': access,
            'refresh_token': refresh,
            'username': login,
            'login': login,
            'user_id': _safe_text(meta.get('user_id')),
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_port': str(port),
            'scopes': sorted(scopes),
            'saved_at': int(time.time()),
            'purpose': 'gam3pick3r_broadcast_update',
        }
        return True, f'Twitch Streamtitel-OAuth gespeichert für {login}. Random/Vote darf jetzt Titel und Kategorie setzen.', cache

    def _load_twitch_caches(self) -> list[dict[str, Any]]:
        paths: list[Path] = []
        appdata = os.environ.get('APPDATA')
        if appdata:
            paths.append(Path(appdata) / 'godisalotachat' / 'gam3pick3r' / 'twitch_broadcast_oauth_cache.json')
        paths.append(TWITCH_BROADCAST_CACHE_FILE)
        if appdata:
            paths.append(Path(appdata) / 'godisalotachat' / 'twitch_chat' / 'oauth_cache.json')
        paths.append(Path.home() / '.godisalotachat' / 'gam3pick3r' / 'twitch_broadcast_oauth_cache.json')
        paths.append(Path.home() / '.godisalotachat' / 'twitch_chat' / 'oauth_cache.json')
        paths.append(_main_data_dir('twitch_chat') / 'oauth_cache.json')
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in paths:
            try:
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding='utf-8') or '{}')
                if not isinstance(data, dict):
                    continue
                token = _safe_text(data.get('access_token')) or _safe_text(data.get('refresh_token'))
                if not token:
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                row = dict(data)
                row['_cache_path'] = str(path)
                out.append(row)
            except Exception:
                pass
        return out

    def _load_twitch_cache(self) -> dict[str, Any]:
        caches = self._load_twitch_caches()
        return dict(caches[0]) if caches else {}

    def _save_twitch_cache(self, cache: dict[str, Any]) -> None:
        path = TWITCH_BROADCAST_CACHE_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            clean = dict(cache)
            clean.pop('_cache_path', None)
            path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

    def _validate_twitch_token(self, token: str, client_id: str = '') -> dict[str, Any]:
        token = _safe_text(token).replace('oauth:', '')
        if not token:
            return {}
        try:
            data = self._http_json(TWITCH_VALIDATE_URL, headers={'Authorization': f'OAuth {token}'})
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._log(f'Twitch Token Validate fehlgeschlagen: {exc}')
            return {}

    def _scope_set(self, value: Any) -> set[str]:
        if isinstance(value, str):
            return {x.strip() for x in value.replace(',', ' ').split() if x.strip()}
        return {str(x).strip() for x in (value or []) if str(x).strip()}

    def _pick_twitch_broadcast_auth(self, ps: dict[str, Any], channel: str) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        client_id = _safe_text(ps.get('client_id'))
        client_secret = _safe_text(ps.get('client_secret'))
        candidates: list[dict[str, Any]] = []
        if _safe_text(ps.get('access_token') or ps.get('oauth_token') or ps.get('refresh_token')):
            row = dict(ps)
            row['_cache_path'] = ''
            candidates.append(row)
        candidates.extend(self._load_twitch_caches())
        best: tuple[int, str, str, dict[str, Any], dict[str, Any]] | None = None
        for cache in candidates:
            cid = _safe_text(cache.get('client_id') or client_id)
            csec = _safe_text(cache.get('client_secret') or client_secret)
            token = _safe_text(cache.get('access_token') or cache.get('oauth_token')).replace('oauth:', '')
            if not token and cache.get('refresh_token') and cid and csec:
                token = self._refresh_twitch_token(cache, cid, csec)
            if not token or not cid:
                continue
            meta = self._validate_twitch_token(token, cid)
            scopes = self._scope_set(meta.get('scopes') or meta.get('scope') or cache.get('scopes') or cache.get('scope'))
            login = _safe_text(meta.get('login') or cache.get('username') or cache.get('login')).lstrip('@#').lower()
            uid = _safe_text(meta.get('user_id') or cache.get('user_id'))
            score = 0
            if 'channel:manage:broadcast' in scopes:
                score += 100
            if channel and login == channel:
                score += 50
            if uid:
                score += 5
            if best is None or score > best[0]:
                merged = dict(cache)
                merged.update({'scopes': list(scopes), 'username': login, 'user_id': uid})
                best = (score, cid, token, merged, meta)
        if best:
            return best[1], best[2], best[3], best[4]
        return client_id, '', {}, {}

    def _http_json(self, url: str, *, method: str = 'GET', data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = None
        final_headers = dict(headers or {})
        final_headers.setdefault('User-Agent', 'gam3pick3r/0.10 (+godisalotachat)')
        if data is not None:
            body = urllib.parse.urlencode(data).encode('utf-8')
            final_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(url, data=body, headers=final_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode('utf-8', errors='replace').strip()
            except Exception:
                raw = ''
            if len(raw) > 500:
                raw = raw[:500] + '...'
            detail = f'HTTP {exc.code} {getattr(exc, "reason", "")}'.strip()
            if raw:
                detail += f' · {raw}'
            raise RuntimeError(detail) from exc

    def _refresh_twitch_token(self, cache: dict[str, Any], client_id: str, client_secret: str) -> str:
        refresh = _safe_text(cache.get('refresh_token'))
        if not refresh:
            return ''
        try:
            data = self._http_json(TWITCH_TOKEN_URL, method='POST', data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh,
                'client_id': client_id,
                'client_secret': client_secret,
            })
            token = _safe_text(data.get('access_token')).replace('oauth:', '')
            if token:
                cache.update({
                    'access_token': token,
                    'refresh_token': _safe_text(data.get('refresh_token')) or refresh,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'saved_at': int(time.time()),
                })
                self._save_twitch_cache(cache)
                return token
        except Exception as exc:
            self._log(f'Twitch Token Refresh fehlgeschlagen: {exc}')
        return ''

    def _platform_settings(self, platform: str) -> dict[str, Any]:
        host = self._host
        if host is None:
            return {}
        try:
            data = host.platform_settings(platform)
            return dict(data or {})
        except Exception:
            return {}

    def _allowed_platforms(self, settings: dict[str, Any]) -> set[str]:
        raw = str(settings.get('platforms_csv') or '').strip()
        if not raw:
            return set()
        return {_clean_platform(x.strip()) for x in raw.replace(';', ',').split(',') if x.strip()}

    def _start_overlay_if_needed(self) -> None:
        try:
            if self._server is not None:
                self._server.stop()
                self._server = None
        except Exception:
            pass
        if not _as_bool(self._settings.get('browser_overlay_enabled'), True):
            return
        try:
            self._server = _OverlayServer(_to_int(self._settings.get('browser_overlay_port'), 17623, 1024, 65535), self._state)
            self._server.start()
        except Exception as exc:
            self._log(f'Overlay-Server konnte nicht gestartet werden: {exc}')

    def _push_state(self, winner_id: str = '') -> None:
        games = self._games or []
        self._prune_runtime_game_state()
        vote_games = [self._game_by_id(gid) for gid in self._vote_candidates]
        vote_games = [g for g in vote_games if g]
        leader_id = self._compute_vote_winner() if self._vote_active else ''
        winner = self._game_by_id(leader_id or winner_id or self._last_winner_id)
        mode = 'vote' if self._vote_active else ('rolling' if self._picker_active else ('picked' if winner else 'idle'))
        bg_enabled = _as_bool(self._settings.get('overlay_background_enabled'), False)
        bg_path = str(self._settings.get('overlay_background_image') or '').strip()
        bg_url = ('/background?v=' + str(int(time.time()))) if (bg_enabled and bg_path) else ''
        self._state.set(
            mode=mode,
            title=str(self._settings.get('overlay_title') or 'gam3pick3r'),
            greenscreen=str(self._settings.get('greenscreen_hex') or '#00FF00'),
            bg_image={'enabled': bool(bg_enabled and bg_path), 'url': bg_url, 'mode': str(self._settings.get('overlay_background_mode') or 'cover').strip().lower() or 'cover'},
            bg_image_path=bg_path,
            games=self._overlay_games(games),
            picked=self._overlay_game(winner) if winner else None,
            vote_active=self._vote_active,
            vote_end_at=self._vote_end_at,
            vote_duration=_to_int(self._settings.get('vote_duration_sec'), 60, 5, 7200),
            vote_games=self._overlay_games(vote_games),
            vote_votes=dict(self._votes),
            vote_command=str(self._settings.get('vote_command') or '!vote').strip() or '!vote',
            roll_step_sec=max(0.2, min(60.0, float(self._settings.get('random_switch_interval_sec') or 1.0))),
        )

    def _overlay_games(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._overlay_game(g) for g in games if g]

    def _overlay_game(self, g: dict[str, Any] | None) -> dict[str, Any] | None:
        if not g:
            return None
        return {
            'id': str(g.get('id') or ''),
            'title': str(g.get('title') or ''),
            'cover': str(g.get('cover') or ''),
            'cover_url': self._cover_url(str(g.get('cover') or '')),
            'num': int(g.get('num') or 0),
            'enabled': _as_bool(g.get('enabled'), True),
        }

    def _load_current_games(self, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # Source of truth is the plugin file. The multiline field is only imported
        # when the user explicitly presses "Feld in Plugin-Datei speichern".
        # Otherwise deleted games could come back from stale UI text.
        games = self._load_games()
        if games:
            return games
        settings = dict(settings or self._settings or {})
        txt = str(settings.get('games_text') or '').strip()
        if txt:
            games = self._parse_games_text(txt)
            self._save_games(games)
            return games
        return []

    def _prune_runtime_game_state(self) -> None:
        valid = {str(g.get('id') or '') for g in (self._games or [])}
        valid_titles = {str(g.get('title') or '').strip().lower() for g in (self._games or [])}
        with self._lock:
            self._vote_candidates = [gid for gid in self._vote_candidates if gid in valid]
            self._votes = {gid: v for gid, v in self._votes.items() if gid in valid}
            self._voted_users = {u: gid for u, gid in self._voted_users.items() if gid in valid}
            self._vote_num_map = {n: gid for n, gid in self._vote_num_map.items() if gid in valid}
            if self._last_winner_id and self._last_winner_id not in valid:
                self._last_winner_id = ''
            if self._pending_pick_id and self._pending_pick_id not in valid:
                self._pending_pick_id = ''
                self._picker_active = False
                self._picker_end_at = 0.0

    def _load_games(self) -> list[dict[str, Any]]:
        _ensure_dirs()
        try:
            if GAMES_FILE.exists():
                data = json.loads(GAMES_FILE.read_text(encoding='utf-8') or '{}')
                games = data.get('games') if isinstance(data, dict) else []
                if isinstance(games, list):
                    return [self._normalize_game(g) for g in games if isinstance(g, dict)]
        except Exception as exc:
            self._log(f'games.json konnte nicht gelesen werden: {exc}')
        return []

    def _save_games(self, games: list[dict[str, Any]]) -> None:
        _ensure_dirs()
        GAMES_FILE.write_text(json.dumps({'games': [self._normalize_game(g) for g in games]}, indent=2, ensure_ascii=False), encoding='utf-8')


    def _game_title(self, g: dict[str, Any], idx: int = 0, fallback: str = '') -> str:
        for key in ('title', 'name', 'game', 'game_name', 'twitch_game_name', 'category'):
            value = str((g or {}).get(key) or '').strip()
            if value:
                return value
        if fallback:
            return str(fallback).strip()
        return f'Spiel {idx}' if idx else 'Spiel'

    def _normalize_game(self, g: dict[str, Any]) -> dict[str, Any]:
        gid = str(g.get('id') or '').strip()
        if not gid:
            import uuid
            gid = str(uuid.uuid4())
        links = g.get('links') if isinstance(g.get('links'), dict) else {}
        # keep legacy flat link keys too
        for k in ['steam', 'epic', 'ubisoft', 'gog', 'website']:
            if g.get(k) and not links.get(k):
                links[k] = str(g.get(k) or '').strip()
        title = self._game_title(g, fallback=gid)
        return {
            'id': gid,
            'title': title,
            'cover': str(g.get('cover') or g.get('cover_file') or '').strip(),
            'enabled': _as_bool(g.get('enabled'), True),
            'num': _to_int(g.get('num') or g.get('vote_number'), 0, 0, 999),
            'links': {str(k): str(v).strip() for k, v in links.items() if str(v).strip()},
            'stream_title': str(g.get('stream_title') or '').strip(),
            'twitch_game_name': str(g.get('twitch_game_name') or g.get('game_name') or g.get('category') or '').strip(),
            'kick_category': str(g.get('kick_category') or g.get('kick_game_name') or '').strip(),
            'youtube_category': str(g.get('youtube_category') or g.get('youtube_category_id') or '').strip(),
            'tags': g.get('tags') if isinstance(g.get('tags'), list) else [],
            'twitch_id': str(g.get('twitch_id') or '').strip(),
        }

    def _parse_games_text(self, text: str) -> list[dict[str, Any]]:
        games: list[dict[str, Any]] = []
        for line in str(text or '').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|')]
            title = parts[0].strip()
            if not title:
                continue
            g: dict[str, Any] = {'title': title, 'enabled': True, 'links': {}}
            for p in parts[1:]:
                if not p:
                    continue
                if '=' not in p:
                    continue
                k, v = p.split('=', 1)
                k = k.strip().lower()
                v = v.strip()
                if k in {'num', 'vote_number'}:
                    g['num'] = _to_int(v, 0, 0, 999)
                elif k in {'cover', 'cover_file'}:
                    g['cover'] = v
                elif k == 'enabled':
                    g['enabled'] = _as_bool(v, True)
                elif k in {'steam', 'epic', 'ubisoft', 'gog', 'website'}:
                    g.setdefault('links', {})[k] = v
                elif k == 'stream_title':
                    g['stream_title'] = v
                elif k in {'twitch_game_name', 'game_name', 'category'}:
                    g['twitch_game_name'] = v
                elif k in {'kick_category', 'kick_game_name'}:
                    g['kick_category'] = v
                elif k in {'youtube_category', 'youtube_category_id'}:
                    g['youtube_category'] = v
                elif k == 'tags':
                    g['tags'] = [x.strip() for x in v.replace(';', ',').split(',') if x.strip()]
                elif k in {'twitch_id', 'game_id'}:
                    g['twitch_id'] = v
            games.append(self._normalize_game(g))
        return games

    def _games_to_text(self, games: list[dict[str, Any]]) -> str:
        lines = []
        for g in games:
            parts = [str(g.get('title') or '')]
            if int(g.get('num') or 0) > 0:
                parts.append(f'num={int(g.get("num") or 0)}')
            if g.get('cover'):
                parts.append(f'cover={g.get("cover")}')
            if g.get('twitch_game_name'):
                parts.append(f'twitch_game_name={g.get("twitch_game_name")}')
            if g.get('twitch_id'):
                parts.append(f'twitch_id={g.get("twitch_id")}')
            if g.get('kick_category'):
                parts.append(f'kick_category={g.get("kick_category")}')
            if g.get('youtube_category'):
                parts.append(f'youtube_category={g.get("youtube_category")}')
            if g.get('stream_title'):
                parts.append(f'stream_title={g.get("stream_title")}')
            if g.get('tags'):
                parts.append('tags=' + ','.join([str(x) for x in (g.get('tags') or [])]))
            for k, v in (g.get('links') or {}).items():
                parts.append(f'{k}={v}')
            if not _as_bool(g.get('enabled'), True):
                parts.append('enabled=false')
            lines.append(' | '.join(parts))
        return '\n'.join(lines)

    def _game_by_id(self, gid: str) -> dict[str, Any] | None:
        for g in self._games:
            if str(g.get('id') or '') == str(gid or ''):
                return g
        return None

    def _best_link(self, game: dict[str, Any]) -> str:
        links = game.get('links') if isinstance(game.get('links'), dict) else {}
        for k in ['steam', 'epic', 'ubisoft', 'gog', 'website']:
            v = str(links.get(k) or '').strip()
            if v:
                return v
        return ''

    def _format_template(self, template: str, game: str, fallback: str) -> str:
        t = (template or fallback).strip() or fallback
        try:
            return t.replace('{game}', game)
        except Exception:
            return f'{t} {game}'

    def _log(self, message: str) -> None:
        try:
            if self._host is not None:
                self._host.log(self.plugin_id, message)
        except Exception:
            pass


def create_plugin() -> Gam3Pick3rPlugin:
    return Gam3Pick3rPlugin()
