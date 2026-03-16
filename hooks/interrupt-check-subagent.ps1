# Cursor subagentStart hook: block new subagent creation on interrupt (per-project, Windows).
$null = $input | Out-Null

$projectHash = ([System.Security.Cryptography.MD5]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes($PWD.Path)
) | ForEach-Object { $_.ToString("x2") }) -join "" | Select-Object -First 1
$projectHash = $projectHash.Substring(0, 8)

$signalFile = Join-Path $env:TEMP "cursor_interrupt_$projectHash"

if (Test-Path $signalFile) {
    Write-Output '{"decision":"deny","reason":"[SYSTEM_INTERRUPT] User interrupt active. Do not create subagents. Call interactive_feedback MCP tool immediately."}'
} else {
    Write-Output '{"decision":"allow"}'
}
exit 0
