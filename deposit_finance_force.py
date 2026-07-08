"""Titan Nova safe extension bridge.

Loads safe app extensions without broad Deposit UI injection:
- global realtime engine for all tabs/actions
- native Finance Deposit subtab
- screenshot proof routes
- screenshot review UI
"""


def register_deposit_finance_force(app):
    app._titan_deposit_finance_force_disabled = True
    try:
        from titan_realtime_global import register_titan_realtime_global
        register_titan_realtime_global(app)
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
