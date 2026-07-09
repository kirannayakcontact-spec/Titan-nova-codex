"""Make Results/Settlement toggles sticky.

Fixes toggles turning ON again after refresh/sync because legacy /save did not
persist settlementSettings in its normal child-path save allowlist.
"""


def register_settlement_toggle_sticky(app):
    if getattr(app, "_titan_settlement_toggle_sticky_registered", False):
        return
    app._titan_settlement_toggle_sticky_registered = True

    # Patch legacy /save globals so normal full-save writes settlementSettings too.
    try:
        save_view = app.view_functions.get("save")
        g = getattr(save_view, "__globals__", {}) if save_view else {}
        original_put = g.get("_firebase_put_top_level_children")
        if callable(original_put) and not getattr(original_put, "_settlement_sticky_wrapped", False):
            def wrapped_put(state, updates, *args, **kwargs):
                try:
                    if isinstance(state, dict) and isinstance(updates, dict):
                        if "settlementSettings" in state and "settlementSettings" not in updates:
                            updates = dict(updates)
                            updates["settlementSettings"] = state.get("settlementSettings")
                except Exception:
                    pass
                return original_put(state, updates, *args, **kwargs)
            wrapped_put._settlement_sticky_wrapped = True
            g["_firebase_put_top_level_children"] = wrapped_put
    except Exception:
        pass

    from flask import jsonify, request

    def _default_settings():
        return {
            "enabled": True,
            "includeSummaryInResultMessage": True,
            "includeHitMissInResultMessage": False,
            "autoLedgerMarking": True,
            "autoLedgerMarkOnlyWait": True,
            "autoLedgerApplyToAllProfiles": True,
            "autoLedgerRecordResults": True,
        }

    def _bool_from_payload(payload, key, current):
        if key in payload:
            return bool(payload.get(key))
        return current

    @app.route("/api/settlement_toggle_sticky", methods=["POST"])
    def settlement_toggle_sticky_api():
        try:
            payload = request.get_json(silent=True) or {}
            save_view = app.view_functions.get("save")
            g = getattr(save_view, "__globals__", {}) if save_view else {}
            get_state = g.get("migrate_and_get_state")
            put = g.get("_firebase_put_top_level_children")
            if not callable(get_state) or not callable(put):
                return jsonify({"status": "error", "message": "state helpers missing"}), 500
            state = get_state()
            cur = state.get("settlementSettings") if isinstance(state.get("settlementSettings"), dict) else _default_settings()
            for k, v in _default_settings().items():
                cur.setdefault(k, v)
            for key in [
                "enabled",
                "includeSummaryInResultMessage",
                "includeHitMissInResultMessage",
                "autoLedgerMarking",
                "autoLedgerMarkOnlyWait",
                "autoLedgerApplyToAllProfiles",
                "autoLedgerRecordResults",
            ]:
                cur[key] = _bool_from_payload(payload, key, cur.get(key))
            state["settlementSettings"] = cur
            put(state, {"settlementSettings": cur}, audit=False)
            return jsonify({"status": "success", "settlementSettings": cur, "sticky": True})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    print("✅ Settlement toggle sticky patch loaded")
