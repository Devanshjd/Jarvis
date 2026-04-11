@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\Devansh\AppData\Local\Microsoft\WindowsApps\python3.13.exe"
set "NODE_HOME=C:\Program Files\nodejs"
set "PATH=%NODE_HOME%;%PATH%"

echo Launching JARVIS backend...
start "JARVIS Backend" cmd /k ""%PYTHON_EXE%" "%~dp0web_main.py""

timeout /t 2 >nul

echo Launching TypeScript frontend dev server...
start "JARVIS Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --host 127.0.0.1"

endlocal
