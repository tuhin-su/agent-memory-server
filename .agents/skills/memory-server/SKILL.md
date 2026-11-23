---
name: memory-server
description: >-
  Use this skill when working with the memory-server project: starting or
  stopping services, writing files, searching memory, managing projects or
  agents, debugging CORS/docker issues, or understanding the API. Provides
  the full runbook for operating and developing the memory-server and its
  web UI dashboard.
---

# Memory Server — Agent Runbook

## Project Overview

A FastAPI + PostgreSQL (pgvector) agent memory server with hybrid search (vector + keyword).
Ships with a standalone web UI dashboard (`memory-ui/`).

```
memory-server/
├── app/              # FastAPI application
│   ├── main.py       # Routes, CORS middleware
│   ├── auth.py       # Token auth, permissions
│   ├── db.py         # psycopg3 pool, schema (pgvector)
│   ├── files.py      # File CRUD + git commits
│   ├── indexer.py    # Chunk + embed + RRF search
│   ├── embeddings.py # Ollama HTTP client
│   ├── chunker.py    # Paragraph-aware chunker
│   ├── security.py   # Path traversal guard
│   └── config.py     # Settings from env
├── memory-ui/        # Standalone web dashboard (port 5055)
│   ├── index.html    # SPA: Chart.js graphs + search UI
│   ├── server.py     # stdlib HTTP server
│   ├── start.sh      # Manual start
│   └── stop.sh       # Manual stop
├── docker-compose.yml
├── Dockerfile
├── .env              # Secrets — never commit
└── .env.example      # Commit this instead
```

---

## Starting & Stopping

### Memory Server (Docker)
```bash
# Start
docker compose up -d

# Stop
docker compose down

# REBUILD after any app/ code change (restart alone won't work!)
docker compose up -d --build api

# Logs
docker compose logs -f api
```

### Web UI (manual)
```bash
./memory-ui/start.sh        # start in background → http://localhost:5055
./memory-ui/stop.sh         # stop

# Or foreground (Ctrl+C to stop)
python3 memory-ui/server.py

# Custom port
UI_PORT=8888 python3 memory-ui/server.py
```

---

## REST API Quick Reference

Base URL: `http://localhost:${API_PORT:-8080}`
Auth: `Authorization: Bearer <token>`

### Health
```
GET /health
```

### Admin: Create Agent
```bash
curl -X POST /admin/agents \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"myagent","is_admin":false,"permissions":[{"project":"*","role":"write"}]}'
# → returns token ONCE — save it immediately
```

### Projects
```bash
POST /projects          # create project  body: {name, template}
GET  /projects          # list accessible projects
GET  /projects/{p}/context   # full project context (memory + file list)
GET  /projects/{p}/tree      # all files with size + version
```

### Files (Text, PDF, Images, Binary)
```bash
# Read file (auto-detects text vs binary)
GET    /projects/{p}/file?path=docs/README.md

# Write text/markdown/code
PUT    /projects/{p}/file
body: {"path": "docs/architecture.md", "content": "# Architecture..."}

# Write binary (PDF, images, spreadsheets) via base64
PUT    /projects/{p}/file
body: {"path": "docs/manual.pdf", "content_b64": "<base64-string>"}

DELETE /projects/{p}/file?path=...                      # delete
POST   /projects/{p}/move   body: {src, dst}            # move/rename
GET    /projects/{p}/history?path=...                   # git log for file
```

### Search (Vector-First Protocol: Low Token, High Quality)
```bash
POST /projects/{p}/search
body: {"query": "invoice total amount", "limit": 5}
```
Returns top ranked chunks:
- `path`: target file (e.g. `docs/manual.pdf` or `docs/spec.md`)
- `chunk`: chunk index
- `score`: similarity score
- `text`: concise excerpt (e.g. `[docs/manual.pdf - Page 3] Total: $4,500`)
- `mode`: `hybrid` or `keyword`

**Always search first**: Evaluate chunk text to answer user queries with minimal token usage. Only read the full raw file if the chunk is insufficient.

### Save Memory
```bash
POST /projects/{p}/memory
body: {"type": "decision"|"task"|"fact"|"note"|"context", "text": "..."}
```
| type | file |
|------|------|
| context | memory/context.md (overwrites) |
| decision | memory/decisions.md (appends) |
| task | memory/tasks.md (appends) |
| fact | memory/facts.md (appends) |
| note | memory/notes.md (appends) |

---

## Embedding Setup

### With Ollama (default)
```bash
# Pull embedding model on host
ollama pull nomic-embed-text

# .env
EMBED_PROVIDER=ollama
OLLAMA_URL=http://host.docker.internal:11434
EMBED_MODEL=nomic-embed-text
EMBED_DIM=768
```

### Disable embeddings (keyword-only search)
```env
EMBED_PROVIDER=none
```

### Change model — IMPORTANT
If you change `EMBED_MODEL` you MUST also update `EMBED_DIM` to match.
Then drop and recreate the chunks table (or wipe the DB volume) because
the vector column dimension is fixed at schema creation time.

---

## Common Troubleshooting

### CORS blocked in browser
```bash
# Verify header is present after rebuild
curl -si http://localhost:8080/health -H "Origin: http://localhost:5055" | grep access-control
# Should show: access-control-allow-origin: *
```
If missing → code change wasn't picked up. Run: `docker compose up -d --build api`

### API not responding
```bash
docker compose ps          # check containers are Up
docker compose logs api    # look for startup errors
```

### Embeddings not working / search returns no vector results
```bash
# Test Ollama directly
curl http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text","input":["test"]}'
# Check EMBED_DIM matches model output
```

### Port conflict
```env
# .env — change and rebuild
API_PORT=9090
```

---

## Development Workflow

1. Edit files in `app/`
2. `docker compose up -d --build api`
3. `curl http://localhost:8080/health` — confirm `{"ok":true}`
4. Test your change
5. `git add ... && git commit -m "..."`

> See [references/production-issues.md](./references/production-issues.md) for all 15 known production-scale issues.
