"use strict";

const blockedRecipients = new Set((process.env.BLOCKED_RECIPIENTS || "").split(",").map((item) => item.trim()).filter(Boolean));
const decisions = [];

function evaluateMessage({ to, message }) {
  const reasons = [];
  if (!to) reasons.push("missing recipient");
  if (!message) reasons.push("missing message");
  if (blockedRecipients.has(to)) reasons.push("recipient blocked");
  if (String(message || "").length > 1000) reasons.push("message too long");
  const decision = { allowed: reasons.length === 0, reasons, checkedAt: new Date().toISOString() };
  decisions.unshift(decision);
  return decision;
}

function safetyStatus() {
  return { status: "ok", module: "safety", blockedRecipients: blockedRecipients.size, checks: decisions.length, latest: decisions.slice(0, 5) };
}

module.exports = { safetyStatus, evaluateMessage };
