---
name: personal-task-intake
description: Turn a vague request into a persisted task plan after clarifications and brief research
---

# personal-task-intake

## Use When

- the user gives a goal, not a finished task plan
- ambiguity matters
- current external facts matter

## Required Workflow

1. Ask clarifying questions first when ambiguity changes scope, cost, risk, or success criteria.
2. If the task depends on current external facts, do a short online research pass before saving work.
3. Convert the request into:
   - one parent task
   - 3-7 concrete subtasks
   - clarification notes
   - research notes
4. Persist parent + subtasks using the tasks API:
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"title\":\"<goal>\",\"intent\":\"<goal>\",\"status\":\"open\",\"kind\":\"task_plan\",\"metadata\":{\"clarifications\":<json-array>,\"research_notes\":<json-array>,\"assumptions\":\"<assumptions>\"}}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks"`
   - For each subtask, use the returned parent task id:
     `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"title\":\"<subtask>\",\"intent\":\"<subtask>\",\"status\":\"open\",\"kind\":\"task\",\"parent_task_id\":\"<parent_task_id>\"}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks"`
5. If deeper work remains, also create or update a research run with sources and claims.

## Rules

- do not store vague tasks if needed clarifications are still missing
- if no online research was needed, record that explicitly in `research_notes`
- if the user already answered clarifications earlier in the thread, use them and record them
