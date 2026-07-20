"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
// ============================================================

process.env.FIREBASE_URL = process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json";
process.env.FIREBASE_DB_URL = process.env.FIREBASE_DB_URL || process.env.FIREBASE_URL;

// The deploy guides and operators use Gateway-specific names so Flask and the
// Gateway can be configured independently.  The legacy runtime reads PORT/HOST,
// therefore normalize the public launcher contract before loading it.  Keep the
// generic variables as the higher-priority compatibility override.
process.env.PORT = process.env.PORT || process.env.GATEWAY_PORT || "3000";
process.env.HOST = process.env.HOST || process.env.GATEWAY_HOST || process.env.TITAN_GATEWAY_HOST || "127.0.0.1";

try {
  const qrTerminal = require("qrcode-terminal");
  if (qrTerminal && typeof qrTerminal.generate === "function" && !qrTerminal.generate.__titanCompactQr) {
    const originalGenerate = qrTerminal.generate.bind(qrTerminal);
    const compactGenerate = function (input, opts, cb) {
      let options = opts;
      let callback = cb;
      if (typeof opts === "function") { callback = opts; options = {}; }
      options = Object.assign({}, options || {}, { small: true });
      return originalGenerate(input, options, callback);
    };
    compactGenerate.__titanCompactQr = true;
    qrTerminal.generate = compactGenerate;
    console.log("✅ Termux compact WhatsApp QR mode enabled");
  }
} catch (err) {
  console.warn("⚠️ Compact QR patch failed:", err && err.message ? err.message : err);
}

try { require("./gateway_codex_preflight_patch.js"); }
catch (err) { console.warn("⚠️ Gateway Codex preflight patch failed:", err && err.message ? err.message : err); }

try { require("./gateway_firebase_guard_patch.js"); }
catch (err) { console.warn("⚠️ Gateway Firebase guard failed:", err && err.message ? err.message : err); }

require.extensions[".bak"] = require.extensions[".js"];

try { require("./gateway_wallet_alias_patch.js"); }
catch (err) { console.warn("⚠️ Gateway wallet alias patch failed:", err && err.message ? err.message : err); }

// Strict payment proof handling is image-only and lives in the OCR bridge.
console.log("✅ Text-only deposit ingest removed; screenshot OCR required");
try { require("./gateway_deposit_ocr_patch.js"); }
catch (err) { console.warn("⚠️ Gateway deposit OCR bridge failed:", err && err.message ? err.message : err); }

// Withdrawal is handled separately so removing unsafe deposit ingest never disables it.
try { require("./gateway_withdrawal_runtime_patch.js"); }
catch (err) { console.warn("⚠️ Gateway withdrawal runtime failed:", err && err.message ? err.message : err); }

require("./legacy-backup/Gateway.js.bak");
