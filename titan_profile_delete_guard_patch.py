"""Titan profile delete guard.

This is the single owner for VIP/profile delete fixes. It keeps the old patcher
CLI for compatibility and also exposes register_vip_profile_delete_guard(app)
for the current launcher runtime. Do not create a second VIP delete guard file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import argparse
import re
import time

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "flask_app.py"
MARKER = "TITAN_PROFILE_DELETE_GUARD_V1"

OLD = """        for k, v in live.items():
            if k not in cand:
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand"""

NEW = """        deleted_profiles = {}
        try:
            if key == 'profiles':
                if isinstance(candidate.get('deletedProfiles'), dict):
                    deleted_profiles.update(candidate.get('deletedProfiles') or {})
                if isinstance(latest.get('deletedProfiles'), dict):
                    deleted_profiles.update(latest.get('deletedProfiles') or {})
        except Exception:
            deleted_profiles = {}
        for k, v in live.items():
            if k not in cand:
                if key == 'profiles':
                    phone = ''
                    try:
                        phone = re.sub(r'[^0-9]', '', str((v or {}).get('phone') or (v or {}).get('mobile') or ''))
                        if len(phone) == 10:
                            phone = '91' + phone
                    except Exception:
                        phone = ''
                    if str(k) in deleted_profiles or (phone and ('phone_' + phone) in deleted_profiles):
                        continue
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand
        if key == 'profiles' and deleted_profiles:
            candidate['deletedProfiles'] = deleted_profiles"""


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

    def profile_phone(profile: Any) -> str:
        if not isinstance(profile, dict):
            return ""
        for k in ("phone", "mobile", "number", "whatsapp", "phoneNumber", "wa", "id"):
            d = digits(profile.get(k))
            if d:
                return d
        return ""

    def profile_id_values(key: Any, profile: Any) -> List[str]:
        vals = [clean(key)]
        if isinstance(profile, dict):
            for k in ("id", "userId", "user_id", "uid", "profileId", "profile_id", "phone", "mobile", "whatsapp", "name"):
                if profile.get(k) is not None:
                    vals.append(clean(profile.get(k)))
                    d = digits(profile.get(k))
                    if d:
                        vals.append(d)
                        vals.append("phone_" + d)
        dkey = digits(key)
        if dkey:
            vals.append(dkey)
            vals.append("phone_" + dkey)
        return [v for v in vals if v]

    def parse_identifiers(data: Dict[str, Any]) -> Tuple[str, str, str, str]:
        text = clean(data.get("text") or data.get("cardText") or "")
        ident = clean(data.get("id") or data.get("user_id") or data.get("userId") or data.get("profile_id") or data.get("profileId") or data.get("identifier") or "")
        phone = digits(data.get("phone") or data.get("phone_number") or data.get("mobile") or "")
        name = clean(data.get("name") or "")
        if not ident and text:
            m = re.search(r"(?:USER\s*ID|PROFILE\s*ID|ID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,80})", text, re.I)
            if m:
                ident = clean(m.group(1))
        if not phone and text:
            m = re.search(r"(?:\+?91[\s\-]?)?[6-9][0-9\s\-]{8,14}", text)
            if m:
                phone = digits(m.group(0))
        if not name and text:
            m = re.search(r"(?:NAME|USER)\s*[:#\-]?\s*([A-Za-z][A-Za-z ._\-]{1,60})", text, re.I)
            if m:
                name = clean(m.group(1))
        return ident, phone, name, text

    def record_matches(key: Any, profile: Any, ident: str, phone: str, name: str) -> bool:
        vals = {v.lower() for v in profile_id_values(key, profile)}
        if ident and ident.lower() in vals:
            return True
        if phone:
            phone_vals = {digits(v) for v in vals if digits(v)}
            if phone in phone_vals or ("phone_" + phone).lower() in vals:
                return True
            if digits(key) == phone or profile_phone(profile) == phone:
                return True
        if name and isinstance(profile, dict):
            n = clean(profile.get("name") or profile.get("customerName") or profile.get("displayName") or "").lower()
            if n and n == name.lower():
                return True
        return False

    profile_top_keys = ("profiles", "userProfiles", "vipProfiles", "users", "customers", "vipUsers")

    def delete_matching_profiles(state: Dict[str, Any], ident: str, phone: str, name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        deleted = []
        tomb = state.get("deletedProfiles") if isinstance(state.get("deletedProfiles"), dict) else {}
        for top in profile_top_keys:
            coll = state.get(top)
            if isinstance(coll, dict):
                remove_keys = []
                for key, profile in list(coll.items()):
                    if record_matches(key, profile, ident, phone, name):
                        remove_keys.append(key)
                for key in remove_keys:
                    profile = coll.pop(key, None)
                    rec_phone = profile_phone(profile) or phone
                    tomb[str(key)] = {"deleted": True, "top": top, "phone": rec_phone, "deletedAt": now_iso()}
                    if rec_phone:
                        tomb["phone_" + rec_phone] = {"deleted": True, "top": top, "key": str(key), "deletedAt": now_iso()}
                    deleted.append({"top": top, "key": str(key), "phone": rec_phone})
                state[top] = coll
            elif isinstance(coll, list):
                kept = []
                for idx, profile in enumerate(coll):
                    if record_matches(idx, profile, ident, phone, name):
                        rec_phone = profile_phone(profile) or phone
                        tomb[f"{top}_{idx}"] = {"deleted": True, "top": top, "index": idx, "phone": rec_phone, "deletedAt": now_iso()}
                        if rec_phone:
                            tomb["phone_" + rec_phone] = {"deleted": True, "top": top, "index": idx, "deletedAt": now_iso()}
                        deleted.append({"top": top, "index": idx, "phone": rec_phone})
                    else:
                        kept.append(profile)
                state[top] = kept
        state["deletedProfiles"] = tomb
        return deleted, tomb

    @app.route("/api/vips/profile/delete", methods=["POST"])
    @app.route("/api/vip/profile/delete", methods=["POST"])
    @app.route("/api/profile/delete", methods=["POST"])
    def vip_profile_delete_api():
        try:
            data = request.get_json(silent=True) or {}
            ident, phone, name, text = parse_identifiers(data)
            if not (ident or phone or name or text):
                return jsonify({"status": "error", "ok": False, "reason": "Missing profile identifier/phone/name"}), 400
            state = state_now()
            deleted, tomb = delete_matching_profiles(state, ident, phone, name)
            if not deleted:
                return jsonify({"status": "not_found", "ok": False, "reason": "Profile not found", "identifier": ident, "phone": phone}), 404
            updates = {k: state.get(k) for k in profile_top_keys if k in state}
            updates["deletedProfiles"] = tomb
            ok = True
            for k, v in updates.items():
                ok = put_child([k], v) and ok
            if not ok:
                put_top(state, updates)
            return jsonify({"status": "success", "ok": True, "deleted": deleted, "identifier": ident, "phone": phone})
        except Exception as exc:
            return jsonify({"status": "error", "ok": False, "reason": str(exc)}), 500

    @app.route("/api/vips/profile/delete/status", methods=["GET"])
    def vip_profile_delete_status():
        return jsonify({"status": "ok", "feature": "titan_profile_delete_guard_patch", "version": "v2-runtime"})

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
            if not html or "vip-profile-delete-guard-v2" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan profile delete guard loaded: v2-runtime")


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
<script id="vip-profile-delete-guard-v2">
(function(){
  if(window.__VIP_PROFILE_DELETE_GUARD_V2__) return;
  window.__VIP_PROFILE_DELETE_GUARD_V2__ = true;
  const API='/api/vips/profile/delete';
  function txt(n){return String((n&&((n.innerText||n.textContent||n.value||n.getAttribute&&n.getAttribute('aria-label'))))||'').replace(/\s+/g,' ').trim()}
  function inVips(){return /\bVIPS\b|VIP\s+PROFILE|USER\s+PROFILE/i.test(txt(document.body))}
  function isDeleteControl(el){const s=txt(el).toUpperCase();return /\b(DELETE|REMOVE|TRASH|PROFILE DELETE|USER DELETE)\b/.test(s)}
  function cardFor(el){let n=el;for(let i=0;n&&i<8;i++,n=n.parentElement){const s=txt(n);if(s.length>40&&s.length<1800&&/(USER|PROFILE|PHONE|MOBILE|VIP|APPROVAL|WALLET|NAME)/i.test(s))return n}return el.parentElement}
  function extract(card){
    const s=txt(card); let id='', phone='', name='';
    let m=s.match(/(?:USER\s*ID|PROFILE\s*ID|ID)\s*[:#\-]?\s*([A-Za-z0-9_@+\-.]{3,80})/i); if(m) id=m[1];
    m=s.match(/(?:\+?91[\s\-]?)?[6-9][0-9\s\-]{8,14}/); if(m) phone=m[0];
    m=s.match(/(?:NAME|USER)\s*[:#\-]?\s*([A-Za-z][A-Za-z ._\-]{1,60})/i); if(m) name=m[1];
    return {id:id, phone:phone, name:name, text:s.slice(0,1600)};
  }
  function headers(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||localStorage.getItem('titan_admin_token')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}
  async function deleteProfile(el){
    const card=cardFor(el); const data=extract(card);
    if(!confirm('VIP profile delete karna hai?')) return;
    try{
      const r=await fetch(API,{method:'POST',headers:headers(),body:JSON.stringify(data)});
      const j=await r.json().catch(()=>({}));
      if(r.ok&&j&&j.ok!==false){
        try{card.style.opacity='0.35'; card.style.pointerEvents='none'}catch(e){}
        alert('Profile deleted. Refresh ke baad wapas nahi aana chahiye.');
        try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}
      }else{
        alert('Delete failed: '+(j.reason||j.status||r.status));
      }
    }catch(e){alert('Delete failed: '+e.message)}
  }
  document.addEventListener('click',function(ev){
    if(!inVips()) return;
    const el=ev.target&&ev.target.closest?ev.target.closest('button,a,[role="button"],.btn'):null;
    if(!el||!isDeleteControl(el)) return;
    ev.preventDefault(); ev.stopPropagation();
    deleteProfile(el);
  },true);
})();
</script>
'''


if __name__ == "__main__":
    raise SystemExit(main())
