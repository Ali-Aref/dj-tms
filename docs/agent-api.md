# Agent API

Paths are relative to `/v1`. The agent sends `Accept: application/json` and, after register, `Authorization: Bearer {token}`.

Management-plane heartbeat diagnostics, event messages/meta, and command result fields are sanitized before persistence and request/response logging. PAN-like values and values under PIN/CVV/track/KSN/token/authorization/bearer/secret/API-key/password keys become `[REDACTED]`; request and response shapes are unchanged.

Auth semantics on terminal-scoped agent routes:

- unknown `terminalId` -> `404` `{ "error": "unknown terminal" }`
- known terminal with missing/invalid bearer -> `401` `{ "error": "unauthorized" }`

## `POST /terminals/register`

Creates or reuses a terminal. No bearer. `serialNumber` is the idempotency key.

**Request**

```json
{
  "protocolVersion": 1,
  "serialNumber": "P653200099993",
  "vendor": "topwise",
  "model": "T6",
  "firmware": "Z6532AA_PARSA_T6_TSEC_V2.0.2_user",
  "osVersion": "13",
  "agentVersion": "1.0",
  "capabilities": ["ping", "collect_inventory", "install_app", "uninstall_app", "reboot", "poweroff", "update_agent"]
}
```

| Field | Required by this server | Notes |
|---|---|---|
| `serialNumber` | yes (non-empty string) | Same serial → same `terminalId` and `token`; identity JSON is overwritten |
| other fields | no | Stored as-is on the terminal |

Missing `serialNumber` → `400` `{ "error": "serialNumber required" }`.

**Response `200`**

```json
{ "terminalId": "uuid", "token": "uuid" }
```

The agent fails register if either field is blank.

On **first** insert only, the server enqueues a `ping` (see [Commands](commands.md)). Re-register does not enqueue another ping.

## `POST /terminals/{terminalId}/heartbeat`

Last-seen liveness. Body is stored with a server `receivedAt` (epoch ms). Response body is ignored by the agent.

**Request**

```json
{
  "protocolVersion": 1,
  "batteryPercent": 100,
  "storageFreeBytes": 23498678272,
  "network": "wifi"
}
```

`network` from the agent: `wifi` | `cellular` | `ethernet` | `offline` | `other` | `unknown`.

**Response:** `204` empty.
Auth failure: `401`.

Optional diagnostics extension:

```json
"diagnostics": {
  "lastError": "none",
  "outboxSize": 0,
  "agentVersion": "1.0"
}
```

## `POST /terminals/{terminalId}/inventory`

Installed-app snapshot. Stored with `receivedAt`. Can be large (full package list on the POS).

**Request**

```json
{
  "protocolVersion": 1,
  "osVersion": "13",
  "firmware": "…",
  "apps": [
    { "packageName": "com.example.tmsmanager", "versionName": "1.0", "versionCode": 1 }
  ]
}
```

**Response:** `204` empty.
Auth failure: `401`.

## `POST /terminals/{terminalId}/location`

Latest terminal location. The agent sends this approximately every 15 minutes after Android location permission is granted. This sample retains only the latest accepted report; it does not build a location history. Read it back from `GET /v1/terminals/{id}` (`lastLocation`) or Django admin (**Terminals** → last location).

**Request**

```json
{
  "protocolVersion": 1,
  "latitude": 34.5,
  "longitude": 69.2,
  "accuracyMeters": 12.5,
  "provider": "network",
  "capturedAt": 1789000000000
}
```

`latitude` must be -90 through 90; `longitude` must be -180 through 180. `accuracyMeters` is optional and must be non-negative. `provider` is a non-empty string. `capturedAt` is device epoch milliseconds; the server adds `receivedAt`.

**Response:** `204` empty.
Auth failure: `401`.

## `GET /terminals/{terminalId}/commands`

Pending work for this terminal. Returns only commands that have **no result yet**.

**Response `200`**

```json
{
  "commands": [
    {
      "id": "c-1",
      "type": "ping",
      "issuedAt": 1787638397396,
      "expiresAt": 1787724797396,
      "payload": {}
    }
  ]
}
```

Idle tick: `{ "commands": [] }`. Field rules and types: [Commands](commands.md).
Auth failure: `401`.

## `POST /terminals/{terminalId}/commands/{commandId}/result`

Agent finished (or failed) a command. At-least-once: the agent may POST the same result again if the outbox was not acked.

**Request**

```json
{
  "protocolVersion": 1,
  "status": "succeeded",
  "message": "pong",
  "completedAt": 1787637915426
}
```

`status` is lowercase: `succeeded` or `failed`. `completedAt` is the **device** clock (epoch ms); it can disagree with the server’s `issuedAt`.

If `commandId` is known, the command is marked done and dropped from later polls. Unknown `commandId` still returns `204` so the agent outbox can drain.

**Response:** `204` empty.
Auth failure: `401`.

## `POST /terminals/{terminalId}/events`

Best-effort progress events from the agent (for install/update lifecycle visibility). These events do not replace final command results.

**Request**

```json
{
  "protocolVersion": 1,
  "kind": "download_started",
  "level": "info",
  "message": "http://files.example.com/app.apk",
  "commandId": "c-123",
  "eventAt": 1789000000000,
  "meta": {
    "type": "install_app",
    "urlHost": "files.example.com"
  }
}
```

**Response:** `204` empty.
Auth failure: `401`.

To push work without waiting for the auto-`ping`, use the [Operator API](operator-api.md).
