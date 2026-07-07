"use strict";

const state = {
  status: "ready",
  connected: false,
  messagesSent: 0,
  messagesReceived: 0,
  lastMessageAt: null,
  outbox: []
};

function whatsappStatus() {
  return { module: "whatsapp", ...state, queued: state.outbox.length };
}

function sendMessage(to, message) {
  if (!to || !message) {
    const error = new Error("to and message are required");
    error.statusCode = 400;
    throw error;
  }
  const envelope = { id: `${Date.now()}-${state.messagesSent + 1}`, to, message, status: "queued", createdAt: new Date().toISOString() };
  state.outbox.push(envelope);
  state.messagesSent += 1;
  state.lastMessageAt = envelope.createdAt;
  return envelope;
}

function recordInbound(from, message) {
  state.connected = true;
  state.messagesReceived += 1;
  state.lastMessageAt = new Date().toISOString();
  return { from, message, receivedAt: state.lastMessageAt };
}

module.exports = { whatsappStatus, sendMessage, recordInbound };
