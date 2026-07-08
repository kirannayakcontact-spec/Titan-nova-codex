"""Force-visible Deposit section inside the Finance tab.

The previous merge waited for Payment DOM anchors. On some mobile renders those anchors
are created only after a subtab is selected, so admins could not see Deposit anywhere.
This module injects a compact inline Finance Deposit panel when the Finance nav is clicked
or when payment/finance UI appears. It never creates the old large floating popup.
"""


def register_deposit_finance_force(app):
    if getattr(app, "_titan_deposit_finance_force_registered", False):
        return
    app._titan_deposit_finance_force_registered = True

    from flask import request

    @app.after_request
    def titan_deposit_finance_force_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/deposit_professional"):
                return resp
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" not in ctype:
                return resp
            html = resp.get_data(as_text=True)
            if not html or "deposit-finance-force-v3" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            if idx >= 0:
                html = html[:idx] + FORCE_SCRIPT + html[idx:]
                resp.set_data(html)
                resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


FORCE_SCRIPT = r'''
<script id="deposit-finance-force-v3">
(function(){
  const API='/api/deposit_professional';
  let financeWanted=false;
  let lastLoad=0;

  function esc(v){return String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]||c));}
  function token(){try{return localStorage.getItem('TITAN_ADMIN_TOKEN')||''}catch(e){return ''}}
  async function jfetch(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});const t=token();if(t)opt.headers['X-Titan-Admin-Token']=t;const r=await fetch(url,opt);const j=await r.json().catch(()=>({status:'error',message:'Invalid JSON'}));if(!r.ok||j.status==='error')throw new Error(j.message||('HTTP '+r.status));return j;}
  function oldCleanup(){document.querySelectorAll('#titanDepositProfessionalShortcut').forEach(x=>x.remove());}

  function textOf(el){return ((el&&el.textContent)||'').replace(/\s+/g,' ').trim().toUpperCase();}
  function visible(el){try{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(el).display!=='none'&&getComputedStyle(el).visibility!=='hidden'}catch(e){return false}}
  function financeIsVisible(){
    if(financeWanted) return true;
    if(document.getElementById('payment-list')||document.getElementById('pay-submit-btn')||document.getElementById('pay-amount')) return true;
    const bodyTxt=textOf(document.body);
    return bodyTxt.includes('PAYMENT PROOF')||bodyTxt.includes('PAYMENT HISTORY')||bodyTxt.includes('WITHDRAWAL')||bodyTxt.includes('WALLET');
  }
  function markFinanceIfClick(ev){
    const path=[]; let n=ev.target; for(let i=0;n&&i<6;i++,n=n.parentElement) path.push(n);
    if(path.some(el=>textOf(el).includes('FINANCE'))){ financeWanted=true; setTimeout(ensurePanel,120); setTimeout(()=>loadDeposits(true),350); }
  }

  function findInsertRoot(){
    const financeAnchors=['payment-list','pay-submit-btn','pay-amount'].map(id=>document.getElementById(id)).filter(Boolean);
    if(financeAnchors.length){return financeAnchors[0].closest('.px-3')||financeAnchors[0].parentElement;}
    const candidates=[...document.querySelectorAll('main,#app,.app,.content,.pb-24,section,body')].filter(visible);
    // Prefer a large content container above bottom navigation.
    candidates.sort((a,b)=>{const ra=a.getBoundingClientRect(), rb=b.getBoundingClientRect(); return (rb.height*rb.width)-(ra.height*ra.width);});
    return candidates[0]||document.body;
  }

  function panelHtml(){return `
  <div id="titanFinanceDepositInline" style="margin:12px 12px 92px;position:relative;z-index:3">
    <div style="border:1px solid rgba(42,171,238,.32);background:rgba(16,29,47,.96);border-radius:18px;padding:14px;box-shadow:0 10px 26px rgba(0,0,0,.25);color:#eef6ff;font-family:Inter,Arial,sans-serif">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px">
        <div><div style="font-weight:900;font-size:13px;text-transform:uppercase">💰 Deposit</div><div style="font-size:10px;color:#91afd1;margin-top:3px">Finance tab me direct approve + wallet credit</div></div>
        <button id="depForceRefresh" style="border:0;background:#263b59;color:#fff;border-radius:11px;padding:9px 11px;font-weight:900;font-size:10px">Refresh</button>
      </div>
      <div id="depForceStats" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px"><div class="dfbox">-</div><div class="dfbox">-</div><div class="dfbox">-</div></div>
      <style>#titanFinanceDepositInline input,#titanFinanceDepositInline select{width:100%;background:#07111f;border:1px solid #243e5f;border-radius:12px;color:#eef6ff;padding:10px;font-size:12px;outline:none}#titanFinanceDepositInline .dfbox{background:#0b1727;border:1px solid #243e5f;border-radius:12px;padding:9px;font-size:10px;color:#91afd1}#titanFinanceDepositInline .dfbox b{display:block;color:#fff;font-size:14px;margin-top:2px}#titanFinanceDepositInline .dfbtn{border:0;border-radius:11px;padding:9px 10px;font-weight:900;font-size:10px;color:#fff}#titanFinanceDepositInline .dfcard{background:#0b1727;border:1px solid #243e5f;border-radius:14px;padding:10px;margin-top:8px}</style>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <input id="dfUpi" placeholder="UPI ID"><input id="dfQr" placeholder="QR URL">
        <input id="dfMin" type="number" placeholder="Min deposit"><input id="dfMax" type="number" placeholder="Max deposit">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <label class="dfbox" style="display:flex;align-items:center;justify-content:space-between">UTR <input id="dfReqUtr" type="checkbox" style="width:auto"></label>
        <label class="dfbox" style="display:flex;align-items:center;justify-content:space-between">Screenshot <input id="dfReqShot" type="checkbox" style="width:auto"></label>
      </div>
      <button id="dfSave" class="dfbtn" style="background:#2aabee;width:100%;margin-bottom:10px">Save Deposit Setup</button>
      <div class="dfcard">
        <div style="font-size:11px;font-weight:900;text-transform:uppercase;margin-bottom:8px">Manual Deposit</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input id="dfUser" placeholder="User/Profile ID"><input id="dfPhone" placeholder="Phone"><input id="dfName" placeholder="Name"><input id="dfAmount" type="number" placeholder="Amount"><input id="dfUtr" placeholder="UTR"><input id="dfProof" placeholder="Screenshot URL"></div>
        <button id="dfCreate" class="dfbtn" style="background:#00C26F;width:100%;margin-top:8px">Create Deposit</button>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px"><div style="font-size:11px;font-weight:900;text-transform:uppercase">Requests</div><select id="dfFilter" style="max-width:145px"><option value="">All</option><option value="payment_pending">Pending</option><option value="payment_submitted">Submitted</option><option value="under_verification">Verifying</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></div>
      <div id="dfList"></div><div id="dfMsg" style="font-size:10px;color:#91afd1;margin-top:10px"></div>
    </div>
  </div>`;}

  function ensurePanel(){
    oldCleanup();
    if(!financeIsVisible()) return false;
    if(document.getElementById('titanFinanceDepositInline')) return true;
    const root=findInsertRoot();
    if(!root) return false;
    if(root.id==='payment-list'||root.id==='pay-submit-btn'||root.id==='pay-amount') root.parentElement.insertAdjacentHTML('beforebegin',panelHtml());
    else if(root===document.body) document.body.insertAdjacentHTML('afterbegin',panelHtml());
    else root.insertAdjacentHTML('afterbegin',panelHtml());
    wire(); return true;
  }
  function msg(t){const e=document.getElementById('dfMsg');if(e)e.textContent=t||''}
  function fill(s){['Upi','Qr','Min','Max'].forEach(x=>{const map={Upi:'upiId',Qr:'qrImageUrl',Min:'minDeposit',Max:'maxDeposit'};const el=document.getElementById('df'+x);if(el)el.value=s?.[map[x]]??''});const a=document.getElementById('dfReqUtr');if(a)a.checked=!!s?.requireUtr;const b=document.getElementById('dfReqShot');if(b)b.checked=!!s?.requireScreenshot;}
  function statsHtml(s){return `<div class="dfbox">Pending<b>${esc(s.pendingCount||0)}</b></div><div class="dfbox">Pending ₹<b>₹${esc(s.pendingAmount||0)}</b></div><div class="dfbox">Total ₹<b>₹${esc(s.amount||0)}</b></div>`}
  function row(d){const p=d.professional||{},id=d.depositId||d.id||'',st=d.status||'';const pending=['payment_submitted','under_verification'].includes(st);return `<div class="dfcard"><div style="display:flex;justify-content:space-between;gap:8px"><div><b style="font-size:11px">${esc(id)}</b><div style="font-size:9px;color:#91afd1">${esc(d.customerName||d.userId||'Guest')} · ${esc(d.phoneNumber||'')}</div></div><span style="font-size:9px;color:#bfdbfe;font-weight:900">${esc(st)}</span></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px;font-size:10px;color:#91afd1"><div>Amount<br><b style="color:#fff">₹${esc(d.amount||0)}</b></div><div>UTR<br><b style="color:#fff">${esc(d.utr||'-')}</b></div><div>New<br><b style="color:#fff">₹${esc(p.newBalancePreview||0)}</b></div></div><div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:8px">${st==='payment_submitted'?`<button class="dfbtn dfAct" data-id="${esc(id)}" data-act="verify" style="background:#263b59">Verify</button>`:''}${pending?`<button class="dfbtn dfAct" data-id="${esc(id)}" data-act="approve" style="background:#00C26F;color:#062013">Approve + Credit</button>`:''}${['payment_pending','payment_submitted','under_verification'].includes(st)?`<button class="dfbtn dfAct" data-id="${esc(id)}" data-act="reject" style="background:#FF5D5D">Reject</button>`:''}</div></div>`;}
  async function loadDeposits(force=false){if(!ensurePanel())return;const now=Date.now();if(!force&&now-lastLoad<1400)return;lastLoad=now;try{const s=await jfetch(API+'/settings');fill(s.settings||{});const f=document.getElementById('dfFilter')?.value||'';const l=await jfetch(API+'/list?limit=20&status='+encodeURIComponent(f));const st=document.getElementById('depForceStats');if(st)st.innerHTML=statsHtml(l.stats||{});const list=document.getElementById('dfList');if(list)list.innerHTML=(l.deposits||[]).length?(l.deposits||[]).map(row).join(''):'<div style="font-size:10px;color:#91afd1;margin-top:10px">No deposits.</div>';msg('Finance deposit loaded ✅')}catch(e){msg('Deposit load failed: '+e.message)}}
  function wire(){const r=document.getElementById('depForceRefresh');if(r)r.onclick=()=>loadDeposits(true);const f=document.getElementById('dfFilter');if(f)f.onchange=()=>loadDeposits(true);const save=document.getElementById('dfSave');if(save)save.onclick=async()=>{try{await jfetch(API+'/settings',{method:'POST',body:JSON.stringify({upiId:document.getElementById('dfUpi')?.value||'',qrImageUrl:document.getElementById('dfQr')?.value||'',minDeposit:Number(document.getElementById('dfMin')?.value||0),maxDeposit:Number(document.getElementById('dfMax')?.value||0),requireUtr:!!document.getElementById('dfReqUtr')?.checked,requireScreenshot:!!document.getElementById('dfReqShot')?.checked})});msg('Deposit setup saved ✅');loadDeposits(true)}catch(e){msg('Save failed: '+e.message)}};const cr=document.getElementById('dfCreate');if(cr)cr.onclick=async()=>{try{await jfetch(API+'/create',{method:'POST',body:JSON.stringify({userId:document.getElementById('dfUser')?.value||'',profileId:document.getElementById('dfUser')?.value||'',phone:document.getElementById('dfPhone')?.value||'',customerName:document.getElementById('dfName')?.value||'',amount:Number(document.getElementById('dfAmount')?.value||0),utr:document.getElementById('dfUtr')?.value||'',proofUrl:document.getElementById('dfProof')?.value||''})});msg('Deposit created ✅');loadDeposits(true)}catch(e){msg('Create failed: '+e.message)}};const list=document.getElementById('dfList');if(list)list.addEventListener('click',async ev=>{const b=ev.target.closest('.dfAct');if(!b)return;const p={depositId:b.dataset.id,action:b.dataset.act,updatedBy:'finance_tab'};if(b.dataset.act==='reject')p.rejectReason=prompt('Reject reason?','UTR/proof not matched')||'';try{await jfetch(API+'/action',{method:'POST',body:JSON.stringify(p)});msg('Deposit '+b.dataset.act+' ✅');loadDeposits(true)}catch(e){msg('Action failed: '+e.message)}})}

  document.addEventListener('click',markFinanceIfClick,true);
  document.addEventListener('click',function(ev){if(ev.target && ev.target.closest('#titanFinanceDepositInline')) return; setTimeout(()=>{oldCleanup(); if(financeIsVisible()) loadDeposits(false);},220)},true);
  const obs=new MutationObserver(()=>{oldCleanup(); if(financeIsVisible()) loadDeposits(false);});
  obs.observe(document.documentElement,{childList:true,subtree:true});
  setTimeout(()=>{oldCleanup(); if(financeIsVisible()) loadDeposits(true);},500);
  setTimeout(()=>{oldCleanup(); if(financeIsVisible()) loadDeposits(true);},1800);
})();
</script>
'''
