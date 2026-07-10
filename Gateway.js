"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
// ============================================================

process.env.FIREBASE_URL = process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json";
process.env.FIREBASE_DB_URL = process.env.FIREBASE_DB_URL || process.env.FIREBASE_URL;

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

// IMPORTANT: gateway_financial_ingest_patch.js intentionally disabled.
// It accepted text-only words such as "Deposit" and created fake payment IDs.
// Strict payment proof handling now lives only in gateway_deposit_ocr_patch.js.
console.log("✅ Text-only deposit ingest disabled; screenshot OCR required");

try { require("./gateway_deposit_ocr_patch.js"); }
catch (err) { console.warn("⚠️ Gateway deposit OCR bridge failed:", err && err.message ? err.message : err); }

require("./legacy-backup/Gateway.js.bak");
