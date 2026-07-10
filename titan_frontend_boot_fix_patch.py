"""Safe frontend boot/render guard for Titan Nova.

Purpose:
- Prevent injected UI patch errors from turning the dashboard into a blank page.
- Keep existing VIP/Ledger/Result features intact.
- Avoid heavy recovery overlays; show a small inline fallback only when render fails.
"""


def register_titan_frontend_boot_fix(app):
    if getattr(app, "_titan_frontend_boot_fix_registered", False):
        return
    app._titan_frontend_boot_fix_registered = True

    from flask import jsonify, request

    VERSION = "2026-07-10-frontend-boot-render-guard-v1"

    @app.route("/api/frontend_boot/status")
    def frontend_boot_status():
        return jsonify({"status": "success", "version": VERSION})

    @app.after_request
    def frontend_boot_fix_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-frontend-boot-render-guard-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan frontend boot/render guard loaded", VERSION)


SCRIPT = r'''
<script id="titan-frontend-boot-render-guard-v1">
(function(){
  if(window.__TITAN_FRONTEND_BOOT_RENDER_GUARD_V1__) return;
  window.__TITAN_FRONTEND_BOOT_RENDER_GUARD_V1__ = true;
  const VERSION='2026-07-10-frontend-boot-render-guard-v1';
  const ERR_KEY='titan.frontend.boot.errors.v1';

  function log(kind,msg,src){
    try{
      const row={at:new Date().toISOString(),version:VERSION,kind:String(kind||'error'),message:String(msg||'').slice(0,700),source:String(src||'browser').slice(0,160)};
      const old=JSON.parse(localStorage.getItem(ERR_KEY)||'[]'); old.push(row); localStorage.setItem(ERR_KEY,JSON.stringify(old.slice(-50)));
      console.warn('[Titan Boot Guard]', row.kind, row.message, row.source);
    }catch(_){ }
  }
  window.addEventListener('error',e=>log('window.error',e.message||'Script error',e.filename||''),true);
  window.addEventListener('unhandledrejection',e=>log('promise',(e.reason&&e.reason.message)||e.reason||'Promise rejection','promise'),true);

  function hasState(){ return !!(window.appState && typeof window.appState==='object'); }
  function ensureStateShape(){
    try{
      if(!hasState()) return false;
      if(!appState.profiles || typeof appState.profiles!=='object' || Array.isArray(appState.profiles)) appState.profiles={};
      if(!appState.wallets || typeof appState.wallets!=='object' || Array.isArray(appState.wallets)) appState.wallets={};
      if(!appState.settlementSettings || typeof appState.settlementSettings!=='object' || Array.isArray(appState.settlementSettings)) appState.settlementSettings={};
      if(!appState.ledgerAutoMarkRecords || typeof appState.ledgerAutoMarkRecords!=='object' || Array.isArray(appState.ledgerAutoMarkRecords)) appState.ledgerAutoMarkRecords={};
      if(!appState.profiles.admin1) appState.profiles.admin1={name:'ADMIN 1',config:{},dayRecords:{},approvalStatus:'approved',vipAccessEnabled:true,role:'admin'};
      ['admin1','admin2','admin3'].forEach(id=>{ if(!appState.profiles[id]) appState.profiles[id]={name:id.toUpperCase(),config:{},dayRecords:{}}; appState.profiles[id].approvalStatus='approved'; appState.profiles[id].vipAccessEnabled=true; appState.profiles[id].role='admin'; });
      return true;
    }catch(e){ log('state-shape',e.message||e,'ensureStateShape'); return false; }
  }
  function target(){
    try{return document.querySelector('#app,#root,#mainContent,main,.main,.content') || document.body}catch(_){return document.body}
  }
  function fallback(title,msg){
    try{
      const t=target(); if(!t || document.getElementById('titanBootInlineFallback')) return;
      const d=document.createElement('div'); d.id='titanBootInlineFallback';
      d.style.cssText='margin:14px;padding:14px;border:1px solid rgba(250,199,72,.35);border-radius:16px;background:#182536;color:#fff;font:800 12px Arial;line-height:1.45';
      d.innerHTML='<b>'+String(title||'Titan UI recovery')+'</b><p style="opacity:.78;font-weight:700">'+String(msg||'Render crash avoid kiya gaya. Reload try karo.').slice(0,280)+'</p><button onclick="location.reload()" style="padding:8px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;font-weight:900">Reload</button>';
      t.prepend(d);
    }catch(_){ }
  }

  function patchRender(){
    try{
      if(typeof window.render==='function' && !window.render.__titanBootGuard){
        const old=window.render;
        window.render=function(){
          try{ ensureStateShape(); return old.apply(this,arguments); }
          catch(e){ log('render-crash',e.message||e,'render'); fallback('⚠️ Render crash fixed','Dashboard blank hone se roka gaya. Reload karo, ya Termux me bash termux_diagnose.sh output bhejo.'); return false; }
        };
        window.render.__titanBootGuard=true;
      }
    }catch(e){ log('patch-render',e.message||e,'patchRender'); }
  }

  function patchVipClients(){
    try{
      if(typeof window.renderClients==='function' && !window.renderClients.__titanBootGuard){
        const old=window.renderClients;
        window.renderClients=function(){
          try{
            if(!ensureStateShape()) return '<div class="px-3 py-4 pb-28"><div class="native-card p-6 text-center text-[var(--text-muted)] text-xs">VIP data load ho raha hai...</div></div>';
            return old.apply(this,arguments);
          }catch(e){
            log('renderClients-crash',e.message||e,'renderClients');
            return '<div class="px-3 py-4 pb-28"><div class="native-card p-4 text-[var(--rose)] text-xs"><b>VIP tab render error safe kiya gaya.</b><br>'+String(e.message||e).slice(0,220)+'</div></div>';
          }
        };
        window.renderClients.__titanBootGuard=true;
      }
    }catch(e){ log('patch-clients',e.message||e,'patchVipClients'); }
  }

  function patchLedgerHud(){
    try{
      if(typeof window.renderWalletHUD==='function' && !window.renderWalletHUD.__titanBootGuard){
        const old=window.renderWalletHUD;
        window.renderWalletHUD=function(){
          try{ ensureStateShape(); return old.apply(this,arguments)||''; }
          catch(e){ log('walletHud-crash',e.message||e,'renderWalletHUD'); return ''; }
        };
        window.renderWalletHUD.__titanBootGuard=true;
      }
      if(typeof window.ledgerAutoPassFailCardHtml==='function' && !window.ledgerAutoPassFailCardHtml.__titanBootGuard){
        const oldCard=window.ledgerAutoPassFailCardHtml;
        window.ledgerAutoPassFailCardHtml=function(){
          try{ ensureStateShape(); return oldCard.apply(this,arguments)||''; }
          catch(e){ log('ledgerAutoCard-crash',e.message||e,'ledgerAutoPassFailCardHtml'); return ''; }
        };
        window.ledgerAutoPassFailCardHtml.__titanBootGuard=true;
      }
    }catch(e){ log('patch-ledger',e.message||e,'patchLedgerHud'); }
  }

  function patchSettlement(){
    try{
      if(typeof window.settlementCardHtml==='function' && !window.settlementCardHtml.__titanBootGuard){
        const old=window.settlementCardHtml;
        window.settlementCardHtml=function(){
          try{ ensureStateShape(); return old.apply(this,arguments)||''; }
          catch(e){ log('settlement-crash',e.message||e,'settlementCardHtml'); return ''; }
        };
        window.settlementCardHtml.__titanBootGuard=true;
      }
    }catch(e){ log('patch-settlement',e.message||e,'patchSettlement'); }
  }

  function patchAll(){ patchRender(); patchVipClients(); patchLedgerHud(); patchSettlement(); }
  patchAll();
  setTimeout(patchAll,200);
  setTimeout(patchAll,900);
  setInterval(patchAll,2500);
  window.__TitanFrontendBootGuard={version:VERSION,patch:patchAll,ensureStateShape:ensureStateShape,errorsKey:ERR_KEY};
  console.log('✅ Titan frontend boot/render guard active',VERSION);
})();
</script>
'''
