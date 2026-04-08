---
name: personal-approval-queue
description: Review pending high-risk external actions that require human approval
---

# personal-approval-queue

## Workflow

1. To inspect pending actions:
   - `curl -fsSL "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks?requires_human_input=true&limit=200"`
   - Filter results where `kind == "approval_request"` or `metadata.approval` exists.
2. To queue a blocked action:
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"title\":\"Approval: <summary>\",\"intent\":\"<summary>\",\"kind\":\"approval_request\",\"status\":\"blocked\",\"requires_human_input\":true,\"metadata\":{\"approval\":{\"kind\":\"<email|contact|purchase|other>\",\"risk_level\":\"<low|medium|high>\",\"payload\":{\"summary\":\"<summary>\"},\"status\":\"pending\",\"requested_at\":\"<iso-8601>\"}}}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks"`
   - Use `date -u "+%Y-%m-%dT%H:%M:%SZ"` for `requested_at`.
3. Never perform the action directly from this skill.
