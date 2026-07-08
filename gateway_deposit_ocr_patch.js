"use strict";

// ============================================================
// TITAN NOVA — WHATSAPP DEPOSIT OCR BRIDGE
// Hooks Baileys before the legacy gateway starts. When a user sends
// a payment screenshot with a deposit/proof caption, the image is
// forwarded to Flask /api/deposit/ocr-verify for OCR validation.
// ============================================================

const axios = require("axios");
const crypto = require("crypto");

const FEATURE_VERSION = "2026-07-09-whatsapp-deposit-ocr-bridge-v1";
const BACKEND_URL = String(process.env.TITAN_BACKEND_URL || process.env.FLASK_URL || process.env.BACKEND_URL || "http://127.0.0.1:5000").replace(/\/$/, "");
const ENABLED = !["0", "false", "no", "off"].includes(String(process.env.TITAN_DEPOSIT_OCR_WA_ENABLED || "1").toLowerCase());
const MAX_IMAGE_BYTES = Math.max(Number(process.env.TITAN_DEPOSIT_OCR_MAX_IMAGE_BYTES || 6 * 1024 * 1024), 256 * 1024);
const seen = new Map();

function remember(key){
  const now = Date.now();
  seen.set(key, now);
  for(const [k,t] of seen.entries()) if(now - t > 30 * 60 * 1000) seen.delete(k);
}
function hasSeen(key){ return seen.has(key); }
function textOfMessage(message){
  const m = message || {};
  const img = m.imageMessage || (m.viewOnceMessage && m.viewOnceMessage.message && m.viewOnceMessage.message.imageMessage) || (m.viewOnceMessageV2 && m.viewOnceMessageV2.message && m.viewOnceMessageV2.message.imageMessage);
  return String((img && img.caption) || m.conversation || (m.extendedTextMessage && m.extendedTextMessage.text) || "");
}
function imageMessageOf(message){
  const m = message || {};
  return m.imageMessage || (m.viewOnceMessage && m.viewOnceMessage.message && m.viewOnceMessage.message.imageMessage) || (m.viewOnceMessageV2 && m.viewOnceMessageV2.message && m.viewOnceMessageV2.message.imageMessage) || null;
}
function isDepositProofCaption(text){
  const t = String(text || "").toLowerCase();
  if(!t.trim()) return false;
  return /\b(deposit|payment|paid|proof|screenshot|utr|upi|add\s*money|wallet)\b/i.test(t);
}
function parseAmount(text){
  const s = String(text || "").replace(/,/g, "");
  const m = s.match(/(?:₹|rs\.?|inr|amount|deposit|paid|payment)?\s*([0-9]+(?:\.[0-9]{1,2})?)/i);
  const n = m ? Number(m[1]) : 0;
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : 0;
}
function senderPhone(jid){
  const digits = String(jid || "").split("@")[0].replace(/\D+/g, "");
  return digits;
}
async function streamToBuffer(stream){
  const chunks = [];
  let total = 0;
  for await (const chunk of stream){
    const b = Buffer.from(chunk);
    total += b.length;
    if(total > MAX_IMAGE_BYTES) throw new Error("Image too large for deposit OCR");
    chunks.push(b);
  }
  return Buffer.concat(chunks);
}
function shortReason(result){
  const st = result && result.status ? String(result.status) : "ERROR";
  const reason = result && result.reason ? String(result.reason) : "Unknown response";
  return `${st}: ${reason}`.slice(0, 240);
}
async function sendReply(sock, chatJid, text, quoted){
  try{
    if(sock && chatJid) await sock.sendMessage(chatJid, { text }, quoted ? { quoted } : undefined);
  }catch(e){ console.warn("Deposit OCR reply failed:", e && e.message ? e.message : e); }
}
async function handleDepositImage(sock, baileys, msg){
  try{
    if(!ENABLED || !sock || !msg || !msg.message) return;
    const chatJid = msg.key && msg.key.remoteJid;
    const senderJid = (msg.key && (msg.key.participant || msg.key.remoteJid)) || "";
    const imageMessage = imageMessageOf(msg.message);
    if(!imageMessage) return;
    const caption = textOfMessage(msg.message);
    if(!isDepositProofCaption(caption)) return;
    const mid = (msg.key && msg.key.id) || crypto.createHash("sha1").update(JSON.stringify(msg.key || {}) + caption).digest("hex");
    if(hasSeen(mid)) return;
    remember(mid);

    const stream = await baileys.downloadContentFromMessage(imageMessage, "image");
    const image = await streamToBuffer(stream);
    const amount = parseAmount(caption);
    const phone = senderPhone(senderJid || chatJid);
    const hash = crypto.createHash("sha256").update(image).digest("hex").slice(0, 12);

    const payload = {
      image_base64: image.toString("base64"),
      user_id: phone || senderJid || chatJid,
      phone_number: phone,
      expected_amount: amount,
      caption,
      source: "whatsapp_gateway",
      whatsapp_chat_jid: chatJid,
      whatsapp_sender_jid: senderJid,
      image_hash_preview: hash
    };
    const res = await axios.post(`${BACKEND_URL}/api/deposit/ocr-verify`, payload, { timeout: 25000, maxBodyLength: MAX_IMAGE_BYTES + 1024 * 1024 });
    const data = res && res.data ? res.data : {};
    const status = String(data.status || "").toUpperCase();
    if(status === "OCR_VALID"){
      await sendReply(sock, chatJid, `✅ Payment proof received. OCR valid hai. Admin approve ke baad wallet credit hoga.\nProof ID: ${data.proof_id || "-"}`, msg);
    } else if(["DUPLICATE_UTR", "DUPLICATE_IMAGE", "AMOUNT_MISMATCH", "RECEIVER_MISMATCH"].includes(status)){
      await sendReply(sock, chatJid, `❌ Payment proof rejected: ${shortReason(data)}\nAdmin se contact karein agar screenshot genuine hai.`, msg);
    } else {
      await sendReply(sock, chatJid, `⏳ Payment proof received. Admin review required.\n${shortReason(data)}\nProof ID: ${data.proof_id || "-"}`, msg);
    }
  }catch(e){
    console.warn("Deposit OCR bridge failed:", e && e.message ? e.message : e);
    try{
      const chatJid = msg && msg.key && msg.key.remoteJid;
      await sendReply(sock, chatJid, "⚠️ Payment screenshot receive hua, lekin OCR check abhi fail hua. Admin manually review karega.", msg);
    }catch(_e){}
  }
}

try{
  if(ENABLED){
    const baileys = require("@whiskeysockets/baileys");
    const original = baileys && baileys.default;
    if(original && !original.__titanDepositOcrWrapped){
      function wrappedMakeWASocket(...args){
        const sock = original(...args);
        try{
          const oldOn = sock && sock.ev && sock.ev.on ? sock.ev.on.bind(sock.ev) : null;
          if(oldOn && !sock.__titanDepositOcrAttached){
            sock.__titanDepositOcrAttached = true;
            oldOn("messages.upsert", async (upsert) => {
              try{
                const messages = Array.isArray(upsert && upsert.messages) ? upsert.messages : [];
                for(const msg of messages) await handleDepositImage(sock, baileys, msg);
              }catch(e){ console.warn("Deposit OCR upsert hook failed:", e && e.message ? e.message : e); }
            });
          }
        }catch(e){ console.warn("Deposit OCR socket attach failed:", e && e.message ? e.message : e); }
        return sock;
      }
      wrappedMakeWASocket.__titanDepositOcrWrapped = true;
      baileys.default = wrappedMakeWASocket;
      console.log(`✅ Deposit OCR WhatsApp bridge loaded: ${FEATURE_VERSION}`);
    }
  } else {
    console.log("ℹ️ Deposit OCR WhatsApp bridge disabled by TITAN_DEPOSIT_OCR_WA_ENABLED=0");
  }
}catch(err){
  console.warn("⚠️ Deposit OCR WhatsApp bridge failed to load:", err && err.message ? err.message : err);
}
