"use strict";

function getConfig() {
  return {
    appName: process.env.APP_NAME || "Andres Berlin",
    host: process.env.HOST || "127.0.0.1",
    port: Number(process.env.PORT || 3000),
    firebaseUrl: process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || ""
  };
}

module.exports = { getConfig };
