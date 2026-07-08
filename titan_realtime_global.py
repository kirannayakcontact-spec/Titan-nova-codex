"""Titan Nova smooth global realtime bridge.

App-wide realtime without UI jank:
- no-store state reads
- quick refresh after writes
- slower background sync
- debounced render through requestAnimationFrame
- no overwrite while typing/scrolling/touching
- Entries tab render-lock so open panels do not collapse during realtime sync
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
            "feature": "titan_global_realtime_smooth",
            "version": "2026-07-08-global-realtime-smooth-v3-entries-render-lock",
            "pollMs": 1800,
            "writeRefresh": True,
            "smoothMode": True,
            "allTabs": True,
            "entriesRenderLock": True,
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
            if not html or "titan-global-realtime-smooth-v3-entries-render-lock" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + REALTIME_SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


REALTIME_SCRIPT = r'''
<script id="titan-global-realtime-smooth-v3-entries-render-lock">
(function(){
  if(window.__TITAN_GLOBAL_REALTIME_SMOOTH_V3__) return;
  window.__TITAN_GLOBAL_REALTIME_SMOOTH_V3__ = true;

  const VERSION = '2026-07-08-global-realtime-smooth-v3-entries-render-lock';
  const POLL_MS = Math.max(900, Number(localStorage.getItem('TITAN_REALTIME_POLL_MS') || 1800));
  const WRITE_REFRESH_DELAYS = [180, 720];
  const RENDER_DEBOUNCE_MS = 160;
  const INPUT_HOLD_MS = 1800;
  const SCROLL_HOLD_MS = 900;
  const ENTRIES_HOLD_MS = 8500;
  let syncBusy = false;
  let lastRaw = '';
  let lastAppliedAt = 0;
  let writeLockUntil = 0;
  let pausedUntil = 0;
  let interactionUntil = 0;
  let entriesHoldUntil = 0;
  let renderTimer = null;
  let renderQueued = false;
  let pendingRenderReason = '';

  function now(){ return Date.now(); }
  function directEval(code){ try { return Function(code)(); } catch(e) { return undefined; } }
  function directSet(nextState){
    try {
      Function('nextState', `
        appState = nextState;
        try { if(typeof IS_MASTER !== 'undefined' && IS_MASTER) appState.activeId = appState.activeId || 'admin1'; } catch(e) {}
        try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
        try { if(typeof applyPendingLedgerPatchesToState === 'function') applyPendingLedgerPatchesToState(appState); } catch(e) {}
        try { state = appState.profiles[appState.activeId] || appState.profiles['admin1']; } catch(e) {}
        try { if(typeof LOCAL_KEY !== 'undefined') localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
      `)(nextState);
      return true;
    } catch(e) { return false; }
  }
  function isMaster(){ return directEval('return typeof IS_MASTER !== "undefined" ? !!IS_MASTER : true') !== false; }
  function stateUrl(){
    const u = directEval('return typeof SERVER_STATE_URL !== "undefined" ? SERVER_STATE_URL : ""');
    if(u) return String(u);
    const aid = directEval('return appState && appState.activeId ? appState.activeId : ""') || '';
    return isMaster() ? '/api/state' : ('/api/state?vip=' + encodeURIComponent(aid));
  }
  function sep(url){ return String(url).includes('?') ? '&' : '?'; }
  function currentNav(){ return String(directEval('return typeof mainNav !== "undefined" ? mainNav : ""') || '').toLowerCase(); }
  function isEntriesNav(){ return currentNav() === 'entries'; }
  function editing(){
    try{
      const el=document.activeElement;
      if(!el) return false;
      const tag=String(el.tagName||'').toUpperCase();
      return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable;
    }catch(e){ return false; }
  }
  function entriesPanelOpen(){
    if(!isEntriesNav()) return false;
    try{
      if(now() < entriesHoldUntil) return true;
      const active = document.activeElement;
      if(active && active.closest && active.closest('input,textarea,select,[contenteditable="true"]')) return true;
      const openDetails = Array.from(document.querySelectorAll('details[open]')).some(d => {
        const t = String(d.textContent || '').toUpperCase();
        return t.includes('ENTRY') || t.includes('MARKET') || t.includes('TIME') || t.includes('SETTING');
      });
      if(openDetails) return true;
      const visiblePanels = Array.from(document.querySelectorAll('[id], [class]')).some(el => {
        const key = String((el.id || '') + ' ' + (el.className || '')).toLowerCase();
        if(!(key.includes('entry') || key.includes('market') || key.includes('time') || key.includes('setting'))) return false;
        const cs = window.getComputedStyle(el);
        return cs && cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect && el.getBoundingClientRect().height > 36;
      });
      return !!visiblePanels && now() < entriesHoldUntil + 1200;
    }catch(e){ return now() < entriesHoldUntil; }
  }
  function interacting(){ return now() < interactionUntil; }
  function shouldAvoidRender(force){
    if(entriesPanelOpen()) return true;
    if(force && now() < entriesHoldUntil && isEntriesNav()) return true;
    if(force) return false;
    return document.hidden || editing() || interacting() || now() < pausedUntil || now() < writeLockUntil;
  }
  function touchInteraction(){ interactionUntil = Math.max(interactionUntil, now() + SCROLL_HOLD_MS); }
  function entriesInteraction(){ if(isEntriesNav()) entriesHoldUntil = Math.max(entriesHoldUntil, now() + ENTRIES_HOLD_MS); }
  ['touchstart','touchmove','wheel','scroll','pointerdown'].forEach(ev=>{
    try { window.addEventListener(ev, function(){ touchInteraction(); entriesInteraction(); }, {passive:true, capture:true}); } catch(e) {}
  });
  ['click','change','input','focusin','keydown'].forEach(ev=>{
    try { document.addEventListener(ev, function(){ entriesInteraction(); }, true); } catch(e) {}
  });
  document.addEventListener('input', ()=>{ interactionUntil = Math.max(interactionUntil, now() + INPUT_HOLD_MS); }, true);

  function showStatus(text){
    try{
      let el=document.getElementById('titanRealtimeStatusDot');
      if(!el){
        el=document.createElement('div'); el.id='titanRealtimeStatusDot';
        el.style.cssText='position:fixed;right:10px;bottom:78px;z-index:9999;background:rgba(0,194,111,.9);color:#062013;border-radius:999px;padding:5px 8px;font:900 9px Inter,Arial;box-shadow:0 4px 14px rgba(0,0,0,.22);pointer-events:none;opacity:0;transition:opacity .18s';
        document.body.appendChild(el);
      }
      el.textContent=text||'LIVE'; el.style.opacity='1'; clearTimeout(el._t); el._t=setTimeout(()=>{el.style.opacity='0'},520);
    }catch(e){}
  }
  function doRender(reason){
    renderQueued = false;
    renderTimer = null;
    if(entriesPanelOpen()) return;
    try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
    try { if(typeof render === 'function') render(true); } catch(e) {}
    try { document.dispatchEvent(new CustomEvent('titan:realtime-applied', {detail:{reason, at:now(), version:VERSION}})); } catch(e) {}
    showStatus('LIVE');
  }
  function queueRender(reason, force){
    pendingRenderReason = reason || pendingRenderReason || 'sync';
    if(shouldAvoidRender(force)) return;
    if(renderQueued) return;
    renderQueued = true;
    clearTimeout(renderTimer);
    renderTimer = setTimeout(()=>{
      if(shouldAvoidRender(force)){ renderQueued=false; return; }
      if(window.requestAnimationFrame) requestAnimationFrame(()=>doRender(pendingRenderReason));
      else doRender(pendingRenderReason);
    }, RENDER_DEBOUNCE_MS);
  }
  function markWrite(reason, holdMs){
    writeLockUntil = Math.max(writeLockUntil, now() + (holdMs || 900));
    interactionUntil = Math.max(interactionUntil, now() + 500);
    if(isEntriesNav()) entriesHoldUntil = Math.max(entriesHoldUntil, now() + Math.max(ENTRIES_HOLD_MS, holdMs || 0));
    try { if(typeof titanMarkUiLocalWrite === 'function') titanMarkUiLocalWrite(reason || 'global_realtime_write', holdMs || 1600); } catch(e) {}
    showStatus('SYNC');
  }
  async function fetchState(reason, force){
    if(syncBusy) return false;
    if(!force && shouldAvoidRender(false)) return false;
    syncBusy = true;
    try{
      const base = stateUrl();
      const url = base + sep(base) + '_rt=' + now() + '&_fast=1&_smooth=1';
      const headers = {'Cache-Control':'no-store'};
      try { const tok = localStorage.getItem('TITAN_ADMIN_TOKEN') || ''; if(tok) headers['X-Titan-Admin-Token'] = tok; } catch(e) {}
      const res = await fetch(url, {cache:'no-store', headers});
      if(!res.ok) return false;
      const raw = await res.text();
      if(!raw || raw === lastRaw) return false;
      const next = JSON.parse(raw);
      if(!next || !next.profiles) return false;
      lastRaw = raw;
      if(!directSet(next)) return false;
      lastAppliedAt = now();
      queueRender(reason || 'poll', !!force);
      return true;
    }catch(e){ return false; }
    finally{ syncBusy=false; }
  }
  function scheduleAfterWrite(reason){
    markWrite(reason || 'write', 900);
    WRITE_REFRESH_DELAYS.forEach((d,i)=>setTimeout(()=>fetchState((reason||'write')+'_'+i, true), d));
  }

  const oldFetch = window.fetch;
  window.fetch = function titanRealtimeFetch(input, init){
    const method = String((init && init.method) || 'GET').toUpperCase();
    const url = String((typeof input === 'string' ? input : (input && input.url)) || '');
    const write = method !== 'GET' && (/\/api\//.test(url) || /\/save(\?|$)/.test(url) || /\/bot_schedule(\?|$)/.test(url));
    if(write) markWrite('fetch_'+method, 1200);
    const p = oldFetch.apply(this, arguments);
    if(write){ p.then(()=>scheduleAfterWrite('fetch_done_'+method)).catch(()=>setTimeout(()=>fetchState('fetch_error_'+method, true), 650)); }
    return p;
  };
  try{
    const XHR = window.XMLHttpRequest;
    const oldOpen = XHR.prototype.open;
    const oldSend = XHR.prototype.send;
    XHR.prototype.open = function(method, url){ this.__titanRtMethod=String(method||'GET').toUpperCase(); this.__titanRtUrl=String(url||''); return oldOpen.apply(this, arguments); };
    XHR.prototype.send = function(){
      const write = this.__titanRtMethod !== 'GET' && (/\/api\//.test(this.__titanRtUrl) || /\/save(\?|$)/.test(this.__titanRtUrl) || /\/bot_schedule(\?|$)/.test(this.__titanRtUrl));
      if(write){ markWrite('xhr_'+this.__titanRtMethod, 1200); this.addEventListener('loadend', ()=>scheduleAfterWrite('xhr_done_'+this.__titanRtMethod)); }
      return oldSend.apply(this, arguments);
    };
  }catch(e){}

  document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) setTimeout(()=>fetchState('visible', true), 220); });
  window.addEventListener('focus', ()=>setTimeout(()=>fetchState('focus', true), 220));
  document.addEventListener('titan:force-sync', ()=>fetchState('event', true));
  window.__TitanRealtime = {version:VERSION, refresh:(r)=>fetchState(r||'manual', true), markWrite, pause:(ms)=>{pausedUntil=now()+Number(ms||1000)}, pauseEntries:(ms)=>{entriesHoldUntil=now()+Number(ms||ENTRIES_HOLD_MS)}, status:()=>({lastAppliedAt, syncBusy, writeLockUntil, interactionUntil, entriesHoldUntil, pollMs:POLL_MS})};

  setInterval(()=>fetchState('poll', false), POLL_MS);
  setTimeout(()=>fetchState('boot', true), 850);
  console.log('✅ Titan Global Realtime Smooth active', VERSION, 'poll', POLL_MS);
})();
</script>
'''
