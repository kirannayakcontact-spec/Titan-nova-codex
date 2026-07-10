"use strict";

const axios = require("axios");
const crypto = require("crypto");

const FEATURE_VERSION = "2026-07-10-whatsapp-deposit-ocr-strict-v2";
const BACKEND_URL = String(process.env.TITAN_BACKEND_URL || process.env.FLASK_URL || process.env.BACKEND_URL || "http://127.0.0.1:5000").replace(/\/$/, "");
const ENABLED = !["0", "false", "no", "off"].includes(String(process.env.TITAN_DEPOSIT_OCR_WA_ENABLED || "1").toLowerCase());
const MAX_IMAGE_BYTES = Math.max(Number(process.env.TITAN_DEPOSIT_OCR_MAX_IMAGE_BYTES || 6 * 1024 * 1024), 256 * 1024);
const seen = new Map();

function remember(key){ const now = Date.now(); seen.set(key, now); for(const [k,t] of seen.entries()) if(now - t > 30 * 60 * 1000) seen.delete(k); }
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
function parseAmount(text){
  const s = String(text || "").replace(/,/g, "");
  const m = s.match(/(?:₹|rs\.?|inr|amount|deposit|paid|payment)?\s*([0-9]+(?:\.[0-9]{1,2})?)/i);
  const n = m ? Number(m[1]) : 0;
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : 0;
}
function senderPhone(jid){ return String(jid || "").split("@")[0].replace(/\D+/g, ""); }
async function streamToBuffer(stream){
  const chunks = []; let total = 0;
  for await (const chunk of stream){ const b = Buffer.from(chunk); total += b.length; if(total > MAX_IMAGE_BYTES) throw new Error("Image too large for deposit OCR"); chunks.push(b); }
  return Buffer.concat(chunks);
}
async function sendReply(sock, chatJid, text, quoted){
  try{ if(sock && chatJid) await sock.sendMessage(chatJid, { text }, quoted ? { quoted } : undefined); }
  catch(e){ console.warn("Deposit OCR reply failed:", e && e.message ? e.message : e); }
}

async function handleDepositImage(sock, baileys, msg){
  try{
    if(!ENABLED || !sock || !msg || !msg.message || msg.key?.fromMe) return;
    const chatJid = msg.key && msg.key.remoteJid;
    if(!chatJid || chatJid === "status@broadcast") return;
    const senderJid = (msg.key && (msg.key.participant || msg.key.remoteJid)) || "";
    const imageMessage = imageMessageOf(msg.message);
    if(!imageMessage) return; // text-only "Deposit" can never create a proof

    const caption = textOfMessage(msg.message);
    const mid = (msg.key && msg.key.id) || crypto.createHash("sha1").update(JSON.stringify(msg.key || {}) + caption).digest("hex");
    if(hasSeen(mid)) return;
    remember(mid);

    const stream = await baileys.downloadContentFromMessage(imageMessage, "image");
    const image = await streamToBuffer(stream);
    if(!image.length) return;

    const amount = parseAmount(caption);
    const phone = senderPhone(senderJid || chatJid);
    const hash = crypto.createHash("sha256").update(image).digest("hex");
    const payload = {
      image_base64: image.toString("base64"),
      user_id: phone || senderJid || chatJid,
      phone_number: phone,
      expected_amount: amount,
      caption,
      source: "whatsapp_gateway_strict_image_only",
      whatsapp_chat_jid: chatJid,
      whatsapp_sender_jid: senderJid,
      image_hash_preview: hash.slice(0, 12)
    };

    const res = await axios.post(`${BACKEND_URL}/api/deposit/ocr-verify`, payload, { timeout: 30000, maxBodyLength: MAX_IMAGE_BYTES + 1024 * 1024 });
    const data = res && res.data ? res.data : {};
    const status = String(data.status || "").toUpperCase();

    if(status === "OCR_VALID"){
      const ex = data.extracted || {};
      await sendReply(sock, chatJid,
        `✅ Payment screenshot verified.\nAmount: ₹${ex.amount || amount || "-"}\nUTR: ${ex.utr || "-"}\nReceiver UPI: ${ex.receiver_upi || "-"}\nProof ID: ${data.proof_id || "-"}\nStatus: Admin approval pending.`, msg);
      return;
    }

    if(status === "DUPLICATE_UTR" || status === "DUPLICATE_IMAGE"){
      await sendReply(sock, chatJid, "❌ Ye payment screenshot/UTR pehle submit ho chuka hai. Naya proof ID nahi bana.", msg);
      return;
    }
    if(status === "RECEIVER_MISMATCH"){
      await sendReply(sock, chatJid, `❌ Payment galat UPI receiver ko hua hai.\n${data.reason || "Receiver UPI match nahi hua."}\nKoi proof ID nahi bana.`, msg);
      return;
    }
    if(status === "AMOUNT_MISMATCH"){
      await sendReply(sock, chatJid, `❌ Screenshot amount match nahi hua.\n${data.reason || "Amount mismatch."}\nKoi proof ID nahi bana.`, msg);
      return;
    }

    await sendReply(sock, chatJid,
      `❌ Valid payment screenshot verify nahi hua.\n${data.reason || "Amount, success status, UTR ya receiver UPI clear nahi mila."}\nPayment app ka successful transaction screenshot dobara bhejo. Koi proof ID nahi bana.`, msg);
  }catch(e){
    console.warn("Deposit OCR bridge failed:", e && e.message ? e.message : e);
    try{
      const chatJid = msg && msg.key && msg.key.remoteJid;
      await sendReply(sock, chatJid, "⚠️ Screenshot OCR check fail hua. Koi payment ID nahi bana. Clear successful payment screenshot dobara bhejo.", msg);
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
      console.log(`✅ Strict image-only Deposit OCR loaded: ${FEATURE_VERSION}`);
    }
  }
}catch(err){ console.warn("⚠️ Deposit OCR WhatsApp bridge failed to load:", err && err.message ? err.message : err); }
