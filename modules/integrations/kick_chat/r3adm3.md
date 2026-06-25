# kick_chat r3adm3

## 2.1.8 - 2026-06-25

### Geänderte Dateien
- `plugin.py`
- `manifest.json`
- `README.md`
- `r3adm3.md`

### Betroffene Funktionen/Bereiche
- Kick Webhook Event Mapping
- Kick Event Subscription
- Kick Diagnose-Log
- Kick Alert-Emission an den Host

### Grund
Der bestehende Kick-Websocket liefert Chat, aber im Test keine echten Follow/Sub/Gift-Alerts. Offizielle Kick-Events kommen über Webhooks/Event-Subscriptions.

### Technische Umsetzung
- `handle_webhook(payload, host, headers)` ergänzt.
- Offizielle Kick-Webhook-Events werden zu internen Alerttypen gemappt:
  - `kick_follow`
  - `kick_sub`
  - `kick_gift`
  - `kick_live_status`
- `chat.message.sent` wird ignoriert, um doppelte Chats zu vermeiden.
- `event_subscriptions_enabled` und `webhook_public_url` ergänzt.
- Event-Subscription-POSTs an `https://api.kick.com/public/v1/events/subscriptions` ergänzt.
- Bestehender Chat-Websocket blieb erhalten.

### Test
- `python -m py_compile plugin.py`

### Offene Punkte
- Für echte Webhooks muss im Plugin eine öffentliche Webhook-URL gesetzt werden.
- Kick muss mit `events:subscribe` neu autorisiert werden.
