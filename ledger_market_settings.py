"""Disabled duplicate Ledger market settings patch.

Market control ka single source ab existing Market tab hai.
"""


def register_ledger_market_settings(app):
    app._ledger_market_settings_disabled = True
    return
