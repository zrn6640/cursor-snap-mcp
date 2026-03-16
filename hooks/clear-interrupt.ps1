# Cursor afterMCPExecution hook: clear interrupt after activation (per-project, Windows).
$null = $input | Out-Null

$projectHash = ([System.Security.Cryptography.MD5]::Create().ComputeHash(
    [System.Text.Encoding]::UTF8.GetBytes($PWD.Path)
) | ForEach-Object { $_.ToString("x2") }) -join "" | Select-Object -First 1
$projectHash = $projectHash.Substring(0, 8)

$signalFile = Join-Path $env:TEMP "cursor_interrupt_$projectHash"
$activeFile = Join-Path $env:TEMP "cursor_interrupt_active_$projectHash"

if (Test-Path $activeFile) {
    Remove-Item -Path $signalFile -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $activeFile -Force -ErrorAction SilentlyContinue
}
exit 0
