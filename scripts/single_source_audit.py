#!/usr/bin/env python3
"""Single-source duplicate audit for Titan Nova.

Scans repository text files for duplicated Flask routes, JS/Python function names,
HTML ids, API path literals, and after_request UI injectors. This is a reporting
script only; it does not modify runtime files.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
SUFFIXES = {".py", ".js", ".html", ".md", ".txt"}

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


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in SUFFIXES:
            continue
        yield p


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def collect():
    hits = {kind: defaultdict(list) for kind in PATTERNS}
    for p in iter_files():
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
    return hits


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
    hits = collect()
    for kind, mapping in hits.items():
        print_section(kind, mapping)
    print("\nSingle-source rule: one feature should have one owner UI, one owner API, and one Firebase source path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
