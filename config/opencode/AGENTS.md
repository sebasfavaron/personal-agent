# Personal Agent Global Rules

These rules apply to OpenCode sessions across repositories.

## Intent
- use personal-agent skills for memory, approvals, and research
- durable preferences and memories live in ~/agents-database

## Rules
- when a request depends on prior knowledge, load `personal-memory-search` first
- outreach or external side effects must go through `personal-approval-queue`
- if a durable preference or memory is learned, write it to ~/agents-database
- irreversible actions require explicit confirmation

## Endpoints
- personal-agent API: http://100.116.176.16:8082/api/status
- agents-database API: http://100.116.176.16:8091/api/status
