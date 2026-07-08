"""Safe patch for Results -> Ledger Auto PASS/FAIL.

Fixes old Firebase ledger buckets that were saved as lists instead of dicts.
The legacy auto-mark code expects bucket.get(...), so list buckets crash with:
'list' object has no attribute 'get'.

This patch normalizes only the auto-mark path and does not delete data.
"""


def register_ledger_auto_mark_safe(app):
    if getattr(app, "_titan_ledger_auto_mark_safe_registered", False):
        return
    app._titan_ledger_auto_mark_safe_registered = True

    target_view = None
    try:
        for rule in app.url_map.iter_rules():
            if str(rule.rule) == "/api/ledger_auto_mark":
                target_view = app.view_functions.get(rule.endpoint)
                break
    except Exception:
        target_view = None
    if not target_view:
        return

    g = getattr(target_view, "__globals__", {}) or {}
    original_for_result = g.get("_ledger_auto_mark_for_result")
    original_all = g.get("_ledger_auto_mark_all_available")

    def _is_dict(v):
        return isinstance(v, dict)

    def _as_dict_bucket(v):
        if isinstance(v, dict):
            return v
        if isinstance(v, list):
            out = {}
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out[str(i)] = item
            return out
        return {}

    def _sanitize_state(state_obj):
        if not isinstance(state_obj, dict):
            return state_obj
        default_settings = g.get("_default_settlement_settings")
        if not isinstance(state_obj.get("settlementSettings"), dict):
            state_obj["settlementSettings"] = default_settings() if callable(default_settings) else {}
        if not isinstance(state_obj.get("profiles"), dict):
            state_obj["profiles"] = {}
        if not isinstance(state_obj.get("resultRecords"), dict):
            state_obj["resultRecords"] = {}
        if not isinstance(state_obj.get("ledgerAutoMarkRecords"), dict):
            state_obj["ledgerAutoMarkRecords"] = {}
        profiles = state_obj.get("profiles") or {}
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            if not isinstance(profile.get("dayRecords"), dict):
                profile["dayRecords"] = {}
            for day in list((profile.get("dayRecords") or {}).values()):
                if not isinstance(day, dict):
                    continue
                for bucket_name in ("data", "jodiData", "pannelData"):
                    if bucket_name in day and not isinstance(day.get(bucket_name), dict):
                        day[bucket_name] = _as_dict_bucket(day.get(bucket_name))
        return state_obj

    def safe_apply(profile, date, typ, idx, win, result, stage, market, only_wait=True):
        if not isinstance(profile, dict):
            return {"checked": 0, "changed": 0, "pass": 0, "fail": 0}
        day_records = profile.get("dayRecords")
        if not isinstance(day_records, dict):
            day_records = {}
            profile["dayRecords"] = day_records
        day = day_records.get(date)
        if not isinstance(day, dict):
            day = {}
            day_records[date] = day

        ledger_dict_for_type = g.get("_ledger_dict_for_type")
        dict_name = ledger_dict_for_type(typ) if callable(ledger_dict_for_type) else ("data" if typ == "ank" else ("jodiData" if typ == "jodi" else "pannelData"))
        bucket = day.get(dict_name)
        if not isinstance(bucket, dict):
            bucket = _as_dict_bucket(bucket)
            day[dict_name] = bucket

        rec = bucket.get(str(idx))
        if rec is None:
            rec = bucket.get(idx)
        if not isinstance(rec, dict):
            return {"checked": 0, "changed": 0, "pass": 0, "fail": 0}

        digit_fn = g.get("_ledger_digit_tokens")
        match_fn = g.get("_ledger_token_match")
        now_fn = g.get("_now_iso_local")
        tokens = digit_fn(rec.get("d", "")) if callable(digit_fn) else []
        if not tokens:
            return {"checked": 0, "changed": 0, "pass": 0, "fail": 0}
        current_status = str(rec.get("s") or "WAIT").upper()
        if only_wait and current_status in ("PASS", "FAIL", "SKIP"):
            return {"checked": 1, "changed": 0, "pass": 0, "fail": 0}
        is_pass = match_fn(tokens, win, typ) if callable(match_fn) else False
        new_status = "PASS" if is_pass else "FAIL"
        if current_status == new_status and rec.get("autoMarkedByResult") == result:
            return {"checked": 1, "changed": 0, "pass": 0, "fail": 0}
        rec["s"] = new_status
        rec["autoMarkedAt"] = now_fn() if callable(now_fn) else ""
        rec["autoMarkedByResult"] = result
        rec["autoMarkStage"] = stage
        rec["autoMarkMarket"] = market
        rec["autoMarkWinDigit"] = win
        bucket[str(idx)] = rec
        return {"checked": 1, "changed": 1, "pass": 1 if new_status == "PASS" else 0, "fail": 1 if new_status == "FAIL" else 0}

    def safe_for_result(state_obj, date, market, stage, result, force=False):
        _sanitize_state(state_obj)
        if callable(original_for_result):
            return original_for_result(state_obj, date, market, stage, result, force=force)
        return {"changed": False, "skipped": True, "reason": "auto_mark_function_missing"}

    def safe_all_available(state_obj, date=None, force=False):
        _sanitize_state(state_obj)
        if callable(original_all):
            return original_all(state_obj, date, force=force)
        return {"changed": False, "results": [], "marked": 0, "pass": 0, "fail": 0}

    g["_apply_ledger_mark_to_profile"] = safe_apply
    g["_ledger_auto_mark_for_result"] = safe_for_result
    g["_ledger_auto_mark_all_available"] = safe_all_available

    print("✅ Ledger Auto Mark safe list/dict patch loaded")
