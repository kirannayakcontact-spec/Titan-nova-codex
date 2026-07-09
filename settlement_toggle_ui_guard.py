"""UI guard for settlement toggles.

Captures Settlement/Msg Summary/Auto HitMiss/Auto Mark/Only WAIT/All VIPs changes
and persists settlementSettings through sticky API immediately.
"""


def register_settlement_toggle_ui_guard(app):
    if getattr(app, "_titan_settlement_toggle_ui_guard_registered", False):
        return
    app._titan_settlement_toggle_ui_guard_registered = True

    from flask import request

    @app.after_request
    def settlement_toggle_ui_guard_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "settlement-toggle-sticky-ui-v2" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="settlement-toggle-sticky-ui-v2">
(function(){
  if(window.__TITAN_SETTLEMENT_TOGGLE_STICKY_UI__) return;
  window.__TITAN_SETTLEMENT_TOGGLE_STICKY_UI__ = true;
  const ST_API='/api/settlement_toggle_sticky';
  const ST_LABEL_MAP = [
    ['SETTLEMENT ON','enabled'],
    ['MSG SUMMARY','includeSummaryInResultMessage'],
    ['AUTO HIT/MISS','includeHitMissInResultMessage'],
    ['AUTO MARK','autoLedgerMarking'],
    ['ONLY WAIT','autoLedgerMarkOnlyWait'],
    ['ALL VIPS','autoLedgerApplyToAllProfiles']
  ];
  function stText(e){return ((e&&e.textContent)||'').replace(/\s+/g,' ').trim().toUpperCase();}
  function stGetSettings(){try{return (appState.settlementSettings=appState.settlementSettings||{})}catch(e){return {}}}
  function stHeaders(){const h={'Content-Type':'application/json'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t;}catch(e){}return h;}
  function stClosestLabel(el){
    let n=el;
    for(let i=0;i<6&&n;i++,n=n.parentElement){
      const t=stText(n);
      for(const pair of ST_LABEL_MAP){ if(t.includes(pair[0])) return pair; }
    }
    return null;
  }
  async function stSave(key, val){
    const s=stGetSettings(); s[key]=!!val; try{ if(typeof titanMarkUiLocalWrite==='function') titanMarkUiLocalWrite('settlement_toggle_'+key,3500); }catch(e){}
    try{ if(window.__TitanRealtime) window.__TitanRealtime.pause(1500); }catch(e){}
    try{
      const r=await fetch(ST_API,{method:'POST',headers:stHeaders(),body:JSON.stringify(s)});
      const j=await r.json().catch(()=>({}));
      if(j&&j.settlementSettings){try{appState.settlementSettings=j.settlementSettings;}catch(e){}}
      try{document.dispatchEvent(new CustomEvent('titan:force-sync'));}catch(e){}
    }catch(e){console.warn('settlement sticky save failed',e);}
  }
  document.addEventListener('change',function(ev){
    const el=ev.target;
    if(!el||String(el.tagName||'').toUpperCase()!=='INPUT') return;
    const type=String(el.type||'').toLowerCase();
    if(type!=='checkbox'&&type!=='radio') return;
    const hit=stClosestLabel(el);
    if(!hit) return;
    stSave(hit[1], !!el.checked);
  }, true);
  document.addEventListener('click',function(ev){
    const hit=stClosestLabel(ev.target);
    if(!hit) return;
    setTimeout(function(){
      try{
        const s=stGetSettings();
        if(typeof s[hit[1]]==='boolean') stSave(hit[1], s[hit[1]]);
      }catch(e){}
    },120);
  }, true);
})();
</script>
'''
