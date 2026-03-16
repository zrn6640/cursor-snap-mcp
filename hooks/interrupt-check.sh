#!/bin/bash
# Cursor preToolUse hook: detect user interrupt signal (per-project).
# Exit code 2 = block the tool. Writes reason to stderr for agent visibility.
cat > /dev/null

# Compute per-project hash from cwd
if command -v md5 &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5 -q | cut -c1-8)
elif command -v md5sum &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5sum | cut -c1-8)
else
    PROJECT_HASH="global"
fi

SIGNAL_FILE="/tmp/cursor_interrupt_${PROJECT_HASH}"
ACTIVE_FILE="/tmp/cursor_interrupt_active_${PROJECT_HASH}"

if [ -f "$SIGNAL_FILE" ]; then
    touch "$ACTIVE_FILE"
    echo "[SYSTEM_INTERRUPT] User interrupt active. You MUST call interactive_feedback MCP tool immediately to get new instructions. No other operations allowed." >&2
    exit 2
fi
exit 0
