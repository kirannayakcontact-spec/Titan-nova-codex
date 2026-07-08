"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
// ============================================================

require.extensions[".bak"] = require.extensions[".js"];

// Screenshot-only deposit listener:
// User sends only payment screenshot -> pending Finance/Deposit review.
try {
  require("./deposit_screenshot_gateway_patch.js");
} catch (e) {
  console.error("⚠️ Deposit screenshot patch failed:", e && e.message ? e.message : e);
}

require("./legacy-backup/Gateway.js.bak");
