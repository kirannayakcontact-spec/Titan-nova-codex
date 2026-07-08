"""Screenshot-only deposit support routes.

Serves WhatsApp payment screenshots saved by Gateway and adds helper API for
manual amount/UTR review. Screenshot alone never credits wallet.
"""

from pathlib import Path
import os
import re
import datetime
import requests

DEFAULT_FIREBASE_URL = "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json"
FIREBASE_URL = (os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL") or DEFAULT_FIREBASE_URL).rstrip("/")


def _fb_url(parts):
    base = re.sub(r"\.json$", "", FIREBASE_URL, flags=re.I)
    clean = "/".join(str(p).strip("/") for p in parts if str(p).strip("/"))
    return f"{base}/{clean}.json"


def _fb_get_rest(parts, default=None):
    try:
        r = requests.get(_fb_url(parts), timeout=12)
        if r.status_code >= 400:
            return default
        data = r.json()
        return default if data is None else data
    except Exception:
        return default


def _fb_patch_rest(parts, value):
    r = requests.patch(_fb_url(parts), json=value, timeout=15)
    r.raise_for_status()
    return r.json() if r.content else None


def register_deposit_screenshot_routes(app, ctx=None):
    if getattr(app, "_titan_deposit_screenshot_routes_registered", False):
        return
    app._titan_deposit_screenshot_routes_registered = True

    from flask import jsonify, request, send_from_directory

    ctx = ctx or {}
    base_dir = Path(os.environ.get("TITAN_STATE_DIR") or Path(__file__).resolve().parent)
    proof_dir = base_dir / "payment_uploads" / "deposit_screenshots"
    proof_dir.mkdir(parents=True, exist_ok=True)

    def ds_now_iso():
        fn = ctx.get("_now_iso") or ctx.get("_now_iso_local")
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        return datetime.datetime.now().isoformat(timespec="seconds")

    def ds_fb_get(parts, default=None):
        fn = ctx.get("_fb_get")
        if callable(fn):
            try:
                return fn(parts, default=default)
            except Exception:
                pass
        return _fb_get_rest(parts, default)

    def ds_fb_patch(parts, value):
        fn = ctx.get("_fb_patch")
        if callable(fn):
            try:
                return fn(parts, value)
            except Exception:
                pass
        return _fb_patch_rest(parts, value)

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
            rec = ds_fb_get(["depositRequests", deposit_id], default=None)
            if not isinstance(rec, dict):
                return jsonify({"status": "error", "message": "Deposit not found"}), 404
            updates = {"updatedAt": ds_now_iso(), "lastUpdatedBy": str(payload.get("updatedBy") or "admin").strip()[:80]}
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
            ds_fb_patch(["depositRequests", deposit_id], updates)
            return jsonify({"status": "success", "depositId": deposit_id, "updates": updates})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500
