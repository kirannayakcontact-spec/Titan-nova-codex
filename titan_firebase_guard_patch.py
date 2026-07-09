"""Titan Nova Firebase reliability guard.

Loaded after the legacy Flask app.  It normalizes the Firebase URL, adds retrying
Firebase HTTP helpers, avoids blank dashboards by serving last-known-good state
when Firebase is temporarily unreadable, and keeps full-root saves behind the
existing protected merge/data-loss guard.
"""


def register_titan_firebase_guard(app):
    if getattr(app, "_titan_firebase_guard_registered", False):
        return
    app._titan_firebase_guard_registered = True

    from flask import jsonify
    import copy
    import datetime
    import json
    import os
    import time
    import requests
    from urllib.parse import quote

    VERSION = "2026-07-09-firebase-guard-v1"
    LIVE_DEFAULT = "https://odisha-17fa5-default-rtdb.firebaseio.com/titan_master_data.json"
    RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
    MAX_RETRIES = max(1, int(os.environ.get("TITAN_FIREBASE_HTTP_RETRIES", "3") or "3"))
    CONNECT_TIMEOUT = float(os.environ.get("TITAN_FIREBASE_CONNECT_TIMEOUT", "4") or "4")
    READ_TIMEOUT = float(os.environ.get("TITAN_FIREBASE_READ_TIMEOUT", "14") or "14")
    FALLBACK_LAST_GOOD = str(os.environ.get("TITAN_FIREBASE_FALLBACK_LAST_GOOD", "1")).strip().lower() not in ("0", "false", "no", "off")

    last_request = {"status": "boot", "version": VERSION}

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for v in app.view_functions.values():
                g = getattr(v, "__globals__", {}) or {}
                if "get_firebase_url" in g or "load_from_firebase" in g:
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
        try:
            fn = G().get("_now_iso_local")
            if callable(fn):
                return fn()
        except Exception:
            pass
        return datetime.datetime.now().isoformat(timespec="seconds")

    def obs(kind, severity="info", message="", detail=None):
        rec = {"kind": kind, "severity": severity, "message": str(message or "")[:500], "detail": detail or {}, "version": VERSION, "time": now_iso()}
        try:
            fn = G().get("_obs_event")
            if callable(fn):
                fn(kind, severity, message, detail or {}, source="firebase_guard", persist_firebase=False)
        except Exception:
            pass
        try:
            print(("❌" if severity in ("error", "critical") else "⚠️" if severity == "warning" else "✅"), "Titan Firebase Guard:", rec["message"])
        except Exception:
            pass
        return rec

    def normalize_firebase_url(raw=None):
        url = str(raw or os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL") or G().get("FIREBASE_DB_URL") or LIVE_DEFAULT).strip()
        url = url.split("?", 1)[0].strip().rstrip("/")
        if not (url.startswith("https://") or url.startswith("http://")):
            url = LIVE_DEFAULT
        if url.endswith(".json"):
            return url
        if url.endswith("/titan_master_data"):
            return url + ".json"
        return url + "/titan_master_data.json"

    def apply_url_fix():
        g = G()
        fixed = normalize_firebase_url()
        os.environ["FIREBASE_URL"] = fixed
        os.environ["FIREBASE_DB_URL"] = fixed
        g["FIREBASE_DB_URL"] = fixed
        return fixed

    def get_firebase_url_patched():
        return apply_url_fix()

    def no_cache_headers(extra=None):
        h = {"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"}
        if extra:
            h.update(extra)
        return h

    def request_firebase(method, url, **kwargs):
        method = str(method or "GET").upper()
        headers = no_cache_headers(kwargs.pop("headers", None))
        kwargs["headers"] = headers
        kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
        last_exc = None
        for attempt in range(MAX_RETRIES):
            started = time.time()
            try:
                res = requests.request(method, url, **kwargs)
                ms = int((time.time() - started) * 1000)
                last_request.update({"status": "success" if res.status_code < 400 else "http_error", "method": method, "httpStatus": res.status_code, "ms": ms, "attempt": attempt + 1, "urlTail": url[-90:], "checkedAt": now_iso()})
                if res.status_code in RETRY_CODES and attempt + 1 < MAX_RETRIES:
                    obs("firebase_retry_http", "warning", f"Firebase {method} HTTP {res.status_code}; retrying", {"attempt": attempt + 1, "ms": ms, "urlTail": url[-90:]})
                    time.sleep(0.18 * (attempt + 1))
                    continue
                return res
            except Exception as exc:
                last_exc = exc
                last_request.update({"status": "exception", "method": method, "message": str(exc)[:240], "attempt": attempt + 1, "urlTail": url[-90:], "checkedAt": now_iso()})
                if attempt + 1 < MAX_RETRIES:
                    obs("firebase_retry_exception", "warning", f"Firebase {method} exception; retrying: {exc}", {"attempt": attempt + 1, "urlTail": url[-90:]})
                    time.sleep(0.22 * (attempt + 1))
                    continue
                break
        raise last_exc or RuntimeError("Firebase request failed")

    def child_url(*parts):
        root = get_firebase_url_patched()
        base = root[:-5] if root.endswith(".json") else root.rstrip("/")
        clean = [quote(str(p), safe="") for p in parts if str(p) != ""]
        return root if not clean else base + "/" + "/".join(clean) + ".json"

    def cache_apply(parts, value=None, mode="put"):
        try:
            fn = G().get("_rt_cache_apply_child")
            if callable(fn):
                fn(parts, value, mode)
        except Exception:
            try:
                fn = G().get("_rt_cache_clear")
                if callable(fn):
                    fn("firebase_guard_cache_apply_error")
            except Exception:
                pass

    def cache_set(data, source="firebase_guard"):
        try:
            fn = G().get("_rt_cache_set")
            if callable(fn):
                fn(data, source)
        except Exception:
            pass

    def cache_get(force=False):
        try:
            fn = G().get("_rt_cache_get")
            if callable(fn):
                return fn(force=force)
        except Exception:
            pass
        return None

    def read_last_known_good():
        if not FALLBACK_LAST_GOOD:
            return None
        path = str(G().get("LAST_KNOWN_GOOD_FILE") or "")
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            state = payload.get("state") if isinstance(payload, dict) else payload
            if isinstance(state, dict) and state:
                state = clone(state)
                state.setdefault("firebaseFallbackMeta", {})
                state["firebaseFallbackMeta"].update({"source": "last_known_good", "usedAt": now_iso(), "version": VERSION})
                obs("firebase_last_good_used", "warning", "Firebase unreadable; serving last-known-good backup for UI continuity", {"file": os.path.basename(path)})
                return state
        except Exception as exc:
            obs("firebase_last_good_read_failed", "warning", str(exc), {})
        return None

    def fetch_root_json(timeout=None, etag=False):
        headers = {"X-Firebase-ETag": "true"} if etag else None
        res = request_firebase("GET", get_firebase_url_patched(), headers=headers, timeout=timeout or (CONNECT_TIMEOUT, READ_TIMEOUT))
        if res.status_code >= 400:
            raise RuntimeError(f"Firebase GET HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
        try:
            data = res.json() if getattr(res, "text", "") else None
        except Exception as exc:
            raise RuntimeError(f"Firebase JSON parse failed: {exc}")
        if not isinstance(data, dict):
            data = {}
        return (data, res.headers.get("ETag") or res.headers.get("etag") or "*") if etag else data

    def load_from_firebase_patched():
        g = G()
        meta_name = "FIREBASE_LAST_LOAD_META"
        try:
            cached = cache_get(force=False)
            if cached is not None:
                g[meta_name] = {"status": "cache", "message": "served from firebase guard/realtime cache", "version": VERSION}
                return cached
            started = time.time()
            data = fetch_root_json()
            ms = int((time.time() - started) * 1000)
            if isinstance(data, dict) and data:
                data.setdefault("firebaseGuardMeta", {})
                data["firebaseGuardMeta"].update({"lastLoadAt": now_iso(), "version": VERSION, "ms": ms})
                cache_set(data, "firebase_guard_load")
                g[meta_name] = {"status": "success", "httpStatus": 200, "ms": ms, "message": "loaded by Firebase guard", "version": VERSION}
                return data
            g[meta_name] = {"status": "empty", "message": "Firebase root empty", "ms": ms, "version": VERSION}
            fallback = read_last_known_good()
            if fallback is not None:
                g[meta_name] = {"status": "fallback_last_good", "message": "Firebase empty; using last-known-good backup", "ms": ms, "version": VERSION}
                cache_set(fallback, "firebase_guard_last_good")
                return fallback
            return None
        except Exception as exc:
            g[meta_name] = {"status": "exception", "message": str(exc)[:240], "version": VERSION}
            obs("firebase_load_guard_exception", "error", str(exc), {})
            fallback = read_last_known_good()
            if fallback is not None:
                cache_set(fallback, "firebase_guard_last_good_exception")
                return fallback
            return None

    def put_child(parts, value, timeout=12):
        res = request_firebase("PUT", child_url(*(parts or [])), json=value, timeout=timeout)
        if res.status_code >= 400:
            raise RuntimeError(f"Firebase child PUT HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
        cache_apply(parts or [], value, "put")
        return True

    def patch_child(parts, value, timeout=12):
        res = request_firebase("PATCH", child_url(*(parts or [])), json=value, timeout=timeout)
        if res.status_code >= 400:
            raise RuntimeError(f"Firebase child PATCH HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
        cache_apply(parts or [], value, "patch")
        return True

    def delete_child(parts, timeout=12):
        res = request_firebase("DELETE", child_url(*(parts or [])), timeout=timeout)
        if res.status_code >= 400:
            raise RuntimeError(f"Firebase child DELETE HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
        cache_apply(parts or [], None, "delete")
        return True

    def get_child(parts, timeout=12):
        res = request_firebase("GET", child_url(*(parts or [])), timeout=timeout)
        if res.status_code >= 400:
            raise RuntimeError(f"Firebase child GET HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
        try:
            return res.json() if getattr(res, "text", "") else None
        except Exception:
            return None

    def fetch_root_with_etag_guarded(timeout=14):
        started = time.time()
        data, etag = fetch_root_json(timeout=(CONNECT_TIMEOUT, timeout), etag=True)
        return data, etag, int((time.time() - started) * 1000)

    def get_root_with_etag(timeout=12):
        return fetch_root_json(timeout=(CONNECT_TIMEOUT, timeout), etag=True)

    def guarded_root_save(data, backup_label="firebase_guard_save"):
        if not isinstance(data, dict):
            return False
        g = G()
        last_error = None
        for attempt in range(max(MAX_RETRIES, 3)):
            try:
                latest, etag, read_ms = fetch_root_with_etag_guarded(timeout=14)
                candidate = clone(data)
                try:
                    fn = g.get("_ensure_foundation_state")
                    if callable(fn):
                        fn(candidate)
                        if latest:
                            fn(latest)
                except Exception as exc:
                    obs("firebase_foundation_warning", "warning", str(exc), {"attempt": attempt})
                try:
                    fn = g.get("_firebase_merge_protected_source_of_truth")
                    if callable(fn):
                        candidate = fn(candidate, latest, backup_label) or candidate
                except Exception as exc:
                    obs("firebase_protected_merge_warning", "warning", str(exc), {"attempt": attempt})
                try:
                    val = g.get("_runtime_state_validation_report")
                    loss = g.get("_firebase_data_loss_guard")
                    runtime_report = val(candidate, latest) if callable(val) else {"ok": True}
                    loss_report = loss(candidate, latest, backup_label) if callable(loss) else {"ok": True}
                    if not runtime_report.get("ok") or not loss_report.get("ok"):
                        obs("firebase_guard_blocked_risky_root_save", "critical", "Risky Firebase root save blocked", {"runtime": runtime_report, "lossGuard": loss_report, "label": backup_label})
                        return False
                except Exception as exc:
                    obs("firebase_validation_warning", "warning", str(exc), {"attempt": attempt})
                try:
                    wb = g.get("_write_state_backup")
                    if callable(wb) and latest:
                        wb(latest, backup_label or "before_firebase_guard_save")
                except Exception:
                    pass
                started = time.time()
                res = request_firebase("PUT", get_firebase_url_patched(), json=candidate, headers={"if-match": etag or "*"}, timeout=(CONNECT_TIMEOUT, 18))
                write_ms = int((time.time() - started) * 1000)
                if res.status_code == 412:
                    obs("firebase_cas_conflict_retry", "warning", "Firebase CAS conflict; retrying", {"attempt": attempt + 1, "readMs": read_ms, "writeMs": write_ms})
                    time.sleep(0.14 * (attempt + 1))
                    continue
                if res.status_code >= 400:
                    raise RuntimeError(f"Firebase PUT HTTP {res.status_code}: {getattr(res, 'text', '')[:220]}")
                try:
                    wb = g.get("_write_state_backup")
                    if callable(wb):
                        wb(candidate, "last_known_good")
                except Exception:
                    pass
                cache_set(candidate, "firebase_guard_root_save")
                obs("firebase_guard_root_save_ok", "info", "Firebase guarded root save committed", {"attempt": attempt + 1, "readMs": read_ms, "writeMs": write_ms})
                return candidate
            except Exception as exc:
                last_error = exc
                obs("firebase_guard_root_save_error", "error", str(exc), {"attempt": attempt + 1, "label": backup_label})
                time.sleep(0.16 * (attempt + 1))
        print("Firebase guard save failed:", last_error)
        return False

    def safe_save_to_firebase_put(data):
        # Redirect legacy direct root PUT into guarded CAS save.
        return guarded_root_save(data, "legacy_safe_put_redirected")

    fixed_url = apply_url_fix()
    g = G()
    g["get_firebase_url"] = get_firebase_url_patched
    g["load_from_firebase"] = load_from_firebase_patched
    g["_firebase_child_url"] = child_url
    g["_firebase_put_child"] = put_child
    g["_firebase_patch_child"] = patch_child
    g["_firebase_delete_child"] = delete_child
    g["_firebase_get_child"] = get_child
    g["_firebase_fetch_root_with_etag_guarded"] = fetch_root_with_etag_guarded
    g["_firebase_get_root_with_etag"] = get_root_with_etag
    g["_firebase_guarded_root_save"] = guarded_root_save
    g["_safe_save_to_firebase_put"] = safe_save_to_firebase_put

    @app.route("/api/firebase_guard/status", methods=["GET"])
    def firebase_guard_status():
        g = G()
        return jsonify({
            "status": "success",
            "version": VERSION,
            "urlTail": get_firebase_url_patched()[-90:],
            "lastRequest": last_request,
            "fallbackLastGoodEnabled": FALLBACK_LAST_GOOD,
            "maxRetries": MAX_RETRIES,
            "timeouts": {"connect": CONNECT_TIMEOUT, "read": READ_TIMEOUT},
            "legacyLastLoadMeta": g.get("FIREBASE_LAST_LOAD_META", {}),
            "patchedFunctions": [k for k in ("get_firebase_url", "load_from_firebase", "_firebase_put_child", "_firebase_guarded_root_save", "_safe_save_to_firebase_put") if callable(g.get(k))]
        })

    @app.route("/api/firebase_guard/ping", methods=["GET"])
    def firebase_guard_ping():
        started = time.time()
        try:
            data = fetch_root_json(timeout=(CONNECT_TIMEOUT, 10))
            summary = {"type": type(data).__name__, "topLevelKeys": sorted(list(data.keys()))[:40] if isinstance(data, dict) else [], "topLevelCount": len(data) if isinstance(data, dict) else 0}
            return jsonify({"status": "success", "version": VERSION, "ms": int((time.time() - started) * 1000), "urlTail": get_firebase_url_patched()[-90:], "summary": summary})
        except Exception as exc:
            return jsonify({"status": "error", "version": VERSION, "message": str(exc), "ms": int((time.time() - started) * 1000), "urlTail": get_firebase_url_patched()[-90:]}), 502

    obs("firebase_guard_loaded", "info", f"Firebase guard loaded {VERSION}", {"urlTail": fixed_url[-90:]})
