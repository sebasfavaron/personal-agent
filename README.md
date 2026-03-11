# personal-agent

Successor to `second-brain`.

Personal research + memory runtime, kept separate from `ai-dev-workflow`.

## Principles

- Repo-local ownership for personal capabilities
- Global skill discovery via symlinks from `~/.codex/skills`
- SQLite as operational source of truth
- Human approval required for outreach / external side effects
- `ai-dev-workflow` stays focused on project workflows

## Current Scope

V1 foundation:

- research run tracking
- sources / claims / tasks persistence
- approval queue
- memory search
- skill wrappers for Codex

Not included yet:

- sending email
- contacting people
- browser automation runtime
- background daemon execution

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

Internal command surface only. Not intended as user-facing primary UX.

```bash
python3 scripts/personal.py research start --goal "Investigate X"
python3 scripts/personal.py research add-source --run-id <id> --url https://example.com
python3 scripts/personal.py report --run-id <id> --format md
python3 scripts/personal.py memory-search --query "X"
python3 scripts/personal.py approvals list
```

## Tests

```bash
python3 -m unittest discover -s tests
```
