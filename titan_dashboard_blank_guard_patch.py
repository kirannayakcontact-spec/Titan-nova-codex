"""Dashboard blank screen recovery guard.

This patch is intentionally UI-only. It does not change ledger/result/wallet logic.
It adds a small emergency overlay when the browser loads the page but the main
Titan UI stays blank because of localStorage corruption, a render exception, or
an injected UI script failing during boot.
"""


def register_titan_dashboard_blank_guard(app):
    if getattr(app, "_titan_dashboard_blank_guard_registered", False):
        return
    app._titan_dashboard_blank_guard_registered = True

    from flask import request

    VERSION = "2026-07-10-dashboard-blank-guard-v1"

    @app.after_request
    def dashboard_blank_guard_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-dashboard-blank-guard-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan dashboard blank guard loaded", VERSION)


SCRIPT = r'''
<script id="titan-dashboard-blank-guard-v1">
(function(){
  if(window.__TITAN_DASHBOARD_BLANK_GUARD_V1__) return;
  window.__TITAN_DASHBOARD_BLANK_GUARD_V1__ = true;
  const VERSION='2026-07-10-dashboard-blank-guard-v1';
  const errors=[];
  function pushErr(kind,msg,src){
    try{
      const item={at:new Date().toISOString(),kind:String(kind||'error'),message:String(msg||'').slice(0,800),source:String(src||'browser').slice(0,200)};
      errors.push(item);
      const old=JSON.parse(localStorage.getItem('titan.dashboard.boot.errors.v1')||'[]');
      old.push(Object.assign({version:VERSION},item));
      localStorage.setItem('titan.dashboard.boot.errors.v1',JSON.stringify(old.slice(-40)));
    }catch(_){ }
  }
  window.addEventListener('error',e=>pushErr('error',e.message||'Script error',e.filename||''),true);
  window.addEventListener('unhandledrejection',e=>pushErr('promise',(e.reason&&e.reason.message)||e.reason||'Promise rejection','promise'),true);

  function css(el,txt){try{el.style.cssText=txt}catch(_){}}
  function textLen(){try{return String(document.body&&document.body.innerText||'').replace(/\s+/g,' ').trim().length}catch(_){return 0}}
  function htmlLen(){try{return String(document.body&&document.body.innerHTML||'').replace(/\s+/g,' ').trim().length}catch(_){return 0}}
  function isBlank(){
    try{
      if(!document.body) return false;
      if(document.getElementById('titanBlankGuardPanel')) return false;
      if(/Titan Admin Login|Unlock Admin|Ledger|Dashboard|VIP Control|Setup|Result|Wallet/i.test(document.body.innerText||'')) return false;
      return textLen()<30 || htmlLen()<350;
    }catch(_){return false}
  }
  function headers(){
    const h={'Content-Type':'application/json','Cache-Control':'no-store'};
    try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||''; if(t)h['X-Titan-Admin-Token']=t}catch(_){ }
    return h;
  }
  function callRender(){
    try{
      if(typeof window.refreshMarketArrays==='function') window.refreshMarketArrays();
    }catch(e){pushErr('call','refreshMarketArrays: '+(e.message||e),'guard')}
    try{
      if(typeof window.ensureDataStruct==='function') window.ensureDataStruct();
    }catch(e){pushErr('call','ensureDataStruct: '+(e.message||e),'guard')}
    try{
      if(typeof window.render==='function') return window.render(true);
      pushErr('missing','window.render missing','guard');
    }catch(e){pushErr('call','render: '+(e.message||e),'guard')}
  }
  function clearBadCache(){
    try{
      const keepToken=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';
      ['appState','titanState','TITAN_STATE','titan.local.state','titan.codex.client.errors.v1','titan.dashboard.boot.errors.v1'].forEach(k=>{try{localStorage.removeItem(k)}catch(_){}});
      Object.keys(localStorage).forEach(k=>{if(/^titan\./i.test(k)&&!/token/i.test(k))try{localStorage.removeItem(k)}catch(_){}});
      if(keepToken) localStorage.setItem('TITAN_ADMIN_TOKEN',keepToken);
    }catch(e){pushErr('cache','clear cache: '+(e.message||e),'guard')}
  }
  async function repairState(out){
    try{
      out.textContent='Repair running...';
      const r=await fetch('/api/titan-codex/repair-state',{method:'POST',headers:headers(),body:'{}',cache:'no-store'});
      const j=await r.json().catch(()=>({status:'error',message:'Bad JSON'}));
      out.textContent=(j.status||'done')+' • '+((j.repairs||[]).slice(0,8).join(', ')||j.message||'state checked');
      setTimeout(()=>location.reload(),900);
    }catch(e){out.textContent='Repair error: '+(e.message||e);pushErr('repair',e.message||e,'guard')}
  }
  function panel(){
    if(!document.body || document.getElementById('titanBlankGuardPanel')) return;
    const oldText=textLen(), oldHtml=htmlLen();
    const wrap=document.createElement('div');
    wrap.id='titanBlankGuardPanel';
    css(wrap,'position:fixed;inset:0;z-index:2147483647;background:linear-gradient(180deg,#07111d,#101b2b);color:#fff;font-family:Arial,system-ui,sans-serif;overflow:auto;padding:18px;box-sizing:border-box');
    wrap.innerHTML='<div style="max-width:560px;margin:30px auto;border:1px solid rgba(42,171,238,.35);border-radius:18px;background:rgba(255,255,255,.06);padding:18px;box-shadow:0 20px 50px rgba(0,0,0,.45)"><h2 style="margin:0 0 8px;font-size:18px">⚠️ Titan Dashboard Blank Recovery</h2><p style="font-size:13px;line-height:1.5;opacity:.82;margin:0 0 14px">Page load hua, lekin UI render nahi hua. Ye usually browser cache/localStorage, render error, ya injected UI script ke crash se hota hai.</p><div id="tbgStatus" style="font-size:12px;line-height:1.45;background:rgba(0,0,0,.25);border-radius:12px;padding:10px;margin-bottom:12px">Checking...</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><button data-a="render">Force Render</button><button data-a="repair">Repair State</button><button data-a="cache">Clear Cache + Reload</button><button data-a="reload">Hard Reload</button></div><p style="font-size:11px;opacity:.68;margin-top:14px">Agar button ke baad bhi blank aaye, Termux me <b>bash termux_diagnose.sh</b> run karke output bhejo.</p></div>';
    document.body.appendChild(wrap);
    const st=wrap.querySelector('#tbgStatus');
    const btns=wrap.querySelectorAll('button');
    btns.forEach(b=>css(b,'border:1px solid rgba(42,171,238,.32);border-radius:12px;background:rgba(42,171,238,.15);color:#fff;padding:12px 10px;font-weight:900;font-size:12px'));
    function status(extra){
      const latest=errors.slice(-5).map(e=>'• '+e.kind+': '+e.message).join('<br>')||'No browser error captured yet.';
      st.innerHTML='Text length: '+oldText+' • HTML length: '+oldHtml+'<br>Render: '+(typeof window.render)+' • appState: '+(window.appState?'yes':'no')+'<br>'+(extra?'<b>'+extra+'</b><br>':'')+latest;
    }
    status('Blank detected');
    wrap.onclick=async function(e){
      const a=e.target&&e.target.getAttribute('data-a');
      if(!a) return;
      if(a==='render'){
        status('Trying force render...'); callRender(); setTimeout(()=>{ if(!isBlank()){wrap.remove()} else status('Force render tried, still blank.'); },600);
      }
      if(a==='repair') await repairState(st);
      if(a==='cache'){ clearBadCache(); location.href=location.pathname+'?reset='+Date.now(); }
      if(a==='reload'){ location.href=location.pathname+'?hard='+Date.now(); }
    };
  }
  function bootCheck(){ try{callRender()}catch(_){ } setTimeout(()=>{if(isBlank())panel()},900); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',()=>setTimeout(bootCheck,1200));
  else setTimeout(bootCheck,1200);
  setTimeout(()=>{if(isBlank())panel()},3500);
  window.__TitanDashboardBlankGuard={version:VERSION,show:panel,render:callRender,clearCache:clearBadCache,errors:errors};
})();
</script>
'''
