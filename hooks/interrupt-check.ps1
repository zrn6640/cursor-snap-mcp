# Cursor preToolUse hook: detect user interrupt signal (per-project, Windows).
# Exit code 2 = block the tool. Consume stdin for compatibility.
$null = $input | Out-Null

$projectHash = ([System.Security.Cryptography.MD5]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes($PWD.Path)
) | ForEach-Object { $_.ToString("x2") }) -join "" | Select-Object -First 1
$projectHash = $projectHash.Substring(0, 8)

$signalFile = Join-Path $env:TEMP "cursor_interrupt_$projectHash"
$activeFile = Join-Path $env:TEMP "cursor_interrupt_active_$projectHash"

if (Test-Path $signalFile) {
    New-Item -Path $activeFile -ItemType File -Force | Out-Null
    [Console]::Error.WriteLine("[SYSTEM_INTERRUPT] User interrupt active. You MUST call interactive_feedback MCP tool immediately to get new instructions. No other operations allowed.")
    exit 2
}
exit 0
