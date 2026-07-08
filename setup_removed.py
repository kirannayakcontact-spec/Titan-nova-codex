"""Remove Setup tab from Titan Nova runtime.

This is a removal-only guard:
- hides Setup navigation and Setup screen from the frontend
- prevents navigation to mainNav='setup'
- disables Setup-only backend endpoints with HTTP 410

It does not create a replacement UI/API and does not touch Market, Health, Gateway,
Ledger, Entries, Finance, VIP, Forward, Guard, Backup, AI Scan, or Audit features.
"""


def register_setup_removed(app):
    if getattr(app, "_titan_setup_removed_registered", False):
        return
    app._titan_setup_removed_registered = True

    from flask import jsonify, request

    blocked_exact = {
        "/api/config_migration_status",
        "/api/setup_status",
        "/api/setup_control_status",
        "/api/setup_control_center_status",
        "/api/titan_setup_status",
        "/api/titan_setup_cleanup_status",
    }

    @app.before_request
    def titan_setup_backend_removed():
        try:
            path = (request.path or "").lower().rstrip("/")
            if not path.startswith("/api/"):
                return None
            if path in blocked_exact or "/setup" in path or "setup_" in path or "_setup" in path:
                return jsonify({
                    "status": "disabled",
                    "feature": "setup_removed",
                    "message": "Setup tab/backend has been removed from this Titan Nova runtime.",
                }), 410
        except Exception:
            return None
        return None

    @app.after_request
    def titan_setup_frontend_removed(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-setup-removed-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<style id="titan-setup-removed-v1-style">
  [data-nav="setup"], [data-tab="setup"], [href="#setup"], [href="/setup"],
  button[onclick*="setup"], a[onclick*="setup"] { display:none !important; }
</style>
<script id="titan-setup-removed-v1">
(function(){
  if(window.__TITAN_SETUP_REMOVED_V1__) return;
  window.__TITAN_SETUP_REMOVED_V1__ = true;

  function directEval(code){ try { return Function(code)(); } catch(e) { return undefined; } }
  function directSet(name, value){ try { Function('v', name + '=v')(value); return true; } catch(e) { try { window[name]=value; return true; } catch(_) { return false; } } }
  function txt(el){ return String((el && el.textContent) || '').replace(/\s+/g,' ').trim().toUpperCase(); }
  function qsa(sel){ return Array.from(document.querySelectorAll(sel)); }
  function currentNav(){ return String(directEval('return typeof mainNav !== "undefined" ? mainNav : ""') || '').toLowerCase(); }

  function isSetupNode(el){
    if(!el) return false;
    const t = txt(el);
    const attrs = String((el.getAttribute && (el.getAttribute('onclick') || el.getAttribute('href') || el.dataset?.nav || el.dataset?.tab || el.id || el.className)) || '').toLowerCase();
    if(attrs.includes('setup')) return true;
    if(t === 'SETUP') return true;
    if(t.includes('SETUP') && (el.tagName === 'BUTTON' || el.tagName === 'A')) return true;
    return false;
  }

  function hideNode(el){
    try{
      el.style.setProperty('display','none','important');
      el.style.setProperty('visibility','hidden','important');
      el.setAttribute('aria-hidden','true');
      el.setAttribute('data-titan-setup-removed','1');
    }catch(e){}
  }

  function removeSetupNav(){
    qsa('button,a,[data-nav],[data-tab],[onclick],[href],nav div,footer div,.bottom-nav div').forEach(function(el){
      if(isSetupNode(el)) hideNode(el);
    });
  }

  function leaveSetupIfOpen(){
    try{
      if(currentNav() === 'setup'){
        directSet('mainNav','ledger');
        try { if(typeof render === 'function') render(false); } catch(e) {}
      }
    }catch(e){}
  }

  function patchSetMainNav(){
    try{
      const old = directEval('return typeof setMainNav === "function" ? setMainNav : null');
      if(!old || old.__titanSetupRemoved) return;
      const next = function(nav){
        if(String(nav || '').toLowerCase() === 'setup') nav = 'ledger';
        return old.apply(this, arguments.length ? [nav] : arguments);
      };
      next.__titanSetupRemoved = true;
      directSet('setMainNav', next);
      try { window.setMainNav = next; } catch(e) {}
    }catch(e){}
  }

  document.addEventListener('click', function(ev){
    const el = ev.target && ev.target.closest ? ev.target.closest('button,a,[data-nav],[data-tab],[onclick],[href]') : null;
    if(isSetupNode(el)){
      ev.preventDefault();
      ev.stopPropagation();
      directSet('mainNav','ledger');
      try { if(typeof render === 'function') render(false); } catch(e) {}
      setTimeout(clean, 40);
      return false;
    }
  }, true);

  function clean(){
    patchSetMainNav();
    leaveSetupIfOpen();
    removeSetupNav();
  }

  const obs = new MutationObserver(function(){ clean(); });
  try { obs.observe(document.documentElement, {childList:true, subtree:true}); } catch(e) {}
  document.addEventListener('DOMContentLoaded', clean);
  window.addEventListener('load', clean);
  setInterval(clean, 700);
  setTimeout(clean, 80);
  setTimeout(clean, 500);
})();
</script>
'''
