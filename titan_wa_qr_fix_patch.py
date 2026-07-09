from pathlib import Path
import argparse
from titan_runtime_files import ensure_runtime_file

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "Gateway.js"
ensure_runtime_file("Gateway.js")
MARKER = "WHATSAPP_QR_REFRESH_FIX_V1"

INSERT_AFTER = 'const WHATSAPP_TARGET_SYNC_VERSION = "2026-07-05-whatsapp-target-realtime-sync-v45";'
INSERT = r'''
const WHATSAPP_QR_REFRESH_FIX_VERSION = "2026-07-06-whatsapp-qr-refresh-fix-v1";
const WHATSAPP_QR_TTL_MS = Math.max(Number(process.env.WHATSAPP_QR_TTL_MS || 45000), 15000);
function whatsappQrAgeMs(){
  if(!lastQRAt) return null;
  const t = new Date(lastQRAt).getTime();
  return Number.isFinite(t) ? Date.now() - t : null;
}
function whatsappQrExpired(){
  const age = whatsappQrAgeMs();
  return !!(lastQR && age !== null && age > WHATSAPP_QR_TTL_MS);
}
function clearExpiredWhatsAppQR(reason="expired"){
  if(whatsappQrExpired()){
    lastQR = "";
    lastQRAt = "";
    gatewayHealth.lastWhatsAppEvent = "qr_" + reason;
    return true;
  }
  return false;
}
function setFreshWhatsAppQR(qr){
  lastQR = String(qr || "");
  lastQRAt = new Date().toISOString();
  gatewayHealth.lastWhatsAppEvent = "qr";
  gatewayHealth.lastQrRefreshFix = WHATSAPP_QR_REFRESH_FIX_VERSION;
}
function noStoreJson(res){
  try{
    res.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
    res.set("Pragma", "no-cache");
    res.set("Expires", "0");
    res.set("Surrogate-Control", "no-store");
  }catch(e){}
  return res;
}
// WHATSAPP_QR_REFRESH_FIX_V1
'''

OLD_STATUS = r'''app.get("/wa_login_status", (req,res)=>{
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
});'''

NEW_STATUS = r'''app.get("/wa_login_status", (req,res)=>{
  clearExpiredWhatsAppQR("expired_on_status");
  const qrAgeMs = whatsappQrAgeMs();
  const qrAgeSeconds = qrAgeMs === null ? null : Math.floor(qrAgeMs / 1000);
  const qrExpiresInSeconds = lastQR ? Math.max(0, Math.floor((WHATSAPP_QR_TTL_MS - (qrAgeMs || 0)) / 1000)) : 0;
  noStoreJson(res).json({
    status:"success",
    connected,
    user:sock?.user || null,
    lastWhatsAppEvent:gatewayHealth.lastWhatsAppEvent || "",
    lastDisconnectCode:gatewayHealth.lastDisconnectCode || "",
    qrAvailable:!!lastQR,
    qr:lastQR,
    qrAt:lastQRAt,
    qrAgeSeconds,
    qrExpiresInSeconds,
    qrTtlSeconds:Math.floor(WHATSAPP_QR_TTL_MS / 1000),
    qrRefreshFix:WHATSAPP_QR_REFRESH_FIX_VERSION,
    authDir:AUTH_DIR,
    resetCount:whatsappResetCount,
    lastSessionResetAt,
    note: connected ? "WhatsApp connected" : (lastQR ? "Fresh QR. Scan within the countdown from WhatsApp > Linked devices." : "QR expired/not ready. Press Reset session / Fresh QR and wait 5-10 seconds.")
  });
});'''

OLD_QR_TEXT = r'''app.get("/wa_qr_text", (req,res)=>{
  if(!lastQR) return res.status(404).type("text/plain").send("QR not available yet. Refresh or reset session.");
  res.type("text/plain").send(lastQR);
});'''

NEW_QR_TEXT = r'''app.get("/wa_qr_text", (req,res)=>{
  clearExpiredWhatsAppQR("expired_on_text");
  noStoreJson(res);
  if(!lastQR) return res.status(404).type("text/plain").send("QR not available or expired. Use /wa_reset_session for a fresh QR.");
  res.type("text/plain").send(lastQR);
});'''

OLD_QR_LINE = 'if(qr){ lastQR = qr; lastQRAt = new Date().toISOString(); gatewayHealth.lastWhatsAppEvent = "qr"; gatewayObsEvent("whatsapp_qr_ready", "warning", "WhatsApp QR ready for login", {at:lastQRAt}); qrcode.generate(qr, {small:true}); console.log("📲 Scan QR in WhatsApp > Linked devices"); }'
NEW_QR_LINE = 'if(qr){ setFreshWhatsAppQR(qr); gatewayObsEvent("whatsapp_qr_ready", "warning", "Fresh WhatsApp QR ready for login", {at:lastQRAt, ttlMs:WHATSAPP_QR_TTL_MS, version:WHATSAPP_QR_REFRESH_FIX_VERSION}); qrcode.generate(qr, {small:true}); console.log(`📲 Fresh QR generated. Scan within ${Math.floor(WHATSAPP_QR_TTL_MS/1000)}s in WhatsApp > Linked devices`); }'


def apply_patch(text: str) -> tuple[str, bool]:
    changed = False
    if MARKER not in text:
        if INSERT_AFTER not in text:
            raise RuntimeError("QR fix insert anchor not found")
        text = text.replace(INSERT_AFTER, INSERT_AFTER + INSERT, 1)
        changed = True
    if OLD_STATUS in text:
        text = text.replace(OLD_STATUS, NEW_STATUS, 1)
        changed = True
    if OLD_QR_TEXT in text:
        text = text.replace(OLD_QR_TEXT, NEW_QR_TEXT, 1)
        changed = True
    if OLD_QR_LINE in text:
        text = text.replace(OLD_QR_LINE, NEW_QR_LINE, 1)
        changed = True
    if "WHATSAPP_QR_REFRESH_FIX_VERSION" not in text or NEW_QR_LINE not in text:
        raise RuntimeError("QR fix patch incomplete; expected markers not found after patch")
    return text, changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    original = TARGET.read_text(encoding="utf-8", errors="replace")
    patched, changed = apply_patch(original)
    if not changed:
        print("WhatsApp QR refresh fix already present")
        return 0
    print("WhatsApp QR refresh fix can be applied")
    if args.apply:
        backup = TARGET.with_suffix(TARGET.suffix + ".wa-qr.bak")
        backup.write_text(original, encoding="utf-8")
        TARGET.write_text(patched, encoding="utf-8")
        print(f"Applied WhatsApp QR refresh fix. Backup: {backup.name}")
    else:
        print("Dry-run only. Use --apply to modify Gateway.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
