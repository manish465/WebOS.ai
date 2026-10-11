@echo off
echo ========================================================
echo       WebOS Copilot — Real Chrome Session Bridge         
echo ========================================================
echo Connecting your real Chrome session to WebOS Copilot...
echo (Preserves all your logins: LinkedIn, Amazon, Google)
echo.

set EXT_DIR=%~dp0extension
start "" "chrome.exe" --load-extension="%EXT_DIR%" "http://127.0.0.1:8080"

echo Chrome launched with WebOS Real Session Bridge.
echo You can now use WebOS without any isolated profiles!
pause
