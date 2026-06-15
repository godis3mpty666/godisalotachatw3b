# godisalotachat webbased

Lokales Web-Dashboard mit Plugins fuer Twitch, YouTube, TikTok, Kick, Spotify,
OBS und Meld.

## Sicherheit

Das Verzeichnis `data/` enthaelt lokale Einstellungen, OAuth-Tokens,
Passwoerter, Cookies und weitere persoenliche Laufzeitdaten. Es wird deshalb
von Git ignoriert. Veröffentliche niemals Dateien aus diesem Verzeichnis.

## Entwicklung unter Windows

Voraussetzung: Python 3.11 oder neuer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py run_webbased.py
```

Beim ersten Start wird `data/` automatisch befuellt.

## EXE bauen

```powershell
.\build_exe.bat
```

Das Ergebnis liegt anschließend unter `dist\webbased`. Build-Artefakte und
lokale Laufzeitdaten werden nicht versioniert.

## Mitarbeit

1. Repository forken oder einen Branch erstellen.
2. Aenderungen klein und nachvollziehbar halten.
3. Vor einem Commit `git status` pruefen und sicherstellen, dass keine Tokens,
   Passwoerter, Logs oder persoenlichen Daten enthalten sind.
4. `py -m compileall -q godisalotachat plugins server run_webbased.py` ausfuehren.
5. Pull Request mit einer kurzen Beschreibung und Testhinweisen erstellen.

## Contributors

- [psychoedge](https://github.com/psychoedge)

Historische Versionshinweise stehen in `README.txt`.
