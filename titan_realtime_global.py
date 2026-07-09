"""Titan Nova smooth global realtime bridge.

App-wide realtime without UI jank:
- no-store state reads
- quick refresh after writes
- slower background sync
- debounced render through requestAnimationFrame
- no overwrite while typing/scrolling/touching
- Entries/Forward/Finance tab render-lock so open panels do not collapse during realtime sync
- local-only UI toggle policy: checkbox/toggle/on-off state stays in browser storage; business data remains in Firebase
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
            "version": "2026-07-09-global-realtime-local-only-ui-toggles-v6",
            "pollMs": 1800,
            "writeRefresh": True,
            "smoothMode": True,
            "allTabs": True,
            "entriesRenderLock": True,
            "forwardRenderLock": True,
            "financeRenderLock": True,
            "localOnlyUiToggles": True,
            "firebaseBusinessDataOnly": True,
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
            if not html or "titan-global-realtime-local-only-ui-toggles-v6" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + REALTIME_SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


REALTIME_SCRIPT = r'''
<script id="titan-global-realtime-local-only-ui-toggles-v6">
(function(){
  if(window.__TITAN_GLOBAL_REALTIME_SMOOTH_V6__) return;
  window.__TITAN_GLOBAL_REALTIME_SMOOTH_V6__ = true;

  const VERSION = '2026-07-09-global-realtime-local-only-ui-toggles-v6';
  const POLL_MS = Math.max(900, Number(localStorage.getItem('TITAN_REALTIME_POLL_MS') || 1800));
  const WRITE_REFRESH_DELAYS = [180, 720];
  const RENDER_DEBOUNCE_MS = 160;
  const INPUT_HOLD_MS = 1800;
  const SCROLL_HOLD_MS = 900;
  const TAB_HOLD_MS = 9500;
  const LOCAL_UI_STORE = 'titan.local.ui.toggles.v1';
  let syncBusy = false;
  let lastRaw = '';
  let lastAppliedAt = 0;
  let writeLockUntil = 0;
  let pausedUntil = 0;
  let interactionUntil = 0;
  let protectedHoldUntil = 0;
  let protectedHoldNav = '';
  let renderTimer = null;
  let renderQueued = false;
  let pendingRenderReason = '';

  function now(){ return Date.now(); }
  function directEval(code){ try { return Function(code)(); } catch(e) { return undefined; } }
  function clone(obj){ try { return JSON.parse(JSON.stringify(obj)); } catch(e) { return obj; } }

  const LOCAL_ONLY_KEY_RE = /(toggle|checkbox|uiOnly|ui_only|viewState|view_state|expanded|collapsed|selectedTab|activeTab|tabState|drawer|modal|panelOpen|panel_open|toast|filterText|searchText|sortBy|sort_by|themeTemp|tempUi|localUi|local_ui|stickyToggle|toggleSticky|resultToggleSticky|autoMark|onlyWait|allVips|msgSummary|settlementOn|autoHitMiss)/i;
  const BUSINESS_KEY_RE = /(ledger|payment|payments|deposit|deposits|withdraw|withdrawal|wallet|wallets|transaction|transactions|entry|entries|result|results|market|markets|profile|profiles|vipProfile|vipProfiles|userProfiles|vipUsers|customers|client|clients|schedule|schedules|target|targets|group|groups|audit|backup|settingsVersion|deletedProfiles|utr|upi|amount|balance|pass|fail|approval|expiry|access)/i;
  function isPlainObject(x){ return !!x && typeof x === 'object' && !Array.isArray(x); }
  function isLocalOnlyKey(k){ return LOCAL_ONLY_KEY_RE.test(String(k||'')) && !BUSINESS_KEY_RE.test(String(k||'')); }
  function scrubLocalOnly(obj, depth){
    if(!obj || typeof obj !== 'object' || depth > 7) return obj;
    if(Array.isArray(obj)){ obj.forEach(v => scrubLocalOnly(v, depth+1)); return obj; }
    Object.keys(obj).forEach(k => {
      if(isLocalOnlyKey(k)){
        try{ delete obj[k]; }catch(e){}
        return;
      }
      scrubLocalOnly(obj[k], depth+1);
    });
    return obj;
  }
  function loadLocalUi(){ try { return JSON.parse(localStorage.getItem(LOCAL_UI_STORE) || '{}') || {}; } catch(e) { return {}; } }
  function saveLocalUi(map){ try { localStorage.setItem(LOCAL_UI_STORE, JSON.stringify(map || {})); } catch(e) {} }
  function navName(){ return String(directEval('return typeof mainNav !== "undefined" ? mainNav : ""') || '').toLowerCase() || 'global'; }
  function stableControlKey(el){
    try{
      const bits=[];
      const nav = navName();
      bits.push(nav);
      let label='';
      try{
        const id = el.id || el.getAttribute('id') || '';
        if(id) bits.push('id:'+id);
        const nm = el.name || el.getAttribute('name') || '';
        if(nm) bits.push('name:'+nm);
        const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';
        if(aria) bits.push('aria:'+aria);
        const wrap = el.closest && el.closest('label,.switch,.toggle,.form-check,.control,.setting,.card,.row,li,div');
        if(wrap) label = String(wrap.innerText || wrap.textContent || '').replace(/\s+/g,' ').trim().slice(0,80);
        if(label) bits.push('text:'+label);
      }catch(e){}
      if(bits.length <= 1) bits.push('idx:'+Array.prototype.indexOf.call(document.querySelectorAll('input[type="checkbox"],input[type="radio"],[role="switch"]'), el));
      return bits.join('|').toLowerCase();
    }catch(e){ return 'global|unknown'; }
  }
  function shouldKeepLocal(el){
    try{
      if(!el) return false;
      const type = String(el.type || '').toLowerCase();
      const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
      if(!(type === 'checkbox' || type === 'radio' || role === 'switch')) return false;
      const ctx = String((el.closest && el.closest('.card,.row,.setting,.control,section,div') || document.body).innerText || '').toLowerCase();
      // Business access switch must remain persistent when it represents VIP access/expiry/payment/ledger data.
      if(/app access|vip can use app|expiry|wallet|payment|ledger|entry|deposit|withdraw|balance|profile/.test(ctx)) return false;
      return true;
    }catch(e){ return false; }
  }
  function rememberLocalControl(el){
    try{
      if(!shouldKeepLocal(el)) return;
      const map = loadLocalUi();
      const key = stableControlKey(el);
      map[key] = {checked: !!el.checked, value: el.value, nav: navName(), at: now()};
      saveLocalUi(map);
      try { if(typeof titanMarkUiLocalWrite === 'function') titanMarkUiLocalWrite('local_ui_toggle', 1200); } catch(e) {}
    }catch(e){}
  }
  function applyLocalControls(){
    try{
      const map = loadLocalUi();
      document.querySelectorAll('input[type="checkbox"],input[type="radio"],[role="switch"]').forEach(el => {
        if(!shouldKeepLocal(el)) return;
        const rec = map[stableControlKey(el)];
        if(!rec) return;
        if(!!el.checked !== !!rec.checked){
          el.checked = !!rec.checked;
          try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch(e) {}
        }
      });
    }catch(e){}
  }

  function directSet(nextState){
    try {
      const localMap = loadLocalUi();
      scrubLocalOnly(nextState, 0);
      Function('nextState', `
        appState = nextState;
        try { if(typeof IS_MASTER !== 'undefined' && IS_MASTER) appState.activeId = appState.activeId || 'admin1'; } catch(e) {}
        try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
        try { if(typeof applyPendingLedgerPatchesToState === 'function') applyPendingLedgerPatchesToState(appState); } catch(e) {}
        try { state = appState.profiles[appState.activeId] || appState.profiles['admin1']; } catch(e) {}
        try { if(typeof LOCAL_KEY !== 'undefined') localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
      `)(nextState);
      saveLocalUi(localMap);
      setTimeout(applyLocalControls, 30);
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
  function isProtectedNav(nav){ nav = nav || currentNav(); return nav === 'entries' || nav === 'forward' || nav === 'finance'; }
  function isFinanceNav(){ return currentNav() === 'finance'; }
  function editing(){
    try{
      const el=document.activeElement;
      if(!el) return false;
      const tag=String(el.tagName||'').toUpperCase();
      return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable;
    }catch(e){ return false; }
  }
  function protectedKeywords(nav){
    if(nav === 'finance') return ['finance','deposit','payment','wallet','withdraw','withdrawal','upi','amount','utr','screenshot','proof','balance','credit','debit','history','transaction'];
    if(nav === 'forward') return ['forward','target','schedule','message','template','group','contact','whatsapp','market','load','time'];
    return ['entry','entries','market','time','timing','setting','parser','risk','wallet'];
  }
  function protectedPanelOpen(){
    const nav = currentNav();
    if(!isProtectedNav(nav)) return false;
    try{
      if(now() < protectedHoldUntil && (!protectedHoldNav || protectedHoldNav === nav)) return true;
      const active = document.activeElement;
      if(active && active.closest && active.closest('input,textarea,select,[contenteditable="true"]')) return true;
      const keys = protectedKeywords(nav);
      const openDetails = Array.from(document.querySelectorAll('details[open]')).some(d => {
        const t = String(d.textContent || '').toLowerCase();
        return keys.some(k => t.includes(k));
      });
      if(openDetails) return true;
      const visiblePanels = Array.from(document.querySelectorAll('[id], [class]')).some(el => {
        const key = String((el.id || '') + ' ' + (el.className || '')).toLowerCase();
        if(!keys.some(k => key.includes(k))) return false;
        const cs = window.getComputedStyle(el);
        return cs && cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect && el.getBoundingClientRect().height > 36;
      });
      return !!visiblePanels && now() < protectedHoldUntil + 1200;
    }catch(e){ return now() < protectedHoldUntil; }
  }
  function interacting(){ return now() < interactionUntil; }
  function shouldAvoidRender(force){
    if(protectedPanelOpen()) return true;
    if(force && isProtectedNav() && now() < protectedHoldUntil) return true;
    if(force) return false;
    return document.hidden || editing() || interacting() || now() < pausedUntil || now() < writeLockUntil;
  }
  function touchInteraction(){ interactionUntil = Math.max(interactionUntil, now() + SCROLL_HOLD_MS); }
  function protectedInteraction(){
    const nav = currentNav();
    if(isProtectedNav(nav)){
      protectedHoldNav = nav;
      protectedHoldUntil = Math.max(protectedHoldUntil, now() + TAB_HOLD_MS);
    }
  }
  ['touchstart','touchmove','wheel','scroll','pointerdown'].forEach(ev=>{
    try { window.addEventListener(ev, function(){ touchInteraction(); protectedInteraction(); }, {passive:true, capture:true}); } catch(e) {}
  });
  ['click','change','input','focusin','keydown'].forEach(ev=>{
    try { document.addEventListener(ev, function(e){ protectedInteraction(); if(e && e.target) rememberLocalControl(e.target); }, true); } catch(e) {}
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
    if(protectedPanelOpen()) return;
    try { if(typeof refreshMarketArrays === 'function') refreshMarketArrays(); } catch(e) {}
    try { if(typeof render === 'function') render(true); } catch(e) {}
    setTimeout(applyLocalControls, 30);
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
    if(isProtectedNav()){
      protectedHoldNav = currentNav();
      protectedHoldUntil = Math.max(protectedHoldUntil, now() + Math.max(TAB_HOLD_MS, holdMs || 0));
    }
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
      scrubLocalOnly(next, 0);
      lastRaw = JSON.stringify(next);
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
    try{
      if(init && init.body && method !== 'GET'){
        const ct = String((init.headers && (init.headers['Content-Type'] || init.headers['content-type'])) || '');
        if(ct.includes('json') || String(init.body).trim().startsWith('{')){
          const data = JSON.parse(String(init.body));
          const cleaned = scrubLocalOnly(data, 0);
          init = Object.assign({}, init, {body: JSON.stringify(cleaned)});
        }
      }
    }catch(e){}
    const write = method !== 'GET' && (/\/api\//.test(url) || /\/save(\?|$)/.test(url) || /\/bot_schedule(\?|$)/.test(url));
    if(write) markWrite('fetch_'+method, 1200);
    const p = oldFetch.apply(this, [input, init]);
    if(write){ p.then(()=>scheduleAfterWrite('fetch_done_'+method)).catch(()=>setTimeout(()=>fetchState('fetch_error_'+method, true), 650)); }
    return p;
  };
  try{
    const XHR = window.XMLHttpRequest;
    const oldOpen = XHR.prototype.open;
    const oldSend = XHR.prototype.send;
    XHR.prototype.open = function(method, url){ this.__titanRtMethod=String(method||'GET').toUpperCase(); this.__titanRtUrl=String(url||''); return oldOpen.apply(this, arguments); };
    XHR.prototype.send = function(body){
      try{
        if(body && this.__titanRtMethod !== 'GET' && String(body).trim().startsWith('{')){
          body = JSON.stringify(scrubLocalOnly(JSON.parse(String(body)), 0));
        }
      }catch(e){}
      const write = this.__titanRtMethod !== 'GET' && (/\/api\//.test(this.__titanRtUrl) || /\/save(\?|$)/.test(this.__titanRtUrl) || /\/bot_schedule(\?|$)/.test(this.__titanRtUrl));
      if(write){ markWrite('xhr_'+this.__titanRtMethod, 1200); this.addEventListener('loadend', ()=>scheduleAfterWrite('xhr_done_'+this.__titanRtMethod)); }
      return oldSend.call(this, body);
    };
  }catch(e){}

  document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) setTimeout(()=>fetchState('visible', true), 220); });
  window.addEventListener('focus', ()=>setTimeout(()=>fetchState('focus', true), 220));
  document.addEventListener('titan:force-sync', ()=>fetchState('event', true));
  document.addEventListener('titan:apply-local-ui', applyLocalControls);
  window.__TitanRealtime = {version:VERSION, refresh:(r)=>fetchState(r||'manual', true), markWrite, applyLocalControls, scrubLocalOnly, pause:(ms)=>{pausedUntil=now()+Number(ms||1000)}, pauseEntries:(ms)=>{protectedHoldNav='entries'; protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)}, pauseForward:(ms)=>{protectedHoldNav='forward'; protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)}, pauseFinance:(ms)=>{protectedHoldNav='finance'; protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)}, status:()=>({lastAppliedAt, syncBusy, writeLockUntil, interactionUntil, protectedHoldUntil, protectedHoldNav, pollMs:POLL_MS, localOnlyUiToggles:true})};

  setInterval(()=>fetchState('poll', false), POLL_MS);
  setInterval(applyLocalControls, 1500);
  setTimeout(()=>fetchState('boot', true), 850);
  setTimeout(applyLocalControls, 900);
  console.log('✅ Titan Global Realtime Smooth active', VERSION, 'poll', POLL_MS, 'local-only-ui-toggles');
})();
</script>
'''
