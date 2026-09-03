import json
import uuid
from contextlib import redirect_stdout
from io import StringIO

from django.contrib import admin
from django.test import Client, TestCase

from .admin import TerminalAdmin
from .models import Command, Terminal, TerminalEvent
from .redaction import REDACTED, redact_obj, redact_text
from .services import enqueue


class ApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.identity = {
            "protocolVersion": 1,
            "serialNumber": "SN-1",
            "vendor": "topwise",
            "model": "T1",
            "firmware": "1",
            "osVersion": "10",
            "agentVersion": "1.0",
            "capabilities": ["ping", "collect_inventory"],
        }
        self.terminal = Terminal.objects.create(
            serial_number=self.identity["serialNumber"],
            identity=self.identity,
            status=Terminal.Status.ACTIVE,
        )
        enqueue(self.terminal, "ping")

    def _json(self, method, path, body=None, auth=None):
        kwargs = {"content_type": "application/json"}
        if body is not None:
            kwargs["data"] = json.dumps(body)
        if auth is not None:
            kwargs["HTTP_AUTHORIZATION"] = auth
        if method == "GET":
            res = self.client.get(path, **kwargs)
        else:
            res = self.client.generic(method, path, **kwargs)
        text = res.content.decode("utf-8") if res.content else ""
        return res.status_code, json.loads(text) if text else None

    def test_register_heartbeat_inventory_poll_result(self):
        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 200)
        self.assertTrue(body["terminalId"])
        self.assertTrue(body["token"])
        tid = body["terminalId"]
        token = body["token"]

        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(tid, body["terminalId"])
        self.assertEqual(code, 200)

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/heartbeat",
            {"protocolVersion": 1, "batteryPercent": 80, "storageFreeBytes": 1, "network": "wifi"},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/inventory",
            {
                "protocolVersion": 1,
                "osVersion": "10",
                "firmware": "1",
                "apps": [{"packageName": "a.b", "versionName": "1.0", "versionCode": 1}],
            },
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/location",
            {
                "protocolVersion": 1,
                "latitude": 34.5,
                "longitude": 69.2,
                "accuracyMeters": 12.5,
                "provider": "network",
                "capturedAt": 1789000000000,
            },
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)
        code, terminal = self._json("GET", f"/v1/terminals/{tid}")
        self.assertEqual(code, 200)
        self.assertEqual(terminal["status"], Terminal.Status.ACTIVE)
        self.assertEqual(terminal["lastLocation"]["latitude"], 34.5)
        self.assertIn("receivedAt", terminal["lastLocation"])

        code, body = self._json("GET", f"/v1/terminals/{tid}/commands", auth=f"Bearer {token}")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["commands"]), 1)
        self.assertEqual(body["commands"][0]["type"], "ping")
        ping_id = body["commands"][0]["id"]

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands/{ping_id}/result",
            {"protocolVersion": 1, "status": "succeeded", "message": "pong", "completedAt": 1},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{tid}/commands", auth=f"Bearer {token}")
        self.assertEqual(body["commands"], [])

        code, body = self._json(
            "POST", f"/v1/terminals/{tid}/commands", {"type": "collect_inventory"}
        )
        self.assertEqual(code, 201)
        code, body = self._json("GET", f"/v1/terminals/{tid}/commands", auth=f"Bearer {token}")
        self.assertEqual(body["commands"][0]["type"], "collect_inventory")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "install_app",
                "payload": {
                    "url": "http://example.com/app.apk",
                    "sha256": "a" * 64,
                },
            },
        )
        self.assertEqual(code, 400)
        self.assertIn("does not support", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "reboot", "payload": {"delayMs": 0}},
        )
        self.assertEqual(code, 400)
        self.assertIn("does not support", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "poweroff", "payload": {"delayMs": 0}},
        )
        self.assertEqual(code, 400)
        self.assertIn("does not support", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "update_agent",
                "payload": {
                    "url": "http://example.com/agent.apk",
                    "sha256": "a" * 64,
                    "packageName": "com.example.tmsmanager",
                },
            },
        )
        self.assertEqual(code, 400)
        self.assertIn("does not support", body["error"])

        full_identity = {
            **self.identity,
            "capabilities": [
                "ping",
                "collect_inventory",
                "install_app",
                "uninstall_app",
                "reboot",
                "poweroff",
                "update_agent",
            ],
        }
        code, body = self._json("POST", "/v1/terminals/register", full_identity)
        self.assertEqual(code, 200)
        self.assertEqual(body["terminalId"], tid)

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "install_app", "payload": {}},
        )
        self.assertEqual(code, 400)

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "install_app",
                "payload": {"url": "http://example.com/app.apk"},
            },
        )
        self.assertEqual(code, 400)
        self.assertIn("sha256", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "install_app",
                "payload": {
                    "url": "http://example.com/app.apk",
                    "sha256": "not-a-valid-hash",
                },
            },
        )
        self.assertEqual(code, 400)
        self.assertIn("sha256 must be 64 hex chars", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "install_app",
                "payload": {
                    "url": "http://example.com/app.apk",
                    "sha256": "a" * 64,
                },
            },
        )
        self.assertEqual(code, 201)
        self.assertEqual(body["type"], "install_app")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "reboot", "payload": {"delayMs": 0}},
        )
        self.assertEqual(code, 201)
        self.assertEqual(body["type"], "reboot")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "poweroff", "payload": {"delayMs": 0}},
        )
        self.assertEqual(code, 201)
        self.assertEqual(body["type"], "poweroff")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {"type": "update_agent", "payload": {}},
        )
        self.assertEqual(code, 400)
        self.assertIn("url required", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "update_agent",
                "payload": {
                    "url": "http://example.com/agent.apk",
                    "sha256": "a" * 64,
                },
            },
        )
        self.assertEqual(code, 400)
        self.assertIn("packageName required", body["error"])

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands",
            {
                "type": "update_agent",
                "payload": {
                    "url": "http://example.com/agent.apk",
                    "sha256": "a" * 64,
                    "packageName": "com.example.tmsmanager",
                },
            },
        )
        self.assertEqual(code, 201)
        self.assertEqual(body["type"], "update_agent")

        code, _ = self._json("POST", f"/v1/terminals/{uuid.uuid4()}/heartbeat", {})
        self.assertEqual(code, 404)

    def test_agent_routes_require_bearer_auth(self):
        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 200)
        tid = body["terminalId"]
        token = body["token"]

        code, body = self._json("GET", f"/v1/terminals/{tid}/commands")
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "unauthorized")

        code, body = self._json(
            "GET",
            f"/v1/terminals/{tid}/commands",
            auth="Bearer wrong-token",
        )
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "unauthorized")

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/heartbeat",
            {"protocolVersion": 1, "network": "wifi"},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/location",
            {"latitude": 34.5, "longitude": 69.2, "provider": "network", "capturedAt": 1},
        )
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "unauthorized")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands/unknown/result",
            {"protocolVersion": 1, "status": "succeeded", "message": "ok", "completedAt": 1},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{uuid.uuid4()}/commands")
        self.assertEqual(code, 404)
        self.assertEqual(body, {"error": "unknown_terminal", "code": "unknown_terminal"})

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/events",
            {"kind": "install_started", "message": "start", "eventAt": 1},
        )
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "unauthorized")

    def test_location_validates_coordinates(self):
        _, registered = self._json("POST", "/v1/terminals/register", self.identity)
        tid, token = registered["terminalId"], registered["token"]
        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/location",
            {"latitude": 100, "longitude": 69.2, "provider": "network", "capturedAt": 1},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 400)
        self.assertEqual(body["error"], "latitude must be between -90 and 90")

    def test_events_endpoint_persists_and_shows_in_terminal_detail(self):
        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 200)
        tid = body["terminalId"]
        token = body["token"]

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/events",
            {
                "protocolVersion": 1,
                "kind": "download_started",
                "level": "info",
                "message": "http://files.example.com/a.apk",
                "commandId": "c-123",
                "eventAt": 1789000000000,
                "meta": {"type": "install_app", "urlHost": "files.example.com"},
            },
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{tid}")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["events"]), 1)
        event = body["events"][0]
        self.assertEqual(event["kind"], "download_started")
        self.assertEqual(event["commandId"], "c-123")
        self.assertEqual(event["meta"]["urlHost"], "files.example.com")

    def test_redaction_helpers(self):
        self.assertEqual(redact_text("normal diagnostic"), "normal diagnostic")
        self.assertNotIn("4111", redact_text("card 4111-1111-1111-1111 failed"))
        self.assertEqual(redact_text("Authorization: Bearer abc.def"), f"Authorization: {REDACTED}")
        redacted = redact_obj({"nested": [{"accessToken": "opaque-value"}], "status": "ok"})
        self.assertEqual(redacted, {"nested": [{"accessToken": REDACTED}], "status": "ok"})

    def test_agent_management_data_is_redacted_before_persistence(self):
        _, registered = self._json("POST", "/v1/terminals/register", self.identity)
        tid, token = registered["terminalId"], registered["token"]
        auth = f"Bearer {token}"

        self._json(
            "POST",
            f"/v1/terminals/{tid}/heartbeat",
            {"diagnostics": {"lastError": "authorization=heartbeat-secret"}},
            auth=auth,
        )
        self._json(
            "POST",
            f"/v1/terminals/{tid}/events",
            {
                "kind": "install_finished",
                "message": "card 4111-1111-1111-1111 failed",
                "meta": {"apiKey": "event-secret", "context": "readable"},
            },
            auth=auth,
        )
        command = Command.objects.filter(terminal__terminal_id=tid).first()
        self._json(
            "POST",
            f"/v1/terminals/{tid}/commands/{command.command_id}/result",
            {"status": "failed", "message": "token=result-secret", "completedAt": 1},
            auth=auth,
        )

        terminal = Terminal.objects.get(terminal_id=tid)
        event = TerminalEvent.objects.get(terminal=terminal)
        command.refresh_from_db()
        self.assertEqual(terminal.last_heartbeat["diagnostics"]["lastError"], f"authorization={REDACTED}")
        self.assertEqual(event.message, f"card {REDACTED} failed")
        self.assertEqual(event.meta, {"apiKey": REDACTED, "context": "readable"})
        self.assertEqual(command.result["message"], f"token={REDACTED}")

    def test_request_and_response_logs_are_redacted(self):
        output = StringIO()
        with redirect_stdout(output):
            _, registered = self._json("POST", "/v1/terminals/register", self.identity)
            self._json(
                "POST",
                f"/v1/terminals/{registered['terminalId']}/events",
                {"kind": "failed", "message": "password=log-secret"},
                auth=f"Bearer {registered['token']}",
            )

        logged = output.getvalue()
        self.assertNotIn(registered["token"], logged)
        self.assertNotIn("log-secret", logged)
        self.assertIn(REDACTED, logged)

    def test_health(self):
        code, body = self._json("GET", "/health")
        self.assertEqual(code, 200)
        self.assertEqual(body, {"ok": True})

    def test_expires_at_conversion(self):
        from datetime import datetime, timezone

        from core.services import dt_to_ms, format_expires_at, ms_to_dt

        dt = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        ms = dt_to_ms(dt)
        self.assertEqual(ms_to_dt(ms), dt)
        self.assertIn("2026", format_expires_at(ms))

    def test_persistence_across_requests(self):
        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        tid = body["terminalId"]
        token = body["token"]

        # simulate restart: new client, same DB
        client2 = Client()
        res = client2.get(f"/v1/terminals/{tid}")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data["terminalId"], tid)

        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(body["terminalId"], tid)
        self.assertEqual(body["token"], token)

    def test_new_terminal_waits_for_approval(self):
        identity = {**self.identity, "serialNumber": "SN-PENDING"}

        code, body = self._json("POST", "/v1/terminals/register", identity)

        self.assertEqual(code, 202)
        self.assertEqual(body["code"], "terminal_pending_approval")
        self.assertNotIn("token", body)
        terminal = Terminal.objects.get(serial_number="SN-PENDING")
        self.assertEqual(terminal.status, Terminal.Status.PENDING)
        self.assertFalse(terminal.commands.exists())

        old_token = terminal.token
        TerminalAdmin(Terminal, admin.site).approve_selected(
            None, Terminal.objects.filter(pk=terminal.pk)
        )
        terminal.refresh_from_db()
        self.assertEqual(terminal.status, Terminal.Status.ACTIVE)
        self.assertNotEqual(terminal.token, old_token)
        self.assertEqual(terminal.commands.filter(type="ping").count(), 1)
        TerminalAdmin(Terminal, admin.site).approve_selected(
            None, Terminal.objects.filter(pk=terminal.pk)
        )
        self.assertEqual(terminal.commands.filter(type="ping").count(), 1)

        code, body = self._json("POST", "/v1/terminals/register", identity)
        self.assertEqual(code, 200)
        self.assertEqual(body["terminalId"], str(terminal.terminal_id))
        self.assertEqual(body["token"], str(terminal.token))

    def test_revoke_preserves_history_and_allows_pending_reenrollment(self):
        token = self.terminal.token
        TerminalEvent.objects.create(
            terminal=self.terminal,
            kind="before_revoke",
            message="kept",
            event_at=1,
            received_at=1,
        )

        TerminalAdmin(Terminal, admin.site).revoke_selected(
            None, Terminal.objects.filter(pk=self.terminal.pk)
        )

        code, body = self._json(
            "GET",
            f"/v1/terminals/{self.terminal.terminal_id}/commands",
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 401)
        self.assertEqual(body["code"], "terminal_revoked")

        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 202)
        self.assertEqual(body["code"], "terminal_pending_approval")
        self.terminal.refresh_from_db()
        self.assertEqual(self.terminal.status, Terminal.Status.PENDING)
        self.assertTrue(self.terminal.commands.exists())
        self.assertTrue(self.terminal.events.exists())

        code, body = self._json(
            "POST",
            f"/v1/terminals/{self.terminal.terminal_id}/commands",
            {"type": "ping"},
        )
        self.assertEqual(code, 400)
        self.assertEqual(body["error"], "terminal is not active")

    def test_decommission_blocks_routes_and_registration_until_reenrollment_allowed(self):
        token = self.terminal.token
        terminal_admin = TerminalAdmin(Terminal, admin.site)
        queryset = Terminal.objects.filter(pk=self.terminal.pk)
        terminal_admin.decommission_selected(None, queryset)

        code, body = self._json(
            "POST",
            f"/v1/terminals/{self.terminal.terminal_id}/heartbeat",
            {},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 403)
        self.assertEqual(body["code"], "terminal_decommissioned")

        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 403)
        self.assertEqual(body["code"], "terminal_decommissioned")

        terminal_admin.allow_reenrollment(None, queryset)
        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(code, 202)
        self.assertEqual(body["code"], "terminal_pending_approval")
        self.assertFalse(terminal_admin.has_delete_permission(None, self.terminal))
