"""Titan Nova strict result state machine.

Rules:
- website full result seen at first scan is baseline only; never declare it
- fresh OPEN (PPP-A) must arrive before CLOSE (PPP-AB-QQQ)
- CLOSE must start with the exact fresh OPEN token
- one market/date progresses only BASELINE -> OPEN -> CLOSE
- duplicate/stale/regressive candidates are idempotently ignored
- invalid stored closes are automatically quarantined after result writes
"""


def register_titan_strict_result_rules(app):
    if getattr(app, "_titan_strict_result_rules_registered", False):
        return
    app._titan_strict_result_rules_registered = True

    import datetime
    import hashlib
    import json
    import re
    import time
    from flask import jsonify, request

    VERSION = "2026-07-10-strict-result-state-machine-v1"

    def globals_map():
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

    def now_iso():
        return datetime.datetime.now().isoformat(timespec="seconds")

    def today():
        g = globals_map()
        fn = g.get("_safe_today")
        if callable(fn):
            try:
                return str(fn())
            except Exception:
                pass
        return datetime.date.today().isoformat()

    def load_state():
        g = globals_map()
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
        g = globals_map()
        fn = g.get("_firebase_put_child")
        if callable(fn):
            return fn(parts, value)
        saver = g.get("save_to_firebase")
        if callable(saver):
            st = load_state()
            cur = st
            for key in parts[:-1]:
                cur = cur.setdefault(str(key), {})
            cur[str(parts[-1])] = value
            return saver(st)
        return False

    def norm_market(value):
        text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()
        aliases = {
            "SRIDEV DAY": "SRIDEVI DAY",
            "TIMEBAZAR": "TIME BAZAR",
            "MADHURDAY": "MADHUR DAY",
            "MILANDAY": "MILAN DAY",
            "RAJDHANIDAY": "RAJDHANI DAY",
            "SUPREMEDAY": "SUPREME DAY",
            "SRIDEVINIGHT": "SRIDEVI NIGHT",
            "MADHURNIGHT": "MADHUR NIGHT",
            "SUPREMENIGHT": "SUPREME NIGHT",
            "MILANNIGHT": "MILAN NIGHT",
            "RAJDHANINIGHT": "RAJDHANI NIGHT",
            "KALYANNIGHT": "KALYAN NIGHT",
            "MAINBAZAR": "MAIN BAZAR",
        }
        compact = text.replace(" ", "")
        return aliases.get(compact, re.sub(r"\s+", " ", text))

    def norm_result(value):
        return re.sub(r"\s+", "", str(value or "").strip().upper())

    def stage(value):
        value = norm_result(value)
        if re.fullmatch(r"\d{3}-\d", value):
            return "open", value
        if re.fullmatch(r"\d{3}-\d{2}-\d{3}", value):
            return "close", value
        return "invalid", value

    def fingerprint(date_key, market, result):
        raw = "|".join((str(date_key), norm_market(market), norm_result(result)))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def ensure(st):
        if not isinstance(st, dict):
            st = {}
        if not isinstance(st.get("resultRecords"), dict):
            st["resultRecords"] = {}
        if not isinstance(st.get("resultRuleState"), dict):
            st["resultRuleState"] = {}
        if not isinstance(st.get("resultRuleAudit"), list):
            st["resultRuleAudit"] = []
        return st

    def audit(st, event, detail):
        rows = st.setdefault("resultRuleAudit", [])
        rows.append({"id": "rr_" + str(int(time.time() * 1000)), "time": now_iso(), "event": event, "detail": detail, "version": VERSION})
        if len(rows) > 1500:
            del rows[:-1500]

    def market_machine(st, date_key, market):
        root = st.setdefault("resultRuleState", {}).setdefault(str(date_key), {})
        rec = root.setdefault(norm_market(market), {})
        rec.setdefault("phase", "EMPTY")
        rec.setdefault("baseline", "")
        rec.setdefault("open", "")
        rec.setdefault("close", "")
        rec.setdefault("seen", {})
        return rec

    def validate(st, date_key, market, candidate, source="", baseline=False):
        st = ensure(st)
        market = norm_market(market)
        typ, value = stage(candidate)
        machine = market_machine(st, date_key, market)
        sig = fingerprint(date_key, market, value)
        base = {"version": VERSION, "date": str(date_key), "market": market, "stage": typ, "result": value, "fingerprint": sig, "phaseBefore": machine.get("phase")}

        if not market:
            return {**base, "accepted": False, "reason": "market_missing"}
        if typ == "invalid":
            return {**base, "accepted": False, "reason": "invalid_format"}
        if sig in machine.get("seen", {}):
            return {**base, "accepted": False, "reason": "duplicate_candidate"}

        # First/full website value is history baseline, not a new close result.
        if baseline or (machine.get("phase") == "EMPTY" and typ == "close"):
            machine["baseline"] = value
            machine["phase"] = "BASELINE"
            machine["baselineAt"] = now_iso()
            machine["seen"][sig] = {"at": now_iso(), "decision": "baseline"}
            return {**base, "accepted": False, "reason": "baseline_full_result_ignored", "phaseAfter": "BASELINE"}

        if typ == "open":
            if machine.get("phase") == "CLOSE":
                return {**base, "accepted": False, "reason": "stage_regression_after_close"}
            if value == machine.get("open"):
                return {**base, "accepted": False, "reason": "duplicate_open"}
            # Fresh open must differ from the open part of the baseline full result.
            baseline_value = norm_result(machine.get("baseline"))
            if baseline_value and baseline_value.startswith(value):
                machine["seen"][sig] = {"at": now_iso(), "decision": "stale_baseline_open"}
                return {**base, "accepted": False, "reason": "stale_baseline_open"}
            machine.update({"phase": "OPEN", "open": value, "close": "", "openAt": now_iso(), "source": str(source or "")})
            machine["seen"][sig] = {"at": now_iso(), "decision": "accepted_open"}
            return {**base, "accepted": True, "reason": "fresh_open", "phaseAfter": "OPEN"}

        # Close rules
        if machine.get("phase") != "OPEN" or not machine.get("open"):
            return {**base, "accepted": False, "reason": "fresh_open_missing"}
        if not value.startswith(norm_result(machine.get("open"))):
            return {**base, "accepted": False, "reason": "close_open_mismatch", "expectedOpen": machine.get("open")}
        if value == machine.get("baseline"):
            machine["seen"][sig] = {"at": now_iso(), "decision": "stale_baseline_close"}
            return {**base, "accepted": False, "reason": "stale_baseline_close"}
        machine.update({"phase": "CLOSE", "close": value, "closeAt": now_iso(), "source": str(source or "")})
        machine["seen"][sig] = {"at": now_iso(), "decision": "accepted_close"}
        return {**base, "accepted": True, "reason": "fresh_close", "phaseAfter": "CLOSE"}

    def quarantine_invalid(st, date_key):
        st = ensure(st)
        date_records = st["resultRecords"].setdefault(str(date_key), {})
        repaired = []
        for raw_market, rec in list(date_records.items()):
            if not isinstance(rec, dict):
                continue
            market = norm_market(raw_market)
            open_type, open_val = stage(rec.get("openResult"))
            close_type, close_val = stage(rec.get("closeResult"))
            reason = ""
            if close_type == "close":
                if open_type != "open" or rec.get("openInferredFromClose") is True:
                    reason = "fresh_open_missing"
                elif not close_val.startswith(open_val):
                    reason = "close_open_mismatch"
            if reason:
                rec["quarantinedCloseResult"] = close_val
                rec["quarantinedCloseReason"] = reason
                rec["quarantinedCloseAt"] = now_iso()
                rec["closeResult"] = ""
                rec["closeUpdatedAt"] = ""
                rec["updatedAt"] = now_iso()
                repaired.append({"market": market, "result": close_val, "reason": reason})
                audit(st, "close_quarantined", repaired[-1])
        return repaired

    @app.route("/api/result_rules/status", methods=["GET"])
    def result_rules_status():
        date_key = request.args.get("date") or today()
        st = ensure(load_state())
        return jsonify({"status": "success", "version": VERSION, "date": date_key, "machines": (st.get("resultRuleState") or {}).get(str(date_key), {}), "recentAudit": (st.get("resultRuleAudit") or [])[-50:]})

    @app.route("/api/result_rules/validate", methods=["POST"])
    def result_rules_validate():
        payload = request.get_json(silent=True) or {}
        date_key = payload.get("date") or today()
        st = ensure(load_state())
        decision = validate(st, date_key, payload.get("market"), payload.get("result"), payload.get("source"), bool(payload.get("baseline")))
        return jsonify({"status": "success", "decision": decision})

    @app.route("/api/result_rules/ingest", methods=["POST"])
    def result_rules_ingest():
        payload = request.get_json(silent=True) or {}
        date_key = payload.get("date") or today()
        st = ensure(load_state())
        decision = validate(st, date_key, payload.get("market"), payload.get("result"), payload.get("source"), bool(payload.get("baseline")))
        audit(st, "candidate_decision", decision)
        put_child(["resultRuleState", str(date_key)], (st.get("resultRuleState") or {}).get(str(date_key), {}))
        put_child(["resultRuleAudit"], (st.get("resultRuleAudit") or [])[-1500:])
        return jsonify({"status": "success", "accepted": bool(decision.get("accepted")), "decision": decision})

    @app.route("/api/result_rules/repair", methods=["POST"])
    def result_rules_repair():
        payload = request.get_json(silent=True) or {}
        date_key = payload.get("date") or today()
        st = ensure(load_state())
        repaired = quarantine_invalid(st, date_key)
        put_child(["resultRecords", str(date_key)], (st.get("resultRecords") or {}).get(str(date_key), {}))
        put_child(["resultRuleAudit"], (st.get("resultRuleAudit") or [])[-1500:])
        return jsonify({"status": "success", "version": VERSION, "date": date_key, "repaired": repaired, "count": len(repaired)})

    # Any successful result-related write receives a post-write integrity pass.
    @app.after_request
    def strict_result_post_write_guard(resp):
        try:
            path = str(request.path or "").lower()
            if request.method not in ("POST", "PUT", "PATCH") or resp.status_code >= 400:
                return resp
            if "result" not in path or path.startswith("/api/result_rules/"):
                return resp
            payload = request.get_json(silent=True) or {}
            date_key = payload.get("date") or today()
            st = ensure(load_state())
            repaired = quarantine_invalid(st, date_key)
            if repaired:
                put_child(["resultRecords", str(date_key)], (st.get("resultRecords") or {}).get(str(date_key), {}))
                put_child(["resultRuleAudit"], (st.get("resultRuleAudit") or [])[-1500:])
                resp.headers["X-Titan-Result-Repairs"] = str(len(repaired))
        except Exception as exc:
            print("⚠️ Strict result post-write guard:", exc)
        return resp

    print("✅ Titan strict result state machine loaded", VERSION)
