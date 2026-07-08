"""Finance-only Deposit bridge.

No broad UI injection here. This bridge loads the native Finance Deposit subtab.
"""


def register_deposit_finance_force(app):
    app._titan_deposit_finance_force_disabled = True
    try:
        from deposit_finance_native import register_deposit_finance_native
        register_deposit_finance_native(app)
    except Exception:
        pass
