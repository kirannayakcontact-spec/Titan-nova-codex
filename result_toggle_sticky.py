"""Result tab checkbox sticky persistence.

v3 fix: each Result tab checkbox maps only to its own nearest control label.
Old bad sticky data from v2 is ignored so one checkbox cannot turn every checkbox on.
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
        val = boolish(val)
        updates = {"resultToggleSticky": {"_version": "v3", ui_key: val}}
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
            if sticky.get("_version") != "v3":
                sticky = {"_version": "v3"}
            return jsonify({
                "status": "success",
                "resultToggleSticky": sticky,
                "resultSettings": as_dict(state.get("resultSettings")),
                "autoResultSettings": as_dict(state.get("autoResultSettings")),
                "resultSettlement": as_dict(state.get("resultSettlement")),
                "ledgerAutoPassFail": as_dict(state.get("ledgerAutoPassFail")),
            })

        data = request.get_json(silent=True) or {}
        if data.get("reset") is True:
            state["resultToggleSticky"] = {"_version": "v3"}
            put_child(["resultToggleSticky"], state["resultToggleSticky"]) or put_top(state, {"resultToggleSticky": state["resultToggleSticky"]})
            return jsonify({"status": "success", "reset": True, "resultToggleSticky": state["resultToggleSticky"]})

        grouped = {}
        ui_key = str(data.get("key") or data.get("uiKey") or "").strip()
        if ui_key:
            grouped.update(toggle_bundle(ui_key, data.get("value")))

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
            if not html or "result-toggle-sticky-v3" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


SCRIPT = r'''
<script id="result-toggle-sticky-v3">
(function(){
  if(window.__RESULT_TOGGLE_STICKY_V3__) return;
  window.__RESULT_TOGGLE_STICKY_V3__ = true;
  const API='/api/result_toggle_sticky';
  const LS='titan.result.toggle.sticky.v3';
  const keys=['settlementOn','msgSummary','autoHitMiss','autoMark','onlyWait','allVips'];
  let sticky={_version:'v3'};
  let saving=false;
  let lastLoad=0;
  function readLS(){try{const v=JSON.parse(localStorage.getItem(LS)||'{}')||{};return v._version==='v3'?v:{_version:'v3'}}catch(e){return {_version:'v3'}}}
  function writeLS(){try{sticky._version='v3';localStorage.setItem(LS,JSON.stringify(sticky||{}))}catch(e){}}
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||localStorage.getItem('titan_admin_token')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  function textOf(n){return String((n&&((n.innerText||n.textContent||n.getAttribute&&n.getAttribute('aria-label'))))||'').replace(/\s+/g,' ').trim()}
  function resultVisible(){return /RESULT\s+SETTLEMENT|LEDGER\s+AUTO\s+PASS\/FAIL|MARKET\s+RESULTS/i.test(textOf(document.body))}
  function ownText(el){
    const parts=[];
    if(el.id){try{document.querySelectorAll('label[for="'+CSS.escape(el.id)+'"]').forEach(l=>parts.push(textOf(l)))}catch(e){}}
    const aria=el.getAttribute&&el.getAttribute('aria-label'); if(aria) parts.push(aria);
    let n=el.parentElement;
    for(let depth=0;n&&depth<4;depth++,n=n.parentElement){
      const t=textOf(n);
      if(!t) continue;
      const inputCount=n.querySelectorAll?n.querySelectorAll('input[type="checkbox"],input[type="radio"]').length:0;
      // Use only the nearest small control container. Never use the whole Result section/card.
      if(inputCount<=1 && t.length<=90){parts.push(t);break;}
      const direct=[];
      for(const c of Array.from(n.childNodes||[])){
        if(c===el) continue;
        if(c.nodeType===3) direct.push(c.textContent||'');
        else if(c.nodeType===1 && !/INPUT/i.test(c.tagName||'')){
          const ct=textOf(c);
          if(ct && ct.length<=60) direct.push(ct);
        }
      }
      const d=direct.join(' ').replace(/\s+/g,' ').trim();
      if(d && d.length<=90){parts.push(d);break;}
    }
    return parts.join(' ').replace(/\s+/g,' ').trim();
  }
  function keyFor(el){
    const s=ownText(el).toUpperCase();
    if(!s) return '';
    if(/\bSETTLEMENT\s+ON\b/.test(s)) return 'settlementOn';
    if(/\bMSG\s+SUMMARY\b|\bMESSAGE\s+SUMMARY\b/.test(s)) return 'msgSummary';
    if(/\bAUTO\s+HIT\/?MISS\b/.test(s)) return 'autoHitMiss';
    if(/\bAUTO\s+MARK\b/.test(s)) return 'autoMark';
    if(/\bONLY\s+WAIT\b/.test(s)) return 'onlyWait';
    if(/\bALL\s+VIPS\b/.test(s)) return 'allVips';
    return '';
  }
  function boxes(){
    if(!resultVisible()) return [];
    return Array.from(document.querySelectorAll('input[type="checkbox"],input[type="radio"]')).filter(el=>!!keyFor(el));
  }
  function applySticky(){
    if(!resultVisible()) return;
    for(const el of boxes()){
      const k=keyFor(el);
      if(!k || typeof sticky[k] === 'undefined') continue;
      const want=!!sticky[k];
      if(el.checked!==want){el.checked=want;try{el.setAttribute('aria-checked',String(want))}catch(e){}}
    }
  }
  async function loadRemote(force){
    const now=Date.now();
    if(!force && now-lastLoad<8000) return;
    lastLoad=now;
    try{
      const r=await fetch(API,{cache:'no-store',headers:headers()});
      const j=await r.json();
      const remote=(j&&j.resultToggleSticky&&j.resultToggleSticky._version==='v3')?j.resultToggleSticky:{};
      sticky=Object.assign({_version:'v3'}, readLS(), remote);
      writeLS(); applySticky();
    }catch(e){sticky=Object.assign({_version:'v3'}, sticky, readLS()); applySticky();}
  }
  async function save(k,v){
    if(!k || !keys.includes(k)) return;
    sticky[k]=!!v; sticky._version='v3'; writeLS(); saving=true;
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
    setTimeout(function(){
      const el=ev.target&&ev.target.closest?ev.target.closest('input[type="checkbox"],input[type="radio"]'):null;
      if(el){const k=keyFor(el);if(k)save(k,!!el.checked)}
    },40);
  },true);
  const mo=new MutationObserver(function(){ if(!saving) applySticky(); });
  try{mo.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['checked','class','style']});}catch(e){}
  try{localStorage.removeItem('titan.result.toggle.sticky.v2')}catch(e){}
  sticky=readLS();
  loadRemote(true);
  setInterval(function(){applySticky();loadRemote(false)},900);
})();
</script>
'''
