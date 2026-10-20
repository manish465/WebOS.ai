@echo off
title WebOS.ai Launcher
echo ===================================================
echo           Starting WebOS.ai v2.0
echo ===================================================
echo.
echo 1. Opening Test Form in Google Chrome...
start chrome "file:///D:/DEVLOPMENT/Projects/WebOS.ai/tests/fixtures/greenhouse_job_application.html"

echo 2. Launching WebOS Desktop Control Plane...
cd /d "D:\DEVLOPMENT\Projects\WebOS.ai"
npm run dev -- --open

pause
