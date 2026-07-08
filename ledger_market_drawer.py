"""Disabled duplicate Ledger market drawer patch.

Market control ka single source ab existing Market tab hai.
"""


def register_ledger_market_drawer(app):
    app._ledger_market_drawer_disabled = True
    return
