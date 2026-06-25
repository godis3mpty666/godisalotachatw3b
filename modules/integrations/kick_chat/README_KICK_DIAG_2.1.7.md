# kick_chat 2.1.7

Diagnose-Version nur für Kick.

## Änderungen

- TikTok/Twitch/YouTube bleiben unangetastet.
- Normale Kick-Chats bleiben `chat_no_alert`.
- Unbekannte Kick/Pusher-Events werden jetzt ins Diagnose-Log geschrieben.
- Eventname, Payload-Keys und gekürzte Payload werden geloggt.
- Zusätzliche Kick-Alias-Erkennung für Follow/Sub/Gift/Raid/Join ergänzt.
- Join wird weiterhin nicht aus normalem Chat abgeleitet.

## Logdatei

Die Diagnose steht im Plugin-Settings-Feld und zusätzlich unter:

`data/kick_chat/kick_chat_last_diag.txt`

Nach einem Testlauf mit Kick bitte diese Datei oder den DEV-Log schicken, wenn Alerts noch fehlen.
