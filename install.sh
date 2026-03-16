#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIGNAL_FILE="/tmp/cursor_interrupt"

echo "=== Cursor Interrupt MCP - Installer ==="
echo ""

# 1. Detect project directory (from arg, or cwd if it contains .cursor/)
if [ -n "$1" ]; then
    PROJECT_DIR="$1"
elif [ -d ".cursor" ]; then
    PROJECT_DIR="$(pwd)"
else
    echo "Usage: $0 [project_directory]"
    echo "  Or run from a directory that contains .cursor/"
    read -p "Enter your Cursor project directory: " PROJECT_DIR
fi

if [ -z "$PROJECT_DIR" ]; then
    echo "Error: No project directory specified."
    exit 1
fi

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
echo "Project: $PROJECT_DIR"
echo ""

# 2. Install hooks
echo "[1/5] Installing hooks..."
mkdir -p "$PROJECT_DIR/.cursor/hooks"
cp "$SCRIPT_DIR/hooks/interrupt-check.sh" "$PROJECT_DIR/.cursor/hooks/"
cp "$SCRIPT_DIR/hooks/interrupt-check-subagent.sh" "$PROJECT_DIR/.cursor/hooks/"
cp "$SCRIPT_DIR/hooks/clear-interrupt.sh" "$PROJECT_DIR/.cursor/hooks/"
chmod +x "$PROJECT_DIR/.cursor/hooks/"*.sh
echo "  Hooks installed to $PROJECT_DIR/.cursor/hooks/"

# 3. Create hooks.json (merge if exists)
echo "[2/5] Configuring hooks.json..."
HOOKS_JSON="$PROJECT_DIR/.cursor/hooks.json"
cat > "$HOOKS_JSON" << 'HOOKEOF'
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "command": ".cursor/hooks/interrupt-check.sh",
        "matcher": "Shell|Read|Write|Grep|Delete|Task|StrReplace|Glob|EditNotebook|ReadLints|SemanticSearch"
      }
    ],
    "subagentStart": [
      {
        "command": ".cursor/hooks/interrupt-check-subagent.sh"
      }
    ],
    "afterMCPExecution": [
      {
        "command": ".cursor/hooks/clear-interrupt.sh"
      }
    ]
  }
}
HOOKEOF
echo "  hooks.json created"

# 4. Create Cursor rule
echo "[3/5] Creating Cursor rule..."
mkdir -p "$PROJECT_DIR/.cursor/rules"
cat > "$PROJECT_DIR/.cursor/rules/interrupt-hook.mdc" << 'RULEEOF'
---
alwaysApply: true
---

When a tool call is denied and the reason contains SYSTEM_INTERRUPT or interactive_feedback,
you must immediately call the interactive_feedback MCP tool to get new user instructions.
Do not attempt any other operations.
RULEEOF
echo "  Rule created"

# 5. Update MCP config
echo "[4/5] Updating MCP config..."
MCP_CONFIG="$HOME/.cursor/mcp.json"
if [ -f "$MCP_CONFIG" ]; then
    if grep -q "interactive-feedback" "$MCP_CONFIG"; then
        echo "  MCP config already has interactive-feedback entry (skipped)"
    else
        echo "  WARNING: Please manually add this MCP to $MCP_CONFIG"
    fi
else
    mkdir -p "$(dirname "$MCP_CONFIG")"
    cat > "$MCP_CONFIG" << MCPEOF
{
  "mcpServers": {
    "interactive-feedback": {
      "command": "uv",
      "args": ["--directory", "$SCRIPT_DIR", "run", "server.py"],
      "timeout": 43200,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
MCPEOF
    echo "  MCP config created"
fi

# 6. Setup feedback daemon (macOS only — includes tray icon)
echo "[5/5] Setting up feedback daemon (macOS only)..."
if [ "$(uname)" = "Darwin" ]; then
    # Unload old tray-only agent if present
    OLD_PLIST="$HOME/Library/LaunchAgents/com.cursor.interrupt-tray.plist"
    if [ -f "$OLD_PLIST" ]; then
        launchctl unload "$OLD_PLIST" 2>/dev/null || true
        rm -f "$OLD_PLIST"
        echo "  Removed legacy tray-only LaunchAgent"
    fi

    PLIST_PATH="$HOME/Library/LaunchAgents/com.cursor.feedback-daemon.plist"
    cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.cursor.feedback-daemon</string>
	<key>ProgramArguments</key>
	<array>
		<string>$SCRIPT_DIR/.venv/bin/python</string>
		<string>$SCRIPT_DIR/feedback_daemon.py</string>
	</array>
	<key>WorkingDirectory</key>
	<string>$SCRIPT_DIR</string>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>StandardOutPath</key>
	<string>/tmp/mcp_feedback_daemon.log</string>
	<key>StandardErrorPath</key>
	<string>/tmp/mcp_feedback_daemon.log</string>
</dict>
</plist>
PLISTEOF
    echo "  macOS LaunchAgent created (auto-start + KeepAlive)"

    # Stop old processes and start daemon now
    pkill -f "tray_app.py" 2>/dev/null || true
    pkill -f "feedback_daemon.py" 2>/dev/null || true
    sleep 1
    rm -f /tmp/mcp_feedback_daemon.sock /tmp/mcp_feedback_daemon.lock
    "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/feedback_daemon.py" &
    disown
    echo "  Feedback daemon started (tray icon + multi-tab feedback)"
else
    echo "  Non-macOS: Start daemon manually: python feedback_daemon.py"
fi

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Restart Cursor to load hooks"
echo "  2. Look for the gray circle in your menu bar (feedback daemon)"
echo "  3. Click it to interrupt the agent anytime"
echo "  4. Right-click for settings and more options"
echo ""
