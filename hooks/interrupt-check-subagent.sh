#!/bin/bash
# Cursor subagentStart hook: block new subagent creation when interrupt is active (per-project).
cat > /dev/null

if command -v md5 &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5 -q | cut -c1-8)
elif command -v md5sum &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5sum | cut -c1-8)
else
    PROJECT_HASH="global"
fi

SIGNAL_FILE="/tmp/cursor_interrupt_${PROJECT_HASH}"

if [ -f "$SIGNAL_FILE" ]; then
    echo '{"decision":"deny","reason":"[SYSTEM_INTERRUPT] User interrupt active. Do not create subagents. Call interactive_feedback MCP tool immediately."}'
else
    echo '{"decision":"allow"}'
fi
exit 0
