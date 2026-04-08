# Install

This project is currently a local-first starter repo for building a personal assistant runtime.

What you get today:

- local SQLite storage
- research run tracking
- OpenCode skill wrappers
- approval queue foundation
- task intake persistence with subtasks
- request routing across personal, company, and code specialists

What you do not get yet:

- browser automation
- email sending
- background daemon
- external account integrations

## Prerequisites

- Python 3.11+ recommended
- Git
- OpenCode, only if you want to use the included skills

## Clone

```bash
git clone https://github.com/sebasfavaron/personal-agent.git
cd personal-agent
```

## Verify Python

```bash
python3 --version
```

## Run Tests

```bash
python3 -m unittest discover -s tests
```

## Start A Sample Research Run

```bash
python3 scripts/personal.py research start --json   --goal "Investigate local-first personal assistant patterns"   --scope "starter implementation ideas"   --assumptions "foundation repo only"
```

Then add sources and claims:

```bash
python3 scripts/personal.py research search-web --json   --run-id "<run-id>"   --query "local-first personal assistant patterns"   --max-results 5

python3 scripts/personal.py research capture-url --json   --run-id "<run-id>"   --url "https://example.com"   --notes "why this source matters"

python3 scripts/personal.py research add-source --json   --run-id "<run-id>"   --url "https://example.com"   --title "Example source"

python3 scripts/personal.py research add-claim --json   --run-id "<run-id>"   --claim "Example finding"   --confidence 0.6   --status tentative   --source-url "https://example.com"
```

Render a report:

```bash
python3 scripts/personal.py report --run-id "<run-id>" --format md
```

## Data Location

Default database path:

```text
~/agents-database/data/shared-agent-memory.sqlite3
```

The database is created on first use by the shared-memory service.

To override it:

```bash
export PERSONAL_AGENT_SHARED_MEMORY_DB_PATH=/absolute/path/to/shared-agent-memory.sqlite3
```

## OpenCode Global Install (No Clone Required)

This installs the global OpenCode rules file and the personal-agent skills without cloning this repo.

```bash
curl -fsSL https://raw.githubusercontent.com/sebasfavaron/personal-agent/main/scripts/install-opencode.sh | sh
```

Restore previous config if needed:

```bash
curl -fsSL https://raw.githubusercontent.com/sebasfavaron/personal-agent/main/scripts/install-opencode.sh | sh -s -- restore
```

## Optional: Expose Skills Globally For Codex

This repo owns its own skills under:

```text
.agents/skills/
```

If you want Codex to discover them globally on your machine:

```bash
./scripts/install-skills.sh
```

## Optional: Verify Routing

```bash
python3 scripts/personal.py route --json   --input "Ballbox necesita fix en repo de pagos"   --execute
```

## Gotchas

- the OpenCode installer overwrites `~/.agents/skills` and `~/AGENTS.md` (and symlinks `~/.config/opencode/AGENTS.md`)
- backups are saved to `~/.agents/skills.bck`, `~/AGENTS.md.bck`, and `~/.config/opencode/AGENTS.md.bck` (existing `.bck` is replaced)
- `opencode` and `curl` must be on your `PATH`

## Current Limitations

- no browser runtime
- no outbound integrations
- internal command surface may still evolve
