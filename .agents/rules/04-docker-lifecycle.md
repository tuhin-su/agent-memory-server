# Rule: Docker Container Lifecycle

## 1. Rebuild on Code Edits
> [!CAUTION]
> The FastAPI application is baked into the Docker image. `docker compose restart` does NOT reload code changes in `app/` or dependency updates in `requirements.txt`.

Always execute:
```bash
docker compose up -d --build api
```

## 2. CORS Verification
After any rebuild, verify that CORS headers are active:
```bash
curl -si http://localhost:8080/health -H "Origin: http://localhost:5055" | grep access-control
# Expected output:
# access-control-allow-origin: *
```

## 3. Web UI is Independent
- The web UI in `memory-ui/` is a separate app with zero npm dependencies.
- Start/stop manually: `./memory-ui/start.sh` or `./memory-ui/stop.sh`.
- Do not add memory-ui to `docker-compose.yml`.
