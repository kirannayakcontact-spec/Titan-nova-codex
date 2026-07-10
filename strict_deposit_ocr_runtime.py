"""Strict WhatsApp deposit proof validation.

Replaces the legacy OCR endpoint after deposit_ocr_guard registers it.
A proof ID is created only when OCR confirms success, amount, UTR and the
configured receiver UPI. Invalid/unclear screenshots never create records.
"""


def register_strict_deposit_ocr_runtime(app):
    if getattr(app, "_strict_deposit_ocr_runtime_registered", False):
        return
    app._strict_deposit_ocr_runtime_registered = True

    import hashlib
    import time
    import uuid
    from datetime import datetime
    from flask import jsonify, request
    import deposit_ocr_guard as base

    def strict_verify():
        started = time.time()
        try:
            image_bytes, filename = base._read_image_bytes()
            if not image_bytes:
                return jsonify({"ok": False, "status": "INVALID_IMAGE", "reason": "Payment screenshot image required. No proof ID created."}), 400

            form = request.form.to_dict() if request.form else {}
            payload = request.get_json(silent=True) or {}
            data = {**payload, **form}
            expected_amount = base._clean_amount(data.get("expected_amount") or data.get("amount"))
            expected_upi = base._norm_upi(data.get("expected_receiver_upi") or data.get("receiver_upi") or data.get("upi"))
            user_id = str(data.get("user_id") or data.get("customer_id") or data.get("phone_number") or data.get("from") or "").strip()
            phone = base._norm_phone(data.get("phone_number") or data.get("phone") or user_id)
            image_hash = hashlib.sha256(image_bytes).hexdigest()

            ocr_text, ocr_error = base._ocr_text(image_bytes)
            manual_text = str(data.get("ocr_text") or "").strip()
            if manual_text and not ocr_text:
                ocr_text = manual_text
            extracted = base._extract_payment_text(ocr_text)
            state = base._fb_root_get()
            configured_upi = expected_upi or base._deposit_settings_receiver(state)

            got_amount = base._clean_amount(extracted.get("amount"))
            got_utr = str(extracted.get("utr") or "").strip().upper()
            got_upi = base._norm_upi(extracted.get("receiver_upi"))
            payment_status = str(extracted.get("status") or "").lower()

            if ocr_error:
                return jsonify({"ok": False, "status": "OCR_FAILED", "reason": f"OCR failed: {ocr_error}. No proof ID created."}), 422
            if payment_status != "success":
                return jsonify({"ok": False, "status": "INVALID_PAYMENT_STATUS", "reason": "Successful/completed payment status not detected. No proof ID created."}), 422
            if got_amount <= 0:
                return jsonify({"ok": False, "status": "AMOUNT_MISSING", "reason": "Payment amount not detected. No proof ID created."}), 422
            if expected_amount > 0 and abs(got_amount - expected_amount) > 0.009:
                return jsonify({"ok": False, "status": "AMOUNT_MISMATCH", "reason": f"Expected amount {expected_amount}, screenshot amount {got_amount}. No proof ID created."}), 422
            if not got_utr:
                return jsonify({"ok": False, "status": "UTR_MISSING", "reason": "UTR/reference number not detected. No proof ID created."}), 422
            if not configured_upi:
                return jsonify({"ok": False, "status": "RECEIVER_NOT_CONFIGURED", "reason": "Admin receiver UPI is not configured. No proof ID created."}), 422
            if not got_upi:
                return jsonify({"ok": False, "status": "RECEIVER_MISSING", "reason": "Receiver UPI not detected in screenshot. No proof ID created."}), 422
            if got_upi != configured_upi:
                return jsonify({"ok": False, "status": "RECEIVER_MISMATCH", "reason": f"Expected receiver {configured_upi}, screenshot receiver {got_upi}. No proof ID created."}), 422

            dup = base._duplicate_reason(state, got_utr, image_hash)
            if dup:
                return jsonify({"ok": False, "status": dup, "reason": "Same UTR/image already submitted. No new proof ID created."}), 409

            proof_id = "DP-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()
            proof = {
                "id": proof_id,
                "feature_version": "2026-07-10-strict-image-only-v2",
                "user_id": user_id,
                "phone_number": phone,
                "filename": filename,
                "expected_amount": expected_amount,
                "extracted_amount": got_amount,
                "expected_receiver_upi": configured_upi,
                "extracted_receiver_upi": got_upi,
                "utr": got_utr,
                "payment_status_text": payment_status,
                "status": "OCR_VALID",
                "reason": "Amount, UTR, success status and receiver UPI verified.",
                "ocr_text": ocr_text[-4000:],
                "image_hash": image_hash,
                "created_at": base._now_iso(),
                "runtime_ms": int((time.time() - started) * 1000),
                "wallet_credit_done": False,
            }
            proofs = base._all_proofs(state)
            proofs[proof_id] = proof
            state["deposit_proofs"] = proofs
            base._upsert_audit(state, {"type": "strict_deposit_ocr_verify", "proof_id": proof_id, "status": "OCR_VALID", "user_id": user_id})
            base._fb_root_put(state)
            return jsonify({"ok": True, "status": "OCR_VALID", "proof_id": proof_id, "extracted": extracted, "reason": proof["reason"]})
        except Exception as exc:
            return jsonify({"ok": False, "status": "ERROR", "reason": f"{exc}. No proof ID created."}), 500

    # Flask endpoint name created by deposit_ocr_guard.py
    if "deposit_ocr_verify" not in app.view_functions:
        raise RuntimeError("deposit_ocr_guard must load before strict runtime")
    app.view_functions["deposit_ocr_verify"] = strict_verify
    print("✅ Strict image-only deposit OCR runtime active")
