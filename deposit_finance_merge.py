"""Disable old Deposit popup and broad merge injection.

This module only removes the old floating Professional Deposit Desk shortcut that
was registered by deposit_professional_v2. It does not inject any new UI.
"""


def register_deposit_finance_merge(app):
    if getattr(app, "_titan_deposit_finance_merge_guard_registered", False):
        return
    app._titan_deposit_finance_merge_guard_registered = True
    try:
        funcs = app.after_request_funcs.get(None, [])
        app.after_request_funcs[None] = [
            fn for fn in funcs
            if getattr(fn, "__name__", "") != "deposit_professional_existing_tab_shortcut"
        ]
    except Exception:
        pass
