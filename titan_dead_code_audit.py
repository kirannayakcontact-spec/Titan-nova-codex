from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "flask_app.py",
    "Gateway.js",
    "TITAN_STABLE_DEPLOY.md",
    "termux.env.example",
    ".github/workflows/titan-check.yml",
]
OBSOLETE = [
    "sitecustomize.py",
    "usercustomize.py",
    "dashboard.js",
    "bot.js",
    "README_TERMUX_FINAL.txt",
]


def read(rel):
    p = ROOT / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def main():
    failures = []
    warnings = []
    for rel in FILES:
        text = read(rel)
        if not text:
            failures.append(f"missing expected file: {rel}")
            continue
        for name in OBSOLETE:
            if name in text:
                failures.append(f"obsolete reference found in {rel}: {name}")
    for rel in ("flask_app.py", "Gateway.js"):
        text = read(rel)
        marker_count = text.count("_VERSION")
        if marker_count > 40:
            warnings.append(f"{rel} still has many patch markers: {marker_count}")
    print("Titan dead-code audit")
    print("failures:", len(failures))
    for x in failures:
        print("FAIL:", x)
    print("warnings:", len(warnings))
    for x in warnings:
        print("WARN:", x)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
