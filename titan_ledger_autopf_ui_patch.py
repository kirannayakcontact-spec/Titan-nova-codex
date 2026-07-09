"""Ledger auto status UI relocation patch.

The existing auto status engine and /api/ledger_auto_mark endpoint stay intact.
This patch only moves the control card from Result/Settlement UI to Ledger UI
and routes setting saves through the existing safe result_control endpoint.
"""


def register_titan_ledger_autopf_ui(app):
    if getattr(app, "_titan_ledger_autopf_ui_registered", False):
        return
    app._titan_ledger_autopf_ui_registered = True

    from flask import request

    VERSION = "2026-07-09-ledger-autopf-ui-v1"

    @app.after_request
    def ledger_autopf_ui_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-autopf-ui-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan Ledger Auto P/F UI patch loaded", VERSION)


SCRIPT = r'''
<script id="titan-ledger-autopf-ui-v1">
(function(){
 if(window.__TITAN_LEDGER_AUTOPF_UI_V1__) return;
 window.__TITAN_LEDGER_AUTOPF_UI_V1__ = true;
 const VERSION='2026-07-09-ledger-autopf-ui-v1';
 function h(v){return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
 function notify(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else console.log(t,m)}catch(e){}}
 function headers(){const out={'Content-Type':'application/json','Cache-Control':'no-store'};try{const tok=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(tok)out['X-Titan-Admin-Token']=tok}catch(e){}return out;}
 function fixAutoPfState(){
   try{ if(typeof ensureResultStruct==='function') ensureResultStruct(); }catch(e){}
   if(!window.appState) return {};
   if(!appState.ledgerAutoMarkRecords || typeof appState.ledgerAutoMarkRecords!=='object' || Array.isArray(appState.ledgerAutoMarkRecords)) appState.ledgerAutoMarkRecords={};
   if(typeof currentDate!=='undefined' && !appState.ledgerAutoMarkRecords[currentDate]) appState.ledgerAutoMarkRecords[currentDate]={};
   const s = appState.settlementSettings = (appState.settlementSettings && typeof appState.settlementSettings==='object') ? appState.settlementSettings : {};
   if(typeof s.autoLedgerMarking==='undefined') s.autoLedgerMarking=true;
   if(typeof s.autoLedgerMarkOnlyWait==='undefined') s.autoLedgerMarkOnlyWait=true;
   if(typeof s.autoLedgerApplyToAllProfiles==='undefined') s.autoLedgerApplyToAllProfiles=true;
   if(typeof s.autoLedgerRecordResults==='undefined') s.autoLedgerRecordResults=true;
   if(typeof s.enabled==='undefined') s.enabled=true;
   if(typeof s.includeSummaryInResultMessage==='undefined') s.includeSummaryInResultMessage=true;
   if(typeof s.includeHitMissInResultMessage==='undefined') s.includeHitMissInResultMessage=false;
   if(!s.payoutMultipliers || typeof s.payoutMultipliers!=='object') s.payoutMultipliers={ank:9.5,jodi:95,penel:150,panel:150,patti:150};
   if(Number(s.payoutMultipliers.jodi||0)<50) s.payoutMultipliers.jodi=95;
   if(Number(s.payoutMultipliers.ank||0)<=0) s.payoutMultipliers.ank=9.5;
   ['penel','panel','patti'].forEach(k=>{ if(Number(s.payoutMultipliers[k]||0)<=0) s.payoutMultipliers[k]=150; });
   return s;
 }
 function autoRows(){
   const d = (typeof currentDate!=='undefined' ? currentDate : new Date().toISOString().slice(0,10));
   const day = (window.appState && appState.ledgerAutoMarkRecords && appState.ledgerAutoMarkRecords[d]) || {};
   return Object.values(day).filter(x=>x&&typeof x==='object').sort((a,b)=>String(b.time||b.createdAt||'').localeCompare(String(a.time||a.createdAt||'')));
 }
 function autoSummary(){
   const rows=autoRows();
   return {marked:rows.reduce((s,x)=>s+Number(x.marked||0),0),pass:rows.reduce((s,x)=>s+Number(x.pass||0),0),fail:rows.reduce((s,x)=>s+Number(x.fail||0),0),recent:rows.slice(0,5)};
 }
 async function safeSave(patch){
   const payload=Object.assign({date:(typeof currentDate!=='undefined'?currentDate:'')},patch||{});
   const res=await fetch('/api/result_control/save_settings',{method:'POST',headers:headers(),body:JSON.stringify(payload)});
   const raw=await res.text();
   let data={};
   try{data=raw?JSON.parse(raw):{}}catch(e){throw new Error(raw&&raw.trim().startsWith('<')?'Server HTML error return hua, JSON nahi.':'Bad JSON response')}
   if(!res.ok||data.status!=='success') throw new Error(data.message||('HTTP '+res.status));
   if(data.settlementSettings) appState.settlementSettings=data.settlementSettings;
   try{localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(e){}
   return data;
 }
 window.saveLedgerAutoPassFailSettings=async function(patch){
   if(!window.IS_MASTER) return;
   const s=fixAutoPfState(); Object.assign(s,patch||{});
   try{const data=await safeSave(patch||{}); notify('✅ Ledger Auto P/F Saved','Setting Ledger tab se save ho gayi.','success'); try{render(true)}catch(e){} return data;}
   catch(e){notify('❌ Ledger Auto P/F Save Error',String(e.message||e),'danger')}
 };
 const previousSaveSettlement=window.saveSettlementSettings;
 window.saveSettlementSettings=async function(patch){
   // keep result settlement toggles functional, but avoid old broad /save path
   return window.saveLedgerAutoPassFailSettings(patch||{});
 };
 window.runLedgerAutoMarkNow=async function(){
   if(!window.IS_MASTER) return;
   const s=fixAutoPfState();
   if(s.autoLedgerMarking===false){ notify('🔴 Auto P/F OFF','Pehle Ledger tab me Auto Mark ON karo.','danger'); return; }
   try{
     notify('🤖 Ledger Auto P/F','Saved result se ledger status check ho raha hai...','info');
     const res=await fetch('/api/ledger_auto_mark',{method:'POST',headers:headers(),body:JSON.stringify({date:(typeof currentDate!=='undefined'?currentDate:''),force:false,source:'ledger_tab'})});
     const raw=await res.text();
     let data={};
     try{data=raw?JSON.parse(raw):{}}catch(e){throw new Error(raw&&raw.trim().startsWith('<')?'Server ne HTML error/redirect return kiya, JSON nahi.':'Invalid JSON response.')}
     if(!res.ok||data.status!=='success') throw new Error(data.message||('Auto mark failed HTTP '+res.status));
     if(data.ledgerAutoMarkRecords) appState.ledgerAutoMarkRecords=data.ledgerAutoMarkRecords;
     if(data.profiles) appState.profiles=data.profiles;
     if(appState.profiles&&appState.activeId) window.state=appState.profiles[appState.activeId]||state;
     try{localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(e){}
     const sum=data.summary||autoSummary();
     notify('✅ Ledger Auto P/F',`${sum.marked||0} card mark hua • PASS ${sum.pass||0} / FAIL ${sum.fail||0}`,(sum.marked||0)?'success':'info');
     try{render(true)}catch(e){}
     return data;
   }catch(e){notify('❌ Ledger Auto P/F Error',String(e.message||e),'danger')}
 };
 window.ledgerAutoPassFailCardHtml=function(){
   if(!window.IS_MASTER || window.mainNav!=='ledger') return '';
   const s=fixAutoPfState(); const sum=autoSummary(); const recent=sum.recent||[];
   const on=s.autoLedgerMarking!==false, onlyWait=s.autoLedgerMarkOnlyWait!==false, allProfiles=s.autoLedgerApplyToAllProfiles!==false;
   return `<div class="px-3 pt-2"><div class="native-card p-4 mb-3" style="border-color:rgba(250,199,72,0.26);background:rgba(250,199,72,0.055)">
     <div class="flex items-start justify-between gap-3 mb-3"><div class="min-w-0"><h3 class="text-white font-black text-[13px] uppercase"><i class="fas fa-robot text-[var(--amber)] mr-1"></i> Ledger Auto Pass/Fail</h3><p class="text-[9px] text-[var(--text-muted)] leading-relaxed mt-1">Control ab Ledger tab me hai. Existing auto engine same rahega.</p></div><div class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${on?'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]':'text-[var(--rose)] border-[rgba(255,93,93,0.25)] bg-[rgba(255,93,93,0.08)]'}">${on?'ON':'OFF'}</div></div>
     <div class="grid grid-cols-3 gap-2 mb-3"><div class="stat-box"><p class="stat-lbl">Marked</p><p class="stat-val text-white">${sum.marked}</p></div><div class="stat-box"><p class="stat-lbl">Pass</p><p class="stat-val text-[var(--green)]">${sum.pass}</p></div><div class="stat-box"><p class="stat-lbl">Fail</p><p class="stat-val text-[var(--rose)]">${sum.fail}</p></div></div>
     <div class="grid grid-cols-3 gap-2 mb-3"><label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">Auto Mark <input type="checkbox" onchange="saveLedgerAutoPassFailSettings({autoLedgerMarking:this.checked})" ${on?'checked':''}></label><label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">Only WAIT <input type="checkbox" onchange="saveLedgerAutoPassFailSettings({autoLedgerMarkOnlyWait:this.checked})" ${onlyWait?'checked':''}></label><label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">All VIPs <input type="checkbox" onchange="saveLedgerAutoPassFailSettings({autoLedgerApplyToAllProfiles:this.checked})" ${allProfiles?'checked':''}></label></div>
     <button onclick="runLedgerAutoMarkNow()" class="w-full bg-[rgba(250,199,72,0.18)] text-[var(--amber)] border border-[rgba(250,199,72,0.30)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-wand-magic-sparkles mr-1"></i> Mark Now From Saved Results</button>
     ${recent.length?`<div class="mt-3 max-h-24 overflow-y-auto no-scrollbar space-y-1">${recent.map(x=>`<div class="text-[8px] text-[var(--text-muted)] flex justify-between gap-2"><span class="truncate">${h(x.market||'')} ${h(String(x.stage||'').toUpperCase())} ${h(x.result||'')}</span><span class="shrink-0">✅${Number(x.pass||0)} ❌${Number(x.fail||0)}</span></div>`).join('')}</div>`:`<p class="text-[9px] text-[var(--text-muted)] mt-3">Aaj abhi auto PASS/FAIL run nahi hua.</p>`}
   </div></div>`;
 };
 const oldHUD=window.renderWalletHUD;
 if(typeof oldHUD==='function') window.renderWalletHUD=function(){return (oldHUD.apply(this,arguments)||'') + (window.ledgerAutoPassFailCardHtml?window.ledgerAutoPassFailCardHtml():'')};
 const oldSettlement=window.settlementCardHtml;
 if(typeof oldSettlement==='function') window.settlementCardHtml=function(){
   let html=oldSettlement.apply(this,arguments)||'';
   const needle='Ledger Auto Pass/Fail';
   const n=html.indexOf(needle);
   if(n>=0){
     const start=html.lastIndexOf('<div class="mb-3 rounded-2xl',n);
     const end=html.indexOf('<p class="text-[9px] text-[var(--text-muted)] leading-relaxed mb-3">Auto Hit/Miss OFF',n);
     if(start>=0&&end>start) html=html.slice(0,start)+html.slice(end);
   }
   return html;
 };
 fixAutoPfState();
 console.log('✅ Titan Ledger Auto P/F UI active',VERSION);
})();
</script>
'''
