# personal-agent

Successor to `second-brain`.

Personal research + memory runtime, kept separate from `ai-dev-workflow`.

See [INSTALL.md](INSTALL.md) for setup.

## Principles

- Repo-local ownership for personal capabilities
- Global skill discovery via symlinks from `~/.codex/skills`
- Shared DB in sibling repo `~/agents-database` is the durable source of truth for new work
- legacy local SQLite stays only for transition, migration, and old-run inspection
- Human approval required for outreach / external side effects
- `ai-dev-workflow` stays focused on project workflows

## V1 Front Door

`personal-agent` now grows toward a front-door runtime:

- daemon + dashboard at `127.0.0.1:6666`
- shared-memory orchestration over `agents-database`
- Codex-backed intake planner with heuristic fallback
- event worker using `codex exec` for structured task decisions, blockers, and approval requests
- specialist handoff contract for sibling subagents

System map and machine-recreation guide:

- [docs/system-v1.md](docs/system-v1.md)

## What Exists Today

This repository now contains both:

- legacy local-first research/task runtime
- emerging V1 front-door runtime on top of shared memory

- SQLite-backed persistence for research runs
- source, claim, task, and approval tracking
- memory search over stored runs, claims, and tasks
- Codex skill wrappers owned by this repo
- task intake persistence with parent tasks and subtasks
- request routing and specialist delegation across personal/company/code contexts
- internal command surface via `python3 scripts/personal.py`
- unit tests for the storage lifecycle

## Shared Memory Integration

Durable shared memory lives in the sibling project at `~/agents-database`.

- new research claims and sources are mirrored into shared memory when available
- completed research runs are mirrored as durable memory summaries
- `memory-search` now queries shared memory first and also returns legacy local matches
- `memory-migrate` imports existing legacy research memory into the shared system
- `research status --run-id <id>` falls back to the mirrored shared-memory record when the old local run is no longer present

Default shared-memory path discovery:

- tries `~/agents-database/src` first
- then falls back to `~/Code/agents-database/src`
- database defaults to `<shared-memory-root>/data/shared-agent-memory.sqlite3`
- when launching Codex from `personal-agent`, add `--add-dir ~/agents-database` so sandboxed Codex runs can write the canonical DB in place

These can be overridden with:

- `PERSONAL_AGENT_SHARED_MEMORY_ROOT`
- `PERSONAL_AGENT_SHARED_MEMORY_DB_PATH`
- `PERSONAL_AGENT_CODEX_ADD_DIRS`

## What Is Still A Promise

These are goals for future work. They are not implemented in this repo yet.

- browser automation and live web execution
- email sending or contact workflows
- proactive background daemon / scheduler
- calendar or inbox integrations
- fully autonomous task execution

## Routing Model

`personal-agent` is the intended front door.

- start here for general requests
- personal context stays here
- Ballbox or company-shaped requests can be delegated to `~/ballbox-company-agent`
- code-shaped requests can be delegated to `~/ai-dev-workflow`
- company requests that also imply repo work can cascade `personal -> company -> code`

## Layout

```text
personal-agent/
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
python3 scripts/personal.py approvals list
python3 scripts/personal.py tasks next
python3 scripts/personal.py leisure add --title "Severance" --media-type series
python3 scripts/personal.py leisure list --media-type series
```

## Intended Usage Model

- personal capabilities stay in this repo
- this repo should be the normal conversational entry point
- Codex skills from this repo can be exposed globally with symlinks
- `ai-dev-workflow` remains separate and keeps owning its own workflow skills
- specialist repos can be delegated to when the request clearly matches them
- risky external actions should go through the approval queue first

## Clone-Friendly Extras

- `scripts/install-skills.sh` links this repo's skills into `~/.codex/skills`
- GitHub Actions runs the unit test suite on push and pull request

## Tests

```bash
python3 -m unittest discover -s tests
```

## Push Gate

Install the local pre-push gate once per clone:

```bash
./scripts/install-git-hooks.sh
```

After that, `git push` is blocked unless `scripts/run-checks.sh` passes.
