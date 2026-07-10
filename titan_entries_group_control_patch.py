"""Permanent Entries tab group/contact routing controls."""


def register_titan_entries_group_control(app):
    if getattr(app, "_titan_entries_group_control_registered", False):
        return
    app._titan_entries_group_control_registered = True

    import datetime
    import re
    from flask import jsonify, request

    VERSION = "2026-07-10-entries-inline-group-contact-v3"

    def runtime_globals():
        try:
            if "index" in app.view_functions:
                return getattr(app.view_functions["index"], "__globals__", {}) or {}
            for view in app.view_functions.values():
                g = getattr(view, "__globals__", {}) or {}
                if "migrate_and_get_state" in g or "load_from_firebase" in g:
                    return g
        except Exception:
            pass
        return {}

    def load_state():
        g = runtime_globals()
        for name in ("migrate_and_get_state", "load_from_firebase"):
            fn = g.get(name)
            if callable(fn):
                try:
                    data = fn()
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {}

    def save_child(path, value):
        g = runtime_globals()
        fn = g.get("_firebase_put_child")
        if callable(fn):
            return fn(path, value)
        saver = g.get("save_to_firebase")
        if callable(saver):
            st = load_state()
            cur = st
            for key in path[:-1]:
                cur = cur.setdefault(str(key), {})
            cur[str(path[-1])] = value
            return saver(st)
        return False

    def clean_jid(value):
        return re.sub(r":\d+(?=@)", "", str(value or "").strip())

    def phone(value):
        digits = re.sub(r"\D", "", str(value or ""))
        return digits[-10:] if len(digits) >= 10 else digits

    def defaults():
        return {
            "enabled": True,
            "strictRouting": False,
            "groupIds": {"gameEntry": [], "withdrawal": [], "deposit": []},
            "contactIds": {"gameEntry": [], "withdrawal": [], "deposit": []},
        }

    def normalize(raw):
        raw = raw if isinstance(raw, dict) else {}
        out = defaults()
        out["enabled"] = raw.get("enabled") is not False
        out["strictRouting"] = raw.get("strictRouting") is True or raw.get("strictGroups") is True
        for bucket, cleaner in (("groupIds", clean_jid), ("contactIds", phone)):
            src = raw.get(bucket) if isinstance(raw.get(bucket), dict) else {}
            for key in out[bucket]:
                values = src.get(key, [])
                if not isinstance(values, list):
                    values = []
                out[bucket][key] = sorted({cleaner(v) for v in values if cleaner(v)})
        out["updatedAt"] = str(raw.get("updatedAt") or "")
        return out

    def contact_directory(st):
        contacts = {}
        profiles = st.get("profiles") if isinstance(st.get("profiles"), dict) else {}
        for pid, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            number = phone(profile.get("phone") or profile.get("mobile") or pid)
            if not number:
                continue
            contacts[number] = {
                "id": number,
                "name": str(profile.get("name") or profile.get("userName") or pid or number),
                "approved": str(profile.get("approvalStatus") or "").lower() == "approved",
            }
        gateway = st.get("gatewayContactDirectory")
        if isinstance(gateway, list):
            for item in gateway:
                if not isinstance(item, dict):
                    continue
                number = phone(item.get("phone") or item.get("id") or item.get("jid"))
                if number and number not in contacts:
                    contacts[number] = {"id": number, "name": str(item.get("name") or number), "approved": False}
        return sorted(contacts.values(), key=lambda x: (not x.get("approved"), str(x.get("name") or "").lower()))

    @app.route("/api/entries_group_control/status", methods=["GET"])
    def entries_group_status():
        st = load_state()
        groups = st.get("gatewayGroupDirectory") if isinstance(st.get("gatewayGroupDirectory"), list) else []
        groups = [g for g in groups if isinstance(g, dict) and g.get("id")]
        groups.sort(key=lambda x: str(x.get("name") or x.get("id") or "").lower())
        return jsonify({
            "status": "success",
            "version": VERSION,
            "settings": normalize(st.get("entriesGroupRouting")),
            "groups": groups,
            "contacts": contact_directory(st),
        })

    @app.route("/api/entries_group_control/save", methods=["POST"])
    def entries_group_save():
        cfg = normalize(request.get_json(silent=True) or {})
        cfg["updatedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
        ok = save_child(["entriesGroupRouting"], cfg)
        return jsonify({"status": "success" if ok is not False else "error", "version": VERSION, "settings": cfg}), (200 if ok is not False else 500)

    @app.after_request
    def inject(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-entries-inline-routing-v3" in html or "</body>" not in html.lower():
                return resp
            pos = html.lower().rfind("</body>")
            resp.set_data(html[:pos] + SCRIPT + html[pos:])
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception as exc:
            print("⚠️ Entries inline routing injection failed:", exc)
        return resp

    print("✅ Titan permanent Entries group/contact setup loaded", VERSION)


SCRIPT = r'''
<script id="titan-entries-inline-routing-v3">
(function(){
 if(window.__TITAN_ENTRIES_INLINE_ROUTING_V3__)return;
 window.__TITAN_ENTRIES_INLINE_ROUTING_V3__=true;
 const ID='titanEntriesInlineRoutingPanel';
 let entriesMode=false, loading=false;
 const navNames=/^(LEDGER|VIPS?|WALLET|WITHDRAWAL|PAY|RESULTS?|MARKET|FORWARD|GUARD|BACKUP|HEALTH|AI|AUDIT|SETUP)$/i;
 function h(){const x={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN');if(t)x['X-Titan-Admin-Token']=t}catch(_){}return x}
 function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
 function visible(e){if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>20&&r.height>15&&r.bottom>0&&r.top<innerHeight&&s.display!=='none'&&s.visibility!=='hidden'}
 function isEntriesText(e){return /^(ENTRIES|ENTRY)$/i.test((e?.textContent||'').replace(/\s+/g,' ').trim())}
 function activeEntries(){
   if(entriesMode)return true;
   const marks=['ENTRY MANAGEMENT','BULK ENTRY','TODAY ENTRIES','PENDING ENTRIES','ENTRY INBOX','ENTRY APPROVAL'];
   return [...document.querySelectorAll('h1,h2,h3,h4,section,main,div')].some(e=>visible(e)&&marks.some(m=>(e.textContent||'').toUpperCase().includes(m)));
 }
 document.addEventListener('click',e=>{
   const n=e.target?.closest?.('button,a,[role="tab"],div,span');
   if(isEntriesText(n)){entriesMode=true;setTimeout(mount,80);setTimeout(mount,500);return}
   const b=e.target?.closest?.('button,a,[role="tab"]');
   if(b&&navNames.test((b.textContent||'').trim())){entriesMode=false;document.getElementById(ID)?.remove()}
 },true);
 function selected(id){const e=document.getElementById(id);return e?[...e.selectedOptions].map(o=>o.value):[]}
 function options(rows,chosen,type){return rows.map(x=>`<option value="${esc(x.id)}" ${chosen.includes(x.id)?'selected':''}>${esc(x.name||x.id)}${type==='group'?' ('+Number(x.participants||0)+')':(x.approved?' ✓':'')}</option>`).join('')}
 function selector(title,prefix,key,data,s){
   const groups=options(data.groups||[],s.groupIds?.[key]||[],'group')||'<option disabled>Gateway group sync ka wait ho raha hai</option>';
   const contacts=options(data.contacts||[],s.contactIds?.[key]||[],'contact')||'<option disabled>Koi profile/contact nahi mila</option>';
   return `<div style="background:#101e2d;border:1px solid #ffffff12;border-radius:14px;padding:12px;margin-top:10px"><b>${title}</b><div style="font-size:10px;color:#9db0c0;margin:5px 0">Group select</div><select id="${prefix}-g" multiple size="4" style="width:100%;min-height:105px;background:#07111d;color:#fff;border:1px solid #ffffff22;border-radius:9px;padding:7px">${groups}</select><div style="font-size:10px;color:#9db0c0;margin:9px 0 5px">Contact/User select</div><select id="${prefix}-c" multiple size="4" style="width:100%;min-height:105px;background:#07111d;color:#fff;border:1px solid #ffffff22;border-radius:9px;padding:7px">${contacts}</select></div>`
 }
 async function renderPanel(panel){
   if(loading)return;loading=true;
   try{
     const r=await fetch('/api/entries_group_control/status',{headers:h()});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Load failed');
     const s=d.settings||{};
     panel.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center"><div><b style="font-size:15px">👥 GROUP & CONTACT SETUP</b><div style="font-size:10px;color:#9db0c0;margin-top:3px">Game Entry · Withdrawal · Deposit</div></div><button id="egc-refresh" style="background:#203247;color:#fff;border:0;border-radius:9px;padding:8px">↻ Refresh</button></div><div style="background:#101e2d;border-radius:14px;padding:12px;margin-top:10px"><label style="display:flex;justify-content:space-between"><b>Routing Enabled</b><input id="egc-enabled" type="checkbox" ${s.enabled!==false?'checked':''}></label><label style="display:flex;justify-content:space-between;margin-top:10px"><span>Only selected groups/contacts</span><input id="egc-strict" type="checkbox" ${s.strictRouting===true?'checked':''}></label></div>${selector('🎮 Game Entry','egc-game','gameEntry',d,s)}${selector('💸 Withdrawal Request','egc-withdraw','withdrawal',d,s)}${selector('💳 Deposit Request','egc-deposit','deposit',d,s)}<button id="egc-save" style="width:100%;margin-top:12px;padding:13px;background:#00a884;color:#fff;border:0;border-radius:11px;font-weight:900">SAVE GROUP & CONTACT SETUP</button><div style="font-size:10px;color:#9db0c0;margin-top:8px;text-align:center">Groups: ${(d.groups||[]).length} · Contacts: ${(d.contacts||[]).length}</div>`;
     panel.querySelector('#egc-refresh').onclick=()=>renderPanel(panel);
     panel.querySelector('#egc-save').onclick=async()=>{
       const payload={enabled:panel.querySelector('#egc-enabled').checked,strictRouting:panel.querySelector('#egc-strict').checked,groupIds:{gameEntry:selected('egc-game-g'),withdrawal:selected('egc-withdraw-g'),deposit:selected('egc-deposit-g')},contactIds:{gameEntry:selected('egc-game-c'),withdrawal:selected('egc-withdraw-c'),deposit:selected('egc-deposit-c')}};
       const x=await fetch('/api/entries_group_control/save',{method:'POST',headers:h(),body:JSON.stringify(payload)});const y=await x.json();if(!x.ok||y.status!=='success')throw new Error(y.message||'Save failed');alert('✅ Group & Contact setup save ho gaya');
     };
   }catch(e){panel.innerHTML=`<b>❌ Group & Contact Setup load failed</b><div style="margin-top:8px">${esc(e.message||e)}</div><button id="egc-retry" style="margin-top:10px;padding:10px">Retry</button>`;panel.querySelector('#egc-retry').onclick=()=>renderPanel(panel)}finally{loading=false}
 }
 function target(){
   const candidates=[...document.querySelectorAll('main,[role="main"],section,.content,.page-content,#app>div')].filter(visible);
   return candidates.sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width)[0]||document.body;
 }
 function mount(){
   if(!activeEntries()){document.getElementById(ID)?.remove();return}
   if(document.getElementById(ID))return;
   const p=document.createElement('div');p.id=ID;p.style.cssText='position:relative;z-index:20;background:#132234;color:#fff;border:1px solid #2563eb55;border-radius:16px;padding:13px;margin:12px 8px 90px;font-family:Arial;box-shadow:0 8px 25px #0005';p.innerHTML='<b>Loading Group & Contact Setup...</b>';target().prepend(p);renderPanel(p)
 }
 new MutationObserver(mount).observe(document.documentElement,{childList:true,subtree:true});setInterval(mount,500);setTimeout(mount,200);setTimeout(mount,1200);
 console.log('✅ Permanent Entries Group & Contact setup active');
})();
</script>
'''
