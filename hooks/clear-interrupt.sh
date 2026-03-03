#!/bin/bash
# Cursor afterMCPExecution hook: clear interrupt only after it was actually activated.
# Only clears when preToolUse has denied at least once (active marker exists).
cat > /dev/null

SIGNAL_FILE="/tmp/cursor_interrupt"
ACTIVE_FILE="/tmp/cursor_interrupt_active"

if [ -f "$ACTIVE_FILE" ]; then
    rm -f "$SIGNAL_FILE" "$ACTIVE_FILE"
fi
exit 0
