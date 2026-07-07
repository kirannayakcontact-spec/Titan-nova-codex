"""Wallet business logic."""


def wallet_summary() -> dict:
    """Return the initial wallet module status."""

    return {"status": "ok", "module": "wallet", "balance": 0}
