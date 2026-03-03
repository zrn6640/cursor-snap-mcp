#!/bin/bash
# Cursor subagentStart hook: block new subagent creation when interrupt is active.
cat > /dev/null

SIGNAL_FILE="/tmp/cursor_interrupt"

if [ -f "$SIGNAL_FILE" ]; then
    echo '{"decision":"deny","reason":"[SYSTEM_INTERRUPT] User interrupt active. Do not create subagents. Call interactive_feedback MCP tool immediately."}'
else
    echo '{"decision":"allow"}'
fi
exit 0
