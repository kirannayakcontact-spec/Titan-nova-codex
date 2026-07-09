"""Result tab checkbox sticky persistence.

Fixes Result tab toggles reverting after realtime sync by:
- registering a small API endpoint that persists known Result/Settlement/Auto Pass-Fail toggles
- injecting a browser guard that reapplies the last selected checkbox state after UI refresh/re-render
- writing broad legacy-compatible state keys so the monolith can read whichever settings shape it already uses
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

    def as_dict(value):
        return value if isinstance(value, dict) else {}

    def boolish(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("1", "true", "yes", "on", "checked", "enable", "enabled")

    def toggle_bundle(ui_key, val):
        """Return broad state updates for legacy/new result-tab toggle names."""
        val = boolish(val)
        updates = {"resultToggleSticky": {ui_key: val}}
        if ui_key == "settlementOn":
            updates.update({
                "resultSettlement": {"enabled": val, "settlementOn": val},
                "settlementSettings": {"enabled": val, "settlementOn": val},
                "resultSettings": {"settlementEnabled": val, "settlementOn": val},
            })
        elif ui_key == "msgSummary":
            updates.update({
                "resultSettlement": {"msgSummary": val, "messageSummary": val},
                "settlementSettings": {"msgSummary": val, "messageSummary": val},
                "resultSettings": {"msgSummary": val, "messageSummary": val},
            })
        elif ui_key == "autoHitMiss":
            updates.update({
                "ledgerAutoPassFail": {"enabled": val, "autoHitMiss": val},
                "autoPassFailSettings": {"enabled": val, "autoHitMiss": val},
                "resultSettings": {"autoHitMiss": val, "autoPassFail": val},
                "autoResultSettings": {"autoHitMiss": val, "autoPassFail": val},
            })
        elif ui_key == "autoMark":
            updates.update({
                "ledgerAutoPassFail": {"autoMark": val},
                "autoPassFailSettings": {"autoMark": val},
                "resultSettings": {"autoMark": val},
                "autoResultSettings": {"autoMark": val},
            })
        elif ui_key == "onlyWait":
            updates.update({
                "ledgerAutoPassFail": {"onlyWait": val, "waitOnly": val},
                "autoPassFailSettings": {"onlyWait": val, "waitOnly": val},
                "resultSettings": {"onlyWait": val, "waitOnly": val},
            })
        elif ui_key == "allVips":
            updates.update({
                "ledgerAutoPassFail": {"allVips": val, "includeAllVips": val},
                "autoPassFailSettings": {"allVips": val, "includeAllVips": val},
                "resultSettings": {"allVips": val, "includeAllVips": val},
            })
        elif ui_key:
            updates.update({"resultSettings": {ui_key: val}, "autoResultSettings": {ui_key: val}})
        return updates

    def merge_into_state(state, grouped_updates):
        changed = {}
        for top_key, patch in grouped_updates.items():
            if not isinstance(patch, dict):
                state[top_key] = patch
                changed[top_key] = patch
                continue
            cur = as_dict(state.get(top_key)).copy()
            cur.update(patch)
            state[top_key] = cur
            for k, v in patch.items():
                changed[f"{top_key}.{k}"] = v
        return changed

    @app.route("/api/result_toggle_sticky", methods=["GET", "POST"])
    def result_toggle_sticky_api():
        state = state_now()
        if request.method == "GET":
            sticky = as_dict(state.get("resultToggleSticky"))
            return jsonify({
                "status": "success",
                "resultToggleSticky": sticky,
                "resultSettings": as_dict(state.get("resultSettings")),
                "autoResultSettings": as_dict(state.get("autoResultSettings")),
                "resultSettlement": as_dict(state.get("resultSettlement")),
                "ledgerAutoPassFail": as_dict(state.get("ledgerAutoPassFail")),
            })

        data = request.get_json(silent=True) or {}
        grouped = {}

        # Preferred compact payload from injected JS: { key:'autoMark', value:true }
        ui_key = str(data.get("key") or data.get("uiKey") or "").strip()
        if ui_key:
            grouped.update(toggle_bundle(ui_key, data.get("value")))

        # Backward-compatible payloads from older script.
        for possible in ("settlementOn", "msgSummary", "autoHitMiss", "autoMark", "onlyWait", "allVips"):
            if possible in data:
                bundle = toggle_bundle(possible, data.get(possible))
                for top, patch in bundle.items():
                    grouped.setdefault(top, {}).update(patch)

        for top in ("resultSettings", "autoResultSettings", "resultSettlement", "settlementSettings", "ledgerAutoPassFail", "autoPassFailSettings"):
            if isinstance(data.get(top), dict):
                grouped.setdefault(top, {}).update(data[top])

        if not grouped:
            return jsonify({"status": "noop", "resultToggleSticky": True, "changed": {}})

        changed = merge_into_state(state, grouped)
        ok_all = True
        for top_key in grouped.keys():
            ok_all = put_child([top_key], state.get(top_key)) and ok_all
        if not ok_all:
            put_top(state, {k: state.get(k) for k in grouped.keys()})
        return jsonify({
            "status": "success",
            "resultToggleSticky": as_dict(state.get("resultToggleSticky")),
            "changed": changed,
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
            if not html or "result-toggle-sticky-v2" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="result-toggle-sticky-v2">
(function(){
  if(window.__RESULT_TOGGLE_STICKY_V2__) return;
  window.__RESULT_TOGGLE_STICKY_V2__ = true;
  const API='/api/result_toggle_sticky';
  const LS='titan.result.toggle.sticky.v2';
  const labels={
    settlementOn:/\bSETTLEMENT\s+ON\b/i,
    msgSummary:/\bMSG\s+SUMMARY\b|\bMESSAGE\s+SUMMARY\b/i,
    autoHitMiss:/\bAUTO\s+HIT\/?MISS\b/i,
    autoMark:/\bAUTO\s+MARK\b/i,
    onlyWait:/\bONLY\s+WAIT\b/i,
    allVips:/\bALL\s+VIPS\b/i
  };
  let sticky={};
  let saving=false;
  let lastLoad=0;
  function readLS(){try{return JSON.parse(localStorage.getItem(LS)||'{}')||{}}catch(e){return {}}}
  function writeLS(){try{localStorage.setItem(LS,JSON.stringify(sticky||{}))}catch(e){}}
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||localStorage.getItem('titan_admin_token')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  function pageText(){return String(document.body&&document.body.innerText||'')}
  function resultVisible(){return /RESULT\s+SETTLEMENT|LEDGER\s+AUTO\s+PASS\/FAIL|MARKET\s+RESULTS/i.test(pageText())}
  function clean(s){return String(s||'').replace(/\s+/g,' ').trim()}
  function nearText(el){let s='';let n=el;for(let i=0;i<7&&n;i++,n=n.parentElement){s+=' '+clean(n.innerText||n.textContent||'')}return s.slice(0,900)}
  function keyFor(el){const s=nearText(el);for(const [k,re] of Object.entries(labels)){if(re.test(s))return k}return ''}
  function boxes(){return Array.from(document.querySelectorAll('input[type="checkbox"],input[type="radio"]')).filter(el=>keyFor(el))}
  function applySticky(){
    if(!resultVisible()) return;
    for(const el of boxes()){
      const k=keyFor(el);
      if(!k || typeof sticky[k] === 'undefined') continue;
      const want=!!sticky[k];
      if(el.checked!==want){
        el.checked=want;
        try{el.setAttribute('aria-checked', String(want));}catch(e){}
      }
    }
  }
  async function loadRemote(force){
    const now=Date.now();
    if(!force && now-lastLoad<8000) return;
    lastLoad=now;
    try{
      const r=await fetch(API,{cache:'no-store',headers:headers()});
      const j=await r.json();
      const remote=(j&&j.resultToggleSticky)||{};
      sticky=Object.assign({}, readLS(), remote);
      writeLS();
      applySticky();
    }catch(e){sticky=Object.assign({}, sticky, readLS()); applySticky();}
  }
  async function save(k,v){
    if(!k) return;
    sticky[k]=!!v; writeLS(); applySticky(); saving=true;
    try{if(window.__TitanRealtime&&window.__TitanRealtime.pause)window.__TitanRealtime.pause(5000)}catch(e){}
    try{await fetch(API,{method:'POST',headers:headers(),body:JSON.stringify({key:k,value:!!v})});}
    catch(e){console.warn('result toggle sticky save failed',e)}
    finally{saving=false; setTimeout(()=>loadRemote(true),700)}
  }
  document.addEventListener('change',function(ev){
    const el=ev.target;
    if(!el||!/^(INPUT)$/i.test(el.tagName||''))return;
    if(!/^(checkbox|radio)$/i.test(el.type||''))return;
    const k=keyFor(el); if(!k)return;
    save(k,!!el.checked);
  },true);
  document.addEventListener('click',function(ev){
    setTimeout(function(){const el=ev.target&&ev.target.closest?ev.target.closest('input[type="checkbox"],input[type="radio"]'):null;if(el){const k=keyFor(el);if(k)save(k,!!el.checked)}},30);
  },true);
  const mo=new MutationObserver(function(){ if(!saving) applySticky(); });
  try{mo.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['checked','class','style']});}catch(e){}
  sticky=readLS();
  loadRemote(true);
  setInterval(function(){applySticky();loadRemote(false)},600);
})();
</script>
'''
