# Operator API

Not used by the POS. These routes let you see what the sample stored and enqueue a command while the agent is polling.

## `GET /health`

Liveness. Not under `/v1`.

**Response `200`:** `{ "ok": true }`

## `GET /v1/terminals`

All terminals in the database.

**Response `200`**

```json
{
  "terminals": [
    {
      "terminalId": "uuid",
      "status": "active",
      "identity": { "serialNumber": "…", "vendor": "topwise", "…": "…" },
      "lastHeartbeat": { "batteryPercent": 100, "network": "wifi", "receivedAt": 0 },
      "lastInventory": { "osVersion": "13", "apps": [], "receivedAt": 0 },
      "lastLocation": { "latitude": 34.5, "longitude": 69.2, "provider": "network", "receivedAt": 0 },
      "commands": []
    }
  ]
}
```

`lastHeartbeat`, `lastInventory`, and `lastLocation` are `null` until the agent has posted them. `lastLocation` is only the newest accepted location, not a history; inspect it here or in Django admin at `/admin/` (**Terminals** list **last location** column, or the terminal’s `last_location` field). `commands` is the full stored list (pending and completed). There is no map view in this sample.

`status` is `pending`, `active`, `deleted`, or `decommissioned`. Only active terminals can receive commands.

Agent-supplied heartbeat diagnostics, event messages/meta, and command result strings are displayed from already-redacted persisted values. Sensitive values appear as `[REDACTED]`.

## `GET /v1/terminals/{terminalId}`

Same object as one element of the list above, plus a latest-events list (up to 20 items). Unknown id → `404`.

Each event item contains:

- `commandId` (nullable)
- `kind`
- `level`
- `message`
- `meta` (JSON object)
- `eventAt`
- `receivedAt`

## `POST /v1/terminals/{terminalId}/commands`

Enqueue work. The next agent poll will include it until a result is posted.

**Request**

```json
{
  "type": "collect_inventory",
  "payload": {},
  "expiresAt": 1787724797396
}
```

| Field | Required | Default |
|---|---|---|
| `type` | yes (non-empty string) | — |
| `payload` | no | `{}` |
| `expiresAt` | no | now + 24h (epoch ms on wire; use admin date/time picker in Django) |

Missing `type` → `400` `{ "error": "type required" }`. A non-active terminal returns `400 {"error":"terminal is not active"}`.

**Response `201`** — the stored command, including `status: "pending"` and `result: null`.

Install / uninstall / reboot / poweroff / update-agent examples: [Remote ops](remote-ops.md).

```bash
curl -s -X POST http://127.0.0.1:3000/v1/terminals/<terminalId>/commands \
  -H 'content-type: application/json' \
  -d '{"type":"ping"}'
```

Useful types today: `ping`, `collect_inventory`, `install_app`, `uninstall_app`, `reboot`, `poweroff`, `update_agent`. Payload rules: [Commands](commands.md). Invalid payload or missing terminal capability → `400` with an error string (e.g. `install_app: sha256 required`, `terminal does not support install_app`).
