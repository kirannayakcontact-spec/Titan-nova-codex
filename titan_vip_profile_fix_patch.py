from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'flask_app.py'
MARKER = 'TITAN_VIP_PROFILE_PERSISTENCE_FIX_V1'
ANCHOR = """@app.route('/api/gateway_status')
def api_gateway_status():
    try:
        res = _gateway_request('GET', '/status', timeout=5)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({'status': 'offline', 'connected': False, 'message': str(e), 'timezone': APP_TZ})"""

BLOCK = r'''

# TITAN_VIP_PROFILE_PERSISTENCE_FIX_V1

def _vip_fix_phone(v):
    try:
        d = re.sub(r'[^0-9]', '', str(v or ''))
    except Exception:
        d = ''.join(ch for ch in str(v or '') if ch.isdigit())
    if len(d) == 10:
        d = '91' + d
    return d

def _vip_fix_profile_ids_for_phone(state_obj, phone):
    phone = _vip_fix_phone(phone)
    ids = []
    profiles = state_obj.get('profiles', {}) if isinstance(state_obj, dict) and isinstance(state_obj.get('profiles'), dict) else {}
    for pid, prof in profiles.items():
        if isinstance(prof, dict) and phone and _vip_fix_phone(prof.get('phone') or prof.get('mobile') or '') == phone:
            ids.append(str(pid))
    return ids

def _vip_fix_stamp_deleted(state_obj, profile_id, profile=None, reason='admin_removed'):
    if not isinstance(state_obj, dict):
        return
    table = state_obj.setdefault('deletedProfiles', {})
    if not isinstance(table, dict):
        state_obj['deletedProfiles'] = {}
        table = state_obj['deletedProfiles']
    phone = _vip_fix_phone((profile or {}).get('phone') or (profile or {}).get('mobile') or '')
    rec = {'id': str(profile_id or ''), 'phone': phone, 'name': (profile or {}).get('name') if isinstance(profile, dict) else '', 'removedAt': _now_iso_local(), 'reason': reason, 'source': 'vip_profile_persistence_fix_v1'}
    if profile_id:
        table[str(profile_id)] = rec
    if phone:
        table['phone_' + phone] = rec

def _vip_fix_clear_user_paths(state_obj, profile_id):
    pid = str(profile_id or '')
    if not pid:
        return
    try:
        if isinstance(state_obj.get('wallets'), dict):
            state_obj['wallets'].pop(pid, None)
        if isinstance(state_obj.get('ledgerSchedules'), dict):
            for k in list(state_obj['ledgerSchedules'].keys()):
                if str(k).startswith(pid + '|'):
                    state_obj['ledgerSchedules'].pop(k, None)
        if isinstance(state_obj.get('entries'), list):
            for e in state_obj['entries']:
                if isinstance(e, dict) and str(e.get('userId') or '') == pid:
                    e['userProfileRemoved'] = True
                    e['userProfileRemovedAt'] = _now_iso_local()
        if isinstance(state_obj.get('withdrawals'), list):
            for w in state_obj['withdrawals']:
                if isinstance(w, dict) and str(w.get('userId') or '') == pid and str(w.get('status') or '').lower() not in ('paid','rejected','cancelled'):
                    w['userProfileRemoved'] = True
        if isinstance(state_obj.get('payments'), list):
            for p in state_obj['payments']:
                if isinstance(p, dict) and str(p.get('userId') or '') == pid:
                    p['userProfileRemoved'] = True
    except Exception:
        pass

@app.route('/api/vip_profile_remove', methods=['POST'])
@admin_required
def api_vip_profile_remove():
    try:
        data = request.get_json(silent=True) or {}
        pid = str(data.get('profileId') or data.get('id') or data.get('userId') or '').strip()
        phone = _vip_fix_phone(data.get('phone') or '')
        state_obj = migrate_and_get_state()
        profiles = state_obj.setdefault('profiles', {})
        if not isinstance(profiles, dict):
            state_obj['profiles'] = {}
            profiles = state_obj['profiles']
        targets = []
        if pid and pid in profiles:
            targets.append(pid)
        if phone:
            for x in _vip_fix_profile_ids_for_phone(state_obj, phone):
                if x not in targets:
                    targets.append(x)
        if not targets:
            return jsonify({'status': 'not_found', 'message': 'Profile not found', 'profileId': pid, 'phone': phone})
        removed = []
        for tid in targets:
            prof = profiles.get(tid) if isinstance(profiles.get(tid), dict) else {}
            if str(tid).startswith('admin'):
                continue
            _vip_fix_stamp_deleted(state_obj, tid, prof, 'admin_removed')
            profiles.pop(tid, None)
            _vip_fix_clear_user_paths(state_obj, tid)
            removed.append(tid)
        if not removed:
            return jsonify({'status': 'blocked', 'message': 'Admin profile remove blocked'}) , 403
        _firebase_put_child(['profiles'], profiles)
        _firebase_put_child(['deletedProfiles'], state_obj.get('deletedProfiles', {}))
        try:
            _firebase_put_child(['wallets'], state_obj.get('wallets', {}))
            _firebase_put_child(['ledgerSchedules'], state_obj.get('ledgerSchedules', {}))
            if isinstance(state_obj.get('entries'), list):
                _firebase_put_child(['entries'], state_obj.get('entries', []))
            if isinstance(state_obj.get('auditLog'), list):
                state_obj['auditLog'].append({'id':'VIPRM'+str(int(time.time())), 'time':_now_iso_local(), 'action':'vip_profile_removed', 'detail':{'removed':removed, 'phone':phone}})
                _firebase_put_child(['auditLog'], state_obj['auditLog'][-1000:])
        except Exception:
            pass
        _rt_cache_clear('vip_profile_removed')
        return jsonify({'status':'success','removed':removed,'message':'VIP profile removed from Firebase. Refresh will not restore it.'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500

@app.route('/api/vip_profile_create_pending', methods=['POST'])
@admin_required
def api_vip_profile_create_pending():
    try:
        data = request.get_json(silent=True) or {}
        phone = _vip_fix_phone(data.get('phone') or data.get('mobile') or data.get('number') or '')
        if not phone:
            return jsonify({'status':'error','message':'Valid phone required'}), 400
        state_obj = migrate_and_get_state()
        profiles = state_obj.setdefault('profiles', {})
        for pid, prof in profiles.items():
            if isinstance(prof, dict) and _vip_fix_phone(prof.get('phone') or '') == phone:
                return jsonify({'status':'exists','profileId':pid,'profile':prof})
        pid = str(data.get('profileId') or ('client_' + phone)).strip()
        prof = {'id':pid,'name':str(data.get('name') or ('VIP ' + phone[-4:]))[:80],'phone':phone,'approvalStatus':'pending','vipAccessEnabled':False,'autoCreated':True,'approvalSource':'manual_pending_profile','createdAt':_now_iso_local(),'updatedAt':_now_iso_local()}
        profiles[pid] = prof
        try:
            if isinstance(state_obj.get('deletedProfiles'), dict):
                state_obj['deletedProfiles'].pop(pid, None)
                state_obj['deletedProfiles'].pop('phone_' + phone, None)
                _firebase_put_child(['deletedProfiles'], state_obj['deletedProfiles'])
        except Exception:
            pass
        _firebase_put_child(['profiles', pid], prof)
        _rt_cache_clear('vip_profile_created_pending')
        return jsonify({'status':'success','profileId':pid,'profile':prof,'message':'Pending VIP profile created'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)}), 500
# /TITAN_VIP_PROFILE_PERSISTENCE_FIX_V1
'''

def apply_patch(text):
    if MARKER in text:
        return text, False
    if ANCHOR not in text:
        raise RuntimeError('anchor not found')
    return text.replace(ANCHOR, ANCHOR + BLOCK, 1), True

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); args = ap.parse_args()
    old = TARGET.read_text(encoding='utf-8', errors='replace')
    new, changed = apply_patch(old)
    if not changed:
        print('VIP profile persistence fix already present'); return 0
    print('VIP profile persistence fix can be applied')
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + '.vip-profile-fix.bak').write_text(old, encoding='utf-8')
        TARGET.write_text(new, encoding='utf-8')
        print('Applied VIP profile persistence fix')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
