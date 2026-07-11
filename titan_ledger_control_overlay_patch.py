"""Canonical Ledger control UI.

This is the only Ledger Auto Pass/Fail UI injector. It keeps the controls only
inside Ledger and removes the obsolete Result-tab Auto Pass/Fail presentation.
"""


def register_titan_ledger_control_overlay(app):
    if getattr(app, "_titan_ledger_control_overlay_registered", False):
        return
    app._titan_ledger_control_overlay_registered = True

    from flask import request

    version = "2026-07-10-ledger-control-canonical-v3"

    @app.after_request
    def inject_ledger_control(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-control-canonical-v3" in html or "</body>" not in html.lower():
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
<script id="titan-ledger-control-canonical-v3">
(function(){
 if(window.__TITAN_LEDGER_CONTROL_CANONICAL_V3__) return;
 window.__TITAN_LEDGER_CONTROL_CANONICAL_V3__=true;
 const BUTTON_ID='titanLedgerControlButton';
 const MODAL_ID='titanLedgerControlModal';
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
   modal.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;background:#123047;border:1px solid #00c79a55;padding:14px;border-radius:16px"><div><b>⚙ LEDGER CONTROL CENTER</b><div style="font-size:10px;color:#9db0c0;margin-top:4px">ANK · JODI · PANEL</div></div><button onclick="document.getElementById('${MODAL_ID}').remove()" style="background:#203247;color:#fff;border:0;border-radius:10px;padding:9px 12px">✕</button></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px"><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>MARKED</small><b style="display:block;margin-top:4px">${sum.marked}</b></div><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>PASS</small><b style="display:block;margin-top:4px;color:#4ade80">${sum.pass}</b></div><div style="background:#132234;padding:11px;border-radius:12px;text-align:center"><small>FAIL</small><b style="display:block;margin-top:4px;color:#fb7185">${sum.fail}</b></div></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🤖 Auto Pass / Fail</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">${toggle('Auto Mark','autoLedgerMarking',s.autoLedgerMarking!==false)}${toggle('Only WAIT','autoLedgerMarkOnlyWait',s.autoLedgerMarkOnlyWait!==false)}${toggle('All VIPs','autoLedgerApplyToAllProfiles',s.autoLedgerApplyToAllProfiles!==false)}${toggle('Record Results','autoLedgerRecordResults',s.autoLedgerRecordResults!==false)}</div><button onclick="titanLedgerControlRun()" style="width:100%;margin-top:10px;padding:12px;background:#fac74822;color:#fac748;border:1px solid #fac74866;border-radius:11px;font-weight:900">MARK NOW FROM SAVED RESULTS</button></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🎯 Game & Payout</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px"><input id="tlc-ank" value="${p.ank}" type="number" step="0.1" placeholder="ANK" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlc-jodi" value="${p.jodi}" type="number" step="0.1" placeholder="JODI" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlc-panel" value="${p.penel}" type="number" step="0.1" placeholder="PANEL" style="min-width:0;padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></div><button onclick="titanLedgerControlSavePayout()" style="width:100%;margin-top:10px;padding:12px;background:#00a884;color:white;border:0;border-radius:11px;font-weight:900">SAVE PAYOUT</button></div>`;
   document.body.appendChild(modal);
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
