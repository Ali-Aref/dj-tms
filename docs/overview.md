# Overview

TMSExpress is the sample backend in this repo. The product TMS is a separate system. This process exists so the Android agent can be tested and so a real backend can copy the HTTP shapes.

Canonical agent intent lives in TMSManager `llm/purpose.md`. This sample covers registration, heartbeat, inventory, latest-location reporting, command delivery, and result reporting.

## Design choices

| Choice | Behavior |
|---|---|
| Bearer auth on agent routes | Register returns a `token`; terminal-scoped agent routes require `Authorization: Bearer {token}` for known terminals. |
| Vendor-neutral | No Topwise / PAX SDK. Identity fields (`vendor`, `model`, `firmware`) are stored as JSON. |
| SQLite | Terminals and commands survive restart in `db.sqlite3`. Same `serialNumber` → same `terminalId` and `token`. |
| Observability | Agents can post install/update lifecycle events to `/v1/terminals/{id}/events`; latest events are visible in terminal detail. |
| Latest location | Agents can post location to `/v1/terminals/{id}/location`; only the latest accepted report is stored. |
| Outbound poll | The device calls the server. There is no push or MQTT. |
| Protocol v1 | `protocolVersion: 1` on agent bodies. The server does not reject other values. |
| Django admin | Browse terminals, last heartbeat/inventory/location, enqueue commands. Staff login only; no agent auth. |
| Management-data redaction | Sensitive-like heartbeat diagnostics, events, results, and HTTP body logs are masked with `[REDACTED]` before storage/output. |

## What the agent does each tick (~60s)

1. `POST /terminals/register` if it has no stored `terminalId` + `token`.
2. `POST .../heartbeat`.
3. Drain its result outbox (`POST .../commands/:id/result`).
4. `GET .../commands`, run each new id locally, enqueue results, drain again.
5. `POST .../inventory` after first register, every 6 hours, or after a successful `collect_inventory`.
6. `POST .../location` every 15 minutes when device background location permission is granted. Location upload failures retry at 2m, 4m, 8m, then 15m without changing the heartbeat/poll schedule.

First register in this sample also enqueues a `ping` so the first poll proves command delivery. Details: [Agent API](agent-api.md), [Commands](commands.md).

## What a production TMS should add

Not implemented here, on purpose:

- Rotate and revoke bearer tokens.
- Check `capabilities` before enqueueing a type the agent does not support.
- Sign packages; firmware OTA only after silent install is proven on hardware.
- Never put payment data, PINs, or plaintext keys in these messages or in logs.
