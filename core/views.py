import json
import math
import time

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Command, Terminal, TerminalEvent
from .redaction import redact_obj, redact_text
from .services import (
    command_view,
    enqueue,
    terminal_view,
    validate_enqueue_payload,
    validate_terminal_capability,
)


def _json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _terminal_or_404(terminal_id):
    try:
        return Terminal.objects.get(terminal_id=terminal_id)
    except Terminal.DoesNotExist:
        return None


def _bearer_token(request):
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    return token or None


def _terminal_and_auth_or_error(request, terminal_id):
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return None, JsonResponse(
            {"error": "unknown_terminal", "code": "unknown_terminal"}, status=404
        )
    if terminal.status == Terminal.Status.DECOMMISSIONED:
        return None, JsonResponse(
            {"error": "terminal_blocked", "code": "terminal_decommissioned"}, status=403
        )
    if terminal.status != Terminal.Status.ACTIVE:
        return None, JsonResponse(
            {"error": "unauthorized", "code": "terminal_revoked"}, status=401
        )
    token = _bearer_token(request)
    if token != str(terminal.token):
        return None, JsonResponse(
            {"error": "unauthorized", "code": "terminal_revoked"}, status=401
        )
    return terminal, None


@csrf_exempt
@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    serial = body.get("serialNumber")
    if not serial or not isinstance(serial, str):
        return JsonResponse({"error": "serialNumber required"}, status=400)
    terminal, created = Terminal.objects.get_or_create(
        serial_number=serial,
        defaults={"identity": body},
    )
    if terminal.status == Terminal.Status.DECOMMISSIONED:
        return JsonResponse(
            {"error": "terminal_blocked", "code": "terminal_decommissioned"}, status=403
        )
    terminal.identity = body
    if terminal.status == Terminal.Status.DELETED:
        terminal.status = Terminal.Status.PENDING
        terminal.save(update_fields=["identity", "status"])
    elif not created:
        terminal.save(update_fields=["identity"])
    if terminal.status == Terminal.Status.PENDING:
        return JsonResponse(
            {"error": "pending approval", "code": "terminal_pending_approval"}, status=202
        )
    return JsonResponse({"terminalId": str(terminal.terminal_id), "token": str(terminal.token)})


@csrf_exempt
@require_http_methods(["GET"])
def terminal_list(request):
    terminals = Terminal.objects.prefetch_related("commands").all()
    return JsonResponse({"terminals": [terminal_view(t) for t in terminals]})


@csrf_exempt
@require_http_methods(["GET"])
def terminal_detail(request, terminal_id):
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse({"error": "unknown terminal"}, status=404)
    terminal = Terminal.objects.prefetch_related("commands", "events").get(pk=terminal.pk)
    return JsonResponse(terminal_view(terminal, include_events=True))


@csrf_exempt
@require_http_methods(["POST"])
def heartbeat(request, terminal_id):
    terminal, error = _terminal_and_auth_or_error(request, terminal_id)
    if error:
        return error
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    terminal.last_heartbeat = {**redact_obj(body), "receivedAt": int(time.time() * 1000)}
    terminal.save(update_fields=["last_heartbeat"])
    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["POST"])
def inventory(request, terminal_id):
    terminal, error = _terminal_and_auth_or_error(request, terminal_id)
    if error:
        return error
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    terminal.last_inventory = {**body, "receivedAt": int(time.time() * 1000)}
    terminal.save(update_fields=["last_inventory"])
    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["POST"])
def location(request, terminal_id):
    terminal, error = _terminal_and_auth_or_error(request, terminal_id)
    if error:
        return error
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    latitude = body.get("latitude")
    longitude = body.get("longitude")
    accuracy = body.get("accuracyMeters")
    provider = body.get("provider")
    captured_at = body.get("capturedAt")
    if not _number(latitude) or not -90 <= latitude <= 90:
        return JsonResponse({"error": "latitude must be between -90 and 90"}, status=400)
    if not _number(longitude) or not -180 <= longitude <= 180:
        return JsonResponse({"error": "longitude must be between -180 and 180"}, status=400)
    if accuracy is not None and (not _number(accuracy) or accuracy < 0):
        return JsonResponse({"error": "accuracyMeters must be non-negative"}, status=400)
    if not isinstance(provider, str) or not provider.strip():
        return JsonResponse({"error": "provider required"}, status=400)
    if not _number(captured_at):
        return JsonResponse({"error": "capturedAt required"}, status=400)

    terminal.last_location = {
        "protocolVersion": body.get("protocolVersion"),
        "latitude": latitude,
        "longitude": longitude,
        "accuracyMeters": accuracy,
        "provider": provider.strip(),
        "capturedAt": int(captured_at),
        "receivedAt": int(time.time() * 1000),
    }
    terminal.save(update_fields=["last_location"])
    return HttpResponse(status=204)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def commands(request, terminal_id):
    if request.method == "GET":
        terminal, error = _terminal_and_auth_or_error(request, terminal_id)
        if error:
            return error
        pending = terminal.commands.filter(result__isnull=True)
        return JsonResponse(
            {"commands": [command_view(c, include_result=False) for c in pending]}
        )
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse(
            {"error": "unknown_terminal", "code": "unknown_terminal"}, status=404
        )
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    cmd_type = body.get("type")
    if not cmd_type or not isinstance(cmd_type, str):
        return JsonResponse({"error": "type required"}, status=400)
    cap_err = validate_terminal_capability(terminal, cmd_type)
    if cap_err:
        return JsonResponse({"error": cap_err}, status=400)
    payload = body.get("payload") or {}
    err = validate_enqueue_payload(cmd_type, payload)
    if err:
        return JsonResponse({"error": err}, status=400)
    cmd = enqueue(terminal, cmd_type, payload, body.get("expiresAt"))
    return JsonResponse(command_view(cmd), status=201)


@csrf_exempt
@require_http_methods(["POST"])
def command_result(request, terminal_id, command_id):
    terminal, error = _terminal_and_auth_or_error(request, terminal_id)
    if error:
        return error
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    result = redact_obj({
        "protocolVersion": body.get("protocolVersion"),
        "status": body.get("status"),
        "message": body.get("message"),
        "completedAt": body.get("completedAt"),
        "receivedAt": int(time.time() * 1000),
    })
    cmd = Command.objects.filter(terminal=terminal, command_id=command_id).first()
    if cmd:
        cmd.status = result.get("status") or "succeeded"
        cmd.result = result
        cmd.save(update_fields=["status", "result"])
    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["POST"])
def terminal_event(request, terminal_id):
    terminal, error = _terminal_and_auth_or_error(request, terminal_id)
    if error:
        return error
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    kind = body.get("kind")
    message = body.get("message")
    level = body.get("level") or "info"
    command_id = body.get("commandId") or ""
    meta = body.get("meta") or {}
    event_at = body.get("eventAt")

    if not kind or not isinstance(kind, str):
        return JsonResponse({"error": "kind required"}, status=400)
    if not message or not isinstance(message, str):
        return JsonResponse({"error": "message required"}, status=400)
    if not isinstance(level, str):
        return JsonResponse({"error": "level must be a string"}, status=400)
    if command_id and not isinstance(command_id, str):
        return JsonResponse({"error": "commandId must be a string"}, status=400)
    if not isinstance(meta, dict):
        return JsonResponse({"error": "meta must be an object"}, status=400)

    now = int(time.time() * 1000)
    if not isinstance(event_at, (int, float)):
        event_at = now

    TerminalEvent.objects.create(
        terminal=terminal,
        command_id=command_id.strip(),
        kind=kind.strip(),
        level=level.strip() or "info",
        message=redact_text(message),
        meta=redact_obj(meta),
        event_at=int(event_at),
        received_at=now,
    )
    return HttpResponse(status=204)
