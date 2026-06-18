modalot ver. 0.06

Standalone Moderation Plugin fuer godischatalotw3b.

Neu in dieser Version:
- Pro Plattform eigener anklickbarer Reiter in den Plugin-Settings.
- Twitch, Kick und YouTube haben jeweils eigene Blacklist-Regeln.
- Jede Plattform hat ein Blacklist-Textfeld plus 8 kompaktere anklickbare Regelzeilen.
- Pro Regel kann die Aktion gewaehlt werden: nur loeschen, loeschen + Timeout, loeschen + Ban. Bei Ban wird das Timeout-Feld im UI ausgeblendet.
- Nachrichten werden bei jedem Treffer immer geloescht, sofern die Chat-Payload eine Message-ID liefert.
- Alte globale blocked_words/default_action bleiben als Fallback erhalten.
- TikTok zeigt dasselbe Menue, bleibt aber bewusst deaktiviert.
- Plugin-Settings im Core haben jetzt echte anklickbare Tabs und schliessen sich nach Speichern automatisch.

Syntax im Blacklist-Textfeld:
wort
phrase mit leerzeichen
spamwort | timeout | 600
extremwort | ban

Aktionen:
- delete: Nachricht loeschen
- timeout: Nachricht loeschen + User timeouten
- ban: Nachricht loeschen + User bannen

Wichtig:
- Twitch/Kick/YouTube brauchen weiterhin passende OAuth-/Modrechte im Core.
- Delete braucht eine Message-ID aus dem jeweiligen Chatplugin.
- YouTube braucht fuer Mod-Aktionen live_chat_id und author_channel_id aus dem Chat-Payload.


Update 0.06:
- Session-Reiter und Session-Button aus den Settings entfernt.
- Regel-Liste kompakter gemacht und von 12 auf 8 sichtbare Zeilen reduziert.
- Timeout-Felder werden ausgeblendet, wenn Ban gewaehlt ist.
