---
name: personal-status
description: Inspect a personal-agent research run and report current state
---

# personal-status

## Workflow

1. Use run id.
2. Execute:
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/memories?run_id=<id>&subtype=research_run&limit=1"`
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/memories?run_id=<id>&subtype=research_source&limit=200"`
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/memories?run_id=<id>&subtype=research_claim&limit=200"`
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks?status=open&limit=200"` (filter by `metadata.run_id == <id>` for open tasks)
3. Summarize:
   - goal
   - status
   - source count
   - claim count
   - open tasks / gaps
