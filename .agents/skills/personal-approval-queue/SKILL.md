---
name: personal-approval-queue
description: Review pending high-risk external actions that require human approval
---

# personal-approval-queue

## Workflow

1. To inspect pending actions:
   - `scripts/run.sh list`
2. To queue a blocked action:
   - `scripts/run.sh request --kind "<email|contact|purchase|other>" --risk-level "<low|medium|high>" --payload '{"summary":"..."}'`
3. Never perform the action directly from this skill.
