"""Wallet action sticky save override.

Uses existing wallet API paths only:
- /api/wallet_transaction
- /api/wallet_credit_limit
- /api/wallet_zero_settle
- /api/wallet_settings

No new UI, no new API surface. The fix bypasses stale full-sync/idempotency issues
by committing wallet child paths directly to Firebase and returning the latest
wallets/transactions to the existing Finance/Wallet UI.
"""


def register_wallet_action_sticky(app):
    if getattr(app, "_wallet_action_sticky_registered", False):
        return
    app._wallet_action_sticky_registered = True

    from flask import jsonify, request
    import uuid

    def G():
        view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(view, "__globals__", {}) or {}

    def fn(name, default=None):
        return G().get(name, default)

    def now_iso():
        f = fn("_now_iso_local")
        return f() if callable(f) else ""

    def money(v):
        f = fn("_wallet_float")
        if callable(f):
            return f(v)
        try:
            return round(float(v or 0), 2)
        except Exception:
            return 0.0

    def hold(wallet):
        f = fn("_wallet_hold_amount")
        if callable(f):
            return f(wallet)
        return money((wallet or {}).get("hold", (wallet or {}).get("walletHold", 0)))

    def state_now():
        f = fn("migrate_and_get_state")
        return f() if callable(f) else {}

    def ensure_foundation(state):
        f = fn("_ensure_foundation_state")
        if callable(f):
            f(state)
        state.setdefault("wallets", {})
        state.setdefault("walletTransactions", [])
        state.setdefault("auditLog", [])
        state.setdefault("profiles", {})
        state.setdefault("walletSettings", {"defaultCreditLimit": 0, "walletEnabled": True})
        return state

    def ensure_wallet(state, user_id):
        f = fn("_ensure_wallet_for_user")
        if callable(f):
            return f(state, user_id)
        ensure_foundation(state)
        profiles = state.get("profiles", {}) if isinstance(state.get("profiles"), dict) else {}
        if user_id not in profiles:
            return None
        wallets = state.setdefault("wallets", {})
        prof = profiles.get(user_id) or {}
        if not isinstance(wallets.get(user_id), dict):
            wallets[user_id] = {
                "userId": user_id,
                "name": prof.get("name") or user_id,
                "phone": prof.get("phone") or "",
                "balance": 0,
                "hold": 0,
                "walletHold": 0,
                "creditLimit": money((state.get("walletSettings") or {}).get("defaultCreditLimit")),
                "ledger": [],
                "createdAt": now_iso(),
            }
        wallets[user_id].setdefault("ledger", [])
        wallets[user_id].setdefault("hold", wallets[user_id].get("walletHold", 0))
        wallets[user_id].setdefault("walletHold", wallets[user_id].get("hold", 0))
        wallets[user_id].setdefault("balance", 0)
        wallets[user_id].setdefault("creditLimit", 0)
        wallets[user_id]["name"] = wallets[user_id].get("name") or prof.get("name") or user_id
        wallets[user_id]["phone"] = wallets[user_id].get("phone") or prof.get("phone") or ""
        return wallets[user_id]

    def record_tx(state, user_id, wallet, entry):
        f = fn("_record_wallet_transaction")
        if callable(f):
            return f(state, user_id, wallet, entry)
        txns = state.setdefault("walletTransactions", [])
        txn_id = str(entry.get("txnId") or f"{user_id}_{entry.get('id','')}_{entry.get('time','')}_{entry.get('type','')}")[:120]
        entry["txnId"] = txn_id
        row = {
            "id": txn_id,
            "userId": user_id,
            "name": wallet.get("name") or user_id,
            "phone": wallet.get("phone") or "",
            "time": entry.get("time") or now_iso(),
            "type": entry.get("type") or "wallet",
            "amount": money(entry.get("amount")),
            "balanceBefore": money(entry.get("balanceBefore")),
            "balanceAfter": money(entry.get("balanceAfter")),
            "holdBefore": money(entry.get("holdBefore")),
            "holdAfter": money(entry.get("holdAfter")),
            "creditLimit": money(wallet.get("creditLimit")),
            "note": entry.get("note") or entry.get("type") or "Wallet transaction",
            "source": entry.get("source") or "admin_wallet_tab",
            "refId": entry.get("id") or "",
        }
        txns.append(row)
        if len(txns) > 2000:
            del txns[:-2000]
        return row

    def txns(state, user_id=None, limit=500):
        f = fn("_wallet_transactions_from_state")
        if callable(f):
            return f(state, user_id, limit)
        rows = state.get("walletTransactions") if isinstance(state.get("walletTransactions"), list) else []
        if user_id:
            rows = [x for x in rows if str(x.get("userId")) == str(user_id)]
        return rows[-int(limit or 500):]

    def add_audit(state, action, detail):
        f = fn("_add_audit")
        if callable(f):
            return f(state, action, detail)
        log = state.setdefault("auditLog", [])
        log.append({"id": uuid.uuid4().hex[:8].upper(), "time": now_iso(), "action": action, "detail": detail or {}})
        if len(log) > 500:
            del log[:-500]
        return log[-1]

    def put_child(parts, value):
        f = fn("_firebase_put_child")
        if callable(f):
            f(parts, value)
            return True
        return False

    def put_top(state, updates):
        f = fn("_firebase_put_top_level_children")
        if callable(f):
            f(state, updates, audit=False)
            return True
        return False

    def commit_wallet_state(state, user_id):
        wallet = (state.get("wallets") or {}).get(user_id)
        if not isinstance(wallet, dict):
            raise RuntimeError("Wallet missing after mutation")
        if not put_child(["wallets", str(user_id)], wallet):
            if not put_top(state, {"wallets": state.get("wallets", {})}):
                raise RuntimeError("Firebase wallet child save helper missing")
        try:
            put_child(["walletTransactions"], state.get("walletTransactions", [])[-2000:])
        except Exception:
            put_top(state, {"walletTransactions": state.get("walletTransactions", [])[-2000:]})
        try:
            put_child(["auditLog"], state.get("auditLog", [])[-500:])
        except Exception:
            pass
        return wallet

    def response(state, user_id, wallet=None, extra=None):
        payload = {
            "status": "success",
            "walletStickySave": True,
            "wallet": wallet or (state.get("wallets") or {}).get(user_id),
            "wallets": state.get("wallets", {}),
            "walletTransactions": txns(state, None, 500),
        }
        if extra:
            payload.update(extra)
        return jsonify(payload)

    def wallet_transaction_override():
        data = request.get_json(silent=True) or {}
        user_id = str(data.get("userId") or "").strip()
        action = str(data.get("action") or "add").strip().lower()
        note = str(data.get("note") or "").strip()
        amount = money(data.get("amount"))
        if not user_id:
            return jsonify({"status": "error", "message": "userId missing"}), 400
        if action not in ("add", "subtract"):
            return jsonify({"status": "error", "message": "action add/subtract hona chahiye"}), 400
        if amount <= 0:
            return jsonify({"status": "error", "message": "Amount 0 se zyada hona chahiye"}), 400
        state = ensure_foundation(state_now())
        wallet = ensure_wallet(state, user_id)
        if wallet is None:
            return jsonify({"status": "error", "message": "User/profile not found"}), 404
        signed = amount if action == "add" else -amount
        before = money(wallet.get("balance"))
        after = round(before + signed, 2)
        wallet["balance"] = after
        wallet["updatedAt"] = now_iso()
        entry = {
            "id": uuid.uuid4().hex[:8].upper(),
            "time": now_iso(),
            "type": action,
            "amount": signed,
            "balanceBefore": before,
            "balanceAfter": after,
            "holdBefore": hold(wallet),
            "holdAfter": hold(wallet),
            "note": note or ("Manual credit" if action == "add" else "Manual debit"),
            "source": "admin_wallet_tab_sticky",
            "moneyAtomic": True,
            "stickyWalletFix": True,
        }
        wallet.setdefault("ledger", []).append(entry)
        record_tx(state, user_id, wallet, entry)
        add_audit(state, "wallet_transaction_sticky", {"userId": user_id, "amount": signed, "balanceAfter": after, "note": entry["note"]})
        commit_wallet_state(state, user_id)
        return response(state, user_id, wallet, {"action": action, "amount": amount, "balanceAfter": after})

    def wallet_credit_limit_override():
        data = request.get_json(silent=True) or {}
        user_id = str(data.get("userId") or "").strip()
        credit = money(data.get("creditLimit"))
        if not user_id:
            return jsonify({"status": "error", "message": "userId missing"}), 400
        if credit < 0:
            return jsonify({"status": "error", "message": "Credit limit negative nahi ho sakta"}), 400
        state = ensure_foundation(state_now())
        wallet = ensure_wallet(state, user_id)
        if wallet is None:
            return jsonify({"status": "error", "message": "User/profile not found"}), 404
        before_credit = money(wallet.get("creditLimit"))
        wallet["creditLimit"] = credit
        wallet["updatedAt"] = now_iso()
        entry = {
            "id": uuid.uuid4().hex[:8].upper(),
            "time": now_iso(),
            "type": "credit_limit",
            "amount": 0,
            "balanceBefore": money(wallet.get("balance")),
            "balanceAfter": money(wallet.get("balance")),
            "holdBefore": hold(wallet),
            "holdAfter": hold(wallet),
            "note": f"Credit limit {before_credit} → {credit}",
            "source": "admin_wallet_tab_sticky",
            "stickyWalletFix": True,
        }
        wallet.setdefault("ledger", []).append(entry)
        record_tx(state, user_id, wallet, entry)
        add_audit(state, "wallet_credit_limit_sticky", {"userId": user_id, "oldCreditLimit": before_credit, "creditLimit": credit})
        commit_wallet_state(state, user_id)
        return response(state, user_id, wallet, {"creditLimit": credit})

    def wallet_zero_settle_override():
        data = request.get_json(silent=True) or {}
        user_id = str(data.get("userId") or "").strip()
        note = str(data.get("note") or "Zero settle").strip()
        if not user_id:
            return jsonify({"status": "error", "message": "userId missing"}), 400
        state = ensure_foundation(state_now())
        wallet = ensure_wallet(state, user_id)
        if wallet is None:
            return jsonify({"status": "error", "message": "User/profile not found"}), 404
        before = money(wallet.get("balance"))
        wallet["balance"] = 0
        wallet["updatedAt"] = now_iso()
        entry = {
            "id": uuid.uuid4().hex[:8].upper(),
            "time": now_iso(),
            "type": "zero_settle",
            "amount": -before,
            "balanceBefore": before,
            "balanceAfter": 0,
            "holdBefore": hold(wallet),
            "holdAfter": hold(wallet),
            "note": note,
            "source": "admin_wallet_tab_sticky",
            "moneyAtomic": True,
            "stickyWalletFix": True,
        }
        wallet.setdefault("ledger", []).append(entry)
        record_tx(state, user_id, wallet, entry)
        add_audit(state, "wallet_zero_settle_sticky", {"userId": user_id, "oldBalance": before})
        commit_wallet_state(state, user_id)
        return response(state, user_id, wallet, {"balanceAfter": 0, "oldBalance": before})

    def wallet_settings_override():
        data = request.get_json(silent=True) or {}
        state = ensure_foundation(state_now())
        settings = state.setdefault("walletSettings", {"defaultCreditLimit": 0, "walletEnabled": True})
        if "defaultCreditLimit" in data:
            settings["defaultCreditLimit"] = money(data.get("defaultCreditLimit"))
        if "requirePositiveBalance" in data:
            settings["requirePositiveBalance"] = bool(data.get("requirePositiveBalance"))
        if "walletEnabled" in data:
            settings["walletEnabled"] = bool(data.get("walletEnabled"))
        settings["updatedAt"] = now_iso()
        add_audit(state, "wallet_settings_sticky", settings)
        if not put_child(["walletSettings"], settings):
            put_top(state, {"walletSettings": settings})
        return jsonify({"status": "success", "walletSettings": settings, "walletStickySave": True})

    # Override the existing Flask endpoint functions without adding duplicate routes.
    app.view_functions["api_wallet_transaction"] = wallet_transaction_override
    app.view_functions["api_wallet_credit_limit"] = wallet_credit_limit_override
    app.view_functions["api_wallet_zero_settle"] = wallet_zero_settle_override
    app.view_functions["api_wallet_settings"] = wallet_settings_override
    app._wallet_action_sticky_overrides = True
