function cleanJid(value){
  return String(value || "").trim().replace(/:\d+(?=@)/, "");
}

function digits(value){
  let d = String(value || "").replace(/\D/g, "");
  if (d.length === 10) d = "91" + d;
  return d;
}

function unwrapMessage(message){
  let current = message?.message || message || {};
  for (let i = 0; i < 4; i += 1) {
    const wrapped = current?.ephemeralMessage?.message
      || current?.viewOnceMessage?.message
      || current?.viewOnceMessageV2?.message
      || current?.documentWithCaptionMessage?.message;
    if (!wrapped || wrapped === current) break;
    current = wrapped;
  }
  return current || {};
}

function messageText(message){
  const x = unwrapMessage(message);
  return String(
    x.conversation
      || x.extendedTextMessage?.text
      || x.imageMessage?.caption
      || x.videoMessage?.caption
      || x.documentMessage?.caption
      || x.buttonsResponseMessage?.selectedButtonId
      || x.buttonsResponseMessage?.selectedDisplayText
      || x.listResponseMessage?.singleSelectReply?.selectedRowId
      || x.templateButtonReplyMessage?.selectedId
      || ""
  ).trim();
}

function senderCandidates(message){
  const key = message?.key || {};
  const values = [
    key.participant,
    key.participantPn,
    key.senderPn,
    key.participantAlt,
    key.remoteJid,
    key.remoteJidAlt,
    message?.participant,
    message?.participantPn,
    message?.senderPn,
  ].map(cleanJid).filter(Boolean);
  return [...new Set(values)];
}

function senderNumber(message){
  for (const candidate of senderCandidates(message)) {
    const value = digits(candidate);
    if (value) return value;
  }
  return "";
}

function normalizeJid(to){
  let jid = cleanJid(to);
  if (!jid.includes("@")) jid = digits(jid) + "@s.whatsapp.net";
  return jid;
}

module.exports = { cleanJid, digits, unwrapMessage, messageText, senderCandidates, senderNumber, normalizeJid };
