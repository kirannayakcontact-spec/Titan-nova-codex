"""Disabled Deposit screenshot review UI.

Finance Deposit tab/panel has been removed. This module is intentionally no-op.
"""


def register_deposit_screenshot_ui(app):
    app._titan_deposit_screenshot_ui_disabled = True
    return
