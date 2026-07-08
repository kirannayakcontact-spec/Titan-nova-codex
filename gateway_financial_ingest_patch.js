"use strict";

// WhatsApp financial ingest patch
// Purpose: create admin-side Deposit/Withdrawal records from incoming WhatsApp media/text
// before the legacy message handler can swallow the message as a generic smart command
// or spam/forward event. No new UI. Uses existing Firebase children: payments, withdrawals, wallets.

const axios = require("axios");
const crypto = require("crypto");

if (!global.__TITAN_FINANCIAL_INGEST_PATCH__) {
  global.__TITAN_FINANCIAL_INGEST_PATCH__ = true;

  const FB_BASE = String(process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json").replace(/\/+$/, "");
  const APP_TZ = process.env.APP_TZ || "Asia/Kolkata";

  function childUrl(path) {
    const clean = String(path || "").split("/").map(encodeURIComponent).join("/");
    if (FB_BASE.endsWith(".json")) return FB_BASE.replace(/\.json$/, clean ? "/" + clean + ".json" : ".json");
    return FB_BASE + (clean ? "/" + clean : "") + ".json";
  }
  async function fbGet(path, fallback) {
    try {
      const r = await axios.get(childUrl(path), { timeout: 12000, headers: { "Cache-Control": "no-store" } });
      return r.data == null ? fallback : r.data;
    } catch (e) { return fallback; }
  }
  async function fbPut(path, value) {
    await axios.put(childUrl(path), value == null ? null : value, { timeout: 15000, headers: { "Content-Type": "application/json" } });
  }
  async function fbPatch(path, value) {
    await axios.patch(childUrl(path), value || {}, { timeout: 15000, headers: { "Content-Type": "application/json" } });
  }
  function nowIso() { return new Date().toISOString(); }
  function todayKey() {
    try {
      const d = new Date(new Date().toLocaleString("en-US", { timeZone: APP_TZ }));
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}${m}${day}`.slice(2);
    } catch (e) { return new Date().toISOString().slice(2, 10).replace(/-/g, ""); }
  }
  function money(v) {
    const n = Number(v || 0);
    return "₹" + (Number.isInteger(n) ? String(n) : n.toFixed(2));
  }
  function phoneKey(value) {
    const raw = String(value || "").trim();
    if (raw.includes("@") && !raw.includes("@s.whatsapp.net")) return "";
    let d = raw.replace(/\D/g, "");
    if (!d || d.length < 10) return "";
    d = d.slice(-10);
    return d;
  }
  function jidKey(value) { return String(value || "").trim().replace(/:\d+(?=@)/, ""); }
  function waTarget(phoneOrJid) {
    const raw = String(phoneOrJid || "").trim();
    if (raw.includes("@")) return jidKey(raw);
    let d = raw.replace(/\D/g, "");
    if (d.length === 10) d = "91" + d;
    if (d.length > 12) d = d.slice(-12);
    return d ? d + "@s.whatsapp.net" : "";
  }
  function messageKey(m) {
    const k = m && m.key || {};
    return [k.remoteJid || "", k.participant || "", k.id || ""].join("|");
  }
  function messageText(m) {
    const msg = m && m.message || {};
    return String(
      msg.conversation ||
      msg.extendedTextMessage?.text ||
      msg.imageMessage?.caption ||
      msg.videoMessage?.caption ||
      msg.documentMessage?.caption ||
      msg.buttonsResponseMessage?.selectedDisplayText ||
      msg.listResponseMessage?.title ||
      ""
    ).trim();
  }
  function hasImage(m) { return !!(m && m.message && m.message.imageMessage); }
  async function downloadImageData(baileys, m, limitBytes) {
    try {
      const image = m?.message?.imageMessage;
      if (!image || !baileys.downloadContentFromMessage) return "";
      const stream = await baileys.downloadContentFromMessage(image, "image");
      const chunks = [];
      let total = 0;
      for await (const chunk of stream) {
        const b = Buffer.from(chunk);
        total += b.length;
        if (total > (limitBytes || 900000)) break;
        chunks.push(b);
      }
      const buf = Buffer.concat(chunks);
      if (!buf.length) return "";
      const mime = image.mimetype || "image/jpeg";
      return `data:${mime};base64,${buf.toString("base64")}`;
    } catch (e) { return ""; }
  }
  function parseAmount(text) {
    const t = String(text || "").replace(/,/g, " ");
    const m = t.match(/(?:₹|rs\.?|inr|amount|amt|deposit|payment|pay|withdraw|withdrawal|wd)?\s*[:#-]?\s*([0-9]+(?:\.[0-9]+)?)/i);
    const n = m ? Math.round(Number(m[1]) * 100) / 100 : 0;
    return Number.isFinite(n) && n > 0 ? n : 0;
  }
  function parseUtr(text) {
    const t = String(text || "");
    const m = t.match(/(?:utr|rrn|txn|transaction(?:\s*id)?|ref(?:erence)?)[\s:#-]*([A-Z0-9]{6,32})/i);
    return m ? String(m[1]).toUpperCase() : "";
  }
  function parseUpi(text) {
    const m = String(text || "").match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+/i);
    return m ? m[0].toLowerCase() : "";
  }
  function looksDeposit(text, hasImg) {
    const t = String(text || "").toLowerCase();
    if (/\b(withdraw|withdrawal|wd)\b/.test(t)) return false;
    if (/\b(deposit|payment|paid|pay|recharge|add\s*money|utr|rrn|txn|transaction|screenshot|proof|upi)\b/.test(t)) return true;
    return !!hasImg && parseAmount(t) > 0;
  }
  function parseWithdrawal(text, img) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (!/^\s*(withdraw|withdrawal|wd)\b/i.test(t)) return null;
    const amount = parseAmount(t);
    if (!(amount > 0)) return { ok: false, message: "Withdrawal amount missing." };
    let method = "";
    if (/\bqr\b/i.test(t) || img) method = "qr";
    else if (/\b(bank|ifsc|account|a\/c|ac\s*no)\b/i.test(t)) method = "bank";
    else if (parseUpi(t) || /\bupi\b/i.test(t)) method = "upi";
    if (!method) method = img ? "qr" : "upi";
    let detail = "";
    if (method === "upi") detail = parseUpi(t) || t.replace(/^\s*(withdraw|withdrawal|wd)\b/i, "").replace(String(amount), "").trim();
    else if (method === "qr") detail = img ? "QR image attached" : "QR requested";
    else detail = t.replace(/^\s*(withdraw|withdrawal|wd)\b/i, "").replace(String(amount), "").trim();
    return { ok: true, amount, method, detail };
  }
  function senderCandidates(m, chatJid) {
    const k = m?.key || {};
    const out = [k.participant, k.participantPn, k.senderPn, k.participantAlt, k.participantAltJid, m?.participant, m?.participantPn, m?.senderPn];
    if (chatJid && !String(chatJid).endsWith("@g.us")) out.push(chatJid);
    return [...new Set(out.map(x => jidKey(x)).filter(Boolean))];
  }
  function findProfile(state, candidates, pushName) {
    const profiles = state.profiles && typeof state.profiles === "object" ? state.profiles : (state.profiles = {});
    const keys = [...new Set((candidates || []).map(phoneKey).filter(Boolean))];
    for (const [pid, p] of Object.entries(profiles)) {
      const pk = phoneKey(p && p.phone || "");
      if (pk && keys.includes(pk)) return { userId: pid, profile: p, phone: pk, created: false };
    }
    const wallets = state.wallets && typeof state.wallets === "object" ? state.wallets : {};
    for (const [uid, w] of Object.entries(wallets)) {
      const wk = phoneKey(w && w.phone || "");
      if (wk && keys.includes(wk) && profiles[uid]) return { userId: uid, profile: profiles[uid], phone: wk, created: false };
    }
    const phone = keys[0] || "";
    const uid = phone ? "client_" + phone : "client_wa_" + crypto.createHash("sha1").update((candidates || []).join("|")).digest("hex").slice(0, 12);
    if (!profiles[uid]) {
      profiles[uid] = { name: pushName || (phone ? "VIP " + phone : "WhatsApp VIP"), phone, approvalStatus: "pending", vipAccessEnabled: false, autoCreated: true, approvalSource: "whatsapp_financial_ingest", createdAt: nowIso(), dayRecords: {}, config: { capital: 0, dayTarget: 0 } };
    }
    return { userId: uid, profile: profiles[uid], phone, created: true };
  }
  function ensureWallet(state, userId, profile) {
    if (!state.wallets || typeof state.wallets !== "object") state.wallets = {};
    let w = state.wallets[userId];
    if (!w || typeof w !== "object") {
      w = state.wallets[userId] = { userId, name: profile?.name || userId, phone: profile?.phone || "", balance: 0, hold: 0, walletHold: 0, creditLimit: Number(state.walletSettings?.defaultCreditLimit || 0), ledger: [], createdAt: nowIso() };
    }
    if (!Array.isArray(w.ledger)) w.ledger = [];
    w.name = w.name || profile?.name || userId;
    w.phone = w.phone || profile?.phone || "";
    w.balance = Number(w.balance || 0);
    w.hold = Number(w.hold || w.walletHold || 0);
    w.walletHold = w.hold;
    w.creditLimit = Number(w.creditLimit || 0);
    return w;
  }
  function withdrawAvailable(w) { return Math.round((Number(w?.balance || 0) - Number(w?.hold || w?.walletHold || 0)) * 100) / 100; }
  function nextId(prefix, list) { return prefix + todayKey() + "-" + String((Array.isArray(list) ? list.length : 0) + 1).padStart(4, "0"); }
  function duplicateByMessage(list, msgKey) { return Array.isArray(list) && msgKey ? list.find(x => x && x.messageKey === msgKey) : null; }
  async function appendAudit(state, action, detail) {
    try {
      const audit = Array.isArray(state.auditLog) ? state.auditLog : [];
      audit.push({ id: action + "_" + crypto.randomBytes(4).toString("hex"), time: nowIso(), action, detail: detail || {} });
      state.auditLog = audit.slice(-500);
      await fbPut("auditLog", state.auditLog);
    } catch (e) {}
  }
  async function saveProfileWallet(state, userId) {
    try { await fbPut("profiles/" + userId, state.profiles[userId]); } catch (e) {}
    try { await fbPut("wallets/" + userId, state.wallets[userId]); } catch (e) {}
  }
  async function createDepositRecord(sock, baileys, m, state, found, caption, imgData) {
    state.payments = Array.isArray(state.payments) ? state.payments : [];
    const msgKey = messageKey(m);
    const old = duplicateByMessage(state.payments, msgKey);
    if (old) return { handled: true, reply: `⚠️ Deposit proof already submitted. ID: #${old.id}` };
    const amount = parseAmount(caption);
    const utr = parseUtr(caption);
    const txid = utr || parseUtr(caption.replace(/utr/i, "txn"));
    const p = {
      id: nextId("P", state.payments),
      userId: found.userId,
      userName: found.profile?.name || found.userId,
      phone: found.profile?.phone || found.phone || "",
      senderJid: senderCandidates(m, m.key?.remoteJid || "")[0] || "",
      chatJid: m.key?.remoteJid || "",
      messageKey: msgKey,
      amount: amount || 0,
      utr,
      transactionId: txid,
      status: "pending",
      paymentStatus: amount > 0 ? "pending_admin_approval" : "needs_amount",
      source: "whatsapp_deposit_screenshot_patch",
      walletCredited: false,
      screenshotImageData: imgData || "",
      image: imgData || "",
      screenshotHash: imgData ? crypto.createHash("sha256").update(String(imgData).split(",").pop() || "").digest("hex") : "",
      rawOcrText: caption || "",
      riskFlags: amount > 0 ? [] : ["missing_amount"],
      riskLevel: amount > 0 ? "MEDIUM" : "HIGH",
      requestNotified: true,
      approvalNotified: false,
      rejectionNotified: false,
      createdAt: nowIso(),
      time: new Date().toLocaleString("en-IN", { timeZone: APP_TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    };
    state.payments.push(p);
    await fbPut("payments", state.payments.slice(-1000));
    await saveProfileWallet(state, found.userId);
    await appendAudit(state, "whatsapp_deposit_request_created", { paymentId: p.id, userId: p.userId, amount: p.amount, source: p.source });
    return { handled: true, reply: amount > 0 ? `✅ Deposit request created.\nID: #${p.id}\nAmount: ${money(amount)}\nStatus: Pending admin approval.` : `📷 Deposit screenshot received.\nID: #${p.id}\nAmount clear nahi mila. Admin review karega.` };
  }
  async function createWithdrawalRecord(sock, baileys, m, state, found, parsed, imgData) {
    state.withdrawals = Array.isArray(state.withdrawals) ? state.withdrawals : [];
    const msgKey = messageKey(m);
    const old = duplicateByMessage(state.withdrawals, msgKey);
    if (old) return { handled: true, reply: `⚠️ Withdrawal request already submitted. ID: #${old.id}` };
    const wallet = ensureWallet(state, found.userId, found.profile);
    const avail = withdrawAvailable(wallet);
    const canHold = avail + 0.0001 >= parsed.amount && String(found.profile?.approvalStatus || "approved").toLowerCase() === "approved";
    let holdBefore = Number(wallet.hold || wallet.walletHold || 0);
    if (canHold) {
      wallet.hold = Math.round((holdBefore + parsed.amount) * 100) / 100;
      wallet.walletHold = wallet.hold;
      wallet.updatedAt = nowIso();
      wallet.ledger.push({ id: "WHOLD-" + Date.now(), time: nowIso(), type: "withdrawal_hold", amount: 0, balanceBefore: wallet.balance, balanceAfter: wallet.balance, holdBefore, holdAfter: wallet.hold, note: "Withdrawal hold " + parsed.method.toUpperCase(), source: "whatsapp_withdrawal_patch" });
    }
    const wd = {
      id: nextId("W", state.withdrawals),
      userId: found.userId,
      userName: found.profile?.name || found.userId,
      phone: found.profile?.phone || found.phone || "",
      senderJid: senderCandidates(m, m.key?.remoteJid || "")[0] || "",
      chatJid: m.key?.remoteJid || "",
      messageKey: msgKey,
      amount: parsed.amount,
      method: parsed.method,
      detail: parsed.detail || (parsed.method === "qr" ? "QR image attached" : ""),
      qrImageData: parsed.method === "qr" ? (imgData || "") : "",
      status: "pending",
      paymentStatus: canHold ? "pending_approval" : "pending_admin_review",
      requestNotified: true,
      approvalNotified: false,
      paidNotified: false,
      rejectionNotified: false,
      holdApplied: canHold,
      holdAmount: canHold ? parsed.amount : 0,
      walletBalanceAtRequest: wallet.balance,
      walletHoldAfter: wallet.hold,
      needsAdminReview: !canHold,
      reviewReason: canHold ? "" : (String(found.profile?.approvalStatus || "").toLowerCase() !== "approved" ? "profile_not_approved" : "insufficient_withdrawable_balance"),
      createdAt: nowIso(),
      source: "whatsapp_withdrawal_patch"
    };
    if (canHold && wallet.ledger.length) wallet.ledger[wallet.ledger.length - 1].withdrawalId = wd.id;
    state.withdrawals.push(wd);
    await fbPut("withdrawals", state.withdrawals.slice(-1000));
    await saveProfileWallet(state, found.userId);
    await appendAudit(state, "whatsapp_withdrawal_request_created", { withdrawalId: wd.id, userId: wd.userId, amount: wd.amount, method: wd.method, holdApplied: wd.holdApplied, reviewReason: wd.reviewReason });
    return { handled: true, reply: `✅ Withdrawal request created.\nID: #${wd.id}\nAmount: ${money(wd.amount)}\nMethod: ${String(wd.method).toUpperCase()}\nStatus: Pending admin approval.` };
  }
  async function sendReply(sock, chatJid, text, quoted) {
    try { if (sock && chatJid && text) await sock.sendMessage(chatJid, { text: String(text) }, quoted ? { quoted } : undefined); } catch (e) {}
  }
  async function processOne(sock, baileys, m) {
    try {
      if (!m || !m.message || m.key?.fromMe) return false;
      const chatJid = m.key?.remoteJid || "";
      if (!chatJid || chatJid === "status@broadcast") return false;
      const caption = messageText(m);
      const img = hasImage(m);
      const wParsed = parseWithdrawal(caption, img);
      const deposit = !wParsed && looksDeposit(caption, img);
      if (!wParsed && !deposit) return false;
      const state = await fbGet("", {}) || {};
      state.profiles = state.profiles && typeof state.profiles === "object" ? state.profiles : {};
      state.wallets = state.wallets && typeof state.wallets === "object" ? state.wallets : {};
      const candidates = senderCandidates(m, chatJid);
      const sender = chatJid.endsWith("@g.us") ? (candidates[0] || m.key?.participant || "") : chatJid;
      const found = findProfile(state, [sender, ...candidates], m.pushName || m.verifiedBizName || "");
      ensureWallet(state, found.userId, found.profile);
      const imgData = img ? await downloadImageData(baileys, m, wParsed ? 800000 : 1100000) : "";
      let out = null;
      if (wParsed) {
        if (!wParsed.ok) out = { handled: true, reply: "❌ " + (wParsed.message || "Withdrawal format invalid.") };
        else out = await createWithdrawalRecord(sock, baileys, m, state, found, wParsed, imgData);
      } else {
        out = await createDepositRecord(sock, baileys, m, state, found, caption, imgData);
      }
      if (out && out.handled) {
        await sendReply(sock, chatJid, out.reply, m);
        console.log("✅ WhatsApp financial request captured:", wParsed ? "withdrawal" : "deposit", found.userId);
        return true;
      }
    } catch (e) {
      console.log("Financial ingest patch error:", e.response ? `HTTP ${e.response.status}` : e.message);
    }
    return false;
  }

  const Module = require("module");
  const oldLoad = Module._load;
  Module._load = function patchedLoad(request, parent, isMain) {
    const mod = oldLoad.apply(this, arguments);
    try {
      if (request === "@whiskeysockets/baileys" && mod && !mod.__titanFinancialWrapped) {
        const originalMake = mod.default;
        if (typeof originalMake === "function") {
          mod.default = function wrappedMakeWASocket() {
            const sock = originalMake.apply(this, arguments);
            if (sock && sock.ev && typeof sock.ev.on === "function" && !sock.ev.__titanFinancialWrapped) {
              const oldOn = sock.ev.on.bind(sock.ev);
              sock.ev.on = function wrappedOn(eventName, handler) {
                if (eventName === "messages.upsert" && typeof handler === "function") {
                  return oldOn(eventName, async function financialFirst(upsert) {
                    const originalMessages = Array.isArray(upsert && upsert.messages) ? upsert.messages : [];
                    const remaining = [];
                    for (const msg of originalMessages) {
                      const handled = await processOne(sock, mod, msg);
                      if (!handled) remaining.push(msg);
                    }
                    if (remaining.length) return handler({ ...upsert, messages: remaining });
                    return undefined;
                  });
                }
                return oldOn(eventName, handler);
              };
              sock.ev.__titanFinancialWrapped = true;
            }
            return sock;
          };
          Object.assign(mod.default, originalMake);
        }
        mod.__titanFinancialWrapped = true;
        console.log("✅ Gateway financial ingest patch active");
      }
    } catch (e) {
      console.log("Gateway financial ingest patch load error:", e.message);
    }
    return mod;
  };
}

module.exports = { enabled: true, feature: "gateway_financial_ingest_patch" };
