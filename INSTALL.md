# Install

This project is currently a local-first starter repo for building a personal assistant runtime.

What you get today:

- local SQLite storage
- research run tracking
- Codex skill wrappers
- approval queue foundation

What you do not get yet:

- browser automation
- email sending
- background daemon
- external account integrations

## Prerequisites

- Python 3.11+ recommended
- Git
- Codex, only if you want to use the included skills

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
python3 scripts/personal.py --json research start \
  --goal "Investigate local-first personal assistant patterns" \
  --scope "starter implementation ideas" \
  --assumptions "foundation repo only"
```

Then add sources and claims:

```bash
python3 scripts/personal.py --json research add-source \
  --run-id "<run-id>" \
  --url "https://example.com" \
  --title "Example source"

python3 scripts/personal.py --json research add-claim \
  --run-id "<run-id>" \
  --claim "Example finding" \
  --confidence 0.6 \
  --status tentative \
  --source-url "https://example.com"
```

Render a report:

```bash
python3 scripts/personal.py report --run-id "<run-id>" --format md
```

## Data Location

Default database path:

```text
./data/personal-agent.sqlite3
```

To override it:

```bash
export PERSONAL_AGENT_DATA_DIR=/absolute/path/to/data-dir
```

## Optional: Expose Skills Globally For Codex

This repo owns its own skills under:

```text
.agents/skills/
```

If you want Codex to discover them globally on your machine:

```bash
mkdir -p ~/.codex/skills
ln -sfn "$PWD/.agents/skills/personal-research" ~/.codex/skills/personal-research
ln -sfn "$PWD/.agents/skills/personal-status" ~/.codex/skills/personal-status
ln -sfn "$PWD/.agents/skills/personal-memory-search" ~/.codex/skills/personal-memory-search
ln -sfn "$PWD/.agents/skills/personal-approval-queue" ~/.codex/skills/personal-approval-queue
```

## Current Limitations

- no browser runtime
- no outbound integrations
- no packaged installer yet
- internal command surface may still evolve
