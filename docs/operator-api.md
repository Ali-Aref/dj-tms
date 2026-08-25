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
      "identity": { "serialNumber": "…", "vendor": "topwise", "…": "…" },
      "lastHeartbeat": { "batteryPercent": 100, "network": "wifi", "receivedAt": 0 },
      "lastInventory": { "osVersion": "13", "apps": [], "receivedAt": 0 },
      "commands": []
    }
  ]
}
```

`lastHeartbeat` / `lastInventory` are `null` until the agent has posted them. `commands` is the full stored list (pending and completed). Same data is visible in Django admin at `/admin/`.

## `GET /v1/terminals/{terminalId}`

Same object as one element of the list above. Unknown id → `404`.

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

Missing `type` → `400` `{ "error": "type required" }`.

**Response `201`** — the stored command, including `status: "pending"` and `result: null`.

Install / uninstall / reboot examples: [Remote ops](remote-ops.md).

```bash
curl -s -X POST http://127.0.0.1:3000/v1/terminals/<terminalId>/commands \
  -H 'content-type: application/json' \
  -d '{"type":"ping"}'
```

Useful types today: `ping`, `collect_inventory`, `install_app`, `uninstall_app`, `reboot`. Payload rules: [Commands](commands.md). Invalid payload → `400` with an error string.
