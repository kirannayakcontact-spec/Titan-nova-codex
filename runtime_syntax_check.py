#!/usr/bin/env python3
"""Validate Titan Nova active runtime files before deployment."""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent

PYTHON_FILES = [
    "flask_app.py",
    "titan_core.py",
    "bot_connection_manager.py",
    "deposit_finance_native.py",
    "deposit_ocr_guard.py",
    "deposit_screenshot_routes.py",
    "deposit_tasks.py",
    "finance_flow_split.py",
    "ledger_auto_mark_safe.py",
    "result_toggle_sticky.py",
    "security_runtime.py",
    "settlement_toggle_sticky.py",
    "settlement_toggle_ui_guard.py",
    "titan_codex_stability_patch.py",
    "titan_firebase_guard_patch.py",
    "titan_frontend_boot_fix_patch.py",
    "titan_pwa_fast_patch.py",
    "titan_realtime_global.py",
    "titan_strict_result_rules_patch.py",
    "vip_delete_sticky.py",
]

JAVASCRIPT_FILES = [
    "whatsapp_multi_session.js",
    "gateway_codex_preflight_patch.js",
    "multi_session_manager.js",
    "redis_auth_state.js",
    "static/pwa-fast.js",
]

FORBIDDEN_REFERENCES = [
    "titan_ledger_autopf_ui_patch",
    "titan_ledger_autopf_visible_patch",
    "gateway_financial_ingest_patch",
]


def fail(message: str) -> None:
    print(f"❌ {message}")
    raise SystemExit(1)


def check_python(path: pathlib.Path) -> None:
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
    except Exception as exc:
        fail(f"Python syntax failed: {path.name}: {exc}")
    print(f"✅ Python syntax: {path.name}")


def check_javascript(path: pathlib.Path) -> None:
    try:
        result = subprocess.run(
            ["node", "--check", str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        fail("Node.js missing; JavaScript syntax check nahi ho sakta.")
    except Exception as exc:
        fail(f"JavaScript checker failed for {path.name}: {exc}")
    if result.returncode != 0:
        fail(f"JavaScript syntax failed: {path.name}\n{result.stderr.strip()}")
    print(f"✅ JavaScript syntax: {path.name}")


def check_launcher_references() -> None:
    combined = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("flask_app.py", "whatsapp_multi_session.js", "multi_session_manager.js")
    )
    for forbidden in FORBIDDEN_REFERENCES:
        if re.search(rf"\b{re.escape(forbidden)}\b", combined):
            fail(f"Obsolete runtime reference remains: {forbidden}")
    required = [
        "BEGIN CONSOLIDATED gateway_deposit_ocr_patch.js",
        "BEGIN CONSOLIDATED gateway_withdrawal_runtime_patch.js",
        "OWNER_CODE_LOGIN_V1",
        "titan_strict_result_rules_patch",
    ]
    for marker in required:
        if marker not in combined:
            fail(f"Required runtime reference missing: {marker}")
    print("✅ Runtime references: canonical and clean")


def main() -> int:
    for name in PYTHON_FILES + JAVASCRIPT_FILES:
        if not (ROOT / name).is_file():
            fail(f"Required runtime file missing: {name}")

    for name in PYTHON_FILES:
        check_python(ROOT / name)
    for name in JAVASCRIPT_FILES:
        check_javascript(ROOT / name)
    check_launcher_references()
    print("✅ Titan Nova active runtime syntax/reference check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
