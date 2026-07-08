"""Disabled duplicate Entries quick actions patch.

Entries control ka single source ab original Entries tab/system hai.
No extra API, no extra UI injection.
"""


def register_entries_quick_actions(app):
    app._entries_quick_actions_disabled = True
    return
