from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'flask_app.py'
MARKER = 'TITAN_VIP_DELETE_UI_FIX_V1'
ANCHOR = """        function showToast(msg, color='blue') {
            const typeMap = { blue:'info', green:'success', cyan:'info', rose:'danger', red:'danger', emerald:'success' };
            showRealNotification('Titan Nova', msg, typeMap[color] || 'info');
        }"""

BLOCK = r'''

        // TITAN_VIP_DELETE_UI_FIX_V1
        async function titanPersistentVipRemove(profileIdOrPhone, extra={}){
            const id = String(profileIdOrPhone || extra.profileId || extra.id || '').trim();
            const phone = String(extra.phone || '').trim();
            if(!id && !phone){ showRealNotification('VIP Delete', 'Profile id/phone detect nahi hua.', 'danger'); return false; }
            if(id && id.startsWith('admin')){ showRealNotification('VIP Delete Blocked', 'Admin profile delete blocked.', 'danger'); return false; }
            if(!confirm('VIP profile permanently remove karna hai? Refresh ke baad wapas nahi aayega.')) return false;
            try{
                const res = await fetch('/api/vip_profile_remove', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profileId:id, id:id, userId:id, phone:phone})});
                const data = await res.json().catch(()=>({}));
                if(!res.ok || data.status === 'error' || data.status === 'blocked') throw new Error(data.message || ('HTTP ' + res.status));
                const removed = Array.isArray(data.removed) ? data.removed : (id ? [id] : []);
                removed.forEach(pid => {
                    try{ if(appState && appState.profiles) delete appState.profiles[pid]; }catch(e){}
                    try{ if(appState && appState.wallets) delete appState.wallets[pid]; }catch(e){}
                });
                if(phone && appState && appState.profiles){
                    Object.keys(appState.profiles).forEach(pid => { const p=appState.profiles[pid]||{}; const d=String(p.phone||p.mobile||'').replace(/[^0-9]/g,''); const ph=String(phone).replace(/[^0-9]/g,''); if(ph && (d===ph || d===('91'+ph) || ('91'+d)===ph)) delete appState.profiles[pid]; });
                }
                try{ localStorage.setItem(LOCAL_KEY, JSON.stringify(appState)); }catch(e){}
                if(appState && appState.activeId && removed.includes(appState.activeId)){ appState.activeId='admin1'; state=appState.profiles.admin1; }
                showRealNotification('✅ VIP Deleted', data.message || 'Profile Firebase se remove ho gaya.', 'success');
                try{ await loadStateFromServer ? loadStateFromServer() : null; }catch(e){}
                try{ render(true); }catch(e){ location.reload(); }
                setTimeout(()=>{ try{ render(true); }catch(e){} }, 800);
                return true;
            }catch(e){ showRealNotification('❌ VIP Delete Failed', e.message || String(e), 'danger'); return false; }
        }
        function titanExtractVipIdFromOnclick(raw){
            raw = String(raw || '');
            const m = raw.match(/(?:delete|remove|drop)[A-Za-z0-9_]*\(['\"]([^'\"]+)['\"]/i) || raw.match(/['\"](client_[^'\"]+|vip_[^'\"]+|user_[^'\"]+|[0-9]{10,15})['\"]/i);
            return m ? m[1] : '';
        }
        ['deleteClient','removeClient','deleteVip','removeVip','deleteUser','removeUser','deleteProfile','removeProfile'].forEach(fn => { window[fn] = function(id){ return titanPersistentVipRemove(id); }; });
        document.addEventListener('click', function(ev){
            try{
                const btn = ev.target && ev.target.closest ? ev.target.closest('button,a') : null;
                if(!btn) return;
                const txt = String(btn.innerText || btn.textContent || '').toLowerCase();
                const onclick = String(btn.getAttribute('onclick') || '');
                const isDelete = txt.includes('delete') || txt.includes('remove') || txt.includes('trash') || onclick.toLowerCase().includes('delete') || onclick.toLowerCase().includes('remove');
                if(!isDelete) return;
                const nav = String(window.mainNav || '').toLowerCase();
                const maybeVip = nav === 'clients' || nav === 'vips' || onclick.toLowerCase().includes('client') || onclick.toLowerCase().includes('vip') || onclick.toLowerCase().includes('profile');
                if(!maybeVip) return;
                const id = titanExtractVipIdFromOnclick(onclick) || btn.dataset.profileId || btn.dataset.userId || btn.dataset.id || '';
                if(!id) return;
                ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation();
                titanPersistentVipRemove(id);
            }catch(e){}
        }, true);
        // /TITAN_VIP_DELETE_UI_FIX_V1
'''

def apply_patch(text):
    if MARKER in text:
        return text, False
    if ANCHOR not in text:
        raise RuntimeError('showToast anchor not found')
    return text.replace(ANCHOR, ANCHOR + BLOCK, 1), True

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); args=ap.parse_args()
    old=TARGET.read_text(encoding='utf-8', errors='replace')
    new, changed=apply_patch(old)
    if not changed:
        print('VIP delete UI fix already present'); return 0
    print('VIP delete UI fix can be applied')
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + '.vip-delete-ui.bak').write_text(old, encoding='utf-8')
        TARGET.write_text(new, encoding='utf-8')
        print('Applied VIP delete UI fix')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
