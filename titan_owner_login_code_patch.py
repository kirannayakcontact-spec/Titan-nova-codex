from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "Gateway.js"
MARKER = "OWNER_CODE_LOGIN_V1"

ADD_AFTER = 'const WHATSAPP_TARGET_SYNC_VERSION = "2026-07-05-whatsapp-target-realtime-sync-v45";'
HELPER = r'''
const OWNER_CODE_LOGIN_VERSION = "2026-07-06-owner-code-login-v1";
const OWNER_LOGIN_NUMBER = String(process.env.WHATSAPP_OWNER_NUMBER || process.env.TITAN_OWNER_WHATSAPP || "").replace(/[^0-9]/g, "");
let ownerCodePending = false;
let ownerCodeLast = "";
let ownerCodeLastAt = "";
function ownerLoginNumber(){
  let d = String(OWNER_LOGIN_NUMBER || "").replace(/[^0-9]/g, "");
  if(d.length === 10) d = "91" + d;
  return d.length >= 11 ? d : "";
}
function ownerMask(v){ const d = String(v || "").replace(/[^0-9]/g, ""); return d.length > 4 ? d.slice(0, -4).replace(/./g, "*") + d.slice(-4) : d; }
function ownerNoStore(res){ try{ res.set("Cache-Control", "no-store"); res.set("Pragma", "no-cache"); res.set("Expires", "0"); }catch(e){} return res; }
// OWNER_CODE_LOGIN_V1
'''

OLD = '    sock.ev.on("creds.update", saveCreds);'
NEW = r'''    sock.ev.on("creds.update", saveCreds);
    try{
      const n = ownerLoginNumber();
      if(ownerCodePending && n && state && state.creds && !state.creds.registered && sock && typeof sock.requestPairingCode === "function"){
        ownerCodePending = false;
        ownerCodeLast = String(await sock.requestPairingCode(n) || "").trim();
        ownerCodeLastAt = new Date().toISOString();
        gatewayHealth.lastWhatsAppEvent = "owner_code_ready";
        console.log(`Owner login code ready for ${ownerMask(n)}: ${ownerCodeLast}`);
      }
    }catch(e){ ownerCodePending = false; gatewayHealth.lastWhatsAppEvent = "owner_code_error"; gatewayHealth.ownerCodeError = e.message || String(e); console.log("Owner login code error:", e.message || e); }'''

ANCHOR = '''app.post("/wa_reset_session", async (req,res)=>{
  try {
    const out = await restartWhatsAppFresh("manual_reset_api");
    res.json({status:"success", message:"WhatsApp session reset. Fresh QR will appear shortly.", cleared:out, authDir:AUTH_DIR});
  } catch(e) {
    res.status(500).json({status:"error", message:e.message || String(e)});
  }
});'''

ROUTES = r'''

app.post("/wa_owner_code", async (req,res)=>{
  try{
    const n = ownerLoginNumber();
    if(!n) return ownerNoStore(res).status(400).json({status:"error", message:"Set WHATSAPP_OWNER_NUMBER in Termux first.", ownerCodeLogin:true});
    ownerCodePending = true;
    ownerCodeLast = "";
    ownerCodeLastAt = "";
    lastQR = "";
    lastQRAt = "";
    await stopWhatsAppSocket("owner_code_login_request");
    const cleared = clearWhatsAppSessionFiles();
    setTimeout(() => startWhatsApp().catch(e => console.error("Owner code start error", e.message || e)), 900);
    return ownerNoStore(res).json({status:"success", ownerCodeLogin:true, message:"Owner login code request started. Check /wa_owner_code_status after 5-10 seconds.", numberMasked:ownerMask(n), cleared, authDir:AUTH_DIR});
  }catch(e){ return ownerNoStore(res).status(500).json({status:"error", message:e.message || String(e), ownerCodeLogin:true}); }
});

app.get("/wa_owner_code_status", (req,res)=>{
  const n = ownerLoginNumber();
  return ownerNoStore(res).json({status:"success", ownerCodeLogin:true, version:OWNER_CODE_LOGIN_VERSION, connected, configured:!!n, numberMasked:ownerMask(n), pending:ownerCodePending, codeAvailable:!!ownerCodeLast, code:ownerCodeLast, codeAt:ownerCodeLastAt, lastWhatsAppEvent:gatewayHealth.lastWhatsAppEvent || "", lastError:gatewayHealth.ownerCodeError || "", note:ownerCodeLast ? "Use this only on your own WhatsApp linked-device screen." : "Code not ready yet."});
});
'''

def patch(text):
    changed = False
    if MARKER not in text:
        if ADD_AFTER not in text: raise RuntimeError("anchor missing")
        text = text.replace(ADD_AFTER, ADD_AFTER + HELPER, 1); changed = True
    if OLD in text and "ownerCodePending" not in text[text.find(OLD):text.find(OLD)+1000]:
        text = text.replace(OLD, NEW, 1); changed = True
    if ANCHOR in text and 'app.post("/wa_owner_code"' not in text:
        text = text.replace(ANCHOR, ANCHOR + ROUTES, 1); changed = True
    if 'app.post("/wa_owner_code"' not in text: raise RuntimeError("routes missing")
    return text, changed

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); args = ap.parse_args()
    old = TARGET.read_text(encoding="utf-8", errors="replace")
    new, changed = patch(old)
    if not changed:
        print("Owner code login patch already present"); return 0
    print("Owner code login patch can be applied")
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + ".owner-code.bak").write_text(old, encoding="utf-8")
        TARGET.write_text(new, encoding="utf-8")
        print("Applied owner code login patch")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
