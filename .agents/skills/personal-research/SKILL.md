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
2. Start a run (pick a run id):
   - `RUN_ID="run_$(date -u +%Y%m%d%H%M%S)"`
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"id\":\"mem_${RUN_ID}\",\"type\":\"episode\",\"subtype\":\"research_run\",\"scope\":\"global\",\"run_id\":\"${RUN_ID}\",\"title\":\"Research run: <goal>\",\"content\":\"Goal: <goal>\\nScope: <scope>\\nAssumptions: <assumptions>\\nSummary: <summary>\",\"metadata\":{\"goal\":\"<goal>\",\"scope\":\"<scope>\",\"assumptions\":\"<assumptions>\",\"run_status\":\"active\"},\"source_kind\":\"manual\",\"source_ref\":\"personal-research:${RUN_ID}\"}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/ingest"`
3. For each source you find, capture it:
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"type\":\"artifact\",\"subtype\":\"research_source\",\"scope\":\"global\",\"run_id\":\"${RUN_ID}\",\"title\":\"<title>\",\"content\":\"<summary>\\n<url>\",\"url\":\"<url>\",\"metadata\":{\"notes\":\"<why it matters>\"},\"source_kind\":\"document\",\"source_ref\":\"personal-research:${RUN_ID}\"}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/ingest"`
4. For each meaningful finding, add a claim:
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"type\":\"artifact\",\"subtype\":\"research_claim\",\"scope\":\"global\",\"run_id\":\"${RUN_ID}\",\"title\":\"Research claim: <short>\",\"content\":\"<claim>\",\"metadata\":{\"claim_status\":\"<tentative|verified|contradicted>\",\"confidence\":\"<0-1>\",\"source_url\":\"<url>\"},\"source_kind\":\"manual\",\"source_ref\":\"personal-research:${RUN_ID}\"}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/ingest"`
5. Add follow-up tasks when useful:
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"title\":\"<task>\",\"intent\":\"<task>\",\"status\":\"open\",\"kind\":\"research_followup\",\"metadata\":{\"run_id\":\"${RUN_ID}\"}}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/tasks"`
6. Close the run (overwrite the run memory with the same id):
   - `curl -fsSL -X POST -H "Content-Type: application/json" \
      -d "{\"id\":\"mem_${RUN_ID}\",\"type\":\"episode\",\"subtype\":\"research_run\",\"scope\":\"global\",\"run_id\":\"${RUN_ID}\",\"title\":\"Research run: <goal>\",\"content\":\"Goal: <goal>\\nScope: <scope>\\nAssumptions: <assumptions>\\nSummary: <summary>\",\"metadata\":{\"goal\":\"<goal>\",\"scope\":\"<scope>\",\"assumptions\":\"<assumptions>\",\"run_status\":\"closed\",\"summary\":\"<short conclusion + gaps>\"},\"source_kind\":\"manual\",\"source_ref\":\"personal-research:${RUN_ID}\"}" \
      "${AGENTS_DB_API:-http://100.116.176.16:8091}/api/ingest"`
7. Return:
   - short executive summary
   - key claims with confidence
   - gaps / next actions
   - source links

## Rules

- do not fabricate sources
- mark weak evidence explicitly
- outreach or external action => send to approval queue, never execute
