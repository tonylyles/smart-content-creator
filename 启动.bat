@echo off
chcp 65001 >nul
title AuraScribe

cd /d "%~dp0"

set "PYTHON="
if exist "C:\Program Files\AutoClaw\resources\python\python.exe" (
    set "PYTHON=C:\Program Files\AutoClaw\resources\python\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON=python"
    ) else (
        echo Python not found. Please install Python 3.10+
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import gradio" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    "%PYTHON%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo Install failed. Check network.
        pause
        exit /b 1
    )
    echo Done!
)

echo Starting AuraScribe...
echo Browser will open in 8 seconds...
echo If not, visit: http://127.0.0.1:7860
echo Close this window to stop.

start "" cmd /c "timeout /t 8 /nobreak >nul & start http://127.0.0.1:7860"

"%PYTHON%" -u run_ui.py
pause
