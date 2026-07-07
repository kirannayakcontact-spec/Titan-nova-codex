"use strict";

const { getConfig } = require("./config");

function firebaseStatus() {
  const { firebaseUrl } = getConfig();
  return { configured: Boolean(firebaseUrl), urlPreview: firebaseUrl ? `${firebaseUrl.slice(0, 24)}...` : "" };
}

module.exports = { firebaseStatus };
