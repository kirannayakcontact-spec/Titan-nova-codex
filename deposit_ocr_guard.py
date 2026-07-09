# ==========================================================
# TITAN NOVA — UPI DEPOSIT OCR GUARD
# Safe payment-proof verification bridge for legacy runtime.
# OCR is first-level validation only; final wallet credit is idempotent
# and should normally happen after admin approval.
# ==========================================================

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests
from flask import jsonify, request

try:  # Optional runtime dependency. Route still works without OCR engine.
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:  # Optional runtime dependency. Termux also needs tesseract binary installed.
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

FEATURE_VERSION = "2026-07-09-upi-deposit-ocr-guard-v1"

SUCCESS_WORDS = ("success", "successful", "paid", "completed", "credited", "sent")
REJECT_STATUS_WORDS = ("failed", "failure", "declined", "cancelled", "canceled", "pending", "processing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _firebase_url() -> str:
    url = os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL") or ""
    if not url:
        raise RuntimeError("FIREBASE_URL/FIREBASE_DB_URL missing")
    return url.rstrip("/")


def _fb_auth_params() -> Dict[str, str]:
    token = os.environ.get("FIREBASE_AUTH") or os.environ.get("FIREBASE_TOKEN") or os.environ.get("FIREBASE_DATABASE_SECRET") or ""
    return {"auth": token} if token else {}


def _fb_root_get() -> Dict[str, Any]:
    res = requests.get(_firebase_url(), params=_fb_auth_params(), timeout=12)
    res.raise_for_status()
    data = res.json()
    return data if isinstance(data, dict) else {}


def _fb_root_put(data: Dict[str, Any]) -> None:
    res = requests.put(_firebase_url(), params=_fb_auth_params(), json=data, timeout=15)
    res.raise_for_status()


def _clean_amount(value: Any) -> float:
    s = str(value or "").replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return 0.0
    try:
        return round(float(m.group(0)), 2)
    except Exception:
        return 0.0


def _norm_upi(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _norm_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 10:
        return "91" + digits
    return digits


def _read_image_bytes() -> Tuple[bytes, str]:
    if "image" in request.files:
        f = request.files["image"]
        return f.read(), f.filename or "upload.jpg"
    if "file" in request.files:
        f = request.files["file"]
        return f.read(), f.filename or "upload.jpg"
    payload = request.get_json(silent=True) or {}
    b64 = payload.get("image_base64") or payload.get("base64") or payload.get("image") or ""
    if isinstance(b64, str) and b64.startswith("data:image/"):
        b64 = b64.split(",", 1)[1]
    if not b64:
        raise ValueError("image file or image_base64 is required")
    return base64.b64decode(b64), "base64-upload.jpg"


def _ocr_text(image_bytes: bytes) -> Tuple[str, str]:
    if Image is None or pytesseract is None:
        return "", "OCR engine not installed. Install Pillow + pytesseract and Termux package tesseract for auto OCR."
    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, config="--psm 6") or ""
        return text.strip(), ""
    except Exception as exc:
        return "", f"OCR failed: {exc}"


def _extract_amount(text: str) -> float:
    patterns = [
        r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"(?:amount|paid|sent|debited|credited)\D{0,20}([0-9][0-9,]*(?:\.\d{1,2})?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            amt = _clean_amount(m.group(1))
            if amt > 0:
                return amt
    return 0.0


def _extract_utr(text: str) -> str:
    patterns = [
        r"(?:utr|upi\s*ref(?:erence)?|reference\s*(?:no|number|id)?|transaction\s*(?:id|no|number)|txn\s*(?:id|no)?)\D{0,18}([A-Z0-9]{8,24})",
        r"\b([0-9]{10,18})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return re.sub(r"\W+", "", m.group(1)).upper()
    return ""


def _extract_upi(text: str) -> str:
    m = re.search(r"[a-zA-Z0-9._\-]{2,}@[a-zA-Z]{2,}[a-zA-Z0-9._\-]*", text or "")
    return _norm_upi(m.group(0)) if m else ""


def _extract_status(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in REJECT_STATUS_WORDS):
        return "failed_or_pending"
    if any(w in t for w in SUCCESS_WORDS):
        return "success"
    return "unknown"


def _extract_payment_text(text: str) -> Dict[str, Any]:
    return {
        "amount": _extract_amount(text),
        "utr": _extract_utr(text),
        "receiver_upi": _extract_upi(text),
        "status": _extract_status(text),
    }


def _deposit_settings_receiver(state: Dict[str, Any]) -> str:
    ds = (((state.get("depositSettings") or {}).get("v1") or {}) if isinstance(state, dict) else {})
    accounts = ds.get("allowedReceiverAccounts") if isinstance(ds, dict) else None
    if isinstance(accounts, list):
        active = ds.get("activeReceiverId")
        chosen = None
        for acc in accounts:
            if not isinstance(acc, dict) or acc.get("enabled") is False:
                continue
            if active and acc.get("id") == active:
                chosen = acc
                break
            if chosen is None:
                chosen = acc
        if chosen and chosen.get("upiId"):
            return _norm_upi(chosen.get("upiId"))
    pm = state.get("paymentMethods") if isinstance(state, dict) else {}
    if isinstance(pm, dict):
        for key in ("upi", "phonepeUpi", "gpayUpi", "paytmUpi"):
            if pm.get(key):
                return _norm_upi(pm.get(key))
    return _norm_upi(ds.get("upiId") if isinstance(ds, dict) else "")


def _all_proofs(state: Dict[str, Any]) -> Dict[str, Any]:
    proofs = state.get("deposit_proofs") or state.get("depositProofs") or {}
    return proofs if isinstance(proofs, dict) else {}


def _duplicate_reason(state: Dict[str, Any], utr: str, image_hash: str, current_id: Optional[str] = None) -> str:
    for pid, proof in _all_proofs(state).items():
        if current_id and pid == current_id:
            continue
        if not isinstance(proof, dict):
            continue
        if utr and str(proof.get("utr") or "").upper() == utr.upper():
            return "DUPLICATE_UTR"
        if image_hash and proof.get("image_hash") == image_hash:
            return "DUPLICATE_IMAGE"
    return ""


def _validate(expected_amount: float, expected_upi: str, extracted: Dict[str, Any], state: Dict[str, Any], image_hash: str) -> Tuple[str, str]:
    utr = str(extracted.get("utr") or "").upper()
    got_amount = _clean_amount(extracted.get("amount"))
    got_upi = _norm_upi(extracted.get("receiver_upi"))
    expected_upi = _norm_upi(expected_upi) or _deposit_settings_receiver(state)

    dup = _duplicate_reason(state, utr, image_hash)
    if dup:
        return dup, "Same UTR/image already submitted."
    if extracted.get("status") != "success":
        return "ADMIN_REVIEW", "Success status not confidently detected from screenshot."
    if expected_amount > 0 and abs(got_amount - expected_amount) > 0.009:
        return "AMOUNT_MISMATCH", f"Expected amount {expected_amount}, OCR amount {got_amount or 'missing'}."
    if expected_upi and got_upi and got_upi != expected_upi:
        return "RECEIVER_MISMATCH", f"Expected receiver UPI {expected_upi}, OCR receiver {got_upi}."
    if expected_upi and not got_upi:
        return "ADMIN_REVIEW", "Receiver UPI not confidently detected; admin review required."
    if not utr:
        return "ADMIN_REVIEW", "UTR/reference number not detected; admin review required."
    return "OCR_VALID", "OCR checks passed. Admin approval still recommended before wallet credit."


def _upsert_audit(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    logs = state.get("auditLogs")
    if not isinstance(logs, list):
        logs = []
    logs.append({"id": "AUD-" + uuid.uuid4().hex[:12].upper(), "time": _now_iso(), **event})
    state["auditLogs"] = logs[-1000:]


def _credit_wallet_once(state: Dict[str, Any], proof_id: str, proof: Dict[str, Any], admin: str) -> Tuple[bool, str]:
    if proof.get("wallet_credit_done") is True:
        return False, "Wallet credit already done for this proof."
    user_id = str(proof.get("user_id") or proof.get("customer_id") or proof.get("phone_number") or "").strip()
    amount = _clean_amount(proof.get("expected_amount") or proof.get("extracted_amount"))
    if not user_id or amount <= 0:
        return False, "Missing user_id or amount."

    wallets = state.get("wallets")
    if not isinstance(wallets, dict):
        wallets = {}
    wallet = wallets.get(user_id)
    if not isinstance(wallet, dict):
        wallet = {"user_id": user_id, "balance": 0}
    old_balance = _clean_amount(wallet.get("balance"))
    wallet["balance"] = round(old_balance + amount, 2)
    wallet["updated_at"] = _now_iso()
    wallet["last_deposit_proof_id"] = proof_id
    wallets[user_id] = wallet
    state["wallets"] = wallets

    txs = state.get("walletTransactions")
    if not isinstance(txs, list):
        txs = []
    txs.append({
        "id": "WAL-TX-" + uuid.uuid4().hex[:12].upper(),
        "type": "deposit",
        "source": "upi_deposit_ocr_guard",
        "user_id": user_id,
        "amount": amount,
        "old_balance": old_balance,
        "new_balance": wallet["balance"],
        "proof_id": proof_id,
        "utr": proof.get("utr"),
        "admin": admin,
        "created_at": _now_iso(),
    })
    state["walletTransactions"] = txs[-2000:]
    proof["wallet_credit_done"] = True
    proof["wallet_credit_at"] = _now_iso()
    proof["wallet_credit_amount"] = amount
    return True, f"Wallet credited ₹{amount}."


def register_deposit_ocr_guard(app):
    @app.get("/api/deposit/ocr/status")
    def deposit_ocr_status():
        return jsonify({
            "ok": True,
            "feature": "deposit_ocr_guard",
            "version": FEATURE_VERSION,
            "pillow_available": Image is not None,
            "pytesseract_available": pytesseract is not None,
        })

    @app.post("/api/deposit/ocr-verify")
    def deposit_ocr_verify():
        started = time.time()
        try:
            image_bytes, filename = _read_image_bytes()
            form = request.form.to_dict() if request.form else {}
            payload = request.get_json(silent=True) or {}
            data = {**payload, **form}
            expected_amount = _clean_amount(data.get("expected_amount") or data.get("amount"))
            expected_upi = _norm_upi(data.get("expected_receiver_upi") or data.get("receiver_upi") or data.get("upi"))
            user_id = str(data.get("user_id") or data.get("customer_id") or data.get("phone_number") or data.get("from") or "").strip()
            phone = _norm_phone(data.get("phone_number") or data.get("phone") or user_id)
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            ocr_text, ocr_error = _ocr_text(image_bytes)
            manual_text = str(data.get("ocr_text") or "").strip()
            if manual_text and not ocr_text:
                ocr_text = manual_text
            extracted = _extract_payment_text(ocr_text)
            state = _fb_root_get()
            status, reason = _validate(expected_amount, expected_upi, extracted, state, image_hash)
            if ocr_error and status == "OCR_VALID":
                status, reason = "ADMIN_REVIEW", ocr_error
            proof_id = "DP-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()
            proof = {
                "id": proof_id,
                "feature_version": FEATURE_VERSION,
                "user_id": user_id,
                "phone_number": phone,
                "filename": filename,
                "expected_amount": expected_amount,
                "extracted_amount": extracted.get("amount"),
                "expected_receiver_upi": expected_upi or _deposit_settings_receiver(state),
                "extracted_receiver_upi": extracted.get("receiver_upi"),
                "utr": extracted.get("utr"),
                "payment_status_text": extracted.get("status"),
                "status": status,
                "reason": reason,
                "ocr_text": ocr_text[-4000:],
                "ocr_error": ocr_error,
                "image_hash": image_hash,
                "created_at": _now_iso(),
                "runtime_ms": int((time.time() - started) * 1000),
                "wallet_credit_done": False,
            }
            proofs = _all_proofs(state)
            proofs[proof_id] = proof
            state["deposit_proofs"] = proofs
            _upsert_audit(state, {"type": "deposit_ocr_verify", "proof_id": proof_id, "status": status, "reason": reason, "user_id": user_id})
            _fb_root_put(state)
            return jsonify({"ok": True, "status": status, "proof_id": proof_id, "extracted": extracted, "reason": reason})
        except Exception as exc:
            return jsonify({"ok": False, "status": "ERROR", "reason": str(exc)}), 500

    @app.get("/api/deposit/proofs")
    def deposit_proofs_list():
        try:
            state = _fb_root_get()
            proofs = list(_all_proofs(state).values())
            proofs = [p for p in proofs if isinstance(p, dict)]
            proofs.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
            limit = max(1, min(int(request.args.get("limit", 100)), 500))
            return jsonify({"ok": True, "count": len(proofs[:limit]), "proofs": proofs[:limit]})
        except Exception as exc:
            return jsonify({"ok": False, "reason": str(exc)}), 500

    @app.post("/api/deposit/proof/<proof_id>/approve")
    def deposit_proof_approve(proof_id):
        try:
            body = request.get_json(silent=True) or {}
            admin = str(body.get("admin") or body.get("reviewed_by") or request.headers.get("X-Admin-User") or "admin")[:80]
            state = _fb_root_get()
            proofs = _all_proofs(state)
            proof = proofs.get(proof_id)
            if not isinstance(proof, dict):
                return jsonify({"ok": False, "reason": "Proof not found"}), 404
            if str(proof.get("status") or "").upper() == "ADMIN_APPROVED" and proof.get("wallet_credit_done") is True:
                return jsonify({"ok": True, "status": "ADMIN_APPROVED", "reason": "Already approved and credited.", "proof_id": proof_id})
            dup = _duplicate_reason(state, str(proof.get("utr") or ""), str(proof.get("image_hash") or ""), current_id=proof_id)
            if dup:
                proof["status"] = dup
                proof["reason"] = "Duplicate detected during approval; wallet not credited."
                proofs[proof_id] = proof
                state["deposit_proofs"] = proofs
                _fb_root_put(state)
                return jsonify({"ok": False, "status": dup, "reason": proof["reason"]}), 409
            credited, msg = _credit_wallet_once(state, proof_id, proof, admin)
            proof["status"] = "ADMIN_APPROVED"
            proof["reviewed_by"] = admin
            proof["reviewed_at"] = _now_iso()
            proof["reason"] = msg
            proofs[proof_id] = proof
            state["deposit_proofs"] = proofs
            _upsert_audit(state, {"type": "deposit_proof_approve", "proof_id": proof_id, "admin": admin, "credited": credited, "reason": msg})
            _fb_root_put(state)
            return jsonify({"ok": True, "status": "ADMIN_APPROVED", "proof_id": proof_id, "credited": credited, "reason": msg})
        except Exception as exc:
            return jsonify({"ok": False, "reason": str(exc)}), 500

    @app.post("/api/deposit/proof/<proof_id>/reject")
    def deposit_proof_reject(proof_id):
        try:
            body = request.get_json(silent=True) or {}
            admin = str(body.get("admin") or body.get("reviewed_by") or request.headers.get("X-Admin-User") or "admin")[:80]
            reason = str(body.get("reason") or "Rejected by admin")[:500]
            state = _fb_root_get()
            proofs = _all_proofs(state)
            proof = proofs.get(proof_id)
            if not isinstance(proof, dict):
                return jsonify({"ok": False, "reason": "Proof not found"}), 404
            if proof.get("wallet_credit_done") is True:
                return jsonify({"ok": False, "reason": "Already credited; cannot reject credited proof."}), 409
            proof["status"] = "ADMIN_REJECTED"
            proof["reason"] = reason
            proof["reviewed_by"] = admin
            proof["reviewed_at"] = _now_iso()
            proofs[proof_id] = proof
            state["deposit_proofs"] = proofs
            _upsert_audit(state, {"type": "deposit_proof_reject", "proof_id": proof_id, "admin": admin, "reason": reason})
            _fb_root_put(state)
            return jsonify({"ok": True, "status": "ADMIN_REJECTED", "proof_id": proof_id, "reason": reason})
        except Exception as exc:
            return jsonify({"ok": False, "reason": str(exc)}), 500

    print(f"✅ Deposit OCR guard loaded: {FEATURE_VERSION}")
    return app
