@echo off
setlocal
cd /d "%~dp0desktop"
set "PATH=C:\Program Files\nodejs;%PATH%"
powershell -NoProfile -Command "Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq 'JARVIS Desktop Shell' } | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1
call npm run build
if errorlevel 1 exit /b %errorlevel%
call npm run start
endlocal
