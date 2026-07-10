"""Serve the Codex mobile-first Admin Dashboard template.

This patch intentionally keeps all existing Titan Nova API routes intact and only
replaces the root HTML renderer with templates/index.html when the legacy app
boots successfully.
"""
from __future__ import annotations


def register_mobile_admin_dashboard(app):
    from flask import render_template, request

    def mobile_admin_index():
        # The legacy runtime exposes migrate_and_get_state in the original index
        # function globals. Reuse it so the initial render receives the same data
        # shape as /api/state while all mutations continue through existing APIs.
        old_index = app.view_functions.get("index")
        g = getattr(old_index, "__globals__", {}) if old_index else {}
        get_state = g.get("migrate_and_get_state")
        state = get_state() if callable(get_state) else {}
        if not isinstance(state, dict):
            state = {}
        vip_id = request.args.get("vip")
        state["activeId"] = str(vip_id or state.get("activeId") or "admin1")
        return render_template("index.html", state=state)

    app.view_functions["index"] = mobile_admin_index
    return app
