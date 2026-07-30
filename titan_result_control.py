"""Titan Nova Result tab control patch.

Keeps the existing strict result declaration engine intact, but fixes the Result
UI/settings layer so toggles, targets, and settlement settings are saved through
safe child-path writes instead of broad /save full-state writes.
"""


def register_titan_result_control(app):
    if getattr(app, "_titan_result_control_registered", False):
        return
    app._titan_result_control_registered = True

    from flask import jsonify, request
    import copy
    import datetime
    import json
    import re
    import time

    VERSION = "2026-07-09-result-control-v1"

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for v in app.view_functions.values():
                g = getattr(v, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "_detect_result_stage" in g:
                    return g
        except Exception:
            pass
        return {}

    def clone(obj):
        try:
            return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
        except Exception:
            try:
                return copy.deepcopy(obj)
            except Exception:
                return obj

    def now_iso():
        try:
            fn = G().get("_now_iso_local")
            if callable(fn):
                return fn()
        except Exception:
            pass
        return datetime.datetime.now().isoformat(timespec="seconds")

    def today():
        try:
            fn = G().get("_safe_today")
            if callable(fn):
                return fn()
        except Exception:
            pass
        return datetime.date.today().isoformat()

    def state():
        g = G()
        for name in ("migrate_and_get_state", "load_from_firebase"):
            fn = g.get(name)
            if callable(fn):
                try:
                    st = fn()
                    if isinstance(st, dict):
                        return st
                except Exception:
                    pass
        return {}

    def put_child(parts, value):
        fn = G().get("_firebase_put_child")
        if callable(fn):
            return fn(parts, value)
        saver = G().get("save_to_firebase")
        if callable(saver):
            st = state()
            cur = st
            for p in parts[:-1]:
                cur = cur.setdefault(str(p), {})
            if parts:
                cur[str(parts[-1])] = value
            return saver(st)
        return False

    def add_audit(st, action, detail=None):
        log = st.setdefault("auditLog", [])
        if not isinstance(log, list):
            log = []
            st["auditLog"] = log
        rec = {"id": "result_" + str(int(time.time() * 1000)), "time": now_iso(), "action": action, "detail": detail or {}, "version": VERSION}
        log.append(rec)
        if len(log) > 1000:
            del log[:-1000]
        return rec

    def clean_targets(v):
        if isinstance(v, list):
            vals = v
        elif isinstance(v, dict):
            vals = list(v.values())
        else:
            vals = str(v or "").replace("\r", "\n").replace(",", "\n").split("\n")
        out, seen = [], set()
        for raw in vals:
            if isinstance(raw, dict):
                raw = raw.get("id") or raw.get("jid") or raw.get("target") or raw.get("phone") or ""
            s = str(raw or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out[:500]

    def num(v, default=0):
        try:
            return float(str(v).replace(",", "").strip())
        except Exception:
            return default

    def boolv(v, default=False):
        if isinstance(v, bool):
            return v
        if v is None:
            return default
        return str(v).strip().lower() in ("1", "true", "yes", "on", "checked")

    def clean_result(v):
        return str(v or "").strip().upper().replace(" ", "")

    def stage_of(v):
        val = clean_result(v)
        if re.fullmatch(r"\d{3}-\d", val):
            return "open", val
        if re.fullmatch(r"\d{3}-\d{2}-\d{3}", val):
            return "close", val
        return "", val

    def norm_market(v):
        s = re.sub(r"[^A-Z0-9]+", " ", str(v or "").upper().replace("SRIDEVI DAY", "SRIDEV DAY")).strip()
        return re.sub(r"\s+", " ", s)

    def default_result_settings(st=None):
        g = G()
        return {
            "autoScrapeEnabled": True,
            "useForwardTargetsForResults": True,
            "sourceName": str(g.get("RESULT_SOURCE_NAME") or "Dpbosss Net In"),
            "sourceUrl": str(g.get("RESULT_SOURCE_URL") or "https://dpbosss.net.in/"),
            "strictTwoStage": True,
            "updatedAt": now_iso(),
            "version": VERSION,
        }

    def _is_number_like(value):
        try:
            float(value)
            return True
        except Exception:
            return False

    def default_settlement_settings():
        g = G()
        fn = g.get("_default_settlement_settings")
        if callable(fn):
            try:
                base = fn()
            except Exception:
                base = {}
        else:
            base = {}
        if not isinstance(base, dict):
            base = {}
        base.setdefault("enabled", True)
        base.setdefault("includeSummaryInResultMessage", True)
        base.setdefault("includeHitMissInResultMessage", False)
        base.setdefault("autoLedgerMarking", True)
        base.setdefault("autoLedgerMarkOnlyWait", True)
        base.setdefault("autoLedgerApplyToAllProfiles", True)
        base.setdefault("autoLedgerRecordResults", True)
        pm = base.setdefault("payoutMultipliers", {})
        if not isinstance(pm, dict):
            pm = {}
            base["payoutMultipliers"] = pm
        pm.setdefault("ank", 9.5)
        if not _is_number_like(pm.get("jodi")):
            pm["jodi"] = 95
        pm.setdefault("penel", 150)
        pm.setdefault("panel", pm.get("penel", 150))
        pm.setdefault("patti", 150)
        base["updatedAt"] = base.get("updatedAt") or now_iso()
        base["version"] = base.get("version") or VERSION
        return base

    def ensure_result_state(st):
        if not isinstance(st, dict):
            st = {}
        repairs = []
        if not isinstance(st.get("resultRecords"), dict):
            st["resultRecords"] = {}; repairs.append("resultRecords")
        if not isinstance(st.get("settlementRecords"), dict):
            st["settlementRecords"] = {}; repairs.append("settlementRecords")
        if not isinstance(st.get("ledgerAutoMarkRecords"), dict):
            st["ledgerAutoMarkRecords"] = {}; repairs.append("ledgerAutoMarkRecords")
        if not isinstance(st.get("resultTargets"), list):
            st["resultTargets"] = clean_targets(st.get("resultTargets")); repairs.append("resultTargets")
        rs = st.setdefault("resultSettings", {})
        if not isinstance(rs, dict):
            rs = {}; st["resultSettings"] = rs; repairs.append("resultSettings")
        base_rs = default_result_settings(st)
        for k, v in base_rs.items():
            rs.setdefault(k, v)
        ss = st.setdefault("settlementSettings", {})
        if not isinstance(ss, dict):
            ss = {}; st["settlementSettings"] = ss; repairs.append("settlementSettings")
        base_ss = default_settlement_settings()
        for k, v in base_ss.items():
            if k == "payoutMultipliers":
                pm = ss.setdefault("payoutMultipliers", {})
                if not isinstance(pm, dict):
                    pm = {}; ss["payoutMultipliers"] = pm
                for pk, pv in v.items():
                    try: old = float(pm.get(pk))
                    except Exception: old = None
                    if old is None:
                        pm[pk] = pv; repairs.append("payout." + pk)
            else:
                ss.setdefault(k, v)
        st["resultControlMeta"] = {"version": VERSION, "checkedAt": now_iso(), "repairs": repairs[-80:]}
        return st, repairs

    def repair_invalid_close_results(st, date_key):
        repairs = []
        records = (st.get("resultRecords") or {}).setdefault(str(date_key), {})
        if not isinstance(records, dict):
            return repairs
        for market, rec in list(records.items()):
            if not isinstance(rec, dict):
                continue
            close_stage, close_val = stage_of(rec.get("closeResult"))
            if close_stage != "close":
                continue
            open_stage, open_val = stage_of(rec.get("openResult"))
            reason = ""
            if open_stage != "open" or rec.get("openInferredFromClose") is True:
                reason = "fresh_open_missing_strict_2_stage"
            elif not close_val.startswith(open_val):
                reason = "close_open_mismatch"
            if reason:
                rec["ignoredCloseResult"] = close_val
                rec["ignoredCloseAt"] = now_iso()
                rec["ignoredCloseReason"] = reason
                rec["closeResult"] = ""
                rec["closeUpdatedAt"] = ""
                rec["updatedAt"] = now_iso()
                repairs.append({"market": market, "close": close_val, "reason": reason})
        return repairs

    def result_summary(st, date_key):
        records = (st.get("resultRecords") or {}).get(str(date_key), {}) if isinstance(st.get("resultRecords"), dict) else {}
        if not isinstance(records, dict):
            records = {}
        open_count = 0; close_count = 0; ignored = 0; invalid = []
        for market, rec in records.items():
            if not isinstance(rec, dict):
                continue
            if stage_of(rec.get("openResult"))[0] == "open" and rec.get("openInferredFromClose") is not True:
                open_count += 1
            if stage_of(rec.get("closeResult"))[0] == "close":
                close_count += 1
            if rec.get("ignoredCloseResult"):
                ignored += 1
            close_stage, close_val = stage_of(rec.get("closeResult"))
            if close_stage == "close":
                open_stage, open_val = stage_of(rec.get("openResult"))
                if open_stage != "open" or rec.get("openInferredFromClose") is True or not close_val.startswith(open_val):
                    invalid.append({"market": market, "close": close_val})
        return {
            "date": str(date_key),
            "marketsWithRecords": len(records),
            "openCount": open_count,
            "closeCount": close_count,
            "ignoredCloseCount": ignored,
            "invalidCloseCount": len(invalid),
            "invalidClosePreview": invalid[:20],
            "targetCount": len(clean_targets(st.get("resultTargets") or [])),
            "resultSettings": st.get("resultSettings", {}),
            "settlementSettings": st.get("settlementSettings", {}),
        }

    def save_settings(st, payload):
        st, repairs = ensure_result_state(st)
        changed = []
        rs = st["resultSettings"]
        for k in ("autoScrapeEnabled", "useForwardTargetsForResults", "strictTwoStage"):
            if k in payload:
                rs[k] = boolv(payload.get(k), rs.get(k, True))
        for k in ("sourceName", "sourceUrl"):
            if k in payload:
                rs[k] = str(payload.get(k) or "").strip()[:300]
        rs["updatedAt"] = now_iso(); rs["version"] = VERSION
        changed.append("resultSettings")
        ss = st["settlementSettings"]
        for k in ("enabled", "includeSummaryInResultMessage", "includeHitMissInResultMessage", "autoLedgerMarking", "autoLedgerMarkOnlyWait", "autoLedgerApplyToAllProfiles", "autoLedgerRecordResults"):
            if k in payload:
                ss[k] = boolv(payload.get(k), ss.get(k, True))
        pm_in = payload.get("payoutMultipliers") if isinstance(payload.get("payoutMultipliers"), dict) else {}
        pm = ss.setdefault("payoutMultipliers", {})
        for k in ("ank", "jodi", "penel", "panel", "patti"):
            if k in pm_in:
                val = num(pm_in.get(k), pm.get(k, 0))
                if val >= 0:
                    pm[k] = val
        if not _is_number_like(pm.get("jodi")):
            pm["jodi"] = 95
        if "panel" not in pm and "penel" in pm:
            pm["panel"] = pm.get("penel")
        if "patti" not in pm and "penel" in pm:
            pm["patti"] = pm.get("penel")
        ss["updatedAt"] = now_iso(); ss["version"] = VERSION
        changed.append("settlementSettings")
        if "resultTargets" in payload or "targets" in payload:
            st["resultTargets"] = clean_targets(payload.get("resultTargets") if "resultTargets" in payload else payload.get("targets"))
            changed.append("resultTargets")
        add_audit(st, "result_control_settings_save", {"changed": changed, "repairs": repairs})
        put_child(["resultSettings"], st.get("resultSettings"))
        put_child(["settlementSettings"], st.get("settlementSettings"))
        if "resultTargets" in changed:
            put_child(["resultTargets"], st.get("resultTargets", []))
        put_child(["auditLog"], (st.get("auditLog") or [])[-1000:])
        return st, repairs, changed

    @app.route("/api/result_control/status", methods=["GET"])
    def result_control_status():
        date_key = request.args.get("date") or today()
        st, repairs = ensure_result_state(state())
        return jsonify({"status": "success", "version": VERSION, "summary": result_summary(st, date_key), "repairsPreview": repairs, "resultControl": True})

    @app.route("/api/result_control/repair", methods=["POST"])
    def result_control_repair():
        payload = request.get_json(silent=True) or {}
        date_key = payload.get("date") or request.args.get("date") or today()
        st, repairs = ensure_result_state(state())
        invalid = repair_invalid_close_results(st, date_key)
        add_audit(st, "result_control_repair", {"date": date_key, "shapeRepairs": repairs, "invalidCloseRepairs": invalid})
        put_child(["resultRecords", str(date_key)], (st.get("resultRecords") or {}).get(str(date_key), {}))
        put_child(["resultSettings"], st.get("resultSettings"))
        put_child(["settlementSettings"], st.get("settlementSettings"))
        put_child(["resultTargets"], st.get("resultTargets", []))
        put_child(["auditLog"], (st.get("auditLog") or [])[-1000:])
        return jsonify({"status": "success", "version": VERSION, "date": date_key, "shapeRepairs": repairs, "invalidCloseRepairs": invalid, "summary": result_summary(st, date_key)})

    @app.route("/api/result_control/save_settings", methods=["POST"])
    def result_control_save_settings():
        payload = request.get_json(silent=True) or {}
        try:
            st, repairs, changed = save_settings(state(), payload)
            return jsonify({"status": "success", "version": VERSION, "changed": changed, "repairs": repairs, "resultSettings": st.get("resultSettings"), "settlementSettings": st.get("settlementSettings"), "resultTargets": st.get("resultTargets", []), "summary": result_summary(st, payload.get("date") or today())})
        except Exception as exc:
            return jsonify({"status": "error", "version": VERSION, "message": str(exc)}), 500

    @app.after_request
    def result_control_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-result-control-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan result control patch loaded", VERSION)


SCRIPT = r'''
<script id="titan-result-control-v1">
(function(){
 if(window.__TITAN_RESULT_CONTROL_V1__)return; window.__TITAN_RESULT_CONTROL_V1__=true;
 const VERSION='2026-07-09-result-control-v1';
 function headers(){const h={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
 function notify(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else console.log(t,m)}catch(e){}}
 function fixResultState(){
   try{
     if(!window.appState)return;
     if(!appState.resultRecords||typeof appState.resultRecords!=='object'||Array.isArray(appState.resultRecords))appState.resultRecords={};
     if(typeof currentDate!=='undefined'&&!appState.resultRecords[currentDate])appState.resultRecords[currentDate]={};
     if(!Array.isArray(appState.resultTargets))appState.resultTargets=[];
     if(!appState.resultSettings||typeof appState.resultSettings!=='object')appState.resultSettings={};
     if(typeof appState.resultSettings.autoScrapeEnabled==='undefined')appState.resultSettings.autoScrapeEnabled=true;
     if(typeof appState.resultSettings.useForwardTargetsForResults==='undefined')appState.resultSettings.useForwardTargetsForResults=true;
     if(!appState.settlementRecords||typeof appState.settlementRecords!=='object'||Array.isArray(appState.settlementRecords))appState.settlementRecords={};
     if(typeof currentDate!=='undefined'&&!appState.settlementRecords[currentDate])appState.settlementRecords[currentDate]={};
     if(!appState.ledgerAutoMarkRecords||typeof appState.ledgerAutoMarkRecords!=='object'||Array.isArray(appState.ledgerAutoMarkRecords))appState.ledgerAutoMarkRecords={};
     if(typeof currentDate!=='undefined'&&!appState.ledgerAutoMarkRecords[currentDate])appState.ledgerAutoMarkRecords[currentDate]={};
     if(!appState.settlementSettings||typeof appState.settlementSettings!=='object')appState.settlementSettings={};
     const s=appState.settlementSettings;
     if(typeof s.enabled==='undefined')s.enabled=true;
     if(typeof s.includeSummaryInResultMessage==='undefined')s.includeSummaryInResultMessage=true;
     if(typeof s.includeHitMissInResultMessage==='undefined')s.includeHitMissInResultMessage=false;
     if(typeof s.autoLedgerMarking==='undefined')s.autoLedgerMarking=true;
     if(typeof s.autoLedgerMarkOnlyWait==='undefined')s.autoLedgerMarkOnlyWait=true;
     if(typeof s.autoLedgerApplyToAllProfiles==='undefined')s.autoLedgerApplyToAllProfiles=true;
     if(typeof s.autoLedgerRecordResults==='undefined')s.autoLedgerRecordResults=true;
     if(!s.payoutMultipliers||typeof s.payoutMultipliers!=='object')s.payoutMultipliers={};
     if(!Number.isFinite(Number(s.payoutMultipliers.ank)))s.payoutMultipliers.ank=9.5;
     if(!Number.isFinite(Number(s.payoutMultipliers.jodi))||Number(s.payoutMultipliers.jodi)<50)s.payoutMultipliers.jodi=95;
     if(!Number.isFinite(Number(s.payoutMultipliers.penel)))s.payoutMultipliers.penel=150;
     if(!Number.isFinite(Number(s.payoutMultipliers.panel)))s.payoutMultipliers.panel=s.payoutMultipliers.penel;
     if(!Number.isFinite(Number(s.payoutMultipliers.patti)))s.payoutMultipliers.patti=s.payoutMultipliers.penel;
   }catch(e){console.warn('Result state repair failed',e)}
 }
 const oldEnsure=window.ensureResultStruct;
 window.ensureResultStruct=function(){try{if(typeof oldEnsure==='function')oldEnsure.apply(this,arguments)}catch(e){console.warn(e)}fixResultState();};
 async function saveResultControl(payload){
   fixResultState();
   const res=await fetch('/api/result_control/save_settings',{method:'POST',headers:headers(),body:JSON.stringify(Object.assign({date:(typeof currentDate!=='undefined'?currentDate:'')},payload||{}))});
   const data=await res.json().catch(()=>({status:'error',message:'Bad JSON'}));
   if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));
   appState.resultSettings=data.resultSettings||appState.resultSettings;
   appState.settlementSettings=data.settlementSettings||appState.settlementSettings;
   appState.resultTargets=data.resultTargets||appState.resultTargets||[];
   fixResultState();
   try{if(window.__TitanRealtime)window.__TitanRealtime.refresh('result_control_save')}catch(e){}
   return data;
 }
 window.saveResultScrapeSetting=async function(enabled){try{fixResultState();appState.resultSettings.autoScrapeEnabled=!!enabled;try{render(true)}catch(e){}await saveResultControl({autoScrapeEnabled:!!enabled});notify(enabled?'🟢 Auto Scrape ON':'🔴 Auto Scrape OFF',enabled?'Gateway live result scrape karega.':'Gateway auto scrape skip karega. Manual declare active rahega.',enabled?'success':'danger')}catch(e){notify('❌ Result Setting Error',String(e.message||e),'danger')}};
 window.saveResultDeliverySettings=async function(){try{fixResultState();const useForward=!!document.getElementById('result-use-forward-targets')?.checked;appState.resultSettings.useForwardTargetsForResults=useForward;await saveResultControl({useForwardTargetsForResults:useForward});notify('✅ Delivery Saved',useForward?'Result + Forward targets dono use honge.':'Sirf Result targets use honge.','success');try{render(true)}catch(e){}}catch(e){notify('❌ Delivery Error',String(e.message||e),'danger')}};
 window.saveSettlementSettings=async function(partial){try{fixResultState();partial=partial||{};Object.assign(appState.settlementSettings,partial);if(partial.payoutMultipliers)Object.assign(appState.settlementSettings.payoutMultipliers,partial.payoutMultipliers);fixResultState();await saveResultControl(Object.assign({},appState.resultSettings,appState.settlementSettings,{payoutMultipliers:appState.settlementSettings.payoutMultipliers}));notify('✅ Settlement Saved','Result settlement settings safe Firebase child path me save ho gaye.','success');try{render(true)}catch(e){}}catch(e){notify('❌ Settlement Error',String(e.message||e),'danger')}};
 const oldSaveTargets=window.saveResultTargetsList;
 window.saveResultTargetsList=async function(targets){try{const raw=Array.isArray(targets)?targets.join('\n'):String(targets||'');const cleaned=typeof titanCleanTargets==='function'?titanCleanTargets(raw):raw.split(/[\r\n,]+/).map(x=>x.trim()).filter(Boolean);appState.resultTargets=cleaned;await saveResultControl({resultTargets:cleaned});notify('✅ Result Targets Saved',cleaned.length+' WhatsApp target ready.','success');try{render(true)}catch(e){}}catch(e){try{if(typeof oldSaveTargets==='function')return oldSaveTargets(targets)}catch(_){}notify('❌ Target Error',String(e.message||e),'danger')}};
 window.refreshResultsState=async function(){try{fixResultState();const res=await fetch('/api/results?date='+encodeURIComponent(typeof currentDate!=='undefined'?currentDate:''),{headers:headers(),cache:'no-store'});const data=await res.json();if(data.status==='success'){appState.resultRecords=data.resultRecords||{};appState.resultTargets=data.resultTargets||[];appState.resultSettings=data.resultSettings||appState.resultSettings||{};appState.settlementRecords=data.settlementRecords||{};appState.ledgerAutoMarkRecords=data.ledgerAutoMarkRecords||appState.ledgerAutoMarkRecords||{};appState.settlementSettings=data.settlementSettings||appState.settlementSettings||{};fixResultState();return data}}catch(e){console.warn('refreshResultsState failed',e)}return null};
 window.resultControlRepair=async function(){try{const res=await fetch('/api/result_control/repair',{method:'POST',headers:headers(),body:JSON.stringify({date:(typeof currentDate!=='undefined'?currentDate:'')})});const data=await res.json().catch(()=>({}));if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));await window.refreshResultsState();notify('✅ Result Repaired',`${(data.shapeRepairs||[]).length} shape, ${(data.invalidCloseRepairs||[]).length} invalid close repaired.`,'success');try{render(true)}catch(e){}}catch(e){notify('❌ Result Repair Error',String(e.message||e),'danger')}};
 window.resultControlStatus=async function(){try{const res=await fetch('/api/result_control/status?date='+encodeURIComponent(typeof currentDate!=='undefined'?currentDate:''),{headers:headers(),cache:'no-store'});const data=await res.json();notify('Result Status',JSON.stringify(data.summary||{},null,2),'info');return data}catch(e){notify('❌ Result Status Error',String(e.message||e),'danger')}};
 function injectResultTools(){try{if(typeof mainNav==='undefined'||mainNav!=='results')return;const root=document.querySelector('#app')||document.querySelector('main')||document.body;if(!root||document.getElementById('result-control-tools'))return;const bar=document.createElement('div');bar.id='result-control-tools';bar.className='mx-3 mb-3 native-card p-3';bar.innerHTML='<div class="flex items-center justify-between gap-2"><div><p class="text-white font-black text-[11px] uppercase">Result Safety Control</p><p class="text-[9px] text-[var(--text-muted)]">Safe settings save + invalid close cleanup</p></div><div class="flex gap-2"><button onclick="resultControlStatus()" class="bg-[var(--surface-light)] border border-[var(--border)] text-white px-3 py-2 rounded-lg font-black text-[9px] uppercase">Status</button><button onclick="resultControlRepair()" class="bg-[var(--green)] text-white px-3 py-2 rounded-lg font-black text-[9px] uppercase">Repair</button></div></div>';root.prepend(bar)}catch(e){}}
 const oldRender=window.render;window.render=function(){const out=oldRender?oldRender.apply(this,arguments):undefined;try{fixResultState();setTimeout(injectResultTools,50)}catch(e){}return out};
 fixResultState();
 console.log('✅ Titan Result Control active',VERSION);
})();
</script>
'''
