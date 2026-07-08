"""Titan Nova professional deposit flow v2.

This module is loaded by flask_app.py after the legacy runtime is executed.
It upgrades the existing admin-side deposit flow without replacing old routes.
"""

import datetime
import hashlib
import random
import re
import uuid


def register_deposit_professional_v2(app, ctx):
    if getattr(app, "_titan_deposit_professional_v2_registered", False):
        return
    app._titan_deposit_professional_v2_registered = True

    from flask import Response, jsonify, request

    def now_iso():
        fn = ctx.get("_now_iso") or ctx.get("_now_iso_local")
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        return datetime.datetime.now().isoformat(timespec="seconds")

    def money(value):
        fn = ctx.get("_money_amount")
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

    def norm_phone(value):
        fn = ctx.get("_normalize_phone")
        if callable(fn):
            return fn(value)
        digits = re.sub(r"\D+", "", str(value or ""))
        return "91" + digits if len(digits) == 10 else digits

    def norm_utr(value):
        fn = ctx.get("_normalize_utr")
        if callable(fn):
            return fn(value)
        return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:80]

    def utr_hash(value):
        fn = ctx.get("_utr_hash")
        if callable(fn):
            return fn(value)
        return hashlib.sha256(norm_utr(value).encode("utf-8")).hexdigest()

    def fb_get(parts, default=None):
        return ctx["_fb_get"](parts, default=default)

    def fb_put(parts, value):
        return ctx["_fb_put"](parts, value)

    def fb_patch(parts, value):
        return ctx["_fb_patch"](parts, value)

    def new_deposit_id():
        fn = ctx.get("_new_deposit_id")
        if callable(fn):
            return fn()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"DEP-{stamp}-{random.randint(1000, 9999)}"

    def audit(deposit_id, event, detail=None):
        fn = ctx.get("_audit")
        if callable(fn):
            try:
                return fn(deposit_id, event, detail or {})
            except Exception:
                pass
        rec = {
            "id": uuid.uuid4().hex[:12],
            "depositId": deposit_id,
            "event": event,
            "time": now_iso(),
            "version": "deposit_professional_v2",
            "detail": detail or {},
        }
        fb_put(["depositAuditLog", deposit_id, rec["id"]], rec)
        return rec

    def settings():
        fn = ctx.get("_get_deposit_settings")
        data = fn() if callable(fn) else {}
        data = data if isinstance(data, dict) else {}
        data.setdefault("enabled", True)
        data.setdefault("paymentName", "TITAN NOVA")
        data.setdefault("upiId", "")
        data.setdefault("accountName", data.get("paymentName") or "TITAN NOVA")
        data.setdefault("qrImageUrl", "")
        data.setdefault("minDeposit", 1)
        data.setdefault("maxDeposit", 100000)
        data.setdefault("manualApproval", True)
        data.setdefault("requireUtr", True)
        data.setdefault("requireScreenshot", False)
        data.setdefault("autoCreditOnApprove", True)
        data.setdefault("duplicateUtrGuard", True)
        data.setdefault("rejectReasonRequired", True)
        data.setdefault("version", "deposit_professional_v2")
        return data

    def save_settings(payload):
        payload = payload or {}
        save_fn = ctx.get("_save_deposit_settings")
        base_keys = {
            "enabled", "paymentName", "upiId", "accountName", "bankName", "qrImageUrl",
            "minDeposit", "maxDeposit", "manualApproval", "autoWhatsapp", "adminNote",
            "allowedReceiverAccounts", "activeReceiverId", "receiverMatchRequired", "allowWeakNameMatch",
        }
        if callable(save_fn):
            save_fn({k: v for k, v in payload.items() if k in base_keys})
        extra = {}
        for key in ("requireUtr", "requireScreenshot", "autoCreditOnApprove", "duplicateUtrGuard", "rejectReasonRequired"):
            if key in payload:
                extra[key] = bool(payload.get(key))
        for key in ("receiptTemplate", "qrMessageTemplate", "approvalMessageTemplate", "rejectionMessageTemplate"):
            if key in payload:
                extra[key] = str(payload.get(key) or "")[:2000]
        if extra:
            extra["version"] = "deposit_professional_v2"
            extra["updatedAt"] = now_iso()
            fb_patch(["depositSettings", "v1"], extra)
        return settings()

    def enrich(rec, cfg=None):
        cfg = cfg or settings()
        fn = ctx.get("_enrich_deposit_record")
        out = fn(rec, cfg) if callable(fn) else dict(rec or {})
        out = out if isinstance(out, dict) else dict(rec or {})
        user_id = str(out.get("userId") or out.get("profileId") or "").strip()
        wallet = fb_get(["wallets", user_id], default={}) if user_id and user_id != "guest" else {}
        try:
            balance = round(float((wallet or {}).get("balance") or 0), 2) if isinstance(wallet, dict) else 0
        except Exception:
            balance = 0
        amount = money(out.get("amount")) or 0
        out["professional"] = {
            "version": "deposit_professional_v2",
            "currentWalletBalance": balance,
            "newBalancePreview": round(balance + amount, 2),
            "requiresUtr": bool(cfg.get("requireUtr", True)),
            "requiresScreenshot": bool(cfg.get("requireScreenshot", False)),
            "autoCreditOnApprove": bool(cfg.get("autoCreditOnApprove", True)),
            "hasUtr": bool(out.get("utr")),
            "hasProof": bool(out.get("proofUrl") or out.get("screenshotUrl")),
        }
        return out

    def records(status_filter="", limit=80):
        raw = fb_get(["depositRequests"], default={})
        items = list(raw.values()) if isinstance(raw, dict) else []
        if status_filter:
            sf = str(status_filter).lower().strip()
            items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").lower() == sf]
        items.sort(key=lambda x: str((x or {}).get("updatedAt") or (x or {}).get("createdAt") or ""), reverse=True)
        return items[: max(1, min(int(limit or 80), 500))], items

    def stats(items):
        fn = ctx.get("_deposit_stats")
        if callable(fn):
            try:
                return fn(items)
            except Exception:
                pass
        out = {"total": 0, "amount": 0, "pendingCount": 0, "pendingAmount": 0, "approvedAmount": 0, "rejectedAmount": 0, "byStatus": {}}
        for item in items:
            if not isinstance(item, dict):
                continue
            st = str(item.get("status") or "payment_pending").lower()
            amt = float(item.get("amount") or 0)
            out["total"] += 1
            out["amount"] = round(out["amount"] + amt, 2)
            out["byStatus"].setdefault(st, {"count": 0, "amount": 0})
            out["byStatus"][st]["count"] += 1
            out["byStatus"][st]["amount"] = round(out["byStatus"][st]["amount"] + amt, 2)
            if st in ("payment_pending", "payment_submitted", "under_verification"):
                out["pendingCount"] += 1
                out["pendingAmount"] = round(out["pendingAmount"] + amt, 2)
            elif st == "approved":
                out["approvedAmount"] = round(out["approvedAmount"] + amt, 2)
            elif st == "rejected":
                out["rejectedAmount"] = round(out["rejectedAmount"] + amt, 2)
        return out

    @app.route("/api/deposit_professional/status", methods=["GET"])
    def deposit_professional_status():
        shown, all_items = records(limit=500)
        return jsonify({
            "status": "success",
            "feature": "deposit_professional_v2",
            "version": "2026-07-08-deposit-professional-v2",
            "open": "/api/deposit_professional/admin_ui",
            "settings": settings(),
            "stats": stats(all_items),
        })

    @app.route("/api/deposit_professional/settings", methods=["GET", "POST"])
    def deposit_professional_settings():
        try:
            if request.method == "GET":
                return jsonify({"status": "success", "settings": settings()})
            cfg = save_settings(request.get_json(silent=True) or {})
            audit("SETTINGS", "deposit_professional_settings_saved", {})
            return jsonify({"status": "success", "settings": cfg})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/deposit_professional/list", methods=["GET"])
    def deposit_professional_list():
        try:
            cfg = settings()
            shown, all_items = records(request.args.get("status") or "", request.args.get("limit") or 80)
            return jsonify({
                "status": "success",
                "deposits": [enrich(x, cfg) for x in shown],
                "count": len(shown),
                "stats": stats(all_items),
                "settings": cfg,
            })
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/deposit_professional/create", methods=["POST"])
    def deposit_professional_create():
        try:
            payload = request.get_json(silent=True) or {}
            cfg = settings()
            if not cfg.get("enabled", True):
                return jsonify({"status": "error", "message": "Deposit disabled"}), 403
            amount = money(payload.get("amount"))
            if amount is None:
                return jsonify({"status": "error", "message": "Valid amount required"}), 400
            min_dep = float(cfg.get("minDeposit") or 0)
            max_dep = float(cfg.get("maxDeposit") or 0)
            if min_dep and amount < min_dep:
                return jsonify({"status": "error", "message": f"Minimum deposit ₹{min_dep:g}"}), 400
            if max_dep and amount > max_dep:
                return jsonify({"status": "error", "message": f"Maximum deposit ₹{max_dep:g}"}), 400
            utr = norm_utr(payload.get("utr") or payload.get("utrNumber") or payload.get("transactionId"))
            if utr and cfg.get("duplicateUtrGuard", True):
                existing = fb_get(["depositUtrIndex", utr_hash(utr)], default=None)
                if existing:
                    return jsonify({"status": "error", "message": "Duplicate UTR blocked", "existing": existing}), 409
            proof_url = str(payload.get("proofUrl") or payload.get("screenshotUrl") or payload.get("imageUrl") or "").strip()
            deposit_id = str(payload.get("depositId") or "").strip() or new_deposit_id()
            user_id = str(payload.get("userId") or payload.get("profileId") or payload.get("customerId") or "guest").strip() or "guest"
            status = "payment_submitted" if (utr or proof_url) else "payment_pending"
            rec = {
                "id": deposit_id,
                "depositId": deposit_id,
                "version": "deposit_professional_v2",
                "status": status,
                "stage": status,
                "userId": user_id,
                "profileId": str(payload.get("profileId") or user_id),
                "customerName": str(payload.get("customerName") or payload.get("name") or "").strip(),
                "phoneNumber": norm_phone(payload.get("phoneNumber") or payload.get("phone") or ""),
                "amount": amount,
                "utr": utr,
                "proofUrl": proof_url,
                "note": str(payload.get("note") or "").strip()[:500],
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
                "payment": {
                    "upiId": cfg.get("upiId", ""),
                    "accountName": cfg.get("accountName", ""),
                    "paymentName": cfg.get("paymentName", ""),
                    "qrImageUrl": cfg.get("qrImageUrl", ""),
                },
                "walletCredit": {"applied": False, "source": "deposit_professional_v2"},
            }
            fb_put(["depositRequests", deposit_id], rec)
            if utr:
                fb_put(["depositUtrIndex", utr_hash(utr)], {"depositId": deposit_id, "utr": utr, "amount": amount, "createdAt": rec["createdAt"]})
            audit(deposit_id, "deposit_professional_created", {"amount": amount, "status": status, "userId": user_id})
            return jsonify({"status": "success", "deposit": enrich(rec, cfg)})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/deposit_professional/action", methods=["POST"])
    def deposit_professional_action():
        try:
            payload = request.get_json(silent=True) or {}
            deposit_id = str(payload.get("depositId") or payload.get("id") or "").strip()
            if not deposit_id:
                return jsonify({"status": "error", "message": "depositId required"}), 400
            rec = fb_get(["depositRequests", deposit_id], default=None)
            if not isinstance(rec, dict):
                return jsonify({"status": "error", "message": "Deposit not found"}), 404
            cfg = settings()
            action = str(payload.get("action") or payload.get("status") or "").lower().strip()
            status_map = {
                "submit": "payment_submitted", "submitted": "payment_submitted",
                "verify": "under_verification", "under_verification": "under_verification",
                "approve": "approved", "approved": "approved",
                "reject": "rejected", "rejected": "rejected",
                "cancel": "cancelled", "cancelled": "cancelled",
            }
            new_status = status_map.get(action)
            if not new_status:
                return jsonify({"status": "error", "message": "Invalid action", "allowed": sorted(status_map)}), 400
            current = str(rec.get("status") or "payment_pending").lower()
            allowed = (ctx.get("_DEPOSIT_ACTIONS") or {}).get(current, [])
            if allowed and new_status not in allowed and not bool(payload.get("force")):
                return jsonify({"status": "error", "message": f"Status flow blocked: {current} -> {new_status}", "allowedNextStatuses": allowed}), 409
            updates = {"status": new_status, "stage": new_status, "updatedAt": now_iso(), "lastUpdatedBy": str(payload.get("updatedBy") or "admin").strip()[:80]}
            if "utr" in payload or "utrNumber" in payload or "transactionId" in payload:
                updates["utr"] = norm_utr(payload.get("utr") or payload.get("utrNumber") or payload.get("transactionId"))
            if "proofUrl" in payload or "screenshotUrl" in payload or "imageUrl" in payload:
                updates["proofUrl"] = str(payload.get("proofUrl") or payload.get("screenshotUrl") or payload.get("imageUrl") or "").strip()
            for key in ("adminNote", "verificationNote", "rejectReason"):
                if key in payload:
                    updates[key] = str(payload.get(key) or "").strip()[:1000]
            fresh_preview = dict(rec)
            fresh_preview.update(updates)
            utr = norm_utr(fresh_preview.get("utr"))
            proof = str(fresh_preview.get("proofUrl") or fresh_preview.get("screenshotUrl") or "").strip()
            if new_status in ("payment_submitted", "under_verification", "approved") and cfg.get("requireUtr", True) and not utr:
                return jsonify({"status": "error", "message": "UTR required before verification/approval"}), 400
            if new_status in ("payment_submitted", "under_verification", "approved") and cfg.get("requireScreenshot", False) and not proof:
                return jsonify({"status": "error", "message": "Screenshot/proof required before verification/approval"}), 400
            if utr and cfg.get("duplicateUtrGuard", True):
                existing = fb_get(["depositUtrIndex", utr_hash(utr)], default=None)
                if isinstance(existing, dict) and str(existing.get("depositId")) not in ("", deposit_id):
                    return jsonify({"status": "error", "message": "Duplicate UTR blocked", "existing": existing}), 409
                updates["utr"] = utr
            if new_status == "approved":
                updates["approvedAt"] = now_iso()
                updates["approvedBy"] = updates["lastUpdatedBy"]
                if cfg.get("autoCreditOnApprove", True):
                    credit_fn = ctx.get("_deposit_wallet_credit")
                    if callable(credit_fn):
                        wallet, credit = credit_fn(fresh_preview, updates["approvedBy"])
                        updates["walletCredit"] = credit
                        updates["walletCredited"] = bool(isinstance(credit, dict) and credit.get("applied"))
                        if isinstance(credit, dict) and credit.get("applied"):
                            updates["walletCreditAmount"] = credit.get("amount")
                            updates["walletBalanceAfter"] = credit.get("balanceAfter")
                        else:
                            updates["walletCreditError"] = credit.get("reason", "wallet_credit_failed") if isinstance(credit, dict) else "wallet_credit_failed"
                    else:
                        updates["walletCreditError"] = "wallet_credit_function_missing"
            if new_status == "rejected":
                reason = str(updates.get("rejectReason") or payload.get("reason") or "").strip()
                if cfg.get("rejectReasonRequired", True) and not reason:
                    return jsonify({"status": "error", "message": "Reject reason required"}), 400
                updates["rejectReason"] = reason
                updates["rejectedAt"] = now_iso()
            fb_patch(["depositRequests", deposit_id], updates)
            if updates.get("utr"):
                fb_put(["depositUtrIndex", utr_hash(updates["utr"])], {"depositId": deposit_id, "utr": updates["utr"], "amount": fresh_preview.get("amount"), "updatedAt": updates["updatedAt"]})
            fresh = dict(rec)
            fresh.update(updates)
            audit(deposit_id, "deposit_professional_action", {"action": action, "newStatus": new_status, "updates": updates})
            queue_fn = ctx.get("_queue_deposit_message")
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
            return jsonify({"status": "success", "deposit": enrich(fresh, cfg), "updates": updates})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/api/deposit_professional/admin_ui", methods=["GET"])
    def deposit_professional_admin_ui():
        return Response(DEPOSIT_DESK_HTML, mimetype="text/html")

    @app.after_request
    def deposit_professional_existing_tab_shortcut(resp):
        try:
            if request.method != "GET" or resp.status_code != 200:
                return resp
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" not in content_type or request.path.startswith("/api/deposit_professional"):
                return resp
            html = resp.get_data(as_text=True)
            if not html or "deposit-professional-v2-boot" in html or "</body>" not in html.lower():
                return resp
            inject = DEPOSIT_SHORTCUT_SCRIPT
            idx = html.lower().rfind("</body>")
            if idx >= 0:
                html = html[:idx] + inject + html[idx:]
                resp.set_data(html)
                resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


DEPOSIT_DESK_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Titan Nova Deposit Desk</title><style>:root{--bg:#07111f;--card:#101d2f;--line:#243e5f;--txt:#eef6ff;--muted:#91afd1;--brand:#2aabee;--ok:#22c55e;--danger:#ff4d6d;--warn:#fbbf24}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#07111f,#0c1728);color:var(--txt);font-family:Inter,Arial,sans-serif;padding:14px}.wrap{max-width:1040px;margin:0 auto}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px}.title{font-weight:900;font-size:22px}.badge{background:rgba(34,197,94,.18);border:1px solid rgba(34,197,94,.35);color:#a7f3d0;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:900}.grid{display:grid;grid-template-columns:1fr;gap:12px}@media(min-width:850px){.grid{grid-template-columns:.95fr 1.2fr}}.card{background:rgba(16,29,47,.95);border:1px solid rgba(42,171,238,.22);border-radius:18px;padding:14px;box-shadow:0 12px 35px rgba(0,0,0,.28)}label{font-size:11px;color:var(--muted);font-weight:900;text-transform:uppercase;display:block;margin:10px 0 6px}input,textarea,select{width:100%;background:#07111f;border:1px solid var(--line);border-radius:13px;color:var(--txt);padding:12px;font-size:14px}textarea{min-height:70px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.tog{display:flex;align-items:center;justify-content:space-between;gap:8px;background:#14243a;border:1px solid var(--line);border-radius:13px;padding:10px;margin-top:8px}.tog input{width:auto}button{border:0;border-radius:13px;padding:11px 12px;background:var(--brand);color:#fff;font-weight:900;margin-top:10px}.btns{display:flex;gap:8px;flex-wrap:wrap}.btns button{margin-top:8px}.ok{background:var(--ok);color:#062013}.danger{background:var(--danger)}.soft{background:#263b59}.stat{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:10px}@media(min-width:650px){.stat{grid-template-columns:repeat(4,1fr)}}.stat div{background:#0b1727;border:1px solid var(--line);border-radius:14px;padding:10px}.stat b{display:block;font-size:18px}.stat span{color:var(--muted);font-size:11px}.item{background:#0b1727;border:1px solid var(--line);border-radius:16px;padding:12px;margin:9px 0}.pill{display:inline-block;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900;margin-left:6px}.pill.approved{background:rgba(34,197,94,.18);color:#a7f3d0}.pill.rejected{background:rgba(255,77,109,.18);color:#ffc2cc}.pill.payment_pending,.pill.under_verification{background:rgba(251,191,36,.16);color:#fde68a}.pill.payment_submitted{background:rgba(42,171,238,.18);color:#bfdbfe}.muted{color:var(--muted);font-size:12px;line-height:1.45}.status{background:#0b1727;border:1px solid var(--line);border-radius:13px;padding:10px;margin:10px 0;color:var(--muted);white-space:pre-wrap}.copy{font-family:ui-monospace,monospace;background:#07111f;border:1px dashed var(--line);border-radius:12px;padding:8px;margin-top:8px;color:#b8d8ff;font-size:12px;overflow:auto}.proof{max-width:100%;max-height:120px;border-radius:12px;margin-top:8px;border:1px solid var(--line)}</style></head><body><div class="wrap"><div class="top"><div><div class="title">💰 Titan Nova Deposit Desk</div><div class="muted">Professional admin-side deposit verification + wallet credit</div></div><span class="badge">V2 ACTIVE</span></div><div class="stat" id="stats"><div><b>-</b><span>Total</span></div><div><b>-</b><span>Pending</span></div><div><b>-</b><span>Pending ₹</span></div><div><b>-</b><span>Total ₹</span></div></div><div class="grid"><div class="card"><h3>Payment Settings</h3><label>Payment Name</label><input id="paymentName"><label>UPI ID</label><input id="upiId"><label>Account Name</label><input id="accountName"><label>QR Image URL</label><input id="qrImageUrl"><div class="row"><div><label>Min Deposit</label><input id="minDeposit" type="number"></div><div><label>Max Deposit</label><input id="maxDeposit" type="number"></div></div><div class="tog"><span>Require UTR</span><input id="requireUtr" type="checkbox"></div><div class="tog"><span>Require Screenshot</span><input id="requireScreenshot" type="checkbox"></div><div class="tog"><span>Auto wallet credit on approve</span><input id="autoCreditOnApprove" type="checkbox"></div><div class="tog"><span>Duplicate UTR guard</span><input id="duplicateUtrGuard" type="checkbox"></div><label>Admin Note</label><textarea id="adminNote"></textarea><button onclick="saveSettings()">💾 Save Settings</button><div class="status" id="msg">Loading...</div><hr style="border-color:#243e5f;border-style:solid;border-width:1px 0 0;margin:16px 0"><h3>Create Manual Deposit</h3><div class="row"><div><label>User ID/Profile ID</label><input id="newUserId"></div><div><label>Phone</label><input id="newPhone"></div></div><label>Name</label><input id="newName"><label>Amount</label><input id="newAmount" type="number"><label>UTR</label><input id="newUtr"><label>Screenshot URL</label><input id="newProof"><button class="soft" onclick="createDeposit()">➕ Create Deposit</button></div><div class="card"><div class="btns"><select id="filter" onchange="loadList()"><option value="">All</option><option value="payment_pending">Payment Pending</option><option value="payment_submitted">Submitted</option><option value="under_verification">Verifying</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select><button class="soft" onclick="loadList()">Refresh</button></div><div id="list" style="margin-top:10px"></div></div></div></div><script>const API='/api/deposit_professional';const $=id=>document.getElementById(id);function token(){return localStorage.getItem('TITAN_ADMIN_TOKEN')||''}async function j(url,opt={}){opt.headers=Object.assign({'Content-Type':'application/json'},opt.headers||{});if(token())opt.headers['X-Titan-Admin-Token']=token();let r=await fetch(url,opt);let x=await r.json().catch(()=>({status:'error',message:'Invalid JSON'}));if(!r.ok||x.status==='error')throw new Error(x.message||('HTTP '+r.status));return x}function esc(v){return String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]||c))}function setMsg(t){$('msg').textContent=t}function fill(s){['paymentName','upiId','accountName','qrImageUrl','adminNote'].forEach(k=>$(k).value=s[k]||'');['minDeposit','maxDeposit'].forEach(k=>$(k).value=s[k]??'');['requireUtr','requireScreenshot','autoCreditOnApprove','duplicateUtrGuard'].forEach(k=>$(k).checked=!!s[k])}async function loadSettings(){let x=await j(API+'/settings');fill(x.settings||{});setMsg('Settings loaded ✅')}async function saveSettings(){try{let p={};['paymentName','upiId','accountName','qrImageUrl','adminNote'].forEach(k=>p[k]=$(k).value.trim());['minDeposit','maxDeposit'].forEach(k=>p[k]=Number($(k).value||0));['requireUtr','requireScreenshot','autoCreditOnApprove','duplicateUtrGuard'].forEach(k=>p[k]=$(k).checked);await j(API+'/settings',{method:'POST',body:JSON.stringify(p)});setMsg('Settings saved ✅');loadList()}catch(e){setMsg('Save failed: '+e.message)}}async function createDeposit(){try{let p={userId:$('newUserId').value.trim(),profileId:$('newUserId').value.trim(),phone:$('newPhone').value.trim(),customerName:$('newName').value.trim(),amount:Number($('newAmount').value||0),utr:$('newUtr').value.trim(),proofUrl:$('newProof').value.trim()};let x=await j(API+'/create',{method:'POST',body:JSON.stringify(p)});setMsg('Created '+x.deposit.depositId+' ✅');loadList()}catch(e){setMsg('Create failed: '+e.message)}}function img(d){let u=d.proofUrl||d.screenshotUrl||'';return u?`<img class="proof" src="${esc(u)}" onerror="this.style.display='none'">`:''}async function act(id,action){try{let p={depositId:id,action,updatedBy:'admin_ui'};if(action==='reject'){p.rejectReason=prompt('Reject reason?','UTR/proof not matched')||''}await j(API+'/action',{method:'POST',body:JSON.stringify(p)});setMsg(id+' '+action+' ✅');loadList()}catch(e){setMsg('Action failed: '+e.message)}}function item(d){let p=d.professional||{};let st=d.status||'';return `<div class="item"><b>${esc(d.depositId||d.id)}</b><span class="pill ${esc(st)}">${esc(st)}</span><div class="muted">${esc(d.customerName||d.userId||'Guest')} · ${esc(d.phoneNumber||'')} · ₹${esc(d.amount||0)}</div><div class="copy">UTR: ${esc(d.utr||'-')}\nOld Wallet: ₹${esc(p.currentWalletBalance||0)}\nNew Preview: ₹${esc(p.newBalancePreview||0)}\nProof: ${d.proofUrl?'Yes':'No'}</div>${img(d)}<div class="btns"><button class="soft" onclick="act('${esc(d.depositId||d.id)}','verify')">Verify</button><button class="ok" onclick="act('${esc(d.depositId||d.id)}','approve')">Approve + Credit</button><button class="danger" onclick="act('${esc(d.depositId||d.id)}','reject')">Reject</button></div></div>`}async function loadList(){try{let x=await j(API+'/list?limit=80&status='+encodeURIComponent($('filter').value));let s=x.stats||{};$('stats').innerHTML=`<div><b>${s.total||0}</b><span>Total</span></div><div><b>${s.pendingCount||0}</b><span>Pending</span></div><div><b>₹${s.pendingAmount||0}</b><span>Pending ₹</span></div><div><b>₹${s.amount||0}</b><span>Total ₹</span></div>`;$('list').innerHTML=(x.deposits||[]).length?(x.deposits||[]).map(item).join(''):'<div class="muted">No deposits.</div>'}catch(e){$('list').innerHTML='<div class="muted">Load failed: '+esc(e.message)+'</div>'}}loadSettings().catch(e=>setMsg('Load failed: '+e.message));loadList();</script></body></html>'''

DEPOSIT_SHORTCUT_SCRIPT = r'''<script id="deposit-professional-v2-boot">(function(){function ready(fn){document.readyState==='loading'?document.addEventListener('DOMContentLoaded',fn):fn();}ready(function(){if(document.getElementById('titanDepositProfessionalShortcut'))return;var card=document.createElement('div');card.id='titanDepositProfessionalShortcut';card.style.cssText='margin:12px 0;padding:14px;border-radius:16px;border:1px solid rgba(42,171,238,.35);background:#101d2f;color:#eef6ff;font-family:Inter,Arial,sans-serif;box-shadow:0 10px 28px rgba(0,0,0,.25)';card.innerHTML='<b>💰 Professional Deposit Desk</b><div style="font-size:12px;color:#91afd1;margin:6px 0">QR/UPI setup, UTR proof, duplicate guard, approve + wallet credit.</div><button type="button" onclick="window.open(\'/api/deposit_professional/admin_ui\',\'_blank\')" style="border:0;border-radius:12px;padding:10px 12px;background:#2aabee;color:white;font-weight:900">Open Deposit Desk</button>';var nodes=[].slice.call(document.querySelectorAll('[id*="pay" i],[id*="payment" i],[id*="withdraw" i],[class*="pay" i],[class*="payment" i],[class*="withdraw" i]'));var target=nodes.find(function(n){return n.offsetParent!==null||n.getBoundingClientRect().height>0;});if(target){target.appendChild(card);}else{card.style.position='fixed';card.style.right='12px';card.style.bottom='12px';card.style.zIndex='9999';card.style.maxWidth='320px';document.body.appendChild(card);}});})();</script>'''
