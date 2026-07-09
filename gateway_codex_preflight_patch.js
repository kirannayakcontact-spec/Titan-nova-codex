"use strict";

// Titan Nova Codex Gateway preflight patch.
// Loaded before the legacy Gateway runtime so it can set safe defaults and crash guards
// without editing legacy-backup/Gateway.js.bak directly.

(function titanCodexGatewayPreflight(){
  if (global.__TITAN_CODEX_GATEWAY_PREFLIGHT_V1__) return;
  global.__TITAN_CODEX_GATEWAY_PREFLIGHT_V1__ = true;

  const fs = require("fs");
  const path = require("path");
  const VERSION = "2026-07-09-codex-clean-bugs-v1";
  const STATE_DIR = process.env.TITAN_STATE_DIR || process.cwd();
  const LOG_FILE = path.join(STATE_DIR, "titan_codex_gateway_events.jsonl");

  function boolEnv(name, fallback){
    const raw = process.env[name];
    if (raw === undefined || raw === null || raw === "") return fallback;
    return /^(1|true|yes|on)$/i.test(String(raw).trim());
  }

  function event(kind, severity, message, detail){
    const rec = {
      time: new Date().toISOString(),
      version: VERSION,
      kind: String(kind || "event").slice(0, 80),
      severity: String(severity || "info").slice(0, 20),
      message: String(message || "").slice(0, 600),
      detail: detail || {}
    };
    try { fs.mkdirSync(STATE_DIR, {recursive:true}); } catch (_) {}
    try { fs.appendFileSync(LOG_FILE, JSON.stringify(rec) + "\n"); } catch (_) {}
    const prefix = severity === "error" ? "❌" : severity === "warning" ? "⚠️" : "✅";
    try { console.log(prefix, "Titan Codex Gateway:", rec.message); } catch (_) {}
    return rec;
  }

  function setDefault(name, value){
    if (!process.env[name]) process.env[name] = value;
  }

  setDefault("FIREBASE_URL", "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json");
  setDefault("FIREBASE_DB_URL", process.env.FIREBASE_URL);
  setDefault("APP_TZ", "Asia/Kolkata");

  setDefault("RESULT_SCRAPE_CONFIRM_COUNT", "2");
  setDefault("SCHEDULE_RECOVERY_MINUTES", "10");
  setDefault("TITAN_GATEWAY_STATE_CACHE_TTL_MS", "250");
  setDefault("WHATSAPP_TARGET_SYNC_INTERVAL_MS", "60000");

  if (!process.env.RESULT_SOURCE_NAME) process.env.RESULT_SOURCE_NAME = "dpbosse.net";
  if (!process.env.RESULT_SOURCE_URL) process.env.RESULT_SOURCE_URL = "https://dpbosse.net/";

  const DPBOSSE_JODI_URLS = [
    "https://dpbosse.net/jodi/SRIDEVI/2",
    "https://dpbosse.net/jodi/TIMEBAZAR/11",
    "https://dpbosse.net/jodi/MADHURDAY/41",
    "https://dpbosse.net/jodi/MILANDAY/17",
    "https://dpbosse.net/jodi/RAJDHANIDAY/125",
    "https://dpbosse.net/jodi/SUPREMEDAY/73",
    "https://dpbosse.net/jodi/KALYAN/20",
    "https://dpbosse.net/jodi/SRIDEVINIGHT/21",
    "https://dpbosse.net/jodi/MADHURNIGHT/63",
    "https://dpbosse.net/jodi/SUPREMENIGHT/74",
    "https://dpbosse.net/jodi/MILANNIGHT/65",
    "https://dpbosse.net/jodi/RAJDHANINIGHT/127",
    "https://dpbosse.net/jodi/KALYANNIGHT/39",
    "https://dpbosse.net/jodi/MAINBAZAR/66"
  ];
  if (!process.env.RESULT_SCRAPE_URLS && boolEnv("TITAN_USE_DPBOSSE_JODI_URLS", false)) {
    process.env.RESULT_SCRAPE_URLS = DPBOSSE_JODI_URLS.join(",");
  }

  process.on("unhandledRejection", (reason) => {
    event("unhandled_rejection", "error", (reason && reason.message) || String(reason || "Unhandled promise rejection"), {stack: reason && reason.stack ? String(reason.stack).slice(0, 1500) : ""});
  });

  process.on("uncaughtException", (err) => {
    event("uncaught_exception", "error", (err && err.message) || String(err || "Uncaught exception"), {stack: err && err.stack ? String(err.stack).slice(0, 1500) : ""});
  });

  event("preflight_loaded", "info", `Gateway preflight loaded ${VERSION}`, {
    firebaseConfigured: !!process.env.FIREBASE_URL,
    resultSource: process.env.RESULT_SOURCE_URL,
    appTz: process.env.APP_TZ,
    logFile: LOG_FILE
  });
})();
