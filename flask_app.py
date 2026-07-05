# ==========================================================
# TWO FILE EDITION
# Python deps: pip install flask requests
# Run UI/API: python flask_app.py
# Node Gateway is controlled over localhost endpoints from this file.
# ==========================================================

# ==========================================================
# FIREBASE ONLY STORAGE EDITION
# Local JSON storage removed
# ==========================================================

from flask import Flask, render_template_string, request, jsonify, make_response, redirect, has_request_context
import json
import os
import uuid
import datetime
import io
import csv
import zipfile
import re
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
import requests
import hmac
import secrets
import time
import hashlib
import traceback

app = Flask(__name__)
app.secret_key = os.environ.get("TITAN_FLASK_SECRET", os.environ.get("TITAN_ADMIN_TOKEN", secrets.token_hex(24)))

# ==========================================================
# SECURITY LOCKDOWN v8: token-gated admin/Gateway controls
# ==========================================================
SECURITY_LOCKDOWN_VERSION = "2026-07-02-security-lockdown-v8"
MONEY_ATOMICITY_VERSION = "2026-07-02-money-atomicity-v9"
CONFIG_CLEANUP_VERSION = "2026-07-02-config-cleanup-v11"
OBSERVABILITY_VERSION = "2026-07-02-observability-v12"
WHATSAPP_RELIABILITY_VERSION = "2026-07-02-whatsapp-reliability-dashboard-v19"
WALLET_STATEMENT_VERSION = "2026-07-02-wallet-statement-passbook-v20"
PAYMENT_VERIFICATION_VERSION = "2026-07-02-payment-verification-panel-v21"
WITHDRAWAL_RISK_VERSION = "2026-07-03-withdrawal-risk-guard-v22"
LEDGER_PRO_VERSION = "2026-07-03-ledger-pro-dashboard-v24"
LEDGER_CARD_COLOR_VERSION = "v34.1-ledger-full-card-colors"
LEDGER_BASE_SYNC_VERSION = "v41-base-file-manual-overwrite"
UI_CONSOLIDATION_VERSION = "2026-07-03-ui-consolidation-v25"
MARKET_CORE_VERSION = "2026-07-03-market-direct-add-v29"
MARKET_DIRECT_ADD_VERSION = "2026-07-03-market-direct-add-v29"
MARKET_ENTRY_TARGET_VERSION = "2026-07-03-market-entry-target-v30"
WHATSAPP_ROLE_ROUTING_VERSION = "2026-07-03-whatsapp-role-routing-v32"
BOOKIE_ADMIN_ROUTING_VERSION = "2026-07-03-bookie-admin-group-routing-v35"
FIREBASE_DATA_GUARD_VERSION = "2026-07-03-base-file-manual-overwrite-v41"
REALTIME_SYNC_VERSION = "2026-07-03-base-file-manual-overwrite-sync-v41"
RUNTIME_STABILITY_VERSION = "2026-07-05-runtime-stability-patch-v44"
DEPLOY_SAFETY_VERSION = "2026-07-02-deploy-safety-v13"
UI_POLISH_VERSION = "2026-07-02-admin-mobile-ui-v14"
USER_SAFETY_VERSION = "2026-07-02-user-vip-account-safety-v15"
SMART_COMMAND_VERSION = "2026-07-02-smart-whatsapp-commands-v16"
DATA_CLEANUP_VERSION = "2026-07-02-firebase-data-cleanup-v17"
TITAN_VIP_DEVICE_LIMIT = int(os.environ.get("TITAN_VIP_DEVICE_LIMIT", "3") or "3")
TITAN_VIP_DEVICE_STRICT = str(os.environ.get("TITAN_VIP_DEVICE_STRICT", "0")).strip().lower() in ("1", "true", "yes", "on")
TITAN_VIP_ACCESS_ENFORCE = str(os.environ.get("TITAN_VIP_ACCESS_ENFORCE", "1")).strip().lower() not in ("0", "false", "no", "off")
TITAN_VIP_ACCESS_LOG_THROTTLE_SECONDS = int(os.environ.get("TITAN_VIP_ACCESS_LOG_THROTTLE_SECONDS", "300") or "300")
TITAN_ADMIN_TOKEN = os.environ.get("TITAN_ADMIN_TOKEN", "").strip()
TITAN_GATEWAY_TOKEN = os.environ.get("TITAN_GATEWAY_TOKEN", TITAN_ADMIN_TOKEN).strip()
TITAN_SECURITY_DISABLED = str(os.environ.get("TITAN_SECURITY_DISABLED", "0")).strip().lower() in ("1", "true", "yes", "on")
TITAN_ENV = str(os.environ.get("TITAN_ENV", os.environ.get("FLASK_ENV", ""))).strip().lower()
TITAN_PRODUCTION_MODE = TITAN_ENV in ("prod", "production")
TITAN_SECURITY_MISCONFIGURED = TITAN_PRODUCTION_MODE and (not TITAN_ADMIN_TOKEN or TITAN_SECURITY_DISABLED)
TITAN_SECURITY_STRICT = bool(TITAN_ADMIN_TOKEN) and not TITAN_SECURITY_DISABLED
TITAN_COOKIE_SECURE = str(os.environ.get("TITAN_COOKIE_SECURE", "0")).strip().lower() in ("1", "true", "yes", "on")
TITAN_ALLOW_QUERY_TOKEN = str(os.environ.get("TITAN_ALLOW_QUERY_TOKEN", "0")).strip().lower() in ("1", "true", "yes", "on")
FIREBASE_LAST_LOAD_META = {"status": "unchecked", "message": "not loaded yet"}

@app.after_request
def titan_no_store_realtime_api(resp):
    try:
        p = request.path or ""
        if p.startswith("/api/") or p == "/save" or p == "/bot_schedule":
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp

# v38 Real-Time Stability Lock: shorter cache + no-store API headers.
# v37 Real-Time Fast Sync: Firebase reads are cached for a very short window.
# Writes update/clear this cache immediately, so UI refreshes stop waiting on repeated
# full Firebase GETs while protected child writes still remain the source of truth.
REALTIME_FAST_SYNC_ENABLED = str(os.environ.get("TITAN_REALTIME_FAST_SYNC", "1")).strip().lower() not in ("0", "false", "no", "off")
REALTIME_STATE_CACHE_TTL_MS = max(0, int(os.environ.get("TITAN_STATE_CACHE_TTL_MS", "250") or "250"))
FIREBASE_STATE_CACHE = None
FIREBASE_STATE_CACHE_AT_MS = 0
FIREBASE_STATE_CACHE_SOURCE = "empty"

def _rt_ms():
    return int(time.time() * 1000)

def _rt_clone(obj):
    try:
        return json.loads(json.dumps(obj))
    except Exception:
        return obj

def _rt_cache_get(force=False):
    global FIREBASE_STATE_CACHE, FIREBASE_STATE_CACHE_AT_MS
    if force or not REALTIME_FAST_SYNC_ENABLED or not isinstance(FIREBASE_STATE_CACHE, dict):
        return None
    if REALTIME_STATE_CACHE_TTL_MS <= 0:
        return None
    if (_rt_ms() - int(FIREBASE_STATE_CACHE_AT_MS or 0)) <= REALTIME_STATE_CACHE_TTL_MS:
        return _rt_clone(FIREBASE_STATE_CACHE)
    return None

def _rt_cache_set(data, source='unknown'):
    global FIREBASE_STATE_CACHE, FIREBASE_STATE_CACHE_AT_MS, FIREBASE_STATE_CACHE_SOURCE
    if not REALTIME_FAST_SYNC_ENABLED or not isinstance(data, dict):
        return
    FIREBASE_STATE_CACHE = _rt_clone(data)
    FIREBASE_STATE_CACHE_AT_MS = _rt_ms()
    FIREBASE_STATE_CACHE_SOURCE = source or 'unknown'

def _rt_cache_clear(source='clear'):
    global FIREBASE_STATE_CACHE, FIREBASE_STATE_CACHE_AT_MS, FIREBASE_STATE_CACHE_SOURCE
    FIREBASE_STATE_CACHE = None
    FIREBASE_STATE_CACHE_AT_MS = 0
    FIREBASE_STATE_CACHE_SOURCE = source or 'clear'

def _rt_cache_apply_child(parts, value=None, mode='put'):
    global FIREBASE_STATE_CACHE, FIREBASE_STATE_CACHE_AT_MS, FIREBASE_STATE_CACHE_SOURCE
    if not REALTIME_FAST_SYNC_ENABLED or not isinstance(FIREBASE_STATE_CACHE, dict):
        return
    try:
        keys = [str(x) for x in (parts or []) if str(x) != '']
        if not keys:
            if mode in ('put','patch') and isinstance(value, dict):
                if mode == 'put': FIREBASE_STATE_CACHE = _rt_clone(value)
                else: FIREBASE_STATE_CACHE.update(_rt_clone(value))
            elif mode == 'delete':
                _rt_cache_clear('child_delete_root')
                return
        else:
            cur = FIREBASE_STATE_CACHE
            for k in keys[:-1]:
                if not isinstance(cur.get(k), dict): cur[k] = {}
                cur = cur[k]
            last = keys[-1]
            if mode == 'delete':
                if isinstance(cur, dict): cur.pop(last, None)
            elif mode == 'patch':
                if isinstance(value, dict) and isinstance(cur.get(last), dict): cur[last].update(_rt_clone(value))
                else: cur[last] = _rt_clone(value)
            else:
                cur[last] = _rt_clone(value)
        FIREBASE_STATE_CACHE_AT_MS = _rt_ms()
        FIREBASE_STATE_CACHE_SOURCE = 'child_' + str(mode)
    except Exception:
        _rt_cache_clear('child_apply_error')

PUBLIC_SECURITY_PATHS = {
    "/api/security_status", "/api/admin_login", "/api/admin_logout",
    "/sw.js", "/icon.svg", "/manifest.json"
}
PUBLIC_CLIENT_API_PATHS = {
    "/api/submit_payment",     # VIP/client payment upload must remain public, validated separately.
    "/api/scrape_market",      # Read-only market scrape used by client screen.
    "/api/upload_image",       # Public VIP payment screenshot upload proxy; key stays server-side.
}


def _constant_time_equal(a, b):
    try:
        return hmac.compare_digest(str(a or ""), str(b or ""))
    except Exception:
        return False


def _request_token():
    auth = str(request.headers.get("Authorization") or "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = (
        request.headers.get("X-Titan-Admin-Token")
        or request.headers.get("X-Titan-Gateway-Token")
        or request.cookies.get("titan_admin_token")
        or ""
    )
    if not token and TITAN_ALLOW_QUERY_TOKEN:
        # Query-string tokens leak through browser history, access logs and referrers;
        # keep them off by default and allow only for explicit legacy deployments.
        token = request.args.get("admin_token") or request.args.get("token") or ""
    return str(token).strip()


def _admin_authorized():
    if not TITAN_SECURITY_STRICT:
        return True
    return _constant_time_equal(_request_token(), TITAN_ADMIN_TOKEN)


def _gateway_headers():
    headers = {}
    if TITAN_GATEWAY_TOKEN:
        headers["X-Titan-Gateway-Token"] = TITAN_GATEWAY_TOKEN
    elif TITAN_ADMIN_TOKEN:
        headers["X-Titan-Admin-Token"] = TITAN_ADMIN_TOKEN
    return headers

def _gateway_url(path=""):
    path = str(path or "")
    if not path.startswith("/"):
        path = "/" + path
    return GATEWAY_URL + path

def _gateway_request(method, path, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.update(_gateway_headers())
    kwargs["headers"] = headers
    return requests.request(str(method or "GET").upper(), _gateway_url(path), **kwargs)

def _startup_config_warnings():
    warnings = []
    if not (os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL")):
        warnings.append("FIREBASE_URL/FIREBASE_DB_URL is missing; using local compatibility default Firebase URL.")
    if not TITAN_ADMIN_TOKEN:
        warnings.append("TITAN_ADMIN_TOKEN is missing; admin security is compatibility-open.")
    if not os.environ.get("TITAN_GATEWAY_TOKEN"):
        warnings.append("TITAN_GATEWAY_TOKEN is missing; Gateway proxy calls will fall back to TITAN_ADMIN_TOKEN when available.")
    if re.search(r"https?://(127\.0\.0\.1|localhost)(:|/|$)", GATEWAY_URL, re.I):
        warnings.append("GATEWAY_URL is using localhost; this is OK for local Termux but not for split-host deployments.")
    for msg in warnings:
        print("⚠️ TITAN CONFIG WARNING:", msg)
    return warnings


def _json_auth_required():
    return jsonify({
        "status": "auth_required",
        "message": "Admin token required. Login again or set TITAN_ADMIN_TOKEN correctly.",
        "securityLockdown": True,
        "version": SECURITY_LOCKDOWN_VERSION
    }), 401


def admin_required(fn):
    """Compatibility admin guard for late-added routes.
    The global before_request security gate still protects /api routes;
    this decorator prevents startup crashes and enforces the same token check
    if it is used on any standalone admin route.
    """
    from functools import wraps
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        if not _admin_authorized():
            return _json_auth_required()
        return fn(*args, **kwargs)
    return _wrapped


def _admin_login_page():
    return """
<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Titan Admin Login</title>
<style>body{margin:0;background:#17212B;color:#fff;font-family:Inter,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:22px}.box{width:100%;max-width:420px;background:#232E3C;border:1px solid rgba(42,171,238,.25);border-radius:20px;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.35)}input{width:100%;box-sizing:border-box;background:#17212B;border:1px solid #374F65;color:#fff;border-radius:14px;padding:15px;font-size:16px;outline:none}button{width:100%;margin-top:14px;background:#2AABEE;border:0;color:#fff;border-radius:14px;padding:15px;font-weight:900;text-transform:uppercase}p{color:#7A9CB8;font-size:13px;line-height:1.45}.err{color:#FF5D5D;font-size:12px;margin-top:10px;min-height:16px}</style></head>
<body><div class=\"box\"><h2 style=\"margin:0 0 8px;font-weight:900\">TITAN NOVA Admin Lock</h2><p>Security Lockdown v8 active hai. Admin dashboard open karne ke liye server ka <b>TITAN_ADMIN_TOKEN</b> enter karo.</p><input id=\"tok\" type=\"password\" placeholder=\"Admin token\" autocomplete=\"current-password\"><button onclick=\"login()\">Unlock Admin</button><div class=\"err\" id=\"err\"></div></div>
<script>
async function login(){
 const token=document.getElementById('tok').value.trim();
 const err=document.getElementById('err'); err.textContent='';
 try{
  const r=await fetch('/api/admin_login',{method:'POST',headers:{'Content-Type':'application/json','X-Titan-Admin-Token':token},body:JSON.stringify({token})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){err.textContent=j.message||'Token wrong hai';return;}
  localStorage.setItem('TITAN_ADMIN_TOKEN', token);
  location.href='/';
 }catch(e){err.textContent='Login failed: '+e.message;}
}
document.getElementById('tok').addEventListener('keydown',e=>{if(e.key==='Enter')login();});
</script></body></html>"""


@app.before_request
def _security_lockdown_before_request():
    if request.method == "OPTIONS":
        return None
    path = request.path or "/"
    if TITAN_SECURITY_MISCONFIGURED and path not in PUBLIC_SECURITY_PATHS:
        return jsonify({
            "status": "security_misconfigured",
            "message": "Production mode requires TITAN_ADMIN_TOKEN and enabled security.",
            "securityLockdown": True,
            "version": SECURITY_LOCKDOWN_VERSION
        }), 503
    if path in PUBLIC_SECURITY_PATHS or path.startswith('/static/'):
        return None
    if not TITAN_SECURITY_STRICT:
        return None
    # Public VIP page remains accessible. Master dashboard is locked.
    if path == "/" and request.args.get("vip"):
        return None
    if path.startswith("/observability"):
        if not _admin_authorized():
            return make_response(_admin_login_page(), 401)
        return None
    if path == "/":
        if not _admin_authorized():
            return make_response(_admin_login_page(), 401)
        return None
    # Allow VIP isolated state only; full /api/state remains admin-only.
    if path == "/api/state" and request.args.get("vip"):
        return None
    if path in ("/api/wallet_statement", "/api/wallet_statement_csv") and request.args.get("vip"):
        return None
    if path in PUBLIC_CLIENT_API_PATHS:
        return None
    # Everything else under /api, /save and direct bot schedule aliases is admin-only.
    if path.startswith("/api/") or path in ("/save", "/bot_schedule"):
        if not _admin_authorized():
            return _json_auth_required()
    return None


@app.route('/api/security_status')
def api_security_status():
    return jsonify({
        "status": "success",
        "securityLockdown": True,
        "version": SECURITY_LOCKDOWN_VERSION,
        "adminTokenConfigured": bool(TITAN_ADMIN_TOKEN),
        "enforced": bool(TITAN_SECURITY_STRICT),
        "gatewayTokenConfigured": bool(TITAN_GATEWAY_TOKEN),
        "currentRequestAuthorized": bool(_admin_authorized()),
        "publicClientApis": sorted(PUBLIC_CLIENT_API_PATHS),
        "configCleanupVersion": CONFIG_CLEANUP_VERSION,
        "observabilityVersion": OBSERVABILITY_VERSION,
        "deploySafetyVersion": DEPLOY_SAFETY_VERSION,
        "uiPolishVersion": UI_POLISH_VERSION,
        "userSafetyVersion": USER_SAFETY_VERSION,
        "dataCleanupVersion": DATA_CLEANUP_VERSION,
        "configWarnings": _config_migration_report().get("warnings", []),
        "note": "TITAN_ADMIN_TOKEN set hoga to admin APIs/dashboard locked rahenge. Token absent hoga to compatibility mode open rahega."
    })


@app.route('/api/admin_login', methods=['POST'])
def api_admin_login():
    data = request.json or {}
    token = str(data.get('token') or _request_token() or '').strip()
    if not TITAN_SECURITY_STRICT:
        resp = jsonify({"status": "success", "message": "Security token not enforced", "enforced": False})
        return resp
    if not _constant_time_equal(token, TITAN_ADMIN_TOKEN):
        return jsonify({"status": "error", "message": "Invalid admin token", "securityLockdown": True}), 401
    resp = jsonify({"status": "success", "message": "Admin unlocked", "securityLockdown": True, "version": SECURITY_LOCKDOWN_VERSION})
    resp.set_cookie('titan_admin_token', token, max_age=60*60*24*30, httponly=True, secure=TITAN_COOKIE_SECURE, samesite='Lax')
    return resp


@app.route('/api/admin_logout', methods=['POST'])
def api_admin_logout():
    resp = jsonify({"status": "success", "message": "Logged out"})
    resp.delete_cookie('titan_admin_token')
    return resp


@app.route('/api/config_migration_status')
def api_config_migration_status():
    """v11 config cleanup status. Values are redacted; endpoint is admin-gated by before_request."""
    return jsonify(_config_migration_report())


@app.route('/api/upload_image', methods=['POST'])
def api_upload_image():
    """Server-side image upload proxy so IMGBB_API_KEY is never exposed in browser JS."""
    if not IMGBB_API_KEY:
        return jsonify({
            'status': 'error',
            'message': 'Image upload not configured. Set IMGBB_API_KEY on server.',
            'configCleanup': True
        }), 503
    file_obj = request.files.get('image') or request.files.get('file')
    if not file_obj:
        return jsonify({'status': 'error', 'message': 'image file missing'}), 400
    content_type = str(file_obj.content_type or '')
    if content_type and not content_type.startswith('image/'):
        return jsonify({'status': 'error', 'message': 'Only image uploads are allowed'}), 400
    raw = file_obj.read()
    if not raw:
        return jsonify({'status': 'error', 'message': 'Empty image file'}), 400
    if len(raw) > TITAN_UPLOAD_MAX_BYTES:
        return jsonify({'status': 'error', 'message': f'Image too large. Max {TITAN_UPLOAD_MAX_BYTES // (1024*1024)} MB allowed.'}), 413
    try:
        res = requests.post(
            'https://api.imgbb.com/1/upload',
            data={'key': IMGBB_API_KEY},
            files={'image': (file_obj.filename or 'upload.jpg', raw, content_type or 'image/jpeg')},
            timeout=25
        )
        try:
            payload = res.json()
        except Exception:
            payload = {'success': False, 'error': {'message': res.text[:200]}}
        if res.status_code >= 400 or not payload.get('success'):
            msg = ((payload.get('error') or {}).get('message') if isinstance(payload, dict) else '') or f'Image upload failed HTTP {res.status_code}'
            return jsonify({'status': 'error', 'message': msg}), 502
        data = payload.get('data') or {}
        return jsonify({
            'status': 'success',
            'url': data.get('url') or data.get('display_url'),
            'display_url': data.get('display_url') or data.get('url'),
            'delete_url': data.get('delete_url'),
            'configCleanup': True
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Image upload failed: ' + str(e)}), 500

# ==========================================================
# ANDRES BARLIN SYSTEM MANIFEST - NATIVE PUSH SYSTEM (V10.9)
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_TZ = os.environ.get("APP_TZ", "Asia/Kolkata")
# Business day cutoff: records/results/entries stay on previous business date
# until this local hour. Default 06 means 00:00-05:59 belongs to yesterday.
def _env_int(name, default, lo=None, hi=None):
    try:
        v = int(str(os.environ.get(name, default)).strip())
    except Exception:
        v = default
    if lo is not None and v < lo: v = lo
    if hi is not None and v > hi: v = hi
    return v
BUSINESS_DAY_CUTOFF_HOUR = _env_int("TITAN_BUSINESS_DAY_CUTOFF_HOUR", 6, 0, 23)

# ==========================================================
# FULL AUDIT PHASE 3: RUNTIME SELF-HEALING + BACKUP/ROLLBACK
# ==========================================================
FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING = True
FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS = True
RUNTIME_SELF_HEALING_VERSION = "2026-06-30-phase3-runtime-self-healing-v1"
PRODUCTION_DIAGNOSTICS_VERSION = "2026-06-30-phase4-production-diagnostics-v1"
TITAN_STATE_DIR = os.environ.get("TITAN_STATE_DIR", BASE_DIR).strip() or BASE_DIR
STATE_BACKUP_DIR = os.path.join(TITAN_STATE_DIR, "titan_state_backups")
LAST_KNOWN_GOOD_FILE = os.path.join(STATE_BACKUP_DIR, "last_known_good.json")
MAX_STATE_BACKUPS = int(os.environ.get("TITAN_MAX_STATE_BACKUPS", "30"))
RUNTIME_CRITICAL_STATE_KEYS = [
    "profiles", "ledgerSchedules", "wallets", "walletTransactions", "withdrawals",
    "resultRecords", "paymentOutbox", "whatsappSafetySettings", "entrySettings", "marketRegistry"
]

# ==========================================================
# DATA CLEANUP v17: safe Firebase maintenance/archive controls
# ==========================================================
TITAN_CLEANUP_LOCK_RETENTION_DAYS = int(os.environ.get("TITAN_CLEANUP_LOCK_RETENTION_DAYS", "3") or "3")
TITAN_CLEANUP_EVENT_RETENTION_DAYS = int(os.environ.get("TITAN_CLEANUP_EVENT_RETENTION_DAYS", "14") or "14")
TITAN_CLEANUP_USER_EVENT_KEEP = int(os.environ.get("TITAN_CLEANUP_USER_EVENT_KEEP", "50") or "50")
TITAN_CLEANUP_ARCHIVE_KEEP = int(os.environ.get("TITAN_CLEANUP_ARCHIVE_KEEP", "12") or "12")

# ==========================================================
# CONFIG CLEANUP v11: environment-first runtime configuration
# ==========================================================
DEFAULT_FIREBASE_DB_URL = "https://titan-bbbc4-default-rtdb.firebaseio.com/"
FIREBASE_DB_URL = os.environ.get("FIREBASE_URL", os.environ.get("FIREBASE_DB_URL", DEFAULT_FIREBASE_DB_URL)).strip() or DEFAULT_FIREBASE_DB_URL
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:3000").strip().rstrip("/") or "http://127.0.0.1:3000"
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "").strip()
TITAN_UPLOAD_MAX_BYTES = int(os.environ.get("TITAN_UPLOAD_MAX_BYTES", str(7 * 1024 * 1024)))
TITAN_PAYMENT_NAME = os.environ.get("TITAN_PAYMENT_NAME", "TITAN NOVA").strip() or "TITAN NOVA"
STARTUP_CONFIG_WARNINGS = _startup_config_warnings()


# ==========================================================
# OBSERVABILITY v12: lightweight event log + diagnostics dashboard
# ==========================================================
OBSERVABILITY_MAX_MEMORY_EVENTS = int(os.environ.get("TITAN_OBS_MEMORY_EVENTS", "300"))
OBSERVABILITY_MAX_FILE_LINES = int(os.environ.get("TITAN_OBS_FILE_LINES", "1500"))
OBSERVABILITY_LOG_FILE = os.path.join(TITAN_STATE_DIR, "titan_observability_events.jsonl")
OBSERVABILITY_FIREBASE_EVENTS_ENABLED = str(os.environ.get("TITAN_OBS_FIREBASE_EVENTS", "0")).strip().lower() in ("1", "true", "yes", "on")
_OBSERVABILITY_EVENTS = []
_OBSERVABILITY_COUNTERS = {"info": 0, "warning": 0, "error": 0, "critical": 0}
_OBSERVABILITY_LAST_ERROR = None


def _obs_now():
    try:
        return _now_iso_local()
    except Exception:
        return datetime.datetime.now().isoformat(timespec='seconds')


def _obs_redact(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lk = str(k).lower()
            if any(tok in lk for tok in ('token', 'secret', 'password', 'apikey', 'api_key', 'key')):
                out[k] = '***redacted***'
            else:
                out[k] = _obs_redact(v)
        return out
    if isinstance(value, list):
        return [_obs_redact(x) for x in value[:50]]
    if isinstance(value, str):
        v = value
        v = re.sub(r'(Bearer\s+)[A-Za-z0-9._\-]+', r'\1***redacted***', v)
        v = re.sub(r'(token=)[^&\s]+', r'\1***redacted***', v, flags=re.I)
        return v[:2000]
    return value


def _obs_event(kind, severity='info', message='', detail=None, source='flask', persist_firebase=False):
    """Record a lightweight operational event without breaking the business flow."""
    global _OBSERVABILITY_LAST_ERROR
    sev = str(severity or 'info').lower()
    if sev not in _OBSERVABILITY_COUNTERS:
        sev = 'info'
    rec = {
        'id': str(uuid.uuid4())[:12].upper(),
        'time': _obs_now(),
        'source': source or 'flask',
        'kind': str(kind or 'event')[:80],
        'severity': sev,
        'message': str(message or '')[:500],
        'detail': _obs_redact(detail or {})
    }
    _OBSERVABILITY_COUNTERS[sev] = int(_OBSERVABILITY_COUNTERS.get(sev, 0)) + 1
    if sev in ('error', 'critical'):
        _OBSERVABILITY_LAST_ERROR = rec
    _OBSERVABILITY_EVENTS.append(rec)
    if len(_OBSERVABILITY_EVENTS) > OBSERVABILITY_MAX_MEMORY_EVENTS:
        del _OBSERVABILITY_EVENTS[:-OBSERVABILITY_MAX_MEMORY_EVENTS]
    try:
        os.makedirs(TITAN_STATE_DIR, exist_ok=True)
        with open(OBSERVABILITY_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass
    if persist_firebase and OBSERVABILITY_FIREBASE_EVENTS_ENABLED:
        try:
            key = f"{int(time.time()*1000)}_{rec['id']}"
            _firebase_put_child(['observabilityEvents', key], rec, timeout=4)
        except Exception:
            pass
    return rec


def _obs_exception(kind, exc, detail=None, severity='error'):
    msg = exc.response.text[:200] if hasattr(exc, 'response') and getattr(exc, 'response', None) is not None else str(exc)
    det = detail.copy() if isinstance(detail, dict) else {'detail': detail} if detail else {}
    det.update({'exception': exc.__class__.__name__, 'trace': traceback.format_exc(limit=4)})
    return _obs_event(kind, severity, msg, det)


def _obs_recent_file_events(limit=200):
    try:
        if not os.path.exists(OBSERVABILITY_LOG_FILE):
            return []
        with open(OBSERVABILITY_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-max(1, min(int(limit or 200), OBSERVABILITY_MAX_FILE_LINES)):]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
    except Exception:
        return []


def _obs_prune_file():
    try:
        if not os.path.exists(OBSERVABILITY_LOG_FILE):
            return 0
        with open(OBSERVABILITY_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) <= OBSERVABILITY_MAX_FILE_LINES:
            return len(lines)
        with open(OBSERVABILITY_LOG_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines[-OBSERVABILITY_MAX_FILE_LINES:])
        return OBSERVABILITY_MAX_FILE_LINES
    except Exception:
        return 0


def _obs_filter_events(events, severity=None, source=None, limit=100):
    sev = str(severity or '').lower().strip()
    src = str(source or '').lower().strip()
    rows = []
    for e in reversed(events or []):
        if sev and str(e.get('severity','')).lower() != sev:
            continue
        if src and str(e.get('source','')).lower() != src:
            continue
        rows.append(e)
        if len(rows) >= int(limit or 100):
            break
    return rows


def _obs_gateway_snapshot():
    try:
        r = _gateway_request('GET', '/observability_status', timeout=4)
        try:
            return r.json()
        except Exception:
            return {'status': 'error', 'message': r.text[:200], 'httpStatus': r.status_code}
    except Exception as e:
        return {'status': 'offline', 'message': str(e)}


def _obs_firebase_ping():
    started = time.time()
    try:
        res = requests.get(get_firebase_url(), timeout=6)
        return {'status': 'success' if res.status_code < 400 else 'error', 'httpStatus': res.status_code, 'ms': int((time.time()-started)*1000)}
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'ms': int((time.time()-started)*1000)}


def _obs_summary(include_gateway=True):
    _obs_prune_file()
    file_events = _obs_recent_file_events(300)
    all_events = file_events if file_events else list(_OBSERVABILITY_EVENTS)
    latest_errors = _obs_filter_events(all_events, severity='error', limit=10) + _obs_filter_events(all_events, severity='critical', limit=10)
    counts = dict(_OBSERVABILITY_COUNTERS)
    # Recompute from file tail so restart history is visible too.
    for e in all_events:
        sev = str(e.get('severity') or 'info').lower()
        if sev in counts:
            counts[sev] = max(counts[sev], 0)
    status = 'success'
    if latest_errors:
        status = 'attention_required'
    gateway = _obs_gateway_snapshot() if include_gateway else {'status': 'skipped'}
    return {
        'status': status,
        'version': OBSERVABILITY_VERSION,
        'observability': True,
        'checkedAt': _obs_now(),
        'flask': {
            'memoryEventCount': len(_OBSERVABILITY_EVENTS),
            'fileEventCountTail': len(file_events),
            'logFile': _redact_config_value(OBSERVABILITY_LOG_FILE, 28),
            'lastError': _OBSERVABILITY_LAST_ERROR,
            'counters': counts,
        },
        'firebase': _obs_firebase_ping(),
        'gateway': gateway,
        'recentErrors': latest_errors[:10],
        'recentWarnings': _obs_filter_events(all_events, severity='warning', limit=10),
        'recommendedChecks': [
            '/api/observability_status', '/api/observability_events', '/api/health_monitor',
            '/api/runtime_health', '/api/money_atomicity_status', '/api/gateway_durability_status'
        ]
    }

def _env_bool(name, default=False):
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in ("1", "true", "yes", "on")

def _redact_config_value(value, keep=8):
    s = str(value or "")
    if not s:
        return ""
    if len(s) <= keep:
        return "***"
    return s[:keep] + "…" + str(len(s)) + "chars"

def get_firebase_url():
    url = FIREBASE_DB_URL.strip().rstrip('/')
    if not url.endswith('.json'):
        url += '/titan_master_data.json'
    return url

def _client_app_config():
    return {
        "version": CONFIG_CLEANUP_VERSION,
        "uploadEndpoint": "/api/upload_image",
        "imageUploadProxy": True,
        "imgbbConfigured": bool(IMGBB_API_KEY),
        "uploadMaxBytes": TITAN_UPLOAD_MAX_BYTES,
        "paymentName": TITAN_PAYMENT_NAME,
        "userSafetyVersion": USER_SAFETY_VERSION,
        "vipDeviceLimit": TITAN_VIP_DEVICE_LIMIT,
        "vipDeviceStrict": bool(TITAN_VIP_DEVICE_STRICT),
        "businessDayCutoffHour": BUSINESS_DAY_CUTOFF_HOUR,
    }

def _config_migration_report():
    warnings = []
    using_default_firebase = not (os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL"))
    if using_default_firebase:
        warnings.append("FIREBASE_URL/FIREBASE_DB_URL env not set; compatibility default database URL is in use.")
    if not IMGBB_API_KEY:
        warnings.append("IMGBB_API_KEY env not set; payment/QR image uploads will be disabled until configured.")
    if not TITAN_ADMIN_TOKEN:
        warnings.append("TITAN_ADMIN_TOKEN env not set; admin security is compatibility-open.")
    if not os.environ.get("TITAN_GATEWAY_TOKEN"):
        warnings.append("TITAN_GATEWAY_TOKEN missing; Flask will fall back to admin token for Gateway proxy calls.")
    if re.search(r"https?://(127\.0\.0\.1|localhost)(:|/|$)", GATEWAY_URL, re.I):
        warnings.append("GATEWAY_URL is localhost; OK for local Termux, risky for split-host deployments.")
    return {
        "status": "warning" if warnings else "success",
        "version": CONFIG_CLEANUP_VERSION,
        "firebase": {
            "configuredFromEnv": not using_default_firebase,
            "urlRedacted": _redact_config_value(get_firebase_url(), 20),
            "pathLooksJson": get_firebase_url().endswith('.json'),
        },
        "security": {
            "adminTokenConfigured": bool(TITAN_ADMIN_TOKEN),
            "gatewayTokenConfigured": bool(TITAN_GATEWAY_TOKEN),
            "strict": bool(TITAN_SECURITY_STRICT),
            "cookieSecure": bool(TITAN_COOKIE_SECURE),
        },
        "storage": {
            "stateDir": _redact_config_value(TITAN_STATE_DIR, 24),
            "backupDir": _redact_config_value(STATE_BACKUP_DIR, 24),
        },
        "uploads": {
            "imgbbConfigured": bool(IMGBB_API_KEY),
            "proxyEndpoint": "/api/upload_image",
            "maxBytes": TITAN_UPLOAD_MAX_BYTES,
        },
        "gateway": {"urlRedacted": _redact_config_value(GATEWAY_URL, 20), "localhost": bool(re.search(r"https?://(127\.0\.0\.1|localhost)(:|/|$)", GATEWAY_URL, re.I))},
        "startupWarnings": STARTUP_CONFIG_WARNINGS,
        "clientConfig": _client_app_config(),
        "warnings": warnings,
        "envRequiredRecommended": ["FIREBASE_URL", "TITAN_ADMIN_TOKEN", "TITAN_GATEWAY_TOKEN", "TITAN_FLASK_SECRET", "IMGBB_API_KEY"],
    }

def load_from_firebase():
    global FIREBASE_LAST_LOAD_META
    try:
        force = False
        try:
            force = bool(has_request_context() and str(request.args.get('force') or '').strip() == '1')
        except Exception:
            force = False
        cached = _rt_cache_get(force=force)
        if cached is not None:
            FIREBASE_LAST_LOAD_META = {"status": "cache", "message": "served from v37 realtime memory cache", "source": FIREBASE_STATE_CACHE_SOURCE, "ageMs": _rt_ms()-int(FIREBASE_STATE_CACHE_AT_MS or 0), "realtimeSync": REALTIME_SYNC_VERSION}
            return cached
        started = time.time()
        res = requests.get(get_firebase_url(), timeout=8)
        ms = int((time.time()-started)*1000)
        if res.status_code == 200:
            try:
                payload = res.json() if getattr(res, 'text', '') else None
            except Exception as parse_err:
                FIREBASE_LAST_LOAD_META = {"status": "parse_error", "httpStatus": res.status_code, "message": str(parse_err)[:160], "ms": ms, "realtimeSync": REALTIME_SYNC_VERSION}
                _obs_event('firebase_load_parse_error', 'error', 'Firebase JSON parse failed', FIREBASE_LAST_LOAD_META)
                return None
            if isinstance(payload, dict) and payload:
                try:
                    score = _runtime_state_score(payload) if '_runtime_state_score' in globals() else {}
                except Exception:
                    score = {}
                FIREBASE_LAST_LOAD_META = {"status": "success", "httpStatus": res.status_code, "message": "loaded", "ms": ms, "score": score, "realtimeSync": REALTIME_SYNC_VERSION}
                _rt_cache_set(payload, 'firebase_get')
                return payload
            FIREBASE_LAST_LOAD_META = {"status": "empty", "httpStatus": res.status_code, "message": "Firebase root returned empty/null body", "ms": ms, "realtimeSync": REALTIME_SYNC_VERSION}
            _obs_event('firebase_load_empty_root', 'critical', 'Firebase root empty/null; v40 manual overwrite mode will not auto-init unless app flow saves', FIREBASE_LAST_LOAD_META)
            return None
        FIREBASE_LAST_LOAD_META = {"status": "http_error", "httpStatus": res.status_code, "message": getattr(res, 'text', '')[:200], "ms": ms, "realtimeSync": REALTIME_SYNC_VERSION}
        _obs_event('firebase_load_non_200_or_empty', 'warning', f'Firebase load returned HTTP {res.status_code}', {'httpStatus': res.status_code, 'ms': ms})
    except Exception as e:
        print("Firebase Load Error:", e)
        FIREBASE_LAST_LOAD_META = {"status": "exception", "message": str(e)[:200], "realtimeSync": REALTIME_SYNC_VERSION}
        _obs_exception('firebase_load_error', e)
    return None

def _runtime_utc_stamp():
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def _runtime_safe_label(label):
    return ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in str(label or 'snapshot'))[:60] or 'snapshot'

def _runtime_deepcopy(obj):
    try:
        return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        return obj

def _runtime_state_score(state_obj):
    if not isinstance(state_obj, dict):
        return {"score": 0, "reason": "not_dict"}
    profiles = state_obj.get("profiles", {}) if isinstance(state_obj.get("profiles"), dict) else {}
    wallets = state_obj.get("wallets", {}) if isinstance(state_obj.get("wallets"), dict) else {}
    ledger_schedules = state_obj.get("ledgerSchedules", {}) if isinstance(state_obj.get("ledgerSchedules"), dict) else {}
    withdrawals = state_obj.get("withdrawals", []) if isinstance(state_obj.get("withdrawals"), list) else []
    wallet_txns = state_obj.get("walletTransactions", []) if isinstance(state_obj.get("walletTransactions"), list) else []
    result_records = state_obj.get("resultRecords", {}) if isinstance(state_obj.get("resultRecords"), dict) else {}
    score = (len(profiles) * 20) + (len(wallets) * 10) + (len(ledger_schedules) * 8) + len(withdrawals) + len(wallet_txns) + (len(result_records) * 5)
    return {
        "score": int(score),
        "profiles": len(profiles),
        "wallets": len(wallets),
        "ledgerSchedules": len(ledger_schedules),
        "withdrawals": len(withdrawals),
        "walletTransactions": len(wallet_txns),
        "resultRecords": len(result_records),
    }

def _runtime_state_validation_report(candidate, existing=None):
    errors = []
    warnings = []
    if not isinstance(candidate, dict):
        return {"ok": False, "errors": ["state_not_dict"], "warnings": [], "score": _runtime_state_score(candidate)}
    profiles = candidate.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles_missing_or_empty")
    else:
        if not any(str(k).startswith("admin") for k in profiles.keys()):
            errors.append("admin_profile_missing")
    for key in ["wallets", "walletTransactions", "withdrawals", "ledgerSchedules", "resultRecords"]:
        if key not in candidate:
            warnings.append(f"missing_key:{key}")
    if isinstance(candidate.get("ledgerSchedules"), dict):
        bad = []
        for sid, sched in list(candidate.get("ledgerSchedules", {}).items())[:50]:
            if not isinstance(sched, dict):
                bad.append(str(sid))
                continue
            t = str(sched.get("time") or sched.get("scheduleTime") or "").strip()
            if t and len(t.split(':')) != 2:
                bad.append(str(sid))
        if bad:
            warnings.append("ledger_schedule_time_format_warning:" + ",".join(bad[:5]))
    if isinstance(existing, dict):
        old_profiles = existing.get("profiles", {}) if isinstance(existing.get("profiles"), dict) else {}
        new_profiles = candidate.get("profiles", {}) if isinstance(candidate.get("profiles"), dict) else {}
        if len(old_profiles) >= 2 and len(new_profiles) < max(1, int(len(old_profiles) * 0.50)):
            errors.append(f"profile_drop_guard:{len(old_profiles)}_to_{len(new_profiles)}")
        old_wallets = existing.get("wallets", {}) if isinstance(existing.get("wallets"), dict) else {}
        new_wallets = candidate.get("wallets", {}) if isinstance(candidate.get("wallets"), dict) else {}
        if len(old_wallets) >= 2 and len(new_wallets) < max(1, int(len(old_wallets) * 0.50)):
            errors.append(f"wallet_drop_guard:{len(old_wallets)}_to_{len(new_wallets)}")
        old_schedules = existing.get("ledgerSchedules", {}) if isinstance(existing.get("ledgerSchedules"), dict) else {}
        new_schedules = candidate.get("ledgerSchedules", {}) if isinstance(candidate.get("ledgerSchedules"), dict) else {}
        active_old = [k for k, v in old_schedules.items() if isinstance(v, dict) and v.get("enabled", True)]
        if active_old and not new_schedules:
            errors.append("active_ledger_schedules_would_be_deleted")
        old_txns = existing.get("walletTransactions", []) if isinstance(existing.get("walletTransactions"), list) else []
        new_txns = candidate.get("walletTransactions", []) if isinstance(candidate.get("walletTransactions"), list) else []
        if len(old_txns) >= 10 and len(new_txns) < int(len(old_txns) * 0.50):
            errors.append(f"wallet_transaction_drop_guard:{len(old_txns)}_to_{len(new_txns)}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "score": _runtime_state_score(candidate)}


# ==========================================================
# FIREBASE DATA GUARD v36
# Blocks accidental root reset when Firebase temporarily returns empty,
# stale UI/Gateway state tries to root-save, or a local default state would
# overwrite real business data. Child-path writes remain allowed.
# ==========================================================
def _firebase_allow_empty_init():
    return str(os.environ.get('TITAN_FIREBASE_ALLOW_EMPTY_INIT', '0')).strip().lower() in ('1', 'true', 'yes', 'on')

def _firebase_collection_size(v):
    if isinstance(v, dict):
        return len(v)
    if isinstance(v, list):
        return len(v)
    if v in (None, ''):
        return 0
    return 1

def _firebase_protected_keys():
    return [
        'profiles', 'wallets', 'walletTransactions', 'payments', 'withdrawals', 'entries',
        'ledgerSchedules', 'resultRecords', 'settlementRecords', 'marketRegistry', 'marketLocks',
        'auditLog', 'paymentOutbox', 'loadForwarderOutbox', 'spamGuardEvents', 'whatsappSafetyTargets',
        'whatsappSafetyEvents', 'resultTargets', 'loadForwarder', 'entrySettings', 'resultSettings',
        'paymentMethods', 'withdrawalSettings', 'walletSettings', 'spamGuardSettings',
        'whatsappSafetySettings', 'moneyIdempotency', 'gatewayDurability'
    ]

def _firebase_default_state_like(state_obj):
    if not isinstance(state_obj, dict):
        return False
    profiles = state_obj.get('profiles') if isinstance(state_obj.get('profiles'), dict) else {}
    profile_keys = set(map(str, profiles.keys()))
    default_profiles = {'admin1', 'admin2', 'admin3', 'client_dummy'}
    wallets = state_obj.get('wallets') if isinstance(state_obj.get('wallets'), dict) else {}
    return bool(profile_keys and profile_keys.issubset(default_profiles) and _firebase_collection_size(wallets) <= 4 and not state_obj.get('walletTransactions') and not state_obj.get('entries'))

def _firebase_merge_dict_if_risky(candidate, latest, key, backup_label=''):
    live = latest.get(key) if isinstance(latest, dict) else None
    cand = candidate.get(key) if isinstance(candidate, dict) else None
    if not isinstance(live, dict) or not live:
        return
    if not isinstance(cand, dict):
        candidate[key] = _runtime_deepcopy(live)
        return
    live_n, cand_n = len(live), len(cand)
    risky_drop = live_n >= 2 and cand_n < max(1, int(live_n * 0.50))
    always_preserve_missing = key in ('profiles', 'wallets', 'ledgerSchedules', 'gatewayDurability', 'moneyIdempotency')
    if risky_drop or always_preserve_missing:
        for k, v in live.items():
            if k not in cand:
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand

def _firebase_merge_list_if_risky(candidate, latest, key):
    live = latest.get(key) if isinstance(latest, dict) else None
    cand = candidate.get(key) if isinstance(candidate, dict) else None
    if not isinstance(live, list) or not live:
        return
    if not isinstance(cand, list):
        candidate[key] = _runtime_deepcopy(live)
        return
    if len(live) >= 5 and len(cand) < max(1, int(len(live) * 0.50)):
        try:
            if '_merge_list_by_id' in globals():
                candidate[key] = _merge_list_by_id(cand, live)
                return
        except Exception:
            pass
        seen, out = set(), []
        for item in cand + live:
            try:
                sig = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                sig = str(item)
            if sig not in seen:
                seen.add(sig)
                out.append(_runtime_deepcopy(item))
        candidate[key] = out[-3000:]

def _firebase_merge_protected_source_of_truth(candidate, latest, backup_label=''):
    if not isinstance(candidate, dict) or not isinstance(latest, dict) or not latest:
        return candidate
    for fn_name in ('_merge_result_source_of_truth', '_merge_ledger_schedules_source_of_truth', '_merge_ledger_records_source_of_truth', '_preserve_server_ledger_auto_marks', '_merge_money_source_of_truth'):
        try:
            fn = globals().get(fn_name)
            if callable(fn):
                fn(candidate, latest)
        except Exception as e:
            print('Firebase protected merge warning', fn_name, e)
    for key in _firebase_protected_keys():
        live = latest.get(key)
        if isinstance(live, dict):
            _firebase_merge_dict_if_risky(candidate, latest, key, backup_label)
        elif isinstance(live, list):
            _firebase_merge_list_if_risky(candidate, latest, key)
    candidate.setdefault('firebaseDataGuard', {})['version'] = FIREBASE_DATA_GUARD_VERSION
    candidate['firebaseDataGuard']['lastRootSaveGuardAt'] = _now_iso_local() if '_now_iso_local' in globals() else datetime.datetime.now().isoformat(timespec='seconds')
    candidate['firebaseDataGuard']['mode'] = 'cas-root-save-with-data-loss-guard'
    return candidate

def _firebase_data_loss_guard(candidate, latest, label=''):
    errors, warnings = [], []
    if not isinstance(candidate, dict):
        return {'ok': False, 'errors': ['candidate_not_dict'], 'warnings': warnings}
    if not isinstance(latest, dict) or not latest:
        if _firebase_default_state_like(candidate) and not _firebase_allow_empty_init():
            return {'ok': False, 'errors': ['empty_firebase_default_state_save_blocked'], 'warnings': ['Set TITAN_FIREBASE_ALLOW_EMPTY_INIT=1 only for a brand new empty database.']}
        if not _firebase_allow_empty_init():
            return {'ok': False, 'errors': ['empty_or_unreadable_firebase_root_save_blocked'], 'warnings': ['Firebase root looked empty/unreadable, so root save was blocked to avoid reset.']}
        return {'ok': True, 'errors': [], 'warnings': ['empty_init_allowed_by_env']}
    for key in _firebase_protected_keys():
        old_n = _firebase_collection_size(latest.get(key))
        new_n = _firebase_collection_size(candidate.get(key))
        if old_n <= 0:
            continue
        if key in ('profiles', 'wallets', 'ledgerSchedules', 'marketRegistry'):
            threshold = max(1, int(old_n * 0.60))
            if new_n < threshold:
                errors.append(f'{key}_drop_guard:{old_n}_to_{new_n}')
        elif old_n >= 10 and new_n < max(1, int(old_n * 0.35)):
            errors.append(f'{key}_mass_drop_guard:{old_n}_to_{new_n}')
        elif old_n >= 3 and new_n == 0:
            errors.append(f'{key}_wipe_guard:{old_n}_to_0')
    if _firebase_default_state_like(candidate) and _runtime_state_score(latest).get('score', 0) > _runtime_state_score(candidate).get('score', 0):
        errors.append('default_state_would_replace_richer_live_state')
    return {'ok': not errors, 'errors': errors, 'warnings': warnings}

def _firebase_fetch_root_with_etag_guarded(timeout=12):
    started = time.time()
    res = requests.get(get_firebase_url(), headers={'X-Firebase-ETag': 'true'}, timeout=timeout)
    ms = int((time.time()-started)*1000)
    if getattr(res, 'status_code', 500) >= 400:
        raise RuntimeError(f"Firebase guarded GET HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    etag = res.headers.get('ETag') or res.headers.get('etag') or '*'
    try:
        data = res.json() if getattr(res, 'text', '') else None
    except Exception as e:
        raise RuntimeError(f'Firebase guarded GET parse error: {e}')
    if not isinstance(data, dict):
        data = {}
    return data, etag, ms

def _firebase_guarded_root_save(data, backup_label='before_save'):
    if not isinstance(data, dict):
        return False
    last_error = None
    for attempt in range(6):
        try:
            latest, etag, read_ms = _firebase_fetch_root_with_etag_guarded()
            candidate = _runtime_deepcopy(data)
            try:
                _ensure_foundation_state(candidate) if '_ensure_foundation_state' in globals() else None
                _ensure_foundation_state(latest) if latest and '_ensure_foundation_state' in globals() else None
            except Exception as e:
                print('Firebase guard foundation warning:', e)
            _firebase_merge_protected_source_of_truth(candidate, latest, backup_label)
            runtime_report = _runtime_state_validation_report(candidate, latest)
            loss_report = _firebase_data_loss_guard(candidate, latest, backup_label)
            if not runtime_report.get('ok') or not loss_report.get('ok'):
                report = {'runtime': runtime_report, 'lossGuard': loss_report, 'label': backup_label, 'attempt': attempt}
                _obs_event('firebase_root_save_blocked_v36', 'critical', 'Risky Firebase root save blocked', report)
                print('Firebase Data Guard v36 blocked root save:', report)
                return False
            if isinstance(latest, dict) and latest:
                _write_state_backup(latest, backup_label or 'before_guarded_save')
            started = time.time()
            res = requests.put(get_firebase_url(), json=candidate, headers={'if-match': etag or '*'}, timeout=15)
            ms = int((time.time()-started)*1000)
            if getattr(res, 'status_code', 500) == 412:
                _obs_event('firebase_root_save_cas_retry_v36', 'warning', 'Firebase CAS conflict; retrying guarded save', {'attempt': attempt, 'readMs': read_ms, 'writeMs': ms})
                time.sleep(0.08 * (attempt + 1))
                continue
            if getattr(res, 'status_code', 500) >= 400:
                raise RuntimeError(f"Firebase guarded PUT HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
            _write_state_backup(candidate, 'last_known_good')
            _rt_cache_set(candidate, 'guarded_root_save_candidate')
            _obs_event('firebase_root_save_ok_v38', 'info', 'Guarded Firebase root save committed', {'attempt': attempt, 'readMs': read_ms, 'writeMs': ms}, persist_firebase=False)
            return candidate
        except Exception as e:
            last_error = e
            _obs_exception('firebase_guarded_root_save_error', e, {'attempt': attempt, 'label': backup_label})
            time.sleep(0.10 * (attempt + 1))
    print('Firebase Data Guard v36 save failed:', last_error)
    return False

def _ensure_state_backup_dir():
    os.makedirs(STATE_BACKUP_DIR, exist_ok=True)

def _state_backup_files():
    _ensure_state_backup_dir()
    files = []
    for name in os.listdir(STATE_BACKUP_DIR):
        if name.endswith('.json') and name != 'last_known_good.json':
            path = os.path.join(STATE_BACKUP_DIR, name)
            try:
                files.append({"file": name, "path": path, "size": os.path.getsize(path), "mtime": os.path.getmtime(path)})
            except Exception:
                pass
    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return files

def _prune_state_backups():
    try:
        files = _state_backup_files()
        for item in files[MAX_STATE_BACKUPS:]:
            try:
                os.remove(item["path"])
            except Exception:
                pass
    except Exception as e:
        print("Backup prune error:", e)

def _write_state_backup(state_obj, label="auto"): 
    if not isinstance(state_obj, dict):
        return None
    _ensure_state_backup_dir()
    stamp = _runtime_utc_stamp()
    safe_label = _runtime_safe_label(label)
    path = os.path.join(STATE_BACKUP_DIR, f"{stamp}_{safe_label}.json")
    payload = {
        "backupMeta": {
            "createdAt": _now_iso_local() if '_now_iso_local' in globals() else datetime.datetime.now().isoformat(timespec='seconds'),
            "label": safe_label,
            "version": RUNTIME_SELF_HEALING_VERSION,
            "score": _runtime_state_score(state_obj),
        },
        "state": _runtime_deepcopy(state_obj),
    }
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        report = _runtime_state_validation_report(state_obj)
        if report.get("ok"):
            with open(LAST_KNOWN_GOOD_FILE, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        _prune_state_backups()
        return os.path.basename(path)
    except Exception as e:
        print("Backup write error:", e)
        return None

def _read_state_backup(filename):
    if not filename:
        return None
    safe = os.path.basename(str(filename))
    path = LAST_KNOWN_GOOD_FILE if safe == 'last_known_good.json' else os.path.join(STATE_BACKUP_DIR, safe)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        state = payload.get("state") if isinstance(payload, dict) and "state" in payload else payload
        return {"file": safe, "payload": payload, "state": state}
    except Exception as e:
        print("Backup read error:", e)
        return None

def _safe_save_to_firebase_put(data):
    """v41 Base-File Manual Overwrite Core: direct Firebase root PUT.
    No v36 data-loss guard, no env unlock, no protected-key merge.
    Whatever admin UI posts is written as source-of-truth.
    """
    if not isinstance(data, dict):
        return False
    started = time.time()
    res = requests.put(get_firebase_url(), json=data, timeout=15)
    if getattr(res, "status_code", 500) >= 400:
        _obs_event('firebase_root_put_failed_v40', 'error', f"Firebase HTTP {res.status_code}", {'httpStatus': res.status_code, 'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    _obs_event('firebase_root_put_ok_base_manual_overwrite_v41', 'warning', 'Manual overwrite root Firebase save committed', {'ms': int((time.time()-started)*1000)}, persist_firebase=False)
    return True

def save_to_firebase(data, backup_label="manual_overwrite"):
    """Guarded Firebase root save.

    Full-root saves are kept for compatibility with the current UI, but they now
    use the v36/v38 guarded CAS path so stale admin tabs cannot blindly replace
    live production collections written by Gateway or atomic money flows.
    """
    try:
        if not isinstance(data, dict):
            return False
        try:
            data.setdefault('firebaseManualOverwrite', {})['version'] = FIREBASE_DATA_GUARD_VERSION
            data['firebaseManualOverwrite']['lastOverwriteAt'] = _now_iso_local() if '_now_iso_local' in globals() else datetime.datetime.now().isoformat(timespec='seconds')
            data['firebaseManualOverwrite']['mode'] = 'guarded-cas-root-save'
        except Exception:
            pass
        saved = _firebase_guarded_root_save(data, backup_label or "guarded_save")
        if not saved:
            _rt_cache_clear('guarded_root_save_blocked')
            return False
        _obs_event('firebase_guarded_save_ok_phase1', 'info', 'Guarded Firebase root save committed; stale overwrite protection active', {'backupLabel': backup_label}, persist_firebase=False)
        return saved
    except Exception as e:
        print('Firebase Guarded Save Error:', e)
        _obs_exception('firebase_guarded_save_error_phase1', e, {'backupLabel': backup_label, 'firebaseDataGuard': FIREBASE_DATA_GUARD_VERSION})
        _rt_cache_clear('guarded_save_error')
        return False


# ==========================================================
# FIREBASE CHILD-PATH WRITES FOR LEDGER ATOMICITY
# Ledger card edits must not use a full root PUT. Full PUT can race when two
# card edits overlap and can restore an older blank card over a newly rated card.
# These helpers write only the exact Firebase child path that changed.
# ==========================================================
def _firebase_child_url(*parts):
    from urllib.parse import quote
    root = get_firebase_url()
    if not root.endswith('.json'):
        root = root.rstrip('/') + '.json'
    base = root[:-5]
    clean = [quote(str(p), safe='') for p in parts if str(p) != '']
    if not clean:
        return root
    return base + '/' + '/'.join(clean) + '.json'

def _firebase_put_child(parts, value, timeout=10):
    started = time.time()
    res = requests.put(_firebase_child_url(*parts), json=value, timeout=timeout)
    if getattr(res, 'status_code', 500) >= 400:
        _obs_event('firebase_child_put_failed', 'error', f"Firebase child PUT HTTP {res.status_code}", {'parts': parts, 'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase child PUT HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    _rt_cache_apply_child(parts, value, 'put')
    return True

def _firebase_patch_child(parts, value, timeout=10):
    started = time.time()
    res = requests.patch(_firebase_child_url(*parts), json=value, timeout=timeout)
    if getattr(res, 'status_code', 500) >= 400:
        _obs_event('firebase_child_patch_failed', 'error', f"Firebase child PATCH HTTP {res.status_code}", {'parts': parts, 'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase child PATCH HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    _rt_cache_apply_child(parts, value, 'patch')
    return True

def _firebase_delete_child(parts, timeout=10):
    started = time.time()
    res = requests.delete(_firebase_child_url(*parts), timeout=timeout)
    if getattr(res, 'status_code', 500) >= 400:
        _obs_event('firebase_child_delete_failed', 'error', f"Firebase child DELETE HTTP {res.status_code}", {'parts': parts, 'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase child DELETE HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    _rt_cache_apply_child(parts, None, 'delete')
    return True

def _firebase_get_child(parts, timeout=10):
    started = time.time()
    res = requests.get(_firebase_child_url(*parts), timeout=timeout)
    if getattr(res, 'status_code', 500) >= 400:
        _obs_event('firebase_child_get_failed', 'error', f"Firebase child GET HTTP {res.status_code}", {'parts': parts, 'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase child GET HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    try:
        return res.json() if getattr(res, 'text', '') else None
    except Exception:
        return None

def _firebase_put_top_level_children(state, updates, audit=True):
    """Persist selected top-level keys without a full Firebase root overwrite.

    Phase 2 single-source cleanup: admin setting panels should not rewrite the
    whole Firebase root and race Gateway-owned runtime collections. This helper
    writes only the changed top-level child paths and optionally persists the
    audit log generated by the caller.
    """
    if not isinstance(updates, dict):
        return False
    for key, value in updates.items():
        _firebase_put_child([key], value)
    if audit and isinstance(state, dict) and isinstance(state.get('auditLog'), list):
        _firebase_put_child(['auditLog'], state.get('auditLog', [])[-1000:])
    return True


# ==========================================================
# MONEY ATOMICITY v9: Firebase ETag compare-and-set for all money actions
# ==========================================================
class _MoneyAbort(Exception):
    def __init__(self, payload, status_code=400):
        super().__init__(str((payload or {}).get('message') or payload))
        self.payload = payload or {"status": "error", "message": "Money action blocked"}
        self.status_code = status_code


def _money_error(message, status_code=400, **extra):
    payload = {"status": "error", "message": message, "moneyAtomicity": True, "version": MONEY_ATOMICITY_VERSION}
    payload.update(extra)
    raise _MoneyAbort(payload, status_code)


def _firebase_get_root_with_etag(timeout=10):
    started = time.time()
    res = requests.get(get_firebase_url(), headers={"X-Firebase-ETag": "true"}, timeout=timeout)
    if getattr(res, 'status_code', 500) >= 400:
        _obs_event('firebase_etag_get_failed', 'error', f"Firebase ETag GET HTTP {res.status_code}", {'body': getattr(res, 'text', '')[:200], 'ms': int((time.time()-started)*1000)})
        raise RuntimeError(f"Firebase ETag GET HTTP {res.status_code}: {getattr(res, 'text', '')[:200]}")
    etag = res.headers.get('ETag') or res.headers.get('etag') or '*'
    try:
        data = res.json() if res.text else {}
    except Exception:
        data = {}
    return (data or {}), etag


def _firebase_put_root_if_match(state_obj, etag, timeout=12):
    # Patch 2: normal money/wallet mutations no longer root-PUT Firebase.
    # The caller still reads with ETag for conflict awareness, then writes changed
    # collections through top-level child PUTs to avoid replacing the full app root.
    started = time.time()
    if not isinstance(state_obj, dict):
        return False
    try:
        _firebase_put_top_level_children(state_obj, state_obj, audit=False)
        _obs_event('firebase_child_path_money_save_ok', 'info', 'Money state committed with child-path PUTs', {'ms': int((time.time()-started)*1000)}, persist_firebase=False)
        return True
    except Exception as e:
        _obs_exception('firebase_child_path_money_save_failed', e, {'ms': int((time.time()-started)*1000)})
        raise


def _money_stamp(v):
    if not v:
        return 0
    try:
        return int(datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00')).timestamp() * 1000)
    except Exception:
        pass
    try:
        return int(float(v))
    except Exception:
        return 0


def _money_terminal_rank(obj):
    st = str((obj or {}).get('status') or '').lower()
    if st in ('paid', 'approved'):
        return 4
    if st == 'rejected':
        return 3
    if st == 'approved_processing':
        return 2
    if st == 'pending':
        return 1
    return 0


def _money_newer_record(a, b):
    """Return safer/newer record between candidate a and live b."""
    if not isinstance(a, dict):
        return _runtime_deepcopy(b)
    if not isinstance(b, dict):
        return _runtime_deepcopy(a)
    # Terminal money states always beat transient states.
    ar, br = _money_terminal_rank(a), _money_terminal_rank(b)
    if br > ar:
        out = _runtime_deepcopy(b)
    elif ar > br:
        out = _runtime_deepcopy(a)
    else:
        at = max(_money_stamp(a.get(k)) for k in ('updatedAt','approvedAt','rejectedAt','paidAt','createdAt','time'))
        bt = max(_money_stamp(b.get(k)) for k in ('updatedAt','approvedAt','rejectedAt','paidAt','createdAt','time'))
        out = _runtime_deepcopy(b if bt > at else a)
    # Preserve one-shot notification/credit flags from both sides.
    for src in (a, b):
        if isinstance(src, dict):
            for k, v in src.items():
                if k.endswith('Notified') or k.endswith('NotifiedAt') or k in ('walletCredited','walletLedgerId','walletCreditAmount'):
                    if v and not out.get(k):
                        out[k] = v
    return out


def _merge_list_by_id(candidate_list, live_list):
    out = []
    by_id = {}
    def add(item):
        if not isinstance(item, dict):
            return
        key = str(item.get('id') or item.get('txnId') or item.get('entryId') or item.get('withdrawalId') or item.get('paymentId') or '')
        if not key:
            key = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:24]
        if key in by_id:
            by_id[key] = _money_newer_record(by_id[key], item)
        else:
            by_id[key] = _runtime_deepcopy(item)
    for x in candidate_list if isinstance(candidate_list, list) else []:
        add(x)
    for x in live_list if isinstance(live_list, list) else []:
        add(x)
    out = list(by_id.values())
    out.sort(key=lambda x: str(x.get('time') or x.get('createdAt') or x.get('updatedAt') or ''), reverse=False)
    return out


def _merge_wallet_record(candidate_wallet, live_wallet):
    if not isinstance(candidate_wallet, dict):
        return _runtime_deepcopy(live_wallet)
    if not isinstance(live_wallet, dict):
        return _runtime_deepcopy(candidate_wallet)
    cw = _runtime_deepcopy(candidate_wallet)
    lw = _runtime_deepcopy(live_wallet)
    c_ledger = cw.get('ledger', []) if isinstance(cw.get('ledger', []), list) else []
    l_ledger = lw.get('ledger', []) if isinstance(lw.get('ledger', []), list) else []
    merged_ledger = _merge_list_by_id(c_ledger, l_ledger)
    ct = _money_stamp(cw.get('updatedAt'))
    lt = _money_stamp(lw.get('updatedAt'))
    out = lw if (lt > ct and len(l_ledger) >= len(c_ledger)) else cw
    out['ledger'] = merged_ledger[-800:]
    # If ledger has a terminal balance/hold entry newer than wallet object, trust it.
    latest_bal_entry = None
    for item in merged_ledger:
        if isinstance(item, dict) and ('balanceAfter' in item or 'holdAfter' in item):
            latest_bal_entry = item
    if latest_bal_entry:
        if 'balanceAfter' in latest_bal_entry:
            out['balance'] = _wallet_float(latest_bal_entry.get('balanceAfter'))
        if 'holdAfter' in latest_bal_entry:
            _set_wallet_hold(out, latest_bal_entry.get('holdAfter'))
    out['updatedAt'] = max(str(cw.get('updatedAt') or ''), str(lw.get('updatedAt') or ''), str(out.get('updatedAt') or ''))
    return out


def _merge_money_source_of_truth(candidate, latest):
    """Protect wallet/payment/withdrawal/entry data during any legacy root save."""
    if not isinstance(candidate, dict) or not isinstance(latest, dict):
        return candidate
    candidate.setdefault('wallets', {})
    latest_wallets = latest.get('wallets', {}) if isinstance(latest.get('wallets', {}), dict) else {}
    cand_wallets = candidate.get('wallets', {}) if isinstance(candidate.get('wallets', {}), dict) else {}
    for uid, live_wallet in latest_wallets.items():
        cand_wallets[uid] = _merge_wallet_record(cand_wallets.get(uid), live_wallet)
    candidate['wallets'] = cand_wallets
    for key in ('walletTransactions', 'payments', 'withdrawals', 'entries', 'paymentOutbox'):
        candidate[key] = _merge_list_by_id(candidate.get(key, []), latest.get(key, []))
        if key == 'walletTransactions' and len(candidate[key]) > 2000:
            candidate[key] = candidate[key][-2000:]
        if key == 'paymentOutbox' and len(candidate[key]) > 500:
            candidate[key] = candidate[key][-500:]
    # Preserve idempotency lock table so duplicate retries cannot be re-applied by old saves.
    cand_idem = candidate.get('moneyIdempotency', {}) if isinstance(candidate.get('moneyIdempotency'), dict) else {}
    live_idem = latest.get('moneyIdempotency', {}) if isinstance(latest.get('moneyIdempotency'), dict) else {}
    cand_idem.update(live_idem)
    candidate['moneyIdempotency'] = cand_idem
    candidate.setdefault('moneyAtomicityGuard', {})['lastMergedAt'] = _now_iso_local()
    candidate['moneyAtomicityGuard']['mode'] = 'v9-protect-money-before-root-save'
    return candidate


def _money_prune_idempotency(state_obj):
    table = state_obj.get('moneyIdempotency', {}) if isinstance(state_obj.get('moneyIdempotency'), dict) else {}
    now_ms = int(time.time() * 1000)
    ttl_ms = int(os.environ.get('TITAN_MONEY_IDEMPOTENCY_TTL_MS', str(24 * 60 * 60 * 1000)))
    cleaned = {}
    for k, v in table.items():
        if not isinstance(v, dict):
            continue
        created = int(v.get('createdMs') or 0)
        if created and now_ms - created > ttl_ms:
            continue
        cleaned[str(k)[:180]] = v
    if len(cleaned) > 1000:
        newest = sorted(cleaned.items(), key=lambda kv: int((kv[1] or {}).get('createdMs') or 0))[-1000:]
        cleaned = dict(newest)
    state_obj['moneyIdempotency'] = cleaned


def _money_idempotency_key(scope, data, fields=None, bucket_seconds=10):
    explicit = (request.headers.get('X-Idempotency-Key') or request.headers.get('X-Titan-Idempotency-Key') or (data or {}).get('idempotencyKey') or (data or {}).get('clientTxnId') or '').strip()
    if explicit:
        return f"{scope}:client:{explicit}"[:180]
    fields = fields or []
    stable = {k: (data or {}).get(k) for k in fields}
    bucket = int(time.time() // max(1, int(bucket_seconds or 10)))
    raw = json.dumps({'scope': scope, 'stable': stable, 'bucket': bucket}, sort_keys=True, default=str)
    return f"{scope}:auto:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _money_atomic_commit(scope, data, fields, mutator, retries=8):
    idem_key = _money_idempotency_key(scope, data or {}, fields)
    last_error = None
    for attempt in range(max(1, int(retries))):
        try:
            state, etag = _firebase_get_root_with_etag()
            if not isinstance(state, dict):
                state = {}
            # v36: money actions must not initialize/overwrite an empty Firebase root.
            if not state and not _firebase_allow_empty_init():
                return {"status": "blocked", "message": "Firebase root empty/unreadable. Money save blocked to avoid data reset.", "firebaseDataGuard": True, "version": FIREBASE_DATA_GUARD_VERSION}, 409
            _ensure_foundation_state(state)
            table = state.setdefault('moneyIdempotency', {})
            if idem_key in table and isinstance(table.get(idem_key), dict):
                rec = table[idem_key]
                resp = _runtime_deepcopy(rec.get('response') or {"status": "success"})
                resp['idempotentReplay'] = True
                resp['moneyAtomicity'] = True
                resp['version'] = MONEY_ATOMICITY_VERSION
                return resp, int(rec.get('httpStatus') or 200)
            try:
                resp, http_status = mutator(state)
            except _MoneyAbort as e:
                return e.payload, e.status_code
            if not isinstance(resp, dict):
                resp = {"status": "success", "result": resp}
            resp['moneyAtomicity'] = True
            resp['version'] = MONEY_ATOMICITY_VERSION
            table[idem_key] = {
                'scope': scope,
                'createdAt': _now_iso_local(),
                'createdMs': int(time.time() * 1000),
                'response': _runtime_deepcopy(resp),
                'httpStatus': int(http_status or 200)
            }
            _money_prune_idempotency(state)
            if '_merge_ledger_records_source_of_truth' in globals():
                live_now, _ = _firebase_get_root_with_etag()
                if isinstance(live_now, dict):
                    _merge_ledger_schedules_source_of_truth(state, live_now)
                    _merge_ledger_records_source_of_truth(state, live_now)
                    _preserve_server_ledger_auto_marks(state, live_now)
            report = _runtime_state_validation_report(state, None)
            if not report.get('ok'):
                return {"status": "blocked", "message": "Money atomic save blocked by runtime guard", "report": report, "moneyAtomicity": True}, 409
            if _firebase_put_root_if_match(state, etag):
                try:
                    _write_state_backup(state, f"money_atomic_{scope}")
                except Exception:
                    pass
                return resp, int(http_status or 200)
            last_error = 'etag_conflict'
            time.sleep(0.08 * (attempt + 1))
        except Exception as e:
            last_error = str(e)
            time.sleep(0.12 * (attempt + 1))
    return {"status": "conflict", "message": "Parallel money update detect hua. Please retry.", "moneyAtomicity": True, "version": MONEY_ATOMICITY_VERSION, "lastError": last_error}, 409


def _json_money_response(resp_status_tuple):
    resp, code = resp_status_tuple
    return jsonify(resp), code

MARKETS = [
    {"n": "SRIDEV DAY OPEN", "hr": 11, "min": 35}, {"n": "SRIDEV DAY CLOSE", "hr": 12, "min": 35},
    {"n": "TIME BAZAR OPEN", "hr": 13, "min": 0}, {"n": "MADHUR DAY OPEN", "hr": 13, "min": 15},
    {"n": "TIME BAZAR CLOSE", "hr": 14, "min": 0}, {"n": "MADHUR DAY CLOSE", "hr": 14, "min": 15},
    {"n": "MILAN DAY OPEN", "hr": 15, "min": 0}, {"n": "RAJDHANI DAY OPEN", "hr": 15, "min": 5},
    {"n": "SUPREME DAY OPEN", "hr": 15, "min": 35}, {"n": "KALYAN OPEN", "hr": 15, "min": 50},
    {"n": "MILAN DAY CLOSE", "hr": 17, "min": 0}, {"n": "RAJDHANI DAY CLOSE", "hr": 17, "min": 5},
    {"n": "SUPREME DAY CLOSE", "hr": 17, "min": 35}, {"n": "KALYAN CLOSE", "hr": 17, "min": 50},
    {"n": "SRIDEVI NIGHT OPEN", "hr": 19, "min": 0}, {"n": "SRIDEVI NIGHT CLOSE", "hr": 20, "min": 0},
    {"n": "MADHUR NIGHT OPEN", "hr": 20, "min": 30}, {"n": "SUPREME NIGHT OPEN", "hr": 20, "min": 45},
    {"n": "MILAN NIGHT OPEN", "hr": 21, "min": 0}, {"n": "KALYAN NIGHT OPEN", "hr": 21, "min": 25},
    {"n": "RAJDHANI NIGHT OPEN", "hr": 21, "min": 35}, {"n": "MAIN BAZAR OPEN", "hr": 21, "min": 40},
    {"n": "MADHUR NIGHT CLOSE", "hr": 22, "min": 30}, {"n": "SUPREME NIGHT CLOSE", "hr": 22, "min": 45},
    {"n": "MILAN NIGHT CLOSE", "hr": 23, "min": 0}, {"n": "KALYAN NIGHT CLOSE", "hr": 23, "min": 35},
    {"n": "RAJDHANI NIGHT CLOSE", "hr": 23, "min": 45}, {"n": "MAIN BAZAR CLOSE", "hr": 0, "min": 5}
]

BASE_MARKETS = [
    {"n": "SRIDEV DAY"}, {"n": "TIME BAZAR"}, {"n": "MADHUR DAY"}, {"n": "MILAN DAY"},
    {"n": "RAJDHANI DAY"}, {"n": "SUPREME DAY"}, {"n": "KALYAN"}, {"n": "SRIDEVI NIGHT"},
    {"n": "MADHUR NIGHT"}, {"n": "SUPREME NIGHT"}, {"n": "MILAN NIGHT"}, {"n": "KALYAN NIGHT"},
    {"n": "RAJDHANI NIGHT"}, {"n": "MAIN BAZAR"}
]

RESULT_SOURCE_NAME = "SattaMatkaDpboss.Mobi"
RESULT_SOURCE_URL = "https://sattamatkadpboss.mobi/"

SAFE_UPDATE_VERSION = "2026-06-30-safe-update-guard-v1"
SAFE_UPDATE_PROTECTED_FEATURES = [
    {"key": "whatsapp_login", "name": "WhatsApp Easy Login", "critical": True},
    {"key": "auto_profile_admin_approval", "name": "New User Auto Profile + Admin Approval", "critical": True},
    {"key": "ledger_daily_repeat", "name": "Ledger Daily Repeat Schedule", "critical": True},
    {"key": "ledger_duplicate_lock", "name": "Ledger Duplicate Send Lock", "critical": True},
    {"key": "withdrawal_flow", "name": "Withdrawal Request / Approve / Pay Now / Mark Paid", "critical": True},
    {"key": "wallet_audit", "name": "Wallet Transaction History / Audit", "critical": True},
    {"key": "target_picker", "name": "Advanced Target Picker", "critical": False},
    {"key": "whatsapp_safety_guard", "name": "WhatsApp Safe Messaging Guard", "critical": True},
    {"key": "result_source", "name": "SattaMatkaDpboss.Mobi Result Source", "critical": True},
    {"key": "strict_open_close", "name": "Strict Open/Close Fresh Result Safety", "critical": True},
]

# Ledger/card scrape links now use the same approved source domain.
# Old .co/.net result sources are intentionally removed to avoid mixed/wrong data.
CHART_LINKS = [
    {"n": "SRIDEV DAY", "l": "https://sattamatkadpboss.mobi/record/sridevi-satta-penal-chart.php"},
    {"n": "TIME BAZAR", "l": "https://sattamatkadpboss.mobi/time-bazar-panel-chart.php"},
    {"n": "MADHUR DAY", "l": "https://sattamatkadpboss.mobi/madhur-day-panel-chart.php"},
    {"n": "MILAN DAY", "l": "https://sattamatkadpboss.mobi/record/milan-day-penal-chart.php"},
    {"n": "RAJDHANI DAY", "l": "https://sattamatkadpboss.mobi/record/rajdhani-day-penal-chart.php"},
    {"n": "SUPREME DAY", "l": "https://sattamatkadpboss.mobi/supreme-day-panel-chart.php"},
    {"n": "KALYAN", "l": "https://sattamatkadpboss.mobi/record/kalyan-penal-chart.php"},
    {"n": "SRIDEVI NIGHT", "l": "https://sattamatkadpboss.mobi/record/sridevi-night-satta-penal-chart.php"},
    {"n": "MADHUR NIGHT", "l": "https://sattamatkadpboss.mobi/madhur-night-panel-chart.php"},
    {"n": "SUPREME NIGHT", "l": "https://sattamatkadpboss.mobi/supreme-night-panel-chart.php"},
    {"n": "MILAN NIGHT", "l": "https://sattamatkadpboss.mobi/record/milan-night-penal-chart.php"},
    {"n": "KALYAN NIGHT", "l": "https://sattamatkadpboss.mobi/record/kalyan-night-penal-chart.php"},
    {"n": "RAJDHANI NIGHT", "l": "https://sattamatkadpboss.mobi/record/rajdhani-night-penal-chart.php"},
    {"n": "MAIN BAZAR", "l": "https://sattamatkadpboss.mobi/main-bazar-panel-chart.php"}
]


# ==========================================================
# MARKET MANAGER PHASE 1: CENTRAL MARKET REGISTRY
# Single source of truth for Ledger/Results market visibility + website mapping.
# Existing records keep their old market names; disabling hides future use only.
# ==========================================================
MARKET_MANAGER_PHASE1_REGISTRY = True
MARKET_REGISTRY_VERSION = "2026-06-30-market-registry-phase3-v1"
MARKET_MANAGER_PHASE2_WEBSITE_TOOLS = True
MARKET_MANAGER_PHASE3_DEEP_INTEGRATION = True
MARKET_MANAGER_MANUAL_SAVE_LOCK = True
MARKET_TIME_LOOP_ORDER_VERSION = "2026-07-03-market-time-loop-v46"
TITAN_MARKET_DAY_START_MINUTES = 6 * 60
TITAN_START_MARKET_ALIASES = {
    'SRIDEV DAY', 'SRIDEVI DAY', 'SRIDEVI', 'SRIDEV'
}

def _market_norm_name_for_order(value):
    raw = ' '.join(str(value or '').strip().upper().split())
    raw = raw.replace('SRIDEVI DAY', 'SRIDEV DAY')
    return raw

def _market_item_base_name(item):
    if isinstance(item, dict):
        name = item.get('displayName') or item.get('name') or item.get('websiteName') or ''
    else:
        name = str(item or '')
    return _market_norm_name_for_order(name)

def _market_is_start_market_name(name):
    n = _market_norm_name_for_order(name)
    return n in TITAN_START_MARKET_ALIASES or n.startswith('SRIDEV DAY')

def _market_order_minutes_from_hhmm(value):
    try:
        raw = str(value or '').strip()
        if ':' not in raw:
            return 99999
        h, mi = [int(x) for x in raw.split(':')[:2]]
        if h < 0 or h > 23 or mi < 0 or mi > 59:
            return 99999
        total = h * 60 + mi
        if total < TITAN_MARKET_DAY_START_MINUTES:
            total += 1440
        return total
    except Exception:
        return 99999

def _market_item_primary_order_minutes(item):
    item = item or {}
    stages = item.get('stages') if isinstance(item.get('stages'), dict) else {}
    times = item.get('times') if isinstance(item.get('times'), dict) else {}
    candidates = []
    if stages.get('open', True) and times.get('open'):
        candidates.append(_market_order_minutes_from_hhmm(times.get('open')))
    if stages.get('close', True) and times.get('close'):
        candidates.append(_market_order_minutes_from_hhmm(times.get('close')))
    candidates = [x for x in candidates if x != 99999]
    return min(candidates) if candidates else 99999

def _market_item_time_loop_sort_key(item):
    name = _market_item_base_name(item)
    start_bucket = 0 if _market_is_start_market_name(name) else 1
    return (start_bucket, _market_item_primary_order_minutes(item), name)

def _market_stage_card_base_name(market_name):
    n = _market_norm_name_for_order(market_name)
    for suffix in (' OPEN', ' CLOSE'):
        if n.endswith(suffix):
            return n[:-len(suffix)].strip()
    return n

def _market_stage_card_time_loop_sort_key(market):
    name = str((market or {}).get('n') or '')
    base = _market_stage_card_base_name(name)
    start_bucket = 0 if _market_is_start_market_name(base) else 1
    try:
        h = int((market or {}).get('hr', 0))
        mi = int((market or {}).get('min', 0))
        total = h * 60 + mi
        if total < TITAN_MARKET_DAY_START_MINUTES:
            total += 1440
    except Exception:
        total = 99999
    return (start_bucket, total, name)

def _market_resequence_sort_orders(registry):
    """Keep saved registry sortOrder aligned with the visible time-loop order.

    This makes every section use the same order: SRIDEVI DAY first, then the
    rest by open/close time from the 06:00 business-day loop.
    """
    if not isinstance(registry, dict):
        return registry
    items = registry.get('items') if isinstance(registry.get('items'), dict) else {}
    rows = [x for x in items.values() if isinstance(x, dict) and x.get('deleted') is not True and x.get('archived') is not True]
    rows.sort(key=_market_item_time_loop_sort_key)
    for idx, item in enumerate(rows):
        item['sortOrder'] = (idx + 1) * 10
    registry['timeLoopOrderVersion'] = MARKET_TIME_LOOP_ORDER_VERSION
    return registry

def _market_slug(name):
    raw = str(name or "").strip().upper()
    raw = raw.replace("SRIDEVI DAY", "SRIDEV DAY")
    out = ''.join(ch.lower() if ch.isalnum() else '_' for ch in raw)
    while '__' in out:
        out = out.replace('__', '_')
    return out.strip('_') or 'market_' + uuid.uuid4().hex[:8]

def _market_stage_time(base_name, stage):
    target = f"{str(base_name or '').strip().upper()} {str(stage or '').strip().upper()}"
    for m in MARKETS:
        if str(m.get('n','')).strip().upper() == target:
            return f"{int(m.get('hr',0)):02d}:{int(m.get('min',0)):02d}"
    return ""

def _market_chart_link(base_name):
    raw = str(base_name or '').strip().upper()
    for link in CHART_LINKS:
        if str(link.get('n','')).strip().upper() == raw:
            return link.get('l') or ''
    return ''

def _default_market_registry():
    items = {}
    for order, bm in enumerate(BASE_MARKETS):
        name = str(bm.get('n') or '').strip().upper()
        if not name:
            continue
        mid = _market_slug(name)
        open_time = _market_stage_time(name, 'OPEN')
        close_time = _market_stage_time(name, 'CLOSE')
        items[mid] = {
            "id": mid,
            "name": name,
            "displayName": name,
            "websiteName": name.replace('SRIDEV DAY', 'SRIDEVI'),
            "aliases": [name, name.replace('SRIDEV DAY', 'SRIDEVI DAY')],
            "enabled": True,
            "ledgerEnabled": True,
            "resultEnabled": True,
            "autoResultEnabled": True,
            "autoPassFailEnabled": True,
            "scheduleEnabled": True,
            "entryEnabled": True,
            "entryTargets": [],
            "scheduleTargets": [],
            "resultTargets": [],
            "forwardTargets": [],
            "bookieTargets": [],
            "sortOrder": order * 10,
            "stages": {"open": bool(open_time), "close": bool(close_time)},
            "times": {"open": open_time, "close": close_time},
            "chartUrl": _market_chart_link(name),
            "createdAt": _now_iso_local() if '_now_iso_local' in globals() else "",
            "updatedAt": _now_iso_local() if '_now_iso_local' in globals() else "",
            "archived": False,
            "hardDeleteAllowed": False
        }
    return {"version": MARKET_REGISTRY_VERSION, "items": items, "deletedMarketIds": [], "updatedAt": _now_iso_local() if '_now_iso_local' in globals() else ""}

def _apply_market_manual_save_lock(item, source='manual_registry_save', locked_at=None):
    """Mark a saved market setting as manual-change-only.

    Website scans/imports may discover new names, but saved registry rows must not
    be overwritten by automatic website refreshes. The admin can still edit the
    row in Market Manager and press Save Registry again, which refreshes
    lastManualSaveAt while preserving old ledgers/results.
    """
    if not isinstance(item, dict):
        return item
    stamp = locked_at or (_now_iso_local() if '_now_iso_local' in globals() else '')
    item['settingsLocked'] = True
    item['manualSaveLocked'] = True
    item['manualChangeOnly'] = True
    item['lockedAfterSave'] = True
    item['settingsLockSource'] = source
    if not item.get('settingsLockedAt'):
        item['settingsLockedAt'] = stamp
    item['lastManualSaveAt'] = stamp
    return item

def _normalize_market_registry(registry):
    default = _default_market_registry()
    if not isinstance(registry, dict):
        registry = {}
    items = registry.get('items') if isinstance(registry.get('items'), dict) else {}
    deleted_ids = set()
    if isinstance(registry.get('deletedMarketIds'), list):
        deleted_ids = {str(x).strip() for x in registry.get('deletedMarketIds') if str(x).strip()}
    # Add missing defaults without overwriting admin choices. Deleted defaults stay removed from UI.
    for mid, item in default.get('items', {}).items():
        if mid in deleted_ids:
            continue
        if mid not in items or not isinstance(items.get(mid), dict):
            items[mid] = item
        else:
            for k, v in item.items():
                if k not in items[mid]:
                    items[mid][k] = v
            if not isinstance(items[mid].get('stages'), dict):
                items[mid]['stages'] = item.get('stages', {"open": True, "close": True})
            else:
                items[mid]['stages'].setdefault('open', item.get('stages', {}).get('open', True))
                items[mid]['stages'].setdefault('close', item.get('stages', {}).get('close', True))
            if not isinstance(items[mid].get('times'), dict):
                items[mid]['times'] = item.get('times', {"open":"", "close":""})
            else:
                items[mid]['times'].setdefault('open', item.get('times', {}).get('open', ''))
                items[mid]['times'].setdefault('close', item.get('times', {}).get('close', ''))
    # Clean custom items.
    cleaned = {}
    for raw_id, raw in list(items.items()):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get('name') or raw.get('displayName') or raw_id).strip().upper()
        if not name:
            continue
        mid = str(raw.get('id') or raw_id or _market_slug(name)).strip() or _market_slug(name)
        item = dict(raw)
        item['id'] = mid
        item['name'] = name
        item['displayName'] = str(item.get('displayName') or name).strip().upper()
        item['websiteName'] = str(item.get('websiteName') or name).strip().upper()
        item['enabled'] = bool(item.get('enabled', True))
        item['ledgerEnabled'] = bool(item.get('ledgerEnabled', True))
        item['resultEnabled'] = bool(item.get('resultEnabled', True))
        item['autoResultEnabled'] = bool(item.get('autoResultEnabled', True))
        item['autoPassFailEnabled'] = bool(item.get('autoPassFailEnabled', True))
        item['scheduleEnabled'] = bool(item.get('scheduleEnabled', True))
        item['entryEnabled'] = bool(item.get('entryEnabled', True))
        item['entryTargets'] = _clean_market_target_list(item.get('entryTargets') or item.get('targets') or []) if '_clean_market_target_list' in globals() else (item.get('entryTargets') if isinstance(item.get('entryTargets'), list) else [])
        item['scheduleTargets'] = _clean_market_target_list(item.get('scheduleTargets') or []) if '_clean_market_target_list' in globals() else (item.get('scheduleTargets') if isinstance(item.get('scheduleTargets'), list) else [])
        item['resultTargets'] = _clean_market_target_list(item.get('resultTargets') or []) if '_clean_market_target_list' in globals() else (item.get('resultTargets') if isinstance(item.get('resultTargets'), list) else [])
        item['forwardTargets'] = _clean_market_target_list(item.get('forwardTargets') or []) if '_clean_market_target_list' in globals() else (item.get('forwardTargets') if isinstance(item.get('forwardTargets'), list) else [])
        item['bookieTargets'] = _clean_market_target_list(item.get('bookieTargets') or item.get('adminTargets') or []) if '_clean_market_target_list' in globals() else (item.get('bookieTargets') if isinstance(item.get('bookieTargets'), list) else [])
        item['archived'] = bool(item.get('archived', False))
        item['deleted'] = bool(item.get('deleted', False))
        if item.get('deleted'):
            deleted_ids.add(mid)
            item['enabled'] = False
            item['ledgerEnabled'] = False
            item['resultEnabled'] = False
            item['autoResultEnabled'] = False
            item['autoPassFailEnabled'] = False
            item['scheduleEnabled'] = False
            item['entryEnabled'] = False
            # Keep archived false so hidden ledger placeholders preserve old index-based records.
            item['archived'] = False
            if not item.get('deletedAt'):
                item['deletedAt'] = _now_iso_local() if '_now_iso_local' in globals() else ''
        if item.get('deletedAt'):
            item['deletedAt'] = str(item.get('deletedAt'))
        item['settingsLocked'] = bool(item.get('settingsLocked', item.get('manualSaveLocked', False)))
        item['manualSaveLocked'] = bool(item.get('manualSaveLocked', item.get('settingsLocked', False)))
        item['manualChangeOnly'] = bool(item.get('manualChangeOnly', item.get('settingsLocked', False)))
        item['lockedAfterSave'] = bool(item.get('lockedAfterSave', item.get('settingsLocked', False)))
        if item.get('settingsLockSource'):
            item['settingsLockSource'] = str(item.get('settingsLockSource'))
        if item.get('settingsLockedAt'):
            item['settingsLockedAt'] = str(item.get('settingsLockedAt'))
        if item.get('lastManualSaveAt'):
            item['lastManualSaveAt'] = str(item.get('lastManualSaveAt'))
        if not isinstance(item.get('stages'), dict): item['stages'] = {"open": True, "close": True}
        item['stages']['open'] = bool(item['stages'].get('open', True))
        item['stages']['close'] = bool(item['stages'].get('close', True))
        if not isinstance(item.get('times'), dict): item['times'] = {"open":"", "close":""}
        item['times']['open'] = _normalize_hhmm(item['times'].get('open')) if '_normalize_hhmm' in globals() else str(item['times'].get('open') or '')
        item['times']['close'] = _normalize_hhmm(item['times'].get('close')) if '_normalize_hhmm' in globals() else str(item['times'].get('close') or '')
        try: item['sortOrder'] = int(item.get('sortOrder', 9999))
        except Exception: item['sortOrder'] = 9999
        cleaned[mid] = item
    registry['version'] = MARKET_REGISTRY_VERSION
    registry['items'] = cleaned
    registry['deletedMarketIds'] = sorted([x for x in deleted_ids if x])
    registry.setdefault('updatedAt', _now_iso_local() if '_now_iso_local' in globals() else '')
    registry['marketManagerPhase1'] = True
    registry['marketManagerDeleteSupport'] = True
    registry['marketTimeLoopOrder'] = True
    _market_resequence_sort_orders(registry)
    return registry


def _clean_market_target_list(targets):
    if isinstance(targets, str):
        targets = [x.strip() for x in targets.replace('\n', ',').split(',') if x.strip()]
    if not isinstance(targets, list):
        return []
    out = []
    for t in targets:
        raw = t
        if isinstance(t, dict):
            raw = t.get('id') or t.get('jid') or t.get('target') or t.get('phone') or t.get('number') or t.get('value') or ''
        cleaned = _clean_whatsapp_target(raw) if '_clean_whatsapp_target' in globals() else str(raw or '').strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out

def _market_entry_keys(item):
    if not isinstance(item, dict):
        return []
    base_names = []
    for k in ('name', 'displayName', 'websiteName'):
        v = ' '.join(str(item.get(k) or '').strip().upper().split())
        if v and v not in base_names:
            base_names.append(v)
    keys = []
    stages = item.get('stages') if isinstance(item.get('stages'), dict) else {}
    times = item.get('times') if isinstance(item.get('times'), dict) else {}
    for b in base_names:
        if b not in keys: keys.append(b)
        if stages.get('open', True) and times.get('open'):
            k = b + ' OPEN'
            if k not in keys: keys.append(k)
        if stages.get('close', True) and times.get('close'):
            k = b + ' CLOSE'
            if k not in keys: keys.append(k)
    return keys

def _sync_market_entry_target_settings(state_obj, item):
    if not isinstance(state_obj, dict) or not isinstance(item, dict):
        return
    entry = state_obj.setdefault('entrySettings', _default_entry_settings() if '_default_entry_settings' in globals() else {})
    targets_map = entry.setdefault('marketTargets', {})
    enabled_map = entry.setdefault('marketEntryEnabled', {})
    targets = _clean_market_target_list(item.get('entryTargets') or [])
    enabled = item.get('entryEnabled', True) is not False
    for key in _market_entry_keys(item):
        enabled_map[key] = enabled
        if targets:
            targets_map[key] = targets
        elif key not in targets_map:
            targets_map[key] = []

def _ensure_market_registry(state_obj):
    if not isinstance(state_obj, dict):
        return _default_market_registry()
    state_obj['marketRegistry'] = _normalize_market_registry(state_obj.get('marketRegistry'))
    # Keep entry close times synced for enabled ledger markets without deleting old custom values.
    entry = state_obj.setdefault('entrySettings', _default_entry_settings() if '_default_entry_settings' in globals() else {})
    close_times = entry.setdefault('marketCloseTimes', {})
    for m in _market_arrays_from_registry(state_obj['marketRegistry'], purpose='ledger')[0]:
        name = m.get('n')
        close_times.setdefault(name, f"{int(m.get('hr',0)):02d}:{int(m.get('min',0)):02d}")
    try:
        for item in (state_obj['marketRegistry'].get('items') or {}).values():
            _sync_market_entry_target_settings(state_obj, item)
    except Exception:
        pass
    return state_obj['marketRegistry']

def _market_registry_items(registry, purpose='ledger', include_disabled=False):
    reg = _normalize_market_registry(registry)
    rows = list((reg.get('items') or {}).values())
    def allowed(item):
        if item.get('deleted'):
            return False
        if include_disabled:
            return True
        if item.get('archived'):
            return False
        if not item.get('enabled', True):
            return False
        if purpose == 'ledger' and not item.get('ledgerEnabled', True):
            return False
        if purpose == 'result' and not item.get('resultEnabled', True):
            return False
        if purpose == 'schedule' and not item.get('scheduleEnabled', True):
            return False
        if purpose == 'autopf' and not item.get('autoPassFailEnabled', True):
            return False
        return True
    rows = [x for x in rows if allowed(x)]
    rows.sort(key=_market_item_time_loop_sort_key)
    return rows

def _ledger_market_time_sort_key(market):
    """Canonical OPEN/CLOSE card order: SRIDEVI DAY first, then time loop."""
    return _market_stage_card_time_loop_sort_key(market)


def _market_arrays_from_registry(registry, purpose='ledger'):
    # For ledger/schedule we keep disabled markets in the array with hidden flags so
    # old index-based dayRecords and ledgerSchedules do not shift/break.
    if purpose in ('ledger', 'schedule'):
        reg = _normalize_market_registry(registry)
        rows = [x for x in (reg.get('items') or {}).values() if isinstance(x, dict) and not x.get('archived')]
        rows.sort(key=_market_item_time_loop_sort_key)
    else:
        rows = _market_registry_items(registry, purpose=purpose)
    markets = []
    bases = []
    for item in rows:
        name = str(item.get('displayName') or item.get('name') or '').strip().upper()
        if not name:
            continue
        hidden_for_ledger = bool(item.get('deleted') is True or item.get('enabled') is False or item.get('ledgerEnabled') is False or item.get('archived') is True)
        schedule_disabled = bool(item.get('deleted') is True or item.get('enabled') is False or item.get('ledgerEnabled') is False or item.get('scheduleEnabled') is False or item.get('archived') is True)
        bases.append({'n': name, 'id': item.get('id'), 'websiteName': item.get('websiteName',''), 'hiddenForLedger': hidden_for_ledger, 'scheduleDisabled': schedule_disabled, 'enabled': item.get('enabled', True), 'ledgerEnabled': item.get('ledgerEnabled', True), 'resultEnabled': item.get('resultEnabled', True), 'autoPassFailEnabled': item.get('autoPassFailEnabled', True), 'scheduleEnabled': item.get('scheduleEnabled', True)})
        stages = item.get('stages') if isinstance(item.get('stages'), dict) else {}
        times = item.get('times') if isinstance(item.get('times'), dict) else {}
        if stages.get('open', True):
            t = _normalize_hhmm(times.get('open')) if '_normalize_hhmm' in globals() else (times.get('open') or '')
            h, mi = (0, 0)
            if t and ':' in t:
                h, mi = [int(x) for x in t.split(':')]
            markets.append({'n': f'{name} OPEN', 'hr': h, 'min': mi, 'id': item.get('id'), 'stage': 'open', 'websiteName': item.get('websiteName',''), 'hiddenForLedger': hidden_for_ledger, 'scheduleDisabled': schedule_disabled, 'enabled': item.get('enabled', True), 'ledgerEnabled': item.get('ledgerEnabled', True), 'resultEnabled': item.get('resultEnabled', True), 'autoPassFailEnabled': item.get('autoPassFailEnabled', True), 'scheduleEnabled': item.get('scheduleEnabled', True)})
        if stages.get('close', True):
            t = _normalize_hhmm(times.get('close')) if '_normalize_hhmm' in globals() else (times.get('close') or '')
            h, mi = (0, 0)
            if t and ':' in t:
                h, mi = [int(x) for x in t.split(':')]
            markets.append({'n': f'{name} CLOSE', 'hr': h, 'min': mi, 'id': item.get('id'), 'stage': 'close', 'websiteName': item.get('websiteName',''), 'hiddenForLedger': hidden_for_ledger, 'scheduleDisabled': schedule_disabled, 'enabled': item.get('enabled', True), 'ledgerEnabled': item.get('ledgerEnabled', True), 'resultEnabled': item.get('resultEnabled', True), 'autoPassFailEnabled': item.get('autoPassFailEnabled', True), 'scheduleEnabled': item.get('scheduleEnabled', True)})
    markets.sort(key=_ledger_market_time_sort_key)
    return markets, bases

def _chart_links_from_registry(registry):
    out = []
    seen = set()
    for item in _market_registry_items(registry, purpose='ledger'):
        name = str(item.get('displayName') or item.get('name') or '').strip().upper()
        url = str(item.get('chartUrl') or _market_chart_link(item.get('name')) or '').strip()
        if name and url and name not in seen:
            seen.add(name)
            out.append({'n': name, 'l': url})
    return out or CHART_LINKS

def _market_context_for_state(state_obj, purpose='ledger'):
    reg = _ensure_market_registry(state_obj) if isinstance(state_obj, dict) else _default_market_registry()
    mk, bm = _market_arrays_from_registry(reg, purpose=purpose)
    links = _chart_links_from_registry(reg)
    return mk or MARKETS, bm or BASE_MARKETS, links or CHART_LINKS


# ==========================================================
# MARKET MANAGER PHASE 3: DEEP INTEGRATION GUARD
# Core flows must use marketRegistry as the single source of truth.
# Disabled/archived markets are preserved for history but blocked for new result,
# auto-result, auto pass/fail, and schedule sends.
# ==========================================================
def _market_phase3_norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', str(text or '').upper().replace('SRIDEVI DAY', 'SRIDEV DAY'))).strip()

def _market_phase3_split_stage(market_name):
    raw = _market_phase3_norm(market_name)
    if raw.endswith(' OPEN'):
        return raw[:-5].strip(), 'open'
    if raw.endswith(' CLOSE'):
        return raw[:-6].strip(), 'close'
    return raw, ''

def _market_phase3_aliases(item):
    vals = [item.get('name'), item.get('displayName'), item.get('websiteName')]
    if isinstance(item.get('aliases'), list):
        vals += item.get('aliases')
    out = []
    for v in vals:
        n = _market_phase3_norm(v)
        if n and n not in out:
            out.append(n)
        if n == 'SRIDEV DAY' and 'SRIDEVI DAY' not in out:
            out.append('SRIDEVI DAY')
        if n == 'SRIDEVI DAY' and 'SRIDEV DAY' not in out:
            out.append('SRIDEV DAY')
    return out

def _market_phase3_find_item(state_obj, market_name, include_disabled=True):
    reg = _ensure_market_registry(state_obj) if isinstance(state_obj, dict) else _default_market_registry()
    base, stage = _market_phase3_split_stage(market_name)
    items = (reg.get('items') or {}).values()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get('deleted'):
            continue
        if not include_disabled and (item.get('archived') or item.get('enabled') is False):
            continue
        if base in _market_phase3_aliases(item):
            return item, stage
    return None, stage

def _market_phase3_allowed(state_obj, market_name, purpose='result', stage=None):
    item, detected_stage = _market_phase3_find_item(state_obj, market_name, include_disabled=True)
    st = str(stage or detected_stage or '').lower().strip()
    if not item:
        return {'ok': False, 'reason': 'market_not_in_registry', 'market': str(market_name or '').upper(), 'stage': st}
    name = str(item.get('displayName') or item.get('name') or '').upper().strip()
    if item.get('deleted') is True:
        return {'ok': False, 'reason': 'market_deleted', 'market': name, 'stage': st, 'item': item}
    if item.get('archived') is True:
        return {'ok': False, 'reason': 'market_archived', 'market': name, 'stage': st, 'item': item}
    if item.get('enabled') is False:
        return {'ok': False, 'reason': 'market_disabled', 'market': name, 'stage': st, 'item': item}
    if purpose in ('ledger', 'schedule', 'autopf') and item.get('ledgerEnabled') is False:
        return {'ok': False, 'reason': 'ledger_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    if purpose in ('result', 'auto_result', 'autopf') and item.get('resultEnabled') is False:
        return {'ok': False, 'reason': 'result_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    if purpose == 'auto_result' and item.get('autoResultEnabled') is False:
        return {'ok': False, 'reason': 'auto_result_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    if purpose == 'autopf' and item.get('autoPassFailEnabled') is False:
        return {'ok': False, 'reason': 'auto_pf_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    if purpose == 'schedule' and item.get('scheduleEnabled') is False:
        return {'ok': False, 'reason': 'schedule_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    stages = item.get('stages') if isinstance(item.get('stages'), dict) else {}
    if st in ('open', 'close') and stages.get(st, True) is False:
        return {'ok': False, 'reason': f'{st}_stage_disabled_for_market', 'market': name, 'stage': st, 'item': item}
    return {'ok': True, 'reason': '', 'market': name, 'stage': st, 'item': item}

def _market_phase3_registry_health(state_obj):
    reg = _ensure_market_registry(state_obj)
    items = [x for x in (reg.get('items') or {}).values() if isinstance(x, dict)]
    active = [x for x in items if x.get('enabled') is not False and x.get('archived') is not True]
    ledger = [x for x in active if x.get('ledgerEnabled') is not False]
    result = [x for x in active if x.get('resultEnabled') is not False]
    auto_result = [x for x in result if x.get('autoResultEnabled') is not False]
    autopf = [x for x in active if x.get('autoPassFailEnabled') is not False]
    schedule = [x for x in active if x.get('ledgerEnabled') is not False and x.get('scheduleEnabled') is not False]
    missing_web = [str(x.get('displayName') or x.get('name')) for x in result if not str(x.get('websiteName') or '').strip()]
    return {
        'marketManagerPhase3': True,
        'version': MARKET_REGISTRY_VERSION,
        'total': len(items), 'active': len(active), 'ledgerEnabled': len(ledger),
        'resultEnabled': len(result), 'autoResultEnabled': len(auto_result),
        'autoPassFailEnabled': len(autopf), 'scheduleEnabled': len(schedule),
        'missingWebsiteName': missing_web[:50],
        'status': 'safe' if active and ledger and result else 'attention_required'
    }

# ==========================================================
# MARKET MANAGER PHASE 2: WEBSITE MAPPING TOOLS
# Scan SattaMatkaDpboss live result section, test registry mapping,
# and safely import newly found website market names without deleting history.
# ==========================================================
def _market_phase2_decode_entities(text):
    return (str(text or '')
        .replace('&nbsp;', ' ').replace('&NBSP;', ' ')
        .replace('&amp;', '&').replace('&AMP;', '&')
        .replace('&#45;', '-').replace('&ndash;', '-').replace('&mdash;', '-'))

def _market_phase2_html_lines(html):
    text = _market_phase2_decode_entities(html)
    text = re.sub(r'<script[\s\S]*?</script>', ' ', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text, flags=re.I)
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.I)
    text = re.sub(r'</(?:div|p|h[1-6]|li|tr|section|article)>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    return [re.sub(r'\s+', ' ', x).strip() for x in text.split('\n') if re.sub(r'\s+', ' ', x).strip()]

def _market_phase2_norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', str(text or '').upper())).strip()

def _market_phase2_live_slices(lines):
    slices = []
    for i, line in enumerate(lines):
        n = _market_phase2_norm(line)
        if 'LIVE MATKA RESULT' in n or 'WORLD ME SABSE FAST' in n:
            end = min(len(lines), i + 900)
            for j in range(i + 1, end):
                x = _market_phase2_norm(lines[j])
                if any(stop in x for stop in ['CONTACT FOR ANY SUPPORT', 'MEMBER S FORUM', 'SATTA MATKA JODI CHART', 'WEEKLY PANEL', 'OPEN TO CLOSE FREE GAME ZONE', 'GUESSING', 'FIX SINGLE']):
                    end = j
                    break
            slices.append({'start': i + 1, 'end': end, 'label': 'LIVE MATKA RESULT' if 'LIVE MATKA RESULT' in n else 'DPBOSS MAIN RESULT'})
        elif 'LIVE UPDATE' in n:
            end = min(len(lines), i + 80)
            for j in range(i + 1, end):
                x = _market_phase2_norm(lines[j])
                if any(stop in x for stop in ['LIVE MATKA RESULT', 'WORLD ME SABSE FAST', 'PLAY ONLINE MATKA', 'INDIA S BIGGEST']):
                    end = j
                    break
            slices.append({'start': i + 1, 'end': end, 'label': 'LIVE UPDATE'})
    if not slices:
        slices.append({'start': 0, 'end': min(len(lines), 700), 'label': 'TOP SAFE BLOCK'})
    return slices

def _market_phase2_clean_candidate(line):
    raw = _market_phase2_decode_entities(line)
    raw = re.sub(r'\s+', ' ', raw).strip().upper()
    raw = re.sub(r'^(?:\d+\s*)+', '', raw).strip()
    raw = re.split(r'\b(?:LOADING|WAITING|WAIT|HOLIDAY|CLOSED|REFRESH|RESULT|OPEN|CLOSE)\b', raw, 1)[0].strip()
    raw = re.split(r'\s+\d{3}\s*-\s*\d(?:\d\s*-\s*\d{3})?', raw, 1)[0].strip()
    raw = re.sub(r'[^A-Z0-9 &]+', ' ', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    if not raw or len(raw) < 3 or len(raw) > 40:
        return ''
    bad = ['LIVE', 'RESULT', 'UPDATE', 'BOOKING', 'CONTACT', 'FORUM', 'GUESSING', 'CHART', 'MATKA', 'SATTA', 'ONLINE', 'PLAY', 'GAME', 'FREE', 'BIGGEST', 'FASTEST', 'WORLD']
    if any(raw == b or raw.startswith(b + ' ') for b in bad):
        return ''
    if re.fullmatch(r'\d+', raw):
        return ''
    return raw

def _market_phase2_extract_names_from_html(html):
    lines = _market_phase2_html_lines(html)
    names = {}
    for sl in _market_phase2_live_slices(lines):
        for i in range(sl['start'], min(sl['end'], len(lines))):
            line = lines[i]
            # Same-line pattern: MARKET 123-4 / MARKET 123-45-678 / MARKET Loading...
            m = re.match(r'^\s*([A-Z0-9 &]{3,40}?)(?:\s+)(?:\d{3}\s*-\s*\d(?:\d\s*-\s*\d{3})?|Loading\.{0,3}|Wait(?:ing)?|Holiday|Closed)\b', line, flags=re.I)
            cand = _market_phase2_clean_candidate(m.group(1) if m else line)
            if not cand:
                continue
            key = _market_phase2_norm(cand)
            rec = names.setdefault(key, {'name': cand, 'count': 0, 'blocks': [], 'sampleLines': []})
            rec['count'] += 1
            if sl['label'] not in rec['blocks']:
                rec['blocks'].append(sl['label'])
            if len(rec['sampleLines']) < 3:
                rec['sampleLines'].append(line[:180])
    return sorted(names.values(), key=lambda x: (-x.get('count', 0), x.get('name', '')))

def _market_phase2_registry_aliases(item):
    vals = [item.get('name'), item.get('displayName'), item.get('websiteName')]
    vals += item.get('aliases') if isinstance(item.get('aliases'), list) else []
    out = []
    for v in vals:
        n = _market_phase2_norm(v)
        if n and n not in out:
            out.append(n)
    return out

def _market_phase2_mapping_diagnostics(state_obj, html=None):
    reg = _ensure_market_registry(state_obj)
    error = ''
    source_url = RESULT_SOURCE_URL
    if html is None:
        try:
            resp = requests.get(source_url, timeout=12, headers={
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            })
            html = resp.text or ''
            if resp.status_code >= 400:
                error = f'HTTP {resp.status_code}'
        except Exception as e:
            html = ''
            error = str(e)
    found = _market_phase2_extract_names_from_html(html)
    found_map = {_market_phase2_norm(x.get('name')): x for x in found}
    matched = []
    missing = []
    all_alias_to_market = {}
    for item in _market_registry_items(reg, purpose='result', include_disabled=False):
        aliases = _market_phase2_registry_aliases(item)
        for a in aliases:
            all_alias_to_market[a] = item
        match_key = next((a for a in aliases if a in found_map), '')
        if match_key:
            matched.append({'id': item.get('id'), 'name': item.get('displayName') or item.get('name'), 'websiteName': item.get('websiteName'), 'foundName': found_map[match_key].get('name'), 'blocks': found_map[match_key].get('blocks', []), 'status': 'found'})
        else:
            missing.append({'id': item.get('id'), 'name': item.get('displayName') or item.get('name'), 'websiteName': item.get('websiteName'), 'status': 'not_found'})
    unknown = []
    for rec in found:
        n = _market_phase2_norm(rec.get('name'))
        if n and n not in all_alias_to_market:
            unknown.append(rec)
    return {
        'status': 'success' if not error else 'warning',
        'marketManagerPhase2': True,
        'sourceUrl': source_url,
        'error': error,
        'foundMarkets': found,
        'matchedMappings': matched,
        'missingRegistryMappings': missing,
        'unknownWebsiteMarkets': unknown,
        'summary': {'found': len(found), 'matched': len(matched), 'missing': len(missing), 'unknown': len(unknown)},
        'checkedAt': _now_iso_local()
    }

def get_default_config():
    return {"ankSplit": True, "panSplit": True, "capital": 0, "dayTarget": 0, "ank": {"cap": 0, "tgt": 0}, "jodi": {"cap": 0, "tgt": 0}, "pannel": {"cap": 0, "tgt": 0}}

def _now_iso_local():
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(APP_TZ)).isoformat(timespec="seconds")
        except Exception:
            pass
    return datetime.datetime.now().isoformat(timespec="seconds")


# ==========================================================
# USER / VIP ACCOUNT SAFETY v15
# Server-side VIP access enforcement + device/suspicious access tracking.
# This is Firebase-first and uses child-path PATCH/PUT so it cannot overwrite
# wallet/ledger/payment state.
# ==========================================================
def _parse_date_only(value):
    s = str(value or '').strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except Exception:
        return None

def _today_local_date():
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(APP_TZ)).date()
        except Exception:
            pass
    return datetime.date.today()

def _vip_profile_access_report(profile):
    profile = profile or {}
    reasons = []
    approval = str(profile.get('approvalStatus', 'approved') or 'approved').lower()
    if approval == 'pending':
        reasons.append('approval_pending')
    if profile.get('vipAccessEnabled') is False:
        reasons.append('vip_access_disabled')
    exp = _parse_date_only(profile.get('expiryDate'))
    if exp and exp < _today_local_date():
        reasons.append('membership_expired')
    allowed = not reasons
    return {
        'allowed': bool(allowed),
        'reasons': reasons,
        'approvalStatus': approval,
        'vipAccessEnabled': profile.get('vipAccessEnabled', True),
        'expiryDate': profile.get('expiryDate', ''),
        'version': USER_SAFETY_VERSION,
    }

def _vip_block_html(title, message, color='#FF5D5D'):
    return f"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no"><title>{title}</title></head>
<body style="background:#17212B;color:#fff;font-family:sans-serif;text-align:center;padding:50px 20px;">
  <div style="background:#232E3C;border:1px solid {color};padding:30px;border-radius:16px;margin-top:20vh;box-shadow:0 4px 20px rgba(0,0,0,.25);">
    <h2 style="color:{color};margin-top:0;font-weight:900;">{title}</h2>
    <p style="color:#7A9CB8;font-size:14px;margin-bottom:0;line-height:1.5;">{message}</p>
  </div>
</body></html>"""

def _sanitize_device_token(value):
    raw = str(value or '').strip()
    raw = re.sub(r'[^A-Za-z0-9_\-.]', '', raw)[:80]
    if raw:
        return raw
    src = (request.headers.get('User-Agent') or '') + '|' + (request.headers.get('X-Forwarded-For') or request.remote_addr or '')
    return 'auto_' + hashlib.sha256(src.encode('utf-8', 'ignore')).hexdigest()[:24]

def _vip_request_meta(vip_id):
    ua = str(request.headers.get('User-Agent') or '')[:180]
    ip = str((request.headers.get('X-Forwarded-For') or request.remote_addr or '')).split(',')[0].strip()[:80]
    device_id = _sanitize_device_token(request.headers.get('X-Titan-Vip-Device') or request.cookies.get('titan_vip_device'))
    fp = str(request.headers.get('X-Titan-Vip-Fp') or '')[:96]
    return {
        'vipId': str(vip_id or ''),
        'deviceId': device_id,
        'fingerprint': fp,
        'ipHash': hashlib.sha256(ip.encode('utf-8', 'ignore')).hexdigest()[:16] if ip else '',
        'userAgent': ua,
        'path': str(request.path or '')[:120],
        'lastSeenAt': _now_iso_local(),
    }

def _iso_age_seconds(iso_value):
    try:
        dt = datetime.datetime.fromisoformat(str(iso_value or '').replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            now = datetime.datetime.now(dt.tzinfo)
        elif ZoneInfo:
            now = datetime.datetime.now(ZoneInfo(APP_TZ))
            dt = dt.replace(tzinfo=now.tzinfo)
        else:
            now = datetime.datetime.now()
        return max(0, int((now - dt).total_seconds()))
    except Exception:
        return 10**9

def _vip_safety_defaults(state_obj=None):
    defaults = {
        'enabled': True,
        'accessEnforce': bool(TITAN_VIP_ACCESS_ENFORCE),
        'deviceTracking': True,
        'maxDevicesPerVip': int(TITAN_VIP_DEVICE_LIMIT),
        'strictDeviceLimit': bool(TITAN_VIP_DEVICE_STRICT),
        'logThrottleSeconds': int(TITAN_VIP_ACCESS_LOG_THROTTLE_SECONDS),
        'version': USER_SAFETY_VERSION,
    }
    if isinstance(state_obj, dict):
        cfg = state_obj.get('userSafetySettings') if isinstance(state_obj.get('userSafetySettings'), dict) else {}
        merged = dict(defaults)
        merged.update({k: v for k, v in cfg.items() if k in defaults})
        try:
            merged['maxDevicesPerVip'] = max(1, int(merged.get('maxDevicesPerVip') or TITAN_VIP_DEVICE_LIMIT))
        except Exception:
            merged['maxDevicesPerVip'] = int(TITAN_VIP_DEVICE_LIMIT)
        try:
            merged['logThrottleSeconds'] = max(60, int(merged.get('logThrottleSeconds') or TITAN_VIP_ACCESS_LOG_THROTTLE_SECONDS))
        except Exception:
            merged['logThrottleSeconds'] = int(TITAN_VIP_ACCESS_LOG_THROTTLE_SECONDS)
        return merged
    return defaults

def _record_vip_access(state_obj, vip_id, profile=None):
    """Record VIP access/device activity in Firebase child path. Never root-PUT."""
    if not isinstance(state_obj, dict) or not vip_id:
        return {'recorded': False, 'reason': 'bad_state_or_vip'}
    settings = _vip_safety_defaults(state_obj)
    if not settings.get('enabled', True) or not settings.get('deviceTracking', True):
        return {'recorded': False, 'reason': 'disabled'}
    meta = _vip_request_meta(vip_id)
    store = state_obj.get('userSafety') if isinstance(state_obj.get('userSafety'), dict) else {}
    vip_store = store.get(str(vip_id)) if isinstance(store.get(str(vip_id)), dict) else {}
    devices = vip_store.get('devices') if isinstance(vip_store.get('devices'), dict) else {}
    old_dev = devices.get(meta['deviceId']) if isinstance(devices.get(meta['deviceId']), dict) else {}
    age = _iso_age_seconds(old_dev.get('lastSeenAt'))
    if old_dev and age < int(settings.get('logThrottleSeconds') or 300):
        return {'recorded': False, 'throttled': True, 'deviceId': meta['deviceId'], 'ageSeconds': age}
    first_seen = old_dev.get('firstSeenAt') or meta['lastSeenAt']
    devices[meta['deviceId']] = {
        'deviceId': meta['deviceId'],
        'firstSeenAt': first_seen,
        'lastSeenAt': meta['lastSeenAt'],
        'lastPath': meta.get('path'),
        'ipHash': meta.get('ipHash'),
        'fingerprint': meta.get('fingerprint'),
        'userAgent': meta.get('userAgent'),
        'seenCount': int(old_dev.get('seenCount') or 0) + 1,
    }
    max_devices = int(settings.get('maxDevicesPerVip') or TITAN_VIP_DEVICE_LIMIT)
    active_count = len(devices)
    suspicious = active_count > max_devices
    events = vip_store.get('events') if isinstance(vip_store.get('events'), list) else []
    events.append({
        'id': 'vip_access_' + uuid.uuid4().hex[:10],
        'time': meta['lastSeenAt'],
        'vipId': str(vip_id),
        'deviceId': meta['deviceId'],
        'path': meta.get('path'),
        'activeDeviceCount': active_count,
        'suspicious': suspicious,
        'version': USER_SAFETY_VERSION,
    })
    events = events[-80:]
    vip_store.update({
        'vipId': str(vip_id),
        'name': (profile or {}).get('name') if isinstance(profile, dict) else '',
        'phone': (profile or {}).get('phone') if isinstance(profile, dict) else '',
        'lastAccessAt': meta['lastSeenAt'],
        'lastDeviceId': meta['deviceId'],
        'devices': devices,
        'events': events,
        'activeDeviceCount': active_count,
        'suspicious': suspicious,
        'suspiciousReason': 'too_many_devices' if suspicious else '',
        'maxDevicesPerVip': max_devices,
        'version': USER_SAFETY_VERSION,
    })
    try:
        _firebase_put_child(['userSafety', str(vip_id)], vip_store)
        _firebase_patch_child(['profiles', str(vip_id)], {'lastSeenAt': meta['lastSeenAt'], 'lastDeviceId': meta['deviceId'], 'lastAccessPath': meta.get('path')})
        if suspicious and '_obs_event' in globals():
            _obs_event('vip_suspicious_device_count', 'warning', f'VIP {vip_id} has {active_count} devices', {'vipId': str(vip_id), 'activeDeviceCount': active_count, 'maxDevicesPerVip': max_devices})
        return {'recorded': True, 'deviceId': meta['deviceId'], 'activeDeviceCount': active_count, 'suspicious': suspicious}
    except Exception as e:
        if '_obs_exception' in globals():
            _obs_exception('vip_access_record_failed', e, {'vipId': str(vip_id), 'deviceId': meta['deviceId']})
        return {'recorded': False, 'error': str(e)[:160], 'deviceId': meta['deviceId']}

def _vip_runtime_access_check(state_obj, vip_id, record=True):
    profiles = state_obj.get('profiles', {}) if isinstance(state_obj.get('profiles'), dict) else {}
    profile = profiles.get(str(vip_id)) if isinstance(profiles.get(str(vip_id)), dict) else None
    if not profile:
        return {'allowed': False, 'reason': 'vip_not_found', 'reasons': ['vip_not_found'], 'httpStatus': 404}
    report = _vip_profile_access_report(profile)
    if record:
        report['safetyRecord'] = _record_vip_access(state_obj, str(vip_id), profile)
    settings = _vip_safety_defaults(state_obj)
    # Optional strict device limit. Default is monitor-only to avoid locking real users unexpectedly.
    safety = state_obj.get('userSafety', {}).get(str(vip_id), {}) if isinstance(state_obj.get('userSafety'), dict) else {}
    if settings.get('strictDeviceLimit') and isinstance(safety, dict) and safety.get('suspicious'):
        report['allowed'] = False
        report.setdefault('reasons', []).append('device_limit_exceeded')
    report['enforced'] = bool(settings.get('accessEnforce', True))
    report['httpStatus'] = 200 if report.get('allowed') else 403
    return report

def _default_wallet_settings():
    return {
        "defaultCreditLimit": 0,
        "requirePositiveBalance": False,
        "currency": "₹",
        "walletEnabled": True
    }

def _default_risk_settings():
    return {
        "marketDailyLimit": 0,
        "digitDailyLimit": 0,
        "userDailyLimit": 0,
        "warningPercent": 80,
        "autoLockOnLimit": False
    }

def _default_settlement_settings():
    return {
        "enabled": True,
        "includeSummaryInResultMessage": True,
        "includeHitMissInResultMessage": False,
        "autoLedgerMarking": True,
        "autoLedgerMarkOnlyWait": True,
        "autoLedgerApplyToAllProfiles": True,
        "autoLedgerRecordResults": True,
        "payoutMultipliers": {"ank": 9.5, "jodi": 9.5, "penel": 150}
    }

def _default_payment_settings():
    return {
        "paymentAutomationEnabled": True,
        "requireUtr": True,
        "duplicateUtrBlock": True,
        "approveCreditsWallet": True,
        "extendMembershipOnApprove": True,
        "minAmount": 1,
        "maxAmount": 200000,
        "notifyUserPrivate": True
    }

def _default_withdrawal_settings():
    return {
        "enabled": True,
        "minAmount": 1,
        "maxAmount": 200000,
        "onePendingPerUser": True,
        "notifyUserPrivate": True,
        "notifyAdminPrivate": True,
        "adminNotifyTargets": [],
        "allowedMethods": ["upi", "qr", "bank"]
    }

def _default_load_forwarder_settings():
    return {
        "enabled": False,
        "scheduleTime": "18:00",
        "selectedMarket": "",
        "targets": [],
        "gameTypes": ["ANK", "PENEL", "JODI"],
        "maxRowsPerType": 80,
        "includeEmptyTypes": False,
        "lastSentKey": "",
        "lastSentAt": "",
        "lastDelivery": []
    }

def _default_spam_guard_settings():
    return {
        "enabled": True,
        "groupsOnly": True,
        "linkGuardEnabled": True,
        "forwardGuardEnabled": True,
        "deleteMessage": True,
        "kickEnabled": True,
        "exemptAdmins": True,
        "linkStrikeLimit": 3,
        "forwardStrikeLimit": 3,
        "forwardWindowSeconds": 60,
        "alertMessage": "⚠️ *ALERT*\nBhai Group Me Link Dalna Mana he",
        "warningMessage": "⚠️ *WARNING*\nNext Time Group Me Link Daloge To Remove Kiya Jayega Group Se",
        "kickMessage": "🚫 *REMOVED*\n@{number} ko group se remove kiya gaya.\nReason: 3 baar link/forward spam.",
        "forwardAlertMessage": "⚠️ *ALERT*\nBhai Group Me Forward/Spam Message Dalna Mana he",
        "forwardWarningMessage": "⚠️ *WARNING*\nNext Time Multiple Forward Message Daloge To Remove Kiya Jayega Group Se"
    }

def _default_whatsapp_safety_settings():
    return {
        "enabled": True,
        "globalPaused": False,
        "pauseReason": "",
        "requireApprovedTargets": False,
        "minDelayMs": 2500,
        "randomDelayMs": 1200,
        "duplicateBlock": True,
        "duplicateWindowMinutes": 1440,
        "targetFailureLimit": 3,
        "globalConsecutiveFailureLimit": 8,
        "dailyTargetLimit": 80,
        "dailyGlobalLimit": 300,
        "autoPauseTargetOnFailures": True,
        "autoPauseGlobalOnFailures": True,
        "safeModeForGroupsOnly": False,
        "allowPrivateReplies": True,
        "allowAdminNotifications": True,
        "adminAlertTargets": [],
        "updatedAt": ""
    }

def _default_update_guard_settings():
    return {
        "enabled": True,
        "strictMode": True,
        "blockOldResultSources": True,
        "requireSafeUpdateCheck": True,
        "protectedFeatures": [f["key"] for f in SAFE_UPDATE_PROTECTED_FEATURES],
        "lastSafeCheckAt": "",
        "lastSafeCheckStatus": ""
    }

def _normalize_forward_targets(targets):
    if isinstance(targets, str):
        targets = [x.strip() for x in targets.replace('\\n', ',').split(',') if x.strip()]
    if not isinstance(targets, list):
        return []
    out = []
    for t in targets:
        txt = str(t or '').strip()
        if txt and txt not in out:
            out.append(txt)
    return out

def _normalize_game_types(types):
    order = ['ANK', 'PENEL', 'JODI']
    if isinstance(types, str):
        types = [x.strip() for x in types.replace('\\n', ',').split(',') if x.strip()]
    if not isinstance(types, list):
        types = order[:]
    out = []
    for t in types:
        typ = str(t or '').strip().upper()
        if typ in ('PANEL', 'PANNEL'):
            typ = 'PENEL'
        if typ in order and typ not in out:
            out.append(typ)
    return [t for t in order if t in out] or order[:]

def _entry_digits_list(entry):
    d = entry.get('digits', []) if isinstance(entry, dict) else []
    if isinstance(d, list):
        return [str(x).strip() for x in d if str(x).strip()]
    return [x.strip() for x in str(d or '').replace('.', ',').replace(' ', ',').split(',') if x.strip()]

def _build_load_report(state_obj, date=None, market=None, max_rows=80, include_empty=False, game_types=None):
    date = date or _safe_today()
    market = ' '.join(str(market or '').strip().upper().split())
    selected_types = _normalize_game_types(game_types)
    entries = state_obj.get('entries', []) if isinstance(state_obj.get('entries', []), list) else []
    rows = [e for e in entries if isinstance(e, dict) and e.get('status') == 'accepted' and e.get('date') == date]
    if market:
        rows = [e for e in rows if ' '.join(str(e.get('market') or '').upper().split()) == market]
    grouped = {}
    user_sets = {}
    entry_counts = {}
    type_totals = {t: 0.0 for t in selected_types}
    type_entry_counts = {t: 0 for t in selected_types}
    grand_total = 0.0
    included_rows = 0
    for e in rows:
        m = ' '.join(str(e.get('market') or 'UNKNOWN').upper().split())
        typ = str(e.get('gameType') or e.get('type') or 'ANK').upper()
        if typ in ('PANEL', 'PANNEL'):
            typ = 'PENEL'
        if typ not in ['ANK', 'JODI', 'PENEL']:
            typ = 'ANK'
        if typ not in selected_types:
            continue
        rate = _wallet_float(e.get('parDigit', e.get('rate', 0)))
        total = _wallet_float(e.get('total', 0))
        grand_total += total
        type_totals[typ] = round(type_totals.get(typ, 0) + total, 2)
        type_entry_counts[typ] = type_entry_counts.get(typ, 0) + 1
        included_rows += 1
        for d in _entry_digits_list(e):
            digit = str(d).strip()
            if typ == 'JODI':
                digit = digit.zfill(2)
            key = (m, typ, digit)
            grouped[key] = round(grouped.get(key, 0) + rate, 2)
            entry_counts[key] = entry_counts.get(key, 0) + 1
            user_sets.setdefault(key, set()).add(str(e.get('userId') or e.get('senderJid') or e.get('userName') or 'user'))
    markets_found = sorted(set([k[0] for k in grouped.keys()] + ([market] if market else [])))
    report = {
        'date': date,
        'market': market,
        'gameTypes': selected_types,
        'entryCount': included_rows,
        'grandTotal': round(grand_total, 2),
        'typeTotals': {t: round(type_totals.get(t, 0), 2) for t in selected_types},
        'typeEntryCounts': {t: int(type_entry_counts.get(t, 0)) for t in selected_types},
        'markets': []
    }
    for m in markets_found:
        market_obj = {'market': m, 'overallTotal': 0, 'types': []}
        for typ in selected_types:
            items = []
            for (mk, gt, digit), amount in grouped.items():
                if mk == m and gt == typ:
                    items.append({
                        'digit': digit,
                        'amount': round(amount, 2),
                        'entryCount': entry_counts.get((mk, gt, digit), 0),
                        'userCount': len(user_sets.get((mk, gt, digit), set()))
                    })
            items.sort(key=lambda x: (-x['amount'], x['digit']))
            if items or include_empty:
                type_total = round(sum(x['amount'] for x in items), 2)
                market_obj['overallTotal'] = round(market_obj['overallTotal'] + type_total, 2)
                market_obj['types'].append({'type': typ, 'overallTotal': type_total, 'items': items[:max(1, int(max_rows or 80))]})
        report['markets'].append(market_obj)
    return report

def _format_load_report_text(report):
    def money(v):
        try:
            n = float(v or 0)
        except Exception:
            n = 0
        return f"₹{n:g}"
    date = report.get('date') or ''
    market = report.get('market') or 'ALL MARKETS'
    lines = [
        '📊 *TITAN NOVA LOAD REPORT*',
        '━━━━━━━━━━━━━━━━━━━━',
        f'📅 *DATE:* {date}',
        f'🔥 *MARKET:* {market}',
        f'🧾 *ENTRIES:* {report.get("entryCount", 0)}',
        f'💰 *TOTAL LOAD:* {money(report.get("grandTotal", 0))}',
        f'🎮 *GAMES:* {", ".join(report.get("gameTypes") or ["ANK", "PENEL", "JODI"])}',
        '━━━━━━━━━━━━━━━━━━━━'
    ]
    type_totals = report.get('typeTotals') or {}
    type_counts = report.get('typeEntryCounts') or {}
    if type_totals:
        lines.append('')
        lines.append('*GAME TYPE TOTALS*')
        for gt in (report.get('gameTypes') or ['ANK', 'PENEL', 'JODI']):
            lines.append(f'{gt}: {money(type_totals.get(gt, 0))} | Entries: {type_counts.get(gt, 0)}')
    if not report.get('markets'):
        lines.append('Aaj is market me accepted entry load nahi hai.')
        return '\n'.join(lines)
    for mk in report.get('markets', []):
        lines.append(f'\n🔥 *{mk.get("market", "MARKET")}*')
        if not mk.get('types'):
            lines.append('No load.')
            continue
        for typ in mk.get('types', []):
            lines.append(f'\n*{typ.get("type")} LOAD*')
            items = typ.get('items') or []
            if not items:
                lines.append('No load.')
            else:
                for it in items:
                    lines.append(f'{it.get("digit")} = {money(it.get("amount"))} | Users: {it.get("userCount",0)} | Entries: {it.get("entryCount",0)}')
            lines.append(f'{typ.get("type")} Overall: {money(typ.get("overallTotal",0))}')
        lines.append(f'📌 Market Overall: {money(mk.get("overallTotal",0))}')
    return '\n'.join(lines).strip()

def _payment_float(v):
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0

def _normalize_utr(v):
    return ''.join(ch for ch in str(v or '').upper().strip() if ch.isalnum())

def _phone_target_from_profile(profile):
    raw = str((profile or {}).get('phone') or '').strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ''
    if len(digits) == 10:
        digits = '91' + digits
    return digits

def _queue_payment_message(state_obj, user_id, text, meta=None):
    settings = state_obj.get('paymentSettings', _default_payment_settings()) if isinstance(state_obj, dict) else _default_payment_settings()
    if not settings.get('notifyUserPrivate', True):
        return None
    profile = (state_obj.get('profiles', {}) or {}).get(user_id, {}) if isinstance(state_obj, dict) else {}
    target = _phone_target_from_profile(profile)
    if not target or not text:
        return None
    msg = {
        'id': str(uuid.uuid4())[:8].upper(),
        'time': _now_iso_local(),
        'target': target,
        'text': str(text),
        'status': 'pending',
        'attempts': 0,
        'meta': meta or {}
    }
    state_obj.setdefault('paymentOutbox', []).append(msg)
    # Keep queue compact. Sent/failed history is useful but should not grow forever.
    if len(state_obj.get('paymentOutbox', [])) > 300:
        state_obj['paymentOutbox'] = state_obj['paymentOutbox'][-300:]
    return msg

def _clean_whatsapp_target(raw):
    txt = str(raw or '').strip()
    if not txt:
        return ''
    if '@g.us' in txt or '@s.whatsapp.net' in txt:
        return txt
    digits = ''.join(ch for ch in txt if ch.isdigit())
    if not digits:
        return ''
    if len(digits) == 10:
        digits = '91' + digits
    return digits

def _queue_whatsapp_target_message(state_obj, target, text, meta=None):
    target = _clean_whatsapp_target(target)
    if not target or not text:
        return None
    msg = {
        'id': str(uuid.uuid4())[:8].upper(),
        'time': _now_iso_local(),
        'target': target,
        'text': str(text),
        'status': 'pending',
        'attempts': 0,
        'meta': meta or {}
    }
    state_obj.setdefault('paymentOutbox', []).append(msg)
    if len(state_obj.get('paymentOutbox', [])) > 300:
        state_obj['paymentOutbox'] = state_obj['paymentOutbox'][-300:]
    return msg

def _admin_notification_targets(state_obj):
    settings = state_obj.get('withdrawalSettings', _default_withdrawal_settings())
    out = []
    raw = settings.get('adminNotifyTargets', [])
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.replace('\\n', ',').split(',') if x.strip()]
    if isinstance(raw, list):
        for t in raw:
            cleaned = _clean_whatsapp_target(t)
            if cleaned and cleaned not in out:
                out.append(cleaned)
    if not out:
        for uid, profile in (state_obj.get('profiles', {}) or {}).items():
            if str(uid).startswith('admin'):
                target = _phone_target_from_profile(profile)
                if target and target not in out:
                    out.append(target)
    return out

def _wallet_hold_amount(wallet):
    return _wallet_float((wallet or {}).get('hold', (wallet or {}).get('walletHold', 0)))

def _set_wallet_hold(wallet, amount):
    wallet['hold'] = round(max(0, _wallet_float(amount)), 2)
    wallet['walletHold'] = wallet['hold']
    return wallet['hold']

def _withdraw_available(wallet):
    return round(_wallet_float((wallet or {}).get('balance', 0)) - _wallet_hold_amount(wallet), 2)

def _entry_available(wallet):
    return round(_wallet_float((wallet or {}).get('balance', 0)) + _wallet_float((wallet or {}).get('creditLimit', 0)) - _wallet_hold_amount(wallet), 2)

def _next_withdrawal_id(state_obj):
    n = len(state_obj.get('withdrawals', []) if isinstance(state_obj.get('withdrawals', []), list) else []) + 1
    return 'W' + datetime.datetime.now().strftime('%y%m%d') + '-' + str(n).zfill(4)

def _withdrawal_summary_line(wd):
    method = str(wd.get('method') or '-').upper()
    return f"#{wd.get('id')} · {wd.get('userName') or wd.get('userId')} · ₹{_wallet_float(wd.get('amount')):g} · {method}"

def _payment_risk_flag(state_obj, user_id, amount, utr):
    settings = state_obj.get('paymentSettings', _default_payment_settings())
    utr_norm = _normalize_utr(utr)
    if amount < _payment_float(settings.get('minAmount', 1)):
        return 'low_amount'
    if amount > _payment_float(settings.get('maxAmount', 200000)):
        return 'high_amount'
    if settings.get('requireUtr', True) and not utr_norm:
        return 'utr_missing'
    for pmt in state_obj.get('payments', []):
        if _normalize_utr(pmt.get('utr')) and _normalize_utr(pmt.get('utr')) == utr_norm and str(pmt.get('status', '')).lower() != 'rejected':
            return 'duplicate'
    pending_same_user = [pmt for pmt in state_obj.get('payments', []) if pmt.get('userId') == user_id and pmt.get('status') == 'pending']
    if len(pending_same_user) >= 3:
        return 'spam'
    return 'safe'

def _credit_wallet_from_payment(state_obj, payment, note=None):
    user_id = payment.get('userId')
    amount = _payment_float(payment.get('amount', 0))
    if not user_id or amount <= 0:
        return None
    wallet = _ensure_wallet_for_user(state_obj, user_id)
    if wallet is None:
        return None
    before = _wallet_float(wallet.get('balance', 0))
    after = round(before + amount, 2)
    wallet['balance'] = after
    wallet['updatedAt'] = _now_iso_local()
    ledger_entry = {
        'id': str(uuid.uuid4())[:8].upper(),
        'time': _now_iso_local(),
        'type': 'payment_credit',
        'amount': amount,
        'balanceBefore': before,
        'balanceAfter': after,
        'note': note or f"Payment approved #{payment.get('id')}",
        'source': 'payment_automation',
        'paymentId': payment.get('id'),
        'utr': payment.get('utr', '')
    }
    wallet.setdefault('ledger', []).append(ledger_entry)
    _record_wallet_transaction(state_obj, user_id, wallet, ledger_entry)
    payment['walletCredited'] = True
    payment['walletCreditAmount'] = amount
    payment['walletBalanceAfter'] = after
    payment['walletLedgerId'] = ledger_entry['id']
    return wallet

def _default_market_close_times():
    out = {m["n"]: f"{int(m['hr']):02d}:{int(m['min']):02d}" for m in MARKETS}
    for b in BASE_MARKETS:
        name = b["n"]
        close = next((m for m in MARKETS if m["n"] == name + " CLOSE"), None)
        open_m = next((m for m in MARKETS if m["n"] == name + " OPEN"), None)
        if close:
            out[name] = f"{int(close['hr']):02d}:{int(close['min']):02d}"
        elif open_m:
            out[name] = f"{int(open_m['hr']):02d}:{int(open_m['min']):02d}"
    if "SRIDEV DAY" in out and "SRIDEVI DAY" not in out:
        out["SRIDEVI DAY"] = out["SRIDEV DAY"]
    return out

def _compact_market_time_key(value):
    return ''.join(ch for ch in str(value or '').upper().replace('SRIDEVI DAY', 'SRIDEV DAY') if ch.isalnum())

def _canonical_market_time_key(value):
    raw = str(value or '').strip().upper().replace('*', '')
    compact = _compact_market_time_key(raw)
    for item in list(MARKETS) + list(BASE_MARKETS):
        name = str(item.get('n') or '').strip().upper()
        if _compact_market_time_key(name) == compact:
            return name
    return ' '.join(raw.split())

def _normalize_hhmm(value):
    txt = str(value or '').strip()
    parts = txt.split(':')
    if len(parts) != 2:
        return ''
    try:
        h, m = int(parts[0]), int(parts[1])
    except Exception:
        return ''
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return ''

def _default_entry_settings():
    return {
        "entryParserEnabled": True,
        "groupsOnly": True,
        "strictFormat": True,
        "autoDebitWallet": True,
        "marketTimingEnabled": True,
        "riskLimitEnabled": True,
        "autoLinkUnknownSender": True,
        "autoCreatePendingProfiles": True,
        "requireProfileApproval": True,
        "duplicatePolicy": "sender_market_type_digits_date",
        "marketCloseTimes": _default_market_close_times(),
        "marketTargets": {},
        "marketEntryEnabled": {},
        "allowUnmappedMarkets": True,
        "entryFormatTemplate": "MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}"
    }

def _client_profile_ids(state_obj):
    profiles = state_obj.get("profiles", {}) if isinstance(state_obj, dict) else {}
    return [pid for pid in profiles.keys() if not str(pid).startswith("admin")]

def _ensure_foundation_state(state_obj):
    if not isinstance(state_obj, dict):
        return state_obj
    state_obj.setdefault("entries", [])
    state_obj.setdefault("wallets", {})
    state_obj.setdefault("walletTransactions", [])
    state_obj.setdefault("auditLog", [])
    state_obj.setdefault("marketLocks", {})
    state_obj.setdefault("riskSettings", _default_risk_settings())
    state_obj.setdefault("walletSettings", _default_wallet_settings())
    state_obj.setdefault("entrySettings", _default_entry_settings())
    state_obj.setdefault("settlementRecords", {})
    state_obj.setdefault("ledgerAutoMarkRecords", {})
    state_obj.setdefault("settlementSettings", _default_settlement_settings())
    state_obj.setdefault("paymentSettings", _default_payment_settings())
    state_obj.setdefault("withdrawalSettings", _default_withdrawal_settings())
    state_obj.setdefault("withdrawals", [])
    state_obj.setdefault("paymentOutbox", [])
    state_obj.setdefault("loadForwarder", _default_load_forwarder_settings())
    state_obj.setdefault("loadForwarderOutbox", [])
    state_obj.setdefault("spamGuardSettings", _default_spam_guard_settings())
    state_obj.setdefault("spamGuardStrikes", {})
    state_obj.setdefault("spamGuardEvents", [])
    state_obj.setdefault("whatsappSafetySettings", _default_whatsapp_safety_settings())
    state_obj.setdefault("whatsappSafetyTargets", {})
    state_obj.setdefault("whatsappSafetyEvents", [])
    state_obj.setdefault("ledgerSchedules", {})
    state_obj.setdefault("updateGuardSettings", _default_update_guard_settings())
    _ensure_market_registry(state_obj)  # MARKET_MANAGER_PHASE1_REGISTRY source-of-truth
    if not isinstance(state_obj.get("ledgerSchedules"), dict):
        state_obj["ledgerSchedules"] = {}
    # Preserve existing custom values while adding any missing keys.
    for k, v in _default_risk_settings().items():
        state_obj["riskSettings"].setdefault(k, v)
    for k, v in _default_wallet_settings().items():
        state_obj["walletSettings"].setdefault(k, v)
    for k, v in _default_settlement_settings().items():
        state_obj["settlementSettings"].setdefault(k, v)
    for k, v in _default_payment_settings().items():
        state_obj["paymentSettings"].setdefault(k, v)
    for k, v in _default_withdrawal_settings().items():
        state_obj["withdrawalSettings"].setdefault(k, v)
    for k, v in _default_load_forwarder_settings().items():
        state_obj["loadForwarder"].setdefault(k, v)
    for k, v in _default_spam_guard_settings().items():
        state_obj["spamGuardSettings"].setdefault(k, v)
    for k, v in _default_update_guard_settings().items():
        state_obj["updateGuardSettings"].setdefault(k, v)
    for k, v in _default_whatsapp_safety_settings().items():
        state_obj["whatsappSafetySettings"].setdefault(k, v)
    if not isinstance(state_obj["settlementSettings"].get("payoutMultipliers"), dict):
        state_obj["settlementSettings"]["payoutMultipliers"] = _default_settlement_settings()["payoutMultipliers"]
    else:
        for k, v in _default_settlement_settings()["payoutMultipliers"].items():
            state_obj["settlementSettings"]["payoutMultipliers"].setdefault(k, v)
    for k, v in _default_entry_settings().items():
        state_obj["entrySettings"].setdefault(k, v)
    if not isinstance(state_obj["entrySettings"].get("marketCloseTimes"), dict):
        state_obj["entrySettings"]["marketCloseTimes"] = _default_market_close_times()
    else:
        for mk, mt in _default_market_close_times().items():
            state_obj["entrySettings"]["marketCloseTimes"].setdefault(mk, mt)
    try:
        for m in _market_arrays_from_registry(state_obj.get('marketRegistry', {}), purpose='ledger')[0]:
            state_obj["entrySettings"]["marketCloseTimes"].setdefault(m.get('n'), f"{int(m.get('hr',0)):02d}:{int(m.get('min',0)):02d}")
    except Exception:
        pass
    return state_obj

def _ensure_wallet_for_user(state_obj, user_id):
    _ensure_foundation_state(state_obj)
    profiles = state_obj.get("profiles", {})
    if user_id not in profiles:
        return None
    settings = state_obj.get("walletSettings", _default_wallet_settings())
    wallets = state_obj.setdefault("wallets", {})
    prof = profiles.get(user_id, {}) or {}
    if user_id not in wallets or not isinstance(wallets.get(user_id), dict):
        wallets[user_id] = {
            "userId": user_id,
            "name": prof.get("name", user_id),
            "phone": prof.get("phone", ""),
            "balance": 0,
            "hold": 0,
            "creditLimit": float(settings.get("defaultCreditLimit", 0) or 0),
            "ledger": [],
            "createdAt": _now_iso_local(),
            "updatedAt": _now_iso_local()
        }
    else:
        wallets[user_id].setdefault("userId", user_id)
        wallets[user_id]["name"] = prof.get("name", wallets[user_id].get("name", user_id))
        wallets[user_id]["phone"] = prof.get("phone", wallets[user_id].get("phone", ""))
        wallets[user_id].setdefault("balance", 0)
        wallets[user_id].setdefault("hold", 0)
        wallets[user_id].setdefault("creditLimit", float(settings.get("defaultCreditLimit", 0) or 0))
        wallets[user_id].setdefault("ledger", [])
        wallets[user_id].setdefault("createdAt", _now_iso_local())
        wallets[user_id]["updatedAt"] = wallets[user_id].get("updatedAt", _now_iso_local())
    return wallets[user_id]

def _ensure_wallets_for_profiles(state_obj):
    _ensure_foundation_state(state_obj)
    for uid in _client_profile_ids(state_obj):
        _ensure_wallet_for_user(state_obj, uid)
    return state_obj.get("wallets", {})

def _wallet_float(v):
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0

def _add_audit(state_obj, action, detail=None):
    _ensure_foundation_state(state_obj)
    log = state_obj.setdefault("auditLog", [])
    log.append({
        "id": str(uuid.uuid4())[:8].upper(),
        "time": _now_iso_local(),
        "action": action,
        "detail": detail or {}
    })
    if len(log) > 500:
        del log[:-500]
    return log[-1]

def _wallet_transactions_from_state(state_obj, user_id=None, limit=500):
    """Return a normalized, newest-first wallet transaction history.
    Source of truth stays the per-wallet ledger so Gateway-created debits/holds/payouts
    are visible without requiring another migration step.
    """
    if not isinstance(state_obj, dict):
        return []
    wallets = state_obj.get("wallets", {}) if isinstance(state_obj.get("wallets", {}), dict) else {}
    profiles = state_obj.get("profiles", {}) if isinstance(state_obj.get("profiles", {}), dict) else {}
    rows = []
    seen = set()
    for uid, wallet in wallets.items():
        if user_id and str(uid) != str(user_id):
            continue
        if not isinstance(wallet, dict):
            continue
        prof = profiles.get(uid, {}) if isinstance(profiles.get(uid, {}), dict) else {}
        ledger = wallet.get("ledger", []) if isinstance(wallet.get("ledger", []), list) else []
        for item in ledger:
            if not isinstance(item, dict):
                continue
            ref = item.get("withdrawalId") or item.get("paymentId") or item.get("entryId") or item.get("settlementKey") or item.get("id") or ""
            row_id = str(item.get("txnId") or f"{uid}_{item.get('id','')}_{item.get('time','')}_{item.get('type','')}")[:120]
            if row_id in seen:
                continue
            seen.add(row_id)
            amount = _wallet_float(item.get("amount", 0))
            rows.append({
                "id": row_id,
                "userId": uid,
                "name": wallet.get("name") or prof.get("name") or uid,
                "phone": wallet.get("phone") or prof.get("phone") or "",
                "time": item.get("time") or item.get("createdAt") or "",
                "type": item.get("type") or "wallet",
                "amount": amount,
                "balanceBefore": _wallet_float(item.get("balanceBefore", 0)),
                "balanceAfter": _wallet_float(item.get("balanceAfter", 0)),
                "holdBefore": _wallet_float(item.get("holdBefore", wallet.get("hold", 0))),
                "holdAfter": _wallet_float(item.get("holdAfter", wallet.get("hold", 0))),
                "creditLimit": _wallet_float(wallet.get("creditLimit", 0)),
                "note": item.get("note") or item.get("type") or "Wallet transaction",
                "source": item.get("source") or "wallet_ledger",
                "refId": ref,
                "entryId": item.get("entryId", ""),
                "paymentId": item.get("paymentId", ""),
                "withdrawalId": item.get("withdrawalId", ""),
                "settlementKey": item.get("settlementKey", "")
            })
    # Keep any newer global-only transactions too, but avoid duplicates.
    for item in state_obj.get("walletTransactions", []) if isinstance(state_obj.get("walletTransactions", []), list) else []:
        if not isinstance(item, dict):
            continue
        if user_id and str(item.get("userId")) != str(user_id):
            continue
        row_id = str(item.get("id") or item.get("txnId") or "")[:120]
        if row_id and row_id in seen:
            continue
        if row_id:
            seen.add(row_id)
        rows.append(item)
    rows.sort(key=lambda x: str(x.get("time") or x.get("createdAt") or ""), reverse=True)
    try:
        limit = max(1, min(int(limit or 500), 2000))
    except Exception:
        limit = 500
    return rows[:limit]

def _record_wallet_transaction(state_obj, user_id, wallet, ledger_entry):
    """Mirror a wallet ledger item into a global walletTransactions list for faster UI/search/export.
    The per-wallet ledger remains backward-compatible and is still the canonical source.
    """
    if not isinstance(state_obj, dict) or not user_id or not isinstance(wallet, dict) or not isinstance(ledger_entry, dict):
        return None
    _ensure_foundation_state(state_obj)
    txns = state_obj.setdefault("walletTransactions", [])
    txn_id = str(ledger_entry.get("txnId") or f"{user_id}_{ledger_entry.get('id','')}_{ledger_entry.get('time','')}_{ledger_entry.get('type','')}")[:120]
    ledger_entry["txnId"] = txn_id
    for old in txns:
        if isinstance(old, dict) and old.get("id") == txn_id:
            return old
    profiles = state_obj.get("profiles", {}) if isinstance(state_obj.get("profiles", {}), dict) else {}
    prof = profiles.get(user_id, {}) if isinstance(profiles.get(user_id, {}), dict) else {}
    txn = {
        "id": txn_id,
        "userId": user_id,
        "name": wallet.get("name") or prof.get("name") or user_id,
        "phone": wallet.get("phone") or prof.get("phone") or "",
        "time": ledger_entry.get("time") or _now_iso_local(),
        "type": ledger_entry.get("type") or "wallet",
        "amount": _wallet_float(ledger_entry.get("amount", 0)),
        "balanceBefore": _wallet_float(ledger_entry.get("balanceBefore", 0)),
        "balanceAfter": _wallet_float(ledger_entry.get("balanceAfter", 0)),
        "holdBefore": _wallet_float(ledger_entry.get("holdBefore", wallet.get("hold", 0))),
        "holdAfter": _wallet_float(ledger_entry.get("holdAfter", wallet.get("hold", 0))),
        "creditLimit": _wallet_float(wallet.get("creditLimit", 0)),
        "note": ledger_entry.get("note") or ledger_entry.get("type") or "Wallet transaction",
        "source": ledger_entry.get("source") or "wallet_ledger",
        "refId": ledger_entry.get("withdrawalId") or ledger_entry.get("paymentId") or ledger_entry.get("entryId") or ledger_entry.get("id") or "",
        "entryId": ledger_entry.get("entryId", ""),
        "paymentId": ledger_entry.get("paymentId", ""),
        "withdrawalId": ledger_entry.get("withdrawalId", ""),
        "settlementKey": ledger_entry.get("settlementKey", "")
    }
    txns.append(txn)
    if len(txns) > 2000:
        del txns[:-2000]
    return txn

def migrate_and_get_state():
    data = load_from_firebase()
    if data and "profiles" in data:
        _ensure_foundation_state(data)
        # Auto-migrate old single master into multi-admin system
        if "master" in data["profiles"] and "admin1" not in data["profiles"]:
            old_master = data["profiles"].pop("master")
            data["profiles"]["admin1"] = old_master
            data["profiles"]["admin2"] = json.loads(json.dumps(old_master))
            data["profiles"]["admin2"]["name"] = "MASTER ADMIN 2"
            data["profiles"]["admin3"] = json.loads(json.dumps(old_master))
            data["profiles"]["admin3"]["name"] = "MASTER ADMIN 3"

        if "client_dummy" not in data["profiles"]:
            data["profiles"]["client_dummy"] = {"name": "DUMMY TEST VIP", "phone": "", "config": get_default_config(), "dayRecords": {}}
        if "broadcasts" not in data:
            data["broadcasts"] = []
        if "payments" not in data:
            data["payments"] = []
        if "withdrawals" not in data or not isinstance(data.get("withdrawals"), list):
            data["withdrawals"] = []
        if "withdrawalSettings" not in data or not isinstance(data.get("withdrawalSettings"), dict):
            data["withdrawalSettings"] = _default_withdrawal_settings()
        if "updateGuardSettings" not in data or not isinstance(data.get("updateGuardSettings"), dict):
            data["updateGuardSettings"] = _default_update_guard_settings()
        if "paymentMethods" not in data:
            data["paymentMethods"] = {"upi": "", "phonepeUpi":"", "gpayUpi":"", "paytmUpi":"", "name": TITAN_PAYMENT_NAME, "phone": "", "qr": ""}
        if "resultRecords" not in data:
            data["resultRecords"] = {}
        if "resultTargets" not in data:
            data["resultTargets"] = []
        if "marketRegistry" not in data or not isinstance(data.get("marketRegistry"), dict):
            data["marketRegistry"] = _default_market_registry()
        else:
            _ensure_market_registry(data)
        if "resultSettings" not in data:
            data["resultSettings"] = {"autoScrapeEnabled": True, "useForwardTargetsForResults": True, "sourceName": RESULT_SOURCE_NAME, "sourceUrl": RESULT_SOURCE_URL}
        if "autoScrapeEnabled" not in data.get("resultSettings", {}):
            data["resultSettings"]["autoScrapeEnabled"] = True
        data["resultSettings"]["sourceName"] = RESULT_SOURCE_NAME
        data["resultSettings"]["sourceUrl"] = RESULT_SOURCE_URL
        if "settlementRecords" not in data:
            data["settlementRecords"] = {}
        if "ledgerAutoMarkRecords" not in data:
            data["ledgerAutoMarkRecords"] = {}
        if "settlementSettings" not in data:
            data["settlementSettings"] = _default_settlement_settings()
        _ensure_wallets_for_profiles(data)
        for pid, profile in data["profiles"].items():
            if "expiryDate" not in profile:
                profile["expiryDate"] = ""
            if "vipAccessEnabled" not in profile:
                profile["vipAccessEnabled"] = True
            if str(pid).startswith("admin"):
                profile.setdefault("approvalStatus", "approved")
            elif "approvalStatus" not in profile:
                profile["approvalStatus"] = "pending" if profile.get("autoCreated") else "approved"
            if str(profile.get("approvalStatus", "approved")).lower() == "pending":
                profile["vipAccessEnabled"] = False
            if "config" not in profile:
                profile["config"] = get_default_config()
            else:
                if "capital" not in profile["config"]:
                    profile["config"]["capital"] = 0
                if "dayTarget" not in profile["config"]:
                    profile["config"]["dayTarget"] = 0
        return data

    default_state = {
        "activeId": "admin1",
        "broadcasts": [],
        "payments": [],
        "withdrawals": [],
        "paymentMethods": {"upi": "", "phonepeUpi":"", "gpayUpi":"", "paytmUpi":"", "name": TITAN_PAYMENT_NAME, "phone": "", "qr": ""},
        "resultRecords": {},
        "resultTargets": [],
        "resultSettings": {"autoScrapeEnabled": True, "useForwardTargetsForResults": True, "sourceName": RESULT_SOURCE_NAME, "sourceUrl": RESULT_SOURCE_URL},
        "marketRegistry": _default_market_registry(),
        "entries": [],
        "wallets": {},
        "walletTransactions": [],
        "auditLog": [],
        "marketLocks": {},
        "riskSettings": _default_risk_settings(),
        "walletSettings": _default_wallet_settings(),
        "entrySettings": _default_entry_settings(),
        "withdrawalSettings": _default_withdrawal_settings(),
        "loadForwarder": _default_load_forwarder_settings(),
        "loadForwarderOutbox": [],
        "spamGuardSettings": _default_spam_guard_settings(),
        "spamGuardStrikes": {},
        "spamGuardEvents": [],
        "whatsappSafetySettings": _default_whatsapp_safety_settings(),
        "whatsappSafetyTargets": {},
        "whatsappSafetyEvents": [],
        "ledgerSchedules": {},
        "updateGuardSettings": _default_update_guard_settings(),
        "profiles": {
            "admin1": { "name": "MASTER ADMIN 1", "phone": "", "config": get_default_config(), "dayRecords": {}, "expiryDate": "", "approvalStatus": "approved" },
            "admin2": { "name": "MASTER ADMIN 2", "phone": "", "config": get_default_config(), "dayRecords": {}, "expiryDate": "", "approvalStatus": "approved" },
            "admin3": { "name": "MASTER ADMIN 3", "phone": "", "config": get_default_config(), "dayRecords": {}, "expiryDate": "", "approvalStatus": "approved" },
            "client_dummy": { "name": "DUMMY TEST VIP", "phone": "", "config": get_default_config(), "dayRecords": {}, "expiryDate": "", "approvalStatus": "approved" }
        }
    }
    _ensure_wallets_for_profiles(default_state)
    # v36: never auto-write a default state when Firebase root is empty/unreadable.
    # This was the main reset risk after network/Firebase hiccups. For a brand-new
    # empty database only, set TITAN_FIREBASE_ALLOW_EMPTY_INIT=1 and save once.
    backup = _read_state_backup('last_known_good.json') if '_read_state_backup' in globals() else None
    if backup and isinstance(backup.get('state'), dict) and _runtime_state_validation_report(backup.get('state')).get('ok'):
        state_from_backup = backup.get('state')
        state_from_backup.setdefault('firebaseDataGuard', {})['servedFromBackupBecauseFirebaseEmptyAt'] = _now_iso_local()
        _obs_event('firebase_default_init_blocked_backup_served_v36', 'critical', 'Firebase empty/unreadable; served last known good backup without writing root', {'file': backup.get('file'), 'loadMeta': FIREBASE_LAST_LOAD_META})
        return state_from_backup
    if _firebase_allow_empty_init():
        save_to_firebase(default_state, 'initial_default_state_allowed')
    else:
        _obs_event('firebase_default_init_blocked_v36', 'critical', 'Firebase empty/unreadable; default state not auto-written during load', {'loadMeta': FIREBASE_LAST_LOAD_META})
    return default_state

@app.route('/sw.js')
def sw():
    js = """
    self.addEventListener('install', (e)=>{self.skipWaiting();});
    self.addEventListener('activate', (e)=>{self.clients.claim();});
    self.addEventListener('fetch', (e)=>{
        const url = new URL(e.request.url);
        if (url.pathname.startsWith('/api/')) {
            e.respondWith(fetch(e.request).catch(()=>new Response(JSON.stringify({status:'error', message:'Offline'}), {status:503, headers:{'Content-Type':'application/json'}})));
            return;
        }
        if (e.request.method !== 'GET') {
            e.respondWith(fetch(e.request));
            return;
        }
        e.respondWith(fetch(e.request).catch(()=>new Response('Offline', {status:503, headers:{'Content-Type':'text/plain'}})));
    });
    self.addEventListener('notificationclick', function(event) {
        event.notification.close();
        event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            if (clientList.length > 0) {
                let client = clientList[0];
                for (let i = 0; i < clientList.length; i++) { if (clientList[i].focused) { client = clientList[i]; } }
                return client.focus();
            }
            return clients.openWindow('/');
        }));
    });
    """
    return app.response_class(js, mimetype='application/javascript')

@app.route('/icon.svg')
def app_icon_svg():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512' viewBox='0 0 512 512'>
  <rect width='512' height='512' rx='100' fill='#2AABEE'/>
  <text x='256' y='360' font-size='300' text-anchor='middle' font-family='Arial Black,sans-serif' font-weight='900' fill='white'>T</text>
</svg>"""
    return app.response_class(svg, mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})

@app.route('/manifest.json')
def manifest():
    vip_id = request.args.get('vip')
    start_url = f"/?vip={vip_id}" if vip_id else "/"
    app_name = "TITAN VIP" if vip_id else "TITAN MASTER"
    base = request.host_url.rstrip('/')
    return jsonify({
        "name": app_name,
        "short_name": "Titan",
        "description": "Titan Nova - Professional Matka Ledger",
        "start_url": start_url,
        "scope": "/",
        "display": "standalone",
        "background_color": "#17212B",
        "theme_color": "#2AABEE",
        "orientation": "portrait",
        "icons": [
            {"src": f"{base}/icon.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any"},
            {"src": f"{base}/icon.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any"},
            {"src": "https://cdn-icons-png.flaticon.com/512/5738/5738033.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "https://cdn-icons-png.flaticon.com/512/5738/5738033.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
        ]
    })

@app.route('/api/state')
def get_state_api():
    state = migrate_and_get_state()
    vip_id = request.args.get('vip') or request.headers.get('X-Titan-Vip-Id') or ''
    if vip_id:
        vip_id = str(vip_id).strip()
        profiles = state.get("profiles", {}) if isinstance(state.get("profiles"), dict) else {}
        if vip_id not in profiles:
            return jsonify({"status": "error", "message": "VIP profile not found", "userSafety": True}), 404
        vip_access = _vip_runtime_access_check(state, vip_id, record=True)
        if TITAN_VIP_ACCESS_ENFORCE and not vip_access.get('allowed'):
            return jsonify({"status": "blocked", "message": "VIP access blocked: " + ",".join(vip_access.get('reasons') or []), "userSafety": vip_access}), int(vip_access.get('httpStatus') or 403)
        user_payments = [p for p in state.get("payments", []) if isinstance(p, dict) and p.get("userId") == vip_id]
        isolated_state = {
            "activeId": vip_id,
            "broadcasts": state.get("broadcasts", []),
            "profiles": {vip_id: profiles[vip_id]},
            "paymentMethods": state.get("paymentMethods", {"upi":"","phonepeUpi":"","gpayUpi":"","paytmUpi":"","name":TITAN_PAYMENT_NAME,"phone":"","qr":""}),
            "payments": user_payments,
            "withdrawals": [w for w in state.get("withdrawals", []) if isinstance(w, dict) and w.get("userId") == vip_id],
            "resultRecords": state.get("resultRecords", {}),
            "resultTargets": [],
            "resultSettings": state.get("resultSettings", {"autoScrapeEnabled": True, "useForwardTargetsForResults": True}),
            "marketRegistry": state.get("marketRegistry", _default_market_registry()),
            "wallets": {vip_id: state.get("wallets", {}).get(vip_id, {})} if isinstance(state.get("wallets"), dict) else {},
            "walletTransactions": [t for t in _wallet_transactions_from_state(state, vip_id, 500)],
            "walletSettings": state.get("walletSettings", _default_wallet_settings()),
            "entrySettings": state.get("entrySettings", _default_entry_settings()),
            "entries": [e for e in state.get("entries", []) if isinstance(e, dict) and e.get("userId") == vip_id],
            "settlementRecords": {},
            "ledgerAutoMarkRecords": {},
            "settlementSettings": {},
            "paymentSettings": {
                "paymentAutomationEnabled": state.get("paymentSettings", _default_payment_settings()).get("paymentAutomationEnabled", True),
                "requireUtr": state.get("paymentSettings", _default_payment_settings()).get("requireUtr", True),
            },
            "loadForwarder": {},
            "loadForwarderOutbox": [],
            "spamGuardSettings": {},
            "spamGuardEvents": [],
            "whatsappSafetySettings": {},
            "whatsappSafetyTargets": {},
            "whatsappSafetyEvents": [],
            "ledgerSchedules": {k:v for k,v in (state.get("ledgerSchedules", {}) or {}).items() if str(k).startswith(vip_id + "|")},
            "userSafety": {vip_id: (state.get("userSafety", {}) or {}).get(vip_id, {})} if isinstance(state.get("userSafety"), dict) else {},
            "userSafetySettings": _vip_safety_defaults(state)
        }
        return jsonify(isolated_state)
    return jsonify(state)


@app.route('/api/realtime_sync_status')
def api_realtime_sync_status():
    return jsonify({
        'status':'success',
        'realtimeFastSync': True,
        'version': REALTIME_SYNC_VERSION,
        'cacheEnabled': REALTIME_FAST_SYNC_ENABLED,
        'cacheTtlMs': REALTIME_STATE_CACHE_TTL_MS,
        'cacheAgeMs': (_rt_ms() - int(FIREBASE_STATE_CACHE_AT_MS or 0)) if FIREBASE_STATE_CACHE_AT_MS else None,
        'cacheSource': FIREBASE_STATE_CACHE_SOURCE,
        'uiPollMs': 1200,
        'autosaveDebounceMs': 180,
        'ledgerHoldMs': 2500,
        'firebaseDataGuardDisabled': FIREBASE_DATA_GUARD_VERSION
    })


# ==========================================================
# MARKET CORE v28: compact, single-source market manager
# ==========================================================
def _market_registry_response(state, extra=None):
    reg = _ensure_market_registry(state)
    ledger_markets, ledger_base = _market_arrays_from_registry(reg, purpose='ledger')
    result_markets, result_base = _market_arrays_from_registry(reg, purpose='result')
    payload = {
        'status': 'success',
        'marketCoreFix': True,
        'marketDirectAdd': True,
        'version': MARKET_CORE_VERSION,
        'marketRegistry': reg,
        'ledgerMarkets': ledger_markets,
        'ledgerBaseMarkets': ledger_base,
        'resultMarkets': result_markets,
        'resultBaseMarkets': result_base,
        'chartLinks': _chart_links_from_registry(reg),
        'counts': {
            'total': len(reg.get('items', {}) or {}),
            'active': len([x for x in (reg.get('items', {}) or {}).values() if isinstance(x, dict) and x.get('deleted') is not True and x.get('enabled') is not False and x.get('archived') is not True]),
            'deleted': len([x for x in (reg.get('items', {}) or {}).values() if isinstance(x, dict) and x.get('deleted') is True]),
        }
    }
    if extra:
        payload.update(extra)
    return payload


def _market_save_registry_child(state, reg, audit_action='market_registry_action', detail=None):
    """Save only marketRegistry child where possible, avoiding unnecessary root PUT."""
    reg = _normalize_market_registry(reg)
    reg['updatedAt'] = _now_iso_local()
    state['marketRegistry'] = reg
    try:
        # Keep derived close-time config in sync without a full root overwrite.
        try:
            _ensure_market_registry(state)
        except Exception:
            pass
        _firebase_put_child(['marketRegistry'], state.get('marketRegistry') or reg)
        try:
            _firebase_put_child(['entrySettings'], state.get('entrySettings', {}))
        except Exception:
            pass
        # best-effort audit log; do not fail market save because of audit write
        try:
            audit_id = 'market_audit_' + uuid.uuid4().hex[:10]
            _firebase_put_child(['auditLog', audit_id], {'id': audit_id, 'time': _now_iso_local(), 'action': audit_action, 'detail': detail or {}, 'marketCoreFix': True})
        except Exception:
            pass
        return True
    except Exception as child_err:
        print('Market child save failed:', child_err)
        _obs_exception('market_child_save_failed', child_err, {'action': audit_action, 'detail': detail or {}})
        return False


def _market_clean_name(v):
    return ' '.join(str(v or '').strip().upper().split())


def _market_clean_hhmm(v):
    raw = str(v or '').strip()
    if not raw:
        return ''
    m = re.match(r'^(\d{1,2}):(\d{2})$', raw)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        return None
    return f'{h:02d}:{mi:02d}'


@app.route('/api/market_core_status')
def api_market_core_status():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    return jsonify(_market_registry_response(state, {'marketCoreFix': True, 'items': len(reg.get('items', {}) or {})}))

@app.route('/api/market_direct_add_status')
def api_market_direct_add_status():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    return jsonify(_market_registry_response(state, {
        'marketDirectAdd': True,
        'version': globals().get('MARKET_DIRECT_ADD_VERSION', MARKET_CORE_VERSION),
        'rules': {
            'sourceOfTruth': 'marketRegistry',
            'directAddEnables': ['ledger', 'results', 'autoPassFail', 'autoResult', 'schedule', 'entries'],
            'requiresTimeForLedgerCards': True,
        },
        'items': len(reg.get('items', {}) or {})
    }))


@app.route('/api/market_action', methods=['POST'])
def api_market_action():
    state = migrate_and_get_state()
    payload = request.get_json(silent=True) or {}
    action = str(payload.get('action') or '').strip().lower()
    reg = _ensure_market_registry(state)
    items = reg.setdefault('items', {})
    stamp = _now_iso_local()

    def get_item(required=True):
        mid = str(payload.get('id') or payload.get('marketId') or '').strip()
        item = items.get(mid)
        if required and not isinstance(item, dict):
            return None, None
        return mid, item

    try:
        if action in ('save_registry', 'replace_registry'):
            candidate = payload.get('marketRegistry') if isinstance(payload.get('marketRegistry'), dict) else reg
            reg = _normalize_market_registry(candidate)
            for it in (reg.get('items') or {}).values():
                if isinstance(it, dict):
                    _apply_market_manual_save_lock(it, source='manual_registry_save', locked_at=stamp)
            ok = _market_save_registry_child(state, reg, 'market_registry_saved', {'count': len(reg.get('items', {}) or {})})
            if not ok:
                return jsonify({'status': 'error', 'message': 'Market registry save failed', 'marketCoreFix': True}), 409
            return jsonify(_market_registry_response(state, {'message': 'Market registry saved'}))

        if action in ('upsert', 'add', 'direct_add', 'direct_add_full'):
            name = _market_clean_name(payload.get('name') or payload.get('displayName'))
            if not name:
                return jsonify({'status': 'error', 'message': 'Market name required', 'marketCoreFix': True}), 400
            open_time = _market_clean_hhmm(payload.get('openTime') or payload.get('open'))
            close_time = _market_clean_hhmm(payload.get('closeTime') or payload.get('close'))
            if open_time is None or close_time is None:
                return jsonify({'status': 'error', 'message': 'Time format HH:MM hona chahiye', 'marketCoreFix': True}), 400
            mid = str(payload.get('id') or _market_slug(name)).strip()
            website = _market_clean_name(payload.get('websiteName') or name)
            item = items.get(mid) if isinstance(items.get(mid), dict) else {'id': mid, 'name': name, 'createdAt': stamp}
            item.update({
                'id': mid,
                'name': _market_clean_name(item.get('name') or name),
                'displayName': name,
                'websiteName': website,
                'enabled': True,
                'ledgerEnabled': bool(payload.get('ledgerEnabled', True)),
                'resultEnabled': bool(payload.get('resultEnabled', True)),
                'autoPassFailEnabled': bool(payload.get('autoPassFailEnabled', True)),
                'autoResultEnabled': bool(payload.get('autoResultEnabled', True)),
                'scheduleEnabled': bool(payload.get('scheduleEnabled', True)),
                'entryEnabled': bool(payload.get('entryEnabled', True)),
                'entryTargets': _clean_market_target_list(payload.get('entryTargets') or item.get('entryTargets') or []),
                'scheduleTargets': _clean_market_target_list(payload.get('scheduleTargets') or item.get('scheduleTargets') or []),
                'resultTargets': _clean_market_target_list(payload.get('resultTargets') or item.get('resultTargets') or []),
                'forwardTargets': _clean_market_target_list(payload.get('forwardTargets') or item.get('forwardTargets') or []),
                'bookieTargets': _clean_market_target_list(payload.get('bookieTargets') or item.get('bookieTargets') or []),
                'stages': {'open': bool(payload.get('openStage', True)) and bool(open_time), 'close': bool(payload.get('closeStage', True)) and bool(close_time)},
                'times': {'open': open_time or '', 'close': close_time or ''},
                'chartUrl': str(payload.get('chartUrl') or item.get('chartUrl') or '').strip(),
                'archived': False,
                'deleted': False,
                'updatedAt': stamp,
                'directAddMarketV29': bool(action in ('upsert', 'add', 'direct_add', 'direct_add_full')) ,
            })
            item['sortOrder'] = int(item.get('sortOrder') or ((len(items) + 1) * 10))
            _apply_market_manual_save_lock(item, source='market_add', locked_at=stamp)
            _sync_market_entry_target_settings(state, item)
            items[mid] = item
            if isinstance(reg.get('deletedMarketIds'), list):
                reg['deletedMarketIds'] = [x for x in reg.get('deletedMarketIds') if str(x) != mid]
            ok = _market_save_registry_child(state, reg, 'market_upsert', {'id': mid, 'name': name})
            if not ok:
                return jsonify({'status': 'error', 'message': 'Market add/save failed', 'marketCoreFix': True}), 409
            return jsonify(_market_registry_response(state, {'message': 'Market saved', 'marketId': mid}))

        if action in ('update_text', 'update_time', 'set_flag', 'set_stage', 'set_entry_targets', 'set_role_targets', 'disable', 'restore', 'archive', 'delete'):
            mid, item = get_item(True)
            if not item:
                return jsonify({'status': 'error', 'message': 'Market not found', 'marketCoreFix': True}), 404
            if action == 'set_entry_targets':
                item['entryTargets'] = _clean_market_target_list(payload.get('targets') or payload.get('entryTargets') or [])
                item['entryEnabled'] = payload.get('entryEnabled', item.get('entryEnabled', True)) is not False
                _sync_market_entry_target_settings(state, item)
            elif action == 'set_role_targets':
                role = str(payload.get('role') or '').strip().lower()
                role_field = {'entry':'entryTargets', 'schedule':'scheduleTargets', 'result':'resultTargets', 'forward':'forwardTargets', 'bookie':'bookieTargets', 'admin':'bookieTargets'}.get(role)
                if not role_field:
                    return jsonify({'status': 'error', 'message': 'Invalid WhatsApp target role', 'marketRoleRouting': True}), 400
                item[role_field] = _clean_market_target_list(payload.get('targets') or payload.get(role_field) or [])
                if role == 'entry':
                    item['entryEnabled'] = payload.get('entryEnabled', item.get('entryEnabled', True)) is not False
                    _sync_market_entry_target_settings(state, item)
            elif action == 'update_text':
                field = str(payload.get('field') or '').strip()
                if field not in ('displayName', 'websiteName', 'chartUrl'):
                    return jsonify({'status': 'error', 'message': 'Invalid text field', 'marketCoreFix': True}), 400
                val = str(payload.get('value') or '').strip()
                item[field] = val if field == 'chartUrl' else _market_clean_name(val)
            elif action == 'update_time':
                stage = str(payload.get('stage') or '').strip().lower()
                if stage not in ('open', 'close'):
                    return jsonify({'status': 'error', 'message': 'Invalid stage', 'marketCoreFix': True}), 400
                val = _market_clean_hhmm(payload.get('value'))
                if val is None:
                    return jsonify({'status': 'error', 'message': 'Time format HH:MM hona chahiye', 'marketCoreFix': True}), 400
                item.setdefault('times', {})[stage] = val
                item.setdefault('stages', {})[stage] = bool(val)
            elif action == 'set_flag':
                field = str(payload.get('field') or '').strip()
                if field not in ('enabled', 'ledgerEnabled', 'resultEnabled', 'autoPassFailEnabled', 'scheduleEnabled', 'autoResultEnabled', 'entryEnabled'):
                    return jsonify({'status': 'error', 'message': 'Invalid flag', 'marketCoreFix': True}), 400
                item[field] = bool(payload.get('value'))
            elif action == 'set_stage':
                stage = str(payload.get('stage') or '').strip().lower()
                if stage not in ('open', 'close'):
                    return jsonify({'status': 'error', 'message': 'Invalid stage', 'marketCoreFix': True}), 400
                item.setdefault('stages', {})[stage] = bool(payload.get('value'))
            elif action == 'disable':
                item['enabled'] = False
            elif action == 'restore':
                item['deleted'] = False
                item['archived'] = False
                item['enabled'] = True
                item['ledgerEnabled'] = item.get('ledgerEnabled') is not False
                item['resultEnabled'] = item.get('resultEnabled') is not False
                item['scheduleEnabled'] = item.get('scheduleEnabled') is not False
                item['entryEnabled'] = item.get('entryEnabled') is not False
                item['autoPassFailEnabled'] = item.get('autoPassFailEnabled') is not False
                if isinstance(reg.get('deletedMarketIds'), list):
                    reg['deletedMarketIds'] = [x for x in reg.get('deletedMarketIds') if str(x) != mid]
            elif action == 'archive':
                item['archived'] = True
                item['enabled'] = False
            elif action == 'delete':
                item['deleted'] = True
                item['enabled'] = False
                item['ledgerEnabled'] = False
                item['resultEnabled'] = False
                item['autoResultEnabled'] = False
                item['autoPassFailEnabled'] = False
                item['scheduleEnabled'] = False
                item['entryEnabled'] = False
                item['archived'] = False
                item['deletedAt'] = stamp
                deleted_ids = reg.get('deletedMarketIds') if isinstance(reg.get('deletedMarketIds'), list) else []
                if mid not in [str(x) for x in deleted_ids]:
                    deleted_ids.append(mid)
                reg['deletedMarketIds'] = deleted_ids
            item['updatedAt'] = stamp
            _sync_market_entry_target_settings(state, item)
            _apply_market_manual_save_lock(item, source='market_' + action, locked_at=stamp)
            items[mid] = item
            ok = _market_save_registry_child(state, reg, 'market_' + action, {'id': mid, 'field': payload.get('field'), 'stage': payload.get('stage')})
            if not ok:
                return jsonify({'status': 'error', 'message': 'Market save failed', 'marketCoreFix': True}), 409
            return jsonify(_market_registry_response(state, {'message': 'Market updated', 'marketId': mid}))

        return jsonify({'status': 'error', 'message': 'Unknown market action', 'marketCoreFix': True}), 400
    except Exception as e:
        _obs_exception('market_action_error', e, {'action': action}) if '_obs_exception' in globals() else None
        return jsonify({'status': 'error', 'message': str(e), 'marketCoreFix': True}), 500


@app.route('/api/market_entry_target_status')
def api_market_entry_target_status():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    entry = state.get('entrySettings', {}) if isinstance(state.get('entrySettings'), dict) else {}
    mapped = sum(1 for v in (entry.get('marketTargets') or {}).values() if isinstance(v, list) and v) if isinstance(entry.get('marketTargets'), dict) else 0
    return jsonify({
        'status': 'success',
        'marketEntryTargetFix': True,
        'version': globals().get('MARKET_ENTRY_TARGET_VERSION', 'v30'),
        'registryMarkets': len(reg.get('items', {}) or {}),
        'mappedEntryMarkets': mapped,
        'rules': {'sourceOfTruth': 'marketRegistry + entrySettings.marketTargets', 'unmappedMarkets': 'allowed for backward compatibility'}
    })


@app.route('/api/whatsapp_role_routing_status')
def api_whatsapp_role_routing_status():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    counts = {'entry': 0, 'schedule': 0, 'result': 0, 'forward': 0, 'bookie': 0}
    for item in (reg.get('items') or {}).values():
        if not isinstance(item, dict):
            continue
        if _clean_market_target_list(item.get('entryTargets') or []): counts['entry'] += 1
        if _clean_market_target_list(item.get('scheduleTargets') or []): counts['schedule'] += 1
        if _clean_market_target_list(item.get('resultTargets') or []): counts['result'] += 1
        if _clean_market_target_list(item.get('forwardTargets') or []): counts['forward'] += 1
        if _clean_market_target_list(item.get('bookieTargets') or []): counts['bookie'] += 1
    return jsonify({'status': 'success', 'whatsappRoleRouting': True, 'bookieAdminRouting': True, 'version': globals().get('WHATSAPP_ROLE_ROUTING_VERSION', 'v32'), 'bookieVersion': globals().get('BOOKIE_ADMIN_ROUTING_VERSION', 'v35'), 'roleCounts': counts, 'roles': ['schedule','entry','result','forward','bookie'], 'fallbackRule': 'blank role targets use old/global behavior'})

@app.route('/api/bookie_admin_routing_status')
def api_bookie_admin_routing_status():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    mapped = 0
    total_targets = 0
    for item in (reg.get('items') or {}).values():
        if not isinstance(item, dict):
            continue
        targets = _clean_market_target_list(item.get('bookieTargets') or [])
        if targets:
            mapped += 1
            total_targets += len(targets)
    return jsonify({'status': 'success', 'bookieAdminRouting': True, 'version': globals().get('BOOKIE_ADMIN_ROUTING_VERSION', 'v35'), 'mappedMarkets': mapped, 'totalTargets': total_targets, 'roles': ['schedule','entry','result','forward','bookie'], 'rule': 'Bookie/Admin Work group is separate from game entry/result/schedule groups.'})

@app.route('/api/market_registry', methods=['GET'])
def api_market_registry_get():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    ledger_markets, ledger_base = _market_arrays_from_registry(reg, purpose='ledger')
    result_markets, result_base = _market_arrays_from_registry(reg, purpose='result')
    return jsonify({
        'status': 'success',
        'marketManagerPhase1': True,
        'version': MARKET_REGISTRY_VERSION,
        'marketRegistry': reg,
        'ledgerMarkets': ledger_markets,
        'ledgerBaseMarkets': ledger_base,
        'resultMarkets': result_markets,
        'resultBaseMarkets': result_base,
        'chartLinks': _chart_links_from_registry(reg)
    })

@app.route('/api/market_registry', methods=['POST'])
def api_market_registry_save():
    state = migrate_and_get_state()
    payload = request.get_json(silent=True) or {}
    reg = payload.get('marketRegistry') if isinstance(payload.get('marketRegistry'), dict) else payload
    state['marketRegistry'] = _normalize_market_registry(reg)
    manual_stamp = _now_iso_local()
    for item in (state['marketRegistry'].get('items') or {}).values():
        _apply_market_manual_save_lock(item, source='manual_registry_save', locked_at=manual_stamp)
    state['marketRegistry']['updatedAt'] = manual_stamp
    state.setdefault('auditLog', []).append({'id': 'market_registry_' + uuid.uuid4().hex[:10], 'time': manual_stamp, 'action': 'market_registry_saved', 'detail': {'count': len(state['marketRegistry'].get('items', {})), 'version': MARKET_REGISTRY_VERSION, 'manualChangeOnly': True}})
    _ensure_foundation_state(state)
    if not _market_save_registry_child(state, state.get('marketRegistry', {}), 'market_registry_saved'):
        return jsonify({'status':'error','message':'Market registry save blocked by runtime guard'}), 409
    ledger_markets, ledger_base = _market_arrays_from_registry(state['marketRegistry'], purpose='ledger')
    result_markets, result_base = _market_arrays_from_registry(state['marketRegistry'], purpose='result')
    return jsonify({'status':'success','marketManagerPhase1': True,'marketRegistry': state['marketRegistry'], 'ledgerMarkets': ledger_markets, 'ledgerBaseMarkets': ledger_base, 'resultMarkets': result_markets, 'resultBaseMarkets': result_base, 'chartLinks': _chart_links_from_registry(state['marketRegistry'])})

@app.route('/api/market_registry_delete', methods=['POST'])
def api_market_registry_delete():
    state = migrate_and_get_state()
    payload = request.get_json(silent=True) or {}
    market_id = str(payload.get('id') or payload.get('marketId') or '').strip()
    if not market_id:
        return jsonify({'status': 'error', 'message': 'Market id missing'}), 400
    reg = _ensure_market_registry(state)
    items = reg.setdefault('items', {})
    item = items.get(market_id)
    if not isinstance(item, dict):
        return jsonify({'status': 'error', 'message': 'Market not found'}), 404
    stamp = _now_iso_local()
    item['deleted'] = True
    item['enabled'] = False
    item['ledgerEnabled'] = False
    item['resultEnabled'] = False
    item['autoResultEnabled'] = False
    item['autoPassFailEnabled'] = False
    item['scheduleEnabled'] = False
    item['archived'] = False
    item['deletedAt'] = stamp
    item['updatedAt'] = stamp
    _apply_market_manual_save_lock(item, source='manual_delete', locked_at=stamp)
    deleted_ids = reg.get('deletedMarketIds') if isinstance(reg.get('deletedMarketIds'), list) else []
    if market_id not in [str(x) for x in deleted_ids]:
        deleted_ids.append(market_id)
    reg['deletedMarketIds'] = deleted_ids
    state['marketRegistry'] = _normalize_market_registry(reg)
    state['marketRegistry']['updatedAt'] = stamp
    state.setdefault('auditLog', []).append({'id': 'market_delete_' + uuid.uuid4().hex[:10], 'time': stamp, 'action': 'market_registry_deleted', 'detail': {'id': market_id, 'name': item.get('displayName') or item.get('name'), 'safeHiddenDelete': True}})
    _ensure_foundation_state(state)
    if not _market_save_registry_child(state, state.get('marketRegistry', {}), 'market_registry_deleted', {'id': market_id}):
        return jsonify({'status':'error','message':'Market delete save blocked by runtime guard'}), 409
    ledger_markets, ledger_base = _market_arrays_from_registry(state['marketRegistry'], purpose='ledger')
    result_markets, result_base = _market_arrays_from_registry(state['marketRegistry'], purpose='result')
    return jsonify({'status':'success','marketManagerDeleteSupport': True,'marketRegistry': state['marketRegistry'], 'ledgerMarkets': ledger_markets, 'ledgerBaseMarkets': ledger_base, 'resultMarkets': result_markets, 'resultBaseMarkets': result_base, 'chartLinks': _chart_links_from_registry(state['marketRegistry'])})

@app.route('/api/market_source_scan', methods=['GET'])
def api_market_source_scan():
    state = migrate_and_get_state()
    out = _market_phase2_mapping_diagnostics(state)
    return jsonify(out)

@app.route('/api/market_import_from_website', methods=['POST'])
def api_market_import_from_website():
    state = migrate_and_get_state()
    reg = _ensure_market_registry(state)
    payload = request.get_json(silent=True) or {}
    # v29: accept names from older/newer clients and normalize object records from website scan.
    raw_names = []
    for key in ('names', 'selectedMarkets', 'markets'):
        val = payload.get(key)
        if isinstance(val, list):
            raw_names.extend(val)
    names = []
    for rec in raw_names:
        if isinstance(rec, dict):
            val = rec.get('name') or rec.get('displayName') or rec.get('websiteName') or rec.get('foundName') or rec.get('market') or rec.get('title') or ''
        else:
            val = rec
        val = re.sub(r'\s+', ' ', str(val or '').strip().upper())
        if val:
            names.append(val)
    added = []
    skipped = []
    items = reg.setdefault('items', {})
    try:
        max_order = max([int((x or {}).get('sortOrder', 0)) for x in items.values()] or [0])
    except Exception:
        max_order = 0
    existing_aliases = {}
    for item in items.values():
        if isinstance(item, dict) and not item.get('deleted'):
            for alias in _market_phase2_registry_aliases(item):
                existing_aliases[alias] = item
    for raw in names:
        name = re.sub(r'\s+', ' ', str(raw or '').strip().upper())
        if not name:
            continue
        norm = _market_phase2_norm(name)
        if norm in existing_aliases:
            existing_item = existing_aliases.get(norm) or {}
            skipped.append({'name': name, 'reason': 'already_saved_locked' if existing_item.get('settingsLocked') or existing_item.get('manualSaveLocked') else 'already_exists'})
            continue
        mid = _market_slug(name)
        if mid in items and isinstance(items.get(mid), dict) and items[mid].get('deleted'):
            # Manual website import is treated as an intentional re-add.
            pass
        elif mid in items:
            mid = f"{mid}_{uuid.uuid4().hex[:5]}"
        max_order += 10
        item = {
            'id': mid,
            'name': name,
            'displayName': name,
            'websiteName': name,
            'aliases': [name],
            'enabled': True,
            'ledgerEnabled': True,
            'resultEnabled': True,
            'autoResultEnabled': True,
            'autoPassFailEnabled': True,
            'scheduleEnabled': True,
            'sortOrder': max_order,
            'stages': {'open': True, 'close': True},
            'times': {'open': '', 'close': ''},
            'chartUrl': '',
            'createdAt': _now_iso_local(),
            'updatedAt': _now_iso_local(),
            'archived': False,
            'importedFromWebsite': True,
            'marketManagerPhase2': True
        }
        _apply_market_manual_save_lock(item, source='website_select_save')
        items[mid] = item
        if isinstance(reg.get('deletedMarketIds'), list):
            reg['deletedMarketIds'] = [x for x in reg.get('deletedMarketIds', []) if str(x) != str(mid)]
        existing_aliases[norm] = item
        added.append({'id': mid, 'name': name, 'settingsLocked': True})
    state['marketRegistry'] = _normalize_market_registry(reg)
    state['marketRegistry']['updatedAt'] = _now_iso_local()
    state.setdefault('auditLog', []).append({'id': 'market_import_' + uuid.uuid4().hex[:10], 'time': _now_iso_local(), 'action': 'market_import_from_website', 'detail': {'added': added, 'skipped': skipped, 'phase': 'marketManagerPhase2', 'manualChangeOnly': True}})
    _ensure_foundation_state(state)
    if added and not _market_save_registry_child(state, state.get('marketRegistry', {}), 'market_import_from_website', {'added': added, 'skipped': skipped}):
        return jsonify({'status':'error','message':'Market import save blocked by runtime guard','added':[], 'skipped':skipped}), 409
    ledger_markets, ledger_base = _market_arrays_from_registry(state['marketRegistry'], purpose='ledger')
    result_markets, result_base = _market_arrays_from_registry(state['marketRegistry'], purpose='result')
    return jsonify({'status':'success','marketManagerPhase2': True,'added':added,'skipped':skipped,'marketRegistry':state['marketRegistry'],'ledgerMarkets':ledger_markets,'ledgerBaseMarkets':ledger_base,'resultMarkets':result_markets,'resultBaseMarkets':result_base,'chartLinks':_chart_links_from_registry(state['marketRegistry'])})

@app.route('/')
def index():
    state = migrate_and_get_state()
    vip_id = request.args.get('vip')

    manifest_url = f"/manifest.json?vip={vip_id}" if vip_id else "/manifest.json"

    if vip_id:
        if vip_id in state.get("profiles", {}):
            vip_profile = state.get("profiles", {}).get(vip_id, {}) or {}
            vip_access = _vip_runtime_access_check(state, vip_id, record=True)
            if TITAN_VIP_ACCESS_ENFORCE and not vip_access.get('allowed'):
                reasons = vip_access.get('reasons') or []
                if 'approval_pending' in reasons:
                    return _vip_block_html('APPROVAL PENDING', 'Aapka profile create ho gaya hai. Admin approve karega, uske baad app/entry access active hoga.', '#FAC748')
                if 'membership_expired' in reasons:
                    return _vip_block_html('MEMBERSHIP EXPIRED', 'Aapki membership expire ho gayi hai. Renewal ke liye Admin se contact karein.', '#FF5D5D')
                if 'vip_access_disabled' in reasons:
                    return _vip_block_html('VIP ACCESS DISABLED', 'Admin ne is VIP app access ko temporarily block kiya hai.', '#FF5D5D')
                if 'device_limit_exceeded' in reasons:
                    return _vip_block_html('DEVICE SAFETY BLOCK', 'Is VIP account me zyada devices detect hue hain. Admin se contact karein.', '#FAC748')
                return _vip_block_html('ACCESS BLOCKED', 'VIP account safety check failed. Admin se contact karein.', '#FF5D5D')
            user_payments = [p for p in state.get("payments", []) if p.get("userId") == vip_id]
            isolated_state = { "activeId": vip_id, "broadcasts": state.get("broadcasts", []), "profiles": { vip_id: state["profiles"][vip_id] }, "paymentMethods": state.get("paymentMethods", {"upi":"","phonepeUpi":"","gpayUpi":"","paytmUpi":"","name":TITAN_PAYMENT_NAME,"phone":"","qr":""}), "payments": user_payments, "withdrawals": [w for w in state.get("withdrawals", []) if w.get("userId") == vip_id], "resultRecords": state.get("resultRecords", {}), "resultTargets": [], "resultSettings": state.get("resultSettings", {"autoScrapeEnabled": True, "useForwardTargetsForResults": True}), "marketRegistry": state.get("marketRegistry", _default_market_registry()), "wallets": {vip_id: state.get("wallets", {}).get(vip_id, {})}, "walletTransactions": [t for t in _wallet_transactions_from_state(state, vip_id, 500)], "walletSettings": state.get("walletSettings", _default_wallet_settings()), "entrySettings": state.get("entrySettings", _default_entry_settings()), "entries": [e for e in state.get("entries", []) if e.get("userId") == vip_id], "settlementRecords": state.get("settlementRecords", {}), "ledgerAutoMarkRecords": state.get("ledgerAutoMarkRecords", {}), "settlementSettings": state.get("settlementSettings", _default_settlement_settings()), "paymentSettings": state.get("paymentSettings", _default_payment_settings()), "loadForwarder": state.get("loadForwarder", _default_load_forwarder_settings()), "loadForwarderOutbox": [], "spamGuardSettings": state.get("spamGuardSettings", _default_spam_guard_settings()), "spamGuardEvents": [], "whatsappSafetySettings": state.get("whatsappSafetySettings", _default_whatsapp_safety_settings()), "whatsappSafetyTargets": state.get("whatsappSafetyTargets", {}), "whatsappSafetyEvents": [], "ledgerSchedules": {k:v for k,v in (state.get("ledgerSchedules", {}) or {}).items() if str(k).startswith(vip_id + "|")}, "userSafety": {vip_id: (state.get("userSafety", {}) or {}).get(vip_id, {})} if isinstance(state.get("userSafety"), dict) else {}, "userSafetySettings": _vip_safety_defaults(state) }
            _mk, _bm, _links = _market_context_for_state(isolated_state, purpose='ledger')
            return render_template_string(HTML_TEMPLATE, state=isolated_state, markets=_mk, baseMarkets=_bm, chartLinks=_links, is_master=False, manifest_url=manifest_url, security_config={'enabled': bool(TITAN_SECURITY_STRICT), 'version': SECURITY_LOCKDOWN_VERSION}, app_config=_client_app_config())
        else:
            blocked_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
                <title>Access Denied</title>
            </head>
            <body style="background:#17212B; color:#fff; font-family:sans-serif; text-align:center; padding:50px 20px;">
                <div style="background:#232E3C; border:1px solid #FF5D5D; padding:30px; border-radius:16px; margin-top:20vh; box-shadow: 0 4px 20px rgba(239, 68, 68, 0.2);">
                    <h2 style="color:#FF5D5D; margin-top:0; font-weight:900;">MEMBERSHIP EXPIRED</h2>
                    <p style="color:#7A9CB8; font-size:14px; margin-bottom:0; line-height:1.5;">Aapka access admin dwara hata diya gaya hai. Kripya naye app link ke liye Admin se sampark karein.</p>
                </div>
            </body>
            </html>
            """
            return blocked_html
    else:
        state["activeId"] = "admin1"
        _mk, _bm, _links = _market_context_for_state(state, purpose='ledger')
        return render_template_string(HTML_TEMPLATE, state=state, markets=_mk, baseMarkets=_bm, chartLinks=_links, is_master=True, manifest_url=manifest_url, security_config={'enabled': bool(TITAN_SECURITY_STRICT), 'version': SECURITY_LOCKDOWN_VERSION}, app_config=_client_app_config())


# ==========================================================
# LEDGER AUTO-MARK SAVE MERGE GUARD
# Gateway/Python auto PASS/FAIL marks Firebase in background. The admin PWA may still
# have an older local copy open; a normal autosave must not overwrite fresh PASS/FAIL
# back to WAIT. This merge preserves server-side auto-marked ledger cards when the
# incoming browser copy is stale.
# ==========================================================
def _safe_deepcopy(obj):
    try:
        return json.loads(json.dumps(obj))
    except Exception:
        return obj

def _ledger_auto_mark_save_key(v):
    return str(v) if v is not None else ''

def _ledger_rec_digits_key(rec):
    import re
    if not isinstance(rec, dict):
        return ''
    return ','.join(re.findall(r'\d+', str(rec.get('d', ''))))

def _ledger_rec_rate_key(rec):
    if not isinstance(rec, dict):
        return ''
    try:
        return str(float(rec.get('r') or 0))
    except Exception:
        return str(rec.get('r') or '')

def _is_server_auto_marked_rec(rec):
    if not isinstance(rec, dict):
        return False
    return str(rec.get('s') or '').upper() in ('PASS', 'FAIL') and bool(rec.get('autoMarkedAt') or rec.get('autoMarkedByResult'))

def _copy_auto_mark_fields(dst, src):
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return dst
    for k in ['s', 'autoMarkedAt', 'autoMarkedByResult', 'autoMarkStage', 'autoMarkMarket', 'autoMarkWinDigit']:
        if k in src:
            dst[k] = src.get(k)
    return dst

def _merge_result_source_of_truth(incoming, existing):
    """Preserve server-generated result/settlement/auto-mark stores from Firebase."""
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return incoming
    # These stores are updated through dedicated APIs/Gateway. Browser full-save should not erase them.
    for key in ['resultRecords', 'ledgerAutoMarkRecords', 'settlementRecords']:
        old = existing.get(key)
        if isinstance(old, dict):
            new = incoming.get(key) if isinstance(incoming.get(key), dict) else {}
            merged = _safe_deepcopy(new)
            # Prefer existing/server for overlapping generated records; keep any brand-new local keys too.
            def merge_pref_server(dst, src):
                if not isinstance(src, dict):
                    return dst
                if not isinstance(dst, dict):
                    dst = {}
                for sk, sv in src.items():
                    if isinstance(sv, dict):
                        dst[sk] = merge_pref_server(dst.get(sk) if isinstance(dst.get(sk), dict) else {}, sv)
                    else:
                        dst[sk] = sv
                return dst
            incoming[key] = merge_pref_server(merged, old)
    return incoming


def _merge_ledger_schedules_source_of_truth(incoming, existing):
    """scheduleRuntimePreserveGuard: keep persistent daily ledger schedules safe during browser autosave.

    Ledger schedules are the source of truth for daily repeat. They are changed through
    /api/schedule_targets, while the PWA also posts a full /save payload from local state.
    If an older browser/PWA cache autosaves without the latest ledgerSchedules map, it must
    not erase the server's active daily schedules. This preserves existing schedules unless
    the incoming payload clearly contains an updated/deleted schedule map from the current app.
    """
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return incoming
    old_store = existing.get('ledgerSchedules') if isinstance(existing.get('ledgerSchedules'), dict) else {}
    new_store = incoming.get('ledgerSchedules') if isinstance(incoming.get('ledgerSchedules'), dict) else None
    if not old_store:
        if new_store is None:
            incoming['ledgerSchedules'] = {}
        return incoming
    # If an old/stale UI posts no store or an empty store while server has schedules,
    # keep server schedules so daily repeat does not silently stop.
    if new_store is None or (not new_store and old_store):
        incoming['ledgerSchedules'] = _safe_deepcopy(old_store)
        incoming.setdefault('scheduleRuntimePreserveGuard', {})['lastPreservedAt'] = _now_iso_local()
        incoming['scheduleRuntimePreserveGuard']['reason'] = 'incoming_missing_or_empty_ledgerSchedules'
        return incoming
    merged = _safe_deepcopy(new_store)
    # Per-schedule merge: incoming wins only when it carries a newer/equal updatedAt,
    # otherwise server wins. This protects against stale PWA autosave while still allowing
    # real edits from /api/schedule_targets and current UI to persist.
    for key, old_item in old_store.items():
        if not isinstance(old_item, dict):
            if key not in merged:
                merged[key] = old_item
            continue
        new_item = merged.get(key)
        if not isinstance(new_item, dict):
            merged[key] = _safe_deepcopy(old_item)
            continue
        old_ts = str(old_item.get('updatedAt') or old_item.get('createdAt') or '')
        new_ts = str(new_item.get('updatedAt') or new_item.get('createdAt') or '')
        if old_ts and (not new_ts or new_ts < old_ts):
            merged[key] = _safe_deepcopy(old_item)
    incoming['ledgerSchedules'] = merged
    return incoming




def _ledger_rec_has_user_payload(rec):
    if not isinstance(rec, dict):
        return False
    # Explicit user actions must count as payload even when the user intentionally
    # cleared all fields. Otherwise the old server record gets restored and the UI
    # looks like delete/clear/PASS/FAIL did not save.
    for k in ('_explicitClearedAt', '_digitClearedAt', '_rateClearedAt', '_manualStatusAt', '_updatedAt', '_dirtyAt', '_resetAt'):
        if str(rec.get(k) or '').strip():
            return True
    if str(rec.get('_sourceAction') or '').strip():
        return True
    if str(rec.get('s') or 'WAIT').upper() not in ('', 'WAIT'):
        return True
    for k in ('d', 'r', 'od', 'trick', 'schTime', 'scheduleTime'):
        if str(rec.get(k) or '').strip():
            return True
    if rec.get('schTargets') or rec.get('targets'):
        return True
    return False


def _merge_ledger_records_source_of_truth(incoming, existing):
    """CORE_STABILITY_FIX: protect ledger records from stale full-state overwrite.

    UI can reorder/add/delete markets. The old app saved by numeric index, so a full /save
    from a stale browser can blank or move a record. This merge prefers the incoming record
    only for the same stable _ledgerKey; otherwise existing non-blank server records are kept.
    """
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return incoming
    in_profiles = incoming.setdefault('profiles', {}) if isinstance(incoming.get('profiles'), dict) else {}
    old_profiles = existing.get('profiles', {}) if isinstance(existing.get('profiles'), dict) else {}
    dicts = ('data', 'jodiData', 'pannelData')

    def normalize_bucket(bucket):
        return bucket if isinstance(bucket, dict) else {}

    def rec_key(rec):
        return str(rec.get('_ledgerKey') or '') if isinstance(rec, dict) else ''

    def preserve_schedule_fields(dst, src):
        if not isinstance(dst, dict) or not isinstance(src, dict):
            return dst
        if not dst.get('schTime') and src.get('schTime'):
            dst['schTime'] = src.get('schTime')
        if not dst.get('scheduleTime') and src.get('scheduleTime'):
            dst['scheduleTime'] = src.get('scheduleTime')
        if (not dst.get('schTargets')) and src.get('schTargets'):
            dst['schTargets'] = _safe_deepcopy(src.get('schTargets'))
        if (not dst.get('targets')) and src.get('targets'):
            dst['targets'] = _safe_deepcopy(src.get('targets'))
        return dst

    for pid, old_prof in old_profiles.items():
        if not isinstance(old_prof, dict):
            continue
        old_days = old_prof.get('dayRecords', {}) if isinstance(old_prof.get('dayRecords'), dict) else {}
        if not old_days:
            continue
        # If the current admin payload intentionally removed a VIP profile, do not
        # resurrect it while preserving ledger records from the latest Firebase snapshot.
        if pid not in in_profiles:
            continue
        in_prof = in_profiles.get(pid)
        if not isinstance(in_prof, dict):
            continue
        in_days = in_prof.setdefault('dayRecords', {}) if isinstance(in_prof.get('dayRecords'), dict) else {}
        for date_key, old_day in old_days.items():
            if not isinstance(old_day, dict):
                continue
            in_day = in_days.setdefault(date_key, {})
            if not isinstance(in_day, dict):
                in_days[date_key] = {}
                in_day = in_days[date_key]
            for dict_name in dicts:
                old_bucket = normalize_bucket(old_day.get(dict_name))
                if not old_bucket:
                    continue
                in_bucket = normalize_bucket(in_day.get(dict_name))
                in_day[dict_name] = in_bucket
                incoming_by_key = {}
                for ik, ir in list(in_bucket.items()):
                    mk = rec_key(ir)
                    if mk:
                        incoming_by_key[mk] = ik
                for ok, old_rec in list(old_bucket.items()):
                    if not isinstance(old_rec, dict) or not _ledger_rec_has_user_payload(old_rec):
                        continue
                    mk = rec_key(old_rec)
                    if mk and mk in incoming_by_key:
                        ik = incoming_by_key[mk]
                        in_rec = in_bucket.get(ik)
                        if not _ledger_rec_has_user_payload(in_rec):
                            in_bucket[ik] = _safe_deepcopy(old_rec)
                        else:
                            # v7: for the same stable market key, prefer the record with the
                            # newer edit stamp. This is the missing global guard that prevents a
                            # non-ledger full save from restoring an older blank rate/status over
                            # a Firebase child-path ledger commit. Manual/reset records still win
                            # when their stamp is current/newer.
                            try:
                                old_stamp = _ledger_commit_stamp(old_rec) if '_ledger_commit_stamp' in globals() else 0
                                new_stamp = _ledger_commit_stamp(in_rec) if '_ledger_commit_stamp' in globals() else 0
                            except Exception:
                                old_stamp = new_stamp = 0
                            if old_stamp and (not new_stamp or old_stamp > new_stamp):
                                kept = _safe_deepcopy(old_rec)
                                preserve_schedule_fields(kept, in_rec)
                                in_bucket[ik] = kept
                            else:
                                preserve_schedule_fields(in_rec, old_rec)
                                if not in_rec.get('_ledgerKey'):
                                    in_rec['_ledgerKey'] = mk
                                if not in_rec.get('_marketName') and old_rec.get('_marketName'):
                                    in_rec['_marketName'] = old_rec.get('_marketName')
                                in_bucket[ik] = in_rec
                        continue
                    # Legacy/no-key or missing-by-key fallback: preserve under the old numeric slot only
                    # when incoming slot is absent/blank. Never overwrite a non-blank new user edit.
                    ik = str(ok)
                    in_rec = in_bucket.get(ik)
                    if in_rec is None:
                        try:
                            in_rec = in_bucket.get(int(ok))
                            ik = int(ok)
                        except Exception:
                            pass
                    if not _ledger_rec_has_user_payload(in_rec):
                        in_bucket[str(ok)] = _safe_deepcopy(old_rec)
    incoming.setdefault('ledgerStabilityGuard', {})['lastMergedAt'] = _now_iso_local()
    incoming['ledgerStabilityGuard']['mode'] = 'marketKey-source-of-truth'
    return incoming

def _preserve_server_ledger_auto_marks(incoming, existing):
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return incoming
    in_profiles = incoming.setdefault('profiles', {}) if isinstance(incoming.get('profiles'), dict) else {}
    old_profiles = existing.get('profiles', {}) if isinstance(existing.get('profiles'), dict) else {}
    for pid, old_prof in old_profiles.items():
        if not isinstance(old_prof, dict):
            continue
        old_days = old_prof.get('dayRecords', {}) if isinstance(old_prof.get('dayRecords'), dict) else {}
        if not old_days:
            continue
        # Deleted VIP profiles must stay deleted; auto-mark preservation should only
        # run for profiles still present in the incoming admin state.
        if pid not in in_profiles:
            continue
        in_prof = in_profiles.get(pid)
        if not isinstance(in_prof, dict):
            continue
        in_days = in_prof.setdefault('dayRecords', {}) if isinstance(in_prof.get('dayRecords'), dict) else {}
        for date, old_day in old_days.items():
            if not isinstance(old_day, dict):
                continue
            in_day = in_days.setdefault(date, {})
            if not isinstance(in_day, dict):
                continue
            for dict_name in ['data', 'jodiData', 'pannelData']:
                old_bucket = old_day.get(dict_name, {}) if isinstance(old_day.get(dict_name), dict) else {}
                if not old_bucket:
                    continue
                in_bucket = in_day.setdefault(dict_name, {}) if isinstance(in_day.get(dict_name), dict) else {}
                for idx, old_rec in old_bucket.items():
                    if not _is_server_auto_marked_rec(old_rec):
                        continue
                    key = str(idx)
                    in_rec = in_bucket.get(key)
                    if in_rec is None:
                        in_rec = in_bucket.get(idx)
                    if not isinstance(in_rec, dict):
                        in_bucket[key] = _safe_deepcopy(old_rec)
                        continue
                    incoming_status = str(in_rec.get('s') or 'WAIT').upper()
                    same_payload = (_ledger_rec_digits_key(in_rec) == _ledger_rec_digits_key(old_rec) and _ledger_rec_rate_key(in_rec) == _ledger_rec_rate_key(old_rec))
                    incoming_auto_at = _ledger_auto_mark_save_key(in_rec.get('autoMarkedAt'))
                    old_auto_at = _ledger_auto_mark_save_key(old_rec.get('autoMarkedAt'))
                    manual_override_at = _ledger_auto_mark_save_key(in_rec.get('_manualStatusAt') or in_rec.get('_explicitClearedAt') or in_rec.get('_updatedAt') or in_rec.get('_dirtyAt'))
                    source_action = str(in_rec.get('_sourceAction') or '').lower()
                    # User/manual actions must beat old server auto-mark records. Without this,
                    # clicking PASS/FAIL/Unlock after an auto PASS/FAIL reverts on refresh.
                    if manual_override_at or source_action in ('manual_status', 'manual_input', 'reset_card', 'card_unlock', 'scrape_digits', 'combo_scrape', 'trick_apply', 'trick_undo'):
                        continue
                    stale_browser_copy = (incoming_status in ('', 'WAIT') or not incoming_auto_at or (old_auto_at and incoming_auto_at < old_auto_at))
                    if same_payload and stale_browser_copy:
                        _copy_auto_mark_fields(in_rec, old_rec)
                        in_bucket[key] = in_rec
    return incoming



# ==========================================================
# LEDGER FIREBASE LIVE COMMIT API
# Ledger card edits must be persisted directly to Firebase. Browser local JSON /
# pending patches are not a source of truth for digits/rates, because live sync can
# otherwise replay stale blank rate records after the UI initially showed a rate.
# ==========================================================
def _ledger_commit_dict_name(typ):
    typ = str(typ or '').lower().strip()
    if typ == 'ank':
        return 'data'
    if typ == 'jodi':
        return 'jodiData'
    if typ == 'pannel':
        return 'pannelData'
    return ''

def _ledger_commit_clean_record(rec):
    if not isinstance(rec, dict):
        rec = {}
    allowed = {
        's','d','r','od','trick','schTime','schTargets','targets',
        '_ledgerKey','_marketName','_ledgerType','_ledgerIndex','_ledgerDate',
        '_updatedAt','_dirtyAt','_sourceAction','_manualStatusAt','_manualStatusBy',
        '_explicitClearedAt','_digitClearedAt','_rateClearedAt','_resetAt',
        '_deleted','_deletedAt','_deletedBy','deleted','deletedAt',
        '_manualR','_autoR','_digitsTouchedAt','_manualRateAt','_autoRateAt','_autoRateReason',
        '_recoveryAutoR','_recoveryDebt','_recoveryUnreal','_recoveryMargin','_recoveryTargetProfit','_recoveryTrackKey','_recoveryFromIdx','_recoveryBaseRate',
        'autoMarkedAt','autoMarkedByResult','autoMarkStage','autoMarkMarket','autoMarkWinDigit'
    }
    out = {}
    for k, v in rec.items():
        if k in allowed:
            out[k] = v
    out.setdefault('s', 'WAIT')
    out.setdefault('d', '')
    out.setdefault('r', '')
    return out

def _ledger_commit_market_name_from_key(market_key):
    key = str(market_key or '')
    if '|' not in key:
        return ''
    return key.split('|', 1)[1].strip()

def _ledger_commit_stamp(rec):
    if not isinstance(rec, dict):
        return 0.0
    candidates = [rec.get('_dirtyAt'), rec.get('_updatedAt'), rec.get('_autoRateAt'), rec.get('_manualRateAt'), rec.get('_digitsTouchedAt')]
    best = 0.0
    for v in candidates:
        try:
            if isinstance(v, (int, float)):
                best = max(best, float(v))
                continue
            txt = str(v or '').strip()
            if not txt:
                continue
            if txt.endswith('Z'):
                txt = txt[:-1] + '+00:00'
            # Browser ISO strings sometimes have timezone, sometimes not.
            dt = datetime.datetime.fromisoformat(txt)
            best = max(best, dt.timestamp() * 1000.0)
        except Exception:
            continue
    return best

def _ledger_commit_merge_record(existing, incoming, typ, idx, market_key, date_key, action='ledger_card_update'):
    existing = existing if isinstance(existing, dict) else {}
    final = _ledger_commit_clean_record(incoming)
    # v41 Base manual overwrite: incoming ledger card always wins.
    # No Firebase Guard / no stale timestamp preservation over manual UI edits.
    # Preserve persistent schedule fields if the browser only changed digits/rate/status.
    for k in ('schTime', 'scheduleTime'):
        if not final.get(k) and existing.get(k):
            final[k] = existing.get(k)
    for k in ('schTargets', 'targets'):
        if (not final.get(k)) and existing.get(k):
            final[k] = _safe_deepcopy(existing.get(k))
    final['_ledgerKey'] = str(market_key or final.get('_ledgerKey') or '')
    final['_marketName'] = str(final.get('_marketName') or _ledger_commit_market_name_from_key(final.get('_ledgerKey')) or '').upper().strip()
    final['_ledgerType'] = str(typ or final.get('_ledgerType') or '').lower().strip()
    final['_ledgerIndex'] = int(idx)
    final['_ledgerDate'] = str(date_key)
    final['_updatedAt'] = final.get('_updatedAt') or _now_iso_local()
    final['_dirtyAt'] = final.get('_dirtyAt') or final['_updatedAt']
    final['_sourceAction'] = action or final.get('_sourceAction') or 'ledger_card_update'
    return final

def _ledger_commit_audit_entry(profile_id, typ, idx, market_key, date_key, action, rec, apply_to_vips=False):
    """Small audit entry for direct ledger card commits.

    The ledger card itself is still saved only at its exact profile/day/type/index
    Firebase child path; this audit row is a separate operational trail so refresh
    issues can be traced without doing a root save.
    """
    safe_rec = rec if isinstance(rec, dict) else {}
    return {
        'id': 'ledger_update_' + uuid.uuid4().hex[:12],
        'time': _now_iso_local(),
        'action': 'ledger_card_update',
        'detail': {
            'profileId': str(profile_id),
            'date': str(date_key),
            'type': str(typ),
            'idx': int(idx),
            'marketKey': str(market_key or ''),
            'sourceAction': str(action or 'ledger_card_update'),
            'status': str(safe_rec.get('s') or 'WAIT'),
            'hasDigits': bool(str(safe_rec.get('d') or '').strip()),
            'hasRate': bool(str(safe_rec.get('r') or '').strip()),
            'deleted': bool(safe_rec.get('_deleted') or safe_rec.get('deleted')),
            'applyToVips': bool(apply_to_vips),
            'exactChildPathOnly': True
        }
    }

def _ledger_commit_upsert_profile(state_obj, profile_id, typ, idx, market_key, date_key, record, action):
    profiles = state_obj.setdefault('profiles', {})
    profile = profiles.get(profile_id)
    if not isinstance(profile, dict):
        return None
    day_records = profile.setdefault('dayRecords', {})
    day = day_records.setdefault(str(date_key), {})
    dict_name = _ledger_commit_dict_name(typ)
    bucket = day.setdefault(dict_name, {})
    if not isinstance(bucket, dict):
        bucket = {}
        day[dict_name] = bucket
    key = str(int(idx))
    existing = bucket.get(key)
    if existing is None:
        existing = bucket.get(int(idx))
    final = _ledger_commit_merge_record(existing, record, typ, idx, market_key, date_key, action)
    bucket[key] = final
    # Keep old integer-key copy from fighting with string-key source of truth.
    try:
        if int(idx) in bucket:
            del bucket[int(idx)]
    except Exception:
        pass
    return final


@app.route('/api/stability_check')
def api_stability_check():
    gateway_url = _gateway_url('/runtime_stability_status')
    reachable = False
    gateway_payload = None
    gateway_error = ''
    try:
        r = _gateway_request('GET', '/runtime_stability_status', timeout=3)
        reachable = getattr(r, 'status_code', 500) < 500
        try:
            gateway_payload = r.json()
        except Exception:
            gateway_payload = {'raw': getattr(r, 'text', '')[:200]}
    except Exception as e:
        gateway_error = str(e)[:300]
    gp = gateway_payload if isinstance(gateway_payload, dict) else {}
    return jsonify({
        'status': 'success',
        'version': RUNTIME_STABILITY_VERSION,
        'firebaseConfigured': bool(get_firebase_url()),
        'gatewayUrl': gateway_url,
        'gatewayReachable': reachable,
        'gatewayError': gateway_error,
        'ledgerChildPathWritesEnabled': True,
        'rootSaveDisabledForNormalOperations': bool(gp.get('rootSaveDisabledForNormalOperations', True)),
        'scheduleIdempotencyEnabled': bool(gp.get('scheduleIdempotencyEnabled', True)),
        'scheduleFirebaseLastSentEnabled': bool(gp.get('scheduleFirebaseLastSentEnabled', True)),
        'walletIdempotencyEnabled': bool(gp.get('walletIdempotencyEnabled', True)),
        'gateway': gp,
    })

@app.route('/api/ledger_card_update', methods=['POST'])
def api_ledger_card_update():
    payload = request.json if isinstance(request.json, dict) else {}
    active_id = str(payload.get('activeId') or 'admin1')
    if active_id not in ['admin1', 'admin2', 'admin3']:
        return jsonify({'status': 'rejected', 'message': 'Only admin can update ledger cards.'}), 403
    typ = str(payload.get('type') or '').lower().strip()
    dict_name = _ledger_commit_dict_name(typ)
    if not dict_name:
        return jsonify({'status': 'error', 'message': 'Invalid ledger type.'}), 400
    try:
        idx = int(payload.get('idx'))
    except Exception:
        return jsonify({'status': 'error', 'message': 'Invalid ledger index.'}), 400
    if idx < 0:
        return jsonify({'status': 'error', 'message': 'Invalid ledger index.'}), 400
    date_key = str(payload.get('date') or _safe_today())
    profile_id = str(payload.get('profileId') or active_id or 'admin1')
    market_key = str(payload.get('marketKey') or (payload.get('record') or {}).get('_ledgerKey') or '')
    action = str(payload.get('action') or 'ledger_card_update')
    record = payload.get('record') if isinstance(payload.get('record'), dict) else {}
    apply_to_vips = bool(payload.get('applyToVips')) and profile_id == 'admin1'

    state = migrate_and_get_state()
    _ensure_foundation_state(state)
    saved_records = {}
    final = _ledger_commit_upsert_profile(state, profile_id, typ, idx, market_key, date_key, record, action)
    if final is None:
        return jsonify({'status': 'error', 'message': 'Profile not found.'}), 404
    saved_records[profile_id] = final

    if apply_to_vips:
        for pid in list((state.get('profiles') or {}).keys()):
            if str(pid) == 'admin1' or str(pid).startswith('admin'):
                continue
            vip_final = _ledger_commit_upsert_profile(state, str(pid), typ, idx, market_key, date_key, record, action)
            if vip_final is not None:
                saved_records[str(pid)] = vip_final

    audit_log = state.setdefault('auditLog', [])
    if not isinstance(audit_log, list):
        audit_log = []
        state['auditLog'] = audit_log
    audit_log.append(_ledger_commit_audit_entry(profile_id, typ, idx, market_key, date_key, action, final, apply_to_vips))
    if len(audit_log) > 1000:
        del audit_log[:-1000]

    # v6: write only changed ledger card paths plus the audit log child.
    # Do not save the full Firebase root and do not write ledger metadata siblings.
    # This prevents overlapping card edits from blanking/overwriting previous cards.
    try:
        for pid, rec in saved_records.items():
            _firebase_put_child(['profiles', str(pid), 'dayRecords', str(date_key), dict_name, str(idx)], rec)
        _firebase_put_child(['auditLog'], audit_log[-1000:])
    except Exception as e:
        print('Ledger atomic child commit error:', e)
        return jsonify({'status': 'error', 'message': 'Firebase atomic ledger commit failed: ' + str(e)}), 500

    return jsonify({
        'status': 'success',
        'firebaseLiveCommit': True,
        'atomicFirebaseCommit': True,
        'date': date_key,
        'profileId': profile_id,
        'type': typ,
        'idx': idx,
        'marketKey': market_key,
        'record': final,
        'records': saved_records,
        'ledgerSchedules': state.get('ledgerSchedules', {})
    })


@app.route('/save', methods=['POST'])
def save():
    incoming = request.json
    if not incoming:
        return jsonify({"status": "error", "message": "No JSON payload received", "manualOverwrite": True}), 400

    active_id = incoming.get("activeId")
    is_master_saving = (
        active_id in ["admin1", "admin2", "admin3"]
        or "admin1" in incoming.get("profiles", {})
        or "admin2" in incoming.get("profiles", {})
        or "admin3" in incoming.get("profiles", {})
    )

    if is_master_saving:
        # v42 Ledger render/source fix:
        # Admin settings/market add-delete still come from the current UI payload, but
        # ledger card records are also written through /api/ledger_card_update child PUTs.
        # Before a full /save, merge against the latest Firebase snapshot so an older
        # browser render cannot restore duplicate/old ledger records after the user
        # manually adds, clears, resets, PASS/FAILs, or deletes card content.
        try:
            latest = load_from_firebase()
            if isinstance(latest, dict) and latest.get('profiles'):
                _merge_ledger_records_source_of_truth(incoming, latest)
                _preserve_server_ledger_auto_marks(incoming, latest)
                incoming.setdefault('ledgerRenderSyncGuard', {})['lastMergedAt'] = _now_iso_local()
                incoming['ledgerRenderSyncGuard']['mode'] = 'full-save-preserves-newest-manual-ledger-edits'
        except Exception as merge_err:
            _obs_exception('ledger_render_sync_guard_merge_failed', merge_err, {'route': '/save'})
        try:
            _ensure_foundation_state(incoming)
            # Patch 4: normal /save is a UI sync path, not an import/restore path.
            # Keep it on narrow Firebase children that the UI legitimately edits,
            # instead of replaying every top-level child from the browser snapshot.
            normal_save_allowed = {
                'ledgerSchedules', 'scheduleTargets', 'botSchedule', 'botSchedules',
                'targets', 'resultTargets', 'loadForwarder', 'loadForwarderOutbox',
                'groups', 'contacts', 'whatsappGroups', 'whatsappContacts',
                'spamGuardSettings', 'spamGuardEvents', 'whatsappSafetySettings',
                'whatsappSafetyTargets', 'whatsappSafetyEvents', 'entrySettings',
                'resultSettings', 'resultRecords', 'paymentOutbox',
                'marketRegistry', 'marketLocks', 'marketAliases'
            }
            normal_updates = {k: v for k, v in incoming.items() if k in normal_save_allowed}
            _firebase_put_top_level_children(incoming, normal_updates, audit=False)
        except Exception as save_err:
            _obs_exception('normal_save_child_path_failed', save_err, {'route': '/save'})
            return jsonify({"status": "error", "message": "Firebase child-path save failed.", "manualOverwrite": False}), 500
        return jsonify({
            "status": "success",
            "manualOverwrite": False,
            "childPathSave": True,
            "ledgerRenderSyncGuard": True,
            "source": "ledger_render_sync_guard_v42_child_paths"
        })
    else:
        return jsonify({"status": "rejected", "msg": "Client app is restricted to Read-Only mode."})

@app.route('/api/submit_payment', methods=['POST'])
def submit_payment():
    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Invalid request"}), 400
    utr = str(data.get('utr', '')).strip()
    amount = _payment_float(data.get('amount', 0))
    user_id = data.get('userId')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Valid user missing'}), 400
    claimed_vip = str(request.headers.get('X-Titan-Vip-Id') or request.args.get('vip') or '').strip()
    if claimed_vip and claimed_vip != str(user_id).strip():
        return jsonify({'status': 'error', 'message': 'VIP identity mismatch', 'userSafety': True}), 403
    # v15: public VIP payment submit must not bypass server-side VIP access status.
    pre_state = migrate_and_get_state()
    vip_access = _vip_runtime_access_check(pre_state, user_id, record=True)
    if TITAN_VIP_ACCESS_ENFORCE and not vip_access.get('allowed'):
        return jsonify({'status': 'blocked', 'message': 'VIP access blocked: ' + ','.join(vip_access.get('reasons') or []), 'userSafety': vip_access}), int(vip_access.get('httpStatus') or 403)
    if amount <= 0:
        return jsonify({'status': 'error', 'message': 'Amount 0 se zyada hona chahiye'}), 400

    def mutator(state):
        _ensure_foundation_state(state)
        if user_id not in state.get('profiles', {}):
            _money_error('Valid user missing', 400)
        state.setdefault('payments', [])
        settings = state.setdefault('paymentSettings', _default_payment_settings())
        if not settings.get('paymentAutomationEnabled', True):
            _money_error('Payment automation OFF hai.', 403)
        # Strong duplicate UTR protection inside latest Firebase transaction.
        utr_norm = _normalize_utr(utr)
        if utr_norm and settings.get('duplicateUtrBlock', True):
            for pmt in state.get('payments', []):
                if isinstance(pmt, dict) and _normalize_utr(pmt.get('utr')) == utr_norm and str(pmt.get('status','')).lower() != 'rejected':
                    return ({'status': 'success', 'flag': 'duplicate', 'paymentStatus': 'rejected', 'paymentId': pmt.get('id'), 'message': 'Duplicate UTR already exists; blocked safely.', 'duplicateSafe': True}, 200)
        autoFlag = _payment_risk_flag(state, user_id, amount, utr)
        decision = 'pending'
        if autoFlag == 'duplicate' and settings.get('duplicateUtrBlock', True):
            decision = 'blocked'
        payment = {
            'id': str(uuid.uuid4())[:8].upper(),
            'userId': user_id,
            'userName': data.get('userName') or state.get('profiles', {}).get(user_id, {}).get('name', user_id),
            'amount': amount,
            'utr': utr,
            'utrNormalized': utr_norm,
            'planLabel': data.get('planLabel', ''),
            'image': data.get('image', ''),
            'status': 'pending' if decision != 'blocked' else 'rejected',
            'autoFlag': autoFlag,
            'riskLevel': 'LOW' if autoFlag == 'safe' else ('HIGH' if autoFlag in ['duplicate', 'high_amount', 'utr_missing'] else 'MEDIUM'),
            'decision': decision,
            'walletCredited': False,
            'time': datetime.datetime.now().strftime('%d-%m-%Y %I:%M %p'),
            'createdAt': _now_iso_local(),
            'moneyAtomicCreated': True
        }
        if decision == 'blocked':
            payment['rejectReason'] = 'Duplicate UTR blocked automatically.'
            payment['rejectedAt'] = _now_iso_local()
        state['payments'].append(payment)
        _add_audit(state, 'payment_submitted_atomic', {'paymentId': payment['id'], 'userId': user_id, 'amount': amount, 'flag': autoFlag, 'status': payment['status']})
        _queue_payment_message(state, user_id, f"💳 *PAYMENT SUBMITTED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{payment['id']}\n💵 *Amount:* ₹{amount:g}\n🔢 *UTR:* {utr or '-'}\n⚡ *Status:* {payment['status'].upper()}\n📝 Admin verification ke baad wallet update hoga.", {'type': 'payment_submitted', 'paymentId': payment['id']})
        return ({'status': 'success', 'flag': autoFlag, 'paymentStatus': payment['status'], 'paymentId': payment['id']}, 200)

    return _json_money_response(_money_atomic_commit('submit_payment', data, ['userId','amount','utr','planLabel'], mutator))


@app.route('/api/approve_payment', methods=['POST'])
def approve_payment():
    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Invalid request"}), 400
    pid = data.get('paymentId')
    if not pid:
        return jsonify({'status': 'error', 'message': 'paymentId missing'}), 400

    def mutator(state):
        _ensure_foundation_state(state)
        settings = state.setdefault('paymentSettings', _default_payment_settings())
        days = int(_payment_float(data.get('days', 30)))
        credit_wallet = bool(data.get('creditWallet', settings.get('approveCreditsWallet', True)))
        extend_membership = bool(data.get('extendMembership', settings.get('extendMembershipOnApprove', True)))
        payment = next((p for p in state.get('payments', []) if isinstance(p, dict) and p.get('id') == pid), None)
        if not payment:
            _money_error('Payment not found', 404)
        if payment.get('status') == 'approved':
            return ({'status': 'success', 'message': 'Already approved', 'payment': payment, 'wallets': state.get('wallets', {}), 'idempotentFinal': True}, 200)
        if payment.get('status') == 'rejected' and payment.get('decision') == 'blocked':
            _money_error('Blocked duplicate payment approve nahi ho sakta.', 400)
        user_id = payment.get('userId')
        wallet = None
        if credit_wallet and not payment.get('walletCredited'):
            wallet = _credit_wallet_from_payment(state, payment, f"Payment approved #{pid}")
        if extend_membership and user_id and user_id in state.get('profiles', {}):
            profile = state['profiles'][user_id]
            current_expiry = profile.get('expiryDate', '')
            now = datetime.datetime.now()
            if current_expiry:
                try:
                    base = datetime.datetime.fromisoformat(current_expiry)
                    if base < now:
                        base = now
                except Exception:
                    base = now
            else:
                base = now
            if days > 0:
                profile['expiryDate'] = (base + datetime.timedelta(days=days)).date().isoformat()
                payment['membershipDays'] = days
                payment['membershipExtended'] = True
        payment['status'] = 'approved'
        payment['approvedAt'] = _now_iso_local()
        payment['approvedBy'] = 'admin'
        payment['moneyAtomicApproved'] = True
        _add_audit(state, 'payment_approved_atomic', {'paymentId': pid, 'userId': user_id, 'amount': payment.get('amount'), 'walletCredited': bool(wallet), 'days': days if extend_membership else 0})
        bal_line = f"\n💰 *Wallet Balance:* ₹{_wallet_float(wallet.get('balance')):g}" if wallet else ""
        _queue_payment_message(state, user_id, f"✅ *PAYMENT APPROVED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{pid}\n💵 *Amount:* ₹{_payment_float(payment.get('amount')):g}\n🔢 *UTR:* {payment.get('utr') or '-'}{bal_line}\n📝 Wallet/payment update complete.", {'type': 'payment_approved', 'paymentId': pid})
        return ({'status': 'success', 'payment': payment, 'wallet': wallet, 'wallets': state.get('wallets', {})}, 200)

    return _json_money_response(_money_atomic_commit('approve_payment', data, ['paymentId','days','creditWallet','extendMembership'], mutator))


@app.route('/api/reject_payment', methods=['POST'])
def reject_payment():
    data = request.json or {}
    if not data:
        return jsonify({"status": "error", "message": "Invalid request"}), 400
    pid = data.get('paymentId')
    reason = str(data.get('reason') or 'Payment rejected by admin').strip()
    if not pid:
        return jsonify({'status': 'error', 'message': 'paymentId missing'}), 400

    def mutator(state):
        _ensure_foundation_state(state)
        payment = next((p for p in state.get('payments', []) if isinstance(p, dict) and p.get('id') == pid), None)
        if not payment:
            _money_error('Payment not found', 404)
        if payment.get('status') == 'approved':
            _money_error('Approved payment reject nahi ho sakta.', 400)
        if payment.get('status') == 'rejected':
            return ({'status': 'success', 'message': 'Already rejected', 'payment': payment, 'idempotentFinal': True}, 200)
        payment['status'] = 'rejected'
        payment['rejectReason'] = reason
        payment['rejectedAt'] = _now_iso_local()
        payment['moneyAtomicRejected'] = True
        _add_audit(state, 'payment_rejected_atomic', {'paymentId': pid, 'userId': payment.get('userId'), 'reason': reason})
        _queue_payment_message(state, payment.get('userId'), f"❌ *PAYMENT REJECTED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{pid}\n💵 *Amount:* ₹{_payment_float(payment.get('amount')):g}\n📝 *Reason:* {reason}", {'type': 'payment_rejected', 'paymentId': pid})
        return ({'status': 'success', 'payment': payment}, 200)

    return _json_money_response(_money_atomic_commit('reject_payment', data, ['paymentId','reason'], mutator))

@app.route('/api/payment_settings', methods=['POST'])
def api_payment_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('paymentSettings', _default_payment_settings())
    for key in ['paymentAutomationEnabled', 'requireUtr', 'duplicateUtrBlock', 'approveCreditsWallet', 'extendMembershipOnApprove', 'notifyUserPrivate']:
        if key in data:
            settings[key] = bool(data.get(key))
    if 'minAmount' in data:
        settings['minAmount'] = max(0, _payment_float(data.get('minAmount')))
    if 'maxAmount' in data:
        settings['maxAmount'] = max(settings.get('minAmount', 0), _payment_float(data.get('maxAmount')))
    _add_audit(state, 'payment_settings', settings)
    _firebase_put_top_level_children(state, {'paymentSettings': settings})
    return jsonify({'status': 'success', 'paymentSettings': settings})

@app.route('/api/payments')
def api_payments():
    state = migrate_and_get_state()
    payments = state.get('payments', []) if isinstance(state.get('payments', []), list) else []
    return jsonify({
        'status': 'success',
        'payments': payments,
        'paymentSettings': state.get('paymentSettings', _default_payment_settings()),
        'wallets': state.get('wallets', {}),
        'paymentOutbox': state.get('paymentOutbox', [])[-50:]
    })



def get_combined_digits_recent_to_old(jodis):
    seen = set()
    result = []

    recent_to_old = list(reversed(jodis))

    for j in recent_to_old:
        clean = j.replace("-", "").strip()

        if len(clean) == 2 and clean.isdigit():
            for d in [clean[0], clean[1]]:
                if d not in seen:
                    seen.add(d)
                    result.append(d)

                if len(result) >= 10:
                    return ",".join(result)

    return ",".join(result)

@app.route('/api/scrape_market', methods=['POST'])
def scrape_market():
    import urllib.request, urllib.error, gzip, re, ssl

    data = request.json
    if not data: return jsonify({'status': 'error', 'message': 'Invalid request'})

    market_name = data.get('market', '').strip().upper()
    url = None
    # PROFESSIONAL_LEDGER_STATE_FIX: resolve chart from saved Market Registry first,
    # then fallback to built-in CHART_LINKS. This makes newly-added markets scrapeable
    # after admin saves a chart URL in Market Manager.
    try:
        _state_for_links = migrate_and_get_state()
        _ensure_foundation_state(_state_for_links)
        chart_links = _chart_links_from_registry(_state_for_links.get('marketRegistry', {}))
    except Exception:
        chart_links = CHART_LINKS
    for link in list(chart_links or []) + list(CHART_LINKS or []):
        if str(link.get('n','')).strip().upper() == market_name:
            url = link.get('l')
            break

    if not url: return jsonify({'status': 'error', 'message': f'Market not found or chart URL missing: {market_name}'})

    def unique_seq(lst):
        seen, result = set(), []
        for x in lst:
            if x not in seen:
                seen.add(x)
                result.append(x)
            if len(result) == 10: break
        return ",".join(result)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',
        }
        req_obj = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        response = urllib.request.urlopen(req_obj, timeout=20, context=ctx)
        raw = response.read()

        enc = response.info().get('Content-Encoding', '')
        if enc == 'gzip': raw = gzip.decompress(raw)
        html = raw.decode('utf-8', errors='ignore')

        clean = re.sub(r'<[^>]+>', ' ', html)
        tokens = clean.split()
        jodis = [t.replace("-", "") for t in tokens if len(t.replace("-", "")) == 2 and t.replace("-", "").isdigit()]

        if not jodis: return jsonify({'status': 'error', 'message': 'Page pe koi jodi data nahi mila'})

        recent_to_old = list(reversed(jodis))
        seq_open  = unique_seq([j[0] for j in recent_to_old])
        seq_close = unique_seq([j[1] for j in recent_to_old])

        seen_j, recent_jodis = set(), []
        for j in recent_to_old:
            if j not in seen_j:
                seen_j.add(j)
                recent_jodis.append(j)
            if len(recent_jodis) == 10: break
        seq_jodi = ",".join(recent_jodis)

        combined_seq = get_combined_digits_recent_to_old(jodis)

        return jsonify({
            'status': 'success',
            'market': market_name,
            'open': seq_open,
            'close': seq_close,
            'combined': combined_seq,
            'jodi': seq_jodi,
            'total': len(jodis)
        })
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {str(e)}'})

@app.route('/api/save_payment_methods', methods=['POST'])
def save_payment_methods():
    data = request.json
    if not data: return jsonify({"status": "error"})
    state = migrate_and_get_state()
    state['paymentMethods'] = {
        'upi': str(data.get('upi') or '').strip(),
        'phonepeUpi': str(data.get('phonepeUpi') or '').strip(),
        'gpayUpi': str(data.get('gpayUpi') or '').strip(),
        'paytmUpi': str(data.get('paytmUpi') or '').strip(),
        'name': str(data.get('name') or TITAN_PAYMENT_NAME).strip() or TITAN_PAYMENT_NAME,
        'phone': str(data.get('phone') or '').strip(),
        'qr': str(data.get('qr') or '').strip(),
    }
    _firebase_put_top_level_children(state, {'paymentMethods': state['paymentMethods']}, audit=False)
    return jsonify({'status': 'success'})

@app.route('/api/set_expiry', methods=['POST'])
def set_expiry():
    data = request.json
    if not data: return jsonify({"status": "error"})
    state = migrate_and_get_state()
    user_id = data.get('userId')
    expiry = data.get('expiryDate')
    if user_id and user_id in state.get('profiles', {}):
        state['profiles'][user_id]['expiryDate'] = expiry
    _firebase_put_top_level_children(state, {'profiles': state.get('profiles', {})}, audit=False)
    return jsonify({'status': 'success'})


def _now_label():
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(APP_TZ)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def _clean_result_value(v):
    return str(v or '').strip().upper().replace(' ', '')

def _detect_result_stage(v):
    import re
    val = _clean_result_value(v)
    if re.fullmatch(r'\d{3}-\d', val):
        return 'open', val
    if re.fullmatch(r'\d{3}-\d{2}-\d{3}', val):
        return 'close', val
    return '', val

def _valid_base_market_name(market, state_obj=None, purpose='result'):
    market = str(market or '').strip().upper()
    if isinstance(state_obj, dict):
        allowed = _market_phase3_allowed(state_obj, market, purpose=purpose)
        if allowed.get('ok'):
            return allowed.get('market') or market
        return ''
    for m in BASE_MARKETS:
        if m['n'].upper() == market:
            return m['n']
    return ''

# ==========================================================
# LEDGER AUTO PASS/FAIL MARKER
# Result dekhkar ledger cards ko automatic PASS/FAIL mark karta hai.
# Safe rule: old/final result se direct jodi/close mark nahi hoga unless strict resultRecords me fresh open/close saved hai.
# ==========================================================
def _ledger_norm_market(v):
    import re
    return re.sub(r'[^A-Z0-9]+', ' ', str(v or '').upper().replace('SRIDEVI DAY', 'SRIDEV DAY')).strip()

def _ledger_result_parts(result):
    stage, val = _detect_result_stage(result)
    if stage == 'open':
        return {'stage': 'open', 'openPanel': val[:3], 'openAnk': val[-1], 'jodi': '', 'closeAnk': '', 'closePanel': ''}
    if stage == 'close':
        parts = val.split('-')
        jodi = parts[1] if len(parts) > 1 else ''
        return {'stage': 'close', 'openPanel': parts[0], 'openAnk': (jodi[:1] if jodi else ''), 'jodi': jodi, 'closeAnk': (jodi[1:2] if len(jodi) > 1 else ''), 'closePanel': (parts[2] if len(parts) > 2 else '')}
    return {'stage': ''}

def _ledger_digit_tokens(raw):
    import re
    return [x for x in re.findall(r'\d+', str(raw or '')) if x != '']

def _ledger_token_match(tokens, win, typ):
    win = str(win or '').strip()
    if not win:
        return False
    for tok in tokens:
        t = str(tok or '').strip()
        if typ == 'ank':
            if t and t[-1] == win[-1]:
                return True
        elif typ == 'jodi':
            if t.zfill(2)[-2:] == win.zfill(2)[-2:]:
                return True
        elif typ == 'pannel':
            if t.zfill(3)[-3:] == win.zfill(3)[-3:]:
                return True
    return False

def _ledger_dict_for_type(typ):
    return 'data' if typ == 'ank' else ('jodiData' if typ == 'jodi' else 'pannelData')

def _ledger_market_index_lookup(state_obj=None):
    if isinstance(state_obj, dict):
        arr, bases = _market_arrays_from_registry(state_obj.get('marketRegistry', {}), purpose='schedule')
    else:
        arr, bases = MARKETS, BASE_MARKETS
    ank_pan = {_ledger_norm_market(m.get('n')): i for i, m in enumerate(arr) if m.get('enabled', True) is not False and m.get('ledgerEnabled', True) is not False and m.get('resultEnabled', True) is not False and m.get('autoPassFailEnabled', True) is not False}
    jodi = {_ledger_norm_market(m.get('n')): i for i, m in enumerate(bases) if m.get('enabled', True) is not False and m.get('ledgerEnabled', True) is not False and m.get('resultEnabled', True) is not False and m.get('autoPassFailEnabled', True) is not False}
    return ank_pan, jodi

def _apply_ledger_mark_to_profile(profile, date, typ, idx, win, result, stage, market, only_wait=True):
    if not isinstance(profile, dict):
        return {'checked': 0, 'changed': 0, 'pass': 0, 'fail': 0}
    day_records = profile.setdefault('dayRecords', {})
    day = day_records.setdefault(date, {})
    dict_name = _ledger_dict_for_type(typ)
    bucket = day.setdefault(dict_name, {})
    rec = bucket.get(str(idx))
    if rec is None:
        rec = bucket.get(idx)
    if not isinstance(rec, dict):
        return {'checked': 0, 'changed': 0, 'pass': 0, 'fail': 0}
    raw_digits = rec.get('d', '')
    tokens = _ledger_digit_tokens(raw_digits)
    if not tokens:
        return {'checked': 0, 'changed': 0, 'pass': 0, 'fail': 0}
    current_status = str(rec.get('s') or 'WAIT').upper()
    if only_wait and current_status in ('PASS', 'FAIL', 'SKIP'):
        return {'checked': 1, 'changed': 0, 'pass': 0, 'fail': 0}
    new_status = 'PASS' if _ledger_token_match(tokens, win, typ) else 'FAIL'
    if current_status == new_status and rec.get('autoMarkedByResult') == result:
        return {'checked': 1, 'changed': 0, 'pass': 0, 'fail': 0}
    rec['s'] = new_status
    rec['autoMarkedAt'] = _now_iso_local()
    rec['autoMarkedByResult'] = result
    rec['autoMarkStage'] = stage
    rec['autoMarkMarket'] = market
    rec['autoMarkWinDigit'] = win
    bucket[str(idx)] = rec
    return {'checked': 1, 'changed': 1, 'pass': 1 if new_status == 'PASS' else 0, 'fail': 1 if new_status == 'FAIL' else 0}

def _ledger_auto_mark_for_result(state_obj, date, market, stage, result, force=False):
    """Mark ledger PASS/FAIL from resultRecords. Returns summary; mutates state_obj only when changed."""
    if not isinstance(state_obj, dict):
        return {'changed': False, 'message': 'state missing'}
    settings = state_obj.setdefault('settlementSettings', _default_settlement_settings())
    for k, v in _default_settlement_settings().items():
        settings.setdefault(k, v)
    if settings.get('autoLedgerMarking') is False and not force:
        return {'changed': False, 'skipped': True, 'reason': 'auto_ledger_marking_off'}
    date = str(date or _safe_today())
    base = _ledger_norm_market(market)
    stage = str(stage or '').lower().strip()
    result = _clean_result_value(result)
    parts = _ledger_result_parts(result)
    if stage not in ('open', 'close'):
        stage = parts.get('stage') or ''
    if not base or stage not in ('open', 'close') or parts.get('stage') != stage:
        return {'changed': False, 'skipped': True, 'reason': 'invalid_market_stage_result'}
    allowed = _market_phase3_allowed(state_obj, base, purpose='autopf', stage=stage)
    if not allowed.get('ok') and not force:
        return {'changed': False, 'skipped': True, 'reason': allowed.get('reason') or 'market_registry_blocked'}
    base = _ledger_norm_market(allowed.get('market') or base)

    # Strict no-old safety: for close, require same-day record having a real open first and matching close prefix.
    if stage == 'close':
        day_results = (state_obj.get('resultRecords') or {}).get(date, {}) if isinstance(state_obj.get('resultRecords'), dict) else {}
        rec = None
        for mk, rr in day_results.items():
            if _ledger_norm_market(mk) == base and isinstance(rr, dict):
                rec = rr
                break
        open_stage, open_value = _detect_result_stage((rec or {}).get('openResult'))
        if open_stage != 'open' or (rec or {}).get('openInferredFromClose') is True or not result.startswith(open_value):
            return {'changed': False, 'skipped': True, 'reason': 'fresh_open_missing_strict_2_stage'}

    targets = []
    if stage == 'open':
        targets = [('ank', f'{base} OPEN', parts.get('openAnk', '')), ('pannel', f'{base} OPEN', parts.get('openPanel', ''))]
    elif stage == 'close':
        targets = [('ank', f'{base} CLOSE', parts.get('closeAnk', '')), ('pannel', f'{base} CLOSE', parts.get('closePanel', '')), ('jodi', base, parts.get('jodi', ''))]

    ank_pan_idx, jodi_idx = _ledger_market_index_lookup(state_obj)
    profiles = state_obj.get('profiles', {}) if isinstance(state_obj.get('profiles'), dict) else {}
    only_wait = settings.get('autoLedgerMarkOnlyWait') is not False
    apply_all = settings.get('autoLedgerApplyToAllProfiles') is not False
    pids = list(profiles.keys()) if apply_all else ['admin1']
    summary = {'changed': False, 'date': date, 'market': base, 'stage': stage, 'result': result, 'profiles': 0, 'checked': 0, 'marked': 0, 'pass': 0, 'fail': 0, 'details': []}
    for pid in pids:
        profile = profiles.get(pid)
        if not isinstance(profile, dict):
            continue
        prof_changed = 0
        for typ, ledger_market, win in targets:
            idx = (jodi_idx if typ == 'jodi' else ank_pan_idx).get(_ledger_norm_market(ledger_market))
            if idx is None or not win:
                continue
            out = _apply_ledger_mark_to_profile(profile, date, typ, idx, win, result, stage, ledger_market, only_wait=only_wait)
            summary['checked'] += out['checked']
            summary['marked'] += out['changed']
            summary['pass'] += out['pass']
            summary['fail'] += out['fail']
            prof_changed += out['changed']
            if out['changed']:
                summary['details'].append({'profileId': pid, 'type': typ, 'market': ledger_market, 'index': idx, 'win': win, 'status': 'PASS' if out['pass'] else 'FAIL'})
        if prof_changed:
            summary['profiles'] += 1
    summary['changed'] = summary['marked'] > 0
    if settings.get('autoLedgerRecordResults') is not False:
        records = state_obj.setdefault('ledgerAutoMarkRecords', {})
        day = records.setdefault(date, {})
        key = f"{base}_{stage}"
        day[key] = {**summary, 'time': _now_iso_local()}
    if summary['changed']:
        _add_audit(state_obj, 'ledger_auto_mark', {'date': date, 'market': base, 'stage': stage, 'result': result, 'marked': summary['marked'], 'pass': summary['pass'], 'fail': summary['fail']})
    return summary

def _ledger_auto_mark_all_available(state_obj, date=None, force=False):
    date = str(date or _safe_today())
    out = {'changed': False, 'date': date, 'results': [], 'marked': 0, 'pass': 0, 'fail': 0}
    records = (state_obj.get('resultRecords') or {}).get(date, {}) if isinstance(state_obj.get('resultRecords'), dict) else {}
    for market, rec in records.items():
        if not isinstance(rec, dict):
            continue
        open_stage, open_value = _detect_result_stage(rec.get('openResult'))
        if open_stage == 'open' and rec.get('openInferredFromClose') is not True:
            r = _ledger_auto_mark_for_result(state_obj, date, market, 'open', open_value, force=force)
            out['results'].append(r); out['marked'] += int(r.get('marked') or 0); out['pass'] += int(r.get('pass') or 0); out['fail'] += int(r.get('fail') or 0); out['changed'] = out['changed'] or bool(r.get('changed'))
        close_stage, close_value = _detect_result_stage(rec.get('closeResult'))
        if close_stage == 'close':
            r = _ledger_auto_mark_for_result(state_obj, date, market, 'close', close_value, force=force)
            out['results'].append(r); out['marked'] += int(r.get('marked') or 0); out['pass'] += int(r.get('pass') or 0); out['fail'] += int(r.get('fail') or 0); out['changed'] = out['changed'] or bool(r.get('changed'))
    return out

@app.route('/api/withdrawals')
def api_withdrawals():
    state = migrate_and_get_state()
    _ensure_foundation_state(state)
    _ensure_wallets_for_profiles(state)
    withdrawals = state.get('withdrawals', []) if isinstance(state.get('withdrawals', []), list) else []
    # Backward compatibility: older builds used status=approved as final paid.
    # Keep paid requests final if paidAt exists; otherwise approved means payment processing.
    changed = False
    for w in withdrawals:
        if not isinstance(w, dict):
            continue
        st = str(w.get('status') or '').lower()
        if st == 'approved' and w.get('paidAt'):
            w['status'] = 'paid'
            w['paymentStatus'] = 'paid'
            changed = True
        elif st == 'approved' and not w.get('paymentStatus'):
            w['paymentStatus'] = 'processing'
            changed = True
        elif st == 'pending' and not w.get('paymentStatus'):
            w['paymentStatus'] = 'pending_approval'
            changed = True
    if changed:
        _firebase_put_top_level_children(state, {'withdrawals': withdrawals}, audit=False)
    withdrawals_sorted = sorted(withdrawals, key=lambda x: str(x.get('createdAt') or x.get('time') or ''), reverse=True)
    pending_count = sum(1 for w in withdrawals if str(w.get('status', '')).lower() == 'pending')
    approved_count = sum(1 for w in withdrawals if str(w.get('status', '')).lower() == 'approved')
    active_count = sum(1 for w in withdrawals if str(w.get('status', '')).lower() in ('pending', 'approved'))
    return jsonify({
        'status': 'success',
        'withdrawals': withdrawals_sorted[:300],
        'withdrawalSettings': state.get('withdrawalSettings', _default_withdrawal_settings()),
        'wallets': state.get('wallets', {}),
        'pendingCount': pending_count,
        'approvedCount': approved_count,
        'activeCount': active_count
    })


@app.route('/api/withdrawal_action', methods=['POST'])
def api_withdrawal_action():
    data = request.json or {}
    wid = str(data.get('id') or data.get('withdrawalId') or '').strip()
    action = str(data.get('action') or '').strip().lower().replace('-', '_')
    reason = str(data.get('reason') or '').strip()
    transaction_id = str(data.get('transactionId') or data.get('utr') or '').strip()
    admin_note = str(data.get('adminNote') or data.get('note') or '').strip()
    if action in ['paid', 'pay', 'markpaid']:
        action = 'mark_paid'
    if not wid or action not in ['approve', 'mark_paid', 'reject']:
        return jsonify({'status': 'error', 'message': 'id aur action approve/mark_paid/reject required hai'}), 400

    def mutator(state):
        _ensure_foundation_state(state)
        withdrawals = state.get('withdrawals', []) if isinstance(state.get('withdrawals', []), list) else []
        wd = next((x for x in withdrawals if isinstance(x, dict) and str(x.get('id')) == wid), None)
        if not wd:
            _money_error('Withdrawal request not found', 404)
        user_id = wd.get('userId')
        wallet = _ensure_wallet_for_user(state, user_id)
        if wallet is None:
            _money_error('Wallet/profile not found', 404)
        amount = _wallet_float(wd.get('amount', 0))
        current_status = str(wd.get('status', '') or 'pending').lower()
        if current_status == 'approved' and wd.get('paidAt'):
            wd['status'] = 'paid'; wd['paymentStatus'] = 'paid'; current_status = 'paid'
        settings = state.get('withdrawalSettings', _default_withdrawal_settings())
        profile = (state.get('profiles', {}) or {}).get(user_id, {})
        target = _phone_target_from_profile(profile)

        def _notify_once(flag_key, text, meta_type):
            if wd.get(flag_key):
                return None
            wd[flag_key] = True
            wd[flag_key + 'At'] = _now_iso_local()
            if settings.get('notifyUserPrivate', True):
                return _queue_whatsapp_target_message(state, target, text, {'type': meta_type, 'withdrawalId': wid})
            return None

        if current_status == 'paid':
            return ({'status': 'success', 'message': 'Already paid', 'withdrawal': wd, 'wallet': wallet, 'wallets': state.get('wallets', {}), 'withdrawals': state.get('withdrawals', []), 'walletTransactions': _wallet_transactions_from_state(state, None, 500), 'idempotentFinal': True}, 200)
        if current_status == 'rejected':
            return ({'status': 'success', 'message': 'Already rejected', 'withdrawal': wd, 'wallet': wallet, 'wallets': state.get('wallets', {}), 'withdrawals': state.get('withdrawals', []), 'walletTransactions': _wallet_transactions_from_state(state, None, 500), 'idempotentFinal': True}, 200)

        if action == 'approve':
            if current_status not in ['pending', 'approved']:
                _money_error(f'Cannot approve withdrawal in status {current_status}', 400)
            wd['status'] = 'approved'
            wd['paymentStatus'] = 'processing'
            wd.setdefault('approvedAt', _now_iso_local())
            wd['approvedBy'] = 'admin'
            wd['walletHoldAfter'] = _wallet_hold_amount(wallet)
            wd['moneyAtomicApproved'] = True
            _add_audit(state, 'withdrawal_approved_processing_atomic', {'withdrawalId': wid, 'userId': user_id, 'amount': amount})
            _notify_once('approvalNotified', f"✅ *WITHDRAWAL APPROVED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{wid}\n💵 *Amount:* ₹{amount:g}\n📝 Aapka withdrawal approve ho gaya hai.\n⏳ Jaldi aapka payment process ho jayega.\n\n*Status:* Payment Processing", 'withdrawal_approved_processing')
        elif action == 'mark_paid':
            if current_status == 'pending':
                _money_error('Pehle withdrawal approve karo, phir payment ke baad Mark Paid karo.', 400)
            if current_status != 'approved':
                _money_error(f'Cannot mark paid in status {current_status}', 400)
            hold_before = _wallet_hold_amount(wallet)
            bal_before = _wallet_float(wallet.get('balance', 0))
            _set_wallet_hold(wallet, hold_before - amount)
            bal_after = round(bal_before - amount, 2)
            wallet['balance'] = bal_after
            wallet['updatedAt'] = _now_iso_local()
            ledger_entry = {
                'id': wid,
                'time': _now_iso_local(),
                'type': 'withdrawal_paid',
                'amount': -amount,
                'balanceBefore': bal_before,
                'balanceAfter': bal_after,
                'holdBefore': hold_before,
                'holdAfter': _wallet_hold_amount(wallet),
                'note': f"Withdrawal paid {wid}" + (f" / Txn {transaction_id}" if transaction_id else ''),
                'source': 'withdrawal_admin',
                'withdrawalId': wid,
                'transactionId': transaction_id,
                'moneyAtomic': True
            }
            wallet.setdefault('ledger', []).append(ledger_entry)
            _record_wallet_transaction(state, user_id, wallet, ledger_entry)
            wd['status'] = 'paid'
            wd['paymentStatus'] = 'paid'
            wd['paidAt'] = _now_iso_local()
            wd['paidBy'] = 'admin'
            wd['transactionId'] = transaction_id
            wd['adminNote'] = admin_note
            wd['walletBalanceAfter'] = bal_after
            wd['walletHoldAfter'] = _wallet_hold_amount(wallet)
            wd['moneyAtomicPaid'] = True
            _add_audit(state, 'withdrawal_mark_paid_atomic', {'withdrawalId': wid, 'userId': user_id, 'amount': amount, 'transactionId': transaction_id})
            tx_line = f"\n🧾 *Transaction ID:* {transaction_id}" if transaction_id else ""
            _notify_once('paidNotified', f"✅ *WITHDRAWAL PAID*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{wid}\n💵 *Amount:* ₹{amount:g}{tx_line}\n\n*Status:* Completed\nPayment successfully processed.", 'withdrawal_paid')
        else:
            if current_status not in ['pending', 'approved']:
                _money_error(f'Cannot reject withdrawal in status {current_status}', 400)
            hold_before = _wallet_hold_amount(wallet)
            bal_before = _wallet_float(wallet.get('balance', 0))
            _set_wallet_hold(wallet, hold_before - amount)
            wallet['updatedAt'] = _now_iso_local()
            ledger_entry = {
                'id': wid,
                'time': _now_iso_local(),
                'type': 'withdrawal_released',
                'amount': 0,
                'balanceBefore': bal_before,
                'balanceAfter': bal_before,
                'holdBefore': hold_before,
                'holdAfter': _wallet_hold_amount(wallet),
                'note': f"Withdrawal rejected {wid}: {reason or 'Rejected by admin'}",
                'source': 'withdrawal_admin',
                'withdrawalId': wid,
                'moneyAtomic': True
            }
            wallet.setdefault('ledger', []).append(ledger_entry)
            _record_wallet_transaction(state, user_id, wallet, ledger_entry)
            wd['status'] = 'rejected'
            wd['paymentStatus'] = 'rejected'
            wd['rejectedAt'] = _now_iso_local()
            wd['rejectedBy'] = 'admin'
            wd['rejectReason'] = reason or 'Rejected by admin'
            wd['walletHoldAfter'] = _wallet_hold_amount(wallet)
            wd['moneyAtomicRejected'] = True
            _add_audit(state, 'withdrawal_rejected_atomic', {'withdrawalId': wid, 'userId': user_id, 'amount': amount, 'reason': wd['rejectReason']})
            _notify_once('rejectionNotified', f"❌ *WITHDRAWAL REJECTED*\n━━━━━━━━━━━━━━━━━━━━\n🆔 *ID:* #{wid}\n💵 *Amount:* ₹{amount:g}\n📝 *Reason:* {wd['rejectReason']}\n💳 Wallet hold release ho gaya hai.", 'withdrawal_rejected')
        return ({'status': 'success', 'withdrawal': wd, 'wallet': wallet, 'wallets': state.get('wallets', {}), 'withdrawals': state.get('withdrawals', []), 'walletTransactions': _wallet_transactions_from_state(state, None, 500)}, 200)

    return _json_money_response(_money_atomic_commit('withdrawal_action', data, ['id','withdrawalId','action','reason','transactionId','utr','adminNote'], mutator))

@app.route('/api/withdrawal_settings', methods=['POST'])
def api_withdrawal_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('withdrawalSettings', _default_withdrawal_settings())
    for key in ['enabled', 'onePendingPerUser', 'notifyUserPrivate', 'notifyAdminPrivate']:
        if key in data:
            settings[key] = bool(data.get(key))
    for key in ['minAmount', 'maxAmount']:
        if key in data:
            settings[key] = max(0, _wallet_float(data.get(key, 0)))
    if 'adminNotifyTargets' in data:
        raw = data.get('adminNotifyTargets') or []
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.replace('\\n', ',').split(',') if x.strip()]
        settings['adminNotifyTargets'] = raw if isinstance(raw, list) else []
    _add_audit(state, 'withdrawal_settings', settings)
    _firebase_put_top_level_children(state, {'withdrawalSettings': settings})
    return jsonify({'status': 'success', 'withdrawalSettings': settings})

@app.route('/api/wallets')
def api_wallets():
    state = migrate_and_get_state()
    _ensure_wallets_for_profiles(state)
    profiles = state.get('profiles', {})
    clients = []
    for uid in _client_profile_ids(state):
        prof = profiles.get(uid, {}) or {}
        wallet = state.get('wallets', {}).get(uid, {}) or {}
        bal = _wallet_float(wallet.get('balance', 0))
        hold = _wallet_hold_amount(wallet)
        credit = _wallet_float(wallet.get('creditLimit', 0))
        clients.append({
            'userId': uid,
            'name': prof.get('name', uid),
            'phone': prof.get('phone', ''),
            'expiryDate': prof.get('expiryDate', ''),
            'vipAccessEnabled': prof.get('vipAccessEnabled', True),
            'balance': bal,
            'hold': hold,
            'creditLimit': credit,
            'available': round(bal + credit - hold, 2),
            'withdrawAvailable': round(bal - hold, 2),
            'ledgerCount': len(wallet.get('ledger', []) if isinstance(wallet.get('ledger', []), list) else [])
        })
    return jsonify({
        'status': 'success',
        'wallets': state.get('wallets', {}),
        'walletSettings': state.get('walletSettings', _default_wallet_settings()),
        'clients': clients,
        'walletTransactions': _wallet_transactions_from_state(state, None, 500)
    })


@app.route('/api/wallet_transaction', methods=['POST'])
def api_wallet_transaction():
    data = request.json or {}
    user_id = data.get('userId')
    action = str(data.get('action') or 'add').strip().lower()
    note = str(data.get('note') or '').strip()
    amount = _wallet_float(data.get('amount', 0))
    if not user_id:
        return jsonify({'status': 'error', 'message': 'userId missing'}), 400
    if action not in ['add', 'subtract']:
        return jsonify({'status': 'error', 'message': 'action add/subtract hona chahiye'}), 400
    if amount <= 0:
        return jsonify({'status': 'error', 'message': 'Amount 0 se zyada hona chahiye'}), 400

    def mutator(state):
        wallet = _ensure_wallet_for_user(state, user_id)
        if wallet is None:
            _money_error('User/profile not found', 404)
        signed = amount if action == 'add' else -amount
        before = _wallet_float(wallet.get('balance', 0))
        after = round(before + signed, 2)
        wallet['balance'] = after
        wallet['updatedAt'] = _now_iso_local()
        entry = {
            'id': str(uuid.uuid4())[:8].upper(),
            'time': _now_iso_local(),
            'type': action,
            'amount': signed,
            'balanceBefore': before,
            'balanceAfter': after,
            'holdBefore': _wallet_hold_amount(wallet),
            'holdAfter': _wallet_hold_amount(wallet),
            'note': note or ('Manual add' if action == 'add' else 'Manual subtract'),
            'source': 'admin_wallet_tab',
            'moneyAtomic': True
        }
        wallet.setdefault('ledger', []).append(entry)
        _record_wallet_transaction(state, user_id, wallet, entry)
        _add_audit(state, 'wallet_transaction_atomic', {'userId': user_id, 'amount': signed, 'balanceAfter': after, 'note': entry['note']})
        return ({'status': 'success', 'wallet': wallet, 'wallets': state.get('wallets', {}), 'walletTransactions': _wallet_transactions_from_state(state, None, 500)}, 200)

    return _json_money_response(_money_atomic_commit('wallet_transaction', data, ['userId','action','amount','note'], mutator))


@app.route('/api/wallet_credit_limit', methods=['POST'])
def api_wallet_credit_limit():
    data = request.json or {}
    user_id = data.get('userId')
    credit = _wallet_float(data.get('creditLimit', 0))
    if not user_id:
        return jsonify({'status': 'error', 'message': 'userId missing'}), 400
    if credit < 0:
        return jsonify({'status': 'error', 'message': 'Credit limit negative nahi ho sakta'}), 400

    def mutator(state):
        wallet = _ensure_wallet_for_user(state, user_id)
        if wallet is None:
            _money_error('User/profile not found', 404)
        before = _wallet_float(wallet.get('creditLimit', 0))
        if before == credit:
            return ({'status': 'success', 'message': 'Credit limit already same', 'wallet': wallet, 'wallets': state.get('wallets', {}), 'walletTransactions': _wallet_transactions_from_state(state, None, 500)}, 200)
        wallet['creditLimit'] = credit
        wallet['updatedAt'] = _now_iso_local()
        ledger_entry = {
            'id': str(uuid.uuid4())[:8].upper(),
            'time': _now_iso_local(),
            'type': 'credit_limit',
            'amount': 0,
            'balanceBefore': _wallet_float(wallet.get('balance', 0)),
            'balanceAfter': _wallet_float(wallet.get('balance', 0)),
            'holdBefore': _wallet_hold_amount(wallet),
            'holdAfter': _wallet_hold_amount(wallet),
            'note': f'Credit limit {before} → {credit}',
            'source': 'admin_wallet_tab',
            'moneyAtomic': True
        }
        wallet.setdefault('ledger', []).append(ledger_entry)
        _record_wallet_transaction(state, user_id, wallet, ledger_entry)
        _add_audit(state, 'wallet_credit_limit_atomic', {'userId': user_id, 'oldCreditLimit': before, 'creditLimit': credit})
        return ({'status': 'success', 'wallet': wallet, 'wallets': state.get('wallets', {}), 'walletTransactions': _wallet_transactions_from_state(state, None, 500)}, 200)

    return _json_money_response(_money_atomic_commit('wallet_credit_limit', data, ['userId','creditLimit'], mutator))


@app.route('/api/wallet_zero_settle', methods=['POST'])
def api_wallet_zero_settle():
    data = request.json or {}
    user_id = data.get('userId')
    note = str(data.get('note') or 'Zero settle').strip()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'userId missing'}), 400

    def mutator(state):
        wallet = _ensure_wallet_for_user(state, user_id)
        if wallet is None:
            _money_error('User/profile not found', 404)
        before = _wallet_float(wallet.get('balance', 0))
        wallet['balance'] = 0
        wallet['updatedAt'] = _now_iso_local()
        ledger_entry = {
            'id': str(uuid.uuid4())[:8].upper(),
            'time': _now_iso_local(),
            'type': 'zero_settle',
            'amount': -before,
            'balanceBefore': before,
            'balanceAfter': 0,
            'holdBefore': _wallet_hold_amount(wallet),
            'holdAfter': _wallet_hold_amount(wallet),
            'note': note,
            'source': 'admin_wallet_tab',
            'moneyAtomic': True
        }
        wallet.setdefault('ledger', []).append(ledger_entry)
        _record_wallet_transaction(state, user_id, wallet, ledger_entry)
        _add_audit(state, 'wallet_zero_settle_atomic', {'userId': user_id, 'oldBalance': before})
        return ({'status': 'success', 'wallet': wallet, 'wallets': state.get('wallets', {}), 'walletTransactions': _wallet_transactions_from_state(state, None, 500)}, 200)

    return _json_money_response(_money_atomic_commit('wallet_zero_settle', data, ['userId','note'], mutator))

@app.route('/api/wallet_history')
def api_wallet_history():
    state = migrate_and_get_state()
    _ensure_wallets_for_profiles(state)
    user_id = str(request.args.get('userId') or '').strip()
    try:
        limit = int(request.args.get('limit') or 500)
    except Exception:
        limit = 500
    rows = _wallet_transactions_from_state(state, user_id or None, limit)
    total_credit = round(sum(_wallet_float(x.get('amount')) for x in rows if _wallet_float(x.get('amount')) > 0), 2)
    total_debit = round(sum(abs(_wallet_float(x.get('amount'))) for x in rows if _wallet_float(x.get('amount')) < 0), 2)
    hold_events = sum(1 for x in rows if 'hold' in str(x.get('type', '')).lower() or 'withdrawal' in str(x.get('type', '')).lower())
    return jsonify({
        'status': 'success',
        'userId': user_id,
        'transactions': rows,
        'walletTransactions': rows,
        'summary': {
            'count': len(rows),
            'credit': total_credit,
            'debit': total_debit,
            'holdEvents': hold_events
        }
    })


@app.route('/api/finance_core_status')
def api_finance_core_status():
    state = migrate_and_get_state()
    _ensure_wallets_for_profiles(state)
    wallets = state.get('wallets', {}) if isinstance(state.get('wallets', {}), dict) else {}
    payments = state.get('payments', []) if isinstance(state.get('payments', []), list) else []
    withdrawals = state.get('withdrawals', []) if isinstance(state.get('withdrawals', []), list) else []
    tx = _wallet_transactions_from_state(state, None, 250)
    total_balance = 0.0
    total_hold = 0.0
    for w in wallets.values():
        if isinstance(w, dict):
            total_balance += _wallet_float(w.get('balance', 0))
            total_hold += _wallet_hold_amount(w)
    return jsonify({
        'status': 'success',
        'financeCoreConsolidation': True,
        'version': 'v27',
        'singleFinanceTab': True,
        'legacyTabsHidden': ['wallets', 'payments', 'withdrawals'],
        'coreRoutesKeptForCompatibility': ['/api/wallets','/api/payments','/api/withdrawals','/api/wallet_transaction','/api/approve_payment','/api/reject_payment','/api/withdrawal_action'],
        'totals': {
            'walletUsers': len(wallets),
            'walletBalance': round(total_balance, 2),
            'walletHold': round(total_hold, 2),
            'pendingPayments': len([p for p in payments if isinstance(p, dict) and str(p.get('status','')).lower() == 'pending']),
            'pendingWithdrawals': len([w for w in withdrawals if isinstance(w, dict) and str(w.get('status','')).lower() == 'pending']),
            'processingWithdrawals': len([w for w in withdrawals if isinstance(w, dict) and str(w.get('status','')).lower() == 'approved']),
            'transactionsSample': len(tx)
        }
    })

@app.route('/api/wallet_settings', methods=['POST'])
def api_wallet_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('walletSettings', _default_wallet_settings())
    if 'defaultCreditLimit' in data:
        settings['defaultCreditLimit'] = _wallet_float(data.get('defaultCreditLimit', 0))
    if 'requirePositiveBalance' in data:
        settings['requirePositiveBalance'] = bool(data.get('requirePositiveBalance'))
    if 'walletEnabled' in data:
        settings['walletEnabled'] = bool(data.get('walletEnabled'))
    _add_audit(state, 'wallet_settings', settings)
    _firebase_put_top_level_children(state, {'walletSettings': settings})
    return jsonify({'status': 'success', 'walletSettings': settings})


@app.route('/api/money_atomicity_status')
def api_money_atomicity_status():
    state = migrate_and_get_state()
    wallets = state.get('wallets', {}) if isinstance(state.get('wallets', {}), dict) else {}
    withdrawals = state.get('withdrawals', []) if isinstance(state.get('withdrawals', []), list) else []
    payments = state.get('payments', []) if isinstance(state.get('payments', []), list) else []
    txns = _wallet_transactions_from_state(state, None, 1000)
    active_withdrawals = [w for w in withdrawals if isinstance(w, dict) and str(w.get('status','')).lower() in ('pending','approved')]
    return jsonify({
        'status': 'success',
        'moneyAtomicity': True,
        'version': MONEY_ATOMICITY_VERSION,
        'walletCount': len(wallets),
        'walletTransactionCount': len(txns),
        'paymentCount': len(payments),
        'withdrawalCount': len(withdrawals),
        'activeWithdrawalCount': len(active_withdrawals),
        'idempotencyLockCount': len(state.get('moneyIdempotency', {}) if isinstance(state.get('moneyIdempotency'), dict) else {}),
        'protectedRoutes': ['/api/submit_payment','/api/approve_payment','/api/reject_payment','/api/wallet_transaction','/api/wallet_credit_limit','/api/wallet_zero_settle','/api/withdrawal_action']
    })

@app.route('/api/entries')
def api_entries():
    state = migrate_and_get_state()
    date = request.args.get('date') or _safe_today()
    all_entries = state.get('entries', []) if isinstance(state.get('entries', []), list) else []
    entries = [e for e in all_entries if not date or e.get('date') == date]
    # newest first, limit to keep mobile UI light
    entries = sorted(entries, key=lambda x: str(x.get('createdAt') or x.get('time') or ''), reverse=True)[:300]
    total_amount = round(sum(_wallet_float(e.get('total', 0)) for e in entries if e.get('status') == 'accepted'), 2)
    by_market = {}
    for e in entries:
        if e.get('status') != 'accepted':
            continue
        m = str(e.get('market') or 'UNKNOWN')
        by_market.setdefault(m, {'market': m, 'entries': 0, 'total': 0})
        by_market[m]['entries'] += 1
        by_market[m]['total'] = round(by_market[m]['total'] + _wallet_float(e.get('total', 0)), 2)
    return jsonify({
        'status': 'success',
        'date': date,
        'entries': entries,
        'totalEntries': len(entries),
        'totalAmount': total_amount,
        'byMarket': sorted(by_market.values(), key=lambda x: (-x['total'], x['market'])),
        'entrySettings': state.get('entrySettings', _default_entry_settings()),
        'riskSettings': state.get('riskSettings', _default_risk_settings()),
        'marketLocks': state.get('marketLocks', {})
    })

@app.route('/api/entry_settings', methods=['POST'])
def api_entry_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('entrySettings', _default_entry_settings())
    for key in ['entryParserEnabled', 'groupsOnly', 'strictFormat', 'autoDebitWallet', 'marketTimingEnabled', 'riskLimitEnabled']:
        if key in data:
            settings[key] = bool(data.get(key))
    if 'duplicatePolicy' in data:
        settings['duplicatePolicy'] = str(data.get('duplicatePolicy') or 'sender_market_type_digits_date')
    if 'entryFormatTemplate' in data:
        template = str(data.get('entryFormatTemplate') or '').strip()
        if not template:
            template = _default_entry_settings()['entryFormatTemplate']
        settings['entryFormatTemplate'] = template[:1000]
    if isinstance(data.get('marketCloseTimes'), dict):
        cur = settings.setdefault('marketCloseTimes', _default_market_close_times())
        for mk, val in data.get('marketCloseTimes', {}).items():
            norm_time = _normalize_hhmm(val)
            if not norm_time:
                continue
            raw_key = ' '.join(str(mk or '').strip().upper().split())
            canon_key = _canonical_market_time_key(raw_key)
            if raw_key:
                cur[raw_key] = norm_time
            if canon_key:
                cur[canon_key] = norm_time
        settings['marketCloseTimesUpdatedAt'] = datetime.datetime.now().isoformat()
    _add_audit(state, 'entry_settings', settings)
    _firebase_put_top_level_children(state, {'entrySettings': settings})
    return jsonify({'status': 'success', 'entrySettings': settings})

@app.route('/api/save_entry_safety', methods=['POST'])
def api_save_entry_safety():
    data = request.json or {}
    state = migrate_and_get_state()
    entry = state.setdefault('entrySettings', _default_entry_settings())
    risk = state.setdefault('riskSettings', _default_risk_settings())

    for key in ['entryParserEnabled', 'groupsOnly', 'strictFormat', 'autoDebitWallet', 'marketTimingEnabled', 'riskLimitEnabled']:
        if key in data:
            entry[key] = bool(data.get(key))

    if isinstance(data.get('marketCloseTimes'), dict):
        cur = entry.setdefault('marketCloseTimes', _default_market_close_times())
        saved_times = {}
        for mk, val in data.get('marketCloseTimes', {}).items():
            norm_time = _normalize_hhmm(val)
            if not norm_time:
                continue
            raw_key = ' '.join(str(mk or '').strip().upper().split())
            canon_key = _canonical_market_time_key(raw_key)
            if raw_key:
                cur[raw_key] = norm_time
                saved_times[raw_key] = norm_time
            if canon_key:
                cur[canon_key] = norm_time
                saved_times[canon_key] = norm_time
        entry['marketCloseTimesUpdatedAt'] = datetime.datetime.now().isoformat()
        entry['lastSavedMarketTimes'] = saved_times

    for key in ['marketDailyLimit', 'digitDailyLimit', 'userDailyLimit']:
        if key in data:
            try:
                risk[key] = max(0, float(data.get(key) or 0))
            except Exception:
                pass
    if 'warningPercent' in data:
        try:
            risk['warningPercent'] = max(1, min(100, int(data.get('warningPercent') or 80)))
        except Exception:
            pass
    if 'autoLockOnLimit' in data:
        risk['autoLockOnLimit'] = bool(data.get('autoLockOnLimit'))

    _add_audit(state, 'entry_safety_settings', {'entrySettings': entry, 'riskSettings': risk})
    _firebase_put_top_level_children(state, {'entrySettings': entry, 'riskSettings': risk})
    return jsonify({'status': 'success', 'entrySettings': entry, 'riskSettings': risk})

@app.route('/api/risk_settings', methods=['POST'])
def api_risk_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('riskSettings', _default_risk_settings())
    for key in ['marketDailyLimit', 'digitDailyLimit', 'userDailyLimit']:
        if key in data:
            settings[key] = max(0, _wallet_float(data.get(key, 0)))
    if 'warningPercent' in data:
        wp = int(_wallet_float(data.get('warningPercent', 80)))
        settings['warningPercent'] = max(1, min(100, wp))
    if 'autoLockOnLimit' in data:
        settings['autoLockOnLimit'] = bool(data.get('autoLockOnLimit'))
    _add_audit(state, 'risk_settings', settings)
    _firebase_put_top_level_children(state, {'riskSettings': settings})
    return jsonify({'status': 'success', 'riskSettings': settings})

@app.route('/api/market_unlock', methods=['POST'])
def api_market_unlock():
    data = request.json or {}
    state = migrate_and_get_state()
    date = data.get('date') or _safe_today()
    market = str(data.get('market') or '').strip().upper()
    locks = state.setdefault('marketLocks', {})
    if isinstance(locks.get(date), dict) and market in locks.get(date, {}):
        locks[date].pop(market, None)
    if market in locks:
        locks.pop(market, None)
    _add_audit(state, 'market_unlock', {'date': date, 'market': market})
    _firebase_put_top_level_children(state, {'marketLocks': locks})
    return jsonify({'status': 'success', 'marketLocks': locks})

@app.route('/api/results')
def api_results():
    state = migrate_and_get_state()
    date = request.args.get('date') or _safe_today()
    return jsonify({
        'status': 'success',
        'date': date,
        'resultRecords': state.get('resultRecords', {}),
        'records': state.get('resultRecords', {}).get(date, {}),
        'resultTargets': state.get('resultTargets', []),
        'resultSettings': state.get('resultSettings', {'autoScrapeEnabled': True, 'sourceName': RESULT_SOURCE_NAME, 'sourceUrl': RESULT_SOURCE_URL}),
        'settlementRecords': state.get('settlementRecords', {}),
        'ledgerAutoMarkRecords': state.get('ledgerAutoMarkRecords', {}),
        'settlementSettings': state.get('settlementSettings', _default_settlement_settings())
    })

@app.route('/api/settlements')
def api_settlements():
    state = migrate_and_get_state()
    date = request.args.get('date') or _safe_today()
    return jsonify({
        'status': 'success',
        'date': date,
        'settlementRecords': state.get('settlementRecords', {}),
        'records': state.get('settlementRecords', {}).get(date, {}),
        'ledgerAutoMarkRecords': state.get('ledgerAutoMarkRecords', {}),
        'settlementSettings': state.get('settlementSettings', _default_settlement_settings())
    })

@app.route('/api/save_settlement_settings', methods=['POST'])
def api_save_settlement_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('settlementSettings', _default_settlement_settings())
    if 'enabled' in data:
        settings['enabled'] = bool(data.get('enabled'))
    if 'includeSummaryInResultMessage' in data:
        settings['includeSummaryInResultMessage'] = bool(data.get('includeSummaryInResultMessage'))
    if 'includeHitMissInResultMessage' in data:
        settings['includeHitMissInResultMessage'] = bool(data.get('includeHitMissInResultMessage'))
    for _k in ['autoLedgerMarking', 'autoLedgerMarkOnlyWait', 'autoLedgerApplyToAllProfiles', 'autoLedgerRecordResults']:
        if _k in data:
            settings[_k] = bool(data.get(_k))
    if isinstance(data.get('payoutMultipliers'), dict):
        pm = settings.setdefault('payoutMultipliers', _default_settlement_settings()['payoutMultipliers'])
        for k in ['ank', 'jodi', 'penel']:
            if k in data['payoutMultipliers']:
                try:
                    val = float(data['payoutMultipliers'][k])
                    if val >= 0: pm[k] = val
                except Exception:
                    pass
    _add_audit(state, 'settlement_settings', settings)
    _firebase_put_top_level_children(state, {'settlementSettings': settings})
    return jsonify({'status': 'success', 'settlementSettings': settings})


@app.route('/api/ledger_auto_mark', methods=['POST'])
def api_ledger_auto_mark():
    data = request.json or {}
    state = migrate_and_get_state()
    _ensure_foundation_state(state)
    date = data.get('date') or _safe_today()
    market = data.get('market') or ''
    stage = data.get('stage') or ''
    result = data.get('result') or ''
    force = bool(data.get('force'))
    if market and result:
        summary = _ledger_auto_mark_for_result(state, date, market, stage, result, force=force)
    else:
        summary = _ledger_auto_mark_all_available(state, date, force=force)
    if summary.get('changed') or data.get('record', True):
        _firebase_put_top_level_children(state, {
            'profiles': state.get('profiles', {}),
            'ledgerAutoMarkRecords': state.get('ledgerAutoMarkRecords', {})
        }, audit=False)
    return jsonify({'status': 'success', 'summary': summary, 'ledgerAutoMarkRecords': state.get('ledgerAutoMarkRecords', {}), 'profiles': state.get('profiles', {})})


@app.route('/api/send_hitmiss_report', methods=['POST'])
def api_send_hitmiss_report():
    data = request.json or {}
    try:
        res = _gateway_request('POST', '/send_hitmiss', json=data, timeout=30)
        try:
            payload = res.json()
        except Exception:
            payload = {'status': 'error', 'message': res.text}
        return jsonify(payload), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Gateway offline or unavailable: {str(e)}'}), 503

@app.route('/api/save_result', methods=['POST'])
def api_save_result():
    data = request.json or {}
    state = migrate_and_get_state()
    _ensure_market_registry(state)
    stage, result_value = _detect_result_stage(data.get('result'))
    date = data.get('date') or _safe_today()
    market = _valid_base_market_name(data.get('market'), state, purpose='result')

    if not market:
        return jsonify({'status': 'error', 'message': 'Valid enabled result market select karein. Market Manager me market/result ON hona chahiye.'}), 400
    if not stage:
        return jsonify({'status': 'error', 'message': 'Result format 123-4 ya 123-45-678 hona chahiye.'}), 400
    allowed = _market_phase3_allowed(state, market, purpose='result', stage=stage)
    if not allowed.get('ok'):
        return jsonify({'status': 'error', 'message': 'Market Manager ne ye result/stage block kiya hai: ' + str(allowed.get('reason') or 'blocked'), 'marketRegistryReason': allowed.get('reason')}), 400

    state.setdefault('resultRecords', {}).setdefault(date, {})
    rec = state['resultRecords'][date].setdefault(market, {'market': market})
    rec['market'] = market
    rec['updatedAt'] = _now_label()
    rec['source'] = data.get('source') or 'manual'

    if stage == 'open':
        rec['openResult'] = result_value
        rec['openUpdatedAt'] = _now_label()
    else:
        open_stage, open_value = _detect_result_stage(rec.get('openResult'))
        if open_stage != 'open':
            return jsonify({'status': 'error', 'message': 'Pehle fresh open result 123-4 save/declare karein. Old close direct accept nahi hoga.'}), 400
        if not result_value.startswith(open_value):
            return jsonify({'status': 'error', 'message': f'Close result open se match nahi hai. Open {open_value} hai, close {result_value} nahi chalega.'}), 400
        rec['closeResult'] = result_value
        rec['closeUpdatedAt'] = _now_label()

    auto_mark = _ledger_auto_mark_for_result(state, date, market, stage, result_value)
    _firebase_put_top_level_children(state, {
        'resultRecords': state.get('resultRecords', {}),
        'profiles': state.get('profiles', {}),
        'ledgerAutoMarkRecords': state.get('ledgerAutoMarkRecords', {})
    }, audit=False)
    return jsonify({
        'status': 'success',
        'stage': stage,
        'market': market,
        'result': result_value,
        'record': rec,
        'autoLedgerMark': auto_mark,
        'resultRecords': state.get('resultRecords', {})
    })


@app.route('/api/clear_invalid_auto_results', methods=['POST'])
def api_clear_invalid_auto_results():
    data = request.json or {}
    date = data.get('date') or _safe_today()
    state = migrate_and_get_state()
    day = state.setdefault('resultRecords', {}).setdefault(date, {})
    cleared = []
    for market, rec in list(day.items()):
        if not isinstance(rec, dict):
            continue
        close_stage, close_value = _detect_result_stage(rec.get('closeResult'))
        if close_stage != 'close':
            continue
        open_stage, open_value = _detect_result_stage(rec.get('openResult'))
        # Fresh close is valid only after today's real Open and must start with that open prefix.
        # Direct/full website results are not allowed to create an inferred Open, because that can declare old/yesterday data.
        close_after_open = True
        try:
            if rec.get('openUpdatedAt') and rec.get('closeUpdatedAt'):
                close_after_open = str(rec.get('closeUpdatedAt')) >= str(rec.get('openUpdatedAt'))
        except Exception:
            close_after_open = True
        invalid_reason = ''
        if open_stage != 'open' or rec.get('openInferredFromClose') is True:
            invalid_reason = 'fresh_open_missing_strict_2_stage'
        elif not close_value.startswith(open_value):
            invalid_reason = 'close_does_not_match_open'
        elif not close_after_open:
            invalid_reason = 'close_before_open_old_result'
        if invalid_reason:
            old_close = rec.pop('closeResult', '')
            rec.pop('closeUpdatedAt', None)
            rec['ignoredCloseResult'] = old_close
            rec['ignoredCloseAt'] = _now_label()
            rec['ignoredCloseReason'] = invalid_reason
            cleared.append({'market': market, 'oldClose': old_close, 'openResult': open_value if open_stage == 'open' else '', 'reason': invalid_reason})
    _firebase_put_top_level_children(state, {'resultRecords': state.get('resultRecords', {})}, audit=False)
    return jsonify({'status': 'success', 'date': date, 'cleared': cleared, 'resultRecords': state.get('resultRecords', {})})

@app.route('/api/save_result_targets', methods=['POST'])
def api_save_result_targets():
    data = request.json or {}
    targets = data.get('targets') or []
    if isinstance(targets, str):
        targets = [x.strip() for x in targets.replace('\\n', ',').split(',') if x.strip()]
    clean_targets = []
    for t in targets:
        if isinstance(t, dict):
            t = t.get('id') or t.get('jid') or t.get('target') or t.get('phone') or t.get('number') or t.get('value') or ''
        t = str(t or '').strip()
        import re
        m = re.search(r'([0-9A-Za-z._:-]+@(?:g\.us|s\.whatsapp\.net))', t, re.I)
        if m:
            t = m.group(1)
        if t and t not in clean_targets:
            clean_targets.append(t)
    state = migrate_and_get_state()
    state['resultTargets'] = clean_targets
    _firebase_put_top_level_children(state, {'resultTargets': clean_targets}, audit=False)
    return jsonify({'status': 'success', 'resultTargets': clean_targets})

@app.route('/api/save_result_settings', methods=['POST'])
def api_save_result_settings():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('resultSettings', {'autoScrapeEnabled': True, 'useForwardTargetsForResults': True, 'sourceName': RESULT_SOURCE_NAME, 'sourceUrl': RESULT_SOURCE_URL})
    # Result source is locked to the approved source so old websites cannot be used accidentally.
    settings['sourceName'] = RESULT_SOURCE_NAME
    settings['sourceUrl'] = RESULT_SOURCE_URL
    if 'autoScrapeEnabled' in data:
        settings['autoScrapeEnabled'] = bool(data.get('autoScrapeEnabled'))
    if 'useForwardTargetsForResults' in data:
        settings['useForwardTargetsForResults'] = bool(data.get('useForwardTargetsForResults'))
    _firebase_put_top_level_children(state, {'resultSettings': settings}, audit=False)
    return jsonify({'status': 'success', 'resultSettings': settings})




@app.route('/api/gateway_result_retry', methods=['POST'])
def api_gateway_result_retry():
    data = request.json or {}
    try:
        res = _gateway_request('POST', '/result_retry', json=data, timeout=8)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/spam_guard')
def api_spam_guard():
    state = migrate_and_get_state()
    settings = state.get('spamGuardSettings', _default_spam_guard_settings())
    events = state.get('spamGuardEvents', []) if isinstance(state.get('spamGuardEvents', []), list) else []
    strikes = state.get('spamGuardStrikes', {}) if isinstance(state.get('spamGuardStrikes', {}), dict) else {}
    return jsonify({
        'status': 'success',
        'settings': settings,
        'events': list(reversed(events[-80:])),
        'strikeCount': len(strikes)
    })

@app.route('/api/save_spam_guard', methods=['POST'])
def api_save_spam_guard():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('spamGuardSettings', _default_spam_guard_settings())
    bool_keys = ['enabled', 'groupsOnly', 'linkGuardEnabled', 'forwardGuardEnabled', 'deleteMessage', 'kickEnabled', 'exemptAdmins']
    for k in bool_keys:
        if k in data:
            settings[k] = bool(data.get(k))
    int_keys = {'linkStrikeLimit': 3, 'forwardStrikeLimit': 3, 'forwardWindowSeconds': 60}
    for k, default in int_keys.items():
        if k in data:
            try:
                settings[k] = max(1 if 'Limit' in k else 10, int(data.get(k) or default))
            except Exception:
                settings[k] = default
    text_keys = ['alertMessage', 'warningMessage', 'kickMessage', 'forwardAlertMessage', 'forwardWarningMessage']
    for k in text_keys:
        if k in data:
            settings[k] = str(data.get(k) or _default_spam_guard_settings().get(k, '')).strip()
    _add_audit(state, 'spam_guard_settings', {'settings': settings})
    _firebase_put_top_level_children(state, {'spamGuardSettings': settings})
    return jsonify({'status': 'success', 'settings': settings})

@app.route('/api/clear_spam_guard', methods=['POST'])
def api_clear_spam_guard():
    state = migrate_and_get_state()
    state['spamGuardStrikes'] = {}
    state['spamGuardEvents'] = []
    _add_audit(state, 'spam_guard_clear', {})
    _firebase_put_top_level_children(state, {
        'spamGuardStrikes': {},
        'spamGuardEvents': []
    })
    return jsonify({'status': 'success'})


@app.route('/api/whatsapp_safety')
def api_whatsapp_safety():
    state = migrate_and_get_state()
    settings = state.get('whatsappSafetySettings', _default_whatsapp_safety_settings())
    targets = state.get('whatsappSafetyTargets', {}) if isinstance(state.get('whatsappSafetyTargets', {}), dict) else {}
    events = state.get('whatsappSafetyEvents', []) if isinstance(state.get('whatsappSafetyEvents', []), list) else []
    gateway = {'status': 'offline'}
    try:
        r = _gateway_request('GET', '/whatsapp_safety_status', timeout=4)
        gateway = r.json()
        if gateway.get('status') == 'success':
            settings = gateway.get('settings') or settings
            targets = gateway.get('targets') or targets
            events = gateway.get('events') or list(reversed(events[-80:]))
    except Exception as e:
        gateway = {'status': 'offline', 'message': str(e)}
    return jsonify({'status': 'success', 'settings': settings, 'targets': targets, 'events': list(events[-80:]) if isinstance(events, list) else [], 'gateway': gateway})

@app.route('/api/save_whatsapp_safety', methods=['POST'])
def api_save_whatsapp_safety():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('whatsappSafetySettings', _default_whatsapp_safety_settings())
    bool_keys = ['enabled', 'globalPaused', 'requireApprovedTargets', 'duplicateBlock', 'autoPauseTargetOnFailures', 'autoPauseGlobalOnFailures', 'safeModeForGroupsOnly', 'allowPrivateReplies', 'allowAdminNotifications']
    for k in bool_keys:
        if k in data:
            settings[k] = bool(data.get(k))
    int_keys = {
        'minDelayMs': 0,
        'randomDelayMs': 0,
        'duplicateWindowMinutes': 1,
        'targetFailureLimit': 1,
        'globalConsecutiveFailureLimit': 1,
        'dailyTargetLimit': 0,
        'dailyGlobalLimit': 0
    }
    for k, minv in int_keys.items():
        if k in data:
            try:
                settings[k] = max(minv, int(float(data.get(k) or 0)))
            except Exception:
                pass
    if 'pauseReason' in data:
        settings['pauseReason'] = str(data.get('pauseReason') or '').strip()[:200]
    if 'adminAlertTargets' in data:
        settings['adminAlertTargets'] = _normalize_forward_targets(data.get('adminAlertTargets') or [])
    settings['updatedAt'] = datetime.now().isoformat()
    state.setdefault('whatsappSafetyEvents', []).append({'id': f"WSG{int(time.time()*1000)}", 'time': datetime.now().isoformat(), 'date': _safe_today(), 'action': 'settings_saved', 'target': 'ALL'})
    state['whatsappSafetyEvents'] = state.get('whatsappSafetyEvents', [])[-300:]
    _add_audit(state, 'whatsapp_safety_settings', {'settings': settings})
    _firebase_put_top_level_children(state, {'whatsappSafetySettings': settings, 'whatsappSafetyEvents': state.get('whatsappSafetyEvents', [])})
    return jsonify({'status': 'success', 'settings': settings})

@app.route('/api/whatsapp_safety_pause', methods=['POST'])
def api_whatsapp_safety_pause():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('whatsappSafetySettings', _default_whatsapp_safety_settings())
    settings['globalPaused'] = True
    settings['pauseReason'] = str(data.get('reason') or 'Manual safety pause').strip()[:200]
    settings['updatedAt'] = datetime.now().isoformat()
    state.setdefault('whatsappSafetyEvents', []).append({'id': f"WSG{int(time.time()*1000)}", 'time': datetime.now().isoformat(), 'date': _safe_today(), 'action': 'global_paused', 'target': 'ALL', 'reason': settings['pauseReason']})
    state['whatsappSafetyEvents'] = state.get('whatsappSafetyEvents', [])[-300:]
    _add_audit(state, 'whatsapp_safety_pause', {'reason': settings['pauseReason']})
    _firebase_put_top_level_children(state, {'whatsappSafetySettings': settings, 'whatsappSafetyEvents': state.get('whatsappSafetyEvents', [])})
    try:
        _gateway_request('POST', '/whatsapp_safety_pause', json={'reason': settings['pauseReason']}, timeout=3)
    except Exception:
        pass
    return jsonify({'status': 'success', 'settings': settings})

@app.route('/api/whatsapp_safety_resume', methods=['POST'])
def api_whatsapp_safety_resume():
    state = migrate_and_get_state()
    settings = state.setdefault('whatsappSafetySettings', _default_whatsapp_safety_settings())
    settings['globalPaused'] = False
    settings['pauseReason'] = ''
    settings['updatedAt'] = datetime.now().isoformat()
    state.setdefault('whatsappSafetyEvents', []).append({'id': f"WSG{int(time.time()*1000)}", 'time': datetime.now().isoformat(), 'date': _safe_today(), 'action': 'global_resumed', 'target': 'ALL'})
    state['whatsappSafetyEvents'] = state.get('whatsappSafetyEvents', [])[-300:]
    _add_audit(state, 'whatsapp_safety_resume', {})
    _firebase_put_top_level_children(state, {'whatsappSafetySettings': settings, 'whatsappSafetyEvents': state.get('whatsappSafetyEvents', [])})
    try:
        _gateway_request('POST', '/whatsapp_safety_resume', json={}, timeout=3)
    except Exception:
        pass
    return jsonify({'status': 'success', 'settings': settings})

@app.route('/api/whatsapp_safety_target', methods=['POST'])
def api_whatsapp_safety_target():
    data = request.json or {}
    target = str(data.get('target') or data.get('id') or data.get('jid') or '').strip()
    if not target:
        return jsonify({'status': 'error', 'message': 'target required'}), 400
    import re
    m = re.search(r'([0-9A-Za-z._:-]+@(?:g\.us|s\.whatsapp\.net))', target, re.I)
    if m:
        target = m.group(1)
    target = target.replace(':', ':')
    state = migrate_and_get_state()
    store = state.setdefault('whatsappSafetyTargets', {})
    rec = store.setdefault(target, {'id': target, 'type': 'group' if '@g.us' in target else 'contact', 'approved': True, 'paused': False, 'failureCount': 0, 'dailyCount': 0})
    if 'approved' in data:
        rec['approved'] = bool(data.get('approved'))
    if 'paused' in data:
        rec['paused'] = bool(data.get('paused'))
    status = str(data.get('status') or '').lower()
    if status == 'approve': rec['approved'] = True
    if status == 'pause': rec['paused'] = True
    if status == 'resume': rec['paused'] = False
    if status == 'reset_failures':
        rec['failureCount'] = 0
        rec['lastError'] = ''
    if data.get('name'):
        rec['name'] = str(data.get('name'))[:120]
    rec['pauseReason'] = str(data.get('reason') or rec.get('pauseReason') or ('Manual target pause' if rec.get('paused') else '')).strip()[:200] if rec.get('paused') else ''
    rec['updatedAt'] = datetime.now().isoformat()
    state.setdefault('whatsappSafetyEvents', []).append({'id': f"WSG{int(time.time()*1000)}", 'time': datetime.now().isoformat(), 'date': _safe_today(), 'action': 'target_update', 'target': target, 'approved': rec.get('approved'), 'paused': rec.get('paused')})
    state['whatsappSafetyEvents'] = state.get('whatsappSafetyEvents', [])[-300:]
    _add_audit(state, 'whatsapp_safety_target', {'target': target, 'approved': rec.get('approved'), 'paused': rec.get('paused')})
    _firebase_put_top_level_children(state, {'whatsappSafetyTargets': store, 'whatsappSafetyEvents': state.get('whatsappSafetyEvents', [])})
    try:
        _gateway_request('POST', '/whatsapp_safety_target', json=data, timeout=3)
    except Exception:
        pass
    return jsonify({'status': 'success', 'target': rec})

@app.route('/api/clear_whatsapp_safety', methods=['POST'])
def api_clear_whatsapp_safety():
    state = migrate_and_get_state()
    state['whatsappSafetyEvents'] = []
    for rec in (state.get('whatsappSafetyTargets') or {}).values():
        if isinstance(rec, dict):
            rec['failureCount'] = 0
            rec['lastError'] = ''
    _add_audit(state, 'whatsapp_safety_clear', {})
    _firebase_put_top_level_children(state, {
        'whatsappSafetyTargets': state.get('whatsappSafetyTargets', {}),
        'whatsappSafetyEvents': state.get('whatsappSafetyEvents', [])
    })
    return jsonify({'status': 'success'})

@app.route('/api/load_forwarder')
def api_load_forwarder():
    state = migrate_and_get_state()
    settings = state.get('loadForwarder', _default_load_forwarder_settings())
    date = request.args.get('date') or _safe_today()
    market = request.args.get('market') or settings.get('selectedMarket') or ''
    max_rows = int(settings.get('maxRowsPerType') or 80)
    report = _build_load_report(state, date=date, market=market, max_rows=max_rows, include_empty=bool(settings.get('includeEmptyTypes')), game_types=settings.get('gameTypes'))
    return jsonify({
        'status': 'success',
        'date': date,
        'settings': settings,
        'report': report,
        'text': _format_load_report_text(report),
        'targets': settings.get('targets', [])
    })

@app.route('/api/save_load_forwarder', methods=['POST'])
def api_save_load_forwarder():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('loadForwarder', _default_load_forwarder_settings())
    if 'enabled' in data:
        settings['enabled'] = bool(data.get('enabled'))
    if 'scheduleTime' in data:
        norm = _normalize_hhmm(data.get('scheduleTime'))
        if norm:
            settings['scheduleTime'] = norm
    if 'selectedMarket' in data:
        settings['selectedMarket'] = ' '.join(str(data.get('selectedMarket') or '').strip().upper().split())
    if 'targets' in data:
        settings['targets'] = _normalize_forward_targets(data.get('targets'))
    if 'gameTypes' in data:
        settings['gameTypes'] = _normalize_game_types(data.get('gameTypes'))
    if 'maxRowsPerType' in data:
        try:
            settings['maxRowsPerType'] = max(5, min(300, int(data.get('maxRowsPerType') or 80)))
        except Exception:
            settings['maxRowsPerType'] = 80
    if 'includeEmptyTypes' in data:
        settings['includeEmptyTypes'] = bool(data.get('includeEmptyTypes'))
    settings['updatedAt'] = _now_iso_local()
    _add_audit(state, 'load_forwarder_settings', settings)
    _firebase_put_top_level_children(state, {'loadForwarder': settings})
    return jsonify({'status': 'success', 'settings': settings})

@app.route('/api/load_report_preview')
def api_load_report_preview():
    state = migrate_and_get_state()
    settings = state.get('loadForwarder', _default_load_forwarder_settings())
    date = request.args.get('date') or _safe_today()
    market = request.args.get('market') or settings.get('selectedMarket') or ''
    max_rows = int(request.args.get('maxRowsPerType') or settings.get('maxRowsPerType') or 80)
    game_types = request.args.get('gameTypes') or ','.join(settings.get('gameTypes') or ['ANK', 'PENEL', 'JODI'])
    report = _build_load_report(state, date=date, market=market, max_rows=max_rows, include_empty=bool(settings.get('includeEmptyTypes')), game_types=game_types)
    return jsonify({'status': 'success', 'date': date, 'report': report, 'text': _format_load_report_text(report)})

@app.route('/api/load_forwarder_send', methods=['POST'])
def api_load_forwarder_send():
    data = request.json or {}
    state = migrate_and_get_state()
    settings = state.setdefault('loadForwarder', _default_load_forwarder_settings())
    date = data.get('date') or _safe_today()
    market = data.get('market') if 'market' in data else settings.get('selectedMarket', '')
    targets = _normalize_forward_targets(data.get('targets') if 'targets' in data else settings.get('targets', []))
    if not targets:
        return jsonify({'status': 'error', 'message': 'Forward target select/save karein.'}), 400
    max_rows = int(data.get('maxRowsPerType') or settings.get('maxRowsPerType') or 80)
    game_types = data.get('gameTypes') if 'gameTypes' in data else settings.get('gameTypes')
    report = _build_load_report(state, date=date, market=market, max_rows=max_rows, include_empty=bool(settings.get('includeEmptyTypes')), game_types=game_types)
    text = _format_load_report_text(report)
    msg = {
        'id': str(uuid.uuid4())[:8].upper(),
        'date': date,
        'market': ' '.join(str(market or '').strip().upper().split()),
        'targets': targets,
        'text': text,
        'status': 'pending',
        'attempts': 0,
        'createdAt': _now_iso_local(),
        'source': data.get('source') or 'dashboard_send_now'
    }
    state.setdefault('loadForwarderOutbox', []).append(msg)
    if len(state['loadForwarderOutbox']) > 300:
        state['loadForwarderOutbox'] = state['loadForwarderOutbox'][-300:]
    settings['lastQueuedAt'] = _now_iso_local()
    _add_audit(state, 'load_report_queued', {'id': msg['id'], 'date': date, 'market': msg['market'], 'targets': targets})
    _firebase_put_top_level_children(state, {
        'loadForwarder': settings,
        'loadForwarderOutbox': state.get('loadForwarderOutbox', [])
    })
    return jsonify({'status': 'success', 'message': 'Load report queue ho gaya. Gateway online hote hi send karega.', 'queued': msg, 'text': text})


# ==========================================================
# TITAN NOVA BACKUP / EXPORT / AUDIT API
# ==========================================================
def _json_dumps_safe(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)

def _csv_bytes(headers, rows):
    buff = io.StringIO()
    writer = csv.DictWriter(buff, fieldnames=headers, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, '') for h in headers})
    return buff.getvalue().encode('utf-8-sig')

def _csv_response(filename, headers, rows):
    data = _csv_bytes(headers, rows)
    return app.response_class(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

def _backup_summary(state_obj):
    today = _safe_today()
    entries = state_obj.get('entries', []) if isinstance(state_obj.get('entries', []), list) else []
    payments = state_obj.get('payments', []) if isinstance(state_obj.get('payments', []), list) else []
    wallets = state_obj.get('wallets', {}) if isinstance(state_obj.get('wallets', {}), dict) else {}
    settlements = state_obj.get('settlementRecords', {}) if isinstance(state_obj.get('settlementRecords', {}), dict) else {}
    today_settlements = settlements.get(today, {}) if isinstance(settlements.get(today, {}), dict) else {}
    audit = state_obj.get('auditLog', []) if isinstance(state_obj.get('auditLog', []), list) else []
    accepted_today = [e for e in entries if e.get('date') == today and e.get('status') == 'accepted']
    return {
        'date': today,
        'profiles': len(state_obj.get('profiles', {}) or {}),
        'wallets': len(wallets),
        'entries': len(entries),
        'acceptedToday': len(accepted_today),
        'todayLoad': round(sum(_wallet_float(e.get('total', 0)) for e in accepted_today), 2),
        'payments': len(payments),
        'pendingPayments': len([p for p in payments if p.get('status') == 'pending']),
        'settlementDays': len(settlements),
        'todaySettlements': len(today_settlements),
        'auditEvents': len(audit),
        'lastBackupAt': (state_obj.get('backupSettings') or {}).get('lastBackupAt', '')
    }

def _entries_export_rows(state_obj):
    rows = []
    for e in state_obj.get('entries', []) if isinstance(state_obj.get('entries', []), list) else []:
        if not isinstance(e, dict):
            continue
        rows.append({
            'id': e.get('id', ''),
            'date': e.get('date', ''),
            'time': e.get('time') or e.get('createdAt', ''),
            'status': e.get('status', ''),
            'userId': e.get('userId', ''),
            'userName': e.get('userName', ''),
            'phone': e.get('phone') or e.get('senderPhone', ''),
            'market': e.get('market', ''),
            'gameType': e.get('gameType') or e.get('type', ''),
            'digits': ','.join([str(x) for x in e.get('digits', [])]) if isinstance(e.get('digits'), list) else str(e.get('digits', '')),
            'parDigit': e.get('parDigit') or e.get('rate', ''),
            'total': e.get('total', ''),
            'source': e.get('source', ''),
            'rawText': e.get('rawText', '')
        })
    return rows

def _wallet_export_rows(state_obj):
    rows = []
    wallets = state_obj.get('wallets', {}) if isinstance(state_obj.get('wallets', {}), dict) else {}
    for uid, w in wallets.items():
        if not isinstance(w, dict):
            continue
        ledger = w.get('ledger', []) if isinstance(w.get('ledger', []), list) else []
        rows.append({
            'userId': uid,
            'name': w.get('name', ''),
            'phone': w.get('phone', ''),
            'balance': w.get('balance', 0),
            'creditLimit': w.get('creditLimit', 0),
            'available': round(_wallet_float(w.get('balance', 0)) + _wallet_float(w.get('creditLimit', 0)), 2),
            'ledgerCount': len(ledger),
            'createdAt': w.get('createdAt', ''),
            'updatedAt': w.get('updatedAt', '')
        })
    return rows

def _withdrawal_export_rows(state_obj):
    rows = []
    for w in state_obj.get('withdrawals', []) if isinstance(state_obj.get('withdrawals', []), list) else []:
        rows.append({
            'id': w.get('id', ''),
            'userId': w.get('userId', ''),
            'userName': w.get('userName', ''),
            'phone': w.get('phone', ''),
            'amount': w.get('amount', 0),
            'method': w.get('method', ''),
            'detail': w.get('detail', ''),
            'status': w.get('status', ''),
            'createdAt': w.get('createdAt', ''),
            'approvedAt': w.get('approvedAt', ''),
            'rejectedAt': w.get('rejectedAt', ''),
            'rejectReason': w.get('rejectReason', '')
        })
    return rows

def _wallet_ledger_export_rows(state_obj):
    rows = []
    wallets = state_obj.get('wallets', {}) if isinstance(state_obj.get('wallets', {}), dict) else {}
    for uid, w in wallets.items():
        if not isinstance(w, dict):
            continue
        for item in w.get('ledger', []) if isinstance(w.get('ledger', []), list) else []:
            if not isinstance(item, dict):
                continue
            rows.append({
                'userId': uid,
                'name': w.get('name', ''),
                'phone': w.get('phone', ''),
                'time': item.get('time') or item.get('timestamp') or item.get('createdAt', ''),
                'type': item.get('type', ''),
                'amount': item.get('amount', ''),
                'balanceAfter': item.get('balanceAfter', ''),
                'note': item.get('note') or item.get('reason', ''),
                'ref': item.get('ref', '')
            })
    return rows

def _payments_export_rows(state_obj):
    rows = []
    for pmt in state_obj.get('payments', []) if isinstance(state_obj.get('payments', []), list) else []:
        if not isinstance(pmt, dict):
            continue
        rows.append({
            'id': pmt.get('id', ''),
            'userId': pmt.get('userId', ''),
            'userName': pmt.get('userName', ''),
            'amount': pmt.get('amount', ''),
            'utr': pmt.get('utr', ''),
            'status': pmt.get('status', ''),
            'autoFlag': pmt.get('autoFlag', ''),
            'planLabel': pmt.get('planLabel', ''),
            'time': pmt.get('time', ''),
            'approvedAt': pmt.get('approvedAt', ''),
            'rejectedAt': pmt.get('rejectedAt', ''),
            'rejectReason': pmt.get('rejectReason', ''),
            'walletCredited': pmt.get('walletCredited', '')
        })
    return rows

def _settlement_export_rows(state_obj):
    rows = []
    records = state_obj.get('settlementRecords', {}) if isinstance(state_obj.get('settlementRecords', {}), dict) else {}
    for date, markets_map in records.items():
        if not isinstance(markets_map, dict):
            continue
        for market, stages in markets_map.items():
            if not isinstance(stages, dict):
                continue
            for stage, rec in stages.items():
                if not isinstance(rec, dict):
                    continue
                rows.append({
                    'date': date,
                    'market': market,
                    'stage': stage,
                    'result': rec.get('result', ''),
                    'entries': rec.get('entries', rec.get('entryCount', '')),
                    'hit': rec.get('hit', rec.get('hitCount', '')),
                    'miss': rec.get('miss', rec.get('missCount', '')),
                    'load': rec.get('load', rec.get('totalLoad', '')),
                    'payout': rec.get('payout', rec.get('totalPayout', '')),
                    'profitLoss': rec.get('profitLoss', rec.get('marketProfit', '')),
                    'settledAt': rec.get('settledAt') or rec.get('createdAt', '')
                })
    return rows

def _audit_export_rows(state_obj):
    rows = []
    for a in state_obj.get('auditLog', []) if isinstance(state_obj.get('auditLog', []), list) else []:
        if not isinstance(a, dict):
            continue
        rows.append({
            'id': a.get('id', ''),
            'time': a.get('time', ''),
            'action': a.get('action', ''),
            'detail': _json_dumps_safe(a.get('detail', {}))
        })
    return rows

def _csv_export_spec(kind, state_obj):
    kind = str(kind or '').strip().lower()
    if kind == 'entries':
        rows = _entries_export_rows(state_obj)
        return 'entries', ['id','date','time','status','userId','userName','phone','market','gameType','digits','parDigit','total','source','rawText'], rows
    if kind == 'wallets':
        rows = _wallet_export_rows(state_obj)
        return 'wallets', ['userId','name','phone','balance','creditLimit','hold','available','withdrawAvailable','ledgerCount','createdAt','updatedAt'], rows
    if kind in ('wallet_ledger','ledger'):
        rows = _wallet_ledger_export_rows(state_obj)
        return 'wallet_ledger', ['userId','name','phone','time','type','amount','balanceAfter','note','ref'], rows
    if kind in ('wallet_transactions','wallet_history'):
        rows = []
        for x in _wallet_transactions_from_state(state_obj, None, 2000):
            rows.append({
                'userId': x.get('userId',''), 'name': x.get('name',''), 'phone': x.get('phone',''), 'time': x.get('time',''),
                'type': x.get('type',''), 'amount': x.get('amount',0), 'balanceBefore': x.get('balanceBefore',0),
                'balanceAfter': x.get('balanceAfter',0), 'holdBefore': x.get('holdBefore',0), 'holdAfter': x.get('holdAfter',0),
                'source': x.get('source',''), 'note': x.get('note',''), 'refId': x.get('refId','')
            })
        return 'wallet_transactions', ['userId','name','phone','time','type','amount','balanceBefore','balanceAfter','holdBefore','holdAfter','source','note','refId'], rows
    if kind == 'payments':
        rows = _payments_export_rows(state_obj)
        return 'payments', ['id','userId','userName','amount','utr','status','autoFlag','planLabel','time','approvedAt','rejectedAt','rejectReason','walletCredited'], rows
    if kind == 'settlements':
        rows = _settlement_export_rows(state_obj)
        return 'settlements', ['date','market','stage','result','entries','hit','miss','load','payout','profitLoss','settledAt'], rows
    if kind == 'audit':
        rows = _audit_export_rows(state_obj)
        return 'audit', ['id','time','action','detail'], rows
    return None, None, None



def _health_recent_result_updates(state_obj, today):
    """Return recent saved open/close results from Firebase state for Health tab.
    This survives Gateway restarts, unlike runtime gatewayHealth counters.
    """
    out = []
    records = (state_obj.get('resultRecords', {}) or {}).get(today, {}) if isinstance(state_obj, dict) else {}
    if not isinstance(records, dict):
        return out
    for market, rec in records.items():
        if not isinstance(rec, dict):
            continue
        for stage_key, result_key, time_key in [
            ('open', 'openResult', 'openUpdatedAt'),
            ('close', 'closeResult', 'closeUpdatedAt')
        ]:
            result = str(rec.get(result_key, '') or '').strip()
            if not result:
                continue
            out.append({
                'market': market,
                'stage': stage_key,
                'result': result,
                'time': rec.get(time_key) or rec.get('updatedAt') or rec.get('lastResultAt') or '',
                'source': rec.get('source') or rec.get('sourceUrl') or 'firebase'
            })
    def _sort_key(x):
        return str(x.get('time') or '')
    return sorted(out, key=_sort_key, reverse=True)[:12]

def _health_label_guard_reason(reason):
    reason = str(reason or '').strip()
    labels = {
        'fresh_open_missing': 'Old/final ignored — fresh open missing',
        'close_open_mismatch': 'Close ignored — open/result mismatch',
        'invalid_format': 'Invalid result format skipped',
        'stale_candidate': 'Stale duplicate skipped'
    }
    return labels.get(reason, reason or 'skipped')

def _safe_update_code_markers_status():
    """Lightweight marker audit used before/after future patches.
    This does not prove runtime success, but it catches accidental removal of protected systems.
    """
    checks = []
    root = BASE_DIR
    files = {
        'flask_app.py': os.path.join(root, 'flask_app.py'),
        'Gateway.js': os.path.join(root, 'Gateway.js')
    }
    texts = {}
    for name, path in files.items():
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                texts[name] = fh.read()
            checks.append({'key': f'file_{name}', 'name': f'{name} exists/readable', 'ok': True, 'detail': path})
        except Exception as e:
            texts[name] = ''
            checks.append({'key': f'file_{name}', 'name': f'{name} exists/readable', 'ok': False, 'detail': str(e), 'critical': True})

    combined = "\n".join(texts.values())
    marker_specs = [
        ('whatsapp_login', ['wa_login_status', 'wa_reset_session', 'wa_qr_text'], True),
        ('auto_profile_admin_approval', ['autoCreatePendingProfiles', 'approvalStatus', 'profile_pending_approval'], True),
        ('ledger_daily_repeat', ['ledgerSchedules', 'Auto Schedule', 'scheduleTime', 'scheduleRuntimePreserveGuard'], True),
        ('ledger_duplicate_lock', ['scheduleTickRunning', 'scheduleTargetLogKey', 'markScheduleTargetSent'], True),
        ('withdrawal_flow', ['withdrawalSettings', 'approvalNotified', 'paidNotified', 'mark_paid'], True),
        ('wallet_audit', ['walletTransactions', 'wallet_history', 'wallet_transactions'], True),
        ('target_picker', ['openTargetPicker', 'targetPickerState', 'readSavedTargetLists'], False),
        ('whatsapp_safety_guard', ['whatsappSafetySettings', 'refreshWhatsappSafetyState', 'saveWhatsappSafetySettings'], True),
        ('result_source', [RESULT_SOURCE_URL, RESULT_SOURCE_NAME, 'LIVE MATKA RESULT'], True),
        ('strict_open_close', ['fresh_open_missing_strict_2_stage', 'strict 2-stage', 'OPEN'], True),
    ]
    for key, markers, critical in marker_specs:
        missing = [m for m in markers if m not in combined]
        checks.append({
            'key': key,
            'name': next((f['name'] for f in SAFE_UPDATE_PROTECTED_FEATURES if f['key'] == key), key),
            'ok': not missing,
            'critical': critical,
            'missingMarkers': missing,
            'detail': 'OK' if not missing else ('Missing markers: ' + ', '.join(missing[:6]))
        })

    old_sources = ['dp' + 'bosse.net', 'dp' + 'boss.net', 'dp' + 'boss.services', 'dp' + 'bossmatka', 'satta' + 'matka.mobi']
    found_old = [x for x in old_sources if x in combined and x not in RESULT_SOURCE_URL]
    checks.append({
        'key': 'old_result_sources_removed',
        'name': 'Old result sources removed/blocked',
        'ok': not found_old,
        'critical': True,
        'found': found_old,
        'detail': 'OK' if not found_old else ('Old source marker found: ' + ', '.join(found_old))
    })
    return checks

def _safe_update_guard_summary(state_obj=None):
    checks = _safe_update_code_markers_status()
    critical_failed = [c for c in checks if c.get('critical') and not c.get('ok')]
    failed = [c for c in checks if not c.get('ok')]
    return {
        'version': SAFE_UPDATE_VERSION,
        'status': 'safe' if not critical_failed else 'attention_required',
        'message': 'Protected systems markers are present.' if not critical_failed else 'Critical protected markers are missing; check before deploying.',
        'protectedFeatures': SAFE_UPDATE_PROTECTED_FEATURES,
        'settings': (state_obj or {}).get('updateGuardSettings', _default_update_guard_settings()) if isinstance(state_obj, dict) else _default_update_guard_settings(),
        'checks': checks,
        'failed': failed,
        'criticalFailed': critical_failed,
        'source': {'name': RESULT_SOURCE_NAME, 'url': RESULT_SOURCE_URL},
        'checkedAt': _now_iso_local(),
        'rules': [
            'Future update me existing protected feature delete/rename nahi karna.',
            'New feature ko isolated helper/route/function me add karo; common wallet/result/schedule flow ko direct edit na karo jab tak zaroori na ho.',
            'Deployment se pehle python safe_update_check.py run karo.',
            'Browser/PWA blank prevention ke liye rendered front-end JavaScript syntax check zaroor karo.',
        ]
    }


# ==========================================================
# FULL A-Z AUDIT GUARD — PHASE 1 + PHASE 2
# ==========================================================
FULL_AUDIT_PHASE1_FEATURE_FREEZE = True
FULL_AUDIT_PHASE2_SINGLE_SOURCE_CLEANUP = True
FULL_AUDIT_VERSION = "2026-06-30-phase2-single-source-cleanup-v1"
FULL_AUDIT_LOCKED_FEATURES = [
    "WhatsApp Easy Login",
    "New WhatsApp User Auto Profile + Admin Approval",
    "Ledger Daily Repeat Schedule",
    "Ledger Duplicate Send Lock",
    "Ledger Intel Share Schedule + Auto Rate Compact Format",
    "SattaMatkaDpboss.Mobi Result Source",
    "Strict Open/Close No-Old Result Safety",
    "Ledger Auto Pass/Fail Live Sync",
    "Withdrawal Approve / Pay Now / Mark Paid",
    "Wallet Transaction History / Audit",
    "Advanced Target Picker",
    "WhatsApp Safe Messaging Guard",
    "Safe Update Guard",
    "Full Audit Phase 1 Feature Freeze Guard",
    "Full Audit Phase 2 Single Source Cleanup Guard",
]

def _full_audit_phase1_summary():
    return {
        "phase": "phase4_production_diagnostics",
        "version": PRODUCTION_DIAGNOSTICS_VERSION if 'PRODUCTION_DIAGNOSTICS_VERSION' in globals() else FULL_AUDIT_VERSION,
        "status": "locked",
        "message": "Phase 2 single-source cleanup guard active. Run python full_audit_check.py before deploy.",
        "featureFreeze": FULL_AUDIT_PHASE1_FEATURE_FREEZE,
        "singleSourceCleanup": FULL_AUDIT_PHASE2_SINGLE_SOURCE_CLEANUP,
        "runtimeSelfHealing": FULL_AUDIT_PHASE3_RUNTIME_SELF_HEALING,
        "productionDiagnostics": FULL_AUDIT_PHASE4_PRODUCTION_DIAGNOSTICS,
        "lockedFeatures": FULL_AUDIT_LOCKED_FEATURES,
        "sourceOfTruth": {
            "ledgerSchedule": "ledgerSchedules + scheduleRuntimePreserveGuard",
            "whatsappSending": "Gateway sendText() -> whatsappSafetyBeforeSend() -> safeSendQueueRun()",
            "operationalReplies": "Gateway replyToMessage()/sendSpamGuardNotice() -> safeSendQueueRun()",
            "resultSource": RESULT_SOURCE_URL,
            "resultSendLock": "sentLog result target signatures",
            "ledgerScheduleLock": "sentLog schedule per date/card/time/target",
            "withdrawalFinalDeduct": "Mark Paid only",
            "targets": "Advanced Target Picker + saved target lists",
        },
        "noBreakContract": "Existing locked features cannot be bypassed by duplicate helper/route/source logic.",
        "commands": ["python safe_update_check.py", "python full_audit_check.py"],
        "checkedAt": _now_iso_local(),
    }

@app.route('/api/full_audit')
def api_full_audit():
    return jsonify({'status': 'success', 'fullAudit': _full_audit_phase1_summary()})

@app.route('/api/update_guard')
def api_update_guard():
    state = migrate_and_get_state()
    summary = _safe_update_guard_summary(state)
    if isinstance(state, dict):
        state.setdefault('updateGuardSettings', _default_update_guard_settings())
        state['updateGuardSettings']['lastSafeCheckAt'] = summary['checkedAt']
        state['updateGuardSettings']['lastSafeCheckStatus'] = summary['status']
        try:
            _firebase_put_top_level_children(state, {'updateGuardSettings': state.get('updateGuardSettings', {})}, audit=False)
        except Exception:
            pass
    return jsonify({'status': 'success', 'updateGuard': summary})

@app.route('/api/health_monitor')
def api_health_monitor():
    state = migrate_and_get_state()
    today = _safe_today()

    def _count_pending(items):
        if not isinstance(items, list):
            return 0
        return len([x for x in items if isinstance(x, dict) and str(x.get('status', '')).lower() == 'pending'])

    gateway = {'status': 'offline', 'connected': False, 'message': 'Gateway not reachable'}
    gateway_results = {'status': 'offline', 'results': []}
    gateway_targets = {'status': 'offline', 'contacts': [], 'groups': []}
    wa_login = {'status': 'offline', 'connected': False, 'qrAvailable': False}
    try:
        r = _gateway_request('GET', '/health', timeout=4)
        try:
            gateway = r.json()
        except Exception:
            gateway = {'status': 'error', 'connected': False, 'message': r.text[:200]}
    except Exception as e:
        gateway = {'status': 'offline', 'connected': False, 'message': str(e)}
    try:
        r = _gateway_request('GET', '/results', timeout=4)
        gateway_results = r.json()
    except Exception as e:
        gateway_results = {'status': 'offline', 'results': [], 'message': str(e)}
    try:
        r = _gateway_request('GET', '/targets?force=1', timeout=6)
        gateway_targets = r.json()
    except Exception as e:
        gateway_targets = {'status': 'offline', 'contacts': [], 'groups': [], 'message': str(e)}

    try:
        r = _gateway_request('GET', '/wa_login_status', timeout=4)
        wa_login = r.json()
    except Exception as e:
        wa_login = {'status': 'offline', 'connected': False, 'qrAvailable': False, 'message': str(e)}

    entries = state.get('entries', []) if isinstance(state.get('entries', []), list) else []
    today_entries = [e for e in entries if isinstance(e, dict) and e.get('date') == today and e.get('status') == 'accepted']
    today_load = sum(_wallet_float(e.get('total', 0)) for e in today_entries)
    settlements_today = state.get('settlementRecords', {}).get(today, {}) if isinstance(state.get('settlementRecords', {}), dict) else {}
    result_records_today = state.get('resultRecords', {}).get(today, {}) if isinstance(state.get('resultRecords', {}), dict) else {}
    audit = state.get('auditLog', []) if isinstance(state.get('auditLog', []), list) else []
    payments = state.get('payments', []) if isinstance(state.get('payments', []), list) else []
    payment_outbox = state.get('paymentOutbox', []) if isinstance(state.get('paymentOutbox', []), list) else []
    load_outbox = state.get('loadForwarderOutbox', []) if isinstance(state.get('loadForwarderOutbox', []), list) else []
    lf = state.get('loadForwarder', _default_load_forwarder_settings()) or {}
    rs = state.get('resultSettings', {'autoScrapeEnabled': True, 'sourceName': RESULT_SOURCE_NAME, 'sourceUrl': RESULT_SOURCE_URL}) or {}

    summary = {
        'firebase': {'status': 'success', 'url': get_firebase_url(), 'lastCheckedAt': _now_iso_local()},
        'gateway': gateway,
        'gatewayResults': gateway_results,
        'gatewayTargets': gateway_targets,
        'waLogin': wa_login,
        'updateGuard': _safe_update_guard_summary(state),
        'modules': {
            'autoScrape': rs.get('autoScrapeEnabled', True),
            'entryParser': (state.get('entrySettings') or {}).get('entryParserEnabled', True),
            'marketTiming': (state.get('entrySettings') or {}).get('marketTimingEnabled', True),
            'riskLimits': (state.get('entrySettings') or {}).get('riskLimitsEnabled', True),
            'settlement': (state.get('settlementSettings') or {}).get('enabled', True),
            'paymentAutomation': (state.get('paymentSettings') or {}).get('paymentAutomationEnabled', True),
            'loadForwarder': lf.get('enabled', False),
            'spamGuard': (state.get('spamGuardSettings') or {}).get('enabled', True),
            'whatsappSafetyGuard': (state.get('whatsappSafetySettings') or {}).get('enabled', True)
        },
        'counts': {
            'profiles': len(state.get('profiles', {}) or {}),
            'wallets': len(state.get('wallets', {}) or {}),
            'acceptedEntriesToday': len(today_entries),
            'todayLoad': round(today_load, 2),
            'paymentsPending': len([p for p in payments if isinstance(p, dict) and p.get('status') == 'pending']),
            'paymentOutboxPending': _count_pending(payment_outbox),
            'loadForwardOutboxPending': _count_pending(load_outbox),
            'settlementsToday': len(settlements_today or {}),
            'resultMarketsToday': len(result_records_today or {}),
            'resultTargets': len(state.get('resultTargets', []) or []),
            'auditEvents': len(audit),
            'guardEvents': len(state.get('spamGuardEvents', []) or []) if isinstance(state.get('spamGuardEvents', []), list) else 0,
            'whatsappSafetyEvents': len(state.get('whatsappSafetyEvents', []) or []) if isinstance(state.get('whatsappSafetyEvents', []), list) else 0
        },
        'last': {
            'backupAt': (state.get('backupSettings') or {}).get('lastBackupAt', ''),
            'audit': audit[-1] if audit else None,
            'loadForwarder': {'scheduleTime': lf.get('scheduleTime', ''), 'lastSentAt': lf.get('lastSentAt', ''), 'lastSentKey': lf.get('lastSentKey', '')},
            'recentResultMarkets': list((result_records_today or {}).keys())[-8:],
            'recentFirebaseResults': _health_recent_result_updates(state, today),
            'guardReasonLabels': {
                'fresh_open_missing': _health_label_guard_reason('fresh_open_missing'),
                'close_open_mismatch': _health_label_guard_reason('close_open_mismatch'),
                'invalid_format': _health_label_guard_reason('invalid_format'),
                'stale_candidate': _health_label_guard_reason('stale_candidate')
            }
        }
    }
    return jsonify({'status': 'success', 'health': summary})

@app.route('/api/backup_audit')
def api_backup_audit():
    state = migrate_and_get_state()
    audit = state.get('auditLog', []) if isinstance(state.get('auditLog', []), list) else []
    return jsonify({
        'status': 'success',
        'summary': _backup_summary(state),
        'auditLog': list(reversed(audit[-200:])),
        'exports': ['entries', 'wallets', 'wallet_ledger', 'wallet_transactions', 'payments', 'withdrawals', 'settlements', 'audit']
    })

@app.route('/api/export_csv')
def api_export_csv():
    kind = request.args.get('kind') or 'entries'
    state = migrate_and_get_state()
    name, headers, rows = _csv_export_spec(kind, state)
    if not name:
        return jsonify({'status': 'error', 'message': 'Invalid export kind'}), 400
    date = _safe_today()
    return _csv_response(f'titan_{name}_{date}.csv', headers, rows)

@app.route('/api/download_backup')
def api_download_backup():
    state = migrate_and_get_state()
    _ensure_foundation_state(state)
    date = _safe_today()
    state.setdefault('backupSettings', {})['lastBackupAt'] = _now_iso_local()
    _add_audit(state, 'manual_backup_download', {'date': date})
    _firebase_put_top_level_children(state, {'backupSettings': state.get('backupSettings', {})})
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('state.json', json.dumps(state, ensure_ascii=False, indent=2))
        for kind in ['entries', 'wallets', 'wallet_ledger', 'wallet_transactions', 'payments', 'withdrawals', 'settlements', 'audit']:
            name, headers, rows = _csv_export_spec(kind, state)
            zf.writestr(f'{name}.csv', _csv_bytes(headers, rows))
        zf.writestr('README.txt', 'Titan Nova backup export. Restore carefully: state.json contains the full Firebase app state. CSV files are for audit/review.\n')
    mem.seek(0)
    return app.response_class(
        mem.read(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="titan_backup_{date}.zip"'}
    )

@app.route('/api/clear_audit_log', methods=['POST'])
def api_clear_audit_log():
    state = migrate_and_get_state()
    state['auditLog'] = []
    _add_audit(state, 'audit_log_cleared', {'time': _now_iso_local()})
    _firebase_put_top_level_children(state, {'auditLog': state.get('auditLog', [])}, audit=False)
    return jsonify({'status': 'success', 'auditLog': state.get('auditLog', []), 'summary': _backup_summary(state)})

# ==========================================================
# TITAN NOVA BAILEYS GATEWAY / AUTO-SCHEDULE API
# These routes keep the app stable even if the Node bot reads Firebase directly.
# ==========================================================
def _business_now():
    """Local business timestamp. Before cutoff hour, business date is previous calendar day."""
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(APP_TZ))
        except Exception:
            pass
    return datetime.datetime.now()

def _business_date_from_dt(dt):
    try:
        cutoff = int(BUSINESS_DAY_CUTOFF_HOUR)
    except Exception:
        cutoff = 6
    try:
        if int(dt.hour) < cutoff:
            dt = dt - datetime.timedelta(days=1)
    except Exception:
        pass
    return dt.date().isoformat()

def _safe_today():
    return _business_date_from_dt(_business_now())

def _calendar_today():
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo(APP_TZ)).date().isoformat()
        except Exception:
            pass
    return datetime.datetime.now().date().isoformat()

def _digits_display(v):
    if not v:
        return ""
    parts = [x.strip() for x in str(v).replace("|", ",").replace(" ", ",").split(",") if x.strip()]
    return ",".join(parts)


def _ledger_date_dmy(date_value):
    txt = str(date_value or "")
    try:
        return datetime.date.fromisoformat(txt).strftime("%d/%m/%Y")
    except Exception:
        return txt


def _ledger_digits_list(v):
    return [x.strip() for x in _digits_display(v).split(",") if x.strip()]


def _ledger_type_multiplier(typ):
    t = str(typ or "").lower()
    if t == "jodi":
        return 95.0
    if t in ("pannel", "panel", "penel"):
        return 150.0
    return 9.5


def _ledger_schedule_rate(rec):
    if not isinstance(rec, dict):
        rec = {}
    for k in ("r", "rate", "parDigit"):
        try:
            n = float(rec.get(k) or 0)
            if n > 0:
                return n
        except Exception:
            pass
    # v7: never fallback to ₹10 for scheduled ledger Intel. A blank rate means the
    # recovery/auto-rate engine did not resolve the card yet; schedule should skip/block
    # instead of sending a wrong amount.
    return 0.0


def _ledger_money(n):
    try:
        v = round(float(n or 0), 2)
    except Exception:
        v = 0.0
    if float(v).is_integer():
        return f"₹{int(v)}"
    return f"₹{v:.2f}"


def _format_ledger_intel_message(date_value, market_name, digits_value, rate_value, typ):
    digits = _ledger_digits_list(digits_value)
    rate = _ledger_schedule_rate({'r': rate_value})
    total = len(digits) * rate
    return (
        f"🚀 *TITAN NOVA INTEL* [{_ledger_date_dmy(date_value)}]\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 *MARKET:* {market_name}\n"
        f"🔢 *DIGITS:* [{', '.join(digits)}]\n"
        f"💰 *PAR DIGIT:* {_ledger_money(rate)}\n"
        f"💸 *TOTAL:* {_ledger_money(total)}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

def _normalize_schedule_time(v):
    txt = str(v or "").strip()
    parts = txt.split(":")
    if len(parts) < 2:
        return ""
    try:
        h, m = int(parts[0]), int(parts[1])
    except Exception:
        return ""
    if h < 0 or h > 23 or m < 0 or m > 59:
        return ""
    return f"{h:02d}:{m:02d}"

def _schedule_dict_name(typ):
    return 'data' if typ == 'ank' else ('jodiData' if typ == 'jodi' else 'pannelData')

def _ledger_norm_key_name(v):
    return str(v or '').strip().upper()

def _ledger_market_key(typ, market_name):
    return f"{str(typ or '').lower()}|{_ledger_norm_key_name(market_name)}"


# v33: schedule records must belong to the exact ledger card/stage.
def _schedule_exact_norm(v):
    return ' '.join(str(v or '').upper().split()).strip()

def _schedule_name_from_key(k):
    raw = str(k or '').strip()
    if not raw:
        return ''
    return _schedule_exact_norm(raw.split('|', 1)[1] if '|' in raw else raw)

def _schedule_stage_of_name(v):
    n = _schedule_exact_norm(v)
    if n.endswith(' OPEN'):
        return 'open'
    if n.endswith(' CLOSE'):
        return 'close'
    return ''

def _schedule_base_of_name(v):
    n = _schedule_exact_norm(v)
    if n.endswith(' OPEN'):
        return n[:-5].strip()
    if n.endswith(' CLOSE'):
        return n[:-6].strip()
    return n

def _schedule_record_matches_exact_card(sched, typ, idx, market_key, market_name):
    if not isinstance(sched, dict):
        return False
    typ = str(typ or '').lower()
    card_name = _schedule_exact_norm(market_name or _schedule_name_from_key(market_key))
    card_key = _schedule_exact_norm(market_key or (_ledger_market_key(typ, card_name) if card_name else ''))
    card_stage = _schedule_stage_of_name(card_name or _schedule_name_from_key(card_key))
    rec = sched.get('record') if isinstance(sched.get('record'), dict) else {}
    sched_key = str(sched.get('marketKey') or rec.get('_ledgerKey') or '').strip()
    sched_name = _schedule_exact_norm(sched.get('marketName') or rec.get('_marketName') or _schedule_name_from_key(sched_key) or '')
    sched_stage = _schedule_stage_of_name(sched_name or _schedule_name_from_key(sched_key))

    if sched_key:
        if _schedule_exact_norm(sched_key) == card_key:
            return True
        if card_stage or sched_stage:
            if not card_stage or not sched_stage or card_stage != sched_stage:
                return False
            if _schedule_base_of_name(sched_name or _schedule_name_from_key(sched_key)) != _schedule_base_of_name(card_name):
                return False

    if sched_name and card_name:
        if sched_name == card_name:
            return True
        if card_stage or sched_stage:
            if not card_stage or not sched_stage or card_stage != sched_stage:
                return False
            if _schedule_base_of_name(sched_name) != _schedule_base_of_name(card_name):
                return False

    try:
        return int(sched.get('index')) == int(idx)
    except Exception:
        return False

def _ledger_arrays_for_state(state_obj, typ=None):
    try:
        arrs = _market_arrays_from_registry((state_obj or {}).get('marketRegistry', _default_market_registry()), purpose='schedule')
        markets = arrs[0] if isinstance(arrs, tuple) else arrs.get('markets', [])
        bases = arrs[1] if isinstance(arrs, tuple) else arrs.get('baseMarkets', [])
    except Exception:
        markets, bases = MARKETS, BASE_MARKETS
    return bases if typ == 'jodi' else markets

def _market_key_for_schedule(state_obj, typ, idx):
    try:
        idx_i = int(idx)
    except Exception:
        return ''
    arr = _ledger_arrays_for_state(state_obj, typ)
    if 0 <= idx_i < len(arr):
        return _ledger_market_key(typ, arr[idx_i].get('n') if isinstance(arr[idx_i], dict) else '')
    return ''

def _market_name_for_schedule(typ, idx=None, state_obj=None, market_key=None, rec=None):
    # Prefer stable marketKey / record annotation. Index is only a legacy fallback.
    key = str(market_key or (rec.get('_ledgerKey') if isinstance(rec, dict) else '') or '').strip()
    arr = _ledger_arrays_for_state(state_obj, typ)
    if key:
        for m in arr:
            name = m.get('n') if isinstance(m, dict) else ''
            if _ledger_market_key(typ, name) == key:
                return name
        if '|' in key:
            return key.split('|', 1)[1].strip().upper()
    try:
        idx_i = int(idx)
    except Exception:
        return ''
    return arr[idx_i].get('n') if 0 <= idx_i < len(arr) and isinstance(arr[idx_i], dict) else ''

def _ledger_schedule_key(profile_id, typ, idx=None, market_key=None):
    key = str(market_key or '').strip()
    if key:
        return f"{profile_id}|{typ}|{key}"
    try:
        idx = int(idx)
    except Exception:
        idx = str(idx)
    return f"{profile_id}|{typ}|{idx}"

def _ledger_schedule_key_candidates(profile_id, typ, idx=None, market_key=None):
    keys = []
    if market_key:
        keys.append(_ledger_schedule_key(profile_id, typ, idx, market_key))
    if idx is not None:
        legacy = _ledger_schedule_key(profile_id, typ, idx, None)
        if legacy not in keys:
            keys.append(legacy)
    return keys


def _ledger_schedule_obsolete_keys(state_obj, profile_id, typ, idx=None, market_key=None):
    """Find old numeric/duplicate schedule keys for the same card.

    A stale legacy key such as admin1|ank|5 can keep the old time (02:30) alive
    after the new marketKey key has been saved as 03:00. Delete these duplicates
    whenever /api/schedule_targets commits a schedule edit.
    """
    out = set(_ledger_schedule_key_candidates(profile_id, typ, idx, None))
    canonical = _ledger_schedule_key(profile_id, typ, idx, market_key) if market_key else ''
    if canonical in out:
        out.remove(canonical)
    store = state_obj.get('ledgerSchedules', {}) if isinstance(state_obj, dict) and isinstance(state_obj.get('ledgerSchedules'), dict) else {}
    prefix = f"{profile_id}|{typ}|"
    mk = str(market_key or '').strip()
    idx_s = str(int(idx)) if str(idx).isdigit() else str(idx)
    for sk, item in list(store.items()):
        if not str(sk).startswith(prefix) or sk == canonical:
            continue
        same = False
        if isinstance(item, dict):
            item_mk = str(item.get('marketKey') or (item.get('record', {}) if isinstance(item.get('record'), dict) else {}).get('_ledgerKey') or '').strip()
            item_idx = str(item.get('index') if item.get('index') is not None else '').strip()
            if mk and item_mk == mk:
                same = True
            elif item_idx and item_idx == idx_s and not item_mk:
                same = True
        tail = str(sk)[len(prefix):]
        if tail == idx_s:
            same = True
        if same:
            out.add(sk)
    return sorted(k for k in out if k and k != canonical)

def _ledger_schedule_store(state_obj):
    if not isinstance(state_obj, dict):
        return {}
    store = state_obj.setdefault('ledgerSchedules', {})
    if not isinstance(store, dict):
        state_obj['ledgerSchedules'] = {}
        store = state_obj['ledgerSchedules']
    return store

def _snapshot_schedule_record(rec):
    """Return only stable identity metadata for a daily schedule.

    Daily repeat must preserve only time + targets. Ledger payload such as
    digits/rate/status/trick is date-specific and must not be copied into
    tomorrow's fresh ledger or restored after a manual clear/reset.
    """
    if not isinstance(rec, dict):
        return {}
    out = {}
    for k in ('_ledgerKey', '_marketName', '_ledgerType', '_ledgerIndex'):
        if k in rec:
            out[k] = rec.get(k)
    return out

def _legacy_schedule_for_card(profile, typ, idx, today):
    """Read old per-date schedule data so existing users keep their schedules after update."""
    if not isinstance(profile, dict):
        return {}
    day_records = profile.get('dayRecords', {}) if isinstance(profile.get('dayRecords', {}), dict) else {}
    dict_name = _schedule_dict_name(typ)
    idx_s = str(idx)
    for date_key in sorted([str(k) for k in day_records.keys() if str(k) <= str(today)], reverse=True):
        day = day_records.get(date_key, {}) or {}
        data_map = day.get(dict_name, {}) or {}
        rec = data_map.get(idx_s)
        if rec is None and idx_s.isdigit():
            rec = data_map.get(int(idx_s))
        if not isinstance(rec, dict):
            continue
        sch_time = _normalize_schedule_time(rec.get('schTime') or rec.get('scheduleTime') or '')
        targets = _normalize_forward_targets(rec.get('schTargets') or rec.get('targets') or [])
        if sch_time or targets:
            return {
                'profileId': '',
                'type': typ,
                'index': int(idx_s) if idx_s.isdigit() else idx_s,
                'time': sch_time,
                'targets': targets,
                'record': _snapshot_schedule_record(rec),
                'sourceDate': date_key,
                'legacy': True
            }
    return {}

def _upsert_ledger_schedule(state_obj, profile_id, typ, idx, sch_time, targets, record=None, market_key=None):
    store = _ledger_schedule_store(state_obj)
    record = record or {}
    stable_key = market_key or (record.get('_ledgerKey') if isinstance(record, dict) else '') or _market_key_for_schedule(state_obj, typ, idx)
    key = _ledger_schedule_key(profile_id, typ, idx, stable_key)
    legacy_keys = _ledger_schedule_key_candidates(profile_id, typ, idx, None)
    clean_targets = _normalize_forward_targets(targets)
    sch_time = _normalize_schedule_time(sch_time)
    record_snapshot = _snapshot_schedule_record(record or {})
    if not sch_time and not clean_targets:
        store.pop(key, None)
        for lk in legacy_keys:
            if lk != key:
                store.pop(lk, None)
        return None
    current = store.get(key, {}) if isinstance(store.get(key), dict) else {}
    if not current:
        for lk in legacy_keys:
            if isinstance(store.get(lk), dict):
                current = store.get(lk)
                break
    market_name = (record.get('_marketName') if isinstance(record, dict) else '') or current.get('marketName', '') or _market_name_for_schedule(typ, idx, state_obj, stable_key, record)
    item = {
        **current,
        'profileId': profile_id,
        'type': typ,
        'index': int(idx) if str(idx).isdigit() else idx,
        'marketKey': stable_key or current.get('marketKey', ''),
        'marketName': market_name,
        'time': sch_time,
        'targets': clean_targets,
        'record': record_snapshot or current.get('record', {}),
        'repeat': 'daily',
        'enabled': bool(sch_time and clean_targets),
        'updatedAt': _now_iso_local(),
        'keyVersion': 'marketKey-v2'
    }
    store[key] = item
    for lk in legacy_keys:
        if lk != key:
            store.pop(lk, None)
    return item

def _collect_bot_schedule(state_obj=None):
    state_obj = state_obj or migrate_and_get_state()
    today = _safe_today()
    result = []
    profiles = state_obj.get("profiles", {}) if isinstance(state_obj, dict) else {}
    store = _ledger_schedule_store(state_obj)
    maps = [("ank", "data"), ("jodi", "jodiData"), ("pannel", "pannelData")]

    def store_items_for(profile_id, typ):
        prefix = f"{profile_id}|{typ}|"
        out = []
        for sk, item in list(store.items()):
            if not str(sk).startswith(prefix) or not isinstance(item, dict):
                continue
            mk = item.get('marketKey') or (str(sk).split('|', 2)[2] if len(str(sk).split('|', 2)) > 2 else '')
            idx = item.get('index')
            out.append((mk, idx, item))
        return out

    def record_by_market_key(data_map, market_key, idx=None):
        if not isinstance(data_map, dict):
            return {}
        if market_key:
            for _, val in data_map.items():
                if isinstance(val, dict) and str(val.get('_ledgerKey') or '') == str(market_key):
                    return val
        if idx is not None:
            rec = data_map.get(str(idx))
            if rec is None:
                try:
                    rec = data_map.get(int(idx))
                except Exception:
                    rec = None
            if isinstance(rec, dict):
                return rec
        return {}

    for profile_id, profile in profiles.items():
        day_records = profile.get("dayRecords", {}) if isinstance(profile, dict) else {}
        today_rec = day_records.get(today, {}) or {}
        for typ, key in maps:
            data_map = today_rec.get(key, {}) or {}
            candidates = []
            seen = set()
            # 1) Persistent schedule store is source-of-truth, preferably marketKey-based.
            for mk, idx, item in store_items_for(profile_id, typ):
                stable_mk = mk or _market_key_for_schedule(state_obj, typ, idx)
                ident = stable_mk or str(idx)
                if ident in seen:
                    continue
                seen.add(ident)
                candidates.append((stable_mk, idx, item))
            # 2) Today's records with schedule fields also remain valid.
            if isinstance(data_map, dict):
                for idx, rec in data_map.items():
                    if not isinstance(rec, dict):
                        continue
                    if not (rec.get('schTime') or rec.get('scheduleTime') or rec.get('schTargets') or rec.get('targets')):
                        continue
                    mk = rec.get('_ledgerKey') or _market_key_for_schedule(state_obj, typ, idx)
                    ident = mk or str(idx)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    candidates.append((mk, idx, {}))
            # 3) Legacy old dayRecords fallback for users upgraded from index schedule.
            for old_date, old_day in day_records.items():
                if str(old_date) > str(today) or not isinstance(old_day, dict):
                    continue
                old_map = old_day.get(key, {}) or {}
                if not isinstance(old_map, dict):
                    continue
                for old_idx, old_rec in old_map.items():
                    if not isinstance(old_rec, dict) or not (old_rec.get('schTime') or old_rec.get('scheduleTime') or old_rec.get('schTargets') or old_rec.get('targets')):
                        continue
                    mk = old_rec.get('_ledgerKey') or _market_key_for_schedule(state_obj, typ, old_idx)
                    ident = mk or str(old_idx)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    candidates.append((mk, old_idx, _legacy_schedule_for_card(profile, typ, old_idx, today)))

            # Sort by current registry time order when possible.
            arr = _ledger_arrays_for_state(state_obj, typ)
            order = {_ledger_market_key(typ, m.get('n') if isinstance(m, dict) else ''): i for i, m in enumerate(arr)}
            candidates.sort(key=lambda x: order.get(str(x[0] or ''), int(x[1]) if str(x[1]).isdigit() else 9999))

            for market_key, idx, sched in candidates:
                rec = record_by_market_key(data_map, market_key, idx)
                if not isinstance(sched, dict) or not sched:
                    # Try persistent schedule by both new marketKey and legacy index keys.
                    for sk in _ledger_schedule_key_candidates(profile_id, typ, idx, market_key):
                        if isinstance(store.get(sk), dict):
                            sched = store.get(sk)
                            break
                if not isinstance(sched, dict) or not sched:
                    sched = _legacy_schedule_for_card(profile, typ, idx, today)
                if not isinstance(rec, dict):
                    rec = {}
                # INTEL_SCHEDULE_TIME_FIX v17.3: persistent ledgerSchedules is
                # source-of-truth for daily Intel schedule time/targets; today's
                # card may contain stale schTime from an old full save.
                sch_time = _normalize_schedule_time(sched.get("time") or rec.get("schTime") or rec.get("scheduleTime") or "")
                targets = _normalize_forward_targets(sched.get("targets") or rec.get("schTargets") or rec.get("targets") or [])
                # DATEWISE_LEDGER_FIX: schedule store repeats only time/targets.
                # Digits/rate/status are today's work only, so Gateway must send only
                # when today's visible card has fresh digits/rate. Never fall back to
                # persistent schedule.record, otherwise yesterday's digits repeat.
                payload_rec = rec if isinstance(rec, dict) else {}
                digits = _digits_display(payload_rec.get("d", ""))
                rate = _ledger_schedule_rate(payload_rec)
                if not sch_time or not targets or not digits or not (rate > 0):
                    continue
                market_name = _market_name_for_schedule(typ, idx, state_obj, market_key or sched.get('marketKey'), rec or payload_rec)
                if not market_name:
                    continue
                # v33: exact card/stage guard. If OPEN is scheduled, CLOSE must not be returned.
                if not _schedule_record_matches_exact_card(sched, typ, idx, market_key or sched.get('marketKey') or '', market_name):
                    continue
                result.append({
                    "id": f"{profile_id}_{today}_{typ}_{market_key or idx}",
                    "profileId": profile_id,
                    "date": today,
                    "type": typ,
                    "index": int(idx) if str(idx).isdigit() else idx,
                    "marketKey": market_key or sched.get('marketKey') or '',
                    "time": sch_time,
                    "market": market_name,
                    "digits": digits,
                    "rate": rate,
                    "total": len(_ledger_digits_list(digits)) * rate,
                    "targets": targets,
                    "repeat": "daily",
                    "sourceDate": sched.get("sourceDate", today) if isinstance(sched, dict) else today,
                    "message": _format_ledger_intel_message(today, market_name, digits, rate, typ)
                })
    return result

@app.route('/api/bot_schedule')
def api_bot_schedule():
    try:
        return jsonify({"status": "success", "date": _safe_today(), "calendarDate": _calendar_today(), "timezone": APP_TZ, "businessDayCutoffHour": BUSINESS_DAY_CUTOFF_HOUR, "schedules": _collect_bot_schedule()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "schedules": []}), 500


@app.route('/api/ledger_schedule_exact_card_status')
def api_ledger_schedule_exact_card_status():
    return jsonify({
        'status': 'success',
        'ledgerScheduleExactCardFix': True,
        'version': 'v33',
        'rule': 'Only exact scheduled ledger card/stage is returned; OPEN and CLOSE schedules are isolated.'
    })

@app.route('/api/ledger_card_color_status')
def api_ledger_card_color_status():
    return jsonify({
        'status': 'success',
        'ledgerCardColorFix': True,
        'version': LEDGER_CARD_COLOR_VERSION,
        'mode': 'deterministic_unique_color_per_ledger_card',
        'rule': 'Every ledger card receives a stable full-card background color from its type + market key; new markets automatically get a different color.',
        'fullCardColor': True
    })

@app.route('/api/business_day_cutoff_status')
def api_business_day_cutoff_status():
    now = _business_now()
    return jsonify({
        "status":"success",
        "businessDayCutoffFix": True,
        "version":"v31-business-day-cutoff",
        "timezone": APP_TZ,
        "cutoffHour": BUSINESS_DAY_CUTOFF_HOUR,
        "businessDate": _safe_today(),
        "calendarDate": _calendar_today(),
        "localTime": now.strftime('%H:%M'),
        "rule": f"00:00-{BUSINESS_DAY_CUTOFF_HOUR-1:02d}:59 previous business day; {BUSINESS_DAY_CUTOFF_HOUR:02d}:00 fresh next day"
    })

@app.route('/bot_schedule')
def bot_schedule_alias():
    return api_bot_schedule()


@app.route('/api/ledger_schedule_health')
def api_ledger_schedule_health():
    """Runtime check for daily-repeat ledger schedules."""
    try:
        state_obj = migrate_and_get_state()
        _ensure_foundation_state(state_obj)
        store = state_obj.get('ledgerSchedules', {}) if isinstance(state_obj.get('ledgerSchedules'), dict) else {}
        schedules = _collect_bot_schedule(state_obj)
        active_store = [v for v in store.values() if isinstance(v, dict) and v.get('enabled')]
        return jsonify({
            'status': 'success',
            'date': _safe_today(),
            'timezone': APP_TZ,
            'dailyRepeatProtected': True,
            'scheduleRuntimePreserveGuard': True,
            'ledgerSchedulesCount': len(store),
            'enabledSchedulesCount': len(active_store),
            'dueSchedulePreviewCount': len(schedules),
            'schedules': schedules[:50]
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'dailyRepeatProtected': False, 'schedules': []}), 500

@app.route('/api/schedule_targets', methods=['POST'])
def api_schedule_targets():
    """Save Intel ledger schedule time/targets without full-card overwrite.

    v17.4 fix: schedule save must not fail because a full today's card record contains
    stale/invalid/heavy fields. The persistent ledgerSchedules item is the source of
    truth, so we write that first. Today's visible card receives only a minimal
    schedule-field patch as best-effort. Duplicate/legacy key cleanup is also
    best-effort so old bad keys cannot break a new time save.
    """
    warnings = []
    try:
        data = request.get_json(silent=True) or {}
        profile_id = str(data.get('profileId') or 'admin1')
        typ = str(data.get('type') or '').strip()
        raw_idx = data.get('index')
        idx = str(raw_idx if raw_idx is not None else '')
        market_key = str(data.get('marketKey') or '').strip()
        sch_time = _normalize_schedule_time(data.get('time') or '')
        targets = _normalize_forward_targets(data.get('targets') or [])
        dict_name = _schedule_dict_name(typ)
        if dict_name not in ('data', 'jodiData', 'pannelData'):
            return jsonify({'status': 'error', 'message': 'invalid schedule type', 'scheduleSave500Fix': True}), 400
        if not idx:
            return jsonify({'status': 'error', 'message': 'invalid schedule index', 'scheduleSave500Fix': True}), 400

        state_obj = migrate_and_get_state()
        _ensure_foundation_state(state_obj)
        profiles = state_obj.setdefault('profiles', {})
        if profile_id not in profiles:
            return jsonify({'status': 'error', 'message': 'profile not found', 'profileId': profile_id, 'scheduleSave500Fix': True}), 404

        prof = profiles[profile_id]
        today = _safe_today()
        prof.setdefault('dayRecords', {}).setdefault(today, {})
        prof['dayRecords'][today].setdefault(dict_name, {})
        data_map = prof['dayRecords'][today][dict_name]
        if not isinstance(data_map, dict):
            prof['dayRecords'][today][dict_name] = {}
            data_map = prof['dayRecords'][today][dict_name]

        # Locate visible card by stable marketKey first; index is legacy fallback.
        rec_key = None
        if market_key:
            for k, v in data_map.items():
                if isinstance(v, dict) and str(v.get('_ledgerKey') or '') == market_key:
                    rec_key = k
                    break
        if rec_key is None:
            rec_key = idx
        data_map.setdefault(rec_key, {'s':'WAIT','d':'','r':''})
        rec = data_map.get(rec_key)
        if not isinstance(rec, dict):
            rec = {'s':'WAIT','d':'','r':''}
            data_map[rec_key] = rec

        incoming_rec = data.get('record') or {}
        if isinstance(incoming_rec, dict):
            # Keep only normal JSON-safe keys in memory. Schedule persistence below uses
            # a minimal snapshot, not this whole record.
            for k, v in incoming_rec.items():
                if k not in ('__proto__', 'constructor', 'prototype'):
                    rec[k] = v

        schedule_stamp = _now_iso_local()
        stable_key = market_key or rec.get('_ledgerKey') or _market_key_for_schedule(state_obj, typ, idx)
        rec['_ledgerKey'] = stable_key
        if not rec.get('_marketName'):
            rec['_marketName'] = _market_name_for_schedule(typ, idx, state_obj, stable_key, rec)
        rec['schTime'] = sch_time
        rec['schTargets'] = targets
        rec['_updatedAt'] = schedule_stamp
        rec['_dirtyAt'] = schedule_stamp
        rec['_sourceAction'] = 'schedule_time'
        rec['_scheduleUpdatedAt'] = schedule_stamp

        persistent = _upsert_ledger_schedule(state_obj, profile_id, typ, idx, sch_time, targets, rec, stable_key)
        sched_key = _ledger_schedule_key(profile_id, typ, idx, stable_key)

        # Critical commit: persistent daily schedule source-of-truth.
        # v17.5: verify-read after write so UI cannot show a false "time set"
        # notification while Firebase still contains the previous schedule time.
        try:
            if persistent is None:
                _firebase_delete_child(['ledgerSchedules', sched_key])
                saved_persistent = None
            else:
                _firebase_put_child(['ledgerSchedules', sched_key], persistent)
                saved_persistent = _firebase_get_child(['ledgerSchedules', sched_key])
                saved_time = _normalize_schedule_time((saved_persistent or {}).get('time') if isinstance(saved_persistent, dict) else '')
                if saved_time != sch_time:
                    raise RuntimeError(f"schedule verify mismatch: requested {sch_time or 'blank'} saved {saved_time or 'blank'}")
        except Exception as e:
            _obs_exception('schedule_source_commit_failed', e, {'profileId': profile_id, 'type': typ, 'index': idx, 'marketKey': stable_key, 'time': sch_time})
            return jsonify({'status': 'error', 'message': 'Schedule source save failed: ' + str(e), 'scheduleSave500Fix': True, 'schedulePersistenceFix': True, 'phase': 'ledgerSchedules'}), 500

        # Best-effort: update only schedule fields on today's card. Do NOT PUT full rec.
        card_patch = {
            'schTime': sch_time,
            'schTargets': targets,
            '_ledgerKey': stable_key,
            '_marketName': rec.get('_marketName') or '',
            '_updatedAt': schedule_stamp,
            '_dirtyAt': schedule_stamp,
            '_sourceAction': 'schedule_time',
            '_scheduleUpdatedAt': schedule_stamp,
        }
        try:
            _firebase_patch_child(['profiles', str(profile_id), 'dayRecords', str(today), dict_name, str(rec_key)], card_patch)
        except Exception as e:
            warnings.append('today_card_patch_failed:' + str(e)[:160])
            _obs_exception('schedule_today_card_patch_warning', e, {'profileId': profile_id, 'type': typ, 'index': idx, 'marketKey': stable_key, 'time': sch_time})

        # Best-effort: remove stale legacy/duplicate keys. Failure here must not fail save.
        try:
            obsolete_keys = _ledger_schedule_obsolete_keys(state_obj, profile_id, typ, idx, stable_key)
            for lk in obsolete_keys:
                if lk != sched_key:
                    try:
                        _firebase_delete_child(['ledgerSchedules', lk])
                    except Exception as del_err:
                        warnings.append('obsolete_delete_failed:' + str(lk)[:60])
                        _obs_exception('schedule_obsolete_key_delete_warning', del_err, {'key': lk})
        except Exception as e:
            warnings.append('obsolete_key_scan_failed:' + str(e)[:160])
            _obs_exception('schedule_obsolete_scan_warning', e, {'profileId': profile_id, 'type': typ, 'index': idx})

        try:
            _firebase_put_child(['ledgerScheduleLiveCommit'], {'lastCommitAt': _now_iso_local(), 'profileId': profile_id, 'type': typ, 'index': idx, 'marketKey': stable_key, 'time': sch_time, 'mode': 'minimal-source-first-v17.4'})
        except Exception as e:
            warnings.append('live_commit_marker_failed:' + str(e)[:160])
            _obs_exception('schedule_live_commit_marker_warning', e, {'profileId': profile_id, 'type': typ, 'index': idx})

        try:
            _add_audit(state_obj, 'ledger_schedule_saved', {'profileId': profile_id, 'type': typ, 'index': idx, 'marketKey': stable_key, 'time': sch_time, 'targets': targets, 'repeat': 'daily', 'mode': 'minimal-source-first-v17.4'})
        except Exception:
            pass

        return jsonify({'status': 'success', 'schedule': persistent, 'verifiedSchedule': saved_persistent if persistent is not None else None, 'atomicFirebaseCommit': True, 'intelScheduleTimeFix': True, 'scheduleSave500Fix': True, 'schedulePersistenceFix': True, 'warnings': warnings})
    except Exception as e:
        _obs_exception('schedule_targets_unhandled_500_fixed', e, {})
        return jsonify({'status': 'error', 'message': 'Schedule save internal error: ' + str(e), 'scheduleSave500Fix': True, 'phase': 'unhandled'}), 500

@app.route('/api/schedule_save_fix_status')
def api_schedule_save_fix_status():
    return jsonify({'status':'success','scheduleSave500Fix':True,'version':'v17.5','mode':'ledgerSchedules-source-first-minimal-card-patch','nonCriticalCleanup':'best-effort','schedulePersistenceFix':True})

@app.route('/api/schedule_persistence_fix_status')
def api_schedule_persistence_fix_status():
    return jsonify({'status':'success','schedulePersistenceFix':True,'version':'v17.5','mode':'frontend-no-stale-merge-plus-firebase-verify-read','sourceOfTruth':'ledgerSchedules.time'})

@app.route('/api/intel_schedule_time_fix_status')
def api_intel_schedule_time_fix_status():
    try:
        state_obj = migrate_and_get_state()
        store = state_obj.get('ledgerSchedules', {}) if isinstance(state_obj.get('ledgerSchedules'), dict) else {}
        duplicates = []
        seen = {}
        for sk, item in store.items():
            if not isinstance(item, dict):
                continue
            pid = item.get('profileId') or str(sk).split('|')[0]
            typ = item.get('type') or (str(sk).split('|')[1] if '|' in str(sk) else '')
            ident = item.get('marketKey') or (item.get('record', {}) if isinstance(item.get('record'), dict) else {}).get('_ledgerKey') or str(item.get('index') or '')
            group = f"{pid}|{typ}|{ident}"
            if group in seen:
                duplicates.append({'group': group, 'keys': [seen[group], sk]})
            else:
                seen[group] = sk
        return jsonify({'status':'success','intelScheduleTimeFix':True,'version':'v17.3','ledgerSchedulesCount':len(store),'duplicatePreview':duplicates[:20], 'sourceOfTruth':'ledgerSchedules.time'})
    except Exception as e:
        return jsonify({'status':'error','intelScheduleTimeFix':True,'message':str(e)}), 500

@app.route('/api/wa_targets')
def api_wa_targets():
    # Proxy to local Baileys Gateway if running. App still works if gateway is off.
    try:
        res = _gateway_request('GET', '/targets?force=1', timeout=6)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({'status': 'offline', 'contacts': [], 'groups': [], 'message': str(e)})


@app.route('/api/wa_login_status')
def api_wa_login_status():
    try:
        res = _gateway_request('GET', '/wa_login_status', timeout=5)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'connected': False, 'qrAvailable': False, 'message': str(e)}), 503

@app.route('/api/wa_reset_session', methods=['POST'])
def api_wa_reset_session():
    try:
        res = _gateway_request('POST', '/wa_reset_session', timeout=10)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'message': str(e)}), 503

@app.route('/api/wa_qr_image')
def api_wa_qr_image():
    try:
        import urllib.parse
        res = _gateway_request('GET', '/wa_login_status', timeout=5)
        data = res.json()
        qr = str(data.get('qr') or '')
        if not qr:
            return app.response_class('QR not available yet. Refresh or reset WhatsApp session.', mimetype='text/plain'), 404
        url = 'https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=' + urllib.parse.quote(qr)
        return app.redirect(url)
    except Exception as e:
        return app.response_class('QR error: ' + str(e), mimetype='text/plain'), 503

@app.route('/api/gateway_status')
def api_gateway_status():
    try:
        res = _gateway_request('GET', '/status', timeout=5)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({'status': 'offline', 'connected': False, 'message': str(e), 'timezone': APP_TZ})

@app.route('/api/gateway_durability_status')
def api_gateway_durability_status():
    try:
        res = _gateway_request('GET', '/gateway_durability_status', timeout=5)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'version': '2026-07-02-gateway-durability-v10', 'firebaseLocks': False, 'message': str(e)}), 503

@app.route('/api/smart_command_status')
def api_smart_command_status():
    try:
        res = _gateway_request('GET', '/smart_command_status', timeout=5)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'version': SMART_COMMAND_VERSION, 'enabled': False, 'message': str(e)}), 503

@app.route('/api/whatsapp_compliance_status')
def api_whatsapp_compliance_status():
    try:
        res = _gateway_request('GET', '/whatsapp_compliance_status', timeout=5)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'complianceGuardV18': True, 'enabled': False, 'message': str(e)}), 503

@app.route('/api/gateway_scrape_results')
def api_gateway_scrape_results():
    # Manual trigger for Gateway auto-result scraper. Gateway still scrapes automatically on interval.
    try:
        res = _gateway_request('GET', '/scrape_results', timeout=30)
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'offline', 'message': str(e), 'updates': [], 'scraped': []}), 503

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="theme-color" content="#2AABEE">

    <link rel="manifest" href="{{ manifest_url }}">
    <link rel="apple-touch-icon" href="/icon.svg">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Titan Nova">
    <meta name="mobile-web-app-capable" content="yes">

    <title>TITAN NOVA</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.tailwindcss.com"></script>

    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        :root {
            --app-bg:       #17212B;
            --surface:      #232E3C;
            --surface-light:#2B3A4D;
            --surface-mid:  #374F65;
            --primary:      #2AABEE;
            --primary-glow: rgba(42,171,238,0.20);
            --primary-dark: #1A8FC4;
            --green:        #00C26F;
            --green-dark:   #00A05E;
            --green-glow:   rgba(0,194,111,0.18);
            --cyan:         #2AABEE;
            --cyan-glow:    rgba(42,171,238,0.18);
            --rose:         #FF5D5D;
            --rose-glow:    rgba(255,93,93,0.18);
            --purple:       #7B8FFF;
            --purple-glow:  rgba(123,143,255,0.18);
            --amber:        #FAC748;
            --text-main:    #FFFFFF;
            --text-muted:   #7A9CB8;
            --border:       rgba(255,255,255,0.07);
            --radius-lg:    16px;
            --radius-md:    12px;
            --radius-sm:    8px;
            --header-h:     56px;
        }

        * { box-sizing: border-box; }
        body {
            background: var(--app-bg);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            -webkit-tap-highlight-color: transparent;
            -webkit-user-select: none; user-select: none;
            overscroll-behavior-y: auto;
            -webkit-overflow-scrolling: touch;
            touch-action: pan-y;
            overflow-x: hidden;
            overflow-y: auto;
            min-height: 100dvh;
            padding-bottom: 88px;
        }
        input, textarea { -webkit-user-select: auto; user-select: auto; }
        .no-scrollbar::-webkit-scrollbar { display: none; }

        /* ── CARDS ── */
        .native-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            margin-bottom: 8px;
            overflow: hidden;
            transition: transform 0.1s ease;
        }

        /* ── INPUTS ── */
        .native-input {
            background: var(--surface-light);
            border: 1.5px solid var(--surface-mid);
            color: var(--text-main);
            border-radius: var(--radius-md);
            text-align: center;
            font-weight: 700;
            padding: 13px 12px;
            outline: none;
            width: 100%;
            font-size: 16px;
            transition: 0.2s;
            font-family: inherit;
        }
        .native-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-glow); }
        .native-input::placeholder { color: var(--text-muted); font-weight: 500; }

        /* ── STATS HUD ── */
        .wallet-hud {
            display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;
            padding: 12px 14px;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }
        .stat-box {
            background: var(--surface-light);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
            border: 1px solid var(--border);
        }

        /* ── APP BAR ── */
        .app-bar {
            position: sticky; top: 0; z-index: 50;
            background: #1C2733;
            border-bottom: 1px solid rgba(42,171,238,0.15);
            height: var(--header-h);
            padding: 0 12px;
            display: flex; align-items: center; justify-content: space-between;
        }

        /* ── BOTTOM NAV — scrollable native tab rail ── */
        .bottom-nav {
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: #1C2733;
            border-top: 1px solid rgba(255,255,255,0.06);
            display: flex; justify-content: flex-start; align-items: stretch;
            gap: 4px;
            padding: 6px 8px env(safe-area-inset-bottom, 8px);
            z-index: 100; height: 76px;
            overflow-x: auto; overflow-y: hidden;
            scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
            scroll-snap-type: x proximity;
        }
        .bottom-nav::-webkit-scrollbar { display: none; }
        .nav-item {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            color: var(--text-muted); font-size: 8.5px; font-weight: 700;
            text-transform: uppercase; padding: 4px 8px; border-radius: 10px;
            transition: 0.2s; min-width: 62px; flex: 0 0 62px; letter-spacing: 0.02em;
            position: relative; scroll-snap-align: center;
            white-space: nowrap;
        }
        .nav-item i { font-size: 18px; margin-bottom: 3px; transition: 0.2s; }
        @media (max-width: 380px) {
            .nav-item { min-width: 58px; flex-basis: 58px; font-size: 8px; padding-left: 6px; padding-right: 6px; }
            .nav-item i { font-size: 17px; }
        }
        .nav-item.active { color: var(--primary); }
        .nav-item.active i { filter: drop-shadow(0 0 6px rgba(42,171,238,0.5)); }
        .nav-item.active::after {
            content: '';
            position: absolute;
            top: 0; left: 50%; transform: translateX(-50%);
            width: 32px; height: 3px;
            background: var(--primary);
            border-radius: 0 0 4px 4px;
        }

        /* ── PILL TABS ── */
        .pill-tabs {
            display: flex; background: var(--surface); padding: 4px 14px; gap: 6px;
            border-bottom: 1px solid var(--border);
            overflow-x: auto; scrollbar-width: none;
        }
        .pill-tab {
            flex: 1; text-align: center; padding: 8px 0; font-size: 11px;
            font-weight: 700; text-transform: uppercase; color: var(--text-muted);
            border-radius: 8px; transition: 0.2s; white-space: nowrap;
            border-bottom: 2px solid transparent;
        }
        .pill-tab.active { color: var(--primary); border-bottom-color: var(--primary); background: rgba(42,171,238,0.08); }
        .pill-btn {
            background: var(--surface-light); border: 1px solid var(--surface-mid);
            color: var(--text-muted); border-radius: 20px; padding: 7px 18px;
            font-size: 11px; font-weight: 700; text-transform: uppercase; transition: 0.2s;
            font-family: inherit;
        }
        .pill-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); box-shadow: 0 4px 12px var(--primary-glow); }

        /* ── PAY PLAN CARDS ── */
        .plan-card-wrap { border-radius: var(--radius-lg); padding: 1.5px; }
        .plan-card-inner { background: var(--surface); border-radius: calc(var(--radius-lg) - 1.5px); padding: 16px; }
        .plan-card-wrap.selected { background: linear-gradient(135deg, var(--primary), var(--green)); }
        .plan-card-wrap:not(.selected) { background: var(--surface-light); }

        /* ── BOTTOM SHEET ── */
        .bottom-sheet {
            position: fixed; inset: 0; z-index: 9001;
            background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
            display: flex; flex-direction: column; justify-content: flex-end;
            opacity: 0; pointer-events: none; transition: opacity 0.25s ease;
        }
        .bottom-sheet.open { opacity: 1; pointer-events: auto; }
        .sheet-content {
            background: #1C2733;
            border-top-left-radius: 20px; border-top-right-radius: 20px;
            padding: 20px; padding-bottom: calc(20px + env(safe-area-inset-bottom, 0px));
            transform: translateY(100%); transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1);
            border-top: 1px solid rgba(42,171,238,0.2); max-height: 85vh; overflow-y: auto;
        }
        .bottom-sheet.open .sheet-content { transform: translateY(0); }
        .sheet-handle { width: 36px; height: 4px; background: rgba(255,255,255,0.15); border-radius: 10px; margin: 0 auto 18px auto; }

        /* ── TOGGLE SWITCH ── */
        .switch { position: relative; display: inline-block; width: 36px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--surface-mid); transition: .3s; border-radius: 20px; }
        .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: #fff; transition: .3s; border-radius: 50%; opacity: 0.5; }
        input:checked + .slider { background-color: var(--primary); }
        input:checked + .slider:before { opacity: 1; transform: translateX(16px); }

        /* ── SIDEBAR ── */
        #sidebar {
            position: fixed; top: 0; left: -300px; height: 100%; width: 280px;
            background: #1C2733; z-index: 1000;
            transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-right: 1px solid rgba(42,171,238,0.15); overflow-y: auto;
        }
        #sidebar.open { left: 0; box-shadow: 10px 0 40px rgba(0,0,0,0.7); }
        .sidebar-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 12px; }
        .side-link-btn {
            display: block; background: var(--surface-light); color: var(--text-muted);
            border: 1px solid var(--border); font-size: 9px; font-weight: 700;
            padding: 10px; border-radius: 10px; text-transform: uppercase; text-align: center;
            font-family: inherit;
        }

        /* ── TOAST — Telegram Style ── */
        .tg-toast {
            background: #2B3A4D;
            border: 1px solid rgba(42,171,238,0.25);
            border-radius: 14px;
            padding: 12px 14px;
            display: flex; align-items: center; gap: 10px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
            transform: translateY(-120%) scale(0.96);
            opacity: 0;
            transition: all 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.1);
            pointer-events: auto; cursor: pointer;
            min-width: 0;
        }
        .tg-toast.show { transform: translateY(0) scale(1); opacity: 1; }
        .tg-toast-icon {
            width: 36px; height: 36px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px; flex-shrink: 0;
        }
        .tg-toast-icon.info  { background: rgba(42,171,238,0.2);  color: #2AABEE; }
        .tg-toast-icon.success { background: rgba(0,194,111,0.2); color: #00C26F; }
        .tg-toast-icon.danger  { background: rgba(255,93,93,0.2);  color: #FF5D5D; }
        .tg-toast-body h4 { font-size: 13px; font-weight: 700; color: #fff; margin: 0 0 2px; line-height: 1.3; }
        .tg-toast-body p  { font-size: 11px; color: var(--text-muted); margin: 0; line-height: 1.4; }

        /* ── INSTALL MODAL ── */
        .install-modal {
            position: fixed; inset: 0; z-index: 9500;
            background: rgba(0,0,0,0.75); backdrop-filter: blur(6px);
            display: flex; align-items: flex-end;
            opacity: 0; pointer-events: none; transition: opacity 0.3s;
        }
        .install-modal.open { opacity: 1; pointer-events: auto; }
        .install-modal-content {
            background: #1C2733; width: 100%;
            border-top-left-radius: 20px; border-top-right-radius: 20px;
            padding: 24px; padding-bottom: calc(24px + env(safe-area-inset-bottom, 0px));
            border-top: 2px solid var(--primary);
            transform: translateY(100%); transition: transform 0.35s cubic-bezier(0.175, 0.885, 0.32, 1);
        }
        .install-modal.open .install-modal-content { transform: translateY(0); }

        /* ── SECTION HEADER ── */
        .sec-header {
            font-size: 11px; font-weight: 700; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 0.06em;
            padding: 14px 14px 8px; display: flex; justify-content: space-between; align-items: center;
        }

        /* ── SCROLLBAR FIX ── */
        .pill-tabs::-webkit-scrollbar { display: none; }

        /* ── STAT LABEL ── */
        .stat-lbl { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 4px; }
        .stat-val  { font-size: 15px; font-weight: 800; }

        /* ── GLOBAL RENDERING / RESPONSIVE FIX ── */
        html { width: 100%; min-height: 100%; margin: 0; overflow-x: hidden; overflow-y: auto; }
        body { width: 100%; min-height: 100dvh; margin: 0; overflow-x: hidden; overflow-y: auto; }
        #screen-content {
            width: 100%;
            max-width: 100%;
            min-height: calc(100dvh - var(--header-h));
            overflow-x: hidden;
            overflow-y: visible;
            padding-bottom: calc(120px + env(safe-area-inset-bottom, 0px));
        }
        button, input, select, textarea { max-width: 100%; min-width: 0; }
        img, video, canvas, svg { max-width: 100%; height: auto; }
        .native-card, .stat-box, .wallet-hud, .sheet-content, .tg-toast { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
        .native-input { min-width: 0; }
        .grid > *, .flex > * { min-width: 0; }
        .grid { max-width: 100%; }
        .bottom-nav { max-width: 100vw; }
        @media (max-width: 390px) {
            .stat-box { padding: 8px 9px; }
            .stat-val { font-size: 13px; }
            .native-card { border-radius: 14px; }
        }



        /* ── MARKET MANAGER MOBILE COMPACT ── */
        .market-manager-wrap { padding-left: 10px !important; padding-right: 10px !important; }
        .market-quick-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
        .market-card-compact { padding: 12px !important; border-radius: 16px; }
        .market-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
        .market-card-title { font-size: 12px; line-height: 1.15; }
        .market-card-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; min-width: 112px; }
        .market-card-actions button { padding: 8px 7px; border-radius: 11px; font-size: 8px; line-height: 1; }
        .market-field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-bottom: 8px; }
        .market-field-grid .native-input, .market-chart-row .native-input { padding: 9px 8px; font-size: 10px; border-radius: 11px; }
        .market-toggle-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; font-size: 8px; }
        .market-toggle-grid label { padding: 8px 7px; border-radius: 11px; gap: 6px; }
        .market-toggle-grid span { line-height: 1.1; }
        .market-toggle-grid input[type=checkbox] { width: 16px; height: 16px; flex: 0 0 auto; }
        .market-chart-row { display: grid; grid-template-columns: minmax(0, 1fr) 92px; gap: 7px; margin-top: 8px; }
        .market-route-box { margin-top: 8px; padding: 10px !important; border-radius: 14px; }
        .market-route-box p { line-height: 1.25; }
        @media (max-width: 390px) {
            .market-manager-wrap { padding-left: 8px !important; padding-right: 8px !important; }
            .market-card-compact { padding: 10px !important; margin-bottom: 7px; }
            .market-card-head { gap: 8px; margin-bottom: 8px; }
            .market-card-title { font-size: 11px; }
            .market-card-actions { min-width: 96px; gap: 5px; }
            .market-card-actions button { padding: 7px 5px; font-size: 7.5px; }
            .market-toggle-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; }
            .market-field-grid { gap: 6px; }
            .market-chart-row { grid-template-columns: minmax(0, 1fr) 78px; gap: 6px; }
        }


        /* ── LEDGER MOBILE COMPACT v43 ── */
        .ledger-compact { padding-left: 8px !important; padding-right: 8px !important; }
        .ledger-compact .native-card { margin-bottom: 6px; border-radius: 14px; }
        .ledger-card-head { padding: 8px 10px; min-height: 38px; }
        .ledger-card-body { padding: 10px; }
        .ledger-main-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(82px, .8fr); gap: 8px; margin-bottom: 8px; }
        .ledger-actions { display: grid; grid-template-columns: 1fr 1fr 46px; gap: 8px; margin-bottom: 8px; }
        .ledger-actions button { padding-top: 9px; padding-bottom: 9px; border-radius: 11px; box-shadow: none !important; }
        .ledger-more { border-top: 1px solid var(--border); padding-top: 8px; }
        .ledger-more > summary { list-style: none; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--text-muted); font-size: 9px; font-weight: 900; text-transform: uppercase; letter-spacing: .05em; }
        .ledger-more > summary::-webkit-details-marker { display: none; }
        .ledger-more > summary::after { content: 'More'; color: var(--primary); font-size: 9px; }
        .ledger-more[open] > summary::after { content: 'Hide'; color: var(--rose); }
        .ledger-more-body { margin-top: 8px; }
        .ledger-compact .native-input { padding: 10px 9px; font-size: 15px; border-radius: 11px; }
        .ledger-compact .stat-lbl { margin-bottom: 2px; }
        @media (max-width: 380px) {
            .ledger-main-grid { grid-template-columns: minmax(0, 1.35fr) minmax(76px, .75fr); gap: 6px; }
            .ledger-actions { grid-template-columns: 1fr 1fr 42px; gap: 6px; }
            .ledger-card-body { padding: 9px; }
        }


        /* ── v14 ADMIN MOBILE POLISH ── */
        .v14-admin-fab {
            position: fixed;
            right: 14px;
            bottom: calc(86px + env(safe-area-inset-bottom, 0px));
            z-index: 140;
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 48px;
            padding: 0 14px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--primary), #00C26F);
            color: #fff;
            font-size: 12px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: .03em;
            box-shadow: 0 12px 30px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.10) inset;
            text-decoration: none;
            touch-action: manipulation;
        }
        .v14-admin-fab i { font-size: 15px; }
        .v14-tap-safe { touch-action: manipulation; -webkit-tap-highlight-color: transparent; }
        @media (max-width: 390px) {
            .v14-admin-fab { right: 10px; bottom: calc(82px + env(safe-area-inset-bottom, 0px)); min-height: 44px; padding: 0 12px; font-size: 10px; }
        }
    </style>
</head>
<body>
    <!-- Toast Container -->
    <div id="push-container" class="fixed top-3 left-1/2 -translate-x-1/2 w-[92%] max-w-sm z-[9999] pointer-events-none flex flex-col gap-2"></div>

    <!-- PWA Install Banner — shows when Android prompt is available -->
    <div id="pwa-install-banner" class="fixed top-[calc(var(--header-h)+8px)] left-1/2 -translate-x-1/2 z-[100] hidden w-[92%] max-w-sm pointer-events-auto">
        <div class="flex items-center gap-3 bg-[#1A3348] border border-[var(--primary)] rounded-2xl px-4 py-3 shadow-lg shadow-[rgba(42,171,238,0.2)]">
            <div class="w-10 h-10 rounded-xl bg-[var(--primary)] flex items-center justify-center shrink-0">
                <i class="fas fa-mobile-alt text-white text-lg"></i>
            </div>
            <div class="flex-1 min-w-0">
                <p class="text-white font-bold text-[13px] leading-tight">App Install Karein</p>
                <p class="text-[var(--text-muted)] text-[10px]">Faster, offline-ready experience</p>
            </div>
            <button onclick="installPWA()" class="bg-[var(--primary)] text-white px-4 py-2 rounded-xl font-bold text-[11px] uppercase shrink-0 active:scale-95 transition-transform">
                Install
            </button>
            <button onclick="document.getElementById('pwa-install-banner').classList.add('hidden')" class="text-[var(--text-muted)] w-6 h-6 flex items-center justify-center shrink-0 text-xs">
                <i class="fas fa-times"></i>
            </button>
        </div>
    </div>

    <!-- Manual Install Guide Modal -->
    <div id="install-modal" class="install-modal" onclick="if(event.target===this)closeInstallModal()">
        <div class="install-modal-content">
            <div class="flex items-center gap-3 mb-5">
                <div class="w-12 h-12 rounded-2xl bg-[var(--primary)] flex items-center justify-center text-white text-xl">
                    <i class="fas fa-download"></i>
                </div>
                <div>
                    <h3 class="text-white font-black text-base">App Install Karein</h3>
                    <p class="text-[var(--text-muted)] text-[11px]">Android pe Home Screen add karein</p>
                </div>
            </div>

            <div id="auto-install-section" class="hidden mb-4">
                <button onclick="installPWA()" class="w-full bg-[var(--primary)] text-white py-4 rounded-2xl font-black text-[13px] uppercase tracking-wide active:scale-95 transition-transform shadow-lg shadow-[rgba(42,171,238,0.3)]">
                    <i class="fas fa-download mr-2"></i> Abhi Install Karein
                </button>
                <p class="text-[var(--text-muted)] text-[10px] text-center mt-2">Ya neeche manual steps follow karein</p>
            </div>

            <div class="space-y-3">
                <div class="flex items-start gap-3 bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                    <div class="w-7 h-7 rounded-full bg-[var(--primary)] text-white text-[11px] font-black flex items-center justify-center shrink-0 mt-0.5">1</div>
                    <div>
                        <p class="text-white font-bold text-[12px]">Chrome Browser Mein Kholo</p>
                        <p class="text-[var(--text-muted)] text-[10px] mt-0.5">Google Chrome mein yeh page open karo</p>
                    </div>
                </div>
                <div class="flex items-start gap-3 bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                    <div class="w-7 h-7 rounded-full bg-[var(--primary)] text-white text-[11px] font-black flex items-center justify-center shrink-0 mt-0.5">2</div>
                    <div>
                        <p class="text-white font-bold text-[12px]">3 Dots Menu Tap Karein</p>
                        <p class="text-[var(--text-muted)] text-[10px] mt-0.5">Browser ke top-right mein ⋮ icon</p>
                    </div>
                </div>
                <div class="flex items-start gap-3 bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                    <div class="w-7 h-7 rounded-full bg-[var(--primary)] text-white text-[11px] font-black flex items-center justify-center shrink-0 mt-0.5">3</div>
                    <div>
                        <p class="text-white font-bold text-[12px]">"Add to Home Screen" Choose Karein</p>
                        <p class="text-[var(--text-muted)] text-[10px] mt-0.5">Menu mein se yeh option select karo</p>
                    </div>
                </div>
                <div class="flex items-start gap-3 bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                    <div class="w-7 h-7 rounded-full bg-[var(--green)] text-white text-[11px] font-black flex items-center justify-center shrink-0 mt-0.5"><i class="fas fa-check text-[9px]"></i></div>
                    <div>
                        <p class="text-white font-bold text-[12px]">"Add" pe Tap Karein</p>
                        <p class="text-[var(--text-muted)] text-[10px] mt-0.5">App Home Screen par install ho jayega!</p>
                    </div>
                </div>
            </div>

            <button onclick="closeInstallModal()" class="mt-5 w-full py-4 rounded-2xl font-bold text-[13px] text-[var(--text-muted)] border border-[var(--border)] active:scale-95 transition-transform">
                Samajh Gaya, Close Karein
            </button>
        </div>
    </div>

    <div id="sidebar-overlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black/70 z-[999] hidden backdrop-blur-sm"></div>
    <div id="sidebar">
        <div class="p-5 border-b border-[rgba(42,171,238,0.15)]">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 rounded-xl bg-[var(--primary)] flex items-center justify-center text-white font-black text-lg">T</div>
                <div>
                    <h2 class="text-white font-black text-base">TITAN NOVA</h2>
                    <p class="text-[var(--text-muted)] text-[10px]">Charts & Live Database</p>
                </div>
            </div>
            <button id="sidebar-install-btn" onclick="showInstallModal()" class="w-full bg-[rgba(42,171,238,0.15)] text-[var(--primary)] py-3 rounded-xl font-bold text-[11px] uppercase tracking-wide border border-[rgba(42,171,238,0.3)] flex items-center justify-center gap-2 active:scale-95 transition-transform">
                <i class="fas fa-download"></i> Install App
            </button>
        </div>
        <div id="sidebar-links-container" class="sidebar-grid"></div>
    </div>

    <div id="top-bar-container" class="app-bar"></div>
    <main id="screen-content"></main>
    <div id="bottom-nav-container" class="bottom-nav"></div>

    <div id="shareModal" class="bottom-sheet" onclick="if(event.target===this) closeShareModal()">
        <div class="sheet-content">
            <div class="sheet-handle"></div>
            <h4 class="text-white font-black uppercase text-[12px] mb-5 tracking-widest text-center">Dispatch Destination</h4>
            <div id="modal-client-list" class="max-h-64 overflow-y-auto flex flex-col no-scrollbar mb-5"></div>
            <button onclick="closeShareModal()" class="text-[var(--rose)] font-bold text-[12px] uppercase block mx-auto py-3.5 w-full bg-[rgba(255,93,93,0.1)] rounded-xl border border-[rgba(255,93,93,0.2)] active:scale-95 transition-all">Cancel</button>
        </div>
    </div>

    <div id="targetPickerModal" class="bottom-sheet" onclick="if(event.target===this) closeTargetPicker()">
        <div class="sheet-content p-0 overflow-hidden">
            <div class="sheet-handle mt-4"></div>
            <div id="target-picker-content"></div>
        </div>
    </div>

    <script>
        // ==========================================
        // SECURITY LOCKDOWN v8 — same-origin API token wrapper
        // ==========================================
        const TITAN_SECURITY = {{ security_config | tojson }};
        const TITAN_APP_CONFIG = {{ app_config | tojson }};
        (function(){
            const originalFetch = window.fetch.bind(window);
            function storedAdminToken(){ try { return localStorage.getItem('TITAN_ADMIN_TOKEN') || ''; } catch(e){ return ''; } }
            function sameOriginUrl(input){
                const url = (typeof input === 'string') ? input : ((input && input.url) || '');
                return url.startsWith('/') || url.startsWith(location.origin);
            }
            function titanMoneyRoute(url){
                try {
                    const u = (typeof url === 'string') ? url : ((url && url.url) || '');
                    return ['/api/submit_payment','/api/approve_payment','/api/reject_payment','/api/wallet_transaction','/api/wallet_credit_limit','/api/wallet_zero_settle','/api/withdrawal_action'].some(p => u.includes(p));
                } catch(e){ return false; }
            }
            async function titanDigest(s){
                try{
                    if(window.crypto && crypto.subtle){
                        const data = new TextEncoder().encode(s);
                        const buf = await crypto.subtle.digest('SHA-256', data);
                        return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,32);
                    }
                }catch(e){}
                let h=0; for(let i=0;i<s.length;i++) h=((h<<5)-h)+s.charCodeAt(i)|0;
                return String(Math.abs(h));
            }
            function titanVipId(){
                try { return new URLSearchParams(location.search).get('vip') || (window.appState && appState.activeId && !IS_MASTER ? appState.activeId : '') || ''; } catch(e){ return ''; }
            }
            function titanVipDeviceId(vipId){
                try{
                    const key = 'TITAN_VIP_DEVICE_' + (vipId || 'default');
                    let id = localStorage.getItem(key);
                    if(!id){
                        const rnd = (crypto && crypto.getRandomValues) ? Array.from(crypto.getRandomValues(new Uint8Array(12))).map(b=>b.toString(16).padStart(2,'0')).join('') : String(Date.now()) + Math.random().toString(16).slice(2);
                        id = 'vipdev_' + rnd;
                        localStorage.setItem(key, id);
                    }
                    return id;
                }catch(e){ return 'vipdev_' + Math.abs((navigator.userAgent||'').split('').reduce((a,c)=>((a<<5)-a)+c.charCodeAt(0)|0,0)); }
            }
            function withAdminHeader(init, input){
                const out = Object.assign({}, init || {});
                const headers = new Headers(out.headers || {});
                const token = storedAdminToken();
                if(token && !headers.has('X-Titan-Admin-Token')) headers.set('X-Titan-Admin-Token', token);
                try{
                    const vid = titanVipId();
                    if(vid){
                        headers.set('X-Titan-Vip-Id', vid);
                        if(!headers.has('X-Titan-Vip-Device')) headers.set('X-Titan-Vip-Device', titanVipDeviceId(vid));
                        if(!headers.has('X-Titan-Vip-Fp')) headers.set('X-Titan-Vip-Fp', String((navigator.platform||'') + '|' + (navigator.language||'') + '|' + (screen.width||0) + 'x' + (screen.height||0)).slice(0,96));
                    }
                }catch(e){}
                out.headers = headers;
                return out;
            }
            window.titanAdminLogout = async function(){
                try { await originalFetch('/api/admin_logout', {method:'POST', headers:{'X-Titan-Admin-Token':storedAdminToken()}}); } catch(e){}
                try { localStorage.removeItem('TITAN_ADMIN_TOKEN'); } catch(e){}
                location.href = '/';
            };
            window.fetch = async function(input, init){
                const patched = sameOriginUrl(input) ? withAdminHeader(init, input) : (init || {});
                try{
                    const method = String((patched && patched.method) || 'GET').toUpperCase();
                    if(method !== 'GET' && titanMoneyRoute(input) && patched && patched.headers && !patched.headers.has('X-Idempotency-Key')){
                        const url = (typeof input === 'string') ? input : ((input && input.url) || '');
                        const body = typeof patched.body === 'string' ? patched.body : JSON.stringify(patched.body || '');
                        const bucket = Math.floor(Date.now()/10000);
                        const digest = await titanDigest(method + '|' + url + '|' + body + '|' + bucket);
                        patched.headers.set('X-Idempotency-Key', 'ui-' + digest);
                    }
                }catch(e){}
                return originalFetch(input, patched).then(res => {
                    if(res && res.status === 401 && TITAN_SECURITY && TITAN_SECURITY.enabled){
                        try { showRealNotification('🔒 Admin Token Required', 'Session expire/token missing. Login again.', 'warning'); } catch(e){}
                    }
                    return res;
                });
            };
        })();

        // ==========================================
        // IMAGE UPLOAD SETUP v11 — server proxy; no browser API key exposure
        // ==========================================
        const IMGBB_API_KEY = ""; // v11: deprecated, never expose third-party upload keys in browser JS.
        async function titanUploadImage(file){
            if(!file) return '';
            const maxBytes = Number((TITAN_APP_CONFIG && TITAN_APP_CONFIG.uploadMaxBytes) || (7 * 1024 * 1024));
            if(file.size && file.size > maxBytes) throw new Error('Image too large. Max ' + Math.round(maxBytes/1024/1024) + ' MB allowed.');
            const fd = new FormData();
            fd.append('image', file);
            const endpoint = (TITAN_APP_CONFIG && TITAN_APP_CONFIG.uploadEndpoint) || '/api/upload_image';
            const res = await fetch(endpoint, { method:'POST', body: fd });
            const data = await res.json().catch(()=>({}));
            if(!res.ok || data.status !== 'success') throw new Error(data.message || 'Image upload failed');
            return data.url || data.display_url || '';
        }
        // ==========================================

        // ── PWA / SERVICE WORKER ──
        if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(()=>{}); }
        let deferredPrompt;

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            const floatBanner = document.getElementById('pwa-install-banner');
            const autoSection = document.getElementById('auto-install-section');
            if(floatBanner) floatBanner.classList.remove('hidden');
            if(autoSection) autoSection.classList.remove('hidden');
        });

        function installPWA() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        showRealNotification('✅ Install Successful!', 'App aapke home screen par add ho gaya hai!', 'success');
                        document.getElementById('pwa-install-banner').classList.add('hidden');
                    }
                    deferredPrompt = null;
                });
            } else {
                showInstallModal();
            }
        }

        function showInstallModal() {
            document.getElementById('install-modal').classList.add('open');
        }
        function closeInstallModal() {
            document.getElementById('install-modal').classList.remove('open');
        }

        const IS_MASTER = {{ 'true' if is_master else 'false' }};
        let appState = {{ state | tojson }};
        let chartLinks = {{ chartLinks | tojson }};

        const LOCAL_KEY = IS_MASTER ? 'TITAN_NOVA_None' : 'TITAN_NOVA_VIP_' + appState.activeId;
        const TITAN_REALTIME_SYNC_MS = 1200;
        const TITAN_VIP_REALTIME_SYNC_MS = 1500;
        const TITAN_AUTOSAVE_DEBOUNCE_MS = 180;
        const TITAN_SAVE_RELEASE_MS = 350;

        // v26 Lite: only keep tab/sub query routing; removed pro-tool panels.
        const TITAN_LITE_QUERY = new URLSearchParams(window.location.search || '');
        function titanApplyStartupToolRoute(){
            try{
                const requestedTab = String(TITAN_LITE_QUERY.get('tab') || '').trim();
                if(requestedTab) mainNav = requestedTab;
                const requestedSub = String(TITAN_LITE_QUERY.get('sub') || '').trim();
                if(requestedSub && ['ank','jodi','pannel'].includes(requestedSub)) activeTab = requestedSub;
            }catch(e){}
        }

        // v50: capture checkbox/radio edits before inline onchange runs so old live-sync
        // responses cannot flip the control back while the manual overwrite save is in-flight.
        document.addEventListener('change', function(ev){
            try{
                const el = ev && ev.target;
                if(el && String(el.tagName || '').toUpperCase() === 'INPUT' && ['checkbox','radio'].includes(String(el.type || '').toLowerCase())){
                    if(typeof titanMarkUiLocalWrite === 'function') titanMarkUiLocalWrite('input_toggle_capture');
                }
            }catch(e){}
        }, true);


        // SERVER FIRST SYNC (PythonAnywhere/Firebase source of truth)
        // v8: master loads full state only after admin auth; VIP/client app loads only isolated VIP state.
        const SERVER_STATE_URL = IS_MASTER ? '/api/state' : ('/api/state?vip=' + encodeURIComponent(appState.activeId || ''));
        const SERVER_STATE_BOOT_URL = SERVER_STATE_URL + (SERVER_STATE_URL.includes('?') ? '&' : '?') + '_boot=' + Date.now();
        fetch(SERVER_STATE_BOOT_URL, {cache:'no-store'})
            .then(r => { if(!r.ok) throw new Error('state_http_' + r.status); return r.json(); })
            .then(serverState => {
                appState = serverState;
                if(IS_MASTER) appState.activeId = 'admin1';
                refreshMarketArrays();
                applyPendingLedgerPatchesToState(appState);
                // v4: do not make browser cache a ledger source of truth.
                try { localStorage.removeItem(TITAN_LEDGER_PATCH_KEY); } catch(e){}
                state = appState.profiles[appState.activeId] || appState.profiles['admin1'];
                titanApplyStartupToolRoute();
                render(true);
            })
            .catch((err) => {
                // v4/v8: master ledger must not be restored from browser local JSON.
                if(IS_MASTER) return showRealNotification('⚠️ Firebase/Auth Sync', 'Firebase state load nahi hua ya admin token missing hai. Ledger local cache se restore nahi kiya gaya.', 'warning');
                let cached = localStorage.getItem(LOCAL_KEY);
                if(cached) {
                    try {
                        const parsed = JSON.parse(cached);
                        if(parsed.activeId === appState.activeId) appState = parsed;
                    } catch(e) {}
                }
                try { titanApplyStartupToolRoute(); render(true); } catch(e) {}
            });

        let state = appState.profiles[appState.activeId];
        if(!state){
            appState.activeId = "admin1";
            state = appState.profiles["admin1"];
        }


        function titanStableStringify(obj) {
            if (obj !== null && typeof obj === 'object') {
                if (Array.isArray(obj)) return '[' + obj.map(titanStableStringify).join(',') + ']';
                return '{' + Object.keys(obj).sort().map(k => '"' + k + '":' + titanStableStringify(obj[k])).join(',') + '}';
            }
            return JSON.stringify(obj);
        }
        function titanIsTypingNow() {
            const el = document.activeElement;
            if(!el) return false;
            const tag = String(el.tagName || '').toUpperCase();
            return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
        }
        let titanMasterSyncBusy = false;
        let titanFullSaveInFlight = false;
        let titanFullSaveQueued = false;

        // UI_LOCAL_LOCK_v50:
        // Checkboxes/toggles/settings are optimistic local edits. A live sync request that
        // started just before a tap can return an old Firebase snapshot and flip the UI
        // ON/OFF/ON for a few seconds. Keep a short local-write lock and overlay the
        // admin's latest settings until /save has had time to become the source of truth.
        let titanUiLocalWriteUntil = 0;
        let titanUiLocalWriteSeq = 0;
        const TITAN_UI_LOCAL_WRITE_HOLD_MS = 6500;
        const TITAN_UI_LOCAL_SETTING_KEYS = [
            'settlementSettings','resultSettings','entrySettings','walletSettings','paymentSettings',
            'loadForwarder','spamGuardSettings','whatsappSafetySettings','userSafetySettings',
            'marketRegistry','ledgerSchedules','resultTargets','whatsappSafetyTargets','loadForwarderOutbox'
        ];
        function titanDeepClone(v){ try { return JSON.parse(JSON.stringify(v)); } catch(e){ return v; } }
        function titanUiHasLocalWrite(){ return Date.now() < (titanUiLocalWriteUntil || 0); }
        function titanMarkUiLocalWrite(reason, holdMs){
            titanUiLocalWriteSeq += 1;
            titanUiLocalWriteUntil = Math.max(titanUiLocalWriteUntil || 0, Date.now() + (holdMs || TITAN_UI_LOCAL_WRITE_HOLD_MS));
            try { appState._uiLocalWrite = {at: Date.now(), seq: titanUiLocalWriteSeq, reason: reason || 'ui_write'}; } catch(e) {}
        }
        function titanOverlayLocalUiWrites(targetState){
            if(!targetState || !appState || !titanUiHasLocalWrite()) return targetState;
            try {
                TITAN_UI_LOCAL_SETTING_KEYS.forEach(k => {
                    if(typeof appState[k] !== 'undefined') targetState[k] = titanDeepClone(appState[k]);
                });
                if(appState.profiles && targetState.profiles && appState.activeId && appState.profiles[appState.activeId]){
                    const pid = appState.activeId;
                    targetState.profiles[pid] = titanDeepClone(appState.profiles[pid]);
                    targetState.activeId = pid;
                }
            } catch(e) {}
            return targetState;
        }

        async function titanMasterLiveLedgerSync() {
            if(!IS_MASTER || titanMasterSyncBusy || titanFullSaveInFlight || titanIsTypingNow() || titanLedgerHasLocalDirty() || titanUiHasLocalWrite()) return;
            titanMasterSyncBusy = true;
            try {
                const activeId = appState.activeId || 'admin1';
                const before = titanStableStringify({
                    day: appState.profiles?.[activeId]?.dayRecords?.[currentDate] || {},
                    results: appState.resultRecords?.[currentDate] || {},
                    auto: appState.ledgerAutoMarkRecords?.[currentDate] || {},
                    settlements: appState.settlementRecords?.[currentDate] || {},
                    schedules: appState.ledgerSchedules || {},
                    markets: appState.marketRegistry || {},
                    settings: {resultSettings: appState.resultSettings || {}, settlementSettings: appState.settlementSettings || {}, entrySettings: appState.entrySettings || {}, loadForwarder: appState.loadForwarder || {}}
                });
                const syncStartSeq = titanLedgerLocalMutationSeq || 0;
                const res = await fetch('/api/state?live_sync=1&_fast=1&_=' + Date.now(), {cache:'no-store'});
                if(!res.ok) return;
                const newState = await res.json();
                if(!newState || !newState.profiles) return;
                // A sync response may have been launched before the user tapped a checkbox.
                // Do not let that old snapshot flip the latest local toggle state.
                if(titanUiHasLocalWrite()) { titanOverlayLocalUiWrites(newState); return; }
                newState.activeId = newState.profiles[activeId] ? activeId : 'admin1';
                refreshMarketArrays();
                applyPendingLedgerPatchesToState(newState);
                const staleWhileEditing = (titanLedgerLocalMutationSeq || 0) !== syncStartSeq || titanLedgerHasLocalDirty() || titanTypingActive();
                const after = titanStableStringify({
                    day: newState.profiles?.[newState.activeId]?.dayRecords?.[currentDate] || {},
                    results: newState.resultRecords?.[currentDate] || {},
                    auto: newState.ledgerAutoMarkRecords?.[currentDate] || {},
                    settlements: newState.settlementRecords?.[currentDate] || {},
                    schedules: newState.ledgerSchedules || {},
                    markets: newState.marketRegistry || {},
                    settings: {resultSettings: newState.resultSettings || {}, settlementSettings: newState.settlementSettings || {}, entrySettings: newState.entrySettings || {}, loadForwarder: newState.loadForwarder || {}}
                });
                if(before !== after) {
                    appState = newState;
                    refreshMarketArrays();
                    state = appState.profiles[appState.activeId] || appState.profiles['admin1'];
                    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
                    if(['ledger','results','audit'].includes(mainNav) && !staleWhileEditing) render(true);
                    else if(['ledger','results','audit'].includes(mainNav) && staleWhileEditing) titanQueueRenderAfterTyping(true);
                }
            } catch(e) {}
            finally { titanMasterSyncBusy = false; }
        }
        if(IS_MASTER) setInterval(titanMasterLiveLedgerSync, TITAN_REALTIME_SYNC_MS);
        const STATIC_MARKETS = {{ markets | tojson }};
        const STATIC_BASE_MARKETS = {{ baseMarkets | tojson }};
        let markets = (STATIC_MARKETS || []).slice();
        let baseMarkets = (STATIC_BASE_MARKETS || []).slice();
        let resultMarkets = (STATIC_MARKETS || []).slice();
        let resultBaseMarkets = (STATIC_BASE_MARKETS || []).slice();

        // MARKET_MANAGER_PHASE1_REGISTRY: central market visibility/mapping for Ledger + Results.
        function marketSlug(name){ return String(name || '').trim().toUpperCase().replace(/SRIDEVI\\s+DAY/g,'SRIDEV DAY').replace(/[^A-Z0-9]+/g,'_').replace(/^_+|_+$/g,'').toLowerCase() || ('market_' + Date.now()); }
        function normalizeHHMM(v){ const m = String(v || '').trim().match(/^(\\d{1,2}):(\\d{2})$/); if(!m) return ''; const h=Number(m[1]), mi=Number(m[2]); return (h>=0&&h<=23&&mi>=0&&mi<=59) ? `${String(h).padStart(2,'0')}:${String(mi).padStart(2,'0')}` : ''; }
        function timeForStaticMarket(base, stage){ const target = String(base || '').toUpperCase().trim() + ' ' + String(stage || '').toUpperCase(); const m = (STATIC_MARKETS || []).find(x => String(x.n || '').toUpperCase() === target); return m ? `${String(Number(m.hr||0)).padStart(2,'0')}:${String(Number(m.min||0)).padStart(2,'0')}` : ''; }
        const TITAN_MARKET_TIME_LOOP_VERSION = '2026-07-03-market-time-loop-v46';
        const TITAN_MARKET_DAY_START_MINUTES = 6 * 60;
        function marketOrderMinutesFromHHMM(v){
            const t = normalizeHHMM(v);
            if(!t) return 99999;
            const [h, mi] = t.split(':').map(Number);
            let total = (h * 60) + mi;
            if(total < TITAN_MARKET_DAY_START_MINUTES) total += 1440;
            return total;
        }
        function marketNormalizeOrderName(v){
            return String(v || '').trim().toUpperCase().replace(/\\s+/g,' ').replace(/SRIDEVI DAY/g,'SRIDEV DAY');
        }
        function marketStageBaseName(v){
            let n = marketNormalizeOrderName(v);
            n = n.replace(/\\s+(OPEN|CLOSE)$/,'').trim();
            return n;
        }
        function isStartMarketName(v){
            const n = marketNormalizeOrderName(v);
            return n === 'SRIDEV DAY' || n === 'SRIDEVI' || n === 'SRIDEV' || n.startsWith('SRIDEV DAY');
        }
        function marketItemPrimaryTime(item){
            item = item || {};
            const st = item.stages || {}, tm = item.times || {};
            const vals = [];
            if(st.open !== false && tm.open) vals.push(marketOrderMinutesFromHHMM(tm.open));
            if(st.close !== false && tm.close) vals.push(marketOrderMinutesFromHHMM(tm.close));
            const real = vals.filter(x => x !== 99999);
            return real.length ? Math.min(...real) : 99999;
        }
        function marketItemLoopKey(item){
            const name = marketNormalizeOrderName((item && (item.displayName || item.name || item.websiteName)) || '');
            return {start:isStartMarketName(name) ? 0 : 1, time:marketItemPrimaryTime(item), name};
        }
        function marketItemLoopCompare(a,b){
            const ka = marketItemLoopKey(a), kb = marketItemLoopKey(b);
            return (ka.start-kb.start) || (ka.time-kb.time) || ka.name.localeCompare(kb.name) || (Number(a?.sortOrder||9999)-Number(b?.sortOrder||9999));
        }
        function ledgerMarketTimeSortKey(m){
            const base = marketStageBaseName(m && m.n);
            const start = isStartMarketName(base) ? 0 : 1;
            const h = Number(m && m.hr), mi = Number(m && m.min);
            let total = 99999;
            if(Number.isFinite(h) && Number.isFinite(mi)){ total = (h * 60) + mi; if(total < TITAN_MARKET_DAY_START_MINUTES) total += 1440; }
            return (start * 100000) + total;
        }
        function resequenceMarketSortOrders(reg){
            if(!reg || !reg.items) return reg;
            Object.values(reg.items || {}).filter(x => x && x.deleted !== true && x.archived !== true).sort(marketItemLoopCompare).forEach((item, idx) => { item.sortOrder = (idx + 1) * 10; });
            reg.timeLoopOrderVersion = TITAN_MARKET_TIME_LOOP_VERSION;
            reg.marketTimeLoopOrder = true;
            return reg;
        }
        function defaultMarketRegistry(){
            const items = {};
            (STATIC_BASE_MARKETS || []).forEach((bm, i) => {
                const name = String(bm.n || '').toUpperCase().trim(); if(!name) return;
                const id = marketSlug(name), open = timeForStaticMarket(name, 'OPEN'), close = timeForStaticMarket(name, 'CLOSE');
                items[id] = {id, name, displayName:name, websiteName:name.replace('SRIDEV DAY','SRIDEVI'), aliases:[name, name.replace('SRIDEV DAY','SRIDEVI DAY')], enabled:true, ledgerEnabled:true, resultEnabled:true, autoResultEnabled:true, autoPassFailEnabled:true, scheduleEnabled:true, entryEnabled:true, entryTargets:[], scheduleTargets:[], resultTargets:[], forwardTargets:[], bookieTargets:[], sortOrder:i*10, stages:{open:!!open, close:!!close}, times:{open, close}, chartUrl:'', archived:false, hardDeleteAllowed:false, createdAt:new Date().toISOString(), updatedAt:new Date().toISOString()};
            });
            return {version:'2026-06-30-market-registry-phase3-v1', marketManagerPhase1:true, marketManagerPhase3:true, marketManagerDeleteSupport:true, deletedMarketIds:[], updatedAt:new Date().toISOString(), items};
        }
        function applyMarketManualSaveLock(item, source='manual_registry_save'){
            if(!item || typeof item !== 'object') return item;
            const stamp = new Date().toISOString();
            item.settingsLocked = true;
            item.manualSaveLocked = true;
            item.manualChangeOnly = true;
            item.lockedAfterSave = true;
            item.settingsLockSource = source;
            item.settingsLockedAt = item.settingsLockedAt || stamp;
            item.lastManualSaveAt = stamp;
            return item;
        }
        function normalizeMarketRegistry(reg){
            if(!reg || typeof reg !== 'object') reg = {};
            const def = defaultMarketRegistry();
            const items = (reg.items && typeof reg.items === 'object') ? reg.items : {};
            const deletedIds = new Set(Array.isArray(reg.deletedMarketIds) ? reg.deletedMarketIds.map(x => String(x)).filter(Boolean) : []);
            Object.keys(def.items).forEach(id => { if(deletedIds.has(id)) return; if(!items[id]) items[id] = def.items[id]; else { const d = def.items[id]; Object.keys(d).forEach(k => { if(typeof items[id][k] === 'undefined') items[id][k] = d[k]; }); } });
            const cleaned = {};
            Object.entries(items).forEach(([key, raw]) => {
                if(!raw || typeof raw !== 'object') return;
                const name = String(raw.name || raw.displayName || key || '').toUpperCase().trim(); if(!name) return;
                const id = String(raw.id || key || marketSlug(name));
                const item = {...raw, id, name};
                item.displayName = String(item.displayName || name).toUpperCase().trim();
                item.websiteName = String(item.websiteName || name).toUpperCase().trim();
                item.enabled = item.enabled !== false;
                item.ledgerEnabled = item.ledgerEnabled !== false;
                item.resultEnabled = item.resultEnabled !== false;
                item.autoResultEnabled = item.autoResultEnabled !== false;
                item.autoPassFailEnabled = item.autoPassFailEnabled !== false;
                item.scheduleEnabled = item.scheduleEnabled !== false; item.entryEnabled = item.entryEnabled !== false; if(!Array.isArray(item.entryTargets)) item.entryTargets = []; if(!Array.isArray(item.scheduleTargets)) item.scheduleTargets = []; if(!Array.isArray(item.resultTargets)) item.resultTargets = []; if(!Array.isArray(item.forwardTargets)) item.forwardTargets = []; if(!Array.isArray(item.bookieTargets)) item.bookieTargets = [];
                item.archived = item.archived === true;
                item.deleted = item.deleted === true;
                if(item.deleted){
                    deletedIds.add(id);
                    item.enabled = false;
                    item.ledgerEnabled = false;
                    item.resultEnabled = false;
                    item.autoResultEnabled = false;
                    item.autoPassFailEnabled = false;
                    item.scheduleEnabled = false;
                    item.archived = false;
                    item.deletedAt = item.deletedAt || new Date().toISOString();
                }
                item.settingsLocked = item.settingsLocked === true || item.manualSaveLocked === true;
                item.manualSaveLocked = item.manualSaveLocked === true || item.settingsLocked === true;
                item.manualChangeOnly = item.manualChangeOnly === true || item.settingsLocked === true;
                item.lockedAfterSave = item.lockedAfterSave === true || item.settingsLocked === true;
                if(item.settingsLockSource) item.settingsLockSource = String(item.settingsLockSource);
                if(item.settingsLockedAt) item.settingsLockedAt = String(item.settingsLockedAt);
                if(item.lastManualSaveAt) item.lastManualSaveAt = String(item.lastManualSaveAt);
                item.stages = (item.stages && typeof item.stages === 'object') ? item.stages : {open:true, close:true};
                item.stages.open = item.stages.open !== false;
                item.stages.close = item.stages.close !== false;
                item.times = (item.times && typeof item.times === 'object') ? item.times : {open:'', close:''};
                item.times.open = normalizeHHMM(item.times.open);
                item.times.close = normalizeHHMM(item.times.close);
                item.sortOrder = Number.isFinite(Number(item.sortOrder)) ? Number(item.sortOrder) : 9999;
                cleaned[id] = item;
            });
            reg.version = '2026-06-30-market-registry-phase3-v1'; reg.marketManagerPhase1 = true; reg.marketManagerPhase3 = true; reg.marketManagerDeleteSupport = true; reg.deletedMarketIds = Array.from(deletedIds).filter(Boolean); reg.items = cleaned; reg.updatedAt = reg.updatedAt || new Date().toISOString(); reg.marketTimeLoopOrder = true;
            resequenceMarketSortOrders(reg);
            return reg;
        }
        function ensureMarketRegistry(){ if(!appState.marketRegistry) appState.marketRegistry = defaultMarketRegistry(); appState.marketRegistry = normalizeMarketRegistry(appState.marketRegistry); return appState.marketRegistry; }
        function marketItemsForPurpose(purpose, includeDisabled=false){ const reg = ensureMarketRegistry(); return Object.values(reg.items || {}).filter(item => { if(item.deleted) return false; if(includeDisabled) return true; if(item.archived || item.enabled === false) return false; if(purpose==='ledger' && item.ledgerEnabled === false) return false; if(purpose==='result' && item.resultEnabled === false) return false; if(purpose==='schedule' && item.scheduleEnabled === false) return false; if(purpose==='autopf' && item.autoPassFailEnabled === false) return false; return true; }).sort(marketItemLoopCompare); }
        function marketArraysForPurpose(purpose){
            const ms = [], bs = [];
            let rows;
            if(purpose === 'ledger' || purpose === 'schedule'){
                const reg = ensureMarketRegistry();
                rows = Object.values(reg.items || {}).filter(item => item && item.archived !== true).sort(marketItemLoopCompare);
            } else rows = marketItemsForPurpose(purpose);
            rows.forEach(item => { const name = String(item.displayName || item.name || '').toUpperCase().trim(); if(!name) return; const hiddenForLedger = (item.deleted === true || item.enabled === false || item.ledgerEnabled === false || item.archived === true); const scheduleDisabled = (item.deleted === true || item.enabled === false || item.ledgerEnabled === false || item.scheduleEnabled === false || item.archived === true); bs.push({n:name, id:item.id, websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false}); const st = item.stages || {}, tm = item.times || {}; if(st.open !== false){ const t=normalizeHHMM(tm.open); const [h,mi]=t?t.split(':').map(Number):[0,0]; ms.push({n:name+' OPEN', hr:h, min:mi, id:item.id, stage:'open', websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false}); } if(st.close !== false){ const t=normalizeHHMM(tm.close); const [h,mi]=t?t.split(':').map(Number):[0,0]; ms.push({n:name+' CLOSE', hr:h, min:mi, id:item.id, stage:'close', websiteName:item.websiteName, hiddenForLedger, scheduleDisabled, enabled:item.enabled!==false, ledgerEnabled:item.ledgerEnabled!==false, resultEnabled:item.resultEnabled!==false, autoPassFailEnabled:item.autoPassFailEnabled!==false, scheduleEnabled:item.scheduleEnabled!==false}); } });
            ms.sort((a,b)=>ledgerMarketTimeSortKey(a)-ledgerMarketTimeSortKey(b) || String(a.n||'').localeCompare(String(b.n||'')));
            return {markets:ms.length?ms:(STATIC_MARKETS||[]).slice(), baseMarkets:bs.length?bs:(STATIC_BASE_MARKETS||[]).slice()};
        }
        function refreshMarketArrays(){ ensureMarketRegistry(); const ledger = marketArraysForPurpose('ledger'); markets = ledger.markets; baseMarkets = ledger.baseMarkets; const result = marketArraysForPurpose('result'); resultMarkets = result.markets; resultBaseMarkets = result.baseMarkets; }

        // MARKET_MANAGER_ADD_SAVE_FIX: preserve old ledger/card data when market order changes.
        function marketOrderName(m){ return String((m && m.n) || '').toUpperCase().trim(); }
        function cloneMarketOrderArray(arr){ return (arr || []).map(m => ({n:marketOrderName(m)})); }
        function captureMarketOrderSnapshot(){ return {markets: cloneMarketOrderArray(markets), baseMarkets: cloneMarketOrderArray(baseMarkets)}; }
        function reindexRecordDictByMarketOrder(oldArr, newArr, dict){
            if(!dict || typeof dict !== 'object' || Array.isArray(dict)) return dict || {};
            const byName = {};
            (oldArr || []).forEach((m, idx) => {
                const key = marketOrderName(m);
                if(!key) return;
                if(Object.prototype.hasOwnProperty.call(dict, idx)) byName[key] = dict[idx];
                else if(Object.prototype.hasOwnProperty.call(dict, String(idx))) byName[key] = dict[String(idx)];
            });
            const out = {};
            (newArr || []).forEach((m, idx) => {
                const key = marketOrderName(m);
                if(key && Object.prototype.hasOwnProperty.call(byName, key)) out[idx] = byName[key];
            });
            Object.keys(dict || {}).forEach(k => { if(!/^\\d+$/.test(k)) out[k] = dict[k]; });
            return out;
        }
        function reindexProfileDayRecordsForMarketOrder(pState, oldMarkets, oldBaseMarkets, newMarkets, newBaseMarkets){
            if(!pState || !pState.dayRecords || typeof pState.dayRecords !== 'object') return;
            Object.values(pState.dayRecords).forEach(rec => {
                if(!rec || typeof rec !== 'object') return;
                if(rec.data) rec.data = reindexRecordDictByMarketOrder(oldMarkets, newMarkets, rec.data);
                if(rec.pannelData) rec.pannelData = reindexRecordDictByMarketOrder(oldMarkets, newMarkets, rec.pannelData);
                if(rec.jodiData) rec.jodiData = reindexRecordDictByMarketOrder(oldBaseMarkets, newBaseMarkets, rec.jodiData);
            });
        }
        function reindexLedgerSchedulesForMarketOrder(oldMarkets, oldBaseMarkets, newMarkets, newBaseMarkets){
            if(!appState.ledgerSchedules || typeof appState.ledgerSchedules !== 'object' || Array.isArray(appState.ledgerSchedules)) return;
            const out = {};
            Object.entries(appState.ledgerSchedules).forEach(([key, item]) => {
                if(!item || typeof item !== 'object'){ out[key] = item; return; }
                const type = String(item.type || '').toLowerCase();
                if(!['ank','jodi','pannel'].includes(type)){ out[key] = item; return; }
                const oldArr = type === 'jodi' ? oldBaseMarkets : oldMarkets;
                const newArr = type === 'jodi' ? newBaseMarkets : newMarkets;
                const oldIdx = parseInt(item.index, 10);
                const oldName = marketOrderName((oldArr || [])[oldIdx]);
                if(!oldName){ out[key] = item; return; }
                const newIdx = (newArr || []).findIndex(m => marketOrderName(m) === oldName);
                if(newIdx < 0){ out[key] = item; return; }
                const profileId = item.profileId || String(key).split('|')[0] || appState.activeId || 'admin1';
                const mk = item.marketKey || ledgerMarketKeyForCard(type, (newArr || [])[newIdx] || {});
                const newKey = ledgerScheduleKey(profileId, type, newIdx, mk);
                out[newKey] = {...item, profileId, type, index:newIdx, marketKey:mk, marketName:(((newArr || [])[newIdx] || {}).n || item.marketName || ''), keyVersion:'marketKey-v2', updatedAt:new Date().toISOString()};
            });
            appState.ledgerSchedules = out;
        }
        function applyMarketOrderTransition(oldOrder){
            oldOrder = oldOrder || captureMarketOrderSnapshot();
            const oldMarkets = oldOrder.markets || [];
            const oldBaseMarkets = oldOrder.baseMarkets || [];
            refreshMarketArrays();
            const newMarkets = cloneMarketOrderArray(markets);
            const newBaseMarkets = cloneMarketOrderArray(baseMarkets);
            Object.values(appState.profiles || {}).forEach(p => reindexProfileDayRecordsForMarketOrder(p, oldMarkets, oldBaseMarkets, newMarkets, newBaseMarkets));
            reindexLedgerSchedulesForMarketOrder(oldMarkets, oldBaseMarkets, newMarkets, newBaseMarkets);
            state = appState.profiles[appState.activeId] || appState.profiles['admin1'] || state;
        }
        function itemPrimaryTimeSortValue(item){ return marketItemPrimaryTime(item); }
        function nextMarketSortOrderForTime(openTime, closeTime){
            const reg = ensureMarketRegistry();
            const probe = {stages:{open:!!openTime, close:!!closeTime}, times:{open:openTime || '', close:closeTime || ''}};
            const target = itemPrimaryTimeSortValue(probe);
            const active = Object.values(reg.items || {}).filter(x => x && x.deleted !== true && x.archived !== true).sort(marketItemLoopCompare);
            let prev = null, next = null;
            for(const item of active){
                if(itemPrimaryTimeSortValue(item) <= target) prev = item;
                else { next = item; break; }
            }
            const prevOrder = prev ? Number(prev.sortOrder || 0) : null;
            const nextOrder = next ? Number(next.sortOrder || 0) : null;
            if(prevOrder !== null && nextOrder !== null && nextOrder - prevOrder > 1) return Math.floor((prevOrder + nextOrder) / 2);
            if(prevOrder !== null && nextOrder === null) return prevOrder + 10;
            if(prevOrder === null && nextOrder !== null) return nextOrder - 10;
            return (active.length + 1) * 10;
        }

        // MARKET CORE v28: blank-tab fix + compact market controls.
        let marketManagerSearch = '';
        let marketManagerShowDisabled = true;
        let marketSourceScanLoading = false;
        let marketSourceScanData = null;
        let marketSourceSelected = {};
        let marketActionBusy = false;

        function marketBadge(ok, yes, no){
            return `<span class="px-2 py-1 rounded-lg text-[8px] font-black uppercase ${ok?'bg-[rgba(0,194,111,0.12)] text-[var(--green)] border border-[rgba(0,194,111,0.20)]':'bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.18)]'}">${ok?yes:no}</span>`;
        }
        function marketCandidateName(x){
            if(x && typeof x === 'object') return String(x.name || x.displayName || x.websiteName || x.foundName || x.market || x.title || '').trim().toUpperCase();
            return String(x || '').trim().toUpperCase();
        }
        function marketCandidateMeta(x){
            if(!x || typeof x !== 'object') return '';
            const bits = [];
            if(Array.isArray(x.blocks) && x.blocks.length) bits.push(x.blocks.slice(0,2).join(', '));
            if(x.count) bits.push('count ' + x.count);
            return bits.join(' · ');
        }
        function setMarketManagerSearch(v){ marketManagerSearch = String(v || ''); render(true); }
        function toggleMarketManagerDisabled(v){ marketManagerShowDisabled = !!v; render(true); }
        function marketScanSummaryHtml(){
            const d = marketSourceScanData;
            if(marketSourceScanLoading) return '<div class="text-[10px] text-[var(--amber)] font-bold">Website scan running...</div>';
            if(!d) return '<div class="text-[10px] text-[var(--text-muted)]">Optional: website se new market names scan kar sakte ho.</div>';
            const found = Array.isArray(d.foundMarkets) ? d.foundMarkets : [];
            const unknown = Array.isArray(d.unknownWebsiteMarkets) ? d.unknownWebsiteMarkets : [];
            return `<div class="space-y-2"><div class="text-[10px] text-[var(--text-muted)]">Found: <b class="text-white">${found.length}</b> · New: <b class="text-[var(--amber)]">${unknown.length}</b></div>${unknown.slice(0,10).map(x => { const key=marketCandidateName(x); if(!key) return ''; const meta=marketCandidateMeta(x); return `<label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2 text-[10px]"><span class="min-w-0"><b class="text-white block truncate">${htmlEscape(key)}</b>${meta?`<small class="text-[var(--text-muted)]">${htmlEscape(meta)}</small>`:''}</span><input type="checkbox" ${marketSourceSelected[key]!==false?'checked':''} onchange="marketSourceSelected['${attrEscape(key)}']=this.checked"></label>`; }).join('')}</div>`;
        }
        function updateMarketText(id, field, value){ const item = ensureMarketRegistry().items[id]; if(!item) return; item[field] = field === 'chartUrl' ? String(value||'').trim() : String(value||'').trim().toUpperCase(); item.updatedAt = new Date().toISOString(); marketAction('update_text', {id, field, value:item[field]}, false); }
        function updateMarketTime(id, stage, value){ const t = normalizeHHMM(value); if(value && !t) return showRealNotification('⚠️ Time Error','HH:MM format use karo, example 03:00','warning'); const item = ensureMarketRegistry().items[id]; if(!item) return; item.times = item.times || {}; item.stages = item.stages || {}; item.times[stage] = t; item.stages[stage] = !!t; item.updatedAt = new Date().toISOString(); applyMarketOrderTransition(); marketAction('update_time', {id, stage, value:t}, false); }
        function setMarketItemFlag(id, field, value){ titanMarkUiLocalWrite('market_item_flag'); const item = ensureMarketRegistry().items[id]; if(!item) return; item[field] = !!value; item.updatedAt = new Date().toISOString(); refreshMarketArrays(); render(true); marketAction('set_flag', {id, field, value:!!value}, false); }
        function setMarketStageFlag(id, stage, value){ titanMarkUiLocalWrite('market_stage_flag'); const item = ensureMarketRegistry().items[id]; if(!item) return; item.stages = item.stages || {}; item.stages[stage] = !!value; item.updatedAt = new Date().toISOString(); applyMarketOrderTransition(); render(true); marketAction('set_stage', {id, stage, value:!!value}, false); }
        async function marketAction(action, payload={}, shouldRender=true){
            if(marketActionBusy && ['add','upsert','delete','archive','restore','disable'].includes(action)) return;
            marketActionBusy = true;
            try{
                const res = await fetch('/api/market_action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, ...payload})});
                const data = await res.json().catch(()=>({}));
                if(!res.ok || data.status !== 'success') throw new Error(data.message || ('Market action failed: ' + res.status));
                if(data.marketRegistry) appState.marketRegistry = data.marketRegistry;
                if(data.ledgerMarkets) markets = data.ledgerMarkets;
                if(data.ledgerBaseMarkets) baseMarkets = data.ledgerBaseMarkets;
                if(data.resultMarkets) resultMarkets = data.resultMarkets;
                if(data.resultBaseMarkets) resultBaseMarkets = data.resultBaseMarkets;
                if(data.chartLinks) chartLinks = data.chartLinks;
                refreshMarketArrays();
                if(shouldRender) render(true);
                return data;
            }catch(e){
                showRealNotification('❌ Market Save', String(e.message || e), 'danger');
                return null;
            }finally{ marketActionBusy = false; }
        }
        async function saveMarketRegistry(){ const old = captureMarketOrderSnapshot(); Object.values(ensureMarketRegistry().items || {}).forEach(x=>applyMarketManualSaveLock(x,'manual_registry_save')); const data = await marketAction('save_registry', {marketRegistry: ensureMarketRegistry()}, false); if(data){ applyMarketOrderTransition(old); render(true); showRealNotification('✅ Market Saved','Market registry save ho gaya','success'); } }
        async function reloadMarketRegistry(){
            try{
                const res = await fetch('/api/market_registry?_=' + Date.now(), {cache:'no-store'});
                const data = await res.json();
                if(!res.ok || data.status !== 'success') throw new Error(data.message || 'Reload failed');
                appState.marketRegistry = data.marketRegistry || appState.marketRegistry;
                if(data.ledgerMarkets) markets = data.ledgerMarkets;
                if(data.ledgerBaseMarkets) baseMarkets = data.ledgerBaseMarkets;
                if(data.resultMarkets) resultMarkets = data.resultMarkets;
                if(data.resultBaseMarkets) resultBaseMarkets = data.resultBaseMarkets;
                refreshMarketArrays(); render(true); showRealNotification('✅ Market Reloaded','Firebase se latest market registry loaded','success');
            }catch(e){ showRealNotification('❌ Market Reload', String(e.message || e), 'danger'); }
        }
        async function addMarketFromManager(){
            const oldOrder = captureMarketOrderSnapshot();
            const name = (document.getElementById('mm-name')||{}).value || '';
            const websiteName = (document.getElementById('mm-website')||{}).value || name;
            const openTime = normalizeHHMM((document.getElementById('mm-open')||{}).value || '');
            const closeTime = normalizeHHMM((document.getElementById('mm-close')||{}).value || '');
            const chartUrl = (document.getElementById('mm-chart')||{}).value || '';
            if(!String(name).trim()) return showRealNotification('⚠️ Market Name','Market name required','warning');
            if(!openTime && !closeTime) return showRealNotification('⚠️ Market Time','Open ya Close me se ek valid HH:MM time do','warning');
            const data = await marketAction('direct_add_full', {name, websiteName, openTime, closeTime, chartUrl,
                ledgerEnabled: !!(document.getElementById('mm-ledger')||{}).checked,
                resultEnabled: !!(document.getElementById('mm-results')||{}).checked,
                autoPassFailEnabled: !!(document.getElementById('mm-autopf')||{}).checked,
                scheduleEnabled: !!(document.getElementById('mm-schedule')||{}).checked,
                entryEnabled: !!(document.getElementById('mm-entry')||{}).checked,
                entryTargets: titanCleanTargets((document.getElementById('mm-entry-targets')||{}).value || ''),
                scheduleTargets: titanCleanTargets((document.getElementById('mm-schedule-targets')||{}).value || ''),
                resultTargets: titanCleanTargets((document.getElementById('mm-result-targets')||{}).value || ''),
                forwardTargets: titanCleanTargets((document.getElementById('mm-forward-targets')||{}).value || ''),
                bookieTargets: titanCleanTargets((document.getElementById('mm-bookie-targets')||{}).value || ''),
                openStage: !!(document.getElementById('mm-stage-open')||{}).checked,
                closeStage: !!(document.getElementById('mm-stage-close')||{}).checked
            }, false);
            if(data){ applyMarketOrderTransition(oldOrder); ['mm-name','mm-website','mm-open','mm-close','mm-chart','mm-schedule-targets','mm-entry-targets','mm-result-targets','mm-forward-targets','mm-bookie-targets'].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=''; }); render(true); showRealNotification('✅ Direct Market Added','Time order me market add ho gaya. Ledger/Results/Jodi order sync ho gaya.','success'); }
        }
        function disableMarket(id){ if(confirm('Disable market? Old history safe rahegi.')) marketAction('disable', {id}); }
        function restoreMarket(id){ marketAction('restore', {id}); }
        function archiveMarket(id){ if(confirm('Archive market? Ye active lists se hide hoga.')) marketAction('archive', {id}); }
        function deleteMarket(id){ if(confirm('Delete market from UI? Old history safe rahegi.')) marketAction('delete', {id}); }
        async function testMarketWebsiteMapping(){
            marketSourceScanLoading = true; render(true);
            try{
                const res = await fetch('/api/market_source_scan?_=' + Date.now(), {cache:'no-store'});
                const data = await res.json();
                if(!res.ok) throw new Error(data.message || 'Scan failed');
                marketSourceScanData = data; marketSourceSelected = {};
                (Array.isArray(data.unknownWebsiteMarkets) ? data.unknownWebsiteMarkets : []).forEach(x => { const key = marketCandidateName(x); if(key) marketSourceSelected[key] = true; });
            }catch(e){ showRealNotification('❌ Website Scan', String(e.message || e), 'danger'); }
            finally{ marketSourceScanLoading = false; render(true); }
        }
        async function importMarketsFromWebsite(){
            const selected = Object.entries(marketSourceSelected || {}).filter(([k,v])=>v).map(([k])=>k);
            if(!selected.length) return showRealNotification('⚠️ No Selection','Save ke liye market select karo','warning');
            try{
                const res = await fetch('/api/market_import_from_website', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({names:selected, selectedMarkets:selected})});
                const data = await res.json().catch(()=>({}));
                if(!res.ok || data.status !== 'success') throw new Error(data.message || 'Import failed');
                if(data.marketRegistry) appState.marketRegistry = data.marketRegistry;
                refreshMarketArrays(); render(true); showRealNotification('✅ Markets Imported', `${(data.added||[]).length} added`, 'success');
            }catch(e){ showRealNotification('❌ Market Import', String(e.message || e), 'danger'); }
        }

        refreshMarketArrays();

        let mainNav = 'ledger';
        let financeSubTab = 'summary';
        let activeTab = 'ank';
        let weeklyTabType = 'ank';

        const TITAN_BUSINESS_DAY_CUTOFF_HOUR = Number((TITAN_APP_CONFIG && TITAN_APP_CONFIG.businessDayCutoffHour) || 6); // 00:00-cutoff belongs to previous business day
        function titanLocalDateISO(){
            const d = new Date();
            if(d.getHours() < TITAN_BUSINESS_DAY_CUTOFF_HOUR) d.setDate(d.getDate() - 1);
            const y = d.getFullYear();
            const m = String(d.getMonth()+1).padStart(2,'0');
            const day = String(d.getDate()).padStart(2,'0');
            return `${y}-${m}-${day}`;
        }
        function titanCalendarDateISO(){
            const d = new Date();
            const y = d.getFullYear();
            const m = String(d.getMonth()+1).padStart(2,'0');
            const day = String(d.getDate()).padStart(2,'0');
            return `${y}-${m}-${day}`;
        }
        let currentDate = titanLocalDateISO();
        let manualDateMode = false;
        function syncTodayIfNotManual(){
            const today = titanLocalDateISO();
            if(!manualDateMode && currentDate !== today) currentDate = today;
        }
        let currentMsg = ""; let selectedPhone = "";
        let globalStats = { ank: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 }, jodi: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 }, pannel: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 } };

        let autoSyncTimer;
        // v43: Setup/Market/Guard/Forward toggles are non-ledger admin settings.
        // Earlier autoSave silently returned while a ledger card was dirty/in-flight;
        // therefore toggles looked OFF in the UI but refreshed back ON because /save never ran.
        // In manual-overwrite mode the admin's current state must win, so autoSave forces /save.
        function autoSave(force = true) {
            if(force) titanMarkUiLocalWrite('autosave_forced_setting');
            clearTimeout(autoSyncTimer);
            autoSyncTimer = setTimeout(() => {
                saveMaster(true, force);
            }, TITAN_AUTOSAVE_DEBOUNCE_MS);
        }
        function titanSaveAdminSettingsNow(){
            titanMarkUiLocalWrite('admin_setting_now');
            clearTimeout(autoSyncTimer);
            saveMaster(true, true);
        }

        // INPUT_KEYBOARD_STABILITY_v47:
        // Mobile keyboard was hiding because global render()/modal render rebuilt the DOM
        // while a text/number/search field was focused. Keep editable inputs mounted until blur.
        let titanDeferredRenderArgs = null;
        let titanDeferredRenderTimer = null;
        let titanDeferredTargetPickerRender = false;
        let titanDeferredTargetPickerTimer = null;
        let titanInteractiveInputHoldUntil = 0;
        const TITAN_INTERACTIVE_INPUT_HOLD_MS = 3500;
        function titanMarkInteractiveInputHold(reason, holdMs){
            titanInteractiveInputHoldUntil = Math.max(titanInteractiveInputHoldUntil || 0, titanNowMs() + (holdMs || TITAN_INTERACTIVE_INPUT_HOLD_MS));
        }
        function titanEditableInput(el){
            if(!el) return false;
            const tag = String(el.tagName || '').toUpperCase();
            if(tag === 'TEXTAREA' || tag === 'SELECT') return true;
            if(el.isContentEditable) return true;
            if(tag !== 'INPUT') return false;
            const typ = String(el.type || 'text').toLowerCase();
            // LEDGER_INPUT_STABILITY_v51: date/time pickers are real editing sessions too.
            // Excluding them allowed live-sync/render() to rebuild the Ledger DOM while the
            // native picker was open, so the picker disappeared and nearby fields looked blank.
            return !['checkbox','radio','button','submit','reset','file','range','color','hidden'].includes(typ);
        }
        function titanTypingActive(){
            try { return titanEditableInput(document.activeElement) || titanNowMs() < (titanInteractiveInputHoldUntil || 0); } catch(e){ return titanNowMs() < (titanInteractiveInputHoldUntil || 0); }
        }
        document.addEventListener('focusin', function(ev){
            try { if(titanEditableInput(ev && ev.target)) titanMarkInteractiveInputHold('focusin'); } catch(e){}
        }, true);
        document.addEventListener('input', function(ev){
            try { if(titanEditableInput(ev && ev.target)) titanMarkInteractiveInputHold('input'); } catch(e){}
        }, true);
        document.addEventListener('pointerdown', function(ev){
            try { if(titanEditableInput(ev && ev.target)) titanMarkInteractiveInputHold('pointerdown'); } catch(e){}
        }, true);
        function titanQueueRenderAfterTyping(keepScroll){
            titanDeferredRenderArgs = {keepScroll: keepScroll !== false};
            clearTimeout(titanDeferredRenderTimer);
            titanDeferredRenderTimer = setTimeout(() => {
                if(titanTypingActive()) { titanQueueRenderAfterTyping(titanDeferredRenderArgs ? titanDeferredRenderArgs.keepScroll : true); return; }
                const args = titanDeferredRenderArgs;
                titanDeferredRenderArgs = null;
                if(args) render(args.keepScroll);
            }, 450);
        }
        function titanQueueTargetPickerRenderAfterTyping(){
            titanDeferredTargetPickerRender = true;
            clearTimeout(titanDeferredTargetPickerTimer);
            titanDeferredTargetPickerTimer = setTimeout(() => {
                if(titanTypingActive()) { titanQueueTargetPickerRenderAfterTyping(); return; }
                if(titanDeferredTargetPickerRender){
                    titanDeferredTargetPickerRender = false;
                    renderTargetPicker();
                }
            }, 450);
        }
        function titanFlushDeferredRendersSoon(){
            setTimeout(() => {
                if(!titanTypingActive()){
                    if(titanDeferredRenderArgs){
                        const args = titanDeferredRenderArgs;
                        titanDeferredRenderArgs = null;
                        render(args.keepScroll);
                    }
                    if(titanDeferredTargetPickerRender){
                        titanDeferredTargetPickerRender = false;
                        renderTargetPicker();
                    }
                }
            }, 120);
        }
        document.addEventListener('focusout', titanFlushDeferredRendersSoon, true);

        // LEDGER_PRO_COMMIT_FIX: local ledger actions must not be overwritten by stale live/server refresh.
        const TITAN_LEDGER_PATCH_KEY = LOCAL_KEY + '_LEDGER_PENDING_PATCHES_V3';
        const TITAN_LEDGER_LOCAL_HOLD_MS = 6500; // v48: hold local ledger edits long enough to avoid stale server flash
        const TITAN_LEDGER_PATCH_EXPIRY_MS = 10 * 60 * 1000;
        let titanLedgerDirtyUntil = 0;
        let titanLedgerSaveInFlight = false;
        function titanNowMs(){ return Date.now ? Date.now() : (new Date()).getTime(); }
        function titanMarkLedgerDirty(){ titanLedgerDirtyUntil = Math.max(titanLedgerDirtyUntil || 0, titanNowMs() + TITAN_LEDGER_LOCAL_HOLD_MS); }
        function titanLedgerHasLocalDirty(){ return titanNowMs() < (titanLedgerDirtyUntil || 0) || titanLedgerSaveInFlight || titanLedgerCommitInFlightCount > 0; }
        // LEDGER_REALTIME_NO_FLASH_v48:
        // Keep optimistic ledger edits in memory only. This is not a browser-storage
        // source of truth; it only protects the currently edited card from a stale
        // live-sync response that started before the user's latest keystroke/status tap.
        let titanLedgerOptimisticPatches = {};
        let titanLedgerLocalMutationSeq = 0;
        function titanReadPendingLedgerPatches(){
            try { localStorage.removeItem(TITAN_LEDGER_PATCH_KEY); } catch(e){}
            return titanPrunePendingLedgerPatches();
        }
        function titanWritePendingLedgerPatches(obj){
            titanLedgerOptimisticPatches = obj && typeof obj === 'object' ? obj : {};
            try { localStorage.removeItem(TITAN_LEDGER_PATCH_KEY); } catch(e){}
        }
        function titanPrunePendingLedgerPatches(){
            const now = titanNowMs();
            const out = {};
            Object.entries(titanLedgerOptimisticPatches || {}).forEach(([k, patch]) => {
                if(!patch || !patch.rec) return;
                const ts = Number(patch.ts || patch.rec._dirtyAt || patch.rec._updatedAt || 0);
                if(ts && now - ts > TITAN_LEDGER_PATCH_EXPIRY_MS) return;
                out[k] = patch;
            });
            titanLedgerOptimisticPatches = out;
            return out;
        }
        function titanPatchDictForType(type){ return type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData'); }
        function titanLedgerPatchKey(date, profileId, type, marketKey){ return [date || currentDate, profileId || 'admin1', type || '', marketKey || ''].join('|'); }
        function titanCopyLedgerRecordForPatch(rec){
            const out = {}; rec = rec || {};
            ['s','d','r','od','trick','schTime','schTargets','_ledgerKey','_marketName','_ledgerType','_ledgerIndex','_ledgerDate','_updatedAt','_dirtyAt','_sourceAction','_manualStatusAt','_manualStatusBy','_explicitClearedAt','_digitClearedAt','_rateClearedAt','_resetAt','_deleted','_deletedAt','_deletedBy','deleted','deletedAt','_manualR','_autoR','_digitsTouchedAt','_manualRateAt','_autoRateAt','_autoRateReason','_recoveryAutoR','_recoveryDebt','_recoveryUnreal','_recoveryMargin','_recoveryTargetProfit','_recoveryTrackKey','_recoveryFromIdx','_recoveryBaseRate'].forEach(k => { if(typeof rec[k] !== 'undefined') out[k] = rec[k]; });
            return JSON.parse(JSON.stringify(out));
        }
        function titanDeletedLedgerFieldsForPatch(rec){
            const del = []; rec = rec || {};
            ['trick','od','autoMarkedAt','autoMarkedByResult','autoMarkStage','autoMarkMarket','autoMarkWinDigit'].forEach(k => { if(typeof rec[k] === 'undefined') del.push(k); });
            return del;
        }
        function recordLedgerLocalPatch(profileId, type, idx, marketKey, rec, action){
            try { titanMarkLedgerDirty(); } catch(e){}
            try {
                const pid = profileId || appState.activeId || 'admin1';
                const key = titanLedgerPatchKey(currentDate, pid, type, marketKey || (rec && rec._ledgerKey) || idx);
                const patchRec = annotateLedgerRecord(titanCopyLedgerRecordForPatch(rec || {}), type, parseInt(idx, 10), marketKey || (rec && rec._ledgerKey) || '');
                patchRec._dirtyAt = patchRec._dirtyAt || titanNowMs();
                patchRec._sourceAction = action || patchRec._sourceAction || 'local_ledger_edit';
                titanLedgerLocalMutationSeq += 1;
                titanLedgerOptimisticPatches[key] = {ts: titanNowMs(), seq: titanLedgerLocalMutationSeq, profileId: pid, date: currentDate, type, idx: parseInt(idx,10), marketKey: marketKey || (rec && rec._ledgerKey) || '', rec: patchRec};
            } catch(e) {}
        }
        function applyPendingLedgerPatchesToState(targetState){
            try { localStorage.removeItem(TITAN_LEDGER_PATCH_KEY); } catch(e){}
            if(!targetState || !targetState.profiles) return targetState;
            const patches = titanPrunePendingLedgerPatches();
            Object.values(patches || {}).forEach(patch => {
                try {
                    const pid = patch.profileId || targetState.activeId || appState.activeId || 'admin1';
                    const pState = targetState.profiles && targetState.profiles[pid];
                    if(!pState || !patch.rec) return;
                    if(!pState.dayRecords) pState.dayRecords = {};
                    if(!pState.dayRecords[patch.date]) pState.dayRecords[patch.date] = {};
                    const dictName = titanPatchDictForType(patch.type);
                    if(!pState.dayRecords[patch.date][dictName]) pState.dayRecords[patch.date][dictName] = {};
                    const idxNum = parseInt(patch.idx, 10);
                    const existing = pState.dayRecords[patch.date][dictName][idxNum] || {};
                    const serverAt = Number(existing._updatedAt || 0);
                    const localAt = Number(patch.rec._updatedAt || patch.rec._dirtyAt || patch.ts || 0);
                    // Only overlay when local edit is newer/equal. This prevents old Firebase
                    // snapshots from flashing old digits/rates/status, while still letting a
                    // genuinely newer server write win later.
                    if(!serverAt || !localAt || localAt >= serverAt){
                        pState.dayRecords[patch.date][dictName][idxNum] = Object.assign({}, existing, JSON.parse(JSON.stringify(patch.rec)));
                    }
                } catch(e) {}
            });
            return targetState;
        }

        let titanLedgerCommitSeq = 0;
        let titanLedgerCommitInFlightCount = 0;
        const titanLedgerCommitTimers = {};
        const titanLedgerCommitLatestSeq = {};
        function titanLedgerCommitKey(profileId, type, idx, marketKey){ return [currentDate, profileId || appState.activeId || 'admin1', type || '', marketKey || idx].join('|'); }
        async function titanCommitLedgerRecordToFirebase(profileId, type, idx, marketKey, rec, action, applyToVips=false, forceNow=false){
            if(!IS_MASTER || !rec || !type || idx < 0) return null;
            const commitKey = titanLedgerCommitKey(profileId, type, idx, marketKey);
            const inputCommit = ['digit_with_auto_rate','manual_rate'].includes(String(action || ''));
            if(inputCommit && !forceNow){
                titanLedgerSaveInFlight = true;
                titanMarkLedgerDirty();
                const recSnapshot = JSON.parse(JSON.stringify(rec || {}));
                clearTimeout(titanLedgerCommitTimers[commitKey]);
                titanLedgerCommitTimers[commitKey] = setTimeout(() => {
                    titanCommitLedgerRecordToFirebase(profileId, type, idx, marketKey, recSnapshot, action, applyToVips, true);
                }, 450);
                return null;
            }
            const seq = ++titanLedgerCommitSeq;
            titanLedgerCommitLatestSeq[commitKey] = seq;
            titanLedgerSaveInFlight = true;
            titanMarkLedgerDirty();
            const payload = {
                activeId: 'admin1',
                profileId: profileId || appState.activeId || 'admin1',
                date: currentDate,
                type,
                idx: parseInt(idx, 10),
                marketKey: marketKey || (rec && rec._ledgerKey) || '',
                action: action || (rec && rec._sourceAction) || 'ledger_card_update',
                applyToVips: !!applyToVips,
                record: JSON.parse(JSON.stringify(rec || {}))
            };
            titanLedgerCommitInFlightCount += 1;
            try {
                const res = await fetch('/api/ledger_card_update', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json().catch(() => ({}));
                if(!res.ok || data.status !== 'success') throw new Error(data.message || 'Ledger Firebase commit failed');
                if(data.records && appState.profiles && titanLedgerCommitLatestSeq[commitKey] === seq){
                    Object.entries(data.records).forEach(([pid, serverRec]) => {
                        const pState = appState.profiles[pid];
                        if(!pState) return;
                        ensureDataStructForProfile(pState);
                        const op = ensureLedgerRecordBoundForProfile(pState, pid, type, idx, marketKey, true);
                        pState.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(serverRec, type, op.idx, op.key);
                    });
                }
                if(data.ledgerSchedules) appState.ledgerSchedules = data.ledgerSchedules;
                try { localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
                titanLedgerDirtyUntil = Math.max(titanLedgerDirtyUntil || 0, titanNowMs() + 1500);
                // Keep optimistic patch briefly after success so an already-in-flight
                // /api/state response cannot flash the old value, then remove it.
                setTimeout(() => {
                    try {
                        const p = titanLedgerOptimisticPatches[commitKey];
                        if(p && p.seq <= seq) delete titanLedgerOptimisticPatches[commitKey];
                    } catch(e) {}
                }, 1800);
                return data;
            } catch(e){
                titanLedgerDirtyUntil = Math.max(titanLedgerDirtyUntil || 0, titanNowMs() + 10000);
                showRealNotification('❌ Firebase Ledger Save', String(e.message || e) + ' — local card hold kiya gaya, auto-sync overwrite nahi karega.', 'danger');
                return null;
            } finally {
                setTimeout(() => {
                    titanLedgerCommitInFlightCount = Math.max(0, titanLedgerCommitInFlightCount - 1);
                    if(titanLedgerCommitInFlightCount === 0) titanLedgerSaveInFlight = false;
                }, 1200);
            }
        }

        function titanCommitLedgerAutoRateUpdates(updates, sourceAction='recovery_auto_rate'){
            if(!IS_MASTER || !Array.isArray(updates) || !updates.length) return;
            const seen = new Set();
            updates.forEach(u => {
                if(!u || !u.rec || !u.type || typeof u.idx === 'undefined') return;
                const k = titanLedgerCommitKey(appState.activeId || 'admin1', u.type, u.idx, u.key || u.marketKey || '');
                if(seen.has(k)) return;
                seen.add(k);
                const rec = annotateLedgerRecord(JSON.parse(JSON.stringify(u.rec || {})), u.type, parseInt(u.idx, 10), u.key || u.marketKey || '');
                updateLedgerScheduleStore(appState.activeId || 'admin1', u.type, parseInt(u.idx, 10), rec, u.key || u.marketKey || '');
                titanCommitLedgerRecordToFirebase(appState.activeId || 'admin1', u.type, parseInt(u.idx, 10), u.key || u.marketKey || '', rec, u.action || sourceAction, appState.activeId === 'admin1');
            });
        }


        // ── Payment UPI config v11: use Firebase admin paymentMethods, no hardcoded production UPI IDs. ──
        function titanPaymentMethods(){ return (appState && appState.paymentMethods) || {}; }
        function titanUpiFor(appId){
            const pm = titanPaymentMethods();
            const map = pm.upis || {};
            return map[appId] || pm[appId + 'Upi'] || pm.upi || '';
        }
        function titanPaymentName(){
            const pm = titanPaymentMethods();
            return pm.name || (TITAN_APP_CONFIG && TITAN_APP_CONFIG.paymentName) || 'TITAN NOVA';
        }

        window.shareModalOpen = false;
        window.targetPickerOpen = false;
        function pushNativeState() { history.pushState({nova: true}, '', window.location.href); }

        window.addEventListener("popstate", function(e) {
            if (window.targetPickerOpen) { closeTargetPicker(true); }
            else if (window.shareModalOpen) { closeShareModal(true); }
            else if (IS_MASTER && appState.activeId !== 'admin1') { appState.activeId = 'admin1'; state = appState.profiles['admin1']; setMainNav('clients'); }
            else if (mainNav !== 'ledger') { setMainNav('ledger'); }
        });

        function backToMasterUI() {
            if (!IS_MASTER) return;
            if (window.history.state && window.history.state.nova) { history.back(); }
            else { appState.activeId = 'admin1'; state = appState.profiles['admin1']; setMainNav('clients'); }
        }

        function closeShareModal(fromHistory = false) {
            document.getElementById('shareModal').classList.remove('open');
            window.shareModalOpen = false;
            if(!fromHistory) { if(window.history.state && window.history.state.nova) history.back(); }
        }

        function requestNotificationPermission() {
            if (!("Notification" in window)) {
                showRealNotification('⚠️ Not Supported', 'Aapka phone notifications support nahi karta.', 'danger');
                return;
            }
            if (Notification.permission !== "granted" && Notification.permission !== "denied") {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") {
                        showRealNotification('✅ Notifications ON!', 'Ab aapko phone par direct alerts milenge!', 'success');
                        renderAppBar();
                    } else {
                        showRealNotification('❌ Permission Denied', 'Notifications allow nahi kiye gaye.', 'danger');
                    }
                });
            } else if (Notification.permission === "granted") {
                showRealNotification('🔔 Already Active', 'Native Notifications pehle se on hain.', 'success');
            } else {
                showRealNotification('⚠️ Blocked', 'Browser settings mein notifications allow karein.', 'danger');
            }
        }

        function showRealNotification(title, body, type='info') {
            const container = document.getElementById('push-container');
            const toast = document.createElement('div');
            toast.className = 'tg-toast';

            const icons = {
                info:    { icon: 'fa-bullhorn',            cls: 'info'    },
                success: { icon: 'fa-check',               cls: 'success' },
                danger:  { icon: 'fa-exclamation-triangle', cls: 'danger'  }
            };
            const ic = icons[type] || icons.info;

            toast.innerHTML = `
                <div class="tg-toast-icon ${ic.cls}"><i class="fas ${ic.icon}"></i></div>
                <div class="tg-toast-body flex-1 min-w-0">
                    <h4>${title}</h4>
                    <p>${body}</p>
                </div>
                <button onclick="this.parentElement.classList.remove('show');setTimeout(()=>this.parentElement.remove(),350)" class="text-[var(--text-muted)] text-xs w-5 h-5 flex items-center justify-center shrink-0 opacity-60">
                    <i class="fas fa-times"></i>
                </button>`;

            toast.onclick = (e) => {
                if(e.target.closest('button')) return;
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 350);
            };

            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => { if(toast.parentElement) { toast.classList.remove('show'); setTimeout(() => toast.remove(), 350); } }, 6000);

            if ("Notification" in window && Notification.permission === "granted") {
                navigator.serviceWorker.ready.then((registration) => {
                    registration.showNotification(title, {
                        body: body,
                        icon: '/icon.svg',
                        badge: '/icon.svg',
                        vibrate: [150, 80, 150]
                    });
                }).catch(()=>{});
            }
        }

        function checkTargetsAndLimits() {
            if (IS_MASTER) return;
            ['ank', 'jodi', 'pannel'].forEach(type => {
                let stats = globalStats[type];
                let cfg = state.config[type];
                let tgt = parseFloat(cfg.tgt) || 0;
                let cap = parseFloat(cfg.cap) || 0;

                let keyPrefix = `TITAN_ALERT_${appState.activeId}_${currentDate}_${type}`;

                if (tgt > 0 && stats.pl >= tgt) {
                    if (!localStorage.getItem(keyPrefix+'_tgt')) {
                        showRealNotification('🎯 Target Hit!', `Aapka ${type.toUpperCase()} ka target (₹${tgt}) pura ho gaya hai!`, 'success');
                        localStorage.setItem(keyPrefix+'_tgt', '1');
                    }
                }

                if (cap > 0 && stats.pl <= -cap) {
                    if (!localStorage.getItem(keyPrefix+'_cap')) {
                        showRealNotification('⚠️ Capital Risk!', `Dhyan de! Aapka ${type.toUpperCase()} ka loss limit (-₹${cap}) cross ho gaya hai.`, 'danger');
                        localStorage.setItem(keyPrefix+'_cap', '1');
                    }
                }
            });
        }

        // ==========================================
        // AUTO-SYNC FIX: STOP RENDER LOOP ON MEMBERSHIP TAB
        // ==========================================
        if (!IS_MASTER) {
            setInterval(async () => {
                try {
                    let res = await fetch('/api/state?live_sync=1&_fast=1&_=' + Date.now(), {cache:'no-store'});
                    if(!res.ok) return;
                    let newState = await res.json();

                    let lastBcast = parseInt(localStorage.getItem('TITAN_BCAST_LAST') || '0');
                    let maxId = lastBcast;
                    if(newState.broadcasts) {
                        newState.broadcasts.forEach(b => {
                            if(b.id > lastBcast) {
                                showRealNotification(b.title, b.msg, 'info');
                                if(b.id > maxId) maxId = b.id;
                            }
                        });
                    }
                    if(maxId > lastBcast) localStorage.setItem('TITAN_BCAST_LAST', maxId.toString());

                    if(newState.profiles && newState.profiles[appState.activeId]) {
                        function sortedStringify(obj) {
                            if (obj !== null && typeof obj === 'object') {
                                if (Array.isArray(obj)) return '[' + obj.map(sortedStringify).join(',') + ']';
                                return '{' + Object.keys(obj).sort().map(k => '"' + k + '":' + sortedStringify(obj[k])).join(',') + '}';
                            }
                            return JSON.stringify(obj);
                        }

                        let localRec = appState.profiles[appState.activeId].dayRecords[currentDate] || {};
                        let fetchedRec = newState.profiles[appState.activeId].dayRecords[currentDate] || {};
                        let currentLocalStateStr = sortedStringify(localRec);
                        let fetchedStateStr = sortedStringify(fetchedRec);

                        let currentAccess = appState.profiles[appState.activeId].vipAccessEnabled;
                        let fetchedAccess = newState.profiles[appState.activeId].vipAccessEnabled;

                        if (currentLocalStateStr !== fetchedStateStr || currentAccess !== fetchedAccess) {
                            if(titanLedgerHasLocalDirty()) return;
                            appState = applyPendingLedgerPatchesToState(newState);
                            state = appState.profiles[appState.activeId];

                            // ── Save VIP state to localStorage (mobile offline support) ──
                            try { localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}

                            let activeTag = document.activeElement ? document.activeElement.tagName : '';
                            let isTyping = (activeTag === 'INPUT' || activeTag === 'TEXTAREA');
                            let isSafeTab = (mainNav === 'ledger' || mainNav === 'audit');

                            if (isSafeTab && !isTyping) {
                                render(true);
                            }
                        } else {
                            // Always update payments + broadcasts in localStorage even if ledger didn't change
                            appState.payments = (newState.payments || []).filter(p => p.userId === appState.activeId);
                            appState.broadcasts = newState.broadcasts || [];
                            try { localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
                        }
                    }
                } catch(e) {}
            }, TITAN_VIP_REALTIME_SYNC_MS);
        }

        function showToast(msg, color='blue') {
            const typeMap = { blue:'info', green:'success', cyan:'info', rose:'danger', red:'danger', emerald:'success' };
            showRealNotification('Titan Nova', msg, typeMap[color] || 'info');
        }


        // ==========================================
        // WALLET FOUNDATION UI HELPERS
        // ==========================================
        function ensureWalletStruct(){
            if(!appState.wallets) appState.wallets = {};
            if(!appState.walletSettings) appState.walletSettings = {defaultCreditLimit:0, requirePositiveBalance:false, walletEnabled:true, currency:'₹'};
            if(!Array.isArray(appState.walletTransactions)) appState.walletTransactions = [];
        }
        function walletCurrency(){ ensureWalletStruct(); return appState.walletSettings.currency || '₹'; }
        function fmtMoney(v){
            const n = Number(v || 0);
            const clean = Number.isInteger(n) ? String(n) : n.toFixed(2);
            return walletCurrency() + clean;
        }
        function htmlEscape(v){
            return String(v == null ? '' : v)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
        function attrEscape(v){ return htmlEscape(v); }


        // ==========================================
        // ADVANCED WHATSAPP TARGET PICKER
        // ==========================================
        const TARGET_LISTS_STORAGE_KEY = 'titanTargetListsV1';
        let targetPickerState = null;

        function cleanTargetId(id){ return String(id == null ? '' : id).trim(); }
        function targetTypeFromId(id){ return String(id || '').includes('@g.us') ? 'group' : 'contact'; }
        function normalizeTargetType(type, id){
            const t = String(type || '').toLowerCase();
            if(t.includes('group') || String(id || '').includes('@g.us')) return 'group';
            if(t.includes('manual')) return 'manual';
            if(t.includes('saved')) return 'saved';
            return 'contact';
        }
        function targetIcon(type){
            type = normalizeTargetType(type, '');
            if(type === 'group') return 'fa-users';
            if(type === 'manual') return 'fa-keyboard';
            if(type === 'saved') return 'fa-bookmark';
            return 'fa-user';
        }
        function targetTypeLabel(type){
            type = normalizeTargetType(type, '');
            if(type === 'group') return 'Group';
            if(type === 'manual') return 'Manual';
            if(type === 'saved') return 'Saved';
            return 'Contact';
        }
        function humanTargetId(id){
            let v = cleanTargetId(id);
            if(v.endsWith('@s.whatsapp.net')) v = v.replace('@s.whatsapp.net','');
            if(v.endsWith('@c.us')) v = v.replace('@c.us','');
            if(v.endsWith('@g.us')) return v.replace('@g.us','');
            return v;
        }
        function targetLabelFromObj(o){
            if(!o) return '';
            const id = cleanTargetId(o.id || o.jid || o.phone || '');
            const raw = cleanTargetId(o.name || o.subject || o.notify || o.pushName || '');
            if(raw && raw !== id && raw !== humanTargetId(id)) return raw;
            return humanTargetId(id) || id;
        }
        function mergeTargetOptions(existing, extra){
            const map = new Map();
            (existing || []).concat(extra || []).forEach(o => {
                const id = cleanTargetId(o && (o.id || o.jid || o.phone));
                if(!id) return;
                const prev = map.get(id) || {};
                map.set(id, {
                    id,
                    name: targetLabelFromObj(o) || prev.name || humanTargetId(id),
                    type: normalizeTargetType(o.type || o.kind || prev.type, id)
                });
            });
            return Array.from(map.values());
        }
        function readSavedTargetLists(){
            try{
                const raw = localStorage.getItem(TARGET_LISTS_STORAGE_KEY) || '{}';
                const parsed = JSON.parse(raw);
                return (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : {};
            }catch(e){ return {}; }
        }
        function writeSavedTargetLists(lists){ localStorage.setItem(TARGET_LISTS_STORAGE_KEY, JSON.stringify(lists || {})); }
        function knownTargetOptions(){
            let opts = [];
            if(appState.waTargetOptions && Array.isArray(appState.waTargetOptions.options)) opts = opts.concat(appState.waTargetOptions.options);
            if(Array.isArray(appState.forwardTargetOptions)) opts = opts.concat(appState.forwardTargetOptions);
            if(Array.isArray(appState.resultTargets)) opts = opts.concat(appState.resultTargets.map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)})));
            if(appState.loadForwarder && Array.isArray(appState.loadForwarder.targets)) opts = opts.concat(appState.loadForwarder.targets.map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)})));
            const ws = appState.withdrawalSettings || {};
            if(Array.isArray(ws.adminNotifyTargets)) opts = opts.concat(ws.adminNotifyTargets.map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)})));
            try{ Object.values(readSavedTargetLists()).forEach(list => (list.targets || []).forEach(t => opts.push({id:t, name:humanTargetId(t), type:targetTypeFromId(t)}))); }catch(e){}
            return mergeTargetOptions([], opts);
        }
        async function fetchWhatsappTargetOptions(){
            const fallback = knownTargetOptions();
            try{
                const res = await fetch('/api/wa_targets', {cache:'no-store'});
                const text = await res.text();
                let data = {};
                try{ data = JSON.parse(text); }catch(parseErr){ throw new Error(text.slice(0,80) || 'Invalid target response'); }
                const opts = [];
                (data.groups || []).forEach(g => opts.push({id:g.id || g.jid, name:g.name || g.subject || g.id || g.jid, type:'group'}));
                (data.contacts || []).forEach(c => opts.push({id:c.id || c.jid || c.phone, name:c.name || c.pushName || c.notify || c.id || c.jid || c.phone, type:'contact'}));
                const merged = mergeTargetOptions(fallback, opts);
                appState.waTargetOptions = {options: merged, loadedAt: Date.now(), status: data.status || 'success'};
                appState.forwardTargetOptions = mergeTargetOptions(appState.forwardTargetOptions || [], merged);
                return merged;
            }catch(e){ if(fallback.length) return fallback; throw e; }
        }
        function selectedTargetSummary(targets, max=3){
            const arr = (targets || []).filter(Boolean);
            if(!arr.length) return '<span class="text-[var(--text-muted)]">No target selected</span>';
            const lookup = new Map(knownTargetOptions().map(o => [o.id, o]));
            const shown = arr.slice(0,max).map(id => {
                const o = lookup.get(id) || {id, name:humanTargetId(id), type:targetTypeFromId(id)};
                return `<span class="inline-flex items-center gap-1 max-w-full bg-[rgba(42,171,238,0.10)] border border-[rgba(42,171,238,0.18)] text-[var(--primary)] rounded-lg px-2 py-1 text-[9px] font-black uppercase"><i class="fas ${targetIcon(o.type)}"></i><span class="truncate max-w-[130px]">${htmlEscape(o.name || humanTargetId(id))}</span></span>`;
            }).join('');
            const more = arr.length > max ? `<span class="text-[9px] text-[var(--text-muted)] font-bold">+${arr.length-max} more</span>` : '';
            return `<div class="flex flex-wrap gap-1.5 items-center">${shown}${more}</div>`;
        }

        function marketRoleField(role){ return ({entry:'entryTargets', schedule:'scheduleTargets', result:'resultTargets', forward:'forwardTargets', bookie:'bookieTargets', admin:'bookieTargets'})[String(role||'').toLowerCase()] || 'entryTargets'; }
        function marketRoleLabel(role){ return ({entry:'Game Entry', schedule:'Ledger Schedule', result:'Results', forward:'Forward/Load', bookie:'Bookie/Admin Work', admin:'Bookie/Admin Work'})[String(role||'').toLowerCase()] || 'Entry'; }
        function marketRoleTargetsForItem(item, role){ const field = marketRoleField(role); return Array.isArray(item && item[field]) ? item[field].slice() : []; }
        function marketEntryTargetsForItem(item){ return marketRoleTargetsForItem(item, 'entry'); }
        function openMarketRoleTargetPicker(id, role){
            const item = ensureMarketRegistry().items[id];
            if(!item) return showRealNotification('⚠️ Market Error','Market not found','warning');
            openTargetPicker('marketRole', {marketId:id, role, title:`${item.displayName || item.name} ${marketRoleLabel(role)} Targets`});
        }
        function openMarketEntryTargetPicker(id){ openMarketRoleTargetPicker(id, 'entry'); }
        async function saveMarketRoleTargets(id, role, targets){
            const item = ensureMarketRegistry().items[id];
            if(!item) throw new Error('Market not found');
            const field = marketRoleField(role);
            item[field] = Array.from(new Set((targets || []).filter(Boolean)));
            if(role === 'entry') item.entryEnabled = item.entryEnabled !== false;
            const data = await marketAction('set_role_targets', {id, role, targets:item[field], entryEnabled:item.entryEnabled}, false);
            if(!data) throw new Error('Target save failed');
            render(true);
            showRealNotification('✅ Targets Saved', `${marketRoleLabel(role)}: ${item[field].length} target saved for ${item.displayName || item.name}`,'success');
        }
        async function saveMarketEntryTargets(id, targets){ return saveMarketRoleTargets(id, 'entry', targets); }
        function roleTargetRow(item, role, icon, hint){
            const field = marketRoleField(role);
            return `<div class="bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-2"><div class="flex items-center justify-between gap-2 mb-1"><div class="text-[8px] font-black uppercase text-[var(--text-muted)]"><i class="fas ${icon} mr-1"></i>${marketRoleLabel(role)}</div><button onclick="openMarketRoleTargetPicker('${attrEscape(item.id)}','${role}')" class="bg-[var(--primary)] text-white px-2.5 py-1.5 rounded-lg font-black text-[8px] uppercase">Choose</button></div>${selectedTargetSummary(item[field] || [], 2)}<p class="mt-1 text-[7px] text-[var(--text-muted)]">${hint}</p></div>`;
        }

        function targetPickerTitleForContext(ctx){
            if(ctx === 'result') return 'Result Send Targets';
            if(ctx === 'ledger') return 'Ledger Schedule Targets';
            if(ctx === 'forward') return 'Load Forward Targets';
            if(ctx === 'withdrawAdmin') return 'Withdrawal Admin Notify';
            if(ctx === 'entryMarket') return 'Market Entry Targets';
            if(ctx === 'marketRole') return 'Market Role Targets';
            return 'WhatsApp Targets';
        }
        async function openTargetPicker(context, meta={}){
            if(!IS_MASTER) return;
            let selected = [];
            if(context === 'result') { ensureResultStruct(); selected = (appState.resultTargets || []).slice(); }
            else if(context === 'forward') { ensureLoadForwarderStruct(); selected = (appState.loadForwarder.targets || []).slice(); }
            else if(context === 'withdrawAdmin') { ensureWithdrawalStruct(); selected = ((appState.withdrawalSettings || {}).adminNotifyTargets || []).slice(); }
            else if(context === 'entryMarket') { const item = ensureMarketRegistry().items[meta.marketId]; selected = marketEntryTargetsForItem(item); }
            else if(context === 'marketRole') { const item = ensureMarketRegistry().items[meta.marketId]; selected = marketRoleTargetsForItem(item, meta.role); }
            else if(context === 'ledger') {
                ensureDataStruct();
                const op = resolveLedgerAction(meta.type, meta.idx, meta.marketKey);
                meta.idx = op.idx; meta.marketKey = op.key;
                selected = (op.rec.schTargets || []).slice();
            }
            targetPickerState = {context, meta, title:meta.title || targetPickerTitleForContext(context), selected:Array.from(new Set(selected.filter(Boolean))), options:knownTargetOptions(), tab:meta.tab || 'groups', search:'', showSelected:false, loading:true};
            renderTargetPicker(); pushNativeState();
            document.getElementById('targetPickerModal')?.classList.add('open');
            window.targetPickerOpen = true;
            try{ refreshWhatsappSafetyState(true).catch(()=>{}); }catch(e){}
            try{
                const opts = await fetchWhatsappTargetOptions();
                if(targetPickerState && targetPickerState.context === context){
                    const selectedOpts = targetPickerState.selected.map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)}));
                    targetPickerState.options = mergeTargetOptions(opts, selectedOpts);
                    targetPickerState.loading = false; renderTargetPicker();
                }
            }catch(e){
                if(targetPickerState){ targetPickerState.loading = false; renderTargetPicker(); }
                showRealNotification('⚠️ Gateway Offline', 'Saved/manual targets available hain. Latest WhatsApp list ke liye Gateway run karo.', 'info');
            }
        }
        function closeTargetPicker(fromHistory=false){
            document.getElementById('targetPickerModal')?.classList.remove('open');
            window.targetPickerOpen = false; targetPickerState = null;
            if(!fromHistory) { if(window.history.state && window.history.state.nova) history.back(); }
        }
        function setTargetPickerTab(tab){ if(!targetPickerState) return; targetPickerState.tab = tab; targetPickerState.showSelected = false; renderTargetPicker(); }
        function setTargetPickerSearch(value){ if(!targetPickerState) return; targetPickerState.search = String(value || ''); titanQueueTargetPickerRenderAfterTyping(); }
        function toggleTargetPickerSelectedOnly(){ if(!targetPickerState) return; targetPickerState.showSelected = !targetPickerState.showSelected; renderTargetPicker(); }
        function toggleTargetPickerId(id, checked){
            if(!targetPickerState) return;
            id = cleanTargetId(id); const set = new Set(targetPickerState.selected || []);
            if(checked) set.add(id); else set.delete(id);
            targetPickerState.selected = Array.from(set); renderTargetPicker();
        }
        function clearTargetPickerSelection(){ if(!targetPickerState) return; targetPickerState.selected = []; renderTargetPicker(); }
        function addManualTargetFromPicker(){
            if(!targetPickerState) return;
            const raw = document.getElementById('target-picker-manual')?.value || '';
            const parts = titanCleanTargets(raw);
            if(!parts.length) return showRealNotification('⚠️ Empty', 'Phone/JID paste karo.', 'danger');
            targetPickerState.options = mergeTargetOptions(targetPickerState.options || [], parts.map(t => ({id:t, name:humanTargetId(t), type:'manual'})));
            const set = new Set(targetPickerState.selected || []); parts.forEach(t => set.add(t));
            targetPickerState.selected = Array.from(set);
            const input = document.getElementById('target-picker-manual'); if(input) input.value = '';
            renderTargetPicker();
        }
        function saveSelectionAsTargetList(){
            if(!targetPickerState || !targetPickerState.selected.length) return showRealNotification('⚠️ No Selection', 'Pehle targets select karo.', 'danger');
            const name = prompt('Saved list name:', targetPickerState.title || 'My Targets'); if(!name) return;
            const key = 'list_' + Date.now(); const lists = readSavedTargetLists();
            lists[key] = {id:key, name:String(name).trim(), targets:targetPickerState.selected.slice(), createdAt:new Date().toISOString()};
            writeSavedTargetLists(lists);
            showRealNotification('✅ List Saved', `${targetPickerState.selected.length} targets saved as ${name}.`, 'success');
            targetPickerState.tab = 'lists'; renderTargetPicker();
        }
        function applySavedTargetList(key){
            if(!targetPickerState) return;
            const list = readSavedTargetLists()[key]; if(!list) return;
            const set = new Set(targetPickerState.selected || []); (list.targets || []).forEach(t => set.add(t));
            targetPickerState.selected = Array.from(set);
            targetPickerState.options = mergeTargetOptions(targetPickerState.options || [], (list.targets || []).map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)})));
            renderTargetPicker();
        }
        function deleteSavedTargetList(key){
            const lists = readSavedTargetLists(); if(!lists[key]) return;
            if(!confirm('Saved target list delete karni hai?')) return;
            delete lists[key]; writeSavedTargetLists(lists); renderTargetPicker();
        }
        function targetPickerFilteredOptions(){
            if(!targetPickerState) return [];
            const q = String(targetPickerState.search || '').trim().toLowerCase();
            const sel = new Set(targetPickerState.selected || []);
            let opts = mergeTargetOptions(targetPickerState.options || [], targetPickerState.selected.map(t => ({id:t, name:humanTargetId(t), type:targetTypeFromId(t)})));
            if(targetPickerState.showSelected) opts = opts.filter(o => sel.has(o.id));
            if(targetPickerState.tab === 'groups') opts = opts.filter(o => normalizeTargetType(o.type, o.id) === 'group');
            else if(targetPickerState.tab === 'contacts') opts = opts.filter(o => normalizeTargetType(o.type, o.id) !== 'group');
            if(q) opts = opts.filter(o => String(o.name || '').toLowerCase().includes(q) || String(o.id || '').toLowerCase().includes(q) || humanTargetId(o.id).toLowerCase().includes(q));
            opts.sort((a,b) => { const as = sel.has(a.id) ? 0 : 1, bs = sel.has(b.id) ? 0 : 1; if(as !== bs) return as - bs; return String(a.name || a.id).localeCompare(String(b.name || b.id)); });
            return opts;
        }
        function renderTargetPicker(){
            if(titanTypingActive()) { titanQueueTargetPickerRenderAfterTyping(); return; }
            const root = document.getElementById('target-picker-content'); if(!root || !targetPickerState) return;
            const sel = new Set(targetPickerState.selected || []);
            const opts = targetPickerFilteredOptions();
            const lists = readSavedTargetLists();
            const listKeys = Object.keys(lists).sort((a,b)=>String(lists[b].createdAt||'').localeCompare(String(lists[a].createdAt||'')));
            const tabBtn = (tab,label,icon) => `<button onclick="setTargetPickerTab('${tab}')" class="flex-1 py-2 rounded-xl font-black text-[10px] uppercase border ${targetPickerState.tab===tab?'bg-[var(--primary)] text-white border-[var(--primary)]':'bg-[var(--surface-light)] text-[var(--text-muted)] border-[var(--border)]'}"><i class="fas ${icon} mr-1"></i>${label}</button>`;
            let body = '';
            if(targetPickerState.tab === 'lists'){
                body = listKeys.length ? listKeys.map(k => { const l = lists[k]; return `<div class="bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 mb-2"><div class="flex items-start justify-between gap-2"><div class="min-w-0"><p class="text-white font-black text-[12px] truncate">${htmlEscape(l.name || 'Saved List')}</p><p class="text-[var(--text-muted)] text-[9px] mt-0.5">${(l.targets||[]).length} targets</p></div><div class="flex gap-2 shrink-0"><button onclick="applySavedTargetList('${attrEscape(k)}')" class="bg-[var(--green)] text-white px-3 py-2 rounded-lg font-black text-[9px] uppercase">Use</button><button onclick="deleteSavedTargetList('${attrEscape(k)}')" class="bg-[rgba(255,93,93,0.12)] text-[var(--rose)] border border-[rgba(255,93,93,0.25)] px-3 py-2 rounded-lg font-black text-[9px] uppercase"><i class="fas fa-trash"></i></button></div></div>${selectedTargetSummary(l.targets || [], 4)}</div>`; }).join('') : `<div class="text-center p-6 text-[var(--text-muted)] text-xs">Abhi saved target list nahi hai. Groups/Contacts select karke Save as List dabao.</div>`;
            } else {
                body = opts.length ? opts.map(o => { const checked = sel.has(o.id); const t = normalizeTargetType(o.type, o.id); return `<label class="flex items-center gap-3 bg-[var(--surface-light)] border ${checked?'border-[var(--primary)]':'border-[var(--border)]'} rounded-xl p-3 mb-2 active:scale-[0.99] transition-all"><input type="checkbox" class="w-4 h-4" ${checked?'checked':''} onchange="toggleTargetPickerId('${attrEscape(o.id)}', this.checked)"><div class="w-9 h-9 rounded-xl ${t==='group'?'bg-[rgba(0,194,111,0.13)] text-[var(--green)]':'bg-[rgba(42,171,238,0.13)] text-[var(--primary)]'} flex items-center justify-center shrink-0"><i class="fas ${targetIcon(t)}"></i></div><div class="min-w-0 flex-1"><p class="text-white font-black text-[12px] truncate">${htmlEscape(o.name || humanTargetId(o.id))}</p><p class="text-[var(--text-muted)] text-[9px] truncate">${targetTypeLabel(t)} · ${htmlEscape(humanTargetId(o.id))} ${targetSafetyBadge(o.id)}</p></div></label>`; }).join('') : `<div class="text-center p-6 text-[var(--text-muted)] text-xs">${targetPickerState.loading ? 'WhatsApp list loading...' : 'Is tab me target nahi mila. Search clear karo ya manual add use karo.'}</div>`;
            }
            root.innerHTML = `<div class="px-4 pb-4"><div class="flex items-start justify-between gap-3 mb-3"><div class="min-w-0"><h3 class="text-white font-black text-[15px] uppercase tracking-wide truncate">${htmlEscape(targetPickerState.title)}</h3><p class="text-[var(--text-muted)] text-[10px] mt-0.5">Groups/Contacts alag, search aur checkbox multi-select.</p></div><button onclick="closeTargetPicker()" class="w-9 h-9 rounded-xl bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] shrink-0"><i class="fas fa-times"></i></button></div><div class="grid grid-cols-3 gap-2 mb-2">${tabBtn('groups','Groups','fa-users')}${tabBtn('contacts','Contacts','fa-user')}${tabBtn('lists','Lists','fa-bookmark')}</div><div class="flex gap-2 mb-2"><input id="target-picker-search" value="${attrEscape(targetPickerState.search)}" oninput="setTargetPickerSearch(this.value)" class="native-input text-left text-[12px] py-2.5" placeholder="Search group/contact..."><button onclick="toggleTargetPickerSelectedOnly()" class="px-3 rounded-xl border ${targetPickerState.showSelected?'bg-[var(--amber)] text-black border-[var(--amber)]':'bg-[var(--surface-light)] text-[var(--text-muted)] border-[var(--border)]'} font-black text-[9px] uppercase">Selected</button></div><div class="flex gap-2 mb-3"><input id="target-picker-manual" class="native-input text-left text-[11px] py-2.5" placeholder="Manual phone/JID paste"><button onclick="addManualTargetFromPicker()" class="px-3 rounded-xl bg-[var(--surface-light)] border border-[var(--border)] text-white font-black text-[9px] uppercase">Add</button></div><div class="bg-[#17212B] border border-[var(--border)] rounded-xl p-2 mb-3 min-h-[42px]">${selectedTargetSummary(targetPickerState.selected, 5)}</div><div class="max-h-[45vh] overflow-y-auto no-scrollbar pr-1">${body}</div><div class="grid grid-cols-3 gap-2 mt-4"><button onclick="clearTargetPickerSelection()" class="bg-[rgba(255,93,93,0.08)] text-[var(--rose)] border border-[rgba(255,93,93,0.20)] py-3 rounded-xl font-black text-[9px] uppercase">Clear</button><button onclick="saveSelectionAsTargetList()" class="bg-[rgba(250,199,72,0.12)] text-[var(--amber)] border border-[rgba(250,199,72,0.25)] py-3 rounded-xl font-black text-[9px] uppercase">Save List</button><button onclick="confirmTargetPickerSelection()" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[9px] uppercase">Save ${sel.size}</button></div></div>`;
        }
        async function confirmTargetPickerSelection(){
            if(!targetPickerState) return;
            const ctx = targetPickerState.context, meta = targetPickerState.meta || {};
            const selected = Array.from(new Set((targetPickerState.selected || []).filter(Boolean)));
            try{
                if(ctx === 'result'){
                    ensureResultStruct(); appState.resultTargets = selected;
                    const box = document.getElementById('result-targets-input'); if(box) box.value = selected.join(String.fromCharCode(10));
                    await saveResultTargetsList(selected);
                } else if(ctx === 'ledger'){
                    ensureDataStruct();
                    const op = resolveLedgerAction(meta.type, meta.idx, meta.marketKey);
                    if(op.idx < 0) throw new Error('Ledger card not found');
                    op.rec.schTargets = selected;
                    op.rec = annotateLedgerRecord(op.rec, meta.type, op.idx, op.key);
                    state.dayRecords[currentDate][op.dictName][op.idx] = op.rec;
                    recordLedgerLocalPatch(appState.activeId, meta.type, op.idx, op.key, op.rec, 'targets_save');
                    const saved = await saveScheduleNow(meta.type, op.idx, op.key, null, selected); render(true);
                    if(!saved) throw new Error('Schedule target save failed');
                    showRealNotification('✅ Targets Saved', selected.length + ' ledger schedule target saved.', 'success');
                } else if(ctx === 'forward'){
                    ensureLoadForwarderStruct(); appState.loadForwarder.targets = selected;
                    await saveLoadForwarderSettings();
                } else if(ctx === 'entryMarket'){
                    await saveMarketEntryTargets(meta.marketId, selected);
                } else if(ctx === 'marketRole'){
                    await saveMarketRoleTargets(meta.marketId, meta.role, selected);
                } else if(ctx === 'withdrawAdmin'){
                    ensureWithdrawalStruct(); appState.withdrawalSettings.adminNotifyTargets = selected;
                    const box = document.getElementById('withdraw-admin-targets'); if(box) box.value = selected.join(String.fromCharCode(10));
                    await saveWithdrawalSettings();
                }
                closeTargetPicker();
            }catch(e){ showRealNotification('❌ Target Save Error', String(e.message || e), 'danger'); }
        }
        function openResultTargetPicker(){ openTargetPicker('result'); }
        function openLoadForwardTargetPicker(){ openTargetPicker('forward'); }
        function openWithdrawalAdminTargetPicker(){ openTargetPicker('withdrawAdmin'); }
        function openLedgerTargetPicker(type, idx, marketKey=null){ const realIdx = resolveLedgerIndex(type, idx, marketKey); openTargetPicker('ledger', {type, idx: realIdx, marketKey: marketKey || ledgerMarketKeyForCard(type, (ledgerArrayForType(type)||[])[realIdx] || {})}); }
        function walletForUser(userId){
            ensureWalletStruct();
            const prof = (appState.profiles || {})[userId] || {};
            if(!appState.wallets[userId]) appState.wallets[userId] = {userId, name:prof.name || userId, phone:prof.phone || '', balance:0, creditLimit:Number(appState.walletSettings.defaultCreditLimit || 0), ledger:[]};
            if(!Array.isArray(appState.wallets[userId].ledger)) appState.wallets[userId].ledger = [];
            return appState.wallets[userId];
        }
        function walletClientIds(){
            return Object.keys(appState.profiles || {}).filter(id => !id.startsWith('admin'));
        }
        async function refreshWalletsState(){
            try{
                const res = await fetch('/api/wallets');
                const data = await res.json();
                if(data.status === 'success'){
                    appState.wallets = data.wallets || {};
                    appState.walletSettings = data.walletSettings || appState.walletSettings || {};
                    appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                }
            } catch(e) {}
        }
        async function walletAddSubtract(userId, action){
            if(!IS_MASTER) return;
            const label = action === 'subtract' ? 'Minus amount' : 'Add amount';
            const amountRaw = prompt(label + ' enter karo:');
            if(amountRaw === null) return;
            const amount = Number(String(amountRaw).replace(/[^0-9.]/g,''));
            if(!amount || amount <= 0){ showRealNotification('⚠️ Invalid Amount', 'Amount 0 se zyada hona chahiye.', 'danger'); return; }
            const note = prompt('Note optional:', action === 'subtract' ? 'Manual debit' : 'Manual credit') || '';
            try{
                const res = await fetch('/api/wallet_transaction', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({userId, action, amount, note})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Wallet update failed');
                appState.wallets = data.wallets || appState.wallets;
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                showRealNotification('✅ Wallet Updated', `${userId} ${action === 'subtract' ? 'debited' : 'credited'} ${fmtMoney(amount)}`, 'success');
                render(true);
            } catch(e){ showRealNotification('❌ Wallet Error', String(e.message || e), 'danger'); }
        }
        async function walletSetCredit(userId){
            if(!IS_MASTER) return;
            const w = walletForUser(userId);
            const raw = prompt('Credit limit set karo:', String(w.creditLimit || 0));
            if(raw === null) return;
            const creditLimit = Number(String(raw).replace(/[^0-9.]/g,''));
            if(creditLimit < 0 || Number.isNaN(creditLimit)){ showRealNotification('⚠️ Invalid Credit', 'Credit limit valid number hona chahiye.', 'danger'); return; }
            try{
                const res = await fetch('/api/wallet_credit_limit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({userId, creditLimit})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Credit update failed');
                appState.wallets = data.wallets || appState.wallets;
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                showRealNotification('✅ Credit Limit Updated', `${userId}: ${fmtMoney(creditLimit)}`, 'success');
                render(true);
            } catch(e){ showRealNotification('❌ Credit Error', String(e.message || e), 'danger'); }
        }
        async function walletZeroSettle(userId){
            if(!IS_MASTER) return;
            const w = walletForUser(userId);
            if(!confirm(`Zero settle ${w.name || userId}? Current balance ${fmtMoney(w.balance || 0)} reset ho jayega.`)) return;
            try{
                const res = await fetch('/api/wallet_zero_settle', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({userId, note:'Zero settle from Wallet tab'})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Zero settle failed');
                appState.wallets = data.wallets || appState.wallets;
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                showRealNotification('✅ Zero Settled', `${userId} balance zero ho gaya.`, 'success');
                render(true);
            } catch(e){ showRealNotification('❌ Settle Error', String(e.message || e), 'danger'); }
        }
        async function saveWalletDefaultCredit(){
            if(!IS_MASTER) return;
            const raw = document.getElementById('wallet-default-credit')?.value || '0';
            const defaultCreditLimit = Number(String(raw).replace(/[^0-9.]/g,'')) || 0;
            try{
                const res = await fetch('/api/wallet_settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({defaultCreditLimit})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Settings save failed');
                appState.walletSettings = data.walletSettings || appState.walletSettings;
                showRealNotification('✅ Wallet Settings Saved', 'New clients ke liye default credit update ho gaya.', 'success');
                render(true);
            } catch(e){ showRealNotification('❌ Settings Error', String(e.message || e), 'danger'); }
        }
        function walletLedgerPreview(userId){
            const w = walletForUser(userId);
            const rows = (w.ledger || []).slice(-8).reverse();
            if(!rows.length) return '<p class="text-[10px] text-[var(--text-muted)] mt-3">No wallet ledger yet.</p>';
            return `<div class="mt-3 border-t border-[var(--border)] pt-2 space-y-1">${rows.map(x => {
                const amt = Number(x.amount || 0);
                const cls = amt >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]';
                return `<div class="flex items-start justify-between gap-2 text-[9px]"><div class="min-w-0"><p class="text-white font-bold truncate">${x.note || x.type || 'Wallet'}</p><p class="text-[var(--text-muted)] truncate">${String(x.time || '').replace('T',' ')}</p></div><div class="text-right shrink-0"><p class="${cls} font-black">${amt >= 0 ? '+' : ''}${fmtMoney(amt)}</p><p class="text-[var(--text-muted)]">Bal ${fmtMoney(x.balanceAfter || 0)}</p></div></div>`;
            }).join('')}</div>`;
        }

        let walletHistoryUserId = null;
        let walletHistoryRows = [];
        function walletTxnLabel(type){
            const t = String(type || '').replace(/_/g,' ');
            return t ? t.toUpperCase() : 'WALLET';
        }
        async function showWalletHistory(userId){
            if(!IS_MASTER) return;
            walletHistoryUserId = userId;
            walletHistoryRows = [];
            try{
                const res = await fetch('/api/wallet_history?userId=' + encodeURIComponent(userId) + '&limit=120');
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'History load failed');
                walletHistoryRows = data.transactions || data.walletTransactions || [];
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                render(true);
                setTimeout(() => document.getElementById('wallet-history-panel')?.scrollIntoView({behavior:'smooth', block:'start'}), 80);
            }catch(e){ showRealNotification('❌ History Error', String(e.message || e), 'danger'); }
        }
        function closeWalletHistory(){ walletHistoryUserId = null; walletHistoryRows = []; render(true); }
        function renderWalletHistoryPanel(){
            if(!walletHistoryUserId) return '';
            const prof = (appState.profiles || {})[walletHistoryUserId] || {};
            const rows = walletHistoryRows || [];
            const totalCr = rows.reduce((s,x)=>s + Math.max(0, Number(x.amount || 0)), 0);
            const totalDr = rows.reduce((s,x)=>s + Math.max(0, -Number(x.amount || 0)), 0);
            const body = rows.length ? rows.map(x => {
                const amt = Number(x.amount || 0);
                const cls = amt >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]';
                const ref = x.refId || x.withdrawalId || x.paymentId || x.entryId || '';
                return `<div class="native-card p-3 mb-2"><div class="flex items-start justify-between gap-2"><div class="min-w-0"><p class="text-white font-black text-[11px] truncate">${htmlEscape(x.note || walletTxnLabel(x.type))}</p><p class="text-[var(--text-muted)] text-[9px] uppercase mt-0.5">${htmlEscape(walletTxnLabel(x.type))} · ${htmlEscape(x.source || '-')}</p></div><div class="text-right shrink-0"><p class="${cls} font-black text-[12px]">${amt >= 0 ? '+' : ''}${fmtMoney(amt)}</p><p class="text-[var(--primary)] text-[9px]">Bal ${fmtMoney(x.balanceAfter || 0)}</p></div></div><div class="grid grid-cols-2 gap-2 mt-2 text-[9px]"><div class="stat-box"><p class="stat-lbl">Before</p><p class="stat-val">${fmtMoney(x.balanceBefore || 0)}</p></div><div class="stat-box"><p class="stat-lbl">Hold</p><p class="stat-val">${fmtMoney(x.holdAfter || 0)}</p></div></div><p class="text-[9px] text-[var(--text-muted)] mt-2 break-all">${htmlEscape(String(x.time || '').replace('T',' ').slice(0,19))}${ref ? ' · Ref: ' + htmlEscape(ref) : ''}</p></div>`;
            }).join('') : '<div class="native-card p-5 text-center text-[var(--text-muted)] text-xs">Is user ka wallet history abhi empty hai.</div>';
            return `<div id="wallet-history-panel" class="mb-4"><div class="flex items-center justify-between mb-2"><p class="sec-header mb-0">Wallet History · ${htmlEscape(prof.name || walletHistoryUserId)}</p><button onclick="closeWalletHistory()" class="text-[var(--rose)] font-black text-[10px] uppercase"><i class="fas fa-times mr-1"></i>Close</button></div><div class="wallet-hud rounded-2xl mb-3"><div class="stat-box"><p class="stat-lbl">Rows</p><p class="stat-val">${rows.length}</p></div><div class="stat-box"><p class="stat-lbl">Credit</p><p class="stat-val text-[var(--green)]">${fmtMoney(totalCr)}</p></div><div class="stat-box"><p class="stat-lbl">Debit</p><p class="stat-val text-[var(--rose)]">${fmtMoney(totalDr)}</p></div></div>${body}</div>`;
        }

        // ==========================================
        // WITHDRAWAL UI HELPERS — Phase 1
        // ==========================================
        function ensureWithdrawalStruct(){
            if(!Array.isArray(appState.withdrawals)) appState.withdrawals = [];
            if(!appState.withdrawalSettings) appState.withdrawalSettings = {enabled:true,minAmount:1,maxAmount:200000,onePendingPerUser:true,notifyUserPrivate:true,notifyAdminPrivate:true,adminNotifyTargets:[],allowedMethods:['upi','qr','bank']};
        }
        function walletHold(w){ return Number((w || {}).hold || (w || {}).walletHold || 0); }
        function walletEntryAvailable(w){ return Number((w || {}).balance || 0) + Number((w || {}).creditLimit || 0) - walletHold(w); }
        function walletWithdrawAvailable(w){ return Number((w || {}).balance || 0) - walletHold(w); }
        async function refreshWithdrawalsState(){
            ensureWithdrawalStruct();
            try{
                const res = await fetch('/api/withdrawals');
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Withdrawal load failed');
                appState.withdrawals = data.withdrawals || [];
                appState.withdrawalSettings = data.withdrawalSettings || appState.withdrawalSettings;
                appState.wallets = data.wallets || appState.wallets || {};
                return data;
            }catch(e){ return null; }
        }
        function findWithdrawalById(id){
            return (appState.withdrawals || []).find(w => String(w.id || '') === String(id || '')) || null;
        }
        function withdrawalUpiId(w){
            const txt = String((w || {}).detail || '');
            const m = txt.match(/[a-zA-Z0-9._-]{2,}@[a-zA-Z0-9._-]{2,}/);
            return m ? m[0] : '';
        }
        function withdrawalUpiPayLink(w){
            const upi = withdrawalUpiId(w);
            if(!upi) return '';
            const amount = Number((w || {}).amount || 0);
            const note = 'Withdrawal ' + String((w || {}).id || '');
            return 'upi://pay?pa=' + encodeURIComponent(upi) + '&am=' + encodeURIComponent(amount.toFixed(2)) + '&cu=INR&tn=' + encodeURIComponent(note);
        }
        async function copyWithdrawalDetail(id){
            const w = findWithdrawalById(id);
            if(!w) return;
            const text = `Withdrawal #${w.id}\nUser: ${w.userName || w.userId || '-'}\nPhone: ${w.phone || '-'}\nAmount: ${fmtMoney(w.amount || 0)}\nMethod: ${String(w.method || '-').toUpperCase()}\nDetail: ${w.method === 'qr' ? 'QR image attached' : (w.detail || '-')}`;
            try{ await navigator.clipboard.writeText(text); showRealNotification('✅ Copied', 'Withdrawal payment details copied.', 'success'); }
            catch(e){ prompt('Copy withdrawal details:', text); }
        }
        function openWithdrawalPayNow(id){
            const w = findWithdrawalById(id);
            if(!w) return;
            const method = String(w.method || '').toLowerCase();
            if(method === 'upi'){
                const link = withdrawalUpiPayLink(w);
                if(!link){ showRealNotification('⚠️ UPI Missing', 'UPI ID detail me nahi mila. Copy Details use karo.', 'warning'); return; }
                window.location.href = link;
                showRealNotification('📲 Payment App Opening', 'Payment complete hone ke baad app me wapas aake Mark Paid dabao.', 'info');
                return;
            }
            if(method === 'qr'){
                if(w.qrImageData){
                    const win = window.open('', '_blank');
                    if(win){ win.document.write('<title>Withdrawal QR</title><body style="margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh"><img style="max-width:96vw;max-height:96vh;background:#fff;padding:12px;border-radius:16px" src="'+String(w.qrImageData).replace(/"/g,'&quot;')+'"></body>'); }
                    showRealNotification('📷 QR Opened', 'Payment app se QR pay karo, phir Mark Paid dabao.', 'info');
                } else {
                    showRealNotification('⚠️ QR Missing', 'QR image nahi mila. User se QR image dobara bhejne ko bolo.', 'warning');
                }
                return;
            }
            if(method === 'bank'){
                copyWithdrawalDetail(id);
                showRealNotification('🏦 Bank Details Copied', 'Banking app me manually transfer karo, phir Mark Paid dabao.', 'info');
                return;
            }
            copyWithdrawalDetail(id);
        }
        async function withdrawalAction(id, action){
            if(!IS_MASTER) return;
            let reason = '';
            if(action === 'reject'){
                reason = prompt('Reject reason:', 'Rejected by admin') || 'Rejected by admin';
            } else if(action === 'approve'){
                if(!confirm('Approve withdrawal #' + id + '? User ko ek baar approval notification jayega: payment jaldi process hoga.')) return;
            } else {
                showRealNotification('⚠️ Invalid Action', 'Unknown withdrawal action.', 'warning');
                return;
            }
            try{
                const res = await fetch('/api/withdrawal_action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id, action, reason})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Withdrawal update failed');
                appState.wallets = data.wallets || appState.wallets;
                appState.withdrawals = data.withdrawals || appState.withdrawals;
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                showRealNotification(action === 'approve' ? '✅ Withdrawal Approved' : '❌ Withdrawal Rejected', '#' + id + ' update ho gaya. Notification duplicate-safe hai.', action === 'approve' ? 'success' : 'info');
                render(true);
            }catch(e){ showRealNotification('❌ Withdrawal Error', String(e.message || e), 'danger'); }
        }
        async function markWithdrawalPaid(id){
            if(!IS_MASTER) return;
            const w = findWithdrawalById(id);
            if(!w) return;
            if(String(w.status || '').toLowerCase() !== 'approved'){
                showRealNotification('⚠️ Approve First', 'Pehle withdrawal approve karo, phir payment ke baad Mark Paid.', 'warning');
                return;
            }
            const transactionId = prompt('UTR / Transaction ID (optional):', '') || '';
            const adminNote = prompt('Admin note (optional):', '') || '';
            if(!confirm('Mark Paid #' + id + '? Iske baad wallet se amount final deduct hoga aur user ko paid notification jayega.')) return;
            try{
                const res = await fetch('/api/withdrawal_action', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id, action:'mark_paid', transactionId, adminNote})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Mark paid failed');
                appState.wallets = data.wallets || appState.wallets;
                appState.withdrawals = data.withdrawals || appState.withdrawals;
                appState.walletTransactions = data.walletTransactions || appState.walletTransactions || [];
                showRealNotification('✅ Withdrawal Paid', '#' + id + ' paid mark ho gaya. User notification queue me add hai.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Mark Paid Error', String(e.message || e), 'danger'); }
        }

        async function saveWithdrawalSettings(){
            if(!IS_MASTER) return;
            const payload = {
                enabled: !!document.getElementById('withdraw-enabled')?.checked,
                onePendingPerUser: !!document.getElementById('withdraw-one-pending')?.checked,
                notifyUserPrivate: !!document.getElementById('withdraw-user-notify')?.checked,
                notifyAdminPrivate: !!document.getElementById('withdraw-admin-notify')?.checked,
                minAmount: Number(document.getElementById('withdraw-min')?.value || 0),
                maxAmount: Number(document.getElementById('withdraw-max')?.value || 0),
                adminNotifyTargets: document.getElementById('withdraw-admin-targets')?.value || ''
            };
            try{
                const res = await fetch('/api/withdrawal_settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Settings save failed');
                appState.withdrawalSettings = data.withdrawalSettings || appState.withdrawalSettings;
                showRealNotification('✅ Withdrawal Settings Saved', 'Commands aur notifications settings update ho gayi.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Settings Error', String(e.message || e), 'danger'); }
        }
        function withdrawalStatusBadge(status){
            status = String(status || 'pending').toLowerCase();
            if(status === 'paid') return 'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]';
            if(status === 'approved') return 'text-[var(--primary)] border-[rgba(42,171,238,0.25)] bg-[rgba(42,171,238,0.08)]';
            if(status === 'rejected') return 'text-[var(--rose)] border-[rgba(255,93,93,0.25)] bg-[rgba(255,93,93,0.08)]';
            return 'text-[var(--amber)] border-[rgba(250,199,72,0.25)] bg-[rgba(250,199,72,0.08)]';
        }
        function withdrawalStatusLabel(w){
            const status = String((w || {}).status || 'pending').toLowerCase();
            if(status === 'approved') return 'Approved · Processing';
            if(status === 'paid') return 'Paid';
            if(status === 'rejected') return 'Rejected';
            return 'Pending Approval';
        }
        function renderWithdrawalButtons(w){
            const id = attrEscape(w.id || '');
            const status = String(w.status || 'pending').toLowerCase();
            if(status === 'pending'){
                return `<div class="grid grid-cols-2 gap-2 mt-3"><button onclick="withdrawalAction('${id}','approve')" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-check mr-1"></i> Approve</button><button onclick="withdrawalAction('${id}','reject')" class="bg-[rgba(255,93,93,0.12)] text-[var(--rose)] border border-[rgba(255,93,93,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-times mr-1"></i> Reject</button></div>`;
            }
            if(status === 'approved'){
                return `<div class="grid grid-cols-3 gap-2 mt-3"><button onclick="openWithdrawalPayNow('${id}')" class="bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-mobile-screen-button mr-1"></i> Pay Now</button><button onclick="markWithdrawalPaid('${id}')" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-circle-check mr-1"></i> Mark Paid</button><button onclick="withdrawalAction('${id}','reject')" class="bg-[rgba(255,93,93,0.12)] text-[var(--rose)] border border-[rgba(255,93,93,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-ban mr-1"></i> Cancel</button></div>`;
            }
            return `<div class="grid grid-cols-2 gap-2 mt-3"><button onclick="copyWithdrawalDetail('${id}')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-copy mr-1"></i> Copy Details</button></div>`;
        }

        function financeStatCard(label, value, tone){
            const cls = tone === 'green' ? 'text-[var(--green)]' : tone === 'rose' ? 'text-[var(--rose)]' : tone === 'amber' ? 'text-[var(--amber)]' : 'text-white';
            return `<div class="stat-box"><p class="stat-lbl">${htmlEscape(label)}</p><p class="stat-val ${cls}">${value}</p></div>`;
        }
        function financeSummaryData(){
            ensureWalletStruct(); ensureWithdrawalStruct();
            const wallets = appState.wallets || {};
            const payments = Array.isArray(appState.payments) ? appState.payments : [];
            const withdrawals = Array.isArray(appState.withdrawals) ? appState.withdrawals : [];
            const tx = Array.isArray(appState.walletTransactions) ? appState.walletTransactions : [];
            const walletList = Object.values(wallets || {}).filter(x => x && typeof x === 'object');
            const totalBal = walletList.reduce((s,w)=>s+Number(w.balance||0),0);
            const totalHold = walletList.reduce((s,w)=>s+walletHold(w),0);
            const pendingPay = payments.filter(p => String(p.status||'').toLowerCase()==='pending');
            const pendingWd = withdrawals.filter(w => String(w.status||'').toLowerCase()==='pending');
            const processingWd = withdrawals.filter(w => String(w.status||'').toLowerCase()==='approved');
            const creditToday = tx.filter(x => Number(x.amount||0) > 0).slice(-300).reduce((s,x)=>s+Number(x.amount||0),0);
            const debitToday = tx.filter(x => Number(x.amount||0) < 0).slice(-300).reduce((s,x)=>s+Math.abs(Number(x.amount||0)),0);
            return {walletList, payments, withdrawals, tx, totalBal, totalHold, pendingPay, pendingWd, processingWd, creditToday, debitToday};
        }
        function renderFinanceSummary(){
            const d = financeSummaryData();
            const recent = (d.tx || []).slice(-12).reverse();
            return `<div class="px-3 py-4">
                <p class="sec-header">Finance Control</p>
                <div class="wallet-hud rounded-2xl mb-3">
                    ${financeStatCard('Wallet Balance', fmtMoney(d.totalBal), 'green')}
                    ${financeStatCard('Hold', fmtMoney(d.totalHold), 'amber')}
                    ${financeStatCard('Pending Pay', d.pendingPay.length, 'primary')}
                    ${financeStatCard('Pending W/D', d.pendingWd.length, 'rose')}
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(42,171,238,0.22);background:rgba(42,171,238,0.04)">
                    <h3 class="text-white font-black text-[14px] mb-1">Single Finance Hub</h3>
                    <p class="text-[10px] text-[var(--text-muted)] leading-5">Wallet, payment aur withdrawal ab ek hi lightweight Finance tab me control honge. Old Wallet/Pay/Withdraw nav duplicate remove hai; backend core atomic routes same rahenge.</p>
                    <div class="grid grid-cols-3 gap-2 mt-3">
                        <button onclick="setFinanceTab('wallets')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-wallet mr-1"></i> Wallets</button>
                        <button onclick="setFinanceTab('payments')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-rupee-sign mr-1"></i> Payments</button>
                        <button onclick="setFinanceTab('withdrawals')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-money-bill-transfer mr-1"></i> Withdraw</button>
                    </div>
                </div>
                <p class="sec-header">Recent Transactions</p>
                <div class="native-card p-3">
                    ${recent.length ? recent.map(x=>`<div class="flex items-start justify-between gap-2 py-2 border-b border-[var(--border)] last:border-b-0"><div class="min-w-0"><p class="text-white font-bold text-[10px] truncate">${htmlEscape(x.userName || x.userId || '-')} · ${htmlEscape(x.note || x.type || 'wallet')}</p><p class="text-[9px] text-[var(--text-muted)] truncate">${htmlEscape(String(x.time || '').replace('T',' '))}</p></div><p class="shrink-0 font-black text-[11px] ${Number(x.amount||0)>=0?'text-[var(--green)]':'text-[var(--rose)]'}">${Number(x.amount||0)>=0?'+':''}${fmtMoney(x.amount||0)}</p></div>`).join('') : `<p class="text-[10px] text-[var(--text-muted)] text-center py-4">Abhi transaction history nahi hai.</p>`}
                </div>
            </div>`;
        }
        function renderFinanceTabs(){
            const items = [
                ['summary','Summary','fa-chart-pie'],
                ['wallets','Wallets','fa-wallet'],
                ['payments','Payments','fa-rupee-sign'],
                ['withdrawals','Withdraw','fa-money-bill-transfer']
            ];
            return `<div class="pill-tabs">${items.map(x=>`<button onclick="setFinanceTab('${x[0]}')" class="pill-tab ${financeSubTab===x[0]?'active':''}"><i class="fas ${x[2]} mr-1"></i>${x[1]}</button>`).join('')}</div>`;
        }
        function renderFinanceTab(){
            if(!IS_MASTER) return '';
            let body = '';
            if(financeSubTab === 'wallets') body = renderWalletsTab();
            else if(financeSubTab === 'payments') { body = renderAdminPaymentsTab(); setTimeout(renderAdminPayments, 100); }
            else if(financeSubTab === 'withdrawals') body = renderWithdrawalsTab();
            else body = renderFinanceSummary();
            return renderFinanceTabs() + body;
        }

        function renderWithdrawalsTab(){
            if(!IS_MASTER) return '';
            ensureWithdrawalStruct(); ensureWalletStruct();
            const ws = appState.withdrawalSettings || {};
            const rows = (appState.withdrawals || []).slice().sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||'')));
            const pending = rows.filter(w => String(w.status || '').toLowerCase() === 'pending');
            const approved = rows.filter(w => String(w.status || '').toLowerCase() === 'approved');
            const paid = rows.filter(w => String(w.status || '').toLowerCase() === 'paid');
            const active = rows.filter(w => ['pending','approved'].includes(String(w.status || '').toLowerCase()));
            const totalActive = active.reduce((s,w)=>s+Number(w.amount||0),0);
            const adminTargets = Array.isArray(ws.adminNotifyTargets) ? ws.adminNotifyTargets.join('\\n') : String(ws.adminNotifyTargets || '');
            let html = `<div class="px-3 py-4">
                
                <p class="sec-header">Withdrawal Requests</p>
                <div class="wallet-hud rounded-2xl mb-3">
                    <div class="stat-box"><p class="stat-lbl">Pending</p><p class="stat-val text-[var(--amber)]">${pending.length}</p></div>
                    <div class="stat-box"><p class="stat-lbl">Processing</p><p class="stat-val text-[var(--primary)]">${approved.length}</p></div>
                    <div class="stat-box"><p class="stat-lbl">Active Amt</p><p class="stat-val text-[var(--rose)]">${fmtMoney(totalActive)}</p></div>
                    <div class="stat-box"><p class="stat-lbl">Paid</p><p class="stat-val text-[var(--green)]">${paid.length}</p></div>
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(42,171,238,0.22);background:rgba(42,171,238,0.04)">
                    <div class="flex items-center gap-3 mb-3"><div class="w-10 h-10 rounded-xl bg-[rgba(42,171,238,0.15)] text-[var(--primary)] flex items-center justify-center border border-[rgba(42,171,238,0.2)]"><i class="fas fa-money-bill-transfer"></i></div><div><h3 class="text-white font-black text-[14px]">WhatsApp Withdrawal Commands</h3><p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest">Pending → Approved/Processing → Paid</p></div></div>
                    <pre class="text-[10px] text-[var(--text-muted)] whitespace-pre-wrap bg-[#17212B] rounded-xl p-3 border border-[var(--border)]">withdraw 500 upi user@upi
wd 500 qr  (QR image caption ke saath)
withdraw 500 bank Name / A-C / IFSC
balance
withdraw status</pre>
                    <div class="mt-3 text-[10px] text-[var(--text-muted)] leading-5 bg-[rgba(255,255,255,0.03)] rounded-xl p-3 border border-[var(--border)]">
                        <b class="text-white">Safe payment flow:</b><br>
                        Approve = user ko ek baar message: payment jaldi process hoga.<br>
                        Pay Now = payment app/detail open, wallet deduct nahi hota.<br>
                        Mark Paid = wallet final deduct + user ko paid notification.
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-3">
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">Withdraw ON</span><span class="switch"><input id="withdraw-enabled" type="checkbox" ${ws.enabled!==false?'checked':''}><span class="slider"></span></span></label>
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">One Active/User</span><span class="switch"><input id="withdraw-one-pending" type="checkbox" ${ws.onePendingPerUser!==false?'checked':''}><span class="slider"></span></span></label>
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">User Notify</span><span class="switch"><input id="withdraw-user-notify" type="checkbox" ${ws.notifyUserPrivate!==false?'checked':''}><span class="slider"></span></span></label>
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">Admin Notify</span><span class="switch"><input id="withdraw-admin-notify" type="checkbox" ${ws.notifyAdminPrivate!==false?'checked':''}><span class="slider"></span></span></label>
                    </div>
                    <div class="grid grid-cols-2 gap-2 mt-3"><div><p class="stat-lbl">Min Amount</p><input id="withdraw-min" class="native-input text-[12px]" type="number" value="${Number(ws.minAmount||1)}"></div><div><p class="stat-lbl">Max Amount</p><input id="withdraw-max" class="native-input text-[12px]" type="number" value="${Number(ws.maxAmount||200000)}"></div></div>
                    <p class="stat-lbl mt-3">Admin WhatsApp Notify Targets</p>
                    <textarea id="withdraw-admin-targets" class="hidden">${htmlEscape(adminTargets)}</textarea>
                    <div class="bg-[#17212B] border border-[var(--border)] rounded-xl p-3 mb-2 min-h-[54px]">${selectedTargetSummary(ws.adminNotifyTargets || [], 6)}</div>
                    <div class="grid grid-cols-2 gap-2 mt-3"><button onclick="openWithdrawalAdminTargetPicker()" class="bg-[rgba(42,171,238,0.15)] text-[var(--primary)] border border-[rgba(42,171,238,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-list-check mr-1"></i> Pick Notify Targets</button><button onclick="saveWithdrawalSettings()" class="bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-save mr-1"></i> Save Settings</button></div>
                </div>`;
            if(!rows.length){
                html += `<div class="native-card p-5 text-center text-[var(--text-muted)] text-xs">Abhi koi withdrawal request nahi hai.</div>`;
            } else {
                html += `<div class="space-y-2">${rows.map(w=>{
                    const status = String(w.status || 'pending').toLowerCase();
                    const uid = w.userId || '';
                    const wallet = walletForUser(uid);
                    const detail = w.method === 'qr' && w.qrImageData ? '<div class="mt-2"><img src="'+attrEscape(w.qrImageData)+'" class="w-32 h-32 object-contain rounded-xl border border-[var(--border)] bg-white p-1"></div>' : `<p class="text-[10px] text-[var(--text-muted)] mt-2 whitespace-pre-wrap"><b>Detail:</b> ${htmlEscape(w.detail || '-')}</p>`;
                    const utr = w.transactionId ? `<p class="text-[9px] text-[var(--green)] mt-2">Transaction ID: ${htmlEscape(w.transactionId)}</p>` : '';
                    const approvedAt = w.approvedAt ? `<p class="text-[9px] text-[var(--primary)] mt-1">Approved: ${htmlEscape(String(w.approvedAt).replace('T',' '))}</p>` : '';
                    const paidAt = w.paidAt ? `<p class="text-[9px] text-[var(--green)] mt-1">Paid: ${htmlEscape(String(w.paidAt).replace('T',' '))}</p>` : '';
                    return `<div class="native-card p-3">
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0"><h3 class="text-white font-black text-[13px] uppercase truncate">${htmlEscape(w.userName || uid || '-')}</h3><p class="text-[9px] text-[var(--text-muted)] font-bold mt-1 truncate">${htmlEscape(w.phone || '')} · #${htmlEscape(w.id || '')}</p></div>
                            <span class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${withdrawalStatusBadge(status)}">${htmlEscape(withdrawalStatusLabel(w))}</span>
                        </div>
                        <div class="grid grid-cols-3 gap-2 mt-3">
                            <div class="stat-box"><p class="stat-lbl">Amount</p><p class="stat-val text-[var(--rose)]">${fmtMoney(w.amount || 0)}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Method</p><p class="stat-val text-[var(--primary)]">${htmlEscape(String(w.method||'-').toUpperCase())}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Hold</p><p class="stat-val text-[var(--amber)]">${fmtMoney(walletHold(wallet))}</p></div>
                        </div>
                        ${detail}
                        <div class="grid grid-cols-2 gap-2 mt-3"><button onclick="copyWithdrawalDetail('${attrEscape(w.id)}')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-2 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-copy mr-1"></i> Copy Details</button>${String(w.method||'').toLowerCase()==='upi' && withdrawalUpiPayLink(w) ? `<a href="${attrEscape(withdrawalUpiPayLink(w))}" class="text-center bg-[rgba(42,171,238,0.12)] text-[var(--primary)] border border-[rgba(42,171,238,0.25)] py-2 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-link mr-1"></i> UPI Link</a>` : `<span></span>`}</div>
                        <p class="text-[9px] text-[var(--text-muted)] mt-2">Requested: ${htmlEscape(String(w.createdAt || w.time || '').replace('T',' '))}</p>
                        ${approvedAt}${paidAt}${utr}
                        ${renderWithdrawalButtons(w)}
                        ${w.rejectReason ? `<p class="text-[9px] text-[var(--rose)] mt-2">Reason: ${htmlEscape(w.rejectReason)}</p>` : ''}
                    </div>`;
                }).join('')}</div>`;
            }
            html += `</div>`;
            setTimeout(()=>refreshWithdrawalsState().then(()=>{}), 100);
            return html;
        }

        // ==========================================
        // WHATSAPP ENTRY PARSER UI HELPERS
        // ==========================================
        function ensureEntryStruct(){
            if(!Array.isArray(appState.entries)) appState.entries = [];
            if(!appState.entrySettings) appState.entrySettings = {entryParserEnabled:true, groupsOnly:true, strictFormat:true, autoDebitWallet:true, marketTimingEnabled:true, riskLimitEnabled:true, marketCloseTimes:{}, entryFormatTemplate:'MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}'};
            if(!appState.riskSettings) appState.riskSettings = {marketDailyLimit:0, digitDailyLimit:0, userDailyLimit:0, warningPercent:80, autoLockOnLimit:false};
            if(!appState.marketLocks) appState.marketLocks = {};
        }
        async function refreshEntriesState(){
            try{
                const res = await fetch('/api/entries');
                const data = await res.json();
                if(data.status === 'success'){
                    appState.entries = data.entries || [];
                    appState.entrySettings = data.entrySettings || appState.entrySettings || {};
                    appState.riskSettings = data.riskSettings || appState.riskSettings || {};
                    appState.marketLocks = data.marketLocks || appState.marketLocks || {};
                    return data;
                }
            }catch(e){}
            return null;
        }
        async function saveEntryParserToggle(enabled){
            if(!IS_MASTER) return;
            try{
                const res = await fetch('/api/entry_settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entryParserEnabled:!!enabled})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Entry settings save failed');
                appState.entrySettings = data.entrySettings || appState.entrySettings;
                showRealNotification(enabled ? '✅ Entry Parser ON' : '⏸️ Entry Parser OFF', enabled ? 'WhatsApp strict entries accept hongi.' : 'WhatsApp entry auto-accept stopped.', enabled ? 'success' : 'info');
                render(true);
            }catch(e){ showRealNotification('❌ Entry Settings Error', String(e.message || e), 'danger'); }
        }
        async function saveEntrySafetySettings(){
            if(!IS_MASTER) return;
            ensureEntryStruct();
            try{
                const existingEntrySettings = appState.entrySettings || {};
                const existingRiskSettings = appState.riskSettings || {};
                const marketCloseTimes = {};
                document.querySelectorAll('.entry-time-input[data-market]').forEach(inp => {
                    const market = String(inp.getAttribute('data-market') || '').trim().toUpperCase().replace(/\\s+/g, ' ');
                    const value = String(inp.value || '').trim();
                    if(market && /^\\d{2}:\\d{2}$/.test(value)) marketCloseTimes[market] = value;
                });
                const payload = {
                    marketTimingEnabled: document.getElementById('entryTimingToggle') ? !!document.getElementById('entryTimingToggle').checked : existingEntrySettings.marketTimingEnabled !== false,
                    riskLimitEnabled: document.getElementById('entryRiskToggle') ? !!document.getElementById('entryRiskToggle').checked : existingEntrySettings.riskLimitEnabled !== false,
                    marketCloseTimes: Object.keys(marketCloseTimes).length ? marketCloseTimes : (existingEntrySettings.marketCloseTimes || {}),
                    marketDailyLimit: Number(document.getElementById('riskMarketLimit')?.value ?? existingRiskSettings.marketDailyLimit ?? 0),
                    digitDailyLimit: Number(document.getElementById('riskDigitLimit')?.value ?? existingRiskSettings.digitDailyLimit ?? 0),
                    userDailyLimit: Number(document.getElementById('riskUserLimit')?.value ?? existingRiskSettings.userDailyLimit ?? 0),
                    warningPercent: Number(document.getElementById('riskWarnPercent')?.value ?? existingRiskSettings.warningPercent ?? 80),
                    autoLockOnLimit: document.getElementById('riskAutoLock') ? !!document.getElementById('riskAutoLock').checked : !!existingRiskSettings.autoLockOnLimit
                };
                const res = await fetch('/api/save_entry_safety', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Entry safety save failed');
                appState.entrySettings = data.entrySettings || appState.entrySettings;
                appState.riskSettings = data.riskSettings || appState.riskSettings;
                await refreshEntriesState();
                const changedCount = Object.keys(marketCloseTimes).length;
                showRealNotification('✅ Entry Safety Saved', `Manual market times saved: ${changedCount}. Gateway next message me new cut-off use karega.`, 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Risk Save Error', String(e.message || e), 'danger'); }
        }

        async function saveEntryFormatTemplate(){
            if(!IS_MASTER) return;
            ensureEntryStruct();
            const tpl = String(document.getElementById('entryFormatTemplate')?.value || '').trim();
            try{
                const res = await fetch('/api/entry_settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entryFormatTemplate:tpl})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Entry format save failed');
                appState.entrySettings = data.entrySettings || appState.entrySettings;
                showRealNotification('✅ Entry Format Saved', 'Gateway next WhatsApp entry me new template use karega.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Format Save Error', String(e.message || e), 'danger'); }
        }
        async function unlockMarketFromEntries(market){
            if(!market) return;
            try{
                const res = await fetch('/api/market_unlock', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({market})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Unlock failed');
                appState.marketLocks = data.marketLocks || {};
                showRealNotification('🔓 Market Unlocked', market + ' unlocked.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Unlock Error', String(e.message || e), 'danger'); }
        }
        function formatEntryDigits(e){
            const d = Array.isArray(e.digits) ? e.digits : String(e.digits || '').split(',');
            return d.map(x => String(x).trim()).filter(Boolean).join(', ');
        }
        function renderEntriesTab(){
            ensureEntryStruct();
            const entries = (appState.entries || []).slice().sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||''))).slice(0,120);
            const accepted = entries.filter(e => e.status === 'accepted');
            const total = accepted.reduce((s,e)=>s+Number(e.total||0),0);
            const parserOn = appState.entrySettings.entryParserEnabled !== false;
            const byMarket = {};
            accepted.forEach(e=>{ const m=e.market||'UNKNOWN'; byMarket[m]=(byMarket[m]||0)+Number(e.total||0); });
            const marketRows = Object.entries(byMarket).sort((a,b)=>b[1]-a[1]).slice(0,8);
            let html = `<div class="p-3">
                <div class="native-card p-4 mb-3">
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <div><h2 class="text-white font-black text-sm uppercase tracking-wide">WhatsApp Entry Parser</h2><p class="text-[var(--text-muted)] text-[10px]">Strict format entries accept + wallet auto debit</p></div>
                        <label class="switch shrink-0"><input type="checkbox" ${parserOn?'checked':''} onchange="saveEntryParserToggle(this.checked)"><span class="slider"></span></label>
                    </div>
                    <div class="grid grid-cols-3 gap-2">
                        <div class="stat-box"><p class="stat-lbl">Today Entries</p><p class="stat-val text-white">${accepted.length}</p></div>
                        <div class="stat-box"><p class="stat-lbl">Today Load</p><p class="stat-val text-[var(--green)]">${fmtMoney(total)}</p></div>
                        <div class="stat-box"><p class="stat-lbl">Parser</p><p class="stat-val ${parserOn?'text-[var(--green)]':'text-[var(--rose)]'}">${parserOn?'ON':'OFF'}</p></div>
                    </div>
                    <button onclick="refreshEntriesState().then(()=>render(true))" class="mt-3 w-full bg-[var(--surface-light)] text-white py-3 rounded-xl font-black text-[10px] uppercase border border-[var(--border)] active:scale-95"><i class="fas fa-sync mr-1"></i> Refresh Entries</button>
                </div>
                ${(()=>{ const rs = appState.riskSettings || {}; const es = appState.entrySettings || {}; return `<div class="native-card p-4 mb-3">
                    <div class="flex items-center justify-between gap-3 mb-3"><div><p class="text-white font-black text-[12px] uppercase">Market Time + Risk Controls</p><p class="text-[var(--text-muted)] text-[9px]">0 limit = disabled. Timing ON rahega to cut-off ke baad entry reject hogi.</p></div></div>
                    <div class="grid grid-cols-2 gap-2 mb-3">
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">Market Timing</span><span class="switch"><input id="entryTimingToggle" type="checkbox" ${es.marketTimingEnabled!==false?'checked':''}><span class="slider"></span></span></label>
                        <label class="flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">Risk Limits</span><span class="switch"><input id="entryRiskToggle" type="checkbox" ${es.riskLimitEnabled!==false?'checked':''}><span class="slider"></span></span></label>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div><p class="stat-lbl">Market Daily Limit</p><input id="riskMarketLimit" class="native-input text-[12px]" type="number" value="${Number(rs.marketDailyLimit||0)}"></div>
                        <div><p class="stat-lbl">Digit Load Limit</p><input id="riskDigitLimit" class="native-input text-[12px]" type="number" value="${Number(rs.digitDailyLimit||0)}"></div>
                        <div><p class="stat-lbl">User Daily Limit</p><input id="riskUserLimit" class="native-input text-[12px]" type="number" value="${Number(rs.userDailyLimit||0)}"></div>
                        <div><p class="stat-lbl">Warning %</p><input id="riskWarnPercent" class="native-input text-[12px]" type="number" value="${Number(rs.warningPercent||80)}"></div>
                    </div>
                    <label class="mt-3 flex items-center justify-between bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]"><span class="text-white font-bold text-[10px]">Auto Lock Market On Limit</span><span class="switch"><input id="riskAutoLock" type="checkbox" ${rs.autoLockOnLimit?'checked':''}><span class="slider"></span></span></label>
                    ${(()=>{
                        const times = (es.marketCloseTimes && typeof es.marketCloseTimes === 'object') ? es.marketCloseTimes : {};
                        const list = [];
                        (markets || []).forEach(m => { if(m && m.n && !list.includes(m.n)) list.push(m.n); });
                        (baseMarkets || []).forEach(m => { if(m && m.n && !list.includes(m.n)) list.push(m.n); });
                        return `<details class="mt-3 bg-[var(--surface-light)] rounded-xl border border-[var(--border)] overflow-hidden">
                            <summary class="px-3 py-3 text-white font-black text-[10px] uppercase cursor-pointer">
                                <i class="fas fa-clock mr-1 text-[var(--primary)]"></i> Manual Market Entry Time Setup
                            </summary>
                            <div class="px-3 pb-3">
                                <p class="text-[var(--text-muted)] text-[9px] mb-3 leading-relaxed">Jis market ka entry time extend/test karna ho, uska cut-off yahan set karo. Example: abhi 23:36 hai aur KALYAN OPEN test karna hai to KALYAN OPEN ko 23:59 set karo. Timing OFF karne se sab market time-check skip hoga.</p>
                                <div class="grid grid-cols-1 gap-2 max-h-72 overflow-y-auto no-scrollbar">
                                    ${list.map(m => `<div class="flex items-center justify-between gap-2 bg-[#17212B] rounded-xl p-2 border border-[var(--border)]">
                                        <span class="text-white font-bold text-[10px] leading-tight">${htmlEscape(m)}</span>
                                        <input data-market="${attrEscape(m)}" class="entry-time-input native-input max-w-[110px] text-[12px] py-2" type="time" value="${attrEscape(times[m] || '')}">
                                    </div>`).join('')}
                                </div>
                            </div>
                        </details>`;
                    })()}
                    <button onclick="saveEntrySafetySettings()" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">Save Risk Controls</button>
                </div>`; })()}
                ${(()=>{ const locks = appState.marketLocks || {}; const today = new Date().toISOString().slice(0,10); const rows = Object.entries(locks[today] || {}).filter(([m,v])=>v && (v.locked===true || v===true)); if(!rows.length) return ''; return `<div class="native-card p-3 mb-3"><p class="text-white font-black text-[11px] uppercase mb-2">Locked Markets Today</p>${rows.map(([m,v])=>`<div class="flex items-center justify-between gap-2 py-2 border-b border-[var(--border)] last:border-0"><div><p class="text-white font-bold text-[10px]">${m}</p><p class="text-[var(--text-muted)] text-[9px]">${(v&&v.reason)||'locked'}</p></div><button onclick="unlockMarketFromEntries('${String(m).replace(/'/g,"\'")}')" class="text-[var(--green)] font-black text-[10px] px-3 py-2 rounded-lg bg-[rgba(0,194,111,0.12)]">Unlock</button></div>`).join('')}</div>`; })()}
                ${(()=>{ const tpl = (appState.entrySettings && appState.entrySettings.entryFormatTemplate) || 'MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}'; return `<div class="native-card p-3 mb-3">
                    <p class="text-white font-black text-[11px] uppercase mb-2">Configurable WhatsApp Entry Format</p>
                    <p class="text-[9px] text-[var(--text-muted)] mb-2 leading-relaxed">Placeholders required: <span class="text-white">{market}</span>, <span class="text-white">{type}</span>, <span class="text-white">{digits}</span>, <span class="text-white">{parDigit}</span>, <span class="text-white">{total}</span>. Separators/labels admin apni marzi se set kar sakta hai.</p>
                    <textarea id="entryFormatTemplate" class="native-input text-[11px] min-h-[90px] leading-relaxed" placeholder="MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}">${htmlEscape(tpl)}</textarea>
                    <div class="grid grid-cols-1 gap-2 mt-2 text-[9px] text-[var(--text-muted)]">
                        <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><b class="text-white">A:</b> MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}</div>
                        <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><b class="text-white">B:</b> {market} | {type} | {digits} | {parDigit} | {total}</div>
                        <div class="bg-[#17212B] rounded-xl p-2 border border-[var(--border)]"><b class="text-white">C:</b> {market}/{type}/{digits}/{parDigit}/{total}</div>
                    </div>
                    <button onclick="saveEntryFormatTemplate()" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">Save Entry Format</button>
                    <p class="text-[9px] text-[var(--text-muted)] mt-2">Calculation logic same rahegi: digits validate, total calculate, wallet debit aur risk check unchanged.</p>
                </div>`; })()}`;
            if(marketRows.length){
                html += `<div class="native-card p-3 mb-3"><p class="text-white font-black text-[11px] uppercase mb-2">Market Load</p>${marketRows.map(([m,v])=>`<div class="flex justify-between text-[10px] py-1 border-b border-[var(--border)] last:border-0"><span class="text-[var(--text-muted)] font-bold">${m}</span><span class="text-white font-black">${fmtMoney(v)}</span></div>`).join('')}</div>`;
            }
            if(!entries.length){
                html += `<div class="native-card p-5 text-center text-[var(--text-muted)] text-xs">Abhi accepted WhatsApp entries nahi hain.</div>`;
            } else {
                html += `<div class="space-y-2">${entries.map(e=>{
                    const ok = e.status === 'accepted';
                    return `<div class="native-card p-3">
                        <div class="flex justify-between gap-2 mb-2"><div class="min-w-0"><p class="text-white font-black text-[12px] truncate">${e.market || '-'}</p><p class="text-[var(--text-muted)] text-[9px] truncate">${e.userName || e.userId || e.senderJid || '-'}</p></div><div class="text-right shrink-0"><p class="${ok?'text-[var(--green)]':'text-[var(--rose)]'} font-black text-[11px]">${String(e.status||'').toUpperCase()}</p><p class="text-[var(--text-muted)] text-[9px]">#${e.id || ''}</p></div></div>
                        <div class="grid grid-cols-3 gap-2 text-center">
                            <div class="bg-[var(--surface-light)] rounded-lg p-2"><p class="stat-lbl">Type</p><p class="text-white font-black text-[11px]">${e.gameType || '-'}</p></div>
                            <div class="bg-[var(--surface-light)] rounded-lg p-2"><p class="stat-lbl">Rate</p><p class="text-white font-black text-[11px]">${fmtMoney(e.parDigit || 0)}</p></div>
                            <div class="bg-[var(--surface-light)] rounded-lg p-2"><p class="stat-lbl">Total</p><p class="text-[var(--green)] font-black text-[11px]">${fmtMoney(e.total || 0)}</p></div>
                        </div>
                        <p class="text-[10px] text-[var(--text-muted)] mt-2"><b>Digits:</b> ${formatEntryDigits(e)}</p>
                        <p class="text-[9px] text-[var(--text-muted)] mt-1">${String(e.createdAt || e.time || '').replace('T',' ')}</p>
                    </div>`;
                }).join('')}</div>`;
            }
            html += `</div>`;
            setTimeout(()=>refreshEntriesState().then(()=>{}), 100);
            return html;
        }

        // ==========================================
        // SPAM / LINK GUARD UI HELPERS
        // ==========================================

        // ==========================================
        // OUTGOING WHATSAPP SAFE MESSAGING GUARD UI
        // ==========================================
        function ensureWhatsappSafetyStruct(){
            if(!appState.whatsappSafetySettings) appState.whatsappSafetySettings = {enabled:true, globalPaused:false, pauseReason:'', requireApprovedTargets:false, minDelayMs:2500, randomDelayMs:1200, duplicateBlock:true, duplicateWindowMinutes:1440, targetFailureLimit:3, globalConsecutiveFailureLimit:8, dailyTargetLimit:80, dailyGlobalLimit:300, autoPauseTargetOnFailures:true, autoPauseGlobalOnFailures:true, safeModeForGroupsOnly:false, allowPrivateReplies:true, allowAdminNotifications:true, adminAlertTargets:[]};
            if(!appState.whatsappSafetyTargets || Array.isArray(appState.whatsappSafetyTargets)) appState.whatsappSafetyTargets = {};
            if(!Array.isArray(appState.whatsappSafetyEvents)) appState.whatsappSafetyEvents = [];
            if(!appState.whatsappSafetyGateway) appState.whatsappSafetyGateway = {};
        }
        function safetyTargetKey(id){ return String(id || '').trim().replace(/:\\d+(?=@)/, ''); }
        function safetyTargetRecord(id){ ensureWhatsappSafetyStruct(); return appState.whatsappSafetyTargets[safetyTargetKey(id)] || null; }
        function targetSafetyBadge(id){
            const rec = safetyTargetRecord(id);
            if(!rec) return '';
            if(rec.paused) return '<span class="ml-1 text-[8px] px-1.5 py-0.5 rounded bg-[rgba(255,93,93,0.15)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)]">PAUSED</span>';
            if(rec.approved === false) return '<span class="ml-1 text-[8px] px-1.5 py-0.5 rounded bg-[rgba(250,199,72,0.14)] text-[var(--amber)] border border-[rgba(250,199,72,0.22)]">NOT APPROVED</span>';
            if(Number(rec.failureCount || 0) > 0) return '<span class="ml-1 text-[8px] px-1.5 py-0.5 rounded bg-[rgba(250,199,72,0.14)] text-[var(--amber)] border border-[rgba(250,199,72,0.22)]">WARN</span>';
            return '<span class="ml-1 text-[8px] px-1.5 py-0.5 rounded bg-[rgba(0,194,111,0.12)] text-[var(--green)] border border-[rgba(0,194,111,0.18)]">SAFE</span>';
        }
        async function refreshWhatsappSafetyState(silent=false){
            ensureWhatsappSafetyStruct();
            try{
                const res = await fetch('/api/whatsapp_safety?ts=' + Date.now(), {cache:'no-store'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Safety guard load failed');
                appState.whatsappSafetySettings = data.settings || appState.whatsappSafetySettings;
                appState.whatsappSafetyTargets = data.targets || appState.whatsappSafetyTargets || {};
                appState.whatsappSafetyEvents = data.events || [];
                appState.whatsappSafetyGateway = data.gateway || {};
                if(mainNav === 'guard' || window.targetPickerOpen) render(true);
            }catch(e){ if(!silent) showRealNotification('❌ Safety Guard', String(e.message || e), 'danger'); }
        }
        async function saveWhatsappSafetySettings(){
            ensureWhatsappSafetyStruct();
            const s = appState.whatsappSafetySettings || {};
            const checkedOr = (id, fallback) => document.getElementById(id) ? !!document.getElementById(id).checked : fallback;
            const valueOr = (id, fallback) => document.getElementById(id)?.value ?? fallback;
            const payload = {
                enabled: checkedOr('wa-safe-enabled', s.enabled !== false),
                globalPaused: checkedOr('wa-safe-paused', s.globalPaused === true),
                requireApprovedTargets: checkedOr('wa-safe-approved', s.requireApprovedTargets === true),
                duplicateBlock: checkedOr('wa-safe-dup', s.duplicateBlock !== false),
                autoPauseTargetOnFailures: checkedOr('wa-safe-target-autopause', s.autoPauseTargetOnFailures !== false),
                autoPauseGlobalOnFailures: checkedOr('wa-safe-global-autopause', s.autoPauseGlobalOnFailures !== false),
                safeModeForGroupsOnly: checkedOr('wa-safe-groups-only', s.safeModeForGroupsOnly === true),
                allowPrivateReplies: checkedOr('wa-safe-private', s.allowPrivateReplies !== false),
                allowAdminNotifications: checkedOr('wa-safe-admin', s.allowAdminNotifications !== false),
                minDelayMs: Number(valueOr('wa-safe-delay', s.minDelayMs ?? 2500)),
                randomDelayMs: Number(valueOr('wa-safe-random', s.randomDelayMs ?? 1200)),
                duplicateWindowMinutes: Number(valueOr('wa-safe-dup-window', s.duplicateWindowMinutes || 1440)),
                targetFailureLimit: Number(valueOr('wa-safe-target-fail', s.targetFailureLimit || 3)),
                globalConsecutiveFailureLimit: Number(valueOr('wa-safe-global-fail', s.globalConsecutiveFailureLimit || 8)),
                dailyTargetLimit: Number(valueOr('wa-safe-target-limit', s.dailyTargetLimit || 80)),
                dailyGlobalLimit: Number(valueOr('wa-safe-global-limit', s.dailyGlobalLimit || 300)),
                pauseReason: valueOr('wa-safe-reason', s.pauseReason || '')
            };
            try{
                const res = await fetch('/api/save_whatsapp_safety', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Save failed');
                appState.whatsappSafetySettings = data.settings || appState.whatsappSafetySettings;
                showRealNotification('✅ Safety Guard Saved', 'Outgoing WhatsApp safety settings save ho gaye.', 'success');
                await refreshWhatsappSafetyState(true);
            }catch(e){ showRealNotification('❌ Save Error', String(e.message || e), 'danger'); }
        }
        async function pauseWhatsappSafety(){
            const reason = prompt('Pause reason:', 'Manual safety pause') || 'Manual safety pause';
            try{
                const res = await fetch('/api/whatsapp_safety_pause', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({reason})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Pause failed');
                appState.whatsappSafetySettings = data.settings || appState.whatsappSafetySettings;
                showRealNotification('⏸️ WhatsApp Paused', 'All outgoing auto sends pause ho gaye.', 'info');
                await refreshWhatsappSafetyState(true);
            }catch(e){ showRealNotification('❌ Pause Error', String(e.message || e), 'danger'); }
        }
        async function resumeWhatsappSafety(){
            if(!confirm('WhatsApp sending resume karna hai?')) return;
            try{
                const res = await fetch('/api/whatsapp_safety_resume', {method:'POST'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Resume failed');
                appState.whatsappSafetySettings = data.settings || appState.whatsappSafetySettings;
                showRealNotification('▶️ WhatsApp Resumed', 'Outgoing sends resume ho gaye.', 'success');
                await refreshWhatsappSafetyState(true);
            }catch(e){ showRealNotification('❌ Resume Error', String(e.message || e), 'danger'); }
        }
        async function updateWhatsappSafetyTarget(id, status){
            const reason = status === 'pause' ? (prompt('Pause reason:', 'Manual target pause') || 'Manual target pause') : '';
            try{
                const res = await fetch('/api/whatsapp_safety_target', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target:id, status, reason})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Target update failed');
                await refreshWhatsappSafetyState(true);
                showRealNotification('✅ Target Updated', humanTargetId(id) + ' safety status update ho gaya.', 'success');
            }catch(e){ showRealNotification('❌ Target Error', String(e.message || e), 'danger'); }
        }
        async function clearWhatsappSafetyState(){
            if(!confirm('WhatsApp safety events/failures clear karne hain?')) return;
            try{
                const res = await fetch('/api/clear_whatsapp_safety', {method:'POST'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Clear failed');
                await refreshWhatsappSafetyState(true);
                showRealNotification('✅ Safety Cleared', 'Events/failure counters clear ho gaye.', 'success');
            }catch(e){ showRealNotification('❌ Clear Error', String(e.message || e), 'danger'); }
        }
        function renderWhatsappSafetyPanel(){
            ensureWhatsappSafetyStruct();
            const s = appState.whatsappSafetySettings || {};
            const targets = appState.whatsappSafetyTargets || {};
            const events = appState.whatsappSafetyEvents || [];
            const gw = appState.whatsappSafetyGateway || {};
            const local = gw.local || {};
            const targetRows = Object.values(targets).slice(-25).reverse().map(rec => {
                const id = rec.id || rec.target || '';
                const paused = rec.paused === true;
                const approved = rec.approved !== false;
                return `<div class="native-card p-3 mb-2"><div class="flex justify-between gap-2"><div class="min-w-0"><p class="text-white font-black text-[11px] truncate">${htmlEscape(rec.name || humanTargetId(id))}</p><p class="text-[var(--text-muted)] text-[9px] break-all">${htmlEscape(id)}</p><p class="text-[9px] mt-1">${targetSafetyBadge(id)} <span class="text-[var(--text-muted)]">Sent today: ${rec.dailyCount || 0} · Fail: ${rec.failureCount || 0}</span></p></div><div class="flex flex-col gap-1 shrink-0"><button onclick="updateWhatsappSafetyTarget('${attrEscape(id)}','${approved?'':'approve'}')" class="px-2 py-1 rounded-lg ${approved?'bg-[rgba(0,194,111,0.12)] text-[var(--green)]':'bg-[var(--green)] text-white'} text-[8px] font-black uppercase">${approved?'Approved':'Approve'}</button><button onclick="updateWhatsappSafetyTarget('${attrEscape(id)}','${paused?'resume':'pause'}')" class="px-2 py-1 rounded-lg ${paused?'bg-[var(--primary)] text-white':'bg-[rgba(255,93,93,0.12)] text-[var(--rose)]'} text-[8px] font-black uppercase">${paused?'Resume':'Pause'}</button><button onclick="updateWhatsappSafetyTarget('${attrEscape(id)}','reset_failures')" class="px-2 py-1 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] text-[8px] font-black uppercase">Reset</button></div></div>${rec.lastError ? `<p class="mt-2 text-[var(--rose)] text-[9px] break-words">${htmlEscape(rec.lastError)}</p>` : ''}</div>`;
            }).join('') || `<div class="native-card p-4 text-center text-[var(--text-muted)] text-[11px]">Abhi target safety history nahi hai. Pehla send hone ke baad targets yahan dikhenge.</div>`;
            const evRows = events.slice(0,20).map(ev => `<div class="border-b border-[var(--border)] py-2"><div class="flex justify-between gap-2"><p class="text-white font-black text-[10px] uppercase">${htmlEscape(ev.action || '-')}</p><p class="text-[var(--text-muted)] text-[9px]">${String(ev.time || '').replace('T',' ').slice(0,16)}</p></div><p class="text-[var(--text-muted)] text-[9px] break-all">${htmlEscape(ev.target || '')}${ev.error ? ' · ' + htmlEscape(ev.error) : ''}</p></div>`).join('') || '<p class="text-[var(--text-muted)] text-[11px] text-center p-3">No outgoing safety events yet.</p>';
            return `<div class="sec-header">WhatsApp Safe Messaging <button onclick="refreshWhatsappSafetyState()" class="text-[var(--primary)]"><i class="fas fa-sync"></i></button></div>
                <div class="native-card p-4 mb-3">
                    <div class="flex items-center justify-between gap-3 mb-3"><div><p class="text-white font-black text-[13px]">Outgoing Safety Guard</p><p class="text-[var(--text-muted)] text-[10px]">Duplicate block, slow queue, daily limit aur auto-pause.</p></div><span class="px-2 py-1 rounded-lg text-[9px] font-black uppercase ${s.globalPaused?'bg-[rgba(255,93,93,0.14)] text-[var(--rose)]':'bg-[rgba(0,194,111,0.14)] text-[var(--green)]'}">${s.globalPaused?'Paused':'Active'}</span></div>
                    <div class="grid grid-cols-2 gap-2 mb-3">
                        ${toggleRow('wa-safe-enabled','Safety ON', s.enabled !== false)}
                        ${toggleRow('wa-safe-paused','Global Pause', s.globalPaused === true)}
                        ${toggleRow('wa-safe-approved','Require Approved Targets', s.requireApprovedTargets === true)}
                        ${toggleRow('wa-safe-dup','Duplicate Block', s.duplicateBlock !== false)}
                        ${toggleRow('wa-safe-target-autopause','Target Auto Pause', s.autoPauseTargetOnFailures !== false)}
                        ${toggleRow('wa-safe-global-autopause','Global Auto Pause', s.autoPauseGlobalOnFailures !== false)}
                        ${toggleRow('wa-safe-groups-only','Groups Only Guard', s.safeModeForGroupsOnly === true)}
                        ${toggleRow('wa-safe-private','Allow Private Replies', s.allowPrivateReplies !== false)}
                        ${toggleRow('wa-safe-admin','Allow Admin Alerts', s.allowAdminNotifications !== false)}
                    </div>
                    <div class="grid grid-cols-3 gap-2 mb-3">
                        <label><p class="stat-lbl">Delay ms</p><input id="wa-safe-delay" type="number" min="0" value="${s.minDelayMs ?? 2500}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Random ms</p><input id="wa-safe-random" type="number" min="0" value="${s.randomDelayMs ?? 1200}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Dup Min</p><input id="wa-safe-dup-window" type="number" min="1" value="${s.duplicateWindowMinutes || 1440}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Target Fail</p><input id="wa-safe-target-fail" type="number" min="1" value="${s.targetFailureLimit || 3}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Global Fail</p><input id="wa-safe-global-fail" type="number" min="1" value="${s.globalConsecutiveFailureLimit || 8}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Target Daily</p><input id="wa-safe-target-limit" type="number" min="0" value="${s.dailyTargetLimit || 80}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Global Daily</p><input id="wa-safe-global-limit" type="number" min="0" value="${s.dailyGlobalLimit || 300}" class="native-input text-xs"></label>
                    </div>
                    <label><p class="stat-lbl">Pause Reason</p><input id="wa-safe-reason" value="${attrEscape(s.pauseReason || '')}" class="native-input text-left text-xs" placeholder="Reason shown in safety status"></label>
                    <div class="grid grid-cols-3 gap-2 mt-3"><button onclick="saveWhatsappSafetySettings()" class="bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[9px] uppercase">Save</button><button onclick="pauseWhatsappSafety()" class="bg-[rgba(255,93,93,0.12)] text-[var(--rose)] py-3 rounded-xl font-black text-[9px] uppercase">Pause All</button><button onclick="resumeWhatsappSafety()" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[9px] uppercase">Resume</button></div>
                    <div class="grid grid-cols-3 gap-2 mt-3"><div class="stat-box"><p class="stat-lbl">Queue</p><p class="stat-val">${local.queueDepth || 0}</p></div><div class="stat-box"><p class="stat-lbl">Sent Today</p><p class="stat-val">${(local.daily || {}).globalCount || 0}</p></div><div class="stat-box"><p class="stat-lbl">Failures</p><p class="stat-val">${local.consecutiveFailures || 0}</p></div></div>
                    <p class="mt-3 text-[var(--text-muted)] text-[10px] leading-relaxed">Ban risk zero nahi hota, lekin ye guard fast/duplicate sending, repeated failures aur wrong target sends ko control karta hai.</p>
                </div>
                <div class="sec-header">Target Safety <button onclick="clearWhatsappSafetyState()" class="text-[var(--rose)] text-[10px] uppercase font-black">Clear</button></div>${targetRows}
                <div class="sec-header mt-3">Outgoing Safety Events</div><div class="native-card p-3 mb-3">${evRows}</div>`;
        }

        function ensureSpamGuardStruct(){
            if(!appState.spamGuardSettings) appState.spamGuardSettings = {enabled:true, groupsOnly:true, linkGuardEnabled:true, forwardGuardEnabled:true, deleteMessage:true, kickEnabled:true, exemptAdmins:true, linkStrikeLimit:3, forwardStrikeLimit:3, forwardWindowSeconds:60, alertMessage:'⚠️ ALERT - Bhai Group Me Link Dalna Mana he', warningMessage:'⚠️ WARNING - Next Time Group Me Link Daloge To Remove Kiya Jayega Group Se', kickMessage:'🚫 REMOVED - @{number} ko group se remove kiya gaya. Reason: 3 baar link/forward spam.', forwardAlertMessage:'⚠️ ALERT - Bhai Group Me Forward/Spam Message Dalna Mana he', forwardWarningMessage:'⚠️ WARNING - Next Time Multiple Forward Message Daloge To Remove Kiya Jayega Group Se'};
            if(!Array.isArray(appState.spamGuardEvents)) appState.spamGuardEvents = [];
        }
        async function refreshSpamGuardState(){
            ensureSpamGuardStruct();
            try{
                const res = await fetch('/api/spam_guard');
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Spam guard load failed');
                appState.spamGuardSettings = data.settings || appState.spamGuardSettings;
                appState.spamGuardEvents = data.events || [];
                appState.spamGuardStrikeCount = data.strikeCount || 0;
                render(true);
            }catch(e){ showRealNotification('❌ Guard Error', String(e.message || e), 'danger'); }
        }
        async function saveSpamGuardSettings(){
            ensureSpamGuardStruct();
            const payload = {
                enabled: document.getElementById('guard-enabled')?.checked,
                groupsOnly: document.getElementById('guard-groups-only')?.checked,
                linkGuardEnabled: document.getElementById('guard-link')?.checked,
                forwardGuardEnabled: document.getElementById('guard-forward')?.checked,
                deleteMessage: document.getElementById('guard-delete')?.checked,
                kickEnabled: document.getElementById('guard-kick')?.checked,
                exemptAdmins: document.getElementById('guard-exempt')?.checked,
                linkStrikeLimit: Number(document.getElementById('guard-link-limit')?.value || 3),
                forwardStrikeLimit: Number(document.getElementById('guard-forward-limit')?.value || 3),
                forwardWindowSeconds: Number(document.getElementById('guard-forward-window')?.value || 60),
                alertMessage: document.getElementById('guard-alert-msg')?.value || '',
                warningMessage: document.getElementById('guard-warning-msg')?.value || '',
                kickMessage: document.getElementById('guard-kick-msg')?.value || '',
                forwardAlertMessage: document.getElementById('guard-forward-alert-msg')?.value || '',
                forwardWarningMessage: document.getElementById('guard-forward-warning-msg')?.value || ''
            };
            try{
                const res = await fetch('/api/save_spam_guard', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Save failed');
                appState.spamGuardSettings = data.settings || appState.spamGuardSettings;
                showRealNotification('✅ Guard Saved', 'Spam/link guard settings save ho gaye.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Save Error', String(e.message || e), 'danger'); }
        }
        async function clearSpamGuardState(){
            if(!confirm('Spam guard strikes/events clear karne hain?')) return;
            try{
                const res = await fetch('/api/clear_spam_guard', {method:'POST'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Clear failed');
                appState.spamGuardEvents = [];
                appState.spamGuardStrikeCount = 0;
                showRealNotification('✅ Guard Cleared', 'Strikes aur events clear ho gaye.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Clear Error', String(e.message || e), 'danger'); }
        }
        function renderGuardTab(){
            ensureSpamGuardStruct();
            const g = appState.spamGuardSettings || {};
            const events = appState.spamGuardEvents || [];
            const evHtml = events.length ? events.slice(0,40).map(ev => `<div class="native-card p-3 mb-2"><div class="flex justify-between gap-2"><div><p class="text-white font-black text-[11px]">${ev.action || '-'} • ${ev.kind || '-'}</p><p class="text-[var(--text-muted)] text-[9px] break-all">${ev.senderJid || ''}</p><p class="text-[var(--text-muted)] text-[9px] break-all">${ev.chatJid || ''}</p></div><div class="text-right shrink-0"><p class="text-[var(--primary)] text-[10px] font-black">${ev.count || 0}</p><p class="text-[var(--text-muted)] text-[9px]">${String(ev.time || '').replace('T',' ').slice(0,16)}</p></div></div>${ev.textSample ? `<p class="mt-2 text-[var(--text-muted)] text-[9px] break-words">${ev.textSample}</p>` : ''}</div>`).join('') : `<div class="native-card p-4 text-center text-[var(--text-muted)] text-[11px]">No spam/link events yet.</div>`;
            return `<div class="p-3 pb-24">
                
                ${renderWhatsappSafetyPanel()}
                <div class="sec-header">Spam / Link Guard <button onclick="refreshSpamGuardState()" class="text-[var(--primary)]"><i class="fas fa-sync"></i></button></div>
                <div class="native-card p-4 mb-3">
                    <div class="grid grid-cols-2 gap-2 mb-3">
                        ${toggleRow('guard-enabled','Guard ON', g.enabled !== false)}
                        ${toggleRow('guard-groups-only','Groups Only', g.groupsOnly !== false)}
                        ${toggleRow('guard-link','Link Guard', g.linkGuardEnabled !== false)}
                        ${toggleRow('guard-forward','Forward Guard', g.forwardGuardEnabled !== false)}
                        ${toggleRow('guard-delete','Delete Msg', g.deleteMessage !== false)}
                        ${toggleRow('guard-kick','Kick ON', g.kickEnabled !== false)}
                        ${toggleRow('guard-exempt','Admin Exempt', g.exemptAdmins !== false)}
                    </div>
                    <div class="grid grid-cols-3 gap-2 mb-3">
                        <label><p class="stat-lbl">Link Limit</p><input id="guard-link-limit" type="number" min="1" value="${g.linkStrikeLimit || 3}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Forward Limit</p><input id="guard-forward-limit" type="number" min="1" value="${g.forwardStrikeLimit || 3}" class="native-input text-xs"></label>
                        <label><p class="stat-lbl">Window Sec</p><input id="guard-forward-window" type="number" min="10" value="${g.forwardWindowSeconds || 60}" class="native-input text-xs"></label>
                    </div>
                    <div class="space-y-2">
                        <label><p class="stat-lbl">Link Alert Message</p><textarea id="guard-alert-msg" class="native-input text-left text-xs min-h-[55px]">${g.alertMessage || ''}</textarea></label>
                        <label><p class="stat-lbl">Link Warning Message</p><textarea id="guard-warning-msg" class="native-input text-left text-xs min-h-[55px]">${g.warningMessage || ''}</textarea></label>
                        <label><p class="stat-lbl">Kick Message</p><textarea id="guard-kick-msg" class="native-input text-left text-xs min-h-[55px]">${g.kickMessage || ''}</textarea></label>
                        <label><p class="stat-lbl">Forward Alert Message</p><textarea id="guard-forward-alert-msg" class="native-input text-left text-xs min-h-[55px]">${g.forwardAlertMessage || ''}</textarea></label>
                        <label><p class="stat-lbl">Forward Warning Message</p><textarea id="guard-forward-warning-msg" class="native-input text-left text-xs min-h-[55px]">${g.forwardWarningMessage || ''}</textarea></label>
                    </div>
                    <button onclick="saveSpamGuardSettings()" class="mt-3 w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[11px] uppercase active:scale-95"><i class="fas fa-save mr-1"></i> Save Guard Settings</button>
                    <button onclick="clearSpamGuardState()" class="mt-2 w-full bg-[rgba(255,93,93,0.12)] text-[var(--rose)] py-3 rounded-xl font-black text-[11px] uppercase active:scale-95"><i class="fas fa-trash mr-1"></i> Clear Strikes / Events</button>
                    <p class="mt-3 text-[var(--text-muted)] text-[10px] leading-relaxed">Remove/delete ke liye bot ko WhatsApp group admin banana zaroori hai. Admin Exempt ON rahega to group admins par action nahi hoga.</p>
                </div>
                <div class="sec-header">Recent Guard Events <span>${appState.spamGuardStrikeCount || 0} strikes</span></div>
                ${evHtml}
            </div>`;
        }

        // ==========================================

        // HEALTH MONITOR UI HELPERS
        function ensureHealthMonitorStruct(){
            if(!appState.healthMonitor) appState.healthMonitor = null;
        }
        async function refreshHealthMonitor(){
            ensureHealthMonitorStruct();
            try{
                const res = await fetch('/api/health_monitor?ts=' + Date.now());
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Health load failed');
                appState.healthMonitor = data.health || {};
                if(mainNav === 'health') render(false);
            }catch(e){
                appState.healthMonitor = {gateway:{status:'offline', connected:false, message:String(e.message || e)}, counts:{}, modules:{}, firebase:{status:'error'}};
                if(mainNav === 'health') render(false);
                showRealNotification('❌ Health Error', String(e.message || e), 'danger');
            }
        }
        async function resetWhatsAppSession(){
            if(!confirm('WhatsApp session reset karna hai? Iske baad fresh QR scan karna padega.')) return;
            try{
                const res = await fetch('/api/wa_reset_session', {method:'POST'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Reset failed');
                showRealNotification('✅ WhatsApp Reset', 'Fresh QR generate ho raha hai. 3-5 sec wait karein.', 'success');
                setTimeout(refreshHealthMonitor, 2500);
                setTimeout(refreshHealthMonitor, 6500);
            }catch(e){ showRealNotification('❌ Reset Error', String(e.message || e), 'danger'); }
        }
        async function refreshWaLoginCard(){
            try{
                const res = await fetch('/api/wa_login_status?ts=' + Date.now());
                const data = await res.json();
                if(!appState.healthMonitor) appState.healthMonitor = {};
                if(!appState.healthMonitor.gateway) appState.healthMonitor.gateway = {};
                appState.healthMonitor.waLogin = data;
                appState.healthMonitor.gateway.waLogin = data;
                render(false);
            }catch(e){ showRealNotification('❌ Login Status', String(e.message || e), 'danger'); }
        }
        function healthStatusPill(ok, labelOk, labelBad, neutral){
            if(neutral){
                return `<span class="px-2 py-1 rounded-lg text-[9px] font-black uppercase bg-[rgba(122,156,184,0.14)] text-[var(--text-muted)] border border-[rgba(122,156,184,0.18)]">${neutral}</span>`;
            }
            return `<span class="px-2 py-1 rounded-lg text-[9px] font-black uppercase ${ok ? 'bg-[rgba(0,194,111,0.16)] text-[var(--green)] border border-[rgba(0,194,111,0.22)]' : 'bg-[rgba(255,93,93,0.14)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)]'}">${ok ? labelOk : labelBad}</span>`;
        }
        function healthTime(v){
            if(!v) return 'Never';
            try{
                const d = new Date(v);
                if(!isNaN(d.getTime())){
                    return d.toLocaleString('en-GB', {
                        timeZone: 'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit',
                        hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
                    }).replace(',', '');
                }
                return String(v).replace('T',' ').replace('Z','').slice(0,19);
            }catch(e){ return String(v); }
        }
        function healthGuardReason(reason){
            const labels = (appState.healthMonitor && appState.healthMonitor.last && appState.healthMonitor.last.guardReasonLabels) || {};
            return labels[reason] || ({
                fresh_open_missing: 'Old/final ignored — fresh open missing',
                close_open_mismatch: 'Close ignored — open/result mismatch',
                invalid_format: 'Invalid result format skipped',
                stale_candidate: 'Stale duplicate skipped'
            }[reason]) || reason || 'skipped';
        }
        function healthMoney(v){
            const n = Number(v || 0);
            return '₹' + (Number.isInteger(n) ? String(n) : n.toFixed(2));
        }
        function renderHealthMonitorTab(){
            const h = appState.healthMonitor || {};
            const gw = h.gateway || {};
            const gh = gw.health || h.health || {};
            const counts = h.counts || {};
            const mods = h.modules || {};
            const targets = h.gatewayTargets || {};
            const groups = (targets.groups || []).length || (((gw.targets || {}).groups) || 0);
            const contacts = (targets.contacts || []).length || (((gw.targets || {}).contacts) || 0);
            const resultScrape = gw.scrape || gw.resultScrape || {};
            const runtimeUpdates = gh.lastResultScrapeUpdates || [];
            const firebaseUpdates = (h.last && h.last.recentFirebaseResults) || [];
            const recentUpdates = runtimeUpdates.length ? runtimeUpdates : firebaseUpdates;
            const recentSkipped = (gh.lastResultScrapeSkipped || []).slice(-6);
            const gatewayOnline = gw.status === 'success' || gw.status === 'online';
            const waConnected = !!(gw.connected || gw.connected === true);
            const waLogin = h.waLogin || gw.waLogin || {};
            const cards = [
                {title:'Firebase', ok:h.firebase && h.firebase.status === 'success', line1:healthTime(h.firebase?.lastCheckedAt || ''), line2:h.firebase?.url || ''},
                {title:'Gateway', ok:gatewayOnline, line1:gh.startedAt ? 'Started: ' + healthTime(gh.startedAt) : (gw.message || ''), line2:'Port 3000'},
                {title:'WhatsApp', ok:waConnected, line1:gw.user ? (gw.user.name || gw.user.id || 'Connected') : (gh.lastWhatsAppEvent || ''), line2:gh.lastDisconnectCode ? 'Disconnect: ' + gh.lastDisconnectCode : ''},
                {title:'Auto Scrape', ok:!!mods.autoScrape && resultScrape.enabled !== false, line1:'Interval: ' + ((resultScrape.intervalMs || 0) / 1000 || '-') + 's', line2:(resultScrape.urls || []).join(', ')},
                {title:'Entry Parser', ok:!!mods.entryParser, line1:'Timing: ' + (mods.marketTiming ? 'ON' : 'OFF'), line2:'Risk: ' + (mods.riskLimits ? 'ON' : 'OFF')},
                {title:'Settlement', ok:!!mods.settlement, line1:'Today: ' + (counts.settlementsToday || 0), line2:'Result targets: ' + (counts.resultTargets || 0)},
                {title:'Payment', ok:!!mods.paymentAutomation, line1:'Pending: ' + (counts.paymentsPending || 0), line2:'Outbox: ' + (counts.paymentOutboxPending || 0)},
                {title:'Forwarder', ok:!!mods.loadForwarder, neutral:mods.loadForwarder ? '' : 'DISABLED', line1:'Queue: ' + (counts.loadForwardOutboxPending || 0), line2:'Last: ' + healthTime(h.last?.loadForwarder?.lastSentAt)},
                {title:'Guard', ok:!!mods.spamGuard, line1:'Events: ' + (counts.guardEvents || 0), line2:''}
            ];
            return `
                
                <div class="sec-header">System Health <button onclick="refreshHealthMonitor()" class="text-[var(--primary)]"><i class="fas fa-sync"></i></button></div>
                <div class="p-3 pb-28">
                    <div class="native-card p-4 mb-3 bg-[#1A3348] border border-[rgba(42,171,238,0.25)]">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <p class="text-white font-black text-[14px] uppercase">Titan Nova Health Monitor</p>
                                <p class="text-[var(--text-muted)] text-[10px] mt-1">Last check: ${healthTime(h.firebase?.lastCheckedAt || new Date().toISOString())}</p>
                            </div>
                            <div class="text-right">${healthStatusPill(gatewayOnline && waConnected, 'ONLINE', 'CHECK')}</div>
                        </div>
                        <div class="grid grid-cols-3 gap-2 mt-4 text-center">
                            <div class="stat-box"><p class="stat-lbl">Today Entries</p><p class="stat-val">${counts.acceptedEntriesToday || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Today Load</p><p class="stat-val">${healthMoney(counts.todayLoad || 0)}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Targets</p><p class="stat-val">${counts.resultTargets || 0}</p></div>
                        </div>
                    </div>
                    <div class="native-card p-4 mb-3 border border-[rgba(42,171,238,0.18)]">
                        <div class="flex items-center justify-between gap-3 mb-3">
                            <div>
                                <p class="text-white font-black text-[12px] uppercase"><i class="fab fa-whatsapp text-[var(--green)] mr-1"></i> WhatsApp Login Helper</p>
                                <p class="text-[var(--text-muted)] text-[10px] mt-1">Logout ho jaye to yahin se QR scan karke reconnect karo.</p>
                            </div>
                            ${healthStatusPill(waConnected, 'CONNECTED', (waLogin.qrAvailable ? 'QR READY' : 'OFFLINE'))}
                        </div>
                        ${waConnected ? `<div class="bg-[rgba(0,194,111,0.08)] border border-[rgba(0,194,111,0.16)] rounded-xl p-3 text-[10px] text-[var(--green)]">WhatsApp connected: ${gw.user ? (gw.user.name || gw.user.id || 'Connected') : 'Connected'}</div>` : `
                            <div class="grid grid-cols-1 gap-3">
                                ${waLogin.qrAvailable ? `<div class="bg-white rounded-2xl p-3 mx-auto w-[220px] h-[220px] flex items-center justify-center"><img src="/api/wa_qr_image?ts=${Date.now()}" class="w-[200px] h-[200px]" alt="WhatsApp QR"></div><p class="text-[var(--text-muted)] text-[10px] text-center">WhatsApp → Linked devices → Link a device → QR scan karo.</p>` : `<div class="bg-[rgba(250,199,72,0.08)] border border-[rgba(250,199,72,0.16)] rounded-xl p-3 text-[10px] text-[var(--amber)]">QR abhi available nahi hai. Refresh karo ya Reset Session dabao.</div>`}
                            </div>`}
                        <div class="grid grid-cols-2 gap-2 mt-3">
                            <button onclick="refreshWaLoginCard()" class="bg-[var(--surface-light)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-sync mr-1"></i> Refresh QR</button>
                            <button onclick="resetWhatsAppSession()" class="bg-[rgba(255,93,93,0.14)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-right-from-bracket mr-1"></i> Reset Session</button>
                        </div>
                        <p class="text-[9px] text-[var(--text-muted)] mt-3 break-all">Auth folder: ${waLogin.authDir || (gw.waLogin && gw.waLogin.authDir) || 'auth_info_baileys'}</p>
                    </div>
                    <div class="grid grid-cols-1 gap-2 mb-3">
                        ${cards.map(c => `<div class="native-card p-3"><div class="flex items-center justify-between gap-3"><div class="min-w-0"><p class="text-white font-black text-[12px] uppercase">${c.title}</p><p class="text-[var(--text-muted)] text-[10px] truncate mt-1">${c.line1 || '-'}</p><p class="text-[var(--text-muted)] text-[9px] truncate mt-0.5">${c.line2 || ''}</p></div>${healthStatusPill(c.ok, 'OK', 'OFF', c.neutral || '')}</div></div>`).join('')}
                    </div>
                    <div class="native-card p-4 mb-3">
                        <p class="text-white font-black text-[12px] uppercase mb-3">Gateway Details</p>
                        <div class="grid grid-cols-2 gap-2 text-center">
                            <div class="stat-box"><p class="stat-lbl">Groups</p><p class="stat-val">${groups || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Contacts</p><p class="stat-val">${contacts || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Gateway Now</p><p class="stat-val text-[11px]">${gw.now || '-'}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Timezone</p><p class="stat-val text-[10px]">${gw.timezone || '-'}</p></div>
                        </div>
                    </div>
                    <div class="native-card p-4 mb-3">
                        <p class="text-white font-black text-[12px] uppercase mb-3">Realtime Result Scrape</p>
                        <div class="space-y-2 text-[10px]">
                            <div class="flex justify-between gap-2"><span class="text-[var(--text-muted)]">Last scrape</span><span class="text-white font-bold text-right">${healthTime(gh.lastResultScrapeTickAt)}</span></div>
                            <div class="flex justify-between gap-2"><span class="text-[var(--text-muted)]">Status</span><span class="text-white font-bold text-right">${gh.lastResultScrapeStatus || '-'}</span></div>
                            <div class="flex justify-between gap-2"><span class="text-[var(--text-muted)]">Last result send</span><span class="text-white font-bold text-right">${gh.lastResultSendAt ? healthTime(gh.lastResultSendAt) : 'No send since restart'} ${gh.lastResultSendSummary ? '— ' + gh.lastResultSendSummary : ''}</span></div>
                            <div class="flex justify-between gap-2"><span class="text-[var(--text-muted)]">Last send</span><span class="text-white font-bold text-right">${gh.lastSendAt ? healthTime(gh.lastSendAt) : 'No send since restart'} ${gh.lastSendOk === true ? '✅' : (gh.lastSendOk === false ? '❌' : '')}</span></div>
                            ${gh.lastResultScrapeError ? `<div class="bg-[rgba(255,93,93,0.1)] border border-[rgba(255,93,93,0.2)] rounded-xl p-2 text-[var(--rose)]">${gh.lastResultScrapeError}</div>` : ''}
                        </div>
                        <div class="mt-3">
                            <p class="stat-lbl">Recent Updates / Saved Results</p>
                            ${recentUpdates.length ? recentUpdates.map(x => `<div class="bg-[var(--surface-light)] rounded-xl p-2 mb-1 text-[10px] text-white flex justify-between gap-2"><span class="truncate">${x.market || '-'}</span><b class="shrink-0">${(x.stage || '').toUpperCase()} ${x.result || ''}</b></div>`).join('') : `<p class="text-[10px] text-[var(--text-muted)]">No saved result update recorded today.</p>`}
                            ${!runtimeUpdates.length && firebaseUpdates.length ? `<p class="text-[9px] text-[var(--text-muted)] mt-1">Showing Firebase saved results because Gateway runtime counters reset after restart.</p>` : ''}
                        </div>
                        ${recentSkipped.length ? `<div class="mt-3"><p class="stat-lbl">Guarded / Ignored Old Results</p><p class="text-[9px] text-[var(--text-muted)] mb-2">Ye warning nahi hai. System old/final result ko skip kar raha hai jab fresh open match nahi mila.</p>${recentSkipped.map(x => `<div class="bg-[rgba(250,199,72,0.06)] border border-[rgba(250,199,72,0.12)] rounded-xl p-2 mb-1 text-[10px] text-[var(--amber)]">${x.market || '-'} ${x.result || ''} — ${healthGuardReason(x.reason)}</div>`).join('')}</div>` : ''}
                    </div>
                    <div class="native-card p-4">
                        <p class="text-white font-black text-[12px] uppercase mb-3">Data Summary</p>
                        <div class="grid grid-cols-2 gap-2 text-center">
                            <div class="stat-box"><p class="stat-lbl">Profiles</p><p class="stat-val">${counts.profiles || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Wallets</p><p class="stat-val">${counts.wallets || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Result Markets</p><p class="stat-val">${counts.resultMarketsToday || 0}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Audit</p><p class="stat-val">${counts.auditEvents || 0}</p></div>
                        </div>
                        <p class="text-[9px] text-[var(--text-muted)] mt-3 leading-relaxed">Troubleshooting: Gateway/WhatsApp OFF ho to result/entry/send issue Gateway side hai. Firebase OK but queues pending ho to Gateway online rakhna hoga.</p>
                    </div>
                </div>`;
        }

        // BACKUP / EXPORT / AUDIT UI HELPERS
        // ==========================================
        function ensureBackupAuditStruct(){
            if(!appState.backupSummary) appState.backupSummary = {};
            if(!Array.isArray(appState.auditLog)) appState.auditLog = [];
        }
        async function refreshBackupAuditState(){
            ensureBackupAuditStruct();
            try{
                const res = await fetch('/api/backup_audit');
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Backup load failed');
                appState.backupSummary = data.summary || {};
                appState.auditLog = data.auditLog || [];
                render(true);
            }catch(e){ showRealNotification('❌ Backup Error', String(e.message || e), 'danger'); }
        }
        function downloadBackupZip(){
            window.open('/api/download_backup', '_blank');
            showRealNotification('✅ Backup Started', 'ZIP download start ho raha hai.', 'success');
            setTimeout(refreshBackupAuditState, 1200);
        }
        function exportCsv(kind){
            window.open('/api/export_csv?kind=' + encodeURIComponent(kind), '_blank');
        }
        async function clearAuditLog(){
            if(!confirm('Audit log clear karna hai? Backup ZIP pehle download karna recommended hai.')) return;
            try{
                const res = await fetch('/api/clear_audit_log', {method:'POST'});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Clear failed');
                appState.auditLog = data.auditLog || [];
                appState.backupSummary = data.summary || appState.backupSummary || {};
                showRealNotification('✅ Audit Cleared', 'Audit log clear ho gaya.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Clear Error', String(e.message || e), 'danger'); }
        }

        function setupStatusBadge(ok, text){
            return `<span class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${ok ? 'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]' : 'text-[var(--amber)] border-[rgba(250,199,72,0.25)] bg-[rgba(250,199,72,0.08)]'}">${text}</span>`;
        }
        function setupCard(title, icon, badge, body, actionHtml, accent='var(--primary)'){
            const iconClass = /^fa[bsr]?\\s/.test(String(icon || '')) ? icon : `fas ${icon}`;
            return `<section class="native-card p-4 mb-3" style="border-color:${accent.replace('var(--primary)','rgba(42,171,238,0.24)').replace('var(--green)','rgba(0,194,111,0.24)').replace('var(--amber)','rgba(250,199,72,0.24)').replace('var(--rose)','rgba(255,93,93,0.24)')}">
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div class="flex items-center gap-3 min-w-0">
                        <div class="w-10 h-10 rounded-xl bg-[var(--surface-light)] border border-[var(--border)] flex items-center justify-center shrink-0" style="color:${accent}"><i class="${iconClass}"></i></div>
                        <div class="min-w-0"><h3 class="text-white font-black text-[13px] uppercase truncate">${title}</h3><p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Clean Setup Section</p></div>
                    </div>
                    ${badge || ''}
                </div>
                <div class="text-[10px] text-[var(--text-muted)] leading-relaxed">${body}</div>
                ${actionHtml ? `<div class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">${actionHtml}</div>` : ''}
            </section>`;
        }
        function setupSaveButton(label, onclick, color='bg-[var(--primary)]'){
            return `<button onclick="${onclick}" class="w-full ${color} text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-save mr-1"></i>${label}</button>`;
        }
        function setupLinkButton(label, nav, icon='fa-arrow-right'){
            return `<button onclick="setMainNav('${nav}')" class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas ${icon} mr-1 text-[var(--primary)]"></i>${label}</button>`;
        }
        function setupMiniStat(label, value, color='text-white'){
            return `<div class="stat-box"><p class="stat-lbl">${label}</p><p class="stat-val ${color}">${value}</p></div>`;
        }
        function setupTargetCounts(listLike){
            const ids = Array.isArray(listLike) ? listLike : Object.values(listLike || {}).map(x => x && (x.id || x.target)).filter(Boolean);
            return ids.reduce((acc, id) => {
                if(normalizeTargetType(targetTypeFromId(id), id) === 'group') acc.groups += 1;
                else acc.contacts += 1;
                return acc;
            }, {groups:0, contacts:0});
        }
        function renderSetupMarketSettingsCard(marketCount){
            const cfg = state.config || {};
            const visibleMarkets = (baseMarkets || []).filter(m => !(m && m.hiddenForLedger)).length;
            const hiddenMarkets = Math.max(0, marketCount - visibleMarkets);
            const perCardRows = [['ank','ANK','text-[var(--primary)]'], ['jodi','JODI','text-[#B85CFF]'], ['pannel','PAN','text-[var(--amber)]']].map(([type,label,color]) => `
                <label class="bg-[var(--surface-light)] rounded-xl p-3 border border-[var(--border)]">
                    <p class="stat-lbl">${label} Per-card Target</p>
                    <input type="number" inputmode="numeric" class="native-input text-[12px] mt-1 ${color}" value="${Number((cfg[type] || {}).tgt || 0)}" oninput="state.config.${type}.tgt=parseFloat(this.value)||0; runLiveSync(); titanSaveAdminSettingsNow();">
                </label>`).join('');
            const body = `
                <div class="grid grid-cols-2 gap-2 mb-3">
                    <label><p class="stat-lbl">Capital</p><input type="number" inputmode="numeric" class="native-input text-[12px] text-[var(--green)]" value="${Number(cfg.capital || 0)}" oninput="state.config.capital=parseFloat(this.value)||0; titanSaveAdminSettingsNow();"></label>
                    <label><p class="stat-lbl">Day Target</p><input type="number" inputmode="numeric" class="native-input text-[12px] text-[var(--primary)]" value="${Number(cfg.dayTarget || 0)}" oninput="state.config.dayTarget=parseFloat(this.value)||0; titanSaveAdminSettingsNow();"></label>
                </div>
                <div class="grid grid-cols-1 gap-2 mb-3">${perCardRows}</div>
                <div class="grid grid-cols-3 gap-2">
                    ${setupMiniStat('Visible', visibleMarkets, 'text-[var(--green)]')}
                    ${setupMiniStat('Hidden', hiddenMarkets, hiddenMarkets ? 'text-[var(--amber)]' : 'text-white')}
                    ${setupMiniStat('Total', marketCount, 'text-white')}
                </div>`;
            return setupCard('Market Settings','fa-store',setupStatusBadge(true, marketCount + ' Markets'),body,setupSaveButton('Save Market Settings', "setupSaveSection('market')", 'bg-[var(--green)]'),'var(--green)');
        }
        function renderSetupScheduleSettingsCard(scheduleCount){
            ensureEntryStruct();
            const es = appState.entrySettings || {};
            const rs = appState.riskSettings || {};
            const timingOn = es.marketTimingEnabled !== false;
            const repeatOn = Object.values(appState.ledgerSchedules || {}).some(s => s && s.enabled !== false);
            const body = `
                <div class="grid grid-cols-2 gap-2 mb-3">
                    ${toggleRow('entryTimingToggle', timingOn ? 'Reject After Time' : 'Allow After Time', timingOn)}
                    ${toggleRow('entryRiskToggle', 'Safety Limits', es.riskLimitEnabled !== false)}
                </div>
                <input id="riskMarketLimit" type="hidden" value="${Number(rs.marketDailyLimit || 0)}"><input id="riskDigitLimit" type="hidden" value="${Number(rs.digitDailyLimit || 0)}"><input id="riskUserLimit" type="hidden" value="${Number(rs.userDailyLimit || 0)}"><input id="riskWarnPercent" type="hidden" value="${Number(rs.warningPercent || 80)}"><input id="riskAutoLock" type="checkbox" class="hidden" ${rs.autoLockOnLimit ? 'checked' : ''}>
                <div class="grid grid-cols-3 gap-2">
                    ${setupMiniStat('Entry Cutoff', timingOn ? 'Reject' : 'Allow', timingOn ? 'text-[var(--amber)]' : 'text-[var(--green)]')}
                    ${setupMiniStat('Daily Repeat', repeatOn ? 'ON' : 'OFF', repeatOn ? 'text-[var(--green)]' : 'text-[var(--text-muted)]')}
                    ${setupMiniStat('Saved', scheduleCount, 'text-white')}
                </div>`;
            return setupCard('Schedule Settings','fa-clock',setupStatusBadge(repeatOn, scheduleCount + ' Saved'),body,setupSaveButton('Save Schedule Settings', "setupSaveSection('schedule')"),'var(--primary)');
        }
        function renderSetupWhatsAppTargetsCard(){
            ensureWhatsappSafetyStruct(); ensureResultStruct();
            const resultCounts = setupTargetCounts(appState.resultTargets || []);
            const safetyCounts = setupTargetCounts(appState.whatsappSafetyTargets || {});
            const gw = appState.whatsappSafetyGateway || {};
            const connected = gw.connected === true || (gw.gateway && gw.gateway.connected) || (appState.healthMonitor && appState.healthMonitor.gateway && appState.healthMonitor.gateway.connected);
            const body = `
                <div class="grid grid-cols-3 gap-2">
                    ${setupMiniStat('Groups', resultCounts.groups || safetyCounts.groups, 'text-[var(--green)]')}
                    ${setupMiniStat('Private', resultCounts.contacts || safetyCounts.contacts, 'text-[var(--primary)]')}
                    ${setupMiniStat('Sync', connected ? 'Online' : 'Offline', connected ? 'text-[var(--green)]' : 'text-[var(--amber)]')}
                </div>
                <p class="text-[9px] text-[var(--text-muted)] mt-3">Summary uses existing saved result targets first, then safety target history. Target picker and gateway send logic unchanged.</p>`;
            return setupCard('WhatsApp Targets','fab fa-whatsapp',setupStatusBadge(connected, connected?'Synced':'Check'),body,setupSaveButton('Save WhatsApp Targets', "setupSaveSection('whatsapp')", 'bg-[var(--green)]'),'var(--green)');
        }
        async function setupRefreshStatuses(){
            try{ await Promise.all([refreshHealthMonitor(), refreshBackupAuditState()]); showRealNotification('✅ Setup Status', 'Latest Firebase/Gateway/backup status loaded.', 'success'); }
            catch(e){ showRealNotification('❌ Setup Status', String(e.message || e), 'danger'); }
        }
        async function setupSaveSection(section){
            try{
                if(section === 'market') { await saveMaster(false); }
                else if(section === 'schedule') { await saveEntrySafetySettings(); }
                else if(section === 'whatsapp') { await saveWhatsappSafetySettings(); }
                else throw new Error('Unknown setup section');
                showRealNotification('✅ Setup Saved', section + ' settings saved.', 'success');
            }catch(e){ showRealNotification('❌ Setup Save Error', String(e.message || e), 'danger'); }
        }
        function setupConfirmAction(label, fnName){
            if(!confirm(label + ' continue karna hai? Dangerous action se pehle backup download recommended hai.')) return;
            const fn = window[fnName];
            if(typeof fn === 'function') fn();
        }
        function renderSetupTab(){
            if(!IS_MASTER) return '';
            ensureDataStruct(); ensureBackupAuditStruct(); ensureWhatsappSafetyStruct();
            const hm = appState.healthMonitor || {};
            const fb = hm.firebase || {};
            const gw = hm.gateway || {};
            const cfg = (typeof TITAN_CONFIG_STATUS !== 'undefined' && TITAN_CONFIG_STATUS) ? TITAN_CONFIG_STATUS : {};
            const sec = cfg.security || {};
            const bs = appState.backupSummary || {};
            const targets = appState.whatsappSafetyTargets || {};
            const targetCount = Object.keys(targets).length;
            const marketCount = (Array.isArray(appState.marketRegistry) ? appState.marketRegistry.length : ((baseMarkets||[]).length));
            const scheduleCount = Object.keys(appState.ledgerSchedules || {}).length;
            const firebaseOk = fb.status === 'success' || fb.ok === true;
            const gatewayOk = gw.connected === true || gw.status === 'online' || (gw.gateway && gw.gateway.connected);
            const adminLocked = !!sec.adminTokenConfigured;
            const waEnabled = (appState.whatsappSafetySettings || {}).enabled !== false;
            return `<div class="px-3 py-4 pb-24">
                <div class="flex items-center justify-between mb-3">
                    <p class="sec-header m-0">Setup</p>
                    <button onclick="setupRefreshStatuses()" class="bg-[var(--surface-light)] border border-[var(--border)] text-[var(--primary)] px-3 py-2 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-sync mr-1"></i>Refresh</button>
                </div>
                ${setupCard('Firebase Status','fa-database',setupStatusBadge(firebaseOk, firebaseOk?'Saved / Online':'Check'),`URL: <span class="text-white break-all">${htmlEscape((cfg.firebase && cfg.firebase.urlRedacted) || fb.url || 'Configured on server')}</span><br>Guard: <span class="text-white">${htmlEscape((appState.firebaseDataGuard && appState.firebaseDataGuard.mode) || 'active')}</span><br>Status is read-only here; no persistence logic changed.`,setupLinkButton('Open Health','health','fa-heart-pulse'),'var(--green)')}
                ${setupCard('Gateway Status','fa-plug',setupStatusBadge(gatewayOk, gatewayOk?'Online':'Offline'),`Gateway: <span class="text-white">${htmlEscape(gw.message || gw.status || (gatewayOk?'Connected':'Not reachable'))}</span><br>WhatsApp runtime, result sender, and Gateway APIs remain unchanged.`,setupLinkButton('Open Gateway Health','health','fa-heart-pulse'),'var(--primary)')}
                ${setupCard('Admin Security','fa-user-shield',setupStatusBadge(adminLocked, adminLocked?'Locked':'Open'),`Admin token: <span class="text-white">${adminLocked ? 'Configured' : 'Missing / compatibility-open'}</span><br>Gateway token: <span class="text-white">${sec.gatewayTokenConfigured ? 'Configured' : 'Missing / fallback'}</span><br>Firebase URL: <span class="text-white break-all">${(cfg.firebase && cfg.firebase.urlRedacted) || fb.url ? 'Configured' : 'Fallback / server default'}</span><br><span class="text-[var(--amber)]">Read-only warning: token editing is disabled here. Change secrets only from environment/server config.</span>`,setupLinkButton('Security Health','health','fa-shield-halved'),'var(--amber)')}
                ${renderSetupMarketSettingsCard(marketCount)}
                ${renderSetupScheduleSettingsCard(scheduleCount)}
                ${renderSetupWhatsAppTargetsCard()}
                ${setupCard('Backup / Restore','fa-file-zipper',setupStatusBadge(true, (bs.auditEvents || 0) + ' Audit'),`Last backup: <span class="text-white">${bs.lastBackupAt ? String(bs.lastBackupAt).replace('T',' ').slice(0,19) : 'Never'}</span><br>Exports and backups remain in the existing Backup tab.`,setupLinkButton('Open Backup','backup','fa-file-export') + `<button onclick="downloadBackupZip()" class="w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-download mr-1"></i>Download Backup</button>`,'var(--amber)')}
                ${setupCard('Danger Zone','fa-triangle-exclamation',setupStatusBadge(false,'Confirm'),`Dangerous actions require confirmation. Existing features are not removed; this only adds a safer launch point.`,setupLinkButton('Review Audit','backup','fa-clipboard-list') + `<button onclick="setupConfirmAction('Audit log clear', 'clearAuditLog')" class="w-full bg-[rgba(255,93,93,0.16)] text-[var(--rose)] border border-[rgba(255,93,93,0.28)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-trash-alt mr-1"></i>Clear Audit Log</button>`,'var(--rose)')}
            </div>`;
        }

        function renderBackupAuditTab(){
            ensureBackupAuditStruct();
            const s = appState.backupSummary || {};
            const audit = appState.auditLog || [];
            const exportButtons = [
                ['entries','Entries CSV','fa-receipt'],
                ['wallets','Wallets CSV','fa-wallet'],
                ['wallet_ledger','Ledger CSV','fa-list'],
                ['wallet_transactions','Wallet History CSV','fa-clock-rotate-left'],
                ['payments','Payments CSV','fa-rupee-sign'],
                ['settlements','Settlements CSV','fa-trophy'],
                ['audit','Audit CSV','fa-clipboard-list']
            ];
            const auditHtml = audit.length ? audit.slice(0,80).map(a => `<div class="native-card p-3 mb-2"><div class="flex justify-between gap-2"><div class="min-w-0"><p class="text-white font-black text-[11px] truncate">${a.action || '-'}</p><p class="text-[var(--text-muted)] text-[9px] break-all">${a.id || ''}</p></div><p class="text-[var(--primary)] text-[9px] shrink-0">${String(a.time || '').replace('T',' ').slice(0,19)}</p></div><pre class="mt-2 text-[9px] text-[var(--text-muted)] whitespace-pre-wrap break-words bg-[#17212B] rounded-lg p-2 border border-[var(--border)] max-h-24 overflow-y-auto no-scrollbar">${String(JSON.stringify(a.detail || {}, null, 2)).replace(/</g,'&lt;')}</pre></div>`).join('') : `<div class="native-card p-5 text-center text-[var(--text-muted)] text-xs">No audit events.</div>`;
            return `<div class="p-3 pb-24">
                <div class="sec-header">Backup / Export / Audit <button onclick="refreshBackupAuditState()" class="text-[var(--primary)]"><i class="fas fa-sync"></i></button></div>
                <div class="wallet-hud rounded-2xl mb-3">
                    <div class="stat-box"><div class="stat-lbl">Entries</div><div class="stat-val">${s.entries || 0}</div></div>
                    <div class="stat-box"><div class="stat-lbl">Today Load</div><div class="stat-val">₹${Number(s.todayLoad || 0).toFixed(0)}</div></div>
                    <div class="stat-box"><div class="stat-lbl">Wallets</div><div class="stat-val">${s.wallets || 0}</div></div>
                    <div class="stat-box"><div class="stat-lbl">Audit Events</div><div class="stat-val">${s.auditEvents || 0}</div></div>
                </div>
                <div class="native-card p-4 mb-3">
                    <div class="flex items-start gap-3 mb-4">
                        <div class="w-11 h-11 rounded-2xl bg-[rgba(42,171,238,0.15)] text-[var(--primary)] flex items-center justify-center text-lg"><i class="fas fa-file-zipper"></i></div>
                        <div class="flex-1"><p class="text-white font-black text-[13px] uppercase">Full Backup ZIP</p><p class="text-[var(--text-muted)] text-[10px] leading-relaxed">state.json + entries/wallets/payments/settlements/audit CSV files. Last: ${s.lastBackupAt ? String(s.lastBackupAt).replace('T',' ').slice(0,19) : 'Never'}</p></div>
                    </div>
                    <button onclick="downloadBackupZip()" class="w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[11px] uppercase active:scale-95"><i class="fas fa-download mr-1"></i> Download Full Backup ZIP</button>
                </div>
                <div class="native-card p-4 mb-3">
                    <p class="text-white font-black text-[12px] uppercase mb-3">CSV Exports</p>
                    <div class="grid grid-cols-2 gap-2">${exportButtons.map(([kind,label,icon])=>`<button onclick="exportCsv('${kind}')" class="bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas ${icon} mr-1 text-[var(--primary)]"></i>${label}</button>`).join('')}</div>
                </div>
                <div class="native-card p-4 mb-3">
                    <p class="text-white font-black text-[12px] uppercase mb-2">Data Summary</p>
                    <div class="grid grid-cols-2 gap-2 text-[10px]">
                        <div class="bg-[var(--surface-light)] rounded-xl p-3"><p class="stat-lbl">Profiles</p><p class="text-white font-black">${s.profiles || 0}</p></div>
                        <div class="bg-[var(--surface-light)] rounded-xl p-3"><p class="stat-lbl">Pending Payments</p><p class="text-white font-black">${s.pendingPayments || 0}</p></div>
                        <div class="bg-[var(--surface-light)] rounded-xl p-3"><p class="stat-lbl">Settlements Today</p><p class="text-white font-black">${s.todaySettlements || 0}</p></div>
                        <div class="bg-[var(--surface-light)] rounded-xl p-3"><p class="stat-lbl">Accepted Today</p><p class="text-white font-black">${s.acceptedToday || 0}</p></div>
                    </div>
                </div>
                <div class="sec-header">Recent Audit <button onclick="clearAuditLog()" class="text-[var(--rose)] text-[10px] font-black uppercase">Clear</button></div>
                ${auditHtml}
            </div>`;
        }

        function toggleRow(id,label,checked){
            return `<label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="text-white text-[10px] font-bold">${label}</span><span class="switch"><input id="${id}" type="checkbox" ${checked?'checked':''}><span class="slider"></span></span></label>`;
        }

        // ==========================================
        // LOAD REPORT FORWARDER UI HELPERS
        // ==========================================
        function ensureLoadForwarderStruct(){
            if(!appState.loadForwarder) appState.loadForwarder = {enabled:false, scheduleTime:'18:00', selectedMarket:'', targets:[], gameTypes:['ANK','PENEL','JODI'], maxRowsPerType:80, includeEmptyTypes:false};
            if(!Array.isArray(appState.loadForwarder.targets)) appState.loadForwarder.targets = [];
            if(!Array.isArray(appState.loadForwarder.gameTypes) || !appState.loadForwarder.gameTypes.length) appState.loadForwarder.gameTypes = ['ANK','PENEL','JODI'];
            if(!Array.isArray(appState.forwardTargetOptions)) appState.forwardTargetOptions = [];
            if(typeof appState.loadForwarder.enabled === 'undefined') appState.loadForwarder.enabled = false;
            if(!appState.loadForwarder.scheduleTime) appState.loadForwarder.scheduleTime = '18:00';
            if(!appState.loadForwarder.maxRowsPerType) appState.loadForwarder.maxRowsPerType = 80;
        }
        function forwardMarketsList(){
            const fromEntries = Array.from(new Set((appState.entries || []).map(e => String(e.market || '').trim().toUpperCase()).filter(Boolean)));
            const fromStatic = (markets || []).map(m => m.n).concat((baseMarkets || []).map(m => m.n));
            return Array.from(new Set(fromStatic.concat(fromEntries).map(x => String(x || '').trim().toUpperCase()).filter(Boolean))).sort();
        }
        async function refreshLoadForwarderState(){
            ensureLoadForwarderStruct();
            try{
                const market = encodeURIComponent(appState.loadForwarder.selectedMarket || '');
                const res = await fetch(`/api/load_forwarder?market=${market}`);
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Load forwarder load failed');
                appState.loadForwarder = data.settings || appState.loadForwarder;
                appState.loadReportPreview = data.text || '';
                render(true);
            }catch(e){ showRealNotification('❌ Forward Error', String(e.message || e), 'danger'); }
        }
        async function syncForwardTargets(){
            ensureLoadForwarderStruct();
            try{
                const res = await fetch('/api/wa_targets');
                const data = await res.json();
                const opts = [];
                (data.groups || []).forEach(g => opts.push({id:g.id, name:g.name || g.subject || g.id, type:'Group'}));
                (data.contacts || []).forEach(c => opts.push({id:c.id, name:c.name || c.id, type:'Private'}));
                (appState.loadForwarder.targets || []).forEach(t => { if(!opts.find(o => o.id === t)) opts.push({id:t, name:t, type:'Saved'}); });
                appState.forwardTargetOptions = opts;
                showRealNotification('✅ Targets Synced', `${opts.length} WhatsApp target loaded.`, 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Sync Error', String(e.message || e), 'danger'); }
        }
        function toggleForwardTarget(target, checked){
            ensureLoadForwarderStruct();
            const set = new Set(appState.loadForwarder.targets || []);
            if(checked) set.add(target); else set.delete(target);
            appState.loadForwarder.targets = Array.from(set);
        }
        function addManualForwardTarget(){
            ensureLoadForwarderStruct();
            const raw = document.getElementById('manual-forward-target')?.value || '';
            const parts = raw.split(String.fromCharCode(10)).join(',').split(',').map(x => x.trim()).filter(Boolean);
            if(!parts.length) return showRealNotification('⚠️ Empty', 'Number/group JID paste karo.', 'danger');
            const set = new Set(appState.loadForwarder.targets || []);
            parts.forEach(x => set.add(x));
            appState.loadForwarder.targets = Array.from(set);
            appState.forwardTargetOptions = appState.forwardTargetOptions || [];
            parts.forEach(x => { if(!appState.forwardTargetOptions.find(o => o.id === x)) appState.forwardTargetOptions.push({id:x, name:x, type:'Manual'}); });
            const inp = document.getElementById('manual-forward-target'); if(inp) inp.value = '';
            render(true);
        }
        function selectedLoadGameTypes(){
            const vals = [];
            ['ANK','PENEL','JODI'].forEach(gt => { if(document.getElementById('load-game-'+gt)?.checked) vals.push(gt); });
            return vals.length ? vals : ['ANK','PENEL','JODI'];
        }
        async function saveLoadForwarderSettings(){
            ensureLoadForwarderStruct();
            const payload = {
                enabled: document.getElementById('load-enabled')?.checked,
                scheduleTime: document.getElementById('load-schedule-time')?.value || '18:00',
                selectedMarket: document.getElementById('load-market')?.value || '',
                maxRowsPerType: Number(document.getElementById('load-max-rows')?.value || 80),
                includeEmptyTypes: document.getElementById('load-empty-types')?.checked,
                gameTypes: selectedLoadGameTypes(),
                targets: appState.loadForwarder.targets || []
            };
            try{
                const res = await fetch('/api/save_load_forwarder', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Save failed');
                appState.loadForwarder = data.settings || appState.loadForwarder;
                showRealNotification('✅ Forward Saved', 'Load report schedule/settings save ho gaya.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Save Error', String(e.message || e), 'danger'); }
        }
        async function previewLoadReport(){
            ensureLoadForwarderStruct();
            const market = encodeURIComponent(document.getElementById('load-market')?.value || appState.loadForwarder.selectedMarket || '');
            const rows = encodeURIComponent(document.getElementById('load-max-rows')?.value || appState.loadForwarder.maxRowsPerType || 80);
            const gameTypes = encodeURIComponent(selectedLoadGameTypes().join(','));
            try{
                const res = await fetch(`/api/load_report_preview?market=${market}&maxRowsPerType=${rows}&gameTypes=${gameTypes}`);
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Preview failed');
                appState.loadReportPreview = data.text || '';
                showRealNotification('📊 Preview Ready', 'Load report preview update ho gaya.', 'success');
                render(true);
            }catch(e){ showRealNotification('❌ Preview Error', String(e.message || e), 'danger'); }
        }
        async function sendLoadReportNow(){
            ensureLoadForwarderStruct();
            const market = document.getElementById('load-market')?.value || appState.loadForwarder.selectedMarket || '';
            const targets = appState.loadForwarder.targets || [];
            if(!targets.length) return showRealNotification('⚠️ No Target', 'Pehle WhatsApp target select/save karo.', 'danger');
            if(!confirm('Load report abhi selected targets par bhejna hai?')) return;
            try{
                const res = await fetch('/api/load_forwarder_send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({market, targets, gameTypes:selectedLoadGameTypes(), maxRowsPerType:Number(document.getElementById('load-max-rows')?.value || 80), source:'dashboard_send_now'})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Send queue failed');
                appState.loadReportPreview = data.text || appState.loadReportPreview;
                showRealNotification('✅ Queued', 'Gateway online hote hi load report send karega.', 'success');
            }catch(e){ showRealNotification('❌ Send Error', String(e.message || e), 'danger'); }
        }
        function renderForwarderTab(){
            ensureLoadForwarderStruct();
            const lf = appState.loadForwarder;
            const selected = new Set(lf.targets || []);
            const targetOptions = appState.forwardTargetOptions || (lf.targets || []).map(t => ({id:t, name:t, type:'Saved'}));
            const mlist = forwardMarketsList();
            const preview = appState.loadReportPreview || '';
            const selectedGames = new Set(lf.gameTypes || ['ANK','PENEL','JODI']);
            return `<div class="pb-24">
                <p class="sec-header">Load Report Forwarder</p>
                <div class="native-card p-3 mb-3">
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <div><p class="text-white font-black text-[13px] uppercase">Auto Load Forward</p><p class="text-[var(--text-muted)] text-[10px]">Daily selected market load report WhatsApp par send hoga.</p></div>
                        <label class="switch"><input id="load-enabled" type="checkbox" ${lf.enabled !== false && lf.enabled ? 'checked' : ''}><span class="slider"></span></label>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div><p class="stat-lbl">IST Time</p><input id="load-schedule-time" type="time" class="native-input text-[12px]" value="${lf.scheduleTime || '18:00'}"></div>
                        <div><p class="stat-lbl">Rows / Type</p><input id="load-max-rows" type="number" class="native-input text-[12px]" value="${lf.maxRowsPerType || 80}"></div>
                    </div>
                    <div class="mt-3"><p class="stat-lbl">Market</p><select id="load-market" class="native-input text-[12px] text-left"><option value="">ALL MARKETS</option>${mlist.map(m=>`<option value="${m}" ${String(lf.selectedMarket||'').toUpperCase()===m?'selected':''}>${m}</option>`).join('')}</select></div>
                    <div class="mt-3 bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                        <p class="stat-lbl mb-2">Game Type Blocks</p>
                        <div class="grid grid-cols-3 gap-2">${['ANK','PENEL','JODI'].map(gt=>`<label class="flex items-center justify-center gap-2 bg-[#17212B] rounded-lg p-2 text-[10px] font-black text-white border border-[var(--border)]"><input id="load-game-${gt}" type="checkbox" ${selectedGames.has(gt)?'checked':''}> ${gt}</label>`).join('')}</div>
                    </div>
                    <label class="mt-3 flex items-center justify-between gap-2 text-[10px] text-[var(--text-muted)] font-bold bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]"><span>Include empty ANK/PENEL/JODI blocks</span><input id="load-empty-types" type="checkbox" ${lf.includeEmptyTypes?'checked':''}></label>
                    <button onclick="saveLoadForwarderSettings()" class="mt-3 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-save mr-1"></i> Save Forward Settings</button>
                </div>
                <div class="native-card p-3 mb-3">
                    <div class="flex items-center justify-between gap-2 mb-2"><div><p class="text-white font-black text-[11px] uppercase">WhatsApp Targets</p><p class="text-[var(--text-muted)] text-[9px]">Groups/contacts separate picker use karo.</p></div><button onclick="openLoadForwardTargetPicker()" class="bg-[var(--primary)] text-white px-3 py-2 rounded-lg font-black text-[9px] uppercase"><i class="fas fa-list-check mr-1"></i> Pick</button></div>
                    <div class="bg-[#17212B] border border-[var(--border)] rounded-xl p-3 min-h-[54px]">${selectedTargetSummary(lf.targets || [], 6)}</div>
                    <p class="text-[9px] text-[var(--text-muted)] mt-3">Selected: ${(lf.targets || []).length}</p>
                </div>
                <div class="grid grid-cols-2 gap-2 px-3 mb-3">
                    <button onclick="previewLoadReport()" class="bg-[var(--surface-light)] text-white py-3 rounded-xl font-black text-[10px] uppercase border border-[var(--border)] active:scale-95"><i class="fas fa-eye mr-1"></i> Preview</button>
                    <button onclick="sendLoadReportNow()" class="bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-paper-plane mr-1"></i> Send Now</button>
                </div>
                <div class="native-card p-3 mx-3 mb-3"><p class="text-white font-black text-[11px] uppercase mb-2">Preview</p><pre class="text-[10px] text-[var(--text-muted)] whitespace-pre-wrap bg-[#17212B] rounded-xl p-3 border border-[var(--border)] max-h-80 overflow-y-auto no-scrollbar">${preview ? preview.replace(/</g,'&lt;') : 'Preview button dabao.'}</pre></div>
                <button onclick="refreshLoadForwarderState()" class="mx-3 w-[calc(100%-24px)] bg-[var(--surface-light)] text-white py-3 rounded-xl font-black text-[10px] uppercase border border-[var(--border)] active:scale-95"><i class="fas fa-refresh mr-1"></i> Refresh Forwarder</button>
            </div>`;
        }

        // ==========================================
        // AUTO RESULT SENDER UI HELPERS
        // ==========================================
        function ensureResultStruct(){
            if(!appState.resultRecords) appState.resultRecords = {};
            if(!appState.resultRecords[currentDate]) appState.resultRecords[currentDate] = {};
            if(!Array.isArray(appState.resultTargets)) appState.resultTargets = [];
            if(!appState.resultSettings) appState.resultSettings = {autoScrapeEnabled:true,useForwardTargetsForResults:true};
            if(typeof appState.resultSettings.autoScrapeEnabled === 'undefined') appState.resultSettings.autoScrapeEnabled = true;
            if(typeof appState.resultSettings.useForwardTargetsForResults === 'undefined') appState.resultSettings.useForwardTargetsForResults = true;
            if(!appState.settlementRecords) appState.settlementRecords = {};
            if(!appState.settlementRecords[currentDate]) appState.settlementRecords[currentDate] = {};
            if(!appState.ledgerAutoMarkRecords) appState.ledgerAutoMarkRecords = {};
            if(!appState.ledgerAutoMarkRecords[currentDate]) appState.ledgerAutoMarkRecords[currentDate] = {};
            if(!appState.settlementSettings) appState.settlementSettings = {enabled:true, includeSummaryInResultMessage:true, includeHitMissInResultMessage:false, autoLedgerMarking:true, autoLedgerMarkOnlyWait:true, autoLedgerApplyToAllProfiles:true, autoLedgerRecordResults:true, payoutMultipliers:{ank:9.5,jodi:9.5,penel:150}};
            if(typeof appState.settlementSettings.autoLedgerMarking === 'undefined') appState.settlementSettings.autoLedgerMarking = true;
            if(typeof appState.settlementSettings.autoLedgerMarkOnlyWait === 'undefined') appState.settlementSettings.autoLedgerMarkOnlyWait = true;
            if(typeof appState.settlementSettings.autoLedgerApplyToAllProfiles === 'undefined') appState.settlementSettings.autoLedgerApplyToAllProfiles = true;
            if(typeof appState.settlementSettings.autoLedgerRecordResults === 'undefined') appState.settlementSettings.autoLedgerRecordResults = true;
            if(!appState.settlementSettings.payoutMultipliers) appState.settlementSettings.payoutMultipliers = {ank:9.5,jodi:9.5,penel:150};
        }
        function resultStageLabel(value){
            const v = String(value || '').trim().replace(/\\s+/g, '');
            if(/^\\d{3}-\\d$/.test(v)) return 'open';
            if(/^\\d{3}-\\d{2}-\\d{3}$/.test(v)) return 'close';
            return '';
        }
        function getResultRec(marketName){
            ensureResultStruct();
            return appState.resultRecords[currentDate][marketName] || {};
        }
        function resultDisplayView(rec){
            rec = rec || {};
            const open = String(rec.openResult || '').trim().replace(/\\s+/g, '');
            const close = String(rec.closeResult || '').trim().replace(/\\s+/g, '');
            const openOk = resultStageLabel(open) === 'open' && rec.openInferredFromClose !== true;
            const closeOk = resultStageLabel(close) === 'close';
            let closeAfterOpen = true;
            try {
                const oa = Date.parse(rec.openUpdatedAt || rec.updatedAt || '');
                const ca = Date.parse(rec.closeUpdatedAt || rec.updatedAt || '');
                if(Number.isFinite(oa) && Number.isFinite(ca)) closeAfterOpen = ca >= oa;
            } catch(e) {}
            const freshCloseOk = closeOk && openOk && close.startsWith(open) && closeAfterOpen;
            return {
                open: openOk ? open : '',
                close: freshCloseOk ? close : '',
                rawClose: closeOk ? close : '',
                ignoredClose: closeOk && !freshCloseOk
            };
        }
        function titanResultTargetsText(){
            ensureResultStruct();
            return appState.resultTargets.join('\\n');
        }
        async function refreshResultsState(){
            try {
                const res = await fetch('/api/results?date=' + encodeURIComponent(currentDate));
                const data = await res.json();
                if(data.status === 'success'){
                    appState.resultRecords = data.resultRecords || {};
                    appState.resultTargets = data.resultTargets || [];
                    appState.resultSettings = data.resultSettings || {autoScrapeEnabled:true,useForwardTargetsForResults:true};
                    appState.settlementRecords = data.settlementRecords || {};
                    appState.ledgerAutoMarkRecords = data.ledgerAutoMarkRecords || appState.ledgerAutoMarkRecords || {};
                    appState.settlementSettings = data.settlementSettings || {enabled:true, includeSummaryInResultMessage:true, includeHitMissInResultMessage:false, autoLedgerMarking:true, autoLedgerMarkOnlyWait:true, autoLedgerApplyToAllProfiles:true, autoLedgerRecordResults:true, payoutMultipliers:{ank:9.5,jodi:9.5,penel:150}};
                }
            } catch(e) {}
        }
        async function saveResultTargetsList(targets){
            if(!IS_MASTER) return;
            targets = titanCleanTargets(Array.isArray(targets) ? targets.join(String.fromCharCode(10)) : String(targets || ''));
            try {
                const res = await fetch('/api/save_result_targets', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({targets})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Target save failed');
                appState.resultTargets = data.resultTargets || [];
                showRealNotification('✅ Result Targets Saved', appState.resultTargets.length + ' WhatsApp target ready.', 'success');
                render(true);
            } catch(e) { showRealNotification('❌ Error', String(e.message || e), 'danger'); }
        }
        async function saveResultTargets(){
            if(!IS_MASTER) return;
            const raw = document.getElementById('result-targets-input')?.value || (appState.resultTargets || []).join(String.fromCharCode(10));
            await saveResultTargetsList(raw);
        }
        async function syncResultTargets(){ openResultTargetPicker(); }
        // CHECKBOX_MANUAL_OVERWRITE_v49:
        // Result/settlement checkboxes must not depend on small API routes returning JSON.
        // In manual-overwrite mode the visible admin state is the source of truth, so
        // checkbox changes update appState immediately and then use the same full /save
        // overwrite path as the rest of the app. This prevents HTML/lock/error pages from
        // producing "Unexpected token '<'" and reverting the checkbox UI.
        async function saveResultScrapeSetting(enabled){
            titanMarkUiLocalWrite('result_scrape_toggle');
            if(!IS_MASTER) return;
            ensureResultStruct();
            appState.resultSettings.autoScrapeEnabled = !!enabled;
            if(typeof appState.resultSettings.useForwardTargetsForResults === 'undefined') appState.resultSettings.useForwardTargetsForResults = true;
            render(true);
            await saveMaster(true, true);
            showRealNotification(enabled ? '🟢 Auto Scrape ON' : '🔴 Auto Scrape OFF', enabled ? 'Gateway ab live result scrape karega.' : 'Gateway auto scrape skip karega. Manual Declare abhi bhi active hai.', enabled ? 'success' : 'danger');
        }

        async function saveResultDeliverySettings(){
            titanMarkUiLocalWrite('result_delivery_toggle');
            if(!IS_MASTER) return;
            ensureResultStruct();
            const useForward = document.getElementById('result-use-forward-targets')?.checked;
            appState.resultSettings.useForwardTargetsForResults = !!useForward;
            if(typeof appState.resultSettings.autoScrapeEnabled === 'undefined') appState.resultSettings.autoScrapeEnabled = true;
            render(true);
            await saveMaster(true, true);
            showRealNotification('✅ Delivery Saved', useForward ? 'Result targets + Forward targets dono use honge.' : 'Sirf Result targets use honge.', 'success');
        }
        async function retryResultDeclarations(){
            if(!IS_MASTER) return;
            if(!confirm('Aaj ke result send locks clear karke pending declarations retry karna hai?')) return;
            try {
                const res = await fetch('/api/gateway_result_retry', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({date: currentDate})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Retry failed');
                showRealNotification('🔁 Result Retry', (data.cleared || 0) + ' send lock clear. Gateway retry karega.', 'success');
            } catch(e) { showRealNotification('❌ Retry Error', String(e.message || e), 'danger'); }
        }
        async function runResultScrapeNow(){
            if(!IS_MASTER) return;
            ensureResultStruct();
            if(appState.resultSettings && appState.resultSettings.autoScrapeEnabled === false){
                showRealNotification('🔴 Auto Scrape OFF', 'Pehle switch ON karo, phir Scrape Now/Test run karo.', 'danger');
                return;
            }
            try {
                showRealNotification('🧲 Scraping Started', 'Gateway live result page check kar raha hai...', 'info');
                const res = await fetch('/api/gateway_scrape_results');
                const data = await res.json();
                if(data.status === 'offline') throw new Error(data.message || 'Gateway offline');
                if(data.status === 'error') throw new Error(data.message || 'Scrape failed');
                await refreshResultsState();
                const upd = data.updates || [];
                const scraped = data.scraped || [];
                showRealNotification('✅ Scrape Complete', `${upd.length} new update, ${scraped.length} result found.`, 'success');
                render(true);
            } catch(e){
                showRealNotification('❌ Scrape Error', String(e.message || e), 'danger');
            }
        }
        async function clearInvalidAutoResults(){
            if(!IS_MASTER) return;
            try {
                const res = await fetch('/api/clear_invalid_auto_results', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({date: currentDate})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Cleanup failed');
                appState.resultRecords = data.resultRecords || appState.resultRecords;
                const n = (data.cleared || []).length;
                showRealNotification('🛡️ Old Results Cleared', n + ' invalid close result removed/ignored.', n ? 'success' : 'info');
                render(true);
            } catch(e){
                showRealNotification('❌ Cleanup Error', String(e.message || e), 'danger');
            }
        }

        function settlementCurrency(){ return (appState.walletSettings && appState.walletSettings.currency) || '₹'; }
        function fmtSettlementMoney(v){
            const n = Number(v || 0);
            return settlementCurrency() + (Number.isInteger(n) ? String(n) : n.toFixed(2));
        }
        function todaySettlements(){
            ensureResultStruct();
            return Object.values(appState.settlementRecords[currentDate] || {}).filter(Boolean);
        }
        function settlementCardHtml(){
            ensureResultStruct();
            const list = todaySettlements().sort((a,b)=>String(b.settledAt||'').localeCompare(String(a.settledAt||'')));
            const enabled = !(appState.settlementSettings && appState.settlementSettings.enabled === false);
            const summaryOn = !(appState.settlementSettings && appState.settlementSettings.includeSummaryInResultMessage === false);
            const hitMissAutoOn = !!(appState.settlementSettings && appState.settlementSettings.includeHitMissInResultMessage === true);
            const autoLedgerOn = !(appState.settlementSettings && appState.settlementSettings.autoLedgerMarking === false);
            const autoOnlyWait = !(appState.settlementSettings && appState.settlementSettings.autoLedgerMarkOnlyWait === false);
            const autoAllProfiles = !(appState.settlementSettings && appState.settlementSettings.autoLedgerApplyToAllProfiles === false);
            const autoMarkToday = Object.values((appState.ledgerAutoMarkRecords && appState.ledgerAutoMarkRecords[currentDate]) || {}).filter(Boolean).sort((a,b)=>String(b.time||'').localeCompare(String(a.time||'')));
            const autoMarked = autoMarkToday.reduce((s,x)=>s+Number(x.marked||0),0);
            const autoPass = autoMarkToday.reduce((s,x)=>s+Number(x.pass||0),0);
            const autoFail = autoMarkToday.reduce((s,x)=>s+Number(x.fail||0),0);
            const totalPayout = list.reduce((s,x)=>s+Number(x.payoutTotal||0),0);
            const totalStake = list.reduce((s,x)=>s+Number(x.totalStake||0),0);
            const totalProfit = list.reduce((s,x)=>s+Number(x.marketProfit||0),0);
            return `<p class="sec-header">Settlement Engine</p>
                <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.18);background:rgba(0,194,111,0.035)">
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <div>
                            <h3 class="text-white font-black text-[13px] uppercase">Result Settlement</h3>
                            <p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Result declare hote hi accepted entries settle hongi; winner wallet me payout credit hoga.</p>
                        </div>
                        <div class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${enabled ? 'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]' : 'text-[var(--rose)] border-[rgba(255,93,93,0.25)] bg-[rgba(255,93,93,0.08)]'}">${enabled ? 'ON' : 'OFF'}</div>
                    </div>
                    <div class="grid grid-cols-3 gap-2 mb-3">
                        <div class="stat-box"><p class="stat-lbl">Settled</p><p class="stat-val text-white">${list.length}</p></div>
                        <div class="stat-box"><p class="stat-lbl">Payout</p><p class="stat-val text-[var(--green)]">${fmtSettlementMoney(totalPayout)}</p></div>
                        <div class="stat-box"><p class="stat-lbl">P/L</p><p class="stat-val ${totalProfit>=0?'text-[var(--green)]':'text-[var(--rose)]'}">${fmtSettlementMoney(totalProfit)}</p></div>
                    </div>
                    <div class="grid grid-cols-3 gap-2 mb-3">
                        <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[10px] font-bold text-white">Settlement ON <input type="checkbox" onchange="saveSettlementSettings({enabled:this.checked})" ${enabled?'checked':''}></label>
                        <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[10px] font-bold text-white">Msg Summary <input type="checkbox" onchange="saveSettlementSettings({includeSummaryInResultMessage:this.checked})" ${summaryOn?'checked':''}></label>
                        <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[10px] font-bold text-white">Auto Hit/Miss <input type="checkbox" onchange="saveSettlementSettings({includeHitMissInResultMessage:this.checked})" ${hitMissAutoOn?'checked':''}></label>
                    </div>
                    <div class="mb-3 rounded-2xl border border-[rgba(250,199,72,0.22)] bg-[rgba(250,199,72,0.055)] p-3">
                        <div class="flex items-center justify-between gap-3 mb-2">
                            <div><p class="text-white font-black text-[12px] uppercase"><i class="fas fa-robot text-[var(--amber)] mr-1"></i> Ledger Auto Pass/Fail</p><p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Saved open/close result dekhkar ledger cards ko auto PASS/FAIL mark karega. Old direct close result blocked rahega.</p></div>
                            <div class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${autoLedgerOn ? 'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]' : 'text-[var(--rose)] border-[rgba(255,93,93,0.25)] bg-[rgba(255,93,93,0.08)]'}">${autoLedgerOn ? 'ON' : 'OFF'}</div>
                        </div>
                        <div class="grid grid-cols-3 gap-2 mb-2">
                            <div class="stat-box"><p class="stat-lbl">Marked</p><p class="stat-val text-white">${autoMarked}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Pass</p><p class="stat-val text-[var(--green)]">${autoPass}</p></div>
                            <div class="stat-box"><p class="stat-lbl">Fail</p><p class="stat-val text-[var(--rose)]">${autoFail}</p></div>
                        </div>
                        <div class="grid grid-cols-3 gap-2 mb-2">
                            <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">Auto Mark <input type="checkbox" onchange="saveSettlementSettings({autoLedgerMarking:this.checked})" ${autoLedgerOn?'checked':''}></label>
                            <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">Only WAIT <input type="checkbox" onchange="saveSettlementSettings({autoLedgerMarkOnlyWait:this.checked})" ${autoOnlyWait?'checked':''}></label>
                            <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 text-[9px] font-bold text-white">All VIPs <input type="checkbox" onchange="saveSettlementSettings({autoLedgerApplyToAllProfiles:this.checked})" ${autoAllProfiles?'checked':''}></label>
                        </div>
                        <button onclick="runLedgerAutoMarkNow()" class="w-full bg-[rgba(250,199,72,0.15)] text-[var(--amber)] border border-[rgba(250,199,72,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-wand-magic-sparkles mr-1"></i> Mark Now From Saved Results</button>
                        ${autoMarkToday.length ? `<div class="mt-2 max-h-24 overflow-y-auto no-scrollbar space-y-1">${autoMarkToday.slice(0,4).map(x=>`<div class="text-[8px] text-[var(--text-muted)] flex justify-between gap-2"><span>${x.market || ''} ${String(x.stage||'').toUpperCase()} ${x.result || ''}</span><span>✅${x.pass||0} ❌${x.fail||0}</span></div>`).join('')}</div>` : ''}
                    </div>
                    <p class="text-[9px] text-[var(--text-muted)] leading-relaxed mb-3">Auto Hit/Miss OFF recommended hai. Detailed list lambi hoti hai; settlement card se manual Send Hit/Miss use karo.</p>
                    ${list.length ? `<div class="space-y-2 max-h-56 overflow-y-auto no-scrollbar">${list.slice(0,10).map(x=>`<div class="bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3"><div class="flex items-center justify-between gap-2"><p class="text-white font-black text-[10px] uppercase">${x.market} ${String(x.stage||'').toUpperCase()}</p><p class="text-[var(--amber)] font-black text-[10px]">${x.result}</p></div><div class="grid grid-cols-4 gap-2 mt-2 text-center"><div><p class="stat-lbl">Entries</p><p class="text-white font-black text-[10px]">${x.eligibleCount||0}</p></div><div><p class="stat-lbl">Hit</p><p class="text-[var(--green)] font-black text-[10px]">${x.hitCount||0}</p></div><div><p class="stat-lbl">Miss</p><p class="text-[var(--rose)] font-black text-[10px]">${x.missCount||0}</p></div><div><p class="stat-lbl">Payout</p><p class="text-[var(--green)] font-black text-[10px]">${fmtSettlementMoney(x.payoutTotal||0)}</p></div></div><button onclick="sendHitMissReport(decodeURIComponent('${encodeURIComponent(String(x.market||''))}'), decodeURIComponent('${encodeURIComponent(String(x.stage||''))}'))" class="mt-3 w-full bg-[rgba(42,171,238,0.15)] text-[var(--primary)] border border-[rgba(42,171,238,0.25)] py-2 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-list-check mr-1"></i> Send Hit/Miss</button></div>`).join('')}</div>` : `<p class="text-[10px] text-[var(--text-muted)]">Aaj abhi koi settlement nahi hua.</p>`}
                </div>`;
        }

        async function sendHitMissReport(market, stage){
            if(!IS_MASTER) return;
            try {
                const res = await fetch('/api/send_hitmiss_report', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({date: currentDate, market, stage})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Hit/Miss send failed');
                showRealNotification('✅ Hit/Miss Sent', (data.sent || 0) + ' target par report send hua.', 'success');
            } catch(e){ showRealNotification('❌ Hit/Miss Error', String(e.message || e), 'danger'); }
        }

        async function runLedgerAutoMarkNow(){
            if(!IS_MASTER) return;
            try {
                const res = await fetch('/api/ledger_auto_mark', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({date: currentDate, force: false})});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Auto mark failed');
                const sum = data.summary || {};
                appState.ledgerAutoMarkRecords = data.ledgerAutoMarkRecords || appState.ledgerAutoMarkRecords || {};
                if(data.profiles) appState.profiles = data.profiles;
                state = appState.profiles[appState.activeId] || state;
                showRealNotification('🤖 Ledger Auto Mark', `${sum.marked || 0} card mark hua • PASS ${sum.pass || 0} / FAIL ${sum.fail || 0}`, (sum.marked || 0) ? 'success' : 'info');
                render(true);
            } catch(e){ showRealNotification('❌ Auto Mark Error', String(e.message || e), 'danger'); }
        }

        async function saveSettlementSettings(patch){
            if(!IS_MASTER) return;
            titanMarkUiLocalWrite('settlement_checkbox');
            ensureResultStruct();
            patch = patch || {};
            if(!appState.settlementSettings) appState.settlementSettings = {};
            Object.keys(patch).forEach(k => {
                if(k === 'payoutMultipliers' && patch[k] && typeof patch[k] === 'object'){
                    if(!appState.settlementSettings.payoutMultipliers) appState.settlementSettings.payoutMultipliers = {ank:9.5,jodi:9.5,penel:150};
                    Object.assign(appState.settlementSettings.payoutMultipliers, patch[k]);
                } else {
                    appState.settlementSettings[k] = patch[k];
                }
            });
            render(true);
            await saveMaster(true, true);
            showRealNotification('✅ Settlement Settings', 'Saved successfully.', 'success');
        }

        async function saveMarketResult(idx){
            if(!IS_MASTER) return;
            const market = resultBaseMarkets[idx]?.n || '';
            const input = document.getElementById('result-input-' + idx);
            const val = (input?.value || '').trim().replace(/\\s+/g, '');
            const stage = resultStageLabel(val);
            if(!stage){ showRealNotification('⚠️ Format Error', 'Open: 123-4 | Close: 123-45-678', 'danger'); return; }
            if(stage === 'close'){
                const rec = getResultRec(market);
                const view = resultDisplayView(rec);
                if(!view.open){ showRealNotification('⚠️ Fresh Open Missing', 'Close declare se pehle fresh open 123-4 save hona chahiye.', 'danger'); return; }
                if(!val.startsWith(view.open)){ showRealNotification('⚠️ Old/Unmatched Close', 'Close result open ' + view.open + ' se start hona chahiye.', 'danger'); return; }
            }
            if(!appState.resultTargets || !appState.resultTargets.length){
                showRealNotification('⚠️ Result Targets Missing', 'Pehle Result WhatsApp targets save karo.', 'danger');
                return;
            }
            try {
                const res = await fetch('/api/save_result', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({date: currentDate, market, result: val, source:'manual'})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Result save failed');
                appState.resultRecords = data.resultRecords || appState.resultRecords;
                showRealNotification(stage === 'open' ? '🏆 Open Result Saved' : '🏆 Close Result Saved', market + ' result Gateway se auto declare hoga.', 'success');
                render(true);
            } catch(e){ showRealNotification('❌ Error', String(e.message || e), 'danger'); }
        }





        // ==========================================
        // BAILEYS AUTO-SCHEDULE UI HELPERS
        // ==========================================
        function titanScheduleDict(type){ return type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData'); }

        // LEDGER_GLOBAL_BINDING_FIX: every visible card is bound by stable market key, not only by array index.
        function jsArg(v){ return "'" + String(v == null ? '' : v).replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'").replace(/</g, '\\\\u003C') + "'"; }
        function ledgerDictNameForType(type){ return type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData'); }
        function ledgerArrayForType(type){ return type === 'jodi' ? baseMarkets : markets; }
        function ledgerMarketKeyForName(type, name){ return `${String(type || '').toLowerCase()}|${String(name || '').toUpperCase().trim()}`; }
        function ledgerMarketKeyForCard(type, m){ return ledgerMarketKeyForName(type, (m && m.n) || ''); }
        function ledgerIndexForKey(type, marketKey){
            const arr = ledgerArrayForType(type) || [];
            const key = String(marketKey || '');
            if(!key) return -1;
            return arr.findIndex(m => ledgerMarketKeyForCard(type, m) === key);
        }
        function resolveLedgerIndex(type, idx, marketKey){
            const byKey = ledgerIndexForKey(type, marketKey);
            if(byKey >= 0) return byKey;
            const n = parseInt(idx, 10);
            return Number.isFinite(n) && n >= 0 ? n : -1;
        }
        function ledgerBlankRecord(rec){
            if(!rec || typeof rec !== 'object') return true;
            return !rec.s || rec.s === 'WAIT' && !rec.d && !rec.r && !rec.schTime && (!Array.isArray(rec.schTargets) || !rec.schTargets.length) && !rec.trick && !rec.od;
        }
        function annotateLedgerRecord(rec, type, idx, marketKey){
            rec = rec || {s:'WAIT', d:'', r:''};
            const arr = ledgerArrayForType(type) || [];
            const key = marketKey || ledgerMarketKeyForCard(type, arr[idx] || {});
            rec._ledgerKey = key;
            rec._marketName = ((arr[idx] && arr[idx].n) || '').toUpperCase().trim();
            rec._ledgerType = type;
            rec._ledgerIndex = parseInt(idx, 10);
            rec._ledgerDate = currentDate;
            return rec;
        }
        function stampLedgerMutation(rec, action, opts={}){
            rec = rec || {s:'WAIT', d:'', r:''};
            const now = new Date().toISOString();
            rec._updatedAt = now;
            rec._dirtyAt = now;
            rec._sourceAction = action || 'manual_input';
            if(opts.manualStatus){
                rec._manualStatusAt = now;
                rec._manualStatusBy = appState.activeId || 'admin1';
                delete rec.autoMarkedAt;
                delete rec.autoMarkedByResult;
                delete rec.autoMarkStage;
                delete rec.autoMarkMarket;
                delete rec.autoMarkWinDigit;
            }
            if(opts.clearDigit){ rec._digitClearedAt = now; rec._explicitClearedAt = now; rec.d = ''; delete rec.trick; delete rec.od; }
            if(opts.clearRate){ rec._rateClearedAt = now; rec._explicitClearedAt = now; rec.r = ''; rec._manualR = false; rec._autoR = false; delete rec._manualRateAt; delete rec._autoRateAt; delete rec._autoRateReason; }
            if(opts.reset){ rec._resetAt = now; rec._explicitClearedAt = now; rec._digitClearedAt = now; rec._rateClearedAt = now; delete rec._manualRateAt; delete rec._autoRateAt; delete rec._autoRateReason; }
            return rec;
        }
        function ensureLedgerRecordBoundForProfile(pState, profileId, type, idx, marketKey, create=true){
            if(!pState) return {idx:-1, key:marketKey || '', dictName:ledgerDictNameForType(type), rec:{s:'WAIT', d:'', r:''}};
            ensureDataStructForProfile(pState);
            idx = resolveLedgerIndex(type, idx, marketKey);
            const arr = ledgerArrayForType(type) || [];
            const dictName = ledgerDictNameForType(type);
            const key = marketKey || ledgerMarketKeyForCard(type, arr[idx] || {});
            const day = pState.dayRecords[currentDate] || (pState.dayRecords[currentDate] = {});
            const dict = day[dictName] || (day[dictName] = {});
            if(idx < 0) return {idx, key, dictName, rec:{s:'WAIT', d:'', r:''}};

            // If this market's record exists at another index, move it back to the visible card index.
            Object.keys(dict).forEach(k => {
                if(!/^\\d+$/.test(String(k))) return;
                if(parseInt(k,10) === idx) return;
                const r = dict[k];
                if(r && typeof r === 'object' && r._ledgerKey === key){
                    if(!dict[idx] || ledgerBlankRecord(dict[idx]) || (dict[idx]._ledgerKey && dict[idx]._ledgerKey !== key)){
                        dict[idx] = r;
                        delete dict[k];
                    }
                }
            });

            let rec = dict[idx];
            // If a different market's tagged record is sitting here, move it to its real slot when possible.
            if(rec && typeof rec === 'object' && rec._ledgerKey && rec._ledgerKey !== key){
                const realIdx = ledgerIndexForKey(type, rec._ledgerKey);
                if(realIdx >= 0 && realIdx !== idx && (!dict[realIdx] || ledgerBlankRecord(dict[realIdx]))){
                    dict[realIdx] = annotateLedgerRecord(rec, type, realIdx, rec._ledgerKey);
                    delete dict[idx];
                    rec = null;
                } else {
                    dict[`_orphan_${type}_${Date.now()}_${Math.random().toString(36).slice(2,7)}`] = rec;
                    dict[idx] = null;
                    rec = null;
                }
            }
            if(!rec && create) rec = {s:'WAIT', d:'', r:''};
            if(rec) {
                rec = annotateLedgerRecord(rec, type, idx, key);
                dict[idx] = mergePersistentScheduleIntoRecord(profileId, type, idx, rec, key);
                dict[idx] = annotateLedgerRecord(dict[idx], type, idx, key);
                rec = dict[idx];
            }
            return {idx, key, dictName, rec: rec || {s:'WAIT', d:'', r:''}};
        }
        function resolveLedgerAction(type, idx, marketKey){
            return ensureLedgerRecordBoundForProfile(state, appState.activeId || 'admin1', type, idx, marketKey, true);
        }
        function ensureLedgerScheduleStore(){
            if(!appState.ledgerSchedules || typeof appState.ledgerSchedules !== 'object' || Array.isArray(appState.ledgerSchedules)) appState.ledgerSchedules = {};
            return appState.ledgerSchedules;
        }
        function normalizeLedgerScheduleKeyPart(v){ return String(v == null ? '' : v).trim(); }
        function ledgerScheduleKey(profileId, type, idx=null, marketKey=null){
            const mk = normalizeLedgerScheduleKeyPart(marketKey);
            if(mk) return `${profileId}|${type}|${mk}`;
            return `${profileId}|${type}|${parseInt(idx,10)}`;
        }
        function ledgerScheduleKeyCandidates(profileId, type, idx=null, marketKey=null){
            const out = [];
            const mk = normalizeLedgerScheduleKeyPart(marketKey);
            if(mk) out.push(ledgerScheduleKey(profileId, type, idx, mk));
            if(idx !== null && typeof idx !== 'undefined'){
                const legacy = ledgerScheduleKey(profileId, type, idx, null);
                if(!out.includes(legacy)) out.push(legacy);
            }
            return out;
        }
        function titanScheduleSnapshot(rec){
            rec = rec || {};
            const out = {};
            // DATEWISE_LEDGER_FIX: schedule is daily-repeat configuration only.
            // Never store today's digits/rate/PASS/FAIL/trick inside persistent schedule.
            ['_ledgerKey','_marketName','_ledgerType','_ledgerIndex'].forEach(k => { if(typeof rec[k] !== 'undefined') out[k] = rec[k]; });
            return out;
        }
        function migrateLedgerSchedulesToMarketKeys(){
            const store = ensureLedgerScheduleStore();
            const out = {};
            Object.entries(store).forEach(([oldKey, item]) => {
                if(!item || typeof item !== 'object'){ out[oldKey] = item; return; }
                const profileId = item.profileId || String(oldKey).split('|')[0] || appState.activeId || 'admin1';
                const type = item.type || String(oldKey).split('|')[1] || '';
                if(!['ank','jodi','pannel'].includes(type)){ out[oldKey] = item; return; }
                let idx = Number.isFinite(parseInt(item.index,10)) ? parseInt(item.index,10) : null;
                let mk = normalizeLedgerScheduleKeyPart(item.marketKey || (item.record && item.record._ledgerKey) || '');
                // ✅ FIX: Safely handle null ledgerArrayForType
                if(!mk && idx !== null) { 
                    const arr = ledgerArrayForType(type) || [];
                    if(Array.isArray(arr) && idx >= 0 && idx < arr.length) {
                        mk = ledgerMarketKeyForCard(type, arr[idx] || {});
                    }
                }
                const newKey = ledgerScheduleKey(profileId, type, idx, mk);
                out[newKey] = {...item, profileId, type, index: idx, marketKey: mk, marketName: item.marketName || (((ledgerArrayForType(type)||[])[idx]||{}).n||''), keyVersion:'marketKey-v2'};
            });
            appState.ledgerSchedules = out;
            return out;
        }
        function getLedgerSchedule(profileId, type, idx, marketKey=null){
            const store = ensureLedgerScheduleStore();
            const mk = marketKey || ledgerMarketKeyForCard(type, (ledgerArrayForType(type) || [])[parseInt(idx,10)] || {});
            for(const key of ledgerScheduleKeyCandidates(profileId, type, idx, mk)){
                if(store[key] && typeof store[key] === 'object') return store[key];
            }
            return null;
        }
        function mergePersistentScheduleIntoRecord(profileId, type, idx, rec, marketKey=null){
            rec = rec || {s:'WAIT', d:'', r:''};
            const mk = marketKey || rec._ledgerKey || ledgerMarketKeyForCard(type, (ledgerArrayForType(type) || [])[parseInt(idx,10)] || {});
            const sched = getLedgerSchedule(profileId, type, idx, mk);
            if(sched && typeof sched === 'object'){
                // INTEL_SCHEDULE_TIME_FIX v17.3: persistent ledgerSchedules is the
                // source of truth for daily Intel time/targets. Today's card can have
                // stale schTime from an old full save, so overwrite it from the newer
                // persistent schedule store instead of preserving the old card value.
                if(sched.time) rec.schTime = sched.time;
                if(Array.isArray(sched.targets)) rec.schTargets = sched.targets.slice();
                // DATEWISE_LEDGER_FIX: only schedule time/targets repeat daily.
                // Digits/rate/status must stay date-specific and must not be restored
                // from persistent schedule after scrape/clear/reset or next-day fresh start.
                if(!rec._ledgerKey && (sched.marketKey || mk)) rec._ledgerKey = sched.marketKey || mk;
                if(!rec._marketName && sched.marketName) rec._marketName = sched.marketName;
            }
            return rec;
        }
        function updateLedgerScheduleStore(profileId, type, idx, rec, marketKey=null){
            const store = ensureLedgerScheduleStore();
            rec = rec || {};
            const mk = marketKey || rec._ledgerKey || ledgerMarketKeyForCard(type, (ledgerArrayForType(type) || [])[parseInt(idx,10)] || {});
            const key = ledgerScheduleKey(profileId, type, idx, mk);
            const legacyKeys = ledgerScheduleKeyCandidates(profileId, type, idx, null);
            const hadSchedule = !!store[key] || legacyKeys.some(k => !!store[k]);
            const targets = Array.isArray(rec.schTargets) ? rec.schTargets.filter(Boolean) : [];
            const time = rec.schTime || '';
            if(!hadSchedule && !time && !targets.length) return;
            if(!time && !targets.length){
                delete store[key];
                legacyKeys.forEach(k => { if(k !== key) delete store[k]; });
                return;
            }
            let current = store[key] || {};
            if(!current || !Object.keys(current).length){
                for(const lk of legacyKeys){ if(store[lk]) { current = store[lk]; break; } }
            }
            const idxNum = parseInt(idx,10);
            store[key] = {
                ...(current || {}),
                profileId: profileId,
                type: type,
                index: idxNum,
                marketKey: mk,
                marketName: rec._marketName || (((ledgerArrayForType(type) || [])[idxNum] || {}).n || ''),
                time: time,
                targets: targets,
                record: titanScheduleSnapshot(rec),
                repeat: 'daily',
                enabled: !!(time && targets.length),
                updatedAt: new Date().toISOString(),
                keyVersion: 'marketKey-v2'
            };
            legacyKeys.forEach(k => { if(k !== key) delete store[k]; });
        }
        function applyPersistentSchedulesForProfile(pState, profileId){
            if(!pState || !pState.dayRecords || !pState.dayRecords[currentDate]) return;
            const store = migrateLedgerSchedulesToMarketKeys();
            Object.keys(store).forEach(key => {
                const item = store[key];
                if(!item || item.profileId !== profileId) return;
                const type = item.type;
                let idx = ledgerIndexForKey(type, item.marketKey);
                if(idx < 0) idx = parseInt(item.index, 10);
                if(!['ank','jodi','pannel'].includes(type) || isNaN(idx) || idx < 0) return;
                const dn = titanScheduleDict(type);
                if(!pState.dayRecords[currentDate][dn]) pState.dayRecords[currentDate][dn] = {};
                const existing = pState.dayRecords[currentDate][dn][idx] || {s:'WAIT', d:'', r:''};
                pState.dayRecords[currentDate][dn][idx] = annotateLedgerRecord(mergePersistentScheduleIntoRecord(profileId, type, idx, existing, item.marketKey), type, idx, item.marketKey);
            });
        }
        function titanTargetsText(rec){
            let arr = (rec && Array.isArray(rec.schTargets)) ? rec.schTargets : [];
            return arr.length ? arr.join(', ') : 'No target';
        }
        function titanCleanTargets(raw){
            if(!raw) return [];
            return String(raw).split(/[\\r\\n,]+/).map(x => x.trim()).filter(Boolean);
        }
        async function saveScheduleNow(type, idx, marketKey=null, forceTime=null, forceTargets=null){
            if(!IS_MASTER) return;
            try {
                ensureDataStruct();
                const op = resolveLedgerAction(type, idx, marketKey);
                if(op.idx < 0) return;
                // SCHEDULE_PERSISTENCE_FIX v17.5:
                // Do NOT merge persistent schedule here. setScheduleTime() has just
                // edited the visible card, and merging old ledgerSchedules would put
                // the previous time (example 02:30) back into rec before POST.
                const rec = op.rec || {s:'WAIT', d:'', r:''};
                if(forceTime !== null && typeof forceTime !== 'undefined') rec.schTime = forceTime || '';
                if(Array.isArray(forceTargets)) rec.schTargets = forceTargets.slice();
                const intendedTime = rec.schTime || '';
                const intendedTargets = Array.isArray(rec.schTargets) ? rec.schTargets.slice().filter(Boolean) : [];
                state.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(rec, type, op.idx, op.key);
                updateLedgerScheduleStore(appState.activeId, type, op.idx, state.dayRecords[currentDate][op.dictName][op.idx], op.key);
                const res = await fetch('/api/schedule_targets', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        profileId: appState.activeId,
                        type: type,
                        index: op.idx,
                        marketKey: op.key,
                        time: intendedTime,
                        targets: intendedTargets,
                        record: rec
                    })
                });
                let data = null;
                const txt = await res.text();
                try{ data = txt ? JSON.parse(txt) : {}; }catch(parseErr){ data = {status:'error', message: txt.slice(0,180)}; }
                if(!res.ok || !data || data.status === 'error') {
                    throw new Error((data && data.message) || ('Schedule save HTTP '+res.status));
                }
                if(data && data.schedule){
                    const savedTime = data.schedule.time || '';
                    if(savedTime !== intendedTime){
                        throw new Error(`Schedule verify failed: requested ${intendedTime || 'blank'} but saved ${savedTime || 'blank'}`);
                    }
                    ensureLedgerScheduleStore()[ledgerScheduleKey(appState.activeId, type, op.idx, op.key)] = {...data.schedule, marketKey: op.key, keyVersion:'marketKey-v2'};
                    // Keep today's visible card in sync with source-of-truth after server commit.
                    rec.schTime = savedTime;
                    rec.schTargets = Array.isArray(data.schedule.targets) ? data.schedule.targets.slice() : intendedTargets;
                    state.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(rec, type, op.idx, op.key);
                }
                return {ok:true, time:intendedTime, targets:intendedTargets};
            } catch(e) {
                console.log('schedule save failed', e);
                try { showRealNotification('⚠️ Schedule Save Failed', e.message || String(e), 'error'); } catch(_){}
                return false;
            }
        }

        async function setScheduleTime(type, idx, value, marketKey=null){
            if(!IS_MASTER) return;
            ensureDataStruct();
            const op = resolveLedgerAction(type, idx, marketKey);
            if(op.idx < 0) return;
            op.rec.schTime = value || '';
            stampLedgerMutation(op.rec, 'schedule_time');
            state.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(op.rec, type, op.idx, op.key);
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'schedule_time');
            const ok = await saveScheduleNow(type, op.idx, op.key, value || '');
            if(ok) showRealNotification('⏰ Schedule Time', ok.time ? ('Time set: '+ok.time) : 'Time cleared', 'info');
        }
        async function pickCardContact(type, idx, marketKey=null){ openLedgerTargetPicker(type, idx, marketKey); }
        async function syncWhatsAppTargetsToCard(type, idx, marketKey=null){ openLedgerTargetPicker(type, idx, marketKey); }
        function clearCardTargets(type, idx, marketKey=null){
            if(!IS_MASTER) return;
            ensureDataStruct();
            const op = resolveLedgerAction(type, idx, marketKey);
            if(op.idx >= 0 && op.rec){
                op.rec.schTargets = [];
                state.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(op.rec, type, op.idx, op.key);
                recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'targets_clear');
                updateLedgerScheduleStore(appState.activeId, type, op.idx, op.rec, op.key);
                saveScheduleNow(type, op.idx, op.key, null, []); render(true);
            }
        }

        // ==========================================
        // AUTO-TRICK LOGIC WITH ADMIN SYNC
        // v42 fix: T1/T2/T3/T4 always run from the saved original 10-digit source.
        // This makes trick switching idempotent: T1 -> T2 -> T3 -> T4 can be changed anytime
        // without pressing Undo and without using the already-filtered 5 digits as input.
        // ==========================================
        function titanDigitList(value){ return (String(value || '').match(/\\d/g) || []); }
        function titanNormalizeOriginalDigits(rec, type, value, sourceAction){
            rec = rec || {s:'WAIT', d:'', r:''};
            if(type === 'jodi') return rec;
            const action = sourceAction || 'manual_input';
            const rawSourceActions = ['manual_input', 'scrape_digits', 'combo_scrape', 'smart_paste_digits'];
            const digits = titanDigitList(value);
            if(rawSourceActions.includes(action) && digits.length >= 10){
                rec.od = String(value || '');
                delete rec.trick;
            } else if(action === 'manual_input' && digits.length < 10){
                // User manually edited the digit box to a custom/non-source value.
                // It should no longer behave like an old T1/T2/T3 derived card.
                delete rec.trick;
                delete rec.od;
            }
            return rec;
        }
        function titanGetTrickSource(rec, currentValue){
            const inputText = String(currentValue || '').trim();
            const inputDigits = titanDigitList(inputText);
            const originalText = String((rec && rec.od) || '').trim();
            const originalDigits = titanDigitList(originalText);

            // If a trick was already applied, the visible box may contain only 5/6 digits.
            // Reuse the saved original source so another trick can replace the old one.
            if(originalDigits.length >= 10 && ((rec && rec.trick) || inputDigits.length < 10)){
                return {text: originalText, digits: originalDigits, fromOriginal: true};
            }
            if(inputDigits.length >= 10){
                return {text: inputText, digits: inputDigits, fromOriginal: false};
            }
            if(originalDigits.length >= 10){
                return {text: originalText, digits: originalDigits, fromOriginal: true};
            }
            return {text: inputText, digits: inputDigits, fromOriginal: false};
        }
        function applyTrick(type, i, trickNum, marketKey=null) {
            ensureDataStruct();
            const op = resolveLedgerAction(type, i, marketKey);
            if(op.idx < 0) return showRealNotification('⚠️ Ledger Error', 'Card mapping nahi mila. Refresh karke try karo.', 'danger');

            const realIdx = resolveLedgerIndex(type, i, marketKey);
            const inputEl = document.getElementById(`in-d-${type}-${realIdx >= 0 ? realIdx : i}`) || document.getElementById(`in-d-${type}-${i}`);
            if (!inputEl) return;

            const source = titanGetTrickSource(op.rec, inputEl.value);
            const val = source.text;
            const digits = source.digits;
            if (!digits || digits.length < 10) {
                showRealNotification('⚠️ Error', 'Trick ke liye pehle 10 original digits enter/scrape karein!', 'danger');
                return;
            }

            // Always keep the real source separately from the visible trick output.
            // Do not overwrite this with the 5-digit result.
            op.rec.od = val;

            let res = [];
            if (trickNum === 1) { res = [digits[1], digits[3], digits[5], digits[7], digits[9]]; }
            else if (trickNum === 2) { res = [digits[0], digits[2], digits[4], digits[6], digits[8]]; }
            else if (trickNum === 3 || trickNum === 4) {
                // T3/T4 ka rule digit-box ki visible positions par cut karta hai.
                // User-facing index 1-10 ko JS zero-based index 0-9 me map karke:
                // T3 cuts positions 1, 4, 7, 10; T4 cuts positions 2, 5, 6, 9.
                const cutIndexes = trickNum === 3 ? [0, 3, 6, 9] : [1, 4, 5, 8];
                res = digits.filter((_, idx) => !cutIndexes.includes(idx));
            }
            const formatted = res.join(', ');

            op.rec.d = formatted;
            op.rec.trick = 'T' + trickNum;
            op.rec = stampLedgerMutation(op.rec, 'trick_apply');
            op.rec = annotateLedgerRecord(op.rec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = op.rec;
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, op.rec, 'trick_apply');
            updateLedgerScheduleStore(appState.activeId, type, op.idx, op.rec, op.key);

            if(appState.activeId === 'admin1') {
                Object.keys(appState.profiles).forEach(pid => {
                    if(pid === 'admin1') return;
                    let pState = appState.profiles[pid];
                    const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                    vipOp.rec.od = val;
                    vipOp.rec.d = formatted;
                    vipOp.rec.trick = 'T' + trickNum;
                    vipOp.rec = stampLedgerMutation(vipOp.rec, 'trick_apply');
                    vipOp.rec = annotateLedgerRecord(vipOp.rec, type, vipOp.idx, vipOp.key);
                    pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = vipOp.rec;
                    updateLedgerScheduleStore(pid, type, vipOp.idx, vipOp.rec, vipOp.key);
                });
            }

            inputEl.value = formatted;
            runLiveSync(type, op.idx, 'd');
            let trickFinalRec = state.dayRecords[currentDate][op.dictName][op.idx] || op.rec;
            trickFinalRec = annotateLedgerRecord(trickFinalRec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = trickFinalRec;
            updateLedgerScheduleStore(appState.activeId, type, op.idx, trickFinalRec, op.key);
            if(appState.activeId === 'admin1') syncAdminAutoRateToVipProfiles(type, op.idx, op.key, trickFinalRec);
            titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, trickFinalRec, 'trick_apply', appState.activeId === 'admin1');
            showRealNotification('✅ Trick Changed', 'Original 10 digit source se ' + ('T' + trickNum) + ' apply ho gaya.', 'success');
            render(true);
        }

        function undoTrick(type, i, marketKey=null) {
            ensureDataStruct();
            const op = resolveLedgerAction(type, i, marketKey);
            let rec = op.rec;
            if(rec && rec.od) {
                const originalDigits = rec.od;
                rec.d = originalDigits;
                delete rec.trick;
                rec = stampLedgerMutation(rec, 'trick_undo');
                rec = annotateLedgerRecord(rec, type, op.idx, op.key);
                state.dayRecords[currentDate][op.dictName][op.idx] = rec;
                recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, rec, 'trick_undo');
                updateLedgerScheduleStore(appState.activeId, type, op.idx, rec, op.key);

                if(appState.activeId === 'admin1') {
                    Object.keys(appState.profiles).forEach(pid => {
                        if(pid === 'admin1') return;
                        let pState = appState.profiles[pid];
                        const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                        let r = vipOp.rec;
                        if(r && r.od) {
                            r.d = r.od;
                            delete r.trick;
                            r = stampLedgerMutation(r, 'trick_undo');
                            r = annotateLedgerRecord(r, type, vipOp.idx, vipOp.key);
                            pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = r;
                            updateLedgerScheduleStore(pid, type, vipOp.idx, r, vipOp.key);
                        }
                    });
                }

                runLiveSync(type, op.idx, 'd');
                let undoFinalRec = state.dayRecords[currentDate][op.dictName][op.idx] || rec;
                undoFinalRec = annotateLedgerRecord(undoFinalRec, type, op.idx, op.key);
                state.dayRecords[currentDate][op.dictName][op.idx] = undoFinalRec;
                updateLedgerScheduleStore(appState.activeId, type, op.idx, undoFinalRec, op.key);
                if(appState.activeId === 'admin1') syncAdminAutoRateToVipProfiles(type, op.idx, op.key, undoFinalRec);
                titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, undoFinalRec, 'trick_undo', appState.activeId === 'admin1');
                render(true);
                showRealNotification('🔙 Undo', 'Original digits wapas aa gaye!', 'info');
            }
        }

        function getTrickHistoryHTML(type, idx) {
            if (type === 'jodi') return '';
            const dictName = type === 'ank' ? 'data' : 'pannelData';
            let html = '<div class="flex gap-1 mt-3 pt-3 border-t border-[rgba(255,255,255,0.05)] items-center overflow-x-auto no-scrollbar shrink-0"><span class="text-[8px] font-bold text-[var(--text-muted)] uppercase mr-1 shrink-0"><i class="fas fa-history"></i> 7-DAY:</span>';
            let dObj = new Date(currentDate);
            let dayOfWeek = dObj.getDay();
            let diff = dObj.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
            let monday = new Date(dObj);
            monday.setDate(diff);

            let badges = [];
            for(let j = 0; j < 7; j++) {
                let pastDate = new Date(monday);
                pastDate.setDate(monday.getDate() + j);
                let dateStr = pastDate.getFullYear() + '-' + String(pastDate.getMonth() + 1).padStart(2, '0') + '-' + String(pastDate.getDate()).padStart(2, '0');
                let trick = '-';
                let tColor = 'bg-[var(--surface-light)] text-[var(--text-muted)] border-[var(--border)]';
                if (state.dayRecords[dateStr] && state.dayRecords[dateStr][dictName] && state.dayRecords[dateStr][dictName][idx]) {
                    let rec = state.dayRecords[dateStr][dictName][idx];
                    if (rec.trick) {
                        trick = rec.trick;
                        if (trick === 'T1') tColor = 'bg-[rgba(123,143,255,0.1)] text-[var(--purple)] border-[rgba(123,143,255,0.2)]';
                        else if (trick === 'T2') tColor = 'bg-[rgba(250,199,72,0.1)] text-[var(--amber)] border-[rgba(250,199,72,0.2)]';
                        else if (trick === 'T3') tColor = 'bg-[rgba(0,194,111,0.1)] text-[var(--green)] border-[rgba(0,194,111,0.2)]';
                        else if (trick === 'T4') tColor = 'bg-[rgba(42,171,238,0.1)] text-[var(--primary)] border-[rgba(42,171,238,0.2)]';
                    }
                }
                let dayName = pastDate.toLocaleDateString('en-US', {weekday: 'short'}).toUpperCase();
                badges.push(`<div class="flex flex-col items-center shrink-0"><span class="text-[6px] text-[var(--text-muted)] font-bold mb-0.5">${dayName}</span><span class="text-[8px] px-1.5 py-0.5 rounded font-black border ${tColor}">${trick}</span></div>`);
            }
            html += badges.join('<div class="w-px h-3 bg-[var(--surface-mid)] mx-0.5 shrink-0"></div>');
            html += '</div>';
            return html;
        }
        // ==========================================

        function ensureDataStructForProfile(pState) {
            if(!pState) return;
            if(!pState.config) pState.config = {};
            if(!pState.config.ank) pState.config.ank = {cap: 0, tgt: 0};
            if(!pState.config.jodi) pState.config.jodi = {cap: 0, tgt: 0};
            if(!pState.config.pannel) pState.config.pannel = {cap: 0, tgt: 0};
            if(typeof pState.config.ankSplit === 'undefined') pState.config.ankSplit = true;
            if(typeof pState.config.panSplit === 'undefined') pState.config.panSplit = true;
            if(typeof pState.config.capital === 'undefined') pState.config.capital = 0;
            if(typeof pState.config.dayTarget === 'undefined') pState.config.dayTarget = 0;
            if(typeof pState.approvalStatus === 'undefined') pState.approvalStatus = pState.autoCreated ? 'pending' : 'approved';
            if(typeof pState.vipAccessEnabled === 'undefined') pState.vipAccessEnabled = (pState.approvalStatus !== 'pending');
            if(pState.approvalStatus === 'pending') pState.vipAccessEnabled = false;
            if(!pState.dayRecords) pState.dayRecords = {};
            if(!pState.dayRecords[currentDate]) pState.dayRecords[currentDate] = {};
            if(!pState.dayRecords[currentDate].data) pState.dayRecords[currentDate].data = {};
            if(!pState.dayRecords[currentDate].jodiData) pState.dayRecords[currentDate].jodiData = {};
            if(!pState.dayRecords[currentDate].pannelData) pState.dayRecords[currentDate].pannelData = {};
            if(!pState.dayRecords[currentDate].visAnk) pState.dayRecords[currentDate].visAnk = {};
            if(!pState.dayRecords[currentDate].visJodi) pState.dayRecords[currentDate].visJodi = {};
            if(!pState.dayRecords[currentDate].visPan) pState.dayRecords[currentDate].visPan = {};
            try { applyPersistentSchedulesForProfile(pState, (pState === state ? appState.activeId : Object.keys(appState.profiles || {}).find(pid => appState.profiles[pid] === pState))); } catch(e) {}
        }

        function ensureDataStruct() { ensureDataStructForProfile(state); }

        // ✅ FIX #4: Cleanup orphaned ledger records to prevent Firebase bloat
        function cleanupOrphanedLedgerRecords(pState, type) {
            if(!pState || !pState.dayRecords || !pState.dayRecords[currentDate]) return;
            const dictName = ledgerDictNameForType(type);
            const dict = pState.dayRecords[currentDate][dictName];
            if(!dict || typeof dict !== 'object') return;
            let cleaned = 0;
            Object.keys(dict).forEach(k => {
                if(String(k).startsWith('_orphan_')) {
                    delete dict[k];
                    cleaned++;
                }
            });
            if(cleaned > 0) console.log(`🧹 Cleaned ${cleaned} orphaned ${type} records for ${currentDate}`);
        }

        function cleanupAllOrphanedRecords(pState) {
            ['ank', 'jodi', 'pannel'].forEach(type => cleanupOrphanedLedgerRecords(pState, type));
        }

        function renderAppBar() {
            const container = document.getElementById('top-bar-container');
            if(!container) return;

            const showSplitToggle = (IS_MASTER && mainNav === 'ledger' && (activeTab === 'ank' || activeTab === 'pannel'));
            const splitToggleChecked = (activeTab === 'ank') ? state.config.ankSplit : state.config.panSplit;

            let leftIcon = '';
            if (IS_MASTER && appState.activeId === 'admin1') {
                leftIcon = `<button onclick="toggleSidebar()" class="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-white active:scale-95 transition-all"><i class="fas fa-bars text-lg"></i></button>`;
            } else if (IS_MASTER && appState.activeId !== 'admin1') {
                leftIcon = `<button onclick="backToMasterUI()" class="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--primary)] active:scale-95 transition-all"><i class="fas fa-arrow-left text-lg"></i></button>`;
            } else {
                leftIcon = `<button onclick="toggleSidebar()" class="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-white active:scale-95 transition-all"><i class="fas fa-bars text-lg"></i></button>`;
            }

            let titleSection = (appState.activeId === 'admin1')
                ? `<div class="flex flex-col items-center"><h1 class="text-[15px] font-black tracking-tight text-white leading-tight">TITAN NOVA</h1><span class="text-[9px] text-[var(--primary)] font-bold uppercase tracking-wider">Admin Panel</span></div>`
                : `<div class="flex flex-col items-center"><h1 class="text-[15px] font-black tracking-tight text-white leading-tight">${state.name}</h1><span class="text-[9px] text-[var(--primary)] font-bold uppercase tracking-wider">VIP App${!IS_MASTER ? ' • LIVE' : ''}</span></div>`;

            let rightSection = `<div class="flex items-center gap-2">`;

            if (!IS_MASTER) {
                let bellColor = ('Notification' in window && Notification.permission === 'granted') ? 'text-[var(--green)]' : 'text-[var(--text-muted)]';
                rightSection += `
                    <button onclick="requestNotificationPermission()" class="w-9 h-9 rounded-xl flex items-center justify-center ${bellColor} active:scale-95 transition-all">
                        <i class="fas fa-bell text-lg"></i>
                    </button>`;
            }

            if (IS_MASTER) {
                rightSection += `
                    <button onclick="showInstallModal()" class="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] active:scale-95 transition-all">
                        <i class="fas fa-download text-lg"></i>
                    </button>`;
            }

            if (showSplitToggle) {
                rightSection += `
                    <div class="flex items-center gap-1.5 h-9 px-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl">
                        <label class="switch transform scale-75 m-0">
                            <input type="checkbox" onchange="toggleHybridMode(this.checked)" ${splitToggleChecked ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                        <span class="text-[8px] font-bold uppercase ${splitToggleChecked ? 'text-[var(--primary)]' : 'text-[var(--text-muted)]'}">Split</span>
                    </div>`;
            }
            rightSection += `
                <div class="relative w-9 h-9 bg-[var(--surface-light)] rounded-xl flex items-center justify-center border border-[var(--border)] text-[var(--text-muted)] overflow-hidden active:scale-95 transition-all">
                    <i class="fas fa-calendar-alt text-sm"></i>
                    <input type="date" value="${currentDate}" onchange="changeDate(this.value)" class="absolute inset-0 opacity-0 w-full h-full cursor-pointer">
                </div>
            </div>`;

            container.innerHTML = `${leftIcon} ${titleSection} ${rightSection}`;
        }

        // ── VIP capability helpers ──────────────────────────────
        function isVipPlanActive() {
            if(IS_MASTER) return true;
            const p = appState.profiles[appState.activeId] || {};
            const exp = p.expiryDate || '';
            if(!exp) return false;
            const expObj = new Date(exp); const today = new Date();
            today.setHours(0,0,0,0); expObj.setHours(0,0,0,0);
            return expObj >= today;
        }
        function vipCanEdit() {
            if(IS_MASTER) return true;
            const p = appState.profiles[appState.activeId] || {};
            return (p.vipAccessEnabled !== false);
        }
        function vipCanViewOnly() {
            if(IS_MASTER) return false;
            const p = appState.profiles[appState.activeId] || {};
            return (p.vipAccessEnabled === false);
        }
        // ────────────────────────────────────────────────────────

        function renderBottomNav() {
            let navHtml = '';
            const navItems = [
                { id: 'ledger', icon: 'fa-gamepad', label: 'Ledger' },
                { id: 'audit', icon: 'fa-chart-pie', label: 'Audit' }
            ];

            if(IS_MASTER) {
                if(appState.activeId === 'admin1') {
                    navItems.splice(1, 0, { id: 'clients', icon: 'fa-users', label: 'VIPs' });
                    navItems.splice(2, 0, { id: 'finance', icon: 'fa-wallet', label: 'Finance' });
                    navItems.splice(3, 0, { id: 'entries', icon: 'fa-receipt', label: 'Entries' });
                    navItems.splice(4, 0, { id: 'results', icon: 'fa-trophy', label: 'Results' });
                    navItems.splice(5, 0, { id: 'markets', icon: 'fa-store', label: 'Markets' });
                    navItems.splice(6, 0, { id: 'forward', icon: 'fa-share-nodes', label: 'Forward' });
                    navItems.splice(7, 0, { id: 'guard', icon: 'fa-shield-halved', label: 'Guard' });
                    navItems.splice(8, 0, { id: 'backup', icon: 'fa-file-export', label: 'Backup' });
                    navItems.splice(9, 0, { id: 'health', icon: 'fa-heart-pulse', label: 'Health' });
                    navItems.splice(10, 0, { id: 'setup', icon: 'fa-sliders-h', label: 'Setup' });
                    navItems.splice(11, 0, { id: 'smart', icon: 'fa-bolt', label: 'AI Scan' });
                }
            } else {
                // VIP always sees Settings tab, but inputs will be disabled if Read-Only
                navItems.push({ id: 'settings', icon: 'fa-sliders-h', label: 'Settings' });
                navItems.push({ id: 'membership', icon: 'fa-crown', label: 'Member' });
            }

            navItems.forEach(item => {
                navHtml += `<div onclick="setMainNav('${item.id}')" class="nav-item ${mainNav === item.id ? 'active' : ''}"><i class="fas ${item.icon}"></i><span>${item.label}</span></div>`;
            });
            const navEl = document.getElementById('bottom-nav-container');
            navEl.innerHTML = navHtml;
            const activeItem = navEl.querySelector('.nav-item.active');
            if(activeItem) {
                setTimeout(() => {
                    try { activeItem.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }); } catch(e) {}
                }, 0);
            }
        }

        function renderSubTabs() {
            if (mainNav !== 'ledger' && mainNav !== 'audit') return '';
            const t = (mainNav === 'ledger') ? activeTab : weeklyTabType;
            return `
                <div class="pill-tabs">
                    <button onclick="setSubTab('ank')" class="pill-tab ${t === 'ank' ? 'active' : ''}">Ank <span class="text-[9px] opacity-60 ml-1">x9.5</span></button>
                    <button onclick="setSubTab('jodi')" class="pill-tab ${t === 'jodi' ? 'active' : ''}">Jodi <span class="text-[9px] opacity-60 ml-1">x95</span></button>
                    <button onclick="setSubTab('pannel')" class="pill-tab ${t === 'pannel' ? 'active' : ''}">Pannel <span class="text-[9px] opacity-60 ml-1">x150</span></button>
                </div>
            `;
        }

        // v26 Lite: removed pro-dashboard inline helpers.
        function renderWalletHUD() {
            let activeStats; let pLabel = "Portfolio";
            let t = (mainNav === 'ledger') ? activeTab : weeklyTabType;
            if(t === 'ank') { activeStats = globalStats.ank; pLabel = "Ank Port."; }
            else if(t === 'jodi') { activeStats = globalStats.jodi; pLabel = "Jodi Port."; }
            else if(t === 'pannel') { activeStats = globalStats.pannel; pLabel = "Pan Port."; }

            const capital   = parseFloat(state.config.capital)   || 0;
            const dayTarget = parseFloat(state.config.dayTarget)  || 0;
            const totalPL   = globalStats.ank.pl + globalStats.jodi.pl + globalStats.pannel.pl;
            const dayPct    = dayTarget > 0 ? Math.min(100, Math.max(0, Math.round((totalPL / dayTarget) * 100))) : 0;

            const capitalRow = ((capital > 0 || dayTarget > 0)) ? `
                <div class="stat-box col-span-2 px-4 py-2.5" style="border-color:rgba(0,194,111,0.2);background:rgba(0,194,111,0.04)">
                    <div class="flex justify-between items-center mb-1.5">
                        <span class="stat-lbl" style="color:var(--green)">Capital: ₹${capital.toLocaleString()}</span>
                        <span class="stat-lbl ${totalPL >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${totalPL >= 0 ? '+' : ''}₹${totalPL.toLocaleString()} / ₹${dayTarget.toLocaleString()} <span class="font-black">${dayPct}%</span></span>
                    </div>
                    <div class="h-1.5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                        <div class="h-full rounded-full transition-all" style="width:${dayPct}%;background:${totalPL >= 0 ? 'var(--green)' : 'var(--rose)'}"></div>
                    </div>
                </div>` : '';

            return `
                <div class="wallet-hud">
                    <div class="stat-box">
                        <p class="stat-lbl">Total Spent</p>
                        <p id="stat-spent" class="stat-val text-[var(--text-muted)]">₹${activeStats.spent.toLocaleString()}</p>
                    </div>
                    <div class="stat-box" style="border-color:rgba(0,194,111,0.2); background:rgba(0,194,111,0.05)">
                        <p class="stat-lbl" style="color:var(--green)">Net P/L</p>
                        <p id="stat-pl" class="stat-val ${activeStats.pl >= 0 ? 'text-[#00C26F]' : 'text-[#FF5D5D]'}">${activeStats.pl >= 0 ? '+' : ''}₹${activeStats.pl.toLocaleString()}</p>
                    </div>
                    <div class="stat-box col-span-2 flex justify-between items-center" style="border-color:rgba(42,171,238,0.2); background:rgba(42,171,238,0.05)">
                        <div>
                            <p id="stat-port-label" class="stat-lbl" style="color:var(--primary)">${pLabel}</p>
                            <p id="stat-wallet" class="stat-val text-white">₹${activeStats.port.toLocaleString()}</p>
                        </div>
                        <div class="text-right">
                            <p class="stat-lbl" style="color:var(--rose)">Max Risk</p>
                            <p id="stat-maxloss" class="stat-val text-[#FF5D5D]">-₹${activeStats.maxLoss.toLocaleString()}</p>
                        </div>
                    </div>
                    ${capitalRow}
                </div>
            `;
        }

        function toggleHybridMode(isChecked) { ensureDataStruct(); if(activeTab === 'ank') state.config.ankSplit = isChecked; else if(activeTab === 'pannel') state.config.panSplit = isChecked; titanSaveAdminSettingsNow(); render(true); }
        function toggleMarketVis(visType, bmName, isChecked) { ensureDataStruct(); state.dayRecords[currentDate][visType][bmName] = isChecked; titanSaveAdminSettingsNow(); render(true); }
        function toggleAllMarkets(visType, isChecked) { ensureDataStruct(); const arr = visType === 'visJodi' ? baseMarkets : markets; arr.forEach(m => { state.dayRecords[currentDate][visType][m.n] = isChecked; }); titanSaveAdminSettingsNow(); render(true); }
        function setMainNav(nav) {
            if(['wallets','withdrawals','payments'].includes(nav)){
                financeSubTab = (nav === 'wallets') ? 'wallets' : (nav === 'withdrawals' ? 'withdrawals' : 'payments');
                mainNav = 'finance';
            } else {
                mainNav = nav;
            }
            render(false);
        }
        function setFinanceTab(tab) { financeSubTab = tab || 'summary'; render(false); }
        function setSubTab(tab) { if(mainNav === 'ledger') activeTab = tab; else if(mainNav === 'audit') weeklyTabType = tab; render(false); }
        function changeDate(d) { 
            autoSave();  // ✅ Save pending changes before switching
            ensureDataStruct();  // ✅ Initialize structures for new date
            currentDate = d; 
            manualDateMode = (d !== titanLocalDateISO()); 
            ensureDataStruct();  // ✅ Ensure new date is ready
            render(false); 
        }
        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); document.getElementById('sidebar-overlay').classList.toggle('hidden'); }

        async function saveMaster(silent = false, force = false) {
            if(!IS_MASTER) return;
            if(force) titanMarkUiLocalWrite('save_master_force');
            if(titanFullSaveInFlight){
                titanFullSaveQueued = true;
                return;
            }
            if(titanLedgerHasLocalDirty() && !force){
                if(!silent) showRealNotification('⏳ Ledger Save Active', 'Ledger card Firebase me save ho raha hai. 2 second baad Sync dabao.', 'info');
                return;
            }
            titanFullSaveInFlight = true;
            try {
                applyPendingLedgerPatchesToState(appState);
                // ✅ FIX #4: Clean up orphaned records before saving
                Object.keys(appState.profiles || {}).forEach(pid => {
                    cleanupAllOrphanedRecords(appState.profiles[pid]);
                });
                try { appState.ledgerClientCommit = {at:new Date().toISOString(), pending:Object.keys(titanReadPendingLedgerPatches()).length, fullSave:true, force:!!force}; } catch(e){}
                // v4: ledger changes are committed directly to Firebase; do not rely on local JSON.
                try { localStorage.removeItem(TITAN_LEDGER_PATCH_KEY); } catch(e) {}
                // v43: manual overwrite save. Admin UI state is written even when ledger local-hold is active.
                const res = await fetch('/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(appState) });
                if(!res || !res.ok){
                    let msg = 'Firebase save failed';
                    try { const j = await res.json(); msg = j.message || msg; } catch(e) {}
                    throw new Error(msg);
                }
                try { localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); } catch(e) {}
                if(force) titanMarkUiLocalWrite('save_master_success', 1800);
                if(!silent) {
                    const syncBtn = document.getElementById('ledger-sync-btn');
                    if(syncBtn) {
                        const oText = syncBtn.innerHTML;
                        syncBtn.innerHTML = '<i class="fas fa-check mr-2"></i> Synced';
                        syncBtn.style.background = "var(--green)"; syncBtn.style.color = "#fff";
                        setTimeout(() => { syncBtn.innerHTML = oText; syncBtn.style.background = ""; syncBtn.style.color = ""; }, 2000);
                    }
                }
            } catch (e) {
                if(!silent) showRealNotification('❌ Save Failed', String(e.message || e), 'danger');
            }
            finally {
                titanFullSaveInFlight = false;
                if(titanFullSaveQueued){
                    titanFullSaveQueued = false;
                    setTimeout(() => saveMaster(true, true), 80);
                }
            }
        }

        let titanLastAutoRateUpdates = [];
        function ledgerTrackKeyForMarket(type, marketObj, isSplitOn, trackPrefix){
            let key = trackPrefix || type || '';
            const name = String((marketObj && marketObj.n) || '').toUpperCase();
            if(trackPrefix !== 'jodi') key += (isSplitOn ? (name.includes('OPEN') ? 'Open' : 'Close') : 'Unified');
            return key;
        }
        function titanRecordAutoRateUpdate(type, idx, marketKey, rec, action){
            if(!IS_MASTER || !rec) return;
            titanLastAutoRateUpdates.push({type, idx: parseInt(idx, 10), key: marketKey || (rec && rec._ledgerKey) || '', rec: JSON.parse(JSON.stringify(rec)), action: action || 'auto_rate_suggest'});
        }
        function titanAutoRateCanRecalculate(rec){
            rec = rec || {};
            if(ledgerManualRateIsFresh(rec)) return false;
            // Blank rates and old Titan-generated rates are safe to refresh when recovery changes.
            if(String(rec.r || '').trim() === '') return true;
            return rec._autoR === true || rec._recoveryAutoR === true;
        }

        function getHistoricalMultiplier(type, idx, currentDateStr) {
            if(!IS_MASTER) return 1.0;
            const mRecs = appState.profiles['admin1'].dayRecords;
            const dates = Object.keys(mRecs).sort();
            const currPos = dates.indexOf(currentDateStr);
            const dictName = type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData');
            let dailyBoost = 0;
            if (currPos > 0) {
                let consecutiveFails = 0;
                for (let j = currPos - 1; j >= 0; j--) {
                    const rec = mRecs[dates[j]]?.[dictName]?.[idx];
                    if (!rec) continue;
                    if (rec.s === 'FAIL') consecutiveFails++;
                    else if (rec.s === 'PASS') break;
                }
                dailyBoost = consecutiveFails * 0.20;
            }
            let weeklyBoost = 0;
            const currObj = new Date(currentDateStr);
            currObj.setDate(currObj.getDate() - 7);
            const yyyy = currObj.getFullYear();
            const mm = String(currObj.getMonth() + 1).padStart(2, '0');
            const dd = String(currObj.getDate()).padStart(2, '0');
            const lastWeekRec = mRecs[`${yyyy}-${mm}-${dd}`]?.[dictName]?.[idx];
            if (lastWeekRec && lastWeekRec.s === 'FAIL') weeklyBoost = 0.10;
            return 1.0 + dailyBoost + weeklyBoost;
        }

        function getBaseNameForMarket(fullMarketName) { if (!fullMarketName) return null; const sorted = [...baseMarkets].sort((a, b) => b.n.length - a.n.length); for(let bm of sorted) { if(fullMarketName.includes(bm.n)) return bm.n; } return null; }

        function ledgerDigitCountForAutoRate(rec){
            const raw = rec && rec.d ? String(rec.d) : '';
            return raw.split(/[, ]+/).map(x => x.trim()).filter(Boolean).length;
        }
        function ledgerManualRateIsFresh(rec){
            rec = rec || {};
            if(!rec._manualR) return false;
            const manualAt = Number(rec._manualRateAt || 0);
            const digitAt = Number(rec._digitsTouchedAt || 0);
            // Legacy records had _manualR without timestamps. After a fresh digit edit,
            // let Titan calculate a new suggestion instead of permanently blocking auto-rate.
            return manualAt > 0 && manualAt >= digitAt;
        }
        function computeLedgerAutoRate(type, idx, count, debtValue, unrealValue, marginMultiplier, targetProf){
            const margin = Number(marginMultiplier || 0) - Number(count || 0);
            if(!(margin > 0)) return 0;
            const nextRate = (Number(debtValue || 0) + ((Number(unrealValue || 0) + 1) * Number(targetProf || 0))) / margin;
            const finalRate = Math.ceil((nextRate * getHistoricalMultiplier(type, idx, currentDate)) / 10) * 10;
            return Math.max(10, finalRate);
        }
        function applyLedgerAutoRateToRecord(rec, rate, reason, meta=null){
            if(!rec || !(Number(rate) > 0)) return rec;
            rec.r = String(rate);
            rec._autoR = true;
            rec._manualR = false;
            rec._autoRateAt = Date.now();
            rec._autoRateReason = reason || 'digit_change';
            if(reason === 'recovery_next_market' || (meta && meta.recovery)) rec._recoveryAutoR = true;
            if(meta && typeof meta === 'object'){
                if(typeof meta.debt !== 'undefined') rec._recoveryDebt = Number(meta.debt || 0);
                if(typeof meta.unreal !== 'undefined') rec._recoveryUnreal = Number(meta.unreal || 0);
                if(typeof meta.margin !== 'undefined') rec._recoveryMargin = Number(meta.margin || 0);
                if(typeof meta.targetProf !== 'undefined') rec._recoveryTargetProfit = Number(meta.targetProf || 0);
                if(typeof meta.trackKey !== 'undefined') rec._recoveryTrackKey = String(meta.trackKey || '');
                if(typeof meta.fromIdx !== 'undefined') rec._recoveryFromIdx = parseInt(meta.fromIdx, 10);
                if(typeof meta.baseRate !== 'undefined') rec._recoveryBaseRate = Number(meta.baseRate || 0);
            }
            delete rec._manualRateAt;
            return rec;
        }
        function syncAdminAutoRateToVipProfiles(type, idx, marketKey, masterRec){
            if(appState.activeId !== 'admin1' || !masterRec || !masterRec._autoR || String(masterRec.r || '').trim() === '') return;
            Object.keys(appState.profiles || {}).forEach(pid => {
                if(pid === 'admin1') return;
                const pState = appState.profiles[pid];
                const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, idx, marketKey, true);
                vipOp.rec.r = masterRec.r;
                vipOp.rec._autoR = true;
                vipOp.rec._manualR = false;
                vipOp.rec._autoRateAt = masterRec._autoRateAt || Date.now();
                vipOp.rec._autoRateReason = masterRec._autoRateReason || 'digit_change';
                delete vipOp.rec._manualRateAt;
                vipOp.rec = annotateLedgerRecord(vipOp.rec, type, vipOp.idx, vipOp.key);
                pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = vipOp.rec;
                recordLedgerLocalPatch(pid, type, vipOp.idx, vipOp.key, vipOp.rec, 'auto_rate_suggest');
                updateLedgerScheduleStore(pid, type, vipOp.idx, vipOp.rec, vipOp.key);
            });
        }

        function runLiveSync(changedType = null, changedIdx = -1, fieldChanged = null) {
            ensureDataStruct();
            titanLastAutoRateUpdates = [];
            globalStats = { ank: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 }, jodi: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 }, pannel: { spent: 0, win: 0, pl: 0, port: 0, maxLoss: 0 } };
            let debt = { ankOpen: 0, ankClose: 0, ankUnified: 0, jodi: 0, panOpen: 0, panClose: 0, panUnified: 0 };
            let unreal = { ankOpen: 0, ankClose: 0, ankUnified: 0, jodi: 0, panOpen: 0, panClose: 0, panUnified: 0 };
            const record = state.dayRecords[currentDate];
            // 🔧 BUG FIX #5: Add safety check for record existence
            if(!record) return;

            const processGroup = (type, dataDict, arr, marginMultiplier, trackPrefix) => {
                const targetProf = parseFloat(state.config[type].tgt) || 0;
                const visDict = type === 'ank' ? record.visAnk : (type === 'jodi' ? record.visJodi : record.visPan);
                const isSplitOn = (type === 'ank') ? state.config.ankSplit : (type === 'pannel' ? state.config.panSplit : false);
                const changedIndexNum = parseInt(changedIdx, 10);
                const changedMarket = (changedType === type && Number.isFinite(changedIndexNum) && changedIndexNum >= 0) ? arr[changedIndexNum] : null;
                const changedTrackKey = changedMarket ? ledgerTrackKeyForMarket(type, changedMarket, isSplitOn, trackPrefix) : '';
                const recoverySuggestedByTrack = {};
                let runningChronologicalPL = 0; let maxDip = 0;

                arr.forEach((m, i) => {
                    if (visDict && visDict[m.n] === false) return;
                    let trackKey = ledgerTrackKeyForMarket(type, m, isSplitOn, trackPrefix);
                    const d = dataDict[i] || { s: 'WAIT', d: '', r: '' };
                    const count = (d.d ? String(d.d) : '').split(/[, ]+/).filter(x => x.trim()).length;
                    const invest = count * (parseFloat(d.r) || 0);

                    if (d.s === 'FAIL') { runningChronologicalPL -= invest; if (runningChronologicalPL < maxDip) maxDip = runningChronologicalPL; debt[trackKey] += invest; unreal[trackKey] += 1; globalStats[type].spent += invest; }
                    else if (d.s === 'PASS') { runningChronologicalPL -= invest; if (runningChronologicalPL < maxDip) maxDip = runningChronologicalPL; const winAmount = (parseFloat(d.r) || 0) * marginMultiplier; runningChronologicalPL += winAmount; globalStats[type].spent += invest; globalStats[type].win += winAmount; debt[trackKey] = 0; unreal[trackKey] = 0; }
                    else if (d.s === 'SKIP') { unreal[trackKey] += 1; }
                    else if (d.s === 'WAIT') {
                        // Auto-rate v6:
                        // 1) Digit edit: suggest on the same card.
                        // 2) Recovery: after PASS/FAIL/SKIP, refresh the next WAIT card in the
                        //    same track if it already has digits and its rate is blank/auto.
                        // Manual rates edited after digits remain protected.
                        const sameChangedCard = (IS_MASTER && fieldChanged === 'd' && changedType === type && changedIndexNum === i);
                        const downstreamRecoveryCard = (IS_MASTER && fieldChanged === 's' && changedType === type && changedTrackKey && trackKey === changedTrackKey && i > changedIndexNum && count > 0 && !recoverySuggestedByTrack[trackKey] && titanAutoRateCanRecalculate(d));
                        if ((sameChangedCard || downstreamRecoveryCard) && count > 0 && titanAutoRateCanRecalculate(d)) {
                            const margin = Number(marginMultiplier || 0) - Number(count || 0);
                            const autoRate = computeLedgerAutoRate(type, i, count, debt[trackKey], unreal[trackKey], marginMultiplier, targetProf);
                            if(autoRate > 0) {
                                const dn = type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData');
                                const cardKey = ledgerMarketKeyForCard(type, m || {});
                                const reason = downstreamRecoveryCard ? 'recovery_next_market' : 'digit_change';
                                if(!dataDict[i]) dataDict[i] = {s:'WAIT', d:'', r:''};
                                dataDict[i] = applyLedgerAutoRateToRecord(dataDict[i], autoRate, reason, {recovery: downstreamRecoveryCard, debt: debt[trackKey], unreal: unreal[trackKey], margin, targetProf, trackKey, fromIdx: changedIndexNum, baseRate: autoRate});
                                dataDict[i] = annotateLedgerRecord(dataDict[i], type, i, cardKey);
                                state.dayRecords[currentDate][dn][i] = dataDict[i];
                                updateLedgerScheduleStore(appState.activeId || 'admin1', type, i, dataDict[i], cardKey);
                                if(reason === 'recovery_next_market') syncAdminAutoRateToVipProfiles(type, i, cardKey, dataDict[i]);
                                titanRecordAutoRateUpdate(type, i, cardKey, dataDict[i], reason === 'recovery_next_market' ? 'recovery_auto_rate' : 'auto_rate_suggest');
                                if(downstreamRecoveryCard) recoverySuggestedByTrack[trackKey] = true;
                                const rIn = document.getElementById(`in-r-${type}-${i}`);
                                if(rIn) rIn.value = String(autoRate);
                            }
                        }
                    }
                });
                globalStats[type].pl = globalStats[type].win - globalStats[type].spent;
                const masterCap = IS_MASTER ? (parseFloat(appState.profiles['admin1'].config[type].cap) || 0) : 0;
                globalStats[type].port = (parseFloat(state.config[type].cap) || masterCap) + globalStats[type].pl;
                globalStats[type].maxLoss = Math.abs(maxDip);
            };

            processGroup('ank', record.data, markets, 9.5, 'ank');
            processGroup('jodi', record.jodiData, baseMarkets, 95.0, 'jodi');
            processGroup('pannel', record.pannelData, markets, 150.0, 'pan');

            checkTargetsAndLimits();
            return titanLastAutoRateUpdates;
        }

        // v34: stable individual colors for every ledger card.
        // This is deterministic, not saved data: the same type + market key always
        // gets the same color, and any future market automatically gets its own shade.
        function titanLedgerColorHash(input) {
            const str = String(input || 'ledger-card');
            let h = 2166136261;
            for (let i = 0; i < str.length; i++) {
                h ^= str.charCodeAt(i);
                h = Math.imul(h, 16777619);
            }
            return h >>> 0;
        }
        function titanLedgerCardTheme(type, idx, market, marketKey) {
            const name = (market && (market.n || market.name || market.marketName)) || '';
            const key = marketKey || (market && (market.marketKey || market.key)) || name || idx;
            const seed = `${type}|${key}|${idx}`;
            const hash = titanLedgerColorHash(seed);
            const hue = hash % 360;
            const hue2 = (hue + 36 + (hash % 64)) % 360;
            const hue3 = (hue + 210 + (hash % 42)) % 360;
            const sat = 66 + (hash % 18);
            const lit = 53 + (hash % 9);
            return {
                seed,
                accent: `hsl(${hue} ${sat}% ${lit}%)`,
                accent2: `hsl(${hue2} ${Math.min(88, sat + 8)}% ${Math.min(68, lit + 8)}%)`,
                fullA: `hsla(${hue}, ${Math.min(86, sat + 8)}%, 31%, 0.98)`,
                fullB: `hsla(${hue2}, ${Math.min(90, sat + 10)}%, 25%, 0.98)`,
                fullC: `hsla(${hue3}, ${Math.min(76, sat + 3)}%, 18%, 0.99)`,
                line: `hsla(${hue}, ${sat}%, ${Math.min(74, lit + 10)}%, 0.86)`,
                glow: `hsla(${hue}, ${sat}%, ${lit}%, 0.28)`,
                glass: `hsla(${hue}, ${sat}%, 10%, 0.24)`,
            };
        }
        function applyTitanLedgerCardTheme(card, type, idx, market, marketKey, rec) {
            if (!card) return;
            const theme = titanLedgerCardTheme(type, idx, market, marketKey);
            card.classList.add('ledger-unique-color-card', 'ledger-full-color-card');
            card.dataset.ledgerColorSeed = theme.seed;
            card.style.setProperty('--ledger-card-accent', theme.accent);
            card.style.setProperty('--ledger-card-accent-2', theme.accent2);
            card.style.setProperty('--ledger-card-line', theme.line);
            card.style.setProperty('--ledger-card-glow', theme.glow);
            card.style.background = `linear-gradient(135deg, ${theme.fullA} 0%, ${theme.fullB} 56%, ${theme.fullC} 100%)`;
            card.style.borderColor = 'rgba(255,255,255,0.20)';
            card.style.boxShadow = `inset 0 0 0 1px rgba(255,255,255,0.08), inset 5px 0 0 ${theme.line}, 0 14px 34px ${theme.glow}`;
            card.style.color = '#fff';
            card.querySelectorAll('.native-input').forEach(el => {
                el.style.background = 'rgba(0,0,0,0.30)';
                el.style.borderColor = 'rgba(255,255,255,0.24)';
                el.style.color = '#fff';
                el.style.boxShadow = 'inset 0 1px 0 rgba(255,255,255,0.08)';
            });
            card.querySelectorAll('[class*="bg-[var(--surface-light)]"]').forEach(el => {
                el.style.background = 'rgba(0,0,0,0.22)';
                el.style.borderColor = 'rgba(255,255,255,0.20)';
                el.style.backdropFilter = 'blur(8px)';
            });
            card.querySelectorAll('label').forEach(el => {
                el.style.background = 'rgba(0,0,0,0.34)';
                el.style.color = 'rgba(255,255,255,0.82)';
                el.style.borderRadius = '8px';
            });
            card.querySelectorAll('.border-b').forEach(el => { el.style.borderColor = 'rgba(255,255,255,0.18)'; });
            card.querySelectorAll('button').forEach(el => {
                if (String(el.className || '').includes('bg-[var(--surface-light)]') || String(el.className || '').includes('rgba(42,171,238')) {
                    el.style.background = 'rgba(0,0,0,0.24)';
                    el.style.borderColor = 'rgba(255,255,255,0.18)';
                    el.style.color = '#fff';
                }
            });
        }

        const titanLedgerMoreOpenState = {};
        function titanLedgerMoreStateKey(type, cardKey){ return [currentDate || '', appState.activeId || 'admin1', type || '', cardKey || ''].join('|'); }
        function titanLedgerMoreIsOpen(type, cardKey){ return titanLedgerMoreOpenState[titanLedgerMoreStateKey(type, cardKey)] === true; }
        function titanRememberLedgerMore(ev, type, cardKey){
            try {
                if(ev) ev.stopPropagation();
                const el = ev && ev.currentTarget;
                titanLedgerMoreOpenState[titanLedgerMoreStateKey(type, cardKey)] = !!(el && el.open);
            } catch(e) {}
        }

        function titanLedgerBaseStatusMeta(status){
            status = String(status || 'WAIT').toUpperCase();
            if(status === 'PASS') return {bg:'border-l-4 border-l-[var(--green)]', lbl:'text-[var(--green)]', icon:'fa-check-circle', txt:'PASS'};
            if(status === 'FAIL') return {bg:'border-l-4 border-l-[var(--rose)]', lbl:'text-[var(--rose)]', icon:'fa-times-circle', txt:'FAIL'};
            if(status === 'SKIP') return {bg:'border-l-4 border-l-[var(--text-muted)]', lbl:'text-[var(--text-muted)]', icon:'fa-minus-circle', txt:'SKIP'};
            return {bg:'', lbl:'text-[var(--text-muted)]', icon:'fa-clock', txt:'WAITING'};
        }

        function titanLedgerBaseScheduleCompact(type, idx, cardKeyJS, d){
            if(!IS_MASTER) return '';
            return `
                <div class="mb-3 border border-[rgba(0,194,111,0.18)] bg-[rgba(0,194,111,0.06)] rounded-xl p-3">
                    <div class="flex items-center justify-between gap-2 mb-2">
                        <div class="text-[9px] font-black uppercase tracking-widest text-[var(--green)]"><i class="fas fa-clock mr-1"></i> Daily Schedule</div>
                        <div class="text-[8px] text-[var(--text-muted)] truncate max-w-[55%]">${titanTargetsText(d)}</div>
                    </div>
                    <div class="grid grid-cols-3 gap-2">
                        <input type="time" value="${d.schTime || ''}" onfocus="titanMarkInteractiveInputHold('schedule_time_focus', 8000)" oninput="titanMarkInteractiveInputHold('schedule_time_input', 8000)" onchange="titanMarkInteractiveInputHold('schedule_time_change', 8000); setScheduleTime('${type}', ${idx}, this.value, ${cardKeyJS})" class="native-input text-[13px] py-2.5 text-[var(--green)]">
                        <button onclick="openLedgerTargetPicker('${type}', ${idx}, ${cardKeyJS})" class="bg-[rgba(42,171,238,0.12)] border border-[rgba(42,171,238,0.25)] text-[var(--primary)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fab fa-whatsapp mr-1"></i> Targets</button>
                        <button onclick="clearCardTargets('${type}', ${idx}, ${cardKeyJS})" class="bg-[rgba(255,93,93,0.08)] border border-[rgba(255,93,93,0.18)] text-[var(--rose)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95"><i class="fas fa-trash mr-1"></i> Clear</button>
                    </div>
                </div>`;
        }

        function titanLedgerBaseInputBlock(type, i, m, d, trackColor, trickBadge, memoryBadge, cardKeyJS){
            const scrapeButtons = IS_MASTER ? `
                <button id="scrape-btn-${type}-${i}" onclick="scrapeMarket('${type}', ${i}, ${jsArg(m.n)}, ${cardKeyJS})" class="flex items-center gap-1 text-[var(--primary)] bg-[rgba(42,171,238,0.1)] border border-[rgba(42,171,238,0.2)] px-2.5 py-1 rounded-lg active:scale-95 text-[9px] font-bold uppercase"><i class="fas fa-satellite-dish"></i> Scrape</button>
                <button onclick="fetchCombinedScrape(this, '${type}', ${i}, ${cardKeyJS})" class="bg-[#00C26F] text-white px-3 py-1 rounded-lg text-[10px] font-bold uppercase active:scale-95">Combo</button>
                <button onclick="resetCard('${type}', ${i}, ${cardKeyJS})" class="text-[var(--text-muted)] hover:text-[var(--rose)] active:scale-95 ml-1"><i class="fas fa-eraser"></i></button>` : '';
            const moreKey = ledgerMarketKeyForCard(type, m);
            const moreOpen = titanLedgerMoreIsOpen(type, moreKey);
            return `
                <div class="ledger-card-head flex justify-between items-center border-b border-[var(--border)]">
                    <div class="flex items-center min-w-0">
                        <span class="text-[11px] font-black uppercase ${trackColor} truncate">${m.n}</span> ${trickBadge} ${memoryBadge}
                    </div>
                    <div class="flex items-center gap-1.5 shrink-0">${scrapeButtons}</div>
                </div>
                <div class="ledger-card-body">
                    <div class="ledger-main-grid">
                        <div class="relative flex flex-col">
                            <label class="absolute -top-2 left-3 z-10 bg-[var(--surface)] px-1 text-[8px] font-bold text-[var(--text-muted)] uppercase">Digits</label>
                            <input id="in-d-${type}-${i}" onfocus="titanMarkLedgerDirty()" oninput="updateMarket('${type}', ${i}, 'd', this.value, ${cardKeyJS})" value="${d.d || ''}" placeholder="${type === 'jodi' ? 'Jodi' : 'Values'}" class="native-input text-[var(--amber)]">
                            ${type !== 'jodi' ? `
                            <div class="flex gap-1 mt-2 justify-center">
                                <button onclick="applyTrick('${type}', ${i}, 1, ${cardKeyJS})" class="flex-1 text-[9px] bg-[rgba(123,143,255,0.1)] border border-[rgba(123,143,255,0.2)] text-[var(--purple)] py-1.5 rounded font-black active:scale-90 shadow-sm">T1</button>
                                <button onclick="applyTrick('${type}', ${i}, 2, ${cardKeyJS})" class="flex-1 text-[9px] bg-[rgba(250,199,72,0.1)] border border-[rgba(250,199,72,0.2)] text-[var(--amber)] py-1.5 rounded font-black active:scale-90 shadow-sm">T2</button>
                                <button onclick="applyTrick('${type}', ${i}, 3, ${cardKeyJS})" class="flex-1 text-[9px] bg-[rgba(0,194,111,0.1)] border border-[rgba(0,194,111,0.2)] text-[var(--green)] py-1.5 rounded font-black active:scale-90 shadow-sm">T3</button>
                                <button onclick="applyTrick('${type}', ${i}, 4, ${cardKeyJS})" class="flex-1 text-[9px] bg-[rgba(42,171,238,0.1)] border border-[rgba(42,171,238,0.2)] text-[var(--primary)] py-1.5 rounded font-black active:scale-90 shadow-sm">T4</button>
                                ${d.trick ? `<button onclick="undoTrick('${type}', ${i}, ${cardKeyJS})" class="flex-none px-2.5 text-[10px] bg-[rgba(255,93,93,0.1)] border border-[rgba(255,93,93,0.2)] text-[var(--rose)] py-1.5 rounded font-black active:scale-90 shadow-sm"><i class="fas fa-undo"></i></button>` : ''}
                            </div>
                            ${getTrickHistoryHTML(type, i)}
                            ` : ''}
                        </div>
                        <div class="relative">
                            <label class="absolute -top-2 left-3 bg-[var(--surface)] px-1 text-[8px] font-bold text-[var(--text-muted)] uppercase">Invest ₹</label>
                            <input id="in-r-${type}-${i}" type="number" onfocus="titanMarkLedgerDirty()" oninput="updateMarket('${type}', ${i}, 'r', this.value, ${cardKeyJS})" value="${d.r || ''}" placeholder="Amount" class="native-input text-white">
                        </div>
                    </div>
                    <div class="ledger-actions">
                        <button onclick="act('${type}', ${i}, 'PASS', ${cardKeyJS})" class="bg-[var(--green)] text-white font-black text-[10px] uppercase active:scale-95">PASS</button>
                        <button onclick="act('${type}', ${i}, 'FAIL', ${cardKeyJS})" class="bg-[var(--rose)] text-white font-black text-[10px] uppercase active:scale-95">FAIL</button>
                        <button onclick="act('${type}', ${i}, 'SKIP', ${cardKeyJS})" class="bg-[var(--surface-light)] text-[var(--text-muted)] font-bold text-[10px] uppercase active:scale-95 border border-[var(--border)]"><i class="fas fa-forward"></i></button>
                    </div>
                    <details class="ledger-more" ${moreOpen ? 'open' : ''} ontoggle="titanRememberLedgerMore(event, '${type}', ${cardKeyJS})" onclick="event.stopPropagation()">
                        <summary onclick="event.stopPropagation()"><span><i class="fas fa-sliders-h mr-1"></i> Schedule / Share</span></summary>
                        <div class="ledger-more-body">
                            ${titanLedgerBaseScheduleCompact(type, i, cardKeyJS, d)}
                            <div class="grid grid-cols-3 gap-2">
                                <button onclick="copyIntel('${type}', ${i}, this, ${cardKeyJS})" class="text-[var(--primary)] bg-[rgba(42,171,238,0.1)] py-2.5 rounded-lg font-bold text-[9px] uppercase active:scale-95 flex justify-center items-center gap-1 border border-[rgba(42,171,238,0.15)]"><i class="fas fa-copy"></i> Copy</button>
                                <button onclick="prepShare('${type}', ${i}, 'GUIDE', ${cardKeyJS})" class="text-[var(--amber)] bg-[rgba(250,199,72,0.1)] py-2.5 rounded-lg font-bold text-[9px] uppercase active:scale-95 flex justify-center items-center gap-1 border border-[rgba(250,199,72,0.15)]"><i class="fas fa-lightbulb"></i> Intel</button>
                                <button onclick="prepShare('${type}', ${i}, 'STATUS', ${cardKeyJS})" class="text-[var(--green)] bg-[rgba(0,194,111,0.1)] py-2.5 rounded-lg font-bold text-[9px] uppercase active:scale-95 flex justify-center items-center gap-1 border border-[rgba(0,194,111,0.15)]"><i class="fas fa-paper-plane"></i> Result</button>
                            </div>
                        </div>
                    </details>
                </div>`;
        }

        // v39: uploaded flask_app.py ka compact Ledger UI base + v38 atomic Firebase/realtime lock.
        function createLedgerList(type, arr, dictName) {
            ensureDataStruct();
            const list = document.createElement('div');
            list.className = 'ledger-compact px-2 pb-3 pt-1';
            let dayRec = state.dayRecords[currentDate];
            if(!dayRec) {
                ensureDataStruct();
                dayRec = state.dayRecords[currentDate] || {data:{}, jodiData:{}, pannelData:{}, visAnk:{}, visJodi:{}, visPan:{}};
            }
            const visDict = type === 'ank' ? dayRec.visAnk : (type === 'jodi' ? dayRec.visJodi : dayRec.visPan);

            (arr || []).forEach((m, i) => {
                if(!m || m.hiddenForLedger) return;
                if(visDict && visDict[m.n] === false) return;
                const isOpen = String(m.n || '').includes('OPEN');
                const isJodi = type === 'jodi';
                const trackColor = isJodi ? 'text-[#B85CFF]' : (isOpen ? 'text-[var(--primary)]' : 'text-[var(--amber)]');
                const boostPercent = Math.round((getHistoricalMultiplier(type, i, currentDate) - 1) * 100);
                const memoryBadge = boostPercent > 0 ? `<span class="text-[8px] bg-[var(--rose)] text-white px-1.5 py-0.5 rounded font-bold uppercase ml-2">+${boostPercent}%</span>` : '';
                const cardKey = ledgerMarketKeyForCard(type, m);
                const cardKeyJS = jsArg(cardKey);
                // Rendering must be read-mostly. Creating blank records for every
                // visible card during render made old/duplicate records reappear in
                // Firebase after a later full save. Only real user actions create records.
                const op = ensureLedgerRecordBoundForProfile(state, appState.activeId || 'admin1', type, i, cardKey, false);
                const d = op.rec || {s:'WAIT', d:'', r:''};
                const status = titanLedgerBaseStatusMeta(d.s);
                const trickBadge = d.trick ? `<span class="text-[8px] bg-[var(--purple)] text-white px-1.5 py-0.5 rounded font-black uppercase ml-2">${d.trick}</span>` : '';
                const card = document.createElement('div');

                if(!IS_MASTER) {
                    const canEdit = vipCanEdit();
                    if(canEdit && d.s === 'WAIT') {
                        card.className = 'native-card';
                        card.innerHTML = titanLedgerBaseInputBlock(type, i, m, d, trackColor, trickBadge, memoryBadge, cardKeyJS);
                    } else {
                        card.className = `native-card ${status.bg}`;
                        card.innerHTML = `
                            <div class="flex justify-between items-center px-4 py-2.5 border-b border-[var(--border)]">
                                <span class="text-[12px] font-bold uppercase ${d.s === 'WAIT' ? trackColor : 'text-white'}">${m.n}</span> ${trickBadge}
                                <span class="text-[10px] font-bold ${status.lbl} flex items-center gap-1"><i class="fas ${status.icon}"></i> ${status.txt}</span>
                            </div>
                            <div class="p-4 grid grid-cols-2 gap-3 mb-2">
                                <div class="bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                                    <p class="stat-lbl mb-1">Target Digits</p>
                                    <p class="text-[15px] font-black text-white">${d.d || '---'}</p>
                                </div>
                                <div class="bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                                    <p class="stat-lbl mb-1">Amount / Pt</p>
                                    <p class="text-[15px] font-black text-white">₹${d.r || 0}</p>
                                </div>
                            </div>
                            <button onclick="copyIntel('${type}', ${i}, this, ${cardKeyJS})" class="w-full bg-[rgba(42,171,238,0.1)] text-[var(--primary)] py-2.5 rounded-xl font-bold text-[11px] uppercase active:scale-95 flex justify-center items-center gap-2 border border-[rgba(42,171,238,0.2)] mx-4 mb-3" style="width:calc(100% - 2rem)"><i class="fas fa-copy"></i> Copy Card Data</button>`;
                    }
                } else if(d.s !== 'WAIT') {
                    card.className = `native-card ${status.bg}`;
                    card.innerHTML = `
                        <div class="flex justify-between items-center px-4 py-2.5 border-b border-[var(--border)]">
                            <span class="text-[12px] font-bold uppercase text-white">${m.n}</span> ${trickBadge}
                            <span class="text-[10px] font-bold ${status.lbl} flex items-center gap-1"><i class="fas ${status.icon}"></i> ${d.s}</span>
                        </div>
                        <div class="p-4 grid grid-cols-2 gap-3">
                            <div class="bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]"><p class="stat-lbl mb-1">Target Digits</p><p class="text-[15px] font-black text-white">${d.d || '-'}</p></div>
                            <div class="bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]"><p class="stat-lbl mb-1">Amount / Pt</p><p class="text-[15px] font-black text-white">₹${d.r || 0}</p></div>
                        </div>
                        ${titanLedgerBaseScheduleCompact(type, i, cardKeyJS, d)}
                        <button onclick="cardUndo('${type}', ${i}, ${cardKeyJS})" class="w-full bg-[var(--surface-light)] text-[var(--text-muted)] py-3 font-bold text-[10px] uppercase flex items-center justify-center gap-2 active:opacity-70 border-t border-[var(--border)]"><i class="fas fa-undo"></i> Unlock Round</button>`;
                } else {
                    card.className = 'native-card';
                    card.innerHTML = titanLedgerBaseInputBlock(type, i, m, d, trackColor, trickBadge, memoryBadge, cardKeyJS);
                }
                applyTitanLedgerCardTheme(card, type, i, m, cardKey, d);
                list.appendChild(card);
            });

            const actionRow = document.createElement('div');
            actionRow.className = 'flex gap-3 mt-2';
            if(IS_MASTER) {
                actionRow.innerHTML = `
                    <button onclick="prepDailyReportShare('${type}')" class="flex-1 bg-[var(--primary)] text-white py-4 rounded-2xl font-black text-[11px] uppercase tracking-wide active:scale-95 shadow-lg shadow-[rgba(42,171,238,0.2)]"><i class="fas fa-share-alt mr-1"></i> Day Report</button>
                    <button id="ledger-sync-btn" onclick="saveMaster(false)" class="flex-1 bg-[var(--surface-light)] border border-[var(--border)] text-white py-4 rounded-2xl font-black text-[11px] uppercase tracking-wide active:scale-95"><i class="fas fa-cloud-upload-alt mr-1"></i> Sync</button>`;
            } else {
                actionRow.innerHTML = `
                    <div class="w-full flex items-center justify-center gap-2 bg-[rgba(0,194,111,0.08)] text-[var(--green)] border border-[rgba(0,194,111,0.2)] py-4 rounded-2xl font-bold text-[11px] uppercase tracking-wide">
                        <i class="fas fa-satellite-dish animate-pulse"></i> LIVE SYNC ACTIVE
                    </div>`;
            }
            list.appendChild(actionRow);
            return list;
        }

        function act(type, i, s, marketKey=null) {
            if(!IS_MASTER) return;
            ensureDataStruct();
            const op = resolveLedgerAction(type, i, marketKey);
            if(op.idx < 0) return showRealNotification('⚠️ Ledger Error', 'Card mapping nahi mila. Refresh karke try karo.', 'danger');
            op.rec.s = s;
            op.rec = stampLedgerMutation(op.rec, 'manual_status', {manualStatus:true});
            op.rec = annotateLedgerRecord(op.rec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = op.rec;
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, op.rec, 'manual_status');
            // 🔧 BUG FIX #1: Add missing schedule sync after status change
            updateLedgerScheduleStore(appState.activeId, type, op.idx, op.rec, op.key);

            if(appState.activeId === 'admin1') {
                Object.keys(appState.profiles).forEach(pid => {
                    if(pid === 'admin1') return;
                    let pState = appState.profiles[pid];
                    const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                    vipOp.rec.s = s;
                    vipOp.rec = stampLedgerMutation(vipOp.rec, 'manual_status', {manualStatus:true});
                    vipOp.rec = annotateLedgerRecord(vipOp.rec, type, vipOp.idx, vipOp.key);
                    pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = vipOp.rec;
                    // 🔧 BUG FIX #3: Add missing schedule sync for VIP profile
                    recordLedgerLocalPatch(pid, type, vipOp.idx, vipOp.key, vipOp.rec, 'manual_status');
                    updateLedgerScheduleStore(pid, type, vipOp.idx, vipOp.rec, vipOp.key);
                });
            }

            titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'manual_status', appState.activeId === 'admin1');
            // v6: status changes can change the recovery debt. Recalculate and persist the
            // next WAIT card's auto-rate in the same track when digits already exist.
            const recoveryUpdates = runLiveSync(type, op.idx, 's') || [];
            titanCommitLedgerAutoRateUpdates(recoveryUpdates, 'recovery_auto_rate');
            render(true);
        }

        function updateMarket(type, idx, field, value, marketKey=null, sourceAction=null) {
            if(!IS_MASTER) return;
            ensureDataStruct();
            const op = resolveLedgerAction(type, idx, marketKey);
            if(op.idx < 0) return showRealNotification('⚠️ Ledger Error', 'Card mapping nahi mila. Refresh karke try karo.', 'danger');
            op.rec[field] = value;
            const changeAt = Date.now();
            if(field === 'r') {
                const hasRate = String(value || '').trim() !== '';
                op.rec._manualR = hasRate;
                op.rec._autoR = false;
                if(hasRate) op.rec._manualRateAt = changeAt;
                else { delete op.rec._manualRateAt; delete op.rec._autoRateAt; delete op.rec._autoRateReason; }
            }
            if(field === 'd') { op.rec._digitsTouchedAt = changeAt; }
            const cleared = String(value || '').trim() === '';
            const actionName = sourceAction || (field === 'd' ? 'manual_input' : 'manual_rate');
            op.rec = stampLedgerMutation(op.rec, actionName, {clearDigit: field === 'd' && cleared, clearRate: field === 'r' && cleared});
            if(field === 'd' && !cleared){
                delete op.rec._digitClearedAt;
                delete op.rec._explicitClearedAt;
                op.rec = titanNormalizeOriginalDigits(op.rec, type, value, actionName);
            }
            if(field === 'r' && !cleared){ delete op.rec._rateClearedAt; }
            op.rec = annotateLedgerRecord(op.rec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = op.rec;
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, op.rec, actionName);
            updateLedgerScheduleStore(appState.activeId, type, op.idx, op.rec, op.key);

            if(appState.activeId === 'admin1') {
                Object.keys(appState.profiles).forEach(pid => {
                    if(pid === 'admin1') return;
                    let pState = appState.profiles[pid];
                    const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                    vipOp.rec[field] = value;
                    if(field === 'r') {
                        const hasRate = String(value || '').trim() !== '';
                        vipOp.rec._manualR = hasRate;
                        vipOp.rec._autoR = false;
                        if(hasRate) vipOp.rec._manualRateAt = changeAt;
                        else { delete vipOp.rec._manualRateAt; delete vipOp.rec._autoRateAt; delete vipOp.rec._autoRateReason; }
                    }
                    if(field === 'd') { vipOp.rec._digitsTouchedAt = changeAt; }
                    const vipCleared = String(value || '').trim() === '';
                    vipOp.rec = stampLedgerMutation(vipOp.rec, actionName, {clearDigit: field === 'd' && vipCleared, clearRate: field === 'r' && vipCleared});
                    if(field === 'd' && !vipCleared){
                        delete vipOp.rec._digitClearedAt;
                        delete vipOp.rec._explicitClearedAt;
                        vipOp.rec = titanNormalizeOriginalDigits(vipOp.rec, type, value, actionName);
                    }
                    if(field === 'r' && !vipCleared){ delete vipOp.rec._rateClearedAt; }
                    vipOp.rec = annotateLedgerRecord(vipOp.rec, type, vipOp.idx, vipOp.key);
                    pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = vipOp.rec;
                    // ✅ FIX: Record patch for VIP profile too for sync consistency
                    recordLedgerLocalPatch(pid, type, vipOp.idx, vipOp.key, vipOp.rec, actionName);
                    updateLedgerScheduleStore(pid, type, vipOp.idx, vipOp.rec, vipOp.key);
                });
            }

            runLiveSync(type, op.idx, field);
            // LEDGER_RATE_STATE_FIX_v3: after runLiveSync may calculate auto-rate, persist the
            // final card record back into the pending local patch. This prevents the next card's
            // edit/save from replaying an older digit-only patch that clears the previous rate.
            let finalRec = state.dayRecords[currentDate][op.dictName][op.idx] || op.rec;
            finalRec = annotateLedgerRecord(finalRec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = finalRec;
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, finalRec, field === 'd' ? 'digit_with_auto_rate' : actionName);
            updateLedgerScheduleStore(appState.activeId, type, op.idx, finalRec, op.key);
            if(field === 'd') {
                const masterRec = state.dayRecords[currentDate][op.dictName][op.idx];
                updateLedgerScheduleStore(appState.activeId, type, op.idx, masterRec, op.key);
                // If admin pushed digits to VIP ledgers, also push Titan's newly suggested rate
                // so their scheduled Intel message does not fall back to the ₹10 default.
                syncAdminAutoRateToVipProfiles(type, op.idx, op.key, masterRec);
            }
            const firebaseRec = state.dayRecords[currentDate][op.dictName][op.idx];
            titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, firebaseRec, field === 'd' ? 'digit_with_auto_rate' : actionName, appState.activeId === 'admin1');
            // v5: no full-state autoSave after ledger card edit; Firebase child-path commit is source of truth.
        }

        function resetCard(type, i, marketKey=null) {
            if(!IS_MASTER) return;
            const op = resolveLedgerAction(type, i, marketKey);
            if(op.idx < 0) return;
            const oldRec = op.rec || {};
            let resetRec = { s: 'WAIT', d: '', r: '', schTime: oldRec.schTime || '', schTargets: Array.isArray(oldRec.schTargets) ? oldRec.schTargets.slice() : [] };
            resetRec = stampLedgerMutation(resetRec, 'reset_card', {reset:true, manualStatus:true});
            state.dayRecords[currentDate][op.dictName][op.idx] = annotateLedgerRecord(resetRec, type, op.idx, op.key);
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'reset_card');
            updateLedgerScheduleStore(appState.activeId, type, op.idx, state.dayRecords[currentDate][op.dictName][op.idx], op.key);
            if(appState.activeId === 'admin1') {
                Object.keys(appState.profiles).forEach(pid => {
                    if(pid === 'admin1') return;
                    let pState = appState.profiles[pid];
                    const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                    const oldVipRec = vipOp.rec || {};
                    let vipResetRec = { s: 'WAIT', d: '', r: '', schTime: oldVipRec.schTime || '', schTargets: Array.isArray(oldVipRec.schTargets) ? oldVipRec.schTargets.slice() : [] };
                    vipResetRec = stampLedgerMutation(vipResetRec, 'reset_card', {reset:true, manualStatus:true});
                    pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = annotateLedgerRecord(vipResetRec, type, vipOp.idx, vipOp.key);
                    updateLedgerScheduleStore(pid, type, vipOp.idx, pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx], vipOp.key);
                });
            }
            titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'reset_card', appState.activeId === 'admin1');
            render(true);
        }

        function cardUndo(type, i, marketKey=null) {
            if(!IS_MASTER) return;
            const op = resolveLedgerAction(type, i, marketKey);
            if(op.idx < 0) return;
            op.rec.s = 'WAIT';
            op.rec = stampLedgerMutation(op.rec, 'card_unlock', {manualStatus:true});
            op.rec = annotateLedgerRecord(op.rec, type, op.idx, op.key);
            state.dayRecords[currentDate][op.dictName][op.idx] = op.rec;
            recordLedgerLocalPatch(appState.activeId, type, op.idx, op.key, op.rec, 'card_unlock');
            if(appState.activeId === 'admin1') {
                Object.keys(appState.profiles).forEach(pid => {
                    if(pid === 'admin1') return;
                    let pState = appState.profiles[pid];
                    const vipOp = ensureLedgerRecordBoundForProfile(pState, pid, type, op.idx, op.key, true);
                    vipOp.rec.s = 'WAIT';
                    vipOp.rec = stampLedgerMutation(vipOp.rec, 'card_unlock', {manualStatus:true});
                    vipOp.rec = annotateLedgerRecord(vipOp.rec, type, vipOp.idx, vipOp.key);
                    pState.dayRecords[currentDate][vipOp.dictName][vipOp.idx] = vipOp.rec;
                });
            }
            titanCommitLedgerRecordToFirebase(appState.activeId, type, op.idx, op.key, state.dayRecords[currentDate][op.dictName][op.idx], 'card_unlock', appState.activeId === 'admin1');
            render(true);
        }

        function getWeekStats(currDateStr) { let parts = currDateStr.split('-'); let d = new Date(parts[0], parts[1]-1, parts[2]); let day = d.getDay(); let diff = d.getDate() - day + (day === 0 ? -6 : 1); let monday = new Date(d); monday.setDate(diff); let stats = { ank: {}, jodi: {}, pannel: {} }; baseMarkets.forEach(bm => { stats.ank[bm.n] = { rounds: 0, pass: 0, fail: 0, invest: 0, win: 0 }; stats.jodi[bm.n] = { rounds: 0, pass: 0, fail: 0, invest: 0, win: 0 }; stats.pannel[bm.n] = { rounds: 0, pass: 0, fail: 0, invest: 0, win: 0 }; }); let totals = { ank: { invest: 0, win: 0, runningPL: 0, maxLoss: 0 }, jodi: { invest: 0, win: 0, runningPL: 0, maxLoss: 0 }, pannel: { invest: 0, win: 0, runningPL: 0, maxLoss: 0 } }; for(let i=0; i<7; i++) { let loopDate = new Date(monday); loopDate.setDate(monday.getDate() + i); let yyyy = loopDate.getFullYear(); let mm = String(loopDate.getMonth() + 1).padStart(2, '0'); let dd = String(loopDate.getDate()).padStart(2, '0'); let dateStr = `${yyyy}-${mm}-${dd}`; let record = state.dayRecords[dateStr]; if(!record) continue; const processItem = (type, dataDict, arr, marginMultiplier) => { if(!dataDict) return; arr.forEach((m, idx) => { let bmName = getBaseNameForMarket(m.n); if(!bmName || !stats[type][bmName]) return; const dObj = dataDict[idx]; if(!dObj || dObj.s === 'WAIT' || dObj.s === 'SKIP') return; const r = parseFloat(dObj.r) || 0; let count = (dObj.d ? String(dObj.d) : '').split(/[, ]+/).filter(x => x.trim()).length; let invest = count * r; if(dObj.s === 'FAIL') { totals[type].runningPL -= invest; if(totals[type].runningPL < totals[type].maxLoss) totals[type].maxLoss = totals[type].runningPL; } else if(dObj.s === 'PASS') { totals[type].runningPL -= invest; if(totals[type].runningPL < totals[type].maxLoss) totals[type].maxLoss = totals[type].runningPL; totals[type].runningPL += (r * marginMultiplier); } stats[type][bmName].rounds++; stats[type][bmName].invest += invest; totals[type].invest += invest; if(dObj.s === 'PASS') { stats[type][bmName].pass++; stats[type][bmName].win += (r * marginMultiplier); totals[type].win += (r * marginMultiplier); } else if(dObj.s === 'FAIL') { stats[type][bmName].fail++; } }); }; processItem('ank', record.data, markets, 9.5); processItem('jodi', record.jodiData, baseMarkets, 95.0); processItem('pannel', record.pannelData, markets, 150.0); } return { monday, stats, totals }; }

        function renderWeeklyReport() {
            ensureDataStruct();
            let { monday, stats, totals } = getWeekStats(currentDate); let sunday = new Date(monday); sunday.setDate(sunday.getDate() + 6); let dateStr = `${monday.toLocaleDateString('en-GB', {day:'2-digit', month:'short'})} - ${sunday.toLocaleDateString('en-GB', {day:'2-digit', month:'short'})}`;
            let typeStats = stats[weeklyTabType]; let tInvest = totals[weeklyTabType].invest; let tWin = totals[weeklyTabType].win; let net = tWin - tInvest;

            let html = `
                ${renderSubTabs()}
                <div class="px-3 pb-4 pt-2">
                    <div class="native-card p-4 mb-3 text-center" style="border-color:rgba(123,143,255,0.25); background:rgba(123,143,255,0.06)">
                        <h3 class="text-[11px] font-bold text-[var(--purple)] uppercase tracking-widest mb-1">Weekly Audit Report</h3>
                        <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest font-bold mb-4">${dateStr}</p>
                        <div class="grid grid-cols-2 gap-3">
                            <div class="bg-[var(--surface-light)] border border-[var(--border)] p-3 rounded-xl">
                                <p class="stat-lbl mb-1">Total Invest</p>
                                <p class="text-[14px] font-black text-[var(--text-muted)]">₹${tInvest.toLocaleString()}</p>
                            </div>
                            <div class="bg-[var(--surface-light)] border ${net >= 0 ? 'border-[rgba(0,194,111,0.3)]' : 'border-[rgba(255,93,93,0.3)]'} p-3 rounded-xl">
                                <p class="stat-lbl mb-1">Weekly P/L</p>
                                <p class="text-[14px] font-black ${net >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${net >= 0 ? '+' : ''}₹${net.toLocaleString()}</p>
                            </div>
                        </div>
                    </div>
            `;

            for (let bmName in typeStats) {
                let s = typeStats[bmName];
                if(s.rounds > 0) {
                    let pl = s.win - s.invest;
                    html += `
                        <div class="native-card p-4 flex justify-between items-center border-l-4 ${pl >= 0 ? 'border-l-[var(--green)]' : 'border-l-[var(--rose)]'} mb-2">
                            <div>
                                <h4 class="text-[12px] font-bold uppercase text-white mb-1">${bmName}</h4>
                                <p class="text-[9px] text-[var(--text-muted)] font-medium">Invest: ₹${s.invest.toLocaleString()}</p>
                            </div>
                            <div class="text-right">
                                <p class="text-[12px] font-black ${pl >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'} mb-1">${pl >= 0 ? '+' : ''}₹${pl.toLocaleString()}</p>
                                <p class="text-[9px] text-[var(--text-muted)] font-medium"><span class="text-[var(--green)]">W:${s.pass}</span> <span class="text-[var(--rose)] ml-1">L:${s.fail}</span></p>
                            </div>
                        </div>`;
                }
            }

            if(IS_MASTER) {
                html += `<button onclick="shareWeeklyReport()" class="w-full bg-[var(--purple)] text-white py-4 rounded-2xl font-black text-[11px] uppercase tracking-wide mt-3 active:scale-95 shadow-lg shadow-[rgba(123,143,255,0.2)]"><i class="fas fa-paper-plane mr-1"></i> Send Weekly Report</button>`;
            }
            html += `</div>`;
            return html;
        }

        function renderSmartAI() {
            if(!IS_MASTER) return '';
            return `
            <div class="px-3 py-4">
                <div class="native-card p-5" style="border-color:rgba(42,171,238,0.25); background:rgba(42,171,238,0.04)">
                    <div class="flex items-center gap-3 mb-4">
                        <div class="w-10 h-10 rounded-xl bg-[rgba(42,171,238,0.15)] flex items-center justify-center text-[var(--primary)] text-lg"><i class="fas fa-brain"></i></div>
                        <div>
                            <h3 class="text-[14px] font-black text-white">Global AI Scanner</h3>
                            <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Extract & Paste into all VIPs</p>
                        </div>
                    </div>

                    <textarea id="smart-text-input" rows="7" class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-[var(--amber)] font-bold p-4 rounded-xl outline-none text-[13px] placeholder-[var(--text-muted)] transition-colors focus:border-[var(--primary)]" placeholder="Paste your raw text format here..."></textarea>

                    <div class="grid grid-cols-3 gap-3 mt-4">
                        <button onclick="processSmartPaste('ank')" class="bg-[rgba(42,171,238,0.1)] text-[var(--primary)] py-3 rounded-xl font-bold uppercase text-[10px] active:scale-95 border border-[rgba(42,171,238,0.2)]">Ank</button>
                        <button onclick="processSmartPaste('jodi')" class="bg-[rgba(184,92,255,0.1)] text-[#B85CFF] py-3 rounded-xl font-bold uppercase text-[10px] active:scale-95 border border-[rgba(184,92,255,0.2)]">Jodi</button>
                        <button onclick="processSmartPaste('pannel')" class="bg-[rgba(250,199,72,0.1)] text-[var(--amber)] py-3 rounded-xl font-bold uppercase text-[10px] active:scale-95 border border-[rgba(250,199,72,0.2)]">Pan</button>
                    </div>
                </div>
            </div>`;
        }

        function renderVipSettings() {
            if(IS_MASTER) return '';
            ensureDataStruct();
            const canEdit = vipCanEdit();
            const disAttr = !canEdit ? 'disabled' : '';
            const disClass = !canEdit ? 'opacity-50' : '';

            const capital   = parseFloat(state.config.capital)   || 0;
            const dayTarget = parseFloat(state.config.dayTarget)  || 0;
            const totalPL   = globalStats.ank.pl + globalStats.jodi.pl + globalStats.pannel.pl;
            const dayPct    = dayTarget > 0 ? Math.min(100, Math.max(0, Math.round((totalPL / dayTarget) * 100))) : 0;

            const protoRow = (type, label, colorClass) => `
                <div class="flex justify-between items-center bg-[var(--surface-light)] px-4 py-3 rounded-xl border border-[var(--border)]">
                    <div>
                        <p class="text-[9px] font-bold text-[var(--text-muted)] uppercase">${label}</p>
                        <p class="text-[10px] font-bold ${colorClass} mt-0.5">Target / Card</p>
                    </div>
                    <input type="number" inputmode="numeric" ${disAttr}
                        oninput="state.config.${type}.tgt=parseFloat(this.value)||0; runLiveSync(); autoSave();"
                        value="${state.config[type] ? (state.config[type].tgt || 0) : 0}"
                        class="w-24 bg-[var(--surface)] border border-[var(--border)] text-white rounded-xl px-3 py-2 text-[13px] font-black text-right outline-none focus:border-[var(--primary)] ${disClass}"
                        placeholder="₹">
                </div>`;

            return `
                <div class="px-3 py-4">
                    <p class="sec-header">Meri Financial Settings</p>

                    ${!canEdit ? `<div class="bg-[rgba(255,93,93,0.1)] border border-[rgba(255,93,93,0.2)] rounded-xl p-3 mb-4 text-center">
                        <p class="text-[var(--rose)] text-[10px] font-black uppercase"><i class="fas fa-lock"></i> Read-Only Mode</p>
                        <p class="text-[var(--text-muted)] text-[9px] mt-1">Sirf admin details edit kar sakte hain.</p>
                    </div>` : ''}

                    <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.25);background:rgba(0,194,111,0.04)">
                        <h3 class="text-[11px] font-bold text-[var(--green)] uppercase tracking-widest mb-3 flex items-center gap-2"><i class="fas fa-wallet"></i> Capital & Din Ka Target</h3>
                        <div class="grid grid-cols-2 gap-3 mb-3">
                            <div>
                                <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Apna Capital ₹</label>
                                <input type="number" inputmode="numeric" ${disAttr}
                                    oninput="state.config.capital=parseFloat(this.value)||0; autoSave();"
                                    value="${capital}"
                                    class="native-input text-sm py-3 text-[var(--green)] ${disClass}" placeholder="Aapka capital">
                            </div>
                            <div>
                                <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Din Ka Target ₹</label>
                                <input type="number" inputmode="numeric" ${disAttr}
                                    oninput="state.config.dayTarget=parseFloat(this.value)||0; render(true); autoSave();"
                                    value="${dayTarget}"
                                    class="native-input text-sm py-3 text-[var(--primary)] ${disClass}" placeholder="Daily profit goal">
                            </div>
                        </div>
                        ${dayTarget > 0 ? `
                        <div>
                            <div class="flex justify-between mb-1.5">
                                <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">Aaj Ka Progress</span>
                                <span class="text-[9px] font-bold ${totalPL >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${totalPL >= 0 ? '+' : ''}₹${totalPL.toLocaleString()} / ₹${dayTarget.toLocaleString()}</span>
                            </div>
                            <div class="h-2 bg-[var(--surface-light)] rounded-full overflow-hidden">
                                <div class="h-full rounded-full transition-all" style="width:${Math.max(0, dayPct)}%;background:${totalPL >= 0 ? 'var(--green)' : 'var(--rose)'}"></div>
                            </div>
                            <p class="text-[9px] text-right mt-1 font-bold ${totalPL >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${dayPct}% complete</p>
                        </div>` : ''}
                    </div>

                    <p class="sec-header">Har Card Ka Profit Target</p>
                    <div class="native-card p-4 mb-6 space-y-2">
                        ${protoRow('ank',    'ANK (x9.5)',   'text-[var(--primary)]')}
                        ${protoRow('jodi',   'JODI (x95)',   'text-[#B85CFF]')}
                        ${protoRow('pannel', 'PANNEL (x150)','text-[var(--amber)]')}
                    </div>

                    ${canEdit ? `<button onclick="autoSave(); showToast('Settings saved!', 'green')"
                        class="w-full bg-[var(--green)] text-white py-4 rounded-2xl font-black text-[12px] uppercase tracking-wide mb-8 active:scale-95 shadow-lg shadow-[rgba(0,194,111,0.2)]">
                        <i class="fas fa-save mr-2"></i> Save My Settings
                    </button>` : ''}
                </div>`;
        }

        function renderSettings() {
            if(!IS_MASTER) return '';
            ensureDataStruct();

            // ── ANK/PAN: one row per base market, OPEN + CLOSE toggle ──
            let mktsHtmlOpenClose = (title, colorClass, trackDict) => {
                let visibleBaseMarkets = baseMarkets.filter(bm => !(bm && bm.hiddenForLedger));
                let isAllChecked = visibleBaseMarkets.every(bm => {
                    const ok = bm.n + ' OPEN'; const ck = bm.n + ' CLOSE';
                    return state.dayRecords[currentDate][trackDict][ok] !== false &&
                           state.dayRecords[currentDate][trackDict][ck] !== false;
                });
                return `
                <div class="native-card p-4 mb-3">
                    <div class="flex justify-between items-center mb-3">
                        <h3 class="text-[11px] font-bold ${colorClass} uppercase tracking-widest flex items-center gap-2"><i class="fas fa-eye"></i> ${title}</h3>
                        <div class="flex items-center gap-2 bg-[var(--surface-light)] px-2 py-1.5 rounded-lg border border-[var(--border)]">
                            <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">ALL</span>
                            <label class="switch transform scale-[0.6] origin-right m-0">
                                <input type="checkbox" onchange="toggleAllMarketsOpenClose('${trackDict}', this.checked)" ${isAllChecked ? 'checked' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>
                    <div class="flex justify-end gap-5 mb-1.5 pr-1">
                        <span class="text-[8px] font-black text-[var(--primary)] uppercase tracking-wider">OPEN</span>
                        <span class="text-[8px] font-black text-[var(--amber)] uppercase tracking-wider">CLOSE</span>
                    </div>
                    <div class="space-y-1.5">
                        ${visibleBaseMarkets.map(bm => {
                            const ok = bm.n + ' OPEN'; const ck = bm.n + ' CLOSE';
                            const openOn  = state.dayRecords[currentDate][trackDict][ok]  !== false;
                            const closeOn = state.dayRecords[currentDate][trackDict][ck] !== false;
                            return `
                            <div class="flex items-center gap-2 bg-[var(--surface-light)] px-3 py-2 rounded-xl border border-[var(--border)]">
                                <span class="flex-1 text-[9px] font-bold text-[var(--text-muted)] uppercase truncate">${bm.n}</span>
                                <label class="switch transform scale-[0.55] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('${trackDict}', '${ok}', this.checked)" ${openOn ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                                <label class="switch transform scale-[0.55] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('${trackDict}', '${ck}', this.checked)" ${closeOn ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                            </div>`;
                        }).join('')}
                    </div>
                </div>`;
            };

            // ── JODI: single toggle per base market ──
            let mktsHtmlJodi = () => {
                let visibleBaseMarkets = baseMarkets.filter(m => !(m && m.hiddenForLedger));
                let isAllChecked = visibleBaseMarkets.every(m => state.dayRecords[currentDate].visJodi[m.n] !== false);
                return `
                <div class="native-card p-4 mb-3">
                    <div class="flex justify-between items-center mb-3">
                        <h3 class="text-[11px] font-bold text-[#B85CFF] uppercase tracking-widest flex items-center gap-2"><i class="fas fa-eye"></i> Jodi Markets</h3>
                        <div class="flex items-center gap-2 bg-[var(--surface-light)] px-2 py-1.5 rounded-lg border border-[var(--border)]">
                            <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">ALL</span>
                            <label class="switch transform scale-[0.6] origin-right m-0">
                                <input type="checkbox" onchange="toggleAllMarkets('visJodi', this.checked)" ${isAllChecked ? 'checked' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        ${visibleBaseMarkets.map(m => `
                            <div class="flex justify-between items-center bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                                <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase truncate pr-2">${m.n}</span>
                                <label class="switch transform scale-[0.6] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('visJodi', '${m.n}', this.checked)" ${state.dayRecords[currentDate].visJodi[m.n] !== false ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                            </div>`).join('')}
                    </div>
                </div>`;
            };

            let protoHTML = (type, title, colorClass) => `
                <div class="native-card p-4 mb-3">
                    <h3 class="text-[11px] font-bold ${colorClass} uppercase tracking-widest mb-4">${title}</h3>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Capital Cap</label>
                            <input type="number" oninput="state.config.${type}.cap=parseFloat(this.value)||0; runLiveSync(); autoSave();" value="${state.config[type].cap}" class="native-input text-sm py-3" placeholder="0 = Master">
                        </div>
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Target / Card</label>
                            <input type="number" oninput="state.config.${type}.tgt=parseFloat(this.value)||0; runLiveSync(); autoSave();" value="${state.config[type].tgt}" class="native-input text-sm py-3" placeholder="Per card profit">
                        </div>
                    </div>
                </div>`;

            const totalDayPL = globalStats.ank.pl + globalStats.jodi.pl + globalStats.pannel.pl;
            const dayTgt = parseFloat(state.config.dayTarget) || 0;
            const dayPct = dayTgt > 0 ? Math.min(100, Math.round((totalDayPL / dayTgt) * 100)) : 0;
            const capital = parseFloat(state.config.capital) || 0;

            return `
                <div class="px-3 py-4">
                    <p class="sec-header">Capital & Day Targets</p>
                    <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.25);background:rgba(0,194,111,0.04)">
                        <div class="grid grid-cols-2 gap-3 mb-3">
                            <div>
                                <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Apna Capital ₹</label>
                                <input type="number" inputmode="numeric" oninput="state.config.capital=parseFloat(this.value)||0; autoSave();" value="${capital}" class="native-input text-sm py-3 text-[var(--green)]" placeholder="Aapka capital">
                            </div>
                            <div>
                                <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Din Ka Target ₹</label>
                                <input type="number" inputmode="numeric" oninput="state.config.dayTarget=parseFloat(this.value)||0; autoSave();" value="${dayTgt}" class="native-input text-sm py-3 text-[var(--primary)]" placeholder="Daily profit goal">
                            </div>
                        </div>
                        ${dayTgt > 0 ? `
                        <div class="mt-1">
                            <div class="flex justify-between mb-1">
                                <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">Today's Progress</span>
                                <span class="text-[9px] font-bold ${totalDayPL >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${totalDayPL >= 0 ? '+' : ''}₹${totalDayPL.toLocaleString()} / ₹${dayTgt.toLocaleString()}</span>
                            </div>
                            <div class="h-2 bg-[var(--surface-light)] rounded-full overflow-hidden">
                                <div class="h-full rounded-full transition-all" style="width:${Math.max(0, dayPct)}%;background:${totalDayPL >= 0 ? 'var(--green)' : 'var(--rose)'}"></div>
                            </div>
                            <p class="text-[9px] text-[var(--text-muted)] text-right mt-1 font-bold">${dayPct}% complete</p>
                        </div>` : ''}
                    </div>

                    ${mktsHtmlOpenClose('Ank Markets', 'text-[var(--primary)]', 'visAnk')}
                    ${mktsHtmlJodi()}
                    ${mktsHtmlOpenClose('Pan Markets', 'text-[var(--amber)]', 'visPan')}
                    ${protoHTML('ank', 'ANK PROTOCOL', 'text-[var(--primary)]')}
                    ${protoHTML('jodi', 'JODI PROTOCOL', 'text-[#B85CFF]')}
                    ${protoHTML('pannel', 'PAN PROTOCOL', 'text-[var(--amber)]')}
                    <button onclick="saveMaster(false)" class="w-full bg-[var(--green)] text-white py-4 rounded-2xl font-black text-[12px] uppercase tracking-wide mt-2 mb-8 active:scale-95 shadow-lg shadow-[rgba(0,194,111,0.2)]">Save Configuration</button>
                </div>
            `;
        }

        function shareVipApp(pid, name) {
            const safePid = pid.replace('_', '%5F');
            const link = window.location.origin + '/?vip=' + safePid;

            const msg = `🚀 *TITAN NOVA VIP APP* 🚀\\nHello ${name}, yeh aapka personal App portal hai. Is naye link ko open karke *Install App* pe click karein:\\n\\n🔗 ${link}`;

            let textArea = document.createElement("textarea"); textArea.value = msg.replace(/\\\\n/g, '\\n'); textArea.style.position = "fixed"; textArea.style.left = "-999999px"; document.body.appendChild(textArea); textArea.focus(); textArea.select();
            try { document.execCommand('copy'); alert("✅ VIP App Link Copied! Send this link to the client via WhatsApp."); } catch (err) { alert("Link manually copy karein:\\n" + link); } textArea.remove();
        }

        function renderClients() {
            if(!IS_MASTER) return '';
            let html = `
                <div class="px-3 py-4">
                    
                    <div class="native-card p-4 mb-3" style="border-color:rgba(42,171,238,0.25); background:rgba(42,171,238,0.04)">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-10 h-10 rounded-xl bg-[rgba(42,171,238,0.15)] text-[var(--primary)] flex items-center justify-center shrink-0"><i class="fas fa-bullhorn"></i></div>
                            <div>
                                <h3 class="text-[14px] font-black text-white">Live Push Broadcast</h3>
                                <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Send Alert to all VIPs</p>
                            </div>
                        </div>
                        <input id="bcast-title" class="native-input text-[13px] py-3 mb-2" placeholder="Title (e.g. 🔥 Dhamaka Offer)">
                        <textarea id="bcast-msg" rows="2" class="native-input text-[13px] py-3 mb-3" placeholder="Type your message here..."></textarea>
                        <button onclick="sendBroadcast()" class="w-full bg-[var(--primary)] text-white py-3.5 rounded-xl font-black text-[11px] uppercase active:scale-95 shadow-lg shadow-[rgba(42,171,238,0.2)]"><i class="fas fa-paper-plane mr-1"></i> Send Push Notification</button>
                    </div>

                    <div class="native-card p-4 mb-3" style="border-color:rgba(250,199,72,0.2); background:rgba(250,199,72,0.04)">
                        <div class="flex justify-between items-center mb-4">
                            <div>
                                <h3 class="text-[14px] font-black text-white">VIP Connections</h3>
                                <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Manage Client Links</p>
                            </div>
                            <button onclick="importContacts()" class="w-10 h-10 bg-[rgba(250,199,72,0.15)] text-[var(--amber)] rounded-xl flex items-center justify-center active:scale-95 border border-[rgba(250,199,72,0.2)]"><i class="fas fa-address-book"></i></button>
                        </div>
                        <div class="space-y-3">
                            <input id="c-name" class="native-input py-3 text-sm" placeholder="Client Display Name">
                            <input id="c-phone" type="text" inputmode="numeric" class="native-input py-3 text-sm" placeholder="WhatsApp Number">
                            <button onclick="addVIP()" class="w-full bg-[var(--amber)] text-black py-3.5 rounded-xl font-black text-[11px] uppercase active:scale-95">Add VIP Member</button>
                        </div>
                    </div>

                    <p class="sec-header">Active Profiles</p>
                    <div class="space-y-2">
            `;

            Object.keys(appState.profiles).forEach(pid => {
                if(pid === 'admin1') return;
                const c = appState.profiles[pid];
                const isDummy = (pid === 'client_dummy');
                const approvalStatus = String(c.approvalStatus || (c.autoCreated ? 'pending' : 'approved')).toLowerCase();
                const isPendingApproval = approvalStatus === 'pending';
                const expDate = c.expiryDate || '';
                let expLabel = 'No Expiry Set'; let expColor = 'text-[var(--text-muted)]';
                if (expDate) {
                    const expObj = new Date(expDate); const today = new Date(); today.setHours(0,0,0,0); expObj.setHours(0,0,0,0);
                    const dLeft = Math.ceil((expObj - today) / (1000*60*60*24));
                    expLabel = dLeft > 0 ? `${dLeft}d left - ${expObj.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})}` : `Expired - ${expObj.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})}`;
                    expColor = dLeft > 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]';
                }
                html += `
                    <div class="native-card m-0 border-l-4 ${isPendingApproval ? 'border-l-[var(--amber)]' : (isDummy ? 'border-l-[var(--purple)]' : 'border-l-[var(--primary)]')}">
                        <div onclick="openClient('${pid}')" class="p-4 flex justify-between items-center cursor-pointer active:opacity-70 transition-opacity">
                            <div class="flex items-center gap-3">
                                <div class="w-10 h-10 rounded-full bg-[var(--surface-light)] border border-[var(--border)] flex items-center justify-center ${isPendingApproval ? 'text-[var(--amber)]' : (isDummy ? 'text-[var(--purple)]' : 'text-[var(--primary)]')}"><i class="fas ${isPendingApproval ? 'fa-user-clock' : (isDummy ? 'fa-vial' : 'fa-user')}"></i></div>
                                <div>
                                    <p class="${isPendingApproval ? 'text-[var(--amber)]' : (isDummy ? 'text-[var(--purple)]' : 'text-white')} font-black text-[14px] uppercase">${c.name || 'AUTO VIP'} ${isPendingApproval ? '<span class="ml-1 text-[8px] bg-[rgba(250,199,72,0.14)] border border-[rgba(250,199,72,0.25)] text-[var(--amber)] px-1.5 py-0.5 rounded-md align-middle">PENDING</span>' : ''}</p>
                                    <p class="text-[10px] ${expColor} font-medium mt-0.5"><i class="fas fa-crown text-[8px] mr-1"></i>${isPendingApproval ? 'Admin approval required' : expLabel}</p>
                                    ${c.phone ? `<p class="text-[9px] text-[var(--text-muted)] font-bold mt-0.5"><i class="fab fa-whatsapp mr-1"></i>${c.phone}</p>` : ''}
                                </div>
                            </div>
                            <div class="flex gap-2">
                                <button onclick="event.stopPropagation(); shareVipApp('${pid}', '${c.name}')" class="w-9 h-9 text-[var(--primary)] bg-[rgba(42,171,238,0.1)] rounded-xl flex items-center justify-center active:scale-95 border border-[rgba(42,171,238,0.15)]"><i class="fas fa-link text-xs"></i></button>
                                ${!isDummy ? `<button onclick="event.stopPropagation(); deleteProfile('${pid}')" class="w-9 h-9 text-[var(--rose)] bg-[rgba(255,93,93,0.1)] rounded-xl flex items-center justify-center active:scale-95 border border-[rgba(255,93,93,0.15)]"><i class="fas fa-trash-alt text-xs"></i></button>` : ''}
                            </div>
                        </div>
                        ${isPendingApproval ? `
                        <div class="px-4 pb-3 grid grid-cols-2 gap-2 border-t border-[var(--border)]">
                            <button onclick="event.stopPropagation(); approveVipProfile('${pid}')" class="bg-[rgba(0,194,111,0.16)] text-[var(--green)] border border-[rgba(0,194,111,0.28)] py-2.5 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-check mr-1"></i>Approve</button>
                            <button onclick="event.stopPropagation(); rejectVipProfile('${pid}')" class="bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] py-2.5 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-times mr-1"></i>Reject</button>
                        </div>` : ''}
                        <div class="px-4 pb-3 flex items-center gap-2 border-t border-[var(--border)]">
                            <i class="fas fa-calendar-check text-[var(--amber)] text-xs shrink-0"></i>
                            <input type="date" id="exp-${pid}" value="${expDate}" class="flex-1 min-w-0 bg-[var(--surface-light)] border border-[var(--border)] text-white rounded-lg px-2 py-1.5 text-[11px] font-bold outline-none focus:border-[var(--primary)]">
                            <button onclick="saveExpiryDate('${pid}')" class="bg-[rgba(250,199,72,0.15)] text-[var(--amber)] border border-[rgba(250,199,72,0.2)] px-3 py-1.5 rounded-lg font-bold text-[10px] uppercase active:scale-95 shrink-0">Set</button>
                        </div>
                        <div class="px-4 pb-3 flex items-center justify-between border-t border-[var(--border)]">
                            <div>
                                <p class="text-[9px] font-bold text-[var(--text-muted)] uppercase">App Access</p>
                                <p class="text-[10px] font-bold ${isPendingApproval ? 'text-[var(--amber)]' : (c.vipAccessEnabled !== false ? 'text-[var(--green)]' : 'text-[var(--rose)]')}">${isPendingApproval ? 'Pending — entry/app blocked until approval' : (c.vipAccessEnabled !== false ? 'Enabled — VIP can use app' : 'Disabled — Read-Only Mode')}</p>
                            </div>
                            <label class="switch m-0">
                                <input type="checkbox" onchange="toggleVipAccess('${pid}', this.checked)" ${c.vipAccessEnabled !== false ? 'checked' : ''} ${isPendingApproval ? 'disabled' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>`;
            });

            html += '</div></div>';
            return html;
        }

        function renderWalletsTab() {
            if(!IS_MASTER) return '';
            ensureWalletStruct();
            const clients = walletClientIds();
            const rows = clients.map(uid => {
                const p = (appState.profiles || {})[uid] || {};
                const w = walletForUser(uid);
                return {uid, p, w, bal:Number(w.balance||0), hold:walletHold(w), credit:Number(w.creditLimit||0)};
            }).sort((a,b)=>String(a.p.name||a.uid).localeCompare(String(b.p.name||b.uid)));
            const totalBal = rows.reduce((s,x)=>s+x.bal,0);
            const totalHold = rows.reduce((s,x)=>s+x.hold,0);
            const body = rows.map(x=>`<div class="native-card p-3 mb-2">
                <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0"><h3 class="text-white font-black text-[12px] uppercase truncate">${htmlEscape(x.p.name || x.uid)}</h3><p class="text-[9px] text-[var(--text-muted)] truncate">${htmlEscape(x.p.phone || '')} · ${htmlEscape(x.uid)}</p></div>
                    <div class="text-right shrink-0"><p class="text-[var(--green)] font-black text-[13px]">${fmtMoney(x.bal)}</p><p class="text-[9px] text-[var(--text-muted)]">Hold ${fmtMoney(x.hold)}</p></div>
                </div>
                <div class="grid grid-cols-3 gap-2 mt-3 text-center">
                    <button onclick="walletAddSubtract('${x.uid}','add')" class="bg-[rgba(0,194,111,0.12)] text-[var(--green)] border border-[rgba(0,194,111,0.2)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95">Add</button>
                    <button onclick="walletAddSubtract('${x.uid}','subtract')" class="bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.2)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95">Minus</button>
                    <button onclick="walletSetCredit('${x.uid}')" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95">Credit</button>
                </div>
                <div class="grid grid-cols-2 gap-2 mt-2"><button onclick="showWalletHistory('${x.uid}')" class="bg-[rgba(42,171,238,0.10)] text-[var(--primary)] border border-[rgba(42,171,238,0.22)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95">History</button><button onclick="walletZeroSettle('${x.uid}')" class="bg-[var(--surface-light)] text-[var(--text-muted)] border border-[var(--border)] py-2.5 rounded-xl font-black text-[9px] uppercase active:scale-95">Zero</button></div>
            </div>`).join('');
            setTimeout(()=>refreshWalletsState().then(()=>{}), 100);
            return `<div class="px-3 py-4">
                <p class="sec-header">Wallets</p>
                <div class="wallet-hud rounded-2xl mb-3">
                    ${financeStatCard('Users', rows.length, '')}
                    ${financeStatCard('Balance', fmtMoney(totalBal), 'green')}
                    ${financeStatCard('Hold', fmtMoney(totalHold), 'amber')}
                    ${financeStatCard('Available', fmtMoney(totalBal-totalHold), totalBal-totalHold>=0?'green':'rose')}
                </div>
                <div class="native-card p-3 mb-3"><div class="grid grid-cols-2 gap-2"><input id="wallet-default-credit" class="native-input text-[11px]" type="number" placeholder="Default credit" value="${Number((appState.walletSettings||{}).defaultCreditLimit||0)}"><button onclick="saveWalletDefaultCredit()" class="bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">Save Default</button></div></div>
                ${renderWalletHistoryPanel()}
                ${body || `<div class="native-card p-5 text-center text-[var(--text-muted)] text-xs">No VIP wallets found.</div>`}
            </div>`;
        }

        function renderMarketProtocolControls() {
            if(!IS_MASTER) return '';
            ensureDataStruct();

            const visibleBaseMarkets = (baseMarkets || []).filter(m => !(m && m.hiddenForLedger));

            const mktsHtmlOpenClose = (title, colorClass, trackDict) => {
                const isAllChecked = visibleBaseMarkets.every(bm => {
                    const ok = bm.n + ' OPEN'; const ck = bm.n + ' CLOSE';
                    return state.dayRecords[currentDate][trackDict][ok] !== false &&
                           state.dayRecords[currentDate][trackDict][ck] !== false;
                });
                return `
                <div class="native-card p-4 mb-3">
                    <div class="flex justify-between items-center mb-3">
                        <h3 class="text-[11px] font-bold ${colorClass} uppercase tracking-widest flex items-center gap-2"><i class="fas fa-eye"></i> ${title}</h3>
                        <div class="flex items-center gap-2 bg-[var(--surface-light)] px-2 py-1.5 rounded-lg border border-[var(--border)]">
                            <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">ALL</span>
                            <label class="switch transform scale-[0.6] origin-right m-0">
                                <input type="checkbox" onchange="toggleAllMarketsOpenClose('${trackDict}', this.checked)" ${isAllChecked ? 'checked' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>
                    <div class="flex justify-end gap-5 mb-1.5 pr-1">
                        <span class="text-[8px] font-black text-[var(--primary)] uppercase tracking-wider">OPEN</span>
                        <span class="text-[8px] font-black text-[var(--amber)] uppercase tracking-wider">CLOSE</span>
                    </div>
                    <div class="space-y-1.5">
                        ${visibleBaseMarkets.map(bm => {
                            const ok = bm.n + ' OPEN'; const ck = bm.n + ' CLOSE';
                            const openOn  = state.dayRecords[currentDate][trackDict][ok]  !== false;
                            const closeOn = state.dayRecords[currentDate][trackDict][ck] !== false;
                            return `
                            <div class="flex items-center gap-2 bg-[var(--surface-light)] px-3 py-2 rounded-xl border border-[var(--border)]">
                                <span class="flex-1 text-[9px] font-bold text-[var(--text-muted)] uppercase truncate">${bm.n}</span>
                                <label class="switch transform scale-[0.55] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('${trackDict}', '${attrEscape(bm.n)} OPEN', this.checked)" ${openOn ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                                <label class="switch transform scale-[0.55] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('${trackDict}', '${attrEscape(bm.n)} CLOSE', this.checked)" ${closeOn ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                            </div>`;
                        }).join('')}
                    </div>
                </div>`;
            };

            const mktsHtmlJodi = () => {
                const isAllChecked = visibleBaseMarkets.every(m => state.dayRecords[currentDate].visJodi[m.n] !== false);
                return `
                <div class="native-card p-4 mb-3">
                    <div class="flex justify-between items-center mb-3">
                        <h3 class="text-[11px] font-bold text-[#B85CFF] uppercase tracking-widest flex items-center gap-2"><i class="fas fa-eye"></i> Jodi Markets</h3>
                        <div class="flex items-center gap-2 bg-[var(--surface-light)] px-2 py-1.5 rounded-lg border border-[var(--border)]">
                            <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">ALL</span>
                            <label class="switch transform scale-[0.6] origin-right m-0">
                                <input type="checkbox" onchange="toggleAllMarkets('visJodi', this.checked)" ${isAllChecked ? 'checked' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        ${visibleBaseMarkets.map(m => `
                            <div class="flex justify-between items-center bg-[var(--surface-light)] p-3 rounded-xl border border-[var(--border)]">
                                <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase truncate pr-2">${m.n}</span>
                                <label class="switch transform scale-[0.6] origin-right m-0">
                                    <input type="checkbox" onchange="toggleMarketVis('visJodi', '${attrEscape(m.n)}', this.checked)" ${state.dayRecords[currentDate].visJodi[m.n] !== false ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                            </div>`).join('')}
                    </div>
                </div>`;
            };

            const protoHTML = (type, title, colorClass) => `
                <div class="native-card p-4 mb-3">
                    <h3 class="text-[11px] font-bold ${colorClass} uppercase tracking-widest mb-4">${title}</h3>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Capital Cap</label>
                            <input type="number" oninput="state.config.${type}.cap=parseFloat(this.value)||0; runLiveSync(); titanSaveAdminSettingsNow();" value="${state.config[type].cap}" class="native-input text-sm py-3" placeholder="0 = Master">
                        </div>
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Target / Card</label>
                            <input type="number" oninput="state.config.${type}.tgt=parseFloat(this.value)||0; runLiveSync(); titanSaveAdminSettingsNow();" value="${state.config[type].tgt}" class="native-input text-sm py-3" placeholder="Per card profit">
                        </div>
                    </div>
                </div>`;

            const totalDayPL = globalStats.ank.pl + globalStats.jodi.pl + globalStats.pannel.pl;
            const dayTgt = parseFloat(state.config.dayTarget) || 0;
            const dayPct = dayTgt > 0 ? Math.min(100, Math.round((totalDayPL / dayTgt) * 100)) : 0;
            const capital = parseFloat(state.config.capital) || 0;

            return `
                <p class="sec-header">Market Protocol Controls</p>
                <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.25);background:rgba(0,194,111,0.04)">
                    <div class="flex items-start gap-3 mb-3">
                        <div class="w-10 h-10 rounded-xl bg-[rgba(0,194,111,0.15)] text-[var(--green)] flex items-center justify-center"><i class="fas fa-sliders-h"></i></div>
                        <div class="min-w-0">
                            <h3 class="text-white font-black text-[14px]">Capital & Card Target Protocol</h3>
                            <p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Setup tab hata diya gaya hai. Yehi Market tab se capital, day target, capital, day target aur per-card target save hoga. Market visibility sirf neeche Central Market Registry me rahegi.</p>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3 mb-3">
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Apna Capital ₹</label>
                            <input type="number" inputmode="numeric" oninput="state.config.capital=parseFloat(this.value)||0; titanSaveAdminSettingsNow();" value="${capital}" class="native-input text-sm py-3 text-[var(--green)]" placeholder="Aapka capital">
                        </div>
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Din Ka Target ₹</label>
                            <input type="number" inputmode="numeric" oninput="state.config.dayTarget=parseFloat(this.value)||0; titanSaveAdminSettingsNow();" value="${dayTgt}" class="native-input text-sm py-3 text-[var(--primary)]" placeholder="Daily profit goal">
                        </div>
                    </div>
                    ${dayTgt > 0 ? `
                    <div class="mt-1">
                        <div class="flex justify-between mb-1">
                            <span class="text-[9px] font-bold text-[var(--text-muted)] uppercase">Today's Progress</span>
                            <span class="text-[9px] font-bold ${totalDayPL >= 0 ? 'text-[var(--green)]' : 'text-[var(--rose)]'}">${totalDayPL >= 0 ? '+' : ''}₹${totalDayPL.toLocaleString()} / ₹${dayTgt.toLocaleString()}</span>
                        </div>
                        <div class="h-2 bg-[var(--surface-light)] rounded-full overflow-hidden">
                            <div class="h-full rounded-full transition-all" style="width:${Math.max(0, dayPct)}%;background:${totalDayPL >= 0 ? 'var(--green)' : 'var(--rose)'}"></div>
                        </div>
                        <p class="text-[9px] text-[var(--text-muted)] text-right mt-1 font-bold">${dayPct}% complete</p>
                    </div>` : ''}
                </div>
                ${protoHTML('ank', 'ANK CARD PROTOCOL', 'text-[var(--primary)]')}
                ${protoHTML('jodi', 'JODI CARD PROTOCOL', 'text-[#B85CFF]')}
                ${protoHTML('pannel', 'PAN CARD PROTOCOL', 'text-[var(--amber)]')}
            `;
        }

        function renderMarketManagerTab(){
            if(!IS_MASTER) return '';
            const reg = ensureMarketRegistry();
            const q = marketManagerSearch.trim().toLowerCase();
            let items = Object.values(reg.items || {}).filter(x => x && x.deleted !== true).sort(marketItemLoopCompare);
            if(q) items = items.filter(x => [x.name,x.displayName,x.websiteName,(x.aliases||[]).join(' ')].join(' ').toLowerCase().includes(q));
            if(!marketManagerShowDisabled) items = items.filter(x => x.enabled !== false && x.archived !== true);
            const deletedCount = Object.values(reg.items||{}).filter(x=>x && x.deleted===true).length;
            const activeCount = Object.values(reg.items||{}).filter(x=>x && x.deleted!==true && x.enabled!==false && x.archived!==true).length;
            const ledgerCount = marketItemsForPurpose('ledger').length;
            const resultCount = marketItemsForPurpose('result').length;
            const card = item => {
                const off = item.enabled === false || item.archived === true;
                return `<div class="native-card market-card-compact mb-2 ${off ? 'opacity-70' : ''}">
                    <div class="market-card-head">
                        <div class="min-w-0">
                            <h3 class="market-card-title text-white font-black uppercase truncate">${htmlEscape(item.displayName || item.name)}</h3>
                            <p class="text-[9px] text-[var(--text-muted)] mt-1 truncate">Website: ${htmlEscape(item.websiteName || item.name)}</p>
                            ${item.settingsLocked ? '<p class="text-[8px] text-[var(--green)] font-black uppercase mt-1"><i class="fas fa-lock mr-1"></i>Saved · Manual change only</p>' : ''}
                            <div class="flex gap-1 flex-wrap mt-2">${marketBadge(item.enabled !== false && !item.archived, 'ACTIVE', 'DISABLED')}${marketBadge(item.ledgerEnabled !== false, 'LEDGER', 'NO LEDGER')}${marketBadge(item.resultEnabled !== false, 'RESULTS', 'NO RESULTS')}${marketBadge(item.autoPassFailEnabled !== false, 'AUTO PF', 'NO PF')}${marketBadge(item.entryEnabled !== false, 'ENTRY', 'NO ENTRY')}</div>
                        </div>
                        <div class="market-card-actions shrink-0">${off ? `<button onclick="restoreMarket('${attrEscape(item.id)}')" class="bg-[var(--green)] text-white px-3 py-2 rounded-xl font-black text-[9px] uppercase">Restore</button>` : `<button onclick="disableMarket('${attrEscape(item.id)}')" class="bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] px-3 py-2 rounded-xl font-black text-[9px] uppercase">Disable</button>`}<button onclick="deleteMarket('${attrEscape(item.id)}')" class="bg-[rgba(255,93,93,0.14)] text-[var(--rose)] border border-[rgba(255,93,93,0.30)] px-3 py-2 rounded-xl font-black text-[9px] uppercase"><i class="fas fa-trash mr-1"></i>Delete</button></div>
                    </div>
                    <div class="market-field-grid">
                        <div><label class="text-[8px] text-[var(--text-muted)] uppercase font-bold ml-1">App Name</label><input class="native-input py-2.5 text-[11px]" value="${attrEscape(item.displayName || item.name)}" onchange="updateMarketText('${attrEscape(item.id)}','displayName',this.value)"></div>
                        <div><label class="text-[8px] text-[var(--text-muted)] uppercase font-bold ml-1">Website Name</label><input class="native-input py-2.5 text-[11px]" value="${attrEscape(item.websiteName || item.name)}" onchange="updateMarketText('${attrEscape(item.id)}','websiteName',this.value)"></div>
                        <div><label class="text-[8px] text-[var(--text-muted)] uppercase font-bold ml-1">Open Time</label><input class="native-input py-2.5 text-[11px]" placeholder="HH:MM" value="${attrEscape((item.times||{}).open || '')}" onchange="updateMarketTime('${attrEscape(item.id)}','open',this.value)"></div>
                        <div><label class="text-[8px] text-[var(--text-muted)] uppercase font-bold ml-1">Close Time</label><input class="native-input py-2.5 text-[11px]" placeholder="HH:MM" value="${attrEscape((item.times||{}).close || '')}" onchange="updateMarketTime('${attrEscape(item.id)}','close',this.value)"></div>
                    </div>
                    <div class="market-toggle-grid">
                        ${[['enabled','Active'],['ledgerEnabled','Ledger'],['resultEnabled','Results'],['autoPassFailEnabled','Auto P/F'],['scheduleEnabled','Schedule'],['entryEnabled','Entries'],['autoResultEnabled','Auto Result']].map(([key,label]) => `<label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="font-bold text-[var(--text-muted)] uppercase">${label}</span><input type="checkbox" ${item[key]!==false?'checked':''} onchange="setMarketItemFlag('${attrEscape(item.id)}','${key}',this.checked)"></label>`).join('')}
                        <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="font-bold text-[var(--text-muted)] uppercase">Open Stage</span><input type="checkbox" ${(item.stages||{}).open!==false?'checked':''} onchange="setMarketStageFlag('${attrEscape(item.id)}','open',this.checked)"></label>
                        <label class="flex items-center justify-between gap-2 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="font-bold text-[var(--text-muted)] uppercase">Close Stage</span><input type="checkbox" ${(item.stages||{}).close!==false?'checked':''} onchange="setMarketStageFlag('${attrEscape(item.id)}','close',this.checked)"></label>
                    </div>
                    <div class="market-chart-row"><input class="native-input" placeholder="Chart URL" value="${attrEscape(item.chartUrl || '')}" onchange="updateMarketText('${attrEscape(item.id)}','chartUrl',this.value)"><button onclick="archiveMarket('${attrEscape(item.id)}')" class="bg-[var(--surface-light)] text-[var(--text-muted)] border border-[var(--border)] rounded-xl font-black text-[9px] uppercase">Archive</button></div><div class="market-route-box bg-[rgba(42,171,238,0.06)] border border-[rgba(42,171,238,0.16)]"><div class="flex items-center justify-between gap-2 mb-2"><div><div class="text-[9px] font-black uppercase text-[var(--primary)]"><i class="fab fa-whatsapp mr-1"></i>WhatsApp Role Routing</div><p class="text-[8px] text-[var(--text-muted)] mt-0.5">Ledger schedule, game entry, results, forward/load sab alag target me set karo. Blank = old/global behavior.</p></div></div><div class="grid grid-cols-1 gap-2">${roleTargetRow(item,'schedule','fa-clock','Intel/ledger schedule kis group me jayega')}${roleTargetRow(item,'entry','fa-gamepad','User game entry sirf is group/private se accept hogi')}${roleTargetRow(item,'result','fa-trophy','Result declaration kis group me jayega')}${roleTargetRow(item,'forward','fa-share-nodes','Load/forward report kis group me jayega')}${roleTargetRow(item,'bookie','fa-user-shield','Bookie/admin work, alerts aur management kis group me rahega')}</div></div>
                </div>`;
            };
            return `<div class="market-manager-wrap px-3 py-4">
                ${renderMarketProtocolControls()}
                <p class="sec-header">Market Manager</p>
                <div class="native-card p-4 mb-3" style="border-color:rgba(42,171,238,0.24);background:rgba(42,171,238,0.04)">
                    <div class="flex items-start gap-3 mb-3"><div class="w-10 h-10 rounded-xl bg-[rgba(42,171,238,0.15)] text-[var(--primary)] flex items-center justify-center"><i class="fas fa-store"></i></div><div><h3 class="text-white font-black text-[14px]">Single Market Visibility Registry</h3><p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Market ON/OFF, Ledger/Results/Auto PF/Schedule visibility sirf yahin se control hoga. Protocol section me duplicate market visibility nahi rahegi.</p></div></div>
                    <div class="market-quick-grid"><div class="stat-box"><p class="stat-lbl">Active</p><p class="stat-val">${activeCount}</p></div><div class="stat-box"><p class="stat-lbl">Ledger</p><p class="stat-val">${ledgerCount}</p></div><div class="stat-box"><p class="stat-lbl">Results</p><p class="stat-val">${resultCount}</p></div><div class="stat-box"><p class="stat-lbl">Deleted</p><p class="stat-val text-[var(--rose)]">${deletedCount}</p></div></div>
                    <div class="grid grid-cols-2 gap-2 mt-3"><button onclick="saveMarketRegistry()" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-save mr-1"></i>Save Registry</button><button onclick="reloadMarketRegistry()" class="bg-[var(--surface-light)] text-white border border-[var(--border)] py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-rotate mr-1"></i>Reload</button></div>
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(250,199,72,0.24);background:rgba(250,199,72,0.04)">
                    <div class="flex items-start gap-3 mb-3"><div class="w-10 h-10 rounded-xl bg-[rgba(250,199,72,0.15)] text-[var(--amber)] flex items-center justify-center"><i class="fas fa-globe"></i></div><div><h3 class="text-white font-black text-[14px]">Website Mapping Tools</h3><p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Website scan karo, new markets checkbox se choose/select karo, phir Save Selected se direct registry me add/save karo.</p></div></div>
                    <div class="mb-3">${marketScanSummaryHtml()}</div>
                    <div class="grid grid-cols-2 gap-2"><button onclick="testMarketWebsiteMapping()" class="bg-[var(--amber)] text-black py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-magnifying-glass-chart mr-1"></i>${marketSourceScanLoading ? 'Scanning...' : 'Scan Website'}</button><button onclick="importMarketsFromWebsite()" class="bg-[var(--green)] text-white border border-[rgba(0,194,111,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-check-double mr-1"></i>Save Selected</button></div>
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.24);background:rgba(0,194,111,0.04)">
                    <div class="flex items-start gap-3 mb-3"><div class="w-10 h-10 rounded-xl bg-[rgba(0,194,111,0.15)] text-[var(--green)] flex items-center justify-center"><i class="fas fa-plus"></i></div><div><h3 class="text-white font-black text-[14px]">Direct Add Full Market</h3><p class="text-[9px] text-[var(--text-muted)] leading-relaxed">Market name + website name + open/close time do. Save karte hi Ledger, Entries, Results, Auto P/F aur Schedule me same market aa jayega. Role-wise WhatsApp groups bhi optional set kar sakte ho.</p></div></div>
                    <div class="grid grid-cols-2 gap-2"><input id="mm-name" class="native-input py-3 text-[11px]" placeholder="APP MARKET NAME"><input id="mm-website" class="native-input py-3 text-[11px]" placeholder="WEBSITE NAME / RESULT NAME"><input id="mm-open" class="native-input py-3 text-[11px]" placeholder="Open HH:MM"><input id="mm-close" class="native-input py-3 text-[11px]" placeholder="Close HH:MM"><input id="mm-chart" class="native-input py-3 text-[11px] col-span-2" placeholder="Chart/Result URL optional"><textarea id="mm-schedule-targets" class="native-input py-3 text-[10px] col-span-2" rows="1" placeholder="Schedule group optional"></textarea><textarea id="mm-entry-targets" class="native-input py-3 text-[10px] col-span-2" rows="1" placeholder="Game/Entry group optional"></textarea><textarea id="mm-result-targets" class="native-input py-3 text-[10px] col-span-2" rows="1" placeholder="Result group optional"></textarea><textarea id="mm-forward-targets" class="native-input py-3 text-[10px] col-span-2" rows="1" placeholder="Forward/Load group optional"></textarea><textarea id="mm-bookie-targets" class="native-input py-3 text-[10px] col-span-2" rows="1" placeholder="Bookie/Admin work group optional"></textarea></div>
                    <div class="grid grid-cols-2 gap-2 mt-2 text-[9px]">${[['mm-ledger','Ledger',true],['mm-results','Results',true],['mm-autopf','Auto P/F',true],['mm-schedule','Schedule',true],['mm-entry','Entries',true],['mm-stage-open','Open Stage',true],['mm-stage-close','Close Stage',true]].map(([id,label,checked]) => `<label class="flex items-center justify-between bg-[var(--surface-light)] border border-[var(--border)] rounded-xl px-3 py-2"><span class="font-bold text-[var(--text-muted)] uppercase">${label}</span><input id="${id}" type="checkbox" ${checked?'checked':''}></label>`).join('')}</div>
                    <button onclick="addMarketFromManager()" class="mt-3 w-full bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-check mr-1"></i>Direct Add in All</button>
                </div>
                <div class="flex gap-2 mb-3"><input value="${attrEscape(marketManagerSearch)}" oninput="setMarketManagerSearch(this.value)" class="native-input py-3 text-[12px]" placeholder="Search market..."><label class="flex items-center gap-2 px-3 rounded-xl bg-[var(--surface-light)] border border-[var(--border)] text-[9px] text-[var(--text-muted)] font-black uppercase shrink-0"><input type="checkbox" onchange="toggleMarketManagerDisabled(this.checked)" ${marketManagerShowDisabled?'checked':''}> Disabled</label></div>
                ${items.length ? items.map(card).join('') : '<div class="native-card p-6 text-center text-[var(--text-muted)] text-xs">Market nahi mila.</div>'}
                <div class="native-card p-3 mb-8 text-[10px] text-[var(--text-muted)] leading-relaxed"><b class="text-white">Rule:</b> Jo market nahi chahiye usko Delete se UI/Ledger/Results list se hata sakte ho. Old history safe rahegi. Dubara chahiye to + Add New Market ya Website Save Selected se add kar sakte ho. Add Market ab direct save karta hai aur valid time ke hisab se Ledger/Schedule order me fit hota hai. Save ke baad setting locked rahegi; change sirf manual edit + Save se hoga.</div>
            </div>`;
        }

        function renderResultsTab() {
            if(!IS_MASTER) return '';
            ensureResultStruct();
            const targetCount = appState.resultTargets.length;
            const records = appState.resultRecords[currentDate] || {};
            const autoScrapeOn = !(appState.resultSettings && appState.resultSettings.autoScrapeEnabled === false);
            let html = `<div class="px-3 py-4">
                
                <p class="sec-header">Auto Result Sender</p>
                <div class="native-card p-4 mb-3" style="border-color:rgba(250,199,72,0.22);background:rgba(250,199,72,0.04)">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-10 h-10 rounded-xl bg-[rgba(250,199,72,0.15)] text-[var(--amber)] flex items-center justify-center border border-[rgba(250,199,72,0.2)]"><i class="fas fa-trophy"></i></div>
                        <div class="flex-1 min-w-0">
                            <h3 class="text-white font-black text-[14px]">Open / Close Result Declaration</h3>
                            <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Open: 123-4 · Close: 123-45-678</p>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3 mb-3">
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Result Date</label>
                            <input type="date" value="${currentDate}" onchange="changeDate(this.value); setMainNav('results');" class="native-input text-sm py-3">
                        </div>
                        <div>
                            <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Targets</label>
                            <div class="native-input text-sm py-3 text-[var(--green)]">${targetCount} Saved</div>
                        </div>
                    </div>
                    <label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-2 ml-1">Result WhatsApp Targets</label>
                    <textarea id="result-targets-input" class="hidden">${titanResultTargetsText()}</textarea>
                    <div class="bg-[#17212B] border border-[var(--border)] rounded-xl p-3 mb-3 min-h-[54px]">${selectedTargetSummary(appState.resultTargets || [], 6)}</div>
                    <button onclick="openResultTargetPicker()" class="w-full bg-[rgba(42,171,238,0.15)] text-[var(--primary)] border border-[rgba(42,171,238,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-list-check mr-1"></i> Pick Groups / Contacts</button>
                    <div class="mt-3 flex items-center justify-between gap-3 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3">
                        <div class="min-w-0">
                            <p class="text-white font-black text-[11px] uppercase">Auto Scrape</p>
                            <p class="text-[9px] text-[var(--text-muted)] leading-relaxed">${autoScrapeOn ? 'ON: Gateway SattaMatkaDpboss.Mobi live page se result detect karega.' : 'OFF: Gateway scrape skip karega. Manual Declare active hai.'}</p>
                            <p class="text-[8px] text-[var(--text-muted)] mt-1 break-all">Source: ${(appState.resultSettings && appState.resultSettings.sourceUrl) || 'https://sattamatkadpboss.mobi/'}</p>
                        </div>
                        <label class="switch m-0 shrink-0">
                            <input type="checkbox" onchange="saveResultScrapeSetting(this.checked)" ${autoScrapeOn ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="mt-2 flex items-center justify-between gap-3 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3">
                        <div class="min-w-0">
                            <p class="text-white font-black text-[11px] uppercase">Use Forward Targets</p>
                            <p class="text-[9px] text-[var(--text-muted)] leading-relaxed">ON: Result declarations Result targets + Forward tab targets dono par jayenge.</p>
                        </div>
                        <label class="switch m-0 shrink-0"><input id="result-use-forward-targets" type="checkbox" onchange="saveResultDeliverySettings()" ${appState.resultSettings.useForwardTargetsForResults === false ? '' : 'checked'}><span class="slider"></span></label>
                    </div>
                    <div class="grid grid-cols-3 gap-2 mt-2">
                        <button onclick="runResultScrapeNow()" class="w-full ${autoScrapeOn ? 'bg-[rgba(250,199,72,0.14)] text-[var(--amber)] border-[rgba(250,199,72,0.28)]' : 'bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border-[rgba(255,93,93,0.22)]'} border py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-magnet mr-1"></i> Scrape Test</button>
                        <button onclick="retryResultDeclarations()" class="w-full bg-[rgba(42,171,238,0.12)] text-[var(--primary)] border border-[rgba(42,171,238,0.25)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-rotate mr-1"></i> Retry Send</button>
                        <button onclick="clearInvalidAutoResults()" class="w-full bg-[rgba(255,93,93,0.10)] text-[var(--rose)] border border-[rgba(255,93,93,0.22)] py-3 rounded-xl font-black text-[10px] uppercase active:scale-95"><i class="fas fa-shield-alt mr-1"></i> Clear Old</button>
                    </div>
                    <p class="text-[9px] text-[var(--text-muted)] leading-relaxed mt-2">Fresh rule: pehle 123-4 open save hoga; 123-45-678 close tabhi valid hoga jab woh usi open se start ho. Old/yesterday close auto ignore hoga.</p>
                </div>
                ${settlementCardHtml()}
                <p class="sec-header">Market Results</p>`;

            html += resultBaseMarkets.map((m, i) => {
                const rec = records[m.n] || {};
                const view = resultDisplayView(rec);
                const currentVal = view.close || view.open || '';
                const openText = view.open ? view.open : 'Pending';
                const closeText = view.close ? view.close : (view.ignoredClose ? 'Ignored old' : 'Pending');
                const badgeText = view.close ? 'Final' : (view.open ? 'Open Done' : (view.ignoredClose ? 'Old Skipped' : 'Waiting'));
                const badgeClass = view.close ? 'text-[var(--green)] border-[rgba(0,194,111,0.25)] bg-[rgba(0,194,111,0.08)]' : (view.open ? 'text-[var(--primary)] border-[rgba(42,171,238,0.25)] bg-[rgba(42,171,238,0.08)]' : (view.ignoredClose ? 'text-[var(--rose)] border-[rgba(255,93,93,0.25)] bg-[rgba(255,93,93,0.08)]' : 'text-[var(--text-muted)] border-[var(--border)] bg-[var(--surface-light)]'));
                const ignoredNote = view.ignoredClose ? `<p class="text-[8px] text-[var(--rose)] font-bold mt-1">Old close ${view.rawClose} ignored: fresh open missing/mismatch.</p>` : '';
                return `<div class="native-card p-4 mb-2">
                    <div class="flex items-start justify-between gap-3 mb-3">
                        <div class="min-w-0">
                            <h3 class="text-white font-black text-[13px] uppercase truncate">${m.n}</h3>
                            <p class="text-[9px] text-[var(--text-muted)] font-bold mt-1">Open: <span class="text-[var(--primary)]">${openText}</span> · Close: <span class="text-[var(--amber)]">${closeText}</span></p>
                            ${ignoredNote}
                        </div>
                        <div class="text-[8px] font-black uppercase px-2 py-1 rounded-lg border ${badgeClass}">${badgeText}</div>
                    </div>
                    <div class="flex gap-2">
                        <input id="result-input-${i}" class="native-input text-sm py-3 flex-1" placeholder="123-4 / 123-45-678" value="${currentVal}">
                        <button onclick="saveMarketResult(${i})" class="bg-[var(--primary)] text-white px-4 rounded-xl font-black text-[10px] uppercase active:scale-95 shrink-0"><i class="fas fa-paper-plane mr-1"></i>Declare</button>
                    </div>
                </div>`;
            }).join('');

            html += `<div class="native-card p-3 mb-8 text-[10px] text-[var(--text-muted)] leading-relaxed">
                <b class="text-white">Note:</b> Strict 2-stage safety active hai. Pehle fresh Open 123-4 save/declare hoga; uske baad matching Close 123-45-678 declare hoga. Direct full/old website result group me send nahi hoga.
            </div></div>`;
            return html;
        }

        function paymentAutomationSettingsHtml(){
            const ps = appState.paymentSettings || {};
            const boolRow = (id, label, help, val) => `
                <div class="flex items-center justify-between gap-3 bg-[var(--surface-light)] border border-[var(--border)] rounded-xl p-3 mb-2">
                    <div class="min-w-0">
                        <p class="text-white font-black text-[11px] uppercase">${label}</p>
                        <p class="text-[9px] text-[var(--text-muted)] leading-relaxed">${help}</p>
                    </div>
                    <label class="switch m-0 shrink-0"><input id="${id}" type="checkbox" ${val ? 'checked' : ''}><span class="slider"></span></label>
                </div>`;
            return `
                <div class="flex items-center gap-3 mb-4">
                    <div class="w-10 h-10 rounded-xl bg-[rgba(42,171,238,0.15)] text-[var(--primary)] flex items-center justify-center border border-[rgba(42,171,238,0.2)]"><i class="fas fa-shield-halved"></i></div>
                    <div>
                        <h3 class="text-white font-black text-[14px]">Payment Verification</h3>
                        <p class="text-[9px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Approve = wallet credit + optional membership</p>
                    </div>
                </div>
                ${boolRow('pay-auto-enabled', 'Automation Enabled', 'OFF karne par users payment submit nahi kar paayenge.', ps.paymentAutomationEnabled !== false)}
                ${boolRow('pay-require-utr', 'Require UTR', 'UTR blank ho to payment high-risk/blocked mark hoga.', ps.requireUtr !== false)}
                ${boolRow('pay-dup-block', 'Duplicate UTR Block', 'Same UTR pending/approved ho to auto reject/block.', ps.duplicateUtrBlock !== false)}
                ${boolRow('pay-credit-wallet', 'Approve Credits Wallet', 'Approve hote hi user wallet me amount add hoga.', ps.approveCreditsWallet !== false)}
                ${boolRow('pay-extend-membership', 'Approve Extends Membership', 'Approve prompt ke days se VIP expiry extend hogi.', ps.extendMembershipOnApprove !== false)}
                ${boolRow('pay-private-notify', 'Private WhatsApp Notify', 'Gateway online ho to user ko private status message jayega.', ps.notifyUserPrivate !== false)}
                <div class="grid grid-cols-2 gap-2 mt-3">
                    <div><label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-1 ml-1">Min Amount</label><input id="pay-min-amount" class="native-input py-3 text-sm" type="number" value="${ps.minAmount ?? 1}"></div>
                    <div><label class="block text-[9px] text-[var(--text-muted)] uppercase font-bold mb-1 ml-1">Max Amount</label><input id="pay-max-amount" class="native-input py-3 text-sm" type="number" value="${ps.maxAmount ?? 200000}"></div>
                </div>
                <button onclick="savePaymentSettings()" class="mt-3 w-full bg-[var(--primary)] text-white py-3.5 rounded-xl font-black text-[11px] uppercase active:scale-95"><i class="fas fa-save mr-1"></i> Save Payment Automation</button>`;
        }

        async function savePaymentSettings(){
            const payload = {
                paymentAutomationEnabled: document.getElementById('pay-auto-enabled')?.checked,
                requireUtr: document.getElementById('pay-require-utr')?.checked,
                duplicateUtrBlock: document.getElementById('pay-dup-block')?.checked,
                approveCreditsWallet: document.getElementById('pay-credit-wallet')?.checked,
                extendMembershipOnApprove: document.getElementById('pay-extend-membership')?.checked,
                notifyUserPrivate: document.getElementById('pay-private-notify')?.checked,
                minAmount: parseFloat(document.getElementById('pay-min-amount')?.value || 0),
                maxAmount: parseFloat(document.getElementById('pay-max-amount')?.value || 0)
            };
            try{
                const res = await fetch('/api/payment_settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Save failed');
                appState.paymentSettings = data.paymentSettings;
                showRealNotification('✅ Payment Settings Saved', 'Automation settings update ho gaye.', 'success');
            }catch(e){ showRealNotification('❌ Payment Error', String(e.message || e), 'danger'); }
        }

        function renderAdminPaymentsTab() {
            if(!IS_MASTER) return '';
            const pm = appState.paymentMethods || {};
            const pending = (appState.payments || []).filter(p => p.status === 'pending').length;
            return `<div class="px-3 py-4">
                <p class="sec-header">Payments</p>
                <div class="wallet-hud rounded-2xl mb-3">
                    ${financeStatCard('Pending', pending, 'amber')}
                    ${financeStatCard('Total', (appState.payments || []).length, '')}
                    ${financeStatCard('Approved', (appState.payments||[]).filter(p=>p.status==='approved').length, 'green')}
                    ${financeStatCard('Rejected', (appState.payments||[]).filter(p=>p.status==='rejected').length, 'rose')}
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(0,194,111,0.2); background:rgba(0,194,111,0.04)">
                    <h3 class="text-white font-black text-[13px] mb-3">Payment Methods</h3>
                    <input id="pm-upi" class="native-input py-3 mb-2 text-sm" placeholder="Default UPI ID" value="${pm.upi || ''}">
                    <div class="grid grid-cols-3 gap-2 mb-2"><input id="pm-phonepe-upi" class="native-input py-3 text-[11px]" placeholder="PhonePe" value="${pm.phonepeUpi || ''}"><input id="pm-gpay-upi" class="native-input py-3 text-[11px]" placeholder="GPay" value="${pm.gpayUpi || ''}"><input id="pm-paytm-upi" class="native-input py-3 text-[11px]" placeholder="Paytm" value="${pm.paytmUpi || ''}"></div>
                    <input id="pm-name" class="native-input py-3 mb-2 text-sm" placeholder="Receiver name" value="${pm.name || ((TITAN_APP_CONFIG && TITAN_APP_CONFIG.paymentName) || 'TITAN NOVA')}">
                    <input id="pm-phone" class="native-input py-3 mb-2 text-sm" placeholder="Phone / WhatsApp" value="${pm.phone || ''}">
                    <input type="hidden" id="pm-qr-b64" value="${pm.qr || ''}"><input type="file" id="pm-qr-input" accept="image/*" class="hidden" onchange="handleQRSelect(this)">
                    <div class="grid grid-cols-2 gap-2"><label for="pm-qr-input" class="text-center bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">${pm.qr ? 'QR Uploaded ✓' : 'Upload QR'}</label><button onclick="savePaymentMethods()" class="bg-[var(--green)] text-white py-3 rounded-xl font-black text-[10px] uppercase active:scale-95">Save</button></div>
                </div>
                <div class="native-card p-4 mb-3" style="border-color:rgba(42,171,238,0.2); background:rgba(42,171,238,0.04)">${paymentAutomationSettingsHtml()}</div>
                <div class="native-card p-4 mb-3"><div class="flex items-center justify-between gap-2"><h3 class="text-white font-black text-[13px]">Payment Requests</h3><button onclick="approveSafePayments()" class="bg-[rgba(0,194,111,0.15)] text-[var(--green)] border border-[rgba(0,194,111,0.2)] px-3 py-2 rounded-xl font-bold text-[9px] uppercase active:scale-95">Approve Safe</button></div><div class="flex gap-2 flex-wrap mt-3"><button id="filter-all" onclick="setPaymentFilter('all')" class="pill-btn active">All</button><button id="filter-pending" onclick="setPaymentFilter('pending')" class="pill-btn">Pending</button><button id="filter-approved" onclick="setPaymentFilter('approved')" class="pill-btn">Approved</button><button id="filter-rejected" onclick="setPaymentFilter('rejected')" class="pill-btn">Rejected</button></div></div>
                <div id="admin-payment-list"></div>
            </div>`;
        }
        function renderMembership() {
            if(IS_MASTER) return '';
            const profile = appState.profiles[appState.activeId];
            const pm = appState.paymentMethods || {};
            const expiryDate = profile.expiryDate || '';
            let isActive = false; let daysLeft = 0; let expiryLabel = 'Not Set';
            if (expiryDate) {
                const expObj = new Date(expiryDate);
                const today = new Date(); today.setHours(0,0,0,0); expObj.setHours(0,0,0,0);
                daysLeft = Math.ceil((expObj - today) / (1000*60*60*24));
                isActive = daysLeft > 0;
                expiryLabel = expObj.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
            }

            const makeUpiLink = (plan) => {
                const amt = plan === 'day' ? 500 : plan === 'week' ? 1500 : 4000;
                const note = encodeURIComponent('TITAN NOVA ' + plan.toUpperCase());
                const upi  = encodeURIComponent(pm.upi || 'admin@upi');
                const name = encodeURIComponent(pm.name || 'TITAN NOVA');
                return `upi://pay?pa=${upi}&pn=${name}&am=${amt}&cu=INR&tn=${note}`;
            };

            return `
            <div class="pb-6">
              <div class="mx-3 mt-3 mb-3 rounded-2xl overflow-hidden shadow-xl"
                   style="background:${isActive ? 'linear-gradient(135deg,#00A05E 0%,#1A8FC4 100%)' : 'linear-gradient(135deg,#8B1A1A 0%,#5B21B6 100%)'}">
                <div class="p-5">
                  <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-3">
                      <div class="w-11 h-11 rounded-2xl bg-white/15 flex items-center justify-center backdrop-blur-sm">
                        <i class="fas ${isActive ? 'fa-crown' : 'fa-lock'} text-white text-lg"></i>
                      </div>
                      <div>
                        <p class="text-white/60 text-[10px] font-bold uppercase tracking-widest">Membership</p>
                        <p class="text-white font-black text-base tracking-tight leading-tight">${profile.name}</p>
                      </div>
                    </div>
                    <span class="bg-white/20 text-white text-[10px] font-black px-3 py-1 rounded-full backdrop-blur-sm uppercase tracking-wider">
                      ${isActive ? '✓ ACTIVE' : '✗ EXPIRED'}
                    </span>
                  </div>
                  <div class="grid grid-cols-2 gap-3">
                    <div class="bg-white/10 rounded-xl p-3 backdrop-blur-sm border border-white/10">
                      <p class="text-white/60 text-[9px] font-black uppercase mb-1">Expiry Date</p>
                      <p class="text-white font-black text-sm">${expiryLabel}</p>
                    </div>
                    <div class="bg-white/10 rounded-xl p-3 backdrop-blur-sm border border-white/10">
                      <p class="text-white/60 text-[9px] font-black uppercase mb-1">Days Left</p>
                      <p class="text-white font-black text-sm">${expiryDate ? (isActive ? daysLeft + ' Days' : 'Expired') : '---'}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div class="px-3 mb-3">
                <p class="sec-header">Plan Chunein</p>
                <div class="grid grid-cols-3 gap-2.5" id="plan-grid">
                  ${[
                    {id:'day',   label:'1 Din',  price:'₹500',  icon:'fa-sun',      grad:'linear-gradient(135deg,#FAC748,#EF4444)'},
                    {id:'week',  label:'Weekly',  price:'₹1500', icon:'fa-calendar-week', grad:'linear-gradient(135deg,#2AABEE,#3B82F6)'},
                    {id:'month', label:'Monthly', price:'₹4000', icon:'fa-gem',      grad:'linear-gradient(135deg,#7B8FFF,#EC4899)'},
                  ].map(p => `
                  <div class="rounded-2xl p-[1.5px] cursor-pointer plan-wrap" data-plan="${p.id}"
                       onclick="selectPlan('${p.id}')"
                       style="background:var(--surface-light)">
                    <div class="plan-inner bg-[var(--surface)] rounded-[15px] p-3 flex flex-col items-center gap-2">
                      <div class="w-10 h-10 rounded-xl flex items-center justify-center" style="background:${p.grad}">
                        <i class="fas ${p.icon} text-white text-sm"></i>
                      </div>
                      <p class="text-white font-black text-[11px] text-center leading-tight">${p.label}</p>
                      <p class="font-black text-[13px]" style="background:${p.grad};-webkit-background-clip:text;-webkit-text-fill-color:transparent">${p.price}</p>
                    </div>
                  </div>`).join('')}
                </div>
              </div>

              <div class="px-3 mb-3">
                <p class="sec-header">Plan Chunein, Phir Pay Karein</p>
                <div class="grid grid-cols-3 gap-2.5">
                  ${[
                    {id:'phonepe', label:'PhonePe', upi:titanUpiFor('phonepe'), icon:'https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/PhonePe_Logo.svg/2560px-PhonePe_Logo.svg.png',  color:'#6F3FFF'},
                    {id:'gpay',    label:'GPay',    upi:titanUpiFor('gpay'),    icon:'https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Google_Pay_Logo.svg/2560px-Google_Pay_Logo.svg.png', color:'#4285F4'},
                    {id:'paytm',   label:'Paytm',   upi:titanUpiFor('paytm'),   icon:'https://upload.wikimedia.org/wikipedia/commons/4/42/Paytm_logo.png',                                         color:'#00BAF2'},
                  ].filter(app => app.upi).map(app => `
                  <button onclick="openUPIApp('${app.id}')"
                    class="flex flex-col items-center gap-2 py-4 px-2 rounded-2xl border border-[var(--border)] bg-[var(--surface-light)] active:scale-95 transition-transform"
                    style="border-color:${app.color}30">
                    <div class="w-10 h-10 rounded-xl flex items-center justify-center" style="background:${app.color}20">
                      <img src="${app.icon}" class="h-6 object-contain" onerror="this.style.display='none'" />
                    </div>
                    <span class="text-[11px] font-black text-white">${app.label}</span>
                    <span class="text-[8px] font-bold text-[var(--text-muted)] truncate w-full text-center px-1">${app.upi}</span>
                  </button>`).join('')}
                </div>
                <p class="text-[9px] text-[var(--text-muted)] text-center mt-2 font-bold">Upar se apna app choose karein — amount auto-fill hoga, sirf PIN dalein</p>

                <div class="mt-3 space-y-2">
                  ${[
                    {label:'PhonePe UPI', upi:titanUpiFor('phonepe'), color:'#6F3FFF'},
                    {label:'GPay UPI',    upi:titanUpiFor('gpay'), color:'#4285F4'},
                    {label:'Paytm UPI',  upi:titanUpiFor('paytm'), color:'#00BAF2'},
                  ].filter(u => u.upi).map(u => `
                  <div class="flex items-center gap-3 bg-[var(--surface-light)] border border-[var(--border)] rounded-2xl p-3">
                    <div class="flex-1 min-w-0">
                      <p class="text-[9px] font-bold uppercase mb-0.5" style="color:${u.color}">${u.label}</p>
                      <p class="text-white font-black text-sm truncate">${u.upi}</p>
                    </div>
                    <button onclick="navigator.clipboard.writeText('${u.upi}').then(()=>showRealNotification('UPI Copied!','${u.upi} copy ho gaya','success'))"
                      class="shrink-0 text-white px-3 py-2 rounded-xl font-bold text-[10px] uppercase active:scale-95"
                      style="background:${u.color}">Copy</button>
                  </div>`).join('')}
                </div>

                ${pm.phone ? `
                <div class="mt-2 flex items-center gap-3 bg-[var(--surface-light)] border border-[var(--border)] rounded-2xl p-3">
                  <div class="flex-1">
                    <p class="text-[9px] text-[var(--text-muted)] font-bold uppercase mb-0.5">Phone Number</p>
                    <p class="text-white font-black text-sm">${pm.phone}</p>
                  </div>
                  <button onclick="navigator.clipboard.writeText('${pm.phone}').then(()=>showRealNotification('Number Copied!','Clipboard pe copy ho gaya.','success'))"
                    class="bg-[var(--green)] text-white px-4 py-2 rounded-xl font-bold text-[11px] uppercase active:scale-95">
                    Copy
                  </button>
                </div>` : ''}

                ${pm.qr ? `
                <div class="mt-3 bg-white rounded-2xl p-3 flex items-center justify-center">
                  <img src="${pm.qr}" class="w-48 h-48 object-contain" />
                </div>` : ''}
              </div>

              <div class="px-3 mb-3">
                <p class="sec-header">Payment Proof Submit</p>
                <div class="native-card p-4">
                  <div class="relative mb-3">
                    <div class="absolute left-3 top-1/2 -translate-y-1/2 w-7 h-7 bg-[var(--primary-glow)] rounded-lg flex items-center justify-center">
                      <i class="fas fa-rupee-sign text-[var(--primary)] text-xs"></i>
                    </div>
                    <input id="pay-amount" type="number" inputmode="numeric" placeholder="Amount ₹"
                      class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-white font-bold rounded-2xl pl-11 pr-4 py-3.5 outline-none text-sm focus:border-[var(--primary)] transition-colors">
                  </div>
                  <div class="relative mb-3">
                    <div class="absolute left-3 top-1/2 -translate-y-1/2 w-7 h-7 bg-[rgba(42,171,238,0.12)] rounded-lg flex items-center justify-center">
                      <i class="fas fa-hashtag text-[var(--primary)] text-xs"></i>
                    </div>
                    <input id="pay-utr" type="text" placeholder="UTR / Transaction ID"
                      class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-white font-bold rounded-2xl pl-11 pr-4 py-3.5 outline-none text-sm focus:border-[var(--primary)] transition-colors">
                  </div>
                  <label for="pay-image"
                    class="flex items-center gap-3 bg-[var(--surface-light)] border border-dashed border-[var(--surface-mid)] rounded-2xl p-3.5 mb-4 cursor-pointer active:scale-98 transition-transform">
                    <div class="w-9 h-9 bg-[rgba(123,143,255,0.12)] rounded-xl flex items-center justify-center shrink-0">
                      <i class="fas fa-camera text-[var(--purple)] text-base"></i>
                    </div>
                    <p class="text-[var(--text-muted)] text-sm font-bold" id="pay-file-label">Screenshot Upload Karein</p>
                    <i class="fas fa-chevron-right text-[var(--text-muted)] ml-auto text-xs"></i>
                  </label>
                  <input type="file" id="pay-image" accept="image/*" class="hidden"
                    onchange="document.getElementById('pay-file-label').textContent = this.files[0]?.name || 'Screenshot Upload Karein'">
                  <button id="pay-submit-btn" onclick="submitPayment()"
                    class="w-full py-4 rounded-2xl font-black text-[13px] uppercase tracking-wide text-white active:scale-95 transition-transform"
                    style="background:linear-gradient(135deg,var(--green),var(--green-dark));box-shadow:0 6px 20px rgba(0,194,111,0.3)">
                    <i class="fas fa-upload mr-2"></i> Payment Submit Karein
                  </button>
                </div>
              </div>

              <div class="px-3 mb-3">
                <p class="sec-header">Payment History</p>
                <div id="payment-list">
                  <div class="flex items-center justify-center py-8">
                    <i class="fas fa-spinner fa-spin text-[var(--text-muted)] text-xl"></i>
                  </div>
                </div>
              </div>

            </div>`;
        }

        function copyText(text, btn) {
            if(navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(() => {
                    const o = btn.innerHTML; btn.innerHTML = '<i class="fas fa-check mr-1"></i>Copied';
                    setTimeout(() => btn.innerHTML = o, 2000);
                });
            } else {
                let t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.left = '-999999px'; document.body.appendChild(t); t.focus(); t.select();
                try { document.execCommand('copy'); const o = btn.innerHTML; btn.innerHTML = '<i class="fas fa-check mr-1"></i>Copied'; setTimeout(() => btn.innerHTML = o, 2000); } catch(e) {}
                t.remove();
            }
        }

        let _selectedPlan = 'week';
        function selectPlan(plan) {
            _selectedPlan = plan;
            document.querySelectorAll('.plan-wrap').forEach(el => {
                const isSelected = el.dataset.plan === plan;
                const grads = {
                    day:'linear-gradient(135deg,#FAC748,#EF4444)',
                    week:'linear-gradient(135deg,#2AABEE,#3B82F6)',
                    month:'linear-gradient(135deg,#7B8FFF,#EC4899)'
                };
                if (isSelected) {
                    el.style.background = grads[plan];
                    el.querySelector('.plan-inner').style.background = 'rgba(0,0,0,0.5)';
                } else {
                    el.style.background = 'var(--surface-light)';
                    el.querySelector('.plan-inner').style.background = 'var(--surface)';
                }
            });
            const amts = {day:500, week:1500, month:4000};
            const amtEl = document.getElementById('pay-amount');
            if (amtEl) amtEl.value = amts[plan];
        }

        function openUPIApp(appId) {
            const amts = {day:500, week:1500, month:4000};
            const amt = amts[_selectedPlan] || 1500;

            // Use hardcoded per-app UPI ID
            const upi  = titanUpiFor(appId);
            const name = titanPaymentName();
            if(!upi){ showRealNotification('⚠️ UPI Missing', 'Admin payment UPI setup nahi hai.', 'danger'); return; }
            const note = 'TITAN NOVA ' + _selectedPlan.toUpperCase();

            const pa = encodeURIComponent(upi);
            const pn = encodeURIComponent(name);
            const tn = encodeURIComponent(note);

            // Pre-fill amount field
            const amtEl = document.getElementById('pay-amount');
            if (amtEl) amtEl.value = amt;

            const deepLinks = {
                gpay:    `tez://upi/pay?pa=${pa}&pn=${pn}&am=${amt}&cu=INR&tn=${tn}`,
                phonepe: `phonepe://pay?pa=${pa}&pn=${pn}&am=${amt}&cu=INR&tn=${tn}`,
                paytm:   `paytmmp://pay?pa=${pa}&pn=${pn}&am=${amt}&cu=INR&tn=${tn}`,
            };
            const genericUpi = `upi://pay?pa=${pa}&pn=${pn}&am=${amt}&cu=INR&tn=${tn}`;
            const link = deepLinks[appId] || genericUpi;

            let a = document.createElement('a');
            a.href = link;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // Fallback to generic UPI after 1.5s if app didn't open
            setTimeout(() => {
                let b = document.createElement('a');
                b.href = genericUpi;
                document.body.appendChild(b);
                b.click();
                document.body.removeChild(b);
            }, 1500);
        }

        async function submitPayment() {
            const amount = document.getElementById('pay-amount').value;
            const utr    = document.getElementById('pay-utr').value;
            const fileInput = document.getElementById('pay-image');
            const submitBtn = document.getElementById('pay-submit-btn');

            if (!amount || !utr) { showRealNotification('⚠️ Error', 'Amount aur UTR zaroor daalein', 'danger'); return; }

            const originalBtnText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Uploading...';
            submitBtn.disabled = true;

            try {
                let imageUrl = '';
                if (fileInput && fileInput.files[0]) {
                    imageUrl = await titanUploadImage(fileInput.files[0]);
                }

                await sendPayment(amount, utr, imageUrl);
            } catch(error) {
                showRealNotification('❌ Upload Failed', error.message, 'danger');
            } finally {
                submitBtn.innerHTML = originalBtnText;
                submitBtn.disabled = false;
            }
        }

        async function sendPayment(amount, utr, image) {
            const profile = appState.profiles[appState.activeId];
            const planLabels = {day:'1 Din - ₹500', week:'Weekly - ₹1500', month:'Monthly - ₹4000'};
            try {
                const res = await fetch('/api/submit_payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        userId: appState.activeId,
                        userName: profile.name,
                        amount: amount,
                        utr: utr,
                        image: image,
                        planLabel: planLabels[_selectedPlan] || _selectedPlan
                    })
                });
                const data = await res.json();
                const flagMessages = {
                    duplicate:  '⚠️ Duplicate UTR detected',
                    spam:       '⚠️ Multiple requests flagged',
                    low_amount: '⚠️ Amount too low',
                    high_amount:'⚠️ Amount too high',
                    utr_missing:'⚠️ UTR missing',
                    safe:       '✅ Payment submitted successfully'
                };
                const flagTypes = { duplicate: 'danger', spam: 'danger', low_amount: 'danger', high_amount:'danger', utr_missing:'danger', safe: 'success' };
                showRealNotification(flagMessages[data.flag] || '✅ Submitted', 'Admin jald verify karenge.', flagTypes[data.flag] || 'success');
                document.getElementById('pay-amount').value = '';
                document.getElementById('pay-utr').value = '';
                document.getElementById('pay-file-label').textContent = 'Screenshot Upload Karein';
                try {
                    const stateRes = await fetch('/api/state');
                    const newState = await stateRes.json();
                    appState.payments = (newState.payments || []).filter(p => p.userId === appState.activeId);
                } catch(e) {}
                loadPayments();
            } catch(e) { showRealNotification('❌ Network Error', 'Dobara try karein.', 'danger'); }
        }

        function loadPayments() {
            const container = document.getElementById('payment-list');
            if (!container) return;
            container.innerHTML = '';
            const payments = appState.payments || [];
            if (payments.length === 0) {
                container.innerHTML = '<p class="text-[var(--text-muted)] text-xs text-center py-4">Koi payment history nahi hai</p>';
                return;
            }
            payments.slice().reverse().forEach(p => {
                let color = 'text-[var(--amber)]';
                if (p.status === 'approved') color = 'text-[var(--green)]';
                if (p.status === 'rejected') color = 'text-[var(--rose)]';
                container.innerHTML += `
                <div class="native-card p-3 mb-2">
                    <div class="flex justify-between">
                        <span class="font-black text-white">₹${p.amount}</span>
                        <span class="${color} text-xs font-black uppercase">${p.status}</span>
                    </div>
                    <div class="text-xs text-[var(--text-muted)] mt-1">UTR: ${p.utr || '-'}</div>
                    <div class="text-[10px] text-[var(--text-muted)]">${p.time}</div>
                </div>`;
            });
        }

        let paymentFilter = 'all';

        function setPaymentFilter(type) {
            paymentFilter = type;
            document.querySelectorAll('.pill-btn').forEach(el => el.classList.remove('active'));
            const btn = document.getElementById('filter-' + type);
            if (btn) btn.classList.add('active');
            renderAdminPayments();
        }

        function renderAdminPayments() {
            const container = document.getElementById('admin-payment-list');
            if (!container) return;
            container.innerHTML = '';

            let payments = (appState.payments || []).slice();
            if (paymentFilter !== 'all') payments = payments.filter(p => p.status === paymentFilter);
            payments.reverse();

            if (payments.length === 0) {
                container.innerHTML = '<div class="text-center text-[var(--text-muted)] text-xs py-6 native-card"><i class="fas fa-inbox text-2xl mb-2 block opacity-30"></i>Koi payment nahi mili</div>';
                return;
            }

            payments.forEach(p => {
                let flagColor = 'text-[var(--text-muted)]';
                const flagText = p.autoFlag || 'safe';
                if (flagText === 'safe')      flagColor = 'text-[var(--green)]';
                if (flagText === 'duplicate') flagColor = 'text-[var(--rose)]';
                if (flagText === 'spam')      flagColor = 'text-[var(--amber)]';
                if (flagText === 'low_amount') flagColor = 'text-orange-400';

                let statusColor = 'text-[var(--amber)]';
                if (p.status === 'approved') statusColor = 'text-[var(--green)]';
                if (p.status === 'rejected') statusColor = 'text-[var(--rose)]';

                container.innerHTML += `
                <div class="native-card p-4 mb-2">
                    <div class="flex justify-between items-start mb-3">
                        <div>
                            <h3 class="font-black text-white uppercase text-[13px]">${p.userName}</h3>
                            <p class="text-xs text-[var(--text-muted)] mt-0.5">${p.time}</p>
                        </div>
                        <span class="${statusColor} text-xs font-black uppercase">${p.status}</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 mb-3">
                        <div class="bg-[var(--surface-light)] p-2.5 rounded-xl border border-[var(--border)]">
                            <p class="stat-lbl mb-0.5">Amount</p>
                            <p class="font-black text-white text-[13px]">₹${p.amount}</p>
                        </div>
                        <div class="bg-[var(--surface-light)] p-2.5 rounded-xl border border-[var(--border)]">
                            <p class="stat-lbl mb-0.5">UTR</p>
                            <p class="font-black text-white text-[11px] break-all">${p.utr || '-'}</p>
                        </div>
                    </div>
                    <div class="mb-3 flex flex-wrap gap-2 items-center">
                        <span class="${flagColor} text-[10px] font-black uppercase">⚡ ${flagText.toUpperCase()}</span>
                        ${p.riskLevel ? `<span class="text-[10px] font-black uppercase text-[var(--purple)]">🛡️ ${p.riskLevel}</span>` : ''}
                        ${p.walletCredited ? `<span class="text-[10px] font-black uppercase text-[var(--green)]">💳 WALLET +₹${p.walletCreditAmount || p.amount}</span>` : ''}
                    </div>
                    ${p.rejectReason ? `<div class="mb-3 bg-[rgba(255,93,93,0.08)] border border-[rgba(255,93,93,0.18)] rounded-xl p-2 text-[10px] text-[var(--rose)] font-bold">Reason: ${p.rejectReason}</div>` : ''}
                    ${p.image ? `<img src="${p.image}" class="w-full rounded-xl mb-3 border border-[var(--border)] max-h-48 object-contain"/>` : ''}
                    ${p.status === 'pending' ? `
                    <div class="flex gap-2">
                        <button onclick="approvePayment('${p.id}')" class="flex-1 bg-[var(--green)] text-white py-2.5 rounded-xl font-black text-xs active:scale-95">Approve</button>
                        <button onclick="rejectPayment('${p.id}')" class="flex-1 bg-[var(--rose)] text-white py-2.5 rounded-xl font-black text-xs active:scale-95">Reject</button>
                    </div>` : ''}
                </div>`;
            });
        }

        async function approvePayment(id) {
            const ps = appState.paymentSettings || {};
            const defaultDays = ps.extendMembershipOnApprove === false ? '0' : '30';
            const days = prompt('Kitne din membership extend karna hai? Wallet only ke liye 0 daalo.', defaultDays);
            if (days === null) return;
            const creditWallet = confirm('Is payment amount ko user wallet me credit karna hai? OK = Yes, Cancel = No');
            try {
                const res = await fetch('/api/approve_payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({paymentId: id, days: parseInt(days || '0'), creditWallet, extendMembership: ps.extendMembershipOnApprove !== false})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Approve failed');
                if(data.wallets) appState.wallets = data.wallets;
                showRealNotification('✅ Approved!', creditWallet ? 'Wallet credit + payment approve complete.' : 'Payment approve complete.', 'success');
                await refreshPayments();
            } catch(e) { showRealNotification('❌ Approve Failed', String(e.message || e), 'danger'); }
        }

        async function rejectPayment(id) {
            const reason = prompt('Reject reason?', 'UTR/payment proof verify nahi hua');
            if (reason === null) return;
            try {
                const res = await fetch('/api/reject_payment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({paymentId: id, reason})
                });
                const data = await res.json();
                if(data.status !== 'success') throw new Error(data.message || 'Reject failed');
                showRealNotification('❌ Rejected', 'Payment reject kar di gayi.', 'danger');
                await refreshPayments();
            } catch(e) { showRealNotification('❌ Reject Failed', String(e.message || e), 'danger'); }
        }

        async function approveSafePayments() {
            const payments = appState.payments || [];
            let count = 0;
            for (const p of payments) {
                if (p.status === 'pending' && p.autoFlag === 'safe') {
                    const res = await fetch('/api/approve_payment', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({paymentId: p.id, days: 0, creditWallet: true, extendMembership: false})
                    });
                    const data = await res.json();
                    if(data.status === 'success') count++;
                }
            }
            if (count > 0) showRealNotification('✅ Approved!', `${count} safe payment(s) wallet me credit kar di gayi.`, 'success');
            else showRealNotification('ℹ️ None Found', 'Koi safe pending payment nahi mili.', 'info');
            await refreshPayments();
        }

        async function refreshPayments() {
            try {
                const res = await fetch('/api/state');
                const newState = await res.json();
                appState = newState;
                state = appState.profiles[appState.activeId];
                renderAdminPayments();
            } catch(e) {}
        }

        async function savePaymentMethods() {
            const upi = document.getElementById('pm-upi').value.trim();
            const phonepeUpi = document.getElementById('pm-phonepe-upi')?.value.trim() || '';
            const gpayUpi = document.getElementById('pm-gpay-upi')?.value.trim() || '';
            const paytmUpi = document.getElementById('pm-paytm-upi')?.value.trim() || '';
            const name = document.getElementById('pm-name')?.value.trim() || ((TITAN_APP_CONFIG && TITAN_APP_CONFIG.paymentName) || 'TITAN NOVA');
            const phone = document.getElementById('pm-phone').value.trim();
            const qr = document.getElementById('pm-qr-b64').value.trim();
            try {
                await fetch('/api/save_payment_methods', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({upi, phonepeUpi, gpayUpi, paytmUpi, name, phone, qr}) });
                showRealNotification('✅ Saved!', 'Payment methods update ho gaye.', 'success');
                await refreshMasterState();
            } catch(e) { showRealNotification('❌ Error', 'Save nahi ho saka.', 'danger'); }
        }

        async function scrapeMarket(type, i, marketName, marketKey=null) {
            const op = resolveLedgerAction(type, i, marketKey);
            if(op.idx < 0) return showRealNotification('⚠️ Ledger Error', 'Card mapping nahi mila. Refresh karke try karo.', 'danger');
            const arr = ledgerArrayForType(type) || [];
            const visibleMarket = (arr[op.idx] && arr[op.idx].n) || marketName || '';
            let field = 'open';
            let baseName = visibleMarket;
            if (visibleMarket.endsWith(' OPEN')) {
                field = 'open';
                baseName = visibleMarket.replace(/ OPEN$/, '').trim();
            } else if (visibleMarket.endsWith(' CLOSE')) {
                field = 'close';
                baseName = visibleMarket.replace(/ CLOSE$/, '').trim();
            } else if (type === 'jodi') {
                field = 'jodi';
                baseName = visibleMarket.trim();
            }

            const btn = document.getElementById(`scrape-btn-${type}-${op.idx}`) || document.getElementById(`scrape-btn-${type}-${i}`);
            const origHTML = btn ? btn.innerHTML : '';
            if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }

            try {
                const res = await fetch('/api/scrape_market', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({market: baseName})
                });
                const data = await res.json();

                if (data.status === 'success') {
                    const digits = field === 'open' ? data.open : (field === 'close' ? data.close : data.jodi);
                    const inp = document.getElementById(`in-d-${type}-${op.idx}`) || document.getElementById(`in-d-${type}-${i}`);
                    if (inp) {
                        inp.value = digits;
                        updateMarket(type, op.idx, 'd', digits, op.key, 'scrape_digits');
                    }
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-check"></i> Done';
                        setTimeout(() => { if (btn) btn.innerHTML = origHTML; }, 3000);
                    }
                } else {
                    showRealNotification('⚠️ Scraping Error', data.message || 'Unknown error', 'danger');
                    if (btn) btn.innerHTML = origHTML;
                }
            } catch(e) {
                showRealNotification('❌ Network Error', 'Server se connect nahi ho pa raha.', 'danger');
                if (btn) btn.innerHTML = origHTML;
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function saveExpiryDate(userId) {
            const expEl = document.getElementById('exp-' + userId);
            if (!expEl) return;
            const expiry = expEl.value;
            if (!expiry) return showRealNotification('⚠️ Error', 'Date select karein!', 'danger');
            try {
                await fetch('/api/set_expiry', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({userId, expiryDate: expiry}) });
                showRealNotification('✅ Expiry Set!', 'Membership expiry date update ho gayi.', 'success');
                await refreshMasterState();
                render(true);
            } catch(e) { showRealNotification('❌ Error', 'Save nahi ho saka.', 'danger'); }
        }

        async function refreshMasterState() {
            try {
                const res = await fetch('/api/state');
                const newState = await res.json();
                appState = newState;
                state = appState.profiles[appState.activeId];
            } catch(e) {}
        }

        async function handleQRSelect(input) {
            if (!input.files || !input.files[0]) return;

            const file = input.files[0];
            const label = document.getElementById('pm-qr-label');
            const originalText = label.textContent;
            label.textContent = "Uploading QR... ⏳";

            try {
                const downloadURL = await titanUploadImage(file);
                document.getElementById('pm-qr-b64').value = downloadURL;
                label.textContent = "QR Uploaded ✓";
                document.getElementById('pm-qr-preview').src = downloadURL;
                document.getElementById('pm-qr-preview').classList.remove('hidden');
            } catch(error) {
                showRealNotification('❌ QR Upload Failed', error.message, 'danger');
                label.textContent = originalText;
            }
        }

        function approveVipProfile(pid) {
            const p = appState.profiles[pid];
            if(!p) return;
            p.approvalStatus = 'approved';
            p.approvedAt = new Date().toISOString();
            p.approvedBy = appState.activeId || 'admin1';
            p.vipAccessEnabled = true;
            p.autoCreated = !!p.autoCreated;
            if(!appState.wallets) appState.wallets = {};
            if(!appState.wallets[pid]) appState.wallets[pid] = {userId:pid, name:p.name || pid, phone:p.phone || '', balance:0, creditLimit:Number(appState.walletSettings?.defaultCreditLimit || 0), ledger:[], createdAt:new Date().toISOString(), updatedAt:new Date().toISOString()};
            autoSave(); render(true);
            showRealNotification('✅ VIP Approved', `${p.name || pid} ab entry bhej sakta hai.`, 'success');
        }

        function rejectVipProfile(pid) {
            const p = appState.profiles[pid];
            if(!p) return;
            if(!confirm(`${p.name || pid} ka pending profile reject/delete karna hai?`)) return;
            delete appState.profiles[pid];
            if(appState.wallets) delete appState.wallets[pid];
            autoSave(); render(true);
            showRealNotification('🗑️ Profile Rejected', 'Pending profile delete ho gaya.', 'danger');
        }

        function toggleVipAccess(pid, enabled) {
            if(!appState.profiles[pid]) return;
            if(String(appState.profiles[pid].approvalStatus || '').toLowerCase() === 'pending') {
                showRealNotification('⚠️ Approval Required', 'Pehle profile approve karo.', 'danger');
                render(true);
                return;
            }
            appState.profiles[pid].vipAccessEnabled = enabled;
            autoSave();
            showRealNotification(enabled ? '✅ Access Enabled' : '🔒 Access Disabled',
                `${appState.profiles[pid].name} ka app access ${enabled ? 'enable' : 'disable'} kar diya gaya.`,
                enabled ? 'success' : 'danger');
        }

        function toggleAllMarketsOpenClose(trackDict, isChecked) {
            ensureDataStruct();
            baseMarkets.forEach(bm => {
                if(bm && bm.hiddenForLedger) return;
                state.dayRecords[currentDate][trackDict][bm.n + ' OPEN']  = isChecked;
                state.dayRecords[currentDate][trackDict][bm.n + ' CLOSE'] = isChecked;
            });
            titanSaveAdminSettingsNow();
            render(true);
        }

        function sendBroadcast() {
            let t = document.getElementById('bcast-title').value.trim();
            let m = document.getElementById('bcast-msg').value.trim();
            if(!t || !m) return showRealNotification('⚠️ Error', 'Title aur Message dono likhna zaroori hai!', 'danger');

            if(!appState.broadcasts) appState.broadcasts = [];
            appState.broadcasts.push({id: Date.now(), title: t, msg: m});

            saveMaster(true);
            document.getElementById('bcast-title').value = '';
            document.getElementById('bcast-msg').value = '';

            showRealNotification('✅ Broadcast Sent!', 'Aapka message sabhi online VIPs ko bhej diya gaya hai.', 'success');
        }

        function render(keepScroll = true) {
            // v47: never rebuild the screen while mobile keyboard input is active.
            // Rebuilding innerHTML destroys the focused input and Android closes the keyboard.
            if(keepScroll !== false && titanTypingActive()) {
                titanQueueRenderAfterTyping(keepScroll);
                return;
            }
            syncTodayIfNotManual();
            const currentScroll = window.scrollY || document.documentElement.scrollTop;

            refreshMarketArrays();
            ensureDataStruct();
            runLiveSync();

            renderAppBar();
            renderBottomNav();

            const sidebarContainer = document.getElementById('sidebar-links-container');
            if (sidebarContainer && sidebarContainer.innerHTML.trim() === '') {
                sidebarContainer.innerHTML = chartLinks.map(link =>
                    `<a href="${link.l}" target="_blank" class="side-link-btn active:scale-95 transition-transform">${link.n}</a>`
                ).join('');
            }

            const container = document.getElementById('screen-content');
            container.innerHTML = '';

            // User screen unlocked based on request

            if(mainNav === 'ledger') {
                container.innerHTML = renderSubTabs() + renderWalletHUD();
                container.appendChild(createLedgerList(activeTab, (activeTab==='jodi'?baseMarkets:markets), (activeTab==='ank'?'data':(activeTab==='jodi'?'jodiData':'pannelData'))));
            }
            else if(mainNav === 'audit') { container.innerHTML = renderWeeklyReport(); }
            else if(mainNav === 'smart' && IS_MASTER) { container.innerHTML = renderSmartAI(); }
            else if(mainNav === 'clients' && IS_MASTER) { container.innerHTML = renderClients(); }
            else if(mainNav === 'finance' && IS_MASTER) { container.innerHTML = renderFinanceTab(); }
            else if(mainNav === 'wallets' && IS_MASTER) { financeSubTab = 'wallets'; mainNav = 'finance'; container.innerHTML = renderFinanceTab(); }
            else if(mainNav === 'withdrawals' && IS_MASTER) { financeSubTab = 'withdrawals'; mainNav = 'finance'; container.innerHTML = renderFinanceTab(); }
            else if(mainNav === 'payments' && IS_MASTER) { financeSubTab = 'payments'; mainNav = 'finance'; container.innerHTML = renderFinanceTab(); }
            else if(mainNav === 'entries' && IS_MASTER) { container.innerHTML = renderEntriesTab(); }
            else if(mainNav === 'results' && IS_MASTER) { container.innerHTML = renderResultsTab(); }
            else if(mainNav === 'markets' && IS_MASTER) { try { container.innerHTML = renderMarketManagerTab(); } catch(e) { container.innerHTML = `<div class="px-3 py-4"><p class="sec-header">Market Manager</p><div class="native-card p-4 text-[var(--rose)] text-xs"><b>Market tab error:</b> ${htmlEscape(e.message || e)}<br><button onclick="reloadMarketRegistry()" class="mt-3 bg-[var(--primary)] text-white px-4 py-2 rounded-xl font-black text-[10px] uppercase">Reload Market</button></div></div>`; } }
            else if(mainNav === 'forward' && IS_MASTER) { container.innerHTML = renderForwarderTab(); }
            else if(mainNav === 'guard' && IS_MASTER) { container.innerHTML = renderGuardTab(); }
            else if(mainNav === 'backup' && IS_MASTER) { container.innerHTML = renderBackupAuditTab(); }
            else if(mainNav === 'health' && IS_MASTER) { container.innerHTML = renderHealthMonitorTab(); if(!appState.healthMonitor) refreshHealthMonitor(); }
            else if(mainNav === 'setup' && IS_MASTER) { container.innerHTML = renderSetupTab(); if(!appState.healthMonitor) refreshHealthMonitor(); }
            else if(mainNav === 'settings' && IS_MASTER) { mainNav = 'setup'; container.innerHTML = renderSetupTab(); if(!appState.healthMonitor) refreshHealthMonitor(); }
            else if(mainNav === 'settings' && !IS_MASTER) { container.innerHTML = renderVipSettings(); }
            else if(mainNav === 'membership' && !IS_MASTER) { container.innerHTML = renderMembership(); setTimeout(() => { selectPlan(_selectedPlan); loadPayments(); }, 100); }

            // v26 Lite: pro panel auto-load removed.

            if(keepScroll) {
                setTimeout(() => window.scrollTo(0, currentScroll), 10);
            } else {
                setTimeout(() => window.scrollTo(0, 0), 10);
            }
        }

        function processSmartPaste(targetType) {
            if(!IS_MASTER) return;
            ensureDataStruct();
            const textRaw = document.getElementById('smart-text-input').value;
            if(!textRaw.trim()) return showRealNotification('⚠️ Error', 'Paste input message!', 'danger');
            const lines = textRaw.toUpperCase().replace(/[^\\w\\s,:;|\\-⬆️⬇️₹]/g, ' ').split('\\n');
            let currentBaseMarket = ''; let currentPhase = 'OPEN'; let updatesCount = 0; let updatedCards = [];
            const sortedMarkets = [...baseMarkets].sort((a, b) => b.n.length - a.n.length);
            const targetDict = targetType === 'ank' ? 'data' : (targetType === 'jodi' ? 'jodiData' : 'pannelData');
            const targetArr = targetType === 'jodi' ? baseMarkets : markets;

            lines.forEach(line => {
                let foundMarket = '';
                for(let bm of sortedMarkets) { if(line.includes(bm.n)) { foundMarket = bm.n; break; } }
                if(!foundMarket) {
                    if(line.includes('SRIDEVI') || line.includes('SRIDEV')) foundMarket = 'SRIDEV DAY';
                    else if(line.includes('MADHUR')) foundMarket = 'MADHUR DAY';
                    else if(line.includes('MILAN')) foundMarket = 'MILAN DAY';
                    else if(line.includes('RAJDHANI')) foundMarket = 'RAJDHANI DAY';
                    else if(line.includes('SUPREME')) foundMarket = 'SUPREME DAY';
                    else if(line.includes('KALYAN')) foundMarket = 'KALYAN';
                    else if(line.includes('TIME')) foundMarket = 'TIME BAZAR';
                    else if(line.includes('MAIN BAZAR')) foundMarket = 'MAIN BAZAR';
                }
                if (foundMarket) { currentBaseMarket = foundMarket; currentPhase = 'OPEN'; }
                if (currentBaseMarket) {
                    if (line.includes('NIGHT') || line.includes('NIT') || line.includes('NITE')) {
                        if (currentBaseMarket.includes('SRIDEV')) currentBaseMarket = 'SRIDEVI NIGHT'; else if (currentBaseMarket === 'KALYAN') currentBaseMarket = 'KALYAN NIGHT'; else if (currentBaseMarket.includes('MADHUR')) currentBaseMarket = 'MADHUR NIGHT'; else if (currentBaseMarket.includes('MILAN')) currentBaseMarket = 'MILAN NIGHT'; else if (currentBaseMarket.includes('RAJDHANI')) currentBaseMarket = 'RAJDHANI NIGHT'; else if (currentBaseMarket.includes('SUPREME')) currentBaseMarket = 'SUPREME NIGHT';
                    } else if (line.includes('DAY') || line.includes('MORNING')) {
                        if (currentBaseMarket.includes('SRIDEVI NIGHT')) currentBaseMarket = 'SRIDEV DAY'; else if (currentBaseMarket === 'KALYAN NIGHT') currentBaseMarket = 'KALYAN'; else if (currentBaseMarket.includes('MADHUR NIGHT')) currentBaseMarket = 'MADHUR DAY'; else if (currentBaseMarket.includes('MILAN NIGHT')) currentBaseMarket = 'MILAN DAY'; else if (currentBaseMarket.includes('RAJDHANI NIGHT')) currentBaseMarket = 'RAJDHANI DAY'; else if (currentBaseMarket.includes('SUPREME NIGHT')) currentBaseMarket = 'SUPREME DAY';
                    }
                }
                if (line.includes('CLOSE') || line.includes('⬇️') || line.includes('CL')) { currentPhase = 'CLOSE'; } else if (line.includes('OPEN') || line.includes('⬆️') || line.includes('OP')) { currentPhase = 'OPEN'; }
                if(!currentBaseMarket) return;
                let cleanLine = line.replace(/\\d{1,2}:\\d{2}/g, '').replace(/(RATE|INVEST|RS|₹|PRICE|AMT|AMOUNT|INV|INVESTMENT)[\\s:=]*\\d+/g, '');
                let digitMatches = cleanLine.match(/\\d+/g);
                if(!digitMatches) return;
                let validDigits = [];
                if(targetType === 'ank') validDigits = digitMatches.filter(n => n.length === 1); else if (targetType === 'jodi') validDigits = digitMatches.filter(n => n.length === 2); else if (targetType === 'pannel') validDigits = digitMatches.filter(n => n.length === 3);
                if(validDigits.length === 0) return;
                let extractedDigits = validDigits.join(', ');

                if (targetType === 'jodi') {
                    const idx = targetArr.findIndex(m => m.n === currentBaseMarket);
                    if (idx !== -1) {
                        Object.keys(appState.profiles).forEach(pid => {
                            let pState = appState.profiles[pid]; ensureDataStructForProfile(pState);
                            if(!pState.dayRecords[currentDate][targetDict][idx]) pState.dayRecords[currentDate][targetDict][idx] = { s: 'WAIT', d: '', r: '' };
                            let r = pState.dayRecords[currentDate][targetDict][idx];
                            r.d = extractedDigits;
                            r._digitsTouchedAt = Date.now();
                            r = stampLedgerMutation(r, 'smart_paste_digits');
                            r = titanNormalizeOriginalDigits(r, targetType, extractedDigits, 'smart_paste_digits');
                            r = annotateLedgerRecord(r, targetType, idx, ledgerMarketKeyForCard(targetType, targetArr[idx] || {}));
                            pState.dayRecords[currentDate][targetDict][idx] = r;
                        }); updatedCards.push({type: targetType, idx, key: ledgerMarketKeyForCard(targetType, targetArr[idx] || {})}); updatesCount++;
                    }
                } else {
                    const targetName = currentBaseMarket + " " + currentPhase; const idx = targetArr.findIndex(m => m.n === targetName);
                    if(idx !== -1) {
                        Object.keys(appState.profiles).forEach(pid => {
                            let pState = appState.profiles[pid]; ensureDataStructForProfile(pState);
                            if(!pState.dayRecords[currentDate][targetDict][idx]) pState.dayRecords[currentDate][targetDict][idx] = { s: 'WAIT', d: '', r: '' };
                            let r = pState.dayRecords[currentDate][targetDict][idx];
                            r.d = extractedDigits;
                            r._digitsTouchedAt = Date.now();
                            r = stampLedgerMutation(r, 'smart_paste_digits');
                            r = titanNormalizeOriginalDigits(r, targetType, extractedDigits, 'smart_paste_digits');
                            r = annotateLedgerRecord(r, targetType, idx, ledgerMarketKeyForCard(targetType, targetArr[idx] || {}));
                            pState.dayRecords[currentDate][targetDict][idx] = r;
                        }); updatedCards.push({type: targetType, idx, key: ledgerMarketKeyForCard(targetType, targetArr[idx] || {})}); updatesCount++;
                    }
                }
            });

            if(updatesCount > 0) {
                updatedCards.forEach(card => {
                    const autoUpdates = runLiveSync(card.type, card.idx, 'd') || [];
                    const op = resolveLedgerAction(card.type, card.idx, card.key);
                    if(op.idx >= 0){
                        const rec = state.dayRecords[currentDate][op.dictName][op.idx];
                        updateLedgerScheduleStore(appState.activeId, card.type, op.idx, rec, op.key);
                        syncAdminAutoRateToVipProfiles(card.type, op.idx, op.key, rec);
                        if(autoUpdates.length) titanCommitLedgerAutoRateUpdates(autoUpdates, 'smart_paste_auto_rate');
                        else titanCommitLedgerRecordToFirebase(appState.activeId, card.type, op.idx, op.key, rec, 'smart_paste_digits', appState.activeId === 'admin1');
                    }
                });
                titanMarkLedgerDirty(); document.getElementById('smart-text-input').value = ''; activeTab = targetType; setMainNav('ledger');
            }
            else { showRealNotification('⚠️ No Data Found', 'No valid digits found in target format.', 'danger'); }
        }

        async function importContacts() { if (!('contacts' in navigator)) return showRealNotification('⚠️ Not Supported', 'Direct import support nahi karta.', 'danger'); try { const contacts = await navigator.contacts.select(['name', 'tel'], { multiple: false }); if (contacts.length) { const n = contacts[0].name[0]; let p = contacts[0].tel[0].replace(/\\D/g, ''); if (p.length >= 10) { const pid = 'client_' + Date.now(); appState.profiles[pid] = buildNewProfile(n, p.slice(-10)); autoSave(); render(true); } else showRealNotification('⚠️ Error', 'Phone support nahi mila!', 'danger'); } } catch (e) {} }
        function addVIP() { const n = document.getElementById('c-name').value.trim(); const p = document.getElementById('c-phone').value.replace(/\\D/g, ''); if(n) { const pid = 'client_' + Date.now(); appState.profiles[pid] = buildNewProfile(n, p.slice(-10)); autoSave(); render(true); } else showRealNotification('⚠️ Error', 'Valid Name chahiye.', 'danger'); }
        function deleteProfile(pid) {
            if(pid === 'client_dummy') return showRealNotification('⚠️ Error', 'Cannot delete Default Dummy Profile.', 'danger');
            if(String(pid || '').startsWith('admin')) return showRealNotification('⚠️ Error', 'Admin profile delete nahi ho sakta.', 'danger');
            if(confirm("Bhai, kya sachme is VIP ka pura ledger delete karna hai?")) {
                delete appState.profiles[pid];
                if(appState.activeId === pid) { appState.activeId = 'admin1'; state = appState.profiles.admin1; }
                if(appState.ledgerSchedules && typeof appState.ledgerSchedules === 'object') {
                    Object.keys(appState.ledgerSchedules).forEach(k => { if(String(k).startsWith(pid + '|')) delete appState.ledgerSchedules[k]; });
                }
                if(appState.wallets && typeof appState.wallets === 'object') delete appState.wallets[pid];
                if(Array.isArray(appState.walletTransactions)) appState.walletTransactions = appState.walletTransactions.filter(x => String((x && x.userId) || '') !== String(pid));
                titanMarkUiLocalWrite('vip_delete', 9000);
                saveMaster(true, true).then(() => { showRealNotification('🗑️ VIP Deleted', 'VIP profile Firebase se delete ho gaya.', 'success'); render(true); });
            }
        }

        function openClient(pid) {
            if(!IS_MASTER) return;
            pushNativeState(); appState.activeId = pid; state = appState.profiles[pid]; activeTab = 'ank'; ensureDataStruct(); setMainNav('ledger');
        }

        function buildNewProfile(name, phone) {
            let masterConfig = appState.profiles['admin1'].config;
            let newProfile = { name: name, phone: phone, config: JSON.parse(JSON.stringify(masterConfig)), dayRecords: {}, expiryDate: '', vipAccessEnabled: true, approvalStatus: 'approved', approvedAt: new Date().toISOString(), approvedBy: appState.activeId || 'admin1' };
            let masterToday = appState.profiles['admin1'].dayRecords[currentDate];
            if(masterToday) {
                newProfile.dayRecords[currentDate] = JSON.parse(JSON.stringify(masterToday));
            }
            return newProfile;
        }

        function prepDailyReportShare(type) {
            ensureDataStruct(); let arr = type === 'ank' ? markets : (type === 'jodi' ? baseMarkets : markets); let dictName = type === 'ank' ? 'data' : (type === 'jodi' ? 'jodiData' : 'pannelData'); let marginMultiplier = type === 'ank' ? 9.5 : (type === 'jodi' ? 95.0 : 150.0); let typeLabel = type.toUpperCase(); let record = state.dayRecords[currentDate]; if(!record || !record[dictName]) return showRealNotification('⚠️ No Data', 'No data available for today!', 'danger'); let msg = `🏆 *TITAN NOVA - DAILY REPORT [${typeLabel}]* 🏆\\n${appState.activeId !== 'admin1' ? '👤 *VIP:* ' + state.name + '\\n' : ''}📅 *DATE:* ${new Date(currentDate).toLocaleDateString('en-GB')}\\n━━━━━━━━━━━━━━━━━━━━\\n`; let tInvest = 0; let tWin = 0; let tPass = 0; let tFail = 0; let tRounds = 0; let details = ""; const visDict = type === 'ank' ? state.dayRecords[currentDate].visAnk : (type === 'jodi' ? state.dayRecords[currentDate].visJodi : state.dayRecords[currentDate].visPan); arr.forEach((m, idx) => { if (visDict && visDict[m.n] === false) return; let d = record[dictName][idx]; if(d && (d.s === 'PASS' || d.s === 'FAIL')) { const rawDigits = d.d ? String(d.d) : ''; const r = parseFloat(d.r) || 0; const invest = rawDigits.split(/[, ]+/).filter(x => x.trim()).length * r; let win = d.s === 'PASS' ? (r * marginMultiplier) : 0; let pl = win - invest; tInvest += invest; tWin += win; tRounds++; if(d.s === 'PASS') tPass++; else if(d.s === 'FAIL') tFail++; let plSign = pl >= 0 ? '+' : '-'; details += `🏛️ *${m.n}* [${d.s === 'PASS' ? '✅ PASS' : '❌ FAIL'}]\\n🔢 Digits: ${rawDigits}\\n💸 Inv: ₹${invest.toLocaleString()} | 💹 ${plSign}₹${Math.abs(pl).toLocaleString()}\\n\\n`; } }); if (tRounds === 0) return showRealNotification('⚠️ No Data', 'Koi completed round nahi hai aaj!', 'danger'); let net = tWin - tInvest; let finalLabel = net >= 0 ? 'PROFIT' : 'LOSS'; let finalSign = net >= 0 ? '+' : '-'; let maxRiskValue = globalStats[type].maxLoss || 0;
            msg += details + `━━━━━━━━━━━━━━━━━━━━\\n*DAILY SUMMARY [${typeLabel}]*\\n🔄 Rounds: ${tRounds} | ✅ Pass: ${tPass} | ❌ Fail: ${tFail}\\n🛡️ *Balance Risk:* Is Profit ko bachane ke liye ₹${maxRiskValue.toLocaleString()} backup zaroori tha.\\n🚀 *FINAL ${finalLabel}:* ${finalSign}₹${Math.abs(net).toLocaleString()}\\n━━━━━━━━━━━━━━━━━━━━\\n🚀 _Andres Barlin Logic V10.9_`;
            currentMsg = msg; renderShareModal();
        }

        function shareWeeklyReport() {
            let { monday, stats, totals } = getWeekStats(currentDate); let sunday = new Date(monday); sunday.setDate(sunday.getDate() + 6); let dateRange = `${monday.toLocaleDateString('en-GB', {day:'2-digit', month:'short'})} - ${sunday.toLocaleDateString('en-GB', {day:'2-digit', month:'short'})}`; let typeLabel = weeklyTabType.toUpperCase(); let typeStats = stats[weeklyTabType]; let msg = `🏆 *TITAN NOVA - WEEKLY REPORT [${typeLabel}]* 🏆\\n${appState.activeId !== 'admin1' ? '👤 *VIP:* ' + state.name + '\\n' : ''}📅 *WEEK:* ${dateRange}\\n━━━━━━━━━━━━━━━━━━━━\\n`; for (let bmName in typeStats) { let s = typeStats[bmName]; if(s.rounds > 0) { let pl = s.win - s.invest; msg += `🏛️ *${bmName}*\\n🔄 Rounds: ${s.rounds} | ✅ Pass: ${s.pass} | ❌ Fail: ${s.fail}\\n💸 Invest: ₹${s.invest.toLocaleString()}\\n💹 Net P/L: ${pl >= 0 ? '+' : ''}₹${pl.toLocaleString()}\\n━━━━━━━━━━━━━━━━━━━━\\n`; } } let tInvest = totals[weeklyTabType].invest; let tWin = totals[weeklyTabType].win; let net = tWin - tInvest; let tMaxLoss = totals[weeklyTabType].maxLoss || 0; let finalLabel = net >= 0 ? 'PROFIT' : 'LOSS'; let finalSign = net >= 0 ? '+' : '-';
            msg += `*${weeklyTabType.toUpperCase()} WEEKLY SUMMARY*\\n💰 Total Invest: ₹${tInvest.toLocaleString()}\\n💎 Total Win: ₹${tWin.toLocaleString()}\\n🛡️ *Ledger Risk:* Is hafte ₹${Math.abs(tMaxLoss).toLocaleString()} karcha backup chahiye tha.\\n🚀 *FINAL ${finalLabel}:* ${finalSign}₹${Math.abs(net).toLocaleString()}\\n━━━━━━━━━━━━━━━━━━━━\\n🚀 _Andres Barlin Logic V10.9_`;
            currentMsg = msg; renderShareModal();
        }

        function copyIntel(type, idx, btnElem, marketKey=null) {
            const op = resolveLedgerAction(type, idx, marketKey);
            const arr = ledgerArrayForType(type); const m = arr[op.idx] || {}; const d = op.rec || { d: '', r: '', s: 'WAIT' }; const rawDigits = d.d ? String(d.d) : ''; const r = parseFloat(d.r) || 0; const invest = rawDigits.split(/[, ]+/).filter(x => x.trim()).length * r; const s = globalStats[type]; const marginMultiplier = type === 'ank' ? 9.5 : (type === 'jodi' ? 95.0 : 150.0); const winAmount = r * marginMultiplier; const projectedPass = s.port + winAmount - invest; const projectedFail = s.port - invest;
            const copyText = `🚀 *TITAN NOVA INTEL* [${new Date(currentDate).toLocaleDateString('en-GB')}]\n━━━━━━━━━━━━━━━━━━━━\n🔥 *MARKET:* ${m.n || ''}\n🔢 *DIGITS:* [${d.d || ''}]\n💰 *PAR DIGIT:* ₹${r}\n💸 *TOTAL:* ₹${invest.toLocaleString()}\n━━━━━━━━━━━━━━━━━━━━`;
            const textToCopy = copyText;
            if(navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(textToCopy).then(() => { const oHTML = btnElem.innerHTML; btnElem.innerHTML = '<i class="fas fa-check"></i> Copied'; setTimeout(() => { btnElem.innerHTML = oHTML; }, 2000); }); }
            else { let textArea = document.createElement("textarea"); textArea.value = textToCopy; textArea.style.position = "fixed"; textArea.style.left = "-999999px"; document.body.appendChild(textArea); textArea.focus(); textArea.select(); try { document.execCommand('copy'); const oHTML = btnElem.innerHTML; btnElem.innerHTML = '<i class="fas fa-check"></i> Copied'; setTimeout(() => { btnElem.innerHTML = oHTML; }, 2000); } catch (err) {} textArea.remove(); }
        }

        function prepShare(type, idx, msgType, marketKey=null) {
            const op = resolveLedgerAction(type, idx, marketKey);
            const arr = ledgerArrayForType(type); const m = arr[op.idx] || {}; const d = op.rec || { d: '', r: '', s: 'WAIT' }; const rawDigits = d.d ? String(d.d) : ''; const r = parseFloat(d.r) || 0; const invest = rawDigits.split(/[, ]+/).filter(x => x.trim()).length * r; const s = globalStats[type]; const typeLabel = type.toUpperCase(); const marginMultiplier = type === 'ank' ? 9.5 : (type === 'jodi' ? 95.0 : 150.0); const projectedPass = s.port + (r * marginMultiplier) - invest; const projectedFail = s.port - invest;
            if(msgType === 'GUIDE') { currentMsg = `🚀 *TITAN NOVA INTEL* [${new Date(currentDate).toLocaleDateString('en-GB')}]\n━━━━━━━━━━━━━━━━━━━━\n🔥 *MARKET:* ${m.n || ''}\n🔢 *DIGITS:* [${d.d || ''}]\n💰 *PAR DIGIT:* ₹${r}\n💸 *TOTAL:* ₹${invest.toLocaleString()}\n━━━━━━━━━━━━━━━━━━━━`; }
            else { currentMsg = `🚀 *RESULT UPDATE [${typeLabel}]*\n👤 *VIP:* ${state.name}\n━━━━━━━━━━━━━━━━━━━━\n🔥 *MARKET:* ${m.n || ''}\n📝 *RESULT:* ${d.s === 'PASS' ? '✅ PASS' : (d.s === 'SKIP' ? '⚪ SKIP' : '❌ FAIL')}\n🔢 *DIGITS:* [${d.d || ''}]\n━━━━━━━━━━━━━━━━━━━━\n💹 *NET P/L:* ${(s.pl >= 0 ? '+' : '-')}₹${Math.abs(s.pl).toLocaleString()}\n💎 *PORTFOLIO:* ₹${s.port.toLocaleString()}\n━━━━━━━━━━━━━━━━━━━━\n🚀 _Andres Barlin Logic V10.9_`; }
            renderShareModal();
        }

        function renderShareModal() {
            let html = '';
            Object.keys(appState.profiles).forEach(pid => {
                if(pid === 'admin1' || pid === 'client_dummy') return;
                let c = appState.profiles[pid];
                if(c.phone) {
                    html += `
                    <div class="p-4 rounded-xl bg-[var(--surface-light)] border border-[var(--border)] mb-2 flex justify-between items-center active:opacity-70 transition-opacity">
                        <div class="text-left leading-tight">
                            <p class="text-white text-[13px] font-black uppercase">${c.name}</p>
                            <p class="text-[var(--text-muted)] text-[9px] mt-0.5">+${c.phone}</p>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="selectedPhone='${c.phone}'; triggerShare('WA')" class="w-10 h-10 bg-[#128C7E] text-white rounded-xl flex items-center justify-center active:scale-95"><i class="fab fa-whatsapp"></i></button>
                            <button onclick="selectedPhone='${c.phone}'; triggerShare('WAB')" class="w-10 h-10 bg-[rgba(42,171,238,0.2)] text-[var(--primary)] rounded-xl flex items-center justify-center active:scale-95 border border-[rgba(42,171,238,0.2)]"><i class="fas fa-briefcase text-sm"></i></button>
                        </div>
                    </div>`;
                }
            });

            let broadcastBtn = `
                <div class="flex gap-3 mb-2 mt-4">
                    <button onclick="selectedPhone=''; triggerShare('WA')" class="flex-1 py-3 rounded-xl border border-[var(--border)] text-[var(--text-muted)] bg-[var(--surface-light)] text-[10px] font-bold uppercase flex justify-center items-center gap-2 active:scale-95"><i class="fab fa-whatsapp text-[#25D366]"></i> WA Group</button>
                    <button onclick="selectedPhone=''; triggerShare('WAB')" class="flex-1 py-3 rounded-xl border border-[var(--border)] text-[var(--text-muted)] bg-[var(--surface-light)] text-[10px] font-bold uppercase flex justify-center items-center gap-2 active:scale-95"><i class="fas fa-users"></i> Biz Group</button>
                </div>`;

            document.getElementById('modal-client-list').innerHTML = (html || '') + broadcastBtn;
            pushNativeState();
            document.getElementById('shareModal').classList.add('open');
            window.shareModalOpen = true;
        }

        function triggerShare(appType) {
            const text = encodeURIComponent(currentMsg);
            let p = selectedPhone ? (selectedPhone.length === 10 ? '91'+selectedPhone : selectedPhone) : "";
            let url = '';
            if (appType === 'WA') { url = p ? `whatsapp://send?phone=${p}&text=${text}` : `whatsapp://send?text=${text}`; }
            else if (appType === 'WAB') { url = p ? `intent://send?phone=${p}&text=${text}#Intent;package=com.whatsapp.w4b;scheme=whatsapp;end;` : `intent://send?text=${text}#Intent;package=com.whatsapp.w4b;scheme=whatsapp;end;`; }
            window.location.href = url;
            setTimeout(() => { if(appType === 'WA' && !url.startsWith('intent')) { window.location.href = p ? `https://wa.me/${p}?text=${text}` : `https://api.whatsapp.com/send?text=${text}`; } }, 600);
            closeShareModal(false);
        }

        render();
        history.replaceState({base: true}, '', window.location.href);
    

function applyCombinedScrape(marketIndex, combinedDigits) {
    try {
        const inputEl = document.getElementById(`in-d-ank-${marketIndex}`);
        if(inputEl){
            inputEl.value = combinedDigits;
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        }
    } catch(e){
        console.log(e);
    }
}





async function fetchCombinedScrape(btn, type=null, idx=null, marketKey=null){
    try{
        let card = btn ? btn.closest('.native-card') : null;
        let market = '';
        let op = null;
        if(type !== null && idx !== null){
            op = resolveLedgerAction(type, idx, marketKey);
            const arr = ledgerArrayForType(type) || [];
            market = ((arr[op.idx] || {}).n || '').replace(/\\s+(OPEN|CLOSE)$/,'').trim();
        }

        if(!market && card){
            const title = card.querySelector('.font-bold.uppercase, span')?.textContent || '';
            market = String(title || '').replace(/\\s+(OPEN|CLOSE)$/,'').trim();
        }

        if(!market){
            showRealNotification ? showRealNotification('⚠️ Market Error','Market detect failed','danger') : alert('Market detect failed');
            return;
        }

        const res = await fetch('/api/scrape_market', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({market: market})
        });

        const data = await res.json();

        if(data.status === 'success'){
            const combined = data.combined || '';
            let input = null;
            if(op && op.idx >= 0) input = document.getElementById(`in-d-${type}-${op.idx}`);
            if(!input && card) input = card.querySelector('input[id^="in-d-"]') || card.querySelector('input');

            if(input){
                input.value = combined;
                if(type !== null && op && op.idx >= 0){
                    updateMarket(type, op.idx, 'd', combined, op.key, 'combo_scrape');
                } else {
                    input.dispatchEvent(new Event('input', { bubbles:true }));
                }
            }

            showRealNotification ? showRealNotification('✅ Combo Applied', combined || 'No combined digit found', 'success') : alert('Combined Applied: ' + combined);
        } else {
            showRealNotification ? showRealNotification('⚠️ Scrape Failed', data.message || 'Scrape Failed', 'danger') : alert(data.message || 'Scrape Failed');
        }

    }catch(e){
        console.log(e);
        showRealNotification ? showRealNotification('❌ Error', 'Combo scrape failed', 'danger') : alert('Error');
    }
}



</script>
</body>
</html>
"""




# ==========================================================
# v26 Lite Core Cleanup
# Optional dashboard/report APIs and standalone pages removed.
# Core app, ledger, wallet, payment, withdrawal, result, WhatsApp proxy,
# security, atomic save guards, and schedule fixes remain above.
# ==========================================================


@app.route('/api/firebase_data_guard_status')
@admin_required
def api_firebase_data_guard_status():
    backup_files = []
    try:
        backup_files = _state_backup_files()[:5]
    except Exception:
        backup_files = []
    live_score = {}
    live_status = 'unchecked'
    try:
        live = load_from_firebase()
        live_status = FIREBASE_LAST_LOAD_META.get('status', 'unknown')
        live_score = _runtime_state_score(live) if isinstance(live, dict) else {}
    except Exception as e:
        live_status = 'error:' + str(e)[:120]
    return jsonify({
        'status': 'success',
        'firebaseDataGuard': False,
        'version': FIREBASE_DATA_GUARD_VERSION,
        'manualOverwriteMode': True,
        'guardedRootSaves': False,
        'casRootPut': False,
        'emptyFirebaseDefaultOverwriteBlocked': False,
        'unguardedRootPutBlocked': False,
        'allowEmptyInit': True,
        'lastLoad': FIREBASE_LAST_LOAD_META,
        'liveStatus': live_status,
        'liveScore': live_score,
        'protectedKeys': _firebase_protected_keys(),
        'recentBackups': [{k:v for k,v in x.items() if k in ('file','size','mtime')} for x in backup_files],
    })

if __name__ == '__main__':
    app.run(debug=False)
