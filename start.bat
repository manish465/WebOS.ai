@echo off
title WebOS.ai Launcher
echo ===================================================
echo           Starting WebOS.ai v2.0
echo ===================================================
echo.
echo 1. Opening Test Form at http://localhost:1420/test.html in Chrome...
start chrome "http://localhost:1420/test.html"

echo 2. Launching WebOS Desktop Control Plane...
cd /d "D:\DEVLOPMENT\Projects\WebOS.ai"
npm run dev -- --open

pause
