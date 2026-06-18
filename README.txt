godisalotachat webbased v0.59

## 0.68

- Autoconnect-Auswahl im Core jetzt für alle Plattformen ergänzt: Twitch, TikTok, YouTube, Kick, Spotify, OpenAI, Meld und OBS.
- Plattform-Plugins starten beim App-Start nur noch automatisch, wenn die jeweilige Plattform aktiv ist und Autoconnect eingeschaltet ist.
- Spotify/Spotis3mptify respektiert den Autoconnect-Schalter aus der Plattform-Seite.


Start: run_webbased.py

TikTok Loginfenster wird jetzt robuster in den Vordergrund geholt.


0.37: TikTok-Status zählt nur noch echte Session-Cookies; abgebrochener Login wird nicht mehr als verbunden angezeigt. TikTok-Browserstart ohne CMD-Fenster und mit stärkerem Vordergrund-Fokus.

0.59: DEV-Logfilter aktualisieren sich automatisch für neue Plugins/Module. Plugin-Tab hat echte Settings-Buttons. bridg3alot bekommt jetzt alle Plattformdaten vom Host und erkennt schreibbare Ziele korrekt.

0.61
- UI-Heartbeat beendet den lokalen Server nicht mehr.
- Bei verlorenem Heartbeat wird die Haupt-UI automatisch erneut geöffnet/neu geladen.
- Client-Heartbeat lädt die Seite bei wiederholtem Verbindungsfehler selbst neu.
- TikTok-Cookie-Lock wird mit Backoff behandelt, statt die Logs im Sekundentakt zu fluten.

## v0.65

- Neuer Beenden-Button oben rechts in der Weboberfläche.
- Der Button stoppt Plugins, lokale Verbindungen und beendet danach die EXE/den Server sauber.
- Browser/Tab schließen beendet weiterhin nicht automatisch die EXE.



## 0.67
- Entfernt: Desktop-Crashlog-TXT wird beim Start nicht mehr erzeugt oder automatisch geöffnet.

0.69
- Core-Autoconnect ist jetzt wirklich die Quelle für Twitch/TikTok/YouTube/Kick/Spotify.
- Alte plugin-lokale enabled=false Werte blockieren den Plattform-Autostart nicht mehr.
- Fehlende data/auth Token-Dateien werden aus data/settings.json wiederhergestellt, damit nach einem neuen Build keine neue OAuth-Anmeldung nötig ist.


## 0.74
- modalot: Plattform-Reiter auf die anklickbaren Regeln reduziert; Status/Rechte/Textfeld-Bereich aus den Plattform-Tabs entfernt.
