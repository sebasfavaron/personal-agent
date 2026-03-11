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
4. Persist using:
   - `python3 scripts/personal.py --json tasks intake --goal "<goal>" --scope "<scope>" --assumptions "<assumptions>" --clarifications '<json-array>' --research-notes '<json-array>' --parent-task "<parent>" --subtasks '<json-array>'`
5. If deeper work remains, also create or update a research run with sources and claims.

## Rules

- do not store vague tasks if needed clarifications are still missing
- if no online research was needed, record that explicitly in `research-notes`
- if the user already answered clarifications earlier in the thread, use them and record them
