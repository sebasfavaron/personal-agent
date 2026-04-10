# opencode-harness

Successor to `second-brain`.

Personal research + memory runtime, kept separate from `ai-dev-workflow`.

See [INSTALL.md](INSTALL.md) for setup.

## Principles

- Repo-local ownership for personal capabilities
- Global skill discovery via `~/.agents/skills` (installer copies skills)
- Shared DB in sibling repo `~/agents-database` is the durable source of truth for new work
- Human approval required for outreach / external side effects
- `ai-dev-workflow` stays focused on project workflows

## V1 Front Door

`opencode-harness` now grows toward a front-door runtime:

- daemon + dashboard at `127.0.0.1:8082`
- shared-memory orchestration over `agents-database`
- direct task runner with `draft -> confirm cwd -> launch -> result`
- one runner process per task, launched from the selected repo root
- dashboard/CLI snapshot with drafts, active runs, failed runs, and recent results

System map and machine-recreation guide:

- [docs/system-v1.md](docs/system-v1.md)
- [docs/raycast-codex-notify.md](docs/raycast-codex-notify.md)

## What Exists Today

This repository now contains:

- shared-memory-backed persistence for research runs
- source, claim, task, and approval tracking
- memory search over stored runs, claims, and tasks
- Agent skill wrappers owned by this repo
- task intake persistence with parent tasks and subtasks
- request routing and specialist delegation across personal/company/code contexts
- internal command surface via `python3 scripts/personal.py`
- unit tests for the storage lifecycle

## Shared Memory Integration

Durable shared memory lives in the sibling project at `~/agents-database`.

- research, leisure, approvals, and task intake write directly to shared memory
- `memory-search` reads shared memory directly
- approvals use the native shared-memory approvals table
- `memory-migrate` rewrites legacy opencode-harness metadata into the canonical shared-memory schema
- `research status --run-id <id>` resolves runs from canonical shared-memory records only

Default shared-memory path discovery:

- tries `~/agents-database/src` first
- then falls back to sibling discovery heuristics if the direct path is unavailable
- database defaults to `<shared-memory-root>/data/shared-agent-memory.sqlite3`
- runner binary is configurable; choose the installed CLI that best fits the machine/runtime

These can be overridden with:

- `PERSONAL_AGENT_SHARED_MEMORY_ROOT`
- `PERSONAL_AGENT_SHARED_MEMORY_DB_PATH`
- `PERSONAL_AGENT_RUNNER_BIN`
- `PERSONAL_AGENT_RUNNER_ADD_DIRS`
- `PERSONAL_AGENT_CODEX_ADD_DIRS` remains legacy-compatible env input for add-dir lists

## What Is Still A Promise

These are goals for future work. They are not implemented in the main runner path yet.

- browser automation and live web execution
- email sending or contact workflows
- proactive background daemon / scheduler
- calendar or inbox integrations
- fully autonomous task execution

## Routing Model

`opencode-harness` is the intended front door.

- start here for general requests
- personal context stays here
- code-shaped requests default to `~/ai-dev-workflow` unless the draft cwd is changed before launch
- the main daemon path is now a direct code runner, not a multi-agent orchestrator

## Layout

```text
opencode-harness/
├── .agents/skills/
├── data/
├── personal_agent/
├── scripts/
└── tests/
```

## Internal Commands

Internal command surface only. Not intended as the primary UX for end users.

```bash
python3 scripts/personal.py research start --goal "Investigate X"
python3 scripts/personal.py research search-web --run-id <id> --query "best local-first assistants"
python3 scripts/personal.py research capture-url --run-id <id> --url https://example.com
python3 scripts/personal.py research add-source --run-id <id> --url https://example.com
python3 scripts/personal.py report --run-id <id> --format md
python3 scripts/personal.py memory-search --query "X"
python3 scripts/personal.py memory-migrate
python3 scripts/personal.py route --input "Ballbox necesita fix en repo de pagos" --execute
python3 scripts/personal.py --json status
python3 scripts/personal.py approvals list
python3 scripts/personal.py --json approvals resolve --approval-id <id> --status approved --note "safe to proceed"
python3 scripts/personal.py tasks next
python3 scripts/personal.py leisure add --title "Severance" --media-type series
python3 scripts/personal.py leisure list --media-type series
```

## Operator Note

- daemon is long-running
- this agent can start, stop, or restart it across sessions
- canonical UI endpoint: `http://127.0.0.1:8082/`
- canonical status JSON endpoint: `http://127.0.0.1:8082/api/status`
- helper script:
  - `./scripts/daemon-8082.sh start`
  - `./scripts/daemon-8082.sh stop`
  - `./scripts/daemon-8082.sh restart`
  - `./scripts/daemon-8082.sh status`
  - `./scripts/daemon-8082.sh logs`

## Intended Usage Model

- personal capabilities stay in this repo
- this repo should be the normal conversational entry point
- Skills from this repo can be installed globally into `~/.agents/skills`
- `ai-dev-workflow` remains separate and keeps owning its own workflow skills
- specialist repos can be delegated to when the request clearly matches them
- risky external actions should go through the approval queue first

## Clone-Friendly Extras

- `scripts/install-opencode.sh` installs skills + OpenCode rules without cloning (see INSTALL.md)
- `scripts/install-skills.sh` links skills into `~/.codex/skills` (legacy)
- GitHub Actions runs the unit test suite on push and pull request

## Tests

```bash
./scripts/run-checks.sh
```

## Push Gate

Install the local pre-push gate once per clone:

```bash
./scripts/install-git-hooks.sh
```

After that, `git push` is blocked unless `scripts/run-checks.sh` passes.
