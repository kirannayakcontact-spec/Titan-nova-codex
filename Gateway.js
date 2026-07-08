"use strict";

// ============================================================
// TITAN NOVA LEGACY GATEWAY LAUNCHER
// Run WhatsApp Gateway: node Gateway.js
//
// The full previous Titan Nova gateway runtime is preserved in:
//   legacy-backup/Gateway.js.bak
// This launcher loads that restored runtime so old Termux commands keep working.
// ============================================================

require.extensions[".bak"] = require.extensions[".js"];
require("./legacy-backup/Gateway.js.bak");
