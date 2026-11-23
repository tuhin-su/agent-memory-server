# Rule: Memory Protocol

Every agent working on this system must maintain persistent shared memory.

## 1. Task Lifecycle
- **Before starting any task**: Call `start_task(task="...")` on the `agent-memory` MCP server (or check `GET /projects/{project}/context`).
- Review returned `context`, `open_tasks`, `recent_decisions`, and `relevant_notes`.
- **While working**: Never guess about project conventions or historical choices; use `search_memory`.
- **When task is completed**: Call `finish_task` providing a concise summary, key decisions made, and durable facts learned.

## 2. Secrets Prohibition
- Never write secrets, passwords, tokens, or private keys to memory notes or project files.
