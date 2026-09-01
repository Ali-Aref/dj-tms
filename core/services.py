import re
import time
from datetime import datetime, timezone

from django.db import transaction
from django.utils import timezone as dj_tz

from .models import Command, CommandSeq, Terminal

DAY_MS = 24 * 60 * 60 * 1000

COMMAND_CAPABILITIES = {
    "ping": "ping",
    "collect_inventory": "collect_inventory",
    "install_app": "install_app",
    "uninstall_app": "uninstall_app",
    "reboot": "reboot",
    "update_agent": "update_agent",
}


def ms_to_dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def dt_to_ms(dt):
    if dt is None:
        return None
    if dj_tz.is_naive(dt):
        dt = dj_tz.make_aware(dt)
    return int(dt.timestamp() * 1000)


def format_expires_at(ms):
    if not ms:
        return "-"
    return dj_tz.localtime(ms_to_dt(ms)).strftime("%Y-%m-%d %H:%M %Z")


def validate_enqueue_payload(cmd_type, payload):
    if payload is None or not isinstance(payload, dict):
        return "payload must be an object"
    if cmd_type == "install_app":
        url = payload.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return "install_app: url required"
        if not re.match(r"^https?://", url.strip(), re.I):
            return "install_app: url must be http or https"
        sha = payload.get("sha256")
        if not sha or not isinstance(sha, str) or not sha.strip():
            return "install_app: sha256 required"
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha.strip()):
            return "install_app: sha256 must be 64 hex chars"
        pkg = payload.get("packageName")
        if pkg is not None and not isinstance(pkg, str):
            return "install_app: packageName must be a string"
        return None
    if cmd_type == "uninstall_app":
        pkg = payload.get("packageName")
        if not pkg or not isinstance(pkg, str) or not pkg.strip():
            return "uninstall_app: packageName required"
        return None
    if cmd_type == "reboot":
        delay = payload.get("delayMs")
        if delay is not None and (not isinstance(delay, (int, float)) or delay < 0):
            return "reboot: delayMs must be a number >= 0"
        return None
    if cmd_type == "update_agent":
        url = payload.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return "update_agent: url required"
        if not re.match(r"^https?://", url.strip(), re.I):
            return "update_agent: url must be http or https"
        sha = payload.get("sha256")
        if not sha or not isinstance(sha, str) or not sha.strip():
            return "update_agent: sha256 required"
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha.strip()):
            return "update_agent: sha256 must be 64 hex chars"
        pkg = payload.get("packageName")
        if not pkg or not isinstance(pkg, str) or not pkg.strip():
            return "update_agent: packageName required"
        return None
    return None


def validate_terminal_capability(terminal, cmd_type):
    needed = COMMAND_CAPABILITIES.get(cmd_type)
    if needed is None:
        return f"unsupported type: {cmd_type}"
    caps = (terminal.identity or {}).get("capabilities") or []
    if needed not in caps:
        return f"terminal does not support {cmd_type}"
    return None


def enqueue(terminal, cmd_type, payload=None, expires_at=None):
    now = int(time.time() * 1000)
    with transaction.atomic():
        seq = CommandSeq.next_id()
    cmd = Command.objects.create(
        command_id=seq,
        terminal=terminal,
        type=cmd_type,
        payload=payload or {},
        issued_at=now,
        expires_at=expires_at if expires_at is not None else now + DAY_MS,
        status="pending",
        result=None,
    )
    return cmd


def terminal_view(terminal):
    return {
        "terminalId": str(terminal.terminal_id),
        "identity": terminal.identity,
        "lastHeartbeat": terminal.last_heartbeat,
        "lastInventory": terminal.last_inventory,
        "commands": [command_view(c) for c in terminal.commands.all()],
    }


def command_view(cmd, *, include_result=True):
    out = {
        "id": cmd.command_id,
        "type": cmd.type,
        "issuedAt": cmd.issued_at,
        "expiresAt": cmd.expires_at,
        "payload": cmd.payload,
    }
    if include_result:
        out["status"] = cmd.status
        out["result"] = cmd.result
    return out


# attach next_id to CommandSeq
def _next_id():
    with transaction.atomic():
        row, _ = CommandSeq.objects.select_for_update().get_or_create(pk=1, defaults={"n": 0})
        row.n += 1
        row.save(update_fields=["n"])
        return f"c-{row.n}"


CommandSeq.next_id = staticmethod(_next_id)
