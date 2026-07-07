"""Ledger business logic backed by the shared runtime store."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from backend.services.firebase import get_collection, push_record, set_record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("amount must be a valid number") from exc


def create_ledger_entry(account: str, amount: Any, entry_type: str, description: str = "", reference: str = "") -> dict:
    if not account:
        raise ValueError("account is required")
    if entry_type not in {"credit", "debit"}:
        raise ValueError("entry_type must be credit or debit")
    entry = {
        "id": uuid4().hex,
        "account": account,
        "type": entry_type,
        "amount": _money(amount),
        "description": description,
        "reference": reference,
        "createdAt": _now(),
    }
    push_record("ledger_entries", entry, entry["id"])
    return entry


def list_ledger_entries(account: str | None = None, limit: int = 100) -> list[dict]:
    entries = list(get_collection("ledger_entries").values())
    if account:
        entries = [entry for entry in entries if entry.get("account") == account]
    entries.sort(key=lambda entry: entry.get("createdAt", ""), reverse=True)
    return entries[: max(1, min(limit, 500))]


def ledger_summary(account: str | None = None) -> dict:
    """Return ledger totals from persisted entries."""

    entries = list_ledger_entries(account=account, limit=500)
    credits = sum((Decimal(entry["amount"]) for entry in entries if entry.get("type") == "credit"), Decimal("0"))
    debits = sum((Decimal(entry["amount"]) for entry in entries if entry.get("type") == "debit"), Decimal("0"))
    return {
        "status": "ok",
        "module": "ledger",
        "entries": len(entries),
        "credits": f"{credits.quantize(Decimal('0.01'))}",
        "debits": f"{debits.quantize(Decimal('0.01'))}",
        "balance": f"{(credits - debits).quantize(Decimal('0.01'))}",
    }


def record_market(symbol: str, price: Any, source: str = "manual") -> dict:
    if not symbol:
        raise ValueError("symbol is required")
    quote = {"symbol": symbol.upper(), "price": _money(price), "source": source, "updatedAt": _now()}
    set_record(f"markets/{quote['symbol']}", quote)
    return quote
