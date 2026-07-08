"""Disabled Deposit screenshot review routes.

Finance Deposit tab/backend has been removed. This module is intentionally no-op.
"""


def register_deposit_screenshot_routes(app, ctx=None):
    app._titan_deposit_screenshot_routes_disabled = True
    return
