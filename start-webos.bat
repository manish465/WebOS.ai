@echo off
REM ==========================================================
REM WebOS.ai — 1-Click Interactive Chat UI Launcher
REM ==========================================================

cd /d "%~dp0"

echo ==========================================================
echo            Launching WebOS.ai Interactive UI              
echo ==========================================================

REM Check virtualenv
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

REM Start server and launch chat window in default browser
echo [*] Starting WebOS.ai Chat Server at http://localhost:8080...
"%PYTHON_EXE%" -m webos.server

pause
