# Raycast Codex Notify + Reply

Current machine-level implementation for fullscreen-friendly Codex notifications and human replies.

## Scope

This flow is not implemented inside `personal-agent` runtime code.

Current pieces live in:

- hook: `~/.codex/hooks/notify_macos.sh`
- Raycast extension repo: `~/Code/raycast-codex-reply`
- bridge state dir: `~/.codex/raycast-codex-reply`

`personal-agent` only matters here as adjacent context. Its old `blocker reply` CLI path is removed in the active direct-runner flow.

## Current Architecture

1. Codex emits a notify hook event.
2. `~/.codex/hooks/notify_macos.sh` reads the JSON payload from stdin.
3. Hook decides whether this looks like a question needing human input.
4. If no reply needed, hook shows a standard macOS notification with AppleScript.
5. If reply needed, hook launches Raycast via deeplink and waits on a local JSON bridge.
6. Raycast form saves the reply to disk and copies it to clipboard.
7. Hook re-focuses `Warp`, pastes the reply, then presses Enter.

Approval prompts use a sibling flow:

1. watcher polls Codex local state SQLite + rollout logs
2. watcher detects approval-style prompts
3. watcher opens a dedicated Raycast approval form
4. saved one-key reply is sent back into `Warp` via AppleScript keystrokes

## Main Notify Hook

Source: `~/.codex/hooks/notify_macos.sh`

Responsibilities:

- read notify payload from stdin
- log raw payloads to `/tmp/codex-notify/notify_hook_payloads.log`
- extract:
  - `event`
  - `thread-id`
  - `turn-id`
  - `input-messages`
  - last assistant message variants
- recover missing assistant text from `~/.codex/state_5.sqlite` rollout path when payload is empty or generic
- decide `has_question`
- branch to:
  - Raycast reply flow for questions
  - plain macOS notification for non-questions

### Question Detection Heuristic

Current hook treats a turn as reply-worthy when any of these are true:

- resolved `last_msg` contains `?`
- raw payload text contains `?`
- payload is effectively `{}` and event is `agent-turn-complete`

That last rule is a fallback for current cases where Codex sends an empty notify payload.

### Message Recovery

If hook payload lacks usable assistant text, the hook reads the latest rollout file path from `~/.codex/state_5.sqlite`, then scans the rollout JSONL for:

- `event_msg.payload.type == "task_complete"` with `last_agent_message`
- `event_msg.payload.type == "agent_message"` with `message`
- `response_item.payload.type == "message"` with assistant `output_text`

This is why the flow still works when the notify payload itself is thin.

## Raycast Reply Flow

Primary repo: `~/Code/raycast-codex-reply`

### Trigger Script

Source: `~/Code/raycast-codex-reply/scripts/wait-for-reply.sh`

Behavior:

- takes prompt text, prompt id, source
- calls `request-reply.sh`
- polls `~/.codex/raycast-codex-reply/reply.json`
- returns matching reply text on stdout
- times out with exit `124` after `TIMEOUT_SECONDS` default `900`

`request-reply.sh` writes prompt state to:

- `~/.codex/raycast-codex-reply/current-prompt.json`

Then opens this deeplink:

- `raycast://extensions/sebas/raycast-codex-reply/reply-to-codex`

It also removes any stale `reply.json` first.

### Raycast UI Command

Source: `~/Code/raycast-codex-reply/src/reply-to-codex.tsx`

Behavior:

- reads `current-prompt.json`
- shows prompt text in a minimal form
- warns when current hook supplied empty/generic content
- saves reply payload to `reply.json`
- marks prompt status as `answered`
- copies reply to clipboard
- closes Raycast window
- shows HUD: `Reply saved and copied`

Reply payload shape:

```json
{
  "id": "prompt-...",
  "prompt": "original prompt text",
  "reply": "user reply",
  "respondedAt": "2026-03-16T...",
  "source": "codex-notify"
}
```

### Back In Notify Hook

If `wait-for-reply.sh` returns non-empty stdout:

- reply copied again with `pbcopy`
- append reply log row to `/tmp/codex-notify/notify_replies.log`
- `open -a "Warp"`
- AppleScript sends:
  - Cmd+V
  - Enter

Result: user can answer Codex without manually leaving fullscreen playback or retyping into terminal.

## Fallback Without Raycast

If `~/Code/raycast-codex-reply/scripts/wait-for-reply.sh` is not executable, `notify_macos.sh` falls back to AppleScript `display dialog`.

Behavior:

- optional `Warp` activate
- modal dialog with prompt text
- reply text returned from dialog
- empty string on skip/cancel/errors

This fallback is functional but less smooth than the Raycast path.

## Approval Flow

Separate from normal notify replies.

### Watcher

Source: `~/Code/raycast-codex-reply/scripts/watch-approvals.py`

Behavior:

- polls `~/.codex/state_5.sqlite` every second
- resolves latest thread + rollout path
- scans rollout JSONL for:
  - escalated `exec_command` requests with `justification`
  - latest assistant message
- only acts on prompts starting with:
  - `Do you want me to `
- deduplicates prompts by hashed signature saved in:
  - `~/.codex/raycast-codex-reply/approval-watch-state.json`

### Approval Request / Wait

Files:

- `scripts/request-approval.sh`
- `scripts/wait-for-approval.sh`

Bridge files:

- prompt: `approval-prompt.json`
- response: `approval-response.json`

Raycast deeplink:

- `raycast://extensions/sebas/raycast-codex-reply/approve-codex-action`

### Approval UI

Source: `src/approve-codex-action.tsx`

Behavior:

- loads `approval-prompt.json`
- offers one-key choices:
  - `y`
  - `a`
  - `p`
  - `n`
  - `esc`
- optional override field normalizes to first letter or `esc`
- writes `approval-response.json`
- copies key to clipboard
- closes Raycast

### Sending Approval Back To Codex

After `wait-for-approval.sh` returns, watcher calls AppleScript to activate `Warp` and send:

- `esc` via key code `53`, or
- typed single-letter keystroke

Unlike normal reply flow, approval watcher does not paste clipboard content. It sends the key directly.

## Relationship To `personal-agent`

Relevant current state in this repo:

- `scripts/personal.py` still defines `blocker reply` args
- command exits with: `blocker flow removed from direct codex runner`
- `personal_agent/runtime.py` direct runner has no live human-reply pause/resume path
- daemon UI is `draft -> confirm cwd -> launch -> result`

Implication:

- current fullscreen notification + reply path is machine-level Codex hook infrastructure
- not `personal-agent` task runtime infrastructure
- docs or future refactors should not assume replies route through `python3 scripts/personal.py blocker reply`

## Operational Files

- notify payload log: `/tmp/codex-notify/notify_hook_payloads.log`
- notify reply log: `/tmp/codex-notify/notify_replies.log`
- approval watcher log: `/tmp/codex-approval-watch.log`
- bridge dir: `~/.codex/raycast-codex-reply`
- Codex local state DB: `~/.codex/state_5.sqlite`

## Known Constraints

- hook still has to recover assistant text from rollout logs because notify payloads can be empty
- question detection is heuristic, not structured
- normal replies assume terminal focus target is `Warp`
- approval watcher only handles prompts matching `Do you want me to `
- Raycast deeplinks assume extension owner/name `sebas/raycast-codex-reply`

## Likely Change Points

If this flow breaks, check in this order:

1. `~/.codex/hooks/notify_macos.sh`
2. `~/Code/raycast-codex-reply/scripts/request-reply.sh`
3. `~/Code/raycast-codex-reply/src/reply-to-codex.tsx`
4. `~/Code/raycast-codex-reply/scripts/watch-approvals.py`
5. bridge files under `~/.codex/raycast-codex-reply`
6. Codex rollout metadata in `~/.codex/state_5.sqlite`
