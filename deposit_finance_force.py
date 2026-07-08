"""Disabled broad Deposit UI injector.

This file intentionally registers no UI injection. The previous version could show
Deposit on Ledger, VIPs, Entries, Results, and other tabs. Deposit must be merged
inside the native Finance renderer only.
"""


def register_deposit_finance_force(app):
    app._titan_deposit_finance_force_disabled = True
    return
