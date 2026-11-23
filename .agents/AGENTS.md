# Agent Memory Server — Modular Rules System

Welcome agent. Rules in this repository are **modularized** across `.agents/rules/`. Do not assume or guess: search, inspect, and apply the specific rule matching your task.

## 🧭 Core Axioms (Read First)

1. **Memory First**: Always execute `start_task` on `agent-memory` before starting, and `finish_task` before ending.
2. **Vector First (Low Token, Max Quality)**: **Always search vector chunks first** (`search_memory` or `POST /search`) before reading entire files, PDFs, or images. Never load 50-page documents blindly into context. Use the chunk's page citation and targeted snippet to answer accurately while consuming 95% fewer tokens.
3. **Model Read/Write Authority**: You (the AI model) have full authority to search, read, modify, and create any rule in `.agents/rules/` and any skill in `.agents/skills/`. Keep them up to date as the project evolves.

---

## 📂 Modular Rule Directory (`.agents/rules/`)

| Rule File | Scope & Topic |
|---|---|
| [01-memory-protocol.md](file:///home/nic/Downloads/memory-server/.agents/rules/01-memory-protocol.md) | Task lifecycle, start/finish protocol, context checking |
| [02-vector-first-retrieval.md](file:///home/nic/Downloads/memory-server/.agents/rules/02-vector-first-retrieval.md) | Token-efficient vector search protocol before file access |
| [03-model-rw-rules-skills.md](file:///home/nic/Downloads/memory-server/.agents/rules/03-model-rw-rules-skills.md) | Model permissions to read, write, and update rules & skills |
| [04-docker-lifecycle.md](file:///home/nic/Downloads/memory-server/.agents/rules/04-docker-lifecycle.md) | Mandatory `docker compose up -d --build api`, CORS checks |
| [05-multi-modal-storage.md](file:///home/nic/Downloads/memory-server/.agents/rules/05-multi-modal-storage.md) | Storing and indexing PDFs, images, code, and text via base64 |
| [06-security-and-advisory-locks.md](file:///home/nic/Downloads/memory-server/.agents/rules/06-security-and-advisory-locks.md) | Path safety, `.env` security, 32-bit advisory lock collision risk |

---

## 🛠 Skills & Runbooks

- **Memory Server Runbook**: [.agents/skills/memory-server/SKILL.md](file:///home/nic/Downloads/memory-server/.agents/skills/memory-server/SKILL.md)
- **Production Scaling Analysis**: [.agents/skills/memory-server/references/production-issues.md](file:///home/nic/Downloads/memory-server/.agents/skills/memory-server/references/production-issues.md)
