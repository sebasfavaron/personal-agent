# System V1

`personal-agent` V1 is the front door for the local agent system.

## Topology

- `personal-agent`
  - daemon
  - event worker
  - dashboard at `127.0.0.1:6666`
  - intake, blockers, orchestration
- `agents-database`
  - canonical shared state
  - `shared-agent-memory.sqlite3`
  - memory service
  - operational tables for tasks, task runs, approvals, artifacts, handoffs
- `ballbox-company-agent`
  - company/domain subagent
- `ai-dev-workflow`
  - code/repo subagent
- `codex`
  - planning backend for intake/orchestration
  - execution backend for personal-agent worker in read-only report mode
- GitHub
  - public persistence for repo changes and V1 cross-references

## Critical Paths

- `~/Code/personal-agent`
- `~/Code/agents-database`
- `~/Code/ballbox-company-agent`
- `~/Code/ai-dev-workflow`
- `~/Code/agents-database/data/shared-agent-memory.sqlite3`
- `~/Code/ai-dev-workflow/.agents/local-config.json`
- `~/.codex/skills`

## What Lives Where

### Versioned repos

- orchestration code, daemon, dashboard, CLI: `personal-agent`
- canonical shared-memory implementation and schema: `agents-database`
- company-specific operating shell and subagent entrypoint: `ballbox-company-agent`
- code workflow shell and subagent entrypoint: `ai-dev-workflow`

### Durable local state

- shared durable memory and operational task state:
  - `~/Code/agents-database/data/shared-agent-memory.sqlite3`

### Local config / machine-specific state

- repo path mapping for code workflows:
  - `~/Code/ai-dev-workflow/.agents/local-config.json`
- active feature contexts, when present:
  - `~/Code/ai-dev-workflow/.agents/feature-contexts/`
- Codex skill symlinks:
  - `~/.codex/skills`
- Codex writable-extra-dir convention for `personal-agent`:
  - launch with `--add-dir ~/agents-database` so sandboxed `codex exec` can write the canonical shared DB in place

### Legacy transitional state

- pre-V1 personal-agent sqlite:
  - `~/Code/personal-agent/data/personal-agent.sqlite3`

Keep only for migration and audit while V1 stabilizes.

Transition behavior:

- new operational work must land in `agents-database`
- legacy runs can still be inspected through `personal-agent` because mirrored run summaries/claims/sources are readable from shared DB
- local sqlite is not allowed back in as the durable source of truth for new tasks, handoffs, approvals, or artifacts

## Recreate On A New Machine

1. Install prerequisites.
   - Python 3.11+
   - Git
   - Codex CLI
   - GitHub CLI if using `ai-dev-workflow`
2. Recreate sibling layout under `~/Code`.
   - clone `personal-agent`
   - clone `agents-database`
   - clone `ballbox-company-agent`
   - clone `ai-dev-workflow`
3. Restore durable state.
   - copy `shared-agent-memory.sqlite3` into `~/Code/agents-database/data/`
4. Restore local config.
   - copy `~/Code/ai-dev-workflow/.agents/local-config.json`
   - copy any active `feature-contexts/` if needed
5. Reinstall skills.
   - run `~/Code/personal-agent/scripts/install-skills.sh`
6. Verify shared memory import path.
   - `python3 ~/Code/personal-agent/scripts/personal.py status --json`
7. Start the daemon.
   - `python3 ~/Code/personal-agent/scripts/personal.py daemon`
8. Open the dashboard.
   - `http://127.0.0.1:6666`

## Validation Checklist

- `personal-agent` status command returns dashboard JSON
- `personal.py` accepts `--json` before or after subcommands
- dashboard loads at `:6666`
- shared DB contains tasks, runs, artifacts, handoffs
- `ai-dev-workflow` `run-task` returns accepted JSON
- `ballbox-company-agent` `run-task` returns accepted JSON
- `codex exec` is available on PATH

## Recovery / Backup

Minimum backup set:

- all four git repos
- `~/Code/agents-database/data/shared-agent-memory.sqlite3`
- `~/Code/ai-dev-workflow/.agents/local-config.json`
- active `feature-contexts/` if they matter
- optional legacy `personal-agent/data/personal-agent.sqlite3`

## V1 Notes

- blockers should resolve from memory before asking the human when possible
- intake routing/subtask planning should prefer Codex and fall back to local heuristics if Codex is unavailable
- personal-agent worker uses `codex exec` to return structured outcomes: complete, blocked, or needs_approval
- Python applies those outcomes to shared DB state, artifacts, task runs, and approval records
- personal-agent worker also passes `--add-dir ~/agents-database` so shared DB writes remain available inside the sandbox when needed
- status surfaces expose `summary`, `next_action`, `latest_run`, `pending_approval`, `open_subtask_count`, and `route_summary`
- specialist repos are invoked through a stable `run-task` subagent contract
