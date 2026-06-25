# integrations alerts/join fix

Version: 2026-06-23

Geändert wurden nur:

- twitch_chat 1.8.1
- kick_chat 2.1.6
- youtube_chat 1.1.3

TikTok wurde nicht geändert.

## Twitch

- Normale Chatnachrichten bleiben `chat_no_alert` und werden nicht im Alertfenster angezeigt.
- Viewer-Join wird nur aus echtem Twitch-IRC `JOIN` erzeugt, nicht aus einer Chatnachricht.
- Broadcaster/Mainaccount wird nicht pauschal ausgefiltert. Nur bekannte Service-Bots werden unterdrückt.
- Join-Alerts laufen jetzt als `twitch_join` statt generischem `twitch_alert`, damit al3rtalot sie sauber als Join behandeln kann.
- Follow/Sub/Resub/Subgift/Raid/Bits bleiben erhalten.

## Kick

- Normale Chatnachrichten bleiben `chat_no_alert`.
- Kein Join wird aus einer normalen Chatnachricht abgeleitet.
- Echte Kick-Realtime-Events werden, soweit Kick sie liefert, als Alerts ausgegeben:
  - `kick_follow`
  - `kick_sub`
  - `kick_gift`
  - `kick_raid`
  - `kick_join`
- Dedupe für Kick-Alerts ergänzt, damit Pusher-Mehrfachzustellungen nicht direkt doppelt im Alert landen.

## YouTube

- Normale Chatnachrichten bleiben `chat_no_alert`.
- Keine Join-Alerts aus Chatnachrichten.
- Relevante YouTube-LiveChat-API-Events werden als Alerts markiert:
  - `youtube_superchat`
  - `youtube_supersticker`
  - `youtube_member`
  - `youtube_gift`
- Web-Chat-Fallback markiert Paid-Renderer soweit möglich ebenfalls als SuperChat/SuperSticker.

## Test

`python -m compileall` läuft für die drei geänderten Integrations sauber durch.
