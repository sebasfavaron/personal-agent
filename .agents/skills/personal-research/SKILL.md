---
name: personal-research
description: Run a personal research workflow with local memory persistence and explicit source capture
---

# personal-research

## Use When

- web research
- source collection
- claim tracking
- structured follow-up tasks

## Workflow

1. Clarify goal only if ambiguity changes scope or risk.
2. Start a run:
   - `scripts/run.sh start --goal "<goal>" --scope "<scope>" --assumptions "<defaults>"`
3. Research with web/browser tools.
4. For each meaningful source:
   - `scripts/run.sh add-source --run-id "<id>" --url "<url>" --title "<title>" --notes "<why it matters>"`
5. For each meaningful finding:
   - `scripts/run.sh add-claim --run-id "<id>" --claim "<claim>" --confidence "<0-1>" --status "<tentative|verified|contradicted>" --source-url "<url>"`
6. Add follow-up tasks when useful:
   - `scripts/run.sh add-task --run-id "<id>" --task "<next action>"`
7. Close when enough evidence exists:
   - `scripts/run.sh close --run-id "<id>" --summary "<short conclusion + gaps>"`
8. Return:
   - short executive summary
   - key claims with confidence
   - gaps / next actions
   - source links

## Rules

- do not fabricate sources
- mark weak evidence explicitly
- outreach or external action => send to approval queue, never execute
