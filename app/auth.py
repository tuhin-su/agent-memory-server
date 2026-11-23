import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from . import db
from .config import settings

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$")
RANK = {"read": 1, "write": 2}


@dataclass
class Agent:
    name: str
    is_admin: bool


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(token: str) -> Agent | None:
    if hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        return Agent("admin", True)
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT name, is_admin FROM agents WHERE token_hash=%s", (_hash(token),)
        ).fetchone()
    return Agent(row["name"], row["is_admin"]) if row else None


def require_admin(agent: Agent):
    if not agent.is_admin:
        raise PermissionError("admin only")


def require(agent: Agent, project: str, role: str):
    if agent.is_admin:
        return
    with db.pool.connection() as conn:
        rows = conn.execute(
            "SELECT role FROM permissions WHERE agent=%s AND project IN (%s, '*')",
            (agent.name, project),
        ).fetchall()
    if not any(RANK[r["role"]] >= RANK[role] for r in rows):
        raise PermissionError(f"agent '{agent.name}' needs {role} access to '{project}'")


def accessible_projects(agent: Agent) -> list[str]:
    with db.pool.connection() as conn:
        if agent.is_admin:
            return [r["name"] for r in conn.execute("SELECT name FROM projects ORDER BY name")]
        perms = [r["project"] for r in conn.execute(
            "SELECT project FROM permissions WHERE agent=%s", (agent.name,))]
        if "*" in perms:
            return [r["name"] for r in conn.execute("SELECT name FROM projects ORDER BY name")]
        return [r["name"] for r in conn.execute(
            "SELECT name FROM projects WHERE name = ANY(%s) ORDER BY name", (perms,))]


def create_agent(name: str, is_admin: bool, permissions: list[dict]) -> dict:
    if not NAME_RE.match(name):
        raise ValueError("invalid agent name")
    token = secrets.token_urlsafe(32)
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM agents WHERE name=%s", (name,)).fetchone():
            raise ValueError("agent already exists")
        conn.execute(
            "INSERT INTO agents(name, token_hash, is_admin) VALUES (%s,%s,%s)",
            (name, _hash(token), is_admin),
        )
        for p in permissions:
            conn.execute(
                "INSERT INTO permissions(agent, project, role) VALUES (%s,%s,%s)",
                (name, p["project"], p["role"]),
            )
    return {"name": name, "token": token, "note": "Save this token now; it is not stored."}
