"""Finance flow split guard.

User-facing Finance rules:
- Payment label is renamed to Deposit.
- Existing payment request data remains the Deposit source of truth.
- Withdrawal request management stays only under Withdrawal.
- Deposit request management stays only under Deposit.
- Removed Deposit Professional feature is not restored.
"""


def register_finance_flow_split(app):
    if getattr(app, "_finance_flow_split_registered", False):
        return
    app._finance_flow_split_registered = True

    from flask import jsonify, request

    @app.route("/api/finance_flow_split_status", methods=["GET"])
    def finance_flow_split_status():
        return jsonify({
            "status": "success",
            "financeFlowSplit": True,
            "paymentLabel": "Deposit",
            "depositSource": "existing payment request records",
            "withdrawalSource": "withdrawal request records",
            "rules": {
                "depositRequests": "Deposit tab only",
                "withdrawalRequests": "Withdrawal tab only",
                "paymentLabelVisible": False,
                "depositProfessionalRestored": False,
            },
        })

    @app.after_request
    def finance_flow_split_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "finance-flow-split-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<style id="finance-flow-split-v1-style">
  [data-finance-flow-hidden="1"] { display:none !important; visibility:hidden !important; }
</style>
<script id="finance-flow-split-v1">
(function(){
  if(window.__FINANCE_FLOW_SPLIT_V1__) return;
  window.__FINANCE_FLOW_SPLIT_V1__ = true;

  function gv(n){ try { return Function('return typeof '+n+'!=="undefined"?'+n+':""')(); } catch(e) { return ''; } }
  function sv(n,v){ try { Function('v', n+'=v')(v); } catch(e) { try { window[n]=v; } catch(_){} } }
  function nav(){ return String(gv('mainNav') || '').toLowerCase(); }
  function sub(){ return String(gv('financeSubTab') || '').toLowerCase(); }
  function text(el){ return String((el && el.textContent) || '').replace(/\s+/g,' ').trim(); }
  function upper(el){ return text(el).toUpperCase(); }
  function qa(sel){ return Array.from(document.querySelectorAll(sel)); }
  function isFinance(){ return nav() === 'finance'; }
  function isDepositSub(){ const s=sub(); return s === 'payment' || s === 'payments' || s === 'deposit' || s === 'deposits'; }
  function isWithdrawalSub(){ const s=sub(); return s === 'withdrawal' || s === 'withdrawals'; }
  function isWalletSub(){ const s=sub(); return s === 'wallet' || s === 'wallets'; }

  function renamePaymentToDeposit(){
    if(!isFinance()) return;
    qa('button,a,span,div,p,h1,h2,h3,h4,label').forEach(function(el){
      if(!el || el.children.length > 2) return;
      const t = text(el);
      if(!t) return;
      const u = t.toUpperCase();
      if(u === 'PAYMENT') el.textContent = 'DEPOSIT';
      else if(u === 'PAYMENTS') el.textContent = 'DEPOSITS';
      else if(u === 'PAYMENT REQUESTS') el.textContent = 'DEPOSIT REQUESTS';
      else if(u === 'PENDING PAYMENTS') el.textContent = 'PENDING DEPOSITS';
      else if(u === 'APPROVED PAYMENTS') el.textContent = 'APPROVED DEPOSITS';
      else if(u === 'PAYMENT SETTINGS') el.textContent = 'DEPOSIT SETTINGS';
      else if(u === 'PAYMENT METHODS') el.textContent = 'DEPOSIT METHODS';
      else if(u === 'SUBMIT PAYMENT') el.textContent = 'SUBMIT DEPOSIT';
    });
  }

  function patchFinanceSubTab(){
    try{
      const old = Function('return typeof setFinanceSubTab==="function"?setFinanceSubTab:null')();
      if(old && !old.__financeFlowSplit){
        const next = function(tab){
          let t = String(tab || '').toLowerCase();
          if(t === 'payment' || t === 'payments') tab = 'payment';
          if(t === 'deposit' || t === 'deposits') tab = 'payment';
          return old.call(this, tab);
        };
        next.__financeFlowSplit = true;
        sv('setFinanceSubTab', next);
        try { window.setFinanceSubTab = next; } catch(e) {}
      }
    }catch(e){}
  }

  function nodeKind(el){
    const t = upper(el);
    const a = String((el.getAttribute && (el.getAttribute('onclick') || el.getAttribute('href') || el.id || el.className || el.dataset?.tab || el.dataset?.nav)) || '').toLowerCase();
    const isWithdrawal = /withdraw|withdrawal/.test(a) || t.includes('WITHDRAW') || t.includes('WITHDRAWAL');
    const isDeposit = /payment|deposit/.test(a) || t.includes('PAYMENT') || t.includes('DEPOSIT') || t.includes('UTR') || t.includes('UPI');
    return {isWithdrawal, isDeposit};
  }

  function splitVisibleControls(){
    if(!isFinance()) return;
    const dep = isDepositSub();
    const wd = isWithdrawalSub();
    qa('[data-finance-flow-hidden="1"]').forEach(function(el){
      try { el.style.removeProperty('display'); el.style.removeProperty('visibility'); el.removeAttribute('data-finance-flow-hidden'); } catch(e) {}
    });
    // Only hide obvious cross-flow cards/rows. Do not touch Wallet summary rows.
    qa('.native-card, .card, section, article, tr, li, [class*="card"], [id]').forEach(function(el){
      if(!el || el === document.body || el.children.length > 80) return;
      const k = nodeKind(el);
      if(dep && k.isWithdrawal && !k.isDeposit){
        try { el.setAttribute('data-finance-flow-hidden','1'); el.style.setProperty('display','none','important'); } catch(e) {}
      }
      if(wd && k.isDeposit && !k.isWithdrawal){
        try { el.setAttribute('data-finance-flow-hidden','1'); el.style.setProperty('display','none','important'); } catch(e) {}
      }
    });
  }

  function patchClicks(){
    document.addEventListener('click', function(ev){
      if(!isFinance()) return;
      const el = ev.target && ev.target.closest ? ev.target.closest('button,a,[onclick],[data-tab],[data-nav]') : null;
      if(!el) return;
      const u = upper(el);
      const attr = String((el.getAttribute('onclick') || el.getAttribute('href') || el.dataset?.tab || '')).toLowerCase();
      if(u === 'DEPOSIT' || u === 'PAYMENT' || attr.includes('payment') || attr.includes('deposit')){
        if(attr.includes('withdraw')) return;
        // Existing internal subtab remains payment; visible name is Deposit.
        setTimeout(function(){ sv('financeSubTab','payment'); clean(); }, 0);
      }
    }, true);
  }

  function clean(){
    patchFinanceSubTab();
    if(isFinance()){
      if(sub() === 'deposit' || sub() === 'deposits') sv('financeSubTab','payment');
      renamePaymentToDeposit();
      splitVisibleControls();
    }
  }

  patchClicks();
  const obs = new MutationObserver(clean);
  try { obs.observe(document.documentElement, {childList:true, subtree:true, characterData:true}); } catch(e) {}
  document.addEventListener('DOMContentLoaded', clean);
  window.addEventListener('load', clean);
  document.addEventListener('titan:realtime-applied', clean);
  setInterval(clean, 800);
  setTimeout(clean, 100);
  setTimeout(clean, 600);
})();
</script>
'''
