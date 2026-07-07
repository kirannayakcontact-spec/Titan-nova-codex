from pathlib import Path
import argparse
from titan_runtime_files import ensure_runtime_file

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'flask_app.py'
ensure_runtime_file('flask_app.py')
MARKER = 'TITAN_MCP_V1'
ANCHOR = """@app.route('/api/config_migration_status')
def api_config_migration_status():
    \"\"\"v11 config cleanup status. Values are redacted; endpoint is admin-gated by before_request.\"\"\"
    return jsonify(_config_migration_report())"""

BLOCK = r'''

# TITAN_MCP_V1
@app.route('/market_control_pro')
@admin_required
def titan_mcp_page():
    return """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>Market Control Pro</title><style>body{margin:0;background:#0b141a;color:#e9edef;font-family:Arial,sans-serif}.top{position:sticky;top:0;background:#075e54;padding:14px}.wrap{padding:12px;max-width:1050px;margin:auto}.card{background:#202c33;border:1px solid #2a3942;border-radius:16px;padding:12px;margin:10px 0}input,textarea{width:100%;box-sizing:border-box;background:#111b21;color:#fff;border:1px solid #3b4a54;border-radius:12px;padding:10px;margin:5px 0}button{border:0;border-radius:999px;background:#00a884;color:#06140f;font-weight:900;padding:10px 12px;margin:4px}.off{background:#2a3942;color:#e9edef}.warn{background:#ffd166}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}.pill{display:inline-block;background:#12372f;color:#25d366;border:1px solid #315a52;border-radius:999px;padding:3px 8px;font-size:12px;margin:2px}.muted{color:#8696a0;font-size:12px}.tog{display:flex;justify-content:space-between;background:#111b21;border-radius:10px;padding:8px;margin:5px 0}.tog input{width:auto}.toast{position:fixed;bottom:12px;left:12px;right:12px;background:#111b21;border:1px solid #00a884;border-radius:14px;padding:12px;display:none}</style></head><body><div class='top'><b>🟢 Market Control Pro</b><div class='muted'>Add market, save time, roles, groups, ON/OFF controls.</div></div><div class='wrap'><div class='card'><b>Add / Update Market</b><div class='grid'><input id='n' placeholder='Market name'><input id='w' placeholder='Website name'><input id='o' placeholder='Open HH:MM'><input id='c' placeholder='Close HH:MM'><input id='u' placeholder='Chart URL optional'></div><button onclick='addM()'>Save Market</button><button class='off' onclick='loadM()'>Refresh</button><button class='off' onclick="location.href='/'">Dashboard</button></div><input id='q' oninput='draw()' placeholder='Search market'><div id='list'></div></div><div id='toast' class='toast'></div><script>let ms=[];function t(x){toast.textContent=x;toast.style.display='block';setTimeout(()=>toast.style.display='none',3000)}function v(id){return document.getElementById(id).value.trim()}function targets(x){return String(x||'').split(/[\n,]+/).map(s=>s.trim()).filter(Boolean)}async function post(b){let r=await fetch('/api/market_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});let j=await r.json().catch(()=>({}));if(!r.ok||j.status==='error')throw Error(j.message||'save failed');return j}function items(j){let reg=j.marketRegistry||j.registry||j;return Object.values((reg&&reg.items)||j.items||{}).filter(x=>x&&typeof x==='object')}async function loadM(){try{let r=await fetch('/api/market_registry?ts='+Date.now(),{cache:'no-store'});ms=items(await r.json());draw();t('Loaded '+ms.length)}catch(e){t(e.message)}}async function addM(){try{await post({action:'direct_add_full',name:v('n'),websiteName:v('w')||v('n'),openTime:v('o'),closeTime:v('c'),chartUrl:v('u'),ledgerEnabled:true,resultEnabled:true,autoResultEnabled:true,autoPassFailEnabled:true,scheduleEnabled:true,entryEnabled:true});t('Market saved');loadM()}catch(e){t(e.message)}}async function flag(id,f,x){try{await post({action:'set_flag',id:id,field:f,value:x});t('Saved '+f);loadM()}catch(e){t(e.message)}}async function tm(id,s,x){try{await post({action:'update_time',id:id,stage:s,value:x});t('Time saved');loadM()}catch(e){t(e.message)}}async function role(id,r){try{await post({action:'set_role_targets',id:id,role:r,targets:targets(document.getElementById(id+'_'+r).value)});t('Targets saved');loadM()}catch(e){t(e.message)}}async function act(id,a){try{await post({action:a,id:id});t('Market '+a);loadM()}catch(e){t(e.message)}}function on(x){return x!==false}function sw(m,f,l){return `<label class='tog'><span>${l}</span><input type='checkbox' ${on(m[f])?'checked':''} onchange="flag('${m.id}','${f}',this.checked)"></label>`}function rb(m,r,l){let val=(Array.isArray(m[r+'Targets'])?m[r+'Targets']:[]).join('\n');return `<div><b>${l}</b><textarea id='${m.id}_${r}'>${val}</textarea><button class='off' onclick="role('${m.id}','${r}')">Save ${l}</button></div>`}function card(m){let time=m.times||{};let name=m.displayName||m.name||m.id;return `<div class='card'><h3>${name}</h3><div><span class='pill'>${on(m.enabled)?'ACTIVE':'OFF'}</span><span class='pill'>${on(m.resultEnabled)?'RESULT':'NO RESULT'}</span></div><div class='grid'><input value='${time.open||''}' onchange="tm('${m.id}','open',this.value)" placeholder='Open'><input value='${time.close||''}' onchange="tm('${m.id}','close',this.value)" placeholder='Close'></div>${sw(m,'enabled','Market Active')}${sw(m,'ledgerEnabled','Ledger')}${sw(m,'resultEnabled','Results')}${sw(m,'entryEnabled','Entries')}${sw(m,'scheduleEnabled','Schedule')}${sw(m,'autoResultEnabled','Auto Result')}${sw(m,'autoPassFailEnabled','Auto Pass/Fail')}<button class='warn' onclick="act('${m.id}','archive')">Archive/OFF</button><button class='off' onclick="act('${m.id}','restore')">Restore</button><div class='grid'>${rb(m,'entry','Entry Group')}${rb(m,'result','Result Group')}${rb(m,'forward','Forward Group')}${rb(m,'schedule','Schedule Group')}${rb(m,'bookie','Bookie/Admin Group')}</div></div>`}function draw(){let q=v('q').toUpperCase();list.innerHTML=ms.filter(m=>!q||String(m.name||m.displayName||m.id).toUpperCase().includes(q)).map(card).join('')||'<div class=card>No market</div>'}loadM()</script></body></html>"""
# /TITAN_MCP_V1
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
        print('MCP patch already present'); return 0
    print('MCP patch can be applied')
    if args.apply:
        TARGET.with_suffix(TARGET.suffix + '.mcp.bak').write_text(old, encoding='utf-8')
        TARGET.write_text(new, encoding='utf-8')
        print('Applied MCP patch')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
