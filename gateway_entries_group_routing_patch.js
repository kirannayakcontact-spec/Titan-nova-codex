"use strict";

const axios = require("axios");

if (!global.__TITAN_ENTRIES_GROUP_ROUTING_V1__) {
  global.__TITAN_ENTRIES_GROUP_ROUTING_V1__ = true;

  const FB = String(process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json").replace(/\/+$/, "");
  const CACHE_MS = 5000;
  let cache = { at: 0, settings: null };
  const warned = new Map();

  function fbUrl(path) {
    const p = String(path || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
    return FB.endsWith(".json") ? FB.replace(/\.json$/, p ? "/" + p + ".json" : ".json") : FB + (p ? "/" + p : "") + ".json";
  }
  async function get(path, fallback) {
    try { const r = await axios.get(fbUrl(path), { timeout: 12000, headers: { "Cache-Control": "no-store" } }); return r.data == null ? fallback : r.data; }
    catch { return fallback; }
  }
  async function put(path, value) { await axios.put(fbUrl(path), value, { timeout: 15000, headers: { "Content-Type": "application/json" } }); }
  function cleanJid(v) { return String(v || "").trim().replace(/:\d+(?=@)/, ""); }
  function isGroup(jid) { return cleanJid(jid).endsWith("@g.us"); }
  function defaults() {
    return {
      enabled: true,
      strictGroups: false,
      allowPrivate: { gameEntry: true, withdrawal: true, deposit: true },
      groupIds: { gameEntry: [], withdrawal: [], deposit: [] }
    };
  }
  async function settings() {
    if (cache.settings && Date.now() - cache.at < CACHE_MS) return cache.settings;
    const raw = await get("entriesGroupRouting", {});
    const d = defaults();
    const out = {
      enabled: raw?.enabled !== false,
      strictGroups: raw?.strictGroups === true,
      allowPrivate: Object.assign({}, d.allowPrivate, raw?.allowPrivate || {}),
      groupIds: Object.assign({}, d.groupIds, raw?.groupIds || {})
    };
    for (const k of Object.keys(out.groupIds)) out.groupIds[k] = [...new Set((Array.isArray(out.groupIds[k]) ? out.groupIds[k] : []).map(cleanJid).filter(Boolean))];
    cache = { at: Date.now(), settings: out };
    return out;
  }
  async function allow(feature, chatJid) {
    const cfg = await settings();
    const chat = cleanJid(chatJid);
    if (!cfg.enabled || !cfg.strictGroups) return true;
    if (!isGroup(chat)) return cfg.allowPrivate?.[feature] !== false;
    const allowed = cfg.groupIds?.[feature] || [];
    return allowed.length === 0 ? false : allowed.includes(chat);
  }
  global.__TITAN_GROUP_ROUTING_ALLOW__ = allow;
  global.__TITAN_GROUP_ROUTING_REFRESH__ = () => { cache = { at: 0, settings: null }; };

  function unwrap(msg) {
    let m = msg?.message || {};
    m = m.ephemeralMessage?.message || m.viewOnceMessage?.message || m.viewOnceMessageV2?.message || m;
    return m || {};
  }
  function text(msg) {
    const m = unwrap(msg);
    return String(m.conversation || m.extendedTextMessage?.text || m.imageMessage?.caption || m.documentMessage?.caption || "").trim();
  }
  function isWithdrawal(msg) { return /^\s*(withdraw|withdrawal|wd)\b/i.test(text(msg)); }
  function isDeposit(msg) {
    const t = text(msg);
    const m = unwrap(msg);
    return !!m.imageMessage && /\b(deposit|paid|payment|utr|upi)\b/i.test(t || "deposit");
  }
  function isGameEntry(msg) {
    const t = text(msg);
    if (!t || isWithdrawal(msg) || isDeposit(msg)) return false;
    if (!/\d/.test(t)) return false;
    return /\b(ank|jodi|panel|pannel|patti|open|close|market|entry|t1|t2)\b/i.test(t) || /\d\s*[-=:xX]\s*\d/.test(t);
  }
  async function reject(sock, chat, feature, quoted) {
    const key = `${chat}|${feature}`;
    const last = warned.get(key) || 0;
    if (Date.now() - last < 15000) return;
    warned.set(key, Date.now());
    const label = feature === "gameEntry" ? "Game Entry" : feature === "withdrawal" ? "Withdrawal" : "Deposit";
    try { await sock.sendMessage(chat, { text: `❌ ${label} request is group me allowed nahi hai. Admin ne iske liye separate WhatsApp group set kiya hai.` }, quoted ? { quoted } : undefined); } catch {}
  }
  async function publishGroups(sock) {
    try {
      if (!sock?.groupFetchAllParticipating) return;
      const data = await sock.groupFetchAllParticipating();
      const groups = Object.values(data || {}).map(g => ({ id: cleanJid(g.id), name: String(g.subject || g.name || g.id || "WhatsApp Group"), participants: Array.isArray(g.participants) ? g.participants.length : 0, updatedAt: new Date().toISOString() })).sort((a,b) => a.name.localeCompare(b.name));
      await put("gatewayGroupDirectory", groups);
      console.log(`✅ Entries group directory synced: ${groups.length}`);
    } catch (e) { console.warn("Entries group directory sync failed:", e.message); }
  }

  try {
    const baileys = require("@whiskeysockets/baileys");
    const original = baileys?.default;
    if (typeof original === "function" && !original.__titanEntriesRoutingWrapped) {
      function wrappedMakeWASocket(...args) {
        const sock = original(...args);
        try {
          setTimeout(() => publishGroups(sock), 8000);
          const timer = setInterval(() => publishGroups(sock), 10 * 60 * 1000);
          if (timer.unref) timer.unref();
          const oldOn = sock?.ev?.on ? sock.ev.on.bind(sock.ev) : null;
          if (oldOn && !sock.__titanEntriesRoutingAttached) {
            sock.__titanEntriesRoutingAttached = true;
            sock.ev.on = function(event, handler) {
              if (event === "messages.upsert" && typeof handler === "function") {
                return oldOn(event, async upsert => {
                  const pass = [];
                  for (const msg of (Array.isArray(upsert?.messages) ? upsert.messages : [])) {
                    const chat = cleanJid(msg?.key?.remoteJid);
                    if (isGameEntry(msg) && !(await allow("gameEntry", chat))) {
                      await reject(sock, chat, "gameEntry", msg);
                    } else {
                      pass.push(msg);
                    }
                  }
                  if (pass.length) return handler({ ...upsert, messages: pass });
                });
              }
              return oldOn(event, handler);
            };
          }
        } catch (e) { console.warn("Entries routing socket attach failed:", e.message); }
        return sock;
      }
      wrappedMakeWASocket.__titanEntriesRoutingWrapped = true;
      baileys.default = wrappedMakeWASocket;
      console.log("✅ Separate Entries/Withdrawal/Deposit group routing active");
    }
  } catch (e) { console.warn("⚠️ Entries group routing failed to load:", e.message); }
}

module.exports = { enabled: true, feature: "entries_group_routing_v1" };
