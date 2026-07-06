from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'flask_app.py'
MARKER = 'TITAN_PROFILE_DELETE_GUARD_V1'
OLD = """        for k, v in live.items():
            if k not in cand:
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand"""
NEW = """        deleted_profiles = {}
        try:
            if key == 'profiles':
                if isinstance(candidate.get('deletedProfiles'), dict):
                    deleted_profiles.update(candidate.get('deletedProfiles') or {})
                if isinstance(latest.get('deletedProfiles'), dict):
                    deleted_profiles.update(latest.get('deletedProfiles') or {})
        except Exception:
            deleted_profiles = {}
        for k, v in live.items():
            if k not in cand:
                if key == 'profiles':
                    phone = ''
                    try:
                        phone = re.sub(r'[^0-9]', '', str((v or {}).get('phone') or (v or {}).get('mobile') or ''))
                        if len(phone) == 10:
                            phone = '91' + phone
                    except Exception:
                        phone = ''
                    if str(k) in deleted_profiles or (phone and ('phone_' + phone) in deleted_profiles):
                        continue
                cand[k] = _runtime_deepcopy(v)
        candidate[key] = cand
        if key == 'profiles' and deleted_profiles:
            candidate['deletedProfiles'] = deleted_profiles"""

def apply_patch(text):
    if MARKER in text:
        return text, False
    if OLD not in text:
        raise RuntimeError('merge guard anchor not found')
    text = text.replace(OLD, NEW + "\n    # " + MARKER, 1)
    return text, True

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); args=ap.parse_args()
    old=TARGET.read_text(encoding='utf-8', errors='replace')
    new, changed=apply_patch(old)
    if not changed:
        print('Profile delete guard already present'); return 0
    print('Profile delete guard can be applied')
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + '.profile-delete-guard.bak').write_text(old, encoding='utf-8')
        TARGET.write_text(new, encoding='utf-8')
        print('Applied profile delete guard')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
