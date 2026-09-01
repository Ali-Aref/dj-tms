import json
import time

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Command, Terminal
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
    if not created:
        terminal.identity = body
        terminal.save(update_fields=["identity"])
    else:
        enqueue(terminal, "ping")
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
    terminal = Terminal.objects.prefetch_related("commands").get(pk=terminal.pk)
    return JsonResponse(terminal_view(terminal))


@csrf_exempt
@require_http_methods(["POST"])
def heartbeat(request, terminal_id):
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse({"error": "unknown terminal"}, status=404)
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    terminal.last_heartbeat = {**body, "receivedAt": int(time.time() * 1000)}
    terminal.save(update_fields=["last_heartbeat"])
    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["POST"])
def inventory(request, terminal_id):
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse({"error": "unknown terminal"}, status=404)
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    terminal.last_inventory = {**body, "receivedAt": int(time.time() * 1000)}
    terminal.save(update_fields=["last_inventory"])
    return HttpResponse(status=204)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def commands(request, terminal_id):
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse({"error": "unknown terminal"}, status=404)
    if request.method == "GET":
        pending = terminal.commands.filter(result__isnull=True)
        return JsonResponse(
            {"commands": [command_view(c, include_result=False) for c in pending]}
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
    terminal = _terminal_or_404(terminal_id)
    if not terminal:
        return JsonResponse({"error": "unknown terminal"}, status=404)
    try:
        body = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    result = {
        "protocolVersion": body.get("protocolVersion"),
        "status": body.get("status"),
        "message": body.get("message"),
        "completedAt": body.get("completedAt"),
        "receivedAt": int(time.time() * 1000),
    }
    cmd = Command.objects.filter(terminal=terminal, command_id=command_id).first()
    if cmd:
        cmd.status = result.get("status") or "succeeded"
        cmd.result = result
        cmd.save(update_fields=["status", "result"])
    return HttpResponse(status=204)
