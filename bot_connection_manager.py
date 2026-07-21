"""Non-destructive Flask bridge and dashboard modal for five WhatsApp bots."""
from __future__ import annotations

import os
import urllib.parse


def register_bot_connection_manager(app):
    if getattr(app, "_bot_connection_manager_registered", False):
        return
    app._bot_connection_manager_registered = True
    from flask import jsonify, redirect, request
    import requests

    gateway = os.environ.get("GATEWAY_URL", "http://127.0.0.1:3000").rstrip("/")

    def headers():
        token = os.environ.get("TITAN_GATEWAY_TOKEN") or os.environ.get("TITAN_ADMIN_TOKEN") or ""
        return {"X-Titan-Gateway-Token": token} if token else {}

    @app.get("/api/bot_connection_manager/status")
    def bot_connection_manager_status():
        try:
            response = requests.get(gateway + "/api/bots/status", headers=headers(), timeout=5)
            return jsonify(response.json()), response.status_code
        except Exception as exc:
            return jsonify({"status": "offline", "bots": [], "message": str(exc)}), 503

    @app.get("/api/bot_connection_manager/qr/<role>")
    def bot_connection_manager_qr(role):
        try:
            response = requests.get(gateway + "/api/bots/status", headers=headers(), timeout=5)
            bot = next((x for x in response.json().get("bots", []) if x.get("role") == role), {})
            qr = str(bot.get("qr") or "")
            if not qr:
                return "QR not available", 404
            return redirect("https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=" + urllib.parse.quote(qr))
        except Exception as exc:
            return "QR error: " + str(exc), 503

    @app.post("/api/bot_connection_manager/reset/<role>")
    def bot_connection_manager_reset(role):
        try:
            response = requests.post(gateway + f"/api/bots/{role}/reset", headers=headers(), timeout=10)
            return jsonify(response.json()), response.status_code
        except Exception as exc:
            return jsonify({"status": "offline", "message": str(exc)}), 503

    @app.after_request
    def inject_bot_connection_manager(response):
        try:
            if request.method != "GET" or "text/html" not in (response.content_type or "").lower():
                return response
            html = response.get_data(as_text=True)
            if "titan-bot-connection-manager" in html or "</body>" not in html.lower():
                return response
            html = html[: html.lower().rfind("</body>")] + BOT_MANAGER_UI + html[html.lower().rfind("</body>") :]
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass
        return response


BOT_MANAGER_UI = r'''
<div id="titan-bot-connection-manager">
 <button id="tbcm-open" onclick="TitanBots.open()" aria-label="Open Bot Connection Manager">5 Bots</button>
 <div id="tbcm-modal" role="dialog" aria-modal="true" aria-labelledby="tbcm-title">
  <div class="tbcm-panel"><div class="tbcm-head"><div><b id="tbcm-title">Bot Connection Manager</b><small>Five isolated WhatsApp sessions</small></div><button onclick="TitanBots.close()">×</button></div><div id="tbcm-grid"></div></div>
 </div>
</div>
<style id="titan-bot-connection-manager-style">
#tbcm-open{position:fixed;right:14px;bottom:88px;z-index:9997;background:#00a884;color:#fff;border:0;border-radius:999px;padding:11px 16px;font-weight:900;box-shadow:0 8px 25px #0008}
#tbcm-modal{display:none;position:fixed;inset:0;z-index:9998;background:#000b;padding:20px;overflow:auto}#tbcm-modal.on{display:flex;align-items:center;justify-content:center}
.tbcm-panel{width:min(980px,100%);max-height:92vh;overflow:auto;background:#111b21;border:1px solid #ffffff22;border-radius:20px;padding:18px}.tbcm-head{display:flex;justify-content:space-between;align-items:center;color:#fff;margin-bottom:14px}.tbcm-head small{display:block;color:#8696a0;margin-top:4px}.tbcm-head button{font-size:28px;background:transparent!important;color:#fff!important}
#tbcm-grid{display:flex;flex-wrap:wrap;gap:12px}.tbcm-card{flex:1 1 calc(33.333% - 12px);min-width:230px;background:#202c33;border:1px solid #ffffff18;border-radius:16px;padding:14px;text-align:center;color:#fff}.tbcm-card img{width:190px;height:190px;background:#fff;border-radius:10px;padding:6px;margin:10px auto}.tbcm-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#ff5d5d}.tbcm-on .tbcm-dot{background:#25d366}.tbcm-card p{color:#8696a0;font-size:11px}.tbcm-card button{background:#2a3942!important;color:#fff!important;padding:8px 13px}
@media(max-width:760px){.tbcm-card{flex-basis:calc(50% - 12px);min-width:190px}}@media(max-width:480px){#tbcm-modal{padding:8px}.tbcm-card{flex-basis:100%;min-width:0}}
</style>
<script id="titan-bot-connection-manager-script">
window.TitanBots={timer:null,open(){document.getElementById('tbcm-modal').classList.add('on');this.load();this.timer=setInterval(()=>this.load(),4000)},close(){document.getElementById('tbcm-modal').classList.remove('on');clearInterval(this.timer)},async load(){let d={bots:[]};try{d=await fetch('/api/bot_connection_manager/status',{cache:'no-store'}).then(r=>r.json())}catch(e){}const g=document.getElementById('tbcm-grid');g.innerHTML=(d.bots||[]).map(b=>`<div class="tbcm-card ${b.connected?'tbcm-on':''}"><b>${b.role}</b><p><span class="tbcm-dot"></span>${b.connected?'Connected':'Disconnected'}</p>${b.qr?`<img src="/api/bot_connection_manager/qr/${b.role}?t=${Date.now()}" alt="${b.role} QR">`:'<p style="padding:78px 0">Waiting for QR…</p>'}${b.role==='owner_bot'?'':`<button onclick="TitanBots.reset('${b.role}')">Reset session</button>`}</div>`).join('')||'<p style="color:#fff">Gateway unavailable</p>'},async reset(r){await fetch('/api/bot_connection_manager/reset/'+r,{method:'POST'});setTimeout(()=>this.load(),800)}};
</script>
'''
