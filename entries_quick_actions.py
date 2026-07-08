"""Entries tab sticky toggles and quick actions.

Fixes Entry toggles reverting/off by saving entrySettings directly to Firebase.
Adds compact quick actions inside Entries tab without replacing the old Entries UI.
"""


def register_entries_quick_actions(app):
    if getattr(app, "_entries_quick_actions_registered", False):
        return
    app._entries_quick_actions_registered = True

    from flask import jsonify, request
    import datetime

    def G():
        v = app.view_functions.get("index") or next(iter(app.view_functions.values()))
        return getattr(v, "__globals__", {}) or {}

    def now():
        f = G().get("_now_iso_local")
        return f() if callable(f) else datetime.datetime.now().isoformat(timespec="seconds")

    def state():
        f = G().get("migrate_and_get_state")
        return f() if callable(f) else {}

    def defaults():
        f = G().get("_default_entry_settings")
        return f() if callable(f) else {
            "entryParserEnabled": True,
            "groupsOnly": True,
            "strictFormat": True,
            "autoDebitWallet": True,
            "marketTimingEnabled": True,
            "riskLimitEnabled": True,
            "autoLinkUnknownSender": True,
            "autoCreatePendingProfiles": True,
            "requireProfileApproval": True,
            "duplicatePolicy": "sender_market_type_digits_date",
            "marketCloseTimes": {},
            "marketTargets": {},
            "marketEntryEnabled": {},
            "allowUnmappedMarkets": True,
            "entryFormatTemplate": "MARKET:{market} TYPE:{type} DIGITS:{digits} PAR DIGIT:{parDigit} TOTAL:{total}",
        }

    def normalized_settings(s):
        base = defaults()
        cur = s.get("entrySettings") if isinstance(s.get("entrySettings"), dict) else {}
        out = dict(base)
        out.update(cur)
        if not isinstance(out.get("marketCloseTimes"), dict): out["marketCloseTimes"] = base.get("marketCloseTimes", {})
        if not isinstance(out.get("marketTargets"), dict): out["marketTargets"] = {}
        if not isinstance(out.get("marketEntryEnabled"), dict): out["marketEntryEnabled"] = {}
        return out

    def counts(s):
        rows = s.get("entries") if isinstance(s.get("entries"), list) else []
        out = {"total": len(rows), "accepted": 0, "pending": 0, "blocked": 0, "rejected": 0}
        for e in rows:
            if not isinstance(e, dict): continue
            st = str(e.get("status") or "pending").lower()
            if st in out: out[st] += 1
            elif st in ("block", "failed", "error"): out["blocked"] += 1
        return out

    def save_entry_settings(s, settings):
        settings["updatedAt"] = now()
        s["entrySettings"] = settings
        put = G().get("_firebase_put_top_level_children")
        if callable(put):
            put(s, {"entrySettings": settings}, audit=False)
            return True
        return False

    @app.route("/api/entries_quick_actions", methods=["GET"])
    def entries_quick_get():
        s = state()
        return jsonify({"status": "success", "entrySettings": normalized_settings(s), "counts": counts(s)})

    @app.route("/api/entries_quick_actions", methods=["POST"])
    def entries_quick_save():
        payload = request.get_json(silent=True) or {}
        s = state()
        settings = normalized_settings(s)
        for key in [
            "entryParserEnabled", "groupsOnly", "strictFormat", "autoDebitWallet",
            "marketTimingEnabled", "riskLimitEnabled", "autoLinkUnknownSender",
            "autoCreatePendingProfiles", "requireProfileApproval", "allowUnmappedMarkets"
        ]:
            if key in payload:
                settings[key] = bool(payload.get(key))
        if "duplicatePolicy" in payload:
            settings["duplicatePolicy"] = str(payload.get("duplicatePolicy") or settings.get("duplicatePolicy") or "sender_market_type_digits_date")
        if not save_entry_settings(s, settings):
            return jsonify({"status": "error", "message": "Firebase save helper missing"}), 500
        return jsonify({"status": "success", "entrySettings": settings, "counts": counts(s), "sticky": True})

    @app.after_request
    def entries_quick_ui(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "entries-quick-actions-v1" in html or "</body>" not in html.lower():
                return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + UI + html[i:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception:
            pass
        return resp


UI = r'''
<style id="entries-quick-actions-v1-style">
#eqa{margin:10px 12px;padding:12px;border-radius:18px;background:#101d2f;border:1px solid rgba(42,171,238,.30);color:#eef6ff;font-family:Inter,Arial,sans-serif;box-shadow:0 10px 24px rgba(0,0,0,.20)}#eqa .top{display:flex;justify-content:space-between;gap:8px;align-items:center}#eqa .title{font-weight:1000;font-size:14px}#eqa .sub{font-size:10px;color:#91afd1;margin-top:3px}#eqa .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}#eqa label{display:flex;align-items:center;justify-content:space-between;gap:8px;background:#07111f;border:1px solid #243e5f;border-radius:14px;padding:10px;font-size:11px;font-weight:900}#eqa button{border:0;border-radius:12px;padding:9px 10px;background:#2aabee;color:white;font-weight:900}#eqa .save{background:#00c26f;color:#062013}#eqa .mini{font-size:10px;color:#91afd1;margin-top:8px}.eqaBtns{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-top:9px}.eqaBtns button{background:#172d42;font-size:10px}
</style>
<script id="entries-quick-actions-v1">
(function(){if(window.__EQA1)return;window.__EQA1=true;const API='/api/entries_quick_actions';let settings={};function q(s){return document.querySelector(s)}function gv(n){try{return Function('return typeof '+n+'!=="undefined"?'+n+':""')()}catch(e){return''}}function inEntries(){return String(gv('mainNav')||'').toLowerCase()==='entries'}function hdr(){let h={'Content-Type':'application/json'};try{let t=localStorage.getItem('TITAN_ADMIN_TOKEN')||'';if(t)h['X-Titan-Admin-Token']=t}catch(e){}return h}function root(){return q('main')||q('#app')||document.body}function html(){return '<div id="eqa"><div class="top"><div><div class="title">⚡ Entries Quick Actions</div><div id="eqaStat" class="sub">Loading...</div></div><div><button id="eqaRefresh">Refresh</button> <button id="eqaSave" class="save">Save</button></div></div><div class="grid"><label>Entry Parser <input id="eqaParser" type="checkbox"></label><label>Groups Only <input id="eqaGroups" type="checkbox"></label><label>Strict Format <input id="eqaStrict" type="checkbox"></label><label>Auto Debit Wallet <input id="eqaWallet" type="checkbox"></label><label>Market Timing <input id="eqaTiming" type="checkbox"></label><label>Risk Limit <input id="eqaRisk" type="checkbox"></label><label>Auto Profile <input id="eqaProfile" type="checkbox"></label><label>Approval Required <input id="eqaApproval" type="checkbox"></label></div><div class="eqaBtns"><button id="eqaAllOn">All ON</button><button id="eqaSafeMode">Safe Mode</button><button id="eqaForceSync">Force Sync</button></div><div class="mini">Toggle OFF hone ka bug fix: ye direct Firebase entrySettings save karta hai.</div></div>'}function ensure(){if(!inEntries()){let x=q('#eqa');if(x)x.remove();return}if(!q('#eqa')){root().insertAdjacentHTML('afterbegin',html());bind();load()}}function bind(){q('#eqaRefresh').onclick=load;q('#eqaSave').onclick=save;q('#eqaAllOn').onclick=()=>{['eqaParser','eqaGroups','eqaStrict','eqaWallet','eqaTiming','eqaRisk','eqaProfile','eqaApproval'].forEach(id=>q('#'+id).checked=true);save()};q('#eqaSafeMode').onclick=()=>{q('#eqaParser').checked=true;q('#eqaGroups').checked=true;q('#eqaStrict').checked=true;q('#eqaWallet').checked=true;q('#eqaTiming').checked=true;q('#eqaRisk').checked=true;q('#eqaProfile').checked=true;q('#eqaApproval').checked=true;save()};q('#eqaForceSync').onclick=()=>{try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){};load()}}function apply(){if(!q('#eqa'))return;q('#eqaParser').checked=!!settings.entryParserEnabled;q('#eqaGroups').checked=!!settings.groupsOnly;q('#eqaStrict').checked=!!settings.strictFormat;q('#eqaWallet').checked=!!settings.autoDebitWallet;q('#eqaTiming').checked=!!settings.marketTimingEnabled;q('#eqaRisk').checked=!!settings.riskLimitEnabled;q('#eqaProfile').checked=!!settings.autoCreatePendingProfiles;q('#eqaApproval').checked=!!settings.requireProfileApproval}async function load(){try{let r=await fetch(API+'?_='+Date.now(),{cache:'no-store',headers:hdr()});let j=await r.json();settings=j.entrySettings||{};let c=j.counts||{};let st=q('#eqaStat');if(st)st.textContent='Total '+(c.total||0)+' · Accepted '+(c.accepted||0)+' · Pending '+(c.pending||0)+' · Blocked '+(c.blocked||0);apply()}catch(e){let st=q('#eqaStat');if(st)st.textContent='Load failed'}}async function save(){try{let body={entryParserEnabled:q('#eqaParser').checked,groupsOnly:q('#eqaGroups').checked,strictFormat:q('#eqaStrict').checked,autoDebitWallet:q('#eqaWallet').checked,marketTimingEnabled:q('#eqaTiming').checked,riskLimitEnabled:q('#eqaRisk').checked,autoCreatePendingProfiles:q('#eqaProfile').checked,requireProfileApproval:q('#eqaApproval').checked};if(window.__TitanRealtime)window.__TitanRealtime.pause(1600);let r=await fetch(API,{method:'POST',headers:hdr(),body:JSON.stringify(body)});let j=await r.json();if(j.status!=='success')throw Error(j.message||'Save failed');settings=j.entrySettings||settings;apply();try{document.dispatchEvent(new CustomEvent('titan:force-sync'))}catch(e){}if(typeof showRealNotification==='function')showRealNotification('✅ Entries Saved','Quick actions updated','success');else alert('✅ Entries quick actions saved')}catch(e){alert('❌ '+e.message)}}document.addEventListener('click',()=>setTimeout(ensure,150),true);setInterval(ensure,1200);setTimeout(ensure,800)})();
</script>
'''
