(function(){
  "use strict";
  const lang=(window.APP_LANGUAGE==="en"?"en":"de");
  window.APP_LANGUAGE=lang;
  document.documentElement.lang=lang;

  // German is the canonical UI language. Product, platform and plugin names are
  // deliberately absent from this table and are therefore never translated.
  const pairs=[
    ["Beenden","Exit"],["Schließt…","Closing…"],["Sprache","Language"],["Deutsch","German"],["Englisch","English"],
    ["Dashboard","Dashboard"],["Plattformen","Platforms"],["OBS/Meld Integration","OBS/Meld Integration"],["Overlay URLs","Overlay URLs"],
    ["Browserquellen","Browser sources"],["Diese URLs direkt in OBS, Meld oder Browserquelle eintragen.","Add these URLs directly to OBS, Meld, or a browser source."],["Alle URLs öffnen","Open all URLs"],
    ["OpenAI API verbunden","OpenAI API connected"],["Chat-Modelle","chat models"],["verfuegbar","available"],["Gestoppt","Stopped"],["Deaktiviert","Disabled"],["Liest","Reading"],["liest","reading"],["als","as"],
    ["Meld ist nicht gestartet oder nicht erreichbar.","Meld is not running or cannot be reached."],
    ["Übersicht & Status","Overview & status"],["Credits & Community","Credits & community"],["Feedback senden","Send feedback"],
    ["Bug oder Idee auf GitHub","Bug or idea on GitHub"],["Anmeldedaten bleiben im webbased/data Ordner.","Login data remains in the webbased/data folder."],
    ["Gemeinsamer Chat für Dashboard, Browserquelle und Desktopfenster.","Shared chat for the dashboard, browser source and desktop window."],
    ["Dauerhafte Live-Werte gezielt in eine OBS- oder Meld-Quelle schreiben.","Write persistent live values to a specific OBS or Meld source."],
    ["Modularer Pluginbereich für Spotify und das transparente Overlay.","Modular plugin area for Spotify and the transparent overlay."],
    ["Schnellleiste am Fensterrand.","Quick-access bar at the edge of the window."],
    ["Hier stellst du jedes gefundene Plugin direkt ein. Der alte nutzlose Bereit-Button ist weg.","Configure every detected plugin here. The old redundant ready button is gone."],
    ["Lokale Entwicklungsdiagnose. Geheimnisse werden in der Logansicht automatisch ausgeblendet.","Local development diagnostics. Secrets are automatically hidden in the log view."],
    ["Die Oberfläche läuft weiter; Details stehen im DEV-Log.","The interface keeps running; details are available in the DEV log."],
    ["Neu laden","Reload"],["Speichern","Save"],["Gespeichert","Saved"],["Kopieren","Copy"],["Kopiert","Copied"],["Löschen","Delete"],
    ["Abbrechen","Cancel"],["Ändern abbrechen","Cancel editing"],["Bearbeiten","Edit"],["Aktivieren","Enable"],["Deaktivieren","Disable"],
    ["Verbinden","Connect"],["Trennen","Disconnect"],["Verbunden","Connected"],["Nicht verbunden","Not connected"],
    ["nicht verbunden","not connected"],["Inaktiv","Inactive"],["inaktiv","inactive"],["Aktiv","Active"],["aktiv","active"],
    ["Bereit","Ready"],["Status prüfen","Check status"],["Verbindung testen","Test connection"],["Testen","Test"],
    ["Einstellungen","Settings"],["Plugin-Einstellungen","Plugin settings"],["Öffnen","Open"],["Schließen","Close"],
    ["Desktopfenster öffnen","Open desktop window"],["Desktopfenster editieren","Edit desktop window"],["Bearbeitung beenden","Finish editing"],
    ["Browserfenster öffnen","Open browser window"],["Desktopfenster Darstellung","Desktop window appearance"],["Hintergrund","Background"],
    ["Transparenz","Opacity"],["Radien","Corner radius"],["Schriftart","Font"],["Schriftgröße","Font size"],["Schriftfarbe","Text color"],
    ["Desktopfenster beim Toolstart öffnen","Open desktop window when the tool starts"],["Testnachricht ins Overlay schicken","Send a test message to the overlay"],
    ["Senden","Send"],["Neuen Eintrag anlegen","Create new entry"],["Plattform","Platform"],["Live-Wert","Live value"],
    ["Ausgabe","Output"],["Szene","Scene"],["Quelle","Source"],["Name dieses Eintrags","Name of this entry"],
    ["Gespeicherte Einträge","Saved entries"],["Noch keine Einträge gespeichert.","No entries saved yet."],["Aktion","Action"],
    ["Aktueller Song","Current song"],["Kein Song aktiv","No song playing"],["Eine Overlay URL für alles","One overlay URL for everything"],
    ["Overlay öffnen / editieren","Open / edit overlay"],["Alle URLs","All URLs"],["Wichtig sind Chat Browser und eine komplette Spotis3mptify-Overlay-URL. Einzelquellen bleiben nur für alte Setups erhalten.","The important URLs are Chat Browser and one complete Spotis3mptify overlay URL. Individual sources remain available only for legacy setups."],
    ["Position","Position"],["Verzögerung","Delay"],["Deckkraft","Opacity"],["Sekunden","seconds"],["Links","Left"],["Rechts","Right"],
    ["Oben","Top"],["Unten","Bottom"],["Schaltflächen","Buttons"],["Beim Start aktiviert","Enabled on startup"],
    ["Gefundene Plugins","Detected plugins"],["Keine Plugins gefunden","No plugins found"],["Plugin neu starten","Restart plugin"],
    ["Neustart","Restart"],["Laufzeit","Runtime"],["Zustand","State"],["Entwicklerlinks","Developer links"],["Live-Log","Live log"],
    ["automatisch aktualisieren","refresh automatically"],["Alle Level","All levels"],["Fehler","Error"],["Fehler-Test","Error test"],
    ["Warnungen","Warnings"],["Warnungs-Test","Warning test"],["Metriken","Metrics"],["Info-Test","Info test"],
    ["Log durchsuchen","Search log"],["Log kopieren","Copy log"],["Log löschen","Clear log"],["Alle","All"],
    ["Arbeitsordner","Working directory"],["Daten","Data"],["Nachrichten","Messages"],["Aktive Plugins","Active plugins"],
    ["Auth-Dateien","Auth files"],["Freier Speicher","Free space"],["Modus","Mode"],["gesamt","total"],["Zeilen","lines"],
    ["Suche","Search"],["bereinigte Anzeige","sanitized view"],["Logdatei wirklich leeren?","Really clear the log file?"],
    ["Log laden fehlgeschlagen","Failed to load log"],["Manueller","Manual"],["aus der DEV-Seite","from the DEV page"],
    ["Keine Accounts eingetragen","No accounts entered"],["Keine Nachrichten","No messages"],["Keine Daten","No data"],
    ["Hauptaccount","Main account"],["Bot-Account","Bot account"],["Main verbinden","Connect main account"],["Bot verbinden","Connect bot account"],
    ["Client-ID","Client ID"],["Client-Secret","Client secret"],["API-Key","API key"],["Passwort","Password"],["Benutzername","Username"],
    ["Kanal","Channel"],["Host","Host"],["Port","Port"],["Redirect URL","Redirect URL"],["Scopes","Scopes"],
    ["Wird sicher lokal gespeichert.","Stored securely on this device."],["Pflichtfeld","Required field"],["Optional","Optional"],
    ["Ja","Yes"],["Nein","No"],["An","On"],["Aus","Off"],["Unbekannt","Unknown"],["unbekannt","unknown"],
    ["Erfolgreich","Successful"],["Fehlgeschlagen","Failed"],["fehlgeschlagen","failed"],["gestartet","started"],["beendet","stopped"],
    ["gespeichert","saved"],["geladen","loaded"],["gefunden","found"],["fehlt","missing"],["ungültig","invalid"],
    ["Elemente mit der Maus verschieben. Unten rechts skalieren. Bearbeitung im Chat-Reiter beenden.","Move elements with the mouse. Resize at the bottom right. Finish editing in the Chat tab."],
    ["ALERTS","ALERTS"],["Aktueller Song","Current song"],["Neustart","Restart"],["Einstellungen-JSON (bereinigt)","Settings JSON (sanitized)"],
    ["Raw-Debug","Raw debug"],["Quellcode","Source"],["getrennt","disconnected"],["Warnung","warning"],["gesendet","sent"],
    ["Nachricht","Message"],["Nachrichten","Messages"],["Benutzer","User"],["Grund","Reason"],["Regeln","Rules"],["Chat-Browser","Chat Browser"],
    ["Wort/Phrase","Word/phrase"],["nur löschen","delete only"],["löschen + Zeitüberschreitung","delete + timeout"],
    ["Automatik einschalten","Enable automation"],["Wenn aktiv, prüft modalot neue Chatnachrichten mit den Regeln in den Plattform-Reitern.","When enabled, modalot checks new chat messages against the rules in the platform tabs."],
    ["Manuell","Manual"],["Manuelle Aktionen","Manual actions"],["Zeitüberschreitung Minuten","Timeout minutes"],
    ["Nachricht löschen","Delete message"],["Benutzer sperren","Ban user"],["Benutzer freigeben","Unban user"],
    ["Routen","Routes"],["Plattformen verbinden","Bridge platforms"],["Nur an aktive/schreibbare Zielplattformen senden","Only send to active/writable target platforms"],
    ["Platzhalter","Placeholders"],["Leer lassen","Leave empty"],["verfügbar","available"],["nicht verfügbar","unavailable"],
    ["blockiert","blocked"],["ignoriert","ignored"],["empfangen","received"],["aktualisiert","updated"],["erfolgreich","successful"]
    ,["Zeitüberschreitung","Timeout"],["Sperren","Ban"],["Entsperren","Unban"],["Übersicht","Overview"],
    ["Element auswählen","Select element"],["Elemente","Elements"],["Rechteck","Rectangle"],["Kreis","Circle"],["Text","Text"],
    ["Breite","Width"],["Höhe","Height"],["Farbe","Color"],["Effekt","Effect"],["Ausrichtung","Alignment"],
    ["Geschwindigkeit","Speed"],["Drehung","Rotation"],["Form","Shape"],["Ebene","Layer"],["Vorschau","Preview"],
    ["Zurücksetzen","Reset"],["Hinzufügen","Add"],["Auswählen","Select"],["Übernehmen","Apply"],
    ["Elemente mit der Maus verschieben, an der Ecke vergrößern. Ecke rechts unten zum Resizen.","Move elements with the mouse and resize them using the corner. Use the bottom-right corner to resize."],
    ["JavaScript ist aus","JavaScript is disabled"],["Webbased braucht JavaScript.","Webbased requires JavaScript."],
    ["WebUI konnte nicht laden","Could not load WebUI"],["Meist fehlt","Usually missing"],["oder es gab einen JavaScript-Fehler.","or a JavaScript error occurred."],
    ["Debug öffnen","Open debug"],["testen","test"],["Eine komplette URL für Chat und Moderation.","One complete URL for chat and moderation."],
    ["Live","Live"],["Offline","Offline"],["Zuschauer","Viewers"],["Follower","Followers"],["Abonnenten","Subscribers"],
    ["Likes","Likes"],["Geschenke","Gifts"],["Kommentare","Comments"],["Aufrufe","Views"],["Warteschlange","Queue"],
    ["Warte auf","Waiting for"],["leer","empty"],["Nächster","Next"],["Überspringen","Skip"],["Leeren","Clear"]
    ,["Allgemein","General"],["Anfragen","Requests"],["Wiedergabe","Playback"],["Verbindung","Connection"],
    ["Protokollierung","Logging"],["Moderation","Moderation"],["Erweitert","Advanced"],["Darstellung","Appearance"],
    ["Warnungen","Warnings"],["Befehle","Commands"],["Vorlagen","Templates"],["Beschreibung","Description"],
    ["Titel","Title"],["Kategorie","Category"],["Schlagwörter","Tags"],["Zielplattformen","Target platforms"],
    ["Automatisch verbinden","Connect automatically"],["Automatische Verbindung","Automatic connection"],
    ["Beim Start","On startup"],["Nur wenn live","Only while live"],["Alle Plattformen","All platforms"],
    ["Standard","Default"],["Minuten","minutes"],["Stunden","hours"],["Anzahl","Count"],["Grenzwert","Threshold"]
    ,["für","for"],["und","and"],["oder","or"],["mit","with"],["ohne","without"],["von","by"],["über","via"],
    ["nach","after"],["vor","before"],["nicht","not"],["keine","no"],["kein","no"],["beim","when"],
    ["wird","will be"],["werden","will be"],["kann","can"],["konnte","could"],["neue","new"],["vorhandene","existing"]
    ,["Das Token wurde im kompatiblen Format gespeichert.","The token was saved in the compatible format."],
    ["Token wurde original-kompatibel gespeichert.","The token was saved in the compatible format."],
    ["Dieses Fenster schließt sich gleich automatisch.","This window will close automatically."],
    ["Zurück zu Plattformen","Back to Platforms"],["Kann automatisch nicht geschlossen werden","Could not close automatically"],
    ["Die Anmeldung ist gespeichert. Du kannst dieses Fenster schließen.","The login is saved. You can close this window."],
    ["Der Login ist gespeichert. Du kannst dieses Fenster schließen.","The login is saved. You can close this window."]
    ,["Künstler","Artist"],["Lied","Song"],["Linie oben","Line Up"],["Linie unten","Line Down"],
    ["Leinwand","Canvas"],["Anbieterfarben","Provider colors"],["Auswahl","Selection"],["Schrift","Font"],
    ["Größe","Size"],["Fett","Bold"],["Laufband","Marquee"],["Tempo","Speed"],["Anbieterfarbe","Provider color"],
    ["Quadrat","Square"],["Drehen","Rotate"],["Drehdauer","Rotation duration"],["Effekt bei Wechsel","Effect on change"],
    ["Element anklicken, dann Optionen ändern.","Click an element, then change its options."],
    ["Kein vollständiges Neuladen: Künstler/Lied/Cover werden live aktualisiert.","No full reload: artist, song and cover update live."]
    ,["Ungefilterte Diagnose","Raw Debug"],["Programmdatei","Executable"],["Protokolle","Logs"],
    ["Laden","Loading"],["beim Laden","while loading"],["beim Speichern","while saving"],
    ["erreichbar","reachable"],["nicht erreichbar","unreachable"],["wird neu gestartet","is restarting"],
    ["Einstellungsschema","settings schema"],["Dieses Plugin hat kein Einstellungsschema.","This plugin has no settings schema."],
    ["wird in","is stored in"],["gespeichert und danach neu gestartet.","and is then restarted."],
    ["Protokolle im DEV-Bereich prüfen","Check logs in the DEV area"]
    ,["Einstellungen werden geladen...","Loading settings..."],["Einstellungen konnten nicht geladen werden","Could not load settings"],
    ["Plugin-Einstellungen konnten nicht geladen werden","Could not load plugin settings"],
    ["Laufzeit-JSON","Runtime JSON"],["Speichern & neu starten","Save & restart"]
    ,["Desktopfenster zurücksetzen","Reset desktop window"],["Desktopfenster zuruecksetzen","Reset desktop window"],
    ["Desktopfenster schließen","Close desktop window"],["Desktopfenster schliessen","Close desktop window"],
    ["Desktopfenster auf Standardposition und -größe zurücksetzen?","Reset the desktop window to its default position and size?"],
    ["Desktopfenster auf Standardposition und -groesse zuruecksetzen?","Reset the desktop window to its default position and size?"],
    ["Desktopfenster konnte nicht zurückgesetzt werden","Could not reset desktop window"],
    ["Desktopfenster konnte nicht zurueckgesetzt werden","Could not reset desktop window"],
    ["Desktopfenster konnte nicht geschlossen werden","Could not close desktop window"],
    ["Warnungsbereich im Desktopfenster","Alert area in desktop window"],["Alertbereich im Desktopfenster","Alert area in desktop window"],
    ["Warnungsbereich anzeigen","Show alert area"],["Alertbereich anzeigen","Show alert area"],
    ["Warnungen gleichzeitig","Simultaneous alerts"],["Alerts gleichzeitig","Simultaneous alerts"],
    ["Uhrzeit anzeigen","Show timestamp"],
    ["Im Bearbeitungsmodus ist „Warnungen“ ein eigenes, frei verschiebbares Element. Welche Ereignistypen entstehen, wird weiterhin im Warnungs-Plugin je Plattform gesteuert.","In edit mode, Alerts is a separate freely movable element. Event types are still controlled per platform in the alert plugin."],
    ["Im Bearbeitungsmodus ist „Alerts“ ein eigenes, frei verschiebbares Element. Welche Eventtypen entstehen, wird weiterhin im Alert-Plugin je Plattform gesteuert.","In edit mode, Alerts is a separate freely movable element. Event types are still controlled per platform in the alert plugin."],
    ["Desktopfenster Darstellung","Desktop window appearance"],["Gemeinsamer Chat für Dashboard, Browserquelle und Desktopfenster.","Shared chat for the dashboard, browser source and desktop window."]
    ,["Szenen & Quellen neu laden","Reload scenes & sources"],["Chatter","Chatter"],
    ["Auslösen alle X Likes","Trigger every X likes"],["TikTok-Name exakt eingeben","Enter exact TikTok name"],
    ["Gilt nur für TikTok Like-Zähler: Die Aktion läuft wiederkehrend bei jedem Intervall dieses Users, z. B. 50, 100, 150 Likes.","Only applies to the TikTok like counter: the action repeats at every interval for this user, e.g. 50, 100, 150 likes."],
    ["Noch keine Daten","No data yet"],["Testtext","Test text"],["Änderung speichern","Save changes"],
    ["Bitte einen Chatter für den Like-Zähler eintragen.","Please enter a chatter for the like counter."],
    ["Regel speichern fehlgeschlagen","Failed to save rule"],["Info3ditor Vorlagen","Info3ditor presets"],
    ["Spiel anlegen","Create game"],["Neues Spiel anlegen","Create new game"],["Spiel speichern","Save game"],
    ["Spiel / Vorlagenname","Game / preset name"],["Presetname","Preset name"],["Vorlage anlegen","Create preset"],
    ["Vorlage bearbeiten","Edit preset"],["Vorlage speichern","Save preset"],["Noch keine Vorlagen angelegt.","No presets created yet."],
    ["Noch keine Spiele angelegt.","No games created yet."],["Unbenannt","Untitled"],
    ["Beim Senden aktiv","Enabled when sending"],["Noch nicht sendbar","Not available for sending yet"],
    ["TikTok wird aktuell nicht unterstützt.","TikTok is not currently supported."],
    ["An aktivierte Plattformen senden","Send to enabled platforms"],["Sendevorgang gestartet.","Sending started."],
    ["Titel, Kategorie und Aktivierung je Plattform festlegen.","Set title, category and activation for each platform."],
    ["Verwalte deine Spiel- und Plattforminfos.","Manage your game and platform information."],
    ["Ein Spiel anklicken, um dessen Streaminfos an die aktivierten Plattformen zu senden.","Click a game to send its stream information to the enabled platforms."],
    ["Plattformdaten eintragen und anschließend speichern.","Enter platform data and then save."],
    ["Führe Aktion aus...","Running action..."],["Aktion ausgeführt.","Action completed."],["Aktion fehlgeschlagen","Action failed"],
    ["Speichere...","Saving..."],["Gespeichert und neu gestartet.","Saved and restarted."],
    ["Plugin konnte nicht umgeschaltet werden","Could not toggle plugin"],["Plugin konnte nicht neu gestartet werden","Could not restart plugin"],
    ["Dashboard testen","Test dashboard"],["Hier stellst du jedes gefundene Plugin direkt ein. Der alte nutzlose Bereit-Button ist weg.","Configure every detected plugin here. The old redundant Ready button is gone."],
    ["automatisch aktualisieren","refresh automatically"],["Alle Level","All levels"],["Log durchsuchen","Search log"],
    ["Log kopieren","Copy log"],["Log löschen","Clear log"],["Logdatei wirklich leeren?","Really clear the log file?"],
    ["bereinigte Anzeige","sanitized view"],["Freier Speicher","Free space"],["Aktive Plugins","Active plugins"],
    ["Auth-Dateien","Auth files"],["Arbeitsordner","Working directory"]
  ];
  const deToEn=new Map(), enToDe=new Map();
  for(const [de,en] of pairs){ if(de!==en){deToEn.set(de,en); if(!enToDe.has(en))enToDe.set(en,de);} }
  const map=lang==="en"?deToEn:enToDe;
  const ordered=[...map.entries()].sort((a,b)=>b[0].length-a[0].length);
  function translate(value){
    let text=String(value??"");
    if(map.has(text)) return map.get(text);
    for(const [from,to] of ordered){
      if(from.length<2) continue;
      if(/^[\p{L}\p{N}_-]+$/u.test(from)){
        const escaped=from.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
        text=text.replace(new RegExp(`(^|[^\\p{L}\\p{N}_-])${escaped}(?=$|[^\\p{L}\\p{N}_-])`,"gu"),(_,prefix)=>prefix+to);
      }else text=text.split(from).join(to);
    }
    return text;
  }
  window.t=translate;
  window.translateUi=function(root=document){
    const blocked="script,style,code,pre,.startupSplash,.messages,#messages,#desktopMessages,#chatOverlay,#spTitle,#spArtist,#titleEl,#artistEl,#extrasLayer,#stage,.spotifyText,[data-i18n-skip]";
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const nodes=[]; while(walker.nextNode()) nodes.push(walker.currentNode);
    for(const node of nodes){ const p=node.parentElement; if(!p||p.closest(blocked))continue; const next=translate(node.nodeValue); if(next!==node.nodeValue)node.nodeValue=next; }
    const elements=root.querySelectorAll?root.querySelectorAll("[title],[placeholder],[aria-label]"):[];
    for(const el of elements){ if(el.closest(blocked))continue; for(const attr of ["title","placeholder","aria-label"]){if(el.hasAttribute(attr))el.setAttribute(attr,translate(el.getAttribute(attr)));} }
  };
  const originalAlert=window.alert.bind(window), originalConfirm=window.confirm.bind(window);
  window.alert=value=>originalAlert(translate(value));
  window.confirm=value=>originalConfirm(translate(value));
  const start=()=>{
    window.translateUi(document);
    let queued=false;
    new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;window.translateUi(document);});}).observe(document.body,{childList:true,characterData:true,subtree:true});
  };
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start();
})();
