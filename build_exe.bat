@echo off
setlocal
cd /d "%~dp0"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

py -m pip show pyinstaller >nul 2>nul
if errorlevel 1 py -m pip install pyinstaller

py -m PyInstaller --noconfirm --clean --windowed --name webbased --icon static\img\app.ico --add-data "templates;templates" --add-data "static;static" --add-data "server;server" --add-data "godisalotachat;godisalotachat" --add-data "data;data" run_webbased.py
if errorlevel 1 goto :fail

rem Plugins muessen neben der EXE liegen, weil webbased sie dynamisch aus dist\webbased\plugins laedt.
rem PyInstaller --add-data wuerde sie nur nach _internal kopieren, dort findet der Plugin-Loader sie nicht.
if exist "dist\webbased\plugins" rmdir /s /q "dist\webbased\plugins"
robocopy "plugins" "dist\webbased\plugins" /E /NFL /NDL /NJH /NJS /NP >nul
if %ERRORLEVEL% GEQ 8 goto :fail

rem Der Runtime-Data-Ordner liegt ebenfalls neben der EXE. Keine echten Tokens ueberschreiben.
if not exist "dist\webbased\data" mkdir "dist\webbased\data"
if not exist "dist\webbased\data\plugins" mkdir "dist\webbased\data\plugins"

set ERRORLEVEL=0
echo.
echo Fertig: dist\webbased\webbased.exe
echo Plugins kopiert nach: dist\webbased\plugins
pause
exit /b 0

:fail
echo.
echo Build fehlgeschlagen.
pause
exit /b 1
