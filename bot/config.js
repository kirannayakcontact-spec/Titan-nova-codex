"use strict";

// Titan Nova Gateway configuration helpers.
// Phase 1 module scaffold. Import-safe: no WhatsApp/Firebase connection starts here.

const DEFAULT_FIREBASE_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/titan_master_data.json";
const DEFAULT_APP_TZ = "Asia/Kolkata";
const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off"]);

function envStr(name, fallback = "") {
  const value = process.env[name];
  return String(value === undefined || value === null || value === "" ? fallback : value).trim();
}

function envBool(name, fallback = false) {
  const raw = envStr(name, fallback ? "1" : "0").toLowerCase();
  if (TRUE_VALUES.has(raw)) return true;
  if (FALSE_VALUES.has(raw)) return false;
  return !!fallback;
}

function envInt(name, fallback, min, max) {
  let value = Number.parseInt(envStr(name, String(fallback)), 10);
  if (!Number.isFinite(value)) value = Number(fallback);
  if (Number.isFinite(min)) value = Math.max(Number(min), value);
  if (Number.isFinite(max)) value = Math.min(Number(max), value);
  return value;
}

function normalizeFirebaseUrl(url) {
  let out = String(url || "").trim().replace(/\/+$/, "");
  if (out && !out.endsWith(".json")) out += ".json";
  return out || DEFAULT_FIREBASE_URL;
}

function redact(value, keep = 18) {
  const text = String(value || "");
  if (!text) return "";
  if (text.length <= keep) return text;
  const left = Math.max(6, Math.floor(keep / 2));
  const right = Math.max(4, keep - left);
  return `${text.slice(0, left)}…${text.slice(-right)}`;
}

function loadGatewayConfig() {
  const firebaseFromEnv = !!(envStr("FIREBASE_URL") || envStr("FIREBASE_DB_URL"));
  const firebaseUrl = normalizeFirebaseUrl(envStr("FIREBASE_URL") || envStr("FIREBASE_DB_URL") || DEFAULT_FIREBASE_URL);
  const host = envStr("HOST") || envStr("TITAN_GATEWAY_HOST") || "127.0.0.1";
  const port = envInt("PORT", 3000, 1, 65535);
  const appTz = envStr("APP_TZ", DEFAULT_APP_TZ) || DEFAULT_APP_TZ;
  const envName = envStr("TITAN_ENV") || envStr("NODE_ENV");
  const productionMode = ["prod", "production"].includes(envName.toLowerCase());
  return {
    firebaseUrl,
    firebaseFromEnv,
    firebaseUrlRedacted: redact(firebaseUrl, 24),
    host,
    port,
    appTz,
    businessDayCutoffHour: envInt("TITAN_BUSINESS_DAY_CUTOFF_HOUR", 6, 0, 23),
    gatewayTokenConfigured: !!(envStr("TITAN_GATEWAY_TOKEN") || envStr("TITAN_ADMIN_TOKEN")),
    gatewayAuthDisabled: envBool("TITAN_GATEWAY_AUTH_DISABLED", false),
    allowQueryToken: envBool("TITAN_ALLOW_QUERY_TOKEN", false),
    productionMode,
    resultScrapeEnabled: envStr("RESULT_SCRAPE_ENABLED", "1") !== "0",
    resultScrapeIntervalMs: Math.max(envInt("RESULT_SCRAPE_INTERVAL_MS", 5000, 1), 2000),
    schedulePollMs: Math.max(envInt("TITAN_SCHEDULE_POLL_MS", 2000, 1), 1000),
  };
}

function startupWarnings(config = loadGatewayConfig()) {
  const warnings = [];
  if (!config.firebaseFromEnv) warnings.push("FIREBASE_URL/FIREBASE_DB_URL missing; compatibility default is in use.");
  if (!config.gatewayTokenConfigured) warnings.push("TITAN_GATEWAY_TOKEN/TITAN_ADMIN_TOKEN missing; Gateway auth may be compatibility-open.");
  if (config.host === "127.0.0.1" || config.host === "localhost") warnings.push("HOST is localhost; OK for same-phone deploy, wrong for split-phone deploy.");
  if (config.productionMode && config.gatewayAuthDisabled) warnings.push("Production mode with Gateway auth disabled is unsafe.");
  return warnings;
}

module.exports = {
  DEFAULT_APP_TZ,
  DEFAULT_FIREBASE_URL,
  envBool,
  envInt,
  envStr,
  loadGatewayConfig,
  normalizeFirebaseUrl,
  redact,
  startupWarnings,
};
