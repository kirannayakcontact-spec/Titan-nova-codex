"""Titan Nova smooth global realtime bridge.

Runtime owner for app-wide realtime, local UI toggles, full-root save protection,
and ledger delete-intent protection. Keep this as the single realtime guard file.
"""


def register_titan_realtime_global(app):
    if getattr(app, "_titan_realtime_global_registered", False):
        return
    app._titan_realtime_global_registered = True

    from flask import jsonify, request
    import copy
    import json
    import re
    import time

    LEDGER_ROOT_KEYS = (
        "ledger", "ledgers", "ledgerEntries", "entries", "entryBook", "entryBooks",
        "dailyLedger", "marketLedger", "ledgerCards", "cardLedger", "entryLedger",
    )
    PROTECTED_ROOT_KEYS = (
        "profiles", "userProfiles", "vipProfiles", "vipUsers", "vips", "vipList", "vipMembers",
        "clients", "vipClients", "clientProfiles", "customerProfiles", "customers", "members",
        "vipConnections", "vipConnection", "vipLinks", "vip_links", "clientLinks", "client_links",
        "connections", "appUsers", "app_users", "vipAccess", "vip_access", "deletedProfiles",
        *LEDGER_ROOT_KEYS,
        "ledgerDeleteTombstones", "ledgerDeleteIntent",
        "markets", "marketData", "results", "resultHistory", "resultSettings",
        "wallet", "wallets", "balances", "transactions", "payments", "paymentProofs",
        "deposits", "depositProofs", "withdrawals", "withdrawalRequests", "schedules",
        "schedule", "targets", "groups", "contacts", "forward", "forwardSchedules",
        "auditLog", "backupMeta", "settingsVersion",
    )
    PROFILE_KEYS = {
        "profiles", "userProfiles", "vipProfiles", "vipUsers", "vips", "vipList", "vipMembers",
        "clients", "vipClients", "clientProfiles", "customerProfiles", "customers", "members",
        "vipConnections", "vipConnection", "vipLinks", "vip_links", "clientLinks", "client_links",
        "connections", "appUsers", "app_users", "vipAccess", "vip_access",
    }
    LOCAL_ONLY_RE = re.compile(r"(toggle|checkbox|uiOnly|ui_only|viewState|view_state|expanded|collapsed|selectedTab|activeTab|tabState|drawer|modal|panelOpen|panel_open|toast|filterText|searchText|sortBy|sort_by|themeTemp|tempUi|localUi|local_ui|stickyToggle|toggleSticky|resultToggleSticky|autoMark|onlyWait|allVips|msgSummary|settlementOn|autoHitMiss)", re.I)
    BUSINESS_RE = re.compile(r"(ledger|payment|payments|deposit|deposits|withdraw|withdrawal|wallet|wallets|transaction|transactions|entry|entries|result|results|market|markets|profile|profiles|vipProfile|vipProfiles|userProfiles|vipUsers|customers|client|clients|schedule|schedules|target|targets|group|groups|audit|backup|settingsVersion|deletedProfiles|utr|upi|amount|balance|pass|fail|approval|expiry|access)", re.I)

    def G():
        try:
            view = app.view_functions.get("index") or next(iter(app.view_functions.values()))
            return getattr(view, "__globals__", {}) or {}
        except Exception:
            return {}

    def _clone(obj):
        try:
            return json.loads(json.dumps(obj))
        except Exception:
            try:
                return copy.deepcopy(obj)
            except Exception:
                return obj

    def _count(obj):
        if isinstance(obj, (dict, list)):
            return len(obj)
        return 0

    def _digits(value):
        d = re.sub(r"\D+", "", str(value or ""))
        if len(d) == 10:
            return "91" + d
        return d

    def _record_text(value):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
        except Exception:
            return str(value or "").lower()

    def _profile_phone(record):
        if not isinstance(record, dict):
            return ""
        for k in ("phone", "mobile", "number", "whatsapp", "phoneNumber", "wa", "id"):
            d = _digits(record.get(k))
            if d:
                return d
        return ""

    def _tombstone_match_values(deleted_profiles):
        values, phones = set(), set()
        if not isinstance(deleted_profiles, dict):
            return values, phones
        for k, v in deleted_profiles.items():
            raw = str(k or "").strip()
            if raw:
                values.add(raw.lower())
            if isinstance(v, dict):
                for f in ("phone", "key", "path", "id", "rawKey", "rawPath"):
                    val = str(v.get(f) or "").strip()
                    if val:
                        values.add(val.lower())
                        d = _digits(val)
                        if d:
                            phones.add(d)
                for val in v.get("match") or []:
                    s = str(val or "").strip()
                    if s:
                        values.add(s.lower())
                        d = _digits(s)
                        if d:
                            phones.add(d)
        return values, phones

    def _record_is_tombstoned(key, record, deleted_profiles):
        values, phones = _tombstone_match_values(deleted_profiles)
        key_s = str(key or "").strip().lower()
        if key_s and (key_s in values or ("key_" + key_s) in values or ("id_" + key_s) in values):
            return True
        d_key = _digits(key)
        if d_key and d_key in phones:
            return True
        p = _profile_phone(record)
        if p and p in phones:
            return True
        text = _record_text(record)
        for val in values:
            if len(val) >= 8 and val in text:
                return True
        return False

    def _is_local_only_key(key):
        s = str(key or "")
        return bool(LOCAL_ONLY_RE.search(s)) and not bool(BUSINESS_RE.search(s))

    def _scrub_local_only(obj, depth=0):
        if depth > 8 or not isinstance(obj, (dict, list)):
            return obj
        if isinstance(obj, list):
            for item in obj:
                _scrub_local_only(item, depth + 1)
            return obj
        for k in list(obj.keys()):
            if _is_local_only_key(k):
                obj.pop(k, None)
                continue
            _scrub_local_only(obj.get(k), depth + 1)
        return obj

    def _normalize_path(path):
        if isinstance(path, (list, tuple)):
            parts = [str(x).strip() for x in path if str(x).strip()]
        else:
            parts = [p.strip() for p in re.split(r"[/.]+", str(path or "")) if p.strip()]
        return "/".join(parts)

    def _ledger_delete_paths_from(*states):
        out = set()
        for state in states:
            if not isinstance(state, dict):
                continue
            for holder_key in ("ledgerDeleteTombstones", "ledgerDeleteIntent"):
                holder = state.get(holder_key)
                if isinstance(holder, dict):
                    for p in holder.get("paths") or holder.get("deletedPaths") or []:
                        s = _normalize_path(p)
                        if s:
                            out.add(s)
                    for k, v in holder.items():
                        if k in ("paths", "deletedPaths", "version", "lastUpdatedAtMs", "at"):
                            continue
                        if v:
                            s = _normalize_path(k)
                            if s:
                                out.add(s)
                elif isinstance(holder, list):
                    for p in holder:
                        s = _normalize_path(p)
                        if s:
                            out.add(s)
            meta = state.get("fullRootSaveGuard")
            if isinstance(meta, dict):
                for p in meta.get("ledgerDeletePaths") or []:
                    s = _normalize_path(p)
                    if s:
                        out.add(s)
        return {p for p in out if p.split("/", 1)[0] in LEDGER_ROOT_KEYS}

    def _path_deleted(path_parts, delete_paths):
        p = _normalize_path(path_parts)
        if not p:
            return False
        for d in delete_paths or set():
            if p == d or p.startswith(d + "/") or d.startswith(p + "/"):
                return True
        return False

    def _delete_path(obj, path_parts):
        if not path_parts or not isinstance(obj, dict):
            return False
        root = path_parts[0]
        if root not in obj:
            return False
        cur = obj
        for part in path_parts[:-1]:
            if isinstance(cur, dict):
                cur = cur.get(part)
            elif isinstance(cur, list):
                try:
                    cur = cur[int(part)]
                except Exception:
                    return False
            else:
                return False
        last = path_parts[-1]
        if isinstance(cur, dict) and last in cur:
            cur.pop(last, None)
            return True
        if isinstance(cur, list):
            try:
                idx = int(last)
                if 0 <= idx < len(cur):
                    cur.pop(idx)
                    return True
            except Exception:
                return False
        return False

    def _apply_ledger_tombstones(candidate, delete_paths):
        if not isinstance(candidate, dict):
            return []
        applied = []
        for p in sorted(delete_paths or set(), key=lambda x: x.count("/"), reverse=True):
            parts = [x for x in p.split("/") if x]
            if parts and parts[0] in LEDGER_ROOT_KEYS and _delete_path(candidate, parts):
                applied.append(p)
        return applied

    def _merge_protected_dict(top_key, candidate_child, live_child, deleted_profiles, ledger_delete_paths, path_parts):
        if not isinstance(candidate_child, dict) or not isinstance(live_child, dict):
            return candidate_child
        merged = _clone(candidate_child)
        for k, live_value in live_child.items():
            child_path = list(path_parts) + [str(k)]
            if top_key in LEDGER_ROOT_KEYS and _path_deleted(child_path, ledger_delete_paths):
                continue
            if k in merged:
                if isinstance(merged.get(k), dict) and isinstance(live_value, dict):
                    merged[k] = _merge_protected_dict(top_key, merged.get(k) or {}, live_value, deleted_profiles, ledger_delete_paths, child_path)
                continue
            if top_key in PROFILE_KEYS and _record_is_tombstoned(k, live_value, deleted_profiles):
                continue
            merged[k] = _clone(live_value)
        return merged

    def _guard_full_root_candidate(data, latest=None, source="full_root_save"):
        if not isinstance(data, dict):
            return data
        candidate = _clone(data)
        _scrub_local_only(candidate)
        latest = latest if isinstance(latest, dict) else {}
        deleted = {}
        try:
            if isinstance(latest.get("deletedProfiles"), dict):
                deleted.update(_clone(latest.get("deletedProfiles")) or {})
            if isinstance(candidate.get("deletedProfiles"), dict):
                deleted.update(_clone(candidate.get("deletedProfiles")) or {})
        except Exception:
            deleted = candidate.get("deletedProfiles") if isinstance(candidate.get("deletedProfiles"), dict) else {}
        if deleted:
            candidate["deletedProfiles"] = deleted

        ledger_delete_paths = _ledger_delete_paths_from(latest, candidate)
        applied_ledger_deletes = _apply_ledger_tombstones(candidate, ledger_delete_paths)
        if ledger_delete_paths:
            candidate["ledgerDeleteTombstones"] = {
                "version": "2026-07-09-ledger-delete-intent-guard-v8",
                "lastUpdatedAtMs": int(time.time() * 1000),
                "paths": sorted(ledger_delete_paths)[-700:],
            }

        protected_touched, blocked_shrinks = [], []
        for key in PROTECTED_ROOT_KEYS:
            if key not in latest:
                continue
            live_value = latest.get(key)
            cand_has = key in candidate
            cand_value = candidate.get(key)
            if not cand_has:
                if key in LEDGER_ROOT_KEYS and _path_deleted([key], ledger_delete_paths):
                    continue
                candidate[key] = _clone(live_value)
                protected_touched.append(key)
                continue
            if isinstance(live_value, dict) and isinstance(cand_value, dict):
                if key in LEDGER_ROOT_KEYS:
                    candidate[key] = _merge_protected_dict(key, cand_value, live_value, deleted, ledger_delete_paths, [key])
                elif _count(live_value) and _count(cand_value) == 0:
                    candidate[key] = _clone(live_value)
                    blocked_shrinks.append(key)
                else:
                    candidate[key] = _merge_protected_dict(key, cand_value, live_value, deleted, ledger_delete_paths, [key])
                    if _count(candidate[key]) > _count(cand_value):
                        protected_touched.append(key)
                continue
            if isinstance(live_value, list) and isinstance(cand_value, list):
                if key in LEDGER_ROOT_KEYS and _path_deleted([key], ledger_delete_paths):
                    continue
                if len(live_value) > len(cand_value):
                    candidate[key] = _clone(live_value)
                    blocked_shrinks.append(key)
                continue
            if live_value not in (None, {}, []) and cand_value in (None, {}, []):
                if key in LEDGER_ROOT_KEYS and _path_deleted([key], ledger_delete_paths):
                    continue
                candidate[key] = _clone(live_value)
                blocked_shrinks.append(key)

        meta = candidate.get("fullRootSaveGuard") if isinstance(candidate.get("fullRootSaveGuard"), dict) else {}
        meta.update({
            "version": "2026-07-09-ledger-delete-intent-guard-v8",
            "source": source,
            "lastGuardedAtMs": int(time.time() * 1000),
            "protectedTouched": sorted(set(protected_touched))[-40:],
            "blockedShrinks": sorted(set(blocked_shrinks))[-40:],
            "ledgerDeletePaths": sorted(ledger_delete_paths)[-120:],
            "appliedLedgerDeletes": applied_ledger_deletes[-120:],
        })
        candidate["fullRootSaveGuard"] = meta
        return candidate

    def _latest_state_for_guard():
        try:
            getter = G().get("migrate_and_get_state")
            if callable(getter):
                latest = getter()
                if isinstance(latest, dict):
                    return latest
        except Exception:
            pass
        try:
            getter = G().get("_firebase_get_child")
            if callable(getter):
                latest = getter([])
                if isinstance(latest, dict):
                    return latest
        except Exception:
            pass
        return {}

    def _install_full_root_save_guard():
        g = G()
        if g.get("_titan_full_root_save_guard_installed"):
            return
        g["_titan_full_root_save_guard_installed"] = True
        for name in ("save_to_firebase", "_firebase_guarded_root_save", "_safe_save_to_firebase_put"):
            original = g.get(name)
            if not callable(original) or getattr(original, "_titan_full_root_guard_wrapped", False):
                continue
            def make_wrapper(func, func_name):
                def wrapper(data, *args, **kwargs):
                    try:
                        guarded = _guard_full_root_candidate(data, _latest_state_for_guard(), func_name)
                    except Exception:
                        guarded = data
                    return func(guarded, *args, **kwargs)
                wrapper._titan_full_root_guard_wrapped = True
                return wrapper
            g[name] = make_wrapper(original, name)
        print("✅ Titan full-root stale overwrite + ledger delete-intent guard loaded")

    _install_full_root_save_guard()

    @app.route("/api/realtime/status", methods=["GET"])
    def titan_realtime_status():
        return jsonify({
            "status": "success",
            "feature": "titan_global_realtime_smooth",
            "version": "2026-07-09-ledger-delete-intent-guard-v8",
            "pollMs": 1800,
            "writeRefresh": True,
            "smoothMode": True,
            "localOnlyUiToggles": True,
            "firebaseBusinessDataOnly": True,
            "fullRootStaleOverwriteGuard": True,
            "ledgerDeleteIntentGuard": True,
            "protectedRootKeys": list(PROTECTED_ROOT_KEYS),
            "ledgerRootKeys": list(LEDGER_ROOT_KEYS),
            "checkedAt": int(time.time() * 1000),
        })

    @app.route("/api/realtime/full-root-guard/status", methods=["GET"])
    def titan_full_root_guard_status():
        return jsonify({
            "status": "ok",
            "feature": "full_root_stale_overwrite_guard",
            "version": "2026-07-09-ledger-delete-intent-guard-v8",
            "installed": bool(G().get("_titan_full_root_save_guard_installed")),
            "ledgerDeleteIntentGuard": True,
            "protectedRootKeys": list(PROTECTED_ROOT_KEYS),
            "ledgerRootKeys": list(LEDGER_ROOT_KEYS),
        })

    @app.after_request
    def titan_realtime_no_store(resp):
        try:
            path = request.path or ""
            if path.startswith("/api/") or path in ("/save", "/bot_schedule"):
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
        except Exception:
            pass
        return resp

    @app.after_request
    def titan_realtime_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-global-realtime-ledger-delete-intent-v8" in html or "</body>" not in html.lower():
                return resp
            idx = html.lower().rfind("</body>")
            html = html[:idx] + REALTIME_SCRIPT + html[idx:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


REALTIME_SCRIPT = r'''
<script id="titan-global-realtime-ledger-delete-intent-v8">
(function(){
  if(window.__TITAN_GLOBAL_REALTIME_SMOOTH_V8__) return;
  window.__TITAN_GLOBAL_REALTIME_SMOOTH_V8__ = true;
  const VERSION='2026-07-09-ledger-delete-intent-guard-v8';
  const POLL_MS=Math.max(900,Number(localStorage.getItem('TITAN_REALTIME_POLL_MS')||1800));
  const WRITE_REFRESH_DELAYS=[180,720], RENDER_DEBOUNCE_MS=160, INPUT_HOLD_MS=1800, SCROLL_HOLD_MS=900, TAB_HOLD_MS=9500;
  const LOCAL_UI_STORE='titan.local.ui.toggles.v1';
  const LEDGER_ROOT_KEYS=['ledger','ledgers','ledgerEntries','entries','entryBook','entryBooks','dailyLedger','marketLedger','ledgerCards','cardLedger','entryLedger'];
  let syncBusy=false,lastRaw='',lastAppliedAt=0,writeLockUntil=0,pausedUntil=0,interactionUntil=0,protectedHoldUntil=0,protectedHoldNav='',renderTimer=null,renderQueued=false,pendingRenderReason='';
  function now(){return Date.now()}
  function directEval(code){try{return Function(code)()}catch(e){return undefined}}
  const LOCAL_ONLY_KEY_RE=/(toggle|checkbox|uiOnly|ui_only|viewState|view_state|expanded|collapsed|selectedTab|activeTab|tabState|drawer|modal|panelOpen|panel_open|toast|filterText|searchText|sortBy|sort_by|themeTemp|tempUi|localUi|local_ui|stickyToggle|toggleSticky|resultToggleSticky|autoMark|onlyWait|allVips|msgSummary|settlementOn|autoHitMiss)/i;
  const BUSINESS_KEY_RE=/(ledger|payment|payments|deposit|deposits|withdraw|withdrawal|wallet|wallets|transaction|transactions|entry|entries|result|results|market|markets|profile|profiles|vipProfile|vipProfiles|userProfiles|vipUsers|customers|client|clients|schedule|schedules|target|targets|group|groups|audit|backup|settingsVersion|deletedProfiles|utr|upi|amount|balance|pass|fail|approval|expiry|access)/i;
  function isLocalOnlyKey(k){return LOCAL_ONLY_KEY_RE.test(String(k||''))&&!BUSINESS_KEY_RE.test(String(k||''))}
  function scrubLocalOnly(obj,depth){if(!obj||typeof obj!=='object'||depth>7)return obj;if(Array.isArray(obj)){obj.forEach(v=>scrubLocalOnly(v,depth+1));return obj}Object.keys(obj).forEach(k=>{if(isLocalOnlyKey(k)){try{delete obj[k]}catch(e){};return}scrubLocalOnly(obj[k],depth+1)});return obj}
  function loadLocalUi(){try{return JSON.parse(localStorage.getItem(LOCAL_UI_STORE)||'{}')||{}}catch(e){return {}}}
  function saveLocalUi(map){try{localStorage.setItem(LOCAL_UI_STORE,JSON.stringify(map||{}))}catch(e){}}
  function navName(){return String(directEval('return typeof mainNav !== "undefined" ? mainNav : ""')||'').toLowerCase()||'global'}
  function stableControlKey(el){try{const bits=[navName()];let label='';const id=el.id||el.getAttribute('id')||'';if(id)bits.push('id:'+id);const nm=el.name||el.getAttribute('name')||'';if(nm)bits.push('name:'+nm);const aria=el.getAttribute('aria-label')||el.getAttribute('title')||'';if(aria)bits.push('aria:'+aria);const wrap=el.closest&&el.closest('label,.switch,.toggle,.form-check,.control,.setting,.card,.row,li,div');if(wrap)label=String(wrap.innerText||wrap.textContent||'').replace(/\s+/g,' ').trim().slice(0,80);if(label)bits.push('text:'+label);if(bits.length<=1)bits.push('idx:'+Array.prototype.indexOf.call(document.querySelectorAll('input[type="checkbox"],input[type="radio"],[role="switch"]'),el));return bits.join('|').toLowerCase()}catch(e){return 'global|unknown'}}
  function shouldKeepLocal(el){try{if(!el)return false;const type=String(el.type||'').toLowerCase();const role=String(el.getAttribute&&el.getAttribute('role')||'').toLowerCase();if(!(type==='checkbox'||type==='radio'||role==='switch'))return false;const ctx=String((el.closest&&el.closest('.card,.row,.setting,.control,section,div')||document.body).innerText||'').toLowerCase();if(/app access|vip can use app|expiry|wallet|payment|ledger|entry|deposit|withdraw|balance|profile/.test(ctx))return false;return true}catch(e){return false}}
  function rememberLocalControl(el){try{if(!shouldKeepLocal(el))return;const map=loadLocalUi();map[stableControlKey(el)]={checked:!!el.checked,value:el.value,nav:navName(),at:now()};saveLocalUi(map)}catch(e){}}
  function applyLocalControls(){try{const map=loadLocalUi();document.querySelectorAll('input[type="checkbox"],input[type="radio"],[role="switch"]').forEach(el=>{if(!shouldKeepLocal(el))return;const rec=map[stableControlKey(el)];if(!rec)return;if(!!el.checked!==!!rec.checked){el.checked=!!rec.checked;try{el.dispatchEvent(new Event('change',{bubbles:true}))}catch(e){}}})}catch(e){}}
  function normalizePath(parts){return parts.map(x=>String(x).replace(/[/.]+/g,'_')).filter(Boolean).join('/')}
  function collectMissing(prev,next,path,out,depth){if(depth>5||!prev||typeof prev!=='object')return;if(next===undefined||next===null){out.add(normalizePath(path));return}if(Array.isArray(prev)){if(Array.isArray(next)&&next.length<prev.length)out.add(normalizePath(path));return}if(typeof next!=='object')return;Object.keys(prev).forEach(k=>{if(!(k in next))out.add(normalizePath(path.concat([k])));else collectMissing(prev[k],next[k],path.concat([k]),out,depth+1)})}
  function attachLedgerDeleteIntent(data){try{if(!data||typeof data!=='object'||!lastRaw)return data;const prev=JSON.parse(lastRaw);const paths=new Set();LEDGER_ROOT_KEYS.forEach(root=>{if(prev&&prev[root]!==undefined&&data[root]!==undefined)collectMissing(prev[root],data[root],[root],paths,0)});if(paths.size){const existing=data.ledgerDeleteTombstones&&Array.isArray(data.ledgerDeleteTombstones.paths)?data.ledgerDeleteTombstones.paths:[];existing.forEach(p=>paths.add(String(p||'')));data.ledgerDeleteTombstones={version:VERSION,lastUpdatedAtMs:now(),paths:Array.from(paths).filter(Boolean).slice(-700)}}catch(e){}return data}
  function directSet(nextState){try{const localMap=loadLocalUi();scrubLocalOnly(nextState,0);Function('nextState',`appState=nextState;try{if(typeof IS_MASTER!=='undefined'&&IS_MASTER)appState.activeId=appState.activeId||'admin1'}catch(e){}try{if(typeof refreshMarketArrays==='function')refreshMarketArrays()}catch(e){}try{if(typeof applyPendingLedgerPatchesToState==='function')applyPendingLedgerPatchesToState(appState)}catch(e){}try{state=appState.profiles[appState.activeId]||appState.profiles['admin1']}catch(e){}try{if(typeof LOCAL_KEY!=='undefined')localStorage.setItem(LOCAL_KEY,JSON.stringify(appState))}catch(e){}`)(nextState);saveLocalUi(localMap);setTimeout(applyLocalControls,30);return true}catch(e){return false}}
  function isMaster(){return directEval('return typeof IS_MASTER !== "undefined" ? !!IS_MASTER : true')!==false}
  function stateUrl(){const u=directEval('return typeof SERVER_STATE_URL !== "undefined" ? SERVER_STATE_URL : ""');if(u)return String(u);const aid=directEval('return appState && appState.activeId ? appState.activeId : ""')||'';return isMaster()?'/api/state':('/api/state?vip='+encodeURIComponent(aid))}
  function sep(url){return String(url).includes('?')?'&':'?'}
  function currentNav(){return String(directEval('return typeof mainNav !== "undefined" ? mainNav : ""')||'').toLowerCase()}
  function isProtectedNav(nav){nav=nav||currentNav();return nav==='entries'||nav==='forward'||nav==='finance'}
  function editing(){try{const el=document.activeElement;if(!el)return false;const tag=String(el.tagName||'').toUpperCase();return tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||el.isContentEditable}catch(e){return false}}
  function protectedPanelOpen(){const nav=currentNav();if(!isProtectedNav(nav))return false;return now()<protectedHoldUntil&&(!protectedHoldNav||protectedHoldNav===nav)}
  function shouldAvoidRender(force){if(protectedPanelOpen())return true;if(force&&isProtectedNav()&&now()<protectedHoldUntil)return true;if(force)return false;return document.hidden||editing()||now()<interactionUntil||now()<pausedUntil||now()<writeLockUntil}
  function protectedInteraction(){const nav=currentNav();if(isProtectedNav(nav)){protectedHoldNav=nav;protectedHoldUntil=Math.max(protectedHoldUntil,now()+TAB_HOLD_MS)}}
  ['touchstart','touchmove','wheel','scroll','pointerdown'].forEach(ev=>{try{window.addEventListener(ev,function(){interactionUntil=Math.max(interactionUntil,now()+SCROLL_HOLD_MS);protectedInteraction()},{passive:true,capture:true})}catch(e){}});
  ['click','change','input','focusin','keydown'].forEach(ev=>{try{document.addEventListener(ev,function(e){protectedInteraction();if(e&&e.target)rememberLocalControl(e.target)},true)}catch(e){}});
  document.addEventListener('input',()=>{interactionUntil=Math.max(interactionUntil,now()+INPUT_HOLD_MS)},true);
  function showStatus(text){try{let el=document.getElementById('titanRealtimeStatusDot');if(!el){el=document.createElement('div');el.id='titanRealtimeStatusDot';el.style.cssText='position:fixed;right:10px;bottom:78px;z-index:9999;background:rgba(0,194,111,.9);color:#062013;border-radius:999px;padding:5px 8px;font:900 9px Inter,Arial;box-shadow:0 4px 14px rgba(0,0,0,.22);pointer-events:none;opacity:0;transition:opacity .18s';document.body.appendChild(el)}el.textContent=text||'LIVE';el.style.opacity='1';clearTimeout(el._t);el._t=setTimeout(()=>{el.style.opacity='0'},520)}catch(e){}}
  function doRender(reason){renderQueued=false;renderTimer=null;if(protectedPanelOpen())return;try{if(typeof refreshMarketArrays==='function')refreshMarketArrays()}catch(e){}try{if(typeof render==='function')render(true)}catch(e){}setTimeout(applyLocalControls,30);try{document.dispatchEvent(new CustomEvent('titan:realtime-applied',{detail:{reason,at:now(),version:VERSION}}))}catch(e){}showStatus('LIVE')}
  function queueRender(reason,force){pendingRenderReason=reason||pendingRenderReason||'sync';if(shouldAvoidRender(force))return;if(renderQueued)return;renderQueued=true;clearTimeout(renderTimer);renderTimer=setTimeout(()=>{if(shouldAvoidRender(force)){renderQueued=false;return}if(window.requestAnimationFrame)requestAnimationFrame(()=>doRender(pendingRenderReason));else doRender(pendingRenderReason)},RENDER_DEBOUNCE_MS)}
  function markWrite(reason,holdMs){writeLockUntil=Math.max(writeLockUntil,now()+(holdMs||900));interactionUntil=Math.max(interactionUntil,now()+500);if(isProtectedNav()){protectedHoldNav=currentNav();protectedHoldUntil=Math.max(protectedHoldUntil,now()+Math.max(TAB_HOLD_MS,holdMs||0))}showStatus('SYNC')}
  async function fetchState(reason,force){if(syncBusy)return false;if(!force&&shouldAvoidRender(false))return false;syncBusy=true;try{const base=stateUrl();const url=base+sep(base)+'_rt='+now()+'&_fast=1&_smooth=1';const headers={'Cache-Control':'no-store'};try{const tok=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(tok)headers['X-Titan-Admin-Token']=tok}catch(e){}const res=await fetch(url,{cache:'no-store',headers});if(!res.ok)return false;const raw=await res.text();if(!raw||raw===lastRaw)return false;const next=JSON.parse(raw);if(!next||!next.profiles)return false;scrubLocalOnly(next,0);lastRaw=JSON.stringify(next);if(!directSet(next))return false;lastAppliedAt=now();queueRender(reason||'poll',!!force);return true}catch(e){return false}finally{syncBusy=false}}
  function scheduleAfterWrite(reason){markWrite(reason||'write',900);WRITE_REFRESH_DELAYS.forEach((d,i)=>setTimeout(()=>fetchState((reason||'write')+'_'+i,true),d))}
  const oldFetch=window.fetch;window.fetch=function titanRealtimeFetch(input,init){const method=String((init&&init.method)||'GET').toUpperCase();const url=String((typeof input==='string'?input:(input&&input.url))||'');try{if(init&&init.body&&method!=='GET'){const ct=String((init.headers&&(init.headers['Content-Type']||init.headers['content-type']))||'');if(ct.includes('json')||String(init.body).trim().startsWith('{')){let data=JSON.parse(String(init.body));data=attachLedgerDeleteIntent(data);init=Object.assign({},init,{body:JSON.stringify(scrubLocalOnly(data,0))})}}}catch(e){}const write=method!=='GET'&&(/\/api\//.test(url)||/\/save(\?|$)/.test(url)||/\/bot_schedule(\?|$)/.test(url));if(write)markWrite('fetch_'+method,1200);const p=oldFetch.apply(this,[input,init]);if(write){p.then(()=>scheduleAfterWrite('fetch_done_'+method)).catch(()=>setTimeout(()=>fetchState('fetch_error_'+method,true),650))}return p};
  try{const XHR=window.XMLHttpRequest;const oldOpen=XHR.prototype.open;const oldSend=XHR.prototype.send;XHR.prototype.open=function(method,url){this.__titanRtMethod=String(method||'GET').toUpperCase();this.__titanRtUrl=String(url||'');return oldOpen.apply(this,arguments)};XHR.prototype.send=function(body){try{if(body&&this.__titanRtMethod!=='GET'&&String(body).trim().startsWith('{')){let data=JSON.parse(String(body));data=attachLedgerDeleteIntent(data);body=JSON.stringify(scrubLocalOnly(data,0))}}catch(e){}const write=this.__titanRtMethod!=='GET'&&(/\/api\//.test(this.__titanRtUrl)||/\/save(\?|$)/.test(this.__titanRtUrl)||/\/bot_schedule(\?|$)/.test(this.__titanRtUrl));if(write){markWrite('xhr_'+this.__titanRtMethod,1200);this.addEventListener('loadend',()=>scheduleAfterWrite('xhr_done_'+this.__titanRtMethod))}return oldSend.call(this,body)}}catch(e){}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(()=>fetchState('visible',true),220)});window.addEventListener('focus',()=>setTimeout(()=>fetchState('focus',true),220));document.addEventListener('titan:force-sync',()=>fetchState('event',true));document.addEventListener('titan:apply-local-ui',applyLocalControls);
  window.__TitanRealtime={version:VERSION,refresh:(r)=>fetchState(r||'manual',true),markWrite,applyLocalControls,scrubLocalOnly,pause:(ms)=>{pausedUntil=now()+Number(ms||1000)},pauseEntries:(ms)=>{protectedHoldNav='entries';protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)},pauseForward:(ms)=>{protectedHoldNav='forward';protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)},pauseFinance:(ms)=>{protectedHoldNav='finance';protectedHoldUntil=now()+Number(ms||TAB_HOLD_MS)},status:()=>({lastAppliedAt,syncBusy,writeLockUntil,interactionUntil,protectedHoldUntil,protectedHoldNav,pollMs:POLL_MS,localOnlyUiToggles:true,fullRootStaleOverwriteGuard:true,ledgerDeleteIntentGuard:true})};
  setInterval(()=>fetchState('poll',false),POLL_MS);setInterval(applyLocalControls,1500);setTimeout(()=>fetchState('boot',true),850);setTimeout(applyLocalControls,900);console.log('✅ Titan Global Realtime Smooth active',VERSION,'ledger-delete-intent');
})();
</script>
'''
