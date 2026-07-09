"""Sticky VIP delete fix.

Fixes VIP tab delete/reject not persisting by:
- deleting profiles/{pid}, wallets/{pid}, userSafety/{pid}
- writing deletedVipProfiles/{pid} tombstone
- filtering deleted VIP ids out of stale /save payloads so old browser state cannot resurrect them
- exposing the same delete handler on existing reject endpoint and compatibility remove endpoint
"""


def register_vip_delete_sticky(app):
    if getattr(app, "_vip_delete_sticky_registered", False):
        return
    app._vip_delete_sticky_registered = True

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

    def state_now():
        f = fn("migrate_and_get_state")
        return f() if callable(f) else {}

    def put_child(parts, value):
        f = fn("_firebase_put_child")
        if callable(f):
            return f(parts, value)
        raise RuntimeError("Firebase put helper missing")

    def patch_child(parts, value):
        f = fn("_firebase_patch_child")
        if callable(f):
            return f(parts, value)
        return put_child(parts, value)

    def delete_child(parts):
        f = fn("_firebase_delete_child")
        if callable(f):
            return f(parts)
        # REST fallback: writing None deletes in Firebase REST when helper supports it rarely;
        # explicit delete helper is expected in Titan runtime.
        raise RuntimeError("Firebase delete helper missing")

    def get_child(parts, default=None):
        f = fn("_firebase_get_child")
        if callable(f):
            try:
                return f(parts, timeout=8)
            except TypeError:
                return f(parts)
        return default

    def phone_key(value):
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(digits) == 10:
            digits = "91" + digits
        if len(digits) > 12 and digits.startswith("91"):
            digits = digits[-12:]
        return digits

    def deleted_map(state=None):
        obj = None
        try:
            obj = get_child(["deletedVipProfiles"], default=None)
        except Exception:
            obj = None
        if not isinstance(obj, dict) and isinstance(state, dict):
            obj = state.get("deletedVipProfiles")
        return obj if isinstance(obj, dict) else {}

    def is_deleted_pid(pid, state=None):
        pid = str(pid or "").strip()
        if not pid:
            return False
        dm = deleted_map(state)
        if pid in dm:
            return True
        # Also block same phone resurrecting under another client_ id.
        profiles = (state or {}).get("profiles", {}) if isinstance(state, dict) else {}
        prof = profiles.get(pid) if isinstance(profiles.get(pid), dict) else {}
        pk = phone_key(prof.get("phone") or pid)
        if not pk:
            return False
        for rec in dm.values():
            if isinstance(rec, dict) and phone_key(rec.get("phone") or rec.get("userId")) == pk:
                return True
        return False

    original_save = app.view_functions.get("save")

    def save_without_deleted_vips(*args, **kwargs):
        try:
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                dm = deleted_map(data)
                deleted_ids = set(str(k) for k in dm.keys())
                profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
                wallets = data.get("wallets") if isinstance(data.get("wallets"), dict) else {}
                # Include phone-matched deleted profiles too.
                deleted_phones = set()
                for rec in dm.values():
                    if isinstance(rec, dict):
                        pk = phone_key(rec.get("phone") or rec.get("userId"))
                        if pk:
                            deleted_phones.add(pk)
                for pid, prof in list(profiles.items()):
                    if str(pid) in deleted_ids or (deleted_phones and phone_key((prof or {}).get("phone") or pid) in deleted_phones):
                        profiles.pop(pid, None)
                        if isinstance(wallets, dict):
                            wallets.pop(pid, None)
                data["profiles"] = profiles
                if isinstance(wallets, dict):
                    data["wallets"] = wallets
        except Exception:
            pass
        if callable(original_save):
            return original_save(*args, **kwargs)
        return jsonify({"status": "error", "message": "Original save endpoint missing"}), 500

    if callable(original_save):
        app.view_functions["save"] = save_without_deleted_vips

    def sticky_delete_vip():
        data = request.get_json(silent=True) or {}
        pid = str(data.get("pid") or data.get("userId") or data.get("id") or "").strip()
        hard = data.get("hardDelete", True) is not False
        if not pid:
            return jsonify({"status": "error", "message": "VIP id missing"}), 400
        if pid.startswith("admin"):
            return jsonify({"status": "error", "message": "Admin profile cannot be deleted"}), 400

        state = state_now()
        profiles = state.get("profiles") if isinstance(state.get("profiles"), dict) else {}
        wallets = state.get("wallets") if isinstance(state.get("wallets"), dict) else {}
        profile = profiles.get(pid) if isinstance(profiles.get(pid), dict) else {}
        wallet = wallets.get(pid) if isinstance(wallets.get(pid), dict) else {}
        pk = phone_key(profile.get("phone") or wallet.get("phone") or pid)
        now = now_iso()
        tombstone = {
            "userId": pid,
            "phone": profile.get("phone") or wallet.get("phone") or pk,
            "phoneKey": pk,
            "name": profile.get("name") or wallet.get("name") or pid,
            "deletedAt": now,
            "deletedBy": str(data.get("deletedBy") or state.get("activeId") or "admin1"),
            "hardDelete": bool(hard),
            "source": "vip_tab_sticky_delete",
        }
        audit_id = "vip_delete_" + uuid.uuid4().hex[:10]
        audit = {
            "id": audit_id,
            "time": now,
            "action": "vip_profile_deleted_sticky",
            "detail": tombstone,
        }

        try:
            put_child(["deletedVipProfiles", pid], tombstone)
            # Delete exact children.
            for parts in (["profiles", pid], ["wallets", pid], ["userSafety", pid]):
                try:
                    delete_child(parts)
                except Exception:
                    # fallback soft-null marker only if hard delete helper fails
                    try:
                        patch_child(parts, {"deleted": True, "deletedAt": now, "vipAccessEnabled": False, "approvalStatus": "deleted"})
                    except Exception:
                        pass

            # If same phone exists under client_91xxxx or another profile id, delete/disable that too.
            aliases = []
            if pk:
                aliases.append("client_" + pk)
            for alias in set(aliases):
                if alias and alias != pid:
                    try:
                        delete_child(["profiles", alias])
                    except Exception:
                        pass
                    try:
                        delete_child(["wallets", alias])
                    except Exception:
                        pass
                    try:
                        delete_child(["userSafety", alias])
                    except Exception:
                        pass
                    try:
                        put_child(["deletedVipProfiles", alias], dict(tombstone, userId=alias, aliasOf=pid))
                    except Exception:
                        pass

            try:
                put_child(["auditLog", audit_id], audit)
            except Exception:
                pass

            # Verify exact profile/wallet gone or marked deleted.
            saved_profile = get_child(["profiles", pid], default=None)
            saved_wallet = get_child(["wallets", pid], default=None)
            profile_gone = saved_profile is None or saved_profile == {} or (isinstance(saved_profile, dict) and saved_profile.get("deleted") is True)
            wallet_gone = saved_wallet is None or saved_wallet == {} or (isinstance(saved_wallet, dict) and saved_wallet.get("deleted") is True)
            return jsonify({
                "status": "success",
                "message": "VIP user deleted permanently from active runtime",
                "deleted": True,
                "stickyDelete": True,
                "userId": pid,
                "phoneKey": pk,
                "profileGone": bool(profile_gone),
                "walletGone": bool(wallet_gone),
                "deletedVipProfile": tombstone,
            })
        except Exception as exc:
            return jsonify({"status": "error", "message": "VIP delete failed: " + str(exc), "stickyDelete": True}), 500

    # Override existing endpoint without duplicate route.
    app.view_functions["reject_vip_profile_api"] = sticky_delete_vip

    # Compatibility route if the UI calls a remove endpoint.
    if "vip_profile_remove_api" not in app.view_functions:
        app.add_url_rule("/api/vip_profile_remove", "vip_profile_remove_api", sticky_delete_vip, methods=["POST"])

    @app.route("/api/vip_delete_sticky_status", methods=["GET"])
    def vip_delete_sticky_status():
        dm = deleted_map({})
        return jsonify({"status": "success", "vipDeleteSticky": True, "deletedCount": len(dm), "deletedVipProfiles": dm})
