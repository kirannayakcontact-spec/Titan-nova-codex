"""Wallet business logic backed by Firebase REST or a local JSON store."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from backend.services.firebase import get_collection, get_record, mutate_record, push_record, set_record, update_record

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


def _index_key(created_at: str, record_id: str) -> str:
    return f"{created_at}_{record_id}"


def _limited(value: int, maximum: int) -> int:
    return max(1, min(value, maximum))


def _apply_wallet_totals(
    balance_delta: Decimal = Decimal("0"),
    held_delta: Decimal = Decimal("0"),
    wallet_delta: int = 0,
) -> None:
    def update(summary: Any | None) -> dict:
        current = summary if isinstance(summary, dict) else {}
        wallets = int(current.get("wallets", 0)) + wallet_delta
        total = Decimal(str(current.get("totalBalance", "0"))) + balance_delta
        held = Decimal(str(current.get("totalHeld", "0"))) + held_delta
        return {
            "wallets": max(0, wallets),
            "totalBalance": f"{total.quantize(Decimal('0.01'))}",
            "totalHeld": f"{held.quantize(Decimal('0.01'))}",
            "updatedAt": _now(),
        }

    mutate_record("wallet_summary_totals/global", update)


def get_wallet(user_id: str) -> dict:
    """Return a user wallet, creating an empty wallet when needed."""

    existing = get_record(_wallet_path(user_id))
    created = not isinstance(existing, dict) or not existing
    wallet = existing if isinstance(existing, dict) else {}
    wallet.setdefault("userId", user_id)
    wallet.setdefault("currency", DEFAULT_CURRENCY)
    wallet.setdefault("balance", "0.00")
    wallet.setdefault("held", "0.00")
    wallet.setdefault("updatedAt", _now())
    set_record(_wallet_path(user_id), wallet)
    if created:
        _apply_wallet_totals(wallet_delta=1)
    return wallet


def wallet_summary(user_id: str | None = None) -> dict:
    """Return aggregate wallet totals or one user's wallet summary."""

    if user_id:
        wallet = get_wallet(user_id)
        return {"status": "ok", "module": "wallet", "wallet": wallet}

    totals = get_record("wallet_summary_totals/global", {}) or {}
    return {
        "status": "ok",
        "module": "wallet",
        "wallets": int(totals.get("wallets", 0)),
        "totalBalance": str(totals.get("totalBalance", "0.00")),
        "totalHeld": str(totals.get("totalHeld", "0.00")),
    }


def apply_wallet_transaction(
    user_id: str, amount: Any, kind: str, description: str = "", reference: str = ""
) -> dict:
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
    update_record(
        _wallet_path(user_id),
        {"balance": wallet["balance"], "updatedAt": wallet["updatedAt"]},
    )
    _apply_wallet_totals(balance_delta=(delta if kind == "credit" else -delta))

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
    set_record(
        f"wallet_transactions_by_user/{user_id}/{_index_key(transaction['createdAt'], transaction['id'])}",
        transaction,
    )
    return {"wallet": wallet, "transaction": transaction}


def list_wallet_transactions(
    user_id: str | None = None,
    limit: int = 50,
    before_created_at: str | None = None,
) -> list[dict]:
    bounded_limit = _limited(limit, 200)
    if user_id:
        transactions = list(get_collection(f"wallet_transactions_by_user/{user_id}").values())
    else:
        transactions = list(get_collection("wallet_transactions").values())
    if before_created_at:
        transactions = [item for item in transactions if item.get("createdAt", "") < before_created_at]
    transactions.sort(
        key=lambda item: _index_key(item.get("createdAt", ""), item.get("id", "")),
        reverse=True,
    )
    return transactions[:bounded_limit]
