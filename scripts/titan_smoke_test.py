#!/usr/bin/env python3
"""
Titan Nova Stability Smoke Test

Purpose:
- catch syntax/runtime-surface breakage before Termux deploy
- verify Flask + Gateway core stability markers remain present
- warn about config risks that usually cause refresh revert, blank setup, or WhatsApp offline issues

Run:
    python3 scripts/titan_smoke_test.py

Strict mode:
    TITAN_SMOKE_STRICT=1 python3 scripts/titan_smoke_test.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
STRICT = str(os.environ.get("TITAN_SMOKE_STRICT", "0")).strip().lower() in {"1", "true", "yes", "on"}
Result = Tuple[str, str, str]
results: List[Result] = []


def add(level: str, name: str, message: str) -> None:
    results.append((level.upper(), name, message))


def read_text(path: str) -> str:
    full = ROOT / path
    try:
        return full.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return full.read_text(encoding="utf-8", errors="replace")


def require_file(path: str) -> bool:
    full = ROOT / path
    if full.exists() and full.is_file():
        add("PASS", f"file:{path}", "present")
        return True
    add("FAIL", f"file:{path}", "missing")
    return False


def check_python_syntax() -> None:
    path = ROOT / "flask_app.py"
    if not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename="flask_app.py")
        add("PASS", "python:syntax", "flask_app.py parses successfully")
    except SyntaxError as exc:
        add("FAIL", "python:syntax", f"flask_app.py syntax error at line {exc.lineno}: {exc.msg}")
    except Exception as exc:
        add("FAIL", "python:syntax", f"unable to parse flask_app.py: {exc}")


def check_gateway_syntax() -> None:
    path = ROOT / "Gateway.js"
    if not path.exists():
        return
    node = shutil.which("node")
    if not node:
        add("WARN", "node:syntax", "node not found; skipped Gateway.js syntax check")
        return
    proc = subprocess.run([node, "--check", str(path)], cwd=str(ROOT), text=True, capture_output=True)
    if proc.returncode == 0:
        add("PASS", "node:syntax", "Gateway.js passes node --check")
    else:
        msg = (proc.stderr or proc.stdout or "node --check failed").strip().splitlines()
        add("FAIL", "node:syntax", msg[0] if msg else "Gateway.js syntax check failed")


def check_package_json() -> None:
    path = ROOT / "package.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        scripts = payload.get("scripts") or {}
        deps = payload.get("dependencies") or {}
        for dep in ["express", "axios", "qrcode-terminal", "@whiskeysockets/baileys"]:
            if dep in deps:
                add("PASS", f"npm:dep:{dep}", "declared")
            else:
                add("FAIL", f"npm:dep:{dep}", "missing from package.json")
        if "smoke" in scripts:
            add("PASS", "npm:script:smoke", "available")
        else:
            add("WARN", "npm:script:smoke", "missing; run python3 scripts/titan_smoke_test.py directly")
    except Exception as exc:
        add("FAIL", "package.json", f"invalid JSON: {exc}")


def check_flask_surface() -> None:
    if not (ROOT / "flask_app.py").exists():
        return
    src = read_text("flask_app.py")
    required_markers = {
        "REALTIME_SYNC_VERSION": "realtime cache/sync marker",
        "FIREBASE_DATA_GUARD_VERSION": "Firebase data-loss guard marker",
        "def load_from_firebase": "Firebase load function",
        "def save_to_firebase": "Firebase guarded root save function",
        "def _firebase_put_child": "child PUT helper",
        "def _firebase_patch_child": "child PATCH helper",
        "def _firebase_delete_child": "child DELETE helper",
        "def renderSetupTab": "Setup tab render function",
        "@app.after_request": "no-store API cache guard",
    }
    for needle, desc in required_markers.items():
        if needle in src:
            add("PASS", f"flask:{needle}", desc)
        else:
            add("FAIL", f"flask:{needle}", f"missing {desc}")

    routes = re.findall(r"@app\.route\(\s*['\"]([^'\"]+)", src)
    duplicate_routes = sorted({r for r in routes if routes.count(r) > 1})
    if duplicate_routes:
        add("WARN", "flask:duplicate_routes", ", ".join(duplicate_routes[:20]))
    else:
        add("PASS", "flask:duplicate_routes", "no duplicate route decorators detected")

    if "Manual overwrite root Firebase save committed" in src and "guarded-cas-root-save" in src:
        add("WARN", "firebase:root_save_modes", "both manual-overwrite history and guarded-CAS mode exist; avoid new full-root saves")
    else:
        add("PASS", "firebase:root_save_modes", "no conflicting root-save marker detected")


def check_gateway_surface() -> None:
    if not (ROOT / "Gateway.js").exists():
        return
    src = read_text("Gateway.js")
    required_markers = {
        "FIREBASE_URL": "Firebase config constant",
        "APP_TZ": "timezone config",
        "BUSINESS_DAY_CUTOFF_HOUR": "06:00 business-day cutoff support",
        "TITAN_SCHEDULE_POLL_MS": "schedule poll loop config",
        "RESULT_SCRAPE_ENABLED": "result scrape toggle",
        "GATEWAY_ROOT_SAVE_NORMAL_DISABLED": "root-save disable marker",
        "TITAN_GATEWAY_TOKEN": "Gateway auth token support",
    }
    for needle, desc in required_markers.items():
        if needle in src:
            add("PASS", f"gateway:{needle}", desc)
        else:
            add("FAIL", f"gateway:{needle}", f"missing {desc}")

    if "DEFAULT_FIREBASE_URL" in src:
        add("WARN", "gateway:default_firebase_url", "Gateway has fallback Firebase URL; set FIREBASE_URL explicitly in Termux")
    if 'HOST = process.env.HOST' in src and '"127.0.0.1"' in src:
        add("WARN", "gateway:localhost_host", "Gateway binds localhost by default; split-phone deploy needs HOST=0.0.0.0 and reachable GATEWAY_URL")


def check_requirements() -> None:
    if not (ROOT / "requirements.txt").exists():
        return
    txt = read_text("requirements.txt")
    for dep in ["flask", "requests"]:
        if re.search(rf"^\s*{re.escape(dep)}\b", txt, flags=re.I | re.M):
            add("PASS", f"pip:{dep}", "declared")
        else:
            add("FAIL", f"pip:{dep}", "missing from requirements.txt")


def check_env_example() -> None:
    if (ROOT / ".env.example").exists():
        env = read_text(".env.example")
        for key in ["FIREBASE_URL", "TITAN_ADMIN_TOKEN", "TITAN_GATEWAY_TOKEN", "GATEWAY_URL", "APP_TZ"]:
            if re.search(rf"^\s*{key}=", env, flags=re.M):
                add("PASS", f"env.example:{key}", "documented")
            else:
                add("WARN", f"env.example:{key}", "not documented")
    else:
        add("WARN", "env.example", "missing; Termux deploys may use wrong defaults")


def main() -> int:
    print("\n🛡️  Titan Nova Stability Smoke Test\n")
    for path in ["flask_app.py", "Gateway.js", "package.json", "requirements.txt"]:
        require_file(path)
    check_python_syntax()
    check_gateway_syntax()
    check_package_json()
    check_requirements()
    check_env_example()
    check_flask_surface()
    check_gateway_surface()

    max_name = max((len(name) for _, name, _ in results), default=10)
    for level, name, message in results:
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(level, "•")
        print(f"{icon} {level:<4} {name:<{max_name}}  {message}")

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print("\nSummary:")
    print(f"  PASS: {sum(1 for r in results if r[0] == 'PASS')}")
    print(f"  WARN: {len(warns)}")
    print(f"  FAIL: {len(fails)}")

    if fails:
        print("\nDeploy blocked: FAIL items fix karo, phir Termux me run karo.")
        return 1
    if STRICT and warns:
        print("\nStrict mode blocked: WARN items bhi fix karne honge.")
        return 1
    print("\nDeploy smoke check passed. Warnings ko ignore mat karo, par app syntax/surface safe hai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
