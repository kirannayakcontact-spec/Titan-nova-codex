"use strict";

function digits(value){
  let d = String(value || "").replace(/\D/g, "");
  if (d.length === 10) d = "91" + d;
  return d;
}

function messageText(m){
  const x = m?.message || {};
  return String(x.conversation || x.extendedTextMessage?.text || x.imageMessage?.caption || x.documentMessage?.caption || "").trim();
}

function senderNumber(m){
  return digits(m?.key?.participant || m?.key?.remoteJid || "");
}

function normalizeJid(to){
  let jid = String(to || "").trim();
  if (!jid.includes("@")) jid = digits(jid) + "@s.whatsapp.net";
  return jid;
}

module.exports = { digits, messageText, senderNumber, normalizeJid };
