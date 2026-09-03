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

Open `http://<host>:3000/admin/`. Terminals show serial, lifecycle status, vendor, model, last heartbeat, and last location (`lat, lng (provider)`). Open a terminal to see its details. Add commands from **Commands** or the terminal inline; only active terminals accept them.

Terminal lifecycle actions are available from **Admin → Terminals**:

1. A new POS appears as `pending`; select it and run **Approve selected terminals**. Approval rotates its token and queues the initial `ping`.
2. **Delete / revoke selected terminals** revokes credentials but retains history. Its next registration request becomes pending and needs approval.
3. **Decommission selected terminals** blocks the POS. It remains blocked without repeated network calls.
4. To recover a decommissioned POS, run **Allow selected terminals to request re-enrollment**, then use **Request re-enrollment** on the POS. Approve the resulting pending terminal.

Normal hard delete is disabled in admin so commands, events, and audit context are retained.

For **install**, **uninstall**, **reboot**, and **agent update** walkthroughs see [Remote ops](remote-ops.md). `install_app` and `update_agent` require `url` and `sha256` in the payload.

## Point the agent at this server

In TMSManager, `TMS_BASE_URL` must already include `/v1`, for example:

```text
http://10.31.11.228:3000/v1
```

The POS and this machine must be on the same network. `localhost` on the device is the device itself, not this PC.

On first contact you should see register `202`; approve the pending row. The next agent retry receives credentials, then sends heartbeat → polls `ping` → reports result → sends inventory. After background location permission is granted, location reports approximately every 15 minutes. Confirm them in the terminal's **last location** field. The POS should then show Registered yes, a terminal id, Last sync advancing, and no Last error.

| POS message | Meaning | Action |
|---|---|---|
| `pending approval` | Enrollment exists but is not active. | Approve it in Django admin; the POS retries at 2m, 4m, 8m, then every 15m. |
| `removed by admin` | Token/enrollment was revoked. | Approve the new pending request when the POS registers again. |
| `terminal registration lost` | The terminal id was unknown for three consecutive ticks. | Check for database loss, then approve the replacement enrollment. |
| `decommissioned` | Registration is deliberately blocked. | Allow re-enrollment in admin, then request it locally on the POS. |

## Logging

Every request prints method, path, status, duration, JSON body in, JSON body out. `204` responses log `res null`.

```text
POST /v1/terminals/register 200 1ms
  req {"protocolVersion":1,"serialNumber":"...","vendor":"topwise",...}
  res {"terminalId":"...","token":"..."}
```

Restarting the server keeps terminals in SQLite. Active terminals keep working; lifecycle actions rotate credentials as documented above.

## Content type

JSON endpoints expect `Content-Type: application/json`. Bodies over 1 MB are rejected.
