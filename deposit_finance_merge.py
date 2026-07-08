"""Merge professional deposit controls into the existing Finance/Payment tab.

This removes the temporary floating Deposit Desk shortcut and injects a compact
inline deposit verification panel into the existing Finance payment area.
"""


def register_deposit_finance_merge(app):
    if getattr(app, "_titan_deposit_finance_merge_registered", False):
        return
    app._titan_deposit_finance_merge_registered = True

    # Remove the earlier floating/shortcut after_request from deposit_professional_v2.
    try:
        funcs = app.after_request_funcs.get(None, [])
        app.after_request_funcs[None] = [
            fn for fn in funcs
            if getattr(fn, "__name__", "") != "deposit_professional_existing_tab_shortcut"
        ]
    except Exception:
        pass

    from flask import request

    @app.after_request
    def titan_deposit_finance_merge_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" not in content_type:
                return resp
            if request.path.startswith("/api/deposit_professional"):
                return resp
            html = resp.get_data(as_text=True)
            if not html or "deposit-finance-merge-v2" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            if idx >= 0:
                html = html[:idx] + FINANCE_MERGE_SCRIPT + html[idx:]
                resp.set_data(html)
                resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


FINANCE_MERGE_SCRIPT = r'''
<script id="deposit-finance-merge-v2">
(function(){
  const API = '/api/deposit_professional';
  let lastLoadAt = 0;

  function esc(v){
    return String(v ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c] || c));
  }
  function token(){
    try { return localStorage.getItem('TITAN_ADMIN_TOKEN') || ''; } catch(e){ return ''; }
  }
  async function jfetch(url, opt={}){
    opt.headers = Object.assign({'Content-Type':'application/json'}, opt.headers || {});
    const t = token();
    if(t) opt.headers['X-Titan-Admin-Token'] = t;
    const r = await fetch(url, opt);
    const j = await r.json().catch(() => ({status:'error', message:'Invalid JSON'}));
    if(!r.ok || j.status === 'error') throw new Error(j.message || ('HTTP '+r.status));
    return j;
  }

  function removeOldShortcut(){
    const old = document.getElementById('titanDepositProfessionalShortcut');
    if(old) old.remove();
  }

  function findFinancePaymentAnchor(){
    // Best anchor: existing Finance > Payment proof/history DOM.
    const paymentList = document.getElementById('payment-list');
    if(paymentList) return paymentList.closest('.px-3') || paymentList.parentElement;
    const paySubmit = document.getElementById('pay-submit-btn');
    if(paySubmit) return paySubmit.closest('.px-3') || paySubmit.parentElement;
    const payAmount = document.getElementById('pay-amount');
    if(payAmount) return payAmount.closest('.px-3') || payAmount.parentElement;
    // Do not fallback to fixed popup. If Finance payment UI is not present yet, wait.
    return null;
  }

  function panelHtml(){
    return `
      <div id="titanFinanceDepositPanel" class="px-3 mb-3">
        <p class="sec-header">Deposit Verification</p>
        <div class="native-card p-3 border border-[rgba(42,171,238,.25)]">
          <div class="flex items-center justify-between gap-2 mb-3">
            <div>
              <p class="text-white font-black text-[12px] uppercase">Professional Deposit</p>
              <p class="text-[var(--text-muted)] text-[9px]">UTR guard, proof check, approve + wallet credit</p>
            </div>
            <button id="titanDepRefresh" class="bg-[var(--surface-light)] text-white px-3 py-2 rounded-xl font-black text-[9px] uppercase border border-[var(--border)]">Refresh</button>
          </div>

          <div id="titanDepStats" class="grid grid-cols-3 gap-2 mb-3">
            <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Pending</p><p class="text-white font-black text-sm">-</p></div>
            <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Pending ₹</p><p class="text-white font-black text-sm">-</p></div>
            <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Total ₹</p><p class="text-white font-black text-sm">-</p></div>
          </div>

          <div class="grid grid-cols-2 gap-2 mb-3">
            <input id="titanDepUpi" class="native-input text-[11px]" placeholder="UPI ID">
            <input id="titanDepQr" class="native-input text-[11px]" placeholder="QR image URL">
            <input id="titanDepMin" class="native-input text-[11px]" type="number" placeholder="Min deposit">
            <input id="titanDepMax" class="native-input text-[11px]" type="number" placeholder="Max deposit">
          </div>
          <div class="grid grid-cols-2 gap-2 mb-3">
            <label class="flex items-center justify-between gap-2 bg-[#17212B] border border-[var(--border)] rounded-xl px-3 py-2 text-[9px] text-[var(--text-muted)] font-bold"><span>UTR Required</span><input id="titanDepRequireUtr" type="checkbox"></label>
            <label class="flex items-center justify-between gap-2 bg-[#17212B] border border-[var(--border)] rounded-xl px-3 py-2 text-[9px] text-[var(--text-muted)] font-bold"><span>Screenshot</span><input id="titanDepRequireShot" type="checkbox"></label>
          </div>
          <button id="titanDepSaveSettings" class="w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">Save Deposit Setup</button>

          <div class="mt-4 bg-[#17212B] rounded-2xl p-3 border border-[var(--border)]">
            <p class="text-white font-black text-[11px] uppercase mb-2">Manual Deposit Entry</p>
            <div class="grid grid-cols-2 gap-2">
              <input id="titanDepUser" class="native-input text-[11px]" placeholder="User/Profile ID">
              <input id="titanDepPhone" class="native-input text-[11px]" placeholder="Phone">
              <input id="titanDepName" class="native-input text-[11px]" placeholder="Name">
              <input id="titanDepAmount" class="native-input text-[11px]" type="number" placeholder="Amount">
            </div>
            <div class="grid grid-cols-2 gap-2 mt-2">
              <input id="titanDepUtr" class="native-input text-[11px]" placeholder="UTR">
              <input id="titanDepProof" class="native-input text-[11px]" placeholder="Screenshot URL">
            </div>
            <button id="titanDepCreate" class="w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase mt-2 active:scale-95">Create Deposit</button>
          </div>

          <div class="flex items-center justify-between gap-2 mt-4 mb-2">
            <p class="text-white font-black text-[11px] uppercase">Latest Deposit Requests</p>
            <select id="titanDepFilter" class="native-input text-[10px] max-w-[160px]">
              <option value="">All</option>
              <option value="payment_pending">Pending</option>
              <option value="payment_submitted">Submitted</option>
              <option value="under_verification">Verifying</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div id="titanDepList" class="space-y-2"><p class="text-[10px] text-[var(--text-muted)]">Loading...</p></div>
          <p id="titanDepMsg" class="text-[10px] text-[var(--text-muted)] mt-3"></p>
        </div>
      </div>`;
  }

  function ensurePanel(){
    removeOldShortcut();
    const anchor = findFinancePaymentAnchor();
    if(!anchor) return false;
    let panel = document.getElementById('titanFinanceDepositPanel');
    if(!panel){
      anchor.insertAdjacentHTML('beforebegin', panelHtml());
      wirePanel();
    }
    return true;
  }

  function msg(t){ const el=document.getElementById('titanDepMsg'); if(el) el.textContent=t || ''; }
  function fillSettings(s){
    const map = {titanDepUpi:'upiId', titanDepQr:'qrImageUrl', titanDepMin:'minDeposit', titanDepMax:'maxDeposit'};
    Object.keys(map).forEach(id => { const el=document.getElementById(id); if(el) el.value = s && s[map[id]] != null ? s[map[id]] : ''; });
    const utr=document.getElementById('titanDepRequireUtr'); if(utr) utr.checked = !!(s && s.requireUtr);
    const shot=document.getElementById('titanDepRequireShot'); if(shot) shot.checked = !!(s && s.requireScreenshot);
  }
  function renderStats(s){
    const box=document.getElementById('titanDepStats'); if(!box) return;
    box.innerHTML = `<div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Pending</p><p class="text-white font-black text-sm">${esc(s.pendingCount||0)}</p></div><div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Pending ₹</p><p class="text-white font-black text-sm">₹${esc(s.pendingAmount||0)}</p></div><div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><p class="stat-lbl">Total ₹</p><p class="text-white font-black text-sm">₹${esc(s.amount||0)}</p></div>`;
  }
  function itemHtml(d){
    const p=d.professional||{}; const id=d.depositId||d.id||''; const st=d.status||'';
    const canApprove = ['payment_submitted','under_verification'].includes(st);
    const canVerify = st === 'payment_submitted';
    const canReject = ['payment_submitted','under_verification','payment_pending'].includes(st);
    return `<div class="bg-[#17212B] border border-[var(--border)] rounded-2xl p-3">
      <div class="flex items-start justify-between gap-2"><div class="min-w-0"><p class="text-white font-black text-[11px] truncate">${esc(id)}</p><p class="text-[var(--text-muted)] text-[9px] truncate">${esc(d.customerName||d.userId||'Guest')} · ${esc(d.phoneNumber||'')}</p></div><span class="text-[9px] font-black px-2 py-1 rounded-full ${st==='approved'?'bg-[rgba(34,197,94,.18)] text-[#a7f3d0]':st==='rejected'?'bg-[rgba(255,77,109,.18)] text-[#ffc2cc]':'bg-[rgba(42,171,238,.18)] text-[#bfdbfe]'}">${esc(st||'-')}</span></div>
      <div class="grid grid-cols-3 gap-2 mt-2 text-[10px]"><div><p class="stat-lbl">Amount</p><b class="text-white">₹${esc(d.amount||0)}</b></div><div><p class="stat-lbl">UTR</p><b class="text-white truncate block">${esc(d.utr||'-')}</b></div><div><p class="stat-lbl">New Bal</p><b class="text-white">₹${esc(p.newBalancePreview||0)}</b></div></div>
      <div class="flex gap-2 flex-wrap mt-2">${canVerify?`<button class="dep-act bg-[var(--surface-light)] text-white px-3 py-2 rounded-lg font-black text-[9px]" data-id="${esc(id)}" data-act="verify">Verify</button>`:''}${canApprove?`<button class="dep-act bg-[var(--green)] text-white px-3 py-2 rounded-lg font-black text-[9px]" data-id="${esc(id)}" data-act="approve">Approve + Credit</button>`:''}${canReject?`<button class="dep-act bg-[#FF5D5D] text-white px-3 py-2 rounded-lg font-black text-[9px]" data-id="${esc(id)}" data-act="reject">Reject</button>`:''}</div>
    </div>`;
  }

  async function loadFinanceDeposits(force=false){
    if(!ensurePanel()) return;
    const now = Date.now();
    if(!force && now - lastLoadAt < 1200) return;
    lastLoadAt = now;
    try{
      const settingsRes = await jfetch(API + '/settings');
      fillSettings(settingsRes.settings || {});
      const filter = document.getElementById('titanDepFilter')?.value || '';
      const listRes = await jfetch(API + '/list?limit=20&status=' + encodeURIComponent(filter));
      renderStats(listRes.stats || {});
      const list = document.getElementById('titanDepList');
      if(list) list.innerHTML = (listRes.deposits || []).length ? (listRes.deposits || []).map(itemHtml).join('') : '<p class="text-[10px] text-[var(--text-muted)]">No deposit requests.</p>';
      msg('Deposit panel synced ✅');
    }catch(e){ msg('Deposit load failed: ' + e.message); }
  }

  function wirePanel(){
    const refresh=document.getElementById('titanDepRefresh'); if(refresh) refresh.onclick=()=>loadFinanceDeposits(true);
    const filter=document.getElementById('titanDepFilter'); if(filter) filter.onchange=()=>loadFinanceDeposits(true);
    const save=document.getElementById('titanDepSaveSettings'); if(save) save.onclick=async()=>{
      try{
        const payload={upiId:document.getElementById('titanDepUpi')?.value||'',qrImageUrl:document.getElementById('titanDepQr')?.value||'',minDeposit:Number(document.getElementById('titanDepMin')?.value||0),maxDeposit:Number(document.getElementById('titanDepMax')?.value||0),requireUtr:!!document.getElementById('titanDepRequireUtr')?.checked,requireScreenshot:!!document.getElementById('titanDepRequireShot')?.checked};
        await jfetch(API+'/settings',{method:'POST',body:JSON.stringify(payload)}); msg('Deposit setup saved ✅'); loadFinanceDeposits(true);
      }catch(e){ msg('Save failed: '+e.message); }
    };
    const create=document.getElementById('titanDepCreate'); if(create) create.onclick=async()=>{
      try{
        const payload={userId:document.getElementById('titanDepUser')?.value||'',profileId:document.getElementById('titanDepUser')?.value||'',phone:document.getElementById('titanDepPhone')?.value||'',customerName:document.getElementById('titanDepName')?.value||'',amount:Number(document.getElementById('titanDepAmount')?.value||0),utr:document.getElementById('titanDepUtr')?.value||'',proofUrl:document.getElementById('titanDepProof')?.value||''};
        await jfetch(API+'/create',{method:'POST',body:JSON.stringify(payload)}); msg('Deposit created ✅'); loadFinanceDeposits(true);
      }catch(e){ msg('Create failed: '+e.message); }
    };
    const list=document.getElementById('titanDepList'); if(list) list.addEventListener('click', async ev=>{
      const btn=ev.target.closest('.dep-act'); if(!btn) return;
      const payload={depositId:btn.dataset.id,action:btn.dataset.act,updatedBy:'finance_tab'};
      if(btn.dataset.act==='reject') payload.rejectReason=prompt('Reject reason?','UTR/proof not matched')||'';
      try{ await jfetch(API+'/action',{method:'POST',body:JSON.stringify(payload)}); msg('Deposit '+btn.dataset.act+' ✅'); loadFinanceDeposits(true); }
      catch(e){ msg('Action failed: '+e.message); }
    });
  }

  function tick(){ removeOldShortcut(); if(ensurePanel()) loadFinanceDeposits(false); }
  document.addEventListener('click', function(ev){
    const txt = (ev.target && ev.target.textContent || '').trim().toLowerCase();
    if(txt.includes('finance') || txt.includes('pay') || txt.includes('payment')) setTimeout(tick, 250);
  }, true);
  const obs = new MutationObserver(() => tick());
  obs.observe(document.documentElement, {childList:true, subtree:true});
  setTimeout(tick, 300); setTimeout(tick, 1200); setInterval(tick, 5000);
})();
</script>
'''
