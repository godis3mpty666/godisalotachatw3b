"""Runtime localization helpers for application-owned backend messages."""
from __future__ import annotations

import re


LANGUAGES = {"de", "en"}

# Logs stay canonical on disk and are localized when displayed. Technical IDs,
# plugin names, exception details, URLs and user content are left untouched.
_PAIRS = (
    ("Meld is not running or cannot be reached.", "Meld ist nicht gestartet oder nicht erreichbar."),
    ("Chat command detected", "Chatbefehl erkannt"),
    ("Queue reply", "Queue-Antwort"),
    ("mirrored to", "gespiegelt an"),
    ("mirrored", "gespiegelt"),
    ("Like counter triggered", "Like-Zähler ausgelöst"),
    ("YouTube request will wait for Spotify track id", "YouTube-Anfrage wartet auf Spotify-Track-ID"),
    ("Could not attach Spotify wait marker", "Spotify-Wartemarkierung konnte nicht gesetzt werden"),
    ("Spotify snapshot unavailable; keeping YouTube handoff waiting", "Spotify-Status nicht verfügbar; YouTube-Übergabe wartet weiter"),
    ("Spotify moved from queued track", "Spotify wechselte vom eingeplanten Titel"),
    ("starting YouTube handoff now", "YouTube-Übergabe wird jetzt gestartet"),
    ("Spotify nowplaying refresh after YouTube failed", "Aktualisierung der Spotify-Wiedergabe nach YouTube fehlgeschlagen"),
    ("Spotify paused for YouTube request handoff", "Spotify für die YouTube-Anfrage pausiert"),
    ("Spotify pause handoff failed", "Pausieren von Spotify für die YouTube-Übergabe fehlgeschlagen"),
    ("Spotify resumed after YouTube queue finished", "Spotify nach Abschluss der YouTube-Warteschlange fortgesetzt"),
    ("Spotify resume after YouTube failed", "Fortsetzen von Spotify nach YouTube fehlgeschlagen"),
    ("YouTube nowplaying sync failed", "Abgleich der YouTube-Wiedergabe fehlgeschlagen"),
    ("Spotify is playing again; cleared stale YouTube current and switched overlay back to Spotify", "Spotify spielt wieder; veraltete YouTube-Wiedergabe entfernt und Overlay auf Spotify zurückgeschaltet"),
    ("Log cleared from UI", "Protokoll über die Oberfläche geleert"),
    ("Cleared stale YouTube current on startup; Spotify remains the main source", "Veraltete YouTube-Wiedergabe beim Start entfernt; Spotify bleibt die Hauptquelle"),
    ("Queue load failed", "Laden der Warteschlange fehlgeschlagen"),
    ("Checking embed permission for", "Einbettungsberechtigung wird geprüft für"),
    ("Embed check", "Einbettungsprüfung"), ("Fetching metadata for", "Metadaten werden abgerufen für"),
    ("Metadata resolved", "Metadaten aufgelöst"), ("Metadata fetch failed for", "Abruf der Metadaten fehlgeschlagen für"),
    ("Searching YouTube for", "YouTube-Suche nach"),
    ("Search picked embeddable result", "Suche wählte ein einbettbares Ergebnis"),
    ("Search skipped blocked result", "Suche übersprang ein blockiertes Ergebnis"),
    ("Search fallback picked unchecked result", "Ersatzsuche wählte ein ungeprüftes Ergebnis"),
    ("Search found no usable YouTube result", "Suche fand kein verwendbares YouTube-Ergebnis"),
    ("Resolve failed: missing query", "Auflösung fehlgeschlagen: Suchanfrage fehlt"),
    ("Resolve request", "Anfrage auflösen"), ("Detected direct YouTube video id", "Direkte YouTube-Video-ID erkannt"),
    ("No direct video id detected, using search", "Keine direkte Video-ID erkannt; Suche wird verwendet"),
    ("Resolve failed: no YouTube result found", "Auflösung fehlgeschlagen: kein YouTube-Ergebnis gefunden"),
    ("Resolve blocked", "Auflösung blockiert"), ("Resolve OK", "Auflösung erfolgreich"),
    ("Incoming request from", "Eingehende Anfrage von"),
    ("Request rejected: YouTube requests disabled", "Anfrage abgelehnt: YouTube-Anfragen deaktiviert"),
    ("Request rejected: missing YouTube query", "Anfrage abgelehnt: YouTube-Suchanfrage fehlt"),
    ("Queued for YouTube Music WebView", "Für YouTube Music WebView eingeplant"),
    ("Marked played", "Als abgespielt markiert"), ("Now playing", "Aktuelle Wiedergabe"),
    ("Skip requested, but no current video", "Überspringen angefordert, aber kein aktuelles Video vorhanden"),
    ("Queue cleared", "Warteschlange geleert"), ("Player page opened", "Player-Seite geöffnet"),
    ("Audio output selected", "Audioausgabe ausgewählt"),
    ("YouTube web fallback switch failed", "Umschalten auf den YouTube-Web-Ersatzweg fehlgeschlagen"),
    ("YouTube web fallback unavailable after API read failure", "YouTube-Web-Ersatzweg nach API-Lesefehler nicht verfügbar"),
    ("YouTube Data API chat read blocked", "Lesen des Chats über die YouTube Data API blockiert"),
    ("YouTube bot token is missing; main token will be used for writing", "YouTube-Bot-Token fehlt; zum Schreiben wird das Haupt-Token verwendet"),
    ("Found YouTube web live-chat fallback", "YouTube-Web-Ersatzweg für den Livechat gefunden"),
    ("Found YouTube liveChatId", "YouTube-liveChatId gefunden"),
    ("Alert emitted", "Warnung ausgegeben"), ("Join fallback poll warning", "Warnung bei der Ersatzabfrage für Beitritte"),
    ("Metrics poll warning", "Warnung bei der Messwertabfrage"),
    ("Follower alert poll warning", "Warnung bei der Follower-Abfrage"),
    ("Official Twitch emote fetch failed", "Abruf offizieller Twitch-Emotes fehlgeschlagen"),
    ("Emote cache warning", "Warnung im Emote-Zwischenspeicher"),
    ("previous run was not clean", "vorheriger Lauf wurde nicht sauber beendet"),
    ("reason=unknown", "Grund=unbekannt"),
    ("browser profile cleanup removed", "Browserprofil-Bereinigung entfernte"),
    ("imported runtime auth fallback", "Laufzeit-Anmeldedaten importiert"),
    ("runtime auth fallback failed", "Import der Laufzeit-Anmeldedaten fehlgeschlagen"),
    ("duplicate chat row suppressed", "doppelte Chatzeile unterdrückt"),
    ("emit_message failed", "Nachrichtenausgabe fehlgeschlagen"),
    ("dispatch failed", "Verteilung fehlgeschlagen"),
    ("chat ingress blocked", "eingehende Chatnachricht blockiert"),
    ("ingress moderation failed", "Moderation eingehender Nachrichten fehlgeschlagen"),
    ("no send_message handler", "keine Funktion zum Senden von Nachrichten"),
    ("discover failed", "Erkennung fehlgeschlagen"),
    ("start failed", "Start fehlgeschlagen"), ("stop failed", "Beenden fehlgeschlagen"),
    ("restart failed", "Neustart fehlgeschlagen"),
    ("async restart failed", "asynchroner Neustart fehlgeschlagen"),
    ("status failed", "Statusabfrage fehlgeschlagen"),
    ("settings save failed", "Speichern der Einstellungen fehlgeschlagen"),
    ("save settings failed", "Speichern der Einstellungen fehlgeschlagen"),
    ("settings plugin load failed", "Laden der Plugin-Einstellungen fehlgeschlagen"),
    ("settings action failed", "Einstellungsaktion fehlgeschlagen"),
    ("auth settings sync failed", "Abgleich der Anmeldedaten fehlgeschlagen"),
    ("OAuth refreshed for autoconnect", "OAuth für automatische Verbindung erneuert"),
    ("OAuth refresh failed", "OAuth-Erneuerung fehlgeschlagen"),
    ("OAuth invalid before autoconnect", "OAuth vor automatischer Verbindung ungültig"),
    ("login accepted", "Anmeldung akzeptiert"), ("monitor failed", "Überwachung fehlgeschlagen"),
    ("cookie read failed", "Lesen der Cookies fehlgeschlagen"),
    ("cookie DB locked; delaying next read", "Cookie-Datenbank gesperrt; nächster Leseversuch wird verzögert"),
    ("open failed", "Öffnen fehlgeschlagen"),
    ("browser process closed; backend kept running", "Browserprozess geschlossen; Backend läuft weiter"),
    ("browser monitor failed", "Browserüberwachung fehlgeschlagen"),
    ("external browser open failed", "Öffnen im externen Browser fehlgeschlagen"),
    ("main ui heartbeat recovered", "Verbindung zur Hauptoberfläche wiederhergestellt"),
    ("main ui heartbeat lost - reload requested for existing tab", "Verbindung zur Hauptoberfläche verloren – Neuladen des vorhandenen Tabs angefordert"),
    ("main window closed signal ignored; backend kept running", "Schließsignal des Hauptfensters ignoriert; Backend läuft weiter"),
    ("manual restart failed", "manueller Neustart fehlgeschlagen"),
    ("restart after settings failed", "Neustart nach Einstellungsänderung fehlgeschlagen"),
    ("restart after disconnect failed", "Neustart nach Trennung fehlgeschlagen"),
    ("disconnect cleanup failed", "Bereinigung nach Trennung fehlgeschlagen"),
    ("template missing", "Template fehlt"), ("static missing", "statische Datei fehlt"),
    ("static error", "Fehler bei statischer Datei"), ("token failed", "Token-Abfrage fehlgeschlagen"),
    ("current playback OK", "aktuelle Wiedergabe in Ordnung"),
    ("current failed", "Abfrage der aktuellen Wiedergabe fehlgeschlagen"),
    ("channel lookup failed", "Kanalsuche fehlgeschlagen"),
    ("pending save failed", "Speichern der ausstehenden Anmeldung fehlgeschlagen"),
    ("connected", "verbunden"), ("disconnected", "getrennt"), ("connection", "Verbindung"),
    ("failed", "fehlgeschlagen"), ("error", "Fehler"), ("warning", "Warnung"),
    ("missing", "fehlt"), ("invalid", "ungültig"), ("saved", "gespeichert"),
    ("loaded", "geladen"), ("started", "gestartet"), ("stopped", "beendet"),
    ("sent", "gesendet"), ("unknown", "unbekannt"), ("ready", "bereit"),
    ("enabled", "aktiviert"), ("disabled", "deaktiviert"), ("settings", "Einstellungen"),
    ("message", "Nachricht"), ("messages", "Nachrichten"), ("user", "Benutzer"),
    ("channel", "Kanal"), ("source", "Quelle"), ("action", "Aktion"),
    ("request", "Anfrage"), ("response", "Antwort"), ("timeout", "Zeitüberschreitung"),
    ("skipped", "übersprungen"), ("ignored", "ignoriert"), ("blocked", "blockiert"),
    ("received", "empfangen"), ("sending", "wird gesendet"), ("active", "aktiv"),
    ("inactive", "inaktiv"), ("available", "verfügbar"), ("unavailable", "nicht verfügbar"),
    ("reconnect", "erneut verbinden"), ("retry", "erneuter Versuch"),
    ("closed", "geschlossen"), ("opened", "geöffnet"), ("successful", "erfolgreich"),
    ("queued", "eingeplant"), ("cleared", "geleert"), ("updated", "aktualisiert"),
    ("could not", "konnte nicht"), ("will wait", "wartet"), ("waiting", "wartet"),
    ("finished", "abgeschlossen"), ("starting", "wird gestartet"), ("paused", "pausiert"),
    ("resumed", "fortgesetzt"), ("queue", "Warteschlange"), ("checking", "wird geprüft"),
    ("fetching", "wird abgerufen"), ("metadata", "Metadaten"), ("resolved", "aufgelöst"),
    ("searching", "wird gesucht"), ("search", "Suche"), ("picked", "gewählt"),
    ("result", "Ergebnis"), ("found", "gefunden"), ("detected", "erkannt"),
    ("direct", "direkt"), ("using", "verwendet"), ("rejected", "abgelehnt"),
    ("requests", "Anfragen"), ("incoming", "eingehend"), ("marked played", "als abgespielt markiert"),
    ("now playing", "aktuelle Wiedergabe"), ("skip requested", "Überspringen angefordert"),
    ("no current video", "kein aktuelles Video"), ("removed", "entfernt"),
    ("selected", "ausgewählt"), ("page opened", "Seite geöffnet"), ("fallback", "Ersatzweg"),
    ("switched", "umgeschaltet"), ("stale", "veraltet"), ("current", "aktuell"),
    ("startup", "Start"), ("reader", "Leser"), ("writer", "Schreiber"),
    ("poll warning", "Warnung bei Abfrage"), ("parse warning", "Warnung beim Verarbeiten"),
    ("token refreshed", "Token erneuert"), ("not reachable", "nicht erreichbar"),
    ("suppressed", "unterdrückt"), ("already in progress", "bereits in Bearbeitung"),
    ("joined the stream", "ist dem Stream beigetreten"), ("is running", "läuft"),
    ("listener", "Empfänger"), ("write failed", "Schreiben fehlgeschlagen"),
    ("read failed", "Lesen fehlgeschlagen"), ("load failed", "Laden fehlgeschlagen"),
    ("refresh failed", "Aktualisierung fehlgeschlagen"), ("sync failed", "Abgleich fehlgeschlagen"),
    ("metric", "Metrik"), ("language changed", "Sprache geändert"),
    ("answer", "Antwort"), ("send", "senden"), ("file", "Datei"), ("window", "Fenster"),
    ("game", "Spiel"), ("vote", "Abstimmung"), ("winner", "Gewinner"),
    ("command", "Befehl"), ("trigger", "Auslöser"), ("cooldown", "Abklingzeit"),
    ("running", "läuft"), ("route", "Route"), ("entry", "Eintrag"),
    ("methods", "Methoden"), ("properties", "Eigenschaften"), ("session", "Sitzung"),
    ("cache", "Zwischenspeicher"), ("event", "Ereignis"), ("alert", "Warnung"),
    ("count", "Anzahl"), ("read", "lesen"), ("write", "schreiben"),
)


def normalize_language(value: object) -> str:
    return "en" if str(value or "").strip().lower().startswith("en") else "de"


def translate_text(value: object, language: str) -> str:
    text = str(value if value is not None else "")
    pairs = _PAIRS if normalize_language(language) == "de" else tuple((de, en) for en, de in _PAIRS)
    for source, replacement in sorted(pairs, key=lambda item: len(item[0]), reverse=True):
        pattern = re.escape(source)
        if re.fullmatch(r"[\wÄÖÜäöüß]+", source):
            pattern = rf"(?<![\w-]){pattern}(?![\w-])"
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def translate_log(value: object, language: str) -> str:
    localized = []
    for line in str(value or "").splitlines():
        parts = line.split(" | ", 3)
        if len(parts) == 4:
            # Timestamp and source/plugin ID are technical identity, not UI copy.
            message = parts[3]
            if normalize_language(language) == "en":
                source = parts[1].strip().lower()
                if source == "spotis3mptify":
                    message = re.sub(r"(?i)Queue-Antwort an\s+(\S+)\s+gespiegelt:", r"Queue reply mirrored to \1:", message)
                    message = re.sub(r"(?i)Queue-Antwort an\s+(\S+)\s+fehlgeschlagen:", r"Queue reply to \1 failed:", message)
                    message = re.sub(r"(?i)(Chat command detected:\s*\S+)\s+von\s+", r"\1 by ", message)
                elif source == "al3rtalot":
                    message = re.sub(r"(?i)(.*?)\s+hat\s+(\d+)\s+Likes erreicht,\s*Intervall\s+(\d+),\s*Stufe\s+(\d+)", r"\1 reached \2 likes, interval \3, level \4", message)
                    message = re.sub(r"(?i)(->\s*.*?)\s+ist im Live", r"\1 joined the live stream", message)
                    message = re.sub(r"(?i)(->\s*.*?)\s+hat\s+(\d+)\s+Likes geschickt", r"\1 sent \2 likes", message)
            # Chat payloads are user-owned content. Translate only the application
            # prefix and keep username/message text byte-for-byte intact.
            chat_match = re.match(r"(?i)(.*?chat\s*\|\s*)([^:|]*:[^:|]*:\s*)(.*)$", message)
            if not chat_match:
                chat_match = re.match(r"(?i)(.*?chat message:\s*)([^:]*:\s*)(.*)$", message)
            if not chat_match:
                # Bridged chat lines contain application metadata followed by
                # user-owned text. Only localize the metadata prefix.
                chat_match = re.match(
                    r"(?i)(.*?bridge\s+\S+\s+(?:\u2192|->)\s+\S+(?:\s+failed)?\s*:\s*)"
                    r"([^:]+\s+from\s+(?:Twitch|TT|TikTok|YouTube|Kick)\s*:\s*)(.*)$",
                    message,
                )
            if chat_match:
                message = translate_text(chat_match.group(1), language) + chat_match.group(2) + chat_match.group(3)
            else:
                message = translate_text(message, language)
            localized.append(" | ".join((parts[0], parts[1], translate_text(parts[2], language), message)))
        else:
            localized.append(translate_text(line, language))
    return "\n".join(localized)
