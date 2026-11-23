import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .config import settings
from .security import HIDDEN_TOP, safe_path, valid_project_name


class ConflictError(Exception):
    pass


TEMPLATES = {
    "default":  ["docs", "src", "memory", "logs"],
    "python":   ["docs", "src", "tests", "memory", "logs", "data"],
    "web":      ["docs", "src", "public", "tests", "memory", "logs"],
    "research": ["docs", "sources", "notes", "memory", "logs"],
}

MEMORY_FILES = {
    "decision": "memory/decisions.md",
    "task":     "memory/tasks.md",
    "fact":     "memory/facts.md",
    "note":     "memory/notes.md",
}

INITIAL_FILES = {
    "memory/context.md":   "# Project context\n\n(Current state summary. Agents update this with save_memory type=context.)\n",
    "memory/decisions.md": "# Decisions\n\nWhy choices were made.\n",
    "memory/tasks.md":     "# Tasks\n",
    "docs/README.md":      "# Project documents\n",
}


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def project_root(name: str) -> Path:
    if not valid_project_name(name):
        raise ValueError("invalid project name (use a-z, 0-9, '.', '_', '-')")
    return settings.data_dir / "projects" / name


def _ensure_project(name: str) -> Path:
    root = project_root(name)
    with db.pool.connection() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise FileNotFoundError(f"project not found: {name}")
    return root


def _audit(conn, agent, action, project, path=None):
    conn.execute(
        "INSERT INTO audit_log(agent, action, project, path) VALUES (%s,%s,%s,%s)",
        (agent, action, project, path),
    )


# ---------- git ----------
def _git(root: Path, *args, check=True):
    return subprocess.run(
        ["git", "-c", "user.name=memory-server", "-c", "user.email=memory@localhost", *args],
        cwd=root, check=check, capture_output=True, text=True,
    )


def _commit(conn, project: str, root: Path, msg: str):
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"git:{project}",))
    _git(root, "add", "-A")
    if _git(root, "status", "--porcelain").stdout.strip():
        _git(root, "commit", "-q", "-m", msg)


# ---------- projects ----------
def create_project(name: str, template: str, agent: str) -> dict:
    root = project_root(name)
    folders = TEMPLATES.get(template)
    if folders is None:
        raise ValueError(f"unknown template; choose from {sorted(TEMPLATES)}")
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise ConflictError("project already exists")
        conn.execute("INSERT INTO projects(name, template) VALUES (%s,%s)", (name, template))
        for f in folders + [".meta"]:
            (root / f).mkdir(parents=True, exist_ok=True)
        (root / ".meta" / "project.json").write_text(json.dumps({
            "name": name, "template": template, "created_by": agent,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        _git(root, "init", "-q", "-b", "main")
        _audit(conn, agent, "create_project", name)
    written = []
    for rel, body in INITIAL_FILES.items():
        if rel.split("/")[0] in folders:
            write_file(name, rel, body, agent)
            written.append(rel)
    return {"project": name, "template": template, "folders": folders, "files": written}


# ---------- files ----------
def write_file(project, rel, content, agent, expected_sha256=None, append=False) -> dict:
    root = _ensure_project(project)
    target = safe_path(root, rel)
    rel_norm = target.relative_to(root.resolve()).as_posix()
    with db.pool.connection() as conn:
        # Per-file lock: two agents can't interleave on the same file.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"file:{project}:{rel_norm}",))
        row = conn.execute(
            "SELECT id, sha256, version FROM files WHERE project=%s AND path=%s",
            (project, rel_norm),
        ).fetchone()
        if expected_sha256 and (row is None or row["sha256"] != expected_sha256):
            raise ConflictError("file changed since you read it (sha256 mismatch); re-read and retry")
        if append and target.is_file():
            data = target.read_bytes() + content.encode()
        else:
            data = content.encode()
        if len(data) > settings.max_file_bytes:
            raise ValueError("file too large")
        new_hash = sha256(data)
        if row and row["sha256"] == new_hash:
            return {"path": rel_norm, "sha256": new_hash, "version": row["version"], "changed": False}
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        res = conn.execute(
            """INSERT INTO files(project, path, sha256, size, updated_by)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (project, path) DO UPDATE
               SET sha256=EXCLUDED.sha256, size=EXCLUDED.size, version=files.version+1,
                   updated_by=EXCLUDED.updated_by, updated_at=now()
               RETURNING version""",
            (project, rel_norm, new_hash, len(data), agent),
        ).fetchone()
        _commit(conn, project, root, f"{agent}: write {rel_norm}")
        _audit(conn, agent, "write", project, rel_norm)
    return {"path": rel_norm, "sha256": new_hash, "version": res["version"], "changed": True}


def read_file(project, rel, rev=None) -> dict:
    root = _ensure_project(project)
    target = safe_path(root, rel)
    rel_norm = target.relative_to(root.resolve()).as_posix()
    if rev:
        if not re.fullmatch(r"[0-9a-f]{4,40}", rev):
            raise ValueError("invalid revision")
        r = _git(root, "show", f"{rev}:{rel_norm}", check=False)
        if r.returncode != 0:
            raise FileNotFoundError("file/revision not found")
        return {"path": rel_norm, "content": r.stdout, "rev": rev}
    if not target.is_file():
        raise FileNotFoundError(f"no such file: {rel_norm}")
    data = target.read_bytes()
    if len(data) > settings.max_file_bytes:
        raise ValueError("file too large to read")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("binary file")
    return {"path": rel_norm, "content": text, "sha256": sha256(data)}


def list_dir(project, rel="") -> dict:
    root = _ensure_project(project)
    target = safe_path(root, rel, allow_root=True)
    if not target.is_dir():
        raise FileNotFoundError("no such directory")
    root_r = root.resolve()
    entries = []
    for p in sorted(target.iterdir()):
        if target == root_r and p.name in HIDDEN_TOP:
            continue
        entries.append({
            "name": p.name,
            "type": "dir" if p.is_dir() else "file",
            "size": p.stat().st_size if p.is_file() else None,
        })
    return {"path": target.relative_to(root_r).as_posix(), "entries": entries}


def tree(project) -> list[dict]:
    _ensure_project(project)
    with db.pool.connection() as conn:
        return conn.execute(
            "SELECT path, size, version, sha256 FROM files WHERE project=%s ORDER BY path",
            (project,),
        ).fetchall()


def move_file(project, src, dst, agent) -> dict:
    root = _ensure_project(project)
    s, d = safe_path(root, src), safe_path(root, dst)
    root_r = root.resolve()
    s_rel, d_rel = s.relative_to(root_r).as_posix(), d.relative_to(root_r).as_posix()
    with db.pool.connection() as conn:
        for key in sorted([s_rel, d_rel]):  # sorted order avoids deadlocks
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"file:{project}:{key}",))
        if not s.is_file():
            raise FileNotFoundError(f"no such file: {s_rel}")
        if d.exists():
            raise ConflictError(f"destination exists: {d_rel}")
        d.parent.mkdir(parents=True, exist_ok=True)
        os.rename(s, d)
        conn.execute(
            "UPDATE files SET path=%s, version=version+1, updated_by=%s, updated_at=now() "
            "WHERE project=%s AND path=%s",
            (d_rel, agent, project, s_rel),
        )
        _commit(conn, project, root, f"{agent}: move {s_rel} -> {d_rel}")
        _audit(conn, agent, "move", project, f"{s_rel} -> {d_rel}")
    return {"moved": s_rel, "to": d_rel}


def delete_file(project, rel, agent) -> dict:
    root = _ensure_project(project)
    target = safe_path(root, rel)
    rel_norm = target.relative_to(root.resolve()).as_posix()
    with db.pool.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"file:{project}:{rel_norm}",))
        if not target.is_file():
            raise FileNotFoundError(f"no such file: {rel_norm}")
        target.unlink()
        conn.execute("DELETE FROM files WHERE project=%s AND path=%s", (project, rel_norm))
        _commit(conn, project, root, f"{agent}: delete {rel_norm}")  # recoverable from git
        _audit(conn, agent, "delete", project, rel_norm)
    return {"deleted": rel_norm}


def file_history(project, rel, limit=20) -> list[dict]:
    root = _ensure_project(project)
    target = safe_path(root, rel)
    rel_norm = target.relative_to(root.resolve()).as_posix()
    r = _git(root, "log", "--follow", f"-n{int(limit)}", "--format=%h%x09%aI%x09%s", "--", rel_norm, check=False)
    out = []
    for line in r.stdout.splitlines():
        rev, date, msg = line.split("\t", 2)
        out.append({"rev": rev, "date": date, "message": msg})
    return out


# ---------- memory ----------
def save_memory(project, mtype, text, agent) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = text.strip()
    if not text:
        raise ValueError("text required")
    if mtype == "context":
        body = f"# Project context\n\n_Updated {ts} by {agent}_\n\n{text}\n"
        return write_file(project, "memory/context.md", body, agent)
    rel = MEMORY_FILES.get(mtype)
    if not rel:
        raise ValueError(f"type must be one of {['context', *MEMORY_FILES]}")
    return write_file(project, rel, f"\n## {ts} ({agent})\n{text}\n", agent, append=True)


def get_project_context(project) -> dict:
    """Everything a fresh agent needs to get started, in one call."""
    def _read(rel, tail=None):
        try:
            c = read_file(project, rel)["content"]
            return c[-tail:] if tail else c
        except FileNotFoundError:
            return ""
    return {
        "project": project,
        "context": _read("memory/context.md"),
        "tasks": _read("memory/tasks.md", 3000),
        "recent_decisions": _read("memory/decisions.md", 3000),
        "files": [f["path"] for f in tree(project)][:200],
    }
