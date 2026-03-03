#!/bin/bash
# Start the Cursor Interrupt tray app (menu bar icon)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Kill any existing instance
pkill -f "tray_app.py" 2>/dev/null

# Launch in background
.venv/bin/python tray_app.py &
disown
echo "Cursor Interrupt tray app started (menu bar icon)"
