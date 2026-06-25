# godisalotachat webbased

## 0.92 Kick Webhook Patch (2026-06-25)

- Kick-OAuth-Scope im Core um `events:subscribe` erweitert.
- Neuer Core-Endpunkt `POST /api/webhooks/kick` ergänzt; Alias-Endpunkte `/api/kick/events` und `/api/kick/webhook` leiten ebenfalls an `kick_chat` weiter.
- `kick_chat` auf 2.1.8 aktualisiert und für offizielle Kick-Webhook-Events vorbereitet.
- Kick-Chat-Websocket bleibt unverändert für normale Chatnachrichten; Webhooks werden nur für echte Kick-Events wie Follow/Sub/Gift/Live-Status genutzt.
- Twitch, TikTok und YouTube wurden nicht geändert.

## 0.91

- OBS/Meld-Integration speichert neue Live-Wert-Einträge wie TikTok Top-Liker jetzt dauerhaft in `settings.json`.
- `/api/settings` übernimmt `automation_rules` nun sauber als Top-Level-Einstellung statt sie beim Speichern zu verwerfen.
- Automationsregeln werden beim Speichern bereinigt, damit nur gültige Plattformen, Ziele und Aktionen persistiert werden.
- Die App-Version wurde auf `0.01` gesetzt.


## 0.89

- Plattformen -> TikTok hat jetzt einen Testkanal-Schalter mit frei eintragbarem Kanalnamen.
- Wenn der Testkanal aktiv ist, liest `tiktok_chat` Chat und TikTok-Events vom Testkanal statt vom eigenen Main-Kanal. Dadurch koennen TikTok-Alerts getestet werden, ohne selbst live zu gehen.
- `tiktok_chat` registriert wieder Follow-, Share-, Join-, Like- und Gift-Events und startet die Alert-Queue fuer Desktop-/OBS-Ausgabe.
- TikTok-Alert-Events werden weiter direkt an `al3rtalot` gebridged, damit der Alertbereich im Desktopfenster Joins/Likes/Gifts/Follows/Shares anzeigen kann.

## 0.68

- Autoconnect-Auswahl im Core jetzt für alle Plattformen ergänzt: Twitch, TikTok, YouTube, Kick, Spotify, OpenAI, Meld und OBS.
- Plattform-Plugins starten beim App-Start nur noch automatisch, wenn die jeweilige Plattform aktiv ist und Autoconnect eingeschaltet ist.
- Spotify/Spotis3mptify respektiert den Autoconnect-Schalter aus der Plattform-Seite.


Lokales Web-Dashboard mit Plugins fuer Twitch, YouTube, TikTok, Kick, Spotify,
OBS und Meld.

## Struktur

- `build`: Build-Skript, PyInstaller-Konfiguration und Build-Abhaengigkeiten
- `core/host`: Startlogik und Web-UI-Ressourcen
- `core/runtime`: Anwendungslogik und Modulsteuerung
- `data`: Persistente Daten sowie deren Pfade
- `modules/integrations`: Plattform- und Service-Anbindungen
- `modules/plugins`: Optionale Funktionen
- `shared`: Gemeinsame Typen und Vertraege
- `data`: Portable Laufzeitdaten neben Script oder EXE

Die aktuelle Web- und Anwendungsversion wird zentral in
`shared/version.py` gepflegt.

## Sicherheit

Das Verzeichnis `data/` enthaelt lokale Einstellungen, OAuth-Tokens,
Passwoerter, Cookies und weitere persoenliche Laufzeitdaten. Es wird deshalb
von Git ignoriert. Veröffentliche niemals Dateien aus diesem Verzeichnis.

## Entwicklung unter Windows

Voraussetzung: Python 3.11 oder neuer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r build\requirements.txt
py run_webbased.py
```

Beim ersten Start wird `data/` automatisch befuellt.

## EXE bauen

```powershell
.\build\build_exe.bat
```

Das Build-Skript fragt vor dem Build nach einer Bestaetigung. Nach einem
erfolgreichen Build startet es automatisch `dist\webbased\webbased.exe`.
Vorhandene Einstellungen, Anmeldedaten, Tokens und Plugin-Daten werden vor dem
Loeschen von `dist` aus `dist\webbased\data` nach `data` gesichert und danach
wieder neben die neue EXE kopiert. Dabei werden die alte EXE und Browserfenster
mit den portablen Profilen zuerst beendet, damit OAuth-/Cookie-Dateien nicht
gesperrt sind. Build-Artefakte und lokale Laufzeitdaten werden nicht
versioniert. PyInstaller verwendet waehrend des Builds den Ordner `temp/`; nach
einem erfolgreichen Build wird er automatisch entfernt.

## Mitarbeit

1. Repository forken oder einen Branch erstellen.
2. Aenderungen klein und nachvollziehbar halten.
3. Vor einem Commit `git status` pruefen und sicherstellen, dass keine Tokens,
   Passwoerter, Logs oder persoenlichen Daten enthalten sind.
4. `py -m compileall -q core data modules shared run_webbased.py` ausfuehren.
5. Pull Request mit einer kurzen Beschreibung und Testhinweisen erstellen.

## Contributors

- [psychoedge](https://github.com/psychoedge)

Historische Versionshinweise stehen in `README.txt`.


## 0.62

- UI-Heartbeat öffnet keine neuen Tabs mehr.
- Reload erfolgt ausschließlich im vorhandenen Tab per Heartbeat-Flag.
- Backend, Plugins, Overlays und Callback-Listener bleiben weiter aktiv.

## v0.65

- Neuer Beenden-Button oben rechts in der Weboberfläche.
- Der Button stoppt Plugins, lokale Verbindungen und beendet danach die EXE/den Server sauber.
- Browser/Tab schließen beendet weiterhin nicht automatisch die EXE.


## 0.74
- modalot: Plattform-Reiter auf die anklickbaren Regeln reduziert; Status/Rechte/Textfeld-Bereich aus den Plattform-Tabs entfernt.
