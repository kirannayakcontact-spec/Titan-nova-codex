"""Screenshot-only deposit support routes.

Serves WhatsApp payment screenshots saved by Gateway and adds small helper APIs for
manual review. Screenshot alone never credits wallet.
"""

from pathlib import Path
import os
import re


def register_deposit_screenshot_routes(app, ctx=None):
    if getattr(app, "_titan_deposit_screenshot_routes_registered", False):
        return
    app._titan_deposit_screenshot_routes_registered = True

    from flask import jsonify, request, send_from_directory

    ctx = ctx or {}
    base_dir = Path(os.environ.get("TITAN_STATE_DIR") or Path(__file__).resolve().parent)
    proof_dir = base_dir / "payment_uploads" / "deposit_screenshots"
    proof_dir.mkdir(parents=True, exist_ok=True)

    def now_iso():
        fn = ctx.get("_now_iso") or ctx.get("_now_iso_local")
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        import datetime
        return datetime.datetime.now().isoformat(timespec="seconds")

    def fb_get(parts, default=None):
        fn = ctx.get("_fb_get")
        if callable(fn):
            return fn(parts, default=default)
        return default

    def fb_patch(parts, value):
        fn = ctx.get("_fb_patch")
        if callable(fn):
            return fn(parts, value)
        return None

    def clean_utr(v):
        return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()[:80]

    @app.route("/api/deposit_professional/proof/<path:filename>", methods=["GET"])
    def deposit_professional_proof(filename):
        safe = os.path.basename(filename or "")
        if not safe:
            return "Missing file", 404
        return send_from_directory(str(proof_dir), safe, as_attachment=False)

    @app.route("/api/deposit_professional/screenshot_review", methods=["POST"])
    def deposit_professional_screenshot_review():
        try:
            payload = request.get_json(silent=True) or {}
            deposit_id = str(payload.get("depositId") or payload.get("id") or "").strip()
            if not deposit_id:
                return jsonify({"status": "error", "message": "depositId required"}), 400
            rec = fb_get(["depositRequests", deposit_id], default=None)
            if not isinstance(rec, dict):
                return jsonify({"status": "error", "message": "Deposit not found"}), 404
            updates = {"updatedAt": now_iso(), "lastUpdatedBy": str(payload.get("updatedBy") or "admin").strip()[:80]}
            if "amount" in payload:
                try:
                    amount = round(float(str(payload.get("amount") or "0").replace(",", "")), 2)
                except Exception:
                    amount = 0
                if amount > 0:
                    updates["amount"] = amount
                    updates["needsManualAmount"] = False
            if "utr" in payload or "utrNumber" in payload or "transactionId" in payload:
                utr = clean_utr(payload.get("utr") or payload.get("utrNumber") or payload.get("transactionId"))
                if utr:
                    updates["utr"] = utr
                    updates["needsManualUtr"] = False
            if "adminNote" in payload:
                updates["adminNote"] = str(payload.get("adminNote") or "")[:1000]
            amount_ok = float(updates.get("amount") or rec.get("amount") or 0) > 0
            utr_ok = bool(updates.get("utr") or rec.get("utr"))
            if amount_ok and utr_ok:
                updates["status"] = "payment_submitted"
                updates["stage"] = "payment_submitted"
                updates["risk"] = dict(rec.get("risk") or {}, level="medium", adminFilledDetails=True)
            else:
                updates["status"] = "needs_admin_review"
                updates["stage"] = "needs_admin_review"
            fb_patch(["depositRequests", deposit_id], updates)
            return jsonify({"status": "success", "depositId": deposit_id, "updates": updates})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500
