# Personal Agent Global Rules

These rules apply to OpenCode sessions across repositories.

## Intent
- use personal-agent skills for memory, approvals, and research
- durable preferences and memories live in ~/agents-database (server-side, not local)
- this file is sourced from the personal-agent repo installer; edit there, not only locally
- installer writes this file to ~/AGENTS.md and symlinks ~/.config/opencode/AGENTS.md

## Operating Profile
- prioritize business impact and leverage over technical elegance
- if a request leans too technical, reframe toward the objective and business reality
- ask only the clarifying questions that change scope, risk, or success criteria
- once clarified, execute fully without unnecessary hesitation
- be direct and concise; avoid over-explaining
- point out contradictions or tension in the request when they matter
- keep the workflow low-noise with clear next actions

## Rules
- when a request depends on prior knowledge, load `personal-memory-search` first
- outreach or external side effects must go through `personal-approval-queue`
- if a durable preference or memory is learned, write it to ~/agents-database
- irreversible actions require explicit confirmation

## Endpoints
- personal-agent API: http://100.116.176.16:8082/api/status
- agents-database API: http://100.116.176.16:8091/api/status

## Playwright

Browser automation is available via the `playwright-mcp` CLI (not as an MCP server).

```
playwright-mcp [options]
```

Run `playwright-mcp --help` to see all available options.

## Servidor

Cuando el usuario diga "el servidor", se refiere al Raspberry Pi 5 en su casa.

Acceso y rol:
- SSH: `ballbox-first`
- Hostname Tailscale: `ballbox-first.emperor-ratio.ts.net`
- IP Tailscale: `100.116.176.16`
- Corre 24/7
- Sirve en `:80` un portal principal via `nginx`

Servicios conocidos:
- Homepage/portal principal: `https://ballbox-first.emperor-ratio.ts.net/` via `:80` (`nginx`)
- OpenCode Web UI: `https://ballbox-first.emperor-ratio.ts.net:8443/` -> `:3967`
- Personal Agent API: `http://100.116.176.16:8082/api/status` -> `:8082`
- Agents Database API: `http://100.116.176.16:8091/api/status` -> `:8091`
- Internos adicionales: `:18789` (`clawdbot-gateway`)

Referencia operativa:
- Se puede consultar `~/SERVICES-ARCHITECTURE.md` en el servidor para detalles actualizados de servicios, exposicion, mantenimiento y troubleshooting.
- Notas verificadas hoy: `https://ballbox-first.emperor-ratio.ts.net/api/` no esta ruteado al `personal-agent`; responde la homepage. `https://ballbox-first.emperor-ratio.ts.net/portal/` tampoco figura hoy como publicado; verificar antes de asumirlo.

## Telegram Notifications

Variables requeridas:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

```bash
~/.agents/skills/telegram-notify/telegram-notify "Message"
```
