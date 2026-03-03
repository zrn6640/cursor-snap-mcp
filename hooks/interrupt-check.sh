#!/bin/bash
# Cursor preToolUse hook: detect user interrupt signal.
# Exit code 2 = block the tool. Writes reason to stderr for agent visibility.
cat > /dev/null

SIGNAL_FILE="/tmp/cursor_interrupt"
ACTIVE_FILE="/tmp/cursor_interrupt_active"

if [ -f "$SIGNAL_FILE" ]; then
    touch "$ACTIVE_FILE"
    echo "[SYSTEM_INTERRUPT] User interrupt active. You MUST call interactive_feedback MCP tool immediately to get new instructions. No other operations allowed." >&2
    exit 2
fi
exit 0
