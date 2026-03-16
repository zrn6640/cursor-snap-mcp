# ⚡ Cursor Snap MCP

**弹指打断，弹指截图。**

为 [Cursor IDE](https://www.cursor.com) 打造的一键式 Agent 控制工具。

[English](README.md) | [简体中文](README_CN.md)

---

基于 [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp) 深度增强，融合 [Capture 版](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP)截图能力，并**首创 Agent 打断机制**。

> 🎯 核心价值：发现 Agent 做错了？**一键打断，立即纠正**——不浪费一次请求额度。

---

## 💡 为什么用它？

在 Cursor 中，每条提示都计为一次请求。Agent 理解错了，你纠正一次——又一次请求。反复几次，配额就这么消耗了。

这个 MCP 用两种方式解决：

1. **反馈循环** — Agent 在执行中暂停询问你，你用文字 + 截图回复。同一个请求，零额外消耗。
2. **紧急打断** — Agent 方向跑偏？点击托盘图标，输入新指令。Agent 在**同一轮请求内**立即纠正。

> 原本需要 5 次请求的迭代，现在 1 次搞定。

---

## 安装

### 给人类

复制以下提示词，粘贴给 Cursor Agent：

```
安装并配置 cursor-snap-mcp，按照这个指南操作：
https://raw.githubusercontent.com/zrn6640/cursor-snap-mcp/main/docs/install-guide
```

或者自己看[安装指南](docs/install-guide)，但说真的，让 Agent 来吧。

### 给 Cursor Agent

获取安装指南并执行：

```
curl -s https://raw.githubusercontent.com/zrn6640/cursor-snap-mcp/main/docs/install-guide
```

### 手动安装（一行命令）

```bash
git clone https://github.com/zrn6640/cursor-snap-mcp.git && cd cursor-snap-mcp && uv sync && ./install.sh /path/to/your/project
```

### 安装验证

安装成功后，在 Cursor Settings 中可以看到：

**Hooks 配置（Settings → Hooks）：**

```
✓ Configured Hooks (3)

preToolUse
  .cursor/hooks/interrupt-check.sh

subagentStart
  .cursor/hooks/interrupt-check-subagent.sh

afterMCPExecution
  .cursor/hooks/clear-interrupt.sh
```

**MCP 工具（Settings → MCP）：**

```
✓ interactive-feedback
  Tools: interactive_feedback
```

---

## 核心能力

### 1. ⚡ 一键打断 Agent（首创）

Agent 正在执行一连串操作，你发现方向不对？不用等它做完：

```
点击系统托盘图标 → Agent 下一步操作被 Hook 拦截
  → MCP 弹窗自动弹出 → 输入新指令 + 截图
  → Agent 带着新上下文继续工作
```

**全程在同一轮请求内完成，零额外消耗。**

### 2. 📸 截图反馈 + 点击放大

不用文字描述 Bug——直接截图给 AI 看：

| 方式 | 操作 | 说明 |
|------|------|------|
| 📷 全屏截图 | 点击 Capture Screen | 自动最小化窗口，截取全屏后恢复 |
| 📋 粘贴截图 | `Ctrl+V` / `Cmd+V` | 配合系统截图工具先截取再粘贴 |
| 📁 浏览文件 | 点击 Browse... | 选择本地图片 |

缩略图预览，**点击缩略图全屏放大**（模态遮罩），hover 显示删除按钮，超过 1600px 自动压缩。

### 3. 💬 交互式反馈循环

提问、澄清、决策、迭代——全部在一次请求内完成。

### 4. 🔍 智能补全 — `@` 引用文件 & `/` 快捷命令

在反馈输入框中输入 `@` 或 `/`——即时自动补全，体验与 Cursor 原生聊天框一致。

| 触发符 | 功能 | 数据来源 |
|--------|------|---------|
| `@` | 文件引用 — 模糊搜索项目文件 | 每次触发实时扫描项目目录 |
| `/sc/` | Skill 命令 — 从 `~/.cursor/skills*/` 和 `~/.claude/skills/` 自动发现 | 每次触发动态扫描 |
| `/agent/` | Subagent 类型 — `explore`、`shell`、`browser-use`、`code-simplifier` | 内置 |
| `/edit` `/chat` `/plan` | 模式切换 | 内置 |

**键盘操作：** `↑↓` 导航，`Tab`/`Enter` 确认，`Escape` 取消。输入即过滤。

零缓存。新增文件和 Skill 立即可见——无需重启 MCP。

### 5. 🪟 单窗口多 Tab（Daemon 模式）

Unix/macOS 上所有反馈会话在**单一 daemon 窗口**中以 Tab 形式呈现：

- 同一 agent 通过 `tab_id` 去重复用已有 Tab，不会窗口泛滥
- MCP 调用时 daemon 自动启动，后台常驻
- **系统托盘图标内置** — 中断、设置、窗口管理集于一身
- macOS LaunchAgent `KeepAlive: true` 保证崩溃自动重启

### 6. ⚙️ 设置页面 + 底部开关栏

- **齿轮按钮**打开集中设置对话框：语言默认值、自动回复、超时时间、自定义追加文本、快捷回复管理、版本检查
- **「使用中文」** 开关 — 提交时追加中文回复指令
- **「重新读取 Rules」** 开关 — 提醒 AI 重读项目规则
- 两个开关的默认值可在设置中配置

### 7. ⏱ 自动回复倒计时

对不需要响应的反馈提示，在设置中配置倒计时秒数：

- 橙色倒计时标签：`02:30 (点击取消)`
- 用户任何交互（打字、点击）自动取消倒计时
- 到期时自动提交：`"[自动回复] 用户暂未响应，请继续或稍后重试。"`

### 8. 🔄 版本更新检查

- daemon 启动时自动从 GitHub 获取远程 `VERSION`
- 有新版本时托盘通知提醒
- 设置对话框中手动检查按钮

---

## 打断机制架构

```
┌──────────────────┐
│   系统托盘图标    │   ← 菜单栏常驻（灰色●）
│   点击 ⚡         │
└────────┬─────────┘
         │ 创建信号文件
         ▼
┌──────────────────┐
│  preToolUse Hook │   ← Agent 每次工具调用前触发
│  (exit 2 = 阻止) │
└────────┬─────────┘
         │ Agent 被迫调用 MCP
         ▼
┌──────────────────┐
│  interactive_    │   ← 弹窗：输入新指令 + 截图
│  feedback MCP    │
└────────┬─────────┘
         │ 用户提交反馈
         ▼
┌──────────────────┐
│ afterMCPExecution│   ← 自动清除信号，恢复正常
│  Hook (清除)      │
└──────────────────┘
```

**防竞态设计：** 双文件机制——`cursor_interrupt`（信号）+ `cursor_interrupt_active`（激活标记）。只有激活标记存在时才清除信号。

**Subagent：** 可阻止新 Subagent 创建。无法停止已在运行的（Cursor 架构限制）。

---

## 可靠性

| 功能 | 说明 |
|------|------|
| **自适应心跳** | 递进式频率：10s（0-10分钟）→ 60s（10分钟-1小时）→ 300s（1小时+），避免长任务消息堆积 |
| **12 小时软超时** | `SOFT_TIMEOUT = 43000s`，超时返回心跳消息而非失败，支持超长任务 |
| **自动重试** | 首次失败自动重试一次，仍失败则降级到 AskQuestion 工具 |
| **Daemon 看门狗** | 定期检查轮询定时器存活状态，卡死时自动重启 |
| **Tab 去重** | 相同 `tab_id` 复用已有 Tab 而非创建新 Tab |
| **KeepAlive** | macOS LaunchAgent `KeepAlive: true`，daemon 崩溃自动重启 |

---

## 🔧 配置

安装脚本已预配置 MCP 超时为 43200 秒（12 小时）。可在**设置对话框**（齿轮按钮 或 托盘右键 → 设置）中调整，自动同步到 `~/.cursor/mcp.json`：

```json
{
  "interactive-feedback": {
    "command": "uv",
    "timeout": 43200,
    "args": [...]
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 使用中文 | 开启 | 提交时追加中文回复指令 |
| 重读 Rules | 关闭 | 提醒 AI 重读项目规则 |
| 超时时间（分钟） | 720 | 软超时，自动同步到 mcp.json |
| 自动回复（秒） | 0（关闭） | 倒计时自动回复 |
| 自定义追加文本 | 空 | 每次提交时自动追加 |
| 启动检查更新 | 开启 | daemon 启动时检查新版本 |

---

## 使用方法

### 日常反馈

Agent 在任务节点自动弹出 MCP 窗口，提供文字/截图反馈即可。

### 紧急打断

1. 看到菜单栏/托盘的 **灰色圆点** ●
2. **点击图标** → 从菜单中选择 "⚡ Send Interrupt"
3. 圆点变 **红色** 🔴
4. Agent 下一步操作被阻止，MCP 弹窗弹出
5. **输入新指令 + 截图** → 提交
6. 圆点恢复灰色 → Agent 按新指令继续

---

## 安装了什么

| 文件 | 位置 | 用途 |
|------|------|------|
| `interrupt-check.sh/ps1` | `.cursor/hooks/` | preToolUse — 打断时阻止工具调用 |
| `interrupt-check-subagent.sh/ps1` | `.cursor/hooks/` | subagentStart — 阻止新子代理 |
| `clear-interrupt.sh/ps1` | `.cursor/hooks/` | afterMCPExecution — 清除信号 |
| `hooks.json` | `.cursor/` | Hook 配置 |
| `interrupt-hook.mdc` | `.cursor/rules/` | Agent 行为规则 |
| 托盘图标 | 系统托盘 | 一键打断触发器 |

---

## 常见问题

**Q: 打断需要浪费额外的请求次数吗？**
不需要。通过 preToolUse Hook 在**同一轮请求内**重定向 Agent。

**Q: Agent 在"思考"时能打断吗？**
不能直接打断。Hook 只在工具调用前触发。但 Agent 思考完必然执行操作，那时会被拦截。

**Q: 已在运行的 Subagent 能打断吗？**
不能停止。但可以阻止新 Subagent 的创建。

---

## 对比

| 特性 | 本项目 | [原版](https://github.com/noopstudios/interactive-feedback-mcp) | [Capture 版](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP) |
|------|:---:|:---:|:---:|
| 文字反馈 | ✅ | ✅ | ✅ |
| 截图 + 点击放大 | ✅ | ❌ | ✅ |
| 自适应心跳 | ✅ | ❌ | ✅ |
| **一键打断** | ✅ | ❌ | ❌ |
| **`@` 文件补全** | ✅ | ❌ | ❌ |
| **`/` 命令补全** | ✅ | ❌ | ❌ |
| **单窗口多 Tab** | ✅ | ❌ | ❌ |
| **设置对话框** | ✅ | ❌ | ❌ |
| **中文/Rules 开关** | ✅ | ❌ | ❌ |
| **自动回复倒计时** | ✅ | ❌ | ❌ |
| **版本更新检查** | ✅ | ❌ | ❌ |
| **系统托盘（daemon）** | ✅ | ❌ | ❌ |
| **Hooks 集成** | ✅ | ❌ | ❌ |
| **Subagent 拦截** | ✅ | ❌ | ❌ |
| **12 小时软超时** | ✅ | ❌ | ❌ |
| 预定义选项 | ✅ | ❌ | ✅ |
| 命令执行 | ✅ | ✅ | ❌ |

---

## 项目结构

```
cursor-snap-mcp/
├── server.py              ← MCP 服务器（daemon 模式 + 自适应心跳）
├── feedback_ui.py         ← PySide6 反馈 UI（组件、放大、开关、倒计时）
├── feedback_daemon.py     ← 多 Tab daemon + 系统托盘 + 中断 + 设置入口
├── settings_dialog.py     ← 设置对话框 + 配置助手 + 版本检查
├── tray_app.py            ← 独立托盘（已弃用，Windows 降级方案）
├── VERSION                ← 版本文件，用于更新检查
├── hooks/                 ← Cursor Hooks
│   ├── interrupt-check.sh / .ps1
│   ├── interrupt-check-subagent.sh / .ps1
│   └── clear-interrupt.sh / .ps1
├── docs/install-guide     ← Agent 可读的安装指南
├── install.sh / install.ps1
└── pyproject.toml
```

---

## 致谢

- [Interactive Feedback MCP](https://github.com/noopstudios/interactive-feedback-mcp) by Fábio Ferreira
- [Capture MCP](https://github.com/dragonstylecc/Interactive-Feedback-With-Capture-MCP) by dragonstylecc
- [interactive-mcp](https://github.com/ttommyth/interactive-mcp) by Tommy Tong

## 许可证

MIT
