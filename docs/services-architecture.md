# Ballbox-First Services Architecture

Fecha: 2026-03-30

## Servicios Expuestos via Tailscale

Estado real verificado el 2026-03-30 con `tailscale serve status` y `curl`.

| Endpoint | Puerto Local | Descripción |
|----------|--------------|-------------|
| `https://ballbox-first.emperor-ratio.ts.net/` | `:80` (nginx) | Homepage Svelte - Portal principal |
| `https://ballbox-first.emperor-ratio.ts.net:8443/` | `:3967` (opencode web) | OpenCode Web UI |
| `http://100.116.176.16:8082/api/status` | `:8082` (personal-agent daemon) | Personal Agent API directa por Tailscale IP |
| `http://100.116.176.16:8091/api/status` | `:8091` (agents-database HTTP API) | Shared memory + tasks/artifacts API directa por Tailscale IP |

## Servicios Internos (sin exponer)

| Puerto | Proceso | Descripción |
|--------|---------|-------------|
| `:3967` | opencode web | UI de OpenCode |
| `:8082` | personal-agent daemon | API del personal agent |
| `:8091` | agents-database HTTP API | API de memoria compartida, tasks, runs y artifacts |
| `:18789` | clawdbot-gateway | Backend de OpenClaw/Control UI |
| `:80` | nginx | Servidor web principal |

## Resiliencia

- **Tailscale Serve Guardian**: Servicio systemd que verifica cada 5 minutos que los puertos expuestos estén activos
- Si detecta que falta alguno, restaura automáticamente la config

## URLs de Acceso

```bash
# Homepage
curl https://ballbox-first.emperor-ratio.ts.net/

# OpenCode
curl https://ballbox-first.emperor-ratio.ts.net:8443/

# Personal Agent API directa
curl http://100.116.176.16:8082/api/status

# Agents Database API directa
curl http://100.116.176.16:8091/api/status
curl "http://100.116.176.16:8091/api/search?q=memory&scope=global"
```

Notas:

- `https://ballbox-first.emperor-ratio.ts.net/api/` no está hoy ruteado al `personal-agent`; responde la homepage de nginx.
- `https://ballbox-first.emperor-ratio.ts.net/portal/` tampoco aparece hoy en `tailscale serve status`; verificar antes de asumir que sigue publicado.

## Configuración de Red

- **Hostname Tailscale**: `ballbox-first.emperor-ratio.ts.net`
- **IP Tailscale**: `100.116.176.16`
- **Servidor**: Ubuntu en estructura/home
- **Proxy inverso**: nginx en `:80`

## Mantenimiento

### Reiniciar homepage
```bash
ssh ballbox-first
sudo systemctl restart nginx
```

### Ver estado Tailscale Serve
```bash
ssh ballbox-first 'tailscale serve status'
```

### Ver estado servicios remotos
```bash
ssh ballbox-first 'systemctl --user status personal-agent.service --no-pager'
ssh ballbox-first 'systemctl --user status agents-database-http.service --no-pager'
```

### Ver logs de servicios remotos
```bash
ssh ballbox-first 'journalctl --user -u personal-agent.service -f'
ssh ballbox-first 'journalctl --user -u agents-database-http.service -f'
```

### Ver estado Tailscale directo
```bash
curl http://100.116.176.16:8082/api/status
curl http://100.116.176.16:8091/api/status
```
