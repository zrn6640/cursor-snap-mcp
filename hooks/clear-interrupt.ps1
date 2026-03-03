# Cursor afterMCPExecution hook: clear interrupt after preToolUse has denied at least once.
$null = $input | Out-Null

$signalFile = Join-Path $env:TEMP "cursor_interrupt"
$activeFile = Join-Path $env:TEMP "cursor_interrupt_active"

if (Test-Path $activeFile) {
    Remove-Item -Path $signalFile -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $activeFile -Force -ErrorAction SilentlyContinue
}
exit 0
