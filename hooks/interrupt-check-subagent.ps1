# Cursor subagentStart hook: block new subagent creation when interrupt is active (Windows).
# Must output JSON to stdout; exit 0 for both allow and deny (decision is in JSON).
$null = $input | Out-Null

$signalFile = Join-Path $env:TEMP "cursor_interrupt"

if (Test-Path $signalFile) {
    Write-Output '{"decision":"deny","reason":"[SYSTEM_INTERRUPT] User interrupt active. Do not create subagents. Call interactive_feedback MCP tool immediately."}'
} else {
    Write-Output '{"decision":"allow"}'
}
exit 0
