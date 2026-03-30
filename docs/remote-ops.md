# Remote Ops

Target topology:

- laptop: HTTP client only
- server `personal-agent`: task runner API on `http://100.116.176.16:8082`
- server `agents-database`: shared-memory API on `http://100.116.176.16:8091`

Operational rule:

- do not depend on `~/agents-database` on the laptop for normal operation
- prefer running tasks on the server so work survives laptop sleep/shutdown

Server services:

- `personal-agent.service`
- `agents-database-http.service`

Quick checks from the laptop:

```bash
curl http://100.116.176.16:8082/api/status
curl http://100.116.176.16:8091/api/status
curl "http://100.116.176.16:8091/api/search?q=memory&scope=global"
```

Gotchas:

- The server `SERVICES-ARCHITECTURE.md` may not match live routing. Verify with `curl`, not assumptions.
- `personal-agent` launches the configured runner CLI on the server.
- `PERSONAL_AGENT_RUNNER_BIN` overrides the runner binary when needed.
