"use strict";

// Withdrawal-only runtime. Deposit handling is intentionally excluded.
const axios = require("axios");
const crypto = require("crypto");

if (!global.__TITAN_WITHDRAWAL_RUNTIME_V1__) {
  global.__TITAN_WITHDRAWAL_RUNTIME_V1__ = true;

  const FB = String(process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json").replace(/\/+$/, "");
  const TZ = process.env.APP_TZ || "Asia/Kolkata";

  function fbUrl(path) {
    const p = String(path || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
    return FB.endsWith(".json") ? FB.replace(/\.json$/, p ? "/" + p + ".json" : ".json") : FB + (p ? "/" + p : "") + ".json";
  }
  async function get(path, fallback) { try { const r = await axios.get(fbUrl(path), { timeout: 12000, headers: { "Cache-Control": "no-store" } }); return r.data == null ? fallback : r.data; } catch { return fallback; } }
  async function put(path, value) { await axios.put(fbUrl(path), value, { timeout: 15000, headers: { "Content-Type": "application/json" } }); }
  function now() { return new Date().toISOString(); }
  function money(v) { const n = Number(v || 0); return "₹" + (Number.isInteger(n) ? String(n) : n.toFixed(2)); }
  function unwrap(m) { let x = m?.message || {}; x = x.ephemeralMessage?.message || x.viewOnceMessage?.message || x.viewOnceMessageV2?.message || x; return x || {}; }
  function text(m) { const x = unwrap(m); return String(x.conversation || x.extendedTextMessage?.text || x.imageMessage?.caption || x.documentMessage?.caption || "").trim(); }
  function hasImage(m) { return !!unwrap(m).imageMessage; }
  function cleanJid(v) { return String(v || "").trim().replace(/:\d+(?=@)/, ""); }
  function digits(v) { return String(v || "").replace(/\D/g, ""); }
  function phone(v) { const d = digits(v); return d.length >= 10 ? d.slice(-10) : d; }
  function senderIds(m, chat) { const k = m?.key || {}; return [...new Set([k.participant, k.participantPn, k.senderPn, k.participantAlt, m?.participant, chat].map(cleanJid).filter(Boolean))]; }
  function amount(s) { const t = String(s || "").replace(/,/g, " "); const m = t.match(/(?:withdraw|withdrawal|wd|amount|₹|rs\.?|inr)\D{0,18}([0-9]+(?:\.[0-9]+)?)/i) || t.match(/^\s*([0-9]+(?:\.[0-9]+)?)/); const n = m ? Number(m[1]) : 0; return Number.isFinite(n) && n > 0 && n <= 2000000 ? Math.round(n * 100) / 100 : 0; }
  function upi(s) { const m = String(s || "").match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+/i); return m ? m[0].toLowerCase() : ""; }
  function messageKey(m) { const k = m?.key || {}; return [k.remoteJid || "", k.participant || "", k.id || ""].join("|"); }
  function nextId(list) { return "W" + new Date().toISOString().slice(2,10).replace(/-/g, "") + "-" + String((Array.isArray(list) ? list.length : 0) + 1).padStart(4, "0"); }

  async function imageData(baileys, m) {
    try {
      const image = unwrap(m).imageMessage;
      if (!image || !baileys.downloadContentFromMessage) return "";
      const stream = await baileys.downloadContentFromMessage(image, "image");
      const chunks = []; let size = 0;
      for await (const c of stream) { const b = Buffer.from(c); size += b.length; if (size > 1200000) break; chunks.push(b); }
      const buf = Buffer.concat(chunks);
      return buf.length ? `data:${image.mimetype || "image/jpeg"};base64,${buf.toString("base64")}` : "";
    } catch { return ""; }
  }

  function findProfile(state, ids) {
    const profiles = state.profiles && typeof state.profiles === "object" ? state.profiles : {};
    const candidates = ids.map(phone).filter(Boolean);
    for (const [id, p] of Object.entries(profiles)) {
      if (candidates.includes(phone(p?.phone || id))) return { id, profile: p };
    }
    return null;
  }

  async function reply(sock, chat, body, quoted) { try { await sock.sendMessage(chat, { text: String(body) }, quoted ? { quoted } : undefined); } catch {} }

  async function processOne(sock, baileys, m) {
    try {
      if (!m?.message || m.key?.fromMe) return false;
      const chat = m.key?.remoteJid || "";
      if (!chat || chat === "status@broadcast") return false;
      const body = text(m);
      if (!/^\s*(withdraw|withdrawal|wd)\b/i.test(body)) return false;

      const value = amount(body);
      if (!(value > 0)) { await reply(sock, chat, "❌ Withdrawal amount missing. Example: Withdraw 500 user@upi", m); return true; }

      const state = await get("", {}) || {};
      const found = findProfile(state, senderIds(m, chat));
      if (!found) { await reply(sock, chat, "❌ VIP profile nahi mila. Admin se profile approve karvao.", m); return true; }
      const approved = String(found.profile?.approvalStatus || "").toLowerCase() === "approved";
      if (!approved) { await reply(sock, chat, "❌ VIP profile abhi approved nahi hai.", m); return true; }

      state.wallets = state.wallets && typeof state.wallets === "object" ? state.wallets : {};
      const wallet = state.wallets[found.id] || { balance: 0, hold: 0, walletHold: 0, ledger: [] };
      wallet.balance = Number(wallet.balance || 0);
      wallet.hold = Number(wallet.hold || wallet.walletHold || 0);
      wallet.ledger = Array.isArray(wallet.ledger) ? wallet.ledger : [];
      const available = Math.round((wallet.balance - wallet.hold) * 100) / 100;
      if (available + 0.0001 < value) { await reply(sock, chat, `❌ Insufficient withdrawable balance.\nAvailable: ${money(available)}`, m); return true; }

      state.withdrawals = Array.isArray(state.withdrawals) ? state.withdrawals : [];
      const key = messageKey(m);
      const duplicate = state.withdrawals.find(x => x && x.messageKey === key);
      if (duplicate) { await reply(sock, chat, `⚠️ Withdrawal already submitted. ID: #${duplicate.id}`, m); return true; }

      const image = hasImage(m) ? await imageData(baileys, m) : "";
      const method = image ? "qr" : (upi(body) ? "upi" : "manual");
      const id = nextId(state.withdrawals);
      const holdBefore = wallet.hold;
      wallet.hold = Math.round((wallet.hold + value) * 100) / 100;
      wallet.walletHold = wallet.hold;
      wallet.ledger.push({ id: "WHOLD-" + Date.now(), withdrawalId: id, time: now(), type: "withdrawal_hold", amount: 0, balanceBefore: wallet.balance, balanceAfter: wallet.balance, holdBefore, holdAfter: wallet.hold, source: "whatsapp_withdrawal_runtime" });

      const rec = { id, userId: found.id, userName: found.profile?.name || found.id, phone: found.profile?.phone || "", senderJid: senderIds(m, chat)[0] || chat, chatJid: chat, messageKey: key, amount: value, method, detail: image ? "QR image attached" : (upi(body) || body.replace(/^\s*(withdraw|withdrawal|wd)\b/i, "").trim()), qrImageData: image, status: "pending", paymentStatus: "pending_approval", holdApplied: true, holdAmount: value, walletBalanceAtRequest: wallet.balance, walletHoldAfter: wallet.hold, source: "whatsapp_withdrawal_runtime", createdAt: now(), approvalNotified: false, paidNotified: false };
      state.withdrawals.push(rec);
      state.wallets[found.id] = wallet;
      await put("withdrawals", state.withdrawals.slice(-1000));
      await put("wallets/" + found.id, wallet);

      await reply(sock, chat, `✅ Withdrawal request submitted.\nID: #${id}\nAmount: ${money(value)}\nMethod: ${method.toUpperCase()}\nStatus: Pending admin approval.`, m);
      console.log("✅ Withdrawal request created", id, found.id, value);
      return true;
    } catch (e) {
      console.log("Withdrawal runtime error:", e.response ? `HTTP ${e.response.status}` : e.message);
      return false;
    }
  }

  const Module = require("module");
  const oldLoad = Module._load;
  Module._load = function patchedLoad(req, parent, isMain) {
    const mod = oldLoad.apply(this, arguments);
    try {
      if (req === "@whiskeysockets/baileys" && mod && !mod.__titanWithdrawalRuntimeWrapped) {
        const original = mod.default;
        if (typeof original === "function") {
          mod.default = function wrappedSocket() {
            const sock = original.apply(this, arguments);
            if (sock?.ev?.on && !sock.ev.__titanWithdrawalRuntimeWrapped) {
              const originalOn = sock.ev.on.bind(sock.ev);
              sock.ev.on = function(event, handler) {
                if (event === "messages.upsert" && typeof handler === "function") {
                  return originalOn(event, async upsert => {
                    const rest = [];
                    for (const m of (Array.isArray(upsert?.messages) ? upsert.messages : [])) {
                      if (!(await processOne(sock, mod, m))) rest.push(m);
                    }
                    if (rest.length) return handler({ ...upsert, messages: rest });
                  });
                }
                return originalOn(event, handler);
              };
              sock.ev.__titanWithdrawalRuntimeWrapped = true;
            }
            return sock;
          };
        }
        mod.__titanWithdrawalRuntimeWrapped = true;
        console.log("✅ Gateway withdrawal-only runtime active");
      }
    } catch (e) { console.log("Withdrawal hook error:", e.message); }
    return mod;
  };
}

module.exports = { enabled: true, feature: "gateway_withdrawal_runtime_v1" };
