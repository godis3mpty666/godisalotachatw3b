from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


OVERLAY_HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>al3rtalot</title>
<style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent;font-family:Segoe UI,Arial,sans-serif}.wrap{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;padding:40px;pointer-events:none}.alert{min-width:min(760px,90vw);max-width:min(960px,92vw);padding:28px 34px;border-radius:28px;background:rgba(12,12,18,.82);border:2px solid color-mix(in srgb,var(--accent,#ff2d55) 72%,white 28%);box-shadow:0 22px 90px rgba(0,0,0,.48),0 0 44px color-mix(in srgb,var(--accent,#ff2d55) 42%,transparent);color:white;opacity:0;transform:translateY(34px) scale(.94);transition:opacity .28s ease,transform .28s cubic-bezier(.2,.9,.25,1);backdrop-filter:blur(8px)}.alert.show{opacity:1;transform:translateY(0) scale(1)}.badge{display:inline-flex;align-items:center;margin-bottom:12px;padding:6px 13px;border-radius:999px;background:var(--accent,#ff2d55);color:#08080b;font-weight:900;text-transform:uppercase;letter-spacing:.08em;font-size:14px}.title{font-size:42px;line-height:1.06;font-weight:950;text-shadow:0 4px 20px rgba(0,0,0,.35);margin-bottom:8px}.line{font-size:26px;line-height:1.25;font-weight:750;opacity:.96;word-break:break-word}.empty{position:fixed;right:14px;bottom:10px;color:rgba(255,255,255,.22);font-size:12px}
</style>
</head>
<body>
<div class="wrap"><div id="alert" class="alert"><div id="badge" class="badge">al3rtalot</div><div id="title" class="title">Bereit</div><div id="line" class="line"></div></div></div><div id="empty" class="empty">al3rtalot</div>
<script>
let lastId=0;let hideTimer=null;
const alertBox=document.getElementById('alert'), badge=document.getElementById('badge'), title=document.getElementById('title'), line=document.getElementById('line'), empty=document.getElementById('empty');
function esc(s){return String(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function tick(){
  try{
    const r=await fetch('/state?ts='+Date.now(),{cache:'no-store'});
    const d=await r.json();
    const a=d.latest||null;
    if(a && Number(a.id||0)!==lastId){
      lastId=Number(a.id||0);
      alertBox.style.setProperty('--accent',a.color||'#ff2d55');
      badge.textContent=a.platform_label||a.platform||'al3rtalot';
      title.textContent=a.title||'Alert';
      line.textContent=a.text||'';
      empty.style.display='none';
      alertBox.classList.add('show');
      clearTimeout(hideTimer);
      hideTimer=setTimeout(()=>alertBox.classList.remove('show'), Math.max(1000, Number(d.duration_ms||6000)));
    }
  }catch(e){}
  setTimeout(tick,500);
}
tick();
</script>
</body>
</html>"""


class OverlayState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.latest: dict[str, Any] | None = None
        self.duration_ms = 6000
        self.history: list[dict[str, Any]] = []

    def set_settings(self, *, duration_ms: int) -> None:
        with self.lock:
            self.duration_ms = max(1000, int(duration_ms or 6000))

    def push(self, alert: dict[str, Any]) -> None:
        with self.lock:
            item = dict(alert or {})
            item.setdefault('id', int(time.time() * 1000))
            self.latest = item
            self.history.append(item)
            self.history = self.history[-50:]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {'latest': self.latest, 'duration_ms': self.duration_ms, 'history': list(self.history[-20:])}


class AlertOverlayServer:
    def __init__(self, port: int, state: OverlayState, log) -> None:
        self.port = int(port)
        self.state = state
        self.log = log
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.port}/'

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path.startswith('/state'):
                    body = json.dumps(state.snapshot(), ensure_ascii=False).encode('utf-8')
                    self._send(200, body, 'application/json; charset=utf-8')
                    return
                self._send(200, OVERLAY_HTML.encode('utf-8'), 'text/html; charset=utf-8')

        try:
            self._httpd = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name='al3rtalot-overlay')
            self._thread.start()
            return True
        except Exception as exc:
            self._httpd = None
            self.log(f'Overlay server failed on port {self.port}: {exc}')
            return False

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
