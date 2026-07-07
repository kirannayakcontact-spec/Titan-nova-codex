from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    "flask_app.py",
    "Gateway.js",
    "TITAN_STABLE_DEPLOY.md",
    "TITAN_PHASE2_CLEANUP_REPORT.md",
    "TITAN_PHASE3_RUNTIME_BUDGET.md",
    "termux.env.example",
    ".github/workflows/titan-check.yml",
]
OBSOLETE = ["sitecustomize.py", "usercustomize.py", "dashboard.js", "bot.js", "README_TERMUX_FINAL.txt"]
OLD_DEFAULT_HINTS = ["default-rtdb", "SattaMatka", "Mobi"]
RUNTIME_CACHE_NAMES = [
    "whatsapp_targets_cache.json",
    "titan_schedule_sent_log.json",
    "titan_spam_guard_state.json",
    "titan_result_scrape_confirm.json",
    "titan_live_result_state.json",
    "titan_whatsapp_safety_state.json",
    "titan_whatsapp_reliability_log.json",
    "titan_processed_messages.json",
]


def read(rel):
    p = ROOT / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def line_count(text):
    return text.count("\n") + (1 if text else 0)


def main():
    failures = []
    warnings = []
    cleanup_targets = []
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
        lines = line_count(text)
        marker_count = text.count("_VERSION")
        if marker_count > 40:
            cleanup_targets.append(f"{rel}: consolidate patch/version markers ({marker_count})")
        if lines > 5000:
            cleanup_targets.append(f"{rel}: very large runtime file ({lines} lines)")
        for old in OLD_DEFAULT_HINTS:
            if old in text:
                cleanup_targets.append(f"{rel}: legacy default/source hint remains -> {old}")
        for cache_name in RUNTIME_CACHE_NAMES:
            if cache_name in text:
                warnings.append(f"{rel}: runtime cache/local state reference -> {cache_name}")
    flask_text = read("flask_app.py")
    if "render_template_string" in flask_text and "</html>" in flask_text:
        cleanup_targets.append("flask_app.py: dashboard HTML/JS is embedded inside Python string")
    print("Titan dead-code audit")
    print("failures:", len(failures))
    for x in failures:
        print("FAIL:", x)
    print("cleanup_targets:", len(cleanup_targets))
    for x in cleanup_targets:
        print("TARGET:", x)
    print("warnings:", len(warnings))
    for x in warnings:
        print("WARN:", x)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
