const fs = require("fs");
const path = require("path");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const {
  default: makeWASocket, useMultiFileAuthState, DisconnectReason,
  fetchLatestBaileysVersion, Browsers
} = require("@whiskeysockets/baileys");
const { usePersistentAuthState } = require("../redis_auth_state.js");
const { ROLES, ROLE_COLORS, RESET_COLOR } = require("./session_config.js");
const { messageText, senderNumber, normalizeJid } = require("./message_utils.js");
const { allowed, configuredAdmins } = require("./role_access.js");
const { registerBotRoutes } = require("./session_routes.js");

const DEDUPE_TTL_MS = 30 * 60 * 1000;
const DEDUPE_MAX = 5000;

function messageKey(role, message){
  const key = message?.key || {};
  const id = String(key.id || "").trim();
  if (!id) return "";
  return [role, key.remoteJid || "", key.participant || "", id].join("|");
}

class TitanMultiSessionManager {
  constructor(options={}){
    this.stateDir = options.stateDir || process.cwd();
    this.handlers = options.handlers || {};
    this.sessions = new Map();
    this.ownerStatus = options.ownerStatus || (() => ({connected:false, qr:"", user:null}));
    this.ownerSend = options.ownerSend;
    this.sendForRole = options.sendForRole;
    this.starting = new Set();
    this.messageChain = Promise.resolve();
    this.dedupeFile = options.dedupeFile || path.join(this.stateDir, "message_dedupe.json");
    this.seenMessages = this.loadDedupe();
    for (const role of ROLES) {
      this.sessions.set(role, {
        role, connected:false, qr:"", qrAt:"", user:null, socket:null,
        reconnectTimer:null, reconnectAttempt:0, processedCount:0, duplicateCount:0, handlerErrors:0, lastHandlerError:"", lastEvent:"idle", lastError:""
      });
    }
  }
  loadDedupe(){
    try {
      const raw = JSON.parse(fs.readFileSync(this.dedupeFile, "utf8"));
      const now = Date.now();
      return new Map(Object.entries(raw && typeof raw === "object" ? raw : {})
        .filter(([, at]) => Number.isFinite(Number(at)) && now - Number(at) < DEDUPE_TTL_MS)
        .slice(-DEDUPE_MAX));
    } catch (_) { return new Map(); }
  }
  saveDedupe(){
    try {
      fs.mkdirSync(path.dirname(this.dedupeFile), {recursive:true});
      const tmp = `${this.dedupeFile}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(Object.fromEntries(this.seenMessages)), {mode:0o600});
      fs.renameSync(tmp, this.dedupeFile);
    } catch (e) { this.log("owner_bot", "warn", `message dedupe save failed: ${e.message}`); }
  }
  rememberMessage(role, message){
    const key = messageKey(role, message);
    if (!key) return true;
    const now = Date.now();
    for (const [oldKey, at] of this.seenMessages) {
      if (now - Number(at) >= DEDUPE_TTL_MS) this.seenMessages.delete(oldKey);
    }
    if (this.seenMessages.has(key)) return false;
    this.seenMessages.set(key, now);
    while (this.seenMessages.size > DEDUPE_MAX) this.seenMessages.delete(this.seenMessages.keys().next().value);
    return true;
  }
  log(role, level, message){
    const icon = level === "error" ? "❌" : level === "warn" ? "⚠️" : "●";
    console.log(`${ROLE_COLORS[role] || ""}${icon} [${role}]${RESET_COLOR} ${message}`);
  }
  allowed(role, m){ return allowed(role, m); }
  snapshot(){
    const owner = {...this.sessions.get("owner_bot"), ...this.ownerStatus()};
    return ROLES.map(role => {
      const s = role === "owner_bot" ? owner : this.sessions.get(role);
      return {
        role, connected:!!s.connected,
        status:s.connected ? "Connected" : (s.lastEvent || "Disconnected"),
        qr:s.qr || "", qrAt:s.qrAt || "", user:s.user || null,
        lastEvent:s.lastEvent || "", lastError:s.lastError || "",
        reconnectAttempt:Number(s.reconnectAttempt || 0),
        processedCount:Number(s.processedCount || 0), duplicateCount:Number(s.duplicateCount || 0),
        handlerErrors:Number(s.handlerErrors || 0), lastHandlerError:s.lastHandlerError || "",
        commandRestricted: role !== "owner_bot" && ["finance_bot","result_bot","ledger_bot"].includes(role),
        adminsConfigured: role === "owner_bot" || configuredAdmins(role).length > 0,
        authDir:role === "owner_bot" ? "legacy-compatible" : path.join(this.stateDir,"auth_info_baileys",role)
      };
    });
  }
  readiness(){
    const bots = this.snapshot();
    const isolated = bots.filter(bot => bot.role !== "owner_bot");
    const failed = isolated.filter(bot => ["failed", "logged_out", "handler_failed"].includes(bot.lastEvent));
    const starting = isolated.filter(bot => ["starting", "connecting", "qr_ready"].includes(bot.lastEvent));
    return {
      status: failed.length ? "degraded" : (starting.length ? "starting" : "ready"),
      requiredRoles: ROLES,
      connectedRoles: bots.filter(bot => bot.connected).map(bot => bot.role),
      failedRoles: failed.map(bot => ({role:bot.role, error:bot.lastError || bot.lastEvent})),
      startingRoles: starting.map(bot => bot.role),
      bots
    };
  }
  async startAll(){
    const results = await Promise.allSettled(ROLES.slice(1).map(role => this.start(role)));
    return results.map((result, index) => ({role:ROLES[index + 1], status:result.status, reason:result.status === "rejected" ? String(result.reason?.message || result.reason) : ""}));
  }
  scheduleReconnect(role){
    const rec = this.sessions.get(role);
    if (!rec || rec.reconnectTimer || rec.lastEvent === "logged_out") return;
    const attempt = Math.min(8, Number(rec.reconnectAttempt || 0) + 1);
    rec.reconnectAttempt = attempt;
    const delay = Math.min(60000, 1000 * (2 ** (attempt - 1))) + Math.floor(Math.random() * 500);
    rec.reconnectTimer = setTimeout(() => {
      rec.reconnectTimer = null;
      this.start(role).catch(e => this.log(role,"error",e.message));
    }, delay);
  }
  async start(role){
    if (!ROLES.includes(role) || role === "owner_bot") return;
    const rec = this.sessions.get(role);
    if (this.starting.has(role) || rec.connected || rec.socket) return;
    this.starting.add(role);
    rec.lastEvent = "starting";
    rec.lastError = "";
    try {
      const authDir = path.join(this.stateDir,"auth_info_baileys",role);
      fs.mkdirSync(authDir,{recursive:true, mode:0o700});
      const {state,saveCreds} = await usePersistentAuthState(authDir, role, useMultiFileAuthState);
      const {version} = await fetchLatestBaileysVersion();
      const socket = makeWASocket({version, auth:state, printQRInTerminal:false, browser:Browsers.ubuntu(`TitanNova-${role}`), logger:pino({level:"silent"})});
      rec.socket = socket;
      rec.lastEvent = "connecting";
      socket.ev.on("creds.update", (...args) => Promise.resolve(saveCreds(...args)).catch(e => {
        rec.lastError = `credential save: ${e.message}`;
        this.log(role,"error",e.message);
      }));
      socket.ev.on("connection.update", u => Promise.resolve(this.onConnection(role,socket,u)).catch(e => this.log(role,"error",e.message)));
      socket.ev.on("messages.upsert", u => Promise.resolve(this.onMessages(role,u)).catch(e => this.log(role,"error",e.message)));
    } catch (e) {
      rec.lastEvent = "failed";
      rec.lastError = String(e.message || e);
      this.scheduleReconnect(role);
      throw e;
    } finally { this.starting.delete(role); }
  }
  onConnection(role, socket, {connection,lastDisconnect,qr}={}){
    const rec = this.sessions.get(role); if (!rec || rec.socket !== socket) return;
    if (qr) { rec.qr = qr; rec.qrAt = new Date().toISOString(); rec.lastEvent = "qr_ready"; qrcode.generate(qr,{small:true}); this.log(role,"info","QR ready"); }
    if (connection === "open") {
      if (rec.reconnectTimer) { clearTimeout(rec.reconnectTimer); rec.reconnectTimer = null; }
      rec.connected = true; rec.reconnectAttempt = 0; rec.qr = ""; rec.user = socket.user || null; rec.lastEvent = "connected"; rec.lastError = ""; this.log(role,"info","connected");
    }
    if (connection === "close") {
      rec.connected = false; rec.socket = null; rec.lastEvent = "disconnected";
      const code = lastDisconnect?.error?.output?.statusCode; const loggedOut = code === DisconnectReason.loggedOut;
      rec.lastError = String(code || "connection closed"); this.log(role, loggedOut ? "error" : "warn", `disconnected (${rec.lastError})`);
      if (!loggedOut) {
        this.scheduleReconnect(role);
      } else {
        rec.lastEvent = "logged_out";
      }
    }
  }
  async onMessages(role,{messages=[]}={}){
    const batch = Array.isArray(messages) ? messages : [];
    const run = this.messageChain.then(() => this.processMessages(role, batch));
    this.messageChain = run.catch(() => {});
    return run;
  }
  async processMessages(role, messages){
    const rec = this.sessions.get(role);
    const socket = rec?.socket;
    for (const m of messages) {
      if (!m?.message || m.key?.fromMe) continue;
      if (!this.rememberMessage(role, m)) { rec.duplicateCount = Number(rec.duplicateCount || 0) + 1; this.log(role, "warn", `duplicate message skipped: ${m.key?.id || "unknown"}`); continue; }
      const text = messageText(m); const isCommand = /^[#!\/]/.test(text);
      if (isCommand && !this.allowed(role,m)) { this.log(role,"warn",`unauthorized ${role} command from ${senderNumber(m) || "unknown"}`); continue; }
      this.log(role,"info",`handling ${isCommand ? "command" : "message"} from ${senderNumber(m) || "group"}`);
      const fn = this.handlers[role];
      if (typeof fn === "function") {
        const context = Object.freeze({
          role, socket, text,
          send: (to, body, meta={}) => this.send(role, to, body, {...meta, source:`${role}_handler`}),
          sender: senderNumber(m)
        });
        try { await fn(m, context); rec.processedCount = Number(rec.processedCount || 0) + 1; }
        catch (e) { rec.handlerErrors = Number(rec.handlerErrors || 0) + 1; rec.lastHandlerError = String(e.message || e).slice(0, 300); rec.lastEvent = "handler_failed"; this.log(role, "error", `handler failed: ${e.message || e}`); }
      }
    }
    this.saveDedupe();
  }
  async reset(role){
    if (!ROLES.includes(role) || role === "owner_bot") throw new Error("Use the legacy owner reset endpoint for owner_bot");
    const rec = this.sessions.get(role);
    if (rec.reconnectTimer) { clearTimeout(rec.reconnectTimer); rec.reconnectTimer = null; }
    const oldSocket = rec.socket;
    rec.socket = null;
    try { oldSocket?.end(new Error("admin reset")); } catch (_) {}
    fs.rmSync(path.join(this.stateDir,"auth_info_baileys",role),{recursive:true,force:true});
    Object.assign(rec,{connected:false,qr:"",qrAt:"",user:null,reconnectAttempt:0,processedCount:0,duplicateCount:0,handlerErrors:0,lastHandlerError:"",lastEvent:"reset",lastError:""});
    rec.reconnectTimer = setTimeout(() => {
      rec.reconnectTimer = null;
      this.start(role).catch(e => this.log(role,"error",e.message));
    }, 500);
    return this.snapshot().find(x => x.role === role);
  }
  async send(role,to,text){
    if (!ROLES.includes(role)) throw new Error("Unknown bot role");
    const body = String(text ?? "").trim();
    if (!body) throw new Error("Message text is required");
    if (body.length > 4096) throw new Error("Message text exceeds 4096 characters");
    const rec = this.sessions.get(role);
    if (role === "owner_bot") {
      if (typeof this.ownerSend !== "function") throw new Error("owner_bot sender unavailable");
      this.log(role,"info","sending isolated critical owner event");
      return this.ownerSend(to,body);
    }
    if (typeof this.sendForRole === "function") {
      const result = await this.sendForRole(role, to, body, {type:"bot_api"});
      if (result && result.ok === false) throw new Error(result.error || "Bot send failed");
      return result;
    }
    if (!rec.connected || !rec.socket) throw new Error(`${role} is disconnected`);
    const jid = normalizeJid(to);
    if (!/^[^@]+@(s\.whatsapp\.net|g\.us|broadcast)$/.test(jid)) throw new Error("A valid WhatsApp recipient is required");
    this.log(role,"info",`sending isolated event to ${jid}`); return rec.socket.sendMessage(jid,{text:body});
  }
  registerRoutes(app,auth){ registerBotRoutes(this, app, auth); }
}

module.exports = { TitanMultiSessionManager, messageKey };
