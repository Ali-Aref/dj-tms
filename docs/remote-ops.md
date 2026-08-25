# Install, uninstall, and reboot

How to push sensitive commands from TMSExpress to a POS. The agent polls about every **60 seconds**, so expect up to one minute before work starts.

Full payload rules: [Commands](commands.md). API reference: [Operator API](operator-api.md).

## How it works

1. You enqueue a command (Django admin or `POST /v1/terminals/{id}/commands`).
2. The POS polls `GET .../commands` on its next tick.
3. The agent runs the handler locally and posts `POST .../commands/{id}/result`.
4. You see the outcome in admin (**result** field) or server logs.

## Expires at

Every command has an **expiry**. If the POS does not pick it up before then, the agent runs it once but immediately reports **`failed` / `expired`** without installing or rebooting.

| Where | Format |
|---|---|
| Wire API (`expiresAt`) | Epoch milliseconds (number), e.g. `1787724797396` |
| Django admin | **Expires at** date + time picker (local timezone). Default suggestion: now + 24h. Leave blank → server sets enqueue time + 24h. |

Use a shorter expiry for one-shot ops (reboot now). Use a longer window if the device might be offline for a while.

## Prerequisites

- TMS running: `python manage.py runserver 0.0.0.0:3000`
- POS registered (`TMS_BASE_URL` = `http://<host>:3000/v1`)
- Terminal id from **Admin → Terminals** or `GET /v1/terminals`

---

## Install app (`install_app`)

The agent **downloads the APK** from `url`, optionally checks SHA-256, then commits install via `PackageInstaller`.

### 1. Host the APK

TMSExpress does not serve APKs by default. Put the file somewhere the **POS can reach** on your LAN:

```bash
cd /path/to/apk-folder
python -m http.server 8000
```

Use `http://<your-pc-ip>:8000/myapp.apk` in the command (not `localhost` — that is the device itself).

Optional: compute SHA-256 and pass it so a tampered download fails before install:

```bash
sha256sum myapp.apk
```

### 2. Enqueue via admin

**Admin → Commands → Add command**

| Field | Example |
|---|---|
| Terminal | your POS |
| Type | `install_app` |
| Payload | see below |
| Expires at | leave default or pick a deadline |

```json
{
  "url": "http://10.31.11.228:8000/myapp.apk",
  "sha256": "optional 64 hex chars",
  "packageName": "com.example.myapp"
}
```

### 3. Enqueue via curl

```bash
ID="<terminal-uuid>"
curl -s -X POST "http://HOST:3000/v1/terminals/$ID/commands" \
  -H 'content-type: application/json' \
  -d '{
    "type": "install_app",
    "payload": {
      "url": "http://HOST:8000/myapp.apk",
      "packageName": "com.example.myapp"
    }
  }'
```

### 4. Success signals

- Result message: `install committed` (or vendor-specific text)
- Inventory refresh on next tick shows the new package

**Note:** Standard `PackageInstaller` may show a system prompt unless the device is device-owner or uses the Topwise silent-install SDK.

---

## Uninstall app (`uninstall_app`)

### Admin

| Field | Value |
|---|---|
| Type | `uninstall_app` |
| Payload | `{"packageName": "com.example.myapp"}` |

Package name must match an installed app (see terminal **last inventory** in admin or `GET /v1/terminals/{id}`).

### curl

```bash
curl -s -X POST "http://HOST:3000/v1/terminals/$ID/commands" \
  -H 'content-type: application/json' \
  -d '{"type":"uninstall_app","payload":{"packageName":"com.example.myapp"}}'
```

If the package is already gone, the agent still reports **`succeeded` / `already absent`**.

---

## Reboot (`reboot`)

### Admin

| Field | Value |
|---|---|
| Type | `reboot` |
| Payload | `{}` or `{"delayMs": 5000}` |

`delayMs` is optional (default `0`). The agent posts the result first, then reboots after the delay.

### curl

```bash
curl -s -X POST "http://HOST:3000/v1/terminals/$ID/commands" \
  -H 'content-type: application/json' \
  -d '{"type":"reboot","payload":{"delayMs":0}}'
```

Result: **`succeeded` / `reboot scheduled`**, then the device restarts.

**Note:** Reboot needs platform permission; some locked firmware may reject it until vendor APIs are wired.

---

## Quick reference

| Type | Required payload | Typical result |
|---|---|---|
| `install_app` | `url` | `install committed` |
| `uninstall_app` | `packageName` | `uninstall committed` or `already absent` |
| `reboot` | none (`delayMs` optional) | `reboot scheduled` |

## Troubleshooting

| Symptom | Check |
|---|---|
| Command stays pending | POS polling? `Last sync` on device UI? Same LAN / URL? |
| `expired` | Expires at was in the past before the device polled |
| `install_app: url required` | Payload JSON missing `url` |
| Download fails | APK URL reachable from POS (try browser on device) |
| `sha256 mismatch` | Wrong hash or file changed |
| Install prompt on device | Expected without silent-install / device-owner |
