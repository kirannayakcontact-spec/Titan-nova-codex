"""Disabled compact Ledger UI patch.

Old Ledger UI remains active. This file is kept as a safe no-op so imports do not
break if an old local copy still references it.
"""


def register_ledger_compact_ui(app):
    app._ledger_compact_ui_disabled = True
    return
