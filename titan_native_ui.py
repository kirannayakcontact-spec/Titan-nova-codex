"""Disabled native UI shell.

Single-source cleanup: this module intentionally does not inject any Home/native UI.
The app must use the original tab UI unless a future approved UI replacement edits
the owning tab directly.
"""


def register_titan_native_ui(app):
    app._titan_native_ui_disabled = True
    return
