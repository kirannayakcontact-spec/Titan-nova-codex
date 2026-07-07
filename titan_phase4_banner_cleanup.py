from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
TARGETS = ["flask_app.py", "Gateway.js"]


def clean_text(text):
    lines = text.splitlines()
    out = []
    removed = 0
    blank_run = 0
    for line in lines:
        stripped = line.strip()
        is_banner = stripped.startswith("# ===") or stripped.startswith("// ===")
        if is_banner:
            removed += 1
            continue
        if stripped == "":
            blank_run += 1
            if blank_run > 2:
                removed += 1
                continue
        else:
            blank_run = 0
        out.append(line.rstrip())
    return "\n".join(out) + "\n", removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write cleaned files")
    args = parser.parse_args()
    total_removed = 0
    print("Titan Phase 4 banner cleanup")
    for name in TARGETS:
        path = ROOT / name
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned, removed = clean_text(original)
        total_removed += removed
        print(f"{name}: removable banner/blank lines={removed}")
        if args.apply and cleaned != original:
            backup = path.with_suffix(path.suffix + ".phase4.bak")
            backup.write_text(original, encoding="utf-8")
            path.write_text(cleaned, encoding="utf-8")
            print(f"{name}: cleaned, backup={backup.name}")
    if not args.apply:
        print("dry-run only. Run with --apply to write files.")
    print(f"total removable lines={total_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
