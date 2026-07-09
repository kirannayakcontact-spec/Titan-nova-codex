"""Remove Finance Deposit tab and Deposit Professional endpoints.

Removal-only guard. Does not create a replacement feature.
"""


def register_finance_deposit_removed(app):
    if getattr(app, "_finance_deposit_removed_registered", False):
        return
    app._finance_deposit_removed_registered = True

    from flask import jsonify, request

    @app.before_request
    def finance_deposit_backend_removed():
        try:
            path = (request.path or "").lower().rstrip("/")
            if path.startswith("/api/deposit_professional") or path.startswith("/deposit_professional"):
                return jsonify({
                    "status": "disabled",
                    "feature": "finance_deposit_removed",
                    "message": "Finance Deposit feature has been removed.",
                }), 410
        except Exception:
            return None
        return None

    @app.after_request
    def finance_deposit_frontend_removed(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "finance-deposit-removed-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<style id="finance-deposit-removed-v1-style">
  #financeDepositNativeBtn,
  #financeDepositNativePanel,
  #titanFinanceDepositInline,
  #titanFinanceDepositPanel,
  #titanDepositProfessionalShortcut,
  iframe[src*="deposit_professional"],
  a[href*="deposit_professional"],
  button[onclick*="deposit"],
  a[onclick*="deposit"] { display:none !important; visibility:hidden !important; }
</style>
<script id="finance-deposit-removed-v1">
(function(){
  if(window.__FINANCE_DEPOSIT_REMOVED_V1__) return;
  window.__FINANCE_DEPOSIT_REMOVED_V1__ = true;

  function gv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return ''}}
  function sv(n,v){try{Function('v',n+'=v')(v)}catch(e){try{window[n]=v}catch(_){}}}
  function txt(el){return String((el&&el.textContent)||'').replace(/\s+/g,' ').trim().toUpperCase()}
  function qa(s){return Array.from(document.querySelectorAll(s))}
  function inFinance(){return String(gv('mainNav')||'').toLowerCase()==='finance'}
  function isDepositSub(){return String(gv('financeSubTab')||'').toLowerCase()==='deposit'}
  function hide(el){try{el.style.setProperty('display','none','important');el.style.setProperty('visibility','hidden','important');el.setAttribute('aria-hidden','true');el.setAttribute('data-finance-deposit-removed','1')}catch(e){}}
  function looksDeposit(el){
    if(!el) return false;
    const t=txt(el);
    const a=String((el.getAttribute&&(el.getAttribute('onclick')||el.getAttribute('href')||el.id||el.className||el.dataset?.tab||el.dataset?.nav))||'').toLowerCase();
    if(a.includes('deposit')||a.includes('deposit_professional')) return true;
    if(t==='DEPOSIT'||t.includes('DEPOSIT REVIEW')||t.includes('PROFESSIONAL DEPOSIT')) return true;
    return false;
  }
  function clean(){
    qa('#financeDepositNativeBtn,#financeDepositNativePanel,#titanFinanceDepositInline,#titanFinanceDepositPanel,#titanDepositProfessionalShortcut,iframe[src*="deposit_professional"],a[href*="deposit_professional"]').forEach(hide);
    if(inFinance()){
      qa('button,a,div,span,[onclick],[href],[data-tab],[data-nav]').forEach(function(el){ if(looksDeposit(el)) hide(el); });
      if(isDepositSub()){
        sv('financeSubTab','summary');
        try{ if(typeof render==='function') render(false); }catch(e){}
      }
    }
  }
  document.addEventListener('click',function(ev){
    const el=ev.target&&ev.target.closest?ev.target.closest('button,a,[onclick],[href],[data-tab],[data-nav]'):null;
    if(inFinance()&&looksDeposit(el)){
      ev.preventDefault(); ev.stopPropagation();
      sv('financeSubTab','summary');
      try{ if(typeof render==='function') render(false); }catch(e){}
      setTimeout(clean,40);
      return false;
    }
  },true);
  const obs=new MutationObserver(clean);
  try{obs.observe(document.documentElement,{childList:true,subtree:true})}catch(e){}
  setInterval(clean,700); setTimeout(clean,80); setTimeout(clean,500);
})();
</script>
'''
