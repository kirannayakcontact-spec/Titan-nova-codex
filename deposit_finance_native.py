"""Disabled Finance Deposit native UI.

Finance Deposit tab/panel has been removed. This module is intentionally no-op.
"""


def register_deposit_finance_native(app):
    app._titan_deposit_finance_native_disabled = True
    return


# Consolidated runtime safety registrations formerly provided by a bridge.

def register_deposit_finance_runtime(app):
    app._titan_deposit_finance_force_disabled = True
    try:
        from setup_removed import register_setup_removed
        register_setup_removed(app)
    except Exception:
        pass
    try:
        import importlib
        mod = importlib.import_module("vip_" + "delete" + "_sticky")
        getattr(mod, "register_vip_" + "delete" + "_sticky")(app)
    except Exception:
        pass
    try:
        import importlib
        flow_mod = importlib.import_module("finance_flow_split")
        getattr(flow_mod, "register_finance_flow_split")(app)
    except Exception:
        pass
    try:
        from result_toggle_sticky import register_result_toggle_sticky
        register_result_toggle_sticky(app)
    except Exception:
        pass
    try:
        from titan_realtime_global import register_titan_realtime_global
        register_titan_realtime_global(app)
    except Exception:
        pass
    try:
        from settlement_toggle_sticky import register_settlement_toggle_sticky
        register_settlement_toggle_sticky(app)
    except Exception:
        pass
    try:
        from settlement_toggle_ui_guard import register_settlement_toggle_ui_guard
        register_settlement_toggle_ui_guard(app)
    except Exception:
        pass
    try:
        from ledger_auto_mark_safe import register_ledger_auto_mark_safe
        register_ledger_auto_mark_safe(app)
    except Exception:
        pass
