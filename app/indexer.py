import logging
from pathlib import Path

import numpy as np

from . import db
from .chunker import chunk_text
from .embeddings import embed
from .files import project_root, sha256

log = logging.getLogger("indexer")

TEXT_EXT = {
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".html", ".css", ".sql", ".sh", ".csv", ".xml", ".go", ".rs",
    ".java", ".c", ".h", ".cpp", ".rb", ".php",
}
DOC_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg"}
ALL_INDEXABLE = TEXT_EXT | DOC_EXT | IMAGE_EXT


def extract_text_content(target_path: Path, rel: str) -> str:
    ext = target_path.suffix.lower()
    if ext in DOC_EXT:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(target_path))
            pages = []
            for idx, page in enumerate(reader.pages, start=1):
                txt = (page.extract_text() or "").strip()
                if txt:
                    pages.append(f"[{rel} - Page {idx}]\n{txt}")
            return "\n\n".join(pages)
        except Exception as e:
            log.warning("PDF extraction failed for %s: %s", rel, e)
            return ""
    elif ext in IMAGE_EXT:
        try:
            from PIL import Image
            lines = [f"[Image: {rel}]"]
            with Image.open(target_path) as img:
                lines.append(f"Format: {img.format}, Dimensions: {img.width}x{img.height}, Mode: {img.mode}")
                exif = img.getexif()
                if exif:
                    tags = [f"{k}: {str(v)[:60]}" for k, v in list(exif.items())[:10]]
                    if tags:
                        lines.append("EXIF: " + ", ".join(tags))
            for sidecar in [target_path.with_name(target_path.name + ".txt"), target_path.with_name(target_path.name + ".md")]:
                if sidecar.is_file():
                    lines.append("Description: " + sidecar.read_text("utf-8", errors="replace")[:1000])
                    break
            return "\n".join(lines)
        except Exception as e:
            log.warning("Image extraction failed for %s: %s", rel, e)
            return f"[Image: {rel}]"
    else:
        try:
            return target_path.read_text("utf-8", errors="replace")
        except Exception as e:
            log.warning("Text read failed for %s: %s", rel, e)
            return ""


def index_file(project: str, rel: str):
    """Chunk + embed one file. Chunks whose hash didn't change keep their embedding."""
    root = project_root(project)
    target = root / rel
    with db.pool.connection() as conn:
        f = conn.execute(
            "SELECT id, sha256, indexed_sha256 FROM files WHERE project=%s AND path=%s",
            (project, rel),
        ).fetchone()
        if not f or f["indexed_sha256"] == f["sha256"]:
            return
        ext = Path(rel).suffix.lower()
        if ext not in ALL_INDEXABLE or not target.is_file():
            conn.execute("UPDATE files SET indexed_sha256=sha256 WHERE id=%s", (f["id"],))
            return
        text = extract_text_content(target, rel)
        if not text.strip():
            conn.execute("UPDATE files SET indexed_sha256=sha256 WHERE id=%s", (f["id"],))
            return
        existing = {
            r["sha256"]: r["embedding"]
            for r in conn.execute("SELECT sha256, embedding FROM chunks WHERE file_id=%s", (f["id"],))
        }

    chunks = chunk_text(text)
    hashes = [sha256(c.encode()) for c in chunks]
    missing = [i for i, h in enumerate(hashes) if existing.get(h) is None]
    new_embs = embed([chunks[i] for i in missing]) if missing else []
    emb_for: dict[int, object] = {}
    if new_embs:
        for i, e in zip(missing, new_embs):
            emb_for[i] = np.array(e, dtype=np.float32)

    rows = []
    for i, (c, h) in enumerate(zip(chunks, hashes)):
        rows.append((f["id"], i, c, h, existing.get(h) if existing.get(h) is not None else emb_for.get(i)))

    with db.pool.connection() as conn:
        cur = conn.execute("SELECT sha256 FROM files WHERE id=%s", (f["id"],)).fetchone()
        if not cur or cur["sha256"] != f["sha256"]:
            return  # file changed again; a newer index task will handle it
        conn.execute("DELETE FROM chunks WHERE file_id=%s", (f["id"],))
        with conn.cursor() as c:
            c.executemany(
                "INSERT INTO chunks(file_id, idx, text, sha256, embedding) VALUES (%s,%s,%s,%s,%s)", rows
            )
        conn.execute("UPDATE files SET indexed_sha256=%s WHERE id=%s", (f["sha256"], f["id"]))
    log.info("indexed %s/%s (%d chunks, %d embedded)", project, rel, len(rows), len(missing))


def search(project: str, query: str, limit: int = 8) -> list[dict]:
    """Hybrid search: vector similarity + keyword (full-text), merged with reciprocal rank fusion."""
    qe = embed([query])
    k = 60
    scores: dict[tuple, float] = {}
    info: dict[tuple, dict] = {}
    with db.pool.connection() as conn:
        if qe:
            rows = conn.execute(
                """SELECT f.path, c.idx, c.text FROM chunks c JOIN files f ON f.id=c.file_id
                   WHERE f.project=%s AND c.embedding IS NOT NULL
                   ORDER BY c.embedding <=> %s LIMIT %s""",
                (project, np.array(qe[0], dtype=np.float32), limit * 3),
            ).fetchall()
            for rank, r in enumerate(rows):
                key = (r["path"], r["idx"])
                scores[key] = scores.get(key, 0) + 1 / (k + rank)
                info[key] = r
        rows = conn.execute(
            """SELECT f.path, c.idx, c.text FROM chunks c JOIN files f ON f.id=c.file_id
               WHERE f.project=%s AND c.tsv @@ websearch_to_tsquery('english', %s)
               ORDER BY ts_rank(c.tsv, websearch_to_tsquery('english', %s)) DESC LIMIT %s""",
            (project, query, query, limit * 3),
        ).fetchall()
        for rank, r in enumerate(rows):
            key = (r["path"], r["idx"])
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            info[key] = r
    best = sorted(scores, key=scores.get, reverse=True)[:limit]
    return [
        {"path": key[0], "chunk": key[1], "score": round(scores[key], 4),
         "text": info[key]["text"][:600], "mode": "hybrid" if qe else "keyword"}
        for key in best
    ]
