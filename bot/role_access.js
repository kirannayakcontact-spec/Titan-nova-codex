"use strict";

const { RESTRICTED_ROLES } = require("./session_config.js");
const { digits, senderNumber } = require("./message_utils.js");

const restricted = new Set(RESTRICTED_ROLES);

function configuredAdmins(role){
  return String(process.env[`WHATSAPP_${role.toUpperCase()}_ADMINS`] || process.env.TITAN_AUTHORIZED_WHATSAPP_NUMBERS || process.env.WHATSAPP_OWNER_NUMBER || "")
    .split(",")
    .map(digits)
    .filter(Boolean);
}

function allowed(role, m){
  if (!restricted.has(role)) return true;
  return configuredAdmins(role).includes(senderNumber(m));
}

module.exports = { allowed, configuredAdmins, restricted };
