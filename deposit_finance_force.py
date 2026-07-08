"""Titan Nova safe extension bridge."""


def register_deposit_finance_force(app):
    app._titan_deposit_finance_force_disabled = True
    try:
        from titan_realtime_global import register_titan_realtime_global
        register_titan_realtime_global(app)
    except Exception:
        pass
    try:
        from ledger_market_settings import register_ledger_market_settings
        register_ledger_market_settings(app)
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
    try:
        from deposit_finance_native import register_deposit_finance_native
        register_deposit_finance_native(app)
    except Exception:
        pass
    try:
        from deposit_screenshot_routes import register_deposit_screenshot_routes
        register_deposit_screenshot_routes(app)
    except Exception:
        pass
    try:
        from deposit_screenshot_ui import register_deposit_screenshot_ui
        register_deposit_screenshot_ui(app)
    except Exception:
        pass
