# personal-agent

Successor to `second-brain`.

Personal research + memory runtime, kept separate from `ai-dev-workflow`.

See [INSTALL.md](INSTALL.md) for setup.

## Principles

- Repo-local ownership for personal capabilities
- Global skill discovery via symlinks from `~/.codex/skills`
- SQLite as operational source of truth for research/task runtime
- shared agent memory lives in sibling repo `~/agents-database`
- Human approval required for outreach / external side effects
- `ai-dev-workflow` stays focused on project workflows

## What Exists Today

This repository currently implements a local foundation, not a full personal assistant.

- SQLite-backed persistence for research runs
- source, claim, task, and approval tracking
- memory search over stored runs, claims, and tasks
- Codex skill wrappers owned by this repo
- task intake persistence with parent tasks and subtasks
- request routing and specialist delegation across personal/company/code contexts
- internal command surface via `python3 scripts/personal.py`
- unit tests for the storage lifecycle

## Shared Memory Integration

`personal-agent` now treats its own SQLite database as the operational store for research runs, tasks, approvals, and artifacts.

Durable shared memory lives in the sibling project at `~/agents-database`.

- new research claims and sources are mirrored into shared memory when available
- completed research runs are mirrored as durable memory summaries
- `memory-search` now queries shared memory first and also returns legacy local matches
- `memory-migrate` imports existing legacy research memory into the shared system

Default shared-memory path discovery:

- tries `~/agents-database/src` first
- then falls back to `~/Code/agents-database/src`
- database defaults to `<shared-memory-root>/data/shared-agent-memory.sqlite3`

These can be overridden with:

- `PERSONAL_AGENT_SHARED_MEMORY_ROOT`
- `PERSONAL_AGENT_SHARED_MEMORY_DB_PATH`

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
