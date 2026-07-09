"""Titan Nova VIP tab control patch.

This patch stabilizes the VIP/client tab without editing the large legacy backup.
It adds child-path-safe VIP APIs and a frontend override for create, approve,
access toggle, expiry save, repair, and soft archive.
"""


def register_titan_vip_control(app):
    if getattr(app, "_titan_vip_control_registered", False):
        return
    app._titan_vip_control_registered = True

    from flask import jsonify, request
    import copy
    import datetime
    import json
    import re
    import time
    import uuid

    VERSION = "2026-07-09-vip-control-v1"
    ADMIN_IDS = {"admin1", "admin2", "admin3"}

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for v in app.view_functions.values():
                g = getattr(v, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "_firebase_put_child" in g:
                    return g
        except Exception:
            pass
        return {}

    def clone(obj):
        try:
            return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
        except Exception:
            try:
                return copy.deepcopy(obj)
            except Exception:
                return obj

    def now_iso():
        fn = G().get("_now_iso_local")
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        return datetime.datetime.now().isoformat(timespec="seconds")

    def today():
        fn = G().get("_safe_today")
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        return datetime.date.today().isoformat()

    def get_state():
        g = G()
        for name in ("migrate_and_get_state", "load_from_firebase"):
            fn = g.get(name)
            if callable(fn):
                try:
                    st = fn()
                    if isinstance(st, dict):
                        return st
                except Exception:
                    pass
        return {}

    def put_child(parts, value):
        fn = G().get("_firebase_put_child")
        if callable(fn):
            return fn(parts, value)
        fn2 = G().get("_firebase_put_top_level_children")
        if callable(fn2) and len(parts) == 1:
            st = get_state()
            return fn2(st, {str(parts[0]): value}, audit=False)
        saver = G().get("save_to_firebase")
        if callable(saver):
            st = get_state()
            cur = st
            for p in parts[:-1]:
                cur = cur.setdefault(str(p), {})
            if parts:
                cur[str(parts[-1])] = value
            return saver(st)
        return False

    def add_audit(st, action, detail=None):
        log = st.setdefault("auditLog", [])
        if not isinstance(log, list):
            log = []
            st["auditLog"] = log
        rec = {
            "id": "vip_" + str(int(time.time() * 1000)),
            "time": now_iso(),
            "action": action,
            "detail": detail or {},
            "version": VERSION,
        }
        log.append(rec)
        if len(log) > 1000:
            del log[:-1000]
        return rec

    def clean_phone(v):
        digits = re.sub(r"\D+", "", str(v or ""))
        if len(digits) > 10 and digits.startswith("91"):
            digits = digits[-10:]
        return digits[-10:] if len(digits) >= 10 else digits

    def profile_key_from_name_phone(name, phone):
        base = clean_phone(phone) or re.sub(r"[^a-z0-9]+", "_", str(name or "vip").lower()).strip("_") or "vip"
        return "client_" + base[:32]

    def default_config(st):
        profiles = st.setdefault("profiles", {})
        master = profiles.get("admin1", {}) if isinstance(profiles.get("admin1"), dict) else {}
        cfg = clone(master.get("config") or {}) if isinstance(master.get("config"), dict) else {}
        cfg.setdefault("capital", 0)
        cfg.setdefault("dayTarget", 0)
        cfg.setdefault("ank", {"cap": 0, "tgt": 0})
        cfg.setdefault("jodi", {"cap": 0, "tgt": 0})
        cfg.setdefault("pannel", {"cap": 0, "tgt": 0})
        cfg.setdefault("ankSplit", True)
        cfg.setdefault("panSplit", True)
        for k in ("ank", "jodi", "pannel"):
            if not isinstance(cfg.get(k), dict):
                cfg[k] = {"cap": 0, "tgt": 0}
            cfg[k].setdefault("cap", 0)
            cfg[k].setdefault("tgt", 0)
        return cfg

    def ensure_wallet(st, uid, profile=None):
        wallets = st.setdefault("wallets", {})
        if not isinstance(wallets, dict):
            wallets = {}
            st["wallets"] = wallets
        settings = st.get("walletSettings", {}) if isinstance(st.get("walletSettings"), dict) else {}
        w = wallets.get(uid)
        if not isinstance(w, dict):
            w = {
                "userId": uid,
                "name": (profile or {}).get("name", uid),
                "phone": (profile or {}).get("phone", ""),
                "balance": 0,
                "creditLimit": float(settings.get("defaultCreditLimit") or 0),
                "ledger": [],
                "createdAt": now_iso(),
            }
            wallets[uid] = w
        w.setdefault("userId", uid)
        w["name"] = (profile or {}).get("name") or w.get("name") or uid
        w["phone"] = (profile or {}).get("phone") or w.get("phone") or ""
        w.setdefault("balance", 0)
        w.setdefault("creditLimit", float(settings.get("defaultCreditLimit") or 0))
        w.setdefault("ledger", [])
        w["updatedAt"] = now_iso()
        return w

    def ensure_profile(st, uid, profile=None, created=False):
        profile = profile if isinstance(profile, dict) else {}
        profile.setdefault("name", uid)
        profile["phone"] = clean_phone(profile.get("phone", ""))
        profile.setdefault("config", default_config(st))
        if not isinstance(profile.get("config"), dict):
            profile["config"] = default_config(st)
        cfg = profile["config"]
        cfg.setdefault("capital", 0)
        cfg.setdefault("dayTarget", 0)
        cfg.setdefault("ank", {"cap": 0, "tgt": 0})
        cfg.setdefault("jodi", {"cap": 0, "tgt": 0})
        cfg.setdefault("pannel", {"cap": 0, "tgt": 0})
        cfg.setdefault("ankSplit", True)
        cfg.setdefault("panSplit", True)
        for k in ("ank", "jodi", "pannel"):
            if not isinstance(cfg.get(k), dict):
                cfg[k] = {"cap": 0, "tgt": 0}
            cfg[k].setdefault("cap", 0)
            cfg[k].setdefault("tgt", 0)
        profile.setdefault("dayRecords", {})
        if not isinstance(profile.get("dayRecords"), dict):
            profile["dayRecords"] = {}
        if uid in ADMIN_IDS:
            profile["approvalStatus"] = "approved"
            profile["vipAccessEnabled"] = True
            profile.setdefault("role", "admin")
            profile["archived"] = False
            profile["deleted"] = False
        else:
            profile.setdefault("approvalStatus", "approved" if not profile.get("autoCreated") else "pending")
            if str(profile.get("approvalStatus") or "").lower() == "pending":
                profile["vipAccessEnabled"] = False
            else:
                profile.setdefault("vipAccessEnabled", True)
            profile.setdefault("role", "vip")
            profile.setdefault("expiryDate", "")
        profile.setdefault("createdAt", now_iso() if created else profile.get("createdAt", now_iso()))
        profile["updatedAt"] = now_iso()
        return profile

    def ensure_vip_state(st):
        repairs = []
        profiles = st.setdefault("profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            st["profiles"] = profiles
            repairs.append("profiles")
        for aid in ("admin1", "admin2", "admin3"):
            if not isinstance(profiles.get(aid), dict):
                profiles[aid] = {"name": aid.upper(), "phone": "", "config": default_config(st), "dayRecords": {}, "role": "admin"}
                repairs.append(aid)
            profiles[aid] = ensure_profile(st, aid, profiles[aid])
        for uid, p in list(profiles.items()):
            if not isinstance(p, dict):
                profiles.pop(uid, None)
                repairs.append("bad_profile:" + str(uid))
                continue
            profiles[uid] = ensure_profile(st, uid, p)
            if uid not in ADMIN_IDS and profiles[uid].get("archived") is not True and profiles[uid].get("deleted") is not True:
                ensure_wallet(st, uid, profiles[uid])
        if not isinstance(st.get("deletedProfiles"), dict):
            st["deletedProfiles"] = {}
        return st, repairs

    def visible_profiles(st):
        out = []
        for uid, p in (st.get("profiles") or {}).items():
            if uid in ADMIN_IDS or not isinstance(p, dict):
                continue
            if p.get("archived") is True or p.get("deleted") is True:
                continue
            out.append({
                "id": uid,
                "name": p.get("name", uid),
                "phone": p.get("phone", ""),
                "approvalStatus": p.get("approvalStatus", "approved"),
                "vipAccessEnabled": p.get("vipAccessEnabled") is not False,
                "expiryDate": p.get("expiryDate", ""),
                "autoCreated": bool(p.get("autoCreated")),
                "createdAt": p.get("createdAt", ""),
                "updatedAt": p.get("updatedAt", ""),
                "walletBalance": ((st.get("wallets") or {}).get(uid) or {}).get("balance", 0),
            })
        out.sort(key=lambda x: (0 if str(x.get("approvalStatus", "")).lower() == "pending" else 1, str(x.get("name") or "").lower()))
        return out

    def summary(st):
        profiles = st.get("profiles", {}) if isinstance(st.get("profiles"), dict) else {}
        deleted = st.get("deletedProfiles", {}) if isinstance(st.get("deletedProfiles"), dict) else {}
        rows = visible_profiles(st)
        return {
            "totalVisible": len(rows),
            "pending": sum(1 for x in rows if str(x.get("approvalStatus", "")).lower() == "pending"),
            "enabled": sum(1 for x in rows if x.get("vipAccessEnabled") is True),
            "disabled": sum(1 for x in rows if x.get("vipAccessEnabled") is False),
            "archived": len(deleted) + sum(1 for p in profiles.values() if isinstance(p, dict) and p.get("archived") is True),
            "wallets": len(st.get("wallets", {}) if isinstance(st.get("wallets"), dict) else {}),
        }

    def commit_common(st):
        put_child(["profiles"], st.get("profiles", {}))
        put_child(["wallets"], st.get("wallets", {}))
        put_child(["deletedProfiles"], st.get("deletedProfiles", {}))
        put_child(["auditLog"], (st.get("auditLog") or [])[-1000:])

    @app.route("/api/vip_control/status", methods=["GET"])
    def vip_control_status():
        st, repairs = ensure_vip_state(get_state())
        return jsonify({"status": "success", "version": VERSION, "summary": summary(st), "repairsPreview": repairs, "profiles": visible_profiles(st)})

    @app.route("/api/vip_control/repair", methods=["POST"])
    def vip_control_repair():
        st, repairs = ensure_vip_state(get_state())
        add_audit(st, "vip_control_repair", {"repairs": repairs})
        commit_common(st)
        return jsonify({"status": "success", "version": VERSION, "repairs": repairs, "summary": summary(st), "profiles": st.get("profiles", {}), "wallets": st.get("wallets", {})})

    @app.route("/api/vip_control/create", methods=["POST"])
    def vip_control_create():
        data = request.get_json(silent=True) or {}
        st, repairs = ensure_vip_state(get_state())
        name = str(data.get("name") or "").strip()
        phone = clean_phone(data.get("phone") or "")
        if not name:
            return jsonify({"status": "error", "message": "VIP name required"}), 400
        uid = str(data.get("userId") or "").strip() or profile_key_from_name_phone(name, phone)
        if uid in ADMIN_IDS:
            return jsonify({"status": "error", "message": "Admin id reserved"}), 400
        base = uid
        i = 2
        while uid in st.get("profiles", {}) and not data.get("overwrite"):
            uid = f"{base}_{i}"
            i += 1
        profile = ensure_profile(st, uid, {
            "name": name,
            "phone": phone,
            "config": default_config(st),
            "dayRecords": {},
            "expiryDate": str(data.get("expiryDate") or ""),
            "vipAccessEnabled": bool(data.get("vipAccessEnabled", True)),
            "approvalStatus": "approved" if data.get("approvalStatus") != "pending" else "pending",
            "approvedAt": now_iso() if data.get("approvalStatus") != "pending" else "",
            "approvedBy": str(data.get("approvedBy") or "admin1"),
            "role": "vip",
        }, created=True)
        st.setdefault("profiles", {})[uid] = profile
        wallet = ensure_wallet(st, uid, profile)
        add_audit(st, "vip_control_create", {"userId": uid, "name": name, "phone": phone, "repairs": repairs})
        commit_common(st)
        return jsonify({"status": "success", "version": VERSION, "userId": uid, "profile": profile, "wallet": wallet, "profiles": st.get("profiles", {}), "wallets": st.get("wallets", {}), "summary": summary(st)})

    @app.route("/api/vip_control/update", methods=["POST"])
    def vip_control_update():
        data = request.get_json(silent=True) or {}
        st, repairs = ensure_vip_state(get_state())
        uid = str(data.get("userId") or data.get("pid") or "").strip()
        if not uid or uid not in st.get("profiles", {}):
            return jsonify({"status": "error", "message": "VIP not found"}), 404
        profile = ensure_profile(st, uid, st["profiles"][uid])
        if uid in ADMIN_IDS:
            profile["approvalStatus"] = "approved"
            profile["vipAccessEnabled"] = True
        else:
            if "name" in data:
                n = str(data.get("name") or "").strip()
                if n:
                    profile["name"] = n[:120]
            if "phone" in data:
                profile["phone"] = clean_phone(data.get("phone"))
            if "expiryDate" in data:
                profile["expiryDate"] = str(data.get("expiryDate") or "")[:20]
            if "approvalStatus" in data:
                status = str(data.get("approvalStatus") or "").lower().strip()
                if status in ("approved", "pending", "rejected"):
                    profile["approvalStatus"] = status
                    if status == "approved":
                        profile["approvedAt"] = now_iso()
                        profile["approvedBy"] = str(data.get("approvedBy") or "admin1")
                        profile["vipAccessEnabled"] = True
                    elif status == "pending":
                        profile["vipAccessEnabled"] = False
            if "vipAccessEnabled" in data or "enabled" in data:
                enabled = bool(data.get("vipAccessEnabled", data.get("enabled")))
                if str(profile.get("approvalStatus") or "").lower() == "pending" and enabled:
                    return jsonify({"status": "error", "message": "Pending VIP ko pehle approve karo"}), 400
                profile["vipAccessEnabled"] = enabled
        profile["updatedAt"] = now_iso()
        st["profiles"][uid] = profile
        wallet = ensure_wallet(st, uid, profile) if uid not in ADMIN_IDS else None
        add_audit(st, "vip_control_update", {"userId": uid, "fields": sorted(data.keys()), "repairs": repairs})
        commit_common(st)
        return jsonify({"status": "success", "version": VERSION, "userId": uid, "profile": profile, "wallet": wallet, "profiles": st.get("profiles", {}), "wallets": st.get("wallets", {}), "summary": summary(st)})

    @app.route("/api/vip_control/archive", methods=["POST"])
    def vip_control_archive():
        data = request.get_json(silent=True) or {}
        st, repairs = ensure_vip_state(get_state())
        uid = str(data.get("userId") or data.get("pid") or "").strip()
        if not uid or uid not in st.get("profiles", {}):
            return jsonify({"status": "error", "message": "VIP not found"}), 404
        if uid in ADMIN_IDS:
            return jsonify({"status": "error", "message": "Admin profile archive/delete blocked"}), 400
        profile = st["profiles"].pop(uid)
        profile = ensure_profile(st, uid, profile)
        profile["archived"] = True
        profile["deleted"] = True
        profile["vipAccessEnabled"] = False
        profile["archivedAt"] = now_iso()
        profile["archiveReason"] = str(data.get("reason") or "VIP archived from admin tab")[:200]
        st.setdefault("deletedProfiles", {})[uid] = profile
        # Keep wallet ledger safe but remove active wallet card to avoid active-user confusion.
        if isinstance(st.get("wallets"), dict) and uid in st["wallets"]:
            w = st["wallets"].pop(uid)
            profile["archivedWallet"] = w
        # Remove active daily send schedules for this VIP only.
        if isinstance(st.get("ledgerSchedules"), dict):
            for k in list(st["ledgerSchedules"].keys()):
                if str(k).startswith(uid + "|"):
                    st["ledgerSchedules"].pop(k, None)
            put_child(["ledgerSchedules"], st.get("ledgerSchedules", {}))
        add_audit(st, "vip_control_archive", {"userId": uid, "reason": profile.get("archiveReason"), "repairs": repairs})
        commit_common(st)
        return jsonify({"status": "success", "version": VERSION, "userId": uid, "deletedProfiles": st.get("deletedProfiles", {}), "profiles": st.get("profiles", {}), "wallets": st.get("wallets", {}), "summary": summary(st)})

    @app.route("/api/vip_control/restore", methods=["POST"])
    def vip_control_restore():
        data = request.get_json(silent=True) or {}
        st, repairs = ensure_vip_state(get_state())
        uid = str(data.get("userId") or data.get("pid") or "").strip()
        deleted = st.setdefault("deletedProfiles", {})
        if not uid or uid not in deleted:
            return jsonify({"status": "error", "message": "Archived VIP not found"}), 404
        profile = ensure_profile(st, uid, deleted.pop(uid))
        profile["archived"] = False
        profile["deleted"] = False
        profile["vipAccessEnabled"] = bool(data.get("vipAccessEnabled", False))
        profile["restoredAt"] = now_iso()
        st.setdefault("profiles", {})[uid] = profile
        if isinstance(profile.get("archivedWallet"), dict):
            st.setdefault("wallets", {})[uid] = profile.pop("archivedWallet")
        ensure_wallet(st, uid, profile)
        add_audit(st, "vip_control_restore", {"userId": uid, "repairs": repairs})
        commit_common(st)
        return jsonify({"status": "success", "version": VERSION, "userId": uid, "profile": profile, "profiles": st.get("profiles", {}), "wallets": st.get("wallets", {}), "summary": summary(st)})

    @app.after_request
    def vip_control_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-vip-control-v1" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp

    print("✅ Titan VIP control patch loaded", VERSION)


SCRIPT = r'''
<script id="titan-vip-control-v1">
(function(){
 if(window.__TITAN_VIP_CONTROL_V1__)return; window.__TITAN_VIP_CONTROL_V1__=true;
 const VERSION='2026-07-09-vip-control-v1';
 const ADMIN_IDS=new Set(['admin1','admin2','admin3']);
 let vipSearch='';
 function h(v){return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
 function a(v){return h(v).replace(/`/g,'&#96;')}
 function notify(t,m,k){try{if(typeof showRealNotification==='function')showRealNotification(t,m,k||'info');else console.log(t,m)}catch(e){}}
 function headers(){const x={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)x['X-Titan-Admin-Token']=t}catch(e){}return x}
 async function post(url,payload){const res=await fetch(url,{method:'POST',headers:headers(),body:JSON.stringify(payload||{})});const data=await res.json().catch(()=>({status:'error',message:'Bad JSON'}));if(!res.ok||data.status!=='success')throw new Error(data.message||('HTTP '+res.status));return data}
 function fixVipState(){
   try{
     if(!window.appState) return;
     if(!appState.profiles||typeof appState.profiles!=='object'||Array.isArray(appState.profiles))appState.profiles={};
     if(!appState.profiles.admin1)appState.profiles.admin1={name:'ADMIN 1',config:{},dayRecords:{}};
     ['admin1','admin2','admin3'].forEach(id=>{if(!appState.profiles[id])appState.profiles[id]={name:id.toUpperCase(),config:appState.profiles.admin1.config||{},dayRecords:{}};appState.profiles[id].approvalStatus='approved';appState.profiles[id].vipAccessEnabled=true;appState.profiles[id].role='admin';});
     Object.entries(appState.profiles).forEach(([pid,p])=>{if(!p||typeof p!=='object')return;p.config=p.config||{};['ank','jodi','pannel'].forEach(k=>{if(!p.config[k]||typeof p.config[k]!=='object')p.config[k]={cap:0,tgt:0};if(typeof p.config[k].cap==='undefined')p.config[k].cap=0;if(typeof p.config[k].tgt==='undefined')p.config[k].tgt=0});if(typeof p.config.capital==='undefined')p.config.capital=0;if(typeof p.config.dayTarget==='undefined')p.config.dayTarget=0;if(!p.dayRecords||typeof p.dayRecords!=='object')p.dayRecords={};if(!ADMIN_IDS.has(pid)){if(typeof p.approvalStatus==='undefined')p.approvalStatus=p.autoCreated?'pending':'approved';if(String(p.approvalStatus).toLowerCase()==='pending')p.vipAccessEnabled=false;else if(typeof p.vipAccessEnabled==='undefined')p.vipAccessEnabled=true;}});
     if(!appState.wallets||typeof appState.wallets!=='object'||Array.isArray(appState.wallets))appState.wallets={};
   }catch(e){console.warn('VIP state repair failed',e)}
 }
 function vipRows(includeArchived){fixVipState();return Object.entries(appState.profiles||{}).filter(([pid,p])=>!ADMIN_IDS.has(pid)&&p&&typeof p==='object'&&(includeArchived||(!p.archived&&!p.deleted))).map(([pid,p])=>({pid,p,w:(appState.wallets||{})[pid]||{}})).sort((x,y)=>{const px=String(x.p.approvalStatus||'').toLowerCase()==='pending'?0:1;const py=String(y.p.approvalStatus||'').toLowerCase()==='pending'?0:1;return px-py||String(x.p.name||x.pid).localeCompare(String(y.p.name||y.pid));});}
 function vipBadge(p){const st=String(p.approvalStatus||'approved').toLowerCase();if(st==='pending')return '<span class="text-[8px] px-2 py-1 rounded-lg bg-[rgba(250,199,72,0.12)] text-[var(--amber)] border border-[rgba(250,199,72,0.25)] font-black uppercase">Pending</span>';if(p.vipAccessEnabled===false)return '<span class="text-[8px] px-2 py-1 rounded-lg bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] font-black uppercase">Read-only</span>';return '<span class="text-[8px] px-2 py-1 rounded-lg bg-[rgba(0,194,111,0.12)] text-[var(--green)] border border-[rgba(0,194,111,0.22)] font-black uppercase">Active</span>';}
 function vipStats(){const rows=vipRows(false);return {total:rows.length,pending:rows.filter(x=>String(x.p.approvalStatus||'').toLowerCase()==='pending').length,enabled:rows.filter(x=>x.p.vipAccessEnabled!==false).length,disabled:rows.filter(x=>x.p.vipAccessEnabled===false).length};}
 window.refreshVipControl=async function(silent){try{const res=await fetch('/api/vip_control/status?ts='+Date.now(),{headers:headers(),cache:'no-store'});const data=await res.json();if(data.status==='success'&&Array.isArray(data.profiles)){fixVipState();return data}throw new Error(data.message||'VIP status failed')}catch(e){if(!silent)notify('❌ VIP Refresh Error',String(e.message||e),'danger');return null}};
 window.repairVipControl=async function(){try{const data=await post('/api/vip_control/repair',{});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();try{localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(e){}notify('✅ VIP Repair Done',`${(data.repairs||[]).length} repair, ${(data.summary||{}).totalVisible||0} VIP ready.`,'success');try{render(true)}catch(e){}return data}catch(e){notify('❌ VIP Repair Error',String(e.message||e),'danger')}};
 window.addVIP=async function(){try{const n=(document.getElementById('c-name')?.value||'').trim();const p=(document.getElementById('c-phone')?.value||'').replace(/\D/g,'');if(!n)return notify('⚠️ Name Required','VIP ka valid name likho.','danger');const data=await post('/api/vip_control/create',{name:n,phone:p,approvalStatus:'approved',vipAccessEnabled:true});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();try{document.getElementById('c-name').value='';document.getElementById('c-phone').value=''}catch(e){}try{localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(e){}notify('✅ VIP Added',`${n} ka profile + wallet ready.`,'success');render(true)}catch(e){notify('❌ VIP Add Error',String(e.message||e),'danger')}};
 window.approveVipProfile=async function(pid){try{const data=await post('/api/vip_control/update',{userId:pid,approvalStatus:'approved',vipAccessEnabled:true,approvedBy:(appState&&appState.activeId)||'admin1'});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();notify('✅ VIP Approved',(appState.profiles[pid]?.name||pid)+' approved ho gaya.','success');render(true)}catch(e){notify('❌ Approval Error',String(e.message||e),'danger')}};
 window.rejectVipProfile=async function(pid){try{const p=(appState.profiles||{})[pid]||{};if(!confirm((p.name||pid)+' pending profile reject/archive karna hai?'))return;const data=await post('/api/vip_control/archive',{userId:pid,reason:'Pending profile rejected by admin'});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();notify('🗑️ VIP Rejected','Pending profile archive ho gaya.','danger');render(true)}catch(e){notify('❌ Reject Error',String(e.message||e),'danger')}};
 window.toggleVipAccess=async function(pid,enabled){try{const data=await post('/api/vip_control/update',{userId:pid,vipAccessEnabled:!!enabled});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();notify(enabled?'✅ Access Enabled':'🔒 Read-only Mode',(appState.profiles[pid]?.name||pid)+' update ho gaya.',enabled?'success':'danger');render(true)}catch(e){notify('❌ Access Error',String(e.message||e),'danger');render(true)}};
 window.saveExpiryDate=async function(userId){try{const expiry=document.getElementById('exp-'+userId)?.value||'';if(!expiry)return notify('⚠️ Date Required','Expiry date select karo.','danger');const data=await post('/api/vip_control/update',{userId,expiryDate:expiry});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();notify('✅ Expiry Saved','Membership expiry update ho gayi.','success');render(true)}catch(e){notify('❌ Expiry Error',String(e.message||e),'danger')}};
 window.deleteProfile=async function(pid){try{if(ADMIN_IDS.has(pid))return notify('⚠️ Blocked','Admin profile delete nahi ho sakta.','danger');const p=(appState.profiles||{})[pid]||{};if(!confirm((p.name||pid)+' ko active VIP list se archive/disable karna hai? Data deletedProfiles me safe rahega.'))return;const data=await post('/api/vip_control/archive',{userId:pid,reason:'Archived from VIP tab'});appState.profiles=data.profiles||appState.profiles;appState.wallets=data.wallets||appState.wallets;fixVipState();notify('🗄️ VIP Archived','Hard delete nahi hua. Data safe archive me hai.','success');render(true)}catch(e){notify('❌ Archive Error',String(e.message||e),'danger')}};
 window.openClient=function(pid){try{fixVipState();if(!appState.profiles[pid])return notify('⚠️ Missing','VIP profile nahi mila.','danger');if(String(appState.profiles[pid].approvalStatus||'').toLowerCase()==='pending')return notify('⚠️ Pending','Pehle VIP approve karo.','danger');if(typeof pushNativeState==='function')pushNativeState();appState.activeId=pid;state=appState.profiles[pid];activeTab='ank';if(typeof ensureDataStruct==='function')ensureDataStruct();setMainNav('ledger')}catch(e){notify('❌ Open VIP Error',String(e.message||e),'danger')}};
 window.renderClients=function(){
   fixVipState();
   const s=vipStats();
   const q=String(vipSearch||'').toLowerCase();
   let rows=vipRows(false).filter(x=>!q||String(x.p.name||'').toLowerCase().includes(q)||String(x.p.phone||'').includes(q)||String(x.pid).toLowerCase().includes(q));
   const card=x=>{const p=x.p,w=x.w||{},pending=String(p.approvalStatus||'').toLowerCase()==='pending',disabled=p.vipAccessEnabled===false;return `<div class="native-card p-3 mb-2">
     <div class="flex items-start gap-3">
       <div class="w-11 h-11 rounded-full bg-[rgba(0,168,132,0.15)] text-[var(--green)] flex items-center justify-center shrink-0"><i class="fas fa-user"></i></div>
       <div class="flex-1 min-w-0"><div class="flex items-center gap-2 mb-1"><h3 class="text-white font-black text-[13px] truncate">${h(p.name||x.pid)}</h3>${vipBadge(p)}</div><p class="text-[9px] text-[var(--text-muted)] break-all">${h(p.phone||'-')} · ${h(x.pid)}</p><p class="text-[9px] text-[var(--text-muted)] mt-1">Wallet: <b class="text-[var(--green)]">₹${Number(w.balance||0)}</b> · Expiry: ${h(p.expiryDate||'Not set')}</p></div>
       <label class="switch m-0 shrink-0"><input type="checkbox" onchange="toggleVipAccess('${a(x.pid)}',this.checked)" ${!disabled&&!pending?'checked':''} ${pending?'disabled':''}><span class="slider"></span></label>
     </div>
     <div class="grid grid-cols-2 gap-2 mt-3"><input id="exp-${a(x.pid)}" type="date" value="${a(p.expiryDate||'')}" class="native-input text-[11px] py-2"><button onclick="saveExpiryDate('${a(x.pid)}')" class="bg-[var(--primary)] text-white py-2 rounded-xl font-black text-[9px] uppercase">Save Expiry</button></div>
     ${pending?`<div class="grid grid-cols-2 gap-2 mt-2"><button onclick="approveVipProfile('${a(x.pid)}')" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Approve</button><button onclick="rejectVipProfile('${a(x.pid)}')" class="bg-[rgba(255,93,93,0.12)] text-[var(--rose)] border border-[rgba(255,93,93,0.25)] py-3 rounded-xl font-black text-[10px] uppercase">Reject</button></div>`:`<div class="grid grid-cols-3 gap-2 mt-2"><button onclick="openClient('${a(x.pid)}')" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase">Open</button><button onclick="toggleVipAccess('${a(x.pid)}',${disabled?'true':'false'})" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[10px] uppercase">${disabled?'Enable':'Read-only'}</button><button onclick="deleteProfile('${a(x.pid)}')" class="bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] py-3 rounded-xl font-black text-[10px] uppercase">Archive</button></div>`}
   </div>`};
   return `<div class="px-3 py-4 pb-28">
     <p class="sec-header">VIP Control <button onclick="repairVipControl()" class="text-[var(--primary)]"><i class="fas fa-wrench"></i></button></p>
     <div class="wallet-hud rounded-2xl mb-3">${[['Total',s.total],['Pending',s.pending],['Active',s.enabled],['Read-only',s.disabled]].map(([l,v])=>`<div class="stat-box"><p class="stat-lbl">${l}</p><p class="stat-val text-white">${v}</p></div>`).join('')}</div>
     <div class="native-card p-3 mb-3" style="border-color:rgba(0,194,111,0.22);background:rgba(0,194,111,0.04)"><p class="text-white font-black text-[12px] uppercase mb-2">Add VIP</p><div class="grid grid-cols-2 gap-2"><input id="c-name" class="native-input text-[12px] py-3" placeholder="VIP Name"><input id="c-phone" class="native-input text-[12px] py-3" placeholder="Phone"></div><button onclick="addVIP()" class="mt-2 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-user-plus mr-1"></i>Add VIP + Wallet</button></div>
     <div class="flex gap-2 mb-3"><input value="${a(vipSearch)}" oninput="vipSearch=this.value;render(true)" class="native-input text-[12px] py-3" placeholder="Search name / phone / id"><button onclick="refreshVipControl().then(()=>render(true))" class="bg-[var(--surface-light)] text-white border border-[var(--border)] px-4 rounded-xl font-black text-[10px] uppercase">Refresh</button></div>
     ${rows.length?rows.map(card).join(''):'<div class="native-card p-6 text-center text-[var(--text-muted)] text-xs">VIP profile nahi mila.</div>'}
     <div class="native-card p-3 mt-3 text-[10px] text-[var(--text-muted)] leading-relaxed"><b class="text-white">Safety:</b> Archive hard delete nahi karta. Wallet/history deletedProfiles me safe rahta hai. Admin1/Admin2/Admin3 delete blocked hai.</div>
   </div>`;
 };
 const oldRender=window.render;window.render=function(){fixVipState();return oldRender?oldRender.apply(this,arguments):undefined};
 fixVipState();
 console.log('✅ Titan VIP Control active',VERSION);
})();
</script>
'''
