"use strict";

const { getBotConfig } = require("./config");

function firebaseUrl() {
  return getBotConfig().firebaseUrl;
}

module.exports = { firebaseUrl };
