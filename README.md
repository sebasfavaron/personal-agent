# personal-agent

Successor to `second-brain`.

Personal research + memory runtime, kept separate from `ai-dev-workflow`.

See [INSTALL.md](INSTALL.md) for setup.

## Principles

- Repo-local ownership for personal capabilities
- Global skill discovery via symlinks from `~/.codex/skills`
- SQLite as operational source of truth
- Human approval required for outreach / external side effects
- `ai-dev-workflow` stays focused on project workflows

## What Exists Today

This repository currently implements a local foundation, not a full personal assistant.

- SQLite-backed persistence for research runs
- source, claim, task, and approval tracking
- memory search over stored runs, claims, and tasks
- Codex skill wrappers owned by this repo
- internal command surface via `python3 scripts/personal.py`
- unit tests for the storage lifecycle

## What Is Still A Promise

These are goals for future work. They are not implemented in this repo yet.

- browser automation and live web execution
- email sending or contact workflows
- proactive background daemon / scheduler
- calendar or inbox integrations
- fully autonomous task execution

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
python3 scripts/personal.py research add-source --run-id <id> --url https://example.com
python3 scripts/personal.py report --run-id <id> --format md
python3 scripts/personal.py memory-search --query "X"
python3 scripts/personal.py approvals list
```

## Intended Usage Model

- personal capabilities stay in this repo
- Codex skills from this repo can be exposed globally with symlinks
- `ai-dev-workflow` remains separate and keeps owning its own workflow skills
- risky external actions should go through the approval queue first

## Tests

```bash
python3 -m unittest discover -s tests
```
