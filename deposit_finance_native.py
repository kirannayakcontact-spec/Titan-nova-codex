"""Native Finance Deposit subtab injector.

Adds a Deposit subtab beside Finance summary/payment/withdrawal controls and shows
Deposit Desk inside Finance only. No popup and no other-tab injection.
"""


def register_deposit_finance_native(app):
    if getattr(app, "_titan_deposit_finance_native_registered", False):
        return
    app._titan_deposit_finance_native_registered = True

    from flask import request

    @app.after_request
    def titan_deposit_finance_native(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/deposit_professional"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "finance-deposit-native-v1" in html or "</body>" not in html.lower():
                return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + SCRIPT + html[i:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="finance-deposit-native-v1">
(function(){
  function q(s){return document.querySelector(s)}
  function qa(s){return Array.from(document.querySelectorAll(s))}
  function txt(e){return ((e&&e.textContent)||'').replace(/\s+/g,' ').trim().toUpperCase()}
  function getv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return ''}}
  function setv(n,v){try{Function('v',n+'=v')(v)}catch(e){}}
  function inFinance(){return String(getv('mainNav')||'').toLowerCase()==='finance'}
  function isDeposit(){return String(getv('financeSubTab')||'').toLowerCase()==='deposit'}
  function removePanel(){qa('#financeDepositNativePanel,#titanFinanceDepositInline,#titanFinanceDepositPanel,#titanDepositProfessionalShortcut').forEach(x=>x.remove())}
  function clickDeposit(){setv('mainNav','finance');setv('financeSubTab','deposit');try{if(typeof render==='function')render(false)}catch(e){}setTimeout(show,80)}
  function findFinanceTabs(){
    const buttons=qa('button,a,div');
    const hit=buttons.find(b=>{const t=txt(b);return t.includes('SUMMARY')&&t.includes('PAYMENT')}) || buttons.find(b=>txt(b).includes('WITHDRAWAL')&&txt(b).includes('PAYMENT'));
    if(hit) return hit;
    const pay=buttons.find(b=>txt(b)==='PAYMENT'||txt(b).includes('PAYMENT'));
    return pay ? (pay.parentElement||pay) : null;
  }
  function ensureButton(){
    if(!inFinance()) return;
    if(q('#financeDepositNativeBtn')) return;
    const wrap=findFinanceTabs(); if(!wrap) return;
    const btn=document.createElement('button');
    btn.id='financeDepositNativeBtn'; btn.type='button'; btn.textContent='DEPOSIT';
    btn.style.cssText='margin:4px;padding:10px 14px;border:0;border-radius:14px;background:#2aabee;color:white;font-weight:900;font-size:11px;letter-spacing:.04em';
    btn.onclick=clickDeposit;
    wrap.appendChild(btn);
  }
  function panelHtml(){return '<div id="financeDepositNativePanel" style="margin:12px;padding:0 0 92px"><div style="background:#101d2f;border:1px solid rgba(42,171,238,.32);border-radius:18px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.25)"><div style="display:flex;align-items:center;justify-content:space-between;padding:12px 14px;color:#eef6ff;font-family:Inter,Arial,sans-serif"><div><b>💰 Deposit</b><div style="font-size:10px;color:#91afd1">Finance → Deposit</div></div><button onclick="document.getElementById(\'financeDepositFrame\').contentWindow.location.reload()" style="border:0;border-radius:10px;background:#263b59;color:white;padding:8px 10px;font-weight:900">Refresh</button></div><iframe id="financeDepositFrame" src="/api/deposit_professional/admin_ui?embed=1" style="width:100%;height:760px;border:0;background:#07111f"></iframe></div></div>'}
  function root(){return q('main')||q('#app')||document.body}
  function show(){
    ensureButton();
    if(!inFinance()||!isDeposit()){ if(!inFinance()) removePanel(); return; }
    removePanel();
    const r=root(); if(r) r.insertAdjacentHTML('afterbegin',panelHtml());
  }
  document.addEventListener('click',function(ev){setTimeout(show,180)},true);
  const obs=new MutationObserver(function(){ensureButton(); if(!inFinance())removePanel();});
  obs.observe(document.documentElement,{childList:true,subtree:true});
  setInterval(show,1500); setTimeout(show,700);
})();
</script>
'''
