# Agent Memory Server

One shared memory + project file manager for all your coding agents.
FastAPI + Postgres/pgvector + git, with an MCP client that plugs into Claude Code, Gemini CLI, etc.

## Run

```bash
cp .env.example .env            # edit the two secrets
docker compose up -d --build
# Ensure host Ollama has the embedding model:
# ollama pull nomic-embed-text
curl localhost:8080/health
```

## Create an agent token (admin token from .env)

```bash
curl -s localhost:8080/admin/agents -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"claude-code","permissions":[{"project":"*","role":"write"}]}'
# per-project read-only example: {"name":"reviewer","permissions":[{"project":"myapp","role":"read"}]}
```

## Try it

```bash
H="Authorization: Bearer <agent-token>"
curl -s localhost:8080/projects -H "$H" -H "Content-Type: application/json" \
  -d '{"name":"myapp","template":"python"}'
curl -s -X PUT localhost:8080/projects/myapp/file -H "$H" -H "Content-Type: application/json" \
  -d '{"path":"docs/design.md","content":"# Design\nWe use Postgres for metadata."}'
curl -s localhost:8080/projects/myapp/search -H "$H" -H "Content-Type: application/json" \
  -d '{"query":"which database do we use"}'
```

## Plug into agents (MCP)

```bash
pip install -r client/requirements.txt

# Claude Code
claude mcp add agent-memory -e MEMORY_API_URL=http://localhost:8080 \
  -e MEMORY_API_TOKEN=<agent-token> -- python /path/to/client/mcp_client.py
```

Gemini CLI (`~/.gemini/settings.json`):
```json
{ "mcpServers": { "agent-memory": {
    "command": "python", "args": ["/path/to/client/mcp_client.py"],
    "env": { "MEMORY_API_URL": "http://localhost:8080", "MEMORY_API_TOKEN": "<agent-token>" } } } }
```

Tip: add to each agent's instructions file (CLAUDE.md / GEMINI.md):
"At session start call get_project_context. Save decisions with save_memory."

## Notes
- Files live in the `memdata` volume at `/data/projects/<name>/` (real folders, one git repo each).
- Hash map = `files` table (path -> sha256 -> version). Unchanged content is skipped; unchanged chunks keep their embeddings.
- Locks use Postgres advisory locks (no Redis needed yet). Indexing runs as background tasks in the API process.
- If you change `EMBED_MODEL` to one with a different dimension, set `EMBED_DIM` and recreate the `chunks` table.
- Keep the API on localhost / VPN. Never expose it publicly without TLS.
