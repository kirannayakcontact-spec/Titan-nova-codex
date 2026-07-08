# ==========================================================
# TITAN NOVA LEGACY RUNTIME LAUNCHER + DEPOSIT PROFESSIONAL V2
# Run UI/API: python flask_app.py
#
# The full previous Titan Nova Flask runtime is preserved in:
#   legacy-backup/flask_app.py.bak
# This launcher executes that restored runtime, then adds the professional
# deposit admin layer without replacing the old monolith.
# ==========================================================

from pathlib import Path
import os

_LEGACY_FILE = Path(__file__).resolve().parent / "legacy-backup" / "flask_app.py.bak"

if not _LEGACY_FILE.exists():
    raise FileNotFoundError(f"Missing legacy Titan Nova runtime: {_LEGACY_FILE}")

# Execute the old runtime as a loaded module, not as __main__, so we can register
# upgrades before starting Flask.
_legacy_globals = {
    "__name__": "titan_legacy_runtime",
    "__file__": str(_LEGACY_FILE),
    "__package__": None,
}
code = _LEGACY_FILE.read_text(encoding="utf-8")
exec(compile(code, str(_LEGACY_FILE), "exec"), _legacy_globals, _legacy_globals)
globals().update(_legacy_globals)

app = _legacy_globals.get("app")
if app is None:
    raise RuntimeError("Titan Nova legacy runtime did not expose Flask app")


def _titan_dep_now():
    fn = globals().get("_now_iso") or globals().get("_now_iso_local")
    if callable(fn):
        try:
            return fn()
        except Exception:
            pass
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _titan_dep_money(value):
    fn = globals().get("_money_amount")
    if callable(fn):
        try:
            return fn(value)
        except Exception:
            pass
    try:
        amount = float(str(value or "0").replace(",", "").strip())
    except Exception:
        amount = 0.0
    return round(amount, 2) if amount > 0 else None


def _titan_dep_norm_utr(value):
    fn = globals().get("_normalize_utr")
    if callable(fn):
        return fn(value)
    import re
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:80]


def _titan_dep_utr_hash(value):
    fn = globals().get("_utr_hash")
    if callable(fn):
        return fn(value)
    import hashlib
    return hashlib.sha256(_titan_dep_norm_utr(value).encode("utf-8")).hexdigest()


def _titan_dep_phone(value):
    fn = globals().get("_normalize_phone")
    if callable(fn):
        return fn(value)
    import re
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _titan_dep_id():
    fn = globals().get("_new_deposit_id")
    if callable(fn):
        return fn()
    import datetime, random
    return "DEP-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + str(random.randint(1000, 9999))


def _titan_dep_fb_get(parts, default=None):
    return globals()["_fb_get"](parts, default=default)


def _titan_dep_fb_put(parts, value):
    return globals()["_fb_put"](parts, value)


def _titan_dep_fb_patch(parts, value):
    return globals()["_fb_patch"](parts, value)


def _titan_dep_audit(deposit_id, event, detail=None):
    fn = globals().get("_audit")
    if callable(fn):
        try:
            return fn(deposit_id, event, detail or {})
        except Exception:
            pass
    import uuid
    rec = {"id": uuid.uuid4().hex[:12], "depositId": deposit_id, "event": event, "time": _titan_dep_now(), "detail": detail or {}, "version": "deposit_professional_v2"}
    _titan_dep_fb_put(["depositAuditLog", deposit_id, rec["id"]], rec)
    return rec


def _titan_dep_settings():
    base_fn = globals().get("_get_deposit_settings")
    settings = base_fn() if callable(base_fn) else {}
    if not isinstance(settings, dict):
        settings = {}
    settings.setdefault("enabled", True)
    settings.setdefault("paymentName", "TITAN NOVA")
    settings.setdefault("upiId", "")
    settings.setdefault("accountName", settings.get("paymentName") or "TITAN NOVA")
    settings.setdefault("qrImageUrl", "")
    settings.setdefault("minDeposit", 1)
    settings.setdefault("maxDeposit", 100000)
    settings.setdefault("manualApproval", True)
    settings.setdefault("requireUtr", True)
    settings.setdefault("requireScreenshot", False)
    settings.setdefault("autoCreditOnApprove", True)
    settings.setdefault("duplicateUtrGuard", True)
    settings.setdefault("rejectReasonRequired", True)
    settings.setdefault("adminNote", "")
    settings.setdefault("version", "deposit_professional_v2")
    return settings


def _titan_dep_save_settings(data):
    data = data or {}
    save_fn = globals().get("_save_deposit_settings")
    allowed_existing = {
        "enabled", "paymentName", "upiId", "accountName", "bankName", "qrImageUrl",
        "minDeposit", "maxDeposit", "manualApproval", "autoWhatsapp", "adminNote",
        "allowedReceiverAccounts", "activeReceiverId", "receiverMatchRequired", "allowWeakNameMatch"
    }
    if callable(save_fn):
        settings = save_fn({k: v for k, v in data.items() if k in allowed_existing})
    else:
        settings = _titan_dep_settings()
    extra = {}
    for key in ("requireUtr", "requireScreenshot", "autoCreditOnApprove", "duplicateUtrGuard", "rejectReasonRequired"):
        if key in data:
            extra[key] = bool(data.get(key))
    for key in ("receiptTemplate", "qrMessageTemplate", "approvalMessageTemplate", "rejectionMessageTemplate"):
        if key in data:
            extra[key] = str(data.get(key) or "")[:2000]
    if extra:
        extra["version"] = "deposit_professional_v2"
        extra["updatedAt"] = _titan_dep_now()
        _titan_dep_fb_patch(["depositSettings", "v1"], extra)
        settings.update(extra)
    return _titan_dep_settings()


def _titan_dep_enrich(rec, settings=None):
    settings = settings or _titan_dep_settings()
    enrich_fn = globals().get("_enrich_deposit_record")
    out = enrich_fn(rec, settings) if callable(enrich_fn) else dict(rec or {})
    if not isinstance(out, dict):
        out = dict(rec or {})
    user_id = str(out.get("userId") or out.get("profileId") or "").strip()
    wallet = _titan_dep_fb_get(["wallets", user_id], default={}) if user_id and user_id != "guest" else {}
    balance = 0
    if isinstance(wallet, dict):
        try:
            balance = round(float(wallet.get("balance") or 0), 2)
        except Exception:
            balance = 0
    amount = _titan_dep_money(out.get("amount")) or 0
    out["professional"] = {
        "version": "deposit_professional_v2",
        "currentWalletBalance": balance,
        "newBalancePreview": round(balance + amount, 2),
        "requiresUtr": bool(settings.get("requireUtr", True)),
        "requiresScreenshot": bool(settings.get("requireScreenshot", False)),
        "autoCreditOnApprove": bool(settings.get("autoCreditOnApprove", True)),
        "hasUtr": bool(out.get("utr")),
        "hasProof": bool(out.get("proofUrl") or out.get("screenshotUrl")),
    }
    return out


def _titan_dep_records(status_filter="", limit=50):
    records = _titan_dep_fb_get(["depositRequests"], default={})
    items = list(records.values()) if isinstance(records, dict) else []
    if status_filter:
        sf = str(status_filter).strip().lower()
        items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").lower() == sf]
    items.sort(key=lambda x: str((x or {}).get("updatedAt") or (x or {}).get("createdAt") or ""), reverse=True)
    return items[: max(1, min(int(limit or 50), 500))], items


def _titan_dep_stats(items):
    fn = globals().get("_deposit_stats")
    if callable(fn):
        try:
            return fn(items)
        except Exception:
            pass
    stats = {"total": 0, "amount": 0, "pendingCount": 0, "pendingAmount": 0, "approvedAmount": 0, "rejectedAmount": 0, "byStatus": {}}
    for item in items:
        if not isinstance(item, dict):
            continue
        amt = float(item.get("amount") or 0)
        st = str(item.get("status") or "payment_pending").lower()
        stats["total"] += 1
        stats["amount"] = round(stats["amount"] + amt, 2)
        stats["byStatus"].setdefault(st, {"count": 0, "amount": 0})
        stats["byStatus"][st]["count"] += 1
        stats["byStatus"][st]["amount"] = round(stats["byStatus"][st]["amount"] + amt, 2)
        if st in ("payment_pending", "payment_submitted", "under_verification"):
            stats["pendingCount"] += 1
            stats["pendingAmount"] = round(stats["pendingAmount"] + amt, 2)
        elif st == "approved":
            stats["approvedAmount"] = round(stats["approvedAmount"] + amt, 2)
        elif st == "rejected":
            stats["rejectedAmount"] = round(stats["rejectedAmount"] + amt, 2)
    return stats


def _register_deposit_professional_v2(flask_app):
    if getattr(flask_app, "_titan_deposit_professional_v2_registered", False):
        return
    flask_app._titan_deposit_professional_v2_registered = True

    from flask import jsonify, request, Response

    @flask_app.route("/api/deposit_professional/status", methods=["GET"])
    def titan_deposit_professional_status():
        settings = _titan_dep_settings()
        _, all_items = _titan_dep_records(limit=500)
        return jsonify({
            "status": "success",
            "feature": "deposit_professional_v2",
            "version": "2026-07-08-deposit-professional-v2",
            "open": "/api/deposit_professional/admin_ui",
            "settings": settings,
            "stats": _titan_dep_stats(all_items),
            "flow": ["request", "payment_pending", "payment_submitted", "under_verification", "approved/rejected"],
        })

    @flask_app.route("/api/deposit_professional/settings", methods=["GET", "POST"])
    def titan_deposit_professional_settings():
        try:
            if request.method == "GET":
                return jsonify({"status": "success", "settings": _titan_dep_settings()})
            data = request.get_json(silent=True) or {}
            settings = _titan_dep_save_settings(data)
            _titan_dep_audit("SETTINGS", "deposit_professional_settings_saved", {"keys": sorted(data.keys())})
            return jsonify({"status": "success", "settings": settings})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @flask_app.route("/api/deposit_professional/list", methods=["GET"])
    def titan_deposit_professional_list():
        try:
            limit = request.args.get("limit") or 80
            status_filter = request.args.get("status") or ""
            settings = _titan_dep_settings()
            shown, all_items = _titan_dep_records(status_filter=status_filter, limit=limit)
            return jsonify({
                "status": "success",
                "deposits": [_titan_dep_enrich(x, settings) for x in shown],
                "count": len(shown),
                "stats": _titan_dep_stats(all_items),
                "settings": settings,
            })
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @flask_app.route("/api/deposit_professional/create", methods=["POST"])
    def titan_deposit_professional_create():
        try:
            data = request.get_json(silent=True) or {}
            settings = _titan_dep_settings()
            if not settings.get("enabled", True):
                return jsonify({"status": "error", "message": "Deposit disabled"}), 403
            amount = _titan_dep_money(data.get("amount"))
            if amount is None:
                return jsonify({"status": "error", "message": "Valid amount required"}), 400
            min_dep = float(settings.get("minDeposit") or 0)
            max_dep = float(settings.get("maxDeposit") or 0)
            if min_dep and amount < min_dep:
                return jsonify({"status": "error", "message": f"Minimum deposit ₹{min_dep:g}"}), 400
            if max_dep and amount > max_dep:
                return jsonify({"status": "error", "message": f"Maximum deposit ₹{max_dep:g}"}), 400
            utr = _titan_dep_norm_utr(data.get("utr") or data.get("utrNumber") or data.get("transactionId"))
            if utr and settings.get("duplicateUtrGuard", True):
                existing = _titan_dep_fb_get(["depositUtrIndex", _titan_dep_utr_hash(utr)], default=None)
                if existing:
                    return jsonify({"status": "error", "message": "Duplicate UTR blocked", "existing": existing}), 409
            proof_url = str(data.get("proofUrl") or data.get("screenshotUrl") or data.get("imageUrl") or "").strip()
            deposit_id = str(data.get("depositId") or "").strip() or _titan_dep_id()
            user_id = str(data.get("userId") or data.get("profileId") or data.get("customerId") or "guest").strip() or "guest"
            status = "payment_submitted" if (utr or proof_url) else "payment_pending"
            rec = {
                "id": deposit_id,
                "depositId": deposit_id,
                "version": "deposit_professional_v2",
                "status": status,
                "stage": status,
                "userId": user_id,
                "profileId": str(data.get("profileId") or user_id),
                "customerName": str(data.get("customerName") or data.get("name") or "").strip(),
                "phoneNumber": _titan_dep_phone(data.get("phoneNumber") or data.get("phone") or ""),
                "amount": amount,
                "utr": utr,
                "proofUrl": proof_url,
                "note": str(data.get("note") or "").strip()[:500],
                "createdAt": _titan_dep_now(),
                "updatedAt": _titan_dep_now(),
                "payment": {
                    "upiId": settings.get("upiId", ""),
                    "accountName": settings.get("accountName", ""),
                    "paymentName": settings.get("paymentName", ""),
                    "qrImageUrl": settings.get("qrImageUrl", ""),
                },
                "walletCredit": {"applied": False, "source": "deposit_professional_v2"},
                "professional": {"createdByV2": True, "proofRequired": bool(settings.get("requireScreenshot")), "utrRequired": bool(settings.get("requireUtr", True))},
            }
            _titan_dep_fb_put(["depositRequests", deposit_id], rec)
            if utr:
                _titan_dep_fb_put(["depositUtrIndex", _titan_dep_utr_hash(utr)], {"depositId": deposit_id, "utr": utr, "amount": amount, "createdAt": rec["createdAt"]})
            _titan_dep_audit(deposit_id, "deposit_professional_created", {"amount": amount, "status": status, "userId": user_id})
            return jsonify({"status": "success", "deposit": _titan_dep_enrich(rec, settings), "nextStep": "Admin verify kare" if status == "payment_submitted" else "User ko QR/UPI bheje"})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @flask_app.route("/api/deposit_professional/action", methods=["POST"])
    def titan_deposit_professional_action():
        try:
            data = request.get_json(silent=True) or {}
            deposit_id = str(data.get("depositId") or data.get("id") or "").strip()
            if not deposit_id:
                return jsonify({"status": "error", "message": "depositId required"}), 400
            rec = _titan_dep_fb_get(["depositRequests", deposit_id], default=None)
            if not isinstance(rec, dict):
                return jsonify({"status": "error", "message": "Deposit not found"}), 404
            settings = _titan_dep_settings()
            action = str(data.get("action") or data.get("status") or "").strip().lower()
            status_map = {
                "submit": "payment_submitted",
                "submitted": "payment_submitted",
                "verify": "under_verification",
                "under_verification": "under_verification",
                "approve": "approved",
                "approved": "approved",
                "reject": "rejected",
                "rejected": "rejected",
                "cancel": "cancelled",
                "cancelled": "cancelled",
            }
            new_status = status_map.get(action)
            if not new_status:
                return jsonify({"status": "error", "message": "Invalid action", "allowed": sorted(status_map.keys())}), 400
            current_status = str(rec.get("status") or "payment_pending").lower()
            allowed = (globals().get("_DEPOSIT_ACTIONS") or {}).get(current_status, [])
            if allowed and new_status not in allowed and not bool(data.get("force")):
                return jsonify({"status": "error", "message": f"Status flow blocked: {current_status} -> {new_status}", "allowedNextStatuses": allowed}), 409
            updates = {"status": new_status, "stage": new_status, "updatedAt": _titan_dep_now(), "lastUpdatedBy": str(data.get("updatedBy") or "admin").strip()[:80]}
            if "utr" in data or "utrNumber" in data or "transactionId" in data:
                updates["utr"] = _titan_dep_norm_utr(data.get("utr") or data.get("utrNumber") or data.get("transactionId"))
            if "proofUrl" in data or "screenshotUrl" in data or "imageUrl" in data:
                updates["proofUrl"] = str(data.get("proofUrl") or data.get("screenshotUrl") or data.get("imageUrl") or "").strip()
            for key in ("adminNote", "verificationNote", "rejectReason"):
                if key in data:
                    updates[key] = str(data.get(key) or "").strip()[:1000]
            fresh_preview = dict(rec)
            fresh_preview.update(updates)
            utr = _titan_dep_norm_utr(fresh_preview.get("utr"))
            proof = str(fresh_preview.get("proofUrl") or fresh_preview.get("screenshotUrl") or "").strip()
            if new_status in ("payment_submitted", "under_verification", "approved") and settings.get("requireUtr", True) and not utr:
                return jsonify({"status": "error", "message": "UTR required before verification/approval"}), 400
            if new_status in ("payment_submitted", "under_verification", "approved") and settings.get("requireScreenshot", False) and not proof:
                return jsonify({"status": "error", "message": "Screenshot/proof required before verification/approval"}), 400
            if utr and settings.get("duplicateUtrGuard", True):
                existing = _titan_dep_fb_get(["depositUtrIndex", _titan_dep_utr_hash(utr)], default=None)
                if isinstance(existing, dict) and str(existing.get("depositId")) not in ("", deposit_id):
                    return jsonify({"status": "error", "message": "Duplicate UTR blocked", "existing": existing}), 409
                updates["utr"] = utr
            if new_status == "approved":
                updates["approvedAt"] = _titan_dep_now()
                updates["approvedBy"] = updates["lastUpdatedBy"]
                if settings.get("autoCreditOnApprove", True):
                    credit_fn = globals().get("_deposit_wallet_credit")
                    if callable(credit_fn):
                        wallet, wallet_credit = credit_fn(fresh_preview, updates["approvedBy"])
                        updates["walletCredit"] = wallet_credit
                        updates["walletCredited"] = bool(wallet_credit.get("applied")) if isinstance(wallet_credit, dict) else False
                        if isinstance(wallet_credit, dict) and wallet_credit.get("applied"):
                            updates["walletCreditAmount"] = wallet_credit.get("amount")
                            updates["walletBalanceAfter"] = wallet_credit.get("balanceAfter")
                        else:
                            updates["walletCreditError"] = (wallet_credit or {}).get("reason", "wallet_credit_failed") if isinstance(wallet_credit, dict) else "wallet_credit_failed"
                    else:
                        updates["walletCreditError"] = "wallet_credit_function_missing"
            if new_status == "rejected":
                reason = str(updates.get("rejectReason") or data.get("reason") or "").strip()
                if settings.get("rejectReasonRequired", True) and not reason:
                    return jsonify({"status": "error", "message": "Reject reason required"}), 400
                updates["rejectReason"] = reason
                updates["rejectedAt"] = _titan_dep_now()
            _titan_dep_fb_patch(["depositRequests", deposit_id], updates)
            if updates.get("utr"):
                _titan_dep_fb_put(["depositUtrIndex", _titan_dep_utr_hash(updates["utr"])], {"depositId": deposit_id, "utr": updates["utr"], "amount": fresh_preview.get("amount"), "updatedAt": updates["updatedAt"]})
            fresh = dict(rec)
            fresh.update(updates)
            _titan_dep_audit(deposit_id, "deposit_professional_action", {"action": action, "newStatus": new_status, "updates": updates})
            queue_fn = globals().get("_queue_deposit_message")
            if callable(queue_fn) and new_status in ("approved", "rejected"):
                try:
                    if new_status == "approved":
                        wc = fresh.get("walletCredit") if isinstance(fresh.get("walletCredit"), dict) else {}
                        text = f"✅ *Deposit Approved*\n\n🆔 ID: {deposit_id}\n💵 Amount: ₹{float(fresh.get('amount') or 0):g}\n💰 New Balance: ₹{float(wc.get('balanceAfter') or fresh.get('walletBalanceAfter') or 0):g}\n✅ Wallet updated successfully."
                    else:
                        text = f"❌ *Deposit Rejected*\n\n🆔 ID: {deposit_id}\n💵 Amount: ₹{float(fresh.get('amount') or 0):g}\n📝 Reason: {fresh.get('rejectReason') or 'Payment proof not matched'}"
                    queue_fn(fresh, text, {"type": "deposit_professional_" + new_status, "depositId": deposit_id})
                except Exception:
                    pass
            return jsonify({"status": "success", "deposit": _titan_dep_enrich(fresh, settings), "updates": updates})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @flask_app.route("/api/deposit_professional/admin_ui", methods=["GET"])
    def titan_deposit_professional_admin_ui():
        return Response(_titan_deposit_professional_html(), mimetype="text/html")


def _titan_deposit_professional_html():
    return r"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Titan Nova Deposit Desk</title>
<style>
:root{--bg:#07111f;--card:#101d2f;--line:#243e5f;--txt:#eef6ff;--muted:#91afd1;--brand:#2aabee;--ok:#22c55e;--danger:#ff4d6d;--warn:#fbbf24}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#07111f,#0c1728);color:var(--txt);font-family:Inter,Arial,sans-serif;padding:14px}.wrap{max-width:1040px;margin:0 auto}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px}.title{font-weight:900;font-size:22px}.badge{background:rgba(34,197,94,.18);border:1px solid rgba(34,197,94,.35);color:#a7f3d0;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:900}.grid{display:grid;grid-template-columns:1fr;gap:12px}@media(min-width:850px){.grid{grid-template-columns:.95fr 1.2fr}}.card{background:rgba(16,29,47,.95);border:1px solid rgba(42,171,238,.22);border-radius:18px;padding:14px;box-shadow:0 12px 35px rgba(0,0,0,.28)}label{font-size:11px;color:var(--muted);font-weight:900;text-transform:uppercase;display:block;margin:10px 0 6px}input,textarea,select{width:100%;background:#07111f;border:1px solid var(--line);border-radius:13px;color:var(--txt);padding:12px;font-size:14px}textarea{min-height:70px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.tog{display:flex;align-items:center;justify-content:space-between;gap:8px;background:#14243a;border:1px solid var(--line);border-radius:13px;padding:10px;margin-top:8px}.tog input{width:auto}button{border:0;border-radius:13px;padding:11px 12px;background:var(--brand);color:#fff;font-weight:900;margin-top:10px}.btns{display:flex;gap:8px;flex-wrap:wrap}.btns button{margin-top:8px}.ok{background:var(--ok);color:#062013}.danger{background:var(--danger)}.soft{background:#263b59}.stat{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:10px}@media(min-width:650px){.stat{grid-template-columns:repeat(4,1fr)}}.stat div{background:#0b1727;border:1px solid var(--line);border-radius:14px;padding:10px}.stat b{display:block;font-size:18px}.stat span{color:var(--muted);font-size:11px}.item{background:#0b1727;border:1px solid var(--line);border-radius:16px;padding:12px;margin:9px 0}.pill{display:inline-block;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900;margin-left:6px}.pill.approved{background:rgba(34,197,94,.18);color:#a7f3d0}.pill.rejected{background:rgba(255,77,109,.18);color:#ffc2cc}.pill.payment_pending,.pill.under_verification{background:rgba(251,191,36,.16);color:#fde68a}.pill.payment_submitted{background:rgba(42,171,238,.18);color:#bfdbfe}.muted{color:var(--muted);font-size:12px;line-height:1.45}.status{background:#0b1727;border:1px solid var(--line);border-radius:13px;padding:10px;margin:10px 0;color:var(--muted);white-space:pre-wrap}.copy{font-family:ui-monospace,monospace;background:#07111f;border:1px dashed var(--line);border-radius:12px;padding:8px;margin-top:8px;color:#b8d8ff;font-size:12px;overflow:auto}.proof{max-width:100%;max-height:120px;border-radius:12px;margin-top:8px;border:1px solid var(--line)}
</style></head><body><div class="wrap"><div class="top"><div><div class="title">💰 Titan Nova Deposit Desk</div><div class="muted">Professional admin-side deposit verification + wallet credit</div></div><span class="badge">V2 ACTIVE</span></div><div class="stat" id="stats"><div><b>-</b><span>Total</span></div><div><b>-</b><span>Pending</span></div><div><b>-</b><span>Pending ₹</span></div><div><b>-</b><span>Total ₹</span></div></div><div class="grid"><div class="card"><h3>Payment Settings</h3><label>Payment Name</label><input id="paymentName"><label>UPI ID</label><input id="upiId"><label>Account Name</label><input id="accountName"><label>QR Image URL</label><input id="qrImageUrl"><div class="row"><div><label>Min Deposit</label><input id="minDeposit" type="number"></div><div><label>Max Deposit</label><input id="maxDeposit" type="number"></div></div><div class="tog"><span>Require UTR</span><input id="requireUtr" type="checkbox"></div><div class="tog"><span>Require Screenshot</span><input id="requireScreenshot" type="checkbox"></div><div class="tog"><span>Auto wallet credit on approve</span><input id="autoCreditOnApprove" type="checkbox"></div><div class="tog"><span>Duplicate UTR guard</span><input id="duplicateUtrGuard" type="checkbox"></div><label>Admin Note</label><textarea id="adminNote"></textarea><button onclick="saveSettings()">💾 Save Settings</button><div class="status" id="msg">Loading...</div><hr style="border-color:#243e5f;border-style:solid;border-width:1px 0 0;margin:16px 0"><h3>Create Manual Deposit</h3><div class="row"><div><label>User ID/Profile ID</label><input id="newUserId"></div><div><label>Phone</label><input id="newPhone"></div></div><label>Name</label><input id="newName"><label>Amount</label><input id="newAmount" type="number"><label>UTR</label><input id="newUtr"><label>Screenshot URL</label><input id="newProof"><button class="soft" onclick="createDeposit()">➕ Create Deposit</button></div><div class="card"><div class="btns"><select id="filter" onchange="loadList()"><option value="">All</option><option value="payment_pending">Payment Pending</option><option value="payment_submitted">Submitted</option><option value="under_verification">Verifying</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select><button class="soft" onclick="loadList()">Refresh</button></div><div id="list" style="margin-top:10px"></div></div></div></div>
<script>
const API='/api/deposit_professional';
const $=id=>document.getElementById(id);function token(){return localStorage.getItem('TITAN_ADMIN_TOKEN')||''}async function j(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});if(token())opt.headers['X-Titan-Admin-Token']=token();let r=await fetch(url,opt);let x=await r.json().catch(()=>({status:'error',message:'Invalid JSON'}));if(!r.ok||x.status==='error')throw new Error(x.message||('HTTP '+r.status));return x}function esc(v){return String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}function setMsg(t){$('msg').textContent=t}function fill(s){['paymentName','upiId','accountName','qrImageUrl','adminNote'].forEach(k=>$(k).value=s[k]||'');['minDeposit','maxDeposit'].forEach(k=>$(k).value=s[k]??'');['requireUtr','requireScreenshot','autoCreditOnApprove','duplicateUtrGuard'].forEach(k=>$(k).checked=!!s[k])}async function loadSettings(){let x=await j(API+'/settings');fill(x.settings||{});setMsg('Settings loaded ✅')}async function saveSettings(){try{let p={};['paymentName','upiId','accountName','qrImageUrl','adminNote'].forEach(k=>p[k]=$(k).value.trim());['minDeposit','maxDeposit'].forEach(k=>p[k]=Number($(k).value||0));['requireUtr','requireScreenshot','autoCreditOnApprove','duplicateUtrGuard'].forEach(k=>p[k]=$(k).checked);await j(API+'/settings',{method:'POST',body:JSON.stringify(p)});setMsg('Settings saved ✅');loadList()}catch(e){setMsg('Save failed: '+e.message)}}async function createDeposit(){try{let p={userId:$('newUserId').value.trim(),profileId:$('newUserId').value.trim(),phone:$('newPhone').value.trim(),customerName:$('newName').value.trim(),amount:Number($('newAmount').value||0),utr:$('newUtr').value.trim(),proofUrl:$('newProof').value.trim()};let x=await j(API+'/create',{method:'POST',body:JSON.stringify(p)});setMsg('Created '+x.deposit.depositId+' ✅');loadList()}catch(e){setMsg('Create failed: '+e.message)}}function img(d){let u=d.proofUrl||d.screenshotUrl||'';return u?`<img class="proof" src="${esc(u)}" onerror="this.style.display='none'">`:''}async function act(id,action){try{let p={depositId:id,action,updatedBy:'admin_ui'};if(action==='reject'){p.rejectReason=prompt('Reject reason?','UTR/proof not matched')||''}await j(API+'/action',{method:'POST',body:JSON.stringify(p)});setMsg(id+' '+action+' ✅');loadList()}catch(e){setMsg('Action failed: '+e.message)}}function item(d){let p=d.professional||{};let st=d.status||'';return `<div class="item"><b>${esc(d.depositId||d.id)}</b><span class="pill ${esc(st)}">${esc(st)}</span><div class="muted">${esc(d.customerName||d.userId||'Guest')} · ${esc(d.phoneNumber||'')} · ₹${esc(d.amount||0)}</div><div class="copy">UTR: ${esc(d.utr||'-')}\nOld Wallet: ₹${esc(p.currentWalletBalance||0)}\nNew Preview: ₹${esc(p.newBalancePreview||0)}\nProof: ${d.proofUrl?'Yes':'No'}</div>${img(d)}<div class="btns"><button class="soft" onclick="act('${esc(d.depositId||d.id)}','verify')">Verify</button><button class="ok" onclick="act('${esc(d.depositId||d.id)}','approve')">Approve + Credit</button><button class="danger" onclick="act('${esc(d.depositId||d.id)}','reject')">Reject</button></div></div>`}async function loadList(){try{let x=await j(API+'/list?limit=80&status='+encodeURIComponent($('filter').value));let s=x.stats||{};$('stats').innerHTML=`<div><b>${s.total||0}</b><span>Total</span></div><div><b>${s.pendingCount||0}</b><span>Pending</span></div><div><b>₹${s.pendingAmount||0}</b><span>Pending ₹</span></div><div><b>₹${s.amount||0}</b><span>Total ₹</span></div>`;$('list').innerHTML=(x.deposits||[]).length?(x.deposits||[]).map(item).join(''):'<div class="muted">No deposits.</div>'}catch(e){$('list').innerHTML='<div class="muted">Load failed: '+esc(e.message)+'</div>'}}loadSettings().catch(e=>setMsg('Load failed: '+e.message));loadList();
</script></body></html>
"""


_register_deposit_professional_v2(app)


@app.after_request
def titan_deposit_professional_existing_tab_shortcut(resp):
    try:
        from flask import request
        if request.method != "GET" or resp.status_code != 200:
            return resp
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype or request.path.startswith("/api/deposit_professional"):
            return resp
        html = resp.get_data(as_text=True)
        if not html or "deposit-professional-v2-boot" in html or "</body>" not in html.lower():
            return resp
        inject = r'''
<script id="deposit-professional-v2-boot">
(function(){
  function ready(fn){document.readyState==='loading'?document.addEventListener('DOMContentLoaded',fn):fn();}
  ready(function(){
    if(document.getElementById('titanDepositProfessionalShortcut')) return;
    var card=document.createElement('div');
    card.id='titanDepositProfessionalShortcut';
    card.style.cssText='margin:12px 0;padding:14px;border-radius:16px;border:1px solid rgba(42,171,238,.35);background:#101d2f;color:#eef6ff;font-family:Inter,Arial,sans-serif;box-shadow:0 10px 28px rgba(0,0,0,.25)';
    card.innerHTML='<b>💰 Professional Deposit Desk</b><div style="font-size:12px;color:#91afd1;margin:6px 0">QR/UPI setup, UTR proof, duplicate guard, approve + wallet credit.</div><button type="button" onclick="window.open(\'/api/deposit_professional/admin_ui\',\'_blank\')" style="border:0;border-radius:12px;padding:10px 12px;background:#2aabee;color:white;font-weight:900">Open Deposit Desk</button>';
    var nodes=[].slice.call(document.querySelectorAll('[id*="pay" i],[id*="payment" i],[id*="withdraw" i],[class*="pay" i],[class*="payment" i],[class*="withdraw" i]'));
    var target=nodes.find(function(n){return n.offsetParent!==null || n.getBoundingClientRect().height>0;});
    if(target){ target.appendChild(card); }
    else { card.style.position='fixed';card.style.right='12px';card.style.bottom='12px';card.style.zIndex='9999';card.style.maxWidth='320px';document.body.appendChild(card); }
  });
})();
</script>
'''
        idx = html.lower().rfind("</body>")
        if idx >= 0:
            html = html[:idx] + inject + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
    except Exception:
        pass
    return resp


application = app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000") or "5000")
    app.run(host=host, port=port, debug=False)
