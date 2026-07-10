"""Always-visible Ledger CONTROL tab for Titan Nova mobile UI."""


def register_titan_ledger_autopf_visible(app):
    if getattr(app, "_titan_ledger_autopf_visible_registered", False):
        return
    app._titan_ledger_autopf_visible_registered = True
    from flask import request

    @app.after_request
    def inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-ledger-control-v4" in html or "</body>" not in html.lower():
                return resp
            pos = html.lower().rfind("</body>")
            html = html[:pos] + SCRIPT + html[pos:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan Ledger CONTROL visibility fix loaded")


SCRIPT = r'''
<script id="titan-ledger-control-v4">
(function(){
 if(window.__TITAN_LEDGER_CONTROL_V4__)return;
 window.__TITAN_LEDGER_CONTROL_V4__=true;
 let open=false;
 const PANEL='titanLedgerControlPanelV4';
 function headers(){const h={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(_){}return h}
 function notify(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else alert(t+'\n'+m)}catch(_){console.log(t,m)}}
 function tabRow(){
   const all=[...document.querySelectorAll('button,div,span')];
   const pick=(rx)=>all.find(el=>{const tx=(el.innerText||el.textContent||'').trim();const r=el.getBoundingClientRect();return rx.test(tx)&&r.width>40&&r.height>20&&r.top<350});
   const ank=pick(/^ANK\b/i),jodi=pick(/^JODI\b/i),panel=pick(/^(PANEL|PANNEL)\b/i);
   if(!ank||!jodi||!panel)return null;
   let p=ank.parentElement;
   for(let i=0;i<6&&p;i++,p=p.parentElement){if(p.contains(jodi)&&p.contains(panel)&&p.getBoundingClientRect().height<140)return {row:p,ank,jodi,panel}}
   return null;
 }
 function ledgerVisible(){return !!tabRow()}
 function data(){
   if(!window.appState)window.appState={};
   const s=appState.settlementSettings=appState.settlementSettings||{};
   const p=s.payoutMultipliers=s.payoutMultipliers||{};
   if(!p.ank)p.ank=9.5;if(!p.jodi)p.jodi=95;if(!p.penel)p.penel=150;
   return {s,p};
 }
 async function saveSetting(key,val){
   const patch={};patch[key]=val;
   const r=await fetch('/api/result_control/save_settings',{method:'POST',headers:headers(),body:JSON.stringify(Object.assign({date:window.currentDate||''},patch))});
   const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));
   if(d.settlementSettings)appState.settlementSettings=d.settlementSettings;
 }
 window.tlcSet=async function(k,v){try{await saveSetting(k,!!v);notify('✅ Ledger Control','Setting save ho gayi.','success')}catch(e){notify('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcSavePayout=async function(){try{const x={ank:Number(document.getElementById('tlcA').value||9.5),jodi:Number(document.getElementById('tlcJ').value||95),penel:Number(document.getElementById('tlcP').value||150),panel:Number(document.getElementById('tlcP').value||150),patti:Number(document.getElementById('tlcP').value||150)};await saveSetting('payoutMultipliers',x);notify('✅ Payout Saved','ANK/JODI/PANEL payout save ho gaya.','success')}catch(e){notify('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcRun=async function(){try{const r=await fetch('/api/ledger_auto_mark',{method:'POST',headers:headers(),body:JSON.stringify({date:window.currentDate||'',force:false,source:'ledger_control_v4'})});const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));if(d.profiles)appState.profiles=d.profiles;const s=d.summary||{};notify('✅ Auto Pass/Fail',`${Number(s.marked||0)} marked • PASS ${Number(s.pass||0)} • FAIL ${Number(s.fail||0)}`,Number(s.marked||0)?'success':'info');try{render(true)}catch(_){}}catch(e){notify('❌ Auto P/F Error',String(e.message||e),'danger')}};
 function panel(){const z=data();const e=document.createElement('section');e.id=PANEL;e.style.cssText='margin:10px 12px 120px;color:#fff;font-family:Arial';e.innerHTML=`
 <div style="background:#132536;border:1px solid #00c79a55;border-radius:18px;padding:14px"><div style="font-size:15px;font-weight:900">⚙️ LEDGER CONTROL CENTER</div><div style="font-size:10px;color:#8fa5b8;margin-top:4px">ANK · JODI · PANEL ke global controls</div></div>
 <div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🤖 Auto Pass / Fail</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">
 ${toggle('Auto Mark',z.s.autoLedgerMarking!==false,"tlcSet('autoLedgerMarking',this.checked)")}${toggle('Only WAIT',z.s.autoLedgerMarkOnlyWait!==false,"tlcSet('autoLedgerMarkOnlyWait',this.checked)")}${toggle('All VIPs',z.s.autoLedgerApplyToAllProfiles!==false,"tlcSet('autoLedgerApplyToAllProfiles',this.checked)")}${toggle('Record Results',z.s.autoLedgerRecordResults!==false,"tlcSet('autoLedgerRecordResults',this.checked)")}</div><button onclick="tlcRun()" style="width:100%;margin-top:10px;padding:12px;border:1px solid #fac74866;border-radius:11px;background:#fac74822;color:#fac748;font-weight:900">MARK NOW FROM SAVED RESULTS</button></div>
 <div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🎯 Game & Payout</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px">${num('tlcA','ANK X',z.p.ank)}${num('tlcJ','JODI X',z.p.jodi)}${num('tlcP','PANEL X',z.p.penel)}</div><button onclick="tlcSavePayout()" style="width:100%;margin-top:10px;padding:12px;border:0;border-radius:11px;background:#00a884;color:white;font-weight:900">SAVE PAYOUT</button></div>
 <div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px;font-size:10px;color:#9bb0c2;line-height:1.6"><b style="color:white;font-size:12px">📌 Market Card Controls</b><br>Digits, Invest, T1–T4, Combo, Scrape, Pass, Fail, Schedule, Targets, Clear aur Unlock market card par hi rahenge.</div>`;return e}
 function toggle(l,on,fn){return `<label style="display:flex;justify-content:space-between;background:#0d1b29;padding:11px;border-radius:11px;font-size:11px;font-weight:800"><span>${l}</span><input type="checkbox" ${on?'checked':''} onchange="${fn}"></label>`}
 function num(id,l,v){return `<label style="font-size:9px;color:#8fa5b8">${l}<input id="${id}" type="number" step="0.1" value="${v}" style="box-sizing:border-box;width:100%;margin-top:5px;padding:10px;border-radius:10px;border:1px solid #ffffff18;background:#0d1b29;color:white;font-weight:900"></label>`}
 function closePanel(){open=false;document.getElementById(PANEL)?.remove();document.querySelectorAll('[data-tlc-hide]').forEach(x=>{x.style.display=x.dataset.tlcHide||'';delete x.dataset.tlcHide});const b=document.querySelector('[data-tlc-control]');if(b){b.style.color='#8ea3ba';b.style.borderBottomColor='transparent'}}
 function openPanel(){const f=tabRow();if(!f)return;open=true;const root=f.row.parentElement;const p=panel();root.insertBefore(p,f.row.nextSibling);[...root.children].forEach(x=>{if(x!==f.row&&x!==p){x.dataset.tlcHide=x.style.display||'';x.style.display='none'}});const b=f.row.querySelector('[data-tlc-control]');if(b){b.style.color='#00c79a';b.style.borderBottomColor='#00c79a'}}
 function mount(){
   const f=tabRow();
   const fallback=document.getElementById('titanLedgerControlFallback');
   if(!f){if(fallback)fallback.remove();if(open)closePanel();return}
   if(!f.row.querySelector('[data-tlc-control]')){
     const b=document.createElement('button');b.dataset.tlcControl='1';b.textContent='CONTROL';b.style.cssText='flex:1;min-width:78px;background:transparent;border:0;border-bottom:2px solid transparent;color:#8ea3ba;font-weight:900;font-size:12px;padding:15px 6px';b.onclick=()=>open?closePanel():openPanel();f.row.appendChild(b);
     [f.ank,f.jodi,f.panel].forEach(x=>x.addEventListener('click',()=>{if(open)closePanel()}));
   }
   if(!document.querySelector('[data-tlc-control]')&&!fallback){const fb=document.createElement('button');fb.id='titanLedgerControlFallback';fb.textContent='⚙ CONTROL';fb.style.cssText='position:fixed;right:12px;bottom:92px;z-index:99999;background:#00a884;color:#fff;border:0;border-radius:22px;padding:11px 15px;font-weight:900;box-shadow:0 5px 20px #0008';fb.onclick=()=>open?closePanel():openPanel();document.body.appendChild(fb)}
 }
 new MutationObserver(()=>mount()).observe(document.documentElement,{childList:true,subtree:true});
 setInterval(mount,600);setTimeout(mount,100);setTimeout(mount,1200);
 console.log('✅ Titan Ledger CONTROL v4 active');
})();
</script>
'''
