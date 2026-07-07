"""Wallet business logic backed by Firebase REST or a local JSON store."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from backend.services.firebase import get_collection, get_record, push_record, set_record, update_record

DEFAULT_CURRENCY = "EUR"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("amount must be a valid number") from exc
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    return amount.quantize(Decimal("0.01"))


def _wallet_path(user_id: str) -> str:
    if not user_id:
        raise ValueError("user_id is required")
    return f"wallets/{user_id}"


def get_wallet(user_id: str) -> dict:
    """Return a user wallet, creating an empty wallet when needed."""

    wallet = get_record(_wallet_path(user_id)) or {}
    wallet.setdefault("userId", user_id)
    wallet.setdefault("currency", DEFAULT_CURRENCY)
    wallet.setdefault("balance", "0.00")
    wallet.setdefault("held", "0.00")
    wallet.setdefault("updatedAt", _now())
    set_record(_wallet_path(user_id), wallet)
    return wallet


def wallet_summary(user_id: str | None = None) -> dict:
    """Return aggregate wallet totals or one user's wallet summary."""

    if user_id:
        wallet = get_wallet(user_id)
        return {"status": "ok", "module": "wallet", "wallet": wallet}

    wallets = get_collection("wallets")
    total = sum((Decimal(str(wallet.get("balance", "0"))) for wallet in wallets.values()), Decimal("0"))
    held = sum((Decimal(str(wallet.get("held", "0"))) for wallet in wallets.values()), Decimal("0"))
    return {
        "status": "ok",
        "module": "wallet",
        "wallets": len(wallets),
        "totalBalance": f"{total.quantize(Decimal('0.01'))}",
        "totalHeld": f"{held.quantize(Decimal('0.01'))}",
    }


def apply_wallet_transaction(user_id: str, amount: Any, kind: str, description: str = "", reference: str = "") -> dict:
    """Apply a credit/debit to a wallet and append an auditable transaction record."""

    delta = _amount(amount)
    if kind not in {"credit", "debit"}:
        raise ValueError("kind must be credit or debit")

    wallet = get_wallet(user_id)
    balance = Decimal(str(wallet.get("balance", "0")))
    new_balance = balance + delta if kind == "credit" else balance - delta
    if new_balance < 0:
        raise ValueError("insufficient wallet balance")

    wallet["balance"] = f"{new_balance.quantize(Decimal('0.01'))}"
    wallet["updatedAt"] = _now()
    update_record(_wallet_path(user_id), {"balance": wallet["balance"], "updatedAt": wallet["updatedAt"]})

    transaction = {
        "id": uuid4().hex,
        "userId": user_id,
        "type": kind,
        "amount": f"{delta}",
        "currency": wallet.get("currency", DEFAULT_CURRENCY),
        "balanceAfter": wallet["balance"],
        "description": description,
        "reference": reference,
        "createdAt": _now(),
    }
    push_record("wallet_transactions", transaction, transaction["id"])
    return {"wallet": wallet, "transaction": transaction}


def list_wallet_transactions(user_id: str | None = None, limit: int = 50) -> list[dict]:
    transactions = list(get_collection("wallet_transactions").values())
    if user_id:
        transactions = [item for item in transactions if item.get("userId") == user_id]
    transactions.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return transactions[: max(1, min(limit, 200))]
