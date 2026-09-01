import json
import uuid

from django.test import Client, TestCase


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

    def _json(self, method, path, body=None):
        kwargs = {"content_type": "application/json"}
        if body is not None:
            kwargs["data"] = json.dumps(body)
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

        code, body = self._json("POST", "/v1/terminals/register", self.identity)
        self.assertEqual(tid, body["terminalId"])
        self.assertEqual(code, 200)

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/heartbeat",
            {"protocolVersion": 1, "batteryPercent": 80, "storageFreeBytes": 1, "network": "wifi"},
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
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{tid}/commands")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["commands"]), 1)
        self.assertEqual(body["commands"][0]["type"], "ping")
        ping_id = body["commands"][0]["id"]

        code, _ = self._json(
            "POST",
            f"/v1/terminals/{tid}/commands/{ping_id}/result",
            {"protocolVersion": 1, "status": "succeeded", "message": "pong", "completedAt": 1},
        )
        self.assertEqual(code, 204)

        code, body = self._json("GET", f"/v1/terminals/{tid}/commands")
        self.assertEqual(body["commands"], [])

        code, body = self._json(
            "POST", f"/v1/terminals/{tid}/commands", {"type": "collect_inventory"}
        )
        self.assertEqual(code, 201)
        code, body = self._json("GET", f"/v1/terminals/{tid}/commands")
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

        full_identity = {
            **self.identity,
            "capabilities": [
                "ping",
                "collect_inventory",
                "install_app",
                "uninstall_app",
                "reboot",
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

        code, _ = self._json("POST", f"/v1/terminals/{uuid.uuid4()}/heartbeat", {})
        self.assertEqual(code, 404)

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
