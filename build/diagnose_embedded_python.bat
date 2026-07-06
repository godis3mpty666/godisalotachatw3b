@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  godisalotachat - Startdiagnose
echo ============================================================
echo.

if not exist "diagnose_embedded_python.ps1" (
    echo FEHLER: diagnose_embedded_python.ps1 fehlt neben dieser BAT-Datei.
    echo.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_embedded_python.ps1" -AppDirectory "%CD%"
set "DIAG_EXIT=%ERRORLEVEL%"

echo.
if exist "startup_diagnose.txt" (
    echo Diagnose abgeschlossen.
    echo Bitte diese Datei an den Entwickler schicken:
    echo %~dp0startup_diagnose.txt
) else (
    echo FEHLER: Die Diagnosedatei konnte nicht erstellt werden.
)
echo.
pause
exit /b %DIAG_EXIT%
