import json
import uuid
from contextlib import redirect_stdout
from io import StringIO

from django.test import Client, TestCase

from .models import Command, Terminal, TerminalEvent
from .redaction import REDACTED, redact_obj, redact_text


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
            f"/v1/terminals/{tid}/commands/unknown/result",
            {"protocolVersion": 1, "status": "succeeded", "message": "ok", "completedAt": 1},
            auth=f"Bearer {token}",
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{uuid.uuid4()}/commands")
        self.assertEqual(code, 404)
        self.assertEqual(body["error"], "unknown terminal")

        code, body = self._json(
            "POST",
            f"/v1/terminals/{tid}/events",
            {"kind": "install_started", "message": "start", "eventAt": 1},
        )
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "unauthorized")

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
