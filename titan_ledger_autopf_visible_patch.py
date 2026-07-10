"""Dedicated Ledger Control tab for Titan Nova Termux safe UI.

Adds CONTROL beside ANK/JODI/PANEL and groups Ledger-only configuration:
- auto Pass/Fail
- payout/split behavior
- entry/risk behavior
- schedule/share helpers
- maintenance actions
"""


def register_titan_ledger_autopf_visible(app):
    if getattr(app, "_titan_ledger_autopf_visible_registered", False):
        return
    app._titan_ledger_autopf_visible_registered = True

    from flask import request

    @app.after_request
    def inject_ledger_control(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-control-v3" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan Ledger CONTROL tab loaded")


SCRIPT = r'''
<script id="titan-ledger-control-v3">
(function(){
 if(window.__TITAN_LEDGER_CONTROL_V3__)return;
 window.__TITAN_LEDGER_CONTROL_V3__=true;
 let controlOpen=false;
 const ID='titanLedgerControlPanelV3';
 function ledger(){try{return String(window.mainNav||'').toLowerCase()==='ledger'}catch(_){return false}}
 function h(){const x={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)x['X-Titan-Admin-Token']=t}catch(_){}return x}
 function note(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else alert(t+'\n'+m)}catch(_){console.log(t,m)}}
 function stateFix(){
   if(!window.appState)window.appState={};
   const s=appState.settlementSettings=(appState.settlementSettings&&typeof appState.settlementSettings==='object')?appState.settlementSettings:{};
   Object.assign(s,{autoLedgerMarking:s.autoLedgerMarking!==false,autoLedgerMarkOnlyWait:s.autoLedgerMarkOnlyWait!==false,autoLedgerApplyToAllProfiles:s.autoLedgerApplyToAllProfiles!==false,autoLedgerRecordResults:s.autoLedgerRecordResults!==false});
   const p=s.payoutMultipliers=(s.payoutMultipliers&&typeof s.payoutMultipliers==='object')?s.payoutMultipliers:{};
   if(!Number(p.ank))p.ank=9.5;if(!Number(p.jodi)||Number(p.jodi)<50)p.jodi=95;if(!Number(p.penel))p.penel=150;
   const e=appState.entrySettings=(appState.entrySettings&&typeof appState.entrySettings==='object')?appState.entrySettings:{};
   if(typeof e.strictFormat==='undefined')e.strictFormat=true;if(typeof e.autoDebitWallet==='undefined')e.autoDebitWallet=true;if(typeof e.marketTimingEnabled==='undefined')e.marketTimingEnabled=true;
   const r=appState.riskSettings=(appState.riskSettings&&typeof appState.riskSettings==='object')?appState.riskSettings:{};
   r.marketDailyLimit=Number(r.marketDailyLimit||0);r.digitDailyLimit=Number(r.digitDailyLimit||0);r.userDailyLimit=Number(r.userDailyLimit||0);r.warningPercent=Number(r.warningPercent||80);
   try{if(window.state&&state.config){if(typeof state.config.ankSplit==='undefined')state.config.ankSplit=true;if(typeof state.config.panSplit==='undefined')state.config.panSplit=true;}}
   catch(_){}
   return {s,p,e,r,c:(window.state&&state.config)||{}};
 }
 async function saveResult(patch){const r=await fetch('/api/result_control/save_settings',{method:'POST',headers:h(),body:JSON.stringify(Object.assign({date:window.currentDate||''},patch||{}))});const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));if(d.settlementSettings)appState.settlementSettings=d.settlementSettings;return d}
 async function legacySave(){try{if(typeof saveMaster==='function')return await saveMaster(false,true);if(typeof autoSave==='function')return await autoSave();localStorage.setItem(window.LOCAL_KEY||'titan_nova_state',JSON.stringify(appState))}catch(e){throw e}}
 window.tlcToggle=async function(k,v){try{const x={};x[k]=!!v;await saveResult(x);note('✅ Ledger Control','Setting save ho gayi.','success')}catch(e){note('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcPayout=async function(){try{const x={ank:Number(document.getElementById('tlc-pay-ank').value||9.5),jodi:Number(document.getElementById('tlc-pay-jodi').value||95),penel:Number(document.getElementById('tlc-pay-panel').value||150),panel:Number(document.getElementById('tlc-pay-panel').value||150),patti:Number(document.getElementById('tlc-pay-panel').value||150)};await saveResult({payoutMultipliers:x});note('✅ Payout Saved','ANK/JODI/PANEL payout save ho gaya.','success')}catch(e){note('❌ Payout Error',String(e.message||e),'danger')}};
 window.tlcLocal=async function(k,v){try{const z=stateFix();if(k==='ankSplit'||k==='panSplit')z.c[k]=!!v;else if(k.startsWith('entry.'))z.e[k.slice(6)]=!!v;else if(k.startsWith('risk.'))z.r[k.slice(5)]=Number(v||0);await legacySave();note('✅ Ledger Setting','Ledger setting save ho gayi.','success')}catch(e){note('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcRun=async function(){try{const z=stateFix();if(z.s.autoLedgerMarking===false)throw new Error('Auto Mark OFF hai.');note('🤖 Auto Pass/Fail','Saved result se WAIT cards check ho rahe hain...','info');const r=await fetch('/api/ledger_auto_mark',{method:'POST',headers:h(),body:JSON.stringify({date:window.currentDate||'',force:false,source:'ledger_control_tab'})});const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));if(d.profiles)appState.profiles=d.profiles;if(d.ledgerAutoMarkRecords)appState.ledgerAutoMarkRecords=d.ledgerAutoMarkRecords;const s=d.summary||{};note('✅ Auto Pass/Fail',`${Number(s.marked||0)} marked • PASS ${Number(s.pass||0)} • FAIL ${Number(s.fail||0)}`,Number(s.marked||0)?'success':'info');try{render(true)}catch(_){}}catch(e){note('❌ Auto P/F Error',String(e.message||e),'danger')}};
 window.tlcRefresh=async function(){try{if(window.__TitanRealtime)await window.__TitanRealtime.refresh('ledger_control');else if(typeof loadMaster==='function')await loadMaster();note('✅ Refreshed','Ledger/Firebase data refresh ho gaya.','success');draw()}catch(e){note('❌ Refresh Error',String(e.message||e),'danger')}};
 window.tlcScrapeAll=async function(){try{if(typeof scrapeAllMarkets==='function')return scrapeAllMarkets();if(typeof scrapeAll==='function')return scrapeAll();note('ℹ️ Scrape','Bulk scrape function current build me available nahi.','info')}catch(e){note('❌ Scrape Error',String(e.message||e),'danger')}};
 function sw(id,label,on,change){return `<label style="display:flex;justify-content:space-between;align-items:center;background:#0e1c2b;border:1px solid rgba(255,255,255,.08);padding:11px;border-radius:12px;font-size:11px;font-weight:800"><span>${label}</span><input id="${id}" type="checkbox" ${on?'checked':''} onchange="${change}"></label>`}
 function inp(id,label,v){return `<label style="font-size:9px;color:#91a4ba;font-weight:800">${label}<input id="${id}" value="${v}" type="number" step="0.1" style="width:100%;margin-top:5px;background:#0e1c2b;color:#fff;border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:10px;font-weight:900"></label>`}
 function panel(){const z=stateFix();const el=document.createElement('section');el.id=ID;el.style.cssText='margin:10px 12px 110px;border-radius:18px;color:#fff;font-family:Arial,sans-serif';el.innerHTML=`
 <div style="background:linear-gradient(145deg,#11283b,#172033);border:1px solid rgba(0,194,111,.25);border-radius:18px;padding:14px;margin-bottom:10px"><div style="font-size:15px;font-weight:1000">⚙️ LEDGER CONTROL CENTER</div><div style="font-size:10px;color:#91a4ba;margin-top:4px">ANK · JODI · PANEL ke Ledger-only controls</div></div>
 <div style="background:#132234;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:13px;margin-bottom:10px"><b style="font-size:12px">🤖 Auto Pass / Fail</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px">${sw('','Auto Mark',z.s.autoLedgerMarking!==false,"tlcToggle('autoLedgerMarking',this.checked)")}${sw('','Only WAIT',z.s.autoLedgerMarkOnlyWait!==false,"tlcToggle('autoLedgerMarkOnlyWait',this.checked)")}${sw('','All VIPs',z.s.autoLedgerApplyToAllProfiles!==false,"tlcToggle('autoLedgerApplyToAllProfiles',this.checked)")}${sw('','Record Results',z.s.autoLedgerRecordResults!==false,"tlcToggle('autoLedgerRecordResults',this.checked)")}</div><button onclick="tlcRun()" style="width:100%;margin-top:10px;padding:12px;border:1px solid #fac74866;border-radius:11px;background:#fac74822;color:#fac748;font-weight:1000">MARK NOW FROM SAVED RESULTS</button></div>
 <div style="background:#132234;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:13px;margin-bottom:10px"><b style="font-size:12px">🎯 Game & Payout</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px">${inp('tlc-pay-ank','ANK X',z.p.ank)}${inp('tlc-pay-jodi','JODI X',z.p.jodi)}${inp('tlc-pay-panel','PANEL X',z.p.penel)}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px">${sw('','ANK Split',z.c.ankSplit!==false,"tlcLocal('ankSplit',this.checked)")}${sw('','Panel Split',z.c.panSplit!==false,"tlcLocal('panSplit',this.checked)")}</div><button onclick="tlcPayout()" style="width:100%;margin-top:10px;padding:11px;border:0;border-radius:11px;background:#00a884;color:#fff;font-weight:1000">SAVE PAYOUT</button></div>
 <div style="background:#132234;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:13px;margin-bottom:10px"><b style="font-size:12px">🧾 Entry & Risk</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px">${sw('','Strict Format',z.e.strictFormat!==false,"tlcLocal('entry.strictFormat',this.checked)")}${sw('','Auto Debit',z.e.autoDebitWallet!==false,"tlcLocal('entry.autoDebitWallet',this.checked)")}${sw('','Timing Guard',z.e.marketTimingEnabled!==false,"tlcLocal('entry.marketTimingEnabled',this.checked)")}${sw('','Auto Lock Limit',!!z.r.autoLockOnLimit,"tlcLocal('entry.autoLockOnLimit',this.checked)")}</div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:9px">${inp('tlc-risk-market','Market Limit',z.r.marketDailyLimit)}${inp('tlc-risk-digit','Digit Limit',z.r.digitDailyLimit)}${inp('tlc-risk-user','User Limit',z.r.userDailyLimit)}</div><button onclick="tlcLocal('risk.marketDailyLimit',document.getElementById('tlc-risk-market').value);tlcLocal('risk.digitDailyLimit',document.getElementById('tlc-risk-digit').value);tlcLocal('risk.userDailyLimit',document.getElementById('tlc-risk-user').value)" style="width:100%;margin-top:10px;padding:11px;border:1px solid rgba(255,255,255,.12);border-radius:11px;background:#203247;color:#fff;font-weight:1000">SAVE RISK LIMITS</button></div>
 <div style="background:#132234;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:13px"><b style="font-size:12px">🛠 Ledger Actions</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px"><button onclick="tlcRefresh()" style="padding:12px;border:0;border-radius:11px;background:#203247;color:#fff;font-weight:900">REFRESH DATA</button><button onclick="tlcScrapeAll()" style="padding:12px;border:0;border-radius:11px;background:#203247;color:#fff;font-weight:900">SCRAPE ALL</button></div><p style="font-size:9px;color:#91a4ba;line-height:1.5;margin-top:10px">Market card ke individual controls—Digits, Invest, T1–T4, Combo, Scrape, Pass, Fail, Schedule, Targets, Clear aur Unlock—market card par hi rahenge. Global Ledger settings yahan hain.</p></div>`;return el}
 function findTabRow(){const nodes=[...document.querySelectorAll('button,div')];const ank=nodes.find(x=>x.children.length<4&&/^ANK\b/i.test((x.innerText||'').trim()));const jodi=nodes.find(x=>x.children.length<4&&/^JODI\b/i.test((x.innerText||'').trim()));const panel=nodes.find(x=>x.children.length<4&&/^(PANEL|PANNEL)\b/i.test((x.innerText||'').trim()));if(!ank||!jodi||!panel)return null;let p=ank.parentElement;for(let i=0;i<3&&p;i++,p=p.parentElement){if(p.contains(jodi)&&p.contains(panel))return {row:p,ank,jodi,panel}}return null}
 function show(on){controlOpen=on;const old=document.getElementById(ID);if(old)old.remove();const f=findTabRow();if(!f)return;if(on){f.row.querySelectorAll('[data-tlc-control]').forEach(x=>x.style.color='#00c79a');const root=f.row.parentElement;if(root){const p=panel();root.insertBefore(p,f.row.nextSibling);[...root.children].forEach(ch=>{if(ch!==f.row&&ch!==p)ch.dataset.tlcHiddenPrev=ch.style.display,ch.style.display='none'});p.style.display='block'}}else{const root=f.row.parentElement;if(root)[...root.children].forEach(ch=>{if(ch.dataset.tlcHiddenPrev!==undefined){ch.style.display=ch.dataset.tlcHiddenPrev;delete ch.dataset.tlcHiddenPrev}})}}
 function mount(){if(!ledger()){controlOpen=false;return}const f=findTabRow();if(!f)return;if(!f.row.querySelector('[data-tlc-control]')){const b=document.createElement('button');b.dataset.tlcControl='1';b.innerHTML='CONTROL <small style="opacity:.55">⚙</small>';b.style.cssText='flex:1;background:transparent;border:0;color:#8ea3ba;font-weight:1000;font-size:12px;padding:15px 6px;border-bottom:2px solid transparent';b.onclick=()=>{show(!controlOpen);b.style.borderBottomColor=controlOpen?'#00c79a':'transparent';b.style.color=controlOpen?'#00c79a':'#8ea3ba'};f.row.appendChild(b);[f.ank,f.jodi,f.panel].forEach(x=>x.addEventListener('click',()=>{if(controlOpen){show(false);b.style.borderBottomColor='transparent';b.style.color='#8ea3ba'}}))}}
 function draw(){if(controlOpen)show(true)}window.titanLedgerControlDraw=draw;setInterval(mount,700);setTimeout(mount,200);console.log('✅ Titan Ledger CONTROL tab active');
})();
</script>
'''
