import re
from pathlib import Path

PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
HIDDEN_TOP = {".git", ".meta"}


def valid_project_name(name: str) -> bool:
    return bool(PROJECT_RE.match(name)) and ".." not in name


def safe_path(root: Path, rel: str, allow_root: bool = False) -> Path:
    """Resolve rel inside root. Blocks absolute paths, '..', symlink escapes and .git/.meta."""
    rel = (rel or "").strip()
    if rel in ("", ".", "/"):
        if allow_root:
            return root.resolve()
        raise ValueError("path required")
    if "\x00" in rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise ValueError("invalid path")
    root_r = root.resolve()
    target = (root_r / rel).resolve()
    if target != root_r and root_r not in target.parents:
        raise ValueError("path escapes project folder")
    parts = target.relative_to(root_r).parts
    if parts and parts[0] in HIDDEN_TOP:
        raise ValueError("path is reserved")
    return target
