"use strict";

const { getCollection, pushRecord, setRecord } = require("./firebase");

const state = {
  status: "ready",
  connected: false,
  messagesSent: 0,
  messagesReceived: 0,
  lastMessageAt: null,
  outbox: []
};

async function refreshState() {
  const persisted = await getCollection("whatsapp/state");
  Object.assign(state, persisted, { outbox: Array.isArray(persisted.outbox) ? persisted.outbox : state.outbox });
  return state;
}

async function persistState() {
  await setRecord("whatsapp/state", state);
}

async function whatsappStatus() {
  await refreshState();
  return { module: "whatsapp", ...state, queued: state.outbox.length };
}

async function sendMessage(to, message) {
  if (!to || !message) {
    const error = new Error("to and message are required");
    error.statusCode = 400;
    throw error;
  }
  await refreshState();
  const envelope = { id: `${Date.now()}-${state.messagesSent + 1}`, to, message, status: "queued", createdAt: new Date().toISOString() };
  state.outbox.push(envelope);
  state.messagesSent += 1;
  state.lastMessageAt = envelope.createdAt;
  await persistState();
  await pushRecord("whatsapp/messages", envelope, envelope.id);
  return envelope;
}

async function recordInbound(from, message) {
  await refreshState();
  state.connected = true;
  state.messagesReceived += 1;
  state.lastMessageAt = new Date().toISOString();
  const inbound = { from, message, receivedAt: state.lastMessageAt };
  await persistState();
  await pushRecord("whatsapp/inbound", inbound);
  return inbound;
}

module.exports = { whatsappStatus, sendMessage, recordInbound };
