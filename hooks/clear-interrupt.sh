#!/bin/bash
# Cursor afterMCPExecution hook: clear interrupt only after it was actually activated (per-project).
cat > /dev/null

if command -v md5 &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5 -q | cut -c1-8)
elif command -v md5sum &>/dev/null; then
    PROJECT_HASH=$(echo -n "$(pwd)" | md5sum | cut -c1-8)
else
    PROJECT_HASH="global"
fi

SIGNAL_FILE="/tmp/cursor_interrupt_${PROJECT_HASH}"
ACTIVE_FILE="/tmp/cursor_interrupt_active_${PROJECT_HASH}"

if [ -f "$ACTIVE_FILE" ]; then
    rm -f "$SIGNAL_FILE" "$ACTIVE_FILE"
fi
exit 0
