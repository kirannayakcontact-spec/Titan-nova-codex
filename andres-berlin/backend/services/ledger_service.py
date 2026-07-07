"""Ledger business logic."""


def ledger_summary() -> dict:
    """Return the initial ledger module status."""

    return {"status": "ok", "module": "ledger", "entries": 0}
