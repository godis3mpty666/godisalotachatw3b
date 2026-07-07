@echo off
setlocal
cd /d "%~dp0.."

set "SIGNING_THUMBPRINT_FILE=build\.signing-thumbprint"
if not exist "%SIGNING_THUMBPRINT_FILE%" goto :unauthorized
set /p SIGNING_THUMBPRINT=<"%SIGNING_THUMBPRINT_FILE%"
if not defined SIGNING_THUMBPRINT goto :unauthorized
powershell -NoProfile -ExecutionPolicy Bypass -Command "$thumb=$env:SIGNING_THUMBPRINT.Trim(); $cert=Get-Item ('Cert:\CurrentUser\My\'+$thumb) -ErrorAction SilentlyContinue; if(-not $cert -or -not $cert.HasPrivateKey -or $cert.Subject -notmatch 'OU=(Main|Contributor)'){ exit 1 }"
if errorlevel 1 goto :unauthorized
powershell -NoProfile -ExecutionPolicy Bypass -Command "$thumb=$env:SIGNING_THUMBPRINT.Trim(); try{$trusted=Get-Content 'build\trusted_builders.json' -Raw | ConvertFrom-Json}catch{exit 1}; $entry=@($trusted.builders | Where-Object { [string]$_.thumbprint -eq $thumb })[0]; if(-not $entry -or @('Main','Contributor') -notcontains [string]$entry.role){exit 1}; Write-Host ('Autorisierter Build: '+$entry.name+' ('+$entry.role+')')"
if errorlevel 1 goto :unauthorized

rem Dieser nur waehrend des autorisierten Builds vorhandene Marker wird von
rem PyInstaller eingebettet. Quellstarts und andere Buildwege zeigen keinen Build-Suffix.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$hash='nogit'; try{$hash=(git rev-parse --short HEAD).Trim()}catch{}; $stamp=Get-Date -Format 'yyyyMMdd-HHmm'; Set-Content -Path 'shared\build_provenance.py' -Encoding utf8 -NoNewline -Value ('BUILD_SUFFIX = ''-original+'+$stamp+'.'+$hash+'''')"

set DATA_EXCLUDE_DIRS=__pycache__ ui_browser_profile Cache "Code Cache" GPUCache GrShaderCache ShaderCache BrowserMetrics optimization_guide_model_store Crashpad DawnCache blob_storage
set DATA_EXCLUDE_FILES=__init__.py paths.py .gitkeep ui_browser_profile.zip

if /I not "%~1"=="/Y" (
    choice /C JN /N /M "Aenderungen als EXE bauen und danach starten? [J/N] "
    if errorlevel 2 (
        echo Build abgebrochen.
        exit /b 0
    )
)

rem Laufende alte EXE beenden, sonst sperrt Windows Dateien in dist beim Neubau.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $exe=(Join-Path $root 'dist\webbased\webbased.exe'); Get-Process webbased -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force" >nul 2>nul

rem Browserfenster mit alten TikTok-Profilen beenden, sonst bleiben Cookie-Daten gelockt.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $distData=(Join-Path $root 'dist\webbased\data'); if(Test-Path $distData){ Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($distData) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }" >nul 2>nul

rem Browser-/Rendererprozesse beenden, die DLLs aus dist\webbased geladen haben.
rem Das passiert z.B. bei Meld/OBS/Chrome-Browserquellen auf lokale Overlay-URLs.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $dist=(Join-Path $root 'dist\webbased'); if(Test-Path $dist){ $locked=@(); Get-Process | ForEach-Object { $p=$_; try { foreach($m in $p.Modules){ if($m.FileName -like ($dist + '*')){ $locked += $p; break } } } catch{} }; $locked | Sort-Object Id -Unique | ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} } }" >nul 2>nul

rem Einen Moment warten, damit Browser/SQLite-Cookie-Daten sauber freigegeben werden.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Milliseconds 2500" >nul 2>nul

rem Zuletzt in der EXE verwendete Einstellungen, Tokens und Plugin-Daten sichern.
rem Wichtig: vorhandene Root-Auth vorher sichern. Ein leerer/frischer dist\webbased\data
rem darf beim Rebuild keine funktionierenden OAuth-Dateien im Projektroot plattmachen.
if exist temp rmdir /s /q temp
if exist "data\auth" (
    mkdir "temp\root_auth_backup" >nul 2>nul
    robocopy "data\auth" "temp\root_auth_backup" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
)
if exist "dist\webbased\data" (
    echo Uebernehme vorhandene Laufzeit- und Anmeldedaten aus dist...
    robocopy "dist\webbased\data" "data" /E /R:5 /W:1 /XD %DATA_EXCLUDE_DIRS% /XF %DATA_EXCLUDE_FILES% /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 goto :fail
)
if exist "temp\root_auth_backup" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$backup='temp\root_auth_backup'; $auth='data\auth'; $settings='data\settings.json'; $cfg=$null; if(Test-Path $settings){ try{ $cfg=Get-Content $settings -Raw | ConvertFrom-Json } catch{} }; New-Item -ItemType Directory -Force -Path $auth | Out-Null; Get-ChildItem $backup -Filter *.json -ErrorAction SilentlyContinue | ForEach-Object { $stem=$_.BaseName.ToLower(); $parts=$stem -split '_'; $skip=$false; if($parts.Count -ge 2 -and $cfg -and $cfg.platforms){ $platform=($parts[0]); $account=($parts[-1]); $pcfg=$cfg.platforms.$platform; if($pcfg){ if($account -eq 'main' -and $pcfg.main_disconnected_at){ $skip=$true }; if($account -eq 'bot' -and $pcfg.bot_disconnected_at){ $skip=$true } } }; if($skip){ return }; $dst=Join-Path $auth $_.Name; $copy=$false; $src=$null; $cur=$null; try{ $src=Get-Content $_.FullName -Raw | ConvertFrom-Json } catch{}; if($src -and ($src.access_token -or $src.refresh_token)){ if(Test-Path $dst){ try{ $cur=Get-Content $dst -Raw | ConvertFrom-Json } catch{} }; if(-not ($cur -and ($cur.access_token -or $cur.refresh_token))){ $copy=$true } else { $srcSaved=0.0; $curSaved=0.0; try{ if($src.saved_at){ $srcSaved=[double]$src.saved_at } } catch{}; try{ if($cur.saved_at){ $curSaved=[double]$cur.saved_at } } catch{}; if($srcSaved -gt ($curSaved + 1.0)){ $copy=$true } } }; if($copy){ Copy-Item $_.FullName $dst -Force } }"
)

if exist dist rmdir /s /q dist
if exist dist (
    echo.
    echo Dist konnte nicht geloescht werden. Vermutlich haelt noch eine Browserquelle Dateien offen.
    echo Bitte Meld/OBS-Browserquellen auf 127.0.0.1:17890 deaktivieren oder Chrome/Meld schliessen.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path; $dist=(Join-Path $root 'dist\webbased'); if(Test-Path $dist){ Get-Process | ForEach-Object { $p=$_; try { foreach($m in $p.Modules){ if($m.FileName -like ($dist + '*')){ Write-Host ('PID ' + $p.Id + ' ' + $p.ProcessName + ' -> ' + $m.FileName); break } } } catch{} } }"
    goto :fail
)

rem Virtuelle Umgebung neben dist dauerhaft verwenden.
rem .venv wird nur angelegt, wenn sie fehlt, und bleibt bei neuen Builds erhalten.
if not exist ".venv\Scripts\python.exe" (
    echo Erstelle virtuelle Umgebung: .venv
    py -m venv .venv
    if errorlevel 1 goto :fail
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" -m pip install -r build\requirements.txt
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File "build\bump_build_version.ps1" -Bump
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --workpath temp --distpath dist build\webbased.spec
if errorlevel 1 (
    if exist "shared\build_provenance.py" del /q "shared\build_provenance.py"
    goto :fail
)
if exist "shared\build_provenance.py" del /q "shared\build_provenance.py"

rem Nur mit dem privaten lokalen Build-Zertifikat erzeugte EXEs gelten als unsere Builds.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$thumb=$env:SIGNING_THUMBPRINT.Trim(); $cert=Get-Item ('Cert:\CurrentUser\My\'+$thumb) -ErrorAction Stop; $exe=(Resolve-Path 'dist\webbased\webbased.exe').Path; $null=Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256; $sig=Get-AuthenticodeSignature -FilePath $exe; if(-not $sig.SignerCertificate -or $sig.SignerCertificate.Thumbprint -ne $thumb){ Write-Error 'EXE-Signatur konnte nicht verifiziert werden.'; exit 1 }"
if errorlevel 1 goto :fail

rem Module bleiben neben der EXE erweiterbar; die Kopie in _internal ist nur der gebuendelte Fallback.
if exist "dist\webbased\modules" rmdir /s /q "dist\webbased\modules"
robocopy "modules" "dist\webbased\modules" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

rem Diagnosehilfe fuer Rechner, auf denen der PyInstaller-Bootloader Python nicht laden kann.
copy /Y "build\diagnose_embedded_python.ps1" "dist\webbased\diagnose_embedded_python.ps1" >nul
if errorlevel 1 goto :fail
copy /Y "build\diagnose_embedded_python.bat" "dist\webbased\diagnose_embedded_python.bat" >nul
if errorlevel 1 goto :fail

rem Gemeinsame UI-Bilder neben die EXE legen, damit Desktopfenster und WebUI dieselben Symbole nutzen.
robocopy "assets" "dist\webbased\assets" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

rem Alle portablen Einstellungen, Tokens und Plugin-Daten neben die neue EXE kopieren.
if not exist "dist\webbased\data" mkdir "dist\webbased\data"
robocopy "data" "dist\webbased\data" /E /R:5 /W:1 /XD %DATA_EXCLUDE_DIRS% /XF %DATA_EXCLUDE_FILES% /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
if not exist "dist\webbased\data\plugins" mkdir "dist\webbased\data\plugins"

rem Nur auf dem Main-Rechner vorhanden: privaten Drive-Uploader nach dist legen.
if exist "build\private\upload_to_google_drive.bat" copy /Y "build\private\upload_to_google_drive.bat" "dist\upload_to_google_drive.bat" >nul

rem Das isolierte Chrome/Edge-Profil fuer die Haupt-UI wird sehr schnell gross.
rem Fuer die WebUI reichen Local State und die Default-Preferences; alles andere
rem wird von Chromium beim naechsten Start neu erzeugt.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src=Join-Path (Resolve-Path 'data').Path 'ui_browser_profile'; $dst=Join-Path (Resolve-Path 'dist\webbased\data').Path 'ui_browser_profile'; if(Test-Path $dst){ Remove-Item -LiteralPath $dst -Recurse -Force -ErrorAction SilentlyContinue }; New-Item -ItemType Directory -Force -Path (Join-Path $dst 'Default') | Out-Null; $keep=@('Local State','Last Browser','Last Version','Variations','Default\Preferences','Default\Secure Preferences'); foreach($rel in $keep){ $from=Join-Path $src $rel; if(Test-Path -LiteralPath $from){ $to=Join-Path $dst $rel; New-Item -ItemType Directory -Force -Path (Split-Path $to -Parent) | Out-Null; Copy-Item -LiteralPath $from -Destination $to -Force -ErrorAction SilentlyContinue } }; $zip=Join-Path (Resolve-Path 'dist\webbased\data').Path 'ui_browser_profile.zip'; if(Test-Path $zip){ Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue }"

rem Safety net fuer andere Chromium-Laufzeitdaten ausserhalb des UI-Profils.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$data=(Resolve-Path 'dist\webbased\data').Path; $names=@('Cache','Code Cache','GPUCache','GrShaderCache','ShaderCache','BrowserMetrics','optimization_guide_model_store','Crashpad','blob_storage','Safe Browsing','extensions_crx_cache','component_crx_cache','GPUPersistentCache','DawnCache','DawnGraphiteCache','DawnWebGPUCache'); Get-ChildItem -LiteralPath $data -Directory -Recurse -Force | Where-Object { $names -contains $_.Name } | Sort-Object FullName -Descending | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Get-ChildItem -LiteralPath $data -File -Recurse -Force -Filter '*.pma' | Remove-Item -Force -ErrorAction SilentlyContinue"

powershell -NoProfile -ExecutionPolicy Bypass -File "build\bump_build_version.ps1" -Finalize
if errorlevel 1 goto :fail

if exist temp rmdir /s /q temp
set ERRORLEVEL=0
echo.
echo Fertig: dist\webbased\webbased.exe
echo Module kopiert nach: dist\webbased\modules
echo Einstellungen und Anmeldedaten kopiert nach: dist\webbased\data
echo Starte dist\webbased\webbased.exe
start "" "%CD%\dist\webbased\webbased.exe"
exit /b 0

:unauthorized
if exist "shared\build_provenance.py" del /q "shared\build_provenance.py"
echo.
echo Build nicht autorisiert: Das private Build-Zertifikat fehlt.
echo Einmalig ausfuehren: powershell -ExecutionPolicy Bypass -File build\setup_build_signing.ps1
echo Der private Schluessel bleibt im Windows-Zertifikatsspeicher dieses Benutzerkontos.
pause
exit /b 1

:fail
if exist "shared\build_provenance.py" del /q "shared\build_provenance.py"
powershell -NoProfile -ExecutionPolicy Bypass -File "build\bump_build_version.ps1" -Restore >nul 2>nul
echo.
echo Build fehlgeschlagen.
echo Temporaere Build-Daten bleiben zur Fehlersuche unter temp erhalten.
pause
exit /b 1
