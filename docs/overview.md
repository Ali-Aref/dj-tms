# Overview

TMSExpress is the sample backend in this repo. The product TMS is a separate system. This process exists so the Android agent can be tested and so a real backend can copy the HTTP shapes.

Canonical agent intent lives in TMSManager `llm/purpose.md`. This sample covers registration, heartbeat, inventory, latest-location reporting, command delivery, and result reporting.

## Design choices

| Choice | Behavior |
|---|---|
| Approved enrollment | New serials remain pending until approved. Only active terminals receive a bearer token. |
| Vendor-neutral | No Topwise / PAX SDK. Identity fields (`vendor`, `model`, `firmware`) are stored as JSON. |
| Retained lifecycle | SQLite keeps terminal identity, commands, and events across pending, active, deleted, and decommissioned states. Lifecycle changes rotate the token. |
| Observability | Agents can post install/update lifecycle events to `/v1/terminals/{id}/events`; latest events are visible in terminal detail. |
| Latest location | Agents can post location to `/v1/terminals/{id}/location`; only the latest accepted report is stored. |
| Outbound poll | The device calls the server. There is no push or MQTT. |
| Protocol v1 | `protocolVersion: 1` on agent bodies. The server does not reject other values. |
| Django admin | Browse terminals, last heartbeat/inventory/location, enqueue commands. Staff login only; no agent auth. |
| Management-data redaction | Sensitive-like heartbeat diagnostics, events, results, and HTTP body logs are masked with `[REDACTED]` before storage/output. |

## What the agent does each tick (~60s)

1. `POST /terminals/register` if it has no stored credentials. New/deleted terminals wait for approval; decommissioned terminals stop until manual re-enrollment.
2. `POST .../heartbeat`.
3. Drain its result outbox (`POST .../commands/:id/result`).
4. `GET .../commands`, run each new id locally, enqueue results, drain again.
5. `POST .../inventory` after first register, every 6 hours, or after a successful `collect_inventory`.
6. `POST .../location` every 15 minutes when device background location permission is granted. Location upload failures retry at 2m, 4m, 8m, then 15m without changing the heartbeat/poll schedule.

Approval enqueues a `ping` so the first active poll proves command delivery. Delete/revoke retains history and permits a new pending request; decommission blocks registration until an operator selects **Allow re-enrollment**. Details: [Agent API](agent-api.md), [Commands](commands.md).

## What a production TMS should add

Not implemented here, on purpose:

- External immutable lifecycle audit records when compliance requires them.
- Sign packages; firmware OTA only after silent install is proven on hardware.
- Never put payment data, PINs, or plaintext keys in these messages or in logs.
