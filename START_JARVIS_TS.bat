@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\Devansh\AppData\Local\Microsoft\WindowsApps\python3.13.exe"

echo Starting JARVIS TypeScript shell...
"%PYTHON_EXE%" "%~dp0web_main.py"

endlocal
