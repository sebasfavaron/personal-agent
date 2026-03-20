# System V1

`personal-agent` V1 is the front door for the local agent system.

## Topology

- `personal-agent`
  - daemon
  - dashboard at `127.0.0.1:8082`
  - intake draft + cwd confirmation + direct Codex launch
- `agents-database`
  - canonical shared state
  - `shared-agent-memory.sqlite3`
  - memory service
  - operational tables for tasks, task runs, artifacts
- `ballbox-company-agent`
  - company/domain subagent
- `ai-dev-workflow`
  - code/repo subagent
- `codex`
  - direct execution backend for one task per spawned run
- GitHub
  - public persistence for repo changes and V1 cross-references

## Critical Paths

- `~/personal-agent`
- `~/agents-database`
- `~/ballbox-company-agent`
- `~/ai-dev-workflow`
- `~/agents-database/data/shared-agent-memory.sqlite3`
- `~/ai-dev-workflow/.agents/local-config.json`
- `~/.codex/skills`

## What Lives Where

### Versioned repos

- orchestration code, daemon, dashboard, CLI: `personal-agent`
- canonical shared-memory implementation and schema: `agents-database`
- company-specific operating shell and subagent entrypoint: `ballbox-company-agent`
- code workflow shell and subagent entrypoint: `ai-dev-workflow`

### Durable local state

- shared durable memory and operational task state:
  - `~/agents-database/data/shared-agent-memory.sqlite3`

### Local config / machine-specific state

- repo path mapping for code workflows:
  - `~/ai-dev-workflow/.agents/local-config.json`
- active feature contexts, when present:
  - `~/ai-dev-workflow/.agents/feature-contexts/`
- Codex skill symlinks:
  - `~/.codex/skills`
- Codex writable-extra-dir convention for `personal-agent`:
  - launch with `--add-dir ~/agents-database` so sandboxed `codex exec` can write the canonical shared DB in place

### Shared-only state

- all current personal-agent persistence lives in:
  - `~/agents-database/data/shared-agent-memory.sqlite3`

Compatibility behavior:

- new operational work lands in `agents-database`
- research/leisure/legacy CLI flows now also land in `agents-database`
- `personal-agent` can still inspect old mirrored shared-memory run records when present

## Recreate On A New Machine

1. Install prerequisites.
   - Python 3.11+
   - Git
   - Codex CLI
   - GitHub CLI if using `ai-dev-workflow`
2. Recreate sibling layout under `~`.
   - clone `personal-agent`
   - clone `agents-database`
   - clone `ballbox-company-agent`
   - clone `ai-dev-workflow`
3. Restore durable state.
   - copy `shared-agent-memory.sqlite3` into `~/agents-database/data/`
4. Restore local config.
   - copy `~/ai-dev-workflow/.agents/local-config.json`
   - copy any active `feature-contexts/` if needed
5. Reinstall skills.
   - run `~/personal-agent/scripts/install-skills.sh`
6. Verify shared memory import path.
   - `python3 ~/personal-agent/scripts/personal.py status --json`
7. Start the daemon.
   - `python3 ~/personal-agent/scripts/personal.py daemon`
8. Open the dashboard.
   - `http://127.0.0.1:8082`

Operator note:

- daemon is long-running
- this agent can start, stop, or restart it across sessions
- canonical UI endpoint: `http://127.0.0.1:8082/`
- canonical status endpoint: `http://127.0.0.1:8082/api/status`

## Validation Checklist

- `personal-agent` status command returns dashboard JSON
- `personal.py` accepts `--json` before or after subcommands
- dashboard loads at `:8082`
- shared DB contains tasks, runs, artifacts
- draft tasks must not launch until the human confirms or edits the inferred cwd
- `codex exec` is available on PATH

## Recovery / Backup

Minimum backup set:

- all four git repos
- `~/agents-database/data/shared-agent-memory.sqlite3`
- `~/ai-dev-workflow/.agents/local-config.json`
- active `feature-contexts/` if they matter

## V1 Notes

- intake infers a repo/cwd, but the UI exposes it for confirmation before launch
- each accepted task spawns its own `codex exec` process from the chosen cwd
- the default execution mode is `danger-full-access`
- Python persists task state, task runs, stdout/stderr paths, and the final markdown artifact
- status surfaces expose `draft_tasks`, `active_runs`, `failed_tasks`, and `recent_results`
