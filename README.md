# godisalotachat webbased

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
Vorhandene Einstellungen, Anmeldedaten, Tokens und Plugin-Daten werden zwischen
`data` und `dist\webbased\data` uebernommen, damit sie bei einem neuen Build
erhalten bleiben. Build-Artefakte und lokale Laufzeitdaten werden nicht
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
