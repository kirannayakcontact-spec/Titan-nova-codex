"use strict";

// Compatibility entrypoint. Bot features are split into focused modules under
// bot/: session_config, message_utils, role_access, session_routes, and
// session_manager. Keep this file so the canonical gateway and older tooling can
// continue requiring ./multi_session_manager.js without duplicating logic.
const { TitanMultiSessionManager } = require("./bot/session_manager.js");
const { ROLES } = require("./bot/session_config.js");
const { messageText, senderNumber } = require("./bot/message_utils.js");

module.exports = { TitanMultiSessionManager, ROLES, messageText, senderNumber };
