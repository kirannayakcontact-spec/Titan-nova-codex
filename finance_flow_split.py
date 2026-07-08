"""Finance flow split guard.

User-facing Finance rules:
- Payment label is renamed to Deposit.
- Existing payment request data remains the Deposit source of truth.
- Withdrawal request management stays under Withdrawal.
- Deposit request management stays under Deposit/old internal payment subtab.
- Removed Deposit Professional feature is not restored.

v2: label-safe only. It does not hide action cards/rows, so pending actions cannot disappear.
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
            "version": "v2-label-safe-no-action-hide",
            "paymentLabel": "Deposit",
            "depositSource": "existing payment request records",
            "withdrawalSource": "withdrawal request records",
            "rules": {
                "depositRequests": "Deposit tab only / internal payment subtab",
                "withdrawalRequests": "Withdrawal tab only",
                "paymentLabelVisible": False,
                "depositProfessionalRestored": False,
                "hideActionRows": False,
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
            if not html or "finance-flow-split-v2-label-safe" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="finance-flow-split-v2-label-safe">
(function(){
  if(window.__FINANCE_FLOW_SPLIT_V2__) return;
  window.__FINANCE_FLOW_SPLIT_V2__ = true;
  function gv(n){ try { return Function('return typeof '+n+'!=="undefined"?'+n+':""')(); } catch(e) { return ''; } }
  function sv(n,v){ try { Function('v', n+'=v')(v); } catch(e) { try { window[n]=v; } catch(_){} } }
  function nav(){ return String(gv('mainNav') || '').toLowerCase(); }
  function isFinance(){ return nav() === 'finance'; }
  function text(el){ return String((el && el.textContent) || '').replace(/\s+/g,' ').trim(); }
  function qa(sel){ return Array.from(document.querySelectorAll(sel)); }

  function patchFinanceSubTab(){
    try{
      const old = Function('return typeof setFinanceSubTab==="function"?setFinanceSubTab:null')();
      if(old && !old.__financeFlowSplitV2){
        const next = function(tab){
          let t = String(tab || '').toLowerCase();
          if(t === 'deposit' || t === 'deposits') tab = 'payment';
          return old.call(this, tab);
        };
        next.__financeFlowSplitV2 = true;
        sv('setFinanceSubTab', next);
        try { window.setFinanceSubTab = next; } catch(e) {}
      }
    }catch(e){}
  }

  function renamePaymentToDeposit(){
    if(!isFinance()) return;
    qa('button,a,span,div,p,h1,h2,h3,h4,label,th,td').forEach(function(el){
      if(!el || el.children.length > 1) return;
      const t = text(el);
      if(!t) return;
      const u = t.toUpperCase();
      const map = {
        'PAYMENT':'DEPOSIT',
        'PAYMENTS':'DEPOSITS',
        'PAYMENT REQUEST':'DEPOSIT REQUEST',
        'PAYMENT REQUESTS':'DEPOSIT REQUESTS',
        'PENDING PAYMENTS':'PENDING DEPOSITS',
        'APPROVED PAYMENTS':'APPROVED DEPOSITS',
        'REJECTED PAYMENTS':'REJECTED DEPOSITS',
        'PAYMENT SETTINGS':'DEPOSIT SETTINGS',
        'PAYMENT METHODS':'DEPOSIT METHODS',
        'SUBMIT PAYMENT':'SUBMIT DEPOSIT',
        'PAY NOW':'DEPOSIT NOW'
      };
      if(map[u]) el.textContent = map[u];
    });
  }

  function clean(){
    patchFinanceSubTab();
    const s = String(gv('financeSubTab') || '').toLowerCase();
    if(s === 'deposit' || s === 'deposits') sv('financeSubTab','payment');
    renamePaymentToDeposit();
  }

  const obs = new MutationObserver(clean);
  try { obs.observe(document.documentElement, {childList:true, subtree:true, characterData:true}); } catch(e) {}
  document.addEventListener('DOMContentLoaded', clean);
  window.addEventListener('load', clean);
  document.addEventListener('titan:realtime-applied', clean);
  setInterval(clean, 900);
  setTimeout(clean, 100);
  setTimeout(clean, 700);
})();
</script>
'''
