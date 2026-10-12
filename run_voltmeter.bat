@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Run setup.ps1 first:
    echo powershell -ExecutionPolicy Bypass -File setup.ps1
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -B main.py
if errorlevel 1 pause
