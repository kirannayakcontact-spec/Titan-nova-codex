"use strict";

// Titan Nova WhatsApp financial image verifier
// Classifies incoming images before creating admin records:
// - payment_screenshot -> payments[] / Deposit tab
// - withdrawal_qr      -> withdrawals[] / Withdrawal tab
// - invalid_image      -> rejected, no admin action record

const axios = require("axios");
const crypto = require("crypto");

if (!global.__TITAN_FINANCIAL_IMAGE_VERIFY_V2__) {
  global.__TITAN_FINANCIAL_IMAGE_VERIFY_V2__ = true;

  const FB = String(process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json").replace(/\/+$/, "");
  const TZ = process.env.APP_TZ || "Asia/Kolkata";
  const OCR_KEY = String(process.env.OCR_SPACE_API_KEY || "").trim();

  function url(path) {
    const p = String(path || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
    return FB.endsWith(".json") ? FB.replace(/\.json$/, p ? "/" + p + ".json" : ".json") : FB + (p ? "/" + p : "") + ".json";
  }
  async function get(path, fb) { try { const r = await axios.get(url(path), { timeout: 12000, headers: { "Cache-Control": "no-store" } }); return r.data == null ? fb : r.data; } catch { return fb; } }
  async function put(path, value) { await axios.put(url(path), value == null ? null : value, { timeout: 15000, headers: { "Content-Type": "application/json" } }); }
  function now() { return new Date().toISOString(); }
  function day() {
    try { const d = new Date(new Date().toLocaleString("en-US", { timeZone: TZ })); return String(d.getFullYear()).slice(2) + String(d.getMonth() + 1).padStart(2, "0") + String(d.getDate()).padStart(2, "0"); }
    catch { return new Date().toISOString().slice(2, 10).replace(/-/g, ""); }
  }
  function money(v) { const n = Number(v || 0); return "₹" + (Number.isInteger(n) ? String(n) : n.toFixed(2)); }
  function phone(v) { const raw = String(v || ""); if (raw.includes("@") && !raw.includes("@s.whatsapp.net")) return ""; const d = raw.replace(/\D/g, ""); return d.length >= 10 ? d.slice(-10) : ""; }
  function jid(v) { return String(v || "").trim().replace(/:\d+(?=@)/, ""); }
  function msgBody(m) { let x = m && m.message || {}; x = x.ephemeralMessage?.message || x.viewOnceMessage?.message || x.viewOnceMessageV2?.message || x; return x || {}; }
  function text(m) { const x = msgBody(m); return String(x.conversation || x.extendedTextMessage?.text || x.imageMessage?.caption || x.videoMessage?.caption || x.documentMessage?.caption || "").trim(); }
  function hasImage(m) { return !!msgBody(m).imageMessage; }
  function msgKey(m) { const k = m && m.key || {}; return [k.remoteJid || "", k.participant || "", k.id || ""].join("|"); }
  function candidates(m, chat) { const k = m?.key || {}; const a = [k.participant, k.participantPn, k.senderPn, k.participantAlt, k.participantAltJid, m?.participant, m?.participantPn, m?.senderPn]; if (chat && !String(chat).endsWith("@g.us")) a.push(chat); return [...new Set(a.map(jid).filter(Boolean))]; }
  function hash(data) { const b = String(data || "").split(",").pop() || ""; return b ? crypto.createHash("sha256").update(b).digest("hex") : ""; }

  async function downloadImage(baileys, m) {
    try {
      const image = msgBody(m).imageMessage;
      if (!image || !baileys.downloadContentFromMessage) return { data: "", buffer: null };
      const stream = await baileys.downloadContentFromMessage(image, "image");
      const chunks = []; let size = 0;
      for await (const c of stream) { const b = Buffer.from(c); size += b.length; if (size > 1100000) break; chunks.push(b); }
      const buf = Buffer.concat(chunks); if (!buf.length) return { data: "", buffer: null };
      return { data: `data:${image.mimetype || "image/jpeg"};base64,${buf.toString("base64")}`, buffer: buf };
    } catch { return { data: "", buffer: null }; }
  }

  async function runOcr(imageData) {
    if (!OCR_KEY || !imageData) return { text: "", provider: OCR_KEY ? "ocr_space_empty" : "ocr_disabled", confidence: 0 };
    try {
      const body = new URLSearchParams({ apikey: OCR_KEY, base64Image: imageData, language: "eng", scale: "true", OCREngine: "2" }).toString();
      const r = await axios.post("https://api.ocr.space/parse/image", body, { timeout: 20000, headers: { "Content-Type": "application/x-www-form-urlencoded" } });
      const parsed = (r.data && r.data.ParsedResults && r.data.ParsedResults[0]) || {};
      const out = String(parsed.ParsedText || "").trim();
      return { text: out, provider: "ocr.space", confidence: out ? 0.75 : 0.15 };
    } catch (e) { return { text: "", provider: "ocr_error", confidence: 0, error: e.message || String(e) }; }
  }

  function amount(s) {
    const t = String(s || "").replace(/,/g, " ");
    const pats = [/(?:₹|rs\.?|inr)\s*([0-9]+(?:\.[0-9]+)?)/i, /(?:amount|amt|paid|deposit|payment|withdraw|withdrawal|pay)\D{0,16}([0-9]+(?:\.[0-9]+)?)/i, /^\s*([0-9]+(?:\.[0-9]+)?)(?:\s|$)/i];
    for (const p of pats) { const m = t.match(p); const n = m ? Number(m[1]) : 0; if (Number.isFinite(n) && n > 0 && n <= 2000000) return Math.round(n * 100) / 100; }
    return 0;
  }
  function utr(s) { const m = String(s || "").match(/(?:utr|rrn|txn|transaction(?:\s*id)?|ref(?:erence)?)\s*[:#-]?\s*([A-Z0-9]{6,32})/i); return m ? String(m[1]).toUpperCase() : ""; }
  function upi(s) { const m = String(s || "").match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+/i); return m ? m[0].toLowerCase() : ""; }

  function classifyImage(caption, ocrText, img, isWithdraw) {
    if (!img) return { kind: "text_only", ok: true, reason: "no_image" };
    const combined = `${caption || ""}\n${ocrText || ""}`;
    const c = String(caption || "").toLowerCase();
    const t = combined.toLowerCase();
    const hasAmt = amount(combined) > 0;
    const hasUtr = !!utr(combined);
    const paymentWords = /\b(payment|paid|deposit|deposited|success|successful|completed|credited|debited|utr|rrn|transaction|txn|ref|amount|upi)\b/i.test(combined);
    const qrWords = /\b(qr|scan|scanner|pay using|upi qr|bhim|phonepe|gpay|google pay|paytm)\b/i.test(combined);
    if (isWithdraw) {
      if (/\bqr\b/i.test(c) || qrWords || (!ocrText && /\b(withdraw|withdrawal|wd)\b/i.test(c))) return { kind: "withdrawal_qr", ok: true, reason: "withdrawal_qr_detected" };
      return { kind: "invalid_image", ok: false, reason: "withdrawal_image_not_qr" };
    }
    if ((hasAmt || hasUtr) && paymentWords) return { kind: "payment_screenshot", ok: true, reason: "payment_markers_detected" };
    if (!OCR_KEY && /\b(payment|paid|deposit|utr|rrn|txn|transaction)\b/i.test(c) && (amount(caption) > 0 || utr(caption))) return { kind: "payment_screenshot", ok: true, reason: "caption_payment_fallback_ocr_disabled" };
    return { kind: "invalid_image", ok: false, reason: OCR_KEY ? "ocr_not_payment_or_qr" : "ocr_key_missing_and_caption_not_enough" };
  }

  function parseWithdraw(caption, imgClass) {
    const s = String(caption || "").trim();
    if (!/^\s*(withdraw|withdrawal|wd)\b/i.test(s)) return null;
    const a = amount(s); if (!(a > 0)) return { ok: false, message: "Withdrawal amount missing." };
    let method = /\bqr\b/i.test(s) || imgClass === "withdrawal_qr" ? "qr" : (upi(s) || /\bupi\b/i.test(s) ? "upi" : (/\b(bank|ifsc|account|a\/c)\b/i.test(s) ? "bank" : "upi"));
    return { ok: true, amount: a, method, detail: method === "qr" ? "QR image attached" : (upi(s) || s.replace(/^\s*(withdraw|withdrawal|wd)\b/i, "").trim()) };
  }

  function findProfile(state, ids, name) {
    state.profiles = state.profiles && typeof state.profiles === "object" ? state.profiles : {};
    const pks = [...new Set(ids.map(phone).filter(Boolean))];
    for (const [id, p] of Object.entries(state.profiles)) if (pks.includes(phone(p?.phone || id))) return { userId: id, profile: p, phone: phone(p?.phone || id) };
    const pk = pks[0] || ""; const uid = pk ? "client_" + pk : "client_wa_" + crypto.createHash("sha1").update(ids.join("|")).digest("hex").slice(0, 12);
    state.profiles[uid] = state.profiles[uid] || { name: name || (pk ? "VIP " + pk : "WhatsApp VIP"), phone: pk, approvalStatus: "pending", vipAccessEnabled: false, autoCreated: true, approvalSource: "whatsapp_financial_image_verify", createdAt: now(), dayRecords: {}, config: { capital: 0, dayTarget: 0 } };
    return { userId: uid, profile: state.profiles[uid], phone: pk };
  }
  function ensureWallet(state, id, prof) { state.wallets = state.wallets && typeof state.wallets === "object" ? state.wallets : {}; const w = state.wallets[id] = state.wallets[id] || { userId: id, name: prof?.name || id, phone: prof?.phone || "", balance: 0, hold: 0, walletHold: 0, creditLimit: 0, ledger: [], createdAt: now() }; w.ledger = Array.isArray(w.ledger) ? w.ledger : []; w.balance = Number(w.balance || 0); w.hold = Number(w.hold || w.walletHold || 0); w.walletHold = w.hold; return w; }
  function nextId(prefix, arr) { return prefix + day() + "-" + String((Array.isArray(arr) ? arr.length : 0) + 1).padStart(4, "0"); }
  function duplicate(arr, key) { return Array.isArray(arr) && key ? arr.find(x => x && x.messageKey === key) : null; }
  async function saveUser(state, id) { await put("profiles/" + id, state.profiles[id]); await put("wallets/" + id, state.wallets[id]); }
  async function audit(state, action, detail) { const a = Array.isArray(state.auditLog) ? state.auditLog : []; a.push({ id: action + "_" + crypto.randomBytes(3).toString("hex"), time: now(), action, detail }); state.auditLog = a.slice(-500); await put("auditLog", state.auditLog); }

  async function createDeposit(m, state, found, caption, imageData, ocr, cls) {
    state.payments = Array.isArray(state.payments) ? state.payments : []; const key = msgKey(m); const old = duplicate(state.payments, key); if (old) return `⚠️ Deposit proof already submitted. ID: #${old.id}`;
    const src = `${caption || ""}\n${ocr.text || ""}`; const a = amount(src); const record = { id: nextId("P", state.payments), userId: found.userId, userName: found.profile?.name || found.userId, phone: found.profile?.phone || found.phone || "", senderJid: candidates(m, m.key?.remoteJid || "")[0] || "", chatJid: m.key?.remoteJid || "", messageKey: key, amount: a, utr: utr(src), transactionId: utr(src), paidToUpi: upi(src), status: "pending", paymentStatus: a > 0 ? "pending_admin_approval" : "needs_amount", source: "whatsapp_ocr_payment_screenshot", imageClass: cls.kind, imageVerifyReason: cls.reason, ocrText: ocr.text || "", ocrProvider: ocr.provider || "", screenshotImageData: imageData || "", image: imageData || "", screenshotHash: hash(imageData), walletCredited: false, riskFlags: a > 0 ? [] : ["missing_amount"], riskLevel: a > 0 ? "MEDIUM" : "HIGH", createdAt: now(), time: new Date().toLocaleString("en-IN", { timeZone: TZ }) };
    state.payments.push(record); await put("payments", state.payments.slice(-1000)); await saveUser(state, found.userId); await audit(state, "deposit_image_verified", { paymentId: record.id, userId: found.userId, imageClass: cls.kind, amount: a });
    return a > 0 ? `✅ Deposit screenshot verified.\nID: #${record.id}\nAmount: ${money(a)}\nStatus: Pending admin approval.` : `📷 Deposit screenshot verified but amount clear nahi mila.\nID: #${record.id}\nAdmin review karega.`;
  }

  async function createWithdrawal(m, state, found, parsed, imageData, ocr, cls) {
    state.withdrawals = Array.isArray(state.withdrawals) ? state.withdrawals : []; const key = msgKey(m); const old = duplicate(state.withdrawals, key); if (old) return `⚠️ Withdrawal request already submitted. ID: #${old.id}`;
    const w = ensureWallet(state, found.userId, found.profile); const available = Math.round((w.balance - w.hold) * 100) / 100; const approved = String(found.profile?.approvalStatus || "").toLowerCase() === "approved"; const holdOk = approved && available + 0.0001 >= parsed.amount;
    if (holdOk) { const hb = w.hold; w.hold = Math.round((hb + parsed.amount) * 100) / 100; w.walletHold = w.hold; w.ledger.push({ id: "WHOLD-" + Date.now(), time: now(), type: "withdrawal_hold", amount: 0, balanceBefore: w.balance, balanceAfter: w.balance, holdBefore: hb, holdAfter: w.hold, source: "whatsapp_ocr_withdrawal_qr" }); }
    const rec = { id: nextId("W", state.withdrawals), userId: found.userId, userName: found.profile?.name || found.userId, phone: found.profile?.phone || found.phone || "", senderJid: candidates(m, m.key?.remoteJid || "")[0] || "", chatJid: m.key?.remoteJid || "", messageKey: key, amount: parsed.amount, method: parsed.method, detail: parsed.detail, qrImageData: parsed.method === "qr" ? (imageData || "") : "", status: "pending", paymentStatus: holdOk ? "pending_approval" : "pending_admin_review", holdApplied: holdOk, holdAmount: holdOk ? parsed.amount : 0, walletBalanceAtRequest: w.balance, walletHoldAfter: w.hold, needsAdminReview: !holdOk, reviewReason: holdOk ? "" : (approved ? "insufficient_withdrawable_balance" : "profile_not_approved"), source: "whatsapp_ocr_withdrawal_qr", imageClass: cls.kind, imageVerifyReason: cls.reason, ocrText: ocr.text || "", ocrProvider: ocr.provider || "", createdAt: now() };
    if (holdOk && w.ledger.length) w.ledger[w.ledger.length - 1].withdrawalId = rec.id;
    state.withdrawals.push(rec); await put("withdrawals", state.withdrawals.slice(-1000)); await saveUser(state, found.userId); await audit(state, "withdrawal_image_verified", { withdrawalId: rec.id, userId: found.userId, imageClass: cls.kind, amount: parsed.amount, holdApplied: holdOk });
    return `✅ Withdrawal request verified.\nID: #${rec.id}\nAmount: ${money(rec.amount)}\nMethod: ${String(rec.method).toUpperCase()}\nStatus: Pending admin approval.`;
  }

  async function reply(sock, chat, body, quoted) { try { if (sock && chat && body) await sock.sendMessage(chat, { text: String(body) }, quoted ? { quoted } : undefined); } catch {} }
  async function processOne(sock, baileys, m) {
    try {
      if (!m?.message || m.key?.fromMe) return false; const chat = m.key?.remoteJid || ""; if (!chat || chat === "status@broadcast") return false;
      const cap = text(m); const img = hasImage(m); if (!img && !/\b(withdraw|withdrawal|wd|deposit|payment|paid|utr|txn|recharge)\b/i.test(cap)) return false;
      const image = img ? await downloadImage(baileys, m) : { data: "", buffer: null }; const ocr = img ? await runOcr(image.data) : { text: "", provider: "none", confidence: 0 };
      const isW = /^\s*(withdraw|withdrawal|wd)\b/i.test(cap); const cls = classifyImage(cap, ocr.text, img, isW);
      if (img && !cls.ok) { await reply(sock, chat, `❌ Image reject.\nReason: ${cls.reason}\nPayment screenshot ya withdrawal QR image bhejo.`, m); return true; }
      const state = await get("", {}) || {}; const ids = candidates(m, chat); const sender = chat.endsWith("@g.us") ? (ids[0] || m.key?.participant || "") : chat; const found = findProfile(state, [sender, ...ids], m.pushName || m.verifiedBizName || ""); ensureWallet(state, found.userId, found.profile);
      let out = "";
      if (isW) { const parsed = parseWithdraw(cap, cls.kind); if (!parsed?.ok) out = "❌ " + (parsed?.message || "Withdrawal format invalid."); else out = await createWithdrawal(m, state, found, parsed, image.data, ocr, cls); }
      else if (cls.kind === "payment_screenshot" || /\b(deposit|payment|paid|utr|txn|recharge)\b/i.test(cap)) out = await createDeposit(m, state, found, cap, image.data, ocr, cls.kind === "text_only" ? { kind: "payment_text", reason: "text_deposit_request" } : cls);
      else return false;
      await reply(sock, chat, out, m); console.log("✅ Financial image verified:", isW ? "withdrawal" : "deposit", found.userId, cls.kind); return true;
    } catch (e) { console.log("Financial image verify error:", e.response ? `HTTP ${e.response.status}` : e.message); return false; }
  }

  const Module = require("module"); const oldLoad = Module._load;
  Module._load = function patchedLoad(req, parent, isMain) {
    const mod = oldLoad.apply(this, arguments);
    try {
      if (req === "@whiskeysockets/baileys" && mod && !mod.__titanFinancialImageVerifyWrapped) {
        const original = mod.default;
        if (typeof original === "function") {
          mod.default = function wrappedSocket() {
            const sock = original.apply(this, arguments);
            if (sock?.ev?.on && !sock.ev.__titanFinancialImageVerifyWrapped) {
              const oldOn = sock.ev.on.bind(sock.ev);
              sock.ev.on = function on(event, handler) {
                if (event === "messages.upsert" && typeof handler === "function") return oldOn(event, async (upsert) => { const list = Array.isArray(upsert?.messages) ? upsert.messages : []; const rest = []; for (const m of list) { if (!(await processOne(sock, mod, m))) rest.push(m); } if (rest.length) return handler({ ...upsert, messages: rest }); });
                return oldOn(event, handler);
              };
              sock.ev.__titanFinancialImageVerifyWrapped = true;
            }
            return sock;
          };
        }
        mod.__titanFinancialImageVerifyWrapped = true;
        console.log("✅ Gateway financial OCR image verifier active", OCR_KEY ? "OCR ON" : "OCR KEY MISSING");
      }
    } catch (e) { console.log("Financial verifier hook error:", e.message); }
    return mod;
  };
}

module.exports = { enabled: true, feature: "gateway_financial_image_verify_v2" };
