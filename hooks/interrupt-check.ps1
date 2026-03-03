# Cursor preToolUse hook: detect user interrupt signal (Windows).
# Exit code 2 = block the tool. Consume stdin for compatibility.
$null = $input | Out-Null

$signalFile = Join-Path $env:TEMP "cursor_interrupt"
$activeFile = Join-Path $env:TEMP "cursor_interrupt_active"

if (Test-Path $signalFile) {
    New-Item -Path $activeFile -ItemType File -Force | Out-Null
    [Console]::Error.WriteLine("[SYSTEM_INTERRUPT] User interrupt active. You MUST call interactive_feedback MCP tool immediately to get new instructions. No other operations allowed.")
    exit 2
}
exit 0
