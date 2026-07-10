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
    "deposit_ocr_guard.py",
    "strict_deposit_ocr_runtime.py",
    "titan_result_control_patch.py",
    "titan_strict_result_rules_patch.py",
    "titan_frontend_boot_fix_patch.py",
    "titan_ledger_control_overlay_patch.py",
]

JAVASCRIPT_FILES = [
    "Gateway.js",
    "gateway_codex_preflight_patch.js",
    "gateway_firebase_guard_patch.js",
    "gateway_wallet_alias_patch.js",
    "gateway_deposit_ocr_patch.js",
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
        for name in ("flask_app.py", "Gateway.js")
    )
    for forbidden in FORBIDDEN_REFERENCES:
        if re.search(rf"\b{re.escape(forbidden)}\b", combined):
            fail(f"Obsolete runtime reference remains: {forbidden}")
    required = [
        "titan_ledger_control_overlay_patch",
        "gateway_deposit_ocr_patch",
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
