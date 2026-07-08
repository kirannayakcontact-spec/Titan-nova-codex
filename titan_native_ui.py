"""Titan Nova native-style UI shell.

Design-only enhancement. It does not remove or rewrite existing features.
Adds a mobile-native Home Control Center and visual polish while keeping old tabs,
buttons, routes, and data flow intact.
"""


def register_titan_native_ui(app):
    if getattr(app, "_titan_native_ui_registered", False):
        return
    app._titan_native_ui_registered = True

    from flask import request

    @app.after_request
    def titan_native_ui_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/") or request.path.startswith("/static/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-native-ui-shell-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + NATIVE_UI + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


NATIVE_UI = r'''
<style id="titan-native-ui-shell-v1-style">
:root{
  --tn-bg:#06151b;--tn-card:#122536;--tn-card2:#0d1e2b;--tn-line:rgba(146,197,255,.16);
  --tn-text:#f4fbff;--tn-muted:#8fb0ca;--tn-accent:#00c2a8;--tn-blue:#2aabee;--tn-warn:#f6c84c;
  --tn-danger:#ff5d5d;--tn-radius:22px;--tn-shadow:0 16px 42px rgba(0,0,0,.25)
}
html,body{background:radial-gradient(circle at 20% -10%,rgba(0,194,168,.18),transparent 32%),linear-gradient(180deg,#06151b,#07111f 55%,#050b12)!important;color:var(--tn-text)!important;scroll-behavior:smooth}
body{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif!important}
button,input,select,textarea{font-family:inherit!important}
button{touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.titan-native-card{background:linear-gradient(145deg,rgba(25,48,70,.92),rgba(12,27,40,.92));border:1px solid var(--tn-line);border-radius:var(--tn-radius);box-shadow:var(--tn-shadow);backdrop-filter:blur(10px)}
.titan-native-home{padding:14px 14px 110px;min-height:100vh;background:radial-gradient(circle at 100% 0,rgba(42,171,238,.16),transparent 28%)}
.titan-native-hero{padding:18px;margin:6px 0 14px;position:relative;overflow:hidden}
.titan-native-hero:before{content:"";position:absolute;right:-60px;top:-65px;width:170px;height:170px;background:radial-gradient(circle,rgba(0,194,168,.28),transparent 68%)}
.titan-native-title{font-size:22px;font-weight:1000;letter-spacing:.02em;margin:0;color:#fff}.titan-native-sub{font-size:11px;color:var(--tn-muted);line-height:1.45;margin-top:4px}.titan-native-live{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.titan-native-pill{font-size:9px;font-weight:1000;letter-spacing:.08em;border:1px solid rgba(0,194,168,.28);color:#bffdf2;background:rgba(0,194,168,.12);padding:6px 8px;border-radius:999px;text-transform:uppercase}.titan-native-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.titan-native-module{padding:14px;min-height:132px;display:flex;flex-direction:column;justify-content:space-between;cursor:pointer;transition:transform .12s ease,border-color .12s ease,background .12s ease}.titan-native-module:active{transform:scale(.985)}.titan-native-icon{font-size:23px;line-height:1}.titan-native-name{font-size:14px;font-weight:1000;margin-top:7px;color:#fff}.titan-native-desc{font-size:10px;color:var(--tn-muted);line-height:1.35;margin-top:3px}.titan-native-stats{display:flex;justify-content:space-between;gap:6px;align-items:center;margin-top:10px}.titan-native-open{font-size:9px;font-weight:1000;color:#062013;background:linear-gradient(135deg,#00c2a8,#75ffd8);border-radius:999px;padding:6px 9px}.titan-native-count{font-size:10px;color:#bfdbfe}.titan-native-section-title{font-size:12px;font-weight:1000;color:#9dc4df;letter-spacing:.16em;text-transform:uppercase;margin:18px 2px 10px}.titan-native-wide{grid-column:1/-1}.titan-native-quick{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.titan-native-quick button{border:1px solid var(--tn-line);background:rgba(18,37,54,.85);color:#d9f3ff;border-radius:16px;padding:11px 6px;font-size:10px;font-weight:900}.titan-native-bottom-home{position:fixed;left:8px;bottom:8px;z-index:9998;border:0;border-radius:18px;background:linear-gradient(135deg,#00c2a8,#2aabee);color:#021014;padding:10px 12px;font-weight:1000;font-size:11px;box-shadow:0 10px 26px rgba(0,0,0,.35)}
body.titan-native-mode .card,body.titan-native-mode .panel,body.titan-native-mode .box,body.titan-native-mode section{border-radius:18px!important}
body.titan-native-mode .bottom-nav,body.titan-native-mode nav{backdrop-filter:blur(16px)}
@media(max-width:380px){.titan-native-grid{gap:9px}.titan-native-module{min-height:122px;padding:12px}.titan-native-title{font-size:20px}}
</style>
<script id="titan-native-ui-shell-v1">
(function(){
  if(window.__TITAN_NATIVE_UI_SHELL__) return;
  window.__TITAN_NATIVE_UI_SHELL__=true;
  document.body.classList.add('titan-native-mode');
  const modules=[
    {key:'ledger',icon:'📒',name:'Ledger',desc:'Cards, pass/fail, T1/T2/T3, market ledger settings',stat:()=>ledgerStat()},
    {key:'finance',icon:'💰',name:'Finance',desc:'Wallet, deposit, withdrawal, payments',stat:()=>moneyStat()},
    {key:'results',icon:'🏆',name:'Results',desc:'Saved results, settlement, auto mark',stat:()=>resultStat()},
    {key:'entries',icon:'🧾',name:'Entries',desc:'Accepted entries, blocked entries, risk',stat:()=>entryStat()},
    {key:'vips',icon:'👥',name:'VIPs',desc:'Clients, access, approval, profiles',stat:()=>vipStat()},
    {key:'markets',icon:'🏪',name:'Markets',desc:'Market add/delete, timings, source URLs',stat:()=>marketStat()},
    {key:'forward',icon:'🔗',name:'Forward',desc:'WhatsApp schedule, targets, retry send',stat:()=>waStat()},
    {key:'guard',icon:'🛡️',name:'Guard',desc:'Link/forward/spam guard controls',stat:()=>guardStat()},
    {key:'backup',icon:'💾',name:'Backup',desc:'Download, restore, safety copies',stat:()=>genericStat('Safe')},
    {key:'audit',icon:'📜',name:'Audit',desc:'Logs, actions, diagnostics',stat:()=>genericStat('Logs')},
    {key:'setup',icon:'⚙️',name:'Advanced Setup',desc:'System config, tokens, developer tools',stat:()=>genericStat('Admin')}
  ];
  function getState(){try{return window.appState||appState||{}}catch(e){return {}}}
  function activeId(){const s=getState();return s.activeId||'admin1'}
  function today(){try{return window.currentDate||currentDate||new Date().toISOString().slice(0,10)}catch(e){return new Date().toISOString().slice(0,10)}}
  function countObj(o){return o&&typeof o==='object'?Object.keys(o).length:0}
  function ledgerStat(){const s=getState(),p=(s.profiles||{})[activeId()]||{},d=((p.dayRecords||{})[today()]||{});return countObj(d.data||{})+countObj(d.jodiData||{})+countObj(d.pannelData||{})+' cards'}
  function moneyStat(){const s=getState();const w=s.wallets||{};return countObj(w)+' wallets'}
  function resultStat(){const s=getState();const r=((s.resultRecords||{})[today()]||{});return countObj(r)+' results'}
  function entryStat(){const s=getState();const arr=Array.isArray(s.entries)?s.entries:[];return arr.length+' entries'}
  function vipStat(){const s=getState();return countObj(s.profiles||{})+' profiles'}
  function marketStat(){const s=getState();const m=s.marketRegistry||{};return countObj(m)+' markets'}
  function waStat(){const s=getState();const g=s.groups||s.whatsappGroups||[];return (Array.isArray(g)?g.length:countObj(g))+' targets'}
  function guardStat(){const s=getState();const en=(s.spamGuardSettings||{}).enabled;return en?'ON':'OFF'}
  function genericStat(t){return t}
  function setNav(key){
    removeHome();
    try{mainNav=key;if(typeof render==='function')render(true)}catch(e){}
    setTimeout(()=>{try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}},80);
  }
  function moduleCard(m){return `<div class="titan-native-module titan-native-card" data-native-open="${m.key}"><div><div class="titan-native-icon">${m.icon}</div><div class="titan-native-name">${m.name}</div><div class="titan-native-desc">${m.desc}</div></div><div class="titan-native-stats"><span class="titan-native-count">${safe(m.stat())}</span><span class="titan-native-open">OPEN</span></div></div>`}
  function safe(v){return String(v==null?'':v).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
  function homeHtml(){return `<div id="titanNativeHome" class="titan-native-home"><div class="titan-native-hero titan-native-card"><h1 class="titan-native-title">TITAN NOVA</h1><div class="titan-native-sub">Native Control Center · all modules same features · Firebase realtime</div><div class="titan-native-live"><span class="titan-native-pill">Firebase Live</span><span class="titan-native-pill">WhatsApp Gateway</span><span class="titan-native-pill">No Missing Features</span></div></div><div class="titan-native-section-title">Quick Controls</div><div class="titan-native-card titan-native-wide" style="padding:12px;margin-bottom:14px"><div class="titan-native-quick"><button data-native-open="ledger">Ledger</button><button data-native-open="finance">Finance</button><button data-native-open="results">Results</button><button data-native-open="markets">Markets</button></div></div><div class="titan-native-section-title">Modules</div><div class="titan-native-grid">${modules.map(moduleCard).join('')}</div></div>`}
  function root(){return document.querySelector('main')||document.querySelector('#app')||document.body}
  function showHome(){
    try{mainNav='home'}catch(e){}
    const old=document.getElementById('titanNativeHome'); if(old) old.remove();
    const r=root(); if(!r)return;
    r.insertAdjacentHTML('afterbegin',homeHtml());
    Array.from(document.body.children).forEach(ch=>{if(ch.id!=='titanNativeHome'&&ch.id!=='titanRealtimeStatusDot'&&ch.id!=='financeDepositNativePanel'&&ch.id!=='titanNativeHomeBtn'&&ch.tagName!=='SCRIPT'&&ch.tagName!=='STYLE'){try{ch.classList.add('titan-native-hidden-by-home')}catch(e){}}});
    let st=document.getElementById('titanNativeHideStyle'); if(!st){st=document.createElement('style');st.id='titanNativeHideStyle';st.textContent='.titan-native-hidden-by-home{display:none!important} #titanNativeHome{display:block!important}';document.head.appendChild(st)}
  }
  function removeHome(){
    const h=document.getElementById('titanNativeHome'); if(h)h.remove();
    document.querySelectorAll('.titan-native-hidden-by-home').forEach(x=>x.classList.remove('titan-native-hidden-by-home'));
    const st=document.getElementById('titanNativeHideStyle'); if(st)st.remove();
  }
  function addHomeButton(){
    if(document.getElementById('titanNativeHomeBtn'))return;
    const b=document.createElement('button');b.id='titanNativeHomeBtn';b.className='titan-native-bottom-home';b.textContent='⌂ HOME';b.onclick=showHome;document.body.appendChild(b);
  }
  document.addEventListener('click',function(ev){const n=ev.target.closest&&ev.target.closest('[data-native-open]');if(!n)return;const key=n.getAttribute('data-native-open');if(key)setNav(key)},true);
  addHomeButton();
  setTimeout(()=>{try{if(!mainNav||mainNav==='home')showHome()}catch(e){showHome()}},700);
  window.TitanNativeUI={home:showHome,open:setNav,removeHome};
})();
</script>
'''
