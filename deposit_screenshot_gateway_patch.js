"use strict";

// Titan Nova screenshot-only deposit patch.
// User can send only a payment screenshot image in private chat. The bot creates
// a pending deposit proof for Finance -> Deposit admin verification. Wallet is
// never credited from screenshot alone.

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const Module = require("module");

const PATCH_VERSION = "2026-07-08-screenshot-only-deposit-v2";
const ENABLED = String(process.env.TITAN_DEPOSIT_SCREENSHOT_ENABLED || "1") !== "0";
const ACCEPT_EMPTY_GROUP_IMAGES = String(process.env.TITAN_DEPOSIT_SCREENSHOT_GROUPS || "0") === "1";
const STATE_DIR = process.env.TITAN_STATE_DIR || process.cwd();
const PROOF_DIR = path.join(STATE_DIR, "payment_uploads", "deposit_screenshots");
const PROCESSED_FILE = path.join(STATE_DIR, "titan_deposit_screenshot_processed.json");
const DEFAULT_FIREBASE_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/titan_master_data.json";
const FIREBASE_URL = (process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || DEFAULT_FIREBASE_URL).replace(/\/$/, "");

try { fs.mkdirSync(PROOF_DIR, { recursive: true }); } catch (e) {}
let processed = new Set();
try { const raw = JSON.parse(fs.readFileSync(PROCESSED_FILE, "utf8")); if (Array.isArray(raw)) processed = new Set(raw.slice(-1000)); } catch (e) {}
function saveProcessed() { try { fs.writeFileSync(PROCESSED_FILE, JSON.stringify(Array.from(processed).slice(-1000))); } catch (e) {} }
function nowIso() { return new Date().toISOString(); }
function pad(n) { return String(n).padStart(2, "0"); }
function dayStamp() { const d = new Date(); return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`; }
function normPhone(v) { const d = String(v || "").replace(/\D+/g, ""); return d.length === 10 ? "91" + d : d; }
function jidPhone(jid) { return normPhone(String(jid || "").split("@")[0].split(":")[0]); }
function shortHash(v, n=12) { return crypto.createHash("sha256").update(String(v || "")).digest("hex").slice(0, n); }
function bufferHash(buf) { return crypto.createHash("sha256").update(buf).digest("hex"); }
function fbChildUrl(parts) { const base = FIREBASE_URL.replace(/\.json$/i, ""); const clean = parts.map(p => encodeURIComponent(String(p))).join("/"); return `${base}/${clean}.json`; }
async function fbGet(parts) { const axios = require("axios"); const r = await axios.get(fbChildUrl(parts), { timeout: 12000 }); return r.data; }
async function fbPut(parts, value) { const axios = require("axios"); const r = await axios.put(fbChildUrl(parts), value, { timeout: 15000 }); return r.data; }
async function fbPatch(parts, value) { const axios = require("axios"); const r = await axios.patch(fbChildUrl(parts), value, { timeout: 15000 }); return r.data; }
function unwrapMessage(msg) { let m = msg || {}; for (let i=0;i<5;i++){ if(m.ephemeralMessage?.message)m=m.ephemeralMessage.message; else if(m.viewOnceMessage?.message)m=m.viewOnceMessage.message; else if(m.viewOnceMessageV2?.message)m=m.viewOnceMessageV2.message; else break; } return m; }
function getImageMessage(message) { const m = unwrapMessage(message); return m.imageMessage || null; }
function parseCaption(caption) { const text = String(caption || ""); const out = { amount:null, utr:"", text }; const am = text.match(/(?:₹|rs\.?|inr)?\s*([1-9][0-9]{1,6})(?:\.00)?/i); if(am) out.amount = Number(am[1]); const um = text.match(/(?:utr|upi|txn|transaction|ref(?:erence)?)[^a-z0-9]{0,12}([a-z0-9]{8,32})/i) || text.match(/\b([0-9]{10,18})\b/); if(um) out.utr = String(um[1] || "").toUpperCase(); return out; }
function hasDepositWords(text) { const t = String(text || "").toLowerCase(); return t.includes("deposit") || t.includes("paid") || t.includes("payment") || t.includes("utr") || t.includes("upi") || t.includes("txn") || t.includes("transaction"); }
function riskFor({ amount, utr, duplicate }) { const reasons = ["manual_bank_verification_required"]; if(!amount)reasons.push("amount_missing_from_message"); if(!utr)reasons.push("utr_missing_from_message"); if(duplicate)reasons.push("duplicate_screenshot_hash"); return { level: duplicate ? "high" : (!amount || !utr ? "high" : "medium"), reasons, autoCreditBlocked:true }; }
async function downloadImage(downloadContentFromMessage, imageMessage) { const stream = await downloadContentFromMessage(imageMessage, "image"); const chunks=[]; for await (const chunk of stream) chunks.push(chunk); return Buffer.concat(chunks); }
async function safeReply(sock, jid, text, quoted) { try { await sock.sendMessage(jid, { text }, quoted ? { quoted } : undefined); } catch(e){} }

async function handleDepositScreenshot(sock, upsert, baileys) {
  if (!ENABLED || !sock || !upsert || !Array.isArray(upsert.messages)) return;
  const downloadContentFromMessage = baileys.downloadContentFromMessage;
  if (typeof downloadContentFromMessage !== "function") return;
  for (const m of upsert.messages) {
    try {
      if (!m || !m.message || m.key?.fromMe) continue;
      const imageMessage = getImageMessage(m.message);
      if (!imageMessage) continue;
      const caption = String(imageMessage.caption || "");
      const sourceJid = m.key.remoteJid || "";
      const isGroup = String(sourceJid).endsWith("@g.us");
      if (isGroup && !ACCEPT_EMPTY_GROUP_IMAGES && !hasDepositWords(caption)) continue;
      const msgKey = `${sourceJid}:${m.key?.id || ""}:${m.key?.participant || ""}`;
      if (processed.has(msgKey)) continue;
      processed.add(msgKey); saveProcessed();

      const senderJid = m.key.participant || m.key.remoteJid || "";
      const phone = jidPhone(senderJid);
      const parsed = parseCaption(caption);
      const buf = await downloadImage(downloadContentFromMessage, imageMessage);
      if (!buf || !buf.length) continue;
      const imgHash = bufferHash(buf);
      const duplicate = await fbGet(["depositImageIndex", imgHash]).catch(() => null);
      const depositId = `DEP-WA-${dayStamp()}-${shortHash(msgKey, 6).toUpperCase()}`;
      const filename = `${depositId}.jpg`;
      const fullPath = path.join(PROOF_DIR, filename);
      fs.writeFileSync(fullPath, buf);
      const proofUrl = `/api/deposit_professional/proof/${encodeURIComponent(filename)}`;
      const risk = riskFor({ amount: parsed.amount, utr: parsed.utr, duplicate: !!duplicate });
      const status = duplicate ? "duplicate_review" : "needs_admin_review";
      const rec = { id:depositId, depositId, version:PATCH_VERSION, status, stage:status, source:"whatsapp_screenshot_only", userId:phone||"guest", profileId:phone||"guest", phoneNumber:phone, customerName:m.pushName||"", amount:parsed.amount||0, utr:parsed.utr||"", proofUrl, screenshotUrl:proofUrl, proofLocalFile:fullPath, caption, sourceJid, senderJid, whatsappMessageId:m.key?.id||"", imageHash:imgHash, screenshotOnly:true, needsManualAmount:!parsed.amount, needsManualUtr:!parsed.utr, risk, duplicateOf:duplicate||null, walletCredit:{applied:false, source:PATCH_VERSION, blockedUntilAdminApprove:true}, createdAt:nowIso(), updatedAt:nowIso() };
      await fbPut(["depositRequests", depositId], rec);
      await fbPut(["depositImageIndex", imgHash], { depositId, phoneNumber:phone, createdAt:rec.createdAt, status });
      await fbPatch(["depositAuditLog", depositId, shortHash(depositId + Date.now(), 10)], { depositId, event:"whatsapp_screenshot_received", time:nowIso(), detail:{ phoneNumber:phone, status, risk } });
      await safeReply(sock, sourceJid, `✅ Payment screenshot received.\n\nStatus: Pending admin verification.\nWallet admin approve ke baad credit hoga.\nID: ${depositId}`, m);
      console.log("✅ Deposit screenshot proof saved:", depositId, phone, status);
    } catch (e) { console.error("⚠️ Deposit screenshot handler failed:", e && e.message ? e.message : e); }
  }
}

function installPatch() {
  if (!ENABLED || global.__TITAN_DEPOSIT_SCREENSHOT_PATCH_INSTALLED__) return;
  global.__TITAN_DEPOSIT_SCREENSHOT_PATCH_INSTALLED__ = true;
  const originalLoad = Module._load;
  Module._load = function patchedLoad(request, parent, isMain) {
    const exported = originalLoad.apply(this, arguments);
    if (request === "@whiskeysockets/baileys" && exported && !exported.__titanDepositScreenshotWrapped) {
      const originalMake = exported.default;
      if (typeof originalMake === "function") {
        exported.default = function titanDepositMakeWASocketWrapper() {
          const sock = originalMake.apply(this, arguments);
          try { if (sock?.ev?.on && !sock.__titanDepositScreenshotListener) { sock.__titanDepositScreenshotListener = true; sock.ev.on("messages.upsert", (upsert) => handleDepositScreenshot(sock, upsert, exported)); console.log("✅ Titan screenshot-only deposit listener active"); } } catch(e) { console.error("⚠️ Could not attach deposit screenshot listener:", e && e.message ? e.message : e); }
          return sock;
        };
      }
      exported.__titanDepositScreenshotWrapped = true;
    }
    return exported;
  };
  console.log("✅ Titan screenshot-only deposit patch installed", PATCH_VERSION);
}

installPatch();
