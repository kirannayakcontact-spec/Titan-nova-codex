"""Safe Titan Nova patch layer loaded by flask_app.py."""


def register_titan_codex_stability(app):
    if getattr(app, "_titan_codex_stability_registered", False):
        return
    app._titan_codex_stability_registered = True

    from flask import jsonify, request
    import json, os, time, copy

    VERSION = "2026-07-09-codex-clean-bugs-v1"
    KEYS = {
        "profiles": dict, "wallets": dict, "walletTransactions": list, "entries": list,
        "payments": list, "withdrawals": list, "paymentOutbox": list, "auditLog": list,
        "resultRecords": dict, "settlementRecords": dict, "ledgerSchedules": dict,
        "marketRegistry": dict, "entrySettings": dict, "riskSettings": dict,
        "settlementSettings": dict, "loadForwarder": dict, "loadForwarderOutbox": list,
        "whatsappSafetySettings": dict, "whatsappSafetyTargets": dict, "deletedProfiles": dict,
    }
    MARKETS = ["SRIDEVI DAY","TIME BAZAR","MADHUR DAY","MILAN DAY","RAJDHANI DAY","SUPREME DAY","KALYAN","SRIDEVI NIGHT","MADHUR NIGHT","SUPREME NIGHT","MILAN NIGHT","RAJDHANI NIGHT","KALYAN NIGHT","MAIN BAZAR"]

    def G():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for v in app.view_functions.values():
                g = getattr(v, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "load_from_firebase" in g:
                    return g
        except Exception:
            pass
        return {}

    def clone(x):
        try: return json.loads(json.dumps(x, ensure_ascii=False, default=str))
        except Exception:
            try: return copy.deepcopy(x)
            except Exception: return x

    def get_state():
        g, errors = G(), []
        for name in ("migrate_and_get_state", "load_from_firebase"):
            fn = g.get(name)
            if callable(fn):
                try:
                    st = fn()
                    if isinstance(st, dict): return st, {"source": name, "errors": errors}
                    errors.append(f"{name} returned {type(st).__name__}")
                except Exception as e:
                    errors.append(f"{name}: {e}")
        return {}, {"source": "empty", "errors": errors}

    def save_state(st):
        g, errors = G(), []
        for name in ("save_to_firebase", "_firebase_guarded_root_save", "_safe_save_to_firebase_put"):
            fn = g.get(name)
            if callable(fn):
                try: return True, {"writer": name, "result": str(fn(st))[:180], "errors": errors}
                except Exception as e: errors.append(f"{name}: {e}")
        return False, {"writer": "missing", "errors": errors}

    def ensure(st):
        if not isinstance(st, dict): st = {}
        repairs = []
        for k, typ in KEYS.items():
            if not isinstance(st.get(k), typ):
                st[k] = {} if typ is dict else []
                repairs.append(k)
        prof = st.setdefault("profiles", {})
        if "admin1" not in prof:
            prof["admin1"] = {"name":"MASTER ADMIN 1","phone":"","config":{},"dayRecords":{}}
            repairs.append("profiles.admin1")
        for aid, name in (("admin2","MASTER ADMIN 2"),("admin3","MASTER ADMIN 3")):
            if aid not in prof:
                base = clone(prof.get("admin1") or {}) if isinstance(prof.get("admin1"), dict) else {}
                base["name"] = name; prof[aid] = base; repairs.append("profiles." + aid)
        ss = st.setdefault("settlementSettings", {})
        pm = ss.setdefault("payoutMultipliers", {}) if isinstance(ss, dict) else {}
        if not isinstance(pm, dict): ss["payoutMultipliers"] = pm = {}; repairs.append("payoutMultipliers")
        defaults = {"ank":9.5,"jodi":95,"penel":150,"panel":150,"patti":150}
        for k, v in defaults.items():
            try: old = float(pm.get(k))
            except Exception: old = None
            if old is None or (k == "jodi" and old < 50):
                pm[k] = v; repairs.append("payout." + k)
        ss.setdefault("enabled", True); ss.setdefault("includeSummaryInResultMessage", True)
        es = st.setdefault("entrySettings", {})
        if not isinstance(es, dict): st["entrySettings"] = es = {}; repairs.append("entrySettings")
        mct = es.setdefault("marketCloseTimes", {})
        if not isinstance(mct, dict): es["marketCloseTimes"] = mct = {}; repairs.append("marketCloseTimes")
        for m in MARKETS:
            for n in (m, m + " OPEN", m + " CLOSE"): mct.setdefault(n, "")
        es.setdefault("entryParserEnabled", True); es.setdefault("marketTimingEnabled", True)
        es.setdefault("autoCreatePendingProfiles", True); es.setdefault("requireProfileApproval", True)
        reg = st.setdefault("marketRegistry", {})
        if not isinstance(reg, dict): st["marketRegistry"] = reg = {}; repairs.append("marketRegistry")
        reg.setdefault("items", {}); reg.setdefault("deletedMarketIds", []); reg.setdefault("version", VERSION)
        lf = st.setdefault("loadForwarder", {})
        if not isinstance(lf, dict): st["loadForwarder"] = lf = {}; repairs.append("loadForwarder")
        lf.setdefault("enabled", False); lf.setdefault("scheduleTime", ""); lf.setdefault("selectedMarket", "")
        lf.setdefault("targets", []); lf.setdefault("gameTypes", ["ANK","JODI","PENEL"])
        st["codexStabilityRepair"] = {"version": VERSION, "checkedAtMs": int(time.time()*1000), "repairs": repairs[-80:]}
        return st, repairs

    def count(st):
        st = st if isinstance(st, dict) else {}
        def ln(v):
            try: return len(v) if isinstance(v, (dict, list)) else 0
            except Exception: return 0
        reg = st.get("marketRegistry") if isinstance(st.get("marketRegistry"), dict) else {}
        return {"profiles":ln(st.get("profiles")),"wallets":ln(st.get("wallets")),"entries":ln(st.get("entries")),"withdrawals":ln(st.get("withdrawals")),"paymentOutbox":ln(st.get("paymentOutbox")),"ledgerSchedules":ln(st.get("ledgerSchedules")),"resultDays":ln(st.get("resultRecords")),"marketRegistryItems":ln(reg.get("items")),"auditLog":ln(st.get("auditLog"))}

    @app.route("/api/titan-codex/status")
    def titan_codex_status():
        st, meta = get_state(); preview, repairs = ensure(clone(st)); g = G()
        return jsonify({"status":"success","version":VERSION,"firebaseUrlConfigured":bool(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL")),"firebaseUrlTail":str(os.environ.get("FIREBASE_URL") or os.environ.get("FIREBASE_DB_URL") or "")[-80:],"stateSource":meta,"stateSummary":count(st),"repairPreview":repairs[-80:],"legacyGlobalsAvailable":[k for k in ("migrate_and_get_state","save_to_firebase","load_from_firebase","_firebase_guarded_root_save") if callable(g.get(k))],"routes":len(getattr(app,"view_functions",{}) or {})})

    @app.route("/api/titan-codex/repair-state", methods=["POST"])
    def titan_codex_repair_state():
        st, meta = get_state(); before = count(st); fixed, repairs = ensure(clone(st)); ok, save = save_state(fixed)
        return jsonify({"status":"success" if ok else "error","version":VERSION,"stateSource":meta,"before":before,"after":count(fixed),"repairs":repairs[-120:],"save":save}), (200 if ok else 500)

    @app.after_request
    def titan_codex_inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"): return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower(): return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-codex-stability-v1" in html or "</body>" not in html.lower(): return resp
            i = html.lower().rfind("</body>"); html = html[:i] + SCRIPT + html[i:]
            resp.set_data(html); resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception: pass
        return resp

    print("✅ Titan Codex stability patch loaded", VERSION)


SCRIPT = r'''
<script id="titan-codex-stability-v1">
(function(){if(window.__TITAN_CODEX_STABILITY_V1__)return;window.__TITAN_CODEX_STABILITY_V1__=true;const V='2026-07-09-codex-clean-bugs-v1';let last=0;function n(){return Date.now()}function nav(){try{return String(Function('return typeof mainNav!=="undefined"?mainNav:""')()||'').toLowerCase()}catch(e){return''}}function tok(){const h={'Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}function bar(t,e){try{let x=document.getElementById('titanCodexStabilityBanner');if(!x){x=document.createElement('div');x.id='titanCodexStabilityBanner';x.style.cssText='position:fixed;left:10px;right:10px;bottom:10px;z-index:2147483647;background:#152235;color:#fff;border:1px solid rgba(42,171,238,.45);border-radius:14px;padding:10px 12px;font:800 12px Arial;box-shadow:0 10px 30px #0006;display:none';document.body.appendChild(x)}x.style.borderColor=e?'rgba(255,93,93,.65)':'rgba(42,171,238,.45)';x.innerHTML=String(t||'Titan Codex active');x.style.display='block';clearTimeout(x._t);x._t=setTimeout(()=>x.style.display='none',e?9000:2200)}catch(_){}}function err(m,s){try{const a=JSON.parse(localStorage.getItem('titan.codex.client.errors.v1')||'[]');a.push({at:new Date().toISOString(),version:V,nav:nav(),message:String(m||'').slice(0,500),source:String(s||'browser').slice(0,100)});localStorage.setItem('titan.codex.client.errors.v1',JSON.stringify(a.slice(-30)))}catch(_){}bar('⚠️ Titan UI recovery: '+String(m||''),1)}window.addEventListener('error',e=>err(e.message||'Script error',e.filename));window.addEventListener('unhandledrejection',e=>err((e.reason&&e.reason.message)||e.reason||'Promise rejection','promise'));function pause(ms){try{if(window.__TitanRealtime&&typeof window.__TitanRealtime.pause==='function')window.__TitanRealtime.pause(ms||4500)}catch(_){}}['input','change','focusin','keydown','pointerdown','touchstart','click'].forEach(ev=>{try{document.addEventListener(ev,e=>{const t=e&&e.target;if(t&&/^(INPUT|TEXTAREA|SELECT|BUTTON)$/i.test(t.tagName||''))pause(4500)},true)}catch(_){}});function wrap(){try{if(typeof window.render==='function'&&!window.render.__codex){const old=window.render;window.render=function(){try{return old.apply(this,arguments)}catch(e){err('render failed: '+(e.message||e),'render');return false}};window.render.__codex=true}}catch(_){}}function main(){try{return[...document.querySelectorAll('main,#app,#root,#content,#mainContent,.main,.content,.tab-content,.page,.panel')].filter(x=>x&&x.offsetParent!==null).sort((a,b)=>(b.innerText||'').length-(a.innerText||'').length)[0]||document.body}catch(_){return document.body}}function blank(){try{if(/Titan Admin Login|Unlock Admin/i.test(document.body.innerText||''))return false;const x=main(),t=String(x.innerText||'').replace(/\s+/g,' ').trim(),h=String(x.innerHTML||'').replace(/\s+/g,' ').trim();return t.length<25&&h.length<250}catch(_){return false}}function safe(name,args){try{if(typeof window[name]==='function')return window[name].apply(window,args||[])}catch(e){err(name+': '+(e.message||e),name)}}function rescue(){wrap();if(!blank()||n()-last<2200)return;last=n();pause(5000);safe('refreshMarketArrays');safe('render',[true]);setTimeout(()=>{if(!blank()||document.getElementById('titanCodexSetupRescue'))return;let host=main();const d=document.createElement('div');d.id='titanCodexSetupRescue';d.style.cssText='margin:18px;padding:16px;border:1px solid rgba(42,171,238,.35);border-radius:16px;background:#182536;color:#fff;font-family:Arial';d.innerHTML='<b>⚙️ Titan recovery panel</b><p style="opacity:.8">Tab blank tha. Reload/Sync try karo; zarurat pade to state repair run karo.</p><button data-a="r">Reload</button> <button data-a="s">Force Sync</button> <button data-a="fix">Repair State</button><span id="titanCodexRepairOut" style="display:block;margin-top:8px;font-size:12px"></span>';host.appendChild(d);d.onclick=async e=>{const a=e.target&&e.target.getAttribute('data-a'),o=document.getElementById('titanCodexRepairOut');if(!a)return;try{if(a==='r'){safe('refreshMarketArrays');safe('render',[true]);o.textContent='Reload sent'}if(a==='s'){if(window.__TitanRealtime)await window.__TitanRealtime.refresh('codex');o.textContent='Sync done'}if(a==='fix'){o.textContent='Repairing...';const r=await fetch('/api/titan-codex/repair-state',{method:'POST',headers:Object.assign({'Content-Type':'application/json'},tok()),body:'{}'});const j=await r.json().catch(()=>({}));o.textContent=(j.status||'done')+': '+(j.repairs||[]).join(', ').slice(0,220);if(window.__TitanRealtime)window.__TitanRealtime.refresh('repair')}}catch(x){o.textContent='Error: '+(x.message||x)}}},700)}const oldFetch=window.fetch;window.fetch=function(input,init){try{const u=String((typeof input==='string'?input:(input&&input.url))||'');if(/^\/api\//.test(u)||/\/save(\?|$)/.test(u)){init=init||{};const h=Object.assign({},init.headers||{},tok());init=Object.assign({},init,{headers:h,cache:'no-store'})}}catch(_){}return oldFetch.apply(this,[input,init])};setInterval(rescue,1500);setTimeout(rescue,900);setTimeout(()=>bar('✅ Titan Codex stability active'),700);window.__TitanCodexStability={version:V,rescueBlank:rescue,repair:async()=>{const r=await fetch('/api/titan-codex/repair-state',{method:'POST',headers:Object.assign({'Content-Type':'application/json'},tok()),body:'{}'});return r.json()}}})();
</script>
'''
