"""Canonical Ledger control UI.

This is the only Ledger Auto Pass/Fail UI injector. It keeps the controls only
inside Ledger and removes the obsolete Result-tab Auto Pass/Fail presentation.
"""


def register_titan_ledger_control_overlay(app):
    if getattr(app, "_titan_ledger_control_overlay_registered", False):
        return
    app._titan_ledger_control_overlay_registered = True

    from flask import request

    version = "2026-07-11-ledger-market-protocol-control-v4"

    @app.after_request
    def inject_ledger_control(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-control-canonical-v4" in html or "</body>" not in html.lower():
                return resp
            index = html.lower().rfind("</body>")
            html = html[:index] + SCRIPT + html[index:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception as exc:
            print("⚠️ Ledger control injection failed:", exc)
        return resp

    print("✅ Titan canonical Ledger control loaded", version)


SCRIPT = r'''
<script id="titan-ledger-control-canonical-v4">
(function(){
 if(window.__TITAN_LEDGER_CONTROL_CANONICAL_V4__) return;
 window.__TITAN_LEDGER_CONTROL_CANONICAL_V4__=true;
 const BUTTON_ID='titanLedgerControlButton';
 const MODAL_ID='titanLedgerControlModal';
 let titanLedgerMarketItems=[];
 let titanLedgerMarketQuery='';
 function apiHeaders(){const h={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(_){}return h}
 function notify(title,message,type){try{if(typeof showRealNotification==='function')showRealNotification(title,message,type||'info');else alert(title+'\n'+message)}catch(_){console.log(title,message)}}
 function businessDate(){try{return typeof currentDate!=='undefined'&&currentDate?currentDate:new Date().toISOString().slice(0,10)}catch(_){return new Date().toISOString().slice(0,10)}}
 function ledgerVisible(){
   const rows=[...document.querySelectorAll('button,div,span')].map(el=>({text:(el.innerText||el.textContent||'').trim(),rect:el.getBoundingClientRect()}));
   const has=rx=>rows.some(x=>rx.test(x.text)&&x.rect.width>38&&x.rect.height>18&&x.rect.top<360&&x.rect.bottom>0);
   return has(/^ANK\b/i)&&has(/^JODI\b/i)&&(has(/^PANEL\b/i)||has(/^PANNEL\b/i));
 }
 function removeResultAutoPf(){
   try{
     const nodes=[...document.querySelectorAll('h1,h2,h3,h4,p,div,span')];
     for(const node of nodes){
       const text=(node.textContent||'').replace(/\s+/g,' ').trim();
       if(!/^Ledger Auto Pass\/?Fail$/i.test(text))continue;
       if(node.closest('#'+MODAL_ID))continue;
       let card=node;
       for(let i=0;i<7&&card;i++,card=card.parentElement){
         const cls=String(card.className||'');
         const t=(card.textContent||'').replace(/\s+/g,' ');
         if((/native-card|rounded-2xl|settlement/i.test(cls)||card.tagName==='SECTION')&&/Auto Mark|Only WAIT|All VIPs|Mark Now|Auto Hit\/Miss/i.test(t)){
           card.remove();
           break;
         }
       }
     }
   }catch(e){console.warn('Result Auto P/F cleanup failed',e)}
 }
 function state(){
   if(!window.appState)window.appState={};
   const s=appState.settlementSettings=(appState.settlementSettings&&typeof appState.settlementSettings==='object')?appState.settlementSettings:{};
   if(typeof s.autoLedgerMarking==='undefined')s.autoLedgerMarking=true;
   if(typeof s.autoLedgerMarkOnlyWait==='undefined')s.autoLedgerMarkOnlyWait=true;
   if(typeof s.autoLedgerApplyToAllProfiles==='undefined')s.autoLedgerApplyToAllProfiles=true;
   if(typeof s.autoLedgerRecordResults==='undefined')s.autoLedgerRecordResults=true;
   const p=s.payoutMultipliers=(s.payoutMultipliers&&typeof s.payoutMultipliers==='object')?s.payoutMultipliers:{};
   const hasNum=v=>Number.isFinite(Number(v));
   if(!hasNum(p.ank))p.ank=9.5;
   if(!hasNum(p.jodi))p.jodi=95;
   if(!hasNum(p.penel))p.penel=150;
   if(!hasNum(p.panel))p.panel=p.penel;
   if(!hasNum(p.patti))p.patti=p.penel;
   return s;
 }

 function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
 function cleanTargets(v){return String(v||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean)}
 function marketItemsFromPayload(data){const reg=data&& (data.marketRegistry||data.registry||data); const raw=(reg&&reg.items)||data.items||{}; return Object.values(raw).filter(x=>x&&typeof x==='object').sort((a,b)=>Number(a.sortOrder||9999)-Number(b.sortOrder||9999)||String(a.displayName||a.name||a.id).localeCompare(String(b.displayName||b.name||b.id)))}
 async function marketPost(body){const res=await fetch('/api/market_action',{method:'POST',headers:apiHeaders(),body:JSON.stringify(body)});const data=await res.json().catch(()=>({}));if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));if(data.marketRegistry)appState.marketRegistry=data.marketRegistry;if(data.ledgerMarkets)window.markets=data.ledgerMarkets;if(data.ledgerBaseMarkets)window.baseMarkets=data.ledgerBaseMarkets;if(data.resultMarkets)window.resultMarkets=data.resultMarkets;if(data.resultBaseMarkets)window.resultBaseMarkets=data.resultBaseMarkets;try{if(typeof refreshMarketArrays==='function')refreshMarketArrays()}catch(_){}return data}
 window.titanLedgerMarketLoad=async function(silent){try{const res=await fetch('/api/market_registry?_='+Date.now(),{cache:'no-store',headers:apiHeaders()});const data=await res.json().catch(()=>({}));if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));if(data.marketRegistry)appState.marketRegistry=data.marketRegistry;titanLedgerMarketItems=marketItemsFromPayload(data);titanLedgerMarketDraw();if(!silent)notify('✅ Market Protocol','Market list refresh ho gayi.','success')}catch(e){notify('❌ Market Load',String(e.message||e),'danger')}};
 window.titanLedgerMarketSearch=function(v){titanLedgerMarketQuery=String(v||'');titanLedgerMarketDraw()};
 window.titanLedgerMarketFlag=async function(id,field,value){try{await marketPost({action:'set_flag',id,field,value:!!value});await titanLedgerMarketLoad(true);notify('✅ Market Protocol','Control save ho gaya.','success')}catch(e){notify('❌ Market Save',String(e.message||e),'danger')}};
 window.titanLedgerMarketTime=async function(id,stage,value){try{await marketPost({action:'update_time',id,stage,value});await titanLedgerMarketLoad(true);notify('✅ Market Time','Time save ho gaya.','success')}catch(e){notify('❌ Market Time',String(e.message||e),'danger')}};
 window.titanLedgerMarketRole=async function(id,role){try{await marketPost({action:'set_role_targets',id,role,targets:cleanTargets(document.getElementById('tlm-'+id+'-'+role)?.value||'')});await titanLedgerMarketLoad(true);notify('✅ Market Targets','Group targets save ho gaye.','success')}catch(e){notify('❌ Target Save',String(e.message||e),'danger')}};
 window.titanLedgerMarketArchive=async function(id,action){try{await marketPost({action,id});await titanLedgerMarketLoad(true);notify('✅ Market Protocol',action==='restore'?'Market restore ho gaya.':'Market archive/off ho gaya.','success')}catch(e){notify('❌ Market Action',String(e.message||e),'danger')}};
 window.titanLedgerMarketAdd=async function(){try{const g=id=>document.getElementById(id)?.value||''; const payload={action:'direct_add_full',url:g('tlm-url'),name:g('tlm-name'),websiteName:g('tlm-website')||g('tlm-name'),openTime:g('tlm-open'),closeTime:g('tlm-close'),chartUrl:g('tlm-chart'),ledgerEnabled:document.getElementById('tlm-ledger')?.checked!==false,resultEnabled:document.getElementById('tlm-results')?.checked!==false,autoPassFailEnabled:document.getElementById('tlm-autopf')?.checked!==false,scheduleEnabled:document.getElementById('tlm-schedule')?.checked!==false,entryEnabled:document.getElementById('tlm-entry')?.checked!==false,autoResultEnabled:document.getElementById('tlm-autores')?.checked!==false,entryTargets:cleanTargets(g('tlm-entry-targets')),resultTargets:cleanTargets(g('tlm-result-targets')),forwardTargets:cleanTargets(g('tlm-forward-targets')),scheduleTargets:cleanTargets(g('tlm-schedule-targets')),bookieTargets:cleanTargets(g('tlm-bookie-targets'))}; if(!payload.url&&!payload.name)throw new Error('Market URL ya name required hai.'); await marketPost(payload); ['tlm-url','tlm-name','tlm-website','tlm-open','tlm-close','tlm-chart','tlm-entry-targets','tlm-result-targets','tlm-forward-targets','tlm-schedule-targets','tlm-bookie-targets'].forEach(id=>{const el=document.getElementById(id);if(el)el.value=''}); await titanLedgerMarketLoad(true); notify('✅ Market Added','Market Ledger protocol me save ho gaya.','success')}catch(e){notify('❌ Market Add',String(e.message||e),'danger')}};
 function marketSwitch(m,f,l){return `<label style="display:flex;justify-content:space-between;gap:8px;align-items:center;padding:8px;background:#0e1b29;border-radius:10px;font-size:10px;font-weight:900"><span>${l}</span><input type="checkbox" ${m[f]!==false?'checked':''} onchange="titanLedgerMarketFlag('${esc(m.id)}','${f}',this.checked)"></label>`}
 function marketRoleBox(m,r,l){const val=Array.isArray(m[r+'Targets'])?m[r+'Targets'].join('\n'):'';return `<div><b style="font-size:10px;color:#9db0c0">${l}</b><textarea id="tlm-${esc(m.id)}-${r}" rows="1" style="width:100%;box-sizing:border-box;margin-top:4px;padding:8px;border-radius:9px;border:1px solid #ffffff22;background:#0e1b29;color:white;font-size:10px">${esc(val)}</textarea><button onclick="titanLedgerMarketRole('${esc(m.id)}','${r}')" style="width:100%;margin-top:4px;padding:8px;background:#203247;color:#fff;border:0;border-radius:9px;font-size:10px;font-weight:900">SAVE ${l}</button></div>`}
 window.titanLedgerMarketDraw=function(){const root=document.getElementById('tlm-list');if(!root)return;const q=titanLedgerMarketQuery.trim().toUpperCase();const items=titanLedgerMarketItems.filter(m=>!q||String(m.displayName||m.name||m.id).toUpperCase().includes(q)).slice(0,30);root.innerHTML=items.map(m=>{const time=m.times||{};const name=m.displayName||m.name||m.id;return `<div style="background:#0b1724;border:1px solid #ffffff14;border-radius:14px;padding:10px;margin-top:8px"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b style="font-size:12px">${esc(name)}</b><span style="font-size:9px;color:${m.enabled!==false?'#4ade80':'#fb7185'}">${m.enabled!==false?'ACTIVE':'OFF'}</span></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px"><input value="${esc(time.open||'')}" onchange="titanLedgerMarketTime('${esc(m.id)}','open',this.value)" placeholder="Open HH:MM" style="min-width:0;padding:8px;border-radius:9px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input value="${esc(time.close||'')}" onchange="titanLedgerMarketTime('${esc(m.id)}','close',this.value)" placeholder="Close HH:MM" style="min-width:0;padding:8px;border-radius:9px;border:1px solid #ffffff22;background:#0e1b29;color:white"></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px">${marketSwitch(m,'enabled','Market ON')}${marketSwitch(m,'ledgerEnabled','Ledger')}${marketSwitch(m,'resultEnabled','Results')}${marketSwitch(m,'entryEnabled','Entries')}${marketSwitch(m,'scheduleEnabled','Schedule')}${marketSwitch(m,'autoResultEnabled','Auto Result')}${marketSwitch(m,'autoPassFailEnabled','Auto P/F')}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px">${marketRoleBox(m,'entry','ENTRY')}${marketRoleBox(m,'result','RESULT')}${marketRoleBox(m,'forward','FORWARD')}${marketRoleBox(m,'schedule','SCHEDULE')}${marketRoleBox(m,'bookie','BOOKIE')}</div><div style="display:flex;gap:6px;margin-top:8px"><button onclick="titanLedgerMarketArchive('${esc(m.id)}','archive')" style="flex:1;padding:9px;background:#fac74822;color:#fac748;border:1px solid #fac74866;border-radius:9px;font-weight:900">ARCHIVE/OFF</button><button onclick="titanLedgerMarketArchive('${esc(m.id)}','restore')" style="flex:1;padding:9px;background:#00a88422;color:#4ade80;border:1px solid #00a88466;border-radius:9px;font-weight:900">RESTORE</button></div></div>`}).join('')||'<div style="background:#0b1724;border-radius:12px;padding:14px;text-align:center;color:#9db0c0;font-size:12px">Market nahi mila.</div>'};
 function marketProtocolHtml(){return `<div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><div><b>🟢 Market Protocol Control</b><div style="font-size:10px;color:#9db0c0;margin-top:3px">Ledger · Results · Entries · Schedule · Auto P/F</div></div><button onclick="titanLedgerMarketLoad(false)" style="background:#203247;color:#fff;border:0;border-radius:10px;padding:9px 10px;font-size:10px;font-weight:900">REFRESH</button></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px"><input id="tlm-url" placeholder="Website/Chart URL" style="grid-column:1/3;min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlm-name" placeholder="Market name" style="min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlm-website" placeholder="Website name" style="min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlm-open" placeholder="Open HH:MM" style="min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlm-close" placeholder="Close HH:MM" style="min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlm-chart" placeholder="Chart URL optional" style="grid-column:1/3;min-width:0;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></div><div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px">${[['tlm-ledger','Ledger'],['tlm-results','Results'],['tlm-entry','Entries'],['tlm-schedule','Schedule'],['tlm-autores','Auto Result'],['tlm-autopf','Auto P/F']].map(x=>`<label style="display:flex;justify-content:space-between;align-items:center;background:#0e1b29;border-radius:10px;padding:8px;font-size:10px;font-weight:900"><span>${x[1]}</span><input id="${x[0]}" type="checkbox" checked></label>`).join('')}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px"><textarea id="tlm-entry-targets" rows="1" placeholder="Entry groups" style="padding:9px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></textarea><textarea id="tlm-result-targets" rows="1" placeholder="Result groups" style="padding:9px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></textarea><textarea id="tlm-forward-targets" rows="1" placeholder="Forward groups" style="padding:9px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></textarea><textarea id="tlm-schedule-targets" rows="1" placeholder="Schedule groups" style="padding:9px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></textarea><textarea id="tlm-bookie-targets" rows="1" placeholder="Bookie/Admin groups" style="grid-column:1/3;padding:9px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></textarea></div><button onclick="titanLedgerMarketAdd()" style="width:100%;margin-top:10px;padding:12px;background:#00a884;color:white;border:0;border-radius:11px;font-weight:900">SAVE MARKET PROTOCOL</button><input oninput="titanLedgerMarketSearch(this.value)" placeholder="Search market protocol..." style="width:100%;box-sizing:border-box;margin-top:10px;padding:10px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><div id="tlm-list" style="margin-top:8px"></div></div>`}

 function recentSummary(){
   const day=(window.appState&&appState.ledgerAutoMarkRecords&&appState.ledgerAutoMarkRecords[businessDate()])||{};
   const rows=Object.values(day).filter(x=>x&&typeof x==='object');
   return {marked:rows.reduce((n,x)=>n+Number(x.marked||0),0),pass:rows.reduce((n,x)=>n+Number(x.pass||0),0),fail:rows.reduce((n,x)=>n+Number(x.fail||0),0)};
 }
 async function saveSetting(key,value){
   const patch={date:businessDate()};patch[key]=value;
   const res=await fetch('/api/result_control/save_settings',{method:'POST',headers:apiHeaders(),body:JSON.stringify(patch)});
   const data=await res.json().catch(()=>({}));
   if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));
   if(data.settlementSettings){appState.settlementSettings=data.settlementSettings;if(window.__BOOT_STATE__)window.__BOOT_STATE__.settlementSettings=data.settlementSettings;}
   try{if(typeof state==='object'&&state)state.settlementSettings=data.settlementSettings||state.settlementSettings}catch(_){}
   try{if(typeof LOCAL_KEY!=='undefined')localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(_){}
   try{if(typeof refreshResultsState==='function')refreshResultsState()}catch(_){}
   return data;
 }
 window.titanLedgerControlSet=async function(key,value){try{await saveSetting(key,!!value);notify('✅ Ledger Control','Setting save ho gayi.','success')}catch(e){notify('❌ Save Error',String(e.message||e),'danger')}};
 window.titanLedgerControlSavePayout=async function(){
   try{
     const payout={ank:Number(document.getElementById('tlc-ank').value||9.5),jodi:Number(document.getElementById('tlc-jodi').value||95),penel:Number(document.getElementById('tlc-panel').value||150)};
     payout.panel=payout.penel;payout.patti=payout.penel;
     if(!Number.isFinite(payout.ank)||!Number.isFinite(payout.jodi)||!Number.isFinite(payout.penel))throw new Error('Payout number invalid hai.');
     await saveSetting('payoutMultipliers',payout);
     notify('✅ Payout Saved','ANK/JODI/PANEL payout save ho gaya.','success');
   }catch(e){notify('❌ Save Error',String(e.message||e),'danger')}
 };
 window.titanLedgerControlRun=async function(){
   try{
     if(state().autoLedgerMarking===false)throw new Error('Auto Mark OFF hai. Pehle ON karo.');
     notify('🤖 Auto Pass/Fail','Saved result se WAIT cards check ho rahe hain...','info');
     const res=await fetch('/api/ledger_auto_mark',{method:'POST',headers:apiHeaders(),body:JSON.stringify({date:businessDate(),force:false,source:'ledger_control_canonical'})});
     const data=await res.json().catch(()=>({}));
     if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));
     if(data.profiles)appState.profiles=data.profiles;
     if(data.ledgerAutoMarkRecords)appState.ledgerAutoMarkRecords=data.ledgerAutoMarkRecords;
     const x=data.summary||recentSummary();
     notify('✅ Auto Pass/Fail',`${Number(x.marked||0)} marked • PASS ${Number(x.pass||0)} • FAIL ${Number(x.fail||0)}`,Number(x.marked||0)?'success':'info');
     try{if(typeof render==='function')render(true)}catch(_){}
     document.getElementById(MODAL_ID)?.remove();
   }catch(e){notify('❌ Auto P/F Error',String(e.message||e),'danger')}
 };
 function toggle(label,key,on){return `<label style="display:flex;justify-content:space-between;align-items:center;padding:12px;background:#0e1b29;border-radius:12px;font-size:12px;font-weight:800"><span>${label}</span><input type="checkbox" ${on?'checked':''} onchange="titanLedgerControlSet('${key}',this.checked)"></label>`}
 window.titanLedgerControlOpen=function openControl(){
   document.getElementById(MODAL_ID)?.remove();
   const s=state(),p=s.payoutMultipliers,sum=recentSummary();
   const modal=document.createElement('div');modal.id=MODAL_ID;modal.style.cssText='position:fixed;inset:64px 0 70px;z-index:999999;background:#07111df5;overflow:auto;padding:12px;color:#fff;font-family:Arial';
   modal.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;background:#123047;border:1px solid #00c79a55;padding:14px;border-radius:16px"><div><b>⚙ LEDGER CONTROL CENTER</b><div style="font-size:10px;color:#9db0c0;margin-top:4px">ANK · JODI · PANEL</div></div><button onclick="document.getElementById('${MODAL_ID}').remove()" style="background:#203247;color:#fff;border:0;border-radius:10px;padding:9px 12px">✕</button></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px"><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>MARKED</small><b style="display:block;margin-top:4px">${sum.marked}</b></div><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>PASS</small><b style="display:block;margin-top:4px;color:#4ade80">${sum.pass}</b></div><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>FAIL</small><b style="display:block;margin-top:4px;color:#fb7185">${sum.fail}</b></div></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🤖 Auto Pass / Fail</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">${toggle('Auto Mark','autoLedgerMarking',s.autoLedgerMarking!==false)}${toggle('Only WAIT','autoLedgerMarkOnlyWait',s.autoLedgerMarkOnlyWait!==false)}${toggle('All VIPs','autoLedgerApplyToAllProfiles',s.autoLedgerApplyToAllProfiles!==false)}${toggle('Record Results','autoLedgerRecordResults',s.autoLedgerRecordResults!==false)}</div><button onclick="titanLedgerControlRun()" style="width:100%;margin-top:10px;padding:12px;background:#fac74822;color:#fac748;border:1px solid #fac74866;border-radius:11px;font-weight:900">MARK NOW FROM SAVED RESULTS</button></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🎯 Game & Payout</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px"><input id="tlc-ank" value="${p.ank}" type="number" step="0.1" placeholder="ANK" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlc-jodi" value="${p.jodi}" type="number" step="0.1" placeholder="JODI" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlc-panel" value="${p.penel}" type="number" step="0.1" placeholder="PANEL" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></div><button onclick="titanLedgerControlSavePayout()" style="width:100%;margin-top:10px;padding:12px;background:#00a884;color:white;border:0;border-radius:11px;font-weight:900">SAVE PAYOUT</button></div>${marketProtocolHtml()}`;
   document.body.appendChild(modal);
   if(!titanLedgerMarketItems.length) titanLedgerMarketLoad(true); else titanLedgerMarketDraw();
 }
 function mount(){
   removeResultAutoPf();
   let button=document.getElementById(BUTTON_ID);
   if(!ledgerVisible()){if(button)button.remove();document.getElementById(MODAL_ID)?.remove();return}
   if(button)return;
   const tabs=document.querySelector('.pill-tabs'); if(!tabs)return;
   button=document.createElement('button');button.id=BUTTON_ID;button.innerHTML='⚙ Control';button.className='pill-tab titan-ledger-control-tab';button.style.cssText='background:#00a884;color:#fff;border-color:#00a884;box-shadow:0 5px 20px #0005;white-space:nowrap';button.onclick=window.titanLedgerControlOpen;tabs.appendChild(button);
 }
 new MutationObserver(mount).observe(document.documentElement,{childList:true,subtree:true});
 setInterval(mount,700);setTimeout(mount,100);setTimeout(mount,1200);
 console.log('✅ Titan Ledger-only Auto Pass/Fail UI active');
})();
</script>
'''
