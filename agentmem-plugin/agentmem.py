#!/usr/bin/env python3
"""agentmem - one plugin that connects every coding agent to your Agent Memory Server.

Pure standard library (Python 3.9+), no pip install needed.

  python3 agentmem.py install            # configure all detected agents (Claude Code, Codex, Gemini CLI, Antigravity, Cursor)
  python3 ~/.agentmem/agentmem.py init   # run inside a repo: bind it to a memory project + write AGENTS.md/CLAUDE.md/GEMINI.md
  python3 ~/.agentmem/agentmem.py status
  python3 ~/.agentmem/agentmem.py uninstall

Agents then talk to it as an MCP server (`agentmem.py serve`) and follow a simple protocol:
start_task -> work -> finish_task.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
PY = sys.executable or "python3"


def home() -> Path:
    return Path.home()


def app_dir() -> Path:
    return home() / ".agentmem"


def installed_path() -> Path:
    return app_dir() / "agentmem.py"


# ============================================================ config + HTTP
class ApiError(Exception):
    pass


def load_config() -> dict:
    cfg = {}
    f = app_dir() / "config.json"
    if f.is_file():
        try:
            cfg = json.loads(f.read_text("utf-8"))
        except json.JSONDecodeError:
            pass
    if os.environ.get("AGENTMEM_URL"):
        cfg["url"] = os.environ["AGENTMEM_URL"]
    if os.environ.get("AGENTMEM_TOKEN"):
        cfg["token"] = os.environ["AGENTMEM_TOKEN"]
    return cfg


def save_config(url: str, token: str):
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    f = d / "config.json"
    f.write_text(json.dumps({"url": url.rstrip("/"), "token": token}, indent=2), "utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def api(method: str, path: str, body=None, params=None, cfg=None, timeout=60):
    cfg = cfg or load_config()
    if not cfg.get("url") or not cfg.get("token"):
        raise ApiError("not configured: run `agentmem.py install --url ... --token ...`")
    url = cfg["url"].rstrip("/") + path
    if params:
        q = {k: v for k, v in params.items() if v is not None}
        if q:
            url += "?" + urllib.parse.urlencode(q)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(raw)
            msg = j.get("error") or j.get("detail") or raw
        except json.JSONDecodeError:
            msg = raw
        raise ApiError(f"{e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ApiError(f"cannot reach memory server at {cfg['url']}: {e.reason}")


# ============================================================ project resolution
def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", s.lower()).strip("-._")
    return (s or "project")[:63]


def git_root(start: Path):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                           capture_output=True, text=True, timeout=5)
        return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def find_binding(start: Path):
    for d in [start, *start.parents]:
        f = d / ".agentmem.json"
        if f.is_file():
            try:
                p = json.loads(f.read_text("utf-8")).get("project")
                if p:
                    return p, d
            except (json.JSONDecodeError, OSError):
                pass
    return None, None


def resolve_project(explicit=None):
    """Returns (project_name, how_it_was_found)."""
    if explicit:
        return explicit, "argument"
    if os.environ.get("AGENTMEM_PROJECT"):
        return os.environ["AGENTMEM_PROJECT"], "env AGENTMEM_PROJECT"
    cwd = Path.cwd()
    p, d = find_binding(cwd)
    if p:
        return p, f"{d}/.agentmem.json"
    root = git_root(cwd) or cwd
    return slugify(root.name), f"folder name ({root})"


_known: set[str] = set()


def ensure_project(name: str, template="default") -> bool:
    """Create the project on the server if missing. Returns True if created."""
    if name in _known:
        return False
    if name in api("GET", "/projects").get("projects", []):
        _known.add(name)
        return False
    api("POST", "/projects", {"name": name, "template": template})
    _known.add(name)
    return True


# ============================================================ tools (shared by MCP + CLI)
TOOLS: dict = {}


def tool(name, description, props=None, required=()):
    props = props or {}

    def deco(fn):
        schema_props = {}
        for k, (t, d) in props.items():
            schema_props[k] = ({"type": "array", "items": {"type": "string"}, "description": d}
                               if t == "string[]" else {"type": t, "description": d})
        TOOLS[name] = {"fn": fn, "description": description, "required": list(required),
                       "schema": {"type": "object", "properties": schema_props,
                                  "required": list(required)}}
        return fn
    return deco


PROJ = ("string", "Memory project name. Optional: auto-detected from the repo (.agentmem.json / folder name).")


@tool("start_task",
      "CALL THIS FIRST before any task. Returns project context, open tasks, recent decisions and notes "
      "relevant to the task. Creates the project on first use.",
      {"task": ("string", "One-line description of what you are about to do"), "project": PROJ}, ["task"])
def start_task(task, project=None):
    p, how = resolve_project(project)
    created = ensure_project(p)
    ctx = api("GET", f"/projects/{p}/context")
    hits = api("POST", f"/projects/{p}/search", {"query": task, "limit": 5}).get("results", [])
    out = {"project": p, "project_resolved_from": how, "new_project": created,
           "context": ctx.get("context", ""), "open_tasks": ctx.get("tasks", ""),
           "recent_decisions": ctx.get("recent_decisions", ""),
           "relevant_notes": hits, "files": ctx.get("files", []),
           "reminder": "Check docs/ via read_file before assuming. When done call finish_task."}
    return out


@tool("finish_task",
      "CALL THIS WHEN DONE (or when the session ends). Saves what future sessions and other agents need.",
      {"summary": ("string", "What was done and the outcome, 1-5 sentences"),
       "decisions": ("string[]", "Decisions made, each with the reason"),
       "facts": ("string[]", "Durable facts learned about the project (commands, conventions, gotchas)"),
       "next_steps": ("string[]", "What remains to be done"),
       "update_context": ("string", "Optional: new full project state summary (REPLACES memory/context.md)"),
       "task": ("string", "The task title (same as start_task)"),
       "project": PROJ}, ["summary"])
def finish_task(summary, decisions=None, facts=None, next_steps=None, update_context=None,
                task=None, project=None):
    p, _ = resolve_project(project)
    ensure_project(p)
    saved = []

    def save(t, text):
        api("POST", f"/projects/{p}/memory", {"type": t, "text": text})
        saved.append(t)

    save("note", f"Task: {task}\n{summary}" if task else summary)
    for d in decisions or []:
        save("decision", d)
    for f in facts or []:
        save("fact", f)
    if next_steps:
        save("task", "\n".join(f"- [ ] {s}" for s in next_steps))
    if update_context:
        save("context", update_context)
    return {"project": p, "saved": saved}


@tool("search_memory", "Semantic + keyword search over all project files and saved memory.",
      {"query": ("string", "What to look for"), "limit": ("integer", "Max results (default 8)"),
       "project": PROJ}, ["query"])
def search_memory(query, limit=8, project=None):
    p, _ = resolve_project(project)
    return api("POST", f"/projects/{p}/search", {"query": query, "limit": limit})


@tool("save_memory", "Save one piece of durable knowledge. type: decision | fact | task | note | context "
      "(context replaces the project summary).",
      {"type": ("string", "decision | fact | task | note | context"), "text": ("string", "The content"),
       "project": PROJ}, ["type", "text"])
def save_memory(type, text, project=None):
    p, _ = resolve_project(project)
    ensure_project(p)
    return api("POST", f"/projects/{p}/memory", {"type": type, "text": text})


@tool("read_file", "Read a text file from the project memory store (optionally at a git revision).",
      {"path": ("string", "Path inside the project, e.g. docs/design.md"),
       "rev": ("string", "Optional git revision from file_history"), "project": PROJ}, ["path"])
def read_file(path, rev=None, project=None):
    p, _ = resolve_project(project)
    return api("GET", f"/projects/{p}/file", params={"path": path, "rev": rev})


@tool("write_file", "Create/overwrite/append a file in the project memory store (docs, notes, specs). "
      "Pass expected_sha256 from read_file to avoid overwriting someone else's edit.",
      {"path": ("string", "Path inside the project"), "content": ("string", "File content"),
       "append": ("boolean", "Append instead of overwrite"),
       "expected_sha256": ("string", "sha256 from read_file"), "project": PROJ}, ["path", "content"])
def write_file(path, content, append=False, expected_sha256=None, project=None):
    p, _ = resolve_project(project)
    ensure_project(p)
    return api("PUT", f"/projects/{p}/file", {"path": path, "content": content, "append": append,
                                               "expected_sha256": expected_sha256})


@tool("list_dir", "List a directory in the project memory store.",
      {"path": ("string", "Directory ('' = project root)"), "project": PROJ})
def list_dir(path="", project=None):
    p, _ = resolve_project(project)
    return api("GET", f"/projects/{p}/files", params={"path": path})


@tool("move_file", "Move/rename a file in the project memory store.",
      {"src": ("string", "Source path"), "dst": ("string", "Destination path"), "project": PROJ},
      ["src", "dst"])
def move_file(src, dst, project=None):
    p, _ = resolve_project(project)
    return api("POST", f"/projects/{p}/move", {"src": src, "dst": dst})


@tool("delete_file", "Delete a file from the project memory store (recoverable from git history).",
      {"path": ("string", "Path to delete"), "project": PROJ}, ["path"])
def delete_file(path, project=None):
    p, _ = resolve_project(project)
    return api("DELETE", f"/projects/{p}/file", params={"path": path})


@tool("file_history", "Git history of a file in the project memory store.",
      {"path": ("string", "Path"), "project": PROJ}, ["path"])
def file_history(path, project=None):
    p, _ = resolve_project(project)
    return api("GET", f"/projects/{p}/history", params={"path": path})


@tool("list_projects", "List memory projects this agent can access.")
def list_projects():
    return api("GET", "/projects")


@tool("current_project", "Show which memory project this session resolves to and why.",
      {"project": PROJ})
def current_project(project=None):
    p, how = resolve_project(project)
    return {"project": p, "resolved_from": how, "cwd": str(Path.cwd())}


# ============================================================ MCP stdio server
SERVER_INSTRUCTIONS = (
    "Shared project memory. Before any task call start_task(task) and follow the returned context and "
    "decisions. Use search_memory instead of guessing about project history. When finished call "
    "finish_task(summary, decisions, facts, next_steps). Never store secrets."
)


def _send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _call_tool(name, args):
    t = TOOLS.get(name)
    if not t:
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}
    allowed = t["schema"]["properties"].keys()
    clean = {k: v for k, v in (args or {}).items() if k in allowed and v is not None}
    try:
        res = t["fn"](**clean)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}
    except Exception as e:  # noqa: BLE001
        return {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}


def _handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method is None or mid is None:
        return  # notification or client response
    try:
        if method == "initialize":
            ver = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
            result = {"protocolVersion": ver, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "agent-memory", "version": VERSION},
                      "instructions": SERVER_INSTRUCTIONS}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [{"name": n, "description": t["description"], "inputSchema": t["schema"]}
                                for n, t in TOOLS.items()]}
        elif method == "tools/call":
            p = msg.get("params") or {}
            result = _call_tool(p.get("name"), p.get("arguments"))
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})
            return
        _send({"jsonrpc": "2.0", "id": mid, "result": result})
    except Exception as e:  # noqa: BLE001
        _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})


def cmd_serve(_a):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


# ============================================================ instruction blocks
START, END = "<!-- agentmem:start -->", "<!-- agentmem:end -->"


def instruction_block(project=None) -> str:
    proj = (f"Memory project for this repo: `{project}` (pass it as the `project` argument if a tool "
            f"cannot detect it).\n\n") if project else ""
    return f"""{START}
## Shared project memory (MCP server `agent-memory`)

{proj}1. **Before starting a task**, call `start_task` with a one-line description. Read the returned context, open tasks, recent decisions and relevant notes, and follow existing decisions unless the user says otherwise. Check project docs (`list_dir` / `read_file`, e.g. `docs/`) before assuming how things work.
2. **While working**, call `search_memory` before guessing about project history or conventions.
3. **When the task is done** (or the session is ending), call `finish_task` with a short summary, decisions made (with the reason), durable facts learned (commands, conventions, gotchas) and next steps. Keep entries short and factual.
4. Never store secrets (tokens, passwords, keys) in memory.
5. If the memory tools are unavailable, continue the task normally and tell the user.
{END}
"""


_BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)


def upsert_block(path: Path, block: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text("utf-8") if path.exists() else ""
    if _BLOCK_RE.search(text):
        text = _BLOCK_RE.sub(lambda m: block, text, count=1)
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block
    path.write_text(text, "utf-8")


def remove_block(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text("utf-8")
    if not _BLOCK_RE.search(text):
        return False
    text = _BLOCK_RE.sub("", text).strip()
    if text:
        path.write_text(text + "\n", "utf-8")
    else:
        path.unlink()
    return True


# ============================================================ per-agent setup
def entry() -> dict:
    return {"command": PY, "args": [str(installed_path()), "serve"]}


def load_json(path: Path) -> dict:
    if not path.exists() or not path.read_text("utf-8").strip():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError(f"{path} is not plain JSON (comments?). Add the entry manually: "
                           f'"agent-memory": {json.dumps(entry())}')


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_name(path.name + ".agentmem.bak")
    if path.exists() and not bak.exists():
        shutil.copy2(path, bak)
    path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")


def json_server(path: Path, add: bool, key="mcpServers") -> bool:
    data = load_json(path)
    servers = data.setdefault(key, {})
    if add:
        servers["agent-memory"] = entry()
    elif "agent-memory" in servers:
        del servers["agent-memory"]
    else:
        return False
    save_json(path, data)
    return True


def which_any(*names):
    return any(shutil.which(n) for n in names)


# ---- Claude Code
def claude_hook(add: bool):
    p = home() / ".claude" / "settings.json"
    if not add and not p.exists():
        return
    data = load_json(p)
    hooks = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    hooks[:] = [h for h in hooks
                if not any("agentmem.py" in x.get("command", "") for x in h.get("hooks", []))]
    if add:
        hooks.append({"hooks": [{"type": "command", "command": f'"{PY}" "{installed_path()}" hook'}]})
    if not hooks:
        del data["hooks"]["SessionStart"]
        if not data["hooks"]:
            del data["hooks"]
    save_json(p, data)


def setup_claude(hooks=False):
    out = []
    claude = shutil.which("claude")
    cmd = [str(claude or "claude"), "mcp", "add", "--scope", "user", "agent-memory", "--",
           PY, str(installed_path()), "serve"]
    if claude:
        subprocess.run([claude, "mcp", "remove", "agent-memory", "--scope", "user"], capture_output=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        out.append("MCP server added (user scope)" if r.returncode == 0
                   else f"could not run `claude mcp add` ({r.stderr.strip()[:120]}). Run manually:\n    " + " ".join(cmd))
    else:
        out.append("`claude` not on PATH. Run manually:\n    " + " ".join(cmd))
    upsert_block(home() / ".claude" / "CLAUDE.md", instruction_block())
    out.append("global instructions -> ~/.claude/CLAUDE.md")
    if hooks:
        claude_hook(True)
        out.append("SessionStart hook added (context auto-injected at session start)")
    return out


def remove_claude():
    claude = shutil.which("claude")
    if claude:
        subprocess.run([claude, "mcp", "remove", "agent-memory", "--scope", "user"], capture_output=True)
    remove_block(home() / ".claude" / "CLAUDE.md")
    claude_hook(False)


# ---- Codex CLI
CX_S, CX_E = "# agentmem:start", "# agentmem:end"


def _strip_toml(text: str) -> str:
    return re.sub(rf"\n?{re.escape(CX_S)}.*?{re.escape(CX_E)}\n?", "\n", text, flags=re.S).strip()


def setup_codex(hooks=False):
    cfg = home() / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    text = cfg.read_text("utf-8") if cfg.exists() else ""
    text = _strip_toml(text)
    out = []
    if re.search(r'^\[mcp_servers\.("?)agent-memory\1\]', text, re.M):
        out.append("[mcp_servers.agent-memory] already exists in config.toml (not touched)")
    else:
        block = (f"{CX_S}\n[mcp_servers.agent-memory]\ncommand = {json.dumps(PY)}\n"
                 f"args = [{json.dumps(str(installed_path()))}, \"serve\"]\nstartup_timeout_sec = 20\n{CX_E}\n")
        if cfg.exists() and not cfg.with_name("config.toml.agentmem.bak").exists():
            shutil.copy2(cfg, cfg.with_name("config.toml.agentmem.bak"))
        cfg.write_text((text + "\n\n" if text else "") + block, "utf-8")
        out.append("MCP server added -> ~/.codex/config.toml")
    upsert_block(home() / ".codex" / "AGENTS.md", instruction_block())
    out.append("global instructions -> ~/.codex/AGENTS.md")
    return out


def remove_codex():
    cfg = home() / ".codex" / "config.toml"
    if cfg.exists():
        t = _strip_toml(cfg.read_text("utf-8"))
        cfg.write_text(t + "\n" if t else "", "utf-8")
    remove_block(home() / ".codex" / "AGENTS.md")


# ---- Gemini CLI
def setup_gemini(hooks=False):
    json_server(home() / ".gemini" / "settings.json", True)
    upsert_block(home() / ".gemini" / "GEMINI.md", instruction_block())
    return ["MCP server added -> ~/.gemini/settings.json", "global instructions -> ~/.gemini/GEMINI.md"]


def remove_gemini():
    json_server(home() / ".gemini" / "settings.json", False)
    remove_block(home() / ".gemini" / "GEMINI.md")


# ---- Antigravity (agy CLI + IDE)
def setup_antigravity(hooks=False):
    json_server(home() / ".gemini" / "config" / "mcp_config.json", True)
    upsert_block(home() / ".gemini" / "GEMINI.md", instruction_block())
    return ["MCP server added -> ~/.gemini/config/mcp_config.json (shared by agy CLI and IDE)",
            "instructions -> ~/.gemini/GEMINI.md (also run `init` per repo to write AGENTS.md)"]


def remove_antigravity():
    json_server(home() / ".gemini" / "config" / "mcp_config.json", False)


# ---- Cursor
def setup_cursor(hooks=False):
    json_server(home() / ".cursor" / "mcp.json", True)
    return ["MCP server added -> ~/.cursor/mcp.json",
            "Cursor has no global rules file: run `init` per repo (writes AGENTS.md)"]


def remove_cursor():
    json_server(home() / ".cursor" / "mcp.json", False)


AGENTS = {
    "claude":      ("Claude Code", lambda: which_any("claude") or (home() / ".claude").is_dir(), setup_claude, remove_claude),
    "codex":       ("Codex CLI", lambda: which_any("codex") or (home() / ".codex").is_dir(), setup_codex, remove_codex),
    "gemini":      ("Gemini CLI", lambda: which_any("gemini"), setup_gemini, remove_gemini),
    "antigravity": ("Antigravity (agy)", lambda: which_any("agy", "antigravity") or (home() / ".gemini" / "config").is_dir()
                    or (home() / ".gemini" / "antigravity").is_dir(), setup_antigravity, remove_antigravity),
    "cursor":      ("Cursor", lambda: which_any("cursor") or (home() / ".cursor").is_dir(), setup_cursor, remove_cursor),
}


# ============================================================ CLI commands
def cmd_install(a):
    cfg = load_config()
    url = a.url or cfg.get("url") or (input("Memory server URL [http://localhost:8080]: ").strip() or "http://localhost:8080")
    token = a.token or cfg.get("token") or getpass.getpass("Agent token: ").strip()
    try:
        api("GET", "/projects", cfg={"url": url, "token": token})
        print(f"[ok] connected to {url}")
    except ApiError as e:
        print(f"[!] could not verify server: {e}")
        if not a.skip_verify:
            print("    Fix the URL/token, or use --skip-verify to install anyway.")
            sys.exit(1)
    app_dir().mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve()
    if src != installed_path().resolve():
        shutil.copy2(src, installed_path())
    os.chmod(installed_path(), 0o755)
    save_config(url, token)
    print(f"[ok] plugin installed at {installed_path()} (token stored in {app_dir()/'config.json'}, mode 600)")

    if a.agents == "auto":
        names = [n for n, (_, det, _, _) in AGENTS.items() if det()]
        if not names:
            print("[!] no agents detected. Use --agents all or --agents claude,codex,...")
    elif a.agents == "all":
        names = list(AGENTS)
    else:
        names = [n.strip() for n in a.agents.split(",") if n.strip()]
    for n in names:
        if n not in AGENTS:
            print(f"[!] unknown agent '{n}' (choose from {', '.join(AGENTS)})")
            continue
        label, _, setup, _ = AGENTS[n]
        print(f"\n{label}")
        try:
            for line in setup(hooks=a.hooks):
                print(f"  - {line}")
        except Exception as e:  # noqa: BLE001
            print(f"  [!] failed: {e}")
    print("\nNext: restart your agents, then in each repo run:\n"
          f"  {PY} {installed_path()} init")


def cmd_uninstall(a):
    for n, (label, _, _, remove) in AGENTS.items():
        try:
            remove()
            print(f"[ok] removed from {label}")
        except Exception as e:  # noqa: BLE001
            print(f"[!] {label}: {e}")
    if a.purge and app_dir().exists():
        shutil.rmtree(app_dir())
        print(f"[ok] deleted {app_dir()}")


def cmd_init(a):
    root = Path(a.dir).resolve() if a.dir else (git_root(Path.cwd()) or Path.cwd())
    os.chdir(root)
    existing, _ = find_binding(root)
    name = a.project or existing or slugify(root.name)
    created = ensure_project(name, a.template)
    (root / ".agentmem.json").write_text(json.dumps({"project": name}, indent=2) + "\n", "utf-8")
    print(f"[ok] project '{name}' {'created' if created else 'already exists'} on the server")
    print(f"[ok] wrote {root/'.agentmem.json'} (safe to commit; contains no secrets)")
    if not a.no_files:
        for fn in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            upsert_block(root / fn, instruction_block(name))
            print(f"[ok] instructions -> {fn}")


def cmd_status(_a):
    cfg = load_config()
    print(f"agentmem {VERSION}")
    print(f"plugin file : {installed_path()} ({'present' if installed_path().exists() else 'MISSING'})")
    tok = cfg.get("token", "")
    print(f"server      : {cfg.get('url', '(not set)')}  token: {tok[:4] + '...' if tok else '(not set)'}")
    try:
        n = len(api("GET", "/projects").get("projects", []))
        print(f"connection  : ok ({n} projects visible)")
    except ApiError as e:
        print(f"connection  : FAILED - {e}")
    checks = {
        "claude": home() / ".claude" / "CLAUDE.md",
        "codex": home() / ".codex" / "config.toml",
        "gemini": home() / ".gemini" / "settings.json",
        "antigravity": home() / ".gemini" / "config" / "mcp_config.json",
        "cursor": home() / ".cursor" / "mcp.json",
    }
    for n, f in checks.items():
        txt = f.read_text("utf-8") if f.exists() else ""
        ok = ("agentmem" in txt) if n in ("claude", "codex") else ("agent-memory" in txt)
        print(f"{AGENTS[n][0]:<18}: {'configured' if ok else 'not configured'}"
              f"{'' if AGENTS[n][1]() else ' (agent not detected)'}")
    p, how = resolve_project()
    print(f"this folder : project '{p}' (from {how})")


def render_context(project=None) -> str:
    p, _ = resolve_project(project)
    ctx = api("GET", f"/projects/{p}/context")
    return (f"[agent-memory] project `{p}`\n\n## Project context\n{ctx.get('context', '').strip()}\n\n"
            f"## Open tasks\n{ctx.get('tasks', '').strip()}\n\n## Recent decisions\n"
            f"{ctx.get('recent_decisions', '').strip()}\n\n"
            "Call start_task before working and finish_task when done.")


def cmd_context(a):
    print(render_context(a.project))


def cmd_hook(_a):
    """Claude Code SessionStart hook: print context to stdout. Never fails the session."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if payload.get("cwd") and Path(payload["cwd"]).is_dir():
            os.chdir(payload["cwd"])
        p, how = resolve_project()
        if how.startswith("folder name") and not git_root(Path.cwd()):
            return  # not obviously a project folder
        print(render_context())
    except Exception:  # noqa: BLE001
        pass


def cmd_search(a):
    print(json.dumps(search_memory(a.query, project=a.project), indent=2))


def cmd_save(a):
    print(json.dumps(save_memory(a.type, a.text, project=a.project), indent=2))


def main():
    ap = argparse.ArgumentParser(prog="agentmem", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("install", help="configure agents + store server URL/token")
    s.add_argument("--url"); s.add_argument("--token")
    s.add_argument("--agents", default="auto", help="auto | all | claude,codex,gemini,antigravity,cursor")
    s.add_argument("--hooks", action="store_true", help="Claude Code: auto-inject context at session start")
    s.add_argument("--skip-verify", action="store_true")
    s.set_defaults(fn=cmd_install)
    s = sub.add_parser("uninstall"); s.add_argument("--purge", action="store_true", help="also delete ~/.agentmem")
    s.set_defaults(fn=cmd_uninstall)
    s = sub.add_parser("init", help="bind current repo to a memory project")
    s.add_argument("--project"); s.add_argument("--template", default="default")
    s.add_argument("--dir"); s.add_argument("--no-files", action="store_true")
    s.set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("serve", help="run as MCP stdio server").set_defaults(fn=cmd_serve)
    sub.add_parser("hook").set_defaults(fn=cmd_hook)
    s = sub.add_parser("context"); s.add_argument("--project"); s.set_defaults(fn=cmd_context)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--project"); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("save"); s.add_argument("type"); s.add_argument("text"); s.add_argument("--project")
    s.set_defaults(fn=cmd_save)
    a = ap.parse_args()
    try:
        a.fn(a)
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
