# al3rtalot r3adm3

## Version 0.03 - 2026-06-25

### Geänderte Dateien

- `plugin.py`
- `manifest.json`
- `al3rtalot_common.py`
- `al3rtalot_platforms/kick.py`
- `README.md`
- `r3adm3.md`

### Betroffene Bereiche

- Kick-spezifische Event-Normalisierung
- Kick-Webhooks/Event-Subscriptions-Vorbereitung
- Kick-Alerttypen für Follow/Sub/Gift/Live-Status

### Grund der Änderung

Kick liefert echte Alerts laut offizieller Events/Webhook-API mit Eventnamen wie `channel.followed`, `channel.subscription.new`, `channel.subscription.gifts` oder `kicks.gifted`. `al3rtalot` muss diese Namen anzeigen können, sobald die Kick-Integration sie als interne Events weitergibt.

### Technische Umsetzung

- Nur `KickAlerts` erweitert.
- Twitch, TikTok und YouTube wurden nicht funktional verändert.
- Offizielle Kick-Eventnamen werden Kick-spezifisch auf interne Alerttypen normalisiert:
  - `channel.followed` -> `follow`
  - `channel.subscription.new` -> `subscribe`
  - `channel.subscription.renewal` -> `subscribe`
  - `channel.subscription.gifts` -> `gift`
  - `kicks.gifted` -> `gift`
  - `livestream.status.updated` -> `live_status`
- Zusätzliche Payload-Fallbacks für Username, Text und Amount ergänzt.
- `live_status` als Label und Template ergänzt.

### Test

- `python -m compileall al3rtalot`: OK

### Offene Punkte

- Die Kick-Integration muss echte Webhooks/Event-Subscriptions empfangen und an `al3rtalot` weiterreichen.
- Ein Kick-User-Join mit Username ist weiterhin nur möglich, falls Kick dafür tatsächlich einen Event liefert.

---


## Version 0.02 - 2026-06-25

### Geänderte Dateien

- `plugin.py`
- `manifest.json`
- `al3rtalot_common.py`
- `al3rtalot_platforms/base.py`
- `al3rtalot_platforms/twitch.py`
- `al3rtalot_platforms/kick.py`
- `al3rtalot_platforms/youtube.py`
- `README.md`
- `r3adm3.md`

### Betroffene Bereiche

- Alert-Normalisierung
- Event-Aliase
- Twitch Join-Alerts
- Kick-/YouTube-Eventabdeckung
- Chat-/Alert-Trennung
- Duplicate-Blocking für Realtime-Alerts

### Grund der Änderung

Normale Chats sollen nicht doppelt im Chatfenster und im Alertbereich landen. Gleichzeitig sollen relevante Plattformevents wie Twitch-Join, Subs, Gifts, Raids, Bits, YouTube-Member/Superchat/Supersticker und Kick-Events korrekt als Alerts verarbeitet werden.

### Technische Umsetzung

- `chat_no_alert` als ausdrücklicher Nicht-Alert-Alias ergänzt.
- Plattformevents erweitert:
  - Twitch: `join`, `gift`
  - Kick: `join`, `gift`, `raid`
  - YouTube: `supersticker`, `donation`
- Default-Settings setzen `*_enable_chat` auf `False`, alle Nicht-Chat-Events bleiben standardmäßig aktiv.
- Dedupe nutzt jetzt ID-basierte und weiche Fingerprints. Dadurch werden doppelte TikTok-/Realtime-Events mit anderer ID kurzzeitig geblockt, ohne echte spätere Events komplett zu verschlucken.

### Test

- `python -m compileall al3rtalot`: OK
- Plattform-Normalisierung manuell gegen Twitch, TikTok, YouTube und Kick geprüft.
- `chat_no_alert` wird nicht als Alert behandelt.
- `viewer_join`/`user_joined` werden für Twitch/Kick als `join` normalisiert.
- `super_sticker` wird für YouTube als `supersticker` normalisiert.

### Offene Punkte

- Ob Twitch/Kick/YouTube die neuen Eventtypen tatsächlich liefern, hängt von den jeweiligen Integrations-Plugins ab.
- Falls ein Plattformplugin andere Feldnamen nutzt, müssen dort oder in `base.py` weitere Aliase ergänzt werden.
