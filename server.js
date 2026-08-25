import crypto from "node:crypto";
import { pathToFileURL } from "node:url";
import express from "express";

/** ponytail: in-memory Map; lost on restart. Upgrade: sqlite when a real TMS stores terminals. */
export function createStore() {
  return { byId: new Map(), bySerial: new Map(), seq: 0 };
}

function terminalView(t) {
  return {
    terminalId: t.id,
    identity: t.identity,
    lastHeartbeat: t.heartbeat,
    lastInventory: t.inventory,
    commands: t.commands,
  };
}

function enqueue(store, t, type, payload = {}, expiresAt) {
  store.seq += 1;
  const now = Date.now();
  const cmd = {
    id: `c-${store.seq}`,
    type,
    issuedAt: now,
    expiresAt: expiresAt ?? now + 24 * 60 * 60 * 1000,
    payload,
    status: "pending",
    result: null,
  };
  t.commands.push(cmd);
  return cmd;
}

function validateEnqueuePayload(type, payload) {
  if (payload == null || typeof payload !== "object" || Array.isArray(payload)) {
    return "payload must be an object";
  }
  switch (type) {
    case "install_app": {
      const url = payload.url;
      if (!url || typeof url !== "string" || !url.trim()) return "install_app: url required";
      if (!/^https?:\/\//i.test(url.trim())) return "install_app: url must be http or https";
      if (payload.sha256 != null && payload.sha256 !== "") {
        if (typeof payload.sha256 !== "string" || !/^[0-9a-fA-F]{64}$/.test(payload.sha256)) {
          return "install_app: sha256 must be 64 hex chars";
        }
      }
      if (payload.packageName != null && typeof payload.packageName !== "string") {
        return "install_app: packageName must be a string";
      }
      return null;
    }
    case "uninstall_app": {
      const pkg = payload.packageName;
      if (!pkg || typeof pkg !== "string" || !pkg.trim()) return "uninstall_app: packageName required";
      return null;
    }
    case "reboot": {
      if (payload.delayMs != null && (typeof payload.delayMs !== "number" || payload.delayMs < 0)) {
        return "reboot: delayMs must be a number >= 0";
      }
      return null;
    }
    case "ping":
    case "collect_inventory":
      return null;
    default:
      return null;
  }
}

function requireTerminal(store, req, res) {
  const t = store.byId.get(req.params.terminalId);
  if (!t) {
    res.status(404).json({ error: "unknown terminal" });
    return null;
  }
  return t;
}

function chunkToBuf(c, enc) {
  if (c == null || typeof c === "function") return null;
  return Buffer.isBuffer(c) ? c : Buffer.from(c, typeof enc === "string" ? enc : undefined);
}

function logHttp(req, res, next) {
  const t0 = Date.now();
  const chunks = [];
  const { write, end } = res;
  res.write = (c, enc, cb) => {
    const buf = chunkToBuf(c, enc);
    if (buf) chunks.push(buf);
    return write.call(res, c, enc, cb);
  };
  res.end = (c, enc, cb) => {
    const pending = chunkToBuf(c, enc);
    const raw = Buffer.concat(pending ? [...chunks, pending] : chunks).toString("utf8");
    let out = raw;
    try {
      if (raw) out = JSON.parse(raw);
    } catch {
      /* keep raw */
    }
    console.log(
      `${req.method} ${req.originalUrl} ${res.statusCode} ${Date.now() - t0}ms` +
        `\n  req ${JSON.stringify(req.body ?? null)}` +
        `\n  res ${raw ? JSON.stringify(out) : "null"}`,
    );
    return end.call(res, c, enc, cb);
  };
  next();
}

export function createApp(store = createStore()) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.use(logHttp);

  app.get("/health", (_req, res) => res.json({ ok: true }));

  app.get("/v1/terminals", (_req, res) => {
    res.json({ terminals: [...store.byId.values()].map(terminalView) });
  });

  app.get("/v1/terminals/:terminalId", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    res.json(terminalView(t));
  });

  app.post("/v1/terminals/register", (req, res) => {
    const serial = req.body?.serialNumber;
    if (!serial || typeof serial !== "string") {
      res.status(400).json({ error: "serialNumber required" });
      return;
    }
    let t = store.bySerial.get(serial);
    if (!t) {
      t = {
        id: crypto.randomUUID(),
        token: crypto.randomUUID(),
        identity: req.body,
        heartbeat: null,
        inventory: null,
        commands: [],
      };
      store.byId.set(t.id, t);
      store.bySerial.set(serial, t);
      enqueue(store, t, "ping");
    } else {
      t.identity = req.body;
    }
    res.json({ terminalId: t.id, token: t.token });
  });

  app.post("/v1/terminals/:terminalId/heartbeat", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    t.heartbeat = { ...req.body, receivedAt: Date.now() };
    res.status(204).end();
  });

  app.post("/v1/terminals/:terminalId/inventory", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    t.inventory = { ...req.body, receivedAt: Date.now() };
    res.status(204).end();
  });

  app.get("/v1/terminals/:terminalId/commands", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    const commands = t.commands
      .filter((c) => c.result == null)
      .map(({ id, type, issuedAt, expiresAt, payload }) => ({
        id,
        type,
        issuedAt,
        expiresAt,
        payload,
      }));
    res.json({ commands });
  });

  app.post("/v1/terminals/:terminalId/commands", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    const type = req.body?.type;
    if (!type || typeof type !== "string") {
      res.status(400).json({ error: "type required" });
      return;
    }
    const payload = req.body.payload ?? {};
    const payloadErr = validateEnqueuePayload(type, payload);
    if (payloadErr) {
      res.status(400).json({ error: payloadErr });
      return;
    }
    const cmd = enqueue(store, t, type, payload, req.body.expiresAt);
    res.status(201).json(cmd);
  });

  app.post("/v1/terminals/:terminalId/commands/:commandId/result", (req, res) => {
    const t = requireTerminal(store, req, res);
    if (!t) return;
    const cmd = t.commands.find((c) => c.id === req.params.commandId);
    const result = {
      protocolVersion: req.body?.protocolVersion,
      status: req.body?.status,
      message: req.body?.message,
      completedAt: req.body?.completedAt,
      receivedAt: Date.now(),
    };
    if (cmd) {
      cmd.status = result.status || "succeeded";
      cmd.result = result;
    }
    // ponytail: unknown commandId still 204 so the agent outbox can drain
    res.status(204).end();
  });

  return app;
}

const isMain =
  process.argv[1] != null && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  const port = Number(process.env.PORT) || 3000;
  createApp().listen(port, "0.0.0.0", () => {
    console.log(`TMSExpress http://0.0.0.0:${port}/v1`);
  });
}
