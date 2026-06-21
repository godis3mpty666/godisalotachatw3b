@echo off
setlocal
cd /d "%~dp0.."

set DATA_EXCLUDE_DIRS=__pycache__ Cache "Code Cache" GPUCache GrShaderCache ShaderCache BrowserMetrics optimization_guide_model_store Crashpad DawnCache blob_storage
set DATA_EXCLUDE_FILES=__init__.py paths.py .gitkeep

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
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$backup='temp\root_auth_backup'; $auth='data\auth'; $settings='data\settings.json'; $cfg=$null; if(Test-Path $settings){ try{ $cfg=Get-Content $settings -Raw | ConvertFrom-Json } catch{} }; New-Item -ItemType Directory -Force -Path $auth | Out-Null; Get-ChildItem $backup -Filter *.json -ErrorAction SilentlyContinue | ForEach-Object { $stem=$_.BaseName.ToLower(); $parts=$stem -split '_'; $skip=$false; if($parts.Count -ge 2 -and $cfg -and $cfg.platforms){ $platform=($parts[0]); $account=($parts[-1]); $pcfg=$cfg.platforms.$platform; if($pcfg){ if($account -eq 'main' -and $pcfg.main_disconnected_at){ $skip=$true }; if($account -eq 'bot' -and $pcfg.bot_disconnected_at){ $skip=$true } } }; if($skip){ return }; $dst=Join-Path $auth $_.Name; $has=$false; if(Test-Path $dst){ try{ $j=Get-Content $dst -Raw | ConvertFrom-Json; if($j.access_token -or $j.refresh_token){ $has=$true } } catch{} }; if(-not $has){ Copy-Item $_.FullName $dst -Force } }"
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

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --workpath temp --distpath dist build\webbased.spec
if errorlevel 1 goto :fail

rem Module bleiben neben der EXE erweiterbar; die Kopie in _internal ist nur der gebuendelte Fallback.
if exist "dist\webbased\modules" rmdir /s /q "dist\webbased\modules"
robocopy "modules" "dist\webbased\modules" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

rem Gemeinsame UI-Bilder neben die EXE legen, damit Desktopfenster und WebUI dieselben Symbole nutzen.
robocopy "assets" "dist\webbased\assets" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail

rem Alle portablen Einstellungen, Tokens und Plugin-Daten neben die neue EXE kopieren.
if not exist "dist\webbased\data" mkdir "dist\webbased\data"
robocopy "data" "dist\webbased\data" /E /R:5 /W:1 /XD %DATA_EXCLUDE_DIRS% /XF %DATA_EXCLUDE_FILES% /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
if not exist "dist\webbased\data\plugins" mkdir "dist\webbased\data\plugins"

if exist temp rmdir /s /q temp
set ERRORLEVEL=0
echo.
echo Fertig: dist\webbased\webbased.exe
echo Module kopiert nach: dist\webbased\modules
echo Einstellungen und Anmeldedaten kopiert nach: dist\webbased\data
echo Starte dist\webbased\webbased.exe
start "" "%CD%\dist\webbased\webbased.exe"
exit /b 0

:fail
echo.
echo Build fehlgeschlagen.
echo Temporaere Build-Daten bleiben zur Fehlersuche unter temp erhalten.
pause
exit /b 1
