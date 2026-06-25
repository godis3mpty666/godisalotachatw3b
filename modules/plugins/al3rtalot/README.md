# al3rtalot ver.0.03

`al3rtalot` ist ein plattformübergreifendes Alert-Plugin für das neue webbasierte `godischatalotw3b`/`godisalotachat`-System.

Das Plugin ist bewusst als reines Alert-Auswertungs- und Anzeigeplugin gebaut. Es besitzt keine eigene Login-, OAuth- oder Chat-Verbindungslogik. Plattform-Logins bleiben im Haupttool beziehungsweise in den jeweiligen Plattform-Plugins.

## Ziel

`al3rtalot` soll Alerts für mehrere Streamingplattformen zentral anzeigen und verwalten, ohne dass jede Plattform eine eigene komplett getrennte Alert-Logik braucht.

Unterstützte Plattform-Dateien in dieser Version:

- Twitch
- TikTok
- YouTube
- Kick

## Ordnerstruktur

```text
al3rtalot/
├─ manifest.json
├─ plugin.py
├─ al3rtalot_common.py
├─ al3rtalot_overlay_server.py
└─ al3rtalot_platforms/
   ├─ base.py
   ├─ twitch.py
   ├─ tiktok.py
   ├─ youtube.py
   └─ kick.py
```

## Einbau

Den Ordner `al3rtalot` in den Plugin-Ordner des webbasierten Tools legen:

```text
modules/plugins/al3rtalot
```

Danach das Tool neu starten oder die Plugins neu laden.

## Version

Aktuelle Version:

```text
0.03
```

Diese Version ergänzt ausschließlich Kick-spezifische Event-Mappings. Twitch, TikTok und YouTube bleiben funktional unverändert.

## Einstellungsbereiche

Das Plugin stellt eigene Settings-Bereiche bereit:

- Übersicht
- Browser-Overlay
- Twitch
- TikTok
- YouTube
- Kick

Jede Plattform bekommt eigene Einstellungen, damit später pro Plattform getrennt gesteuert werden kann, welche Alerts aktiv sind und wie sie aussehen.

Typische Einstellungen pro Plattform:

- Plattform aktiv/deaktiviert
- Akzentfarbe
- ignorierte User nur für diese Plattform
- aktivierbare Eventtypen
- eigener Titel pro Alerttyp
- eigener Text pro Alerttyp

Globale Einstellungen:

- Plugin aktiv/deaktiviert
- globale ignorierte User
- doppelte Alerts blocken
- Alerts zusätzlich in den gemeinsamen Chat-/Overlaybereich ausgeben

## Browser-Overlay

`al3rtalot` bringt ein eigenes kleines Browser-Overlay mit.

Standard-URL:

```text
http://127.0.0.1:17642/
```

Der Port kann in den Plugin-Einstellungen geändert werden.

Dieses Overlay kann in OBS, Meld oder einem Browser als Browserquelle verwendet werden.

## Wichtiger Systemgedanke

Chat-Alerts funktionieren direkt über das vorhandene Nachrichtensystem.

Follow/Gift/Like/Join und ähnliche Events sind im Plugin bereits vorbereitet. Damit diese Events wirklich angezeigt werden können, müssen die jeweiligen Plattform-Plugins diese Eventtypen später sauber ins gemeinsame Event-System werfen.

Genau so ist das Plugin gedacht:

`al3rtalot` wertet Events nur aus und zeigt sie an. Es baut keine eigenen Login-, OAuth-, Browser- oder Plattformverbindungen auf.

## Aktueller Funktionsstand

Direkt nutzbar:

- Plugin lädt im neuen Plugin-System
- eigene Settings-Tabs werden bereitgestellt
- Testalert ist vorhanden
- eigenes Browser-Overlay ist vorhanden
- Chat-/Message-Events können über das gemeinsame Nachrichtensystem ausgewertet werden
- Plattformstruktur ist vorbereitet

Vorbereitet für spätere Plattform-Events:

- Twitch: Chat, Follow, Subscribe, Raid
- TikTok: Chat, Join, Like, Gift, Follow, Share
- YouTube: Chat, Subscribe, Superchat, Member
- Kick: Chat, Follow, Subscribe, Gift

## Was die Plattform-Plugins später liefern müssen

Damit Nicht-Chat-Alerts sauber funktionieren, sollten die Plattform-Plugins Events mit klaren Feldern an das gemeinsame Event-System übergeben.

Empfohlene Felder:

```json
{
  "platform": "tiktok",
  "event_type": "gift",
  "username": "UserName",
  "text": "Giftname oder Nachricht",
  "amount": 1,
  "channel": "Kanalname",
  "message_id": "eindeutige-id"
}
```

Wichtige Werte:

- `platform`: `twitch`, `tiktok`, `youtube` oder `kick`
- `event_type`: zum Beispiel `chat`, `follow`, `join`, `like`, `gift`, `share`, `subscribe`, `raid`, `superchat`, `member`
- `username`: Name des Users
- `text`: Nachricht oder Eventtext
- `amount`: Anzahl, Betrag oder Menge, falls vorhanden
- `channel`: optionaler Kanalname
- `message_id`: möglichst eindeutig, damit Dedupe sauber funktioniert

## Warum getrennte Plattform-Dateien?

Jede Plattform hat andere Eventnamen, andere mögliche Datenfelder und andere Einschränkungen.

Darum liegt die Auswertung getrennt in:

```text
al3rtalot_platforms/twitch.py
al3rtalot_platforms/tiktok.py
al3rtalot_platforms/youtube.py
al3rtalot_platforms/kick.py
```

Gemeinsame Logik liegt in:

```text
al3rtalot_platforms/base.py
al3rtalot_common.py
plugin.py
```

So kann später eine Plattform erweitert werden, ohne direkt alles andere anzufassen.

## Keine eigenen Logins

`al3rtalot` darf keine eigenen Tokens, OAuth-Daten oder Zugangsdaten speichern.

Das Plugin soll nur die Events verarbeiten, die das Haupttool beziehungsweise die Plattform-Plugins bereits liefern.

Das verhindert doppelte Logins, kaputte Tokenpfade und unnötige Verbindungslogik.

## Datenablage

Runtime-Daten und gespeicherte Pluginwerte gehören zum Hauptsystem-Datenordner unter:

```text
data/al3rtalot
```

Sicherheitsrelevante Daten gehören nicht in den Pluginordner.

## Nächste sinnvolle Schritte

1. `al3rtalot` je Plattform feinjustieren.
2. Später optional Sounds, Bilder, Animationen und eigene Alert-Layouts ergänzen.


---

## Änderung 0.03

Diese Version prüft und korrigiert die Alert-Zuordnung für Twitch, TikTok, YouTube und Kick.

### Wichtigste Änderungen

- Normale Chatnachrichten bleiben standardmäßig **kein Alert** mehr.
- `chat_no_alert` wird ausdrücklich ignoriert, damit die Chat-/Alert-Trennung sauber bleibt.
- Twitch unterstützt jetzt zusätzlich `join`, damit User, die dem Stream/Chat joinen, als Alert angezeigt werden können.
- Kick unterstützt jetzt zusätzlich `join`, `gift` und `raid`.
- YouTube unterstützt jetzt zusätzlich `supersticker` und `donation`.
- Event-Aliase wurden erweitert:
  - Twitch/Kick: `viewer_join`, `user_joined`, `gift_sub`, `gifted_subs`, `cheer`
  - YouTube: `new_member`, `membership`, `super_chat`, `super_sticker`
  - TikTok: `joined`, `likes`, `gifts`, `shares`
- Dedupe wurde verbessert, damit doppelte TikTok-/Realtime-Alerts mit anderer ID innerhalb kurzer Zeit geblockt werden.

### Erwartete Eventtypen

Twitch:
`join`, `follow`, `subscribe`, `gift`, `raid`, `donation`, `bits`

TikTok:
`follow`, `join`, `like`, `gift`, `share`

YouTube:
`subscribe`, `member`, `superchat`, `supersticker`, `donation`

Kick:
`join`, `follow`, `subscribe`, `gift`, `raid`

`chat` ist weiterhin technisch vorhanden, aber standardmäßig deaktiviert, weil Chat ins Chatfenster gehört und nicht doppelt als Alert auftauchen soll.


## Änderung 0.03 - Kick Webhook-Eventnamen

Diese Version bereitet `al3rtalot` auf offizielle Kick-Events/Webhooks vor, ohne das Verhalten von Twitch, TikTok oder YouTube zu ändern.

Neu für Kick normalisiert:

```text
channel.followed              -> kick follow alert
channel.subscription.new      -> kick subscribe alert
channel.subscription.renewal  -> kick subscribe alert
channel.subscription.gifts    -> kick gift alert
kicks.gifted                  -> kick gift alert
livestream.status.updated     -> kick live_status alert
```

Die eigentliche Kick-Webhooks/Event-Subscription-Logik gehört weiterhin in die Kick-Integration. `al3rtalot` zeigt nur die intern ankommenden Alerts an.
