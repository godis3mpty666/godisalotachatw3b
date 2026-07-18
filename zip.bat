@echo off
setlocal

set "BAT_DIR=%~dp0"
set "ROOT=%BAT_DIR%"
if not exist "%ROOT%build\zip_release.ps1" (
  set "ROOT=%BAT_DIR%..\"
)
set "SCRIPT=%ROOT%build\zip_release.ps1"

if not exist "%SCRIPT%" (
  echo Fehler: %SCRIPT% wurde nicht gefunden.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
exit /b %ERRORLEVEL%
