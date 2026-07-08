"""Finance-only Deposit bridge.

No broad UI injection here. This bridge loads native Finance Deposit, screenshot
proof routes, and screenshot review UI.
"""


def register_deposit_finance_force(app):
    app._titan_deposit_finance_force_disabled = True
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
