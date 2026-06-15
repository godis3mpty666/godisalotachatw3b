from __future__ import annotations

import html
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


class RouteHttpServer:
    def __init__(
        self,
        host: str,
        port: int,
        route_provider: Callable[[], list[dict[str, Any]]],
        payload_reader: Callable[[Path, str], str],
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._route_provider = route_provider
        self._payload_reader = payload_reader
        self._logger = logger
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        parent = self

        class Handler(BaseHTTPRequestHandler):
            server_version = 'MeldControlRouteHTTP/1.0'
            def do_GET(self) -> None:  # noqa: N802
                parent._handle(self)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                if parent._logger:
                    try:
                        parent._logger(format % args)
                    except Exception:
                        pass

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name='meld-control-http', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        finally:
            self._httpd = None
            self._thread = None

    def _resolve_route(self, route_id: int) -> dict[str, Any] | None:
        routes = self._route_provider() or []
        if route_id < 0 or route_id >= len(routes):
            return None
        route = dict(routes[route_id] or {})
        if not bool(route.get('enabled', True)):
            return None
        return route

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path or '/'
        if path in ('/', '/health'):
            self._send_text(handler, 'ok')
            return
        if path == '/routes':
            routes = self._route_provider() or []
            data = []
            for idx, route in enumerate(routes):
                if not bool(route.get('enabled', True)):
                    continue
                slug = str(route.get('url_slug', '') or '').strip().strip('/')
                browser_url = f'/{slug}' if slug else f'/route/{idx}/browser'
                data.append({
                    'id': idx,
                    'file_path': str(route.get('file_path', '') or ''),
                    'value_type': str(route.get('value_type', 'text') or 'text'),
                    'url_slug': slug,
                    'browser_url': browser_url,
                    'raw_url': f'/route/{idx}/raw',
                })
            self._send_json(handler, {'routes': data})
            return

        route_by_slug = self._resolve_route_by_slug(path)
        if route_by_slug is not None:
            route_id, route = route_by_slug
            qs = parse_qs(parsed.query)
            file_path = self._route_file_path(route)
            title = qs.get('title', [file_path.name if file_path else f'route-{route_id}'])[0]
            self._send_html(handler, self._render_browser_page(route_id, route, title))
            return

        parts = [p for p in path.split('/') if p]
        if len(parts) != 3 or parts[0] != 'route':
            self._send_error(handler, HTTPStatus.NOT_FOUND, 'not found')
            return
        try:
            route_id = int(parts[1])
        except Exception:
            self._send_error(handler, HTTPStatus.BAD_REQUEST, 'invalid route id')
            return
        action = parts[2].lower()
        route = self._resolve_route(route_id)
        if route is None:
            self._send_error(handler, HTTPStatus.NOT_FOUND, 'route not found')
            return
        file_path = self._route_file_path(route)
        if file_path is None or not file_path.exists():
            self._send_error(handler, HTTPStatus.NOT_FOUND, 'file not found')
            return
        value_type = str(route.get('value_type', 'text') or 'text').strip().lower()
        if value_type.startswith('browser_'):
            value_type = value_type.split('_', 1)[1]
        if action == 'raw':
            if value_type == 'image':
                self._send_binary_file(handler, file_path)
            else:
                self._send_text(handler, self._payload_reader(file_path, 'text'))
            return
        if action == 'image':
            self._send_binary_file(handler, file_path)
            return
        if action == 'text':
            self._send_text(handler, self._payload_reader(file_path, 'text'))
            return
        if action == 'browser':
            qs = parse_qs(parsed.query)
            title = qs.get('title', [file_path.name])[0]
            self._send_html(handler, self._render_browser_page(route_id, route, title))
            return
        self._send_error(handler, HTTPStatus.NOT_FOUND, 'not found')

    def _route_file_path(self, route: dict[str, Any]) -> Path | None:
        file_path = Path(str(route.get('file_path', '') or '')).expanduser()
        if not file_path.is_absolute():
            file_path = (Path.cwd() / file_path).resolve()
        return file_path

    def _resolve_route_by_slug(self, path: str) -> tuple[int, dict[str, Any]] | None:
        slug = str(path or '/').strip().strip('/')
        if not slug:
            return None
        routes = self._route_provider() or []
        for idx, route in enumerate(routes):
            if not isinstance(route, dict) or not bool(route.get('enabled', True)):
                continue
            route_slug = str(route.get('url_slug', '') or '').strip().strip('/')
            if route_slug and route_slug.casefold() == slug.casefold():
                return idx, dict(route)
        return None

    def _send_binary_file(self, handler: BaseHTTPRequestHandler, file_path: Path) -> None:
        content = file_path.read_bytes()
        mime = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
        handler.send_response(HTTPStatus.OK)
        handler.send_header('Content-Type', mime)
        handler.send_header('Content-Length', str(len(content)))
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.end_headers()
        handler.wfile.write(content)

    def _send_text(self, handler: BaseHTTPRequestHandler, text: str) -> None:
        data = (text or '').encode('utf-8')
        handler.send_response(HTTPStatus.OK)
        handler.send_header('Content-Type', 'text/plain; charset=utf-8')
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.end_headers()
        handler.wfile.write(data)

    def _send_json(self, handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        handler.send_response(HTTPStatus.OK)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.end_headers()
        handler.wfile.write(data)

    def _send_html(self, handler: BaseHTTPRequestHandler, markup: str) -> None:
        data = markup.encode('utf-8')
        handler.send_response(HTTPStatus.OK)
        handler.send_header('Content-Type', 'text/html; charset=utf-8')
        handler.send_header('Content-Length', str(len(data)))
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.end_headers()
        handler.wfile.write(data)

    def _send_error(self, handler: BaseHTTPRequestHandler, code: HTTPStatus, text: str) -> None:
        self._send_text(handler, text)

    def _render_browser_page(self, route_id: int, route: dict[str, Any], title: str) -> str:
        safe_title = html.escape(title or 'Meld Route')
        value_type = str(route.get('value_type', 'text') or 'text').strip().lower()
        if value_type.startswith('browser_'):
            value_type = value_type.split('_', 1)[1]
        text_color = html.escape(str(route.get('text_color', '#FFFFFF') or '#FFFFFF'))
        background_color = html.escape(str(route.get('background_color', 'transparent') or 'transparent'))
        font_family = str(route.get('font_family', 'Arial') or 'Arial').strip() or 'Arial'
        font_family_css = ', '.join([f'"{html.escape(part.strip())}"' for part in font_family.split(',') if part.strip()]) or 'Arial'
        font_size = max(8, min(300, int(float(route.get('font_size', 48) or 48))))
        text_align = html.escape(str(route.get('text_align', 'left') or 'left'))
        vertical_align = str(route.get('vertical_align', 'center') or 'center').strip().lower() or 'center'
        justify_map = {'top': 'flex-start', 'center': 'center', 'bottom': 'flex-end'}
        justify = justify_map.get(vertical_align, 'center')
        font_weight = html.escape(str(route.get('font_weight', 'normal') or 'normal'))

        if value_type == 'image':
            body = f"""
<img id="img" alt="{safe_title}" />
<script>
const img = document.getElementById('img');
function refresh() {{
  img.src = '/route/{route_id}/image?ts=' + Date.now();
}}
refresh();
setInterval(refresh, 1000);
</script>
"""
        else:
            body = f"""
<div id="txt-wrap"><div id="txt"></div></div>
<script>
const el = document.getElementById('txt');
async function refresh() {{
  try {{
    const res = await fetch('/route/{route_id}/text?ts=' + Date.now(), {{cache: 'no-store'}});
    el.textContent = await res.text();
  }} catch (e) {{}}
}}
refresh();
setInterval(refresh, 700);
</script>
"""
        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{safe_title}</title>
<style>
html, body {{ margin:0; padding:0; width:100%; height:100%; background:{background_color}; overflow:hidden; }}
body {{ display:flex; align-items:stretch; justify-content:center; background:{background_color}; }}
#img {{ width:100%; height:100%; object-fit:contain; display:block; }}
#txt-wrap {{ width:100%; height:100%; display:flex; align-items:{justify}; justify-content:center; background:{background_color}; }}
#txt {{ width:100%; color:{text_color}; font-family:{font_family_css}, sans-serif; font-size:{font_size}px; font-weight:{font_weight}; text-align:{text_align}; white-space:pre-wrap; word-break:break-word; }}
</style>
</head>
<body>{body}</body>
</html>"""
