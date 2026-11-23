# Memory Server — Large-Scale Production Issues

> [!CAUTION]
> This codebase is designed as a **single-node developer tool**. At production scale (many concurrent agents, many projects, millions of files) the following issues will cause failures, data loss, or unacceptable latency.

---

## 🔴 Critical — Will Break Under Load

### 1. Single Admin Token in Plain Environment Variable (`auth.py:25`, `config.py:7`)

```python
if hmac.compare_digest(token.encode(), settings.admin_token.encode()):
    return Agent("admin", True)
```

- One hardcoded, never-rotating superuser token with **no scope, no expiry, no revocation**.
- If leaked (logs, crash dumps, `ps aux`), the entire server is compromised forever.
- No MFA, no IP allowlisting, no token rotation mechanism.
- **Fix:** Move to short-lived JWT / API-key-per-consumer; store token hash in DB; add rotation endpoint.

---

### 2. No Rate Limiting / Throttling Anywhere (`main.py`)

Every endpoint — `search`, `write_file`, `save_memory` — is completely unbounded:
- A rogue agent can flood `POST /projects/{project}/search` with embedding calls, saturating Ollama **and** the DB.
- `POST /projects/{project}/memory` with tiny writes triggers a git commit + background re-index each time.
- No per-IP, per-agent, or global concurrency limits.
- **Fix:** Add FastAPI middleware (e.g., `slowapi`) with per-agent rate limits; queue or debounce indexing.

---

### 3. Background Indexing Is Fire-and-Forget with No Queue (`main.py:98,136`, `indexer.py`)

```python
bg.add_task(indexer.index_file, project, rel)
```

- FastAPI `BackgroundTasks` runs in-process on the **Uvicorn worker** — not a task queue.
- Under a burst write scenario, thousands of `index_file` calls pile up **in memory** in a single process.
- Each `index_file` call holds a DB connection and calls the external Ollama HTTP API (120 s timeout!) — extremely resource heavy.
- If the process restarts, all queued tasks are **silently lost**; files remain un-indexed with no retry.
- **Fix:** Use Celery/ARQ/Redis Queue or at minimum a persistent work queue. Implement exponential backoff + dead-letter handling.

---

### 4. DB Connection Pool Hardcoded at max 10 (`db.py:81`)

```python
pool = ConnectionPool(..., min_size=1, max_size=10, ...)
```

- With horizontal scaling (multiple Uvicorn workers or replicas), each replica opens its own pool → DB quickly exhausted.
- FastAPI default workers on a 4-core machine = 4 processes × 10 conns = 40 connections even before background tasks.
- **Fix:** Add PgBouncer in front; expose `DB_POOL_MAX` as an env var; integrate with `UVICORN_WORKERS`.

---

### 5. Synchronous `subprocess.run` (git) Inside a Request (`files.py:67-77`)

```python
def _git(root: Path, *args, check=True):
    return subprocess.run(["git", ...], cwd=root, ...)
```

`_commit()` is called inside **every** `write_file`, `delete_file`, and `move_file` within a live DB transaction:
- Blocks the **entire Uvicorn async loop** (this is a sync function called from async FastAPI routes).
- Git operations on large repos or slow disks can take 100–500 ms+, multiplied by all concurrent requests.
- If git hangs (e.g., lock contention, NFS mount), the DB transaction lock (`pg_advisory_xact_lock`) is **held the entire time**, blocking all other writers to that project.
- **Fix:** Run git asynchronously (use `asyncio.create_subprocess_exec`) or move git commits to the background queue.

---

### 6. `pg_advisory_xact_lock(hashtext(...))` Hash Collisions (`files.py:74,113`)

```python
conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"file:{project}:{rel_norm}",))
```

- `hashtext()` returns a 32-bit integer — with **~65,000 files** across projects you hit a 50% chance of collision (Birthday Problem).
- A collision means two **unrelated files** in different projects block each other, creating phantom contention.
- **Fix:** Use `pg_advisory_xact_lock(bigint, bigint)` with two 32-bit hashes, or switch to `sha256` truncated to 64 bits.

---

## 🟠 High — Will Cause Problems at Scale

### 7. No Horizontal Scalability (Stateful Filesystem + In-Process State)

The server mixes **filesystem state** (`/data/projects/`) with **database state**:
- Project files live on a single Docker volume (`memdata`). Multiple replicas cannot share it without NFS/distributed FS.
- The `pool` global is per-process — there is no shared worker-pool awareness.
- Git repos are local directories — no mechanism to sync them across replicas.
- **Fix:** Decouple file storage to object storage (S3/GCS); use git bare remotes or a Git hosting API.

---

### 8. `audit_log` Table Has No Retention / Archival Policy (`db.py:58-65`)

```python
CREATE TABLE IF NOT EXISTS audit_log (
    id bigserial PRIMARY KEY, at timestamptz, ...
)
```

- Unbounded append-only table with **no index on `at`** and no TTL.
- At 1,000 writes/day across 100 agents = 36.5 M rows/year with no cleanup.
- Queries against it (e.g., future compliance tooling) will do full scans.
- **Fix:** Add `CREATE INDEX ON audit_log(at)`, add a partitioning strategy (pg_partman) or a nightly archival job.

---

### 9. HNSW Index Requires Manual Rebuild After Schema Changes (`db.py:56`)

```python
CREATE INDEX IF NOT EXISTS chunks_emb ON chunks USING hnsw (embedding vector_cosine_ops);
```

- `CREATE INDEX IF NOT EXISTS` only creates the index once. If `EMBED_DIM` is later changed in `.env`, the **vector column dimension stays the same** (the schema `CREATE TABLE IF NOT EXISTS` is also idempotent — existing tables are never altered).
- Changing model → dim mismatch error at embed time (`embeddings.py:26-27`).
- No migration framework; schema is applied raw in `init_db()`.
- **Fix:** Use Alembic (or at minimum a versioned migration script); validate `embed_dim` against the live DB column type at startup.

---

### 10. Blocking Synchronous HTTP to Ollama in Async Context (`embeddings.py:19`)

```python
r = httpx.post(f"{settings.ollama_url}/api/embed", ..., timeout=120)
```

- Uses **`httpx` synchronous** client inside `indexer.index_file`, which is called by FastAPI `BackgroundTasks` running in the async event loop thread.
- A 120 s timeout means a stalled Ollama can freeze background tasks for 2 minutes **per file**.
- **Fix:** Use `httpx.AsyncClient` with `await`; or run embedding in a thread pool executor (`asyncio.to_thread`).

---

### 11. `tree()` Returns All Files in One Query with No Pagination (`files.py:188-194`)

```python
return conn.execute(
    "SELECT path, size, version, sha256 FROM files WHERE project=%s ORDER BY path",
    (project,),
).fetchall()
```

- With 100k files in a project this returns a multi-MB JSON payload with no limit.
- Also called inside `get_project_context()` and truncated to 200 entries — but the **full DB query still runs**.
- **Fix:** Add `LIMIT`/`OFFSET` or keyset pagination; push the `[:200]` slice into the SQL query.

---

### 12. No Observability / Structured Logging

- No request tracing (no correlation IDs, no OpenTelemetry spans).
- `log.warning("embedding unavailable: %s", e)` swallows all embedding errors silently.
- No metrics (Prometheus/Grafana) for indexing lag, DB pool saturation, error rates.
- **Fix:** Add `structlog` or standard JSON logging; expose `/metrics` with Prometheus middleware; wire OpenTelemetry.

---

## 🟡 Medium — Technical Debt that Compounds at Scale

### 13. Token Hashing Uses Plain SHA-256 (`auth.py:21`)

```python
return hashlib.sha256(token.encode()).hexdigest()
```

- Tokens are high-entropy (`secrets.token_urlsafe(32)`) so the risk is low, but plain SHA-256 is not a password KDF.
- If the DB is dumped, offline brute-force is fast.
- **Fix:** Use `bcrypt` or `argon2` for token storage; or use HMAC with a server-side secret.

---

### 14. No Chunk Deduplication Across Projects

- The same document indexed in two projects stores two full copies of chunks + embeddings in `chunks`.
- At scale this wastes significant PG storage and embedding API calls.
- **Fix:** Content-address chunks by `sha256`; share embeddings across projects via a `chunk_store` table.

---

### 15. `get_project_context` Tail-Slices In Python, Not SQL (`files.py:264-277`)

```python
c[-tail:]  # slices after reading entire file into Python
```

- Reads the entire `decisions.md` / `tasks.md` into memory then slices. For large memory files this wastes I/O.
- **Fix:** Use `pg_read_file` or SQL `RIGHT(content, n)` — or just apply `LIMIT` by byte offset.

---

## Summary Table

| # | Area | Severity | Impact |
|---|------|----------|--------|
| 1 | Single admin token, no rotation | 🔴 Critical | Full server takeover if leaked |
| 2 | No rate limiting | 🔴 Critical | DoS / resource exhaustion |
| 3 | Fire-and-forget background indexing | 🔴 Critical | Silent data loss on restart |
| 4 | DB pool hardcoded at 10 | 🔴 Critical | Connection exhaustion on scale-out |
| 5 | Blocking git in async request | 🔴 Critical | Event loop stall, cascading locks |
| 6 | 32-bit advisory lock hash collisions | 🔴 Critical | Phantom deadlocks at ~65k files |
| 7 | Filesystem-bound, not horizontally scalable | 🟠 High | Cannot add replicas |
| 8 | Unbounded audit_log, no index | 🟠 High | Full scans, storage growth |
| 9 | No DB migration framework | 🟠 High | Schema drift on embed_dim change |
| 10 | Sync HTTP to Ollama in async context | 🟠 High | 120s event loop stalls |
| 11 | tree() fetches all rows, no pagination | 🟠 High | OOM on large projects |
| 12 | No observability | 🟠 High | Blind in production |
| 13 | SHA-256 token storage | 🟡 Medium | Brute-forceable offline |
| 14 | No cross-project chunk deduplication | 🟡 Medium | Storage bloat |
| 15 | Python-side file tail slicing | 🟡 Medium | Wasted I/O |
