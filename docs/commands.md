# Commands

Commands are vendor-neutral. The server assigns `id`, `issuedAt`, and default `expiresAt`. The agent runs handlers locally and reports a terminal status.

## Wire object (poll)

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Unique per command. Agent skips rows with blank `id` or `type`. Duplicate `id` is not re-executed. |
| `type` | string | Handler name (`ping`, `collect_inventory`, `install_app`, …). |
| `issuedAt` | number | Epoch ms when this server enqueued it. |
| `expiresAt` | number | Epoch ms; agent fails with `expired` if `now >= expiresAt` and `expiresAt > 0`. `0` means no expiry. |
| `payload` | object | Type-specific JSON. Default `{}`. |

Default `expiresAt` is 24 hours after enqueue. Operator may pass a custom `expiresAt` (epoch ms on the API; date/time picker in Django admin). See [Remote ops](remote-ops.md#expires-at).

Ids are `c-1`, `c-2`, … (monotonic counter in SQLite).

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

## Types the agent implements

| `type` | Agent result | Payload (enqueue) |
|---|---|---|
| `ping` | `succeeded` / `pong` | `{}` |
| `collect_inventory` | `succeeded` / `ok` | `{}` — marks inventory due |
| `install_app` | `succeeded` / `installed` | `url` and `sha256` required; optional `packageName` |
| `uninstall_app` | `succeeded` / `uninstalled` or `already absent` | `packageName` required |
| `reboot` | `succeeded` / `reboot scheduled` | optional `delayMs` (default `0`) |
| anything else | `failed` / `unsupported:{type}` | any |

Enqueue validation for the three new types: [Operator API](operator-api.md). This sample does **not** check `capabilities` before enqueue.

### `install_app` payload

```json
{
  "url": "http://10.31.11.228:3000/files/app.apk",
  "sha256": "7c928bb635730f3757ca66e0ab096641dea95be625d245ef619fccf1199cece6",
  "packageName": "com.example.app"
}
```

`sha256` is required. It must be the **SHA-256 digest of the APK file** (`sha256sum app.apk`), not a random value. Details: [Remote ops](remote-ops.md#sha-256-of-the-apk-required).

### `uninstall_app` payload

```json
{ "packageName": "com.example.app" }
```

### `reboot` payload

```json
{ "delayMs": 0 }
```

## Idempotency

- Register: same `serialNumber` → same terminal and token.
- Command `id`: agent-side; retries must not install or reboot twice for the same id.
- Result POST: unknown id is still `204`; known id overwrites stored result.

## Inspecting history

Poll only shows unfinished commands. Full list including results is on `GET /v1/terminals/{id}` ([Operator API](operator-api.md)).
