"""Titan Nova global realtime bridge.

Adds an app-wide browser realtime layer for every tab/action:
- no-store state reads
- instant refresh after every POST/PUT/PATCH/DELETE
- fast background Firebase state sync
- skips overwriting while the admin is typing
"""


def register_titan_realtime_global(app):
    if getattr(app, "_titan_realtime_global_registered", False):
        return
    app._titan_realtime_global_registered = True

    from flask import jsonify, request
    import time

    @app.route("/api/realtime/status", methods=["GET"])
    def titan_realtime_status():
        return jsonify({
            "status": "success",
            "feature": "titan_global_realtime",
            "version": "2026-07-08-global-realtime-v1",
            "pollMs": 450,
            "writeRefresh": True,
            "allTabs": True,
            "checkedAt": int(time.time() * 1000),
        })

    @app.after_request
    def titan_realtime_no_store(resp):
        try:
            path = request.path or ""
            if path.startswith("/api/") or path in ("/save", "/bot_schedule"):
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
        except Exception:
            pass
        return resp

    @app.after_request
    def titan_realtime_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-global-realtime-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + REALTIME_SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


REALTIME_SCRIPT = r'''
<script id="titan-global-realtime-v1">
(function(){
  if(window.__TITAN_GLOBAL_REALTIME__) return;
  window.__TITAN_GLOBAL_REALTIME__ = true;

  const VERSION = '2026-07-08-global-realtime-v1';
  const POLL_MS = Math.max(250, Number(localStorage.getItem('TITAN_REALTIME_POLL_MS') || 450));
  const WRITE_REFRESH_DELAYS = [40, 180, 520, 1100];
  let syncBusy = false;
  let lastRaw = '';
  let lastAppliedAt = 0;
  let writeLockUntil = 0;
  let writeSeq = 0;
  let pausedUntil = 0;

  function directEval(code){ try { return Function(code)(); } catch(e) { return undefined; } }
  function directSet(state){ try { Function('nextState', `
      appState = nextState;
      try { if(typeof IS_MASTER !== 'undefined' && IS_MASTER) appState.activeId = appState.activeId || 'admin1'; } catch(e) {}
      try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
      try { if(typeof applyPendingLedgerPatchesToState === 'function') applyPendingLedgerPatchesToState(appState); } catch(e) {}
      try { state = appState.profiles[appState.activeId] || appState.profiles['admin1']; } catch(e) {}
      try { if(typeof LOCAL_KEY !== 'undefined') localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
  `)(state); return true; } catch(e) { return false; } }
  function isMaster(){ return directEval('return typeof IS_MASTER !== "undefined" ? !!IS_MASTER : true') !== false; }
  function stateUrl(){
    const u = directEval('return typeof SERVER_STATE_URL !== "undefined" ? SERVER_STATE_URL : ""');
    if(u) return String(u);
    const aid = directEval('return appState && appState.activeId ? appState.activeId : ""') || '';
    return isMaster() ? '/api/state' : ('/api/state?vip=' + encodeURIComponent(aid));
  }
  function sep(url){ return String(url).includes('?') ? '&' : '?'; }
  function typing(){
    try{
      const el=document.activeElement;
      if(!el) return false;
      const tag=String(el.tagName||'').toUpperCase();
      return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable;
    }catch(e){ return false; }
  }
  function renderNow(reason){
    try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
    try { if(typeof render === 'function') render(true); } catch(e) {}
    try { document.dispatchEvent(new CustomEvent('titan:realtime-applied', {detail:{reason, at:Date.now(), version:VERSION}})); } catch(e) {}
  }
  function showStatus(text){
    try{
      let el=document.getElementById('titanRealtimeStatusDot');
      if(!el){
        el=document.createElement('div'); el.id='titanRealtimeStatusDot';
        el.style.cssText='position:fixed;right:10px;bottom:78px;z-index:9999;background:rgba(0,194,111,.92);color:#062013;border-radius:999px;padding:5px 8px;font:900 9px Inter,Arial;box-shadow:0 4px 14px rgba(0,0,0,.25);pointer-events:none;opacity:.0;transition:opacity .15s';
        document.body.appendChild(el);
      }
      el.textContent=text||'LIVE'; el.style.opacity='1'; clearTimeout(el._t); el._t=setTimeout(()=>{el.style.opacity='0'},700);
    }catch(e){}
  }
  function markWrite(reason, holdMs){
    writeSeq += 1;
    writeLockUntil = Math.max(writeLockUntil, Date.now() + (holdMs || 1400));
    try { if(typeof titanMarkUiLocalWrite === 'function') titanMarkUiLocalWrite(reason || 'global_realtime_write', holdMs || 2500); } catch(e) {}
    showStatus('SYNCING');
  }
  async function fetchState(reason, force){
    if(syncBusy) return false;
    if(Date.now() < pausedUntil && !force) return false;
    if(typing() && !force) return false;
    if(Date.now() < writeLockUntil && !force) return false;
    syncBusy = true;
    try{
      const base = stateUrl();
      const url = base + sep(base) + '_rt=' + Date.now() + '&_fast=1&_global=1';
      const headers = {'Cache-Control':'no-store'};
      try { const tok = localStorage.getItem('TITAN_ADMIN_TOKEN') || ''; if(tok) headers['X-Titan-Admin-Token'] = tok; } catch(e) {}
      const res = await fetch(url, {cache:'no-store', headers});
      if(!res.ok) return false;
      const raw = await res.text();
      if(!raw || raw === lastRaw){ return false; }
      const next = JSON.parse(raw);
      if(!next || !next.profiles) return false;
      lastRaw = raw;
      if(!directSet(next)) return false;
      lastAppliedAt = Date.now();
      renderNow(reason || 'poll');
      showStatus('LIVE');
      return true;
    }catch(e){ return false; }
    finally{ syncBusy=false; }
  }
  function scheduleAfterWrite(reason){
    markWrite(reason || 'write');
    WRITE_REFRESH_DELAYS.forEach((d,i)=>setTimeout(()=>fetchState((reason||'write')+'_'+i, true), d));
  }

  const oldFetch = window.fetch;
  window.fetch = function titanRealtimeFetch(input, init){
    const method = String((init && init.method) || 'GET').toUpperCase();
    const url = String((typeof input === 'string' ? input : (input && input.url)) || '');
    const write = method !== 'GET' && (/\/api\//.test(url) || /\/save(\?|$)/.test(url) || /\/bot_schedule(\?|$)/.test(url));
    if(write) markWrite('fetch_'+method, 2600);
    const p = oldFetch.apply(this, arguments);
    if(write){
      p.then(()=>scheduleAfterWrite('fetch_done_'+method)).catch(()=>setTimeout(()=>fetchState('fetch_error_'+method, true), 400));
    }
    return p;
  };

  try{
    const XHR = window.XMLHttpRequest;
    const oldOpen = XHR.prototype.open;
    const oldSend = XHR.prototype.send;
    XHR.prototype.open = function(method, url){ this.__titanRtMethod = String(method||'GET').toUpperCase(); this.__titanRtUrl = String(url||''); return oldOpen.apply(this, arguments); };
    XHR.prototype.send = function(){
      const write = this.__titanRtMethod !== 'GET' && (/\/api\//.test(this.__titanRtUrl) || /\/save(\?|$)/.test(this.__titanRtUrl) || /\/bot_schedule(\?|$)/.test(this.__titanRtUrl));
      if(write){ markWrite('xhr_'+this.__titanRtMethod, 2600); this.addEventListener('loadend', ()=>scheduleAfterWrite('xhr_done_'+this.__titanRtMethod)); }
      return oldSend.apply(this, arguments);
    };
  }catch(e){}

  document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) fetchState('visible', true); });
  window.addEventListener('focus', ()=>fetchState('focus', true));
  document.addEventListener('titan:force-sync', ()=>fetchState('event', true));
  window.__TitanRealtime = {version:VERSION, refresh:(r)=>fetchState(r||'manual', true), markWrite, pause:(ms)=>{pausedUntil=Date.now()+Number(ms||1000)}, status:()=>({lastAppliedAt, syncBusy, writeLockUntil, pollMs:POLL_MS})};

  setInterval(()=>fetchState('poll', false), POLL_MS);
  setTimeout(()=>fetchState('boot', true), 500);
  console.log('✅ Titan Global Realtime active', VERSION, 'poll', POLL_MS);
})();
</script>
'''
