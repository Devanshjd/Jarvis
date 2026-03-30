@echo off
title J.A.R.V.I.S — Stark Industries
color 0B
echo.
echo  ============================================
echo    J.A.R.V.I.S  —  STARK INDUSTRIES
echo    Personal AI System v5.0
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from python.org
    pause
    exit /b 1
)
echo  [OK] Python found

:: Install core deps
echo.
echo  Installing required packages...
echo.
pip install anthropic pillow keyboard pystray pyautogui --quiet

:: Install voice deps
echo.
echo  Installing voice system...
echo.
pip install pyttsx3 SpeechRecognition pyaudio --quiet 2>nul
if errorlevel 1 (
    echo  [WARN] pyaudio failed — voice input may not work
    echo         Try: pip install pipwin ^&^& pipwin install pyaudio
)

:: Install monitoring
pip install psutil --quiet

echo.
echo  ============================================
echo  [OK] All systems ready!
echo.
echo  To set your API key:
echo    1. Get key from console.anthropic.com
echo    2. JARVIS will ask for it on first launch
echo  ============================================
echo.

:: Launch
echo  Initializing J.A.R.V.I.S...
echo.
python main.py

pause
