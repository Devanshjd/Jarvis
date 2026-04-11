@echo off
setlocal
cd /d "%~dp0desktop"
set "PATH=C:\Program Files\nodejs;%PATH%"
call npm run dev
endlocal
