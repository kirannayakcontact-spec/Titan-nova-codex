"use strict";

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
const { allowed } = require("./role_access.js");
const { registerBotRoutes } = require("./session_routes.js");

class TitanMultiSessionManager {
  constructor(options={}){
    this.stateDir = options.stateDir || process.cwd();
    this.handlers = options.handlers || {};
    this.sessions = new Map();
    this.ownerStatus = options.ownerStatus || (() => ({connected:false, qr:"", user:null}));
    this.ownerSend = options.ownerSend;
    this.starting = new Set();
    for (const role of ROLES) this.sessions.set(role, {role, connected:false, qr:"", qrAt:"", user:null, socket:null, reconnectTimer:null, reconnectAttempt:0, lastEvent:"idle", lastError:""});
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
      return {role, connected:!!s.connected, status:s.connected ? "Connected" : "Disconnected", qr:s.qr || "", qrAt:s.qrAt || "", user:s.user || null, lastEvent:s.lastEvent || "", lastError:s.lastError || "", authDir:role === "owner_bot" ? "legacy-compatible" : path.join(this.stateDir,"auth_info_baileys",role)};
    });
  }
  async startAll(){ for (const role of ROLES.slice(1)) this.start(role).catch(e => this.log(role, "error", e.message)); }
  async start(role){
    if (!ROLES.includes(role) || role === "owner_bot" || this.starting.has(role)) return;
    this.starting.add(role);
    const rec = this.sessions.get(role);
    try {
      const authDir = path.join(this.stateDir,"auth_info_baileys",role);
      fs.mkdirSync(authDir,{recursive:true});
      const {state,saveCreds} = await usePersistentAuthState(authDir, role, useMultiFileAuthState);
      const {version} = await fetchLatestBaileysVersion();
      const socket = makeWASocket({version, auth:state, printQRInTerminal:false, browser:Browsers.ubuntu(`TitanNova-${role}`), logger:pino({level:"silent"})});
      rec.socket = socket; rec.lastEvent = "connecting"; rec.lastError = "";
      socket.ev.on("creds.update", (...args) => Promise.resolve(saveCreds(...args)).catch(e => this.log(role,"error",e.message)));
      socket.ev.on("connection.update", u => Promise.resolve(this.onConnection(role,socket,u)).catch(e => this.log(role,"error",e.message)));
      socket.ev.on("messages.upsert", u => Promise.resolve(this.onMessages(role,u)).catch(e => this.log(role,"error",e.message)));
    } finally { this.starting.delete(role); }
  }
  onConnection(role, socket, {connection,lastDisconnect,qr}){
    const rec = this.sessions.get(role); if (rec.socket !== socket) return;
    if (qr) { rec.qr = qr; rec.qrAt = new Date().toISOString(); rec.lastEvent = "qr"; qrcode.generate(qr,{small:true}); this.log(role,"info","QR ready"); }
    if (connection === "open") {
      if (rec.reconnectTimer) { clearTimeout(rec.reconnectTimer); rec.reconnectTimer = null; }
      rec.connected = true; rec.reconnectAttempt = 0; rec.qr = ""; rec.user = socket.user || null; rec.lastEvent = "open"; this.log(role,"info","connected");
    }
    if (connection === "close") {
      rec.connected = false; rec.socket = null; rec.lastEvent = "close";
      const code = lastDisconnect?.error?.output?.statusCode; const loggedOut = code === DisconnectReason.loggedOut;
      rec.lastError = String(code || "connection closed"); this.log(role, loggedOut ? "error" : "warn", `disconnected (${rec.lastError})`);
      if (!loggedOut) {
        const attempt = Math.min(8, Number(rec.reconnectAttempt || 0) + 1); rec.reconnectAttempt = attempt;
        const delay = Math.min(60000, 1000 * (2 ** (attempt - 1))) + Math.floor(Math.random() * 500);
        if (rec.reconnectTimer) clearTimeout(rec.reconnectTimer);
        rec.reconnectTimer = setTimeout(() => {
          rec.reconnectTimer = null;
          this.start(role).catch(e => this.log(role,"error",e.message));
        }, delay);
      }
    }
  }
  async onMessages(role,{messages=[]}){
    for (const m of messages) {
      if (!m?.message || m.key?.fromMe) continue;
      const text = messageText(m); const isCommand = /^[#!\/]/.test(text);
      if (isCommand && !this.allowed(role,m)) continue;
      this.log(role,"info",`handling ${isCommand ? "command" : "message"} from ${senderNumber(m) || "group"}`);
      const fn = this.handlers[role]; if (typeof fn === "function") await fn(m,{text,role,socket:this.sessions.get(role).socket});
    }
  }
  async reset(role){
    if (!ROLES.includes(role) || role === "owner_bot") throw new Error("Use the legacy owner reset endpoint for owner_bot");
    const rec = this.sessions.get(role);
    if (rec.reconnectTimer) { clearTimeout(rec.reconnectTimer); rec.reconnectTimer = null; }
    const oldSocket = rec.socket;
    // Clear the reference before closing so the old socket's close event cannot
    // schedule a second reconnect while the explicit reset is being queued.
    rec.socket = null;
    try { oldSocket?.end(new Error("admin reset")); } catch (_) {}
    fs.rmSync(path.join(this.stateDir,"auth_info_baileys",role),{recursive:true,force:true});
    Object.assign(rec,{connected:false,qr:"",qrAt:"",user:null,reconnectAttempt:0,lastEvent:"reset",lastError:""});
    setTimeout(() => this.start(role).catch(e => this.log(role,"error",e.message)), 500); return this.snapshot().find(x => x.role === role);
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
    if (!rec.connected || !rec.socket) throw new Error(`${role} is disconnected`);
    const jid = normalizeJid(to);
    if (!/^[^@]+@(s\.whatsapp\.net|g\.us|broadcast)$/.test(jid)) throw new Error("A valid WhatsApp recipient is required");
    this.log(role,"info",`sending isolated event to ${jid}`); return rec.socket.sendMessage(jid,{text:body});
  }
  registerRoutes(app,auth){ registerBotRoutes(this, app, auth); }
}

module.exports = { TitanMultiSessionManager };
