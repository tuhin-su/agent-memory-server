"""MCP plugin for the Agent Memory Server.

Works with any MCP-capable agent (Claude Code, Gemini CLI, ...). It is a thin wrapper:
every tool calls the server's REST API, so the server can live on another machine.

Env: MEMORY_API_URL (default http://localhost:8080), MEMORY_API_TOKEN (required)
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("MEMORY_API_URL", "http://localhost:8080")
TOKEN = os.environ["MEMORY_API_TOKEN"]

mcp = FastMCP("agent-memory")
http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)


def _call(method: str, url: str, **kw):
    r = http.request(method, url, **kw)
    if r.status_code >= 400:
        try:
            msg = r.json().get("error") or r.json().get("detail")
        except Exception:  # noqa: BLE001
            msg = r.text
        raise RuntimeError(f"{r.status_code}: {msg}")
    return r.json()


@mcp.tool()
def list_projects() -> dict:
    """List projects this agent can access."""
    return _call("GET", "/projects")


@mcp.tool()
def create_project(name: str, template: str = "default") -> dict:
    """Create a project with standard folders. Templates: default, python, web, research."""
    return _call("POST", "/projects", json={"name": name, "template": template})


@mcp.tool()
def get_project_context(project: str) -> dict:
    """START HERE in a new session: returns summary, tasks, recent decisions and file list."""
    return _call("GET", f"/projects/{project}/context")


@mcp.tool()
def list_dir(project: str, path: str = "") -> dict:
    """List a directory inside a project."""
    return _call("GET", f"/projects/{project}/files", params={"path": path})


@mcp.tool()
def read_file(project: str, path: str, rev: str | None = None) -> dict:
    """Read a text file (optionally at a git revision). Returns sha256 for safe edits."""
    return _call("GET", f"/projects/{project}/file", params={"path": path, "rev": rev})


@mcp.tool()
def write_file(project: str, path: str, content: str,
               expected_sha256: str | None = None, append: bool = False) -> dict:
    """Create/overwrite (or append to) a file. Pass expected_sha256 from read_file to avoid
    overwriting someone else's changes."""
    return _call("PUT", f"/projects/{project}/file", json={
        "path": path, "content": content, "expected_sha256": expected_sha256, "append": append})


@mcp.tool()
def move_file(project: str, src: str, dst: str) -> dict:
    """Move/rename a file."""
    return _call("POST", f"/projects/{project}/move", json={"src": src, "dst": dst})


@mcp.tool()
def delete_file(project: str, path: str) -> dict:
    """Delete a file (still recoverable from git history)."""
    return _call("DELETE", f"/projects/{project}/file", params={"path": path})


@mcp.tool()
def file_history(project: str, path: str) -> dict:
    """Git history of a file (use a returned rev with read_file to see an old version)."""
    return _call("GET", f"/projects/{project}/history", params={"path": path})


@mcp.tool()
def search_memory(project: str, query: str, limit: int = 8) -> dict:
    """Semantic + keyword search across all indexed files of a project."""
    return _call("POST", f"/projects/{project}/search", json={"query": query, "limit": limit})


@mcp.tool()
def save_memory(project: str, type: str, text: str) -> dict:
    """Save durable knowledge. type: decision | task | fact | note | context (context replaces
    the project summary)."""
    return _call("POST", f"/projects/{project}/memory", json={"type": type, "text": text})


if __name__ == "__main__":
    mcp.run()  # stdio transport
