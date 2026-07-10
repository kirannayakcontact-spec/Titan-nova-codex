"""Reliable visible Ledger Auto Pass/Fail control for the Termux safe UI.

This does not depend on renderWalletHUD(). It watches the active Ledger tab and
inserts one control card directly into the visible dashboard DOM.
"""


def register_titan_ledger_autopf_visible(app):
    if getattr(app, "_titan_ledger_autopf_visible_registered", False):
        return
    app._titan_ledger_autopf_visible_registered = True

    from flask import request

    @app.after_request
    def inject_visible_ledger_autopf(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-autopf-visible-v2" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan Ledger Auto P/F visible control loaded")


SCRIPT = r'''
<script id="titan-ledger-autopf-visible-v2">
(function(){
 if(window.__TITAN_LEDGER_AUTOPF_VISIBLE_V2__) return;
 window.__TITAN_LEDGER_AUTOPF_VISIBLE_V2__=true;
 function activeLedger(){
   try{return String(window.mainNav||'').toLowerCase()==='ledger'}catch(_){return false}
 }
 function headers(){
   const h={'Content-Type':'application/json','Cache-Control':'no-store'};
   try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(_){}
   return h;
 }
 function notify(title,msg,type){
   try{if(typeof showRealNotification==='function')showRealNotification(title,msg,type||'info');else alert(title+'\n'+msg)}catch(_){console.log(title,msg)}
 }
 function settings(){
   try{
     if(!window.appState) window.appState={};
     const s=appState.settlementSettings=(appState.settlementSettings&&typeof appState.settlementSettings==='object')?appState.settlementSettings:{};
     if(typeof s.autoLedgerMarking==='undefined')s.autoLedgerMarking=true;
     if(typeof s.autoLedgerMarkOnlyWait==='undefined')s.autoLedgerMarkOnlyWait=true;
     if(typeof s.autoLedgerApplyToAllProfiles==='undefined')s.autoLedgerApplyToAllProfiles=true;
     return s;
   }catch(_){return {autoLedgerMarking:true,autoLedgerMarkOnlyWait:true,autoLedgerApplyToAllProfiles:true}}
 }
 async function save(patch){
   const r=await fetch('/api/result_control/save_settings',{method:'POST',headers:headers(),body:JSON.stringify(Object.assign({date:window.currentDate||''},patch||{}))});
   const d=await r.json().catch(()=>({}));
   if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));
   if(d.settlementSettings&&window.appState)appState.settlementSettings=d.settlementSettings;
   return d;
 }
 window.titanVisibleAutoPfSave=async function(key,checked){
   try{const p={};p[key]=!!checked;await save(p);notify('✅ Ledger Auto P/F','Setting save ho gayi.','success')}
   catch(e){notify('❌ Save Error',String(e.message||e),'danger')}
 };
 window.titanVisibleAutoPfRun=async function(){
   try{
     const s=settings();
     if(s.autoLedgerMarking===false)throw new Error('Auto Mark OFF hai. Pehle ON karo.');
     notify('🤖 Ledger Auto P/F','Saved result se ledger cards check ho rahe hain...','info');
     const r=await fetch('/api/ledger_auto_mark',{method:'POST',headers:headers(),body:JSON.stringify({date:window.currentDate||'',force:false,source:'visible_ledger_control'})});
     const d=await r.json().catch(()=>({}));
     if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));
     if(window.appState){if(d.profiles)appState.profiles=d.profiles;if(d.ledgerAutoMarkRecords)appState.ledgerAutoMarkRecords=d.ledgerAutoMarkRecords;}
     const x=d.summary||{};
     notify('✅ Ledger Auto P/F',`${Number(x.marked||0)} marked • PASS ${Number(x.pass||0)} • FAIL ${Number(x.fail||0)}`,Number(x.marked||0)>0?'success':'info');
     try{if(typeof render==='function')render(true)}catch(_){}
   }catch(e){notify('❌ Auto P/F Error',String(e.message||e),'danger')}
 };
 function card(){
   const s=settings();
   const el=document.createElement('div');
   el.id='titanLedgerAutoPfVisibleCard';
   el.style.cssText='margin:12px;border:1px solid rgba(250,199,72,.35);border-radius:16px;background:#182536;padding:14px;color:#fff;font-family:Arial,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.18)';
   el.innerHTML=`<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px"><div><div style="font-size:13px;font-weight:900">🤖 LEDGER AUTO PASS / FAIL</div><div style="font-size:10px;opacity:.7;margin-top:3px">Saved result se WAIT cards auto mark karega</div></div><span style="font-size:9px;color:#4ade80;font-weight:900">ACTIVE</span></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:10px"><label style="font-size:10px;background:#0f1b29;padding:9px;border-radius:10px">Auto Mark<br><input type="checkbox" ${s.autoLedgerMarking!==false?'checked':''} onchange="titanVisibleAutoPfSave('autoLedgerMarking',this.checked)"></label><label style="font-size:10px;background:#0f1b29;padding:9px;border-radius:10px">Only WAIT<br><input type="checkbox" ${s.autoLedgerMarkOnlyWait!==false?'checked':''} onchange="titanVisibleAutoPfSave('autoLedgerMarkOnlyWait',this.checked)"></label><label style="font-size:10px;background:#0f1b29;padding:9px;border-radius:10px">All VIPs<br><input type="checkbox" ${s.autoLedgerApplyToAllProfiles!==false?'checked':''} onchange="titanVisibleAutoPfSave('autoLedgerApplyToAllProfiles',this.checked)"></label></div><button onclick="titanVisibleAutoPfRun()" style="width:100%;border:1px solid rgba(250,199,72,.45);background:rgba(250,199,72,.16);color:#fac748;padding:12px;border-radius:11px;font-weight:900;font-size:11px">MARK NOW FROM SAVED RESULTS</button>`;
   return el;
 }
 function mount(){
   try{
     const old=document.getElementById('titanLedgerAutoPfVisibleCard');
     if(!activeLedger()){if(old)old.remove();return}
     if(old)return;
     const root=document.querySelector('#app')||document.querySelector('#mainContent')||document.querySelector('main')||document.body;
     if(!root)return;
     const c=card();
     const first=root.firstElementChild;
     if(first)root.insertBefore(c,first);else root.appendChild(c);
   }catch(e){console.warn('Ledger Auto P/F mount error',e)}
 }
 setInterval(mount,500);
 setTimeout(mount,100);
 setTimeout(mount,800);
 console.log('✅ Titan Ledger Auto P/F visible control active');
})();
</script>
'''
