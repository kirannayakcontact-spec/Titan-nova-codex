"""Strict two-stage result rules for Titan Nova."""


def register_titan_strict_result_rules(app):
    if getattr(app, "_titan_strict_result_rules_registered", False):
        return
    app._titan_strict_result_rules_registered = True

    import datetime, hashlib, re, time
    from flask import jsonify, request

    VERSION = "2026-07-10-strict-result-state-machine-v1"

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for view in app.view_functions.values():
                g = getattr(view, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "load_from_firebase" in g:
                    return g
        except Exception:
            pass
        return {}

    def now(): return datetime.datetime.now().isoformat(timespec="seconds")
    def today():
        fn = G().get("_safe_today")
        if callable(fn):
            try: return str(fn())
            except Exception: pass
        return datetime.date.today().isoformat()

    def state():
        g = G()
        for name in ("migrate_and_get_state", "load_from_firebase"):
            fn = g.get(name)
            if callable(fn):
                try:
                    out = fn()
                    if isinstance(out, dict): return out
                except Exception: pass
        return {}

    def put(parts, value):
        g = G(); fn = g.get("_firebase_put_child")
        if callable(fn): return fn(parts, value)
        saver = g.get("save_to_firebase")
        if callable(saver):
            st = state(); cur = st
            for key in parts[:-1]: cur = cur.setdefault(str(key), {})
            cur[str(parts[-1])] = value
            return saver(st)
        return False

    def market(v):
        s = re.sub(r"[^A-Z0-9]+", " ", str(v or "").upper()).strip(); c = s.replace(" ", "")
        aliases = {"SRIDEVDAY":"SRIDEVI DAY","SRIDEVIDAY":"SRIDEVI DAY","TIMEBAZAR":"TIME BAZAR","MADHURDAY":"MADHUR DAY","MILANDAY":"MILAN DAY","RAJDHANIDAY":"RAJDHANI DAY","SUPREMEDAY":"SUPREME DAY","SRIDEVINIGHT":"SRIDEVI NIGHT","MADHURNIGHT":"MADHUR NIGHT","SUPREMENIGHT":"SUPREME NIGHT","MILANNIGHT":"MILAN NIGHT","RAJDHANINIGHT":"RAJDHANI NIGHT","KALYANNIGHT":"KALYAN NIGHT","MAINBAZAR":"MAIN BAZAR"}
        return aliases.get(c, re.sub(r"\s+", " ", s))

    def clean(v): return re.sub(r"\s+", "", str(v or "").strip().upper())
    def stage(v):
        v = clean(v)
        if re.fullmatch(r"\d{3}-\d", v): return "open", v
        if re.fullmatch(r"\d{3}-\d{2}-\d{3}", v): return "close", v
        return "invalid", v

    def ensure(st):
        if not isinstance(st, dict): st = {}
        if not isinstance(st.get("resultRecords"), dict): st["resultRecords"] = {}
        if not isinstance(st.get("resultRuleState"), dict): st["resultRuleState"] = {}
        if not isinstance(st.get("resultRuleAudit"), list): st["resultRuleAudit"] = []
        return st

    def machine(st, d, m):
        x = st.setdefault("resultRuleState", {}).setdefault(str(d), {}).setdefault(market(m), {})
        x.setdefault("phase", "EMPTY"); x.setdefault("baseline", ""); x.setdefault("open", ""); x.setdefault("close", ""); x.setdefault("seen", {})
        return x

    def sig(d,m,r): return hashlib.sha256(f"{d}|{market(m)}|{clean(r)}".encode()).hexdigest()[:24]
    def audit(st,event,detail):
        rows=st.setdefault("resultRuleAudit",[]); rows.append({"id":"rr_"+str(int(time.time()*1000)),"time":now(),"event":event,"detail":detail,"version":VERSION}); del rows[:-1500]

    def decide(st,d,m,candidate,source="",baseline=False):
        st=ensure(st); m=market(m); typ,val=stage(candidate); x=machine(st,d,m); fp=sig(d,m,val)
        out={"version":VERSION,"date":str(d),"market":m,"stage":typ,"result":val,"fingerprint":fp,"phaseBefore":x.get("phase")}
        if not m: return {**out,"accepted":False,"reason":"market_missing"}
        if typ=="invalid": return {**out,"accepted":False,"reason":"invalid_format"}
        if fp in x["seen"]: return {**out,"accepted":False,"reason":"duplicate_candidate"}
        if baseline or (x.get("phase")=="EMPTY" and typ=="close"):
            x.update({"phase":"BASELINE","baseline":val,"baselineAt":now(),"source":str(source or "")}); x["seen"][fp]={"at":now(),"decision":"baseline"}
            return {**out,"accepted":False,"reason":"baseline_full_result_ignored","phaseAfter":"BASELINE"}
        if typ=="open":
            if x.get("phase")=="CLOSE": return {**out,"accepted":False,"reason":"stage_regression_after_close"}
            if val==x.get("open"): return {**out,"accepted":False,"reason":"duplicate_open"}
            if x.get("baseline") and clean(x["baseline"]).startswith(val):
                x["seen"][fp]={"at":now(),"decision":"stale_baseline_open"}; return {**out,"accepted":False,"reason":"stale_baseline_open"}
            x.update({"phase":"OPEN","open":val,"close":"","openAt":now(),"source":str(source or "")}); x["seen"][fp]={"at":now(),"decision":"accepted_open"}
            return {**out,"accepted":True,"reason":"fresh_open","phaseAfter":"OPEN"}
        if x.get("phase")!="OPEN" or not x.get("open"): return {**out,"accepted":False,"reason":"fresh_open_missing"}
        if not val.startswith(clean(x["open"])): return {**out,"accepted":False,"reason":"close_open_mismatch","expectedOpen":x.get("open")}
        if val==x.get("baseline"):
            x["seen"][fp]={"at":now(),"decision":"stale_baseline_close"}; return {**out,"accepted":False,"reason":"stale_baseline_close"}
        x.update({"phase":"CLOSE","close":val,"closeAt":now(),"source":str(source or "")}); x["seen"][fp]={"at":now(),"decision":"accepted_close"}
        return {**out,"accepted":True,"reason":"fresh_close","phaseAfter":"CLOSE"}

    def quarantine(st,d):
        st=ensure(st); repaired=[]
        for raw_m,rec in list(st["resultRecords"].setdefault(str(d),{}).items()):
            if not isinstance(rec,dict): continue
            ot,ov=stage(rec.get("openResult")); ct,cv=stage(rec.get("closeResult")); reason=""
            if ct=="close":
                if ot!="open" or rec.get("openInferredFromClose") is True: reason="fresh_open_missing"
                elif not cv.startswith(ov): reason="close_open_mismatch"
            if reason:
                rec.update({"quarantinedCloseResult":cv,"quarantinedCloseReason":reason,"quarantinedCloseAt":now(),"closeResult":"","closeUpdatedAt":"","updatedAt":now()})
                item={"market":market(raw_m),"result":cv,"reason":reason}; repaired.append(item); audit(st,"close_quarantined",item)
        return repaired

    @app.route("/api/result_rules/status",methods=["GET"])
    def rr_status():
        d=request.args.get("date") or today(); st=ensure(state())
        return jsonify({"status":"success","version":VERSION,"date":d,"machines":(st.get("resultRuleState") or {}).get(str(d),{}),"recentAudit":(st.get("resultRuleAudit") or [])[-50:]})

    @app.route("/api/result_rules/validate",methods=["POST"])
    def rr_validate():
        p=request.get_json(silent=True) or {}; d=p.get("date") or today(); st=ensure(state())
        return jsonify({"status":"success","decision":decide(st,d,p.get("market"),p.get("result"),p.get("source"),bool(p.get("baseline")))})

    @app.route("/api/result_rules/ingest",methods=["POST"])
    def rr_ingest():
        p=request.get_json(silent=True) or {}; d=p.get("date") or today(); st=ensure(state()); decision=decide(st,d,p.get("market"),p.get("result"),p.get("source"),bool(p.get("baseline")))
        audit(st,"candidate_decision",decision); put(["resultRuleState",str(d)],(st.get("resultRuleState") or {}).get(str(d),{})); put(["resultRuleAudit"],(st.get("resultRuleAudit") or [])[-1500:])
        return jsonify({"status":"success","accepted":bool(decision.get("accepted")),"decision":decision})

    @app.route("/api/result_rules/repair",methods=["POST"])
    def rr_repair():
        p=request.get_json(silent=True) or {}; d=p.get("date") or today(); st=ensure(state()); fixed=quarantine(st,d)
        put(["resultRecords",str(d)],(st.get("resultRecords") or {}).get(str(d),{})); put(["resultRuleAudit"],(st.get("resultRuleAudit") or [])[-1500:])
        return jsonify({"status":"success","version":VERSION,"date":d,"repaired":fixed,"count":len(fixed)})

    @app.after_request
    def rr_post_write(resp):
        try:
            path=str(request.path or "").lower()
            if request.method not in ("POST","PUT","PATCH") or resp.status_code>=400 or "result" not in path or path.startswith("/api/result_rules/"): return resp
            p=request.get_json(silent=True) or {}; d=p.get("date") or today(); st=ensure(state()); fixed=quarantine(st,d)
            if fixed:
                put(["resultRecords",str(d)],(st.get("resultRecords") or {}).get(str(d),{})); put(["resultRuleAudit"],(st.get("resultRuleAudit") or [])[-1500:]); resp.headers["X-Titan-Result-Repairs"]=str(len(fixed))
        except Exception as exc: print("⚠️ Strict result post-write guard:",exc)
        return resp

    print("✅ Titan strict result state machine loaded",VERSION)
