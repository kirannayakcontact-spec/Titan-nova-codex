"""Titan profile delete guard.

Single owner for VIP/profile delete fixes.

v7-runtime fixes:
- Delete confirmation appears only on the actual trash/delete button.
- Normal VIP tab touches, expiry dropdown, link button, app access switch, and empty card area do not trigger delete.
- Legacy delete fetches are still mirrored to the persistent tombstone API silently.
- Tombstone keys remain Firebase-safe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import argparse
import hashlib
import json
import re
import time

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "flask_app.py"
MARKER = "TITAN_PROFILE_DELETE_GUARD_V2"

BASE_PROFILE_TOP_KEYS = (
    "profiles", "userProfiles", "vipProfiles", "users", "customers", "vipUsers",
    "clients", "vipClients", "vips", "vipList", "vipMembers", "members",
    "clientProfiles", "customerProfiles", "approvals", "pendingProfiles",
    "pendingUsers", "pendingVips", "vipAccounts", "subscriberProfiles",
    "subscriptions", "memberships", "userAccounts", "vipConnections",
    "vipConnection", "vipLinks", "vip_links", "clientLinks", "client_links",
    "connections", "appUsers", "app_users", "vipAccess", "vip_access",
)

PROFILE_NAME_MARKERS = (
    "vip", "profile", "client", "customer", "member", "subscriber",
    "membership", "user", "connection", "link", "access",
)

IDENTIFIER_FIELDS = (
    "id", "key", "uid", "userId", "user_id", "profileId", "profile_id",
    "clientId", "client_id", "customerId", "customer_id", "vipId", "vip_id",
    "memberId", "member_id", "phone", "mobile", "number", "whatsapp",
    "phoneNumber", "wa", "name", "customerName", "displayName", "clientName",
    "vipName", "display_name", "client_display_name",
)


def _stable_hash(value: Any) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8", "ignore")).hexdigest()[:16]


def _firebase_key(value: Any, prefix: str = "k") -> str:
    raw = str(value or "").strip()
    safe = re.sub(r"[\.\#\$\[\]\/]+", "_", raw)
    safe = re.sub(r"\s+", "_", safe)
    safe = re.sub(r"[^A-Za-z0-9_@+\-=,:|]+", "_", safe)
    safe = safe.strip("_")
    if not safe:
        safe = _stable_hash(raw or prefix)
    if len(safe) > 110:
        safe = safe[:80] + "_" + _stable_hash(raw)
    return f"{prefix}_{safe}"


def _normalize_tombstone_keys(tomb: Any) -> Dict[str, Any]:
    if not isinstance(tomb, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in list(tomb.items()):
        if isinstance(v, dict):
            record = dict(v)
            record.setdefault("rawKey", str(k))
        else:
            record = {"deleted": bool(v), "rawKey": str(k)}
        out[_firebase_key(k, "t")] = record
    return out


def register_vip_profile_delete_guard(app):
    """Register persistent VIP profile delete endpoints and anti-restore guards."""
    if getattr(app, "_vip_profile_delete_guard_registered", False):
        return
    app._vip_profile_delete_guard_registered = True

    from flask import jsonify, request

    def G():
        view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(view, "__globals__", {}) or {}

    def fn(name, default=None):
        return G().get(name, default)

    def raw_state_now():
        f = fn("migrate_and_get_state")
        return f() if callable(f) else {}

    def state_now():
        state = raw_state_now()
        if isinstance(state, dict):
            state["deletedProfiles"] = _normalize_tombstone_keys(state.get("deletedProfiles"))
            prune_state_with_tombstones(state)
        return state

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

    def now_iso():
        f = fn("now_iso")
        if callable(f):
            try:
                return f()
            except Exception:
                pass
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def digits(value: Any) -> str:
        d = re.sub(r"\D+", "", str(value or ""))
        if len(d) == 10:
            return "91" + d
        return d

    def clean(value: Any) -> str:
        return str(value or "").strip()

    def normalize_name(value: Any) -> str:
        return re.sub(r"\s+", " ", clean(value)).lower()

    def add_identifier(out: set, value: Any):
        v = clean(value)
        if not v:
            return
        out.add(v)
        out.add(v.lower())
        d = digits(v)
        if d:
            out.add(d)
            out.add("phone_" + d)
            out.add("key_" + d)

    def profile_phone(profile: Any) -> str:
        if not isinstance(profile, dict):
            return ""
        for k in ("phone", "mobile", "number", "whatsapp", "phoneNumber", "wa", "id"):
            d = digits(profile.get(k))
            if d:
                return d
        return ""

    def profile_id_values(key: Any, profile: Any) -> set:
        vals = set()
        add_identifier(vals, key)
        if isinstance(profile, dict):
            for k in IDENTIFIER_FIELDS:
                if profile.get(k) is not None:
                    add_identifier(vals, profile.get(k))
        return vals

    def record_text(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
        except Exception:
            return str(value or "").lower()

    def request_identifiers(data: Dict[str, Any]) -> Tuple[set, str, str, str]:
        ids = set()
        text_parts: List[str] = []
        for k in (
            "id", "key", "recordKey", "user_id", "userId", "profile_id", "profileId",
            "clientId", "vipId", "identifier", "href", "url", "path", "action",
            "buttonText", "requestUrl", "requestBody",
        ):
            add_identifier(ids, data.get(k))
            if data.get(k):
                text_parts.append(clean(data.get(k)))
        for item in data.get("hints") or []:
            add_identifier(ids, item)
            text_parts.append(clean(item))
        text = clean(data.get("text") or data.get("cardText") or data.get("rowText") or "")
        if text:
            text_parts.append(text)
        phone = digits(data.get("phone") or data.get("phone_number") or data.get("mobile") or "")
        name = clean(data.get("name") or "")
        joined_text = " ".join([p for p in text_parts if p])
        for pattern in (
            r"(?:USER\s*ID|PROFILE\s*ID|CLIENT\s*ID|VIP\s*ID|ID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,100})",
            r"(?:KEY|UID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,100})",
            r"(?:profile|vip|client|user)[/_-]([A-Za-z0-9_@+\-.]{3,100})",
        ):
            for m in re.finditer(pattern, joined_text, re.I):
                add_identifier(ids, m.group(1))
        if not phone and joined_text:
            m = re.search(r"(?:\+?91[\s\-]?)?[6-9][0-9\s\-]{8,14}", joined_text)
            if m:
                phone = digits(m.group(0))
        if phone:
            add_identifier(ids, phone)
        if not name and joined_text:
            m = re.search(r"(?:NAME|USER|CLIENT|VIP)\s*[:#\-]?\s*([A-Za-z][A-Za-z ._\-]{1,60})", joined_text, re.I)
            if m:
                name = clean(m.group(1))
        if name:
            add_identifier(ids, name)
        return ids, phone, name, joined_text

    def tombstone_identifiers(tomb: Dict[str, Any]) -> Tuple[set, set]:
        ids = set()
        phones = set()
        if not isinstance(tomb, dict):
            return ids, phones
        for k, v in tomb.items():
            add_identifier(ids, k)
            if isinstance(v, dict):
                for f in ("phone", "key", "path", "id", "rawKey", "rawPath"):
                    val = v.get(f)
                    if val:
                        add_identifier(ids, val)
                        d = digits(val)
                        if d:
                            phones.add(d)
                for val in v.get("match") or []:
                    add_identifier(ids, val)
                    d = digits(val)
                    if d:
                        phones.add(d)
        return {str(x).lower() for x in ids if x}, {p for p in phones if p}

    def record_matches(key: Any, profile: Any, identifiers: set, phone: str, name: str) -> bool:
        vals = {str(v).lower() for v in profile_id_values(key, profile) if v}
        req = {str(v).lower() for v in identifiers if v}
        if req and vals.intersection(req):
            return True
        if phone and (digits(key) == phone or profile_phone(profile) == phone or ("phone_" + phone).lower() in vals):
            return True
        if name and isinstance(profile, dict):
            target = normalize_name(name)
            for f in ("name", "customerName", "displayName", "clientName", "vipName"):
                if normalize_name(profile.get(f)) == target:
                    return True
        text = record_text(profile)
        for ident in req:
            raw = str(ident).strip().lower()
            if len(raw) >= 8 and raw in text:
                return True
        return False

    def record_is_tombstoned(key: Any, profile: Any, tomb: Dict[str, Any]) -> bool:
        ids, phones = tombstone_identifiers(tomb)
        vals = {str(v).lower() for v in profile_id_values(key, profile) if v}
        if vals.intersection(ids):
            return True
        dkey = digits(key)
        if dkey and dkey in phones:
            return True
        p = profile_phone(profile)
        if p and p in phones:
            return True
        text = record_text(profile)
        for ident in ids:
            if len(ident) >= 8 and ident in text:
                return True
        return False

    def top_keys_for_state(state: Dict[str, Any]) -> List[str]:
        keys = []
        for k in BASE_PROFILE_TOP_KEYS:
            if k in state:
                keys.append(k)
        for k, v in state.items():
            lk = str(k).lower()
            if k in keys or k == "deletedProfiles":
                continue
            if isinstance(v, (dict, list)) and any(marker in lk for marker in PROFILE_NAME_MARKERS):
                keys.append(k)
        return keys

    def tomb_put(tomb: Dict[str, Any], raw_key: Any, stamp: Dict[str, Any]):
        tomb[_firebase_key(raw_key, "t")] = dict(stamp)

    def add_tombstone(tomb: Dict[str, Any], top: str, path: List[Any], profile: Any, identifiers: set, phone: str):
        rec_phone = profile_phone(profile) or phone
        path_text = "/".join(str(p) for p in path)
        match_values = [str(top), path_text]
        if path:
            match_values.extend([str(path[-1]), "key_" + str(path[-1])])
        if rec_phone:
            match_values.extend([rec_phone, "phone_" + rec_phone])
        for ident in identifiers:
            if clean(ident):
                match_values.extend([clean(ident), "id_" + clean(ident).lower(), "key_" + clean(ident)])
        stamp = {
            "deleted": True,
            "top": str(top),
            "rawPath": path_text,
            "phone": rec_phone,
            "match": sorted({m for m in match_values if m}),
            "deletedAt": now_iso(),
        }
        tomb_put(tomb, "path_" + str(top) + "_" + path_text, stamp)
        if path:
            tomb_put(tomb, str(path[-1]), stamp)
            tomb_put(tomb, "key_" + str(path[-1]), stamp)
        if rec_phone:
            tomb_put(tomb, "phone_" + rec_phone, stamp)
        for ident in identifiers:
            s = clean(ident)
            if s and len(s) >= 3:
                tomb_put(tomb, "id_" + s.lower(), stamp)
                tomb_put(tomb, "key_" + s, stamp)

    def delete_from_container(top: str, container: Any, identifiers: set, phone: str, name: str, path: List[Any], tomb: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
        deleted: List[Dict[str, Any]] = []
        if isinstance(container, dict):
            for key, value in list(container.items()):
                child_path = path + [key]
                if record_matches(key, value, identifiers, phone, name) or record_is_tombstoned(key, value, tomb):
                    removed = container.pop(key, None)
                    add_tombstone(tomb, top, child_path, removed, identifiers, phone)
                    deleted.append({"top": top, "path": "/".join(str(p) for p in child_path), "key": str(key), "phone": profile_phone(removed) or phone})
                    continue
                if depth < 6 and isinstance(value, (dict, list)):
                    deleted.extend(delete_from_container(top, value, identifiers, phone, name, child_path, tomb, depth + 1))
        elif isinstance(container, list):
            kept = []
            for idx, value in enumerate(container):
                child_path = path + [idx]
                if record_matches(idx, value, identifiers, phone, name) or record_is_tombstoned(idx, value, tomb):
                    add_tombstone(tomb, top, child_path, value, identifiers, phone)
                    deleted.append({"top": top, "path": "/".join(str(p) for p in child_path), "index": idx, "phone": profile_phone(value) or phone})
                else:
                    if depth < 6 and isinstance(value, (dict, list)):
                        deleted.extend(delete_from_container(top, value, identifiers, phone, name, child_path, tomb, depth + 1))
                    kept.append(value)
            container[:] = kept
        return deleted

    def delete_matching_profiles(state: Dict[str, Any], identifiers: set, phone: str, name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
        deleted: List[Dict[str, Any]] = []
        touched: List[str] = []
        tomb = _normalize_tombstone_keys(state.get("deletedProfiles"))
        for top in top_keys_for_state(state):
            coll = state.get(top)
            before_count = len(deleted)
            deleted.extend(delete_from_container(top, coll, identifiers, phone, name, [], tomb, 0))
            if len(deleted) != before_count:
                state[top] = coll
                touched.append(top)
        state["deletedProfiles"] = _normalize_tombstone_keys(tomb)
        return deleted, state["deletedProfiles"], touched

    def prune_state_with_tombstones(state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        if not isinstance(state, dict):
            return False, []
        tomb = _normalize_tombstone_keys(state.get("deletedProfiles"))
        if not tomb:
            return False, []
        state["deletedProfiles"] = tomb
        touched = []
        changed = False
        for top in top_keys_for_state(state):
            coll = state.get(top)
            deleted = delete_from_container(top, coll, set(), "", "", [], tomb, 0)
            if deleted:
                state[top] = coll
                touched.append(top)
                changed = True
        state["deletedProfiles"] = _normalize_tombstone_keys(tomb)
        return changed, touched

    def request_payload():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}
        for src in (request.form, request.args):
            try:
                for k, v in src.items():
                    data.setdefault(k, v)
            except Exception:
                pass
        return data

    def persist_updates(state: Dict[str, Any], updates: Dict[str, Any]) -> bool:
        if isinstance(updates.get("deletedProfiles"), dict):
            updates["deletedProfiles"] = _normalize_tombstone_keys(updates.get("deletedProfiles"))
            state["deletedProfiles"] = updates["deletedProfiles"]
        ok = True
        for k, v in updates.items():
            if not k:
                continue
            ok = put_child([k], v) and ok
        if not ok:
            put_top(state, updates)
        return ok

    def install_state_wrapper():
        g = G()
        orig = g.get("migrate_and_get_state")
        if not callable(orig) or getattr(orig, "_vip_delete_guard_wrapped", False):
            return

        def wrapped_migrate_and_get_state(*args, **kwargs):
            state = orig(*args, **kwargs)
            try:
                if isinstance(state, dict):
                    state["deletedProfiles"] = _normalize_tombstone_keys(state.get("deletedProfiles"))
                    changed, touched = prune_state_with_tombstones(state)
                    if changed:
                        updates = {k: state.get(k) for k in touched if k in state}
                        updates["deletedProfiles"] = state.get("deletedProfiles") or {}
                        persist_updates(state, updates)
            except Exception:
                pass
            return state

        wrapped_migrate_and_get_state._vip_delete_guard_wrapped = True
        g["migrate_and_get_state"] = wrapped_migrate_and_get_state

    install_state_wrapper()

    @app.before_request
    def vip_profile_delete_scrub_legacy_saves():
        try:
            if request.method not in ("POST", "PUT", "PATCH"):
                return None
            if request.path.startswith("/api/vips/profile/delete"):
                return None
            state = raw_state_now()
            tomb = _normalize_tombstone_keys(state.get("deletedProfiles")) if isinstance(state, dict) else {}
            if not tomb:
                return None
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return None
            data["deletedProfiles"] = _normalize_tombstone_keys(data.get("deletedProfiles") or tomb)
            changed, _ = prune_state_with_tombstones(data)
            if changed:
                encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
                request._cached_data = encoded
                request._cached_json = (data, data)
        except Exception:
            pass
        return None

    @app.route("/api/vips/profile/delete", methods=["POST"])
    @app.route("/api/vip/profile/delete", methods=["POST"])
    @app.route("/api/profile/delete", methods=["POST"])
    @app.route("/api/vip_profile_delete_guard", methods=["POST"])
    @app.route("/api/vip_profile_remove", methods=["POST"])
    @app.route("/api/vip_profile_delete", methods=["POST"])
    @app.route("/api/vips/delete", methods=["POST"])
    @app.route("/api/vip/delete", methods=["POST"])
    def vip_profile_delete_api():
        try:
            data = request_payload()
            identifiers, phone, name, text = request_identifiers(data)
            if not (identifiers or phone or name or text):
                return jsonify({"status": "error", "ok": False, "reason": "Missing profile identifier/phone/name"}), 400
            state = state_now()
            tomb = _normalize_tombstone_keys(state.get("deletedProfiles"))
            request_stamp = {"deleted": True, "top": "request", "rawPath": "request", "phone": phone, "match": [], "deletedAt": now_iso()}
            match_values = []
            if phone:
                match_values.extend([phone, "phone_" + phone])
            for ident in identifiers:
                s = clean(ident)
                if s:
                    match_values.extend([s, s.lower(), "id_" + s.lower(), "key_" + s])
            request_stamp["match"] = sorted({m for m in match_values if m})
            if phone:
                tomb_put(tomb, "phone_" + phone, request_stamp)
            for ident in identifiers:
                s = clean(ident)
                if s:
                    tomb_put(tomb, "id_" + s.lower(), request_stamp)
                    tomb_put(tomb, "key_" + s, request_stamp)
            state["deletedProfiles"] = _normalize_tombstone_keys(tomb)
            deleted, tomb, touched = delete_matching_profiles(state, identifiers, phone, name)
            changed, prune_touched = prune_state_with_tombstones(state)
            for k in prune_touched:
                if k not in touched:
                    touched.append(k)
            updates = {k: state.get(k) for k in touched if k in state}
            updates["deletedProfiles"] = _normalize_tombstone_keys(tomb)
            persist_updates(state, updates)
            status = "success" if deleted or changed else "tombstoned"
            return jsonify({"status": status, "ok": True, "deleted": deleted, "phone": phone, "touched": touched, "tombstoneCount": len(updates["deletedProfiles"])})
        except Exception as exc:
            return jsonify({"status": "error", "ok": False, "reason": str(exc)}), 500

    @app.route("/api/vips/profile/delete/status", methods=["GET"])
    def vip_profile_delete_status():
        return jsonify({"status": "ok", "feature": "titan_profile_delete_guard_patch", "version": "v7-runtime", "buttonOnlyDelete": True, "firebaseSafeTombstones": True})

    @app.route("/api/vips/profile/delete/prune", methods=["POST"])
    def vip_profile_delete_prune_api():
        try:
            state = state_now()
            state["deletedProfiles"] = _normalize_tombstone_keys(state.get("deletedProfiles"))
            changed, touched = prune_state_with_tombstones(state)
            updates = {k: state.get(k) for k in touched if k in state}
            updates["deletedProfiles"] = state.get("deletedProfiles") or {}
            if updates:
                persist_updates(state, updates)
            return jsonify({"status": "ok", "changed": changed, "touched": touched, "tombstoneCount": len(updates.get("deletedProfiles") or {})})
        except Exception as exc:
            return jsonify({"status": "error", "ok": False, "reason": str(exc)}), 500

    @app.after_request
    def vip_profile_delete_inject(resp):
        try:
            from flask import request as flask_request
            if flask_request.method != "GET" or resp.status_code != 200:
                return resp
            if flask_request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "vip-profile-delete-guard-v7" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan profile delete guard loaded: v7-runtime button-only")


def apply_patch(text):
    print("Profile delete guard is runtime-registered; legacy patch CLI is kept for compatibility.")
    return text, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.parse_args()
    print("Profile delete guard runtime module present")
    return 0


SCRIPT = r'''
<script id="vip-profile-delete-guard-v7">
(function(){
  if(window.__VIP_PROFILE_DELETE_GUARD_V7__) return;
  window.__VIP_PROFILE_DELETE_GUARD_V7__ = true;
  const API='/api/vips/profile/delete';
  const PRUNE_API='/api/vips/profile/delete/prune';
  const STORE='titan.vip.deleted.v7';
  let lastVipPayload=null;
  let lastVipAt=0;
  const nativeFetch=window.fetch ? window.fetch.bind(window) : null;
  function txt(n){return String((n&&((n.innerText||n.textContent||n.value||(n.getAttribute&&n.getAttribute('aria-label'))||(n.getAttribute&&n.getAttribute('title')))))||'').replace(/\s+/g,' ').trim()}
  function attr(n,k){try{return (n&&n.getAttribute&&n.getAttribute(k))||''}catch(e){return ''}}
  function cls(n){try{return String((n&&n.className)||'')}catch(e){return ''}}
  function pageLooksVip(){return /\bVIPS\b|VIP\s+CONNECTIONS|VIP\s+PROFILE|ACTIVE\s+PROFILES|CLIENT\s+DISPLAY\s+NAME|USER\s+PROFILE|CLIENT\s+PROFILE/i.test(txt(document.body))}
  function profileContext(el){let n=el;for(let i=0;n&&i<10;i++,n=n.parentElement){const s=txt(n);if(s.length>20&&s.length<3500&&/(USER|PROFILE|PHONE|MOBILE|VIP|APPROVAL|WALLET|NAME|CLIENT|MEMBER|ACTIVE PROFILES|APP ACCESS)/i.test(s))return n}return el.closest&&el.closest('tr,li,.card,.row,.profile,.user,.vip,[class*="profile"],[class*="vip"],[class*="client"]')||el.parentElement}
  function hintsFrom(el){const out=[];let n=el;for(let i=0;n&&i<6;i++,n=n.parentElement){['data-id','data-key','data-user-id','data-userid','data-profile-id','data-client-id','data-vip-id','data-phone','id','name','value','href','action','onclick','class','aria-label','title'].forEach(k=>{const v=attr(n,k);if(v)out.push(k+':'+v)});if(n.dataset){Object.keys(n.dataset).forEach(k=>{if(n.dataset[k])out.push(k+':'+n.dataset[k])})}}return Array.from(new Set(out)).slice(0,100)}
  function extract(el){const card=profileContext(el);const s=txt(card);const hints=hintsFrom(el);let id='',phone='',name='';let m=s.match(/(?:USER\s*ID|PROFILE\s*ID|CLIENT\s*ID|VIP\s*ID|ID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,100})/i);if(m)id=m[1];m=s.match(/(?:\+?91[\s\-]?)?[6-9][0-9\s\-]{8,14}/);if(m)phone=m[0];m=s.match(/(?:NAME|USER|CLIENT|VIP)\s*[:#\-]?\s*([A-Za-z][A-Za-z ._\-]{1,60})/i);if(m)name=m[1];return{id:id,phone:phone,name:name,text:s.slice(0,3000),rowText:s.slice(0,3000),buttonText:txt(el),hints:hints,href:attr(el,'href'),action:attr(el,'action')}}
  function loadDeleted(){try{return JSON.parse(localStorage.getItem(STORE)||'[]')}catch(e){return []}}
  function saveDeleted(item){try{const a=loadDeleted();a.push(item);localStorage.setItem(STORE,JSON.stringify(a.slice(-200)))}catch(e){}}
  function compactPhone(x){return String(x||'').replace(/\D+/g,'')}
  function containsDeleted(s){s=String(s||'').replace(/\s+/g,' ');const sp=compactPhone(s);const sl=s.toLowerCase();return loadDeleted().some(x=>{return (x.phone&&sp.indexOf(compactPhone(x.phone))>=0)||(x.id&&sl.indexOf(String(x.id).toLowerCase())>=0)||(x.name&&sl.indexOf(String(x.name).toLowerCase())>=0)})}
  function hideDeletedCards(){if(!pageLooksVip())return;document.querySelectorAll('tr,li,.card,.row,.profile,.user,.vip,[class*="profile"],[class*="vip"],[class*="client"]').forEach(n=>{const s=txt(n);if(s.length>20&&s.length<3500&&/(USER|PROFILE|PHONE|MOBILE|VIP|CLIENT|MEMBER|NAME|APP ACCESS)/i.test(s)&&containsDeleted(s)){try{n.style.display='none'}catch(e){}}})}
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||localStorage.getItem('titan_admin_token')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  function stop(ev){try{ev.preventDefault()}catch(e){}try{ev.stopPropagation()}catch(e){}try{ev.stopImmediatePropagation()}catch(e){}}
  function directControl(target){return target&&target.closest?target.closest('button,a,input[type="button"],input[type="submit"],[role="button"]'):null}
  function ownDeleteSignal(control,target,ev){
    if(!control) return false;
    const direct=(txt(control)+' '+attr(control,'aria-label')+' '+attr(control,'title')+' '+attr(control,'data-action')+' '+attr(control,'id')+' '+cls(control)+' '+cls(target)+' '+String((target&&target.tagName)||'')).toUpperCase();
    if(/\b(DELETE|REMOVE|TRASH|DEL)\b|FA-TRASH|BI-TRASH|LUCIDE-TRASH|MATERIAL-ICONS[^ ]*DELETE|🗑|BTN-DELETE/.test(direct)) return true;
    try{
      const r=control.getBoundingClientRect();
      const x=(ev&&ev.clientX)||0;
      const w=window.innerWidth||document.documentElement.clientWidth||1;
      const small=r.width<=86&&r.height<=86&&r.width>=24&&r.height>=24;
      const rightMost=x>w*0.90;
      const svgLike=/^(SVG|PATH|I|SPAN)$/i.test(String((target&&target.tagName)||'')) || /icon|trash|delete/i.test(cls(target));
      const linkLike=/link|chain|copy|share/i.test(direct);
      return small && rightMost && svgLike && !linkLike;
    }catch(e){return false}
  }
  function rememberVipPayload(target){try{if(!pageLooksVip())return;const ctx=profileContext(target);if(ctx){lastVipPayload=extract(target);lastVipAt=Date.now();}}catch(e){}}
  async function guardDelete(data,quiet){try{const r=await nativeFetch(API,{method:'POST',headers:headers(),body:JSON.stringify(data),cache:'no-store'});const j=await r.json().catch(()=>({}));if(r.ok&&j&&j.ok!==false){saveDeleted({id:data.id,phone:compactPhone(data.phone),name:data.name,at:Date.now()});try{nativeFetch(PRUNE_API,{method:'POST',headers:headers(),body:'{}',cache:'no-store'})}catch(e){}hideDeletedCards();if(!quiet)alert('Profile delete saved. Refresh ke baad wapas nahi aana chahiye.');return true}if(!quiet)alert('Delete failed: '+(j.reason||j.status||r.status))}catch(e){if(!quiet)alert('Delete failed: '+e.message)}return false}
  async function deleteProfile(control,target){const data=extract(control||target);if(!confirm('VIP/user profile delete karna hai?'))return;lastVipPayload=data;lastVipAt=Date.now();const ok=await guardDelete(data,false);if(ok){const card=profileContext(control||target);try{card.style.opacity='0.25';card.style.pointerEvents='none';setTimeout(()=>{try{card.remove()}catch(e){}hideDeletedCards()},350)}catch(e){}try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}}}
  function handleClick(ev){if(!pageLooksVip())return;rememberVipPayload(ev.target);const control=directControl(ev.target);if(!control)return;const ctx=profileContext(control);if(!ctx||!/(USER|PROFILE|PHONE|MOBILE|VIP|CLIENT|MEMBER|NAME|APP ACCESS)/i.test(txt(ctx)))return;if(!ownDeleteSignal(control,ev.target,ev))return;stop(ev);deleteProfile(control,ev.target)}
  if(nativeFetch){window.fetch=async function(input,init){const url=String((input&&input.url)||input||'');const method=String((init&&init.method)||'GET').toUpperCase();const body=String((init&&init.body)||'');const resp=await nativeFetch(input,init);try{const looksVipDelete=/vip|profile|client/i.test(url+body)&&(/delete|remove|trash/i.test(url+body)||method==='DELETE');if(looksVipDelete&&lastVipPayload&&Date.now()-lastVipAt<10000){const payload=Object.assign({},lastVipPayload,{requestUrl:url,requestBody:body.slice(0,1000),hints:(lastVipPayload.hints||[]).concat(['requestUrl:'+url,'requestBody:'+body.slice(0,500)])});setTimeout(()=>guardDelete(payload,true),120)}}catch(e){}return resp}}
  document.addEventListener('pointerdown',function(ev){rememberVipPayload(ev.target)},true);
  document.addEventListener('click',handleClick,true);
  document.addEventListener('submit',handleClick,true);
  setInterval(hideDeletedCards,1200);
  setTimeout(hideDeletedCards,500);
})();
</script>
'''


if __name__ == "__main__":
    raise SystemExit(main())
