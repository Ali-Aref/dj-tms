# TMSExpress

Sample TMS backend for [TMSManager](../../TMSManager). Django + SQLite. Same protocol v1 HTTP contract as before so the POS agent needs no changes.

This is a contract sketch for a real TMS, not a production server.

## Read in this order

| Doc | When |
|---|---|
| [Overview](overview.md) | What this sample is, what it deliberately skips, and how it maps to a real TMS |
| [Running](running.md) | Start the server, Django admin, point the agent at it |
| [Agent API](agent-api.md) | Endpoints the POS calls every tick |
| [Commands](commands.md) | Command shape, status, poll/result rules, v1 types |
| [Remote ops](remote-ops.md) | Install, uninstall, reboot — admin steps, curl, expiry |
| [Operator API](operator-api.md) | Health, inspect terminals, enqueue work (API or admin) |

## Endpoint map

Base URL: `http://<host>:3000/v1` (except `/health`, which is not under `/v1`).

Agent paths match TMSManager `docs/protocol.md`. The agent appends them to `TMS_BASE_URL` (that value already includes `/v1`).

```text
POS agent                         Operator (curl / admin)
─────────                         ─────────────────────
POST /terminals/register          GET  /health
POST /terminals/:id/heartbeat     GET  /v1/terminals
POST /terminals/:id/inventory     GET  /v1/terminals/:id
POST /terminals/:id/location
GET  /terminals/:id/commands      POST /v1/terminals/:id/commands
POST /terminals/:id/commands/:cid/result
                                  Django admin: /admin/
```

Terminals and commands persist in `db.sqlite3`. JSON request and response bodies are logged on every call. See [Running](running.md#logging).
