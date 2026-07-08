"""Proper Ledger Market Settings drawer.
Small card in Ledger, drawer on click, save one market at a time."""


def register_ledger_market_drawer(app):
    if getattr(app, "_ledger_market_drawer_registered", False):
        return
    app._ledger_market_drawer_registered = True
    from flask import jsonify, request
    import datetime, re

    def g():
        v = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(v, "__globals__", {}) or {}
    def now():
        f = g().get("_now_iso_local")
        return f() if callable(f) else datetime.datetime.now().isoformat(timespec="seconds")
    def hh(v):
        m = re.match(r"^(\d{1,2}):(\d{2})$", str(v or "").strip())
        if not m: return ""
        h, mi = int(m.group(1)), int(m.group(2))
        return f"{h:02d}:{mi:02d}" if 0 <= h <= 23 and 0 <= mi <= 59 else ""
    def slug(v):
        return re.sub(r"[^a-z0-9]+", "_", str(v or "").lower()).strip("_") or "market"
    def state():
        f = g().get("migrate_and_get_state")
        return f() if callable(f) else {}
    def reg(s):
        f = g().get("_ensure_market_registry")
        return f(s) if callable(f) else s.setdefault("marketRegistry", {"items": {}})
    def rows(s):
        out = []
        for it in (reg(s).get("items") or {}).values():
            if not isinstance(it, dict) or it.get("deleted"): continue
            t = it.get("times") if isinstance(it.get("times"), dict) else {}
            st = it.get("stages") if isinstance(it.get("stages"), dict) else {}
            name = str(it.get("displayName") or it.get("name") or "").strip().upper()
            out.append({"id": str(it.get("id") or slug(name)), "name": name, "enabled": it.get("enabled", True) is not False, "ledgerEnabled": it.get("ledgerEnabled", True) is not False, "resultEnabled": it.get("resultEnabled", True) is not False, "autoPassFailEnabled": it.get("autoPassFailEnabled", True) is not False, "scheduleEnabled": it.get("scheduleEnabled", True) is not False, "autoResultEnabled": it.get("autoResultEnabled", True) is not False, "openStage": st.get("open", True) is not False, "closeStage": st.get("close", True) is not False, "openTime": hh(t.get("open")), "closeTime": hh(t.get("close"))})
        out.sort(key=lambda r: (r.get("openTime") or "99:99", r.get("name") or ""))
        return out
    def summ(rs):
        return {"total": len(rs), "active": sum(1 for r in rs if r.get("enabled")), "ledger": sum(1 for r in rs if r.get("enabled") and r.get("ledgerEnabled")), "auto": sum(1 for r in rs if r.get("enabled") and r.get("autoPassFailEnabled"))}
    def persist(s, r):
        entry = s.setdefault("entrySettings", {})
        mt = entry.setdefault("marketCloseTimes", {})
        for it in (r.get("items") or {}).values():
            if not isinstance(it, dict) or it.get("deleted"): continue
            name = str(it.get("displayName") or it.get("name") or "").strip().upper()
            t = it.get("times") if isinstance(it.get("times"), dict) else {}
            if name and t.get("open"): mt[name + " OPEN"] = t.get("open")
            if name and t.get("close"): mt[name] = t.get("close"); mt[name + " CLOSE"] = t.get("close")
        r["updatedAt"] = now(); s["marketRegistry"] = r
        put = g().get("_firebase_put_top_level_children")
        if callable(put): put(s, {"marketRegistry": r, "entrySettings": entry}, audit=False); return True
        return False

    @app.route("/api/ledger_market_drawer", methods=["GET"])
    def lmd_get():
        rs = rows(state())
        return jsonify({"status":"success", "markets": rs, "summary": summ(rs)})

    @app.route("/api/ledger_market_drawer", methods=["POST"])
    def lmd_save():
        data = request.get_json(silent=True) or {}
        row = data.get("market") if isinstance(data.get("market"), dict) else data
        s = state(); r = reg(s); items = r.setdefault("items", {})
        mid = str(row.get("id") or "").strip(); name = str(row.get("name") or "").strip().upper()
        if not mid and name: mid = slug(name)
        if not mid: return jsonify({"status":"error", "message":"Market id missing"}), 400
        it = items.get(mid) if isinstance(items.get(mid), dict) else {"id": mid, "name": name, "displayName": name, "aliases": [name], "createdAt": now()}
        items[mid] = it
        if name: it["name"] = name; it["displayName"] = name; it.setdefault("aliases", [name])
        for k in ("enabled","ledgerEnabled","resultEnabled","autoPassFailEnabled","scheduleEnabled","autoResultEnabled"):
            if k in row: it[k] = bool(row.get(k))
        st = it.setdefault("stages", {}); tm = it.setdefault("times", {})
        if "openStage" in row: st["open"] = bool(row.get("openStage"))
        if "closeStage" in row: st["close"] = bool(row.get("closeStage"))
        if "openTime" in row: tm["open"] = hh(row.get("openTime"))
        if "closeTime" in row: tm["close"] = hh(row.get("closeTime"))
        it["deleted"] = False; it["archived"] = False; it["manualSaveLocked"] = True; it["settingsLocked"] = True; it["updatedAt"] = now()
        if not persist(s, r): return jsonify({"status":"error", "message":"Firebase save helper missing"}), 500
        rs = rows(s)
        return jsonify({"status":"success", "markets": rs, "summary": summ(rs)})

    @app.after_request
    def lmd_ui(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"): return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower(): return resp
            html = resp.get_data(as_text=True)
            if not html or "ledger-market-drawer-perfect-v1" in html or "</body>" not in html.lower(): return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + UI + html[i:]
            resp.set_data(html); resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception: pass
        return resp

UI = r'''
<style id="ledger-market-drawer-perfect-v1-style">#lmdPCard{margin:10px 12px;padding:12px;border-radius:18px;background:#101d2f;border:1px solid rgba(42,171,238,.32);color:#eef6ff;font-family:Inter,Arial,sans-serif}#lmdPCard b{font-size:14px}#lmdPCard small,.lmdPMini{color:#91afd1;font-size:10px}#lmdPCard button,.lmdPSave,.lmdPClose{border:0;border-radius:12px;padding:9px 11px;font-weight:900;background:#2aabee;color:#fff}.lmdPOver{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.55);display:none}.lmdPOver.on{display:block}.lmdPSheet{position:absolute;left:0;right:0;bottom:0;max-height:92vh;overflow:auto;background:#07111f;color:#eef6ff;border-radius:24px 24px 0 0;padding:14px;font-family:Inter,Arial,sans-serif}.lmdPHead{position:sticky;top:0;background:#07111f;padding-bottom:10px}.lmdPTitle{font-weight:1000;font-size:18px}.lmdPSearch{width:100%;box-sizing:border-box;margin:10px 0;background:#0d1e2d;border:1px solid #294564;border-radius:14px;padding:11px;color:#fff}.lmdPRow{background:#101d2f;border:1px solid #243e5f;border-radius:16px;padding:12px;margin:10px 0}.lmdPName{font-size:13px;font-weight:1000}.lmdPGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.lmdPGrid label{font-size:10px;color:#d6eeff;display:flex;gap:6px}.lmdPGrid input[type=time]{width:100%;box-sizing:border-box;background:#07111f;border:1px solid #263b59;border-radius:10px;color:#fff;padding:8px}.lmdPSave{background:#00c26f;color:#062013;width:100%;margin-top:10px}.lmdPClose{float:right;background:#263b59}</style>
<script id="ledger-market-drawer-perfect-v1">(function(){if(window.__LMDP)return;window.__LMDP=true;const API='/api/ledger_market_drawer';let rows=[];function q(s){return document.querySelector(s)}function qa(s){return Array.from(document.querySelectorAll(s))}function gv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return''}}function inLedger(){return String(gv('mainNav')||'').toLowerCase()==='ledger'}function root(){return q('main')||q('#app')||document.body}function hdr(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}function stat(s){return (s.active||0)+'/'+(s.total||0)+' active · Ledger '+(s.ledger||0)+' · Auto '+(s.auto||0)}function ensure(){if(!inLedger()){let c=q('#lmdPCard');if(c)c.remove();return}if(q('#lmdPCard'))return;root().insertAdjacentHTML('afterbegin','<div id="lmdPCard"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><div><b>🏪 Market Settings</b><br><small id="lmdPStat">Loading...</small></div><button id="lmdPOpen">Open</button></div></div><div id="lmdPOver" class="lmdPOver"><div class="lmdPSheet"><div class="lmdPHead"><button id="lmdPClose" class="lmdPClose">Close</button><div class="lmdPTitle">🏪 Ledger Market Settings</div><div class="lmdPMini">Setup controls moved here. Har market alag save hoga.</div><input id="lmdPSearch" class="lmdPSearch" placeholder="Search market..."></div><div id="lmdPList">Loading...</div></div></div>');q('#lmdPOpen').onclick=open;q('#lmdPClose').onclick=close;q('#lmdPSearch').oninput=render;load(false)}async function load(draw){try{let r=await fetch(API+'?_='+Date.now(),{cache:'no-store',headers:hdr()});let j=await r.json();rows=j.markets||[];let st=q('#lmdPStat');if(st)st.textContent=stat(j.summary||{});if(draw)render()}catch(e){let st=q('#lmdPStat');if(st)st.textContent='Load failed'}}function row(m,i){return '<div class="lmdPRow" data-i="'+i+'"><div class="lmdPName">'+(m.name||'-')+'</div><div class="lmdPMini">Open '+(m.openTime||'-')+' · Close '+(m.closeTime||'-')+'</div><div class="lmdPGrid"><label><input type="checkbox" data-k="enabled" '+(m.enabled?'checked':'')+'>Market ON</label><label><input type="checkbox" data-k="ledgerEnabled" '+(m.ledgerEnabled?'checked':'')+'>Ledger</label><label><input type="checkbox" data-k="resultEnabled" '+(m.resultEnabled?'checked':'')+'>Result</label><label><input type="checkbox" data-k="autoPassFailEnabled" '+(m.autoPassFailEnabled?'checked':'')+'>Auto Mark</label><label><input type="checkbox" data-k="scheduleEnabled" '+(m.scheduleEnabled?'checked':'')+'>Schedule</label><label><input type="checkbox" data-k="autoResultEnabled" '+(m.autoResultEnabled?'checked':'')+'>Auto Result</label><div><div class="lmdPMini">Open</div><input type="time" data-k="openTime" value="'+(m.openTime||'')+'"></div><div><div class="lmdPMini">Close</div><input type="time" data-k="closeTime" value="'+(m.closeTime||'')+'"></div></div><button class="lmdPSave" data-save="'+i+'">Save This Market</button></div>'}function render(){let t=(q('#lmdPSearch')?.value||'').toUpperCase();let box=q('#lmdPList');if(!box)return;box.innerHTML=rows.map((m,i)=>!t||String(m.name).includes(t)?row(m,i):'').join('')||'<div class="lmdPMini">No market found</div>';qa('[data-save]').forEach(b=>b.onclick=()=>save(Number(b.dataset.save)))}function collect(i){let el=q('.lmdPRow[data-i="'+i+'"]'),m=Object.assign({},rows[i]||{});if(!el)return m;qa('input',el).forEach(x=>{let k=x.dataset.k;if(k)m[k]=x.type==='checkbox'?!!x.checked:x.value});rows[i]=m;return m}async function save(i){try{let m=collect(i);if(window.__TitanRealtime)window.__TitanRealtime.pause(1600);let r=await fetch(API,{method:'POST',headers:hdr(),body:JSON.stringify({market:m})});let j=await r.json();if(j.status!=='success')throw Error(j.message||'Save failed');rows=j.markets||rows;render();let st=q('#lmdPStat');if(st)st.textContent=stat(j.summary||{});if(typeof showRealNotification==='function')showRealNotification('✅ Saved',m.name+' saved','success');else alert('✅ '+m.name+' saved');try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}}catch(e){alert('❌ '+e.message)}}function open(){q('#lmdPOver')?.classList.add('on');load(true)}function close(){q('#lmdPOver')?.classList.remove('on')}document.addEventListener('click',()=>setTimeout(ensure,150),true);setInterval(ensure,1200);setTimeout(ensure,800)})();</script>
'''
