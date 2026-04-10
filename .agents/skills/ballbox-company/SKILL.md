---
name: ballbox-company
description: Load Ballbox company context and operating namespace
---

# ballbox-company

## Purpose

Load the Ballbox company operating context when the request is about Ballbox.

## Workflow

1. Use the Ballbox namespace at `/mnt/rpi/repos/personal-agent/ballbox` as the working context root.
2. Read `/mnt/rpi/repos/personal-agent/ballbox/AGENTS.md` and follow its rules.
3. Use `/mnt/rpi/repos/personal-agent/ballbox/index.md` as the default dashboard entry point.
4. Prefer shared-memory search before assuming facts; avoid invented certainty.
5. If the work implies repo/code changes, delegate to `~/ai-dev-workflow`.
