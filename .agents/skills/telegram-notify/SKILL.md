---
name: telegram-notify
description: Send Telegram notifications via bot
---

# telegram-notify

## Workflow

1. Ensure environment variables are set:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. Execute:
   - `~/.agents/skills/telegram-notify/telegram-notify "<message>"`
3. Confirm that the message was sent.

## Rules

- never print the token or chat id in outputs
- keep messages concise and action-oriented
