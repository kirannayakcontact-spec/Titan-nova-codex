"use strict";

// Compatibility launcher for downstream integrations. The canonical gateway
// implementation and all webhook listeners live in whatsapp_multi_session.js.
console.warn("⚠️ Gateway.js is deprecated; starting whatsapp_multi_session.js");
require("./whatsapp_multi_session.js");
