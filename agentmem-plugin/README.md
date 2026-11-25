# agentmem: one plugin for every coding agent & IDE

Connects **VS Code** (Copilot, Roo Code, Cline, Continue), **Antigravity (agy CLI + IDE)**, **Cursor**, **Windsurf**, **Claude Code**, **Codex CLI**, and **Gemini CLI** to your Agent Memory Server. Pure Python (3.9+, standard library only) with zero pip dependencies.

## 🚀 Install (once per machine)

```bash
python3 agentmem.py install --url http://YOUR-SERVER:8080 --token <agent-token>
#   --agents all                 configure every supported agent and IDE
#   --agents vscode,antigravity  pick specific agents/IDEs
#   --hooks                      Claude Code: auto-inject project context at session start
#   --remove                     remove this plugin from all agents and delete ~/.agentmem
```

### Supported Agents & IDEs:

| Agent / IDE | MCP Server Configuration | Rules & Instruction File |
|---|---|---|
| **VS Code** | `.vscode/mcp.json` / Roo Code / Cline / Continue | `AGENTS.md` / `.vscode/mcp.json` |
| **Antigravity (AGY)** | `~/.gemini/config/mcp_config.json` | `~/.gemini/GEMINI.md` & `.agents/AGENTS.md` |
| **Cursor** | `~/.cursor/mcp.json` & `.cursor/mcp.json` | `AGENTS.md` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | `AGENTS.md` |
| **Claude Code** | `claude mcp add --scope user` | `~/.claude/CLAUDE.md` |
| **Codex CLI** | `~/.codex/config.toml` | `~/.codex/AGENTS.md` |
| **Gemini CLI** | `~/.gemini/settings.json` | `~/.gemini/GEMINI.md` |

Existing settings are safely preserved. Re-running is idempotent and safe.

---

## 📁 Per-Repo Setup

Inside any repository you want your agents to collaborate on:

```bash
cd your-repo
python3 ~/.agentmem/agentmem.py init     # --template python|web|research|default
```

What `init` creates automatically:
1. `.agentmem.json`: binds this repo to its server project (safe to commit; no secrets)
2. `.vscode/mcp.json`: auto-configures VS Code & Roo/Cline/Copilot MCP
3. `.cursor/mcp.json`: auto-configures Cursor MCP
4. `.agents/AGENTS.md`: Antigravity / AGY rules and router
5. `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`: standard rules files

---

## 🧭 The Core Agent Protocol

All agents across all IDEs follow this shared protocol:

1. **Memory First**: Call `start_task("one-line goal")` before any work. Read returned `context`, `open_tasks`, `recent_decisions`, and `relevant_notes`.
2. **Vector-First Retrieval (Low Token, Max Quality)**: **Always search vector chunks first** (`search_memory` / `POST /search`) before reading entire files, PDFs, or images. Use chunk page citations and targeted excerpts to answer accurately while saving 95%+ context tokens.
3. **Model Read/Write Authority**: The AI model has full permission to search, read, modify, and create rules (`.agents/rules/`) and skills (`.agents/skills/`).
4. **Task Completion**: When done (or session ends), call `finish_task(summary, decisions, facts, next_steps)` to persist learning for future sessions and other agents.
5. **No Secrets**: Never store tokens, passwords, or keys in memory.

---

## 🛠 Available Tools

| Tool | Purpose |
|---|---|
| `start_task(task)` | Call first: resolves project, returns context, tasks, and notes |
| `finish_task(...)` | Call when done: records summary, decisions, facts, next steps |
| `search_memory(query)` | Vector-first hybrid search over files, PDFs, images, notes |
| `save_memory(type, text)` | Save durable knowledge (`decision`, `fact`, `task`, `note`, `context`) |
| `read_file(path, ...)` | Read text, PDF, images, or binary files |
| `write_file(path, ...)` | Write text or binary assets (supports `content_b64` for PDFs/images) |
| `list_dir(path)` | List project memory directory |
| `move_file(src, dst)` | Rename/move a file with audit log |
| `delete_file(path)` | Delete a file (recoverable via git) |
| `file_history(path)` | View git commit history of any file |
| `list_projects()` | List all memory projects accessible by this agent |
| `current_project()` | Inspect active project resolution |

---

## ⚙️ CLI Commands

```bash
# Check status and configured agents/IDEs
python3 ~/.agentmem/agentmem.py status

# Inspect project context directly from terminal
python3 ~/.agentmem/agentmem.py context

# Search memory directly from terminal
python3 ~/.agentmem/agentmem.py search "auth decision"

# Save a quick fact or decision
python3 ~/.agentmem/agentmem.py save fact "DB pool is max 10"

# Uninstall / remove from system
python3 agentmem.py install --remove
python3 ~/.agentmem/agentmem.py uninstall [--purge]
```
