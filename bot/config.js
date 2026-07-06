"use strict";

function getBotConfig() {
  return {
    port: Number(process.env.PORT || 3000),
    host: process.env.HOST || process.env.TITAN_GATEWAY_HOST || "127.0.0.1",
    appTimezone: process.env.APP_TZ || "Asia/Kolkata",
    firebaseUrl: process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || ""
  };
}

module.exports = { getBotConfig };
