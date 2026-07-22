"use strict";

// Additive five-session layer.  The original Gateway socket is retained as the
// owner bot; the other roles use isolated auth directories and message queues.
const fs = require("fs");
const path = require("path");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const {
  default: makeWASocket, useMultiFileAuthState, DisconnectReason,
  fetchLatestBaileysVersion, Browsers
} = require("@whiskeysockets/baileys");
const { usePersistentAuthState } = require("./redis_auth_state.js");

const ROLES = Object.freeze(["owner_bot", "finance_bot", "game_bot", "result_bot", "ledger_bot"]);
const COLORS = {owner_bot:"\x1b[35m", finance_bot:"\x1b[33m", game_bot:"\x1b[36m", result_bot:"\x1b[32m", ledger_bot:"\x1b[34m"};
const RESET = "\x1b[0m";
const restricted = new Set(["finance_bot", "result_bot", "ledger_bot"]);

function digits(value){ let d=String(value||"").replace(/\D/g,""); if(d.length===10)d="91"+d; return d; }
function messageText(m){
  const x=m?.message||{};
  return String(x.conversation||x.extendedTextMessage?.text||x.imageMessage?.caption||x.documentMessage?.caption||"").trim();
}
function senderNumber(m){ return digits(m?.key?.participant||m?.key?.remoteJid||""); }

class TitanMultiSessionManager {
  constructor(options={}){
    this.stateDir=options.stateDir||process.cwd();
    this.handlers=options.handlers||{};
    this.sessions=new Map();
    this.ownerStatus=options.ownerStatus||(()=>({connected:false,qr:"",user:null}));
    this.ownerSend=options.ownerSend;
    this.starting=new Set();
    for(const role of ROLES) this.sessions.set(role,{role,connected:false,qr:"",qrAt:"",user:null,socket:null,lastEvent:"idle",lastError:""});
  }
  log(role,level,message){
    const icon=level==="error"?"❌":level==="warn"?"⚠️":"●";
    console.log(`${COLORS[role]||""}${icon} [${role}]${RESET} ${message}`);
  }
  allowed(role,m){
    if(!restricted.has(role)) return true;
    const configured=String(process.env[`WHATSAPP_${role.toUpperCase()}_ADMINS`]||process.env.TITAN_AUTHORIZED_WHATSAPP_NUMBERS||process.env.WHATSAPP_OWNER_NUMBER||"")
      .split(",").map(digits).filter(Boolean);
    return configured.includes(senderNumber(m));
  }
  snapshot(){
    const owner={...this.sessions.get("owner_bot"),...this.ownerStatus()};
    return ROLES.map(role=>{
      const s=role==="owner_bot"?owner:this.sessions.get(role);
      return {role,connected:!!s.connected,status:s.connected?"Connected":"Disconnected",qr:s.qr||"",qrAt:s.qrAt||"",user:s.user||null,lastEvent:s.lastEvent||"",lastError:s.lastError||"",authDir:role==="owner_bot"?"legacy-compatible":path.join(this.stateDir,"auth_info_baileys",role)};
    });
  }
  async startAll(){ for(const role of ROLES.slice(1)) this.start(role).catch(e=>this.log(role,"error",e.message)); }
  async start(role){
    if(!ROLES.includes(role)||role==="owner_bot"||this.starting.has(role)) return;
    this.starting.add(role);
    const rec=this.sessions.get(role);
    try{
      const authDir=path.join(this.stateDir,"auth_info_baileys",role);
      fs.mkdirSync(authDir,{recursive:true});
      const {state,saveCreds}=await usePersistentAuthState(authDir, role, useMultiFileAuthState);
      const {version}=await fetchLatestBaileysVersion();
      const socket=makeWASocket({version,auth:state,printQRInTerminal:false,browser:Browsers.ubuntu(`TitanNova-${role}`),logger:pino({level:"silent"})});
      rec.socket=socket; rec.lastEvent="connecting"; rec.lastError="";
      socket.ev.on("creds.update",(...args)=>Promise.resolve(saveCreds(...args)).catch(e=>this.log(role,"error",e.message)));
      socket.ev.on("connection.update",u=>Promise.resolve(this.onConnection(role,socket,u)).catch(e=>this.log(role,"error",e.message)));
      socket.ev.on("messages.upsert",u=>Promise.resolve(this.onMessages(role,u)).catch(e=>this.log(role,"error",e.message)));
    } finally { this.starting.delete(role); }
  }
  onConnection(role,socket,{connection,lastDisconnect,qr}){
    const rec=this.sessions.get(role); if(rec.socket!==socket)return;
    if(qr){rec.qr=qr;rec.qrAt=new Date().toISOString();rec.lastEvent="qr";qrcode.generate(qr,{small:true});this.log(role,"info","QR ready");}
    if(connection==="open"){rec.connected=true;rec.reconnectAttempt=0;rec.qr="";rec.user=socket.user||null;rec.lastEvent="open";this.log(role,"info","connected");}
    if(connection==="close"){
      rec.connected=false;rec.socket=null;rec.lastEvent="close";
      const code=lastDisconnect?.error?.output?.statusCode; const loggedOut=code===DisconnectReason.loggedOut;
      rec.lastError=String(code||"connection closed");this.log(role,loggedOut?"error":"warn",`disconnected (${rec.lastError})`);
      if(!loggedOut){
        const attempt=Math.min(8,Number(rec.reconnectAttempt||0)+1); rec.reconnectAttempt=attempt;
        const delay=Math.min(60000,1000*(2**(attempt-1)))+Math.floor(Math.random()*500);
        setTimeout(()=>this.start(role).catch(e=>this.log(role,"error",e.message)),delay);
      }
    }
  }
  async onMessages(role,{messages=[]}){
    for(const m of messages){
      if(!m?.message||m.key?.fromMe)continue;
      const text=messageText(m); const isCommand=/^[#!\/]/.test(text);
      if(isCommand&&!this.allowed(role,m)) continue; // deliberately silent
      this.log(role,"info",`handling ${isCommand?"command":"message"} from ${senderNumber(m)||"group"}`);
      const fn=this.handlers[role]; if(typeof fn==="function") await fn(m,{text,role,socket:this.sessions.get(role).socket});
    }
  }
  async reset(role){
    if(!ROLES.includes(role)||role==="owner_bot")throw new Error("Use the legacy owner reset endpoint for owner_bot");
    const rec=this.sessions.get(role); try{rec.socket?.end(new Error("admin reset"));}catch(_){}
    fs.rmSync(path.join(this.stateDir,"auth_info_baileys",role),{recursive:true,force:true});
    Object.assign(rec,{connected:false,qr:"",user:null,socket:null,lastEvent:"reset",lastError:""});
    setTimeout(()=>this.start(role).catch(e=>this.log(role,"error",e.message)),500); return this.snapshot().find(x=>x.role===role);
  }
  async send(role,to,text){
    if(!ROLES.includes(role))throw new Error("Unknown bot role"); const rec=this.sessions.get(role);
    if(role==="owner_bot"){
      if(typeof this.ownerSend!=="function")throw new Error("owner_bot sender unavailable");
      this.log(role,"info","sending isolated critical owner event");
      return this.ownerSend(to,text);
    }
    if(!rec.connected||!rec.socket)throw new Error(`${role} is disconnected`);
    let jid=String(to||"").trim(); if(!jid.includes("@"))jid=digits(jid)+"@s.whatsapp.net";
    this.log(role,"info",`sending isolated event to ${jid}`); return rec.socket.sendMessage(jid,{text:String(text||"")});
  }
  registerRoutes(app,auth){
    const guard=typeof auth==="function"?auth:(req,res,next)=>next();
    app.get("/api/bots/status",guard,(req,res)=>res.json({status:"success",architecture:"5-bot-multi-session",bots:this.snapshot()}));
    app.post("/api/bots/:role/reset",guard,async(req,res)=>{try{res.json({status:"success",bot:await this.reset(req.params.role)});}catch(e){res.status(400).json({status:"error",message:e.message});}});
    app.post("/api/bots/send",guard,async(req,res)=>{try{const event=String(req.body.eventType||"");const routes={crash:"owner_bot",deposit:"finance_bot",withdrawal:"finance_bot",game:"game_bot",result:"result_bot",ledger:"ledger_bot",accounting:"ledger_bot"};const role=routes[event];if(!role)return res.status(400).json({status:"error",message:"A valid eventType is required"});await this.send(role,req.body.to,req.body.text);res.json({status:"success",role,eventType:event});}catch(e){res.status(503).json({status:"error",message:e.message});}});
  }
}
module.exports={TitanMultiSessionManager,ROLES,messageText,senderNumber};
