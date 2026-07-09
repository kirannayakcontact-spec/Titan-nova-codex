"""Titan profile delete guard.

Single owner for VIP/profile delete fixes. This module keeps the old patcher CLI
for compatibility and exposes register_vip_profile_delete_guard(app) for the
current launcher runtime. Do not create a second VIP delete guard file.

v3-runtime fixes:
- Delete button clicks are intercepted before legacy UI reload/local-save handlers.
- Old endpoint aliases such as /api/vip_profile_remove map to the same persistent delete.
- More VIP/profile/client collection paths are removed and tombstoned so refresh cannot restore them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import argparse
import json
import re
import time

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "flask_app.py"
MARKER = "TITAN_PROFILE_DELETE_GUARD_V2"

OLD = """        for k, v in live.items():
            if k not in cand:
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand"""

NEW = """        deleted_profiles = {}
        profile_delete_keys = ('profiles', 'userProfiles', 'vipProfiles', 'users', 'customers', 'vipUsers', 'clients', 'vipClients', 'vips', 'vipMembers', 'members', 'clientProfiles')
        try:
            if isinstance(candidate.get('deletedProfiles'), dict):
                deleted_profiles.update(candidate.get('deletedProfiles') or {})
            if isinstance(latest.get('deletedProfiles'), dict):
                deleted_profiles.update(latest.get('deletedProfiles') or {})
        except Exception:
            deleted_profiles = {}
        for k, v in live.items():
            if k not in cand:
                if key in profile_delete_keys:
                    phone = ''
                    try:
                        phone = re.sub(r'[^0-9]', '', str((v or {}).get('phone') or (v or {}).get('mobile') or (v or {}).get('whatsapp') or ''))
                        if len(phone) == 10:
                            phone = '91' + phone
                    except Exception:
                        phone = ''
                    if str(k) in deleted_profiles or ('key_' + str(k)) in deleted_profiles or (phone and ('phone_' + phone) in deleted_profiles):
                        continue
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand
        if key in profile_delete_keys and deleted_profiles:
            candidate['deletedProfiles'] = deleted_profiles"""

BASE_PROFILE_TOP_KEYS = (
    "profiles",
    "userProfiles",
    "vipProfiles",
    "users",
    "customers",
    "vipUsers",
    "clients",
    "vipClients",
    "vips",
    "vipList",
    "vipMembers",
    "members",
    "clientProfiles",
    "customerProfiles",
    "approvals",
    "pendingProfiles",
    "pendingUsers",
    "pendingVips",
    "vipAccounts",
    "subscriberProfiles",
    "subscriptions",
    "memberships",
    "userAccounts",
)

PROFILE_NAME_MARKERS = (
    "vip",
    "profile",
    "client",
    "customer",
    "member",
    "subscriber",
    "membership",
)

IDENTIFIER_FIELDS = (
    "id",
    "key",
    "uid",
    "userId",
    "user_id",
    "profileId",
    "profile_id",
    "clientId",
    "client_id",
    "customerId",
    "customer_id",
    "vipId",
    "vip_id",
    "memberId",
    "member_id",
    "phone",
    "mobile",
    "number",
    "whatsapp",
    "phoneNumber",
    "wa",
    "name",
    "customerName",
    "displayName",
)


def register_vip_profile_delete_guard(app):
    """Register safe VIP profile delete endpoints and a small UI bridge."""
    if getattr(app, "_vip_profile_delete_guard_registered", False):
        return
    app._vip_profile_delete_guard_registered = True

    from flask import jsonify, request

    def G():
        view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(view, "__globals__", {}) or {}

    def fn(name, default=None):
        return G().get(name, default)

    def state_now():
        f = fn("migrate_and_get_state")
        return f() if callable(f) else {}

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

    def record_text(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
        except Exception:
            return str(value or "").lower()

    def profile_phone(profile: Any) -> str:
        if not isinstance(profile, dict):
            return ""
        for k in ("phone", "mobile", "number", "whatsapp", "phoneNumber", "wa", "id"):
            d = digits(profile.get(k))
            if d:
                return d
        return ""

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

    def profile_id_values(key: Any, profile: Any) -> set:
        vals = set()
        add_identifier(vals, key)
        if isinstance(profile, dict):
            for k in IDENTIFIER_FIELDS:
                if profile.get(k) is not None:
                    add_identifier(vals, profile.get(k))
        return vals

    def request_identifiers(data: Dict[str, Any]) -> Tuple[set, str, str, str]:
        ids = set()
        text_parts = []
        for k in ("id", "key", "recordKey", "user_id", "userId", "profile_id", "profileId", "clientId", "vipId", "identifier", "href", "action", "buttonText"):
            add_identifier(ids, data.get(k))
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
        ):
            m = re.search(pattern, joined_text, re.I)
            if m:
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

    def record_matches(key: Any, profile: Any, identifiers: set, phone: str, name: str) -> bool:
        vals = {str(v).lower() for v in profile_id_values(key, profile) if v}
        req = {str(v).lower() for v in identifiers if v}
        if req and vals.intersection(req):
            return True
        if phone:
            if digits(key) == phone or profile_phone(profile) == phone:
                return True
            if ("phone_" + phone).lower() in vals:
                return True
        if name and isinstance(profile, dict):
            target = normalize_name(name)
            for f in ("name", "customerName", "displayName", "clientName", "vipName"):
                if normalize_name(profile.get(f)) == target:
                    return True
        # Last-resort exact identifier containment for real user cards. Avoid matching very short tokens.
        text = record_text(profile)
        for ident in req:
            raw = str(ident).strip().lower()
            if len(raw) >= 8 and raw in text:
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

    def add_tombstone(tomb: Dict[str, Any], top: str, path: List[Any], profile: Any, identifiers: set, phone: str):
        rec_phone = profile_phone(profile) or phone
        path_text = "/".join(str(p) for p in path)
        stamp = {"deleted": True, "top": top, "path": path_text, "phone": rec_phone, "deletedAt": now_iso()}
        tomb["path_" + top + "/" + path_text] = stamp
        if path:
            tomb[str(path[-1])] = stamp
            tomb["key_" + str(path[-1])] = stamp
        if rec_phone:
            tomb["phone_" + rec_phone] = stamp
        for ident in identifiers:
            s = clean(ident)
            if s and len(s) >= 3:
                tomb["id_" + s.lower()] = stamp

    def delete_from_container(top: str, container: Any, identifiers: set, phone: str, name: str, path: List[Any], tomb: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
        deleted: List[Dict[str, Any]] = []
        if isinstance(container, dict):
            for key, value in list(container.items()):
                child_path = path + [key]
                if record_matches(key, value, identifiers, phone, name):
                    removed = container.pop(key, None)
                    add_tombstone(tomb, top, child_path, removed, identifiers, phone)
                    deleted.append({"top": top, "path": "/".join(str(p) for p in child_path), "key": str(key), "phone": profile_phone(removed) or phone})
                    continue
                if depth < 2 and isinstance(value, (dict, list)):
                    deleted.extend(delete_from_container(top, value, identifiers, phone, name, child_path, tomb, depth + 1))
        elif isinstance(container, list):
            kept = []
            for idx, value in enumerate(container):
                child_path = path + [idx]
                if record_matches(idx, value, identifiers, phone, name):
                    add_tombstone(tomb, top, child_path, value, identifiers, phone)
                    deleted.append({"top": top, "path": "/".join(str(p) for p in child_path), "index": idx, "phone": profile_phone(value) or phone})
                else:
                    if depth < 2 and isinstance(value, (dict, list)):
                        deleted.extend(delete_from_container(top, value, identifiers, phone, name, child_path, tomb, depth + 1))
                    kept.append(value)
            container[:] = kept
        return deleted

    def delete_matching_profiles(state: Dict[str, Any], identifiers: set, phone: str, name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
        deleted: List[Dict[str, Any]] = []
        touched: List[str] = []
        tomb = state.get("deletedProfiles") if isinstance(state.get("deletedProfiles"), dict) else {}
        for top in top_keys_for_state(state):
            coll = state.get(top)
            before_count = len(deleted)
            deleted.extend(delete_from_container(top, coll, identifiers, phone, name, [], tomb, 0))
            if len(deleted) != before_count:
                state[top] = coll
                touched.append(top)
        state["deletedProfiles"] = tomb
        return deleted, tomb, touched

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

    @app.route("/api/vips/profile/delete", methods=["POST"])
    @app.route("/api/vip/profile/delete", methods=["POST"])
    @app.route("/api/profile/delete", methods=["POST"])
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
            deleted, tomb, touched = delete_matching_profiles(state, identifiers, phone, name)
            if not deleted:
                # Persist a tombstone anyway for stale UI/root-save races. This prevents a legacy merge from restoring the same key/phone later.
                for ident in identifiers:
                    s = clean(ident)
                    if s:
                        tomb["id_" + s.lower()] = {"deleted": True, "top": "unknown", "path": s, "phone": phone, "deletedAt": now_iso()}
                        tomb["key_" + s] = {"deleted": True, "top": "unknown", "path": s, "phone": phone, "deletedAt": now_iso()}
                if phone:
                    tomb["phone_" + phone] = {"deleted": True, "top": "unknown", "path": phone, "phone": phone, "deletedAt": now_iso()}
                state["deletedProfiles"] = tomb
                put_child(["deletedProfiles"], tomb) or put_top(state, {"deletedProfiles": tomb})
                return jsonify({"status": "tombstoned", "ok": True, "deleted": [], "reason": "Profile record was not found but delete tombstone was saved", "phone": phone})
            updates = {k: state.get(k) for k in touched if k in state}
            updates["deletedProfiles"] = tomb
            ok = True
            for k, v in updates.items():
                ok = put_child([k], v) and ok
            if not ok:
                put_top(state, updates)
            return jsonify({"status": "success", "ok": True, "deleted": deleted, "phone": phone, "touched": touched})
        except Exception as exc:
            return jsonify({"status": "error", "ok": False, "reason": str(exc)}), 500

    @app.route("/api/vips/profile/delete/status", methods=["GET"])
    def vip_profile_delete_status():
        return jsonify({"status": "ok", "feature": "titan_profile_delete_guard_patch", "version": "v3-runtime"})

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
            if not html or "vip-profile-delete-guard-v3" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan profile delete guard loaded: v3-runtime")


def apply_patch(text):
    """Keep old CLI patcher behavior for local legacy repair."""
    if MARKER in text:
        return text, False
    if OLD not in text:
        raise RuntimeError("merge guard anchor not found")
    text = text.replace(OLD, NEW + "\n    # " + MARKER, 1)
    return text, True


def main():
    try:
        from titan_runtime_files import ensure_runtime_file
        ensure_runtime_file("flask_app.py")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    old = TARGET.read_text(encoding="utf-8", errors="replace")
    new, changed = apply_patch(old)
    if not changed:
        print("Profile delete guard already present")
        return 0
    print("Profile delete guard can be applied")
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + ".profile-delete-guard.bak").write_text(old, encoding="utf-8")
        TARGET.write_text(new, encoding="utf-8")
        print("Applied profile delete guard")
    return 0


SCRIPT = r'''
<script id="vip-profile-delete-guard-v3">
(function(){
  if(window.__VIP_PROFILE_DELETE_GUARD_V3__) return;
  window.__VIP_PROFILE_DELETE_GUARD_V3__ = true;
  const API='/api/vips/profile/delete';
  function txt(n){return String((n&&((n.innerText||n.textContent||n.value||(n.getAttribute&&n.getAttribute('aria-label'))||(n.getAttribute&&n.getAttribute('title')))))||'').replace(/\s+/g,' ').trim()}
  function attr(n,k){try{return (n&&n.getAttribute&&n.getAttribute(k))||''}catch(e){return ''}}
  function pageLooksVip(){return /\bVIPS\b|VIP\s+PROFILE|USER\s+PROFILE|CLIENT\s+PROFILE/i.test(txt(document.body))}
  function buttonText(el){return (txt(el)+' '+attr(el,'aria-label')+' '+attr(el,'title')+' '+attr(el,'class')+' '+attr(el,'id')).toUpperCase()}
  function isDeleteControl(el){const s=buttonText(el);return /\b(DELETE|REMOVE|TRASH|DEL|PROFILE DELETE|USER DELETE)\b|🗑|REMOVE/i.test(s)}
  function profileContext(el){let n=el;for(let i=0;n&&i<8;i++,n=n.parentElement){const s=txt(n);if(s.length>20&&s.length<2500&&/(USER|PROFILE|PHONE|MOBILE|VIP|APPROVAL|WALLET|NAME|CLIENT|MEMBER)/i.test(s))return n}return el.closest&&el.closest('tr,li,.card,.row,.profile,.user,.vip')||el.parentElement}
  function hintsFrom(el){
    const out=[]; let n=el;
    for(let i=0;n&&i<6;i++,n=n.parentElement){
      ['data-id','data-key','data-user-id','data-userid','data-profile-id','data-client-id','data-vip-id','data-phone','id','name','value','href','action'].forEach(k=>{const v=attr(n,k);if(v)out.push(v)});
      if(n.dataset){Object.keys(n.dataset).forEach(k=>{if(n.dataset[k])out.push(k+':'+n.dataset[k])})}
    }
    return Array.from(new Set(out)).slice(0,80);
  }
  function extract(el){
    const card=profileContext(el); const s=txt(card); const hints=hintsFrom(el); let id='', phone='', name='';
    let m=s.match(/(?:USER\s*ID|PROFILE\s*ID|CLIENT\s*ID|VIP\s*ID|ID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,100})/i); if(m) id=m[1];
    m=s.match(/(?:\+?91[\s\-]?)?[6-9][0-9\s\-]{8,14}/); if(m) phone=m[0];
    m=s.match(/(?:NAME|USER|CLIENT|VIP)\s*[:#\-]?\s*([A-Za-z][A-Za-z ._\-]{1,60})/i); if(m) name=m[1];
    return {id:id, phone:phone, name:name, text:s.slice(0,2200), rowText:s.slice(0,2200), buttonText:txt(el), hints:hints, href:attr(el,'href'), action:attr(el,'action')};
  }
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||localStorage.getItem('titan_admin_token')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  function stop(ev){try{ev.preventDefault()}catch(e){} try{ev.stopPropagation()}catch(e){} try{ev.stopImmediatePropagation()}catch(e){}}
  async function deleteProfile(el){
    const card=profileContext(el); const data=extract(el);
    if(!confirm('VIP/user profile delete karna hai?')) return;
    try{
      const r=await fetch(API,{method:'POST',headers:headers(),body:JSON.stringify(data),cache:'no-store'});
      const j=await r.json().catch(()=>({}));
      if(r.ok&&j&&j.ok!==false){
        try{card.style.opacity='0.25'; card.style.pointerEvents='none'; setTimeout(()=>{try{card.remove()}catch(e){}},450)}catch(e){}
        alert('Profile delete saved. Refresh ke baad wapas nahi aana chahiye.');
        try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}
      }else{
        alert('Delete failed: '+(j.reason||j.status||r.status));
      }
    }catch(e){alert('Delete failed: '+e.message)}
  }
  function maybeHandle(ev){
    if(!pageLooksVip()) return;
    const el=ev.target&&ev.target.closest?ev.target.closest('button,a,input[type="button"],input[type="submit"],[role="button"],.btn,.delete,.remove,[data-action],[onclick]'):null;
    if(!el||!isDeleteControl(el)) return;
    const ctx=profileContext(el); if(!ctx||!/(USER|PROFILE|PHONE|MOBILE|VIP|CLIENT|MEMBER|NAME)/i.test(txt(ctx))) return;
    stop(ev); deleteProfile(el);
  }
  ['click','submit'].forEach(type=>document.addEventListener(type,maybeHandle,true));
})();
</script>
'''


if __name__ == "__main__":
    raise SystemExit(main())
