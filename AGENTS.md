---
routing:
  - match:
      - ballbox
      - ballbox company
    include: /mnt/rpi/repos/personal-agent/ballbox/AGENTS.md
    context_root: /mnt/rpi/repos/personal-agent/ballbox
    notes: Load Ballbox specialist rules only when relevant
---

Owner-managed repo. Work style: telegraph; min tokens.

## Intent
- personal capabilities live here
- reusable across workspaces through global Codex skill symlinks
- no duplication of `ai-dev-workflow` skills here

## Rules
- keep skills in this repo; expose globally by symlink, not copy
- keep state local-first
- persist notable user/project facts in shared memory system at `~/agents-database`; local SQLite here stays operational for research/tasks/approvals
- durable cross-agent prefs/rules always to `~/agents-database` first; never rely on Codex-only local state as source of truth
- if a workflow preference, approval convention, repo policy, or operator habit should survive across agents/sessions/devices, write it to `~/agents-database`
- for any ambiguous term, remembered phrase, shorthand, nickname, or speech-to-text alias, query `~/agents-database` before guessing from local context
- ask important doubts up front; once answered, execute as completely as possible without unnecessary risk
- avoid premature action or implementation before intent is clear
- irreversible actions require Sebas confirmation before execution
- approval gate for outreach / side effects
- prefer auditable storage and explicit assumptions
- task hygiene: create `open` tasks only for real follow-up; if work is completed in-turn, avoid creating a task or close it before handoff; completed research runs should be marked finished

## Durable Notes
- Sebas: `street-cast-pwa` main connected
- Sebas: `street-cast-server` main connected
- Sebas preference: durable operational rules/prefs belong in `~/agents-database`, not Codex internal approval/state storage
- Sebas preference: if any spoken, remembered, or ambiguous term needs interpretation, resolve through `~/agents-database` first
- Sebas preference: direct feedback is strong signal; adjust quickly when he says he likes/dislikes something
- Codex launch convention for personal-agent work that must write shared DB: add `--add-dir ~/agents-database` so sandboxed runs can edit the canonical DB in-repo

## Before Handoff
- run repo checks
- call out missing integrations plainly
- after changes to `personal_agent/daemon.py` or daemon-served routing/runtime code, restart `8082` before UI smoke tests; otherwise the dashboard may still serve stale behavior
