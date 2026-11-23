# agentmem: one plugin for every coding agent

Connects Claude Code, Codex CLI, Gemini CLI, Antigravity (agy CLI + IDE) and Cursor to your
Agent Memory Server. No pip install: a single Python file (3.9+, standard library only).

## Install (once per machine)

```bash
python3 agentmem.py install --url http://YOUR-SERVER:8080 --token <agent-token>
#   --agents all                 configure every supported agent (default: only detected ones)
#   --agents claude,codex        pick specific agents
#   --hooks                      Claude Code: auto-inject project context at every session start
```

It copies itself to `~/.agentmem/agentmem.py` and stores the URL and token in
`~/.agentmem/config.json` (mode 600). The token is NOT copied into each agent's config.
Then, for each agent:

| Agent | MCP server added to | Global instructions |
|---|---|---|
| Claude Code | `claude mcp add --scope user` | `~/.claude/CLAUDE.md` |
| Codex CLI | `~/.codex/config.toml` | `~/.codex/AGENTS.md` |
| Gemini CLI | `~/.gemini/settings.json` | `~/.gemini/GEMINI.md` |
| Antigravity | `~/.gemini/config/mcp_config.json` | `~/.gemini/GEMINI.md` |
| Cursor | `~/.cursor/mcp.json` | per repo via `init` (AGENTS.md) |

Existing settings are preserved. The first edit of a file is backed up as `*.agentmem.bak`.
Re-running is safe. Restart your agents afterwards.

## Per repo

```bash
cd your-repo
python3 ~/.agentmem/agentmem.py init     # --template python|web|research|default
```

Creates the memory project on the server, writes `.agentmem.json` (safe to commit, no secrets)
and adds the protocol to `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`. Without `init`, the project
name falls back to the repo folder name.

## What agents do (the protocol)

1. `start_task("add login endpoint")` returns project context, open tasks, recent decisions and relevant notes
2. Work, using `search_memory` and `read_file docs/...`
3. `finish_task(summary, decisions, facts, next_steps)` saves everything for the next session or another agent

Other tools: save_memory, write_file, list_dir, move_file, delete_file, file_history,
list_projects, current_project.

## Other commands

`status` (checks the connection and which agents are configured), `context`, `search "query"`,
`save decision "text"`, `uninstall [--purge]`.

## Notes

- Agents follow instructions, they are not forced to. The `--hooks` option (Claude Code) and the
  MCP `instructions` field make the first step automatic where the agent supports it.
- Antigravity ignores env vars in some versions, which is why the token lives in `~/.agentmem/config.json`.
- Any other MCP agent: command `python3`, args `["~/.agentmem/agentmem.py", "serve"]`.
