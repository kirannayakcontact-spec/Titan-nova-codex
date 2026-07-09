"""Titan Nova Setup/Settings control patch.

This patch makes the Setup tab a safe control center:
- saves settings through child-path Firebase writes instead of full-root saveMaster
- normalizes all core settings in one place
- adds diagnostics/repair endpoints
- injects a frontend override for the Setup tab and setupSaveSection()
"""


def register_titan_setup_control(app):
    if getattr(app, "_titan_setup_control_registered", False):
        return
    app._titan_setup_control_registered = True

    from flask import jsonify, request
    import copy
    import datetime
    import json
    import time

    VERSION = "2026-07-09-setup-control-v1"

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for v in app.view_functions.values():
                g = getattr(v, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "load_from_firebase" in g:
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

    def patch_child(parts, value):
        fn = G().get("_firebase_patch_child")
        if callable(fn):
            return fn(parts, value)
        return put_child(parts, value)

    def add_audit(st, action, detail=None):
        log = st.setdefault("auditLog", [])
        if not isinstance(log, list):
            log = []
            st["auditLog"] = log
        rec = {"id": "setup_" + str(int(time.time() * 1000)), "time": now_iso(), "action": action, "detail": detail or {}, "version": VERSION}
        log.append(rec)
        if len(log) > 1000:
            del log[:-1000]
        return rec

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

    def hhmm(v, default=""):
        raw = str(v or "").strip()
        if not raw:
            return default
        parts = raw.split(":")
        if len(parts) < 2:
            return default
        try:
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        except Exception:
            pass
        return default

    def clean_targets(v):
        if isinstance(v, dict):
            vals = list(v.values())
        elif isinstance(v, list):
            vals = v
        else:
            vals = str(v or "").replace("\r", "\n").replace(",", "\n").split("\n")
        out, seen = [], set()
        for item in vals:
            if isinstance(item, dict):
                item = item.get("id") or item.get("jid") or item.get("target") or item.get("phone") or ""
            s = str(item or "").strip()
            if not s:
                continue
            if s not in seen:
                seen.add(s); out.append(s)
        return out[:500]

    def default_market_registry():
        fn = G().get("_default_market_registry")
        if callable(fn):
            try: return fn()
            except Exception: pass
        return {"version": VERSION, "items": {}, "deletedMarketIds": []}

    def normalize_market_registry(reg):
        fn = G().get("_normalize_market_registry")
        if callable(fn):
            try: return fn(reg)
            except Exception: pass
        if not isinstance(reg, dict):
            reg = {}
        reg.setdefault("items", {})
        reg.setdefault("deletedMarketIds", [])
        reg["version"] = str(reg.get("version") or VERSION)
        return reg

    def ensure_core(st):
        if not isinstance(st, dict): st = {}
        repairs = []
        if not isinstance(st.get("profiles"), dict): st["profiles"] = {}; repairs.append("profiles")
        for aid, label in (("admin1","MASTER ADMIN 1"),("admin2","MASTER ADMIN 2"),("admin3","MASTER ADMIN 3")):
            if aid not in st["profiles"] or not isinstance(st["profiles"].get(aid), dict):
                st["profiles"][aid] = {"name": label, "phone": "", "config": {}, "dayRecords": {}}
                repairs.append("profiles." + aid)
        cfg = st["profiles"]["admin1"].setdefault("config", {})
        if not isinstance(cfg, dict): cfg = {}; st["profiles"]["admin1"]["config"] = cfg; repairs.append("admin1.config")
        for key, default in (("capital",0),("dayTarget",0)):
            if key not in cfg: cfg[key] = default; repairs.append("config." + key)
        for typ in ("ank", "jodi", "pannel"):
            if not isinstance(cfg.get(typ), dict): cfg[typ] = {}; repairs.append("config." + typ)
            cfg[typ].setdefault("tgt", 0)
        st["marketRegistry"] = normalize_market_registry(st.get("marketRegistry") or default_market_registry())
        es = st.setdefault("entrySettings", {})
        if not isinstance(es, dict): es = {}; st["entrySettings"] = es; repairs.append("entrySettings")
        es.setdefault("entryParserEnabled", True); es.setdefault("marketTimingEnabled", True); es.setdefault("riskLimitEnabled", True)
        es.setdefault("groupsOnly", True); es.setdefault("strictFormat", True); es.setdefault("autoDebitWallet", True)
        es.setdefault("autoCreatePendingProfiles", True); es.setdefault("requireProfileApproval", True)
        es.setdefault("marketCloseTimes", {})
        rs = st.setdefault("riskSettings", {})
        if not isinstance(rs, dict): rs = {}; st["riskSettings"] = rs; repairs.append("riskSettings")
        rs.setdefault("marketDailyLimit", 0); rs.setdefault("digitDailyLimit", 0); rs.setdefault("userDailyLimit", 0); rs.setdefault("warningPercent", 80); rs.setdefault("autoLockOnLimit", False)
        res = st.setdefault("resultSettings", {})
        if not isinstance(res, dict): res = {}; st["resultSettings"] = res; repairs.append("resultSettings")
        res.setdefault("autoScrapeEnabled", True); res.setdefault("useForwardTargetsForResults", True)
        ss = st.setdefault("settlementSettings", {})
        if not isinstance(ss, dict): ss = {}; st["settlementSettings"] = ss; repairs.append("settlementSettings")
        ss.setdefault("enabled", True); ss.setdefault("includeSummaryInResultMessage", True); ss.setdefault("includeHitMissInResultMessage", False)
        ss.setdefault("autoLedgerMarking", True); ss.setdefault("autoLedgerMarkOnlyWait", True); ss.setdefault("autoLedgerApplyToAllProfiles", True); ss.setdefault("autoLedgerRecordResults", True)
        pm = ss.setdefault("payoutMultipliers", {})
        if not isinstance(pm, dict): pm = {}; ss["payoutMultipliers"] = pm; repairs.append("payoutMultipliers")
        for k, v in {"ank": 9.5, "jodi": 95, "penel": 150, "panel": 150, "patti": 150}.items():
            try: old = float(pm.get(k))
            except Exception: old = None
            if old is None or (k == "jodi" and old < 50): pm[k] = v; repairs.append("payout." + k)
        lf = st.setdefault("loadForwarder", {})
        if not isinstance(lf, dict): lf = {}; st["loadForwarder"] = lf; repairs.append("loadForwarder")
        lf.setdefault("enabled", False); lf.setdefault("scheduleTime", "18:00"); lf.setdefault("selectedMarket", ""); lf.setdefault("targets", []); lf.setdefault("gameTypes", ["ANK", "PENEL", "JODI"]); lf.setdefault("maxRowsPerType", 80); lf.setdefault("includeEmptyTypes", False)
        ws = st.setdefault("whatsappSafetySettings", {})
        if not isinstance(ws, dict): ws = {}; st["whatsappSafetySettings"] = ws; repairs.append("whatsappSafetySettings")
        ws.setdefault("enabled", True); ws.setdefault("duplicateBlockEnabled", True); ws.setdefault("linkGuardEnabled", False); ws.setdefault("spamGuardEnabled", True)
        if not isinstance(st.get("whatsappSafetyTargets"), dict): st["whatsappSafetyTargets"] = {}; repairs.append("whatsappSafetyTargets")
        if not isinstance(st.get("ledgerSchedules"), dict): st["ledgerSchedules"] = {}; repairs.append("ledgerSchedules")
        if not isinstance(st.get("auditLog"), list): st["auditLog"] = []; repairs.append("auditLog")
        st["setupControlMeta"] = {"version": VERSION, "checkedAt": now_iso(), "repairs": repairs[-80:]}
        return st, repairs

    def summary(st):
        reg = st.get("marketRegistry") if isinstance(st.get("marketRegistry"), dict) else {}
        items = [x for x in (reg.get("items") or {}).values() if isinstance(x, dict)]
        active = [x for x in items if x.get("deleted") is not True and x.get("archived") is not True and x.get("enabled") is not False]
        lf = st.get("loadForwarder") if isinstance(st.get("loadForwarder"), dict) else {}
        rs = st.get("riskSettings") if isinstance(st.get("riskSettings"), dict) else {}
        es = st.get("entrySettings") if isinstance(st.get("entrySettings"), dict) else {}
        return {
            "markets": {"total": len(items), "active": len(active), "resultEnabled": len([x for x in active if x.get("resultEnabled") is not False]), "scheduleEnabled": len([x for x in active if x.get("scheduleEnabled") is not False])},
            "schedules": {"saved": len(st.get("ledgerSchedules") or {}), "entryTimingEnabled": es.get("marketTimingEnabled") is not False, "riskLimitEnabled": es.get("riskLimitEnabled") is not False},
            "risk": {"marketDailyLimit": rs.get("marketDailyLimit", 0), "digitDailyLimit": rs.get("digitDailyLimit", 0), "userDailyLimit": rs.get("userDailyLimit", 0), "warningPercent": rs.get("warningPercent", 80), "autoLockOnLimit": bool(rs.get("autoLockOnLimit"))},
            "forwarder": {"enabled": bool(lf.get("enabled")), "time": lf.get("scheduleTime", ""), "targets": len(clean_targets(lf.get("targets") or [])), "gameTypes": lf.get("gameTypes") or []},
            "whatsapp": {"resultTargets": len(clean_targets(st.get("resultTargets") or [])), "safetyTargets": len(st.get("whatsappSafetyTargets") or {}), "guardEnabled": (st.get("whatsappSafetySettings") or {}).get("enabled") is not False},
        }

    def save_paths(st, paths):
        for p in paths:
            if len(p) == 1:
                put_child([p[0]], st.get(p[0]))
            elif len(p) == 2:
                put_child([p[0], p[1]], (st.get(p[0]) or {}).get(p[1]))
        put_child(["auditLog"], (st.get("auditLog") or [])[-1000:])
        return True

    def apply_section(st, section, payload):
        st, repairs = ensure_core(st)
        section = str(section or "all").strip().lower()
        changed = []
        if section in ("market", "markets", "all"):
            cfg_payload = payload.get("config") if isinstance(payload.get("config"), dict) else payload
            cfg = st["profiles"]["admin1"].setdefault("config", {})
            if "capital" in cfg_payload: cfg["capital"] = num(cfg_payload.get("capital"), cfg.get("capital", 0))
            if "dayTarget" in cfg_payload: cfg["dayTarget"] = num(cfg_payload.get("dayTarget"), cfg.get("dayTarget", 0))
            for typ in ("ank", "jodi", "pannel"):
                if typ in cfg_payload and isinstance(cfg_payload.get(typ), dict):
                    cfg.setdefault(typ, {})["tgt"] = num(cfg_payload[typ].get("tgt"), cfg.get(typ, {}).get("tgt", 0))
                if typ + "Target" in cfg_payload:
                    cfg.setdefault(typ, {})["tgt"] = num(cfg_payload.get(typ + "Target"), cfg.get(typ, {}).get("tgt", 0))
            changed += [("profiles", "admin1")]
        if section in ("schedule", "risk", "entry", "all"):
            es = st["entrySettings"]; rs = st["riskSettings"]
            for key in ("entryParserEnabled", "marketTimingEnabled", "riskLimitEnabled", "groupsOnly", "strictFormat", "autoDebitWallet", "autoCreatePendingProfiles", "requireProfileApproval"):
                if key in payload: es[key] = boolv(payload.get(key), es.get(key, True))
            if isinstance(payload.get("marketCloseTimes"), dict):
                mct = es.setdefault("marketCloseTimes", {})
                for k, v in payload["marketCloseTimes"].items():
                    t = hhmm(v, "")
                    if t: mct[str(k).upper().strip()] = t
            for key in ("marketDailyLimit", "digitDailyLimit", "userDailyLimit", "warningPercent"):
                if key in payload: rs[key] = num(payload.get(key), rs.get(key, 0))
            if "autoLockOnLimit" in payload: rs["autoLockOnLimit"] = boolv(payload.get("autoLockOnLimit"), False)
            changed += [("entrySettings",), ("riskSettings",)]
        if section in ("result", "results", "settlement", "all"):
            res = st["resultSettings"]; ss = st["settlementSettings"]
            for key in ("autoScrapeEnabled", "useForwardTargetsForResults"):
                if key in payload: res[key] = boolv(payload.get(key), res.get(key, True))
            for key in ("enabled", "includeSummaryInResultMessage", "includeHitMissInResultMessage", "autoLedgerMarking", "autoLedgerMarkOnlyWait", "autoLedgerApplyToAllProfiles", "autoLedgerRecordResults"):
                if key in payload: ss[key] = boolv(payload.get(key), ss.get(key, True))
            pm_in = payload.get("payoutMultipliers") if isinstance(payload.get("payoutMultipliers"), dict) else payload
            pm = ss.setdefault("payoutMultipliers", {})
            for k in ("ank", "jodi", "penel", "panel", "patti"):
                if k in pm_in: pm[k] = num(pm_in.get(k), pm.get(k, 0))
            changed += [("resultSettings",), ("settlementSettings",)]
        if section in ("forward", "forwarder", "loadforwarder", "all"):
            lf = st["loadForwarder"]
            if "enabled" in payload: lf["enabled"] = boolv(payload.get("enabled"), False)
            if "scheduleTime" in payload: lf["scheduleTime"] = hhmm(payload.get("scheduleTime"), lf.get("scheduleTime", "18:00"))
            if "selectedMarket" in payload: lf["selectedMarket"] = str(payload.get("selectedMarket") or "").upper().strip()
            if "targets" in payload: lf["targets"] = clean_targets(payload.get("targets"))
            if "gameTypes" in payload:
                games = [str(x).upper().strip() for x in (payload.get("gameTypes") if isinstance(payload.get("gameTypes"), list) else str(payload.get("gameTypes") or "").split(","))]
                lf["gameTypes"] = [x for x in games if x in ("ANK", "JODI", "PENEL", "PANEL", "PATTI")] or ["ANK", "PENEL", "JODI"]
            if "maxRowsPerType" in payload: lf["maxRowsPerType"] = int(num(payload.get("maxRowsPerType"), lf.get("maxRowsPerType", 80)))
            if "includeEmptyTypes" in payload: lf["includeEmptyTypes"] = boolv(payload.get("includeEmptyTypes"), False)
            changed += [("loadForwarder",)]
        if section in ("whatsapp", "guard", "targets", "all"):
            ws = st["whatsappSafetySettings"]
            for key in ("enabled", "duplicateBlockEnabled", "linkGuardEnabled", "spamGuardEnabled", "safeMessagingEnabled"):
                if key in payload: ws[key] = boolv(payload.get(key), ws.get(key, True))
            if "resultTargets" in payload: st["resultTargets"] = clean_targets(payload.get("resultTargets")); changed.append(("resultTargets",))
            changed += [("whatsappSafetySettings",), ("whatsappSafetyTargets",)]
        if section in ("deposit", "all"):
            dep = st.setdefault("depositSettings", {})
            if not isinstance(dep, dict): dep = {}; st["depositSettings"] = dep
            v1 = dep.setdefault("v1", {})
            if not isinstance(v1, dict): v1 = {}; dep["v1"] = v1
            for key in ("enabled", "manualApproval", "autoWhatsapp", "receiverMatchRequired", "allowWeakNameMatch"):
                if key in payload: v1[key] = boolv(payload.get(key), v1.get(key, True))
            for key in ("paymentName", "upiId", "accountName", "bankName", "qrImageUrl", "adminNote", "activeReceiverId"):
                if key in payload: v1[key] = str(payload.get(key) or "").strip()
            for key in ("minDeposit", "maxDeposit"):
                if key in payload: v1[key] = num(payload.get(key), v1.get(key, 0))
            if "allowedReceiverAccounts" in payload and isinstance(payload.get("allowedReceiverAccounts"), list):
                v1["allowedReceiverAccounts"] = payload.get("allowedReceiverAccounts")[:50]
            changed += [("depositSettings", "v1")]
        add_audit(st, "setup_control_save", {"section": section, "changed": ["/".join(x) for x in changed], "repairs": repairs})
        uniq = []
        for p in changed:
            if p not in uniq: uniq.append(p)
        save_paths(st, uniq)
        return st, repairs, uniq

    @app.route("/api/setup_control/status", methods=["GET"])
    def setup_control_status():
        st, repairs = ensure_core(state())
        return jsonify({"status": "success", "version": VERSION, "summary": summary(st), "repairsPreview": repairs, "setupControl": True})

    @app.route("/api/setup_control/repair", methods=["POST"])
    def setup_control_repair():
        st, repairs = ensure_core(state())
        add_audit(st, "setup_control_repair", {"repairs": repairs})
        paths = [("profiles", "admin1"), ("profiles", "admin2"), ("profiles", "admin3"), ("marketRegistry",), ("entrySettings",), ("riskSettings",), ("resultSettings",), ("settlementSettings",), ("loadForwarder",), ("whatsappSafetySettings",), ("whatsappSafetyTargets",), ("ledgerSchedules",)]
        save_paths(st, paths)
        return jsonify({"status": "success", "version": VERSION, "repairs": repairs, "summary": summary(st)})

    @app.route("/api/setup_control/save", methods=["POST"])
    def setup_control_save():
        payload = request.get_json(silent=True) or {}
        section = payload.get("section") or request.args.get("section") or "all"
        body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        try:
            st, repairs, changed = apply_section(state(), section, body)
            return jsonify({"status": "success", "version": VERSION, "section": section, "changed": ["/".join(x) for x in changed], "repairs": repairs, "summary": summary(st), "statePatch": {"entrySettings": st.get("entrySettings"), "riskSettings": st.get("riskSettings"), "resultSettings": st.get("resultSettings"), "settlementSettings": st.get("settlementSettings"), "loadForwarder": st.get("loadForwarder"), "whatsappSafetySettings": st.get("whatsappSafetySettings"), "resultTargets": st.get("resultTargets"), "depositSettings": st.get("depositSettings"), "adminConfig": (st.get("profiles") or {}).get("admin1", {}).get("config", {})}})
        except Exception as exc:
            return jsonify({"status": "error", "version": VERSION, "message": str(exc), "section": section}), 500

    @app.after_request
    def setup_control_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-setup-control-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan setup control patch loaded", VERSION)


SCRIPT = r'''
<script id="titan-setup-control-v1">
(function(){
 if(window.__TITAN_SETUP_CONTROL_V1__)return; window.__TITAN_SETUP_CONTROL_V1__=true;
 const VERSION='2026-07-09-setup-control-v1';
 function H(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
 function A(s){return H(s).replace(/`/g,'&#96;')}
 function tok(){const h={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
 function notify(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else alert(t+'\n'+m)}catch(e){}}
 function card(title,icon,body,foot){return `<div class="native-card p-4 mb-3 setup-control-card"><div class="flex items-center justify-between gap-3 mb-3"><div class="min-w-0"><p class="text-white font-black text-[13px] uppercase"><i class="${icon||'fas fa-gear'} text-[var(--primary)] mr-2"></i>${title}</p><p class="text-[9px] text-[var(--text-muted)] mt-1">Titan Setup Control · ${VERSION}</p></div><span class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border text-[var(--green)] border-[rgba(0,194,111,.25)]">SAFE</span></div>${body}${foot||''}</div>`}
 function inp(id,label,value,type='number'){return `<label><p class="stat-lbl">${label}</p><input id="${id}" type="${type}" class="native-input text-[12px]" value="${A(value||'')}"></label>`}
 function tog(id,label,on){return `<label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="text-white text-[10px] font-bold">${label}</span><span class="switch"><input id="${id}" type="checkbox" ${on?'checked':''}><span class="slider"></span></span></label>`}
 function val(id){return document.getElementById(id)?.value||''}
 function chk(id){return !!document.getElementById(id)?.checked}
 function num(id){return Number(val(id)||0)||0}
 function arr(v){return Array.isArray(v)?v:[]}
 function ensure(){try{if(typeof ensureDataStruct==='function')ensureDataStruct();if(typeof ensureEntryStruct==='function')ensureEntryStruct();if(typeof ensureResultStruct==='function')ensureResultStruct();if(typeof ensureLoadForwarderStruct==='function')ensureLoadForwarderStruct();if(typeof ensureWhatsappSafetyStruct==='function')ensureWhatsappSafetyStruct()}catch(e){}}
 function cfg(){ensure();try{return state&&state.config?state.config:(appState.profiles?.[appState.activeId||'admin1']?.config||{})}catch(e){return {}}}
 function marketList(){try{const a=(baseMarkets||[]).map(x=>x&&x.n).filter(Boolean);const b=(markets||[]).map(x=>x&&x.n).filter(Boolean);return Array.from(new Set(a.concat(b).map(x=>String(x).toUpperCase()))).sort()}catch(e){return []}}
 function targetText(v){if(Array.isArray(v))return v.join('\n'); if(v&&typeof v==='object')return Object.values(v).join('\n'); return String(v||'')}
 async function post(section,data){const r=await fetch('/api/setup_control/save',{method:'POST',headers:tok(),body:JSON.stringify({section,data})});const j=await r.json().catch(()=>({status:'error',message:'Bad JSON'}));if(!r.ok||j.status!=='success')throw new Error(j.message||('HTTP '+r.status));if(j.statePatch){try{Object.assign(appState.entrySettings||={},j.statePatch.entrySettings||{});Object.assign(appState.riskSettings||={},j.statePatch.riskSettings||{});Object.assign(appState.resultSettings||={},j.statePatch.resultSettings||{});Object.assign(appState.settlementSettings||={},j.statePatch.settlementSettings||{});appState.loadForwarder=j.statePatch.loadForwarder||appState.loadForwarder;appState.whatsappSafetySettings=j.statePatch.whatsappSafetySettings||appState.whatsappSafetySettings;appState.resultTargets=j.statePatch.resultTargets||appState.resultTargets;if(j.statePatch.adminConfig&&state)state.config=j.statePatch.adminConfig}catch(e){}}try{if(window.__TitanRealtime)window.__TitanRealtime.refresh('setup_control_save')}catch(e){}return j}
 window.setupSaveSection=async function(section){try{ensure();section=String(section||'all').toLowerCase();let data={};if(section==='market'){data={capital:num('setup-capital'),dayTarget:num('setup-day-target'),ankTarget:num('setup-ank-target'),jodiTarget:num('setup-jodi-target'),pannelTarget:num('setup-pannel-target')}}else if(section==='schedule'||section==='risk'||section==='entry'){data={entryParserEnabled:chk('setup-entry-parser'),marketTimingEnabled:chk('setup-entry-timing'),riskLimitEnabled:chk('setup-risk-enabled'),groupsOnly:chk('setup-groups-only'),strictFormat:chk('setup-strict-format'),autoDebitWallet:chk('setup-auto-debit'),autoCreatePendingProfiles:chk('setup-auto-profile'),requireProfileApproval:chk('setup-require-approval'),marketDailyLimit:num('setup-market-limit'),digitDailyLimit:num('setup-digit-limit'),userDailyLimit:num('setup-user-limit'),warningPercent:num('setup-warn-percent'),autoLockOnLimit:chk('setup-auto-lock')}}else if(section==='result'||section==='settlement'){data={autoScrapeEnabled:chk('setup-auto-scrape'),useForwardTargetsForResults:chk('setup-result-forward-targets'),enabled:chk('setup-settlement-enabled'),includeSummaryInResultMessage:chk('setup-settlement-summary'),includeHitMissInResultMessage:chk('setup-hitmiss'),autoLedgerMarking:chk('setup-auto-ledger-mark'),autoLedgerMarkOnlyWait:chk('setup-mark-only-wait'),autoLedgerApplyToAllProfiles:chk('setup-mark-all-vips'),autoLedgerRecordResults:chk('setup-record-results'),payoutMultipliers:{ank:num('setup-pay-ank'),jodi:num('setup-pay-jodi'),penel:num('setup-pay-penel'),panel:num('setup-pay-penel'),patti:num('setup-pay-penel')}}}else if(section==='forward'){data={enabled:chk('setup-forward-enabled'),scheduleTime:val('setup-forward-time'),selectedMarket:val('setup-forward-market'),targets:val('setup-forward-targets'),maxRowsPerType:num('setup-forward-rows'),includeEmptyTypes:chk('setup-forward-empty'),gameTypes:['ANK','PENEL','JODI'].filter(x=>chk('setup-forward-game-'+x))}}else if(section==='whatsapp'){data={enabled:chk('setup-wa-enabled'),duplicateBlockEnabled:chk('setup-wa-duplicate'),linkGuardEnabled:chk('setup-wa-link'),spamGuardEnabled:chk('setup-wa-spam'),safeMessagingEnabled:chk('setup-wa-safe'),resultTargets:val('setup-result-targets')}}else if(section==='deposit'){data={enabled:chk('setup-deposit-enabled'),paymentName:val('setup-deposit-name'),upiId:val('setup-deposit-upi'),accountName:val('setup-deposit-account'),bankName:val('setup-deposit-bank'),qrImageUrl:val('setup-deposit-qr'),minDeposit:num('setup-deposit-min'),maxDeposit:num('setup-deposit-max'),manualApproval:chk('setup-deposit-manual'),autoWhatsapp:chk('setup-deposit-wa')}}else data={};const j=await post(section,data);notify('✅ Setup Saved',`${section} saved. Changed: ${(j.changed||[]).join(', ')}`,'success');try{render(true)}catch(e){}}catch(e){notify('❌ Setup Save Error',String(e.message||e),'danger')}};
 window.setupControlRepair=async function(){try{const r=await fetch('/api/setup_control/repair',{method:'POST',headers:tok(),body:'{}'});const j=await r.json().catch(()=>({}));if(!r.ok||j.status!=='success')throw new Error(j.message||('HTTP '+r.status));notify('✅ Setup Repaired',`${(j.repairs||[]).length} setting shape repaired.`,'success');try{if(window.__TitanRealtime)window.__TitanRealtime.refresh('setup_repair');render(true)}catch(e){}}catch(e){notify('❌ Repair Error',String(e.message||e),'danger')}};
 window.setupControlStatus=async function(){try{const r=await fetch('/api/setup_control/status',{headers:tok(),cache:'no-store'});const j=await r.json();notify('Setup Status',JSON.stringify(j.summary||{},null,2),'info');return j}catch(e){notify('❌ Status Error',String(e.message||e),'danger')}};
 function setupHtml(){ensure();const c=cfg(),es=appState.entrySettings||{},rs=appState.riskSettings||{},res=appState.resultSettings||{},ss=appState.settlementSettings||{},pm=ss.payoutMultipliers||{},lf=appState.loadForwarder||{},ws=appState.whatsappSafetySettings||{},dep=(appState.depositSettings&&appState.depositSettings.v1)||{};const ml=marketList();let html=`<div class="px-3 py-4 pb-28"><div class="flex items-center justify-between mb-3"><p class="sec-header m-0">Setup Control Center</p><button onclick="setupControlStatus()" class="bg-[var(--surface-light)] border border-[var(--border)] text-[var(--primary)] px-3 py-2 rounded-xl font-black text-[10px] uppercase">Status</button></div>`;
 html+=card('Market / Capital Settings','fas fa-store',`<div class="grid grid-cols-2 gap-2 mb-2">${inp('setup-capital','Capital',c.capital||0)}${inp('setup-day-target','Day Target',c.dayTarget||0)}</div><div class="grid grid-cols-3 gap-2">${inp('setup-ank-target','ANK Target',c.ank?.tgt||0)}${inp('setup-jodi-target','JODI Target',c.jodi?.tgt||0)}${inp('setup-pannel-target','PAN Target',c.pannel?.tgt||0)}</div>`,`<button onclick="setupSaveSection('market')" class="mt-3 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save Market Settings</button>`);
 html+=card('Entry / Schedule / Risk','fas fa-clock',`<div class="grid grid-cols-2 gap-2 mb-3">${tog('setup-entry-parser','Entry Parser',es.entryParserEnabled!==false)}${tog('setup-entry-timing','Reject After Time',es.marketTimingEnabled!==false)}${tog('setup-risk-enabled','Risk Limits',es.riskLimitEnabled!==false)}${tog('setup-groups-only','Groups Only',es.groupsOnly!==false)}${tog('setup-strict-format','Strict Format',es.strictFormat!==false)}${tog('setup-auto-debit','Auto Debit Wallet',es.autoDebitWallet!==false)}${tog('setup-auto-profile','Auto Profile',es.autoCreatePendingProfiles!==false)}${tog('setup-require-approval','Require Approval',es.requireProfileApproval!==false)}</div><div class="grid grid-cols-2 gap-2">${inp('setup-market-limit','Market Limit',rs.marketDailyLimit||0)}${inp('setup-digit-limit','Digit Limit',rs.digitDailyLimit||0)}${inp('setup-user-limit','User Daily Limit',rs.userDailyLimit||0)}${inp('setup-warn-percent','Warning %',rs.warningPercent||80)}</div><div class="mt-2">${tog('setup-auto-lock','Auto Lock On Limit',!!rs.autoLockOnLimit)}</div>`,`<button onclick="setupSaveSection('schedule')" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save Schedule/Risk</button>`);
 html+=card('Result / Settlement','fas fa-trophy',`<div class="grid grid-cols-2 gap-2 mb-3">${tog('setup-auto-scrape','Auto Scrape',res.autoScrapeEnabled!==false)}${tog('setup-result-forward-targets','Use Forward Targets',res.useForwardTargetsForResults!==false)}${tog('setup-settlement-enabled','Settlement ON',ss.enabled!==false)}${tog('setup-settlement-summary','Summary in Result',ss.includeSummaryInResultMessage!==false)}${tog('setup-hitmiss','Hit/Miss in Result',!!ss.includeHitMissInResultMessage)}${tog('setup-auto-ledger-mark','Auto Ledger Mark',ss.autoLedgerMarking!==false)}${tog('setup-mark-only-wait','Only WAIT Mark',ss.autoLedgerMarkOnlyWait!==false)}${tog('setup-mark-all-vips','Apply All VIPs',ss.autoLedgerApplyToAllProfiles!==false)}</div><div class="grid grid-cols-3 gap-2">${inp('setup-pay-ank','ANK Payout',pm.ank||9.5)}${inp('setup-pay-jodi','JODI Payout',pm.jodi||95)}${inp('setup-pay-penel','PAN/Patti Payout',pm.penel||150)}</div>`,`<button onclick="setupSaveSection('result')" class="mt-3 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save Result/Settlement</button>`);
 html+=card('Load Forwarder','fas fa-share-nodes',`<div class="grid grid-cols-2 gap-2 mb-2">${tog('setup-forward-enabled','Forward Enabled',!!lf.enabled)}${inp('setup-forward-time','Daily Time',lf.scheduleTime||'18:00','time')}${inp('setup-forward-rows','Rows / Type',lf.maxRowsPerType||80)}<label><p class="stat-lbl">Market</p><select id="setup-forward-market" class="native-input text-[12px]"><option value="">ALL MARKETS</option>${ml.map(m=>`<option value="${A(m)}" ${String(lf.selectedMarket||'').toUpperCase()===m?'selected':''}>${H(m)}</option>`).join('')}</select></label></div><div class="grid grid-cols-3 gap-2 mb-2">${['ANK','PENEL','JODI'].map(gt=>tog('setup-forward-game-'+gt,gt,(lf.gameTypes||['ANK','PENEL','JODI']).includes(gt))).join('')}</div>${tog('setup-forward-empty','Include Empty Blocks',!!lf.includeEmptyTypes)}<p class="stat-lbl mt-3">Targets</p><textarea id="setup-forward-targets" class="native-input text-[11px] min-h-[80px]">${H(targetText(lf.targets||[]))}</textarea>`,`<button onclick="setupSaveSection('forward')" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save Forwarder</button>`);
 html+=card('WhatsApp / Guard / Result Targets','fab fa-whatsapp',`<div class="grid grid-cols-2 gap-2 mb-3">${tog('setup-wa-enabled','Safety Enabled',ws.enabled!==false)}${tog('setup-wa-duplicate','Duplicate Block',ws.duplicateBlockEnabled!==false)}${tog('setup-wa-link','Link Guard',!!ws.linkGuardEnabled)}${tog('setup-wa-spam','Spam Guard',ws.spamGuardEnabled!==false)}${tog('setup-wa-safe','Safe Messaging',ws.safeMessagingEnabled!==false)}</div><p class="stat-lbl">Result Targets</p><textarea id="setup-result-targets" class="native-input text-[11px] min-h-[90px]">${H(targetText(appState.resultTargets||[]))}</textarea>`,`<button onclick="setupSaveSection('whatsapp')" class="mt-3 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save WhatsApp</button>`);
 html+=card('Deposit Payment','fas fa-qrcode',`<div class="grid grid-cols-2 gap-2 mb-3">${tog('setup-deposit-enabled','Deposit Enabled',dep.enabled!==false)}${tog('setup-deposit-manual','Manual Approval',dep.manualApproval!==false)}${tog('setup-deposit-wa','Auto WhatsApp',!!dep.autoWhatsapp)}${inp('setup-deposit-name','Payment Name',dep.paymentName||'TITAN NOVA','text')}${inp('setup-deposit-upi','UPI ID',dep.upiId||'','text')}${inp('setup-deposit-account','Account Name',dep.accountName||'','text')}${inp('setup-deposit-bank','Bank Name',dep.bankName||'','text')}${inp('setup-deposit-qr','QR Image URL',dep.qrImageUrl||'','text')}${inp('setup-deposit-min','Min Deposit',dep.minDeposit||1)}${inp('setup-deposit-max','Max Deposit',dep.maxDeposit||100000)}</div>`,`<button onclick="setupSaveSection('deposit')" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Save Deposit</button>`);
 html+=card('Repair / Backup / Danger','fas fa-screwdriver-wrench',`<p class="text-[10px] text-[var(--text-muted)] leading-5">Repair missing setting keys without deleting business data. Backup download before dangerous cleanup.</p><div class="grid grid-cols-2 gap-2 mt-3"><button onclick="setupControlRepair()" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Repair Settings</button><button onclick="downloadBackupZip&&downloadBackupZip()" class="bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Backup ZIP</button></div>`);
 return html+'</div>'}
 const oldRender=window.renderSetupTab;window.renderSetupTab=function(){try{return setupHtml()}catch(e){notify('⚠️ Setup UI Error',String(e.message||e),'danger');try{return oldRender?oldRender():''}catch(_){return '<div class="p-4 text-white">Setup recovery failed</div>'}}};
 console.log('✅ Titan Setup Control active',VERSION);
})();
</script>
'''
