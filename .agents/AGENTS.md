# Memory Server Project Rules

These rules apply to ALL agents working in this repository. Read and follow them every session.

## 1. Always Use Agent Memory MCP First

Before starting ANY task:
- Call `start_task` on the `agent-memory` MCP server with a one-line description.
- Read the returned `context`, `open_tasks`, `recent_decisions`, and `relevant_notes`.
- When done, call `finish_task` with a summary, decisions made, and next steps.

## 2. Docker: Rebuild on Code Changes

> [!CAUTION]
> `docker compose restart` does NOT reload code. The app is baked into the image.

**Always use this after editing anything in `app/`:**
```bash
docker compose up -d --build api
```

## 3. Verify CORS After Rebuild

After rebuilding, confirm CORS headers are live:
```bash
curl -si http://localhost:8080/health -H "Origin: http://localhost:5055" | grep access-control
# Must return: access-control-allow-origin: *
```

## 4. Memory UI is a Separate App

- The web dashboard lives in `memory-ui/` — it is NOT part of the FastAPI server.
- Start it manually: `./memory-ui/start.sh` → opens at http://localhost:5055
- Stop it: `./memory-ui/stop.sh`
- Do NOT auto-start the UI from docker-compose.

## 5. Env Vars Control Everything

All runtime config lives in `.env`. Key vars:
| Var | Default | Purpose |
|-----|---------|---------|
| `API_HOST` | `0.0.0.0` | Uvicorn bind host |
| `API_PORT` | `8080` | Uvicorn bind port |
| `ADMIN_TOKEN` | *(required)* | Superuser token |
| `EMBED_PROVIDER` | `ollama` | `ollama` or `none` |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `EMBED_DIM` | `768` | Must match model output dim |

After editing `.env` → always rebuild: `docker compose up -d --build api`

## 6. Never Commit `.env`

`.env` contains secrets. It is gitignored. Only commit `.env.example`.

## 7. Path Safety Rules

All file paths go through `security.safe_path()`. Never bypass it.
- No absolute paths, no `..`, no access to `.git/` or `.meta/`
- Project names: lowercase, `a-z 0-9 . _ -` only

## 8. Advisory Lock Hash Collision Risk

`pg_advisory_xact_lock(hashtext(...))` uses a **32-bit hash** — collision risk grows above ~65k files. If the project scales beyond that, migrate to `pg_advisory_xact_lock(bigint, bigint)` with two separate hash components.
