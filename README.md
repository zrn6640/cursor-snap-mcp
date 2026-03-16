# ⚡ Cursor Snap MCP

**Snap to interrupt. Snap to screenshot.**

One-click agent control for [Cursor IDE](https://www.cursor.com).

[English](README.md) | [简体中文](README_CN.md)

---

Enhanced fork of [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp), combined with screenshot capture from [Capture MCP](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP), plus the **first-ever Agent Interrupt mechanism**.

> 🎯 Caught the agent going wrong? **One click to interrupt and redirect** — without burning a single extra request.

---

## 💡 Why This?

In Cursor, every prompt counts as a request against your quota. When the agent misunderstands and you correct it — that's another request. And another. And another.

This MCP solves that in two ways:

1. **Feedback Loop** — The agent pauses and asks you mid-task. You reply with text + screenshots. Same request, zero extra cost.
2. **Emergency Interrupt** — Agent heading the wrong way? Click the tray icon, type new instructions. The agent course-corrects **within the same request turn**.

> 5 iterations that would cost 5 requests → now just 1.

---

## Installation

### For Humans

Copy and paste this prompt to your Cursor Agent:

```
Install and configure cursor-snap-mcp by following the instructions here:
https://raw.githubusercontent.com/zrn6640/cursor-snap-mcp/main/docs/install-guide
```

Or read the [Installation Guide](docs/install-guide), but seriously, let an agent do it.

### For Cursor Agent

Fetch the installation guide and follow it:

```
curl -s https://raw.githubusercontent.com/zrn6640/cursor-snap-mcp/main/docs/install-guide
```

### Manual (One-liner)

```bash
git clone https://github.com/zrn6640/cursor-snap-mcp.git && cd cursor-snap-mcp && uv sync && ./install.sh /path/to/your/project
```

### Verify Installation

After installation, check Cursor Settings:

**Hooks (Settings → Hooks):**

```
✓ Configured Hooks (3)

preToolUse
  .cursor/hooks/interrupt-check.sh

subagentStart
  .cursor/hooks/interrupt-check-subagent.sh

afterMCPExecution
  .cursor/hooks/clear-interrupt.sh
```

**MCP Tools (Settings → MCP):**

```
✓ interactive-feedback
  Tools: interactive_feedback
```

---

## Core Features

### 1. ⚡ One-Click Agent Interrupt

Agent doing something wrong? Don't wait for it to finish:

```
Click tray icon → Agent's next tool call blocked by Hook
  → MCP popup appears → Type new instructions + screenshots
  → Agent resumes with corrected context
```

**All within the same request turn. Zero extra cost.**

### 2. 📸 Screenshot Feedback + Click-to-Zoom

Stop describing bugs in words — show the AI:

| Method | Action | Description |
|--------|--------|-------------|
| 📷 Capture | Click button | Auto-minimizes, captures full screen |
| 📋 Paste | `Ctrl+V` / `Cmd+V` | Works with system screenshot tools |
| 📁 Browse | Click Browse... | Select local images |

Thumbnail preview with **click-to-enlarge** (full-screen modal overlay), hover-to-delete, auto-compress > 1600px.

### 3. 💬 Feedback Loop

Ask questions. Get clarifications. Make decisions. Repeat — all in one request.

### 4. 🔍 Smart Completion — `@` Files & `/` Commands

Type `@` or `/` in the feedback box — instant autocomplete, just like Cursor's native chat.

| Trigger | What it does | Source |
|---------|-------------|--------|
| `@` | File reference — fuzzy search your project files | Real-time scan of project directory |
| `/sc/` | Skill commands — auto-discovered from `~/.cursor/skills*/` and `~/.claude/skills/` | Dynamic scan on every trigger |
| `/agent/` | Subagent types — `explore`, `shell`, `browser-use`, `code-simplifier` | Built-in |
| `/edit` `/chat` `/plan` | Mode switches | Built-in |

**Keyboard:** `↑↓` navigate, `Tab`/`Enter` accept, `Escape` cancel. Filters as you type.

No cache. New files and skills appear instantly — zero restart needed.

### 5. 🪟 Single-Window Multi-Tab (Daemon Mode)

On Unix/macOS, all feedback sessions run in a **single daemon window** with tabs:

- Same agent reuses its tab via `tab_id` deduplication — no window proliferation
- Daemon auto-starts when MCP is called, stays alive in background
- **System tray icon** integrated — interrupt, settings, and window management in one process
- `KeepAlive: true` LaunchAgent ensures auto-restart on crash

### 6. ⚙️ Settings & Bottom Bar Toggles

- **Gear button** opens a centralized settings dialog: language defaults, auto-reply, timeout, custom suffix text, quick replies management, version check
- **"使用中文"** toggle — appends Chinese-response instruction to feedback
- **"重新读取Rules"** toggle — reminds AI to re-read project rules
- Both toggles configurable as default-on/off in settings

### 7. ⏱ Auto-Reply Countdown

For non-critical feedback prompts, configure a countdown timer (in settings):

- Orange countdown label: `02:30 (click to cancel)`
- Any user interaction (typing, clicking) cancels the countdown
- On expiration: auto-submits `"[自动回复] 用户暂未响应，请继续或稍后重试。"`

### 8. 🔄 Version Update Check

- On daemon startup, fetches remote `VERSION` from GitHub
- Tray notification if a newer version is available
- Manual check button in settings dialog

---

## Architecture

```
┌──────────────┐    signal file    ┌──────────────────┐
│ System Tray  │ ────────────────► │ preToolUse Hook   │
│ (● click)    │                   │ (exit 2 = block)  │
└──────────────┘                   └────────┬──────────┘
                                            │ forced MCP call
                                            ▼
                                   ┌──────────────────┐
                                   │ interactive_      │
                                   │ feedback MCP      │
                                   └────────┬──────────┘
                                            │ user submits
                                            ▼
                                   ┌──────────────────┐
                                   │ afterMCPExecution │
                                   │ (clears signal)   │
                                   └──────────────────┘
```

**Race condition protection:** Two-file mechanism — `cursor_interrupt` (signal) + `cursor_interrupt_active` (marker). Clear hook only runs when marker exists.

**Subagent:** Can block new subagent creation. Cannot stop already-running ones.

---

## Reliability

| Feature | Description |
|---------|-------------|
| **Adaptive Heartbeat** | Progressive intervals: 10s (0-10min) → 60s (10min-1h) → 300s (1h+). Prevents message flooding during long tasks. |
| **12-Hour Soft Timeout** | `SOFT_TIMEOUT = 43000s`. Returns heartbeat message instead of failing — supports very long tasks. |
| **Automatic Retry** | First attempt failed? Retries once. Falls back to AskQuestion if both fail. |
| **Daemon Watchdog** | Periodic check that poll timer is alive. Auto-restart if stuck. |
| **Multi-Tab Deduplication** | Same `tab_id` reuses existing tab instead of creating new ones. |
| **KeepAlive** | macOS LaunchAgent with `KeepAlive: true` — daemon auto-restarts on crash. |

---

## 🔧 Configuration

MCP timeout is pre-configured to 43200s (12 hours) by the installer. You can adjust it in the **Settings dialog** (gear button or tray right-click → Settings), which auto-syncs to `~/.cursor/mcp.json`:

```json
{
  "interactive-feedback": {
    "command": "uv",
    "timeout": 43200,
    "args": [...]
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| 使用中文 | On | Append Chinese response instruction |
| 重读 Rules | Off | Remind AI to re-read project rules |
| Timeout (min) | 720 | Soft timeout, synced to mcp.json |
| Auto-reply (sec) | 0 (off) | Countdown for auto-reply |
| Custom suffix | empty | Custom text appended to every submission |
| Check updates | On | Version check on daemon startup |

---

## Usage

### Daily Feedback

Agent auto-pops MCP at task checkpoints. Provide text + screenshots.

### Emergency Interrupt

1. Spot the **gray circle** ● in menu bar / system tray
2. Click the icon → select "⚡ Send Interrupt" from the menu
3. Dot turns **red** 🔴
4. Agent's next action blocked → MCP popup
5. **New instructions + screenshots** → Submit
6. Dot returns gray → Agent resumes

---

## What Gets Installed

| File | Location | Purpose |
|------|----------|---------|
| `interrupt-check.sh/ps1` | `.cursor/hooks/` | preToolUse — blocks tools on interrupt |
| `interrupt-check-subagent.sh/ps1` | `.cursor/hooks/` | subagentStart — blocks new subagents |
| `clear-interrupt.sh/ps1` | `.cursor/hooks/` | afterMCPExecution — clears signal |
| `hooks.json` | `.cursor/` | Hook configuration |
| `interrupt-hook.mdc` | `.cursor/rules/` | Agent behavior rule |
| Tray icon | System tray | One-click trigger |

---

## FAQ

**Q: Does interrupting waste an extra request?**
No. Redirects within the **same request turn** via preToolUse Hook.

**Q: Can I interrupt during "thinking"?**
Not directly. Hooks fire before tool calls. But the agent will eventually make one.

**Q: Already-running subagent?**
Cannot stop. But new creation can be blocked.

---

## Comparison

| Feature | This project | [Original](https://github.com/noopstudios/interactive-feedback-mcp) | [Capture](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP) |
|---------|:---:|:---:|:---:|
| Text feedback | ✅ | ✅ | ✅ |
| Screenshot + zoom | ✅ | ❌ | ✅ |
| Adaptive heartbeat | ✅ | ❌ | ✅ |
| **One-click interrupt** | ✅ | ❌ | ❌ |
| **`@` file completion** | ✅ | ❌ | ❌ |
| **`/` command completion** | ✅ | ❌ | ❌ |
| **Single-window multi-tab** | ✅ | ❌ | ❌ |
| **Settings dialog** | ✅ | ❌ | ❌ |
| **Chinese/Rules toggles** | ✅ | ❌ | ❌ |
| **Auto-reply countdown** | ✅ | ❌ | ❌ |
| **Version update check** | ✅ | ❌ | ❌ |
| **System tray (daemon)** | ✅ | ❌ | ❌ |
| **Hooks integration** | ✅ | ❌ | ❌ |
| **Subagent block** | ✅ | ❌ | ❌ |
| **12-hour soft timeout** | ✅ | ❌ | ❌ |
| Predefined options | ✅ | ❌ | ✅ |
| Command execution | ✅ | ✅ | ❌ |

---

## Project Structure

```
cursor-snap-mcp/
├── server.py              ← MCP server (daemon mode + adaptive heartbeat)
├── feedback_ui.py         ← PySide6 feedback UI (widgets, zoom, toggles, countdown)
├── feedback_daemon.py     ← Multi-tab daemon + system tray + interrupt + settings
├── settings_dialog.py     ← Settings dialog + config helpers + version check
├── tray_app.py            ← Standalone tray (deprecated, Windows fallback)
├── VERSION                ← Version file for update checks
├── hooks/                 ← Cursor Hooks
│   ├── interrupt-check.sh / .ps1
│   ├── interrupt-check-subagent.sh / .ps1
│   └── clear-interrupt.sh / .ps1
├── docs/install-guide     ← Agent-readable install instructions
├── install.sh / install.ps1
└── pyproject.toml
```

---

## Credits

- [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp) by Fábio Ferreira
- [Capture MCP](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP) by dragonstylecc
- [interactive-mcp](https://github.com/ttommyth/interactive-mcp) by Tommy Tong

## License

MIT
