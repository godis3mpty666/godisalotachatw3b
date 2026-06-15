# Security

## Geheimnisse und persoenliche Daten

Keine OAuth-Tokens, API-Keys, Passwoerter, Cookies, Browserprofile, Logs oder
Dateien aus `data/` committen.

Falls ein Geheimnis versehentlich committed wurde:

1. Geheimnis sofort beim jeweiligen Anbieter widerrufen oder rotieren.
2. Betroffenen Commit nicht nur loeschen, sondern die Git-Historie bereinigen.
3. Repository-Mitwirkende ueber die Rotation informieren.

Sicherheitsprobleme bitte nicht als oeffentliches Issue mit echten
Zugangsdaten melden.
