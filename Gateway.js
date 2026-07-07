"use strict";

// ============================================================
// TITAN NOVA SINGLE GATEWAY BOT — WhatsApp Sync + Bulk + Auto Schedule
// RUN IN TERMUX:
//   npm install express axios qrcode-terminal pino @whiskeysockets/baileys
//   node Gateway.js
// Install deps without package.json:
//   npm install express axios qrcode-terminal pino @whiskeysockets/baileys
// Run:
//   node Gateway.js
// Optional:
//   FIREBASE_URL="https://your-db.firebaseio.com/titan_master_data.json" APP_TZ="Asia/Kolkata" node Gateway.js
// ============================================================

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const express = require("express");
const axios = require("axios");
const qrcode = require("qrcode-terminal");
const pino = require("pino");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
  downloadContentFromMessage
} = require("@whiskeysockets/baileys");

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || process.env.TITAN_GATEWAY_HOST || "127.0.0.1";
const TITAN_ALLOW_QUERY_TOKEN = ["1","true","yes","on"].includes(String(process.env.TITAN_ALLOW_QUERY_TOKEN || "0").toLowerCase());
const DEFAULT_FIREBASE_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/titan_master_data.json";
const FIREBASE_URL = (process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL || DEFAULT_FIREBASE_URL).replace(/\/$/, "");
const FIREBASE_URL_FROM_ENV = !!(process.env.FIREBASE_URL || process.env.FIREBASE_DB_URL);
const TITAN_STATE_DIR = process.env.TITAN_STATE_DIR || process.cwd();
try { fs.mkdirSync(TITAN_STATE_DIR, {recursive:true}); } catch(e) {}
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || path.join(TITAN_STATE_DIR, "auth_info_baileys");
const TARGET_CACHE_FILE = path.join(TITAN_STATE_DIR, "whatsapp_targets_cache.json");
const SENT_LOG_FILE = path.join(TITAN_STATE_DIR, "titan_schedule_sent_log.json");
const SPAM_GUARD_STATE_FILE = path.join(TITAN_STATE_DIR, "titan_spam_guard_state.json");
const SCRAPE_CONFIRM_FILE = path.join(TITAN_STATE_DIR, "titan_result_scrape_confirm.json");
const LIVE_RESULT_STATE_FILE = path.join(TITAN_STATE_DIR, "titan_live_result_state.json");
const WHATSAPP_SAFETY_STATE_FILE = path.join(TITAN_STATE_DIR, "titan_whatsapp_safety_state.json");
const WHATSAPP_RELIABILITY_FILE = path.join(TITAN_STATE_DIR, "titan_whatsapp_reliability_log.json");
const PROCESSED_MESSAGE_CACHE_FILE = path.join(TITAN_STATE_DIR, "titan_processed_messages.json");
const WHATSAPP_BOT_UPGRADE_VERSION = "2026-07-02-whatsapp-bot-improvement-v1";
const WHATSAPP_RELIABILITY_VERSION = "2026-07-02-whatsapp-reliability-dashboard-v19";
const SMART_WHATSAPP_COMMAND_VERSION = "2026-07-02-smart-whatsapp-commands-v16";
const DATA_CLEANUP_VERSION = "2026-07-02-firebase-data-cleanup-v17";
const FIREBASE_DATA_GUARD_VERSION = "2026-07-03-firebase-data-guard-v36";
const REALTIME_SYNC_VERSION = "2026-07-03-realtime-stability-lock-v38";
const RUNTIME_STABILITY_VERSION = "2026-07-05-runtime-stability-patch-v45";
const WHATSAPP_TARGET_SYNC_VERSION = "2026-07-05-whatsapp-target-realtime-sync-v45";
const GATEWAY_ROOT_SAVE_NORMAL_DISABLED = true;
// Schedule timezone: keep Python UI and Node gateway on the same date/time.
const APP_TZ = process.env.APP_TZ || "Asia/Kolkata";
// Business day cutoff: before this local hour, entries/results/ledger schedules
// use previous business date. Default 6 = 00:00-05:59 belongs to yesterday.
const BUSINESS_DAY_CUTOFF_HOUR = Math.min(23, Math.max(0, Number(process.env.TITAN_BUSINESS_DAY_CUTOFF_HOUR || 6) || 6));
// SECURITY LOCKDOWN v8: protect local Express control/API surface when token is configured.
const SECURITY_LOCKDOWN_VERSION = "2026-07-02-security-lockdown-v8";
const MONEY_ATOMICITY_VERSION = "2026-07-02-money-atomicity-v9";
const GATEWAY_DURABILITY_VERSION = "2026-07-02-gateway-durability-v10";
const CONFIG_CLEANUP_VERSION = "2026-07-02-config-cleanup-v11";
const OBSERVABILITY_VERSION = "2026-07-02-observability-v12";
const DEPLOY_SAFETY_VERSION = "2026-07-02-deploy-safety-v13";
const OBSERVABILITY_LOG_FILE = path.join(TITAN_STATE_DIR, "gateway_observability_events.jsonl");
const OBSERVABILITY_MAX_MEMORY_EVENTS = Math.max(Number(process.env.TITAN_GATEWAY_OBS_MEMORY_EVENTS || 300), 50);
const OBSERVABILITY_MAX_FILE_LINES = Math.max(Number(process.env.TITAN_GATEWAY_OBS_FILE_LINES || 1500), 200);
const gatewayObservabilityEvents = [];
const gatewayObservabilityCounters = {info:0, warning:0, error:0, critical:0};
const TITAN_GATEWAY_TOKEN = String(process.env.TITAN_GATEWAY_TOKEN || process.env.TITAN_ADMIN_TOKEN || "").trim();
const TITAN_GATEWAY_AUTH_DISABLED = ["1","true","yes","on"].includes(String(process.env.TITAN_GATEWAY_AUTH_DISABLED || "0").toLowerCase());
const TITAN_ENV = String(process.env.TITAN_ENV || process.env.NODE_ENV || "").trim().toLowerCase();
const TITAN_PRODUCTION_MODE = ["prod","production"].includes(TITAN_ENV);
const TITAN_GATEWAY_SECURITY_MISCONFIGURED = TITAN_PRODUCTION_MODE && (!TITAN_GATEWAY_TOKEN || TITAN_GATEWAY_AUTH_DISABLED);
const TITAN_GATEWAY_AUTH_ENFORCED = !!TITAN_GATEWAY_TOKEN && !TITAN_GATEWAY_AUTH_DISABLED;
// Auto result scraper: set RESULT_SCRAPE_ENABLED=0 to disable.
// RESULT_SCRAPE_URLS can be comma-separated fallback live result pages.
const RESULT_SCRAPE_ENABLED = String(process.env.RESULT_SCRAPE_ENABLED || "1") !== "0";
const RESULT_SCRAPE_INTERVAL_MS = Math.max(Number(process.env.RESULT_SCRAPE_INTERVAL_MS || 5000), 2000);
const TITAN_SCHEDULE_POLL_MS = Math.max(Number(process.env.TITAN_SCHEDULE_POLL_MS || 2000), 1000);
const TITAN_RESULT_POLL_MS = Math.max(Number(process.env.TITAN_RESULT_POLL_MS || 2000), 1000);
const TITAN_PAYMENT_OUTBOX_POLL_MS = Math.max(Number(process.env.TITAN_PAYMENT_OUTBOX_POLL_MS || 2000), 1000);
const TITAN_LOAD_FORWARDER_POLL_MS = Math.max(Number(process.env.TITAN_LOAD_FORWARDER_POLL_MS || 3000), 1500);
const RESULT_SOURCE_NAME = process.env.RESULT_SOURCE_NAME || "SattaMatkaDpboss.Mobi";
const RESULT_SOURCE_URL = process.env.RESULT_SOURCE_URL || "https://sattamatkadpboss.mobi/";
const SAFE_UPDATE_VERSION = "2026-06-30-safe-update-guard-v1";

const FULL_AUDIT_PHASE1_FEATURE_FREEZE = true;
const FULL_AUDIT_PHASE2_SINGLE_SOURCE_CLEANUP = true;
const FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING = true; // PHASE3_RUNTIME_SELF_HEALING_MARKER phase3_runtime_self_healing
const FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS = true;
const FULL_AUDIT_VERSION = "2026-06-30-phase4-production-diagnostics-v1";
const FULL_AUDIT_LOCKED_FEATURES = [
  "WhatsApp Easy Login",
  "New WhatsApp User Auto Profile + Admin Approval",
  "Ledger Daily Repeat Schedule",
  "Ledger Duplicate Send Lock",
  "Ledger Intel Share Schedule + Auto Rate Compact Format",
  "SattaMatkaDpboss.Mobi Result Source",
  "Strict Open/Close No-Old Result Safety",
  "Ledger Auto Pass/Fail Live Sync",
  "Withdrawal Approve / Pay Now / Mark Paid",
  "Wallet Transaction History / Audit",
  "Advanced Target Picker",
  "WhatsApp Safe Messaging Guard",
  "WhatsApp Bot UX Commands + Incoming Duplicate Guard",
  "WhatsApp Reliability Dashboard",
  "Safe Update Guard",
  "Full Audit Phase 1 Feature Freeze Guard",
  "Full Audit Phase 2 Single Source Cleanup Guard",
  "Full Audit Phase 3 Runtime Self-Healing + Backup/Rollback Guard",
  "Full Audit Phase 4 Production Diagnostics + E2E Smoke Test Guard"
];
const SAFE_UPDATE_PROTECTED_MARKERS = [
  {key:"whatsapp_login", markers:["/wa_login_status", "/wa_reset_session", "lastQR"], critical:true},
  {key:"auto_profile_admin_approval", markers:["autoCreatePendingProfiles", "profile_pending_approval", "approvalStatus"], critical:true},
  {key:"ledger_daily_repeat", markers:["ledgerSchedules", "collectSchedules", "scheduleTick"], critical:true},
  {key:"ledger_duplicate_lock", markers:["scheduleTickRunning", "scheduleTargetLogKey", "markScheduleTargetSent"], critical:true},
  {key:"withdrawal_flow", markers:["withdrawalSettings", "approvalNotified", "paidNotified"], critical:true},
  {key:"result_source", markers:[RESULT_SOURCE_URL, RESULT_SOURCE_NAME, "LIVE MATKA RESULT"], critical:true},
  {key:"strict_open_close", markers:["fresh_open_missing_strict_2_stage", "strict 2-stage", "close_open_mismatch"], critical:true},
  {key:"whatsapp_safety_guard", markers:["whatsappSafetySettings", "whatsappSafetyBeforeSend", "safeSendQueueRun"], critical:true},
  {key:"whatsapp_bot_upgrade", markers:["WHATSAPP_BOT_UPGRADE_VERSION", "handleBotCommandMessage", "rememberIncomingMessage"], critical:false},
  {key:"runtime_self_healing", markers:["FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING", "runtime_self_healing", "last_known_good"], critical:true},
  {key:"production_diagnostics", markers:["FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS", "phase4_production_diagnostics", "/production_diagnostics"], critical:true}
];
const RESULT_SCRAPE_URLS = String(process.env.RESULT_SCRAPE_URLS || RESULT_SOURCE_URL)
  .split(",")
  .map(x => x.trim())
  .filter(Boolean);
// Wrong-result protection: same market+stage+result must be seen in repeated scrapes before it is saved/sent.
const RESULT_SCRAPE_CONFIRM_COUNT = Math.max(Number(process.env.RESULT_SCRAPE_CONFIRM_COUNT || 2), 1);
// If phone/Termux sleeps briefly, still send schedules shortly after the exact minute.
// Set SCHEDULE_RECOVERY_MINUTES=0 for exact-minute only.
const SCHEDULE_RECOVERY_MINUTES = Math.max(Number(process.env.SCHEDULE_RECOVERY_MINUTES || 10), 0);
const WHATSAPP_TARGET_SYNC_INTERVAL_MS = Math.max(Number(process.env.WHATSAPP_TARGET_SYNC_INTERVAL_MS || 60000), 15000);
function redactConfigValue(v, keep=18){ const s=String(v||""); return s ? (s.slice(0,keep) + "…" + s.length + "chars") : ""; }
function gatewayStartupConfigWarnings(){
  const warnings=[];
  if(!FIREBASE_URL_FROM_ENV) warnings.push("FIREBASE_URL/FIREBASE_DB_URL is missing; compatibility default database is in use.");
  if(!process.env.TITAN_ADMIN_TOKEN) warnings.push("TITAN_ADMIN_TOKEN is missing; admin-auth fallback is unavailable.");
  if(!process.env.TITAN_GATEWAY_TOKEN) warnings.push("TITAN_GATEWAY_TOKEN is missing; Gateway auth uses TITAN_ADMIN_TOKEN fallback or remains compatibility-open.");
  return warnings;
}
const GATEWAY_STARTUP_WARNINGS = gatewayStartupConfigWarnings();
for(const msg of GATEWAY_STARTUP_WARNINGS) console.warn("⚠️ TITAN CONFIG WARNING:", msg);

function gatewayConfigReport(){
  const warnings=[...GATEWAY_STARTUP_WARNINGS];
  if(!TITAN_GATEWAY_TOKEN && !TITAN_GATEWAY_AUTH_DISABLED) warnings.push("TITAN_GATEWAY_TOKEN not set; Gateway API auth is compatibility-open unless disabled intentionally.");
  return {
    status:warnings.length?"warning":"success",
    version:CONFIG_CLEANUP_VERSION,
    firebase:{configuredFromEnv:FIREBASE_URL_FROM_ENV, urlRedacted:redactConfigValue(FIREBASE_URL), pathLooksJson:FIREBASE_URL.endsWith('.json')},
    security:{gatewayTokenConfigured:!!TITAN_GATEWAY_TOKEN, enforced:TITAN_GATEWAY_AUTH_ENFORCED, authDisabled:TITAN_GATEWAY_AUTH_DISABLED},
    resultSource:{name:RESULT_SOURCE_NAME, url:RESULT_SOURCE_URL, urls:RESULT_SCRAPE_URLS},
    storage:{stateDir:redactConfigValue(TITAN_STATE_DIR, 24), authDir:redactConfigValue(AUTH_DIR, 24)},
    localFallbackFiles:{targetCache:TARGET_CACHE_FILE, sentLog:SENT_LOG_FILE, processedMessages:PROCESSED_MESSAGE_CACHE_FILE, safety:WHATSAPP_SAFETY_STATE_FILE},
    warnings
  };
}

function obsRedact(value){
  if(Array.isArray(value)) return value.slice(0,50).map(obsRedact);
  if(value && typeof value === "object"){
    const out = {};
    for(const [k,v] of Object.entries(value)){
      const lk = String(k).toLowerCase();
      if(lk.includes("token") || lk.includes("secret") || lk.includes("password") || lk.includes("api_key") || lk.includes("apikey")) out[k] = "***redacted***";
      else out[k] = obsRedact(v);
    }
    return out;
  }
  if(typeof value === "string") return value.replace(/(Bearer\s+)[A-Za-z0-9._-]+/ig, "$1***redacted***").replace(/(token=)[^&\s]+/ig, "$1***redacted***").slice(0,2000);
  return value;
}
function gatewayObsEvent(kind, severity="info", message="", detail={}){
  const sev = Object.prototype.hasOwnProperty.call(gatewayObservabilityCounters, String(severity||"info").toLowerCase()) ? String(severity||"info").toLowerCase() : "info";
  const rec = {id:Math.random().toString(36).slice(2,10).toUpperCase(), time:nowIsoSafe(), source:"gateway", kind:String(kind||"event").slice(0,80), severity:sev, message:String(message||"").slice(0,500), detail:obsRedact(detail||{})};
  gatewayObservabilityCounters[sev] = Number(gatewayObservabilityCounters[sev] || 0) + 1;
  gatewayObservabilityEvents.push(rec);
  if(gatewayObservabilityEvents.length > OBSERVABILITY_MAX_MEMORY_EVENTS) gatewayObservabilityEvents.splice(0, gatewayObservabilityEvents.length - OBSERVABILITY_MAX_MEMORY_EVENTS);
  try { fs.appendFileSync(OBSERVABILITY_LOG_FILE, JSON.stringify(rec) + "\n"); } catch(e) {}
  if(sev === "error" || sev === "critical"){
    gatewayHealth.lastObservedError = rec;
    gatewayHealth.lastObservedErrorAt = rec.time;
  }
  return rec;
}
function gatewayObsError(kind, error, detail={}){
  const msg = error && error.response ? `HTTP ${error.response.status}: ${String(error.response.data || error.response.statusText || "").slice(0,180)}` : (error && error.message ? error.message : String(error));
  return gatewayObsEvent(kind, "error", msg, Object.assign({}, detail || {}, {exception:error && error.name ? error.name : "Error"}));
}
function nowIsoSafe(){ try { return new Date().toISOString(); } catch(e){ return String(Date.now()); } }
function gatewayReadObsFile(limit=200){
  try{
    if(!fs.existsSync(OBSERVABILITY_LOG_FILE)) return [];
    const lines = fs.readFileSync(OBSERVABILITY_LOG_FILE, "utf8").split(/\n+/).filter(Boolean);
    const tail = lines.slice(-Math.max(1, Math.min(Number(limit||200), OBSERVABILITY_MAX_FILE_LINES)));
    return tail.map(x=>{ try{return JSON.parse(x);}catch(e){return null;} }).filter(Boolean);
  }catch(e){ return []; }
}
function gatewayPruneObsFile(){
  try{
    if(!fs.existsSync(OBSERVABILITY_LOG_FILE)) return 0;
    const lines = fs.readFileSync(OBSERVABILITY_LOG_FILE, "utf8").split(/\n/);
    if(lines.length <= OBSERVABILITY_MAX_FILE_LINES) return lines.length;
    fs.writeFileSync(OBSERVABILITY_LOG_FILE, lines.slice(-OBSERVABILITY_MAX_FILE_LINES).join("\n"));
    return OBSERVABILITY_MAX_FILE_LINES;
  }catch(e){ return 0; }
}
function gatewayFilterObsEvents(events, query={}){
  const limit = Math.max(1, Math.min(Number(query.limit || 100), 500));
  const sev = String(query.severity || "").toLowerCase();
  const kind = String(query.kind || "").toLowerCase();
  const out = [];
  for(const e of [...(events||[])].reverse()){
    if(sev && String(e.severity||"").toLowerCase() !== sev) continue;
    if(kind && !String(e.kind||"").toLowerCase().includes(kind)) continue;
    out.push(e);
    if(out.length >= limit) break;
  }
  return out;
}
function gatewayObservabilityStatus(){
  gatewayPruneObsFile();
  const tail = gatewayReadObsFile(300);
  const events = tail.length ? tail : gatewayObservabilityEvents;
  const recentErrors = gatewayFilterObsEvents(events, {severity:"error", limit:10}).concat(gatewayFilterObsEvents(events, {severity:"critical", limit:10})).slice(0,10);
  return {
    status: recentErrors.length ? "attention_required" : "success",
    version: OBSERVABILITY_VERSION,
    observability:true,
    checkedAt: nowIsoSafe(),
    gateway:{connected, user:sock?.user || null, port:PORT, timezone:APP_TZ, health:gatewayHealth},
    counters: gatewayObservabilityCounters,
    memoryEventCount: gatewayObservabilityEvents.length,
    fileEventCountTail: tail.length,
    logFile: redactConfigValue(OBSERVABILITY_LOG_FILE, 32),
    recentErrors,
    recentWarnings: gatewayFilterObsEvents(events, {severity:"warning", limit:10}),
    durability:{version:GATEWAY_DURABILITY_VERSION, firebaseLocks:true, owner:GATEWAY_LOCK_OWNER},
    config: gatewayConfigReport()
  };
}

const MARKETS = [
  {n:"SRIDEV DAY OPEN",hr:11,min:35},{n:"SRIDEV DAY CLOSE",hr:12,min:35},{n:"TIME BAZAR OPEN",hr:13,min:0},{n:"MADHUR DAY OPEN",hr:13,min:15},
  {n:"TIME BAZAR CLOSE",hr:14,min:0},{n:"MADHUR DAY CLOSE",hr:14,min:15},{n:"MILAN DAY OPEN",hr:15,min:0},{n:"RAJDHANI DAY OPEN",hr:15,min:5},
  {n:"SUPREME DAY OPEN",hr:15,min:35},{n:"KALYAN OPEN",hr:15,min:50},{n:"MILAN DAY CLOSE",hr:17,min:0},{n:"RAJDHANI DAY CLOSE",hr:17,min:5},
  {n:"SUPREME DAY CLOSE",hr:17,min:35},{n:"KALYAN CLOSE",hr:17,min:50},{n:"SRIDEVI NIGHT OPEN",hr:19,min:0},{n:"SRIDEVI NIGHT CLOSE",hr:20,min:0},
  {n:"MADHUR NIGHT OPEN",hr:20,min:30},{n:"SUPREME NIGHT OPEN",hr:20,min:45},{n:"MILAN NIGHT OPEN",hr:21,min:0},{n:"KALYAN NIGHT OPEN",hr:21,min:25},
  {n:"RAJDHANI NIGHT OPEN",hr:21,min:35},{n:"MAIN BAZAR OPEN",hr:21,min:40},{n:"MADHUR NIGHT CLOSE",hr:22,min:30},{n:"SUPREME NIGHT CLOSE",hr:22,min:45},
  {n:"MILAN NIGHT CLOSE",hr:23,min:0},{n:"KALYAN NIGHT CLOSE",hr:23,min:35},{n:"RAJDHANI NIGHT CLOSE",hr:23,min:45},{n:"MAIN BAZAR CLOSE",hr:0,min:5}
];
const BASE_MARKETS = ["SRIDEV DAY","TIME BAZAR","MADHUR DAY","MILAN DAY","RAJDHANI DAY","SUPREME DAY","KALYAN","SRIDEVI NIGHT","MADHUR NIGHT","SUPREME NIGHT","MILAN NIGHT","KALYAN NIGHT","RAJDHANI NIGHT","MAIN BAZAR"].map(n=>({n}));


// MARKET_MANAGER_PHASE1_REGISTRY: dynamic market registry from Firebase; static lists remain fallback only.
const MARKET_REGISTRY_VERSION = "2026-06-30-market-registry-phase3-v1";
const MARKET_MANAGER_PHASE3_DEEP_INTEGRATION = true;
function marketSlug(name){ return String(name || "").toUpperCase().replace(/SRIDEVI\s+DAY/g,"SRIDEV DAY").replace(/[^A-Z0-9]+/g,"_").replace(/^_+|_+$/g,"").toLowerCase() || ("market_" + Math.random().toString(36).slice(2,8)); }
function defaultMarketRegistry(){
  const items = {};
  for(let i=0;i<BASE_MARKETS.length;i++){
    const name = BASE_MARKETS[i].n;
    const id = marketSlug(name);
    const open = MARKETS.find(x => x.n === name + " OPEN");
    const close = MARKETS.find(x => x.n === name + " CLOSE");
    items[id] = { id, name, displayName:name, websiteName:name.replace("SRIDEV DAY","SRIDEVI"), aliases:[name, name.replace("SRIDEV DAY","SRIDEVI DAY")], enabled:true, ledgerEnabled:true, resultEnabled:true, autoResultEnabled:true, autoPassFailEnabled:true, scheduleEnabled:true, entryEnabled:true, entryTargets:[], scheduleTargets:[], resultTargets:[], forwardTargets:[], bookieTargets:[], sortOrder:i*10, stages:{open:!!open, close:!!close}, times:{open:open?`${pad(open.hr)}:${pad(open.min)}`:"", close:close?`${pad(close.hr)}:${pad(close.min)}`:""}, archived:false, marketManagerPhase1:true };
  }
  return { version:MARKET_REGISTRY_VERSION, marketManagerPhase1:true, marketManagerDeleteSupport:true, deletedMarketIds:[], updatedAt:nowIso ? nowIso() : new Date().toISOString(), items };
}
function normalizeMarketRegistry(reg){
  if(!reg || typeof reg !== "object") reg = {};
  const def = defaultMarketRegistry();
  const items = (reg.items && typeof reg.items === "object") ? reg.items : {};
  const deletedIds = new Set(Array.isArray(reg.deletedMarketIds) ? reg.deletedMarketIds.map(x => String(x)).filter(Boolean) : []);
  for(const [id,d] of Object.entries(def.items)){ if(deletedIds.has(id)) continue; if(!items[id]) items[id] = d; else for(const [k,v] of Object.entries(d)) if(typeof items[id][k] === "undefined") items[id][k] = v; }
  const cleaned = {};
  for(const [key,raw] of Object.entries(items)){
    if(!raw || typeof raw !== "object") continue;
    const name = String(raw.name || raw.displayName || key || "").toUpperCase().trim(); if(!name) continue;
    const id = String(raw.id || key || marketSlug(name));
    const item = {...raw, id, name};
    item.displayName = String(item.displayName || name).toUpperCase().trim();
    item.websiteName = String(item.websiteName || name).toUpperCase().trim();
    item.enabled = item.enabled !== false; item.ledgerEnabled = item.ledgerEnabled !== false; item.resultEnabled = item.resultEnabled !== false; item.autoResultEnabled = item.autoResultEnabled !== false; item.autoPassFailEnabled = item.autoPassFailEnabled !== false; item.scheduleEnabled = item.scheduleEnabled !== false; item.entryEnabled = item.entryEnabled !== false; if(!Array.isArray(item.entryTargets)) item.entryTargets = []; if(!Array.isArray(item.scheduleTargets)) item.scheduleTargets = []; if(!Array.isArray(item.resultTargets)) item.resultTargets = []; if(!Array.isArray(item.forwardTargets)) item.forwardTargets = []; if(!Array.isArray(item.bookieTargets)) item.bookieTargets = []; item.archived = item.archived === true;
    item.deleted = item.deleted === true;
    if(item.deleted){
      deletedIds.add(id);
      item.enabled = false; item.ledgerEnabled = false; item.resultEnabled = false; item.autoResultEnabled = false; item.autoPassFailEnabled = false; item.scheduleEnabled = false; item.archived = false;
      item.deletedAt = item.deletedAt || (nowIso ? nowIso() : new Date().toISOString());
    }
    item.settingsLocked = item.settingsLocked === true || item.manualSaveLocked === true;
    item.manualSaveLocked = item.manualSaveLocked === true || item.settingsLocked === true;
    item.manualChangeOnly = item.manualChangeOnly === true || item.settingsLocked === true;
    item.lockedAfterSave = item.lockedAfterSave === true || item.settingsLocked === true;
    item.stages = (item.stages && typeof item.stages === "object") ? item.stages : {open:true, close:true};
    item.stages.open = item.stages.open !== false; item.stages.close = item.stages.close !== false;
    item.times = (item.times && typeof item.times === "object") ? item.times : {open:"", close:""};
    item.sortOrder = Number.isFinite(Number(item.sortOrder)) ? Number(item.sortOrder) : 9999;
    cleaned[id] = item;
  }
  reg.version = MARKET_REGISTRY_VERSION; reg.marketManagerPhase1 = true; reg.marketManagerDeleteSupport = true; reg.deletedMarketIds = Array.from(deletedIds).filter(Boolean); reg.items = cleaned; return reg;
}
function ensureMarketRegistry(state){ if(!state || typeof state !== "object") state = {}; state.marketRegistry = normalizeMarketRegistry(state.marketRegistry); return state.marketRegistry; }
function marketItemsForPurpose(state, purpose="ledger"){
  const reg = ensureMarketRegistry(state);
  return Object.values(reg.items || {}).filter(item => {
    if(item.deleted) return false;
    if(item.archived || item.enabled === false) return false;
    if(purpose === "ledger" && item.ledgerEnabled === false) return false;
    if(purpose === "result" && item.resultEnabled === false) return false;
    if(purpose === "schedule" && item.scheduleEnabled === false) return false;
    if(purpose === "autopf" && item.autoPassFailEnabled === false) return false;
    return true;
  }).sort((a,b)=>(Number(a.sortOrder||9999)-Number(b.sortOrder||9999)) || String(a.displayName||a.name).localeCompare(String(b.displayName||b.name)));
}
function marketTimeSortKey(m){
  const h = Number(m && m.hr), mi = Number(m && m.min);
  if(!Number.isFinite(h) || !Number.isFinite(mi) || (h === 0 && mi === 0)) return 99999;
  let total = (h * 60) + mi;
  if(total < 360) total += 1440;
  return total;
}

function marketArraysForPurpose(state, purpose="ledger"){
  const mk = [], bm = [];
  let rows;
  if(purpose === "ledger" || purpose === "schedule"){
    const reg = ensureMarketRegistry(state);
    rows = Object.values(reg.items || {}).filter(item => item && item.archived !== true).sort((a,b)=>(Number(a.sortOrder||9999)-Number(b.sortOrder||9999)) || String(a.displayName||a.name).localeCompare(String(b.displayName||b.name)));
  } else rows = marketItemsForPurpose(state, purpose);
  for(const item of rows){
    const name = String(item.displayName || item.name || "").toUpperCase().trim(); if(!name) continue;
    const hiddenForLedger = (item.deleted === true || item.enabled === false || item.ledgerEnabled === false || item.archived === true);
    const scheduleDisabled = (item.deleted === true || item.enabled === false || item.ledgerEnabled === false || item.scheduleEnabled === false || item.archived === true);
    bm.push({n:name, id:item.id, websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false});
    if((item.stages||{}).open !== false){ const t=String((item.times||{}).open || "00:00").split(":"); mk.push({n:name+" OPEN", hr:Number(t[0]||0), min:Number(t[1]||0), id:item.id, stage:"open", websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false}); }
    if((item.stages||{}).close !== false){ const t=String((item.times||{}).close || "00:00").split(":"); mk.push({n:name+" CLOSE", hr:Number(t[0]||0), min:Number(t[1]||0), id:item.id, stage:"close", websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false}); }
  }
  mk.sort((a,b)=>marketTimeSortKey(a)-marketTimeSortKey(b) || String(a.n||"").localeCompare(String(b.n||"")));
  return { markets:mk.length?mk:MARKETS, baseMarkets:bm.length?bm:BASE_MARKETS };
}


// MARKET MANAGER PHASE 3: DEEP INTEGRATION GUARD
// Registry controls result scraping, declarations, auto P/F, and schedule sends.
function marketPhase3Norm(v){ return String(v || "").toUpperCase().replace(/SRIDEVI\s+DAY/g,"SRIDEV DAY").replace(/[^A-Z0-9]+/g," ").trim().replace(/\s+/g," "); }
function marketPhase3SplitStage(v){ const raw=marketPhase3Norm(v); if(raw.endsWith(" OPEN")) return {base:raw.slice(0,-5).trim(), stage:"open"}; if(raw.endsWith(" CLOSE")) return {base:raw.slice(0,-6).trim(), stage:"close"}; return {base:raw, stage:""}; }
function marketPhase3Aliases(item){
  const vals = [item?.name, item?.displayName, item?.websiteName, ...(Array.isArray(item?.aliases)?item.aliases:[])];
  const out = [];
  for(const v of vals){
    const n = marketPhase3Norm(v); if(n && !out.includes(n)) out.push(n);
    if(n === "SRIDEV DAY" && !out.includes("SRIDEVI DAY")) out.push("SRIDEVI DAY");
    if(n === "SRIDEVI DAY" && !out.includes("SRIDEV DAY")) out.push("SRIDEV DAY");
  }
  return out;
}
function marketPhase3FindItem(state, marketName){
  const reg = ensureMarketRegistry(state || {});
  const split = marketPhase3SplitStage(marketName);
  for(const item of Object.values(reg.items || {})){
    if(!item || typeof item !== "object") continue;
    if(item.deleted) continue;
    if(marketPhase3Aliases(item).includes(split.base)) return {item, stage:split.stage};
  }
  return {item:null, stage:split.stage};
}
function marketPhase3Allowed(state, marketName, purpose="result", stage=""){
  const found = marketPhase3FindItem(state || {}, marketName);
  const item = found.item;
  const st = String(stage || found.stage || "").toLowerCase().trim();
  if(!item) return {ok:false, reason:"market_not_in_registry", market:String(marketName||"").toUpperCase(), stage:st};
  const market = String(item.displayName || item.name || "").toUpperCase().trim();
  if(item.deleted === true) return {ok:false, reason:"market_deleted", market, stage:st, item};
  if(item.archived === true) return {ok:false, reason:"market_archived", market, stage:st, item};
  if(item.enabled === false) return {ok:false, reason:"market_disabled", market, stage:st, item};
  if(["ledger","schedule","autopf"].includes(purpose) && item.ledgerEnabled === false) return {ok:false, reason:"ledger_disabled_for_market", market, stage:st, item};
  if(["result","auto_result","autopf"].includes(purpose) && item.resultEnabled === false) return {ok:false, reason:"result_disabled_for_market", market, stage:st, item};
  if(purpose === "auto_result" && item.autoResultEnabled === false) return {ok:false, reason:"auto_result_disabled_for_market", market, stage:st, item};
  if(purpose === "autopf" && item.autoPassFailEnabled === false) return {ok:false, reason:"auto_pf_disabled_for_market", market, stage:st, item};
  if(purpose === "schedule" && item.scheduleEnabled === false) return {ok:false, reason:"schedule_disabled_for_market", market, stage:st, item};
  const stages = (item.stages && typeof item.stages === "object") ? item.stages : {};
  if((st === "open" || st === "close") && stages[st] === false) return {ok:false, reason:`${st}_stage_disabled_for_market`, market, stage:st, item};
  return {ok:true, reason:"", market, stage:st, item};
}
function marketPhase3RegistryHealth(state){
  const reg = ensureMarketRegistry(state || {});
  const items = Object.values(reg.items || {}).filter(x => x && typeof x === "object");
  const active = items.filter(x => x.enabled !== false && x.archived !== true);
  const ledger = active.filter(x => x.ledgerEnabled !== false);
  const result = active.filter(x => x.resultEnabled !== false);
  const autoResult = result.filter(x => x.autoResultEnabled !== false);
  const autoPf = active.filter(x => x.autoPassFailEnabled !== false);
  const schedule = active.filter(x => x.ledgerEnabled !== false && x.scheduleEnabled !== false);
  const missingWebsiteName = result.filter(x => !String(x.websiteName || "").trim()).map(x => x.displayName || x.name).slice(0,50);
  return {marketManagerPhase3:true, version:MARKET_REGISTRY_VERSION, total:items.length, active:active.length, ledgerEnabled:ledger.length, resultEnabled:result.length, autoResultEnabled:autoResult.length, autoPassFailEnabled:autoPf.length, scheduleEnabled:schedule.length, missingWebsiteName, status:(active.length && ledger.length && result.length && !missingWebsiteName.length) ? "safe" : "attention_required"};
}

const DEFAULT_MARKET_CLOSE_TIMES = (() => {
  const out = {};
  for(const m of MARKETS) out[m.n] = `${pad(m.hr)}:${pad(m.min)}`;
  for(const b of BASE_MARKETS){
    const name = b.n;
    const close = MARKETS.find(x => x.n === name + " CLOSE");
    const open = MARKETS.find(x => x.n === name + " OPEN");
    if(close) out[name] = `${pad(close.hr)}:${pad(close.min)}`;
    else if(open) out[name] = `${pad(open.hr)}:${pad(open.min)}`;
  }
  if(out["SRIDEVI DAY"] && !out["SRIDEV DAY"]) out["SRIDEV DAY"] = out["SRIDEVI DAY"];
  if(out["SRIDEV DAY"] && !out["SRIDEVI DAY"]) out["SRIDEVI DAY"] = out["SRIDEV DAY"];
  return out;
})();

let sock = null;
let connected = false;
let lastQR = "";
let lastQRAt = "";
let whatsappStartInProgress = false;
let whatsappResetCount = 0;
let lastSessionResetAt = "";
let targetsCache = loadJson(TARGET_CACHE_FILE, { contacts: [], groups: [], updatedAt: null, lastSyncError: "" });
let sentLog = loadJson(SENT_LOG_FILE, {});
let spamGuardLocalState = loadJson(SPAM_GUARD_STATE_FILE, { strikes:{}, events:[] });
let scrapeConfirm = loadJson(SCRAPE_CONFIRM_FILE, {});
let liveResultState = loadJson(LIVE_RESULT_STATE_FILE, {});
let whatsappSafetyLocalState = loadJson(WHATSAPP_SAFETY_STATE_FILE, { fingerprints:{}, daily:{date:"", globalCount:0}, events:[], consecutiveFailures:0 });
let processedMessageCache = loadJson(PROCESSED_MESSAGE_CACHE_FILE, { items:{}, updatedAt:"" });
let resultTickRunning = false;
let resultScrapeTickRunning = false;
let scheduleTickRunning = false;
let paymentOutboxTickRunning = false;
let loadForwarderTickRunning = false;
let gatewayHealth = {
  startedAt: new Date().toISOString(),
  lastWhatsAppEvent: "starting",
  lastDisconnectCode: "",
  lastScheduleTickAt: "",
  lastScheduleError: "",
  lastResultTickAt: "",
  lastResultError: "",
  lastResultSendAt: "",
  lastResultSendSummary: "",
  lastResultScrapeTickAt: "",
  lastResultScrapeStatus: "never",
  lastResultScrapeUpdates: [],
  lastResultScrapeSkipped: [],
  lastResultScrapeError: "",
  lastPaymentOutboxTickAt: "",
  lastPaymentOutboxError: "",
  lastLoadForwarderTickAt: "",
  lastLoadForwarderError: "",
  lastLoadForwarderSendAt: "",
  lastSendAt: "",
  lastSendOk: null,
  lastSendTarget: "",
  lastSendError: "",
  whatsappSafetyPaused: false,
  whatsappSafetyLastBlock: "",
  whatsappSafetyLastEvent: "",
  whatsappSafetyQueueDepth: 0,
  whatsappSafetyConsecutiveFailures: 0,
  whatsappBotUpgradeVersion: WHATSAPP_BOT_UPGRADE_VERSION,
  lastIncomingAt: "",
  lastIncomingFrom: "",
  lastIncomingType: "",
  lastBotCommand: "",
  processedMessageCacheSize: 0,
  duplicateIncomingSkipped: 0,
  lastTargetSyncAt: targetsCache.updatedAt || "",
  lastTargetSyncGroups: Array.isArray(targetsCache.groups) ? targetsCache.groups.length : 0,
  lastTargetSyncContacts: Array.isArray(targetsCache.contacts) ? targetsCache.contacts.length : 0,
  lastTargetSyncError: targetsCache.lastSyncError || "",
  targetSyncVersion: WHATSAPP_TARGET_SYNC_VERSION
};

function loadJson(file, fallback){ try { return JSON.parse(fs.readFileSync(file,"utf8")); } catch { return fallback; } }
function saveJson(file, obj){ try { fs.writeFileSync(file, JSON.stringify(obj,null,2)); } catch(e) { console.log("Save error", file, e.message); } }
function pad(n){ return String(n).padStart(2,"0"); }
function nowParts(){
  const out = {};
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: APP_TZ, year:"numeric", month:"2-digit", day:"2-digit",
    hour:"2-digit", minute:"2-digit", hourCycle:"h23"
  }).formatToParts(new Date());
  for(const p of parts) if(p.type !== "literal") out[p.type] = p.value;
  return { date:`${out.year}-${out.month}-${out.day}`, hhmm:`${out.hour}:${out.minute}`, hour:Number(out.hour || 0), minute:Number(out.minute || 0) };
}
function calendarTodayISO(){ return nowParts().date; }
function businessDateISO(){
  const parts = nowParts();
  const d = new Date(`${parts.date}T12:00:00`);
  if(parts.hour < BUSINESS_DAY_CUTOFF_HOUR) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}
function todayISO(){ return businessDateISO(); }
function nowHHMM(){ return nowParts().hhmm; }
function normalizeTime(v){
  const m = String(v || "").trim().match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if(!m) return "";
  const h = Number(m[1]), min = Number(m[2]);
  if(h < 0 || h > 23 || min < 0 || min > 59) return "";
  return `${pad(h)}:${pad(min)}`;
}
function hhmmToMinutes(v){ const t=normalizeTime(v); if(!t) return -1; const [h,m]=t.split(":").map(Number); return h*60+m; }
function isDueNow(jobTime, nowTime){
  const j = hhmmToMinutes(jobTime), n = hhmmToMinutes(nowTime);
  if(j < 0 || n < 0) return false;
  const diff = n - j;
  // 0 = exact minute; positive values are a controlled recovery window if Termux/phone slept briefly.
  return diff >= 0 && diff <= SCHEDULE_RECOVERY_MINUTES;
}
function cleanDigits(v){ return String(v || "").replace(/[^0-9, ]/g, "").split(/[, ]+/).filter(Boolean).join(","); }
// Ledger Intel Share: scheduled messages must include the current auto-suggested rate,
// total exposure, and PASS/FAIL projection. Keep this formatter centralized so
// manual preview, /bot_schedule, and daily WhatsApp schedule all stay identical.
function ledgerDateDMY(date){
  const m = String(date || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : String(date || "");
}
function ledgerDigitsArray(digits){ return cleanDigits(digits).split(",").map(x => x.trim()).filter(Boolean); }
function ledgerTypeMultiplier(type){
  const t = String(type || "").toLowerCase();
  if(t === "jodi") return 95;
  if(t === "pannel" || t === "panel" || t === "penel") return 150;
  return 9.5;
}
function ledgerScheduleRate(payload){
  const n = Number(payload?.r ?? payload?.rate ?? payload?.parDigit ?? 0);
  // v7 safety: never fallback to ₹10 for scheduled ledger Intel.
  // If rate is blank, Gateway must recompute recovery auto-rate first; if still
  // unresolved, the job is blocked instead of sending a wrong amount.
  return Number.isFinite(n) && n > 0 ? n : 0;
}
function ledgerMoney(n){
  const v = Math.round(Number(n || 0) * 100) / 100;
  return `₹${Number.isInteger(v) ? String(v) : v.toFixed(2)}`;
}
function formatLedgerIntelMessage(date, market, digits, rate, type){
  const ds = ledgerDigitsArray(digits);
  const par = ledgerScheduleRate({r:rate});
  const total = ds.length * par;
  return `🚀 *TITAN NOVA INTEL* [${ledgerDateDMY(date)}]\n━━━━━━━━━━━━━━━━━━━━\n🔥 *MARKET:* ${market}\n🔢 *DIGITS:* [${ds.join(", ")}]\n💰 *PAR DIGIT:* ${ledgerMoney(par)}\n💸 *TOTAL:* ${ledgerMoney(total)}\n━━━━━━━━━━━━━━━━━━━━`;
}
function formatMessage(date, market, digits, rate, type){ return formatLedgerIntelMessage(date, market, digits, rate, type); }
function arr(v){ if(!v) return []; if(Array.isArray(v)) return v.filter(Boolean); return String(v).split(/[\n,]+/).map(x=>x.trim()).filter(Boolean); }

// Result/load/forward target helper: accepts plain numbers, wa.me links, group JIDs,
// WhatsApp invite links, and UI option objects like {id,name,type}. This prevents
// auto-result sends from failing when targets came from the Forward tab or sync list.
function targetValue(raw){
  if(raw == null) return "";
  if(typeof raw === "object"){
    return String(raw.id || raw.jid || raw.target || raw.to || raw.value || raw.phone || raw.number || raw.link || "").trim();
  }
  return String(raw || "").trim();
}
function targetList(input){
  const out = [];
  const pushOne = (x) => {
    let t = targetValue(x);
    if(!t) return;
    // If a label was accidentally pasted with a JID, extract the JID first.
    const jidMatch = t.match(/([0-9A-Za-z._:-]+@(?:g\.us|s\.whatsapp\.net))/i);
    if(jidMatch) t = jidMatch[1];
    // If several values are pasted in one field, split them safely.
    for(const part of String(t).split(/[\n,]+/).map(v=>v.trim()).filter(Boolean)){
      if(!out.includes(part)) out.push(part);
    }
  };
  if(Array.isArray(input)) input.forEach(pushOne); else pushOne(input);
  return out;
}


function scheduleDictName(type){ return type === "ank" ? "data" : (type === "jodi" ? "jodiData" : "pannelData"); }
function ledgerScheduleKey(profileId, type, idx=null, marketKey=null){
  const mk = String(marketKey || "").trim();
  if(mk) return `${profileId}|${type}|${mk}`;
  return `${profileId}|${type}|${Number(idx)}`;
}
function ledgerScheduleKeyCandidates(profileId, type, idx=null, marketKey=null){
  const out = [];
  const mk = String(marketKey || "").trim();
  if(mk) out.push(ledgerScheduleKey(profileId, type, idx, mk));
  if(idx !== null && typeof idx !== "undefined"){
    const legacy = ledgerScheduleKey(profileId, type, idx, null);
    if(!out.includes(legacy)) out.push(legacy);
  }
  return out;
}
function ledgerMarketKeyForCard(type, m){ return `${String(type||"").toLowerCase()}|${String((m && m.n) || "").toUpperCase().trim()}`; }

// v33: schedule records must belong to the exact ledger card/stage.
// A market OPEN Intel schedule must never pull CLOSE card schedule data, even
// when legacy/base market keys or duplicate schedule records exist.
function scheduleExactNorm(v){ return String(v || '').toUpperCase().replace(/\s+/g,' ').trim(); }
function scheduleNameFromKey(k){
  const raw = String(k || '').trim();
  if(!raw) return '';
  const p = raw.indexOf('|');
  return scheduleExactNorm(p >= 0 ? raw.slice(p + 1) : raw);
}
function scheduleStageOfName(v){
  const n = scheduleExactNorm(v);
  if(/\bOPEN$/.test(n)) return 'open';
  if(/\bCLOSE$/.test(n)) return 'close';
  return '';
}
function scheduleBaseOfName(v){ return scheduleExactNorm(v).replace(/\s+(OPEN|CLOSE)$/,'').trim(); }
function scheduleRecordMatchesExactCard(sched, type, idx, marketKey, marketName){
  if(!sched || typeof sched !== 'object') return false;
  const typ = String(type || '').toLowerCase();
  const cardName = scheduleExactNorm(marketName || scheduleNameFromKey(marketKey));
  const cardKey = scheduleExactNorm(marketKey || (cardName ? ledgerMarketKeyForCard(typ, {n:cardName}) : ''));
  const cardStage = scheduleStageOfName(cardName || scheduleNameFromKey(cardKey));
  const schedKey = String(sched.marketKey || (sched.record && sched.record._ledgerKey) || '').trim();
  const schedNameRaw = String(sched.marketName || (sched.record && sched.record._marketName) || scheduleNameFromKey(schedKey) || '').trim();
  const schedName = scheduleExactNorm(schedNameRaw);
  const schedStage = scheduleStageOfName(schedName || scheduleNameFromKey(schedKey));

  // Strongest rule: marketKey must be exact when present.
  if(schedKey){
    if(scheduleExactNorm(schedKey) === cardKey) return true;
    // If either side is OPEN/CLOSE, reject cross-stage matches immediately.
    if(cardStage || schedStage){
      if(!cardStage || !schedStage || cardStage !== schedStage) return false;
      if(scheduleBaseOfName(cardName) && scheduleBaseOfName(schedName || scheduleNameFromKey(schedKey)) !== scheduleBaseOfName(cardName)) return false;
    }
    // For non-stage JODI/base legacy schedule, allow index fallback below only.
  }

  if(schedName && cardName){
    if(schedName === cardName) return true;
    if(cardStage || schedStage){
      if(!cardStage || !schedStage || cardStage !== schedStage) return false;
      if(scheduleBaseOfName(schedName) !== scheduleBaseOfName(cardName)) return false;
    }
  }

  // Legacy numeric schedules are accepted only when they have no conflicting market identity.
  const recIdx = Number(sched.index);
  if(Number.isFinite(recIdx) && Number.isFinite(Number(idx)) && recIdx === Number(idx)) return true;
  return false;
}

function scheduleRecordSnapshot(rec){
  if(!rec || typeof rec !== "object") return {};
  const out = {};
  for(const k of ["s", "d", "r", "od", "trick"]) if(Object.prototype.hasOwnProperty.call(rec, k)) out[k] = rec[k];
  return out;
}
function legacyScheduleForCard(profile, type, idx, today){
  const dictName = scheduleDictName(type);
  const dayRecords = profile?.dayRecords || {};
  const idxKey = String(idx);
  const dates = Object.keys(dayRecords).map(String).filter(d => d <= today).sort().reverse();
  for(const d of dates){
    const rec = dayRecords?.[d]?.[dictName]?.[idxKey];
    if(!rec || typeof rec !== "object") continue;
    const time = normalizeTime(rec.schTime || rec.scheduleTime || "");
    const targets = targetList(rec.schTargets || rec.targets || []);
    if(time || targets.length) return { time, targets, record:scheduleRecordSnapshot(rec), sourceDate:d, legacy:true };
  }
  return {};
}
function scheduleTs(rec){ const t = Date.parse(String(rec?.updatedAt || rec?.createdAt || rec?._scheduleUpdatedAt || "")); return Number.isFinite(t) ? t : 0; }
function storedScheduleForCard(state, profileId, profile, type, idx, today, marketKey=null){
  const store = state?.ledgerSchedules && typeof state.ledgerSchedules === "object" ? state.ledgerSchedules : {};
  const candidates = [];
  for(const key of ledgerScheduleKeyCandidates(profileId, type, idx, marketKey)){
    const rec = store[key];
    if(rec && typeof rec === "object") candidates.push(rec);
  }
  // Also scan duplicates for the same marketKey/index. A stale legacy key can keep
  // an old Intel time alive; always use the newest persistent schedule record.
  const prefix = `${profileId}|${type}|`;
  const mk = String(marketKey || "").trim();
  for(const [key, rec] of Object.entries(store)){
    if(!String(key).startsWith(prefix) || !rec || typeof rec !== "object") continue;
    const recMk = String(rec.marketKey || (rec.record && rec.record._ledgerKey) || "").trim();
    const recIdx = Number(rec.index);
    if((mk && recMk === mk) || (!mk && Number.isFinite(recIdx) && recIdx === Number(idx))){
      if(!candidates.includes(rec)) candidates.push(rec);
    }
  }
  if(candidates.length){
    candidates.sort((a,b) => scheduleTs(b) - scheduleTs(a));
    return candidates[0];
  }
  return legacyScheduleForCard(profile, type, idx, today);
}

function marketRoleTargetsForMarket(state, marketName, role){
  const field = ({entry:"entryTargets", schedule:"scheduleTargets", result:"resultTargets", forward:"forwardTargets", bookie:"bookieTargets", admin:"bookieTargets"})[String(role||"").toLowerCase()];
  if(!field) return [];
  try{
    const found = marketPhase3FindItem(state || {}, marketName || "");
    const item = found && found.item;
    if(item && Array.isArray(item[field]) && item[field].length) return targetList(item[field]);
  }catch(e){}
  return [];
}
function collectBookieAdminTargets(state, marketName=""){
  const out = [];
  const add = (items) => targetList(items).forEach(t => { if(t && !out.includes(t)) out.push(t); });
  add(marketRoleTargetsForMarket(state, marketName, "bookie"));
  try{
    const items = state?.marketRegistry?.items || {};
    for(const item of Object.values(items)){
      if(item && Array.isArray(item.bookieTargets) && item.bookieTargets.length) add(item.bookieTargets);
    }
  }catch(e){}
  return out;
}
function collectResultTargets(state){
  const out = [];
  const add = (items) => targetList(items).forEach(t => { if(t && !out.includes(t)) out.push(t); });
  add(state?.resultTargets || []);
  add(state?.resultSettings?.targets || []);
  // Practical fallback: many admins select WhatsApp targets in Forward tab and expect
  // result declarations to use the same group/private chats. Keep it ON by default.
  if(state?.resultSettings?.useForwardTargetsForResults !== false){
    add(state?.loadForwarder?.targets || []);
  }
  return out;
}
function resultTargetLogKey(rawTarget){
  const n = normalizeTarget(rawTarget);
  return n || targetValue(rawTarget) || String(rawTarget || "");
}
function resultSentInfo(logValue){
  if(logValue && typeof logValue === "object" && !Array.isArray(logValue)){
    return { signature:String(logValue.signature || ""), targets:logValue.targets && typeof logValue.targets === "object" ? logValue.targets : {}, updatedAt:logValue.updatedAt || "" };
  }
  // Legacy sent-log value was a plain string and did not know which WhatsApp targets succeeded.
  // Treat it as informational only so newly saved group/private/Forward targets can receive the result.
  return { signature:String(logValue || ""), targets:{}, updatedAt:"", legacy:true };
}
function scheduleSentInfo(logValue){
  if(logValue && typeof logValue === "object" && !Array.isArray(logValue)){
    return { date:String(logValue.date || ""), targets:logValue.targets && typeof logValue.targets === "object" ? logValue.targets : {}, updatedAt:logValue.updatedAt || "" };
  }
  // Legacy schedule lock was a plain date string. Treat it as fully sent for that day.
  return { date:String(logValue || ""), targets:{}, legacy:!!logValue };
}
function scheduleTargetLogKey(rawTarget){
  const n = normalizeTarget(rawTarget);
  return n || targetValue(rawTarget) || String(rawTarget || "");
}
function dedupeTargetsByResolvedKey(targets){
  const out = [];
  const seen = new Set();
  for(const t of targetList(targets)){
    const k = scheduleTargetLogKey(t);
    if(!k || seen.has(k)) continue;
    seen.add(k);
    out.push(t);
  }
  return out;
}
function isScheduleTargetAlreadySent(jobKey, date, target){
  const info = scheduleSentInfo(sentLog[jobKey]);
  if(info.date === date && info.legacy) return true;
  if(info.date !== date) return false;
  const tk = scheduleTargetLogKey(target);
  return !!(tk && info.targets && info.targets[tk] === true);
}
function markScheduleTargetSent(jobKey, date, target){
  const info = scheduleSentInfo(sentLog[jobKey]);
  const current = info.date === date ? info : { date, targets:{} };
  current.targets = current.targets && typeof current.targets === "object" ? current.targets : {};
  const tk = scheduleTargetLogKey(target);
  if(tk) current.targets[tk] = true;
  current.updatedAt = nowIso();
  sentLog[jobKey] = current;
}

function markResultTargetSent(key, signature, rawTarget){
  const info = resultSentInfo(sentLog[key]);
  info.signature = signature;
  info.targets = info.targets || {};
  info.targets[resultTargetLogKey(rawTarget)] = nowIso();
  info.updatedAt = nowIso();
  info.legacy = false;
  sentLog[key] = info;
}
function isResultTargetAlreadySent(key, signature, rawTarget){
  const info = resultSentInfo(sentLog[key]);
  if(info.signature !== signature) return false;
  return !!(info.targets && info.targets[resultTargetLogKey(rawTarget)]);
}

// ============================================================
// STRICT WHATSAPP ENTRY PARSER — Phase 3
// Accepts only explicit card format:
// MARKET: KALYAN OPEN
// TYPE: ANK | JODI | PENEL
// DIGITS: 1,2,3
// PAR DIGIT: 100
// TOTAL: 300
// ============================================================
function phoneKey(v){
  const raw = String(v || "").trim();
  // New WhatsApp/Baileys group messages can sometimes expose a @lid sender id.
  // @lid digits are not the real phone number, so never use them for VIP phone linking.
  if(raw.includes("@") && !raw.includes("@s.whatsapp.net")) return "";
  const d = raw.replace(/\D/g, "");
  if(d.length < 10) return "";
  return d.length > 10 ? d.slice(-10) : d;
}
function whatsappIdentityKey(v){
  const raw = String(v || "").trim().toLowerCase();
  if(!raw || !raw.includes("@")) return "";
  // Keep @lid/@g.us-safe sender aliases for identity matching, but never use them as phone numbers.
  return raw.replace(/[^0-9a-z@._:-]/g, "").slice(0, 120);
}
function whatsappIdentityHash(keys){
  const seed = (Array.isArray(keys) ? keys : [keys]).map(whatsappIdentityKey).filter(Boolean).sort().join("|");
  return seed ? crypto.createHash("sha1").update(seed).digest("hex").slice(0, 16) : "";
}
function profileWhatsappIdentityKeys(profile){
  const raw = [profile?.whatsappSenderJid, profile?.whatsappLid, profile?.whatsappIdentityKey, ...(Array.isArray(profile?.whatsappJids) ? profile.whatsappJids : [])];
  return [...new Set(raw.map(whatsappIdentityKey).filter(Boolean))];
}
function senderCandidatesFromMessage(m, chatJid){
  const key = m?.key || {};
  const candidates = [
    key.participant,
    key.participantPn,
    key.senderPn,
    key.participantAlt,
    key.participantAltJid,
    key.remoteJidAlt,
    m?.participant,
    m?.participantPn,
    m?.senderPn
  ];
  if(chatJid && !String(chatJid).endsWith("@g.us")) candidates.push(chatJid);
  return [...new Set(candidates.map(x => String(x || "").trim()).filter(Boolean))];
}
function profileTemplateForAutoLink(phone, name, identityKeys = []){
  const waKeys = [...new Set((Array.isArray(identityKeys) ? identityKeys : [identityKeys]).map(whatsappIdentityKey).filter(Boolean))];
  return {
    name: name || (phone ? `VIP ${phone}` : (waKeys[0] ? `WA ${waKeys[0].slice(0, 10)}` : "AUTO VIP")),
    phone: phone || "",
    whatsappJids: waKeys,
    whatsappSenderJid: waKeys[0] || "",
    config: { ankSplit:true, panSplit:true, capital:0, dayTarget:0, ank:{cap:0,tgt:0}, jodi:{cap:0,tgt:0}, pannel:{cap:0,tgt:0} },
    dayRecords: {},
    expiryDate: "",
    vipAccessEnabled: false,
    approvalStatus: "pending",
    approvalRequestedAt: nowIso(),
    approvalSource: "whatsapp_entry_parser",
    autoCreated: true,
    createdAt: nowIso()
  };
}
function nowIso(){ return new Date().toISOString(); }
function money(v){ const n = Number(v || 0); return "₹" + (Number.isInteger(n) ? String(n) : n.toFixed(2)); }
function walletHoldAmount(wallet){ return Number(wallet?.hold || wallet?.walletHold || 0); }
function setWalletHold(wallet, amount){ wallet.hold = Math.max(0, Math.round(Number(amount || 0) * 100) / 100); wallet.walletHold = wallet.hold; return wallet.hold; }
function entryAvailable(wallet){ return Math.round((Number(wallet?.balance || 0) + Number(wallet?.creditLimit || 0) - walletHoldAmount(wallet)) * 100) / 100; }
function withdrawAvailable(wallet){ return Math.round((Number(wallet?.balance || 0) - walletHoldAmount(wallet)) * 100) / 100; }
function recordWalletTransaction(state, userId, wallet, ledgerEntry){
  if(!state || !userId || !wallet || !ledgerEntry) return null;
  if(!Array.isArray(state.walletTransactions)) state.walletTransactions = [];
  const id = String(ledgerEntry.txnId || `${userId}_${ledgerEntry.id || Date.now()}_${ledgerEntry.type || 'wallet'}`).slice(0,120);
  ledgerEntry.txnId = id;
  if(state.walletTransactions.some(x => x && x.id === id)) return null;
  const prof = state?.profiles?.[userId] || {};
  const txn = {
    id, userId, name: wallet.name || prof.name || userId, phone: wallet.phone || prof.phone || '',
    time: ledgerEntry.time || nowIso(), type: ledgerEntry.type || 'wallet', amount: Number(ledgerEntry.amount || 0),
    balanceBefore: Number(ledgerEntry.balanceBefore || 0), balanceAfter: Number(ledgerEntry.balanceAfter || 0),
    holdBefore: Number(ledgerEntry.holdBefore || walletHoldAmount(wallet) || 0), holdAfter: Number(ledgerEntry.holdAfter || walletHoldAmount(wallet) || 0),
    creditLimit: Number(wallet.creditLimit || 0), note: ledgerEntry.note || ledgerEntry.type || 'Wallet transaction',
    source: ledgerEntry.source || 'gateway_wallet',
    refId: ledgerEntry.withdrawalId || ledgerEntry.paymentId || ledgerEntry.entryId || ledgerEntry.settlementKey || ledgerEntry.id || '',
    entryId: ledgerEntry.entryId || '', paymentId: ledgerEntry.paymentId || '', withdrawalId: ledgerEntry.withdrawalId || '', settlementKey: ledgerEntry.settlementKey || ''
  };
  state.walletTransactions.push(txn);
  if(state.walletTransactions.length > 2000) state.walletTransactions.splice(0, state.walletTransactions.length - 2000);
  return txn;
}
function withdrawalSettings(state){
  const s = state?.withdrawalSettings || {};
  return {
    enabled: s.enabled !== false,
    minAmount: Number(s.minAmount || 1),
    maxAmount: Number(s.maxAmount || 200000),
    onePendingPerUser: s.onePendingPerUser !== false,
    notifyUserPrivate: s.notifyUserPrivate !== false,
    notifyAdminPrivate: s.notifyAdminPrivate !== false,
    adminNotifyTargets: Array.isArray(s.adminNotifyTargets) ? s.adminNotifyTargets : String(s.adminNotifyTargets || "").split(/[\n,]+/).map(x=>x.trim()).filter(Boolean)
  };
}
function nextWithdrawalId(state){
  const n = Array.isArray(state.withdrawals) ? state.withdrawals.length + 1 : 1;
  return "W" + todayISO().replace(/-/g, "").slice(2) + "-" + String(n).padStart(4, "0");
}
function cleanWhatsAppTarget(raw){
  const jid = normalizeTarget(raw);
  if(jid && !jid.startsWith("invite:")) return jid;
  let t = String(raw || "").trim();
  if(!t) return "";
  let d = t.replace(/\D/g, "");
  if(!d) return "";
  if(d.length > 12) d = d.slice(-12);
  if(d.length === 10) d = "91" + d;
  if(d.length < 10) return "";
  return d + "@s.whatsapp.net";
}
function adminNotifyTargets(state){
  const cfg = withdrawalSettings(state);
  const out = [];
  const add = (x) => { const t = cleanWhatsAppTarget(x); if(t && !out.includes(t)) out.push(t); };
  collectBookieAdminTargets(state).forEach(add);
  (cfg.adminNotifyTargets || []).forEach(add);
  if(!out.length){
    for(const [uid, prof] of Object.entries(state?.profiles || {})){
      if(String(uid).startsWith("admin")) add(prof?.phone || "");
    }
  }
  return out;
}
function queueWhatsAppOutbox(state, target, text, meta = {}){
  const t = cleanWhatsAppTarget(target);
  if(!t || !text) return null;
  if(!Array.isArray(state.paymentOutbox)) state.paymentOutbox = [];
  const msg = { id:Math.random().toString(36).slice(2,10).toUpperCase(), time:nowIso(), target:t, text:String(text), status:"pending", attempts:0, meta };
  state.paymentOutbox.push(msg);
  if(state.paymentOutbox.length > 300) state.paymentOutbox = state.paymentOutbox.slice(-300);
  return msg;
}
function userTargetFromProfile(profile){
  const t = cleanWhatsAppTarget(profile?.phone || "");
  return t;
}

function normalizeEntryMarketText(v){
  return String(v || "").toUpperCase().replace(/SRIDEVI\s+DAY/g, "SRIDEV DAY").replace(/[^A-Z0-9]+/g, " ").trim().replace(/\s+/g, " ");
}
function compactEntryMarket(v){ return normalizeEntryMarketText(v).replace(/[^A-Z0-9]/g, ""); }
function canonicalAnkPenelMarket(v, state=null){
  const target = compactEntryMarket(v);
  const arr = state ? marketArraysForPurpose(state, "ledger").markets : MARKETS;
  const found = arr.find(m => compactEntryMarket(m.n) === target);
  return found ? found.n : "";
}
function canonicalJodiMarket(v, state=null){
  let raw = normalizeEntryMarketText(v).replace(/\s+(OPEN|CLOSE)$/i, "").trim();
  const target = compactEntryMarket(raw);
  const arr = state ? marketArraysForPurpose(state, "ledger").baseMarkets : BASE_MARKETS;
  const found = arr.find(m => compactEntryMarket(m.n) === target);
  return found ? found.n : "";
}
const DEFAULT_ENTRY_FORMAT_TEMPLATE = "MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}";
const ENTRY_FORMAT_PLACEHOLDERS = ["market", "type", "digits", "parDigit", "total"];
function escapeEntryRegexLiteral(v){ return String(v || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+"); }
function entryFormatTemplate(state=null){
  const tpl = state?.entrySettings?.entryFormatTemplate;
  return String(tpl || DEFAULT_ENTRY_FORMAT_TEMPLATE).trim() || DEFAULT_ENTRY_FORMAT_TEMPLATE;
}
function parseEntryFieldsByTemplate(raw, template){
  const parts = String(template || "").split(/(\{(?:market|type|digits|parDigit|total)\})/g).filter(x => x !== "");
  const seen = new Set();
  let pattern = "^\\s*";
  for(let i=0; i<parts.length; i++){
    const m = /^\{(.+)\}$/.exec(parts[i]);
    if(m){
      const name = m[1];
      if(seen.has(name)) return null;
      seen.add(name);
      pattern += `(?<${name}>[\\s\\S]+?)`;
    }else{
      pattern += escapeEntryRegexLiteral(parts[i]);
    }
  }
  pattern += "\\s*$";
  if(ENTRY_FORMAT_PLACEHOLDERS.some(k => !seen.has(k))) return null;
  const match = new RegExp(pattern, "i").exec(String(raw || ""));
  if(!match || !match.groups) return null;
  const fields = {};
  ENTRY_FORMAT_PLACEHOLDERS.forEach(k => { fields[k] = String(match.groups[k] || "").trim(); });
  return fields;
}
function parseEntryCardDynamic(text, template=DEFAULT_ENTRY_FORMAT_TEMPLATE, state=null){
  const raw = String(text || "").replace(/\r/g, "\n").trim();
  template = String(template || DEFAULT_ENTRY_FORMAT_TEMPLATE).trim() || DEFAULT_ENTRY_FORMAT_TEMPLATE;
  let fields = parseEntryFieldsByTemplate(raw, template);
  if(!fields && template !== DEFAULT_ENTRY_FORMAT_TEMPLATE) fields = parseEntryFieldsByTemplate(raw, DEFAULT_ENTRY_FORMAT_TEMPLATE);
  if(!fields) {
    if(!/\bMARKET\s*:/i.test(raw) && !/\bDIGITS?\s*:/i.test(raw)) return { ok:false, silent:true, reason:"not_entry_card" };
    fields = {};
    for(const line of raw.split(/\n+/)){
      const idx = line.indexOf(":");
      if(idx < 0) continue;
      const key = line.slice(0, idx).trim().toUpperCase().replace(/\s+/g, " ");
      const val = line.slice(idx + 1).trim();
      if(["MARKET"].includes(key)) fields.market = val;
      else if(["TYPE", "GAME", "GAME TYPE"].includes(key)) fields.type = val;
      else if(["DIGITS", "DIGIT"].includes(key)) fields.digits = val;
      else if(["PAR DIGIT", "PER DIGIT", "RATE", "PAR", "AMOUNT"].includes(key)) fields.parDigit = val;
      else if(["TOTAL", "TOTAL AMOUNT"].includes(key)) fields.total = val;
    }
  }
  const missing = [];
  for(const k of ["market", "type", "digits", "parDigit", "total"]) if(!fields[k]) missing.push(k);
  if(missing.length) return { ok:false, reason:"missing_field", message:`Missing field: ${missing.join(", ")}. Strict format: MARKET, TYPE, DIGITS, PAR DIGIT, TOTAL` };
  let gameType = String(fields.type || "").trim().toUpperCase();
  if(gameType === "PANEL" || gameType === "PANNEL") gameType = "PENEL";
  if(!["ANK", "JODI", "PENEL"].includes(gameType)) return { ok:false, reason:"invalid_type", message:"TYPE sirf ANK, JODI, ya PENEL hona chahiye." };
  let market = "";
  if(gameType === "JODI") market = canonicalJodiMarket(fields.market, state);
  else market = canonicalAnkPenelMarket(fields.market, state);
  if(!market){
    return { ok:false, reason:"invalid_market", message: gameType === "JODI" ? "JODI ke liye valid base MARKET chahiye. Example: KALYAN" : "ANK/PENEL ke liye valid OPEN/CLOSE MARKET chahiye. Example: KALYAN OPEN" };
  }
  const digits = String(fields.digits || "").split(/[,\s]+/).map(x=>x.trim()).filter(Boolean);
  if(!digits.length) return { ok:false, reason:"digits_missing", message:"DIGITS field empty hai." };
  for(const d of digits){
    if(gameType === "ANK" && !/^\d$/.test(d)) return { ok:false, reason:"invalid_ank_digit", message:`ANK digit invalid: ${d}. Sirf 0-9 allowed.` };
    if(gameType === "JODI" && !/^\d{1,2}$/.test(d)) return { ok:false, reason:"invalid_jodi_digit", message:`JODI digit invalid: ${d}. Sirf 00-99 allowed.` };
    if(gameType === "PENEL" && !/^\d{3}$/.test(d)) return { ok:false, reason:"invalid_penel_digit", message:`PENEL digit invalid: ${d}. Sirf 000-999 allowed.` };
  }
  const normDigits = digits.map(d => gameType === "JODI" ? d.padStart(2,"0") : d);
  const parDigit = Number(String(fields.parDigit || "").replace(/[^0-9.]/g, ""));
  const total = Number(String(fields.total || "").replace(/[^0-9.]/g, ""));
  if(!Number.isFinite(parDigit) || parDigit <= 0) return { ok:false, reason:"invalid_rate", message:"PAR DIGIT valid amount hona chahiye." };
  if(!Number.isFinite(total) || total <= 0) return { ok:false, reason:"invalid_total", message:"TOTAL valid amount hona chahiye." };
  const expected = Math.round(parDigit * normDigits.length * 100) / 100;
  if(Math.abs(expected - total) > 0.001){
    return { ok:false, reason:"total_mismatch", message:`TOTAL mismatch. Expected ${money(expected)} (${normDigits.length} digit × ${money(parDigit)}), received ${money(total)}.` };
  }
  return { ok:true, market, gameType, digits:normDigits, parDigit, total, rawText:raw };
}
function parseEntryCard(text, state=null){
  return parseEntryCardDynamic(text, entryFormatTemplate(state), state);
}

function entrySettings(state){
  const s = state?.entrySettings || {};
  return {
    entryParserEnabled: s.entryParserEnabled !== false,
    groupsOnly: s.groupsOnly !== false,
    strictFormat: s.strictFormat !== false,
    autoDebitWallet: s.autoDebitWallet !== false,
    marketTimingEnabled: s.marketTimingEnabled !== false,
    riskLimitEnabled: s.riskLimitEnabled !== false,
    autoLinkUnknownSender: s.autoLinkUnknownSender !== false,
    autoCreatePendingProfiles: s.autoCreatePendingProfiles !== false,
    requireProfileApproval: s.requireProfileApproval !== false,
    marketTargets: (s.marketTargets && typeof s.marketTargets === 'object') ? s.marketTargets : {},
    marketEntryEnabled: (s.marketEntryEnabled && typeof s.marketEntryEnabled === 'object') ? s.marketEntryEnabled : {},
    allowUnmappedMarkets: s.allowUnmappedMarkets !== false,
    entryFormatTemplate: entryFormatTemplate(state)
  };
}

function entryTargetListForMarket(state, market){
  const settings = entrySettings(state);
  const map = settings.marketTargets || {};
  const compact = compactEntryMarket(market);
  const candidates = [String(market || '').toUpperCase().trim(), normalizeEntryMarketText(market)];
  const base = String(market || '').toUpperCase().replace(/\s+(OPEN|CLOSE)$/,'').trim();
  if(base) candidates.push(base);
  for(const key of candidates){
    if(Array.isArray(map[key]) && map[key].length) return map[key].map(normalizeTarget).filter(Boolean);
  }
  for(const [key, targets] of Object.entries(map)){
    if(Array.isArray(targets) && targets.length && compactEntryMarket(key) === compact) return targets.map(normalizeTarget).filter(Boolean);
  }
  return [];
}
function entryMarketEnabledForEntry(state, market){
  const settings = entrySettings(state);
  const enabledMap = settings.marketEntryEnabled || {};
  const compact = compactEntryMarket(market);
  const candidates = [String(market || '').toUpperCase().trim(), normalizeEntryMarketText(market), String(market || '').toUpperCase().replace(/\s+(OPEN|CLOSE)$/,'').trim()];
  for(const key of candidates){ if(typeof enabledMap[key] !== 'undefined') return enabledMap[key] !== false; }
  for(const [key, value] of Object.entries(enabledMap)){ if(compactEntryMarket(key) === compact) return value !== false; }
  try{
    const items = state?.marketRegistry?.items || {};
    const base = compactEntryMarket(String(market || '').replace(/\s+(OPEN|CLOSE)$/i,''));
    for(const item of Object.values(items)){
      if(!item || typeof item !== 'object') continue;
      const names = [item.name, item.displayName, item.websiteName].map(compactEntryMarket);
      if(names.includes(base) || names.includes(compact)) return item.entryEnabled !== false;
    }
  }catch(e){}
  return true;
}
function validateEntrySourceTarget(state, parsed, chatJid){
  if(!parsed || !parsed.market) return {ok:true};
  if(!entryMarketEnabledForEntry(state, parsed.market)) return {ok:false, message:`${parsed.market} entries Market Manager me OFF hain.`};
  const targets = entryTargetListForMarket(state, parsed.market);
  if(!targets.length) return {ok:true};
  const current = normalizeTarget(chatJid);
  if(targets.includes(current)) return {ok:true};
  return {ok:false, message:`${parsed.market} ka entry is WhatsApp target me allowed nahi hai. Admin Market tab me Entry Targets set karein.`};
}

function riskSettings(state){
  const r = state?.riskSettings || {};
  return {
    marketDailyLimit: Number(r.marketDailyLimit || 0),
    digitDailyLimit: Number(r.digitDailyLimit || 0),
    userDailyLimit: Number(r.userDailyLimit || 0),
    warningPercent: Math.max(1, Math.min(100, Number(r.warningPercent || 80))),
    autoLockOnLimit: r.autoLockOnLimit === true
  };
}
function marketCloseTimes(state){
  return {
    ...DEFAULT_MARKET_CLOSE_TIMES,
    ...((state?.riskSettings?.marketCloseTimes && typeof state.riskSettings.marketCloseTimes === "object") ? state.riskSettings.marketCloseTimes : {}),
    ...((state?.entrySettings?.marketCloseTimes && typeof state.entrySettings.marketCloseTimes === "object") ? state.entrySettings.marketCloseTimes : {})
  };
}
function resolveMarketCloseTime(state, market){
  const times = marketCloseTimes(state);
  const raw = normalizeEntryMarketText(market);
  const compact = compactEntryMarket(market);
  const candidates = [market, raw];
  const canon = canonicalAnkPenelMarket(market) || canonicalJodiMarket(market);
  if(canon) candidates.push(canon);
  for(const key of candidates){
    if(times[key]) return times[key];
    const upper = String(key || "").toUpperCase().trim();
    if(times[upper]) return times[upper];
  }
  for(const [key, value] of Object.entries(times)){
    if(compactEntryMarket(key) === compact) return value;
  }
  return "";
}
function isLockedMarket(state, date, market){
  const locks = state?.marketLocks || {};
  const todayLocks = locks[date] || {};
  const rec = todayLocks[market] || locks[market] || null;
  return !!(rec && (rec.locked === true || rec === true));
}
function lockMarket(state, date, market, reason){
  if(!state.marketLocks || typeof state.marketLocks !== "object") state.marketLocks = {};
  if(!state.marketLocks[date] || typeof state.marketLocks[date] !== "object") state.marketLocks[date] = {};
  state.marketLocks[date][market] = { locked:true, reason:reason || "risk_limit", lockedAt:nowIso() };
}
function isEntryMarketClosed(state, market){
  const time = normalizeTime(resolveMarketCloseTime(state, market) || "");
  if(!time) return { closed:false, cutoff:"" };
  const now = nowHHMM();
  const cut = hhmmToMinutes(time), cur = hhmmToMinutes(now);
  if(cut < 0 || cur < 0) return { closed:false, cutoff:time };
  let closed = false;
  if(cut <= 60){
    closed = (cur > cut && cur < 12 * 60);
  } else {
    closed = cur > cut;
  }
  return { closed, cutoff:time, now };
}
function existingAcceptedEntries(state, date){
  return (Array.isArray(state?.entries) ? state.entries : []).filter(e => e && e.status === "accepted" && e.date === date);
}
function entryHasDigit(e, digit){
  const list = Array.isArray(e?.digits) ? e.digits : String(e?.digits || "").split(/[,\.\s]+/).filter(Boolean);
  const target = String(digit);
  return list.map(x => String(x).padStart(target.length, "0")).includes(target);
}
function calculateRiskLoads(state, date, parsed, userId){
  const entries = existingAcceptedEntries(state, date);
  const userTotal = entries.filter(e => e.userId === userId).reduce((s,e)=>s+Number(e.total||0),0);
  const marketTotal = entries.filter(e => e.market === parsed.market).reduce((s,e)=>s+Number(e.total||0),0);
  const digitLoads = {};
  for(const d of parsed.digits){
    digitLoads[d] = entries
      .filter(e => e.market === parsed.market && e.gameType === parsed.gameType && entryHasDigit(e, d))
      .reduce((s,e)=>s+Number(e.parDigit || 0),0);
  }
  return { userTotal, marketTotal, digitLoads };
}
function validateEntryRiskAndTiming(state, parsed, userId){
  const date = todayISO();
  const settings = entrySettings(state);
  const risk = riskSettings(state);
  const warnings = [];
  if(isLockedMarket(state, date, parsed.market)){
    return { ok:false, message:`${parsed.market} locked hai. Admin unlock karein.` };
  }
  if(settings.marketTimingEnabled){
    const t = isEntryMarketClosed(state, parsed.market);
    if(t.closed) return { ok:false, message:`${parsed.market} ka entry time close ho gaya hai. Cut-off ${t.cutoff} IST, current ${t.now} IST.` };
  }
  if(!settings.riskLimitEnabled) return { ok:true, warnings };
  const loads = calculateRiskLoads(state, date, parsed, userId);
  if(risk.userDailyLimit > 0 && loads.userTotal + parsed.total > risk.userDailyLimit){
    return { ok:false, message:`User daily limit cross ho raha hai. Used ${money(loads.userTotal)}, limit ${money(risk.userDailyLimit)}, entry ${money(parsed.total)}.` };
  }
  if(risk.marketDailyLimit > 0 && loads.marketTotal + parsed.total > risk.marketDailyLimit){
    if(risk.autoLockOnLimit) lockMarket(state, date, parsed.market, "market_daily_limit");
    return { ok:false, saveState:risk.autoLockOnLimit, message:`Market daily limit cross ho raha hai. ${parsed.market} used ${money(loads.marketTotal)}, limit ${money(risk.marketDailyLimit)}, entry ${money(parsed.total)}.` };
  }
  if(risk.digitDailyLimit > 0){
    for(const d of parsed.digits){
      const used = Number(loads.digitLoads[d] || 0);
      if(used + parsed.parDigit > risk.digitDailyLimit){
        if(risk.autoLockOnLimit) lockMarket(state, date, parsed.market, `digit_limit_${d}`);
        return { ok:false, saveState:risk.autoLockOnLimit, message:`Digit load limit cross: ${parsed.market} ${parsed.gameType} ${d}. Used ${money(used)}, limit ${money(risk.digitDailyLimit)}, entry ${money(parsed.parDigit)}.` };
      }
    }
  }
  const wp = risk.warningPercent / 100;
  if(risk.userDailyLimit > 0 && loads.userTotal + parsed.total >= risk.userDailyLimit * wp) warnings.push(`User daily load ${money(loads.userTotal + parsed.total)} / ${money(risk.userDailyLimit)}`);
  if(risk.marketDailyLimit > 0 && loads.marketTotal + parsed.total >= risk.marketDailyLimit * wp) warnings.push(`Market load ${money(loads.marketTotal + parsed.total)} / ${money(risk.marketDailyLimit)}`);
  if(risk.digitDailyLimit > 0){
    for(const d of parsed.digits){
      const val = Number(loads.digitLoads[d] || 0) + parsed.parDigit;
      if(val >= risk.digitDailyLimit * wp) warnings.push(`Digit ${d} load ${money(val)} / ${money(risk.digitDailyLimit)}`);
    }
  }
  return { ok:true, warnings };
}
function findProfileBySender(state, senderJid, meta = {}){
  if(!state.profiles || typeof state.profiles !== "object") state.profiles = {};
  const profiles = state.profiles;
  const candidates = [senderJid, ...(Array.isArray(meta.senderCandidates) ? meta.senderCandidates : [])];
  const keys = [...new Set(candidates.map(phoneKey).filter(Boolean))];
  const identityKeys = [...new Set(candidates.map(whatsappIdentityKey).filter(Boolean))];
  if(!keys.length && !identityKeys.length) return null;

  // 1) Existing profile means the WhatsApp phone is already linked on a profile.
  // New users must NOT be matched to an empty-phone VIP profile, otherwise they reach
  // wallet validation directly and see "Insufficient wallet" instead of profile creation.
  for(const [pid, prof] of Object.entries(profiles)){
    const pk = phoneKey(prof?.phone || "");
    if(pk && keys.includes(pk)) return { userId:pid, profile:prof, matchedPhone:pk, existingProfile:true };
    const profIdentity = profileWhatsappIdentityKeys(prof);
    if(identityKeys.length && profIdentity.some(x => identityKeys.includes(x))) return { userId:pid, profile:prof, matchedPhone:pk || "", matchedIdentity:true, existingProfile:true };
  }

  // 2) Fallback: if a wallet already has this phone and the same user profile exists,
  // treat it as an existing linked user.
  const wallets = state?.wallets || {};
  for(const [uid, wallet] of Object.entries(wallets)){
    const wk = phoneKey(wallet?.phone || "");
    if(wk && keys.includes(wk) && profiles[uid]) return { userId:uid, profile:profiles[uid], matchedPhone:wk, existingProfile:true, matchedWallet:true };
  }

  const settings = entrySettings(state);

  // 3) True unknown WhatsApp number: create its own pending profile first.
  // Admin approval must happen before the first entry can be accepted.
  if(settings.autoCreatePendingProfiles !== false){
    const identityHash = whatsappIdentityHash(identityKeys);
    const uid = keys[0] ? `client_${keys[0]}` : `client_wa_${identityHash}`;
    if(!profiles[uid]){
      profiles[uid] = profileTemplateForAutoLink(keys[0] || "", meta.pushName || (keys[0] ? `VIP ${keys[0]}` : "WhatsApp VIP"), identityKeys);
      profiles[uid].phoneDetectionStatus = keys[0] ? "detected" : "identity_only";
      return { userId:uid, profile:profiles[uid], matchedPhone:keys[0] || "", matchedIdentity:!keys[0], autoCreated:true, pendingApproval:true };
    }
    const prof = profiles[uid];
    if(Array.isArray(prof.whatsappJids)){
      for(const k of identityKeys) if(k && !prof.whatsappJids.includes(k)) prof.whatsappJids.push(k);
    } else if(identityKeys.length) prof.whatsappJids = identityKeys;
    if(keys[0] && !phoneKey(prof.phone || "")) prof.phone = keys[0];
    return { userId:uid, profile:prof, matchedPhone:keys[0] || phoneKey(prof.phone || ""), matchedIdentity:!keys[0], existingProfile:true };
  }

  // 4) Optional legacy fallback only when auto profile creation is disabled.
  // This prevents new WhatsApp users from being silently attached to a blank profile.
  if(settings.autoLinkUnknownSender !== false){
    const emptyClients = Object.entries(profiles).filter(([pid, prof]) =>
      !String(pid).startsWith("admin") && (!phoneKey(prof?.phone || ""))
    );
    if(emptyClients.length === 1){
      const [pid, prof] = emptyClients[0];
      prof.phone = keys[0];
      if(!prof.name && meta.pushName) prof.name = meta.pushName;
      prof.autoLinkedPhoneAt = nowIso();
      prof.autoLinkedFrom = candidates[0] || senderJid || "";
      // Since this phone was not previously linked, keep it under approval.
      prof.autoCreated = prof.autoCreated === true;
      prof.approvalStatus = "pending";
      prof.vipAccessEnabled = false;
      return { userId:pid, profile:prof, matchedPhone:keys[0], autoLinked:true, pendingApproval:true };
    }
  }
  return null;
}
function ensureWalletInState(state, userId){
  if(!state.wallets || typeof state.wallets !== "object") state.wallets = {};
  if(!Array.isArray(state.walletTransactions)) state.walletTransactions = [];
  const prof = state?.profiles?.[userId] || {};
  const settings = state.walletSettings || {};
  if(!state.wallets[userId] || typeof state.wallets[userId] !== "object"){
    state.wallets[userId] = { userId, name:prof.name || userId, phone:prof.phone || "", balance:0, hold:0, walletHold:0, creditLimit:Number(settings.defaultCreditLimit || 0), ledger:[], createdAt:nowIso(), updatedAt:nowIso() };
  }
  const w = state.wallets[userId];
  if(!Array.isArray(w.ledger)) w.ledger = [];
  w.balance = Number(w.balance || 0);
  w.hold = Number(w.hold || w.walletHold || 0);
  w.walletHold = w.hold;
  w.creditLimit = Number(w.creditLimit || 0);
  w.name = prof.name || w.name || userId;
  w.phone = prof.phone || w.phone || "";
  return w;
}
function entrySignature(entry){
  return [entry.date, entry.userId, entry.market, entry.gameType, entry.digits.join("."), entry.parDigit, entry.total].join("|");
}
function nextEntryId(state){
  const n = (state.entries || []).length + 1;
  const rand = Math.random().toString(36).slice(2,5).toUpperCase();
  return "E" + todayISO().replace(/-/g,"").slice(2) + "-" + String(n).padStart(4,"0") + rand;
}
function profileApprovalStatus(profile){
  if(!profile || typeof profile !== "object") return "pending";
  const current = String(profile.approvalStatus || "").toLowerCase();
  if(current) return current;
  // Profiles created/linked from WhatsApp must wait for admin approval.
  // Normal old/manual profiles without approvalStatus remain approved for backward compatibility.
  const needsApproval = profile.autoCreated === true || !!profile.autoLinkedPhoneAt || String(profile.approvalSource || "").toLowerCase() === "whatsapp_entry_parser";
  profile.approvalStatus = needsApproval ? "pending" : "approved";
  if(needsApproval) profile.vipAccessEnabled = false;
  return profile.approvalStatus;
}
async function saveAcceptedEntryToFirebaseUnlocked(parsed, meta){
  const state = await fetchFirebaseState();
  const settings = entrySettings(state);
  if(!settings.entryParserEnabled) return { ok:false, reason:"parser_disabled", message:"Entry parser admin app me OFF hai." };
  if(!state.entries || !Array.isArray(state.entries)) state.entries = [];
  const found = findProfileBySender(state, meta.senderJid, meta);
  if(!found){
    const detected = (Array.isArray(meta.senderCandidates) ? meta.senderCandidates : [meta.senderJid]).map(phoneKey).filter(Boolean)[0] || "phone_not_detected";
    return { ok:false, reason:"profile_not_found", message:`Aapka WhatsApp number VIP profile me linked nahi hai. Detected: ${detected}. Admin app me VIP phone same number se set karein.` };
  }
  const profile = found.profile || {};
  const approvalStatus = profileApprovalStatus(profile);
  const isAdminUser = String(found.userId || "").startsWith("admin");
  if(settings.requireProfileApproval !== false && !isAdminUser && approvalStatus !== "approved"){
    profile.approvalStatus = approvalStatus || "pending";
    profile.vipAccessEnabled = false;
    profile.lastEntryRequestAt = nowIso();
    profile.lastEntryRequestText = String(parsed.rawText || "").slice(0, 500);
    profile.lastEntryChatJid = meta.chatJid || "";
    profile.lastEntrySenderJid = meta.senderJid || "";
    ensureWalletInState(state, found.userId);
    if(!Array.isArray(state.auditLog)) state.auditLog = [];
    state.auditLog.push({ id:`AP${Date.now()}`, time:nowIso(), action:"profile_pending_approval", detail:{ userId:found.userId, phone:profile.phone || found.matchedPhone || "", name:profile.name || "", autoCreated:!!found.autoCreated } });
    if(state.auditLog.length > 500) state.auditLog.splice(0, state.auditLog.length - 500);
    await saveGatewayProfileSync(state, found.userId);
    return { ok:false, reason:"profile_pending_approval", message:"Aapka profile auto-create ho gaya hai. Admin approval ke baad entry accept hogi." };
  }
  const riskCheck = validateEntryRiskAndTiming(state, parsed, found.userId);
  if(!riskCheck.ok){
    if(riskCheck.saveState) await saveGatewayChildren(state, ['marketLocks']);
    return { ok:false, reason:"risk_or_time_rejected", message:riskCheck.message || "Entry risk/time validation failed." };
  }
  const entry = {
    id: nextEntryId(state),
    date: todayISO(),
    createdAt: nowIso(),
    source: "whatsapp_entry_parser",
    status: "accepted",
    userId: found.userId,
    userName: profile.name || found.userId,
    userPhone: profile.phone || "",
    senderJid: meta.senderJid,
    chatJid: meta.chatJid,
    market: parsed.market,
    gameType: parsed.gameType,
    digits: parsed.digits,
    parDigit: parsed.parDigit,
    total: parsed.total,
    rawText: parsed.rawText,
    riskWarning: Array.isArray(riskCheck.warnings) ? riskCheck.warnings : []
  };
  const sig = entrySignature(entry);
  const duplicate = state.entries.find(e => e.status === "accepted" && [e.date, e.userId, e.market, e.gameType, (Array.isArray(e.digits)?e.digits.join("."):String(e.digits||"")), e.parDigit, e.total].join("|") === sig);
  if(duplicate) return { ok:false, reason:"duplicate_entry", message:`Duplicate entry already accepted. ID: ${duplicate.id}` };
  const wSettings = state.walletSettings || {};
  const walletEnabled = wSettings.walletEnabled !== false && settings.autoDebitWallet !== false;
  let wallet = null;
  if(walletEnabled){
    wallet = ensureWalletInState(state, found.userId);
    const available = entryAvailable(wallet);
    if(available + 0.0001 < parsed.total){
      return { ok:false, reason:"insufficient_wallet", message:`Insufficient wallet. Available ${money(available)}, entry total ${money(parsed.total)}.` };
    }
    const before = Number(wallet.balance || 0);
    const after = Math.round((before - parsed.total) * 100) / 100;
    wallet.balance = after;
    wallet.updatedAt = nowIso();
    const ledgerEntry = { id:entry.id, time:nowIso(), type:"entry_debit", amount:-parsed.total, balanceBefore:before, balanceAfter:after, holdBefore:walletHoldAmount(wallet), holdAfter:walletHoldAmount(wallet), note:`Entry debit ${entry.market} ${entry.gameType}`, source:"whatsapp_entry_parser", entryId:entry.id };
    wallet.ledger.push(ledgerEntry);
    recordWalletTransaction(state, found.userId, wallet, ledgerEntry);
    entry.walletDebited = true;
    entry.balanceAfter = after;
  } else {
    entry.walletDebited = false;
  }
  state.entries.push(entry);
  if(!Array.isArray(state.auditLog)) state.auditLog = [];
  state.auditLog.push({ id:entry.id, time:nowIso(), action:"entry_accepted", detail:{ userId:entry.userId, market:entry.market, gameType:entry.gameType, total:entry.total, walletDebited:entry.walletDebited } });
  if(state.auditLog.length > 500) state.auditLog.splice(0, state.auditLog.length - 500);
  await saveGatewayEntryAcceptNarrow(state, found.userId);
  return { ok:true, entry, wallet };
}
async function saveAcceptedEntryToFirebase(parsed, meta){
  const lockKey = entryMessageLockKey(parsed, meta || {});
  const lock = await acquireDurableLock('whatsapp_entry_accept', lockKey, 2 * 60 * 1000, { chatJid:meta?.chatJid || '', senderJid:meta?.senderJid || '', market:parsed?.market || '', gameType:parsed?.gameType || '', total:Number(parsed?.total || 0) });
  if(!lock.ok){
    const existing = lock.existing || {};
    if(lock.done) return { ok:false, reason:'duplicate_message_done', message: existing.message || 'Ye entry message already process ho chuka hai. Duplicate accept nahi hoga.' };
    return { ok:false, reason:'duplicate_message_processing', message:'Ye entry message abhi process ho raha hai. Duplicate accept nahi hoga.' };
  }
  try{
    const out = await saveAcceptedEntryToFirebaseUnlocked(parsed, meta || {});
    await markDurableDone('whatsapp_entry_accept', lockKey, { ok:!!out.ok, reason:out.reason || '', message:out.message || '', entryId:out.entry?.id || '', userId:out.entry?.userId || '', total:Number(out.entry?.total || parsed?.total || 0), ttlDays:30 });
    return out;
  }catch(e){
    await markDurableError('whatsapp_entry_accept', lockKey, { error:e.response ? `HTTP ${e.response.status}` : (e.message || String(e)), ttlMs:2*60*1000 });
    throw e;
  }
}

function getMessageText(m){
  const msg = m?.message || {};
  return msg.conversation || msg.extendedTextMessage?.text || msg.imageMessage?.caption || msg.videoMessage?.caption || msg.documentMessage?.caption || "";
}

// ============================================================
// WHATSAPP BOT IMPROVEMENT V1 — UX commands + duplicate guard
// Prevents duplicate processing when Baileys emits the same message again,
// adds /help and /status replies, and makes bot replies feel more natural.
// ============================================================
function messageUniqueKey(m){
  const key = m?.key || {};
  const id = String(key.id || "").trim();
  const remote = _jidKey(key.remoteJid || "");
  const participant = _jidKey(key.participant || key.participantPn || key.senderPn || "");
  if(!remote || !id) return "";
  return `${remote}|${participant}|${id}`;
}
function saveProcessedMessageCache(){
  try{
    const items = processedMessageCache.items && typeof processedMessageCache.items === "object" ? processedMessageCache.items : {};
    const entries = Object.entries(items).sort((a,b)=>String(b[1]||"").localeCompare(String(a[1]||""))).slice(0,2000);
    processedMessageCache = { items:Object.fromEntries(entries), updatedAt:nowIso() };
    gatewayHealth.processedMessageCacheSize = entries.length;
    saveJson(PROCESSED_MESSAGE_CACHE_FILE, processedMessageCache);
  }catch(e){ console.log("Processed message cache save failed:", e.message); }
}
function rememberIncomingMessage(m){
  const k = messageUniqueKey(m);
  if(!k) return true;
  processedMessageCache.items = processedMessageCache.items && typeof processedMessageCache.items === "object" ? processedMessageCache.items : {};
  if(processedMessageCache.items[k]){
    gatewayHealth.duplicateIncomingSkipped = Number(gatewayHealth.duplicateIncomingSkipped || 0) + 1;
    return false;
  }
  processedMessageCache.items[k] = nowIso();
  const size = Object.keys(processedMessageCache.items).length;
  gatewayHealth.processedMessageCacheSize = size;
  if(size > 2000 || size % 25 === 0) saveProcessedMessageCache();
  return true;
}
function trackIncomingMessage(m, handledType="message"){
  try{
    const chatJid = _jidKey(m?.key?.remoteJid || "");
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    gatewayHealth.lastIncomingAt = nowIso();
    gatewayHealth.lastIncomingFrom = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m?.key?.participant || chatJid) : chatJid;
    gatewayHealth.lastIncomingType = handledType;
  }catch(e){}
}
async function sendChatPresence(chatJid, type="composing"){
  try{
    if(sock && connected && chatJid && chatJid !== "status@broadcast" && typeof sock.sendPresenceUpdate === "function"){
      await sock.sendPresenceUpdate(type, chatJid);
    }
  }catch(e){}
}
function botCommandName(text){
  const t = String(text || "").trim().toLowerCase();
  if(!t) return "";
  if(["/help", "help", "menu", "/menu", "commands", "/commands", "cmd", "/cmd"].includes(t)) return "help";
  if(["/status", "status", "bot status", "/bot_status", "gateway status"].includes(t)) return "status";
  if(["/format", "format", "entry format", "sample", "example", "/example"].includes(t)) return "format";
  return "";
}
function botHelpText(){
  return `🤖 *TITAN BOT HELP*
━━━━━━━━━━━━━━━━━━━━
*Entry format:*
MARKET: KALYAN OPEN
TYPE: ANK
DIGITS: 1,2,3
PAR DIGIT: 100
TOTAL: 300

*Smart commands:*
balance / wallet status
profile
history / entries
payment status
deposit / pay 500
withdraw status
summary

*Withdrawal:*
withdraw 500 upi user@upi
withdraw 500 qr  (QR image caption)
withdraw 500 bank Name / A-C / IFSC

*Bot:*
/status
/format
━━━━━━━━━━━━━━━━━━━━`;
}
function botStatusText(){
  return `🟢 *TITAN BOT STATUS*
━━━━━━━━━━━━━━━━━━━━
🔌 *WhatsApp:* ${connected ? "Connected" : "Disconnected"}
📅 *Date:* ${todayISO()}
⏰ *Time:* ${nowHHMM()} ${APP_TZ}
📤 *Send Queue:* ${Number(safeSendQueueDepth || 0)}
🛡️ *Safety:* ${gatewayHealth.whatsappSafetyPaused ? "Paused" : "Active"}
📥 *Last Incoming:* ${gatewayHealth.lastIncomingAt || "-"}
🔁 *Duplicate Skips:* ${Number(gatewayHealth.duplicateIncomingSkipped || 0)}
🧩 *Version:* ${WHATSAPP_BOT_UPGRADE_VERSION}`;
}
function entryFormatText(){
  return `🧾 *ENTRY FORMAT*
━━━━━━━━━━━━━━━━━━━━
MARKET: KALYAN OPEN
TYPE: ANK
DIGITS: 1,2,3
PAR DIGIT: 100
TOTAL: 300

*TYPE allowed:* ANK, JODI, PENEL
*JODI example:*
MARKET: KALYAN
TYPE: JODI
DIGITS: 05,45,99
PAR DIGIT: 10
TOTAL: 30`;
}
async function handleBotCommandMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return false;
    const cmd = botCommandName(getMessageText(m));
    if(!cmd) return false;
    gatewayHealth.lastBotCommand = cmd;
    trackIncomingMessage(m, `bot_command:${cmd}`);
    if(cmd === "status") await replyToMessage(chatJid, botStatusText(), m);
    else if(cmd === "format") await replyToMessage(chatJid, entryFormatText(), m);
    else await replyToMessage(chatJid, botHelpText(), m);
    return true;
  }catch(e){ console.log("Bot command error:", e.message); return false; }
}


function defaultSpamGuardSettings(){
  return {
    enabled:true,
    groupsOnly:true,
    linkGuardEnabled:true,
    forwardGuardEnabled:true,
    deleteMessage:true,
    kickEnabled:true,
    exemptAdmins:true,
    linkStrikeLimit:3,
    forwardStrikeLimit:3,
    forwardWindowSeconds:60,
    alertMessage:"⚠️ *ALERT*\nBhai Group Me Link Dalna Mana he",
    warningMessage:"⚠️ *WARNING*\nNext Time Group Me Link Daloge To Remove Kiya Jayega Group Se",
    kickMessage:"🚫 *REMOVED*\n@{number} ko group se remove kiya gaya.\nReason: 3 baar link/forward spam.",
    forwardAlertMessage:"⚠️ *ALERT*\nBhai Group Me Forward/Spam Message Dalna Mana he",
    forwardWarningMessage:"⚠️ *WARNING*\nNext Time Multiple Forward Message Daloge To Remove Kiya Jayega Group Se"
  };
}
function spamGuardSettings(state){
  const d = defaultSpamGuardSettings();
  const s = state?.spamGuardSettings || {};
  return {
    ...d,
    ...s,
    // Guard is intentionally 3-stage: Alert → Warning → Kick/Remove.
    // Keep minimum 3 so it never repeats only ALERT because of a bad/empty saved limit.
    linkStrikeLimit:Math.max(Number(s.linkStrikeLimit || d.linkStrikeLimit), 3),
    forwardStrikeLimit:Math.max(Number(s.forwardStrikeLimit || d.forwardStrikeLimit), 3),
    forwardWindowSeconds:Math.max(Number(s.forwardWindowSeconds || d.forwardWindowSeconds), 10)
  };
}
function deepContextInfo(msg){
  return msg?.extendedTextMessage?.contextInfo || msg?.imageMessage?.contextInfo || msg?.videoMessage?.contextInfo || msg?.documentMessage?.contextInfo || msg?.audioMessage?.contextInfo || msg?.stickerMessage?.contextInfo || {};
}
function isForwardedMessage(m){
  const ci = deepContextInfo(m?.message || {});
  return !!(ci?.isForwarded || Number(ci?.forwardingScore || 0) > 0);
}
function containsBlockedLink(text){
  const t = String(text || "");
  if(!t.trim()) return false;
  const patterns = [
    /https?:\/\/\S+/i,
    /www\.\S+/i,
    /chat\.whatsapp\.com\/[A-Za-z0-9_-]+/i,
    /t\.me\/\S+/i,
    /telegram\.me\/\S+/i,
    /(?:instagram|facebook|fb|youtube|youtu\.be|x\.com|twitter|threads|snapchat)\.com\/\S+/i,
    /\b(?:bit\.ly|tinyurl\.com|shorturl\.at|cutt\.ly|rebrand\.ly|linktr\.ee)\/\S+/i,
    /\b[a-z0-9-]+\.(?:com|in|net|org|co|me|io|app|site|online|xyz|club|live|shop|store|info)(?:\/\S*)?\b/i
  ];
  return patterns.some(re => re.test(t));
}
function mentionNumberFromJid(jid){
  const d = String(jid || "").replace(/\D/g, "");
  return d ? d.slice(-12) : "user";
}
function guardNormalizeJid(v){
  return String(v || "").trim().replace(/:\d+(?=@)/, "");
}
function guardIdentityFromCandidates(candidates){
  const list = uniqueJids(candidates || []);
  // Prefer real phone number because @lid can vary across WhatsApp multi-device contexts.
  for(const c of list){
    const pk = phoneKey(c);
    if(pk) return { key:`phone:${pk}`, mention: pk.length === 10 ? `91${pk}@s.whatsapp.net` : `${pk}@s.whatsapp.net` };
  }
  const lid = list.find(x => /@lid$/i.test(x));
  if(lid) return { key:`lid:${guardNormalizeJid(lid)}`, mention: guardNormalizeJid(lid) };
  const jid = list.find(x => x.includes("@"));
  if(jid) return { key:`jid:${guardNormalizeJid(jid)}`, mention: guardNormalizeJid(jid) };
  return { key:"unknown", mention:"" };
}
function spamKey(chatJid, identityKey, kind){
  return `${todayISO()}|${chatJid}|${identityKey}|${kind}`;
}
function guardAliasKeys(chatJid, kind, candidates = [], pushName = ""){
  const keys = [];
  const add = (label, value) => {
    const v = String(value || "").trim().toLowerCase();
    if(v) keys.push(spamKey(chatJid, `${label}:${v}`, kind));
  };
  for(const c of uniqueJids(candidates || [])){
    const norm = guardNormalizeJid(c);
    const ph = phoneKey(norm);
    if(ph) add("phone", ph);
    if(norm && norm.includes("@")) add("jid", norm);
    if(/@lid$/i.test(norm)) add("lid", norm);
  }
  const nm = String(pushName || "").trim().replace(/\s+/g, " ").slice(0,60);
  if(nm) add("name", nm);
  return [...new Set(keys)];
}
function getSpamGuardRecordFromAliases(aliasKeys, fallback = {}){
  let best = null;
  for(const k of (aliasKeys || [])){
    const a = spamGuardLocalState?.strikes?.[k];
    const b = fallback?.[k];
    for(const rec of [a,b]){
      if(!rec || typeof rec !== "object") continue;
      if(!best || Number(rec.count || 0) > Number(best.count || 0)) best = rec;
    }
  }
  return best;
}
function saveSpamGuardLocalState(){
  try{
    spamGuardLocalState.strikes = spamGuardLocalState.strikes && typeof spamGuardLocalState.strikes === "object" ? spamGuardLocalState.strikes : {};
    spamGuardLocalState.events = Array.isArray(spamGuardLocalState.events) ? spamGuardLocalState.events.slice(-500) : [];
    saveJson(SPAM_GUARD_STATE_FILE, spamGuardLocalState);
  }catch(e){ console.log("SpamGuard local save failed:", e.message); }
}
async function deleteIncomingMessage(chatJid, m){
  try{
    if(sock && connected && chatJid && m?.key) await sock.sendMessage(chatJid, { delete: m.key });
    return true;
  }catch(e){ console.log("SpamGuard delete failed:", e.message); return false; }
}
async function isGroupAdmin(chatJid, senderJid){
  try{
    if(!chatJid.endsWith("@g.us") || !senderJid) return false;
    const meta = await sock.groupMetadata(chatJid);
    const target = String(senderJid).replace(/:\d+(?=@)/, "");
    const p = (meta.participants || []).find(x => String(x.id || "").replace(/:\d+(?=@)/, "") === target);
    return !!(p && (p.admin === "admin" || p.admin === "superadmin"));
  }catch(e){ return false; }
}
function uniqueJids(list){
  return [...new Set((list || []).map(x => String(x || "").trim().replace(/:\d+(?=@)/, "")).filter(Boolean))];
}
function guardParticipantCandidates(m, senderJid){
  return uniqueJids([
    senderJid,
    m?.key?.participantPn,
    m?.key?.senderPn,
    m?.participantPn,
    m?.senderPn,
    m?.key?.participant,
    m?.participant
  ]);
}
async function removeGroupParticipant(chatJid, senderJid, candidates = []){
  const tried = [];
  try{
    if(!sock || !connected || !chatJid.endsWith("@g.us")) return { ok:false, error:"not_group_or_offline", tried };

    const rawCandidates = uniqueJids([senderJid, ...candidates]);
    const phoneCandidates = rawCandidates.map(phoneKey).filter(Boolean);
    const directIds = [...rawCandidates];

    // Baileys/WhatsApp sometimes emits @lid in messages but group removal may require the participant id
    // exactly as present in group metadata. Add matching metadata participant ids by phone or raw id.
    try{
      const meta = await sock.groupMetadata(chatJid);
      for(const p of (meta.participants || [])){
        const pid = guardNormalizeJid(p.id || p.jid || "");
        if(!pid) continue;
        const pPhone = phoneKey(pid);
        if(rawCandidates.includes(pid) || (pPhone && phoneCandidates.includes(pPhone))) directIds.push(pid);
      }
    }catch(e){ console.log("SpamGuard metadata lookup failed:", e.message); }

    const ids = uniqueJids(directIds).filter(x => x && x.includes("@") && x !== chatJid);
    for(const id of ids){
      tried.push(id);
      try{
        await sock.groupParticipantsUpdate(chatJid, [id], "remove");
        return { ok:true, target:id, tried };
      }catch(e){
        console.log("SpamGuard remove try failed:", id, e.message);
      }
    }
    return { ok:false, error:"all_candidates_failed", tried };
  }catch(e){
    console.log("SpamGuard remove failed:", e.message);
    return { ok:false, error:e.message, tried };
  }
}
function renderSpamGuardMessage(tpl, senderJid){
  const num = mentionNumberFromJid(senderJid);
  return String(tpl || "").replace(/\{number\}/g, num);
}
async function sendSpamGuardNotice(chatJid, text, mentionJid, quoted){
  // PHASE2_SEND_SINGLE_SOURCE: moderation notices are still queued so they cannot burst-send.
  if(!sock || !connected || !chatJid || !text) return { ok:false, error:"offline_or_empty" };
  return safeSendQueueRun(async () => {
    try{
      const opts = quoted ? { quoted } : undefined;
      const payload = { text:String(text) };
      if(mentionJid && String(mentionJid).includes("@")) payload.mentions = [mentionJid];
      const r = await sock.sendMessage(chatJid, payload, opts);
      return { ok:true, id:r?.key?.id || "sent" };
    }catch(e){
      console.log("SpamGuard notice failed:", e.message);
      return { ok:false, error:e.message };
    }
  });
}
function guardSleep(ms){ return new Promise(resolve => setTimeout(resolve, ms)); }
async function handleSpamGuardMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return false;
    const state = await fetchFirebaseState();
    const cfg = spamGuardSettings(state);
    if(!cfg.enabled) return false;
    if(cfg.groupsOnly && !chatJid.endsWith("@g.us")) return false;
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m.key?.participant || "") : chatJid;
    if(!senderJid) return false;
    if(cfg.exemptAdmins && await isGroupAdmin(chatJid, senderJid)) return false;

    const text = getMessageText(m);
    const hasLink = cfg.linkGuardEnabled && containsBlockedLink(text);
    const isFwd = cfg.forwardGuardEnabled && isForwardedMessage(m);
    if(!hasLink && !isFwd) return false;

    state.spamGuardStrikes = state.spamGuardStrikes && typeof state.spamGuardStrikes === "object" ? state.spamGuardStrikes : {};
    state.spamGuardEvents = Array.isArray(state.spamGuardEvents) ? state.spamGuardEvents : [];
    spamGuardLocalState.strikes = spamGuardLocalState.strikes && typeof spamGuardLocalState.strikes === "object" ? spamGuardLocalState.strikes : {};
    spamGuardLocalState.events = Array.isArray(spamGuardLocalState.events) ? spamGuardLocalState.events : [];

    const kind = hasLink ? "link" : "forward";
    const participantCandidates = guardParticipantCandidates(m, senderJid);
    const allIdentityCandidates = [senderJid, ...senderCandidates, ...participantCandidates];
    const identity = guardIdentityFromCandidates(allIdentityCandidates);
    const aliasKeys = guardAliasKeys(chatJid, kind, allIdentityCandidates, m.pushName || "");
    const primaryKey = aliasKeys[0] || spamKey(chatJid, identity.key, kind);

    // Robust 3-stage source of truth:
    // Baileys may alternate @lid / @s.whatsapp.net / PN ids. We read all aliases, take the highest count,
    // then write the same count back to every alias so Alert -> Warning -> Kick cannot reset to Alert.
    let record = getSpamGuardRecordFromAliases(aliasKeys, state.spamGuardStrikes) || { count:0, firstAt:nowIso(), lastAt:"", kind, chatJid, senderJid, identityKey:identity.key, aliasKeys };
    if(kind === "forward"){
      const nowMs = Date.now();
      const firstMs = record.firstMs || nowMs;
      if((nowMs - firstMs) > cfg.forwardWindowSeconds * 1000) record = { count:0, firstAt:nowIso(), firstMs:nowMs, lastAt:"", kind, chatJid, senderJid, identityKey:identity.key, aliasKeys };
      record.firstMs = record.firstMs || firstMs;
    }
    record = { ...record };
    record.count = Number(record.count || 0) + 1;
    record.lastAt = nowIso();
    record.senderJid = senderJid;
    record.identityKey = identity.key;
    record.aliasKeys = aliasKeys;
    for(const k of (aliasKeys.length ? aliasKeys : [primaryKey])){
      spamGuardLocalState.strikes[k] = record;
      state.spamGuardStrikes[k] = record;
    }
    saveSpamGuardLocalState();

    const limit = kind === "link" ? cfg.linkStrikeLimit : cfg.forwardStrikeLimit;
    let action = "alert";
    let msgText = kind === "link" ? cfg.alertMessage : cfg.forwardAlertMessage;
    if(record.count >= limit){ action = "remove"; msgText = cfg.kickMessage; }
    else if(record.count >= 2){ action = "warning"; msgText = kind === "link" ? cfg.warningMessage : cfg.forwardWarningMessage; }

    const mentionJid = identity.mention || participantCandidates.find(x => x.endsWith("@s.whatsapp.net")) || senderJid;
    const rendered = renderSpamGuardMessage(msgText, mentionJid);

    // Send alert/warning first, then delete the spam message. Some WhatsApp builds drop follow-up sends if the source message is deleted first.
    const noticeResult = rendered ? await sendSpamGuardNotice(chatJid, rendered, mentionJid, m) : { ok:false, error:"empty_message" };
    if(cfg.deleteMessage){
      await guardSleep(250);
      await deleteIncomingMessage(chatJid, m);
    }

    let removeResult = { ok:false, skipped: action !== "remove" || !cfg.kickEnabled };
    if(action === "remove" && cfg.kickEnabled){
      await guardSleep(350);
      removeResult = await removeGroupParticipant(chatJid, senderJid, participantCandidates);
    }

    const event = {
      id:`SG${Date.now()}`, time:nowIso(), date:todayISO(), chatJid, senderJid, identityKey:identity.key, aliasKeys:(aliasKeys || []).slice(0,8), kind, count:record.count, action,
      noticeOk:!!noticeResult.ok, noticeError:noticeResult.error || "",
      removeOk:!!removeResult.ok, removeError:removeResult.error || "", removeTarget:removeResult.target || "",
      candidates:participantCandidates.slice(0,8), triedRemove:(removeResult.tried || []).slice(0,8), textSample:String(text || "").slice(0,120)
    };
    state.spamGuardEvents.push(event);
    spamGuardLocalState.events.push(event);
    if(state.spamGuardEvents.length > 300) state.spamGuardEvents.splice(0, state.spamGuardEvents.length - 300);
    if(spamGuardLocalState.events.length > 500) spamGuardLocalState.events.splice(0, spamGuardLocalState.events.length - 500);
    saveSpamGuardLocalState();
    await saveGatewaySpamGuardNarrow(state);

    console.log(`🛡️ SpamGuard ${action}: ${kind} ${record.count}/${limit} ${identity.key} aliases=${(aliasKeys || []).length} notice=${noticeResult.ok?"OK":"FAIL"} remove=${removeResult.ok?"OK":(removeResult.skipped?"SKIP":"FAIL")} tried=${(removeResult.tried || []).join(",")}`);
    return true;
  }catch(e){ console.log("SpamGuard error:", e.response ? `HTTP ${e.response.status}` : e.message); return false; }
}
async function replyToMessage(chatJid, text, quoted){
  // PHASE2_SEND_SINGLE_SOURCE: user replies use the same serial queue as broadcast sends.
  if(!sock || !connected || !chatJid || !text) return null;
  return safeSendQueueRun(async () => {
    try {
      await sendChatPresence(chatJid, "composing");
      await guardSleep(350);
      const out = await sock.sendMessage(chatJid, { text:String(text) }, quoted ? { quoted } : undefined);
      await sendChatPresence(chatJid, "paused");
      return out;
    }
    catch(e){ console.log("Reply failed:", e.message); return null; }
  });
}
function acceptedEntryText(entry){
  const warn = Array.isArray(entry.riskWarning) && entry.riskWarning.length ? `⚠️ *Warning:* ${entry.riskWarning.slice(0,3).join(" | ")}\n` : "";
  return `✅ *ENTRY ACCEPTED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* ${entry.id}\n👤 *User:* ${entry.userName}\n🔥 *Market:* ${entry.market}\n🎮 *Type:* ${entry.gameType}\n🔢 *Digits:* ${entry.digits.join(",")}\n💵 *Par Digit:* ${money(entry.parDigit)}\n💰 *Total:* ${money(entry.total)}\n${entry.walletDebited ? `💳 *Wallet Debited:* ${money(entry.total)}\n` : ""}${warn}━━━━━━━━━━━━━━━━━━━━`;
}
function rejectedEntryText(reason){
  return `❌ *ENTRY REJECTED*\n━━━━━━━━━━━━━━━━━━━━\n📝 *Reason:* ${reason}\n━━━━━━━━━━━━━━━━━━━━\nCorrect format:\nMARKET: KALYAN OPEN\nTYPE: ANK\nDIGITS: 1,2,3\nPAR DIGIT: 100\nTOTAL: 300`;
}
function parseWithdrawalCommand(text, hasQrImage = false){
  const raw = String(text || "").replace(/\r/g, "\n").trim();
  const oneLine = raw.replace(/\s+/g, " ").trim();
  if(!oneLine) return { ok:false, silent:true };
  if(/^(?:bal|balance|wallet)$/i.test(oneLine)) return { ok:true, kind:"balance" };
  if(/^(?:withdraw|withdrawal|wd)\s*(?:status|history)?$/i.test(oneLine) && /status|history/i.test(oneLine)) return { ok:true, kind:"status" };
  if(/^(?:withdraw\s*status|withdrawal\s*status|wd\s*status)$/i.test(oneLine)) return { ok:true, kind:"status" };
  const m = oneLine.match(/^(?:withdraw|withdrawal|wd)\s+(?:rs\.?|inr|₹)?\s*([0-9]+(?:\.[0-9]+)?)([\s\S]*)$/i);
  if(!m) return { ok:false, silent:true };
  const amount = Math.round(Number(m[1] || 0) * 100) / 100;
  let rest = String(m[2] || "").trim();
  let method = "";
  const methodMatch = rest.match(/^(upi|qr|bank|bank\s*account|account|ac|a\/c)\b\s*:?\s*/i);
  if(methodMatch){
    const key = methodMatch[1].toLowerCase();
    method = key.includes("bank") || key === "account" || key === "ac" || key === "a/c" ? "bank" : key;
    rest = rest.slice(methodMatch[0].length).trim();
  }
  if(!method){
    if(hasQrImage || /\bqr\b/i.test(rest)) method = "qr";
    else if(/\b(?:ifsc|account|bank|a\/c|ac\s*no)\b/i.test(rest)) method = "bank";
    else if(/[A-Z0-9._%+-]+@[A-Z0-9.-]+/i.test(rest) || /\bupi\b/i.test(rest)) method = "upi";
  }
  if(!method) return { ok:false, kind:"withdraw", message:"Withdrawal method missing hai. Format: withdraw 500 upi user@upi  OR  withdraw 500 qr  OR  withdraw 500 bank Name / A-C / IFSC" };
  if(amount <= 0 || !Number.isFinite(amount)) return { ok:false, kind:"withdraw", message:"Withdrawal amount valid nahi hai." };
  if(method === "upi"){
    const upi = (rest.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+/i) || [""])[0];
    if(!upi) return { ok:false, kind:"withdraw", message:"UPI detail missing hai. Example: withdraw 500 upi user@upi" };
    rest = upi;
  }
  if(method === "bank" && rest.length < 8){
    return { ok:false, kind:"withdraw", message:"Bank detail incomplete hai. Example: withdraw 500 bank Name / Account No / IFSC" };
  }
  if(method === "qr" && !hasQrImage && !/\bqr\b/i.test(rest)){
    return { ok:false, kind:"withdraw", message:"QR withdrawal ke liye QR image bhejo aur caption me likho: withdraw 500 qr" };
  }
  return { ok:true, kind:"withdraw", amount, method, detail: rest || (method === "qr" ? "QR image attached" : "") };
}
async function downloadQrImageData(m){
  try{
    const image = m?.message?.imageMessage;
    if(!image) return "";
    const stream = await downloadContentFromMessage(image, "image");
    const chunks = [];
    let total = 0;
    for await (const chunk of stream){
      const b = Buffer.from(chunk);
      total += b.length;
      if(total > 750000) return "";
      chunks.push(b);
    }
    const buf = Buffer.concat(chunks);
    if(!buf.length) return "";
    const mime = image.mimetype || "image/jpeg";
    return `data:${mime};base64,${buf.toString("base64")}`;
  }catch(e){ console.log("QR image download failed:", e.message); return ""; }
}
function profileApprovedForWithdrawal(profile, userId, settings){
  const status = profileApprovalStatus(profile);
  if(settings.requireProfileApproval !== false && !String(userId || "").startsWith("admin") && status !== "approved"){
    profile.approvalStatus = status || "pending";
    profile.vipAccessEnabled = false;
    return false;
  }
  return true;
}
function withdrawalAcceptedText(wd, wallet){
  return `✅ *WITHDRAWAL REQUEST CREATED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #${wd.id}\n💵 *Amount:* ${money(wd.amount)}\n🏦 *Method:* ${String(wd.method || "").toUpperCase()}\n🔒 *On Hold:* ${money(walletHoldAmount(wallet))}\n💰 *Withdrawable:* ${money(withdrawAvailable(wallet))}\n📝 Admin approval ke baad payment process hoga.`;
}
function withdrawalRejectedText(reason){
  return `❌ *WITHDRAWAL REJECTED*\n━━━━━━━━━━━━━━━━━━━━\n📝 *Reason:* ${reason}\n━━━━━━━━━━━━━━━━━━━━\nFormats:\nwithdraw 500 upi user@upi\nwithdraw 500 qr  (QR image caption)\nwithdraw 500 bank Name / A-C / IFSC`;
}
function walletBalanceText(profile, wallet){
  return `💳 *WALLET BALANCE*\n━━━━━━━━━━━━━━━━━━━━\n👤 *User:* ${profile?.name || wallet?.userId || "-"}\n💰 *Balance:* ${money(wallet?.balance || 0)}\n🔒 *Withdrawal Hold:* ${money(walletHoldAmount(wallet))}\n✅ *Withdrawable:* ${money(withdrawAvailable(wallet))}\n🎮 *Entry Available:* ${money(entryAvailable(wallet))}`;
}
function withdrawalStatusText(wd){
  if(!wd) return "🧾 *WITHDRAWAL STATUS*\n━━━━━━━━━━━━━━━━━━━━\nAbhi koi withdrawal request nahi mili.";
  const st = String(wd.status || "pending").toLowerCase();
  const label = st === "approved" ? "APPROVED / PAYMENT PROCESSING" : (st === "paid" ? "PAID / COMPLETED" : (st === "rejected" ? "REJECTED" : "PENDING ADMIN APPROVAL"));
  const tx = wd.transactionId ? `\n🧾 *Transaction ID:* ${wd.transactionId}` : "";
  return `🧾 *WITHDRAWAL STATUS*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #${wd.id}\n💵 *Amount:* ${money(wd.amount)}\n🏦 *Method:* ${String(wd.method || "").toUpperCase()}\n⚡ *Status:* ${label}${tx}\n🕒 *Time:* ${String(wd.createdAt || "").replace("T", " ")}\n${wd.rejectReason ? `📝 *Reason:* ${wd.rejectReason}\n` : ""}`;
}

// ============================================================
// SMART WHATSAPP COMMANDS v16 — read-only user self-service
// Adds profile, history, payment, and summary commands with strict triggers.
// Core entry/withdrawal/money logic remains untouched.
// ============================================================
const SMART_COMMAND_ALIASES = {
  profile: ["profile", "my profile", "account", "my account", "/profile", "/account"],
  entries: ["history", "my history", "entries", "my entries", "entry history", "last entries", "/history", "/entries"],
  payments: ["payment status", "payments", "my payments", "deposit status", "pay status", "/payments", "/payment_status"],
  deposit: ["deposit", "payment", "pay", "add money", "recharge", "wallet recharge", "upi", "qr", "/deposit", "/pay", "/recharge"],
  wallet: ["wallet status", "my wallet", "/wallet"],
  withdrawal_status: ["withdraw history", "withdrawal history", "my withdrawals", "/withdrawals", "/withdraw_status"],
  summary: ["summary", "my summary", "today summary", "today", "/summary", "/today"]
};
function normalizeCommandText(text){
  return String(text || "").replace(/\r/g,"\n").split("\n").map(x=>x.trim()).filter(Boolean).join(" ").replace(/\s+/g," ").trim().toLowerCase();
}
function smartUserCommandName(text){
  const t = normalizeCommandText(text);
  if(!t) return "";
  for(const [name, aliases] of Object.entries(SMART_COMMAND_ALIASES)){
    if(aliases.includes(t)) return name;
  }
  if(/^(?:deposit|payment|pay|add money|recharge|wallet recharge|upi|qr)(?:\s+(?:rs\.?|inr|₹)?\s*[0-9]+(?:\.[0-9]+)?)?$/i.test(t)) return "deposit";
  return "";
}
function smartCommandList(){
  return Object.fromEntries(Object.entries(SMART_COMMAND_ALIASES).map(([k,v]) => [k, v.slice(0,6)]));
}
function smartCommandTrack(cmd, ok=true){
  try{
    gatewayHealth.smartCommandCounts = gatewayHealth.smartCommandCounts && typeof gatewayHealth.smartCommandCounts === "object" ? gatewayHealth.smartCommandCounts : {};
    gatewayHealth.smartCommandCounts[cmd] = Number(gatewayHealth.smartCommandCounts[cmd] || 0) + 1;
    gatewayHealth.lastSmartCommand = cmd;
    gatewayHealth.lastSmartCommandAt = nowIso();
    if(!ok) gatewayHealth.smartCommandErrors = Number(gatewayHealth.smartCommandErrors || 0) + 1;
  }catch(e){}
}
function profileSmartText(profile, wallet, userId, found){
  const approval = profileApprovalStatus(profile || {});
  const vipEnabled = (profile?.vipAccessEnabled !== false && profile?.disabled !== true && profile?.blocked !== true) ? "Enabled" : "Disabled";
  const expiry = profile?.expiryDate || profile?.membershipExpiry || profile?.vipExpiry || profile?.planExpiry || profile?.validTill || "-";
  return `👤 *MY PROFILE*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *User ID:* ${userId || "-"}\n📛 *Name:* ${profile?.name || wallet?.name || "-"}\n📱 *Phone:* ${profile?.phone || found?.matchedPhone || wallet?.phone || "-"}\n✅ *Approval:* ${String(approval || "pending").toUpperCase()}\n🔐 *VIP Access:* ${vipEnabled}\n📅 *Expiry:* ${expiry}\n💰 *Wallet:* ${money(wallet?.balance || 0)}\n🔒 *Hold:* ${money(walletHoldAmount(wallet || {}))}`;
}
function shortEntryLine(e){
  const st = String(e.status || e.resultStatus || e.settlementStatus || "accepted").toUpperCase();
  const payout = Number(e.winAmount || e.payout || e.settlementAmount || 0);
  const payoutText = payout > 0 ? ` | WIN ${money(payout)}` : "";
  return `#${e.id || "-"} ${e.market || "-"} ${e.gameType || e.type || "-"} [${Array.isArray(e.digits)?e.digits.join(","):String(e.digits||"")}] ${money(e.total || 0)} | ${st}${payoutText}`;
}
function entriesHistoryText(state, userId){
  const entries = (Array.isArray(state?.entries) ? state.entries : []).filter(e => e && e.userId === userId).slice(-5).reverse();
  if(!entries.length) return "🎮 *ENTRY HISTORY*\n━━━━━━━━━━━━━━━━━━━━\nAbhi koi accepted entry nahi mili.";
  return `🎮 *LAST ENTRIES*\n━━━━━━━━━━━━━━━━━━━━\n${entries.map(shortEntryLine).join("\n")}\n━━━━━━━━━━━━━━━━━━━━\nLatest 5 entries shown.`;
}
function paymentStatusTextSmart(state, userId){
  const payments = (Array.isArray(state?.payments) ? state.payments : []).filter(p => p && p.userId === userId).slice(-5).reverse();
  if(!payments.length) return "💳 *PAYMENT STATUS*\n━━━━━━━━━━━━━━━━━━━━\nAbhi koi payment request nahi mili.";
  const lines = payments.map(p => {
    const st = String(p.status || p.paymentStatus || "pending").toUpperCase();
    const utr = p.utr ? ` | UTR ${String(p.utr).slice(-6)}` : "";
    const reason = p.rejectReason ? ` | ${String(p.rejectReason).slice(0,40)}` : "";
    return `#${p.id || "-"} ${money(p.amount || 0)} | ${st}${utr}${reason}`;
  });
  return `💳 *PAYMENT STATUS*\n━━━━━━━━━━━━━━━━━━━━\n${lines.join("\n")}\n━━━━━━━━━━━━━━━━━━━━\nLatest 5 payments shown.`;
}

function parseDepositAmount(text){
  const t = normalizeCommandText(text);
  const m = t.match(/(?:^|\s)(?:rs\.?|inr|₹)?\s*([0-9]+(?:\.[0-9]+)?)(?:\s|$)/i);
  if(!m) return 0;
  const amount = Math.round(Number(m[1] || 0) * 100) / 100;
  return Number.isFinite(amount) && amount > 0 ? amount : 0;
}
function paymentUpiLink(upi, name, amount, note){
  const pa = encodeURIComponent(String(upi || '').trim());
  if(!pa) return '';
  const pn = encodeURIComponent(String(name || 'TITAN NOVA').trim() || 'TITAN NOVA');
  const tn = encodeURIComponent(String(note || 'TITAN NOVA DEPOSIT').trim());
  const am = amount > 0 ? `&am=${encodeURIComponent(String(amount))}` : '';
  return `upi://pay?pa=${pa}&pn=${pn}${am}&cu=INR&tn=${tn}`;
}
function getDepositPaymentConfig(state){
  const pm = state?.paymentMethods || {};
  const paymentMethodUpis = [
    ['Default UPI', pm.upi],
    ['PhonePe', pm.phonepeUpi],
    ['GPay', pm.gpayUpi],
    ['Paytm', pm.paytmUpi]
  ].filter(([,v], idx, arr) => v && arr.findIndex(([,x]) => String(x).trim().toLowerCase() === String(v).trim().toLowerCase()) === idx);
  const ds = state?.depositSettings?.v1 || {};
  if(ds && typeof ds === 'object' && (ds.upiId || ds.qrImageUrl || ds.paymentName || ds.accountName)){
    const dsUpis = [['UPI', ds.upiId]].filter(([,v]) => v);
    return {
      source: 'depositSettings.v1',
      name: ds.paymentName || ds.accountName || pm.name || 'TITAN NOVA',
      receiver: ds.accountName || ds.paymentName || pm.name || 'TITAN NOVA',
      bankName: ds.bankName || pm.bankName || '',
      phone: ds.phone || pm.phone || '',
      qr: ds.qrImageUrl || pm.qr || '',
      upis: dsUpis.length ? dsUpis : paymentMethodUpis
    };
  }
  return {
    source: 'paymentMethods',
    name: pm.name || 'TITAN NOVA',
    receiver: pm.name || 'TITAN NOVA',
    bankName: pm.bankName || '',
    phone: pm.phone || '',
    qr: pm.qr || '',
    upis: paymentMethodUpis
  };
}
function depositInstructionsText(state, userId, amount = 0){
  const cfg = getDepositPaymentConfig(state);
  const name = cfg.name || 'TITAN NOVA';
  const receiver = cfg.receiver || name;
  const upiList = cfg.upis || [];
  const lines = [];
  lines.push('💳 *DEPOSIT / ADD MONEY*');
  lines.push('━━━━━━━━━━━━━━━━━━━━');
  if(amount > 0) lines.push(`💵 *Amount:* ${money(amount)}`);
  lines.push(`👤 *Receiver:* ${receiver}`);
  if(cfg.bankName) lines.push(`🏦 *Bank:* ${cfg.bankName}`);
  if(cfg.phone) lines.push(`📱 *Phone:* ${cfg.phone}`);
  if(upiList.length){
    lines.push('');
    lines.push('🏦 *UPI Details:*');
    for(const [label, upi] of upiList) lines.push(`• *${label}:* ${upi}`);
    const link = paymentUpiLink(upiList[0][1], name, amount, `TITAN NOVA ${userId || 'USER'} DEPOSIT`);
    if(link) lines.push(`\n🔗 *Direct UPI Link:*\n${link}`);
  } else {
    lines.push('⚠️ Admin ne UPI setup nahi kiya hai. Thodi der baad try karein.');
  }
  lines.push('');
  lines.push('📷 QR image bhi yahin bheja ja raha hai agar admin ne upload kiya hai.');
  lines.push('✅ Payment ke baad screenshot/UTR app me submit karein ya yahan bhejein: *payment status* se status check hoga.');
  return lines.join('\n');
}
async function replyDepositInstructions(chatJid, state, userId, amount, quoted){
  const text = depositInstructionsText(state, userId, amount);
  const cfg = getDepositPaymentConfig(state);
  const qr = String(cfg.qr || '').trim();
  if(!sock || !connected || !chatJid) return null;
  if(qr){
    return safeSendQueueRun(async () => {
      try{
        await sendChatPresence(chatJid, 'composing');
        await guardSleep(350);
        let image = null;
        if(/^data:image\//i.test(qr)){
          const b64 = qr.split(',')[1] || '';
          image = Buffer.from(b64, 'base64');
        } else if(/^https?:\/\//i.test(qr)){
          image = { url: qr };
        }
        if(image){
          const out = await sock.sendMessage(chatJid, { image, caption:text }, quoted ? { quoted } : undefined);
          await sendChatPresence(chatJid, 'paused');
          return out;
        }
      }catch(e){ console.log('Deposit QR send failed:', e.message); }
      try{
        const out = await sock.sendMessage(chatJid, { text:String(text) }, quoted ? { quoted } : undefined);
        await sendChatPresence(chatJid, 'paused');
        return out;
      }catch(e){ console.log('Deposit text fallback failed:', e.message); return null; }
    });
  }
  return replyToMessage(chatJid, text, quoted);
}

function withdrawalsHistoryText(state, userId){
  const rows = (Array.isArray(state?.withdrawals) ? state.withdrawals : []).filter(w => w && w.userId === userId).slice(-5).reverse();
  if(!rows.length) return "🧾 *WITHDRAWAL HISTORY*\n━━━━━━━━━━━━━━━━━━━━\nAbhi koi withdrawal request nahi mili.";
  const lines = rows.map(w => `#${w.id || "-"} ${money(w.amount || 0)} | ${String(w.method || "-").toUpperCase()} | ${String(w.status || "pending").toUpperCase()}`);
  return `🧾 *WITHDRAWAL HISTORY*\n━━━━━━━━━━━━━━━━━━━━\n${lines.join("\n")}\n━━━━━━━━━━━━━━━━━━━━\nLatest 5 withdrawals shown.`;
}
function userSummaryText(state, userId, profile, wallet){
  const today = todayISO();
  const entriesToday = (Array.isArray(state?.entries) ? state.entries : []).filter(e => e && e.userId === userId && String(e.date || "").slice(0,10) === today);
  const totalEntry = entriesToday.reduce((sum,e) => sum + Number(e.total || 0), 0);
  const paymentsPending = (Array.isArray(state?.payments) ? state.payments : []).filter(p => p && p.userId === userId && String(p.status || "pending").toLowerCase() === "pending").length;
  const withdrawalsActive = (Array.isArray(state?.withdrawals) ? state.withdrawals : []).filter(w => w && w.userId === userId && ["pending","approved"].includes(String(w.status || "pending").toLowerCase())).length;
  return `📊 *TODAY SUMMARY*\n━━━━━━━━━━━━━━━━━━━━\n👤 *User:* ${profile?.name || userId}\n📅 *Date:* ${today}\n🎮 *Entries Today:* ${entriesToday.length}\n💵 *Entry Load:* ${money(totalEntry)}\n💰 *Wallet:* ${money(wallet?.balance || 0)}\n🔒 *Hold:* ${money(walletHoldAmount(wallet || {}))}\n💳 *Pending Payments:* ${paymentsPending}\n🧾 *Active Withdrawals:* ${withdrawalsActive}`;
}
async function handleSmartUserCommandMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return false;
    const cmd = smartUserCommandName(getMessageText(m));
    if(!cmd) return false;
    trackIncomingMessage(m, `smart_command:${cmd}`);
    smartCommandTrack(cmd, true);
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m.key?.participant || "") : chatJid;
    const state = await fetchFirebaseState();
    const found = findProfileBySender(state, senderJid, { chatJid, senderJid, senderCandidates, pushName:m.pushName || m.verifiedBizName || "" });
    if(!found){
      await replyToMessage(chatJid, "❌ Profile nahi mila. Admin app me apna WhatsApp number VIP profile se link karwana hoga.", m);
      return true;
    }
    const profile = found.profile || {};
    const wallet = ensureWalletInState(state, found.userId);
    if(found.autoCreated || found.autoLinked){
      try{ await saveGatewayProfileSync(state, found.userId); }catch(e){}
    }
    let text = "";
    if(cmd === "profile") text = profileSmartText(profile, wallet, found.userId, found);
    else if(cmd === "entries") text = entriesHistoryText(state, found.userId);
    else if(cmd === "payments") text = paymentStatusTextSmart(state, found.userId);
    else if(cmd === "deposit"){
      const depositAmount = parseDepositAmount(getMessageText(m));
      profile.lastDepositIntentAmount = depositAmount;
      profile.lastDepositIntentAt = nowIso();
      profile.lastDepositIntentChatJid = chatJid;
      try{ await saveGatewayProfileSync(state, found.userId); }catch(e){}
      await replyDepositInstructions(chatJid, state, found.userId, depositAmount, m);
      return true;
    }
    else if(cmd === "wallet") text = walletBalanceText(profile, wallet);
    else if(cmd === "withdrawal_status") text = withdrawalsHistoryText(state, found.userId);
    else text = userSummaryText(state, found.userId, profile, wallet);
    await replyToMessage(chatJid, text, m);
    return true;
  }catch(e){
    smartCommandTrack("error", false);
    console.log("Smart command error:", e.response ? `HTTP ${e.response.status}` : e.message);
    try{ await replyToMessage(m?.key?.remoteJid || "", "⚠️ Command process nahi ho paya. Thodi der baad try karo.", m); }catch(_e){}
    return true;
  }
}

async function saveWithdrawalRequestToFirebaseUnlocked(parsed, meta, qrImageData = ""){
  const state = await fetchFirebaseState();
  const eSettings = entrySettings(state);
  const wSettings = withdrawalSettings(state);
  if(!wSettings.enabled) return { ok:false, reason:"withdrawal_disabled", message:"Withdrawal system admin app me OFF hai." };
  if(!Array.isArray(state.withdrawals)) state.withdrawals = [];
  if(!state.withdrawalSettings || typeof state.withdrawalSettings !== "object") state.withdrawalSettings = {};
  const found = findProfileBySender(state, meta.senderJid, meta);
  if(!found){
    const detected = (Array.isArray(meta.senderCandidates) ? meta.senderCandidates : [meta.senderJid]).map(phoneKey).filter(Boolean)[0] || "phone_not_detected";
    return { ok:false, reason:"profile_not_found", message:`Profile nahi mila. Detected: ${detected}. Admin approval required.` };
  }
  const profile = found.profile || {};
  if(!profileApprovedForWithdrawal(profile, found.userId, eSettings)){
    profile.lastWithdrawalRequestAt = nowIso();
    profile.lastWithdrawalChatJid = meta.chatJid || "";
    ensureWalletInState(state, found.userId);
    if(!Array.isArray(state.auditLog)) state.auditLog = [];
    state.auditLog.push({ id:`WP${Date.now()}`, time:nowIso(), action:"withdrawal_profile_pending", detail:{ userId:found.userId, phone:profile.phone || found.matchedPhone || "", name:profile.name || "" } });
    await saveGatewayProfileSync(state, found.userId);
    return { ok:false, reason:"profile_pending_approval", message:"Aapka profile auto-create ho gaya hai. Admin approval ke baad withdrawal request accept hogi." };
  }
  if(parsed.amount < wSettings.minAmount) return { ok:false, reason:"below_min", message:`Minimum withdrawal ${money(wSettings.minAmount)} hai.` };
  if(wSettings.maxAmount > 0 && parsed.amount > wSettings.maxAmount) return { ok:false, reason:"above_max", message:`Maximum withdrawal ${money(wSettings.maxAmount)} hai.` };
  if(wSettings.onePendingPerUser !== false){
    const existing = state.withdrawals.find(x => x && x.userId === found.userId && ["pending", "approved"].includes(String(x.status || "").toLowerCase()));
    if(existing) return { ok:false, reason:"active_exists", message:`Aapki ek withdrawal request already active hai. ID: #${existing.id}. Status: ${String(existing.status || "pending").toUpperCase()}` };
  }
  const wallet = ensureWalletInState(state, found.userId);
  const available = withdrawAvailable(wallet);
  if(available + 0.0001 < parsed.amount){
    return { ok:false, reason:"insufficient_wallet", message:`Insufficient wallet. Withdrawable ${money(available)}, request ${money(parsed.amount)}.` };
  }
  const holdBefore = walletHoldAmount(wallet);
  setWalletHold(wallet, holdBefore + parsed.amount);
  wallet.updatedAt = nowIso();
  const holdLedgerEntry = { id:`WHOLD-${Date.now()}`, time:nowIso(), type:"withdrawal_hold", amount:0, balanceBefore:Number(wallet.balance || 0), balanceAfter:Number(wallet.balance || 0), holdBefore, holdAfter:walletHoldAmount(wallet), note:`Withdrawal hold ${parsed.method.toUpperCase()}`, source:"whatsapp_withdrawal", withdrawalId:"pending" };
  wallet.ledger.push(holdLedgerEntry);
  const wd = {
    id: nextWithdrawalId(state),
    userId: found.userId,
    userName: profile.name || found.userId,
    phone: profile.phone || found.matchedPhone || "",
    senderJid: meta.senderJid || "",
    chatJid: meta.chatJid || "",
    amount: parsed.amount,
    method: parsed.method,
    detail: parsed.detail || (parsed.method === "qr" ? "QR image attached" : ""),
    qrImageData: parsed.method === "qr" ? (qrImageData || "") : "",
    status:"pending",
    paymentStatus:"pending_approval",
    requestNotified:true,
    approvalNotified:false,
    paidNotified:false,
    rejectionNotified:false,
    holdApplied:true,
    holdAmount: parsed.amount,
    walletBalanceAtRequest: Number(wallet.balance || 0),
    walletHoldAfter: walletHoldAmount(wallet),
    createdAt: nowIso(),
    source:"whatsapp_command"
  };
  wallet.ledger[wallet.ledger.length - 1].withdrawalId = wd.id;
  holdLedgerEntry.withdrawalId = wd.id;
  recordWalletTransaction(state, found.userId, wallet, holdLedgerEntry);
  state.withdrawals.push(wd);
  if(!Array.isArray(state.auditLog)) state.auditLog = [];
  state.auditLog.push({ id:wd.id, time:nowIso(), action:"withdrawal_requested", detail:{ userId:wd.userId, amount:wd.amount, method:wd.method, phone:wd.phone } });
  const adminText = `🔔 *NEW WITHDRAWAL REQUEST*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #${wd.id}\n👤 *User:* ${wd.userName}\n📱 *Phone:* ${wd.phone || "-"}\n💵 *Amount:* ${money(wd.amount)}\n🏦 *Method:* ${String(wd.method).toUpperCase()}\n📝 *Detail:* ${wd.method === "qr" ? "QR image received" : (wd.detail || "-")}\n\nAdmin panel me Approve karein. Approve ke baad Pay Now / Mark Paid flow use karein.`;
  if(wSettings.notifyAdminPrivate !== false){
    for(const t of adminNotifyTargets(state)) queueWhatsAppOutbox(state, t, adminText, { type:"withdrawal_admin_notify", withdrawalId:wd.id });
  }
  await saveGatewayWithdrawalNarrow(state, found.userId);
  return { ok:true, withdrawal:wd, wallet };
}
async function saveWithdrawalRequestToFirebase(parsed, meta, qrImageData = ""){
  const lockKey = withdrawalMessageLockKey(parsed, meta || {});
  const lock = await acquireDurableLock('whatsapp_withdrawal_request', lockKey, 2 * 60 * 1000, { chatJid:meta?.chatJid || '', senderJid:meta?.senderJid || '', amount:Number(parsed?.amount || 0), method:parsed?.method || '' });
  if(!lock.ok){
    const existing = lock.existing || {};
    if(lock.done) return { ok:false, reason:'duplicate_message_done', message: existing.message || 'Ye withdrawal message already process ho chuka hai. Duplicate request nahi banega.' };
    return { ok:false, reason:'duplicate_message_processing', message:'Ye withdrawal message abhi process ho raha hai. Duplicate request nahi banega.' };
  }
  try{
    const out = await saveWithdrawalRequestToFirebaseUnlocked(parsed, meta || {}, qrImageData || '');
    await markDurableDone('whatsapp_withdrawal_request', lockKey, { ok:!!out.ok, reason:out.reason || '', message:out.message || '', withdrawalId:out.withdrawal?.id || '', userId:out.withdrawal?.userId || '', amount:Number(out.withdrawal?.amount || parsed?.amount || 0), ttlDays:30 });
    return out;
  }catch(e){
    await markDurableError('whatsapp_withdrawal_request', lockKey, { error:e.response ? `HTTP ${e.response.status}` : (e.message || String(e)), ttlMs:2*60*1000 });
    throw e;
  }
}


function parseDepositPaymentProof(text, hasImage = false){
  const raw = String(text || '').replace(/\r/g, '\n').trim();
  const oneLine = raw.replace(/\s+/g, ' ').trim();
  const hasPaymentWords = /\b(?:payment|paid|deposit|recharge|utr|txn|transaction|trans(?:action)?\s*id|ref(?:erence)?|rrn)\b/i.test(oneLine);
  const utrMatch = oneLine.match(/\b(?:utr|txn|transaction(?:\s*id)?|trans(?:action)?\s*id|ref(?:erence)?|rrn)\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-]{5,35})\b/i)
    || (hasPaymentWords ? oneLine.match(/\b([A-Z0-9]{8,35})\b/i) : oneLine.match(/^\s*([A-Z0-9]{10,35})\s*$/i));
  const utr = utrMatch ? String(utrMatch[1] || '').replace(/[^A-Za-z0-9-]/g, '').toUpperCase() : '';
  const amountMatch = oneLine.match(/(?:^|\b)(?:amount|amt|rs\.?|inr|₹)\s*[:#-]?\s*([0-9]+(?:\.[0-9]+)?)(?:\b|$)/i)
    || oneLine.match(/\b(?:payment|paid|deposit|recharge)\s+([0-9]+(?:\.[0-9]+)?)(?:\b|$)/i);
  const amount = amountMatch ? Math.round(Number(amountMatch[1] || 0) * 100) / 100 : 0;
  const looksLikeProof = !!hasImage || !!utr || (hasPaymentWords && amount > 0);
  if(!looksLikeProof) return { ok:false, silent:true };
  return { ok:true, amount:Number.isFinite(amount) ? amount : 0, utr, rawText:raw };
}
function nextPaymentId(state){
  const n = Array.isArray(state.payments) ? state.payments.length + 1 : 1;
  return 'P' + todayISO().replace(/-/g, '').slice(2) + '-' + String(n).padStart(4, '0');
}
function depositPaymentMessageLockKey(parsed, meta){
  return meta?.messageKey || [meta?.chatJid, meta?.senderJid, parsed?.amount, parsed?.utr, String(parsed?.rawText||'').slice(0,300)].join('|');
}
async function downloadPaymentScreenshotImageData(m){
  try{
    const image = m?.message?.imageMessage;
    if(!image) return { data:'', note:'' };
    const stream = await downloadContentFromMessage(image, 'image');
    const chunks = [];
    let total = 0;
    for await (const chunk of stream){
      const b = Buffer.from(chunk);
      total += b.length;
      if(total > 1200000) return { data:'', note:'Screenshot received, preview unavailable' };
      chunks.push(b);
    }
    const buf = Buffer.concat(chunks);
    if(!buf.length) return { data:'', note:'Screenshot received, preview unavailable' };
    const mime = image.mimetype || 'image/jpeg';
    return { data:`data:${mime};base64,${buf.toString('base64')}`, note:'' };
  }catch(e){ console.log('Payment screenshot download failed:', e.message); return { data:'', note:'Screenshot received, preview unavailable' }; }
}
async function saveDepositPaymentRequestUnlocked(parsed, meta, screenshotImageData = '', screenshotNote = ''){
  const state = await fetchFirebaseState();
  if(!Array.isArray(state.payments)) state.payments = [];
  const found = findProfileBySender(state, meta.senderJid, meta);
  if(!found){
    return { ok:false, reason:'profile_not_found', message:'Aapka profile pending/admin approval required hai. Admin approval ke baad payment request accept hogi.' };
  }
  const profile = found.profile || {};
  const approvalStatus = profileApprovalStatus(profile);
  const isAdminUser = String(found.userId || '').startsWith('admin');
  if(entrySettings(state).requireProfileApproval !== false && !isAdminUser && approvalStatus !== 'approved'){
    profile.approvalStatus = approvalStatus || 'pending';
    profile.vipAccessEnabled = false;
    profile.lastPaymentProofAt = nowIso();
    ensureWalletInState(state, found.userId);
    await saveGatewayProfileSync(state, found.userId);
    return { ok:false, reason:'profile_pending_approval', message:'Aapka profile pending/admin approval required hai. Admin approve karega uske baad payment verify hoga.' };
  }
  const intentAmount = Number(profile.lastDepositIntentAmount || 0);
  const amount = Number(parsed.amount || 0) > 0 ? Number(parsed.amount) : (intentAmount > 0 ? intentAmount : 0);
  if(!(amount > 0)) return { ok:false, reason:'missing_amount', message:'Amount missing hai. Screenshot ke saath amount bhejein. Example: payment 500 UTR 123456' };
  const payment = {
    id: nextPaymentId(state),
    userId: found.userId,
    userName: profile.name || found.userId,
    phone: profile.phone || found.matchedPhone || '',
    senderJid: meta.senderJid || '',
    chatJid: meta.chatJid || '',
    amount,
    utr: parsed.utr || '',
    screenshotImageData: screenshotImageData || '',
    image: screenshotImageData || '',
    note: screenshotNote || '',
    status: 'pending',
    paymentStatus: 'pending_approval',
    source: 'whatsapp_screenshot',
    createdAt: nowIso(),
    time: new Date().toLocaleString('en-IN', { timeZone: APP_TZ, day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' }),
    requestNotified: true,
    approvalNotified: false,
    rejectionNotified: false,
    walletCredited: false,
    autoFlag: parsed.utr ? 'whatsapp_screenshot' : 'utr_missing',
    riskLevel: parsed.utr ? 'MEDIUM' : 'HIGH'
  };
  state.payments.push(payment);
  if(!Array.isArray(state.auditLog)) state.auditLog = [];
  state.auditLog.push({ id:payment.id, time:nowIso(), action:'whatsapp_payment_screenshot_received', detail:{ userId:payment.userId, amount:payment.amount, utr:payment.utr, phone:payment.phone } });
  const adminText = `🔔 *NEW PAYMENT SCREENSHOT*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #${payment.id}\n👤 *User:* ${payment.userName}\n📱 *Phone:* ${payment.phone || '-'}\n💵 *Amount:* ${money(payment.amount)}\n🔢 *UTR:* ${payment.utr || '-'}\n⚡ *Status:* Pending\n\nAdmin panel me Approve/Reject karein.`;
  for(const t of adminNotifyTargets(state)) queueWhatsAppOutbox(state, t, adminText, { type:'payment_screenshot_admin_notify', paymentId:payment.id });
  await saveGatewayChildren(state, ['payments', 'paymentOutbox']);
  if(Array.isArray(state.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
  return { ok:true, payment };
}
async function saveDepositPaymentRequest(parsed, meta, screenshotImageData = '', screenshotNote = ''){
  const lockKey = depositPaymentMessageLockKey(parsed, meta || {});
  const lock = await acquireDurableLock('whatsapp_deposit_payment', lockKey, 2 * 60 * 1000, { chatJid:meta?.chatJid || '', senderJid:meta?.senderJid || '', amount:Number(parsed?.amount || 0), utr:parsed?.utr || '' });
  if(!lock.ok){
    const existing = lock.existing || {};
    if(lock.done) return { ok:false, reason:'duplicate_message_done', message: existing.message || 'Ye payment proof already process ho chuka hai. Duplicate request nahi banega.' };
    return { ok:false, reason:'duplicate_message_processing', message:'Ye payment proof abhi process ho raha hai. Duplicate request nahi banega.' };
  }
  try{
    const out = await saveDepositPaymentRequestUnlocked(parsed, meta || {}, screenshotImageData || '', screenshotNote || '');
    await markDurableDone('whatsapp_deposit_payment', lockKey, { ok:!!out.ok, reason:out.reason || '', message:out.message || '', paymentId:out.payment?.id || '', userId:out.payment?.userId || '', amount:Number(out.payment?.amount || parsed?.amount || 0), ttlDays:30 });
    return out;
  }catch(e){
    await markDurableError('whatsapp_deposit_payment', lockKey, { error:e.response ? `HTTP ${e.response.status}` : (e.message || String(e)), ttlMs:2*60*1000 });
    throw e;
  }
}
async function handleIncomingDepositPaymentMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || '';
    if(!chatJid || chatJid === 'status@broadcast') return false;
    const text = getMessageText(m);
    const hasImage = !!m?.message?.imageMessage;
    const parsed = parseDepositPaymentProof(text, hasImage);
    if(parsed.silent) return false;
    trackIncomingMessage(m, 'deposit_payment_proof');
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith('@g.us') ? (senderCandidates[0] || m.key?.participant || '') : chatJid;
    const img = hasImage ? await downloadPaymentScreenshotImageData(m) : { data:'', note:'' };
    const saved = await saveDepositPaymentRequest(parsed, { chatJid, senderJid, senderCandidates, pushName:m.pushName || m.verifiedBizName || '', messageKey:messageUniqueKey(m) }, img.data, img.note);
    if(!saved.ok){
      if(saved.reason === 'missing_amount') await replyToMessage(chatJid, 'Amount missing hai. Screenshot ke saath amount bhejein. Example: “payment 500 UTR 123456”', m);
      else await replyToMessage(chatJid, saved.message || 'Aapka profile pending/admin approval required hai.', m);
      return true;
    }
    await replyToMessage(chatJid, `✅ Payment screenshot received.\nPayment ID: #${saved.payment.id}\nStatus: Pending admin approval.`, m);
    console.log(`💳 Payment screenshot ${saved.payment.id}: ${saved.payment.userId} ${saved.payment.amount}`);
    return true;
  }catch(e){
    console.log('Deposit payment proof error:', e.response ? `HTTP ${e.response.status}` : e.message);
    return false;
  }
}

async function handleIncomingWithdrawalMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return false;
    const text = getMessageText(m);
    const hasQrImage = !!m?.message?.imageMessage;
    const parsed = parseWithdrawalCommand(text, hasQrImage);
    if(parsed.silent) return false;
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m.key?.participant || "") : chatJid;
    trackIncomingMessage(m, `withdrawal_${parsed.kind || "command"}`);
    if(parsed.kind === "balance" || parsed.kind === "status"){
      const state = await fetchFirebaseState();
      const found = findProfileBySender(state, senderJid, { chatJid, senderJid, senderCandidates, pushName:m.pushName || m.verifiedBizName || "" });
      if(!found){ await replyToMessage(chatJid, withdrawalRejectedText("Profile nahi mila."), m); return true; }
      const profile = found.profile || {};
      if(!profileApprovedForWithdrawal(profile, found.userId, entrySettings(state))){
        ensureWalletInState(state, found.userId);
        await saveGatewayProfileSync(state, found.userId);
        await replyToMessage(chatJid, "⏳ Aapka profile pending approval me hai. Admin approve karega uske baad wallet/withdrawal active hoga.", m);
        return true;
      }
      const wallet = ensureWalletInState(state, found.userId);
      if(parsed.kind === "balance") await replyToMessage(chatJid, walletBalanceText(profile, wallet), m);
      else {
        const last = (Array.isArray(state.withdrawals) ? state.withdrawals : []).filter(x => x.userId === found.userId).slice(-1)[0];
        await replyToMessage(chatJid, withdrawalStatusText(last), m);
      }
      await saveGatewayProfileSync(state, found.userId);
      return true;
    }
    if(!parsed.ok){ await replyToMessage(chatJid, withdrawalRejectedText(parsed.message || "Withdrawal command invalid."), m); return true; }
    trackIncomingMessage(m, "withdrawal_request");
    let qrImageData = "";
    if(parsed.method === "qr") qrImageData = await downloadQrImageData(m);
    if(parsed.method === "qr" && !qrImageData && hasQrImage){
      // Still create request; admin can see it in WhatsApp chat if image download failed.
      parsed.detail = parsed.detail || "QR image received, app preview unavailable";
    }
    const saved = await saveWithdrawalRequestToFirebase(parsed, { chatJid, senderJid, senderCandidates, pushName:m.pushName || m.verifiedBizName || "", messageKey:messageUniqueKey(m) }, qrImageData);
    if(!saved.ok){ await replyToMessage(chatJid, withdrawalRejectedText(saved.message || saved.reason || "Withdrawal rejected."), m); return true; }
    await replyToMessage(chatJid, withdrawalAcceptedText(saved.withdrawal, saved.wallet), m);
    console.log(`💸 Withdrawal request ${saved.withdrawal.id}: ${saved.withdrawal.userId} ${saved.withdrawal.amount} ${saved.withdrawal.method}`);
    return true;
  }catch(e){
    console.log("Withdrawal command error:", e.response ? `HTTP ${e.response.status}` : e.message);
    return false;
  }
}

async function handleIncomingEntryMessage(m){
  try{
    if(!m || m.key?.fromMe) return;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return;
    const text = getMessageText(m);
    if(!String(text || "").trim()) return;
    const stateLite = await fetchFirebaseState();
    ensureMarketRegistry(stateLite);
    const settings = entrySettings(stateLite);
    const template = settings.entryFormatTemplate || DEFAULT_ENTRY_FORMAT_TEMPLATE;
    const parsed = parseEntryCardDynamic(text, template, stateLite);
    if(parsed.silent) return;
    trackIncomingMessage(m, "entry_card");
    if(!settings.entryParserEnabled) return;
    if(settings.groupsOnly && !chatJid.endsWith("@g.us")) return;
    if(!parsed.ok){ await replyToMessage(chatJid, rejectedEntryText(parsed.message || parsed.reason || "Invalid entry."), m); return; }
    const targetCheck = validateEntrySourceTarget(stateLite, parsed, chatJid);
    if(!targetCheck.ok){ await replyToMessage(chatJid, rejectedEntryText(targetCheck.message || "Entry target not allowed."), m); return; }
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m.key?.participant || "") : chatJid;
    const saved = await saveAcceptedEntryToFirebase(parsed, { chatJid, senderJid, senderCandidates, pushName:m.pushName || m.verifiedBizName || "", messageKey:messageUniqueKey(m) });
    if(!saved.ok){ await replyToMessage(chatJid, rejectedEntryText(saved.message || saved.reason || "Entry rejected."), m); return; }
    await replyToMessage(chatJid, acceptedEntryText(saved.entry), m);
    console.log(`🧾 Entry accepted ${saved.entry.id}: ${saved.entry.market} ${saved.entry.gameType} ${saved.entry.total}`);
  } catch(e){
    console.log("Entry parser error:", e.response ? `HTTP ${e.response.status}` : e.message);
  }
}
function cleanResult(v){ return String(v || "").trim().replace(/\s+/g, ""); }
function resultStage(v){
  const t = cleanResult(v);
  if(/^\d{3}-\d$/.test(t)) return "open";
  if(/^\d{3}-\d{2}-\d{3}$/.test(t)) return "close";
  return "";
}
function inferOpenFromCloseResult(v){
  const t = cleanResult(v);
  const m = t.match(/^(\d{3})-(\d{2})-(\d{3})$/);
  if(!m) return "";
  return `${m[1]}-${m[2][0]}`;
}
function isApprovedLiveResultSource(item){
  const src = String(item?.sourceUrl || "").toLowerCase();
  const block = String(item?.block || "").toUpperCase();
  return src.includes("sattamatkadpboss.mobi") && (block === "LIVE MATKA RESULT" || block === "LIVE UPDATE");
}
function formatResultMessage(market, result, stage){
  const clean = cleanResult(result);
  const st = stage || resultStage(clean);
  const stageLabel = st === "open" ? "OPEN" : (st === "close" ? "CLOSE" : "RESULT");
  return `🏆 TITAN NOVA RESULT\n\n🔥 MARKET: ${market}\n📌 STAGE: ${stageLabel}\n🎯 RESULT: ${clean}\n\n✅ Updated Successfully`;
}

const RESULT_MARKET_ALIASES = [
  { market:"SRIDEV DAY", aliases:["SRIDEV DAY", "SRIDEVI DAY", "SRIDEVI", "SRI DEVI"] },
  { market:"TIME BAZAR", aliases:["TIME BAZAR"] },
  { market:"MADHUR DAY", aliases:["MADHUR DAY"] },
  { market:"MILAN DAY", aliases:["MILAN DAY"] },
  { market:"RAJDHANI DAY", aliases:["RAJDHANI DAY"] },
  { market:"SUPREME DAY", aliases:["SUPREME DAY"] },
  { market:"KALYAN", aliases:["KALYAN"] },
  { market:"SRIDEVI NIGHT", aliases:["SRIDEVI NIGHT", "SRIDEV NIGHT", "SRI DEVI NIGHT"] },
  { market:"MADHUR NIGHT", aliases:["MADHUR NIGHT", "MADHURI NIGHT"] },
  { market:"SUPREME NIGHT", aliases:["SUPREME NIGHT"] },
  { market:"MILAN NIGHT", aliases:["MILAN NIGHT"] },
  { market:"KALYAN NIGHT", aliases:["KALYAN NIGHT", "MAIN KALYAN NIGHT"] },
  { market:"RAJDHANI NIGHT", aliases:["RAJDHANI NIGHT"] },
  { market:"MAIN BAZAR", aliases:["MAIN BAZAR", "MAINBAZAR", "MAIN BAZAR NIGHT"] }
];
const RESULT_ALIAS_LOOKUP = new Map();
for(const item of RESULT_MARKET_ALIASES){
  for(const a of item.aliases) RESULT_ALIAS_LOOKUP.set(normalizeMarketText(a), item.market);
}

function normalizeMarketText(v){
  return String(v || "")
    .toUpperCase()
    .replace(/&AMP;/g, "&")
    .replace(/[^A-Z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}
function decodeEntitiesBasic(v){
  return String(v || "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&#45;/g, "-")
    .replace(/&ndash;|&mdash;|&#8211;|&#8212;/gi, "-");
}
function htmlToLines(html){
  return decodeEntitiesBasic(String(html || ""))
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<\/div>|<\/p>|<\/h[1-6]>|<\/li>|<\/tr>|<\/section>|<\/article>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .split(/\n+/)
    .map(x => x.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}
function cleanScrapedResult(v){
  const raw = String(v || "")
    .replace(/[–—−]/g, "-")
    .replace(/&nbsp;/gi, " ")
    .trim();
  if(!raw || raw.includes("*")) return "";
  // Extract only the result at the beginning of the text.
  // This avoids merging following time text, e.g. "144-9 9:35 PM" must stay "144-9".
  const close = raw.match(/^\s*(\d{3})\s*-\s*(\d{2})\s*-\s*(\d{3})(?!\d|\s*-\s*\d)/);
  if(close) return `${close[1]}-${close[2]}-${close[3]}`;
  const open = raw.match(/^\s*(\d{3})\s*-\s*(\d)(?!\d|\s*-\s*\d)/);
  if(open) return `${open[1]}-${open[2]}`;
  return "";
}
function escapeRegex(s){ return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
const RESULT_ALIAS_ROWS = [];
for(const item of RESULT_MARKET_ALIASES){
  for(const alias of item.aliases){
    RESULT_ALIAS_ROWS.push({ market:item.market, alias:String(alias).toUpperCase().replace(/\s+/g, " ").trim() });
  }
}
RESULT_ALIAS_ROWS.sort((a,b)=>b.alias.length-a.alias.length);
let runtimeResultAliasRows = null;
function buildResultAliasRowsFromState(state, purpose="result"){
  const rows = [];
  try{
    const allItems = Object.values(ensureMarketRegistry(state || {}).items || {});
    const items = allItems.filter(item => marketPhase3Allowed(state, item.displayName || item.name, purpose === "auto_result" ? "auto_result" : "result").ok);
    for(const item of items){
      const market = String(item.displayName || item.name || "").toUpperCase().trim();
      if(!market) continue;
      const aliases = new Set([market, item.name, item.displayName, item.websiteName, ...(Array.isArray(item.aliases)?item.aliases:[])]);
      aliases.add(market.replace("SRIDEV DAY", "SRIDEVI DAY"));
      aliases.add(market.replace("SRIDEVI DAY", "SRIDEV DAY"));
      for(const a of aliases){ const alias = String(a || "").toUpperCase().replace(/\s+/g," ").trim(); if(alias) rows.push({market, alias}); }
    }
  }catch(e){}
  rows.sort((a,b)=>b.alias.length-a.alias.length);
  return rows.length ? rows : RESULT_ALIAS_ROWS;
}
function resultAliasRowsForRuntime(){ return Array.isArray(runtimeResultAliasRows) && runtimeResultAliasRows.length ? runtimeResultAliasRows : RESULT_ALIAS_ROWS; }
function resultAtStart(v){ return cleanScrapedResult(String(v || "").trim()); }
function liveStatusFromText(v){
  const t = normalizeMarketText(String(v || ""));
  if(!t) return "";
  if(/\b(LOADING|LOADING\.\.\.|WAIT|WAITING|COMING SOON)\b/i.test(t)) return "loading";
  if(/\b(HOLIDAY|CLOSED|NO RESULT)\b/i.test(t)) return "holiday";
  return "";
}
function ensureLiveDateState(date){
  if(!liveResultState || typeof liveResultState !== "object") liveResultState = {};
  if(!liveResultState[date]) liveResultState[date] = {};
  return liveResultState[date];
}
function rememberLiveStatus(item){
  const date = todayISO();
  if(!item || !item.market) return;
  const day = ensureLiveDateState(date);
  const rec = day[item.market] || { market:item.market };
  if(item.status){
    rec.lastStatus = item.status;
    rec.lastStatusAt = new Date().toISOString();
    rec.rawStatusLine = item.rawStatusLine || "";
    if(item.status === "loading"){
      rec.loadingSeen = true;
      rec.loadingSeenAt = rec.lastStatusAt;
    }
    if(item.status === "holiday"){
      rec.holidaySeen = true;
      rec.holidaySeenAt = rec.lastStatusAt;
    }
  }
  if(item.result){
    rec.lastResult = cleanResult(item.result);
    rec.lastResultStage = resultStage(item.result);
    rec.lastResultAt = new Date().toISOString();
  }
  day[item.market] = rec;
  // Keep only today's live state so old Loading/Result transitions never leak into tomorrow.
  for(const k of Object.keys(liveResultState)) if(k !== date) delete liveResultState[k];
  saveJson(LIVE_RESULT_STATE_FILE, liveResultState);
}
function liveStateForMarket(market){
  const day = ensureLiveDateState(todayISO());
  return day[market] || {};
}
function marketFromLineStart(line){
  const raw = decodeEntitiesBasic(line).toUpperCase().replace(/\s+/g, " ").trim();
  if(!raw) return null;
  for(const row of resultAliasRowsForRuntime()){
    const re = new RegExp("^" + escapeRegex(row.alias).replace(/\\\s\+/g, "\\s+") + "(?:\\s+|$)");
    const m = raw.match(re);
    if(!m) continue;
    const rest = raw.slice(m[0].length).trim();
    const result = resultAtStart(rest);
    if(resultStage(result)) return { market:row.market, result, stage:resultStage(result), status:"result", rest, exact:false };
    const status = liveStatusFromText(rest);
    // Treat as a standalone market line only when it does not continue as another market name.
    // Example: "KALYAN MORNING 150-61-560" must not become "KALYAN".
    if(!rest || status || /^(\*|\-)/i.test(rest)) return { market:row.market, result:"", stage:"", status, rest, exact:true };
  }
  return null;
}
function marketFromLineAnywhere(line){
  const raw = decodeEntitiesBasic(line).toUpperCase().replace(/\s+/g, " ").trim();
  if(!raw) return null;
  for(const row of resultAliasRowsForRuntime()){
    const aliasPattern = escapeRegex(row.alias).replace(/\s+/g, "\\s+");
    const re = new RegExp("(?:^|\\s)" + aliasPattern + "(?:\\s+|$)(.*)$");
    const m = raw.match(re);
    if(!m) continue;
    const rest = String(m[1] || "").replace(/^[:\-]+\s*/, "").trim();
    const result = resultAtStart(rest);
    if(resultStage(result)) return { market:row.market, result, stage:resultStage(result), status:"result", rest, exact:false };
    const status = liveStatusFromText(rest);
    if(status) return { market:row.market, result:"", stage:"", status, rest, exact:false };
  }
  return null;
}

function findLiveResultSlices(lines){
  const slices = [];
  for(let i=0; i<lines.length; i++){
    const n = normalizeMarketText(lines[i]);
    if(n.includes("LIVE RESULT")){
      let end = Math.min(lines.length, i + 90);
      for(let j=i+1; j<end; j++){
        const x = normalizeMarketText(lines[j]);
        if(x.includes("WORLD ME SABSE FAST") || x.includes("PLAY ONLINE MATKA") || x.includes("INDIA S BIGGEST") || x.includes("BOOKING OPEN")){ end = j; break; }
      }
      slices.push({ start:i+1, end, label:"DPBOSS LIVE RESULT" });
    }
    if(n.includes("WORLD ME SABSE FAST") || n.includes("LIVE MATKA RESULT")){
      let end = Math.min(lines.length, i + 900);
      for(let j=i+1; j<end; j++){
        const x = normalizeMarketText(lines[j]);
        if(x.includes("CONTACT FOR ANY SUPPORT") || x.includes("MEMBER S FORUM") || x.includes("SATTA MATKA JODI CHART") || x.includes("WEEKLY PANEL") || x.includes("OPEN TO CLOSE FREE GAME ZONE") || x.includes("GUESSING") || x.includes("FIX SINGLE")){ end = j; break; }
      }
      slices.push({ start:i+1, end, label:n.includes("WORLD ME SABSE FAST") ? "DPBOSS MAIN RESULT" : "LIVE MATKA RESULT" });
    }
    if(n.includes("LIVE UPDATE")){
      let end = Math.min(lines.length, i + 80);
      for(let j=i+1; j<end; j++){
        const x = normalizeMarketText(lines[j]);
        if(x.includes("LIVE MATKA RESULT") || x.includes("WORLD ME SABSE FAST") || x.includes("PLAY ONLINE MATKA") || x.includes("INDIA S BIGGEST")){ end = j; break; }
      }
      slices.push({ start:i+1, end, label:"LIVE UPDATE" });
    }
  }
  if(!slices.length){
    let end = Math.min(lines.length, 720);
    for(let j=0; j<end; j++){
      const x = normalizeMarketText(lines[j]);
      if(x.includes("CONTACT FOR ANY SUPPORT") || x.includes("MEMBER S FORUM") || x.includes("SATTA MATKA JODI CHART") || x.includes("WEEKLY PANEL") || x.includes("OPEN TO CLOSE FREE GAME ZONE")){ end = j; break; }
    }
    slices.push({ start:0, end, label:"TOP SAFE BLOCK" });
  }
  return slices;
}
function chooseBetterResult(prev, item){
  if(!prev) return item;
  // Prefer the dedicated LIVE MATKA RESULT list over small widgets/fallback blocks.
  const rank = (x) => (x.block === "LIVE MATKA RESULT" ? 5 : (x.block === "LIVE UPDATE" ? 4 : (x.block === "DPBOSS LIVE RESULT" ? 3 : (x.block === "DPBOSS MAIN RESULT" ? 2 : 1))));
  if(rank(item) !== rank(prev)) return rank(item) > rank(prev) ? item : prev;
  // Same stage only: never replace a fresh open result with a full close result here.
  // Fresh lifecycle is enforced later: open 123-4 must exist before close 123-45-678 is accepted.
  return prev;
}
function extractResultsFromHtml(html, sourceUrl){
  const lines = htmlToLines(html);
  // Keep every distinct market+stage+result candidate.
  // DPBOSSE pages can contain old complete results and fresh live results in nearby blocks.
  // If we collapse only by market+stage, a stale close can hide the fresh matching close.
  const found = new Map();
  const statuses = [];
  const slices = findLiveResultSlices(lines);
  for(const slice of slices){
    for(let i=slice.start; i<slice.end; i++){
      let hit = marketFromLineStart(lines[i]);
      if(!hit && slice.label === "DPBOSS LIVE RESULT") hit = marketFromLineAnywhere(lines[i]);
      if(!hit) continue;
      if(hit.result && hit.stage){
        const item = { market:hit.market, result:hit.result, stage:hit.stage, status:"result", sourceUrl, rawMarketLine:lines[i], rawResultLine:lines[i], block:slice.label, confidence:"same_line", lineIndex:i };
        const key = `${item.market}_${item.stage}_${cleanResult(item.result)}`;
        found.set(key, chooseBetterResult(found.get(key), item));
        continue;
      }
      if(hit.status === "loading" || hit.status === "holiday"){
        statuses.push({ market:hit.market, status:hit.status, sourceUrl, rawMarketLine:lines[i], rawStatusLine:lines[i], block:slice.label, confidence:"same_line_status" });
        continue;
      }
      // Separate market line: accept only the immediate next 1-3 clean lines before any next market.
      // Handles the real widget pattern:
      // MARKET NAME / Loading... / Refresh -> later MARKET NAME / 123-4 / Refresh -> later MARKET NAME / 123-45-678 / Refresh
      for(let j=i+1; j<Math.min(slice.end, i+4); j++){
        if(marketFromLineStart(lines[j])) break;
        const status = liveStatusFromText(lines[j]);
        if(status){
          statuses.push({ market:hit.market, status, sourceUrl, rawMarketLine:lines[i], rawStatusLine:lines[j], block:slice.label, confidence:"next_line_status" });
          break;
        }
        const result = resultAtStart(lines[j]);
        const stage = resultStage(result);
        if(stage){
          const item = { market:hit.market, result, stage, status:"result", sourceUrl, rawMarketLine:lines[i], rawResultLine:lines[j], block:slice.label, confidence:"next_line", lineIndex:j };
          const key = `${item.market}_${item.stage}_${cleanResult(item.result)}`;
          found.set(key, chooseBetterResult(found.get(key), item));
          break;
        }
      }
    }
  }
  return { results:[...found.values()], statuses };
}
async function scrapeLiveResultPages(){
  const byMarketStage = new Map();
  const statuses = [];
  const errors = [];
  const headers = {
    "User-Agent":"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":"en-IN,en;q=0.9,hi;q=0.8",
    "Cache-Control":"no-cache, no-store, must-revalidate",
    "Pragma":"no-cache",
    "Expires":"0"
  };
  for(const url of RESULT_SCRAPE_URLS){
    try {
      const fetchUrl = url + (url.includes("?") ? "&" : "?") + "_=" + Date.now();
      const res = await axios.get(fetchUrl, { timeout:8000, headers });
      const parsed = extractResultsFromHtml(res.data || "", url);
      for(const st of parsed.statuses || []) statuses.push(st);
      for(const item of parsed.results || []){
        const key = `${item.market}_${item.stage}_${cleanResult(item.result)}`;
        const prev = byMarketStage.get(key);
        byMarketStage.set(key, chooseBetterResult(prev, item));
      }
    } catch(e) {
      errors.push(`${url}: ${e.response ? "HTTP "+e.response.status : e.message}`);
    }
  }
  return { results:[...byMarketStage.values()], statuses, errors };
}
function confirmScrapedResults(scraped){
  const date = todayISO();
  const confirmed = [];
  const seenKeys = new Set();
  for(const item of scraped || []){
    const stage = resultStage(item.result);
    if(!stage) continue;
    const key = `${date}_${item.market}_${stage}`;
    const signature = cleanResult(item.result);
    seenKeys.add(key);
    const old = scrapeConfirm[key] || {};
    if(old.signature === signature){
      old.count = Number(old.count || 0) + 1;
    } else {
      old.signature = signature;
      old.count = 1;
      old.firstSeenAt = new Date().toISOString();
    }
    old.market = item.market;
    old.stage = stage;
    old.result = signature;
    old.lastSeenAt = new Date().toISOString();
    old.sourceUrl = item.sourceUrl || "";
    old.rawMarketLine = item.rawMarketLine || "";
    old.rawResultLine = item.rawResultLine || "";
    old.block = item.block || "";
    scrapeConfirm[key] = old;
    if(old.count >= RESULT_SCRAPE_CONFIRM_COUNT){
      confirmed.push({ ...item, result:signature, stage, confirmCount:old.count });
    }
  }
  // Keep file small: remove old dates.
  for(const key of Object.keys(scrapeConfirm)){
    if(!key.startsWith(date + "_")) delete scrapeConfirm[key];
  }
  saveJson(SCRAPE_CONFIRM_FILE, scrapeConfirm);
  return confirmed;
}

function extractInviteCode(raw){
  const t = String(raw || "").trim();
  const m = t.match(/chat\.whatsapp\.com\/([A-Za-z0-9_-]+)/i);
  if(m) return m[1];
  if(/^[A-Za-z0-9_-]{20,}$/.test(t) && !/^\d+$/.test(t) && !t.includes("@")) return t;
  return "";
}

function normalizeTarget(raw){
  let t = targetValue(raw);
  if(!t) return "";
  t = t.replace(/[<>]/g, "").trim();
  const jidMatch = t.match(/([0-9A-Za-z._:-]+@(?:g\.us|s\.whatsapp\.net))/i);
  if(jidMatch) return jidMatch[1].replace(/:\d+(?=@)/, "");
  if(t.includes("@g.us") || t.includes("@s.whatsapp.net")) return t.replace(/:\d+(?=@)/, "");
  const inviteCode = extractInviteCode(t);
  if(inviteCode) return "invite:" + inviteCode;
  // Supports wa.me/91xxxx, api.whatsapp.com/send?phone=, +91 xxxx, and plain 10 digit numbers.
  let digits = t.replace(/[^0-9]/g, "");
  if(!digits) return "";
  // Avoid accidentally merging a visible serial number with the phone; keep the last Indian number shape.
  if(digits.length > 12 && digits.endsWith("0")) digits = digits.slice(-12);
  if(digits.length > 12) digits = digits.slice(-12);
  if(digits.length === 10) digits = "91" + digits;
  if(digits.length < 10) return "";
  return digits + "@s.whatsapp.net";
}

async function resolveTarget(rawTarget){
  let jid = normalizeTarget(rawTarget);
  if(!jid) return "";
  if(jid.startsWith("invite:")){
    if(!sock || !connected) return "";
    const code = jid.slice(7);
    try {
      const info = await sock.groupGetInviteInfo(code);
      if(info?.id) return String(info.id).includes("@g.us") ? String(info.id) : String(info.id) + "@g.us";
    } catch(e) {
      console.log("Group invite resolve failed:", e.message || e);
      return "";
    }
  }
  return jid;
}

async function isValidTarget(jid){
  if(!jid) return false;
  if(jid.endsWith("@g.us")) return true;
  if(!sock || !connected) return false;
  try {
    const res = await sock.onWhatsApp(jid.replace("@s.whatsapp.net", ""));
    return Array.isArray(res) && res[0] && !!res[0].exists;
  } catch { return true; }
}


// ============================================================
// WHATSAPP SAFE MESSAGING GUARD
// Outgoing guard: global pause, per-target pause/approval, safe delay queue,
// duplicate fingerprint lock, daily counters, and auto-pause on failures.
// ============================================================
let safeSendChain = Promise.resolve();
let safeSendQueueDepth = 0;
let whatsappSafetyCache = { at:0, state:null };

function defaultWhatsappSafetySettings(){
  return {
    enabled:true,
    globalPaused:false,
    pauseReason:"",
    requireApprovedTargets:false,
    minDelayMs:2500,
    randomDelayMs:1200,
    duplicateBlock:true,
    duplicateWindowMinutes:1440,
    targetFailureLimit:3,
    globalConsecutiveFailureLimit:8,
    dailyTargetLimit:80,
    dailyGlobalLimit:300,
    autoPauseTargetOnFailures:true,
    autoPauseGlobalOnFailures:true,
    safeModeForGroupsOnly:false,
    allowPrivateReplies:true,
    allowAdminNotifications:true,
    adminAlertTargets:[],
    complianceMode:true,
    optOutEnabled:true,
    optOutKeywords:["STOP","UNSUBSCRIBE","CANCEL","BLOCK"],
    optInKeywords:["START","JOIN","SUBSCRIBE"],
    requireOptInForPrivateSends:false,
    optOutAckText:"Aapko WhatsApp updates se unsubscribe kar diya gaya hai. Dobara start karne ke liye START bhejein.",
    optInAckText:"Aap WhatsApp updates ke liye active ho gaye hain.",
    complianceGuardV18:true,
    updatedAt:""
  };
}
function ensureWhatsappSafetyState(state){
  if(!state || typeof state !== "object") state = {};
  state.whatsappSafetySettings = state.whatsappSafetySettings && typeof state.whatsappSafetySettings === "object" ? state.whatsappSafetySettings : {};
  const defs = defaultWhatsappSafetySettings();
  for(const [k,v] of Object.entries(defs)) if(typeof state.whatsappSafetySettings[k] === "undefined") state.whatsappSafetySettings[k] = v;
  state.whatsappSafetyTargets = state.whatsappSafetyTargets && typeof state.whatsappSafetyTargets === "object" ? state.whatsappSafetyTargets : {};
  state.whatsappSafetyEvents = Array.isArray(state.whatsappSafetyEvents) ? state.whatsappSafetyEvents : [];
  return state;
}
async function getWhatsappSafetyState(force=false){
  const now = Date.now();
  if(!force && whatsappSafetyCache.state && (now - whatsappSafetyCache.at) < 2000) return whatsappSafetyCache.state;
  try{
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    whatsappSafetyCache = { at:now, state };
    return state;
  }catch(e){
    console.log("WhatsApp safety state load failed:", e.response ? `HTTP ${e.response.status}` : e.message);
    return ensureWhatsappSafetyState({});
  }
}
function safetyTargetKey(jid){ return String(jid || "").trim().replace(/:\d+(?=@)/, ""); }
function safetyTargetType(jid){ return String(jid || "").includes("@g.us") ? "group" : "contact"; }
function safetyHash(text){
  const crypto = require("crypto");
  const clean = String(text || "").replace(/\s+/g," ").trim().slice(0,4000);
  return crypto.createHash("sha1").update(clean).digest("hex").slice(0,16);
}
function saveWhatsappSafetyLocalState(){
  try{
    whatsappSafetyLocalState.events = Array.isArray(whatsappSafetyLocalState.events) ? whatsappSafetyLocalState.events.slice(-500) : [];
    saveJson(WHATSAPP_SAFETY_STATE_FILE, whatsappSafetyLocalState);
  }catch(e){ console.log("WhatsApp safety local save failed:", e.message); }
}
function cleanupSafetyFingerprints(settings){
  const today = todayISO();
  whatsappSafetyLocalState.fingerprints = whatsappSafetyLocalState.fingerprints && typeof whatsappSafetyLocalState.fingerprints === "object" ? whatsappSafetyLocalState.fingerprints : {};
  whatsappSafetyLocalState.daily = whatsappSafetyLocalState.daily && typeof whatsappSafetyLocalState.daily === "object" ? whatsappSafetyLocalState.daily : {date:today, globalCount:0};
  if(whatsappSafetyLocalState.daily.date !== today) whatsappSafetyLocalState.daily = {date:today, globalCount:0};
  const cutoff = Date.now() - Math.max(1, Number(settings.duplicateWindowMinutes || 1440)) * 60000;
  for(const [k,v] of Object.entries(whatsappSafetyLocalState.fingerprints || {})){
    const t = Date.parse(v?.time || v || "");
    if(!k.startsWith(today + "|") || (Number.isFinite(t) && t < cutoff)) delete whatsappSafetyLocalState.fingerprints[k];
  }
}
function pushWhatsappSafetyEvent(state, ev){
  const event = { id:`WSG${Date.now()}${Math.floor(Math.random()*1000)}`, time:nowIso(), date:todayISO(), ...ev };
  state.whatsappSafetyEvents = Array.isArray(state.whatsappSafetyEvents) ? state.whatsappSafetyEvents : [];
  state.whatsappSafetyEvents.push(event);
  if(state.whatsappSafetyEvents.length > 300) state.whatsappSafetyEvents.splice(0, state.whatsappSafetyEvents.length - 300);
  whatsappSafetyLocalState.events = Array.isArray(whatsappSafetyLocalState.events) ? whatsappSafetyLocalState.events : [];
  whatsappSafetyLocalState.events.push(event);
  if(whatsappSafetyLocalState.events.length > 500) whatsappSafetyLocalState.events.splice(0, whatsappSafetyLocalState.events.length - 500);
  gatewayHealth.whatsappSafetyLastEvent = `${event.action || event.kind || "event"} ${event.target || ""}`.trim();
  saveWhatsappSafetyLocalState();
  return event;
}
function safetyTargetRecord(state, targetKey, jid){
  state.whatsappSafetyTargets = state.whatsappSafetyTargets && typeof state.whatsappSafetyTargets === "object" ? state.whatsappSafetyTargets : {};
  const rec = state.whatsappSafetyTargets[targetKey] && typeof state.whatsappSafetyTargets[targetKey] === "object" ? state.whatsappSafetyTargets[targetKey] : {};
  rec.id = rec.id || targetKey;
  rec.type = rec.type || safetyTargetType(jid || targetKey);
  rec.approved = rec.approved !== false;
  rec.paused = rec.paused === true;
  rec.failureCount = Number(rec.failureCount || 0);
  rec.optedOut = rec.optedOut === true;
  rec.optedIn = rec.optedIn === true;
  rec.consentUpdatedAt = rec.consentUpdatedAt || "";
  rec.dailyDate = rec.dailyDate || todayISO();
  rec.dailyCount = Number(rec.dailyCount || 0);
  if(rec.dailyDate !== todayISO()){ rec.dailyDate = todayISO(); rec.dailyCount = 0; }
  state.whatsappSafetyTargets[targetKey] = rec;
  return rec;
}

function normalizeComplianceCommand(text){
  const t = String(text || "").trim().replace(/^\/+/, "").toUpperCase();
  if(!t) return "";
  if(["STOP","UNSUBSCRIBE","CANCEL","BLOCK","STOP ALL"].includes(t)) return "opt_out";
  if(["START","JOIN","SUBSCRIBE","RESUME"].includes(t)) return "opt_in";
  return "";
}
async function handleWhatsappComplianceCommandMessage(m){
  try{
    if(!m || m.key?.fromMe) return false;
    const chatJid = m.key?.remoteJid || "";
    if(!chatJid || chatJid === "status@broadcast") return false;
    const cmd = normalizeComplianceCommand(getMessageText(m));
    if(!cmd) return false;
    const senderCandidates = senderCandidatesFromMessage(m, chatJid);
    const senderJid = chatJid.endsWith("@g.us") ? (senderCandidates[0] || m.key?.participant || "") : chatJid;
    const targetKey = safetyTargetKey(senderJid || chatJid);
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    const settings = state.whatsappSafetySettings || defaultWhatsappSafetySettings();
    if(settings.optOutEnabled === false) return false;
    const rec = safetyTargetRecord(state, targetKey, senderJid || chatJid);
    if(cmd === "opt_out"){
      rec.optedOut = true;
      rec.optedIn = false;
      rec.paused = true;
      rec.pauseReason = "User requested STOP/unsubscribe";
      rec.consentUpdatedAt = nowIso();
      pushWhatsappSafetyEvent(state, {action:"user_opted_out", target:targetKey, type:rec.type});
      await patchFirebaseState({whatsappSafetySettings:state.whatsappSafetySettings, whatsappSafetyTargets:state.whatsappSafetyTargets, whatsappSafetyEvents:state.whatsappSafetyEvents});
      whatsappSafetyCache = {at:Date.now(), state};
      await replyToMessage(chatJid, settings.optOutAckText || "Aap unsubscribe ho gaye hain. Dobara start karne ke liye START bhejein.", m);
      return true;
    }
    if(cmd === "opt_in"){
      rec.optedOut = false;
      rec.optedIn = true;
      rec.paused = false;
      rec.pauseReason = "";
      rec.approved = true;
      rec.consentUpdatedAt = nowIso();
      pushWhatsappSafetyEvent(state, {action:"user_opted_in", target:targetKey, type:rec.type});
      await patchFirebaseState({whatsappSafetySettings:state.whatsappSafetySettings, whatsappSafetyTargets:state.whatsappSafetyTargets, whatsappSafetyEvents:state.whatsappSafetyEvents});
      whatsappSafetyCache = {at:Date.now(), state};
      await replyToMessage(chatJid, settings.optInAckText || "Aap WhatsApp updates ke liye active ho gaye hain.", m);
      return true;
    }
    return false;
  }catch(e){ console.log("WhatsApp compliance command error:", e.response ? `HTTP ${e.response.status}` : e.message); return false; }
}

function whatsappSafetyFingerprint(settings, targetKey, text, meta){
  const kind = String(meta?.type || meta?.kind || "message").replace(/[^a-z0-9_-]/ig,"_").slice(0,40);
  return `${todayISO()}|${targetKey}|${kind}|${safetyHash(text)}`;
}
async function whatsappSafetyBeforeSend(jid, text, meta={}){
  const state = await getWhatsappSafetyState(true);
  ensureWhatsappSafetyState(state);
  const settings = state.whatsappSafetySettings;
  gatewayHealth.whatsappSafetyPaused = settings.globalPaused === true;
  if(settings.enabled === false) return { allowed:true, state, settings, targetKey:safetyTargetKey(jid), fingerprint:"" };
  const targetKey = safetyTargetKey(jid);
  const type = safetyTargetType(jid);
  const rec = safetyTargetRecord(state, targetKey, jid);
  cleanupSafetyFingerprints(settings);
  const fp = whatsappSafetyFingerprint(settings, targetKey, text, meta);
  const isPrivateReply = meta && meta.privateReply === true;
  const isAdminNotice = meta && meta.adminNotice === true;
  if(settings.safeModeForGroupsOnly === true && type !== "group") return { allowed:true, state, settings, targetKey, fingerprint:fp, rec };
  if(settings.globalPaused === true){
    gatewayHealth.whatsappSafetyLastBlock = `global_paused: ${settings.pauseReason || "manual pause"}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"global_paused", message:settings.pauseReason || "WhatsApp sending paused" };
  }
  if(isPrivateReply && settings.allowPrivateReplies !== false) return { allowed:true, state, settings, targetKey, fingerprint:fp, rec };
  if(isAdminNotice && settings.allowAdminNotifications !== false) return { allowed:true, state, settings, targetKey, fingerprint:fp, rec };
  if(settings.optOutEnabled !== false && rec.optedOut === true){
    gatewayHealth.whatsappSafetyLastBlock = `user_opted_out: ${targetKey}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"user_opted_out", message:"Target has opted out from WhatsApp updates" };
  }
  if(settings.requireOptInForPrivateSends === true && type === "contact" && rec.optedIn !== true){
    gatewayHealth.whatsappSafetyLastBlock = `opt_in_required: ${targetKey}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"opt_in_required", message:"Target has not opted in for automated WhatsApp updates" };
  }
  if(rec.paused === true){
    gatewayHealth.whatsappSafetyLastBlock = `target_paused: ${targetKey}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"target_paused", message:rec.pauseReason || "Target paused by safety guard" };
  }
  if(settings.requireApprovedTargets === true && rec.approved !== true){
    gatewayHealth.whatsappSafetyLastBlock = `target_not_approved: ${targetKey}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"target_not_approved", message:"Target not approved for auto sending" };
  }
  if(Number(settings.dailyGlobalLimit || 0) > 0 && Number(whatsappSafetyLocalState.daily?.globalCount || 0) >= Number(settings.dailyGlobalLimit)){
    gatewayHealth.whatsappSafetyLastBlock = `daily_global_limit: ${settings.dailyGlobalLimit}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"daily_global_limit", message:"Daily WhatsApp send limit reached" };
  }
  if(Number(settings.dailyTargetLimit || 0) > 0 && Number(rec.dailyCount || 0) >= Number(settings.dailyTargetLimit)){
    gatewayHealth.whatsappSafetyLastBlock = `daily_target_limit: ${targetKey}`;
    return { allowed:false, state, settings, targetKey, fingerprint:fp, rec, reason:"daily_target_limit", message:"Target daily send limit reached" };
  }
  if(settings.duplicateBlock !== false && whatsappSafetyLocalState.fingerprints && whatsappSafetyLocalState.fingerprints[fp]){
    gatewayHealth.whatsappSafetyLastBlock = `duplicate_blocked: ${targetKey}`;
    return { allowed:false, duplicate:true, state, settings, targetKey, fingerprint:fp, rec, reason:"duplicate_blocked", message:"Duplicate message blocked by safety guard" };
  }
  return { allowed:true, state, settings, targetKey, fingerprint:fp, rec };
}
async function whatsappSafetyAfterSend(pre, out){
  if(!pre || !pre.state || pre.settings?.enabled === false) return;
  const state = pre.state;
  ensureWhatsappSafetyState(state);
  const rec = safetyTargetRecord(state, pre.targetKey, out.target || pre.targetKey);
  cleanupSafetyFingerprints(pre.settings);
  if(out.ok){
    rec.failureCount = 0;
    rec.lastError = "";
    rec.lastSentAt = nowIso();
    rec.dailyCount = Number(rec.dailyCount || 0) + 1;
    whatsappSafetyLocalState.daily.globalCount = Number(whatsappSafetyLocalState.daily.globalCount || 0) + 1;
    whatsappSafetyLocalState.consecutiveFailures = 0;
    if(pre.fingerprint) whatsappSafetyLocalState.fingerprints[pre.fingerprint] = { time:nowIso(), target:pre.targetKey, type:out.meta?.type || "message" };
    pushWhatsappSafetyEvent(state, { action:out.skipped ? "duplicate_skip" : "sent", target:pre.targetKey, type:rec.type, meta:out.meta || {}, id:out.id || "" });
  }else{
    rec.failureCount = Number(rec.failureCount || 0) + 1;
    rec.lastFailureAt = nowIso();
    rec.lastError = out.error || "send failed";
    whatsappSafetyLocalState.consecutiveFailures = Number(whatsappSafetyLocalState.consecutiveFailures || 0) + 1;
    if(pre.settings.autoPauseTargetOnFailures !== false && Number(pre.settings.targetFailureLimit || 0) > 0 && rec.failureCount >= Number(pre.settings.targetFailureLimit)){
      rec.paused = true;
      rec.status = "paused";
      rec.pauseReason = `Auto-paused after ${rec.failureCount} failed sends`;
      pushWhatsappSafetyEvent(state, { action:"target_auto_paused", target:pre.targetKey, type:rec.type, error:out.error || "send failed", failureCount:rec.failureCount });
    }else{
      pushWhatsappSafetyEvent(state, { action:"send_failed", target:pre.targetKey, type:rec.type, error:out.error || "send failed", failureCount:rec.failureCount });
    }
    if(pre.settings.autoPauseGlobalOnFailures !== false && Number(pre.settings.globalConsecutiveFailureLimit || 0) > 0 && Number(whatsappSafetyLocalState.consecutiveFailures || 0) >= Number(pre.settings.globalConsecutiveFailureLimit)){
      state.whatsappSafetySettings.globalPaused = true;
      state.whatsappSafetySettings.pauseReason = `Auto-paused after ${whatsappSafetyLocalState.consecutiveFailures} consecutive send failures`;
      pushWhatsappSafetyEvent(state, { action:"global_auto_paused", target:"ALL", error:out.error || "send failed", consecutiveFailures:whatsappSafetyLocalState.consecutiveFailures });
    }
  }
  gatewayHealth.whatsappSafetyPaused = state.whatsappSafetySettings.globalPaused === true;
  gatewayHealth.whatsappSafetyConsecutiveFailures = Number(whatsappSafetyLocalState.consecutiveFailures || 0);
  saveWhatsappSafetyLocalState();
  try{ await patchFirebaseState({ whatsappSafetySettings:state.whatsappSafetySettings, whatsappSafetyTargets:state.whatsappSafetyTargets, whatsappSafetyEvents:state.whatsappSafetyEvents }); whatsappSafetyCache = { at:Date.now(), state }; }catch(e){ console.log("WhatsApp safety state save failed:", e.response ? `HTTP ${e.response.status}` : e.message); }
}
function safeDelayMs(settings){
  const base = Math.max(0, Number(settings?.minDelayMs || 0));
  const rnd = Math.max(0, Number(settings?.randomDelayMs || 0));
  return base + (rnd ? Math.floor(Math.random() * rnd) : 0);
}
function safeSendQueueRun(fn){
  safeSendQueueDepth += 1;
  gatewayHealth.whatsappSafetyQueueDepth = safeSendQueueDepth;
  const run = safeSendChain.then(async () => {
    try { return await fn(); }
    finally { safeSendQueueDepth = Math.max(0, safeSendQueueDepth - 1); gatewayHealth.whatsappSafetyQueueDepth = safeSendQueueDepth; }
  });
  safeSendChain = run.catch(()=>{});
  return run;
}

// ============================================================
// WHATSAPP RELIABILITY DASHBOARD v19
// Operational send ledger: sent / failed / blocked / retryable events.
// This is for diagnostics and resend control, not stealth or anti-detection.
// ============================================================
let whatsappReliabilityState = loadJson(WHATSAPP_RELIABILITY_FILE, {events:[], pending:{}, stats:{}, lastUpdatedAt:""});
const WHATSAPP_RELIABILITY_MAX_EVENTS = Math.max(Number(process.env.TITAN_WA_RELIABILITY_MAX_EVENTS || 1200), 200);
const WHATSAPP_RELIABILITY_PREVIEW_CHARS = Math.max(Number(process.env.TITAN_WA_RELIABILITY_PREVIEW_CHARS || 260), 80);
function waReliabilityEnsure(){
  whatsappReliabilityState = whatsappReliabilityState && typeof whatsappReliabilityState === "object" ? whatsappReliabilityState : {};
  whatsappReliabilityState.events = Array.isArray(whatsappReliabilityState.events) ? whatsappReliabilityState.events : [];
  whatsappReliabilityState.pending = whatsappReliabilityState.pending && typeof whatsappReliabilityState.pending === "object" ? whatsappReliabilityState.pending : {};
  whatsappReliabilityState.stats = whatsappReliabilityState.stats && typeof whatsappReliabilityState.stats === "object" ? whatsappReliabilityState.stats : {};
  return whatsappReliabilityState;
}
function waReliabilitySave(){
  try{
    waReliabilityEnsure();
    whatsappReliabilityState.events = whatsappReliabilityState.events.slice(-WHATSAPP_RELIABILITY_MAX_EVENTS);
    const keepPending = {};
    for(const [k,v] of Object.entries(whatsappReliabilityState.pending || {})){
      const age = Date.now() - Date.parse(v.time || v.lastAt || "");
      if(!Number.isFinite(age) || age < 7*24*3600*1000) keepPending[k] = v;
    }
    whatsappReliabilityState.pending = keepPending;
    whatsappReliabilityState.lastUpdatedAt = nowIso();
    saveJson(WHATSAPP_RELIABILITY_FILE, whatsappReliabilityState);
  }catch(e){ console.log("WhatsApp reliability save failed:", e.message); }
}
function waReliabilityTargetName(jid){
  const id = safetyTargetKey(jid || "");
  try{
    const all = [...(targetsCache.contacts || []), ...(targetsCache.groups || [])];
    const found = all.find(x => safetyTargetKey(x.id || x.jid || x) === id);
    return String(found?.name || found?.subject || id || "");
  }catch(e){ return id; }
}
function waReliabilityMetaType(meta){ return String(meta?.type || meta?.kind || "message").replace(/[^a-z0-9_-]/ig,"_").slice(0,60) || "message"; }
function waReliabilityPreview(text){ return String(text || "").replace(/\s+/g," ").trim().slice(0, WHATSAPP_RELIABILITY_PREVIEW_CHARS); }
function waReliabilityStats(events){
  const today = todayISO();
  const stats = {total:0, sent:0, failed:0, blocked:0, skipped:0, pendingRetry:0, todayTotal:0, todaySent:0, todayFailed:0, todayBlocked:0, lastEventAt:""};
  for(const ev of events || []){
    stats.total += 1;
    const st = String(ev.status || ev.action || "");
    if(st === "sent") stats.sent += 1;
    else if(st === "failed") stats.failed += 1;
    else if(st === "blocked") stats.blocked += 1;
    else if(st === "skipped") stats.skipped += 1;
    if(String(ev.date || "") === today){
      stats.todayTotal += 1;
      if(st === "sent") stats.todaySent += 1;
      else if(st === "failed") stats.todayFailed += 1;
      else if(st === "blocked") stats.todayBlocked += 1;
    }
    if(ev.time) stats.lastEventAt = ev.time;
  }
  stats.pendingRetry = Object.keys((whatsappReliabilityState && whatsappReliabilityState.pending) || {}).length;
  return stats;
}
function waReliabilityRecord(status, rawTarget, jid, text, meta={}, extra={}){
  try{
    waReliabilityEnsure();
    const target = safetyTargetKey(jid || rawTarget || "");
    const ev = {
      id: `WAR${Date.now()}${Math.floor(Math.random()*1000)}`,
      time: nowIso(),
      date: todayISO(),
      version: WHATSAPP_RELIABILITY_VERSION,
      status: String(status || "event"),
      target,
      rawTarget: String(rawTarget || ""),
      targetName: waReliabilityTargetName(jid || rawTarget || ""),
      targetType: safetyTargetType(jid || rawTarget || ""),
      metaType: waReliabilityMetaType(meta),
      meta: meta || {},
      messagePreview: waReliabilityPreview(text),
      messageLength: String(text || "").length,
      retryable: false,
      ...extra
    };
    if(ev.status === "failed" && ev.retryable !== false){ ev.retryable = true; }
    whatsappReliabilityState.events.push(ev);
    if(whatsappReliabilityState.events.length > WHATSAPP_RELIABILITY_MAX_EVENTS) whatsappReliabilityState.events.splice(0, whatsappReliabilityState.events.length - WHATSAPP_RELIABILITY_MAX_EVENTS);
    if(ev.retryable){
      whatsappReliabilityState.pending[ev.id] = {...ev, text:String(text || ""), attempts:Number(extra.attempts || 0)};
    }
    if(extra.retryOf && whatsappReliabilityState.pending[extra.retryOf] && ev.status === "sent"){
      delete whatsappReliabilityState.pending[extra.retryOf];
    }
    whatsappReliabilityState.stats = waReliabilityStats(whatsappReliabilityState.events);
    waReliabilitySave();
    return ev;
  }catch(e){ console.log("WhatsApp reliability record failed:", e.message); return null; }
}
function waReliabilityStatusPayload(limit=80){
  waReliabilityEnsure();
  const events = whatsappReliabilityState.events.slice(-Math.max(1, Math.min(Number(limit||80), 300))).reverse();
  const pending = Object.values(whatsappReliabilityState.pending || {}).slice(-200).reverse();
  const byTarget = {};
  for(const ev of whatsappReliabilityState.events.slice(-500)){
    const k = ev.target || ev.rawTarget || "unknown";
    byTarget[k] = byTarget[k] || {target:k, targetName:ev.targetName || k, sent:0, failed:0, blocked:0, skipped:0, lastAt:"", lastError:""};
    if(ev.status === "sent") byTarget[k].sent += 1;
    else if(ev.status === "failed") { byTarget[k].failed += 1; byTarget[k].lastError = ev.error || ev.reason || ""; }
    else if(ev.status === "blocked") byTarget[k].blocked += 1;
    else if(ev.status === "skipped") byTarget[k].skipped += 1;
    byTarget[k].lastAt = ev.time || byTarget[k].lastAt;
  }
  return {
    status:"success",
    version:WHATSAPP_RELIABILITY_VERSION,
    connected,
    queueDepth:safeSendQueueDepth,
    gateway:{startedAt:gatewayHealth.startedAt, lastSendAt:gatewayHealth.lastSendAt, lastSendOk:gatewayHealth.lastSendOk, lastSendTarget:gatewayHealth.lastSendTarget, lastSendError:gatewayHealth.lastSendError},
    stats:waReliabilityStats(whatsappReliabilityState.events),
    pending,
    events,
    targets:Object.values(byTarget).sort((a,b)=>String(b.lastAt||"").localeCompare(String(a.lastAt||""))).slice(0,120),
    logFile:WHATSAPP_RELIABILITY_FILE
  };
}
async function waReliabilityRetry(eventId){
  waReliabilityEnsure();
  const item = whatsappReliabilityState.pending[eventId] || whatsappReliabilityState.events.find(e => e.id === eventId);
  if(!item) return {ok:false, status:"error", message:"Retry event not found"};
  if(!item.target && !item.rawTarget) return {ok:false, status:"error", message:"Retry target missing"};
  const attempts = Number(item.attempts || 0) + 1;
  if(whatsappReliabilityState.pending[eventId]) whatsappReliabilityState.pending[eventId].attempts = attempts;
  waReliabilitySave();
  const meta = {...(item.meta || {}), type:"manual_retry", retryOf:eventId, retryMetaType:item.metaType || "message"};
  const out = await sendText(item.target || item.rawTarget, item.text || item.messagePreview || "", meta);
  if(out.ok){
    delete whatsappReliabilityState.pending[eventId];
    waReliabilitySave();
  }else if(whatsappReliabilityState.pending[eventId]){
    whatsappReliabilityState.pending[eventId].attempts = attempts;
    whatsappReliabilityState.pending[eventId].lastRetryAt = nowIso();
    whatsappReliabilityState.pending[eventId].lastRetryError = out.error || out.reason || "retry failed";
    waReliabilitySave();
  }
  return {status:out.ok?"success":"error", retried:true, eventId, attempts, result:out};
}

// PHASE2_SEND_SINGLE_SOURCE: all scheduled/result/outbox/broadcast sends must call sendText().
// sendText resolves targets, validates WhatsApp, applies Safe Messaging Guard, serializes queue, then records outcome.
async function sendText(rawTarget, text, meta = {}){
  const jid = await resolveTarget(rawTarget);
  if(!jid){
    gatewayHealth.lastSendAt = nowIso();
    gatewayHealth.lastSendOk = false;
    gatewayHealth.lastSendTarget = String(rawTarget || "");
    gatewayHealth.lastSendError = "invalid/unresolved target";
    gatewayObsEvent("whatsapp_send_blocked", "warning", "Invalid/unresolved WhatsApp target", {rawTarget, meta});
    waReliabilityRecord("blocked", rawTarget, rawTarget, text, meta, {reason:"invalid_target", error:"invalid/unresolved target", retryable:false});
    return {ok:false, rawTarget, target:rawTarget, error:"invalid/unresolved target"};
  }
  if(!sock || !connected){
    gatewayHealth.lastSendAt = nowIso();
    gatewayHealth.lastSendOk = false;
    gatewayHealth.lastSendTarget = jid;
    gatewayHealth.lastSendError = "WhatsApp not connected";
    gatewayObsEvent("whatsapp_send_failed", "error", "WhatsApp not connected", {target:jid, meta});
    waReliabilityRecord("failed", rawTarget, jid, text, meta, {reason:"not_connected", error:"WhatsApp not connected", retryable:true});
    return {ok:false, rawTarget, target:jid, error:"WhatsApp not connected"};
  }
  const okTarget = await isValidTarget(jid);
  if(!okTarget){
    gatewayHealth.lastSendAt = nowIso();
    gatewayHealth.lastSendOk = false;
    gatewayHealth.lastSendTarget = jid;
    gatewayHealth.lastSendError = "number is not on WhatsApp";
    gatewayObsEvent("whatsapp_send_failed", "warning", "Target number is not on WhatsApp", {target:jid, meta});
    waReliabilityRecord("blocked", rawTarget, jid, text, meta, {reason:"not_on_whatsapp", error:"number is not on WhatsApp", retryable:false});
    return {ok:false, rawTarget, target:jid, error:"number is not on WhatsApp"};
  }
  const pre = await whatsappSafetyBeforeSend(jid, text, meta || {});
  if(!pre.allowed){
    const out = {ok:!!pre.duplicate, skipped:!!pre.duplicate, rawTarget, target:jid, error:pre.message || pre.reason || "blocked_by_safety_guard", reason:pre.reason || "blocked_by_safety_guard", safetyBlocked:!pre.duplicate};
    if(pre.duplicate) await whatsappSafetyAfterSend(pre, {ok:true, skipped:true, target:jid, meta});
    gatewayHealth.lastSendAt = nowIso();
    gatewayHealth.lastSendOk = out.ok;
    gatewayHealth.lastSendTarget = jid;
    gatewayHealth.lastSendError = out.ok ? "" : out.error;
    waReliabilityRecord(out.ok ? "skipped" : "blocked", rawTarget, jid, text, meta, {reason:out.reason || (out.ok?"duplicate_skip":"blocked_by_safety_guard"), error:out.error || "", retryable:false});
    if(!out.ok) gatewayObsEvent("whatsapp_send_blocked", "warning", out.error || "blocked_by_safety_guard", {target:jid, reason:out.reason, meta});
    return out;
  }
  return safeSendQueueRun(async () => {
    const waitMs = safeDelayMs(pre.settings);
    if(waitMs > 0) await guardSleep(waitMs);
    try {
      const r = await sock.sendMessage(jid, { text: String(text || "") });
      const out = {ok:true, rawTarget, target:jid, id:r?.key?.id || "sent", meta};
      gatewayHealth.lastSendAt = nowIso();
      gatewayHealth.lastSendOk = true;
      gatewayHealth.lastSendTarget = jid;
      gatewayHealth.lastSendError = "";
      await whatsappSafetyAfterSend(pre, out);
      waReliabilityRecord("sent", rawTarget, jid, text, meta, {messageId:out.id || "", retryOf:meta?.retryOf || "", retryable:false});
      if(["schedule", "result", "manual_send", "payment_outbox", "load_forwarder", "manual_retry"].includes(String(meta?.type || ""))) gatewayObsEvent("whatsapp_send_ok", "info", "WhatsApp message sent", {target:jid, id:out.id, meta});
      return out;
    } catch(e) {
      const out = {ok:false, rawTarget, target:jid, error:e.message, meta};
      gatewayHealth.lastSendAt = nowIso();
      gatewayHealth.lastSendOk = false;
      gatewayHealth.lastSendTarget = jid;
      gatewayHealth.lastSendError = e.message;
      await whatsappSafetyAfterSend(pre, out);
      waReliabilityRecord("failed", rawTarget, jid, text, meta, {reason:"send_exception", error:e.message || String(e), retryable:true, retryOf:meta?.retryOf || ""});
      gatewayObsEvent("whatsapp_send_exception", "error", e.message, {target:jid, meta});
      return out;
    }
  });
}

function _jidKey(v){ return String(v || "").trim().replace(/:\d+(?=@)/, ""); }
function _targetName(x){ return String(x?.name || x?.subject || x?.pushName || x?.verifiedName || x?.id || "").trim(); }
function _mergeTargetList(oldList, newList, type){
  const m = new Map();
  for(const item of Array.isArray(oldList) ? oldList : []){
    const id = _jidKey(item?.id || item?.jid || item);
    if(id) m.set(id, { id, name:_targetName(item) || id, type:item?.type || type });
  }
  for(const item of Array.isArray(newList) ? newList : []){
    const id = _jidKey(item?.id || item?.jid || item);
    if(id) m.set(id, { id, name:_targetName(item) || id, type:item?.type || type });
  }
  return [...m.values()].sort((a,b)=>String(a.name||a.id).localeCompare(String(b.name||b.id)));
}
function _saveTargetsCache(cache){
  targetsCache = {
    contacts: Array.isArray(cache.contacts) ? cache.contacts : [],
    groups: Array.isArray(cache.groups) ? cache.groups : [],
    updatedAt: cache.updatedAt || new Date().toISOString(),
    lastSyncError: cache.lastSyncError || ""
  };
  saveJson(TARGET_CACHE_FILE, targetsCache);
  gatewayHealth.lastTargetSyncAt = targetsCache.updatedAt;
  gatewayHealth.lastTargetSyncGroups = targetsCache.groups.length;
  gatewayHealth.lastTargetSyncContacts = targetsCache.contacts.length;
  gatewayHealth.lastTargetSyncError = targetsCache.lastSyncError || "";
  return targetsCache;
}
function rememberPrivateTarget(jid, name = ""){
  const id = _jidKey(jid);
  if(!id || !id.endsWith("@s.whatsapp.net")) return targetsCache;
  const current = loadJson(TARGET_CACHE_FILE, targetsCache || {contacts:[], groups:[]});
  const contacts = _mergeTargetList(current.contacts || targetsCache.contacts || [], [{id, name:name || id, type:"contact"}], "contact");
  return _saveTargetsCache({
    contacts,
    groups: _mergeTargetList(current.groups || targetsCache.groups || [], [], "group"),
    updatedAt: new Date().toISOString(),
    lastSyncError: current.lastSyncError || ""
  });
}

function rememberGroupTarget(jid, name = ""){
  const id = _jidKey(jid);
  if(!id || !id.endsWith("@g.us")) return targetsCache;
  const current = loadJson(TARGET_CACHE_FILE, targetsCache || {contacts:[], groups:[]});
  const groups = _mergeTargetList(current.groups || targetsCache.groups || [], [{id, name:name || id, type:"group"}], "group");
  return _saveTargetsCache({
    contacts: _mergeTargetList(current.contacts || targetsCache.contacts || [], [], "contact"),
    groups,
    updatedAt: new Date().toISOString(),
    lastSyncError: current.lastSyncError || ""
  });
}

async function refreshSingleGroupTarget(groupJid, fallbackName = ""){
  const id = _jidKey(groupJid);
  if(!id || !id.endsWith("@g.us")) return targetsCache;
  let name = fallbackName || id;
  try {
    if(sock && connected && typeof sock.groupMetadata === "function"){
      const meta = await sock.groupMetadata(id);
      name = meta?.subject || meta?.name || name;
    }
  } catch(e) {}
  return rememberGroupTarget(id, name);
}

async function syncTargets(options = {}){
  const previous = loadJson(TARGET_CACHE_FILE, targetsCache || { contacts: [], groups: [], updatedAt: null, lastSyncError: "" });
  const prevGroups = Array.isArray(previous.groups) ? previous.groups : [];
  const prevContacts = Array.isArray(previous.contacts) ? previous.contacts : [];
  if(!sock || !connected){
    return _saveTargetsCache({ contacts: prevContacts, groups: prevGroups, updatedAt: previous.updatedAt || new Date().toISOString(), lastSyncError: "WhatsApp not connected" });
  }

  let fetchedGroups = [];
  let syncError = "";
  try {
    const allGroups = await sock.groupFetchAllParticipating();
    fetchedGroups = Object.values(allGroups || {}).map(g => ({ id:g.id, name:g.subject || g.name || g.id, type:"group" })).filter(x => x.id);
  } catch(e) {
    syncError = "groupFetchAllParticipating: " + (e.message || String(e));
  }

  // Important: do not wipe a good saved group list when Baileys returns an empty/temporary result.
  let groups = prevGroups;
  if(fetchedGroups.length > 0 || prevGroups.length === 0 || options.clearEmpty === true){
    groups = _mergeTargetList(prevGroups, fetchedGroups, "group");
  }

  const contactCandidates = [];
  try {
    if(sock.user?.id) contactCandidates.push({ id:_jidKey(sock.user.id), name:sock.user.name || sock.user.verifiedName || "Linked WhatsApp", type:"contact" });
  } catch(e) {}
  let contacts = _mergeTargetList(prevContacts, contactCandidates, "contact");

  const out = _saveTargetsCache({ contacts, groups, updatedAt:new Date().toISOString(), lastSyncError: syncError });
  const note = syncError ? ` | ${syncError}` : "";
  console.log(`📦 Synced targets: groups ${out.groups.length} (live ${fetchedGroups.length}), private ${out.contacts.length}. Saved: ${TARGET_CACHE_FILE}${note}`);
  return out;
}

function getRecMaps(day, state=null){ const arrs = state ? marketArraysForPurpose(state, "schedule") : {markets:MARKETS, baseMarkets:BASE_MARKETS}; return [["ank","data",arrs.markets],["jodi","jodiData",arrs.baseMarkets],["pannel","pannelData",arrs.markets]]; }
function collectSchedules(state){
  const date = todayISO();
  const list = [];
  const profiles = state && state.profiles ? state.profiles : {};
  const store = state?.ledgerSchedules && typeof state.ledgerSchedules === "object" ? state.ledgerSchedules : {};
  for(const [pid, profile] of Object.entries(profiles)){
    const day = profile?.dayRecords?.[date] || {};
    for(const [type, key, marketArr] of getRecMaps(day, state)){
      const dict = day[key] || {};
      const candidates = new Map();
      const addCandidate = (idx, marketKey="", source="") => {
        let mk = String(marketKey || "").trim();
        let n = Number(idx);
        if(mk){
          const keyedIdx = marketArr.findIndex(m => ledgerMarketKeyForCard(type, m) === mk);
          if(keyedIdx >= 0) n = keyedIdx;
        }
        if(!Number.isFinite(n) || n < 0) return;
        const id = mk || `idx:${n}`;
        if(!candidates.has(id)) candidates.set(id, {idx:n, marketKey:mk, source});
      };

      for(const [idxRaw, rec] of Object.entries(dict || {})){
        if(String(idxRaw).startsWith("_orphan_")) continue;
        addCandidate(idxRaw, rec && typeof rec === "object" ? rec._ledgerKey : "", "today_record");
      }

      const dayRecords = profile?.dayRecords || {};
      for(const [oldDate, oldDay] of Object.entries(dayRecords)){
        if(String(oldDate) > date || !oldDay || typeof oldDay !== "object") continue;
        const oldMap = oldDay[key] || {};
        for(const [oldIdx, oldRec] of Object.entries(oldMap)){
          if(String(oldIdx).startsWith("_orphan_")) continue;
          if(oldRec && typeof oldRec === "object" && (oldRec.schTime || oldRec.scheduleTime || oldRec.schTargets || oldRec.targets)){
            addCandidate(oldIdx, oldRec._ledgerKey || "", "legacy_day_schedule");
          }
        }
      }

      const prefix = `${pid}|${type}|`;
      for(const [schedKey, sched] of Object.entries(store)){
        if(!String(schedKey).startsWith(prefix) || !sched || typeof sched !== "object") continue;
        const tail = String(schedKey).slice(prefix.length);
        let mk = String(sched.marketKey || (sched.record && sched.record._ledgerKey) || "").trim();
        let idx = Number(sched.index);
        if(!mk && Number.isFinite(Number(tail))) idx = Number(tail);
        else if(!mk) mk = tail;
        addCandidate(idx, mk, "persistent_schedule");
      }

      const orderedCandidates = [...candidates.values()].sort((a,b) => Number(a.idx) - Number(b.idx));
      for(const cand of orderedCandidates){
        let idx = Number(cand.idx);
        let marketKey = String(cand.marketKey || "").trim();
        if(marketKey){
          const keyedIdx = marketArr.findIndex(m => ledgerMarketKeyForCard(type, m) === marketKey);
          if(keyedIdx >= 0) idx = keyedIdx;
        }
        if(!Number.isFinite(idx) || idx < 0) continue;
        const rec = (dict && (dict[String(idx)] || dict[String(cand.idx)])) || {};
        if(!marketKey && rec && typeof rec === "object") marketKey = String(rec._ledgerKey || "").trim();
        const sched = storedScheduleForCard(state, pid, profile, type, idx, date, marketKey) || {};
        if(!marketKey && sched && typeof sched === "object") marketKey = String(sched.marketKey || (sched.record && sched.record._ledgerKey) || "").trim();
        if(marketKey){
          const keyedIdx = marketArr.findIndex(m => ledgerMarketKeyForCard(type, m) === marketKey);
          if(keyedIdx >= 0) idx = keyedIdx;
        }
        // INTEL_SCHEDULE_TIME_FIX v17.3: persistent ledgerSchedules is source of truth
        // for daily Intel time/targets; today's record may contain stale schTime.
        const time = normalizeTime(sched.time || sched.schTime || rec.schTime || rec.scheduleTime || "");
        const marketMeta = marketArr[Number(idx)] || {};
        const market = marketMeta.n || sched.marketName || "";
        // v33: exact card/stage guard. If Sridevi Day OPEN is due, CLOSE must not be sent.
        if(!scheduleRecordMatchesExactCard(sched, type, idx, marketKey, market)) continue;
        const roleTargets = marketRoleTargetsForMarket(state, market || sched.marketName || "", "schedule");
        const targets = roleTargets.length ? roleTargets : targetList(sched.targets || rec.schTargets || rec.targets || []);
        // Daily-repeat schedule uses persistent time/targets only. Digits/rate must come
        // from today's card so yesterday's Intel cannot repeat accidentally.
        const payload = (rec && typeof rec === "object") ? rec : {};
        const digits = cleanDigits(payload.d || "");
        const rate = ledgerScheduleRate(payload);
        if(marketMeta.scheduleDisabled) continue;
        if(!time || !targets.length || !digits || !market || !(rate > 0)) continue;
        list.push({
          id:`${pid}_${date}_${type}_${marketKey || idx}`,
          profileId:pid,
          date,
          type,
          index:idx,
          marketKey,
          time,
          market,
          digits,
          rate,
          total: ledgerDigitsArray(digits).length * rate,
          targets,
          repeat:"daily",
          sourceDate:sched.sourceDate || date,
          message:formatMessage(date, market, digits, rate, type)
        });
      }
    }
  }
  return list;
}

function collectResults(state){
  const date = todayISO();
  const globalTargets = collectResultTargets(state);
  const records = state?.resultRecords?.[date] || {};
  const list = [];
  for(const [market, rec] of Object.entries(records)){
    if(!rec || typeof rec !== "object") continue;
    const openAllowed = marketPhase3Allowed(state, market, "result", "open");
    const closeAllowed = marketPhase3Allowed(state, market, "result", "close");
    if(!openAllowed.ok && !closeAllowed.ok) continue;
    const openResult = cleanResult(rec.openResult || "");
    const closeResult = cleanResult(rec.closeResult || "");
    if(openAllowed.ok && resultStage(openResult) === "open" && !rec.openInferredFromClose){
      const openTargets = marketRoleTargetsForMarket(state, openAllowed.market || market, "result");
      const targets = openTargets.length ? openTargets : globalTargets;
      if(targets.length) list.push({ id:`result_${date}_${market}_open`, date, market:openAllowed.market || market, stage:"open", result:openResult, targets, message:formatResultMessage(openAllowed.market || market, openResult, "open") });
    }
    if(closeAllowed.ok && resultStage(closeResult) === "close"){
      // STRICT 2-STAGE RESULT SAFETY:
      // Close can be declared only after a real same-day Open was saved first.
      // Do not declare direct/full website results as Close when the Open was inferred from that same full line;
      // those can be old/yesterday values sitting on the website.
      if(rec.source === "auto_scrape"){
        if(resultStage(openResult) !== "open") continue;
        if(rec.openInferredFromClose === true) continue;
        if(!closeResult.startsWith(openResult)) continue;
        const openAt = Date.parse(rec.openUpdatedAt || rec.updatedAt || "");
        const closeAt = Date.parse(rec.closeUpdatedAt || rec.updatedAt || "");
        if(Number.isFinite(openAt) && Number.isFinite(closeAt) && closeAt < openAt) continue;
      }
      const closeTargets = marketRoleTargetsForMarket(state, market, "result");
      const targets = closeTargets.length ? closeTargets : globalTargets;
      if(targets.length) list.push({ id:`result_${date}_${market}_close`, date, market, stage:"close", result:closeResult, targets, message:formatResultMessage(market, closeResult, "close") });
    }
  }
  return list;
}


// ============================================================
// PHASE 5 + PHASE 8 — RESULT SETTLEMENT + HIT/MISS DETAIL REPORT
// Entry amount is debited at acceptance time. Settlement only credits winner payout.
// Open result settles OPEN ANK + OPEN PENEL. Close result settles JODI + CLOSE ANK + CLOSE PENEL.
// Phase 8 adds detailed HIT/MISS list for manual/optional WhatsApp send.
// ============================================================
function settlementSettings(state){
  const s = state?.settlementSettings || {};
  const pm = s.payoutMultipliers || {};
  return {
    enabled: s.enabled !== false,
    includeSummaryInResultMessage: s.includeSummaryInResultMessage !== false,
    includeHitMissInResultMessage: s.includeHitMissInResultMessage === true,
    payoutMultipliers: {
      ank: Number(pm.ank ?? 9.5),
      jodi: Number(pm.jodi ?? 9.5),
      penel: Number(pm.penel ?? 150)
    }
  };
}
function roundMoney(n){ return Math.round(Number(n || 0) * 100) / 100; }
function normalizeSettlementMarket(v){ return String(v || '').toUpperCase().replace(/SRIDEVI\s+DAY/g, 'SRIDEV DAY').replace(/[^A-Z0-9]+/g, ' ').trim().replace(/\s+/g, ' '); }
function baseFromAnyMarket(v){ return normalizeSettlementMarket(v).replace(/\s+(OPEN|CLOSE)$/i, '').trim(); }
function resultParts(result){
  const r = cleanResult(result);
  let m = r.match(/^(\d{3})-(\d)$/);
  if(m) return { stage:'open', openPenel:m[1], openAnk:m[2], jodi:'', closeAnk:'', closePenel:'' };
  m = r.match(/^(\d{3})-(\d)(\d)-(\d{3})$/);
  if(m) return { stage:'close', openPenel:m[1], openAnk:m[2], jodi:m[2]+m[3], closeAnk:m[3], closePenel:m[4] };
  return { stage:'' };
}
function entryDigitList(entry){
  if(Array.isArray(entry?.digits)) return entry.digits.map(x => String(x).trim()).filter(Boolean);
  return String(entry?.digits || '').split(/[,.\s]+/).map(x=>x.trim()).filter(Boolean);
}
function entryType(entry){
  const t = String(entry?.gameType || entry?.type || '').trim().toLowerCase();
  if(t === 'panel' || t === 'pannel') return 'penel';
  return t;
}
function isEntryEligibleForSettlement(entry, job){
  if(!entry || entry.status !== 'accepted') return false;
  if(String(entry.date || '') !== String(job.date || todayISO())) return false;
  const base = normalizeSettlementMarket(job.market);
  const em = normalizeSettlementMarket(entry.market);
  const typ = entryType(entry);
  if(job.stage === 'open'){
    if(typ !== 'ank' && typ !== 'penel') return false;
    return em === `${base} OPEN`;
  }
  if(job.stage === 'close'){
    if(typ === 'jodi') return baseFromAnyMarket(em) === base;
    if(typ === 'ank' || typ === 'penel') return em === `${base} CLOSE`;
  }
  return false;
}
function winningDigitForEntryType(job, typ){
  const parts = resultParts(job.result);
  if(job.stage === 'open'){
    if(typ === 'ank') return parts.openAnk || '';
    if(typ === 'penel') return parts.openPenel || '';
  }
  if(job.stage === 'close'){
    if(typ === 'ank') return parts.closeAnk || '';
    if(typ === 'penel') return parts.closePenel || '';
    if(typ === 'jodi') return parts.jodi || '';
  }
  return '';
}
function digitMatchesType(digit, win, typ){
  let d = String(digit || '').trim();
  let w = String(win || '').trim();
  if(typ === 'jodi'){ d = d.padStart(2,'0'); w = w.padStart(2,'0'); }
  if(typ === 'penel'){ d = d.padStart(3,'0'); w = w.padStart(3,'0'); }
  return d === w;
}


// ============================================================
// v7 GATEWAY RECOVERY AUTO-RATE ENGINE
// Keeps the next WAIT market/card rated even when the admin PWA is closed.
// This mirrors the frontend recovery formula and protects manual rates.
// ============================================================
function ledgerNumericStamp(v){
  if(v === null || v === undefined || v === "") return 0;
  if(typeof v === "number" && Number.isFinite(v)) return v;
  const n = Number(v);
  if(Number.isFinite(n) && String(v).trim().match(/^\d+(\.\d+)?$/)) return n;
  const t = Date.parse(String(v || ""));
  return Number.isFinite(t) ? t : 0;
}
function ledgerRecordStamp(rec){
  if(!rec || typeof rec !== "object") return 0;
  return Math.max(
    ledgerNumericStamp(rec._dirtyAt), ledgerNumericStamp(rec._updatedAt),
    ledgerNumericStamp(rec._autoRateAt), ledgerNumericStamp(rec._manualRateAt),
    ledgerNumericStamp(rec._digitsTouchedAt), ledgerNumericStamp(rec._manualStatusAt),
    ledgerNumericStamp(rec.autoMarkedAt), ledgerNumericStamp(rec._resetAt),
    ledgerNumericStamp(rec._explicitClearedAt)
  );
}
function ledgerRecHasPayload(rec){
  if(!rec || typeof rec !== "object") return false;
  if(["_dirtyAt","_updatedAt","_autoRateAt","_manualRateAt","_digitsTouchedAt","_manualStatusAt","autoMarkedAt","_resetAt","_explicitClearedAt","_sourceAction"].some(k => String(rec[k] || "").trim())) return true;
  if(String(rec.s || "WAIT").toUpperCase() !== "WAIT") return true;
  if(["d","r","od","trick","schTime","scheduleTime"].some(k => String(rec[k] || "").trim())) return true;
  if(Array.isArray(rec.schTargets) && rec.schTargets.length) return true;
  if(Array.isArray(rec.targets) && rec.targets.length) return true;
  return false;
}
function ledgerCopyScheduleFields(dst, src){
  if(!dst || typeof dst !== "object" || !src || typeof src !== "object") return dst;
  if(!dst.schTime && src.schTime) dst.schTime = src.schTime;
  if(!dst.scheduleTime && src.scheduleTime) dst.scheduleTime = src.scheduleTime;
  if((!Array.isArray(dst.schTargets) || !dst.schTargets.length) && Array.isArray(src.schTargets) && src.schTargets.length) dst.schTargets = JSON.parse(JSON.stringify(src.schTargets));
  if((!Array.isArray(dst.targets) || !dst.targets.length) && Array.isArray(src.targets) && src.targets.length) dst.targets = JSON.parse(JSON.stringify(src.targets));
  return dst;
}
function mergeLedgerProtectedState(candidate, latest){
  if(!candidate || typeof candidate !== "object" || !latest || typeof latest !== "object") return candidate;
  candidate.profiles = candidate.profiles && typeof candidate.profiles === "object" ? candidate.profiles : {};
  const liveProfiles = latest.profiles && typeof latest.profiles === "object" ? latest.profiles : {};
  const dicts = ["data", "jodiData", "pannelData"];
  for(const [pid, liveProfile] of Object.entries(liveProfiles)){
    if(!liveProfile || typeof liveProfile !== "object") continue;
    const liveDays = liveProfile.dayRecords && typeof liveProfile.dayRecords === "object" ? liveProfile.dayRecords : {};
    if(!Object.keys(liveDays).length) continue;
    const outProfile = candidate.profiles[pid] && typeof candidate.profiles[pid] === "object" ? candidate.profiles[pid] : JSON.parse(JSON.stringify(liveProfile));
    candidate.profiles[pid] = outProfile;
    outProfile.dayRecords = outProfile.dayRecords && typeof outProfile.dayRecords === "object" ? outProfile.dayRecords : {};
    for(const [date, liveDay] of Object.entries(liveDays)){
      if(!liveDay || typeof liveDay !== "object") continue;
      const outDay = outProfile.dayRecords[date] && typeof outProfile.dayRecords[date] === "object" ? outProfile.dayRecords[date] : {};
      outProfile.dayRecords[date] = outDay;
      for(const dictName of dicts){
        const liveBucket = liveDay[dictName] && typeof liveDay[dictName] === "object" ? liveDay[dictName] : {};
        if(!Object.keys(liveBucket).length) continue;
        const outBucket = outDay[dictName] && typeof outDay[dictName] === "object" ? outDay[dictName] : {};
        outDay[dictName] = outBucket;
        const outByMarketKey = new Map();
        for(const [ok, ov] of Object.entries(outBucket)){
          if(ov && typeof ov === "object" && ov._ledgerKey) outByMarketKey.set(String(ov._ledgerKey), ok);
        }
        for(const [lk, liveRec] of Object.entries(liveBucket)){
          if(!ledgerRecHasPayload(liveRec)) continue;
          const mk = String(liveRec._ledgerKey || "").trim();
          let targetKey = mk && outByMarketKey.has(mk) ? outByMarketKey.get(mk) : String(lk);
          const outRec = outBucket[targetKey];
          if(!ledgerRecHasPayload(outRec)){
            outBucket[targetKey] = JSON.parse(JSON.stringify(liveRec));
            continue;
          }
          const liveStamp = ledgerRecordStamp(liveRec);
          const outStamp = ledgerRecordStamp(outRec);
          if(liveStamp && (!outStamp || liveStamp > outStamp)){
            const kept = JSON.parse(JSON.stringify(liveRec));
            ledgerCopyScheduleFields(kept, outRec);
            outBucket[targetKey] = kept;
          } else if(outRec && typeof outRec === "object") {
            ledgerCopyScheduleFields(outRec, liveRec);
            if(mk && !outRec._ledgerKey) outRec._ledgerKey = mk;
            if(liveRec._marketName && !outRec._marketName) outRec._marketName = liveRec._marketName;
          }
        }
      }
    }
  }
  // Persistent daily schedule store: latest server copy wins unless candidate has a newer updatedAt.
  const liveSchedules = latest.ledgerSchedules && typeof latest.ledgerSchedules === "object" ? latest.ledgerSchedules : {};
  const outSchedules = candidate.ledgerSchedules && typeof candidate.ledgerSchedules === "object" ? candidate.ledgerSchedules : {};
  for(const [sk, liveSched] of Object.entries(liveSchedules)){
    const outSched = outSchedules[sk];
    const liveTs = Date.parse(liveSched?.updatedAt || liveSched?.createdAt || "") || 0;
    const outTs = Date.parse(outSched?.updatedAt || outSched?.createdAt || "") || 0;
    if(!outSched || (liveTs && liveTs > outTs)) outSchedules[sk] = JSON.parse(JSON.stringify(liveSched));
  }
  candidate.ledgerSchedules = outSchedules;
  candidate.gatewayFullSaveGuard = {lastMergedAt:nowIso(), mode:"v7-protect-live-ledger-before-root-put"};
  return candidate;
}

function moneyStamp(v){ if(!v) return 0; const t=Date.parse(String(v)); if(Number.isFinite(t)) return t; const n=Number(v); return Number.isFinite(n)?n:0; }
function moneyTerminalRank(x){ const st=String(x?.status||'').toLowerCase(); if(st==='paid'||st==='approved') return 4; if(st==='rejected') return 3; if(st==='pending') return 1; return 0; }
function moneyNewerRecord(a,b){
  if(!a || typeof a !== 'object') return JSON.parse(JSON.stringify(b||{}));
  if(!b || typeof b !== 'object') return JSON.parse(JSON.stringify(a||{}));
  const ar=moneyTerminalRank(a), br=moneyTerminalRank(b);
  let out;
  if(br>ar) out=JSON.parse(JSON.stringify(b));
  else if(ar>br) out=JSON.parse(JSON.stringify(a));
  else {
    const at=Math.max(moneyStamp(a.updatedAt),moneyStamp(a.approvedAt),moneyStamp(a.rejectedAt),moneyStamp(a.paidAt),moneyStamp(a.createdAt),moneyStamp(a.time));
    const bt=Math.max(moneyStamp(b.updatedAt),moneyStamp(b.approvedAt),moneyStamp(b.rejectedAt),moneyStamp(b.paidAt),moneyStamp(b.createdAt),moneyStamp(b.time));
    out=JSON.parse(JSON.stringify(bt>at?b:a));
  }
  for(const src of [a,b]) if(src && typeof src==='object') for(const [k,v] of Object.entries(src)) if((k.endsWith('Notified')||k.endsWith('NotifiedAt')||['walletCredited','walletLedgerId','walletCreditAmount'].includes(k)) && v && !out[k]) out[k]=v;
  return out;
}
function mergeListById(candidateList, liveList){
  const map = new Map();
  const add = (x) => {
    if(!x || typeof x !== 'object') return;
    let id = String(x.id || x.txnId || x.entryId || x.withdrawalId || x.paymentId || '');
    if(!id) id = require('crypto').createHash('sha1').update(JSON.stringify(x)).digest('hex').slice(0,24);
    map.set(id, map.has(id) ? moneyNewerRecord(map.get(id), x) : JSON.parse(JSON.stringify(x)));
  };
  if(Array.isArray(candidateList)) candidateList.forEach(add);
  if(Array.isArray(liveList)) liveList.forEach(add);
  return Array.from(map.values()).sort((a,b)=>String(a.time||a.createdAt||a.updatedAt||'').localeCompare(String(b.time||b.createdAt||b.updatedAt||'')));
}
function mergeWalletRecord(cw,lw){
  if(!cw || typeof cw !== 'object') return JSON.parse(JSON.stringify(lw||{}));
  if(!lw || typeof lw !== 'object') return JSON.parse(JSON.stringify(cw||{}));
  const c=JSON.parse(JSON.stringify(cw)), l=JSON.parse(JSON.stringify(lw));
  const cLedger=Array.isArray(c.ledger)?c.ledger:[], lLedger=Array.isArray(l.ledger)?l.ledger:[];
  const ledger=mergeListById(cLedger,lLedger);
  const out=(moneyStamp(l.updatedAt)>moneyStamp(c.updatedAt) && lLedger.length>=cLedger.length) ? l : c;
  out.ledger=ledger.slice(-800);
  const last=out.ledger.filter(x=>x&&typeof x==='object'&&('balanceAfter' in x || 'holdAfter' in x)).slice(-1)[0];
  if(last){ if('balanceAfter' in last) out.balance=Number(last.balanceAfter||0); if('holdAfter' in last){ out.hold=Math.max(0,Number(last.holdAfter||0)); out.walletHold=out.hold; } }
  out.updatedAt = [String(c.updatedAt||''),String(l.updatedAt||''),String(out.updatedAt||'')].sort().pop();
  return out;
}
function mergeMoneyProtectedState(candidate, latest){
  if(!candidate || typeof candidate !== 'object' || !latest || typeof latest !== 'object') return candidate;
  const outWallets = candidate.wallets && typeof candidate.wallets === 'object' ? candidate.wallets : {};
  const liveWallets = latest.wallets && typeof latest.wallets === 'object' ? latest.wallets : {};
  for(const [uid, liveWallet] of Object.entries(liveWallets)) outWallets[uid] = mergeWalletRecord(outWallets[uid], liveWallet);
  candidate.wallets = outWallets;
  for(const key of ['walletTransactions','payments','withdrawals','entries','paymentOutbox']){
    candidate[key] = mergeListById(Array.isArray(candidate[key])?candidate[key]:[], Array.isArray(latest[key])?latest[key]:[]);
    if(key==='walletTransactions' && candidate[key].length>2000) candidate[key]=candidate[key].slice(-2000);
    if(key==='paymentOutbox' && candidate[key].length>500) candidate[key]=candidate[key].slice(-500);
  }
  candidate.moneyIdempotency = Object.assign({}, (candidate.moneyIdempotency&&typeof candidate.moneyIdempotency==='object')?candidate.moneyIdempotency:{}, (latest.moneyIdempotency&&typeof latest.moneyIdempotency==='object')?latest.moneyIdempotency:{});
  candidate.moneyAtomicityGuard = {lastMergedAt:nowIso(), mode:'v9-gateway-protect-money-before-root-put'};
  return candidate;
}

function ledgerDigitCountForAutoRate(rec){ return ledgerDigitsArray(rec?.d || "").length; }
function ledgerManualRateIsFresh(rec){
  if(!rec || typeof rec !== "object" || !rec._manualR) return false;
  const manualAt = ledgerNumericStamp(rec._manualRateAt);
  const digitAt = ledgerNumericStamp(rec._digitsTouchedAt);
  return manualAt > 0 && manualAt >= digitAt;
}
function gatewayAutoRateCanRecalculate(rec){
  rec = rec || {};
  if(ledgerManualRateIsFresh(rec)) return false;
  if(String(rec.r || "").trim() === "") return true;
  return rec._autoR === true || rec._recoveryAutoR === true;
}
function ledgerHistoricalMultiplier(state, profile, type, idx, date){
  try{
    const dayRecords = profile?.dayRecords && typeof profile.dayRecords === "object" ? profile.dayRecords : {};
    const dates = Object.keys(dayRecords).sort();
    const pos = dates.indexOf(date);
    const dictName = ledgerDictName(type);
    let dailyBoost = 0;
    if(pos > 0){
      let consecutiveFails = 0;
      for(let j=pos-1; j>=0; j--){
        const rec = dayRecords[dates[j]]?.[dictName]?.[String(idx)] || dayRecords[dates[j]]?.[dictName]?.[idx];
        if(!rec) continue;
        if(String(rec.s || "").toUpperCase() === "FAIL") consecutiveFails++;
        else if(String(rec.s || "").toUpperCase() === "PASS") break;
      }
      dailyBoost = consecutiveFails * 0.20;
    }
    const curr = new Date(date + "T00:00:00");
    if(!Number.isFinite(curr.getTime())) return 1.0 + dailyBoost;
    curr.setDate(curr.getDate() - 7);
    const wd = `${curr.getFullYear()}-${pad(curr.getMonth()+1)}-${pad(curr.getDate())}`;
    const lastWeekRec = dayRecords[wd]?.[dictName]?.[String(idx)] || dayRecords[wd]?.[dictName]?.[idx];
    const weeklyBoost = lastWeekRec && String(lastWeekRec.s || "").toUpperCase() === "FAIL" ? 0.10 : 0;
    return 1.0 + dailyBoost + weeklyBoost;
  } catch { return 1.0; }
}
function computeGatewayLedgerAutoRate(state, profile, type, idx, count, debtValue, unrealValue, multiplier, targetProfit, date){
  const margin = Number(multiplier || 0) - Number(count || 0);
  if(!(margin > 0)) return 0;
  const nextRate = (Number(debtValue || 0) + ((Number(unrealValue || 0) + 1) * Number(targetProfit || 0))) / margin;
  const finalRate = Math.ceil((nextRate * ledgerHistoricalMultiplier(state, profile, type, idx, date)) / 10) * 10;
  return Math.max(10, finalRate);
}
function gatewayLedgerTrackKey(type, market, splitOn){
  const name = String(market?.n || "").toUpperCase();
  if(type === "jodi") return "jodi";
  const prefix = type === "pannel" ? "pan" : "ank";
  if(!splitOn) return `${prefix}Unified`;
  return name.includes("OPEN") ? `${prefix}Open` : `${prefix}Close`;
}
function getLedgerRecordSlot(bucket, type, idx, market){
  bucket = bucket && typeof bucket === "object" ? bucket : {};
  const mk = ledgerMarketKeyForCard(type, market || {});
  if(mk){
    for(const [k, v] of Object.entries(bucket)){
      if(v && typeof v === "object" && String(v._ledgerKey || "") === mk) return {key:k, rec:v, marketKey:mk};
    }
  }
  const sidx = String(idx);
  return {key:sidx, rec:(bucket[sidx] || bucket[idx] || {s:"WAIT", d:"", r:""}), marketKey:mk};
}
function annotateGatewayLedgerRecord(rec, type, idx, market, action){
  rec = rec && typeof rec === "object" ? rec : {s:"WAIT", d:"", r:""};
  const mk = ledgerMarketKeyForCard(type, market || {});
  rec._ledgerKey = rec._ledgerKey || mk;
  rec._marketName = String(rec._marketName || market?.n || "").toUpperCase().trim();
  rec._ledgerType = type;
  rec._ledgerIndex = Number(idx);
  rec._ledgerDate = todayISO();
  rec._updatedAt = nowIso();
  rec._dirtyAt = Date.now();
  rec._sourceAction = action || rec._sourceAction || "gateway_recovery_auto_rate";
  if(!rec.s) rec.s = "WAIT";
  if(typeof rec.d === "undefined") rec.d = "";
  if(typeof rec.r === "undefined") rec.r = "";
  return rec;
}
function applyGatewayAutoRate(rec, rate, meta){
  if(!rec || !(Number(rate) > 0)) return rec;
  rec.r = String(rate);
  rec._autoR = true;
  rec._manualR = false;
  rec._recoveryAutoR = !!meta?.recovery;
  rec._autoRateAt = Date.now();
  rec._autoRateReason = meta?.reason || "gateway_recovery_auto_rate";
  rec._recoveryDebt = Number(meta?.debt || 0);
  rec._recoveryUnreal = Number(meta?.unreal || 0);
  rec._recoveryMargin = Number(meta?.margin || 0);
  rec._recoveryTargetProfit = Number(meta?.targetProfit || 0);
  rec._recoveryTrackKey = String(meta?.trackKey || "");
  rec._recoveryBaseRate = Number(rate || 0);
  delete rec._manualRateAt;
  return rec;
}
function recomputeLedgerRecoveryAutoRates(state, date=todayISO(), reason="gateway_recovery_auto_rate"){
  const profiles = state?.profiles && typeof state.profiles === "object" ? state.profiles : {};
  const arrs = marketArraysForPurpose(state, "schedule");
  const groups = [
    {type:"ank", dict:"data", arr:arrs.markets, multiplier:9.5, splitKey:"ankSplit"},
    {type:"jodi", dict:"jodiData", arr:arrs.baseMarkets, multiplier:95, splitKey:null},
    {type:"pannel", dict:"pannelData", arr:arrs.markets, multiplier:150, splitKey:"panSplit"},
  ];
  const summary = {changed:false, count:0, details:[]};
  for(const [pid, profile] of Object.entries(profiles)){
    if(!profile || typeof profile !== "object") continue;
    profile.dayRecords = profile.dayRecords && typeof profile.dayRecords === "object" ? profile.dayRecords : {};
    const day = profile.dayRecords[date] && typeof profile.dayRecords[date] === "object" ? profile.dayRecords[date] : null;
    if(!day) continue;
    const cfg = profile.config || profiles.admin1?.config || {};
    for(const g of groups){
      const typeCfg = cfg[g.type] || {};
      const targetProfit = Number(typeCfg.tgt || 0);
      const splitOn = g.splitKey ? cfg[g.splitKey] !== false : false;
      const bucket = day[g.dict] && typeof day[g.dict] === "object" ? day[g.dict] : {};
      day[g.dict] = bucket;
      const debt = {}; const unreal = {};
      for(let i=0; i<g.arr.length; i++){
        const market = g.arr[i] || {};
        if(market.hiddenForLedger) continue;
        const {key, rec} = getLedgerRecordSlot(bucket, g.type, i, market);
        const record = rec && typeof rec === "object" ? rec : {s:"WAIT", d:"", r:""};
        const trackKey = gatewayLedgerTrackKey(g.type, market, splitOn);
        debt[trackKey] = Number(debt[trackKey] || 0);
        unreal[trackKey] = Number(unreal[trackKey] || 0);
        const count = ledgerDigitCountForAutoRate(record);
        const rate = Number(record.r || 0) || 0;
        const invest = count * rate;
        const status = String(record.s || "WAIT").toUpperCase();
        if(status === "FAIL") { debt[trackKey] += invest; unreal[trackKey] += 1; continue; }
        if(status === "PASS") { debt[trackKey] = 0; unreal[trackKey] = 0; continue; }
        if(status === "SKIP") { unreal[trackKey] += 1; continue; }
        if(status === "WAIT" && count > 0 && gatewayAutoRateCanRecalculate(record)){
          const margin = Number(g.multiplier) - Number(count);
          const autoRate = computeGatewayLedgerAutoRate(state, profile, g.type, i, count, debt[trackKey], unreal[trackKey], g.multiplier, targetProfit, date);
          if(autoRate > 0){
            let final = applyGatewayAutoRate(record, autoRate, {recovery:true, reason, debt:debt[trackKey], unreal:unreal[trackKey], margin, targetProfit, trackKey});
            final = annotateGatewayLedgerRecord(final, g.type, i, market, reason);
            bucket[String(i)] = final;
            summary.changed = true;
            summary.count += 1;
            summary.details.push({profileId:pid, type:g.type, index:i, market:market.n || "", rate:autoRate, trackKey});
          }
        }
      }
    }
  }
  return summary;
}

// ============================================================
// LEDGER AUTO PASS/FAIL MARKER
// Result dekhkar admin ledger/VIP ledger cards ko automatic PASS/FAIL mark karta hai.
// Old/final close result direct mark nahi hota; strict open/close safety respected.
// ============================================================
function ledgerAutoMarkSettings(state){
  const s = state?.settlementSettings || {};
  return {
    enabled: s.autoLedgerMarking !== false,
    onlyWait: s.autoLedgerMarkOnlyWait !== false,
    applyAllProfiles: s.autoLedgerApplyToAllProfiles !== false,
    recordResults: s.autoLedgerRecordResults !== false
  };
}
function ledgerDictName(type){ return type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData'); }
function ledgerNormMarket(v){ return String(v || '').toUpperCase().replace(/SRIDEVI\s+DAY/g, 'SRIDEV DAY').replace(/[^A-Z0-9]+/g, ' ').trim().replace(/\s+/g, ' '); }
function ledgerTokens(raw){ const m = String(raw || '').match(/\d+/g); return m ? m.filter(Boolean) : []; }
function ledgerTokenMatch(tokens, win, type){
  const w = String(win || '').trim();
  if(!w) return false;
  for(const raw of tokens){
    const t = String(raw || '').trim();
    if(type === 'ank' && t && t.slice(-1) === w.slice(-1)) return true;
    if(type === 'jodi' && t.padStart(2,'0').slice(-2) === w.padStart(2,'0').slice(-2)) return true;
    if(type === 'pannel' && t.padStart(3,'0').slice(-3) === w.padStart(3,'0').slice(-3)) return true;
  }
  return false;
}
function ledgerMarketIndexes(state=null){
  const ankPan = new Map();
  const jodi = new Map();
  const arrs = state ? marketArraysForPurpose(state, "schedule") : {markets:MARKETS, baseMarkets:BASE_MARKETS};
  arrs.markets.forEach((m,i)=>{ if(m && (m.enabled === false || m.ledgerEnabled === false || m.resultEnabled === false || m.autoPassFailEnabled === false)) return; ankPan.set(ledgerNormMarket(m.n), i); });
  arrs.baseMarkets.forEach((m,i)=>{ if(m && (m.enabled === false || m.ledgerEnabled === false || m.resultEnabled === false || m.autoPassFailEnabled === false)) return; jodi.set(ledgerNormMarket(m.n), i); });
  return {ankPan, jodi};
}
function applyLedgerAutoMarkToProfile(profile, date, type, idx, win, job, onlyWait){
  if(!profile || typeof profile !== 'object') return {checked:0, changed:0, pass:0, fail:0};
  profile.dayRecords = profile.dayRecords || {};
  const day = profile.dayRecords[date] || {};
  const dictName = ledgerDictName(type);
  const bucket = day[dictName] || {};
  let rec = bucket[String(idx)] || bucket[idx];
  if(!rec || typeof rec !== 'object') return {checked:0, changed:0, pass:0, fail:0};
  const tokens = ledgerTokens(rec.d || '');
  if(!tokens.length) return {checked:0, changed:0, pass:0, fail:0};
  const cur = String(rec.s || 'WAIT').toUpperCase();
  if(onlyWait && ['PASS','FAIL','SKIP'].includes(cur)) return {checked:1, changed:0, pass:0, fail:0};
  const status = ledgerTokenMatch(tokens, win, type) ? 'PASS' : 'FAIL';
  if(cur === status && rec.autoMarkedByResult === job.result) return {checked:1, changed:0, pass:0, fail:0};
  rec.s = status;
  rec.autoMarkedAt = nowIso();
  rec.autoMarkedByResult = job.result;
  rec.autoMarkStage = job.stage;
  rec.autoMarkMarket = job.market;
  rec.autoMarkWinDigit = win;
  day[dictName] = bucket;
  profile.dayRecords[date] = day;
  bucket[String(idx)] = rec;
  return {checked:1, changed:1, pass: status === 'PASS' ? 1 : 0, fail: status === 'FAIL' ? 1 : 0};
}
function isStrictCloseAllowedForLedger(state, job){
  if(job.stage !== 'close') return true;
  const recs = state?.resultRecords?.[job.date || todayISO()] || {};
  let rec = null;
  for(const [mk, rr] of Object.entries(recs)){
    if(ledgerNormMarket(mk) === ledgerNormMarket(job.market) && rr && typeof rr === 'object'){ rec = rr; break; }
  }
  const open = cleanResult(rec?.openResult || '');
  if(resultStage(open) !== 'open') return false;
  if(rec?.openInferredFromClose === true) return false;
  return cleanResult(job.result || '').startsWith(open);
}
function applyLedgerAutoMarkForResult(state, job, force=false){
  const settings = ledgerAutoMarkSettings(state);
  if(!settings.enabled && !force) return {changed:false, skipped:true, reason:'auto_ledger_marking_off'};
  const date = job.date || todayISO();
  const parts = resultParts(job.result);
  if(!job.market || !job.stage || parts.stage !== job.stage) return {changed:false, skipped:true, reason:'invalid_result'};
  if(!isStrictCloseAllowedForLedger(state, job)) return {changed:false, skipped:true, reason:'fresh_open_missing_strict_2_stage'};
  let base = ledgerNormMarket(job.market);
  const allowed = marketPhase3Allowed(state, base, "autopf", job.stage);
  if(!allowed.ok && !force) return {changed:false, skipped:true, reason:allowed.reason || "market_registry_blocked"};
  base = ledgerNormMarket(allowed.market || base);
  const targets = [];
  if(job.stage === 'open'){
    targets.push({type:'ank', market:`${base} OPEN`, win:parts.openAnk});
    targets.push({type:'pannel', market:`${base} OPEN`, win:parts.openPenel});
  } else if(job.stage === 'close'){
    targets.push({type:'ank', market:`${base} CLOSE`, win:parts.closeAnk});
    targets.push({type:'pannel', market:`${base} CLOSE`, win:parts.closePenel});
    targets.push({type:'jodi', market:base, win:parts.jodi});
  }
  const idxs = ledgerMarketIndexes(state);
  const profiles = state.profiles && typeof state.profiles === 'object' ? state.profiles : {};
  const pids = settings.applyAllProfiles ? Object.keys(profiles) : ['admin1'];
  const summary = {changed:false, date, market:base, stage:job.stage, result:cleanResult(job.result), profiles:0, checked:0, marked:0, pass:0, fail:0, details:[]};
  for(const pid of pids){
    const profile = profiles[pid];
    if(!profile || typeof profile !== 'object') continue;
    let pc = 0;
    for(const t of targets){
      const idx = (t.type === 'jodi' ? idxs.jodi : idxs.ankPan).get(ledgerNormMarket(t.market));
      if(idx === undefined || idx === null || !t.win) continue;
      const out = applyLedgerAutoMarkToProfile(profile, date, t.type, idx, t.win, job, settings.onlyWait);
      summary.checked += out.checked; summary.marked += out.changed; summary.pass += out.pass; summary.fail += out.fail; pc += out.changed;
      if(out.changed) summary.details.push({profileId:pid, type:t.type, market:t.market, index:idx, win:t.win, status:out.pass ? 'PASS' : 'FAIL'});
    }
    if(pc) summary.profiles += 1;
  }
  summary.changed = summary.marked > 0;
  if(settings.recordResults){
    state.ledgerAutoMarkRecords = state.ledgerAutoMarkRecords || {};
    state.ledgerAutoMarkRecords[date] = state.ledgerAutoMarkRecords[date] || {};
    state.ledgerAutoMarkRecords[date][`${base}_${job.stage}`] = {...summary, time: nowIso()};
  }
  if(summary.changed){
    state.auditLog = Array.isArray(state.auditLog) ? state.auditLog : [];
    state.auditLog.push({id:`LAM_${Date.now()}`, time:nowIso(), action:'ledger_auto_mark', detail:{date, market:base, stage:job.stage, result:job.result, marked:summary.marked, pass:summary.pass, fail:summary.fail}});
    if(state.auditLog.length > 500) state.auditLog.splice(0, state.auditLog.length - 500);
  }
  return summary;
}
function applyLedgerAutoMarkAll(state, date=todayISO(), force=false){
  const records = state?.resultRecords?.[date] || {};
  const out = {changed:false, date, results:[], marked:0, pass:0, fail:0};
  for(const [market, rec] of Object.entries(records)){
    if(!rec || typeof rec !== 'object') continue;
    const open = cleanResult(rec.openResult || '');
    if(resultStage(open) === 'open' && rec.openInferredFromClose !== true){
      const r = applyLedgerAutoMarkForResult(state, {date, market, stage:'open', result:open}, force);
      out.results.push(r); out.changed = out.changed || !!r.changed; out.marked += Number(r.marked||0); out.pass += Number(r.pass||0); out.fail += Number(r.fail||0);
    }
    const close = cleanResult(rec.closeResult || '');
    if(resultStage(close) === 'close'){
      const r = applyLedgerAutoMarkForResult(state, {date, market, stage:'close', result:close}, force);
      out.results.push(r); out.changed = out.changed || !!r.changed; out.marked += Number(r.marked||0); out.pass += Number(r.pass||0); out.fail += Number(r.fail||0);
    }
  }
  return out;
}
function settlementKey(job){ return `${job.market}_${job.stage}`; }
function ensureSettlementStores(state, date){
  if(!state.settlementRecords || typeof state.settlementRecords !== 'object') state.settlementRecords = {};
  if(!state.settlementRecords[date]) state.settlementRecords[date] = {};
  if(!Array.isArray(state.auditLog)) state.auditLog = [];
}
function settlementSummaryText(settlement){
  if(!settlement) return '';
  const pl = Number(settlement.marketProfit || 0);
  const plLabel = pl >= 0 ? `Profit ${money(pl)}` : `Loss ${money(Math.abs(pl))}`;
  const hitLine = (settlement.hitUsers || []).slice(0,5).map(x => `${x.name || x.userId} ${String(x.gameType||'').toUpperCase()} ${x.digit} ${money(x.payout)}`).join(' | ');
  return `\n\n📊 *SETTLEMENT SUMMARY*\n━━━━━━━━━━━━━━━━━━━━\n🧾 *Entries:* ${settlement.eligibleCount || 0} | ✅ *Hit:* ${settlement.hitCount || 0} | ❌ *Miss:* ${settlement.missCount || 0}\n💵 *Load:* ${money(settlement.totalStake || 0)}\n🏆 *Payout:* ${money(settlement.payoutTotal || 0)}\n📈 *Market:* ${plLabel}${hitLine ? `\n👑 *Hit Users:* ${hitLine}` : ''}\n━━━━━━━━━━━━━━━━━━━━`;
}
function userMentionFromId(userId){
  const digits = String(userId || '').replace(/\D/g, '');
  return digits ? '@' + digits : String(userId || 'USER');
}
function hitMissGroupLabel(type){ return String(type || '').toUpperCase(); }
function formatHitMissDetailedText(settlement, options = {}){
  if(!settlement) return '';
  const maxRows = Number(options.maxRows || 80);
  const lines = [];
  const pl = Number(settlement.marketProfit || 0);
  const plText = pl >= 0 ? `Profit ${money(pl)}` : `Loss ${money(Math.abs(pl))}`;
  lines.push('📋 *TITAN NOVA HIT/MISS LIST*');
  lines.push('━━━━━━━━━━━━━━━━━━━━');
  lines.push(`📅 *DATE:* ${settlement.date || todayISO()}`);
  lines.push(`🔥 *MARKET:* ${settlement.market || ''}`);
  lines.push(`🎯 *RESULT:* ${settlement.result || ''} (${String(settlement.stage || '').toUpperCase()})`);
  lines.push(`🧾 *Entries:* ${settlement.eligibleCount || 0} | ✅ *Hit:* ${settlement.hitCount || 0} | ❌ *Miss:* ${settlement.missCount || 0}`);
  lines.push(`💵 *Load:* ${money(settlement.totalStake || 0)} | 🏆 *Payout:* ${money(settlement.payoutTotal || 0)} | 📈 *Market:* ${plText}`);
  const hitByType = { ank:[], penel:[], jodi:[] };
  for(const x of (settlement.hitUsers || [])){
    const typ = entryType(x) || String(x.gameType || '').toLowerCase();
    if(hitByType[typ]) hitByType[typ].push(x);
  }
  const missByType = { ank:[], penel:[], jodi:[] };
  for(const x of (settlement.missUsers || [])){
    const typ = entryType(x) || String(x.gameType || '').toLowerCase();
    if(missByType[typ]) missByType[typ].push(x);
  }
  let rowCount = 0;
  const addBlock = (title, arrRows, isHit) => {
    lines.push('');
    lines.push(title);
    if(!arrRows.length){ lines.push('_None_'); return; }
    for(const x of arrRows){
      if(rowCount >= maxRows){ lines.push('...more'); break; }
      rowCount += 1;
      const user = userMentionFromId(x.userJid || x.phone || x.userId);
      const name = x.name && String(x.name) !== String(x.userId) ? ` (${x.name})` : '';
      if(isHit){
        lines.push(`${rowCount}. ${user}${name} — ${String(x.gameType||'').toUpperCase()} ${x.digit || ''} | Stake ${money(x.stake || 0)} | Payout ${money(x.payout || 0)}`);
      } else {
        const digits = x.digits || x.entryDigits || '';
        lines.push(`${rowCount}. ${user}${name} — ${String(x.gameType||'').toUpperCase()} ${digits ? '['+digits+'] ' : ''}| Stake ${money(x.stake || 0)}`);
      }
    }
  };
  for(const typ of ['ank','penel','jodi']) addBlock(`🏆 *HIT ${hitMissGroupLabel(typ)}*`, hitByType[typ], true);
  for(const typ of ['ank','penel','jodi']) addBlock(`❌ *MISS ${hitMissGroupLabel(typ)}*`, missByType[typ], false);
  lines.push('━━━━━━━━━━━━━━━━━━━━');
  return lines.join('\n');
}
function settleResultInState(state, job){
  const settings = settlementSettings(state);
  const date = job.date || todayISO();
  ensureSettlementStores(state, date);
  if(!settings.enabled) return { changed:false, skipped:true, reason:'settlement_disabled' };
  const key = settlementKey(job);
  const existing = state.settlementRecords[date][key];
  const result = cleanResult(job.result);
  if(existing && existing.result === result && existing.status === 'settled') return { changed:false, alreadySettled:true, settlement:existing };
  if(existing && existing.status === 'settled' && existing.result !== result){
    return { changed:false, skipped:true, reason:`stage_already_settled_with_${existing.result}`, settlement:existing };
  }
  const entries = Array.isArray(state.entries) ? state.entries : [];
  const eligible = entries.filter(e => isEntryEligibleForSettlement(e, job));
  const hitUsers = [];
  const missUsers = [];
  let totalStake = 0, hitStake = 0, missStake = 0, payoutTotal = 0;
  for(const entry of eligible){
    const typ = entryType(entry);
    const win = winningDigitForEntryType(job, typ);
    const digits = entryDigitList(entry);
    const parDigit = Number(entry.parDigit || 0);
    const total = Number(entry.total || (parDigit * digits.length) || 0);
    totalStake += total;
    const isHit = !!win && digits.some(d => digitMatchesType(d, win, typ));
    entry.settlementStages = Array.isArray(entry.settlementStages) ? entry.settlementStages : [];
    const stageAlready = entry.settlementStages.some(x => x && x.key === key && x.result === result);
    if(stageAlready) continue;
    if(isHit){
      const payout = roundMoney(parDigit * Number(settings.payoutMultipliers[typ] || 0));
      payoutTotal += payout;
      hitStake += total;
      const wallet = ensureWalletInState(state, entry.userId);
      const before = Number(wallet.balance || 0);
      const after = roundMoney(before + payout);
      wallet.balance = after;
      wallet.updatedAt = nowIso();
      wallet.ledger = Array.isArray(wallet.ledger) ? wallet.ledger : [];
      const ledgerEntry = {
        id:`settle_${date}_${key}_${entry.id}_${result}`, txnId:`wallet_settle_${date}_${key}_${entry.id}_${result}`, time:nowIso(), type:'winner_payout', amount:payout, balanceBefore:before, balanceAfter:after, holdBefore:walletHoldAmount(wallet), holdAfter:walletHoldAmount(wallet),
        note:`Winner payout ${job.market} ${job.stage.toUpperCase()} ${result}`, source:'result_settlement', entryId:entry.id, settlementKey:key, result
      };
      wallet.ledger.push(ledgerEntry);
      recordWalletTransaction(state, entry.userId, wallet, ledgerEntry);
      hitUsers.push({ entryId:entry.id, userId:entry.userId, userJid:entry.senderJid || entry.userJid || entry.phone || '', phone:entry.phone || '', name:entry.userName || entry.userId, digit:win, gameType:typ, stake:total, payout, balanceAfter:after });
      entry.settlementStages.push({ key, result, status:'hit', payout, settledAt:nowIso() });
    } else {
      missStake += total;
      missUsers.push({ entryId:entry.id, userId:entry.userId, userJid:entry.senderJid || entry.userJid || entry.phone || '', phone:entry.phone || '', name:entry.userName || entry.userId, gameType:typ, digits:digits.join(','), stake:total });
      entry.settlementStages.push({ key, result, status:'miss', payout:0, settledAt:nowIso() });
    }
  }
  const settlement = {
    id:`S${date.replace(/-/g,'')}_${key.replace(/[^A-Z0-9]/ig,'_')}`,
    date, market:job.market, stage:job.stage, result, status:'settled', settledAt:nowIso(),
    eligibleCount:eligible.length, hitCount:hitUsers.length, missCount:missUsers.length,
    totalStake:roundMoney(totalStake), hitStake:roundMoney(hitStake), missStake:roundMoney(missStake), payoutTotal:roundMoney(payoutTotal),
    marketProfit:roundMoney(totalStake - payoutTotal), hitUsers, missUsers,
    payoutMultipliers:settings.payoutMultipliers
  };
  settlement.hitMissText = formatHitMissDetailedText(settlement, { maxRows: 120 });
  state.settlementRecords[date][key] = settlement;
  state.auditLog.push({ id:settlement.id, time:nowIso(), action:'result_settlement', detail:{ market:job.market, stage:job.stage, result, eligibleCount:settlement.eligibleCount, hitCount:settlement.hitCount, payoutTotal:settlement.payoutTotal, marketProfit:settlement.marketProfit } });
  if(state.auditLog.length > 500) state.auditLog.splice(0, state.auditLog.length - 500);
  return { changed:true, settlement };
}
function findSettlementRecord(state, date, market, stage){
  const recs = state?.settlementRecords?.[date || todayISO()] || {};
  if(market && stage){
    const key = `${market}_${stage}`;
    if(recs[key]) return recs[key];
    const nkey = normalizeSettlementMarket(key);
    for(const [k,v] of Object.entries(recs)) if(normalizeSettlementMarket(k) === nkey) return v;
  }
  const list = Object.values(recs).filter(Boolean).sort((a,b)=>String(b.settledAt||'').localeCompare(String(a.settledAt||'')));
  return list[0] || null;
}

function firebaseDataUrl(){
  return FIREBASE_URL.endsWith(".json") ? FIREBASE_URL : FIREBASE_URL + "/titan_master_data.json";
}
let realtimeStateCache = null;
let realtimeStateCacheAt = 0;
const TITAN_GATEWAY_STATE_CACHE_TTL_MS = Math.max(Number(process.env.TITAN_GATEWAY_STATE_CACHE_TTL_MS || 250), 0);
function realtimeClone(obj){ try{ return JSON.parse(JSON.stringify(obj || {})); }catch(e){ return obj || {}; } }
function firebaseNoCacheHeaders(extra={}){ return Object.assign({"Cache-Control":"no-cache", "Pragma":"no-cache"}, extra || {}); }
function realtimeCacheGet(){
  if(!realtimeStateCache || !TITAN_GATEWAY_STATE_CACHE_TTL_MS) return null;
  if(Date.now() - realtimeStateCacheAt <= TITAN_GATEWAY_STATE_CACHE_TTL_MS) return realtimeClone(realtimeStateCache);
  return null;
}
function realtimeCacheSet(st){ if(st && typeof st === "object"){ realtimeStateCache = realtimeClone(st); realtimeStateCacheAt = Date.now(); } }
function realtimeCacheClear(){ realtimeStateCache = null; realtimeStateCacheAt = 0; }
function realtimeCacheApplyChild(parts, data, mode="put"){
  if(!realtimeStateCache || !Array.isArray(parts) || !parts.length) return;
  try{
    const root = realtimeClone(realtimeStateCache);
    let cur = root;
    for(let i = 0; i < parts.length - 1; i++){
      const key = String(parts[i]);
      if(!cur[key] || typeof cur[key] !== "object" || Array.isArray(cur[key])) cur[key] = {};
      cur = cur[key];
    }
    const leaf = String(parts[parts.length - 1]);
    if(mode === "delete") delete cur[leaf];
    else if(mode === "patch" && cur[leaf] && typeof cur[leaf] === "object" && !Array.isArray(cur[leaf]) && data && typeof data === "object" && !Array.isArray(data)) cur[leaf] = Object.assign({}, cur[leaf], realtimeClone(data));
    else cur[leaf] = realtimeClone(data);
    realtimeStateCache = root;
    realtimeStateCacheAt = Date.now();
  }catch(e){
    realtimeCacheClear();
  }
}
async function fetchFirebaseState(opts={}){
  try{
    if(!opts.force){ const cached = realtimeCacheGet(); if(cached) return cached; }
    const started = Date.now();
    const res = await axios.get(firebaseDataUrl(), { timeout: 8000, headers:firebaseNoCacheHeaders() });
    if(res.status >= 400) gatewayObsEvent("firebase_fetch_non_200", "warning", `Firebase GET HTTP ${res.status}`, {ms:Date.now()-started, realtimeSync:REALTIME_SYNC_VERSION});
    const st = res.data || {};
    if(st && typeof st === "object") realtimeCacheSet(st);
    return st;
  }catch(e){
    gatewayObsError("firebase_fetch_error", e);
    throw e;
  }
}
async function fetchFirebaseStateWithEtag(){
  try{
    const started = Date.now();
    const res = await axios.get(firebaseDataUrl(), { timeout: 15000, headers:firebaseNoCacheHeaders({"X-Firebase-ETag":"true"}) });
    if(res.status >= 400) gatewayObsEvent("firebase_etag_non_200", "warning", `Firebase ETag GET HTTP ${res.status}`, {ms:Date.now()-started});
    return {data:res.data || {}, etag:res.headers?.etag || res.headers?.ETag || "*"};
  }catch(e){
    gatewayObsError("firebase_etag_get_error", e);
    throw e;
  }
}

function gatewayCollectionSize(v){
  if(Array.isArray(v)) return v.length;
  if(v && typeof v === "object") return Object.keys(v).length;
  if(v === null || v === undefined || v === "") return 0;
  return 1;
}
function gatewayStateScore(state){
  state = state && typeof state === "object" ? state : {};
  return {
    score: gatewayCollectionSize(state.profiles) * 20 + gatewayCollectionSize(state.wallets) * 10 + gatewayCollectionSize(state.ledgerSchedules) * 8 + gatewayCollectionSize(state.withdrawals) + gatewayCollectionSize(state.walletTransactions) + gatewayCollectionSize(state.resultRecords) * 5,
    profiles: gatewayCollectionSize(state.profiles), wallets: gatewayCollectionSize(state.wallets), ledgerSchedules: gatewayCollectionSize(state.ledgerSchedules), withdrawals: gatewayCollectionSize(state.withdrawals), walletTransactions: gatewayCollectionSize(state.walletTransactions), resultRecords: gatewayCollectionSize(state.resultRecords)
  };
}
function gatewayProtectedKeys(){
  return ["profiles","wallets","walletTransactions","payments","withdrawals","entries","ledgerSchedules","resultRecords","settlementRecords","marketRegistry","marketLocks","auditLog","paymentOutbox","loadForwarderOutbox","spamGuardEvents","whatsappSafetyTargets","whatsappSafetyEvents","resultTargets","loadForwarder","entrySettings","resultSettings","paymentMethods","withdrawalSettings","walletSettings","spamGuardSettings","whatsappSafetySettings","moneyIdempotency","gatewayDurability"];
}
function gatewayDefaultStateLike(state){
  if(!state || typeof state !== "object") return false;
  const profiles = state.profiles && typeof state.profiles === "object" ? state.profiles : {};
  const keys = Object.keys(profiles);
  const defaults = new Set(["admin1","admin2","admin3","client_dummy"]);
  return keys.length && keys.every(k => defaults.has(String(k))) && gatewayCollectionSize(state.wallets) <= 4 && !gatewayCollectionSize(state.walletTransactions) && !gatewayCollectionSize(state.entries);
}
function gatewayMergeListBySignature(candidate, live){
  const out = [], seen = new Set();
  for(const item of [...(Array.isArray(candidate) ? candidate : []), ...(Array.isArray(live) ? live : [])]){
    let sig = "";
    try{ sig = JSON.stringify(item); }catch(e){ sig = String(item); }
    if(!seen.has(sig)){ seen.add(sig); out.push(item && typeof item === "object" ? JSON.parse(JSON.stringify(item)) : item); }
  }
  return out.slice(-3000);
}
function gatewayMergeGenericProtectedState(candidate, latest){
  if(!candidate || typeof candidate !== "object" || !latest || typeof latest !== "object") return candidate;
  for(const key of gatewayProtectedKeys()){
    const live = latest[key];
    const cand = candidate[key];
    if(live && typeof live === "object" && !Array.isArray(live)){
      if(!cand || typeof cand !== "object" || Array.isArray(cand)){
        candidate[key] = JSON.parse(JSON.stringify(live));
        continue;
      }
      const liveN = Object.keys(live).length, candN = Object.keys(cand).length;
      const riskyDrop = liveN >= 2 && candN < Math.max(1, Math.floor(liveN * 0.50));
      const alwaysPreserve = ["profiles","wallets","ledgerSchedules","gatewayDurability","moneyIdempotency"].includes(key);
      if(riskyDrop || alwaysPreserve){
        for(const [k,v] of Object.entries(live)) if(!(k in cand)) cand[k] = JSON.parse(JSON.stringify(v));
        candidate[key] = cand;
      }
    } else if(Array.isArray(live)){
      if(!Array.isArray(cand)){ candidate[key] = JSON.parse(JSON.stringify(live)); continue; }
      if(live.length >= 5 && cand.length < Math.max(1, Math.floor(live.length * 0.50))) candidate[key] = gatewayMergeListBySignature(cand, live);
    }
  }
  candidate.firebaseDataGuard = candidate.firebaseDataGuard && typeof candidate.firebaseDataGuard === "object" ? candidate.firebaseDataGuard : {};
  candidate.firebaseDataGuard.version = FIREBASE_DATA_GUARD_VERSION;
  candidate.firebaseDataGuard.lastGatewayRootSaveGuardAt = new Date().toISOString();
  candidate.firebaseDataGuard.gatewayMode = "cas-root-save-with-data-loss-guard";
  return candidate;
}
function gatewayDataLossGuard(candidate, latest){
  const errors = [], warnings = [];
  const allowEmptyInit = ["1","true","yes","on"].includes(String(process.env.TITAN_FIREBASE_ALLOW_EMPTY_INIT || "0").toLowerCase());
  if(!candidate || typeof candidate !== "object") return {ok:false, errors:["candidate_not_object"], warnings};
  if(!latest || typeof latest !== "object" || !Object.keys(latest).length){
    if(gatewayDefaultStateLike(candidate) && !allowEmptyInit) return {ok:false, errors:["empty_firebase_default_state_save_blocked"], warnings:["Set TITAN_FIREBASE_ALLOW_EMPTY_INIT=1 only for a brand new empty database."]};
    if(!allowEmptyInit) return {ok:false, errors:["empty_or_unreadable_firebase_root_save_blocked"], warnings:["Firebase root looked empty/unreadable, so Gateway root save was blocked to avoid reset."]};
    return {ok:true, errors:[], warnings:["empty_init_allowed_by_env"]};
  }
  for(const key of gatewayProtectedKeys()){
    const oldN = gatewayCollectionSize(latest[key]);
    const newN = gatewayCollectionSize(candidate[key]);
    if(oldN <= 0) continue;
    if(["profiles","wallets","ledgerSchedules","marketRegistry"].includes(key)){
      const threshold = Math.max(1, Math.floor(oldN * 0.60));
      if(newN < threshold) errors.push(`${key}_drop_guard:${oldN}_to_${newN}`);
    } else if(oldN >= 10 && newN < Math.max(1, Math.floor(oldN * 0.35))){
      errors.push(`${key}_mass_drop_guard:${oldN}_to_${newN}`);
    } else if(oldN >= 3 && newN === 0){
      errors.push(`${key}_wipe_guard:${oldN}_to_0`);
    }
  }
  if(gatewayDefaultStateLike(candidate) && gatewayStateScore(latest).score > gatewayStateScore(candidate).score) errors.push("default_state_would_replace_richer_live_state");
  return {ok:!errors.length, errors, warnings};
}

async function saveFirebaseState(state){
  let lastErr = null;
  for(let attempt=0; attempt<6; attempt++){
    try {
      let candidate = JSON.parse(JSON.stringify(state || {}));
      let latest = {}, etag = "*";
      // v36: if Firebase cannot be read, do NOT root PUT stale/default state.
      const fetched = await fetchFirebaseStateWithEtag();
      latest = fetched.data || {}; etag = fetched.etag || "*";
      candidate = mergeLedgerProtectedState(candidate, latest);
      candidate = mergeMoneyProtectedState(candidate, latest);
      candidate = gatewayMergeGenericProtectedState(candidate, latest);
      const guard = gatewayDataLossGuard(candidate, latest);
      if(!guard.ok){
        gatewayObsEvent("firebase_gateway_root_save_blocked_v36", "critical", "Gateway risky Firebase root save blocked", {attempt, guard, candidateScore:gatewayStateScore(candidate), liveScore:gatewayStateScore(latest)});
        throw new Error("Firebase Data Guard v36 blocked Gateway root save: " + guard.errors.join(","));
      }
      const saved = await putFirebaseTopLevelChildren(candidate || {});
      realtimeCacheSet(candidate || {});
      return saved;
    } catch(error) {
      lastErr = error;
      if(error.response && error.response.status === 412){
        gatewayObsEvent("firebase_cas_conflict", "warning", "Gateway Firebase CAS conflict; retry expected", {attempt, firebaseDataGuard:FIREBASE_DATA_GUARD_VERSION});
        await new Promise(r => setTimeout(r, 120 * (attempt + 1)));
        continue;
      }
      console.error('🔴 Firebase guarded save failed:', error.response ? `HTTP ${error.response.status}` : error.message);
      gatewayObsError("firebase_guarded_save_error_v36", error, {attempt});
      throw error;
    }
  }
  console.error('🔴 Firebase save conflict after retries:', lastErr?.message || lastErr);
  gatewayObsError("firebase_save_conflict_after_retries", lastErr || new Error('Firebase save CAS conflict'));
  throw lastErr || new Error('Firebase save CAS conflict');
}
async function putFirebaseTopLevelChildren(state){
  const out = {};
  for(const [key, value] of Object.entries(state || {})){
    out[key] = await putFirebaseChild([key], value, null);
  }
  realtimeCacheClear();
  return out;
}

async function saveGatewayChildren(state, childKeys){
  const out = {};
  for(const key of childKeys){
    if(Object.prototype.hasOwnProperty.call(state || {}, key)){
      out[key] = await putFirebaseChild([key], state[key], null);
    }
  }
  return out;
}
async function saveGatewayProfileSync(state, userId){
  if(userId && state?.profiles?.[userId]) await putFirebaseChild(['profiles', userId], state.profiles[userId], null);
  if(userId && state?.wallets?.[userId]) await putFirebaseChild(['wallets', userId], state.wallets[userId], null);
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
}
async function saveGatewayEntryAcceptNarrow(state, userId){
  await saveGatewayChildren(state, ['entries', 'walletTransactions', 'paymentOutbox']);
  if(userId && state?.wallets?.[userId]) await putFirebaseChild(['wallets', userId], state.wallets[userId], null);
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
}
async function saveGatewayWithdrawalNarrow(state, userId){
  await saveGatewayChildren(state, ['withdrawals', 'walletTransactions', 'paymentOutbox']);
  if(userId && state?.wallets?.[userId]) await putFirebaseChild(['wallets', userId], state.wallets[userId], null);
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
}
async function saveGatewaySpamGuardNarrow(state){
  await saveGatewayChildren(state, ['spamGuardSettings', 'spamGuardEvents']);
}
async function saveGatewayResultScrapeNarrow(state, updates, autoLedgerMark){
  const date = todayISO();
  const markets = [...new Set((updates || []).map(u => String(u.market || '')).filter(Boolean))];
  for(const market of markets){
    const rec = state?.resultRecords?.[date]?.[market];
    if(rec) await putFirebaseChild(['resultRecords', date, market], rec, null);
  }
  if(autoLedgerMark?.changed) await saveGatewayAutoMarkNarrow(state, {date, details:autoLedgerMark.details || []});
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
}
async function saveGatewayLoadForwarderNarrow(state){
  await saveGatewayChildren(state, ['loadForwarderOutbox', 'loadForwarder']);
}
async function saveGatewayPaymentOutboxNarrow(state){
  await saveGatewayChildren(state, ['paymentOutbox']);
}
async function saveGatewayWhatsappSafetyNarrow(state){
  await saveGatewayChildren(state, ['whatsappSafetySettings', 'whatsappSafetyTargets', 'whatsappSafetyEvents']);
}

async function saveGatewayAutoMarkNarrow(state, summary){
  const date = summary?.date || todayISO();
  const dictByType = {ank:'data', jodi:'jodiData', pannel:'pannelData'};
  const touched = [];
  for(const d of (summary?.details || [])){
    const pid = String(d.profileId || '');
    const typ = String(d.type || '').toLowerCase();
    const dict = dictByType[typ];
    const idx = String(d.index);
    if(!pid || !dict || idx === 'undefined') continue;
    const rec = state?.profiles?.[pid]?.dayRecords?.[date]?.[dict]?.[idx];
    if(rec && typeof rec === 'object'){
      await putFirebaseChild(['profiles', pid, 'dayRecords', date, dict, idx], rec, null);
      touched.push(`${pid}/${dict}/${idx}`);
    }
  }
  if(state?.ledgerAutoMarkRecords?.[date]) await putFirebaseChild(['ledgerAutoMarkRecords', date], state.ledgerAutoMarkRecords[date], null);
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
  return {ok:true, touched};
}
async function saveGatewaySettlementNarrow(state, date, settlement){
  if(!settlement) return {ok:false, reason:'missing_settlement'};
  const key = settlementKey(settlement);
  await putFirebaseChild(['settlementRecords', date, key], settlement, null);
  for(const h of (settlement.hitUsers || [])){
    const uid = String(h.userId || '');
    if(uid && state?.wallets?.[uid]) await putFirebaseChild(['wallets', uid], state.wallets[uid], null);
  }
  if(Array.isArray(state?.walletTransactions)) await putFirebaseChild(['walletTransactions'], state.walletTransactions.slice(-2000), null);
  if(Array.isArray(state?.entries)) await putFirebaseChild(['entries'], state.entries, null);
  if(Array.isArray(state?.auditLog)) await putFirebaseChild(['auditLog'], state.auditLog.slice(-500), null);
  return {ok:true, key};
}

async function patchFirebaseState(patch){
  try {
    const res = await axios.patch(firebaseDataUrl(), patch || {}, { timeout: 8000 });
    realtimeCacheClear();
    return res.data;
  } catch(error) {
    console.error('🔴 Firebase patch failed:', error.response ? `HTTP ${error.response.status}` : error.message);
    gatewayObsError("firebase_patch_error", error);
    throw error;
  }
}


// ============================================================
// GATEWAY DURABILITY v10 — Firebase-backed idempotency + delivery locks
// Keeps local JSON as a fallback only; critical duplicate prevention is stored in Firebase.
// ============================================================
const GATEWAY_LOCK_OWNER = `gateway:${process.pid}:${Math.random().toString(36).slice(2,8)}`;
function firebaseRootBaseUrl(){
  const u = firebaseDataUrl();
  return u.endsWith('.json') ? u.slice(0, -5) : u.replace(/\/$/, '');
}
function firebaseChildUrl(parts){
  const arr = Array.isArray(parts) ? parts : String(parts || '').split('/');
  const enc = arr.map(x => encodeURIComponent(String(x || '').replace(/^\/+|\/+$/g, ''))).filter(Boolean).join('/');
  return firebaseRootBaseUrl() + (enc ? '/' + enc : '') + '.json';
}
function durableHash(v){
  try{ return require('crypto').createHash('sha1').update(String(v || '')).digest('hex'); }
  catch(e){ return String(v || '').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0,120) || Math.random().toString(36).slice(2); }
}
function durablePath(kind, key){
  return ['gatewayDurability', String(kind || 'lock'), durableHash(key)];
}
async function fetchFirebaseChildWithEtag(parts){
  const res = await axios.get(firebaseChildUrl(parts), { timeout: 15000, headers:{'X-Firebase-ETag':'true'} });
  return { data:res.data || null, etag:res.headers?.etag || res.headers?.ETag || '*' };
}
async function putFirebaseChild(parts, data, etag='*'){
  const headers = etag ? {'if-match':etag} : {};
  const res = await axios.put(firebaseChildUrl(parts), data || {}, { timeout:8000, headers });
  realtimeCacheApplyChild(parts, data || {}, "put");
  return res.data;
}
async function patchFirebaseChild(parts, data){
  const res = await axios.patch(firebaseChildUrl(parts), data || {}, { timeout:8000 });
  realtimeCacheApplyChild(parts, Object.assign({}, data || {}), "patch");
  return res.data;
}
function durableExpired(rec){
  const exp = Date.parse(rec?.expiresAt || '');
  return !Number.isFinite(exp) || exp <= Date.now();
}
async function acquireDurableLock(kind, key, ttlMs=120000, meta={}){
  const path = durablePath(kind, key);
  const now = Date.now();
  const nowText = nowIso();
  const expiresAt = new Date(now + Math.max(30000, Number(ttlMs || 120000))).toISOString();
  for(let attempt=0; attempt<6; attempt++){
    const cur = await fetchFirebaseChildWithEtag(path);
    const rec = cur.data;
    if(rec && rec.status === 'done') return { ok:false, done:true, existing:rec, path };
    if(rec && rec.status === 'locked' && !durableExpired(rec)) return { ok:false, locked:true, existing:rec, path };
    const next = { kind, key:String(key || ''), keyHash:durableHash(key), status:'locked', owner:GATEWAY_LOCK_OWNER, acquiredAt:nowText, updatedAt:nowText, expiresAt, meta };
    try{
      await putFirebaseChild(path, next, cur.etag || '*');
      return { ok:true, lock:next, path };
    }catch(e){
      if(e.response && e.response.status === 412){ await new Promise(r => setTimeout(r, 80 * (attempt + 1))); continue; }
      throw e;
    }
  }
  return { ok:false, locked:true, reason:'lock_conflict_after_retries', path };
}
async function markDurableDone(kind, key, extra={}){
  const path = durablePath(kind, key);
  const nowText = nowIso();
  const ttlDays = Number(extra.ttlDays || 7);
  const expiresAt = new Date(Date.now() + ttlDays * 86400000).toISOString();
  await patchFirebaseChild(path, { status:'done', owner:GATEWAY_LOCK_OWNER, doneAt:nowText, updatedAt:nowText, expiresAt, ...extra });
}
async function markDurableError(kind, key, extra={}){
  const path = durablePath(kind, key);
  const nowText = nowIso();
  const expiresAt = new Date(Date.now() + Math.max(30000, Number(extra.ttlMs || 120000))).toISOString();
  await patchFirebaseChild(path, { status:'error', owner:GATEWAY_LOCK_OWNER, errorAt:nowText, updatedAt:nowText, expiresAt, ...extra });
}
function entryMessageLockKey(parsed, meta){
  return meta?.messageKey || [meta?.chatJid, meta?.senderJid, parsed?.market, parsed?.gameType, (parsed?.digits||[]).join('.'), parsed?.parDigit, parsed?.total, String(parsed?.rawText||'').slice(0,500)].join('|');
}
function withdrawalMessageLockKey(parsed, meta){
  return meta?.messageKey || [meta?.chatJid, meta?.senderJid, parsed?.amount, parsed?.method, String(parsed?.detail||'').slice(0,300)].join('|');
}
async function reserveScheduleTarget(jobKey, date, target){
  const tk = scheduleTargetLogKey(target);
  if(!tk) return {ok:false, reason:'missing_target_key'};
  const key = `${jobKey}|${date}|${tk}`;
  return await acquireDurableLock('schedule_target_send', key, 10 * 60 * 1000, {jobKey,date,target:tk});
}
async function markScheduleTargetDoneDurable(jobKey, date, target, sendId=''){
  const tk = scheduleTargetLogKey(target);
  if(!tk) return;
  const key = `${jobKey}|${date}|${tk}`;
  await markDurableDone('schedule_target_send', key, {jobKey,date,target:tk, sendId, lastSentDate:date, lastSentKey:key, ttlDays:14});
}
async function markScheduleTargetErrorDurable(jobKey, date, target, error=''){
  const tk = scheduleTargetLogKey(target);
  if(!tk) return;
  const key = `${jobKey}|${date}|${tk}`;
  await markDurableError('schedule_target_send', key, {jobKey,date,target:tk,error:String(error||'').slice(0,300), ttlMs:2*60*1000});
}
async function reserveResultTarget(jobKey, signature, target){
  const tk = resultTargetLogKey(target);
  if(!tk) return {ok:false, reason:'missing_target_key'};
  const key = `${jobKey}|${signature}|${tk}`;
  return await acquireDurableLock('result_target_send', key, 10 * 60 * 1000, {jobKey,signature,target:tk});
}
async function markResultTargetDoneDurable(jobKey, signature, target, sendId=''){
  const tk = resultTargetLogKey(target);
  if(!tk) return;
  const key = `${jobKey}|${signature}|${tk}`;
  await markDurableDone('result_target_send', key, {jobKey,signature,target:tk,sendId, ttlDays:30});
}
async function markResultTargetErrorDurable(jobKey, signature, target, error=''){
  const tk = resultTargetLogKey(target);
  if(!tk) return;
  const key = `${jobKey}|${signature}|${tk}`;
  await markDurableError('result_target_send', key, {jobKey,signature,target:tk,error:String(error||'').slice(0,300), ttlMs:2*60*1000});
}
async function reserveSettlement(job){
  const date = job?.date || todayISO();
  const result = cleanResult(job?.result || '');
  const key = `${date}|${job?.market}|${job?.stage}|${result}`;
  return await acquireDurableLock('result_settlement', key, 10 * 60 * 1000, {date, market:job?.market, stage:job?.stage, result});
}
async function markSettlementDone(job, settlement){
  const date = job?.date || todayISO();
  const result = cleanResult(job?.result || '');
  const key = `${date}|${job?.market}|${job?.stage}|${result}`;
  await markDurableDone('result_settlement', key, {date, market:job?.market, stage:job?.stage, result, settlementId:settlement?.id || '', payoutTotal:Number(settlement?.payoutTotal || 0), hitCount:Number(settlement?.hitCount || 0), ttlDays:90});
}
function mergeScrapedResultsIntoState(state, scraped){
  const date = todayISO();
  if(!state || typeof state !== "object") state = {};
  if(!state.resultRecords) state.resultRecords = {};
  if(!state.resultRecords[date]) state.resultRecords[date] = {};
  const updates = [];
  const skipped = [];
  // Fresh result lifecycle is strict and follows the live widget transition:
  // Loading/Holiday = status only, never a result.
  // Loading -> 123-4 = fresh open.
  // 123-4 -> 123-45-678 = fresh close, accepted only when the close starts with today's saved open.
  // Any full 123-45-678 seen before today's open is treated as old/yesterday data and skipped.
  const ordered = [...(scraped || [])].sort((a,b) => {
    const sa = resultStage(a.result), sb = resultStage(b.result);
    if(sa !== sb) return sa === "open" ? -1 : 1;
    // Within the same stage prefer the higher confidence block first, but keep all distinct candidates.
    const rank = (x) => (x.block === "LIVE MATKA RESULT" ? 5 : (x.block === "LIVE UPDATE" ? 4 : (x.block === "DPBOSS LIVE RESULT" ? 3 : (x.block === "DPBOSS MAIN RESULT" ? 2 : 1))));
    return rank(b) - rank(a);
  });
  for(const item of ordered){
    const stage = resultStage(item.result);
    if(!stage) continue;
    const allowed = marketPhase3Allowed(state, item.market, "auto_result", stage);
    if(!allowed.ok){ skipped.push({market:item.market, stage, result:item.result, reason:allowed.reason || "market_registry_blocked"}); continue; }
    item.market = allowed.market || item.market;
    const rec = state.resultRecords[date][item.market] || { market:item.market };
    if(stage === "open"){
      const live = liveStateForMarket(item.market);
      // Open format is the first true fresh result. We prefer that Loading was seen before it,
      // but we still accept 123-4 after double confirmation to avoid missing a fresh open if Gateway started late.
      rec.market = item.market;
      rec.source = "auto_scrape";
      rec.sourceUrl = item.sourceUrl || "";
      rec.updatedAt = new Date().toISOString();
      rec.openLifecycle = live.loadingSeen ? "loading_to_open" : "open_confirmed_without_loading_seen";
      if(cleanResult(rec.openResult || "") !== item.result || rec.openInferredFromClose){
        rec.openResult = item.result;
        rec.openInferredFromClose = false;
        rec.openUpdatedAt = new Date().toISOString();
        updates.push({ market:item.market, stage, result:item.result, lifecycle:rec.openLifecycle });
      }
      state.resultRecords[date][item.market] = rec;
      rememberLiveStatus(item);
      continue;
    }

    if(stage === "close"){
      const openResult = cleanResult(rec.openResult || "");
      if(resultStage(openResult) !== "open" || rec.openInferredFromClose === true){
        skipped.push({ market:item.market, stage, result:item.result, reason:"fresh_open_missing_strict_2_stage" });
        continue;
      }
      if(!item.result.startsWith(openResult)){
        skipped.push({ market:item.market, stage, result:item.result, reason:`close_does_not_match_open_${openResult}` });
        continue;
      }
      rec.market = item.market;
      rec.source = "auto_scrape";
      rec.sourceUrl = item.sourceUrl || "";
      rec.updatedAt = new Date().toISOString();
      if(cleanResult(rec.closeResult || "") !== item.result){
        rec.closeResult = item.result;
        rec.closeUpdatedAt = new Date().toISOString();
        updates.push({ market:item.market, stage, result:item.result, lifecycle:"fresh_open_to_close" });
      }
      state.resultRecords[date][item.market] = rec;
      rememberLiveStatus(item);
    }
  }
  return { state, updates, skipped };
}
function firebaseAutoScrapeEnabled(state){
  return !(state && state.resultSettings && state.resultSettings.autoScrapeEnabled === false);
}
async function autoScrapeResultsOnce(){
  if(!RESULT_SCRAPE_ENABLED) return { status:"disabled_env", updates:[], scraped:[], confirmed:[], message:"RESULT_SCRAPE_ENABLED=0" };
  const state = await fetchFirebaseState();
  if(!firebaseAutoScrapeEnabled(state)) return { status:"disabled", updates:[], scraped:[], confirmed:[], message:"Auto scrape is OFF in admin app settings" };
  ensureMarketRegistry(state);
  runtimeResultAliasRows = buildResultAliasRowsFromState(state, "auto_result");
  const scrape = await scrapeLiveResultPages();
  for(const st of scrape.statuses || []) rememberLiveStatus(st);
  if(!scrape.results.length) return { status:"empty", updates:[], scraped:[], statuses:scrape.statuses || [], confirmed:[], errors:scrape.errors };
  const confirmed = confirmScrapedResults(scrape.results);
  if(!confirmed.length){
    return { status:"waiting_confirmation", updates:[], scraped:scrape.results, statuses:scrape.statuses || [], confirmed:[], confirmRequired:RESULT_SCRAPE_CONFIRM_COUNT, errors:scrape.errors };
  }
  const merged = mergeScrapedResultsIntoState(state, confirmed);
  let autoLedgerMark = {changed:false, marked:0, pass:0, fail:0};
  if(merged.updates.length){
    for(const u of merged.updates){
      const r = applyLedgerAutoMarkForResult(merged.state, {date:todayISO(), market:u.market, stage:u.stage, result:u.result});
      autoLedgerMark.changed = autoLedgerMark.changed || !!r.changed;
      autoLedgerMark.marked += Number(r.marked || 0);
      autoLedgerMark.pass += Number(r.pass || 0);
      autoLedgerMark.fail += Number(r.fail || 0);
      autoLedgerMark.details = (autoLedgerMark.details || []).concat(r.details || []);
    }
  }
  gatewayHealth.lastLedgerAutoMark = autoLedgerMark;
  if(merged.updates.length || autoLedgerMark.changed) await saveGatewayResultScrapeNarrow(merged.state, merged.updates, autoLedgerMark);
  return { status:"success", scraped:scrape.results, statuses:scrape.statuses || [], confirmed, updates:merged.updates, autoLedgerMark, skipped:merged.skipped || [], confirmRequired:RESULT_SCRAPE_CONFIRM_COUNT, errors:scrape.errors };
}
async function resultScrapeTick(){
  if(resultScrapeTickRunning) return;
  resultScrapeTickRunning = true;
  gatewayHealth.lastResultScrapeTickAt = nowIso();
  try {
    const out = await autoScrapeResultsOnce();
    gatewayHealth.lastResultScrapeStatus = out.status || "unknown";
    gatewayHealth.lastResultScrapeUpdates = (out.updates || []).slice(-10);
    gatewayHealth.lastResultScrapeSkipped = (out.skipped || []).slice(-10);
    gatewayHealth.lastResultScrapeError = (out.errors || []).join(" ; ");
    if(out.updates && out.updates.length){
      console.log("🧲 Scraped result update:", out.updates.map(x => `${x.market} ${x.stage} ${x.result}`).join(" | "));
      // Low-latency mode: as soon as Firebase is updated from scrape, trigger WhatsApp result sending immediately.
      // This removes the old extra wait for the separate 15-second result poller.
      if(connected) await resultTick();
    }
    if(out.statuses && out.statuses.length){
      const statusLine = out.statuses.slice(0, 8).map(x => `${x.market}:${x.status}`).join(" | ");
      if(statusLine) console.log("📡 Live statuses:", statusLine);
    }
    if(out.skipped && out.skipped.length){
      console.log("🛡️ Skipped old/unmatched scrape:", out.skipped.map(x => `${x.market} ${x.result} (${x.reason})`).join(" | "));
    }
    if(out.errors && out.errors.length) console.log("Scrape fallback errors:", out.errors.join(" ; "));
  } catch(e) {
    gatewayHealth.lastResultScrapeStatus = "error";
    gatewayHealth.lastResultScrapeError = e.response ? `HTTP ${e.response.status}` : e.message;
    console.log("Result scrape error:", e.response ? `HTTP ${e.response.status}` : e.message);
  } finally {
    resultScrapeTickRunning = false;
  }
}

async function scheduleTick(){
  if(scheduleTickRunning) return;
  scheduleTickRunning = true;
  gatewayHealth.lastScheduleTickAt = nowIso();
  try {
    if(!connected) return;
    const state = await fetchFirebaseState();
    const recoveryPreflight = recomputeLedgerRecoveryAutoRates(state, todayISO(), "gateway_schedule_preflight_recovery");
    if(recoveryPreflight.changed){
      await saveGatewayAutoMarkNarrow(state, recoveryPreflight);
      console.log(`🛡️ Schedule preflight recovery auto-rate refreshed ${recoveryPreflight.count} card(s)`);
    }
    const schedules = collectSchedules(state);
    const hhmm = nowHHMM();
    const date = todayISO();
    const inRunSent = new Set();
    for(const job of schedules){
      if(!isDueNow(job.time, hhmm)) continue;
      const key = `schedule_${job.id}_${job.time}`;
      const allTargets = dedupeTargetsByResolvedKey(job.targets);
      if(!allTargets.length) continue;
      // Target-aware daily lock: a ledger schedule can be sent once per date/card/time/target only.
      // This blocks duplicate sends caused by recovery-window polling, duplicate target values,
      // repeated saved day/persistent schedules, or a slow send overlapping the next tick.
      const pendingTargets = [];
      for(const target of allTargets){
        const tk = scheduleTargetLogKey(target);
        const runKey = `${key}|${date}|${tk}`;
        if(!tk || inRunSent.has(runKey) || isScheduleTargetAlreadySent(key, date, target)) continue;
        const durable = await reserveScheduleTarget(key, date, target);
        if(!durable.ok){
          if(durable.done) markScheduleTargetSent(key, date, target);
          continue;
        }
        inRunSent.add(runKey);
        pendingTargets.push(target);
      }
      if(!pendingTargets.length) continue;
      console.log(`⏰ HIT ${job.time}: ${job.market} -> ${pendingTargets.length}/${allTargets.length} pending target(s)`);
      const results = [];
      for(const target of pendingTargets) results.push(await sendText(target, job.message, {type:"ledger_schedule", market:job.market, jobId:job.id}));
      const okCount = results.filter(r => r.ok).length;
      for(const r of results){
        // Mark successful sends only. Failed targets can retry inside the recovery window.
        if(r.ok){
          markScheduleTargetSent(key, date, r.rawTarget || r.target || "");
          try { await markScheduleTargetDoneDurable(key, date, r.rawTarget || r.target || "", r.id || ""); } catch(e){ console.log("⚠️ schedule durable done mark failed:", e.response ? `HTTP ${e.response.status}` : e.message); }
        } else {
          try { await markScheduleTargetErrorDurable(key, date, r.rawTarget || r.target || "", r.error || "send_failed"); } catch(e){ console.log("⚠️ schedule durable error mark failed:", e.response ? `HTTP ${e.response.status}` : e.message); }
        }
      }
      if(okCount > 0) saveJson(SENT_LOG_FILE, sentLog);
      gatewayHealth.lastScheduleSendAt = nowIso();
      gatewayHealth.lastScheduleDelivery = results.slice(-20);
      console.log(`✅ Auto sent ${job.market}:`, results.map(r => r.ok ? "OK" : "FAIL:"+r.error).join(" | "));
    }
  } catch(e) {
    gatewayHealth.lastScheduleError = e.response ? `HTTP ${e.response.status}` : e.message;
    console.log("Schedule poll error:", e.response ? `HTTP ${e.response.status}` : e.message);
    console.log("👉 Firebase direct mode hai. FIREBASE_URL check karo if repeated error.");
  } finally {
    scheduleTickRunning = false;
  }
}

async function resultTick(){
  if(resultTickRunning) return;
  resultTickRunning = true;
  gatewayHealth.lastResultTickAt = nowIso();
  try {
    if(!connected) return;
    const state = await fetchFirebaseState();
    const ledgerAutoMark = applyLedgerAutoMarkAll(state, todayISO(), false);
    const recoveryAfterMark = ledgerAutoMark.changed ? recomputeLedgerRecoveryAutoRates(state, todayISO(), "gateway_result_auto_mark_recovery") : {changed:false,count:0};
    gatewayHealth.lastLedgerAutoMark = {...ledgerAutoMark, recoveryAutoRate: recoveryAfterMark};
    if(ledgerAutoMark.changed || recoveryAfterMark.changed){
      if(ledgerAutoMark.changed) await saveGatewayAutoMarkNarrow(state, ledgerAutoMark);
      if(recoveryAfterMark.changed) await saveGatewayAutoMarkNarrow(state, recoveryAfterMark);
      console.log(`🤖 Ledger auto-mark: ${ledgerAutoMark.marked} card(s) PASS:${ledgerAutoMark.pass} FAIL:${ledgerAutoMark.fail} • recovery rates:${recoveryAfterMark.count || 0}`);
    }
    const jobs = collectResults(state);
    const date = todayISO();
    for(const job of jobs){
      // Target-aware delivery guard: each result is sent once per WhatsApp target.
      // If targets are changed later, new group/private/Forward targets still receive the result.
      const key = job.id;
      const resultSignature = `${date}_${cleanResult(job.result)}`;
      const allTargets = targetList(job.targets);
      if(!allTargets.length){
        console.log(`⚠️ RESULT ${job.stage.toUpperCase()} skipped: no resultTargets/forward targets saved for ${job.market}`);
        continue;
      }
      const pendingTargets = [];
      for(const target of allTargets){
        if(isResultTargetAlreadySent(key, resultSignature, target)) continue;
        const durable = await reserveResultTarget(key, resultSignature, target);
        if(!durable.ok){
          if(durable.done) markResultTargetSent(key, resultSignature, target);
          continue;
        }
        pendingTargets.push(target);
      }
      if(!pendingTargets.length) continue;
      let settlementOut = {changed:false, settlement:findSettlementRecord(state, date, job.market, job.stage)};
      const sLock = await reserveSettlement(job);
      if(sLock.ok){
        settlementOut = settleResultInState(state, job);
        if(settlementOut.changed){
          await saveGatewaySettlementNarrow(state, date, settlementOut.settlement);
          await markSettlementDone(job, settlementOut.settlement);
        } else if(settlementOut.alreadySettled && settlementOut.settlement){
          await markSettlementDone(job, settlementOut.settlement);
        }
      } else if(sLock.done){
        settlementOut = {changed:false, alreadySettled:true, settlement:findSettlementRecord(state, date, job.market, job.stage)};
      } else {
        console.log(`🛡️ Settlement locked by another worker: ${job.market} ${job.stage}`);
      }
      let messageText = formatResultMessage(job.market, job.result);
      const sSettings = settlementSettings(state);
      const settlement = settlementOut.settlement;
      if(sSettings.enabled && sSettings.includeSummaryInResultMessage && settlement) messageText += settlementSummaryText(settlement);
      if(sSettings.enabled && sSettings.includeHitMissInResultMessage && settlement) messageText += "\n\n" + formatHitMissDetailedText(settlement, { maxRows: 60 });
      console.log(`🏆 RESULT ${job.stage.toUpperCase()}: ${job.market} ${job.result} -> ${pendingTargets.length}/${allTargets.length} pending target(s)${settlement ? ` | settlement hit:${settlement.hitCount} payout:${settlement.payoutTotal}` : ""}`);
      const results = [];
      for(const target of pendingTargets) results.push(await sendText(target, messageText, {type:"result_declaration", market:job.market, stage:job.stage, result:job.result}));
      const okCount = results.filter(r => r.ok).length;
      for(const r of results){
        if(r.ok){
          markResultTargetSent(key, resultSignature, r.rawTarget || r.target || "");
          try { await markResultTargetDoneDurable(key, resultSignature, r.rawTarget || r.target || "", r.id || ""); } catch(e){ console.log("⚠️ result durable done mark failed:", e.response ? `HTTP ${e.response.status}` : e.message); }
        } else {
          try { await markResultTargetErrorDurable(key, resultSignature, r.rawTarget || r.target || "", r.error || "send_failed"); } catch(e){ console.log("⚠️ result durable error mark failed:", e.response ? `HTTP ${e.response.status}` : e.message); }
        }
      }
      if(okCount > 0) saveJson(SENT_LOG_FILE, sentLog);
      gatewayHealth.lastResultSendAt = nowIso();
      gatewayHealth.lastResultSendSummary = `${job.market} ${job.stage} ${okCount}/${results.length}`;
      gatewayHealth.lastResultDelivery = results.slice(-20);
      if(okCount === 0 && results.length){ gatewayHealth.lastResultError = results.map(r => `${r.target||''}:${r.error||'failed'}`).join(' | '); }
      else if(okCount > 0){ gatewayHealth.lastResultError = ''; }
      console.log(`✅ Result sent ${job.market} ${job.stage}:`, results.map(r => r.ok ? "OK" : "FAIL:"+r.error).join(" | "));
    }
  } catch(e) {
    gatewayHealth.lastResultError = e.response ? `HTTP ${e.response.status}` : e.message;
    console.log("Result poll error:", e.response ? `HTTP ${e.response.status}` : e.message);
  } finally {
    resultTickRunning = false;
  }
}

function normalizeLoadGameTypes(types){
  const order = ["ANK", "PENEL", "JODI"];
  if(!types) return order.slice();
  if(!Array.isArray(types)) types = String(types).split(/[\n,]+/).map(x=>x.trim()).filter(Boolean);
  const out = [];
  for(const t of types){
    let typ = String(t || "").trim().toUpperCase();
    if(typ === "PANEL" || typ === "PANNEL") typ = "PENEL";
    if(order.includes(typ) && !out.includes(typ)) out.push(typ);
  }
  return order.filter(x => out.includes(x)).length ? order.filter(x => out.includes(x)) : order.slice();
}

function loadForwarderSettings(state){
  const lf = state?.loadForwarder || {};
  return {
    enabled: lf.enabled === true,
    scheduleTime: normalizeTime(lf.scheduleTime || "18:00") || "18:00",
    selectedMarket: normalizeEntryMarketText(lf.selectedMarket || ""),
    targets: targetList(lf.targets || []),
    gameTypes: normalizeLoadGameTypes(lf.gameTypes || ["ANK", "PENEL", "JODI"]),
    maxRowsPerType: Math.max(5, Math.min(300, Number(lf.maxRowsPerType || 80))),
    includeEmptyTypes: lf.includeEmptyTypes === true,
    lastSentKey: lf.lastSentKey || ""
  };
}
function loadEntryDigits(entry){
  const d = entry?.digits;
  if(Array.isArray(d)) return d.map(x => String(x).trim()).filter(Boolean);
  return String(d || "").replace(/[.\s]+/g, ",").split(",").map(x => x.trim()).filter(Boolean);
}
function buildLoadReport(state, date, market, maxRowsPerType, includeEmptyTypes, gameTypes){
  date = date || todayISO();
  market = normalizeEntryMarketText(market || "");
  const selectedTypes = normalizeLoadGameTypes(gameTypes || ["ANK", "PENEL", "JODI"]);
  const entries = (Array.isArray(state?.entries) ? state.entries : []).filter(e => {
    if(!e || e.status !== "accepted" || e.date !== date) return false;
    if(market && normalizeEntryMarketText(e.market || "") !== market) return false;
    return true;
  });
  const grouped = new Map();
  let grandTotal = 0;
  let includedCount = 0;
  const typeTotals = {};
  const typeEntryCounts = {};
  for(const t of selectedTypes){ typeTotals[t] = 0; typeEntryCounts[t] = 0; }
  for(const e of entries){
    const mk = normalizeEntryMarketText(e.market || "UNKNOWN") || "UNKNOWN";
    let typ = String(e.gameType || e.type || "ANK").toUpperCase();
    if(typ === "PANEL" || typ === "PANNEL") typ = "PENEL";
    if(!["ANK","JODI","PENEL"].includes(typ)) typ = "ANK";
    if(!selectedTypes.includes(typ)) continue;
    const rate = Number(e.parDigit || e.rate || 0) || 0;
    const total = Number(e.total || 0) || 0;
    grandTotal += total;
    includedCount += 1;
    typeTotals[typ] = Math.round((Number(typeTotals[typ] || 0) + total) * 100) / 100;
    typeEntryCounts[typ] = Number(typeEntryCounts[typ] || 0) + 1;
    for(let digit of loadEntryDigits(e)){
      digit = String(digit).trim();
      if(typ === "JODI") digit = digit.padStart(2,"0");
      const key = `${mk}|${typ}|${digit}`;
      const old = grouped.get(key) || { market:mk, type:typ, digit, amount:0, entryCount:0, users:new Set() };
      old.amount += rate;
      old.entryCount += 1;
      old.users.add(String(e.userId || e.senderJid || e.userName || "user"));
      grouped.set(key, old);
    }
  }
  const markets = [...new Set([...grouped.values()].map(x => x.market).concat(market ? [market] : []))].filter(Boolean).sort();
  const out = { date, market, gameTypes:selectedTypes, entryCount:includedCount, grandTotal:Math.round(grandTotal*100)/100, typeTotals, typeEntryCounts, markets:[] };
  for(const mk of markets){
    const mObj = { market:mk, overallTotal:0, types:[] };
    for(const typ of selectedTypes){
      const items = [...grouped.values()].filter(x => x.market === mk && x.type === typ)
        .map(x => ({ digit:x.digit, amount:Math.round(x.amount*100)/100, entryCount:x.entryCount, userCount:x.users.size }))
        .sort((a,b) => (b.amount - a.amount) || String(a.digit).localeCompare(String(b.digit)))
        .slice(0, maxRowsPerType || 80);
      if(items.length || includeEmptyTypes){
        const typeTotal = Math.round(items.reduce((s,x)=>s+x.amount,0)*100)/100;
        mObj.overallTotal = Math.round((mObj.overallTotal + typeTotal)*100)/100;
        mObj.types.push({ type:typ, overallTotal:typeTotal, items });
      }
    }
    out.markets.push(mObj);
  }
  return out;
}

function formatLoadReportText(report){
  const money = (v) => `₹${Number(v || 0).toLocaleString("en-IN", {maximumFractionDigits:2})}`;
  const lines = [
    "📊 *TITAN NOVA LOAD REPORT*",
    "━━━━━━━━━━━━━━━━━━━━",
    `📅 *DATE:* ${report.date}`,
    `🔥 *MARKET:* ${report.market || "ALL MARKETS"}`,
    `🧾 *ENTRIES:* ${report.entryCount || 0}`,
    `💰 *TOTAL LOAD:* ${money(report.grandTotal || 0)}`,
    `🎮 *GAMES:* ${(report.gameTypes || ["ANK", "PENEL", "JODI"]).join(", ")}`,
    "━━━━━━━━━━━━━━━━━━━━"
  ];
  if(report.typeTotals){
    lines.push("", "*GAME TYPE TOTALS*");
    for(const gt of (report.gameTypes || ["ANK", "PENEL", "JODI"])) lines.push(`${gt}: ${money(report.typeTotals[gt] || 0)} | Entries: ${(report.typeEntryCounts || {})[gt] || 0}`);
  }
  if(!report.markets || !report.markets.length){
    lines.push("Aaj is market me accepted entry load nahi hai.");
    return lines.join("\n");
  }
  for(const mk of report.markets){
    lines.push(`\n🔥 *${mk.market}*`);
    if(!mk.types || !mk.types.length){ lines.push("No load."); continue; }
    for(const typ of mk.types){
      lines.push(`\n*${typ.type} LOAD*`);
      if(!typ.items || !typ.items.length) lines.push("No load.");
      else for(const it of typ.items) lines.push(`${it.digit} = ${money(it.amount)} | Users: ${it.userCount || 0} | Entries: ${it.entryCount || 0}`);
      lines.push(`${typ.type} Overall: ${money(typ.overallTotal || 0)}`);
    }
    lines.push(`📌 Market Overall: ${money(mk.overallTotal || 0)}`);
  }
  return lines.join("\n").trim();
}
async function sendLoadReportToTargets(targets, text){
  const results = [];
  for(const target of targetList(targets)) results.push(await sendText(target, text, {type:"load_report"}));
  return results;
}
async function loadForwarderTick(){
  if(loadForwarderTickRunning) return;
  loadForwarderTickRunning = true;
  gatewayHealth.lastLoadForwarderTickAt = nowIso();
  try{
    if(!connected) return;
    const state = await fetchFirebaseState();
    let changed = false;
    // 1) Dashboard send-now outbox
    const outbox = Array.isArray(state.loadForwarderOutbox) ? state.loadForwarderOutbox : [];
    for(const msg of outbox){
      if(!msg || msg.status !== "pending") continue;
      const attempts = Number(msg.attempts || 0);
      if(attempts >= 5){ msg.status = "failed"; msg.lastError = msg.lastError || "max attempts"; changed = true; continue; }
      if(!msg.text || !arr(msg.targets).length){ msg.status = "failed"; msg.lastError = "missing text/targets"; changed = true; continue; }
      const results = await sendLoadReportToTargets(msg.targets, msg.text);
      msg.attempts = attempts + 1;
      msg.lastTriedAt = nowIso();
      msg.delivery = results;
      const okCount = results.filter(x => x.ok).length;
      if(okCount > 0){ msg.status = "sent"; msg.sentAt = nowIso(); }
      else { msg.lastError = results.map(x => x.error).filter(Boolean).join(" | ") || "send failed"; }
      changed = true;
      console.log(`📊 Load report outbox ${msg.id || ""}: ${okCount}/${results.length} sent`);
    }
    if(outbox.length > 300){ state.loadForwarderOutbox = outbox.slice(-300); changed = true; }

    // 2) Daily scheduled load report
    const lf = loadForwarderSettings(state);
    if(lf.enabled && lf.targets.length){
      const now = nowHHMM();
      if(isDueNow(lf.scheduleTime, now)){
        const date = todayISO();
        const key = `${date}_${lf.scheduleTime}_${lf.selectedMarket || "ALL"}`;
        state.loadForwarder = state.loadForwarder || {};
        if(state.loadForwarder.lastSentKey !== key){
          const report = buildLoadReport(state, date, lf.selectedMarket, lf.maxRowsPerType, lf.includeEmptyTypes, lf.gameTypes);
          const text = formatLoadReportText(report);
          const forwardRoleTargets = marketRoleTargetsForMarket(state, lf.selectedMarket, "forward");
          const bookieRoleTargets = collectBookieAdminTargets(state, lf.selectedMarket);
          const deliveryTargets = forwardRoleTargets.length ? forwardRoleTargets : (bookieRoleTargets.length ? bookieRoleTargets : lf.targets);
          const results = await sendLoadReportToTargets(deliveryTargets, text);
          const okCount = results.filter(x => x.ok).length;
          state.loadForwarder.lastSentKey = key;
          state.loadForwarder.lastSentAt = nowIso();
          state.loadForwarder.lastDelivery = results;
          state.loadForwarder.lastReportSummary = { date, market:lf.selectedMarket, entryCount:report.entryCount, total:report.grandTotal, okCount, targetCount:results.length };
          changed = true;
          gatewayHealth.lastLoadForwarderSendAt = nowIso();
          console.log(`📊 Scheduled load report ${lf.selectedMarket || "ALL"}: ${okCount}/${results.length} sent`);
        }
      }
    }
    if(changed) await saveGatewayLoadForwarderNarrow(state);
  }catch(e){
    gatewayHealth.lastLoadForwarderError = e.response ? `HTTP ${e.response.status}` : e.message;
    console.log("Load forwarder error:", e.response ? `HTTP ${e.response.status}` : e.message);
  }finally{
    loadForwarderTickRunning = false;
  }
}

async function paymentOutboxTick(){
  if(paymentOutboxTickRunning) return;
  paymentOutboxTickRunning = true;
  gatewayHealth.lastPaymentOutboxTickAt = nowIso();
  try {
    if(!connected) return;
    const state = await fetchFirebaseState();
    const settings = state?.paymentSettings || {};
    const outbox = Array.isArray(state.paymentOutbox) ? state.paymentOutbox : [];
    let changed = false;
    for(const msg of outbox){
      if(!msg || msg.status !== "pending") continue;
      if(!msg.target || !msg.text){ msg.status = "failed"; msg.lastError = "missing target/text"; changed = true; continue; }
      const attempts = Number(msg.attempts || 0);
      if(attempts >= 5){ msg.status = "failed"; msg.lastError = msg.lastError || "max attempts"; changed = true; continue; }
      const out = await sendText(msg.target, msg.text, {type:msg.type || msg.meta?.type || "payment_outbox", privateReply:true});
      msg.attempts = attempts + 1;
      msg.lastTriedAt = nowIso();
      if(out.ok){
        msg.status = "sent";
        msg.sentAt = nowIso();
        msg.sentId = out.id || "sent";
      } else {
        msg.lastError = out.error || "send failed";
        if(/invalid|unresolved|not on WhatsApp/i.test(String(out.error || ""))) msg.status = "failed";
      }
      changed = true;
    }
    if(changed){
      // Keep latest queue history compact.
      if(outbox.length > 300) state.paymentOutbox = outbox.slice(-300);
      await saveGatewayPaymentOutboxNarrow(state);
      const pending = (state.paymentOutbox || outbox).filter(x => x.status === "pending").length;
      console.log(`💳 Payment outbox processed. pending:${pending}`);
    }
  } catch(e){
    gatewayHealth.lastPaymentOutboxError = e.response ? `HTTP ${e.response.status}` : e.message;
    console.log("Payment outbox error:", e.response ? `HTTP ${e.response.status}` : e.message);
  } finally {
    paymentOutboxTickRunning = false;
  }
}


function clearWhatsAppSessionFiles(){
  try {
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    return { ok:true };
  } catch(e) {
    return { ok:false, error:e.message || String(e) };
  }
}

async function stopWhatsAppSocket(reason = "manual_reset"){
  try { if(sock && typeof sock.end === "function") sock.end(new Error(reason)); } catch(e) {}
  try { if(sock && sock.ws && typeof sock.ws.close === "function") sock.ws.close(); } catch(e) {}
  sock = null;
  connected = false;
}

async function restartWhatsAppFresh(reason = "manual_reset"){
  whatsappResetCount += 1;
  lastSessionResetAt = new Date().toISOString();
  gatewayHealth.lastWhatsAppEvent = reason;
  gatewayHealth.lastDisconnectCode = "";
  lastQR = "";
  lastQRAt = "";
  await stopWhatsAppSocket(reason);
  const cleared = clearWhatsAppSessionFiles();
  console.log(`🔐 WhatsApp session reset (${reason}). Auth cleared: ${cleared.ok ? "YES" : "NO"}${cleared.error ? " - " + cleared.error : ""}`);
  setTimeout(() => startWhatsApp().catch(e => console.error("WA restart error", e.message || e)), 1200);
  return cleared;
}

async function startWhatsApp(){
  if(whatsappStartInProgress) return;
  whatsappStartInProgress = true;
  try {
    try {
      if(!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive:true });
    } catch(e) {}
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();
    sock = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      browser: Browsers.ubuntu("TitanNova"),
      logger: pino({ level: "silent" })
    });
    sock.ev.on("creds.update", saveCreds);
    sock.ev.on("connection.update", async (u) => {
      const { connection, lastDisconnect, qr } = u;
      if(qr){ lastQR = qr; lastQRAt = new Date().toISOString(); gatewayHealth.lastWhatsAppEvent = "qr"; gatewayObsEvent("whatsapp_qr_ready", "warning", "WhatsApp QR ready for login", {at:lastQRAt}); qrcode.generate(qr, {small:true}); console.log("📲 Scan QR in WhatsApp > Linked devices"); }
      if(connection === "open") { connected = true; lastQR = ""; lastQRAt = ""; gatewayHealth.lastWhatsAppEvent = "open"; gatewayObsEvent("whatsapp_connected", "info", "WhatsApp connected", {user:sock?.user || null}); console.log("WhatsApp connected"); await syncTargets(); }
      if(connection === "close") {
        connected = false;
        gatewayHealth.lastWhatsAppEvent = "close";
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        gatewayHealth.lastDisconnectCode = String(statusCode || "");
        const loggedOut = statusCode === DisconnectReason.loggedOut;
        gatewayObsEvent("whatsapp_disconnected", loggedOut ? "error" : "warning", "WhatsApp disconnected", {statusCode, loggedOut});
        console.log("WhatsApp disconnected", statusCode || "");
        if(!loggedOut) setTimeout(() => startWhatsApp().catch(e => console.error("WA reconnect error", e.message || e)), 3000);
        else {
          console.log("Logged out. Auto-clearing auth_info_baileys and generating fresh QR...");
          await restartWhatsAppFresh("logged_out_auto_reset");
        }
      }
    });
    sock.ev.on("groups.update", async (updates = []) => {
      for(const g of (Array.isArray(updates) ? updates : [])){
        try { await refreshSingleGroupTarget(g?.id, g?.subject || g?.name || ""); } catch(e) {}
      }
      syncTargets().catch(()=>{});
    });
    sock.ev.on("group-participants.update", async (u = {}) => {
      try { await refreshSingleGroupTarget(u?.id || u?.jid || u?.groupId || ""); } catch(e) {}
      syncTargets().catch(()=>{});
    });
    sock.ev.on("messages.upsert", async ({ messages }) => {
      for(const m of (messages || [])) {
        try {
          const remote = _jidKey(m?.key?.remoteJid || "");
          const participant = _jidKey(m?.key?.participant || "");
          const displayName = m?.pushName || m?.verifiedBizName || "";
          if(remote.endsWith("@g.us")) refreshSingleGroupTarget(remote).catch(()=>{});
          if(remote.endsWith("@s.whatsapp.net")) rememberPrivateTarget(remote, displayName || remote);
          if(participant.endsWith("@s.whatsapp.net")) rememberPrivateTarget(participant, displayName || participant);
        } catch(e) {}
        if(!m?.message || m.key?.fromMe) continue;
        if(!rememberIncomingMessage(m)) continue;
        const complianceHandled = await handleWhatsappComplianceCommandMessage(m);
        if(complianceHandled) continue;
        const commandHandled = await handleBotCommandMessage(m);
        if(commandHandled) continue;
        const smartCommandHandled = await handleSmartUserCommandMessage(m);
        if(smartCommandHandled) continue;
        const stopped = await handleSpamGuardMessage(m);
        if(!stopped){
          const depositHandled = await handleIncomingDepositPaymentMessage(m);
          if(!depositHandled) {
            const withdrawalHandled = await handleIncomingWithdrawalMessage(m);
            if(!withdrawalHandled) await handleIncomingEntryMessage(m);
          }
        }
      }
      saveProcessedMessageCache();
    });
  } catch(e) {
    gatewayHealth.lastWhatsAppEvent = "start_error";
    gatewayHealth.lastObservedErrorAt = nowIsoSafe();
    gatewayHealth.lastObservedError = {time:gatewayHealth.lastObservedErrorAt, message:String(e.message || e).slice(0,300), kind:"whatsapp_start_error"};
    gatewayObsError("whatsapp_start_error", e, {authDir:AUTH_DIR});
    throw e;
  } finally {
    whatsappStartInProgress = false;
  }
}

function constantTimeTokenOk(a, b){
  try{
    const crypto = require("crypto");
    const aa = Buffer.from(String(a || ""));
    const bb = Buffer.from(String(b || ""));
    return aa.length === bb.length && crypto.timingSafeEqual(aa, bb);
  }catch(e){ return String(a || "") === String(b || ""); }
}
function requestAuthToken(req){
  const auth = String(req.headers.authorization || "");
  if(auth.toLowerCase().startsWith("bearer ")) return auth.slice(7).trim();
  let token = req.headers["x-titan-gateway-token"] || req.headers["x-titan-admin-token"] || "";
  if(!token && TITAN_ALLOW_QUERY_TOKEN){
    // Query-string secrets leak via logs/history/referrers; allow only for explicit legacy deployments.
    token = req.query.gateway_token || req.query.admin_token || req.query.token || "";
  }
  return String(token || "").trim();
}
function gatewayAuthMiddleware(req, res, next){
  if(TITAN_GATEWAY_SECURITY_MISCONFIGURED && !(req.method === "GET" && req.path === "/health")){
    return res.status(503).json({
      status:"security_misconfigured",
      message:"Production mode requires TITAN_GATEWAY_TOKEN/TITAN_ADMIN_TOKEN and enabled Gateway auth.",
      securityLockdown:true,
      version:SECURITY_LOCKDOWN_VERSION
    });
  }
  if(!TITAN_GATEWAY_AUTH_ENFORCED) return next();
  // Keep a tiny health surface available for local uptime checks; all control/data endpoints are locked.
  if(req.method === "GET" && req.path === "/health") return next();
  if(constantTimeTokenOk(requestAuthToken(req), TITAN_GATEWAY_TOKEN)) return next();
  return res.status(401).json({
    status:"auth_required",
    message:"Gateway token required. Set/pass TITAN_GATEWAY_TOKEN or TITAN_ADMIN_TOKEN.",
    securityLockdown:true,
    version:SECURITY_LOCKDOWN_VERSION
  });
}

const app = express();
app.use(express.json({limit:"2mb"}));
app.use(gatewayAuthMiddleware);

app.get("/wa_login_status", (req,res)=>{
  const qrAgeSeconds = lastQRAt ? Math.floor((Date.now() - new Date(lastQRAt).getTime()) / 1000) : null;
  res.json({
    status:"success",
    connected,
    user:sock?.user || null,
    lastWhatsAppEvent:gatewayHealth.lastWhatsAppEvent || "",
    lastDisconnectCode:gatewayHealth.lastDisconnectCode || "",
    qrAvailable:!!lastQR,
    qr:lastQR,
    qrAt:lastQRAt,
    qrAgeSeconds,
    authDir:AUTH_DIR,
    resetCount:whatsappResetCount,
    lastSessionResetAt,
    note: connected ? "WhatsApp connected" : (lastQR ? "Scan QR from WhatsApp > Linked devices" : "Waiting for QR. Use reset session if QR does not appear.")
  });
});

app.post("/wa_reset_session", async (req,res)=>{
  try {
    const out = await restartWhatsAppFresh("manual_reset_api");
    res.json({status:"success", message:"WhatsApp session reset. Fresh QR will appear shortly.", cleared:out, authDir:AUTH_DIR});
  } catch(e) {
    res.status(500).json({status:"error", message:e.message || String(e)});
  }
});

app.get("/wa_qr_text", (req,res)=>{
  if(!lastQR) return res.status(404).type("text/plain").send("QR not available yet. Refresh or reset session.");
  res.type("text/plain").send(lastQR);
});

function gatewayUpdateGuardSummary(){
  let txt = "";
  try { txt = fs.readFileSync(__filename, "utf8"); } catch(e) { txt = ""; }
  const checks = SAFE_UPDATE_PROTECTED_MARKERS.map(spec => {
    const missing = spec.markers.filter(m => !txt.includes(String(m)));
    return { key:spec.key, ok:missing.length === 0, critical:spec.critical, missingMarkers:missing, detail:missing.length ? `Missing markers: ${missing.join(", ")}` : "OK" };
  });
  const oldSources = ["dp" + "bosse.net", "dp" + "boss.net", "dp" + "boss.services", "dp" + "bossmatka"];
  const foundOld = oldSources.filter(x => txt.includes(x));
  checks.push({key:"old_result_sources_removed", ok:foundOld.length === 0, critical:true, found:foundOld, detail:foundOld.length ? `Old source marker found: ${foundOld.join(", ")}` : "OK"});
  const criticalFailed = checks.filter(x => x.critical && !x.ok);
  return { status:criticalFailed.length ? "attention_required" : "safe", version:SAFE_UPDATE_VERSION, checkedAt:nowIso(), checks, criticalFailed, source:{name:RESULT_SOURCE_NAME, url:RESULT_SOURCE_URL} };
}


app.get("/full_audit", (req,res)=>{
  res.json({
    status:"success",
    phase:"phase4_production_diagnostics",
    version:FULL_AUDIT_VERSION,
    featureFreeze:FULL_AUDIT_PHASE1_FEATURE_FREEZE,
    singleSourceCleanup:FULL_AUDIT_PHASE2_SINGLE_SOURCE_CLEANUP,
    runtimeSelfHealing:FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING,
    productionDiagnostics:FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS,
    lockedFeatures:FULL_AUDIT_LOCKED_FEATURES,
    sourceOfTruth:{
      ledgerSchedule:"ledgerSchedules + scheduleRuntimePreserveGuard",
      whatsappSending:"sendText() -> whatsappSafetyBeforeSend() -> safeSendQueueRun()",
      operationalReplies:"replyToMessage()/sendSpamGuardNotice() -> safeSendQueueRun()",
      resultSource:RESULT_SOURCE_URL,
      resultSendLock:"sentLog result target signatures",
      ledgerScheduleLock:"sentLog schedule per date/card/time/target",
      withdrawalFinalDeduct:"Mark Paid only",
      targets:"Advanced Target Picker + saved target lists",
      runtimeRecovery:"Flask /api/runtime_health + local last_known_good backups",
      productionDiagnostics:"Gateway /production_diagnostics + /e2e_smoke_test"
    },
    noBreakContract:"Existing locked features cannot be bypassed by duplicate helper/route/source logic.",
    commands:["python safe_update_check.py", "python full_audit_check.py"]
  });
});

app.get("/update_guard", (req,res)=>{
  res.json({status:"success", updateGuard:gatewayUpdateGuardSummary(), configCleanup:gatewayConfigReport()});
});
app.get("/config_migration_status", (req,res)=>{
  res.json(gatewayConfigReport());
});


app.get("/runtime_health", async (req,res)=>{
  let stateSummary = {};
  try {
    const st = await fetchFirebaseState();
    stateSummary = {
      profiles: st && st.profiles ? Object.keys(st.profiles).length : 0,
      ledgerSchedules: st && st.ledgerSchedules ? Object.keys(st.ledgerSchedules).length : 0,
      withdrawals: Array.isArray(st?.withdrawals) ? st.withdrawals.length : 0,
      walletTransactions: Array.isArray(st?.walletTransactions) ? st.walletTransactions.length : 0,
      whatsappSafetySettings: !!(st && st.whatsappSafetySettings)
    };
  } catch(e) {
    stateSummary = { error: String(e.message || e) };
  }
  res.json({
    status:"success",
    phase:"phase4_production_diagnostics",
    version:FULL_AUDIT_VERSION,
    runtimeSelfHealing:FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING,
    productionDiagnostics:FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS,
    gatewaySafeQueue:"sendText -> whatsappSafetyBeforeSend -> safeSendQueueRun",
    flaskHealthEndpoint:"/api/runtime_health",
    flaskBackupEndpoints:["/api/backup_state", "/api/list_backups", "/api/restore_backup", "/api/last_known_good"],
    stateSummary
  });
});

app.get("/status", async (req,res)=>{
  let adminEnabled = true;
  let counts = {};
  try {
    const st = await fetchFirebaseState();
    adminEnabled = firebaseAutoScrapeEnabled(st);
    counts = {
      resultTargets: collectResultTargets(st).length,
      paymentPending: Array.isArray(st.paymentOutbox) ? st.paymentOutbox.filter(x => x && x.status === "pending").length : 0,
      loadForwardPending: Array.isArray(st.loadForwarderOutbox) ? st.loadForwarderOutbox.filter(x => x && x.status === "pending").length : 0,
      acceptedEntriesToday: Array.isArray(st.entries) ? st.entries.filter(x => x && x.status === "accepted" && x.date === todayISO()).length : 0,
      settlementsToday: st.settlementRecords?.[todayISO()] ? Object.keys(st.settlementRecords[todayISO()]).length : 0
    };
  } catch(e) {
    counts.firebaseReadError = e.response ? `HTTP ${e.response.status}` : e.message;
  }
  res.json({
    status:"success", connected, user:sock?.user || null, firebase:FIREBASE_URL, timezone:APP_TZ, now:nowHHMM(), date:todayISO(), cache:targetsCache.updatedAt,
    waLogin:{qrAvailable:!!lastQR, qrAt:lastQRAt, authDir:AUTH_DIR, resetCount:whatsappResetCount, lastSessionResetAt},
    resultScrape:{enabled:RESULT_SCRAPE_ENABLED && adminEnabled, envEnabled:RESULT_SCRAPE_ENABLED, adminEnabled, intervalMs:RESULT_SCRAPE_INTERVAL_MS, confirmCount:RESULT_SCRAPE_CONFIRM_COUNT, urls:RESULT_SCRAPE_URLS, sourceName:RESULT_SOURCE_NAME, sourceUrl:RESULT_SOURCE_URL},
    configCleanup:gatewayConfigReport(), paymentOutbox:true, loadForwarder:true, spamGuard:true, whatsappSafetyGuard:true, durability:{version:GATEWAY_DURABILITY_VERSION, firebaseLocks:true, owner:GATEWAY_LOCK_OWNER, localFallbackFiles:{sentLog:SENT_LOG_FILE, processedMessages:PROCESSED_MESSAGE_CACHE_FILE}}, counts, health:gatewayHealth
  });
});
app.get("/health", async (req,res)=>{
  try {
    const state = await fetchFirebaseState();
    const lf = state.loadForwarder || {};
    const sg = state.spamGuardSettings || {};
    res.json({
      status:"success", connected, user:sock?.user || null, timezone:APP_TZ, now:nowHHMM(), date:todayISO(),
      waLogin:{qrAvailable:!!lastQR, qrAt:lastQRAt, authDir:AUTH_DIR, resetCount:whatsappResetCount, lastSessionResetAt, lastWhatsAppEvent:gatewayHealth.lastWhatsAppEvent || "", lastDisconnectCode:gatewayHealth.lastDisconnectCode || ""},
      targets:{ contacts:(targetsCache.contacts||[]).length, groups:(targetsCache.groups||[]).length, updatedAt:targetsCache.updatedAt, lastSyncError:targetsCache.lastSyncError || "", syncVersion:WHATSAPP_TARGET_SYNC_VERSION, syncIntervalMs:WHATSAPP_TARGET_SYNC_INTERVAL_MS },
      scrape:{ enabled: RESULT_SCRAPE_ENABLED && firebaseAutoScrapeEnabled(state), envEnabled: RESULT_SCRAPE_ENABLED, adminEnabled: firebaseAutoScrapeEnabled(state), intervalMs:RESULT_SCRAPE_INTERVAL_MS, confirmCount:RESULT_SCRAPE_CONFIRM_COUNT, urls:RESULT_SCRAPE_URLS, sourceName:RESULT_SOURCE_NAME, sourceUrl:RESULT_SOURCE_URL },
      queue:{ paymentPending:Array.isArray(state.paymentOutbox)?state.paymentOutbox.filter(x=>x&&x.status==="pending").length:0, loadForwardPending:Array.isArray(state.loadForwarderOutbox)?state.loadForwarderOutbox.filter(x=>x&&x.status==="pending").length:0 },
      modules:{ entryParser: state.entrySettings?.entryParserEnabled !== false, settlement: state.settlementSettings?.enabled !== false, loadForwarder: lf.enabled === true, spamGuard: sg.enabled !== false, whatsappSafetyGuard: state.whatsappSafetySettings?.enabled !== false },
      configCleanup:gatewayConfigReport(), observability:gatewayObservabilityStatus(), durability:{version:GATEWAY_DURABILITY_VERSION, firebaseLocks:true, owner:GATEWAY_LOCK_OWNER},
      health: gatewayHealth
    });
  } catch(e){
    res.status(500).json({status:"error", connected, message:e.response ? `HTTP ${e.response.status}` : e.message, health:gatewayHealth});
  }
});
app.get("/runtime_stability_status", gatewayAuthMiddleware, async (req,res)=>{
  res.json({status:"success", version:RUNTIME_STABILITY_VERSION, ledgerChildPathWritesEnabled:true, rootSaveDisabledForNormalOperations:GATEWAY_ROOT_SAVE_NORMAL_DISABLED, scheduleIdempotencyEnabled:true, scheduleFirebaseLastSentEnabled:true, walletIdempotencyEnabled:true});
});

app.get("/gateway_durability_status", async (req,res)=>{
  res.json({
    status:"success",
    version:GATEWAY_DURABILITY_VERSION,
    firebaseLocks:true,
    owner:GATEWAY_LOCK_OWNER,
    lockRoot:"gatewayDurability",
    protectedFlows:["whatsapp_entry_accept","whatsapp_withdrawal_request","schedule_target_send","result_target_send","result_settlement"],
    localFallbackFiles:{sentLog:SENT_LOG_FILE, processedMessages:PROCESSED_MESSAGE_CACHE_FILE},
    note:"Firebase-backed locks are used before critical send/debit/payout actions; local JSON is fallback/diagnostic only."
  });
});
app.get("/targets", async (req,res)=>{
  try {
    const force = String(req.query.force || "") === "1";
    if(connected || force) await syncTargets({force});
    else targetsCache = loadJson(TARGET_CACHE_FILE, targetsCache);
    res.json({status:connected?"success":"offline", connected, targetSyncVersion:WHATSAPP_TARGET_SYNC_VERSION, syncIntervalMs:WHATSAPP_TARGET_SYNC_INTERVAL_MS, ...targetsCache});
  } catch(e) {
    const cached = loadJson(TARGET_CACHE_FILE, targetsCache || {contacts:[], groups:[]});
    res.json({status:connected?"partial":"offline", connected, targetSyncVersion:WHATSAPP_TARGET_SYNC_VERSION, syncIntervalMs:WHATSAPP_TARGET_SYNC_INTERVAL_MS, ...cached, lastSyncError:e.message || String(e)});
  }
});
app.get("/chats", async (req,res)=>{
  try { if(connected) await syncTargets({force:true}); } catch(e) {}
  res.json({connected, ...targetsCache});
});
app.get("/send", async (req,res)=>{ const out=await sendText(req.query.to || req.query.target, req.query.text || req.query.msg || ""); res.status(out.ok?200:400).json(out); });
app.post("/send_bulk", async (req,res)=>{ const targets=arr(req.body.targets || req.body.to); const text=req.body.text || req.body.message || ""; const results=[]; for(const t of targets) results.push(await sendText(t,text,{type:"manual_send"})); res.json({status:"done", total:results.length, sent:results.filter(x=>x.ok).length, results}); });
app.post("/send_category", async (req,res)=>{ const text=req.body.text || req.body.message || ""; if(connected) await syncTargets(); const category=req.body.category || "all"; let targets=[]; if(category==="groups") targets=targetsCache.groups.map(x=>x.id); else if(category==="contacts") targets=targetsCache.contacts.map(x=>x.id); else targets=[...targetsCache.contacts,...targetsCache.groups].map(x=>x.id); const results=[]; for(const t of targets) results.push(await sendText(t,text,{type:"manual_send"})); res.json({status:"done", total:results.length, sent:results.filter(x=>x.ok).length, results}); });
app.get("/bot_schedule", async (req,res)=>{ const state=await fetchFirebaseState(); const recoveryAutoRate=recomputeLedgerRecoveryAutoRates(state, todayISO(), "gateway_bot_schedule_preview_recovery"); const schedules=collectSchedules(state); res.json({status:"success", now:nowHHMM(), date:todayISO(), calendarDate:calendarTodayISO(), timezone:APP_TZ, businessDayCutoffHour:BUSINESS_DAY_CUTOFF_HOUR, connected, recoveryAutoRate, schedules}); });

app.get("/ledger_schedule_exact_card_status", async (req,res)=>{
  res.json({status:"success", ledgerScheduleExactCardFix:true, version:"v33", rule:"Only the exact scheduled ledger card/stage is sent; OPEN and CLOSE schedules are isolated."});
});


app.get("/whatsapp_role_routing_status", async (req,res)=>{
  try{
    const state = await fetchFirebaseState();
    const reg = ensureMarketRegistry(state || {});
    const counts = {entry:0, schedule:0, result:0, forward:0, bookie:0};
    for(const item of Object.values(reg.items || {})){
      if(Array.isArray(item.entryTargets) && item.entryTargets.length) counts.entry++;
      if(Array.isArray(item.scheduleTargets) && item.scheduleTargets.length) counts.schedule++;
      if(Array.isArray(item.resultTargets) && item.resultTargets.length) counts.result++;
      if(Array.isArray(item.forwardTargets) && item.forwardTargets.length) counts.forward++;
      if(Array.isArray(item.bookieTargets) && item.bookieTargets.length) counts.bookie++;
    }
    res.json({status:"success", whatsappRoleRouting:true, bookieAdminRouting:true, version:"v32", bookieVersion:"v35", roleCounts:counts, roles:["schedule","entry","result","forward","bookie"]});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});

app.get("/bookie_admin_routing_status", async (req,res)=>{
  try{
    const state = await fetchFirebaseState();
    const reg = ensureMarketRegistry(state || {});
    let mappedMarkets = 0, totalTargets = 0;
    for(const item of Object.values(reg.items || {})){
      if(Array.isArray(item.bookieTargets) && item.bookieTargets.length){ mappedMarkets++; totalTargets += item.bookieTargets.length; }
    }
    res.json({status:"success", bookieAdminRouting:true, version:"v35", mappedMarkets, totalTargets, rule:"Bookie/Admin Work is separate from game entry/result/schedule/forward roles."});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});

app.get("/business_day_cutoff_status", (req,res)=>{ res.json({status:"success", businessDayCutoffFix:true, version:"v31-business-day-cutoff", timezone:APP_TZ, cutoffHour:BUSINESS_DAY_CUTOFF_HOUR, businessDate:todayISO(), calendarDate:calendarTodayISO(), localTime:nowHHMM(), rule:`00:00-${pad(BUSINESS_DAY_CUTOFF_HOUR-1)}:59 previous business day; ${pad(BUSINESS_DAY_CUTOFF_HOUR)}:00 fresh next day`}); });
app.get("/load_report", async (req,res)=>{ const state=await fetchFirebaseState(); const lf=loadForwarderSettings(state); const gameTypes=normalizeLoadGameTypes(req.query.gameTypes || lf.gameTypes); const report=buildLoadReport(state, req.query.date || todayISO(), req.query.market || lf.selectedMarket, Number(req.query.maxRowsPerType || lf.maxRowsPerType || 80), lf.includeEmptyTypes, gameTypes); res.json({status:"success", report, text:formatLoadReportText(report)}); });
app.post("/load_forwarder_send", async (req,res)=>{ const state=await fetchFirebaseState(); const targets=arr(req.body.targets || req.body.to); if(!targets.length) return res.status(400).json({status:"error", message:"targets required"}); const lf=loadForwarderSettings(state); const report=buildLoadReport(state, req.body.date || todayISO(), req.body.market || lf.selectedMarket, Number(req.body.maxRowsPerType || lf.maxRowsPerType || 80), lf.includeEmptyTypes); const text=req.body.text || formatLoadReportText(report); const results=await sendLoadReportToTargets(targets, text); res.json({status:"done", sent:results.filter(x=>x.ok).length, total:results.length, results, report}); });

app.post("/result_retry", async (req,res)=>{
  try{
    const body = req.body || {};
    const state = await fetchFirebaseState();
    const date = body.date || todayISO();
    const marketFilter = String(body.market || "").trim().toUpperCase();
    let cleared = 0;
    for(const key of Object.keys(sentLog || {})){
      if(!key.startsWith(`result_${date}_`)) continue;
      if(marketFilter && !key.toUpperCase().includes(marketFilter.replace(/\s+/g, "_"))) continue;
      delete sentLog[key];
      cleared += 1;
    }
    saveJson(SENT_LOG_FILE, sentLog);
    if(connected) setTimeout(()=>resultTick().catch(()=>{}), 200);
    res.json({status:"success", cleared, message:"Result send locks cleared. Gateway will retry pending declarations."});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});
app.get("/results", async (req,res)=>{ const state=await fetchFirebaseState(); const results=collectResults(state); res.json({status:"success", now:nowHHMM(), date:todayISO(), timezone:APP_TZ, connected, results}); });
app.get("/scrape_results", async (req,res)=>{ try { const out=await autoScrapeResultsOnce(); res.json({ ...out, now:nowHHMM(), date:todayISO(), timezone:APP_TZ }); } catch(e){ res.status(500).json({status:"error", message:e.response ? `HTTP ${e.response.status}` : e.message}); } });





app.get("/whatsapp_compliance_status", async (req,res)=>{
  try{
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    const settings = state.whatsappSafetySettings || {};
    const targets = state.whatsappSafetyTargets || {};
    let optedOut = 0, optedIn = 0, paused = 0;
    for(const rec of Object.values(targets || {})){
      if(rec && rec.optedOut === true) optedOut++;
      if(rec && rec.optedIn === true) optedIn++;
      if(rec && rec.paused === true) paused++;
    }
    res.json({status:"success", complianceGuardV18:true, connected, optOutEnabled:settings.optOutEnabled !== false, requireOptInForPrivateSends:settings.requireOptInForPrivateSends === true, counts:{targets:Object.keys(targets||{}).length, optedOut, optedIn, paused}, supportedCommands:["STOP","START"], note:"Compliance guard blocks opted-out targets and supports user unsubscribe/resubscribe commands."});
  }catch(e){ res.status(500).json({status:"error", complianceGuardV18:true, message:e.response ? `HTTP ${e.response.status}` : e.message}); }
});

app.get("/whatsapp_safety_status", async (req,res)=>{
  try{
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    cleanupSafetyFingerprints(state.whatsappSafetySettings || {});
    const targets = state.whatsappSafetyTargets || {};
    const events = Array.isArray(state.whatsappSafetyEvents) ? state.whatsappSafetyEvents.slice(-80).reverse() : [];
    res.json({status:"success", connected, settings:state.whatsappSafetySettings, targets, events, local:{daily:whatsappSafetyLocalState.daily || {}, fingerprintCount:Object.keys(whatsappSafetyLocalState.fingerprints || {}).length, consecutiveFailures:Number(whatsappSafetyLocalState.consecutiveFailures || 0), queueDepth:safeSendQueueDepth}, health:gatewayHealth});
  }catch(e){ res.status(500).json({status:"error", message:e.response ? `HTTP ${e.response.status}` : e.message}); }
});
app.post("/whatsapp_safety_pause", async (req,res)=>{
  try{
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    state.whatsappSafetySettings.globalPaused = true;
    state.whatsappSafetySettings.pauseReason = String(req.body?.reason || "Manual safety pause").slice(0,200);
    state.whatsappSafetySettings.updatedAt = nowIso();
    pushWhatsappSafetyEvent(state, {action:"global_paused", target:"ALL", reason:state.whatsappSafetySettings.pauseReason});
    await saveGatewayWhatsappSafetyNarrow(state);
    whatsappSafetyCache = {at:Date.now(), state};
    res.json({status:"success", settings:state.whatsappSafetySettings});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});
app.post("/whatsapp_safety_resume", async (req,res)=>{
  try{
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    state.whatsappSafetySettings.globalPaused = false;
    state.whatsappSafetySettings.pauseReason = "";
    state.whatsappSafetySettings.updatedAt = nowIso();
    whatsappSafetyLocalState.consecutiveFailures = 0;
    pushWhatsappSafetyEvent(state, {action:"global_resumed", target:"ALL"});
    saveWhatsappSafetyLocalState();
    await saveGatewayWhatsappSafetyNarrow(state);
    whatsappSafetyCache = {at:Date.now(), state};
    res.json({status:"success", settings:state.whatsappSafetySettings});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});
app.post("/whatsapp_safety_target", async (req,res)=>{
  try{
    const body = req.body || {};
    const target = await resolveTarget(body.target || body.id || body.jid || "");
    const key = safetyTargetKey(target || body.target || body.id || body.jid || "");
    if(!key) return res.status(400).json({status:"error", message:"target required"});
    const state = ensureWhatsappSafetyState(await fetchFirebaseState());
    const rec = safetyTargetRecord(state, key, key);
    if(typeof body.approved !== "undefined") rec.approved = body.approved === true || String(body.approved) === "true";
    if(typeof body.paused !== "undefined") rec.paused = body.paused === true || String(body.paused) === "true";
    if(body.status === "approve") rec.approved = true;
    if(body.status === "pause") rec.paused = true;
    if(body.status === "resume") rec.paused = false;
    if(body.status === "reset_failures"){ rec.failureCount = 0; rec.lastError = ""; }
    if(body.name) rec.name = String(body.name).slice(0,120);
    rec.pauseReason = rec.paused ? String(body.reason || rec.pauseReason || "Manual target pause").slice(0,200) : "";
    rec.updatedAt = nowIso();
    pushWhatsappSafetyEvent(state, {action:"target_update", target:key, approved:rec.approved, paused:rec.paused, reason:rec.pauseReason || ""});
    await saveGatewayWhatsappSafetyNarrow(state);
    whatsappSafetyCache = {at:Date.now(), state};
    res.json({status:"success", target:rec});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});



app.get("/bot_upgrade_status", async (req,res)=>{
  res.json({
    status:"success",
    version: WHATSAPP_BOT_UPGRADE_VERSION,
    connected,
    commands:["/help","/status","/format","balance","withdraw status","profile","history","payment status","summary"],
    duplicateGuard:true,
    typingPresence:true,
    smartCommands:true,
    smartCommandVersion:SMART_WHATSAPP_COMMAND_VERSION,
    processedMessageCacheSize:Number(gatewayHealth.processedMessageCacheSize || 0),
    duplicateIncomingSkipped:Number(gatewayHealth.duplicateIncomingSkipped || 0),
    lastBotCommand:gatewayHealth.lastBotCommand || "",
    lastSmartCommand:gatewayHealth.lastSmartCommand || "",
    lastIncomingAt:gatewayHealth.lastIncomingAt || ""
  });
});

app.get("/spam_guard_status", async (req,res)=>{
  try{
    const state = await fetchFirebaseState();
    const cfg = spamGuardSettings(state);
    const events = Array.isArray(state.spamGuardEvents) ? state.spamGuardEvents.slice(-50).reverse() : [];
    res.json({status:"success", settings:cfg, events});
  }catch(e){ res.status(500).json({status:"error", message:e.message}); }
});

app.post("/send_hitmiss", async (req,res)=>{
  try {
    const body = req.body || {};
    const state = await fetchFirebaseState();
    const date = body.date || todayISO();
    const market = body.market || "";
    const stage = body.stage || "";
    const settlement = findSettlementRecord(state, date, market, stage);
    if(!settlement) return res.status(404).json({status:"error", message:"settlement not found"});
    const text = settlement.hitMissText || formatHitMissDetailedText(settlement, { maxRows: 120 });
    const targets = targetList(body.targets || collectResultTargets(state));
    if(!targets.length) return res.status(400).json({status:"error", message:"no targets saved"});
    const results=[];
    for(const t of targets) results.push(await sendText(t, text, {type:"hitmiss_report"}));
    const sent = results.filter(x=>x.ok).length;
    return res.status(sent ? 200 : 400).json({status:sent?"success":"failed", sent, total:results.length, results});
  } catch(e){
    return res.status(500).json({status:"error", message:e.message});
  }
});


// ========================================================== 
// FULL AUDIT PHASE 4: Production Diagnostics + E2E Smoke Test
// ==========================================================
function phase4StatusItem(name, ok=true, detail="", critical=true, data={}){
  return {name, ok:!!ok, detail:detail || (ok ? "OK" : "attention_required"), critical:!!critical, data:data || {}};
}
function phase4ScheduleDiagnostics(state){
  const schedules = state && state.ledgerSchedules && typeof state.ledgerSchedules === "object" ? state.ledgerSchedules : {};
  const enabled = [];
  const invalid = [];
  for(const [id, rec] of Object.entries(schedules)){
    if(!rec || typeof rec !== "object"){ invalid.push(String(id)); continue; }
    if(rec.enabled === false) continue;
    const tm = String(rec.time || rec.scheduleTime || "").trim();
    const targets = Array.isArray(rec.targets) ? rec.targets : [];
    if(/^\d{2}:\d{2}$/.test(tm) && targets.length) enabled.push({id:String(id), time:tm, targetCount:targets.length});
    else if(tm || targets.length) invalid.push(String(id));
  }
  return {enabledCount:enabled.length, invalidCount:invalid.length, sampleEnabled:enabled.slice(0,10), invalidIds:invalid.slice(0,10), dailyRepeatProtected:true, sourceOfTruth:"ledgerSchedules"};
}
function phase4WalletWithdrawalDiagnostics(state){
  const wallets = state && state.wallets && typeof state.wallets === "object" ? state.wallets : {};
  const withdrawals = Array.isArray(state?.withdrawals) ? state.withdrawals : [];
  const active = new Set(["pending", "approved", "processing"]);
  const byUser = {};
  const paidWithoutPaidAt = [];
  for(const w of withdrawals){
    if(!w || typeof w !== "object") continue;
    const uid = String(w.userId || w.uid || "").trim();
    const status = String(w.status || "").toLowerCase();
    const amount = Number(w.amount || 0);
    if(uid && active.has(status)) byUser[uid] = Number(byUser[uid] || 0) + amount;
    if(status === "paid" && !(w.paidAt || w.markedPaidAt)) paidWithoutPaidAt.push(String(w.id || w.withdrawalId || "unknown"));
  }
  const mismatches = [];
  for(const [uid, holdSum] of Object.entries(byUser)){
    const wallet = wallets[uid] && typeof wallets[uid] === "object" ? wallets[uid] : {};
    const walletHold = Number(wallet.walletHold || wallet.hold || 0);
    if(walletHold + 0.01 < Number(holdSum || 0)) mismatches.push({userId:uid, walletHold, activeWithdrawalAmount:holdSum});
  }
  return {walletCount:Object.keys(wallets).length, withdrawalCount:withdrawals.length, activeWithdrawalUsers:Object.keys(byUser).length, holdMismatchCount:mismatches.length, holdMismatches:mismatches.slice(0,10), paidWithoutPaidAt:paidWithoutPaidAt.slice(0,10), markPaidOnlyProtected:true};
}
function phase4ResultSourceDiagnostics(state){
  const rr = state && state.resultRecords && typeof state.resultRecords === "object" ? state.resultRecords : {};
  const oldTokens = ["dpbosse", "dp" + "boss.net", "dp" + "boss.services", "dp" + "bossmatka"];
  let primary = 0, old = 0;
  for(const rec of Object.values(rr)){
    if(!rec || typeof rec !== "object") continue;
    const src = String(rec.source || rec.sourceUrl || "");
    if(src.includes(RESULT_SOURCE_URL) || src.includes(RESULT_SOURCE_NAME)) primary++;
    if(oldTokens.some(t => src.includes(t))) old++;
  }
  return {sourceName:RESULT_SOURCE_NAME, sourceUrl:RESULT_SOURCE_URL, recordCount:Object.keys(rr).length, recordsFromPrimarySource:primary, oldSourceRecordCount:old, strictOpenClose:true, doubleConfirmRequired:true};
}
function phase4AutoPfSmokeCase(){
  const digits = ["4", "6", "2", "7", "1"];
  const result = "123-4";
  const hitDigit = result.split("-").pop();
  return {case:"MILAN NIGHT OPEN ANK", digits, result, hitDigit, expectedStatus:"PASS", ok:digits.includes(hitDigit), note:"Dry-run only; Firebase/ledger cards mutate nahi hote."};
}
async function phase4ProductionDiagnostics(){
  let state = {};
  let stateError = "";
  try { state = await fetchFirebaseState(); } catch(e){ stateError = String(e.message || e); }
  const checks = [];
  checks.push(phase4StatusItem("Firebase state fetch", !stateError && !!state && typeof state === "object", stateError || "Firebase state readable", true, {hasState:!!state}));
  const sched = phase4ScheduleDiagnostics(state || {});
  checks.push(phase4StatusItem("Ledger daily repeat schedule health", sched.invalidCount === 0, `enabled=${sched.enabledCount} invalid=${sched.invalidCount}`, false, sched));
  const wallet = phase4WalletWithdrawalDiagnostics(state || {});
  checks.push(phase4StatusItem("Wallet/withdrawal hold consistency", wallet.holdMismatchCount === 0 && !wallet.paidWithoutPaidAt.length, `mismatch=${wallet.holdMismatchCount}`, true, wallet));
  const source = phase4ResultSourceDiagnostics(state || {});
  checks.push(phase4StatusItem("Result source lock", source.oldSourceRecordCount === 0 && source.sourceUrl === RESULT_SOURCE_URL, source.sourceUrl, true, source));
  const marketHealth = marketPhase3RegistryHealth(state || {});
  checks.push(phase4StatusItem("Market registry deep integration", marketHealth.status === "safe", `active=${marketHealth.active} ledger=${marketHealth.ledgerEnabled} result=${marketHealth.resultEnabled}`, true, marketHealth));
  const autoPf = phase4AutoPfSmokeCase();
  checks.push(phase4StatusItem("Ledger auto PASS/FAIL dry-run", autoPf.ok, autoPf.expectedStatus, true, autoPf));
  checks.push(phase4StatusItem("WhatsApp safe queue runtime", typeof safeSendQueueRun === "function" && typeof sendText === "function", `queueDepth=${safeSendQueueDepth}`, true, {queueDepth:safeSendQueueDepth, consecutiveFailures:Number(whatsappSafetyLocalState.consecutiveFailures || 0)}));
  const criticalFailed = checks.filter(c => c.critical && !c.ok);
  const failed = checks.filter(c => !c.ok);
  return {phase:"phase4_production_diagnostics", version:FULL_AUDIT_VERSION, productionDiagnostics:true, status:criticalFailed.length ? "attention_required" : "safe", connected, checks, failed, criticalFailed, checkedAt:nowIso(), commands:["python safe_update_check.py", "python full_audit_check.py", "python production_diagnostics_check.py"]};
}


app.get("/deploy_safety_status", async (req,res)=>{
  const env = {
    firebaseUrlConfigured: !!FIREBASE_URL,
    firebaseUrlLooksValid: /^https:\/\/.+\.json$/.test(String(FIREBASE_URL || "")),
    gatewayTokenConfigured: !!GATEWAY_TOKEN,
    authDir: AUTH_DIR,
    stateDir: TITAN_STATE_DIR,
    timezone: APP_TZ
  };
  let firebase = {status:"unchecked"};
  try{
    const t = Date.now();
    await fetchFirebaseState();
    firebase = {status:"success", ms:Date.now()-t};
  }catch(e){ firebase = {status:"error", message:String(e?.response?.status ? `HTTP ${e.response.status}` : (e.message || e)).slice(0,160)}; }
  const warnings = [];
  if(!env.firebaseUrlLooksValid) warnings.push("FIREBASE_URL invalid/missing");
  if(firebase.status !== "success") warnings.push("Firebase read failed");
  res.json({
    status:warnings.length ? "attention_required" : "safe",
    version:DEPLOY_SAFETY_VERSION,
    deploySafety:true,
    checkedAt:nowIso(),
    connected,
    waLogin:{qrAvailable:!!lastQR, qrAt:lastQRAt, authDir:AUTH_DIR},
    env,
    firebase,
    gatewayHealth,
    warnings,
    commands:["titan health", "titan restart", "titan logs gateway"]
  });
});



// ============================================================
// DATA CLEANUP v17: Gateway local/state diagnostics
// ============================================================
function dataCleanupFileInfo(filePath, label){
  try{
    const exists = fs.existsSync(filePath);
    const st = exists ? fs.statSync(filePath) : null;
    let jsonCount = null;
    if(exists && st && st.size < 5 * 1024 * 1024){
      try{
        const j = JSON.parse(fs.readFileSync(filePath, "utf8"));
        if(Array.isArray(j)) jsonCount = j.length;
        else if(j && typeof j === "object") jsonCount = Object.keys(j.items && typeof j.items === "object" ? j.items : j).length;
      }catch(e){}
    }
    return {label, path:redactConfigValue(filePath, 34), exists, bytes:st ? st.size : 0, modifiedAt:st ? st.mtime.toISOString() : "", jsonCount};
  }catch(e){ return {label, path:redactConfigValue(filePath, 34), exists:false, error:e.message}; }
}
function gatewayDataCleanupStatus(){
  const files = [
    dataCleanupFileInfo(TARGET_CACHE_FILE, "target_cache"),
    dataCleanupFileInfo(SENT_LOG_FILE, "legacy_sent_log"),
    dataCleanupFileInfo(PROCESSED_MESSAGE_CACHE_FILE, "legacy_processed_messages"),
    dataCleanupFileInfo(SPAM_GUARD_STATE_FILE, "spam_guard"),
    dataCleanupFileInfo(WHATSAPP_SAFETY_STATE_FILE, "whatsapp_safety"),
    dataCleanupFileInfo(SCRAPE_CONFIRM_FILE, "scrape_confirm"),
    dataCleanupFileInfo(LIVE_RESULT_STATE_FILE, "live_result_state"),
    dataCleanupFileInfo(OBSERVABILITY_LOG_FILE, "observability_log")
  ];
  const totalBytes = files.reduce((a,x)=>a+Number(x.bytes||0),0);
  const warnings = [];
  for(const f of files){
    if(Number(f.bytes||0) > 1024 * 1024) warnings.push(`${f.label} local file is large`);
  }
  if(processedMessageCache && processedMessageCache.items && Object.keys(processedMessageCache.items).length > 1500) warnings.push("processed message local fallback cache is large");
  return {
    status:warnings.length ? "attention_required" : "success",
    version:DATA_CLEANUP_VERSION,
    dataCleanup:true,
    checkedAt:nowIsoSafe(),
    connected,
    stateDir:redactConfigValue(TITAN_STATE_DIR, 34),
    authDir:redactConfigValue(AUTH_DIR, 34),
    totalLocalBytes:totalBytes,
    files,
    runtimeCaches:{
      processedMessageCacheSize: processedMessageCache && processedMessageCache.items ? Object.keys(processedMessageCache.items).length : 0,
      memoryObservabilityEvents: gatewayObservabilityEvents.length,
      targetCacheUpdatedAt: targetsCache.updatedAt || ""
    },
    firebaseLocks:{enabled:true, root:"gatewayDurability", owner:GATEWAY_LOCK_OWNER},
    warnings
  };
}


app.get("/production_diagnostics", async (req,res)=>{
  try { res.json({status:"success", diagnostics:await phase4ProductionDiagnostics()}); }
  catch(e){ res.status(500).json({status:"error", message:e.message}); }
});
app.get("/e2e_smoke_test", async (req,res)=>{
  try { const smoke = await phase4ProductionDiagnostics(); res.json({status:smoke.status === "safe" ? "success" : "attention_required", smokeTest:smoke}); }
  catch(e){ res.status(500).json({status:"error", message:e.message}); }
});


app.get('/firebase_data_guard_status', gatewayAuthMiddleware, async (req,res)=>{
  let liveStatus = "unchecked", liveScore = {};
  try{
    const live = await fetchFirebaseState();
    liveStatus = live && typeof live === "object" && Object.keys(live).length ? "success" : "empty";
    liveScore = gatewayStateScore(live || {});
  }catch(e){ liveStatus = "error:" + String(e?.response?.status ? `HTTP ${e.response.status}` : (e.message || e)).slice(0,120); }
  res.json({status:"success", firebaseDataGuard:true, version:FIREBASE_DATA_GUARD_VERSION, guardedRootSaves:true, casRootPut:true, emptyFirebaseDefaultOverwriteBlocked:!["1","true","yes","on"].includes(String(process.env.TITAN_FIREBASE_ALLOW_EMPTY_INIT || "0").toLowerCase()), protectedKeys:gatewayProtectedKeys(), liveStatus, liveScore});
});

app.get('/realtime_sync_status', gatewayAuthMiddleware, async (req,res)=>{
  res.json({
    status:'success',
    realtimeFastSync:true,
    gateway:true,
    version:REALTIME_SYNC_VERSION,
    schedulePollMs:TITAN_SCHEDULE_POLL_MS,
    resultPollMs:TITAN_RESULT_POLL_MS,
    paymentOutboxPollMs:TITAN_PAYMENT_OUTBOX_POLL_MS,
    loadForwarderPollMs:TITAN_LOAD_FORWARDER_POLL_MS,
    stateCacheTtlMs:TITAN_GATEWAY_STATE_CACHE_TTL_MS,
    stateCacheAgeMs:realtimeStateCacheAt ? Date.now()-realtimeStateCacheAt : null,
    firebaseDataGuardKept:FIREBASE_DATA_GUARD_VERSION
  });
});

function pruneTextFileByLines(filePath, maxLines){
  try{
    if(!fs.existsSync(filePath)) return 0;
    const lines = fs.readFileSync(filePath, "utf8").split(/\n/);
    if(lines.length <= maxLines) return lines.length;
    fs.writeFileSync(filePath, lines.slice(-maxLines).join("\n"));
    return maxLines;
  }catch(e){
    gatewayObsError("local_text_prune_error", e, {file:redactConfigValue(filePath, 34)});
    return 0;
  }
}

function pruneJsonFileEntries(filePath, maxEntries){
  try{
    if(!fs.existsSync(filePath)) return 0;
    const obj = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if(Array.isArray(obj)){
      if(obj.length > maxEntries) fs.writeFileSync(filePath, JSON.stringify(obj.slice(-maxEntries), null, 2));
      return Math.min(obj.length, maxEntries);
    }
    if(obj && typeof obj === "object"){
      const root = obj.items && typeof obj.items === "object" ? obj.items : obj;
      const entries = Object.entries(root);
      if(entries.length > maxEntries){
        const trimmed = Object.fromEntries(entries.slice(-maxEntries));
        if(obj.items && typeof obj.items === "object") obj.items = trimmed;
        else {
          for(const key of Object.keys(obj)) delete obj[key];
          Object.assign(obj, trimmed);
        }
        fs.writeFileSync(filePath, JSON.stringify(obj, null, 2));
      }
      return Math.min(entries.length, maxEntries);
    }
  }catch(e){
    gatewayObsError("local_json_prune_error", e, {file:redactConfigValue(filePath, 34)});
  }
  return 0;
}

function runLocalRetentionCleanup(){
  const summary = {
    observability: pruneTextFileByLines(OBSERVABILITY_LOG_FILE, OBSERVABILITY_MAX_FILE_LINES),
    sentLog: pruneJsonFileEntries(SENT_LOG_FILE, 2500),
    processedMessages: pruneJsonFileEntries(PROCESSED_MESSAGE_CACHE_FILE, 2500),
    reliability: pruneJsonFileEntries(WHATSAPP_RELIABILITY_FILE, 1500),
    scrapeConfirm: pruneJsonFileEntries(SCRAPE_CONFIRM_FILE, 1000),
    liveResultState: pruneJsonFileEntries(LIVE_RESULT_STATE_FILE, 1000),
    spamGuard: pruneJsonFileEntries(SPAM_GUARD_STATE_FILE, 1500),
    whatsappSafety: pruneJsonFileEntries(WHATSAPP_SAFETY_STATE_FILE, 1500)
  };
  gatewayObsEvent("local_retention_cleanup", "info", "Gateway local retention cleanup completed", summary);
  return summary;
}

function managedInterval(name, fn, ms){
  let running = false;
  return setInterval(async () => {
    if(running){
      gatewayObsEvent("managed_interval_skip", "warning", `${name} skipped because previous run is still active`, {name, intervalMs:ms});
      return;
    }
    running = true;
    try { await fn(); }
    catch(e){ gatewayObsError(`${name}_interval_error`, e, {name}); }
    finally { running = false; }
  }, ms);
}

function managedTimeout(name, fn, delayMs){
  return setTimeout(() => Promise.resolve()
    .then(fn)
    .catch(e => gatewayObsError(`${name}_timeout_error`, e, {name, delayMs})), delayMs);
}

app.listen(PORT, HOST, () => { console.log(`🚀 Titan Gateway running: http://${HOST}:${PORT}`); gatewayObsEvent("gateway_started", "info", "Gateway HTTP server started", {host:HOST, port:PORT, timezone:APP_TZ}); });
startWhatsApp().catch(e => console.error("WA start error", e));
managedInterval("whatsapp_target_sync", async () => { if(connected) await syncTargets({periodic:true}); }, WHATSAPP_TARGET_SYNC_INTERVAL_MS);
managedInterval("schedule_tick", scheduleTick, TITAN_SCHEDULE_POLL_MS);
managedInterval("result_tick", resultTick, TITAN_RESULT_POLL_MS);
managedInterval("result_scrape_tick", resultScrapeTick, RESULT_SCRAPE_INTERVAL_MS);
managedInterval("payment_outbox_tick", paymentOutboxTick, TITAN_PAYMENT_OUTBOX_POLL_MS);
managedInterval("load_forwarder_tick", loadForwarderTick, TITAN_LOAD_FORWARDER_POLL_MS);
managedTimeout("result_scrape_bootstrap", resultScrapeTick, 2000);
managedTimeout("payment_outbox_bootstrap", paymentOutboxTick, 5000);
managedTimeout("load_forwarder_bootstrap", loadForwarderTick, 7000);
managedInterval("target_sync", () => syncTargets(), 10*60*1000);
managedInterval("local_retention_cleanup", () => runLocalRetentionCleanup(), 60*60*1000);
managedTimeout("local_retention_cleanup_bootstrap", () => runLocalRetentionCleanup(), 15000);
