#!/usr/bin/env python3
"""Single-source duplicate audit for Titan Nova.

Scans repository text files for duplicated Flask routes, JS/Python function names,
HTML ids, API path literals, and after_request UI injectors.

Default mode scans the repo.
`--active-only` scans the active Termux/root runtime and intentionally excludes
modular scaffolds, docs, backup files, and patch scripts so the report is useful
for cleaning the running app.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
SUFFIXES = {".py", ".js", ".html", ".md", ".txt", ".sh", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".example", ".bak"}

NEW_RESULT_SOURCE_URL = "https://dpbosss.net.in/"
# Keep banned names assembled so an old website never appears literally in the current tree.
FORBIDDEN_RESULT_SOURCE_TOKENS = (
    "dp" + "bosse",
    "sattamatka" + "dpboss",
    "dp" + "boss.net",
    "dp" + "boss.mobi",
    "dp" + "boss.boston",
    "dp" + "boss.services",
    "dp" + "bossmatka",
)

ACTIVE_ROOT_FILES = {
    "flask_app.py",
    "titan_core.py",
    "whatsapp_multi_session.js",
    "bot_connection_manager.py",
    "deposit_finance_native.py",
    "deposit_ocr_guard.py",
    "deposit_screenshot_routes.py",
    "finance_flow_split.py",
    "ledger_auto_mark_safe.py",
    "result_toggle_sticky.py",
    "security_runtime.py",
    "settlement_toggle_sticky.py",
    "settlement_toggle_ui_guard.py",
    "titan_codex_stability_patch.py",
    "titan_firebase_guard_patch.py",
    "titan_frontend_boot_fix_patch.py",
    "titan_ledger_control_overlay_patch.py",
    "titan_pwa_fast_patch.py",
    "titan_realtime_global.py",
    "titan_strict_result_rules_patch.py",
    "vip_delete_sticky.py",
}

ACTIVE_SKIP_PARTS = {
    "backend",
    "bot",
    "docs",
    "scripts",
    "tests",
    "node_modules",
    ".git",
    "__pycache__",
}

PATCH_FILE_HINTS = (
    "_patch.py",
    "_patcher.py",
    "patch.py",
    "phase",
    "cleanup",
)

PATTERNS = {
    "flask_route": re.compile(r"@app\.(?:route|get|post|put|delete)\(\s*['\"]([^'\"]+)['\"]"),
    "python_def": re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.M),
    "js_function": re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
    "js_const_function": re.compile(r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\("),
    "html_id": re.compile(r"\bid=['\"]([^'\"]+)['\"]"),
    "api_path_literal": re.compile(r"['\"](/api/[A-Za-z0-9_./{}:\-]+)['\"]"),
    "after_request_injector": re.compile(r"@app\.after_request\s*\n\s*def\s+([A-Za-z_][A-Za-z0-9_]*)"),
}

KNOWN_ALLOWED = {
    "python_def": {"register", "main"},
    "js_function": set(),
    "js_const_function": set(),
    "flask_route": set(),
    "html_id": set(),
    "api_path_literal": set(),
    "after_request_injector": set(),
}


def is_active_runtime_file(p: Path) -> bool:
    rp = p.relative_to(ROOT)
    if len(rp.parts) != 1:
        return False
    name = rp.name
    if name not in ACTIVE_ROOT_FILES:
        return False
    low = name.lower()
    if any(hint in low for hint in PATCH_FILE_HINTS):
        return False
    return True


def iter_files(active_only: bool = False):
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(ROOT).parts)
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in SUFFIXES:
            continue
        if active_only:
            if parts & ACTIVE_SKIP_PARTS:
                continue
            if not is_active_runtime_file(p):
                continue
        yield p



def iter_tracked_text_files():
    """Yield current tracked text/config files; ignore runtime data and Git history."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=20,
        )
        names = [x for x in proc.stdout.decode("utf-8", "ignore").split("\0") if x]
    except Exception:
        names = []

    if names:
        candidates = (ROOT / name for name in names)
    else:
        candidates = ROOT.rglob("*")

    for p in candidates:
        if not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in SUFFIXES:
            continue
        yield p


def check_result_source_policy():
    violations = []
    allowed_seen = []
    for p in iter_tracked_text_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = text.lower()
        hits = sorted({token for token in FORBIDDEN_RESULT_SOURCE_TOKENS if token in low})
        if hits:
            violations.append((rel(p), hits))
        if NEW_RESULT_SOURCE_URL in low:
            allowed_seen.append(rel(p))

    required = {"whatsapp_multi_session.js", "termux.env.example"}
    missing_required = sorted(required.difference(allowed_seen))
    if violations:
        print("\n❌ Old result website references found:")
        for name, hits in violations:
            print(f"  - {name}: {', '.join(hits)}")
    if missing_required:
        print("\n❌ New result website missing from required files:")
        for name in missing_required:
            print("  -", name)
    if violations or missing_required:
        return False

    print(f"✅ Result website policy clean: old references=0, source={NEW_RESULT_SOURCE_URL}")
    return True


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def collect(active_only: bool = False):
    hits = {kind: defaultdict(list) for kind in PATTERNS}
    scanned = []
    for p in iter_files(active_only=active_only):
        scanned.append(rel(p))
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for kind, rx in PATTERNS.items():
            for m in rx.finditer(text):
                name = m.group(1)
                if name in KNOWN_ALLOWED.get(kind, set()):
                    continue
                hits[kind][name].append(f"{rel(p)}:{line_of(text, m.start())}")
    return hits, sorted(scanned)


def print_section(kind: str, mapping):
    dups = {name: locs for name, locs in mapping.items() if len(locs) > 1}
    print(f"\n== {kind}: {len(dups)} duplicate keys ==")
    for name, locs in sorted(dups.items(), key=lambda item: (-len(item[1]), item[0])):
        print(f"\n{name}  x{len(locs)}")
        for loc in locs[:15]:
            print(f"  - {loc}")
        if len(locs) > 15:
            print(f"  ... {len(locs) - 15} more")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active-only", action="store_true", help="scan only active root Termux runtime files")
    parser.add_argument("--show-files", action="store_true", help="print scanned file list")
    parser.add_argument("--result-source-only", action="store_true", help="enforce the single allowed result website and exit")
    args = parser.parse_args()

    if not check_result_source_policy():
        return 1
    if args.result_source_only:
        return 0

    hits, scanned = collect(active_only=args.active_only)
    print("Mode:", "active root runtime only" if args.active_only else "full repository")
    print("Scanned files:", len(scanned))
    if args.show_files:
        for name in scanned:
            print("  -", name)
    for kind, mapping in hits.items():
        print_section(kind, mapping)
    print("\nSingle-source rule: one feature should have one owner UI, one owner API, and one Firebase source path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
