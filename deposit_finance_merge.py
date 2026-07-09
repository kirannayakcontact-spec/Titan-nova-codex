"""Disabled Deposit Finance merge.

Finance Deposit tab/panel has been removed. This module is intentionally no-op.
"""


def register_deposit_finance_merge(app):
    app._titan_deposit_finance_merge_disabled = True
    return
