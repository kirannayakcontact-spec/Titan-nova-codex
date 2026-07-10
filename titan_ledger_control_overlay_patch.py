def register_titan_ledger_control_overlay(app):
    if getattr(app, '_titan_ledger_control_overlay_registered', False):
        return
    app._titan_ledger_control_overlay_registered = True
    from flask import request

    @app.after_request
    def inject(resp):
        try:
            if request.method != 'GET' or resp.status_code != 200 or request.path.startswith('/api/'):
                return resp
            if 'text/html' not in (resp.headers.get('Content-Type') or '').lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or 'titan-ledger-control-overlay-v1' in html or '</body>' not in html.lower():
                return resp
            i = html.lower().rfind('</body>')
            html = html[:i] + SCRIPT + html[i:]
            resp.set_data(html)
            resp.headers['Content-Length'] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp
    print('✅ Titan Ledger control overlay loaded')

SCRIPT = r'''
<script id="titan-ledger-control-overlay-v1">
(function(){
 if(window.__TLC_OVERLAY_V1__) return; window.__TLC_OVERLAY_V1__=true;
 const BTN='titanLedgerControlBtnFinal', MOD='titanLedgerControlModalFinal';
 function visibleLedger(){
   const t=[...document.querySelectorAll('button,div,span')].map(e=>({e,t:(e.innerText||'').trim(),r:e.getBoundingClientRect()}));
   const has=x=>t.some(o=>new RegExp('^'+x+'\\b','i').test(o.t)&&o.r.width>40&&o.r.height>20&&o.r.top<350&&o.r.bottom>0);
   return has('ANK')&&has('JODI')&&(has('PANEL')||has('PANNEL'));
 }
 function h(){const x={'Content-Type':'application/json'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN');if(t)x['X-Titan-Admin-Token']=t}catch(_){}return x}
 function n(a,b,c){try{if(typeof showRealNotification==='function')showRealNotification(a,b,c||'info');else alert(a+'\n'+b)}catch(_){}}
 function s(){if(!window.appState)window.appState={};const x=appState.settlementSettings=appState.settlementSettings||{};x.payoutMultipliers=x.payoutMultipliers||{ank:9.5,jodi:95,penel:150};return x}
 async function save(k,v){const p={};p[k]=v;const r=await fetch('/api/result_control/save_settings',{method:'POST',headers:h(),body:JSON.stringify(Object.assign({date:window.currentDate||''},p))});const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));if(d.settlementSettings)appState.settlementSettings=d.settlementSettings}
 window.tlcFinalSet=async(k,v)=>{try{await save(k,!!v);n('✅ Ledger Control','Setting save ho gayi','success')}catch(e){n('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcFinalPayout=async()=>{try{const p={ank:+document.getElementById('tlfa').value||9.5,jodi:+document.getElementById('tlfj').value||95,penel:+document.getElementById('tlfp').value||150,panel:+document.getElementById('tlfp').value||150,patti:+document.getElementById('tlfp').value||150};await save('payoutMultipliers',p);n('✅ Payout Saved','ANK/JODI/PANEL payout save ho gaya','success')}catch(e){n('❌ Save Error',String(e.message||e),'danger')}};
 window.tlcFinalRun=async()=>{try{const r=await fetch('/api/ledger_auto_mark',{method:'POST',headers:h(),body:JSON.stringify({date:window.currentDate||'',force:false,source:'ledger_control_overlay'})});const d=await r.json().catch(()=>({}));if(!r.ok||d.status!=='success')throw new Error(d.message||('HTTP '+r.status));const x=d.summary||{};n('✅ Auto Pass/Fail',`${x.marked||0} marked • PASS ${x.pass||0} • FAIL ${x.fail||0}`,'success');try{render(true)}catch(_){}}catch(e){n('❌ Auto P/F Error',String(e.message||e),'danger')}};
 function tog(l,k,on){return `<label style="display:flex;justify-content:space-between;padding:12px;background:#0e1b29;border-radius:12px;font-size:12px;font-weight:800"><span>${l}</span><input type="checkbox" ${on?'checked':''} onchange="tlcFinalSet('${k}',this.checked)"></label>`}
 function open(){const x=s();let m=document.getElementById(MOD);if(m)m.remove();m=document.createElement('div');m.id=MOD;m.style.cssText='position:fixed;inset:70px 0 72px 0;z-index:999999;background:#07111df2;overflow:auto;padding:12px;color:#fff;font-family:Arial';m.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;background:#123047;border:1px solid #00c79a55;padding:14px;border-radius:16px"><div><b>⚙ LEDGER CONTROL CENTER</b><div style="font-size:10px;color:#9db0c0;margin-top:4px">ANK · JODI · PANEL</div></div><button onclick="document.getElementById('${MOD}').remove()" style="background:#203247;color:#fff;border:0;border-radius:10px;padding:9px 12px">✕</button></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🤖 Auto Pass / Fail</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">${tog('Auto Mark','autoLedgerMarking',x.autoLedgerMarking!==false)}${tog('Only WAIT','autoLedgerMarkOnlyWait',x.autoLedgerMarkOnlyWait!==false)}${tog('All VIPs','autoLedgerApplyToAllProfiles',x.autoLedgerApplyToAllProfiles!==false)}${tog('Record Results','autoLedgerRecordResults',x.autoLedgerRecordResults!==false)}</div><button onclick="tlcFinalRun()" style="width:100%;margin-top:10px;padding:12px;background:#fac74822;color:#fac748;border:1px solid #fac74866;border-radius:11px;font-weight:900">MARK NOW FROM SAVED RESULTS</button></div><div style="background:#132234;border-radius:16px;padding:13px;margin-top:10px"><b>🎯 Game & Payout</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px"><input id="tlfa" value="${x.payoutMultipliers?.ank||9.5}" type="number" step="0.1" style="padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlfj" value="${x.payoutMultipliers?.jodi||95}" type="number" step="0.1" style="padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"><input id="tlfp" value="${x.payoutMultipliers?.penel||150}" type="number" step="0.1" style="padding:11px;border-radius:10px;border:1px solid #ffffff22;background:#0e1b29;color:white"></div><button onclick="tlcFinalPayout()" style="width:100%;margin-top:10px;padding:12px;background:#00a884;color:white;border:0;border-radius:11px;font-weight:900">SAVE PAYOUT</button></div>`;document.body.appendChild(m)}
 function mount(){let b=document.getElementById(BTN);if(!visibleLedger()){if(b)b.remove();return}if(!b){b=document.createElement('button');b.id=BTN;b.textContent='⚙ CONTROL';b.style.cssText='position:fixed;right:12px;top:145px;z-index:999998;background:#00a884;color:#fff;border:0;border-radius:22px;padding:11px 15px;font-weight:900;box-shadow:0 5px 20px #0008';b.onclick=open;document.body.appendChild(b)}}
 new MutationObserver(mount).observe(document.documentElement,{childList:true,subtree:true});setInterval(mount,500);setTimeout(mount,200);setTimeout(mount,1200);
})();
</script>
'''
