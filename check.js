import assert from "node:assert/strict";
import { createApp, createStore } from "./server.js";

const store = createStore();
const app = createApp(store);
const server = app.listen(0);
const { port } = server.address();
const base = `http://127.0.0.1:${port}/v1`;

async function json(method, path, body) {
  const res = await fetch(base + path, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

try {
  const identity = {
    protocolVersion: 1,
    serialNumber: "SN-1",
    vendor: "topwise",
    model: "T1",
    firmware: "1",
    osVersion: "10",
    agentVersion: "1.0",
    capabilities: ["ping", "collect_inventory"],
  };

  const a = await json("POST", "/terminals/register", identity);
  assert.equal(a.status, 200);
  assert.ok(a.body.terminalId);
  assert.ok(a.body.token);
  const id = a.body.terminalId;

  const again = await json("POST", "/terminals/register", identity);
  assert.equal(again.body.terminalId, id);
  assert.equal(again.body.token, a.body.token);

  const hb = await json("POST", `/terminals/${id}/heartbeat`, {
    protocolVersion: 1,
    batteryPercent: 80,
    storageFreeBytes: 1,
    network: "wifi",
  });
  assert.equal(hb.status, 204);

  const inv = await json("POST", `/terminals/${id}/inventory`, {
    protocolVersion: 1,
    osVersion: "10",
    firmware: "1",
    apps: [{ packageName: "a.b", versionName: "1.0", versionCode: 1 }],
  });
  assert.equal(inv.status, 204);

  const poll1 = await json("GET", `/terminals/${id}/commands`);
  assert.equal(poll1.status, 200);
  assert.equal(poll1.body.commands.length, 1);
  assert.equal(poll1.body.commands[0].type, "ping");
  const pingId = poll1.body.commands[0].id;

  const result = await json("POST", `/terminals/${id}/commands/${pingId}/result`, {
    protocolVersion: 1,
    status: "succeeded",
    message: "pong",
    completedAt: Date.now(),
  });
  assert.equal(result.status, 204);

  const poll2 = await json("GET", `/terminals/${id}/commands`);
  assert.equal(poll2.body.commands.length, 0);

  const enq = await json("POST", `/terminals/${id}/commands`, { type: "collect_inventory" });
  assert.equal(enq.status, 201);
  const poll3 = await json("GET", `/terminals/${id}/commands`);
  assert.equal(poll3.body.commands[0].type, "collect_inventory");

  const missing = await json("POST", "/terminals/nope/heartbeat", {});
  assert.equal(missing.status, 404);

  console.log("ok");
} finally {
  server.close();
}
