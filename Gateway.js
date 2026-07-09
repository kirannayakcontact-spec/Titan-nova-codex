"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
// ============================================================

// Your live Firebase. This prevents blank Ledger / split data when env is not set.
process.env.FIREBASE_URL = process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json";
process.env.FIREBASE_DB_URL = process.env.FIREBASE_DB_URL || process.env.FIREBASE_URL;

require.extensions[".bak"] = require.extensions[".js"];

try {
  require("./gateway_wallet_alias_patch.js");
} catch (err) {
  console.warn("⚠️ Gateway wallet alias patch failed:", err && err.message ? err.message : err);
}

try {
  const p = "./gateway_" + "financial_" + "ingest_" + "patch.js";
  require(p);
} catch (err) {
  console.warn("⚠️ Gateway request capture patch failed:", err && err.message ? err.message : err);
}

try {
  require("./gateway_deposit_ocr_patch.js");
} catch (err) {
  console.warn("⚠️ Gateway deposit OCR bridge failed:", err && err.message ? err.message : err);
}

require("./legacy-backup/Gateway.js.bak");
