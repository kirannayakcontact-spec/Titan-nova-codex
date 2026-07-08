"""Ledger tab Market Settings panel and sticky save API.

Moves practical market controls into Ledger without removing existing features.
Saves directly to marketRegistry so settings do not revert after refresh/realtime sync.
"""


def register_ledger_market_settings(app):
    if getattr(app, "_titan_ledger_market_settings_registered", False):
        return
    app._titan_ledger_market_settings_registered = True

    from flask import jsonify, request
    import datetime
    import re

    def lg():
        view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(view, "__globals__", {}) or {}

    def now_iso():
        fn = lg().get("_now_iso_local")
        return fn() if callable(fn) else datetime.datetime.now().isoformat(timespec="seconds")

    def norm_hhmm(v):
        v = str(v or "").strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", v)
        if not m:
            return ""
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
        return ""

    def slug(name):
        fn = lg().get("_market_slug")
        if callable(fn):
            try:
                return fn(name)
            except Exception:
                pass
        return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_") or "market"

    def get_state():
        fn = lg().get("migrate_and_get_state")
        if callable(fn):
            return fn()
        return {}

    def ensure_reg(state):
        fn = lg().get("_ensure_market_registry")
        if callable(fn):
            return fn(state)
        reg = state.setdefault("marketRegistry", {})
        reg.setdefault("items", {})
        return reg

    def save_reg(state, reg):
        reg["updatedAt"] = now_iso()
        state["marketRegistry"] = reg
        entry = state.setdefault("entrySettings", {})
        close_times = entry.setdefault("marketCloseTimes", {})
        for item in (reg.get("items") or {}).values():
            if not isinstance(item, dict):
                continue
            name = str(item.get("displayName") or item.get("name") or "").strip().upper()
            close_time = ((item.get("times") or {}).get("close") or "") if isinstance(item.get("times"), dict) else ""
            open_time = ((item.get("times") or {}).get("open") or "") if isinstance(item.get("times"), dict) else ""
            if name:
                if close_time:
                    close_times[name] = close_time
                    close_times[name + " CLOSE"] = close_time
                if open_time:
                    close_times[name + " OPEN"] = open_time
        put = lg().get("_firebase_put_top_level_children")
        if callable(put):
            put(state, {"marketRegistry": reg, "entrySettings": entry}, audit=False)
            return True
        return False

    def serialize(state):
        reg = ensure_reg(state)
        items = []
        for item in (reg.get("items") or {}).values():
            if not isinstance(item, dict) or item.get("deleted"):
                continue
            times = item.get("times") if isinstance(item.get("times"), dict) else {}
            stages = item.get("stages") if isinstance(item.get("stages"), dict) else {}
            items.append({
                "id": item.get("id") or slug(item.get("displayName") or item.get("name")),
                "name": str(item.get("displayName") or item.get("name") or "").strip().upper(),
                "websiteName": item.get("websiteName") or item.get("displayName") or item.get("name") or "",
                "enabled": item.get("enabled", True) is not False,
                "ledgerEnabled": item.get("ledgerEnabled", True) is not False,
                "resultEnabled": item.get("resultEnabled", True) is not False,
                "autoResultEnabled": item.get("autoResultEnabled", True) is not False,
                "autoPassFailEnabled": item.get("autoPassFailEnabled", True) is not False,
                "scheduleEnabled": item.get("scheduleEnabled", True) is not False,
                "openStage": stages.get("open", True) is not False,
                "closeStage": stages.get("close", True) is not False,
                "openTime": norm_hhmm(times.get("open")),
                "closeTime": norm_hhmm(times.get("close")),
                "chartUrl": item.get("chartUrl") or "",
                "sortOrder": item.get("sortOrder") or 9999,
            })
        items.sort(key=lambda x: (str(x.get("openTime") or "99:99"), str(x.get("name") or "")))
        return {"status": "success", "marketRegistry": reg, "markets": items, "count": len(items)}

    @app.route("/api/ledger_market_settings", methods=["GET"])
    def ledger_market_settings_load():
        try:
            return jsonify(serialize(get_state()))
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/ledger_market_settings", methods=["POST"])
    def ledger_market_settings_save():
        try:
            payload = request.get_json(silent=True) or {}
            state = get_state()
            reg = ensure_reg(state)
            items = reg.setdefault("items", {})
            stamp = now_iso()
            rows = payload.get("markets") if isinstance(payload.get("markets"), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                mid = str(row.get("id") or "").strip()
                name = str(row.get("name") or "").strip().upper()
                if not mid and name:
                    mid = slug(name)
                if not mid:
                    continue
                item = items.get(mid)
                if not isinstance(item, dict):
                    item = {"id": mid, "name": name, "displayName": name, "websiteName": name, "aliases": [name], "createdAt": stamp, "sortOrder": len(items) * 10 + 10}
                    items[mid] = item
                if name:
                    item["name"] = name
                    item["displayName"] = name
                    item.setdefault("aliases", [name])
                if "websiteName" in row:
                    item["websiteName"] = str(row.get("websiteName") or name).strip().upper()
                for key in ["enabled", "ledgerEnabled", "resultEnabled", "autoResultEnabled", "autoPassFailEnabled", "scheduleEnabled"]:
                    if key in row:
                        item[key] = bool(row.get(key))
                stages = item.setdefault("stages", {})
                if "openStage" in row:
                    stages["open"] = bool(row.get("openStage"))
                if "closeStage" in row:
                    stages["close"] = bool(row.get("closeStage"))
                times = item.setdefault("times", {})
                if "openTime" in row:
                    times["open"] = norm_hhmm(row.get("openTime"))
                if "closeTime" in row:
                    times["close"] = norm_hhmm(row.get("closeTime"))
                if "chartUrl" in row:
                    item["chartUrl"] = str(row.get("chartUrl") or "").strip()
                item["deleted"] = False
                item["archived"] = False
                item["manualSaveLocked"] = True
                item["settingsLocked"] = True
                item["manualSaveLockSource"] = "ledger_market_settings"
                item["updatedAt"] = stamp
            ok = save_reg(state, reg)
            if not ok:
                return jsonify({"status": "error", "message": "Firebase save helper missing"}), 500
            return jsonify(serialize(state))
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.after_request
    def ledger_market_settings_ui(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            if request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "ledger-market-settings-v1" in html or "</body>" not in html.lower():
                return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + UI + html[i:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


UI = r'''
<style id="ledger-market-settings-v1-style">
#ledgerMarketSettingsPanel{margin:12px;padding:12px;background:#101d2f;border:1px solid rgba(42,171,238,.28);border-radius:18px;color:#eef6ff;font-family:Inter,Arial,sans-serif;box-shadow:0 10px 28px rgba(0,0,0,.25)}
#ledgerMarketSettingsPanel .lms-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}#ledgerMarketSettingsPanel .lms-title{font-weight:1000;font-size:14px}#ledgerMarketSettingsPanel .lms-sub{color:#91afd1;font-size:10px;margin-top:2px}#ledgerMarketSettingsPanel button{border:0;border-radius:12px;padding:8px 10px;font-weight:900;background:#2aabee;color:white}#ledgerMarketSettingsPanel .lms-save{background:#00c26f;color:#062013}#ledgerMarketSettingsPanel .lms-row{background:#07111f;border:1px solid #243e5f;border-radius:14px;padding:10px;margin-top:9px}#ledgerMarketSettingsPanel .lms-name{font-weight:900;font-size:12px;margin-bottom:7px}#ledgerMarketSettingsPanel .lms-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}#ledgerMarketSettingsPanel label{display:flex;align-items:center;gap:6px;font-size:10px;color:#cfe8ff}#ledgerMarketSettingsPanel input[type=time],#ledgerMarketSettingsPanel input[type=text]{width:100%;background:#0b1727;border:1px solid #263b59;border-radius:10px;color:#eef6ff;padding:8px;font-size:12px}#ledgerMarketSettingsPanel .lms-small{font-size:10px;color:#91afd1;margin-top:7px}.lms-hidden{display:none!important}
</style>
<script id="ledger-market-settings-v1">
(function(){
 if(window.__LEDGER_MARKET_SETTINGS_V1__)return;window.__LEDGER_MARKET_SETTINGS_V1__=true;
 const API='/api/ledger_market_settings';let rows=[];
 function q(s){return document.querySelector(s)} function qa(s){return Array.from(document.querySelectorAll(s))}
 function getv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return ''}}
 function inLedger(){return String(getv('mainNav')||'').toLowerCase()==='ledger'}
 function headers(){const h={'Content-Type':'application/json'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
 function root(){return q('main')||q('#app')||document.body}
 function rowHtml(m,i){return `<div class="lms-row" data-i="${i}"><div class="lms-name">${m.name||'-'}</div><div class="lms-grid"><label><input type="checkbox" data-k="enabled" ${m.enabled?'checked':''}> Market ON</label><label><input type="checkbox" data-k="ledgerEnabled" ${m.ledgerEnabled?'checked':''}> Ledger</label><label><input type="checkbox" data-k="resultEnabled" ${m.resultEnabled?'checked':''}> Result</label><label><input type="checkbox" data-k="autoPassFailEnabled" ${m.autoPassFailEnabled?'checked':''}> Auto Mark</label><label><input type="checkbox" data-k="scheduleEnabled" ${m.scheduleEnabled?'checked':''}> Schedule</label><label><input type="checkbox" data-k="autoResultEnabled" ${m.autoResultEnabled?'checked':''}> Auto Result</label><div><div class="lms-small">Open Time</div><input type="time" data-k="openTime" value="${m.openTime||''}"></div><div><div class="lms-small">Close Time</div><input type="time" data-k="closeTime" value="${m.closeTime||''}"></div></div><div class="lms-small">Setup market setting now Ledger tab me direct save hota hai.</div></div>`}
 function panel(){return `<div id="ledgerMarketSettingsPanel"><div class="lms-top"><div><div class="lms-title">🏪 Ledger Market Settings</div><div class="lms-sub">Market ON/OFF, Ledger, Result, Auto Mark, Schedule, Open/Close time</div></div><div><button onclick="window.LedgerMarketSettingsReload&&window.LedgerMarketSettingsReload()">Refresh</button> <button class="lms-save" onclick="window.LedgerMarketSettingsSave&&window.LedgerMarketSettingsSave()">Save</button></div></div><div id="ledgerMarketSettingsList">Loading...</div></div>`}
 function show(){if(!inLedger()){const p=q('#ledgerMarketSettingsPanel');if(p)p.remove();return}if(!q('#ledgerMarketSettingsPanel')){const r=root();if(r)r.insertAdjacentHTML('afterbegin',panel());load()}}
 async function load(){try{const r=await fetch(API+'?_='+Date.now(),{cache:'no-store',headers:headers()});const j=await r.json();rows=j.markets||[];const box=q('#ledgerMarketSettingsList');if(box)box.innerHTML=rows.map(rowHtml).join('')||'<div class="lms-small">No markets found</div>'}catch(e){const box=q('#ledgerMarketSettingsList');if(box)box.textContent='Load failed: '+e.message}}
 function collect(){qa('#ledgerMarketSettingsPanel .lms-row').forEach(el=>{const i=Number(el.dataset.i);const m=rows[i]||{};qa('input',el).forEach(inp=>{const k=inp.dataset.k;if(!k)return;m[k]=inp.type==='checkbox'?!!inp.checked:inp.value});rows[i]=m});return rows}
 async function save(){try{collect();if(window.__TitanRealtime)window.__TitanRealtime.pause(1600);const r=await fetch(API,{method:'POST',headers:headers(),body:JSON.stringify({markets:rows})});const j=await r.json();if(j.status!=='success')throw new Error(j.message||'Save failed');rows=j.markets||rows;await load();try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}alert('✅ Ledger Market Settings saved')}catch(e){alert('❌ Market save failed: '+e.message)}}
 window.LedgerMarketSettingsReload=load;window.LedgerMarketSettingsSave=save;
 document.addEventListener('click',()=>setTimeout(show,180),true);setInterval(show,1200);setTimeout(show,800);
})();
</script>
'''
