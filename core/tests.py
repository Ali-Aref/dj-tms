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
            {"type": "install_app", "payload": {}},
        )
        self.assertEqual(code, 400)

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
