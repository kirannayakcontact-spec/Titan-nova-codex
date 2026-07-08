"""Compact Ledger UI.

Ledger-only design replacement:
Ledger -> ANK/JODI/PENEL -> Card Protocol -> Ledger Auto Pass/Fail.
Old Ledger content is visually covered only while the Ledger tab is active.
"""


def register_ledger_compact_ui(app):
    if getattr(app, "_ledger_compact_ui_registered", False):
        return
    app._ledger_compact_ui_registered = True

    from flask import jsonify, request
    import datetime

    def G():
        v = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(v, "__globals__", {}) or {}

    def now():
        f = G().get("_now_iso_local")
        return f() if callable(f) else datetime.datetime.now().isoformat(timespec="seconds")

    def state():
        f = G().get("migrate_and_get_state")
        return f() if callable(f) else {}

    def put_child(parts, value):
        f = G().get("_firebase_put_child")
        if callable(f):
            f(parts, value)
            return True
        return False

    def put_top(s, updates):
        f = G().get("_firebase_put_top_level_children")
        if callable(f):
            f(s, updates, audit=False)
            return True
        return False

    def active_id(payload=None):
        payload = payload or {}
        return str(payload.get("activeId") or request.args.get("activeId") or "admin1").strip() or "admin1"

    def protocol_from_profile(profile):
        cfg = profile.get("config") if isinstance(profile.get("config"), dict) else {}
        cp = cfg.get("cardProtocol") if isinstance(cfg.get("cardProtocol"), dict) else {}
        out = {}
        defaults = {"ank": 1000, "jodi": 5000, "penel": 8000}
        for k, d in defaults.items():
            rec = cp.get(k) if isinstance(cp.get(k), dict) else {}
            try:
                target = float(rec.get("targetProfit", d) or d)
            except Exception:
                target = d
            out[k] = {"targetProfit": target}
        return out

    def compact_payload(uid="admin1"):
        s = state()
        profiles = s.get("profiles") if isinstance(s.get("profiles"), dict) else {}
        profile = profiles.get(uid) if isinstance(profiles.get(uid), dict) else {}
        ss = s.get("settlementSettings") if isinstance(s.get("settlementSettings"), dict) else {}
        return {
            "status": "success",
            "activeId": uid,
            "cardProtocol": protocol_from_profile(profile),
            "auto": {
                "autoLedgerMarking": ss.get("autoLedgerMarking", True) is not False,
                "autoLedgerMarkOnlyWait": ss.get("autoLedgerMarkOnlyWait", True) is not False,
                "autoLedgerApplyToAllProfiles": ss.get("autoLedgerApplyToAllProfiles", True) is not False,
            },
        }

    @app.route("/api/ledger_compact_ui", methods=["GET"])
    def ledger_compact_get():
        return jsonify(compact_payload(active_id()))

    @app.route("/api/ledger_compact_ui/protocol", methods=["POST"])
    def ledger_compact_protocol_save():
        data = request.get_json(silent=True) or {}
        uid = active_id(data)
        s = state()
        profiles = s.setdefault("profiles", {})
        profile = profiles.setdefault(uid, {"name": uid, "config": {}, "dayRecords": {}})
        cfg = profile.setdefault("config", {})
        cp = cfg.setdefault("cardProtocol", {})
        incoming = data.get("cardProtocol") if isinstance(data.get("cardProtocol"), dict) else {}
        for k in ("ank", "jodi", "penel"):
            rec = incoming.get(k) if isinstance(incoming.get(k), dict) else {}
            cp.setdefault(k, {})
            if "targetProfit" in rec:
                try:
                    cp[k]["targetProfit"] = max(0, float(rec.get("targetProfit") or 0))
                except Exception:
                    pass
            cp[k]["updatedAt"] = now()
        if not put_child(["profiles", uid, "config"], cfg):
            return jsonify({"status": "error", "message": "Firebase profile config save helper missing"}), 500
        return jsonify(compact_payload(uid))

    @app.route("/api/ledger_compact_ui/auto", methods=["POST"])
    def ledger_compact_auto_save():
        data = request.get_json(silent=True) or {}
        s = state()
        ss = s.setdefault("settlementSettings", {})
        for k in ("autoLedgerMarking", "autoLedgerMarkOnlyWait", "autoLedgerApplyToAllProfiles"):
            if k in data:
                ss[k] = bool(data.get(k))
        ss["updatedAt"] = now()
        if not put_top(s, {"settlementSettings": ss}):
            return jsonify({"status": "error", "message": "Firebase settlement save helper missing"}), 500
        return jsonify(compact_payload(active_id(data)))

    @app.after_request
    def compact_ledger_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "ledger-compact-ui-v1" in html or "</body>" not in html.lower():
                return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + UI + html[i:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


UI = r'''
<style id="ledger-compact-ui-v1-style">
#lcui{position:fixed;inset:0;z-index:9000;background:linear-gradient(180deg,#07111f,#050b12);color:#eef6ff;font-family:Inter,Arial,sans-serif;overflow:auto;padding:14px 12px 82px;box-sizing:border-box;display:none}#lcui.on{display:block}.lcTop{display:flex;justify-content:space-between;gap:10px;align-items:center}.lcTitle{font-size:22px;font-weight:1000}.lcSub{font-size:11px;color:#91afd1;margin-top:3px}.lcCard{background:#101d2f;border:1px solid rgba(42,171,238,.28);border-radius:20px;padding:13px;margin-top:12px;box-shadow:0 12px 28px rgba(0,0,0,.23)}.lcTabs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px}.lcTabs button,.lcBtn{border:0;border-radius:14px;padding:11px 8px;background:#172d42;color:#cfe8ff;font-weight:1000}.lcTabs button.on{background:#2aabee;color:white}.lcHead{font-size:13px;font-weight:1000;margin-bottom:8px}.lcGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.lcMetric{background:#07111f;border:1px solid #243e5f;border-radius:15px;padding:10px}.lcMetric b{display:block;font-size:16px}.lcMetric span{font-size:10px;color:#91afd1}.lcInput{width:100%;box-sizing:border-box;background:#07111f;border:1px solid #294564;border-radius:13px;color:white;padding:12px;font-size:16px}.lcSave{background:#00c26f!important;color:#062013!important;width:100%;margin-top:10px}.lcSwitch{display:flex;align-items:center;justify-content:space-between;background:#07111f;border:1px solid #243e5f;border-radius:15px;padding:11px;margin-top:8px;font-size:12px;font-weight:900}.lcBottom{position:fixed;left:0;right:0;bottom:0;z-index:9001;background:#08131f;border-top:1px solid #203952;display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:8px}.lcBottom button{border:0;border-radius:13px;padding:10px 4px;background:#101d2f;color:#bfe7ff;font-size:10px;font-weight:1000}
</style>
<script id="ledger-compact-ui-v1">
(function(){if(window.__LCUI)return;window.__LCUI=true;const API='/api/ledger_compact_ui';let game='ank',data=null;function q(s){return document.querySelector(s)}function gv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return''}}function sv(n,v){try{Function('v',n+'=v')(v)}catch(e){}}function state(){try{return appState||{}}catch(e){return {}}}function uid(){return state().activeId||'admin1'}function inLedger(){return String(gv('mainNav')||'').toLowerCase()==='ledger'}function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}function today(){try{return currentDate||new Date().toISOString().slice(0,10)}catch(e){return new Date().toISOString().slice(0,10)}}function bucket(){let s=state(),p=(s.profiles||{})[uid()]||{},d=((p.dayRecords||{})[today()]||{});return game==='ank'?(d.data||{}):game==='jodi'?(d.jodiData||{}):(d.pannelData||{})}function metrics(){let vals=Object.values(bucket()).filter(x=>x&&typeof x==='object'),wait=0,pass=0,fail=0;vals.forEach(r=>{let st=String(r.s||'WAIT').toUpperCase();if(st==='PASS')pass++;else if(st==='FAIL')fail++;else wait++});return {cards:vals.length,wait,pass,fail}}function ensure(){let el=q('#lcui');if(!el){document.body.insertAdjacentHTML('beforeend',html());bind();el=q('#lcui')}if(inLedger()){el.classList.add('on');render()}else el.classList.remove('on')}function html(){return '<div id="lcui"><div class="lcTop"><div><div class="lcTitle">Ledger</div><div class="lcSub">ANK → JODI → PENEL · Compact Control</div></div><button class="lcBtn" id="lcRefresh">Refresh</button></div><div class="lcTabs"><button data-g="ank">ANK</button><button data-g="jodi">JODI</button><button data-g="penel">PENEL</button></div><div class="lcCard"><div class="lcHead" id="lcGameTitle">ANK</div><div class="lcGrid"><div class="lcMetric"><b id="lcCards">0</b><span>Cards</span></div><div class="lcMetric"><b id="lcWait">0</b><span>WAIT</span></div><div class="lcMetric"><b id="lcPass">0</b><span>PASS</span></div><div class="lcMetric"><b id="lcFail">0</b><span>FAIL</span></div></div></div><div class="lcCard"><div class="lcHead">Card Protocol</div><div class="lcSub" id="lcProtocolLabel">ANK set target profit</div><input id="lcTarget" class="lcInput" type="number" min="0" step="1" placeholder="Target profit"><button id="lcSaveProtocol" class="lcBtn lcSave">Save Card Protocol</button></div><div class="lcCard"><div class="lcHead">Ledger Auto Pass / Fail</div><label class="lcSwitch">Auto Mark <input id="lcAutoMark" type="checkbox"></label><label class="lcSwitch">Only WAIT <input id="lcOnlyWait" type="checkbox"></label><label class="lcSwitch">All VIPs <input id="lcAllVips" type="checkbox"></label><button id="lcSaveAuto" class="lcBtn lcSave">Save Auto Pass/Fail</button></div><div class="lcBottom"><button data-nav="ledger">Ledger</button><button data-nav="results">Results</button><button data-nav="market">Market</button><button data-nav="finance">Finance</button></div></div>'}function bind(){document.querySelectorAll('#lcui [data-g]').forEach(b=>b.onclick=()=>{game=b.dataset.g;render()});q('#lcRefresh').onclick=load;q('#lcSaveProtocol').onclick=saveProtocol;q('#lcSaveAuto').onclick=saveAuto;document.querySelectorAll('#lcui [data-nav]').forEach(b=>b.onclick=()=>{sv('mainNav',b.dataset.nav);try{if(typeof render==='function')render(true)}catch(e){}ensure()})}async function load(){try{let r=await fetch(API+'?activeId='+encodeURIComponent(uid())+'&_='+Date.now(),{cache:'no-store',headers:headers()});data=await r.json();render()}catch(e){}}function render(){if(!q('#lcui'))return;document.querySelectorAll('#lcui [data-g]').forEach(b=>b.classList.toggle('on',b.dataset.g===game));let m=metrics();q('#lcGameTitle').textContent=game.toUpperCase();q('#lcCards').textContent=m.cards;q('#lcWait').textContent=m.wait;q('#lcPass').textContent=m.pass;q('#lcFail').textContent=m.fail;q('#lcProtocolLabel').textContent=game.toUpperCase()+' set target profit';if(data){let cp=(data.cardProtocol||{})[game]||{};q('#lcTarget').value=cp.targetProfit||'';let a=data.auto||{};q('#lcAutoMark').checked=!!a.autoLedgerMarking;q('#lcOnlyWait').checked=!!a.autoLedgerMarkOnlyWait;q('#lcAllVips').checked=!!a.autoLedgerApplyToAllProfiles}}async function saveProtocol(){try{let cp=data&&data.cardProtocol?data.cardProtocol:{ank:{},jodi:{},penel:{}};cp[game]=cp[game]||{};cp[game].targetProfit=Number(q('#lcTarget').value||0);let r=await fetch(API+'/protocol',{method:'POST',headers:headers(),body:JSON.stringify({activeId:uid(),cardProtocol:cp})});let j=await r.json();if(j.status!=='success')throw Error(j.message||'Save failed');data=j;alert('✅ '+game.toUpperCase()+' protocol saved')}catch(e){alert('❌ '+e.message)}}async function saveAuto(){try{let body={activeId:uid(),autoLedgerMarking:q('#lcAutoMark').checked,autoLedgerMarkOnlyWait:q('#lcOnlyWait').checked,autoLedgerApplyToAllProfiles:q('#lcAllVips').checked};let r=await fetch(API+'/auto',{method:'POST',headers:headers(),body:JSON.stringify(body)});let j=await r.json();if(j.status!=='success')throw Error(j.message||'Save failed');data=j;alert('✅ Auto Pass/Fail saved')}catch(e){alert('❌ '+e.message)}}document.addEventListener('click',()=>setTimeout(ensure,120),true);setInterval(ensure,1000);setTimeout(()=>{ensure();load()},700)})();
</script>
'''
