# Running

```bash
npm install
npm start
```

Listens on `0.0.0.0:3000`. Override with `PORT`.

```bash
PORT=8080 npm start
```

Self-check (does not need a device):

```bash
npm run check
```

## Point the agent at this server

In TMSManager, `TMS_BASE_URL` must already include `/v1`, for example:

```text
http://10.31.11.228:3000/v1
```

The POS and this machine must be on the same network. `localhost` on the device is the device itself, not this PC.

On a successful first tick you should see register → heartbeat → poll (`ping`) → result → inventory, then heartbeat + empty polls. The status screen should show Registered yes, a terminal id, Last sync advancing, Last error empty.

## Logging

Every request prints method, path, status, duration, JSON body in, JSON body out. `204` responses log `res null`.

```text
POST /v1/terminals/register 200 1ms
  req {"protocolVersion":1,"serialNumber":"...","vendor":"topwise",...}
  res {"terminalId":"...","token":"..."}
```

Restarting the process drops all terminals. The next agent call to heartbeat/poll/inventory returns `404 unknown terminal`. The agent treats that as lost credentials and registers again.

## Content type

JSON endpoints expect `Content-Type: application/json`. Bodies over 1 MB are rejected by Express.
