"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
// ============================================================

// Your live Firebase. This prevents blank Ledger / split data when env is not set.
process.env.FIREBASE_URL = process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json";
process.env.FIREBASE_DB_URL = process.env.FIREBASE_DB_URL || process.env.FIREBASE_URL;

require.extensions[".bak"] = require.extensions[".js"];

// Screenshot-only deposit listener:
// User sends only payment screenshot -> pending Finance/Deposit review.
try {
  require("./deposit_screenshot_gateway_patch.js");
} catch (e) {
  console.error("⚠️ Deposit screenshot patch failed:", e && e.message ? e.message : e);
}

require("./legacy-backup/Gateway.js.bak");
