# ⚡ Cursor Snap MCP

**Snap to interrupt. Snap to screenshot.**

One-click agent control for [Cursor IDE](https://www.cursor.com).

[English](README.md) | [简体中文](README_CN.md)

---

Enhanced fork of [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp), combined with screenshot capture from [Capture MCP](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP), plus the **first-ever Agent Interrupt mechanism**.

> 🎯 Caught the agent going wrong? **One click to interrupt and redirect** — without burning a single extra request.

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

Then **restart Cursor**.

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

## Three Core Features

### 1. ⚡ One-Click Agent Interrupt (Unique)

Agent heading the wrong way? Don't wait for it to finish:

```
Click tray icon → Agent's next tool call blocked by Hook
  → MCP popup appears → Type new instructions + screenshots
  → Agent resumes with corrected context
```

**All within the same request turn. Zero extra cost.**

### 2. 📸 Screenshot Feedback

Stop describing bugs in words — show the AI:

| Method | Action | Description |
|--------|--------|-------------|
| 📷 Capture | Click button | Auto-minimizes, captures full screen |
| 📋 Paste | `Ctrl+V` / `Cmd+V` | Works with system screenshot tools |
| 📁 Browse | Click Browse... | Select local images |

Thumbnail preview, individual delete, auto-compress > 1600px.

### 3. 💬 Feedback Loop

MCP tool calls don't count as separate requests:

```
Agent → Popup → Your feedback → Agent continues → Popup → ...
```

**5 iterations that would cost 5 requests → now just 1.**

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

## Usage

### Daily Feedback

Agent auto-pops MCP at task checkpoints. Provide text + screenshots.

### Emergency Interrupt

1. Spot the **gray circle** ● in menu bar / system tray
2. **Click** → "⚡ Send Interrupt"
3. Dot turns **red** 🔴
4. Agent's next action blocked → MCP popup
5. **New instructions + screenshots** → Submit
6. Dot returns gray → Agent resumes

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
| Screenshot | ✅ | ❌ | ✅ |
| Heartbeat | ✅ | ❌ | ✅ |
| **One-click interrupt** | ✅ | ❌ | ❌ |
| **System tray** | ✅ | ❌ | ❌ |
| **Hooks integration** | ✅ | ❌ | ❌ |
| **One-click install** | ✅ | ❌ | ❌ |
| **Subagent block** | ✅ | ❌ | ❌ |
| **Cross-platform hooks** | ✅ | — | — |
| Predefined options | ✅ | ❌ | ✅ |
| Command execution | ✅ | ✅ | ❌ |

---

## Project Structure

```
cursor-snap-mcp/
├── server.py              ← MCP server
├── feedback_ui.py         ← PySide6 feedback UI
├── tray_app.py            ← System tray trigger (cross-platform)
├── hooks/                 ← Cursor Hooks
│   ├── interrupt-check.sh / .ps1
│   ├── interrupt-check-subagent.sh / .ps1
│   └── clear-interrupt.sh / .ps1
├── docs/install-guide     ← Agent-readable install instructions
├── install.sh / install.ps1
├── start-tray.sh
└── pyproject.toml
```

---

## Credits

- [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp) by Fábio Ferreira
- [Capture MCP](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP) by dragonstylecc
- [interactive-mcp](https://github.com/ttommyth/interactive-mcp) by Tommy Tong

## License

MIT
