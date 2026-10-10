#!/usr/bin/env bash
# ==========================================================
# WebOS.ai — 1-Click Interactive Chat UI Launcher (Bash)
# ==========================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "          Launching WebOS.ai Interactive Chat UI          "
echo "=========================================================="

PYTHON_EXE="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
fi

echo "[*] Starting WebOS.ai Chat Server at http://localhost:8080..."
"$PYTHON_EXE" -m webos.server
