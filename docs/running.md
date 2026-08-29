# Running

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:3000
```

Listens on `0.0.0.0:3000` by default.

Self-check (does not need a device):

```bash
python manage.py test
```

## Django admin

Create a staff user once:

```bash
python manage.py createsuperuser
```

Open `http://<host>:3000/admin/`. Terminals show serial, vendor, model, last heartbeat. Add commands from **Commands** or the terminal inline. Payload validation matches the operator API.

For **install**, **uninstall**, and **reboot** walkthroughs see [Remote ops](remote-ops.md). `install_app` requires `url` and `sha256` in the payload.

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

Restarting the server keeps terminals in SQLite. The agent keeps using the same `terminalId` and `token` after re-register with the same serial.

## Content type

JSON endpoints expect `Content-Type: application/json`. Bodies over 1 MB are rejected.
