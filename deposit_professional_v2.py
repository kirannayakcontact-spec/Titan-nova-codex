"""Disabled Deposit Professional feature.

Finance Deposit tab/panel/backend has been removed from the active Titan Nova runtime.
This module is intentionally no-op so accidental imports cannot register Deposit routes
or inject Deposit UI again.
"""


def register_deposit_professional_v2(app, ctx=None):
    app._titan_deposit_professional_v2_disabled = True
    return
