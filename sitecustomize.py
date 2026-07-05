"""Titan Nova Deposit Flow v1 backend extension.

This module is loaded automatically by Python when running `python flask_app.py`.
It patches Flask app creation to add deposit backend APIs without changing the
large two-file dashboard during the quick Update 1 rollout.
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import os as _os
import random as _random
import re as _re
import time as _time
import urllib.parse as _urlparse
import urllib.request as _urlrequest
import urllib.error as _urlerror
import uuid as _uuid

DEPOSIT_FLOW_V1_VERSION = "2026-07-05-deposit-flow-v1-backend-u1"
_ALLOWED_STATUS = {
    "new",
    "payment_pending",
    "payment_submitted",
    "under_verification",
    "approved",
    "rejected",
    "cancelled",
}
_DEFAULT_FIREBASE_DB_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/"


def _now_iso() -> str:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo(_os.environ.get("APP_TZ", "Asia/Kolkata"))).isoformat(timespec="seconds")
    except Exception:
        return _dt.datetime.now().isoformat(timespec="seconds")


def _business_date_compact() -> str:
    try:
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo(_os.environ.get("APP_TZ", "Asia/Kolkata")))
    except Exception:
        now = _dt.datetime.now()
    try:
        cutoff = int(str(_os.environ.get("TITAN_BUSINESS_DAY_CUTOFF_HOUR", "6")).strip() or "6")
        cutoff = min(23, max(0, cutoff))
    except Exception:
        cutoff = 6
    if now.hour < cutoff:
        now = now - _dt.timedelta(days=1)
    return now.strftime("%Y%m%d")


def _firebase_root_url() -> str:
    url = (_os.environ.get("FIREBASE_URL") or _os.environ.get("FIREBASE_DB_URL") or _DEFAULT_FIREBASE_DB_URL).strip()
    if not url:
        url = _DEFAULT_FIREBASE_DB_URL
    url = url.rstrip("/")
    if not url.endswith(".json"):
        url += "/titan_master_data.json"
    return url


def _firebase_child_url(*parts: str) -> str:
    root = _firebase_root_url()
    base = root[:-5] if root.endswith(".json") else root.rstrip("/")
    clean = [_urlparse.quote(str(p), safe="") for p in parts if str(p) != ""]
    if not clean:
        return root
    return base + "/" + "/".join(clean) + ".json"


def _json_request(method: str, url: str, payload=None, timeout: int = 10):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = _urlrequest.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with _urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            if not raw:
                return None
            try:
                return _json.loads(raw)
            except Exception:
                return raw
    except _urlerror.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Firebase HTTP {e.code}: {body}")


def _fb_get(parts, default=None):
    try:
        val = _json_request("GET", _firebase_child_url(*parts), timeout=10)
        return default if val is None else val
    except Exception:
        raise


def _fb_put(parts, value):
    return _json_request("PUT", _firebase_child_url(*parts), value, timeout=12)


def _fb_patch(parts, value):
    return _json_request("PATCH", _firebase_child_url(*parts), value, timeout=12)


def _normalize_phone(phone: str) -> str:
    digits = _re.sub(r"\D+", "", str(phone or ""))
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _normalize_utr(utr: str) -> str:
    return _re.sub(r"[^A-Za-z0-9]", "", str(utr or "")).upper()[:80]


def _utr_hash(utr: str) -> str:
    return _hashlib.sha256(_normalize_utr(utr).encode("utf-8")).hexdigest()


def _money_amount(value):
    try:
        amt = float(str(value or "0").replace(",", "").strip())
    except Exception:
        amt = 0.0
    if amt <= 0:
        return None
    return round(amt, 2)


def _deposit_settings_default() -> dict:
    return {
        "version": DEPOSIT_FLOW_V1_VERSION,
        "enabled": True,
        "paymentName": _os.environ.get("TITAN_PAYMENT_NAME", "TITAN NOVA").strip() or "TITAN NOVA",
        "upiId": _os.environ.get("TITAN_UPI_ID", "").strip(),
        "accountName": _os.environ.get("TITAN_PAYMENT_ACCOUNT_NAME", _os.environ.get("TITAN_PAYMENT_NAME", "TITAN NOVA")).strip() or "TITAN NOVA",
        "bankName": _os.environ.get("TITAN_PAYMENT_BANK", "").strip(),
        "qrImageUrl": _os.environ.get("TITAN_PAYMENT_QR_URL", "").strip(),
        "minDeposit": float(_os.environ.get("TITAN_MIN_DEPOSIT", "1") or "1"),
        "maxDeposit": float(_os.environ.get("TITAN_MAX_DEPOSIT", "100000") or "100000"),
        "manualApproval": True,
        "autoWhatsapp": False,
        "createdBy": "deposit_flow_v1_default",
        "updatedAt": _now_iso(),
    }


def _get_deposit_settings() -> dict:
    saved = _fb_get(["depositSettings", "v1"], default={})
    base = _deposit_settings_default()
    if isinstance(saved, dict):
        base.update(saved)
    base["version"] = DEPOSIT_FLOW_V1_VERSION
    return base


def _save_deposit_settings(data: dict) -> dict:
    cur = _get_deposit_settings()
    allowed = {
        "enabled", "paymentName", "upiId", "accountName", "bankName", "qrImageUrl",
        "minDeposit", "maxDeposit", "manualApproval", "autoWhatsapp", "adminNote"
    }
    for key in allowed:
        if key in data:
            cur[key] = data.get(key)
    for k in ("enabled", "manualApproval", "autoWhatsapp"):
        cur[k] = bool(cur.get(k))
    for k in ("minDeposit", "maxDeposit"):
        try:
            cur[k] = float(cur.get(k) or 0)
        except Exception:
            cur[k] = 0.0
    cur["version"] = DEPOSIT_FLOW_V1_VERSION
    cur["updatedAt"] = _now_iso()
    _fb_put(["depositSettings", "v1"], cur)
    return cur


def _new_deposit_id() -> str:
    stamp = _dt.datetime.now().strftime("%H%M%S")
    return f"DEP-{_business_date_compact()}-{stamp}-{_random.randint(1000, 9999)}"


def _audit(deposit_id: str, event: str, detail=None):
    rec = {
        "id": _uuid.uuid4().hex[:12],
        "depositId": deposit_id,
        "event": str(event or "event")[:80],
        "time": _now_iso(),
        "version": DEPOSIT_FLOW_V1_VERSION,
        "detail": detail or {},
    }
    _fb_put(["depositAuditLog", deposit_id, rec["id"]], rec)
    return rec


def _register_deposit_routes(app):
    if getattr(app, "_titan_deposit_flow_v1_registered", False):
        return
    app._titan_deposit_flow_v1_registered = True

    from flask import jsonify, request

    @app.route("/api/deposit_flow_v1/status", methods=["GET"])
    def titan_deposit_flow_v1_status():
        return jsonify({
            "status": "success",
            "feature": "deposit_flow_v1",
            "version": DEPOSIT_FLOW_V1_VERSION,
            "endpoints": [
                "/api/deposit_flow_v1/settings",
                "/api/deposit_flow_v1/request",
                "/api/deposit_flow_v1/list",
                "/api/deposit_flow_v1/detail/<depositId>",
                "/api/deposit_flow_v1/update",
            ],
            "note": "Update 1 backend APIs only. Wallet credit and WhatsApp automation come in later updates.",
        })

    @app.route("/api/deposit_flow_v1/settings", methods=["GET", "POST"])
    def titan_deposit_flow_v1_settings():
        try:
            if request.method == "GET":
                return jsonify({"status": "success", "settings": _get_deposit_settings(), "version": DEPOSIT_FLOW_V1_VERSION})
            data = request.get_json(silent=True) or {}
            settings = _save_deposit_settings(data)
            _audit("SETTINGS", "deposit_settings_saved", {"keys": sorted(list(data.keys()))})
            return jsonify({"status": "success", "settings": settings, "version": DEPOSIT_FLOW_V1_VERSION})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "version": DEPOSIT_FLOW_V1_VERSION}), 500

    @app.route("/api/deposit_flow_v1/request", methods=["POST"])
    def titan_deposit_flow_v1_request():
        try:
            data = request.get_json(silent=True) or {}
            settings = _get_deposit_settings()
            if not settings.get("enabled", True):
                return jsonify({"status": "error", "message": "Deposit flow disabled", "version": DEPOSIT_FLOW_V1_VERSION}), 403
            amount = _money_amount(data.get("amount"))
            if amount is None:
                return jsonify({"status": "error", "message": "Valid deposit amount required", "version": DEPOSIT_FLOW_V1_VERSION}), 400
            min_dep = float(settings.get("minDeposit") or 0)
            max_dep = float(settings.get("maxDeposit") or 0)
            if min_dep and amount < min_dep:
                return jsonify({"status": "error", "message": f"Minimum deposit is ₹{min_dep:g}", "version": DEPOSIT_FLOW_V1_VERSION}), 400
            if max_dep and amount > max_dep:
                return jsonify({"status": "error", "message": f"Maximum deposit is ₹{max_dep:g}", "version": DEPOSIT_FLOW_V1_VERSION}), 400

            utr = _normalize_utr(data.get("utr") or data.get("utrNumber") or data.get("transactionId"))
            if utr:
                existing = _fb_get(["depositUtrIndex", _utr_hash(utr)], default=None)
                if existing:
                    return jsonify({"status": "error", "message": "Duplicate UTR blocked", "existing": existing, "version": DEPOSIT_FLOW_V1_VERSION}), 409

            deposit_id = str(data.get("depositId") or "").strip() or _new_deposit_id()
            proof_url = str(data.get("proofUrl") or data.get("screenshotUrl") or data.get("imageUrl") or "").strip()
            current_status = "payment_submitted" if (utr or proof_url) else "payment_pending"
            user_id = str(data.get("userId") or data.get("profileId") or data.get("customerId") or "guest").strip() or "guest"
            rec = {
                "id": deposit_id,
                "depositId": deposit_id,
                "version": DEPOSIT_FLOW_V1_VERSION,
                "status": current_status,
                "stage": current_status,
                "userId": user_id,
                "profileId": str(data.get("profileId") or user_id),
                "customerName": str(data.get("customerName") or data.get("name") or "").strip(),
                "phoneNumber": _normalize_phone(data.get("phoneNumber") or data.get("phone") or ""),
                "amount": amount,
                "utr": utr,
                "proofUrl": proof_url,
                "note": str(data.get("note") or "").strip()[:500],
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
                "createdBusinessDate": _business_date_compact(),
                "payment": {
                    "upiId": settings.get("upiId", ""),
                    "accountName": settings.get("accountName", ""),
                    "paymentName": settings.get("paymentName", ""),
                    "qrImageUrl": settings.get("qrImageUrl", ""),
                },
                "walletCredit": {"applied": False, "readyForUpdate4": False},
                "whatsapp": {"queued": False, "sent": False, "readyForUpdate3": False},
            }
            _fb_put(["depositRequests", deposit_id], rec)
            if utr:
                _fb_put(["depositUtrIndex", _utr_hash(utr)], {"depositId": deposit_id, "utr": utr, "amount": amount, "createdAt": rec["createdAt"]})
            _audit(deposit_id, "deposit_request_created", {"status": current_status, "amount": amount, "userId": user_id})
            return jsonify({"status": "success", "deposit": rec, "settings": settings, "version": DEPOSIT_FLOW_V1_VERSION})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "version": DEPOSIT_FLOW_V1_VERSION}), 500

    @app.route("/api/deposit_flow_v1/list", methods=["GET"])
    def titan_deposit_flow_v1_list():
        try:
            status_filter = str(request.args.get("status") or "").strip().lower()
            limit = int(str(request.args.get("limit") or "50").strip() or "50")
            limit = max(1, min(limit, 300))
            records = _fb_get(["depositRequests"], default={})
            items = list(records.values()) if isinstance(records, dict) else []
            if status_filter:
                items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").lower() == status_filter]
            items.sort(key=lambda x: str((x or {}).get("updatedAt") or (x or {}).get("createdAt") or ""), reverse=True)
            return jsonify({"status": "success", "deposits": items[:limit], "count": len(items), "version": DEPOSIT_FLOW_V1_VERSION})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "version": DEPOSIT_FLOW_V1_VERSION}), 500

    @app.route("/api/deposit_flow_v1/detail/<deposit_id>", methods=["GET"])
    def titan_deposit_flow_v1_detail(deposit_id):
        try:
            rec = _fb_get(["depositRequests", deposit_id], default=None)
            if not rec:
                return jsonify({"status": "error", "message": "Deposit not found", "version": DEPOSIT_FLOW_V1_VERSION}), 404
            audit = _fb_get(["depositAuditLog", deposit_id], default={})
            return jsonify({"status": "success", "deposit": rec, "audit": audit or {}, "version": DEPOSIT_FLOW_V1_VERSION})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "version": DEPOSIT_FLOW_V1_VERSION}), 500

    @app.route("/api/deposit_flow_v1/update", methods=["POST"])
    def titan_deposit_flow_v1_update():
        try:
            data = request.get_json(silent=True) or {}
            deposit_id = str(data.get("depositId") or data.get("id") or "").strip()
            if not deposit_id:
                return jsonify({"status": "error", "message": "depositId required", "version": DEPOSIT_FLOW_V1_VERSION}), 400
            rec = _fb_get(["depositRequests", deposit_id], default=None)
            if not isinstance(rec, dict):
                return jsonify({"status": "error", "message": "Deposit not found", "version": DEPOSIT_FLOW_V1_VERSION}), 404
            updates = {}
            new_status = str(data.get("status") or "").strip().lower()
            if new_status:
                if new_status not in _ALLOWED_STATUS:
                    return jsonify({"status": "error", "message": "Invalid deposit status", "allowed": sorted(_ALLOWED_STATUS), "version": DEPOSIT_FLOW_V1_VERSION}), 400
                updates["status"] = new_status
                updates["stage"] = new_status
            for key in ("adminNote", "rejectReason", "verificationNote", "proofUrl", "utr"):
                if key in data:
                    updates[key] = str(data.get(key) or "").strip()[:1000]
            if "utr" in updates:
                updates["utr"] = _normalize_utr(updates.get("utr"))
            updates["updatedAt"] = _now_iso()
            updates["lastUpdatedBy"] = str(data.get("updatedBy") or "admin").strip()[:80]
            _fb_patch(["depositRequests", deposit_id], updates)
            if updates.get("utr"):
                _fb_put(["depositUtrIndex", _utr_hash(updates["utr"])], {"depositId": deposit_id, "utr": updates["utr"], "updatedAt": updates["updatedAt"]})
            fresh = dict(rec)
            fresh.update(updates)
            _audit(deposit_id, "deposit_request_updated", {"updates": updates})
            return jsonify({"status": "success", "deposit": fresh, "updates": updates, "version": DEPOSIT_FLOW_V1_VERSION})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "version": DEPOSIT_FLOW_V1_VERSION}), 500


try:
    import flask as _flask
    _orig_flask_init = _flask.Flask.__init__

    def _titan_patched_flask_init(self, *args, **kwargs):
        _orig_flask_init(self, *args, **kwargs)
        try:
            _register_deposit_routes(self)
        except Exception as exc:
            print("⚠️ TITAN DEPOSIT FLOW V1 route registration failed:", exc)

    if not getattr(_flask.Flask, "_titan_deposit_flow_v1_init_patch", False):
        _flask.Flask.__init__ = _titan_patched_flask_init
        _flask.Flask._titan_deposit_flow_v1_init_patch = True
except Exception:
    # Flask may not be installed during package setup commands. Runtime will work
    # after `pip install -r requirements.txt` is completed.
    pass
