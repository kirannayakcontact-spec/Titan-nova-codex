const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { TitanMultiSessionManager } = require("../bot/session_manager.js");
const { registerBotRoutes } = require("../bot/session_routes.js");

async function expectReject(promise, pattern) {
  await assert.rejects(promise, pattern);
}

async function testManagerValidationAndRouting() {
  let ownerPayload;
  const manager = new TitanMultiSessionManager({
    stateDir: fs.mkdtempSync(path.join(os.tmpdir(), "titan-session-test-")),
    ownerSend: async (to, text) => { ownerPayload = { to, text }; return { ok: true }; },
  });

  await expectReject(manager.send("owner_bot", "919999999999", "   "), /Message text is required/);
  await manager.send("owner_bot", "919999999999", "  owner alert  ");
  assert.deepStrictEqual(ownerPayload, { to: "919999999999", text: "owner alert" });

  const rec = manager.sessions.get("finance_bot");
  const sent = [];
  rec.connected = true;
  rec.socket = { sendMessage: async (jid, payload) => { sent.push({ jid, payload }); return { jid, payload }; } };
  await manager.send("finance_bot", "9999999999", "  deposit notice  ");
  assert.deepStrictEqual(sent[0], {
    jid: "919999999999@s.whatsapp.net",
    payload: { text: "deposit notice" },
  });
  await expectReject(manager.send("finance_bot", "not-a-recipient", "hello"), /valid WhatsApp recipient/);
  await expectReject(manager.send("finance_bot", "9999999999", "x".repeat(4097)), /exceeds 4096/);
}

async function testResetDoesNotDoubleStart() {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "titan-reset-test-"));
  const manager = new TitanMultiSessionManager({ stateDir });
  const rec = manager.sessions.get("finance_bot");
  let closeCalls = 0;
  let starts = 0;
  rec.socket = { end: () => { closeCalls += 1; } };
  rec.connected = true;
  manager.start = async () => { starts += 1; };
  await manager.reset("finance_bot");
  await new Promise(resolve => setTimeout(resolve, 650));
  assert.strictEqual(closeCalls, 1);
  assert.strictEqual(starts, 1);
  assert.strictEqual(rec.reconnectAttempt, 0);
}

async function testRouteValidation() {
  const routes = {};
  const app = {
    get: (route, guard, handler) => { routes[`GET ${route}`] = handler; },
    post: (route, guard, handler) => { routes[`POST ${route}`] = handler; },
  };
  const manager = { send: async () => { throw new Error("finance_bot is disconnected"); } };
  registerBotRoutes(manager, app);

  const response = () => ({ statusCode: 200, body: null, status(code) { this.statusCode = code; return this; }, json(body) { this.body = body; } });
  const missing = response();
  await routes["POST /api/bots/send"]({ body: { eventType: "deposit", to: "", text: "hello" } }, missing);
  assert.strictEqual(missing.statusCode, 400);
  assert.strictEqual(missing.body.message, "A recipient is required");

  const disconnected = response();
  await routes["POST /api/bots/send"]({ body: { eventType: "deposit", to: "9999999999", text: "hello" } }, disconnected);
  assert.strictEqual(disconnected.statusCode, 503);
}

(async () => {
  await testManagerValidationAndRouting();
  await testResetDoesNotDoubleStart();
  await testRouteValidation();
  console.log("Session manager regression tests passed");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
