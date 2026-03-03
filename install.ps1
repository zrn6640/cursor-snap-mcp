# Cursor Interrupt MCP - Windows Installer
param(
    [string]$ProjectDir
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "=== Cursor Interrupt MCP - Installer ===" -ForegroundColor Cyan
Write-Host ""

# 1. Detect project directory (from param, or cwd if it contains .cursor)
if (-not $ProjectDir) {
    if (Test-Path ".cursor") {
        $ProjectDir = (Get-Location).Path
    } else {
        $ProjectDir = Read-Host "Enter your Cursor project directory"
    }
}
$ProjectDir = (Resolve-Path $ProjectDir).Path
Write-Host "Project: $ProjectDir"
Write-Host ""

# 2. Install hooks
Write-Host "[1/4] Installing hooks..." -ForegroundColor Yellow
$hooksDir = Join-Path $ProjectDir ".cursor\hooks"
New-Item -Path $hooksDir -ItemType Directory -Force | Out-Null

Copy-Item "$ScriptDir\hooks\interrupt-check.sh" $hooksDir -Force
Copy-Item "$ScriptDir\hooks\interrupt-check-subagent.sh" $hooksDir -Force
Copy-Item "$ScriptDir\hooks\clear-interrupt.sh" $hooksDir -Force
Copy-Item "$ScriptDir\hooks\interrupt-check.ps1" $hooksDir -Force
Copy-Item "$ScriptDir\hooks\interrupt-check-subagent.ps1" $hooksDir -Force
Copy-Item "$ScriptDir\hooks\clear-interrupt.ps1" $hooksDir -Force
Write-Host "  Hooks installed"

# 3. Create hooks.json (use PowerShell scripts on Windows)
Write-Host "[2/4] Configuring hooks.json..." -ForegroundColor Yellow
$hooksJson = @'
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "command": "powershell -ExecutionPolicy Bypass -File .cursor/hooks/interrupt-check.ps1",
        "matcher": "Shell|Read|Write|Grep|Delete|Task|StrReplace|Glob|EditNotebook|ReadLints|SemanticSearch"
      }
    ],
    "subagentStart": [
      {
        "command": "powershell -ExecutionPolicy Bypass -File .cursor/hooks/interrupt-check-subagent.ps1"
      }
    ],
    "afterMCPExecution": [
      {
        "command": "powershell -ExecutionPolicy Bypass -File .cursor/hooks/clear-interrupt.ps1"
      }
    ]
  }
}
'@
Set-Content -Path (Join-Path $ProjectDir ".cursor\hooks.json") -Value $hooksJson -Encoding UTF8
Write-Host "  hooks.json created"

# 4. Create Cursor rule
Write-Host "[3/4] Creating Cursor rule..." -ForegroundColor Yellow
$rulesDir = Join-Path $ProjectDir ".cursor\rules"
New-Item -Path $rulesDir -ItemType Directory -Force | Out-Null
$rule = @"
---
alwaysApply: true
---

When a tool call is denied and the reason contains SYSTEM_INTERRUPT or interactive_feedback,
you must immediately call the interactive_feedback MCP tool to get new user instructions.
Do not attempt any other operations.
"@
Set-Content -Path (Join-Path $rulesDir "interrupt-hook.mdc") -Value $rule -Encoding UTF8
Write-Host "  Rule created"

# 5. Start tray app
Write-Host "[4/4] Starting tray app..." -ForegroundColor Yellow
$pythonPath = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    $pythonPath = "python"
}
Start-Process -FilePath $pythonPath -ArgumentList "$ScriptDir\tray_app.py" -WindowStyle Hidden
Write-Host "  Tray app started (system tray icon)"

Write-Host ""
Write-Host "=== Installation complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart Cursor to load hooks"
Write-Host "  2. Look for the gray circle in your system tray"
Write-Host "  3. Click it to interrupt the agent anytime"
