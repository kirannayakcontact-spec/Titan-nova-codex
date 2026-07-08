"""Result tab toggle sticky save.

Fixes Result tab toggles reverting after realtime sync by persisting the owning
state children immediately. No new UI surface is created.
"""


def register_result_toggle_sticky(app):
    if getattr(app, "_result_toggle_sticky_registered", False):
        return
    app._result_toggle_sticky_registered = True

    from flask import jsonify, request

    def G():
        view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(view, "__globals__", {}) or {}

    def fn(name, default=None):
        return G().get(name, default)

    def state_now():
        f = fn("migrate_and_get_state")
        return f() if callable(f) else {}

    def put_child(parts, value):
        f = fn("_firebase_put_child")
        if callable(f):
            f(parts, value)
            return True
        return False

    def put_top(state, updates):
        f = fn("_firebase_put_top_level_children")
        if callable(f):
            f(state, updates, audit=False)
            return True
        return False

    @app.route("/api/result_toggle_sticky", methods=["POST"])
    def result_toggle_sticky_api():
        data = request.get_json(silent=True) or {}
        state = state_now()
        result_settings = state.get("resultSettings") if isinstance(state.get("resultSettings"), dict) else {}
        auto_settings = state.get("autoResultSettings") if isinstance(state.get("autoResultSettings"), dict) else {}

        allowed_result = {
            "enabled", "autoSend", "sendToGroups", "useForwardTargetsForResults",
            "declareOpen", "declareClose", "notifyAdmin", "resultEnabled",
            "autoResultEnabled", "autoDeclare", "manualDeclareEnabled",
        }
        allowed_auto = {
            "enabled", "autoSend", "autoDeclare", "scrapeEnabled", "openEnabled",
            "closeEnabled", "sendOpen", "sendClose", "resultEnabled",
        }

        changed = {}
        for k, v in data.items():
            if k in allowed_result:
                result_settings[k] = bool(v)
                changed["resultSettings." + k] = bool(v)
            if k in allowed_auto:
                auto_settings[k] = bool(v)
                changed["autoResultSettings." + k] = bool(v)

        # Generic nested support from UI guard.
        rs = data.get("resultSettings") if isinstance(data.get("resultSettings"), dict) else None
        ar = data.get("autoResultSettings") if isinstance(data.get("autoResultSettings"), dict) else None
        if rs:
            for k, v in rs.items():
                result_settings[k] = bool(v) if isinstance(v, bool) else v
                changed["resultSettings." + k] = result_settings[k]
        if ar:
            for k, v in ar.items():
                auto_settings[k] = bool(v) if isinstance(v, bool) else v
                changed["autoResultSettings." + k] = auto_settings[k]

        state["resultSettings"] = result_settings
        state["autoResultSettings"] = auto_settings
        ok1 = put_child(["resultSettings"], result_settings)
        ok2 = put_child(["autoResultSettings"], auto_settings)
        if not (ok1 and ok2):
            put_top(state, {"resultSettings": result_settings, "autoResultSettings": auto_settings})
        return jsonify({
            "status": "success",
            "resultToggleSticky": True,
            "changed": changed,
            "resultSettings": result_settings,
            "autoResultSettings": auto_settings,
        })

    @app.after_request
    def result_toggle_sticky_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "result-toggle-sticky-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="result-toggle-sticky-v1">
(function(){
  if(window.__RESULT_TOGGLE_STICKY_V1__) return;
  window.__RESULT_TOGGLE_STICKY_V1__ = true;
  const API='/api/result_toggle_sticky';
  function gv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return ''}}
  function nav(){return String(gv('mainNav')||'').toLowerCase()}
  function inResult(){return nav()==='results'||nav()==='result'}
  function txt(e){return String((e&&e.textContent)||'').replace(/\s+/g,' ').trim().toUpperCase()}
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  function keyFor(el){
    let s=''; let n=el;
    for(let i=0;i<5&&n;i++,n=n.parentElement) s+=' '+txt(n);
    if(/AUTO\s*RESULT|AUTO\s*DECLARE|AUTO\s*SEND/.test(s)) return 'autoSend';
    if(/SCRAPE|AUTO\s*SCRAP/.test(s)) return 'scrapeEnabled';
    if(/OPEN/.test(s)&&/RESULT|SEND|DECLARE/.test(s)) return 'sendOpen';
    if(/CLOSE/.test(s)&&/RESULT|SEND|DECLARE/.test(s)) return 'sendClose';
    if(/FORWARD/.test(s)) return 'useForwardTargetsForResults';
    if(/GROUP/.test(s)) return 'sendToGroups';
    if(/ADMIN/.test(s)&&/NOTIFY|MSG/.test(s)) return 'notifyAdmin';
    if(/RESULT/.test(s)&&/ON|ENABLE|ACTIVE/.test(s)) return 'enabled';
    return '';
  }
  async function save(key,val){
    if(!key) return;
    try{if(window.__TitanRealtime&&window.__TitanRealtime.pauseResult)window.__TitanRealtime.pauseResult(10000);else if(window.__TitanRealtime&&window.__TitanRealtime.pause)window.__TitanRealtime.pause(3500)}catch(e){}
    try{
      const body={}; body[key]=!!val;
      if(['scrapeEnabled','sendOpen','sendClose'].includes(key)) body.autoResultSettings={[key]:!!val};
      else body.resultSettings={[key]:!!val};
      await fetch(API,{method:'POST',headers:headers(),body:JSON.stringify(body)});
      try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}
    }catch(e){console.warn('result toggle sticky save failed',e)}
  }
  document.addEventListener('change',function(ev){
    if(!inResult()) return;
    const el=ev.target;
    if(!el||String(el.tagName||'').toUpperCase()!=='INPUT') return;
    const type=String(el.type||'').toLowerCase();
    if(type!=='checkbox'&&type!=='radio') return;
    save(keyFor(el),!!el.checked);
  },true);
})();
</script>
'''
