# ==========================================================
# WebOS.ai — 1-Click Interactive Chat UI Launcher (PowerShell)
# ==========================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "          Launching WebOS.ai Interactive Chat UI          " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$pythonExe = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    $pythonExe = ".venv\Scripts\python.exe"
}

Write-Host "[*] Starting WebOS.ai Chat Server at http://localhost:8080..." -ForegroundColor Yellow
& $pythonExe -m webos.server
