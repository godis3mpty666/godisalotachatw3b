# r3adm3

## 0.92 Kick Webhook Patch - 2026-06-25

### Geänderte Dateien
- `core/runtime/webbased_server.py`
- `modules/integrations/kick_chat/plugin.py`
- `modules/integrations/kick_chat/manifest.json`
- `modules/integrations/kick_chat/README.md`
- `modules/integrations/kick_chat/r3adm3.md`
- `README.md`
- `r3adm3.md`

### Betroffene Bereiche
- Kick OAuth Scopes
- Kick Webhook-Eingang im Core
- Kick Event Subscription / Webhook-Verarbeitung in `kick_chat`

### Grund
Kick liefert normale Chats über den bestehenden Realtime/Pusher-Websocket, aber echte Alerts wie Follow/Sub/Gift laufen offiziell über Event-Subscriptions/Webhooks. Dafür braucht Kick den Scope `events:subscribe` und einen Webhook-Eingang.

### Technische Umsetzung
- Kick-Scopes im Core um `events:subscribe` ergänzt.
- `POST /api/webhooks/kick` im Core ergänzt und an `kick_chat.handle_webhook(...)` weitergeleitet.
- `kick_chat` 2.1.8 verarbeitet offizielle Kick-Webhook-Events:
  - `channel.followed`
  - `channel.subscription.new`
  - `channel.subscription.renewal`
  - `channel.subscription.gifts`
  - `kicks.gifted`
  - `livestream.status.updated`
- `chat.message.sent` wird aus Webhooks ignoriert, damit Chat nicht doppelt erscheint.
- Bestehender Kick-Chat-Websocket bleibt erhalten.

### Test
- `python -m py_compile core/runtime/webbased_server.py`
- `python -m py_compile modules/integrations/kick_chat/plugin.py`

### Offene Punkte
- Kick muss nach dem Scope-Update neu per OAuth verbunden werden.
- Für echte Kick-Webhooks muss eine öffentlich erreichbare URL eingetragen werden, z. B. über Cloudflare Tunnel oder ngrok.
