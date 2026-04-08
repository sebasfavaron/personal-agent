---
name: personal-memory-search
description: Search persisted research memory, claims, and tasks
---

# personal-memory-search

## Workflow

1. Execute:
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/search?q=<query>&scope=global&scope=project&limit=20"`
2. Return matching runs, claims, and tasks from the JSON response.
3. Prefer reuse of prior work before starting a new run.
