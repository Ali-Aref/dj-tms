# Overview

TMSExpress is the sample backend in this repo. The product TMS is a separate system. This process exists so the Android agent can be tested and so a real backend can copy the HTTP shapes.

Canonical agent intent lives in TMSManager `llm/purpose.md`. This sample covers only the v1 foundation: registration, heartbeat, inventory, command delivery, and result reporting.

## Design choices

| Choice | Behavior |
|---|---|
| No auth | Register still returns a `token` because the agent requires it. The server never checks `Authorization`. |
| Vendor-neutral | No Topwise / PAX SDK. Identity fields (`vendor`, `model`, `firmware`) are stored as JSON. |
| In memory | Terminals and commands are a `Map`. Restart wipes everything. The agent then gets HTTP 404 and should re-register. |
| Outbound poll | The device calls the server. There is no push or MQTT. |
| Protocol v1 | `protocolVersion: 1` on agent bodies. The server does not reject other values. |

## What the agent does each tick (~60s)

1. `POST /terminals/register` if it has no stored `terminalId` + `token`.
2. `POST .../heartbeat`.
3. Drain its result outbox (`POST .../commands/:id/result`).
4. `GET .../commands`, run each new id locally, enqueue results, drain again.
5. `POST .../inventory` after first register, every 6 hours, or after a successful `collect_inventory`.

First register in this sample also enqueues a `ping` so the first poll proves command delivery. Details: [Agent API](agent-api.md), [Commands](commands.md).

## What a production TMS should add

Not implemented here, on purpose:

- Verify bearer tokens; rotate and revoke them.
- Persist terminals and command history.
- Check `capabilities` before enqueueing a type the agent does not support.
- Sign packages; install / reboot / firmware only after the foundation is reliable.
- Never put payment data, PINs, or plaintext keys in these messages or in logs.
