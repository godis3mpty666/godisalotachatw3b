botalot ver. 0.86

- Übersicht trennt jetzt Twitch OAuth/Senden und echten Twitch Chat-Empfang.
- Neuer Button "Echten Botstatus prüfen". Grün gibt es für Twitch nur noch, wenn Senden UND twitch_chat-Empfang plausibel aktiv sind.
- Letzte bei botalot angekommene Twitch-Nachricht, letzte Botantwort und letzter Twitch-Fehler werden in der Übersicht angezeigt.

botalot ver. 0.81

UI: Settings-Bereiche sind jetzt per Tab-Metadaten in eigene Reiter gruppiert. Allgemein enthält Status/Auth für alle Plattformen.

botalot ver. 0.32

Nur Plugin-Ordner. In godisalotachat/plugins/ kopieren.

Wichtig fuer TikTok schreiben:
1. In den botalot Settings TikTok Live URL setzen.
2. TikTok Zweitaccount Name eintragen.
3. Button "Zweitaccount-Browser öffnen" drücken.
4. Im geöffneten Browser einmal mit dem Zweitaccount einloggen.
5. TikTok Live Chatfeld anklicken/fokussieren.
6. "TikTok per Zweitaccount-Browser senden" aktivieren.
7. Sendetest drücken.

Warum so?
TikTok hat hier keine stabile öffentliche Chat-Send-API. Deshalb schreibt botalot in diesem Spezialfall über einen separaten Browser mit eigenem Profil/Zweitaccount.

Module:
- plugin.py: Plugin-Hooks/UI
- ai_client.py: OpenAI Anfrage
- trigger_matcher.py: botis3mpty/Ursula Erkennung
- context_memory.py: 10-Nachrichten-Kontext
- platform_outputs.py: Routing zu Ausgaben
- writers/twitch_writer.py: Twitch Sendebrücke
- writers/tiktok_browser_writer.py: TikTok Zweitaccount-Browser/Clipboard/Enter Brücke


Version 0.05:
- Statusbereich hinzugefügt
- Test OpenAI Connection
- Test Twitch Send
- TikTok Login/Tab prüfen und Testsendung über Zweitaccount-Browser


Version 0.08:
- OpenAI Connect-Fix: nutzt max_completion_tokens statt max_tokens für neue Modelle.
- AI-Antworten begrenzen jetzt ebenfalls über max_completion_tokens.


0.08: Twitch OAuth Flow eingebaut wie beim twitch_chat Plugin, aber mit eigenem Standard-Port 17564 und editierbarem Redirect Port. Scopes: chat:read chat:edit.


0.14: TikTok UI vereinfacht: nur Botaccount-Name und Mainaccount/Live-Kanal eintragen; Live-URL wird automatisch gebaut.


TikTok v0.14: Connect TikTok startet den separaten Botaccount-Browser automatisch, wenn der Debug-Port noch nicht erreichbar ist. Beim ersten Mal dort mit dem Botaccount einloggen, danach Main-Live im Botbrowser öffnen.

0.14: TikTok Browserstart erzwingt jetzt eine eigene Chrome/Edge-Instanz mit separatem Profilordner, --new-window, Remote-Debugging-Adresse und öffnet weitere TikTok-Seiten per Debug-Port im Botbrowser statt im normalen Browser.


Neu in 0.14:
- Zusätzlicher Trigger @bot, z.B. "@bot wie ist das Wetter bei dir?".


Neu in 0.15:
- Beim Stoppen/Beenden von godisalotachat schließt botalot die von ihm gestartete TikTok-Zusatzbrowser-Instanz.
- Zusätzlicher Button zum manuellen Schließen des TikTok-Zusatzbrowsers.
- Es werden nur von botalot gestartete Prozesse/Tabs geschlossen, nicht dein normaler Chrome/Edge.

v0.16:
- TikTok Botaccount-Browser nutzt jetzt einen persistenten Profilordner außerhalb des Pluginordners.
- Standard: %APPDATA%/godisalotachat/botalot/tiktok_bot_profile
- Dadurch bleibt der TikTok-Login nach einem einmaligen Login erhalten, auch nach Plugin-Updates.
- Optional kann ein eigener Profilordner im UI gesetzt werden.


0.20: Added @botis3mpty mention trigger alongside @bot.


v0.24:
- Antworten werden hart nur noch auf die Eingangsplattform gesendet.
- TikTok-Trigger gehen nicht mehr nach Twitch.
- Neuer Standard-Prompt für natürlichere Antworten und schärfere Ursula-Reaktionen.
- Button: Neuen Standard-Prompt einsetzen.


0.29:
- Kontext/Memory läuft jetzt pro Chatter und Plattform, nicht mehr global.
- Ursula wird nur noch bei aktuellem Ursula-Trigger in die Antwort gezogen.
- Bot-Antworten werden zusätzlich ins godisalotachat Desktopwindow/Overlay gespiegelt.


0.29:
- AI-Antworten können jetzt optional zusätzlich auf die andere Plattform gespiegelt werden.
- Neue Optionen: AI Twitch→TikTok, AI TikTok→Twitch, Spiegel-Format, Desktop-Anzeige.
- Sprachregel verschärft: immer Sprache der aktuellen User-Nachricht verwenden.


0.29: Bridge output format changed to "TT-Message from Name: Text" / "Twitch-Message from Name: Text". Twitch ↔ TikTok works directly; labels prepared for YouTube/Kick.


v0.32:
- Autoconnect startet TikTok nur noch einmal und erzeugt keine doppelten Login/Live-Tabs mehr.
- Wenn TikTok-Profil angemeldet wirkt: Main-Live wird minimiert im Botbrowser geöffnet.
- Wenn nicht angemeldet: Login-Fenster bleibt sichtbar.
- Standardprompt verschärft: Sprache pro User, Kontext pro User, Ursula nur bei aktuellem Ursula-Trigger, keine Smileys/Sternchenaktionen.
- Chat-Bridge Twitch ↔ TikTok bleibt erhalten.
0.71: Twitch Moderation Ban/Unban nutzt jetzt die offizielle Helix Moderation API mit moderator:manage:banned_users statt IRC /ban-/unban-Chatcommands.

0.72: Twitch OAuth Scopes erweitert um moderator:manage:chat_messages; Moderation löscht die auslösende Twitch-Nachricht per Helix Delete Chat Message, bevor Ban/Meldung verarbeitet werden.

0.77: Moderation Session-Liste aktualisiert jetzt die Host-Settings per Referenz/Best-Effort-Update, damit neu gebannte Nutzer in der Übersicht auftauchen. Zusätzlich Refresh-Button für die Session-Liste.

0.85: Übersicht bereinigt: Last Twitch Bot Reply entfernt; separate Lesen/Schreiben-Tabs entfernt und Trigger/Antwort-Ausgabe in AI zusammengeführt. Moderationsrechte/Ban-Funktion bleiben unverändert vorhanden.

0.86: Startup-Status korrigiert: Twitch-Empfang wird beim Toolstart nicht mehr fälschlich als FEHLER markiert, solange twitch_chat noch startet. Harte Fehleranzeige bleibt für manuelle Live-Checks/Connect erhalten.

0.90: Twitch-Ausgaben werden wieder automatisch nach 149 Zeichen in mehrere Chatnachrichten aufgeteilt.
0.91: Twitch-Ausgaben splitten jetzt konsequent ab 100 Zeichen.
0.92: Split nur noch bei Twitch → TikTok ab 100 Zeichen; TikTok → Twitch und normale Twitch-Ausgaben splitten nicht mehr bei 100.
