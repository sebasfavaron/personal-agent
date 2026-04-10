# ballbox

Ballbox company agent knowledge namespace.

Primary memory lives in shared Ballbox memory. Files here are the operating shell around that memory.

This namespace is a specialist, not the default front door. Normal entry should start in `~/personal-agent`, which can route Ballbox requests here.

## Layout

- `index.md`: root dashboard
- `what-goes-where.md`: file vs DB policy
- `.self/`: mission, values, principles
- `.cycle/`: cycle plans and reviews
- `.inbox/`: raw internal inputs
- `.tasks/`: working TODOs
- `strategy/`: positioning, maxims, reviews
- `signals/`: raw observations
- `worldview/`: hypotheses and beliefs
- `projects/`: active workstreams
- `SOP/`: step-by-step operating procedures
- `scripts/ballbox_company_agent.py`: shared-memory + dashboard CLI

## Shared memory

Memory access:

- prefer the shared memory service / configured Ballbox memory path
- fallback discovery can still check `~/agents-database`

Canonical rule:

- use the shared memory service / configured memory location instead of hardcoding a single sqlite path in docs

- search: memory-service first
- search fallback: direct sqlite read if the environment blocks `retrieval_logs` writes
- add-note: real memory-service ingest
- delegate: when the request smells like repo/code work, hand it off to `~/ai-dev-workflow`

Policy:

- durable memory in DB
- active operating loop in files

## Usage

```bash
python3 scripts/ballbox_company_agent.py dashboard
python3 scripts/ballbox_company_agent.py snapshot
python3 scripts/ballbox_company_agent.py search --query "Ballbox pilots pricing"
python3 scripts/ballbox_company_agent.py add-note \
  --title "Ballbox pilot question" \
  --content "Still missing current pilot clubs and commercial terms." \
  --type task_hint \
  --scope project
python3 scripts/ballbox_company_agent.py delegate \
  --input "Ballbox necesita fix en repo de pagos y abrir branch para QR" \
  --repo-hint ballbox-payment-integration
```
