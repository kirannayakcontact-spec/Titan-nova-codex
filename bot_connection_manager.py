"""Non-destructive Flask bridge and inline Admin tab for five WhatsApp bots."""
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
<section id="titan-bot-connection-manager" class="native-card" aria-labelledby="tbcm-title" hidden>
 <div class="tbcm-head">
  <div><span class="tbcm-eyebrow">Admin Gateway</span><h2 id="tbcm-title">Bot Connection Manager</h2><p>Owner, Finance, Game, Result and Ledger sessions in one Admin tab</p></div>
  <button type="button" onclick="TitanBots.load()" aria-label="Refresh bot connections"><span aria-hidden="true">&#8635;</span> Refresh</button>
 </div>
 <div id="tbcm-grid" aria-live="polite"></div>
</section>
<style id="titan-bot-connection-manager-style">
#titan-bot-connection-manager{box-sizing:border-box;margin:18px 12px 110px;padding:20px;background:var(--surface,#111b21);border:1px solid var(--border,#263b4a);border-radius:18px;color:var(--text,#fff);box-shadow:0 12px 35px rgba(0,0,0,.18)}
.tbcm-head{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:18px}.tbcm-eyebrow{display:block;margin-bottom:5px;color:var(--green,#00c26f);font-size:9px;font-weight:900;letter-spacing:.14em;text-transform:uppercase}.tbcm-head h2{margin:0;color:#fff;font-size:18px;font-weight:900}.tbcm-head p{margin:5px 0 0;color:var(--text-muted,#8696a0);font-size:11px}.tbcm-head button,.tbcm-card button{border:1px solid var(--border,#2a3942);border-radius:10px;background:var(--surface-light,#202c33)!important;color:#fff!important;font-size:10px;font-weight:800}.tbcm-head button{flex:none;padding:9px 12px}
#tbcm-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.tbcm-card{min-width:0;background:var(--surface-light,#202c33);border:1px solid var(--border,#ffffff18);border-radius:14px;padding:14px;color:#fff;overflow:hidden}.tbcm-card.tbcm-on{border-color:rgba(0,194,111,.35);background:linear-gradient(145deg,rgba(0,194,111,.08),var(--surface-light,#202c33) 48%)}.tbcm-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.tbcm-role{font-size:12px;font-weight:900;text-transform:capitalize}.tbcm-status{display:flex;align-items:center;color:var(--text-muted,#8696a0);font-size:9px;font-weight:800;white-space:nowrap}.tbcm-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;background:var(--rose,#ff5d5d);box-shadow:0 0 0 3px rgba(255,93,93,.1)}.tbcm-on .tbcm-dot{background:var(--green,#25d366);box-shadow:0 0 0 3px rgba(37,211,102,.1)}.tbcm-qr{display:flex;align-items:center;justify-content:center;aspect-ratio:1;margin:12px 0;background:#fff;border-radius:10px;overflow:hidden}.tbcm-qr img{display:block;width:100%;height:100%;object-fit:contain;padding:7px}.tbcm-wait{background:rgba(0,0,0,.12);color:var(--text-muted,#8696a0);font-size:10px;text-align:center}.tbcm-card button{width:100%;padding:8px 10px}.tbcm-owner-note{display:block;padding:9px;color:var(--text-muted,#8696a0);font-size:9px;text-align:center}.tbcm-unavailable{grid-column:1/-1;margin:0;padding:18px;color:var(--text-muted,#8696a0);font-size:11px;text-align:center}.tbcm-floating-admin{position:fixed;right:14px;bottom:82px;z-index:9999;border:1px solid var(--border,#2a3942);border-radius:999px;background:var(--primary,#00a884);color:#fff;padding:10px 14px;font-size:11px;font-weight:900;box-shadow:0 10px 28px rgba(0,0,0,.25)}
@media(min-width:768px){#titan-bot-connection-manager{margin:18px 0 48px}}@media(max-width:760px){#tbcm-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){#titan-bot-connection-manager{padding:15px}.tbcm-head{align-items:flex-start}.tbcm-head p{max-width:210px}#tbcm-grid{grid-template-columns:1fr}}
</style>
<script id="titan-bot-connection-manager-script">
(function(){
 const roles=['owner_bot','finance_bot','game_bot','result_bot'];
 const ADMIN_TAB='admin';
 const label=r=>r.replace(/_bot$/,'').replace(/_/g,' ');
 const manager=document.getElementById('titan-bot-connection-manager');
 let syncing=false;
 function currentMainNav(){try{return typeof mainNav!=='undefined'?String(mainNav||''):''}catch(e){return ''}}
 function isAdminTab(){return currentMainNav()===ADMIN_TAB}
 function mainHost(){return document.getElementById('screen-content')||document.querySelector('[data-screen-content]')||document.querySelector('main')||document.body}
 function restoreHidden(main){try{Array.from((main||document).querySelectorAll('[data-tbcm-hidden="1"]')).forEach(el=>{el.hidden=false;delete el.dataset.tbcmHidden})}catch(e){}}
 function makeAdminButton(ref){
  const btn=ref?ref.cloneNode(true):document.createElement('button');
  btn.removeAttribute('id');btn.removeAttribute('onclick');btn.removeAttribute('href');btn.setAttribute('type','button');btn.setAttribute('data-titan-admin-tab-button','1');btn.setAttribute('aria-label','Open Admin tab');
  btn.innerHTML='<i class="fas fa-user-shield" aria-hidden="true"></i><span>Admin</span>';
  btn.addEventListener('click',ev=>{ev.preventDefault();activateAdmin()});
  return btn;
 }
 function ensureAdminNavButton(){
  if(document.querySelector('[data-titan-admin-tab-button]'))return;
  const clicks=Array.from(document.querySelectorAll('button,a')).filter(el=>String(el.getAttribute('onclick')||'').includes('setMainNav'));
  const guard=clicks.find(el=>/guard/i.test(String(el.getAttribute('onclick')||el.textContent||'')));
  const ref=guard||clicks[0];
  if(ref&&ref.parentElement){ref.parentElement.insertBefore(makeAdminButton(ref),guard&&guard.nextSibling?guard.nextSibling:null);return}
  const floating=makeAdminButton(null);floating.className='tbcm-floating-admin';floating.textContent='Admin';document.body.appendChild(floating);
 }
 function setAdminActive(){
  try{document.querySelectorAll('[data-titan-admin-tab-button]').forEach(el=>{el.classList.add('active');el.setAttribute('aria-current','page')})}catch(e){}
 }
 function renderAdminShell(){
  const main=mainHost();if(!main)return false;
  restoreHidden(main);
  if(manager.parentElement!==main)main.appendChild(manager);
  Array.from(main.children).forEach(el=>{if(el!==manager){el.dataset.tbcmHidden='1';el.hidden=true}});
  manager.hidden=false;setAdminActive();return true;
 }
 function syncPlacement(loadAfter){
  if(syncing)return isAdminTab();
  syncing=true;
  ensureAdminNavButton();
  const main=mainHost(),adminOpen=isAdminTab();
  if(!adminOpen){manager.hidden=true;restoreHidden(main);syncing=false;return false}
  renderAdminShell();syncing=false;
  if(loadAfter&&window.TitanBots)window.TitanBots.load();
  return true;
 }
 function activateAdmin(){
  try{if(typeof pushNativeState==='function')pushNativeState()}catch(e){}
  try{mainNav=ADMIN_TAB}catch(e){window.mainNav=ADMIN_TAB}
  try{activeTab=ADMIN_TAB}catch(e){}
  syncPlacement(true);
 }
 const originalSetMainNav=window.setMainNav;
 if(typeof originalSetMainNav==='function'&&!originalSetMainNav.__titanAdminTabPatch){
  const patched=function(tab){if(String(tab||'')===ADMIN_TAB)return activateAdmin();const out=originalSetMainNav.apply(this,arguments);setTimeout(()=>syncPlacement(false),0);return out};
  patched.__titanAdminTabPatch=true;window.setMainNav=patched;
 }
 const originalRender=window.render;
 if(typeof originalRender==='function'&&!originalRender.__titanAdminTabPatch){
  const patchedRender=function(){if(isAdminTab()){syncPlacement(false);return}const out=originalRender.apply(this,arguments);setTimeout(()=>syncPlacement(false),0);return out};
  patchedRender.__titanAdminTabPatch=true;window.render=patchedRender;
 }
 window.TitanBots={timer:null,lastLoad:0,async load(){if(!syncPlacement(false))return;this.lastLoad=Date.now();let d={bots:[]};try{const res=await fetch('/api/bot_connection_manager/status',{cache:'no-store'});if(res.ok)d=await res.json()}catch(e){}const byRole=new Map((d.bots||[]).map(b=>[b.role,b]));const g=document.getElementById('tbcm-grid');if(!g)return;g.innerHTML=roles.map(role=>{const b=byRole.get(role)||{role,connected:false,qr:false};const connected=!!b.connected;return `<article class="tbcm-card ${connected?'tbcm-on':''}"><div class="tbcm-card-head"><span class="tbcm-role">${label(role)}</span><span class="tbcm-status"><span class="tbcm-dot"></span>${connected?'Connected':'Disconnected'}</span></div>${b.qr?`<div class="tbcm-qr"><img src="/api/bot_connection_manager/qr/${role}?t=${Date.now()}" alt="QR code for ${label(role)} bot"></div>`:'<div class="tbcm-qr tbcm-wait">Waiting for QR&hellip;</div>'}${role==='owner_bot'?'<span class="tbcm-owner-note">Primary session</span>':`<button type="button" onclick="TitanBots.reset('${role}')">Reset session</button>`}</article>`}).join('')},async reset(role){if(!isAdminTab()||!roles.includes(role))return;await fetch('/api/bot_connection_manager/reset/'+role,{method:'POST'});setTimeout(()=>this.load(),800)}};
 new MutationObserver(()=>syncPlacement(false)).observe(document.body,{childList:true,subtree:true});
 syncPlacement(false);TitanBots.timer=setInterval(()=>{if(syncPlacement(false)&&Date.now()-TitanBots.lastLoad>=3900)TitanBots.load()},1000);
})();
</script>
'''
