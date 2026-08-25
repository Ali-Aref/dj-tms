# Commands

Commands are vendor-neutral. The server assigns `id`, `issuedAt`, and default `expiresAt`. The agent runs handlers locally and reports a terminal status.

## Wire object (poll)

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Unique per command. Agent skips rows with blank `id` or `type`. Duplicate `id` is not re-executed. |
| `type` | string | Handler name (`ping`, `collect_inventory`, …). |
| `issuedAt` | number | Epoch ms when this server enqueued it. |
| `expiresAt` | number | Epoch ms; agent fails with `expired` if `now >= expiresAt` and `expiresAt > 0`. `0` means no expiry. |
| `payload` | object | Opaque. v1 agent handlers ignore it. Default `{}`. |

Default `expiresAt` is 24 hours after enqueue. Operator may pass a custom `expiresAt`.

Ids in this sample are `c-1`, `c-2`, … (process-local counter).

## Lifecycle

Server-side this sample only tracks:

- `pending` — created, returned by poll while `result` is null
- whatever the agent posted (`succeeded` / `failed`) once a result arrives

The **agent** uses a stricter local machine:

```text
pending → received → running → succeeded | failed
pending | received → failed   (expiry)
```

Terminal states do not move again. If the server keeps returning the same `id`, the agent re-reports the stored result and does not run the handler twice.

After a result is stored here, poll omits that command.

## v1 types the agent implements

| `type` | Agent result | Side effect |
|---|---|---|
| `ping` | `succeeded` / `pong` | None |
| `collect_inventory` | `succeeded` / `ok` | Marks inventory due; agent POSTs inventory later in the same tick if it can |
| anything else | `failed` / `unsupported:{type}` | None |

This sample does **not** check `capabilities` before enqueue. A real TMS should. Do not enqueue install / reboot / firmware until those handlers exist on the agent.

## Idempotency

- Register: same `serialNumber` → same terminal and token.
- Command `id`: agent-side; retries must not install or reboot twice once those types exist.
- Result POST: unknown id is still `204`; known id overwrites stored result.

## Inspecting history

Poll only shows unfinished commands. Full list including results is on `GET /v1/terminals/{id}` ([Operator API](operator-api.md)).
