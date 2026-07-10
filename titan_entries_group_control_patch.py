"""Entries tab control for separate WhatsApp source groups."""


def register_titan_entries_group_control(app):
    if getattr(app, "_titan_entries_group_control_registered", False):
        return
    app._titan_entries_group_control_registered = True

    import datetime
    from flask import jsonify, request

    VERSION = "2026-07-10-entries-group-control-v2"

    def globals_map():
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
        g = globals_map()
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
        g = globals_map()
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
        value = str(value or "").strip()
        if not value:
            return ""
        return value.split(":")[0] + ("@" + value.split("@", 1)[1] if "@" in value else "") if ":" in value.split("@", 1)[0] else value

    def defaults():
        return {
            "enabled": True,
            "strictGroups": False,
            "allowPrivate": {"gameEntry": True, "withdrawal": True, "deposit": True},
            "groupIds": {"gameEntry": [], "withdrawal": [], "deposit": []},
        }

    def normalize(raw):
        raw = raw if isinstance(raw, dict) else {}
        out = defaults()
        out["enabled"] = raw.get("enabled") is not False
        out["strictGroups"] = raw.get("strictGroups") is True
        if isinstance(raw.get("allowPrivate"), dict):
            out["allowPrivate"].update({k: bool(raw["allowPrivate"].get(k, True)) for k in out["allowPrivate"]})
        if isinstance(raw.get("groupIds"), dict):
            for key in out["groupIds"]:
                vals = raw["groupIds"].get(key, [])
                if not isinstance(vals, list):
                    vals = []
                out["groupIds"][key] = sorted({clean_jid(v) for v in vals if clean_jid(v)})
        out["updatedAt"] = raw.get("updatedAt", "")
        return out

    @app.route("/api/entries_group_control/status", methods=["GET"])
    def entries_group_status():
        st = load_state()
        groups = st.get("gatewayGroupDirectory") if isinstance(st.get("gatewayGroupDirectory"), list) else []
        groups = [g for g in groups if isinstance(g, dict) and g.get("id")]
        groups.sort(key=lambda x: str(x.get("name") or x.get("id") or "").lower())
        return jsonify({"status": "success", "version": VERSION, "settings": normalize(st.get("entriesGroupRouting")), "groups": groups})

    @app.route("/api/entries_group_control/save", methods=["POST"])
    def entries_group_save():
        payload = request.get_json(silent=True) or {}
        cfg = normalize(payload)
        cfg["updatedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_child(["entriesGroupRouting"], cfg)
        return jsonify({"status": "success", "version": VERSION, "settings": cfg})

    @app.after_request
    def inject_entries_group_control(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or request.path.startswith("/api/"):
                return resp
            if "text/html" not in (resp.headers.get("Content-Type") or "").lower():
                return resp
            html = resp.get_data(as_text=True)
            if not html or "titan-entries-group-control-v2" in html or "</body>" not in html.lower():
                return resp
            i = html.lower().rfind("</body>")
            html = html[:i] + SCRIPT + html[i:]
            resp.set_data(html)
            resp.headers["Content-Length"] = str(len(resp.get_data()))
        except Exception as exc:
            print("⚠️ Entries group control injection failed:", exc)
        return resp

    print("✅ Titan Entries group control loaded", VERSION)


SCRIPT = r'''
<script id="titan-entries-group-control-v2">
(function(){
 if(window.__TITAN_ENTRIES_GROUP_CONTROL_V2__) return;
 window.__TITAN_ENTRIES_GROUP_CONTROL_V2__=true;
 const BTN='titanEntriesGroupControlBtn', MOD='titanEntriesGroupControlModal';
 let entriesSelected=false, lastEntriesClick=0;
 function headers(){const h={'Content-Type':'application/json','Cache-Control':'no-store'};try{const t=localStorage.getItem('TITAN_ADMIN_TOKEN');if(t)h['X-Titan-Admin-Token']=t}catch(_){}return h}
 function notify(a,b,c){try{if(typeof showRealNotification==='function')showRealNotification(a,b,c||'info');else alert(a+'\n'+b)}catch(_){}}
 function visible(el){if(!el)return false;const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>20&&r.height>15&&r.bottom>0&&r.top<innerHeight&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||1)>0}
 function exactEntriesNode(el){const t=(el?.textContent||'').replace(/\s+/g,' ').trim().toUpperCase();return t==='ENTRIES'||t==='ENTRY'}
 function entriesVisible(){
   const markers=['ENTRY MANAGEMENT','BULK ENTRY','TODAY ENTRIES','ENTRY INBOX','PARSED ENTRIES','PENDING ENTRIES','ENTRY APPROVAL','ENTRY CONTROL'];
   const nodes=[...document.querySelectorAll('h1,h2,h3,h4,h5,button,a,[role="tab"],section,main,div')];
   if(nodes.some(el=>visible(el)&&markers.some(m=>(el.textContent||'').toUpperCase().includes(m))))return true;
   if(entriesSelected&&Date.now()-lastEntriesClick<15000)return true;
   const tabs=nodes.filter(el=>exactEntriesNode(el)&&visible(el));
   return tabs.some(el=>{
     const c=String(el.className||'').toLowerCase();
     const aria=String(el.getAttribute?.('aria-selected')||'').toLowerCase();
     const current=String(el.getAttribute?.('aria-current')||'').toLowerCase();
     const data=String(el.getAttribute?.('data-active')||'').toLowerCase();
     return aria==='true'||current==='page'||data==='true'||/active|selected|current|bg-primary|text-white/.test(c);
   });
 }
 document.addEventListener('click',e=>{
   const hit=e.target?.closest?.('button,a,[role="tab"],div,span');
   if(exactEntriesNode(hit)){entriesSelected=true;lastEntriesClick=Date.now();setTimeout(mount,80);setTimeout(mount,500);return}
   const nav=hit?.closest?.('button,a,[role="tab"]');
   if(nav&&visible(nav)&&!exactEntriesNode(nav)&&/^(LEDGER|RESULTS?|WITHDRAWAL|PAY|WALLET|MARKET|SETUP|VIP|FORWARD|GUARD|BACKUP|AUDIT|HEALTH|AI)$/i.test((nav.textContent||'').trim()))entriesSelected=false;
 },true);
 function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
 function option(g,selected){return `<option value="${esc(g.id)}" ${selected?'selected':''}>${esc(g.name||g.id)} (${Number(g.participants||0)})</option>`}
 function selected(id){return [...document.getElementById(id).selectedOptions].map(o=>o.value)}
 async function load(){const r=await fetch('/api/entries_group_control/status',{headers:headers()});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Load failed');return d}
 async function save(){
   try{
     const payload={enabled:document.getElementById('egc-enabled').checked,strictGroups:document.getElementById('egc-strict').checked,allowPrivate:{gameEntry:document.getElementById('egc-private-game').checked,withdrawal:document.getElementById('egc-private-withdraw').checked,deposit:document.getElementById('egc-private-deposit').checked},groupIds:{gameEntry:selected('egc-game'),withdrawal:selected('egc-withdraw'),deposit:selected('egc-deposit')}};
     const r=await fetch('/api/entries_group_control/save',{method:'POST',headers:headers(),body:JSON.stringify(payload)});const d=await r.json();if(!r.ok||d.status!=='success')throw new Error(d.message||'Save failed');notify('✅ Group Control','Separate group settings save ho gayi.','success');document.getElementById(MOD)?.remove();
   }catch(e){notify('❌ Save Error',String(e.message||e),'danger')}
 }
 async function open(){
   try{
     const d=await load(),s=d.settings||{},g=d.groups||[];
     document.getElementById(MOD)?.remove();
     const m=document.createElement('div');m.id=MOD;m.style.cssText='position:fixed;inset:55px 0 65px;z-index:2147483646;background:#07111df7;overflow:auto;padding:12px;color:#fff;font-family:Arial';
     const opts=(key)=>g.map(x=>option(x,(s.groupIds?.[key]||[]).includes(x.id))).join('');
     const empty=g.length?'':'<option disabled>WhatsApp groups abhi sync nahi hue</option>';
     const box=(title,id,key,privateId,privateOn)=>`<div style="background:#132234;border-radius:15px;padding:13px;margin-top:10px"><b>${title}</b><div style="font-size:11px;color:#9db0c0;margin:5px 0 9px">Ek ya multiple WhatsApp groups select karo</div><select id="${id}" multiple size="5" style="width:100%;min-height:135px;background:#0e1b29;color:#fff;border:1px solid #ffffff22;border-radius:10px;padding:8px">${opts(key)||empty}</select><label style="display:flex;justify-content:space-between;margin-top:10px;font-size:12px"><span>Private chat allow</span><input id="${privateId}" type="checkbox" ${privateOn?'checked':''}></label></div>`;
     m.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;background:#123047;padding:14px;border-radius:16px"><div><b>📥 ENTRIES GROUP CONTROL</b><div style="font-size:10px;color:#9db0c0;margin-top:4px">Game · Withdrawal · Deposit</div></div><button id="egc-close" style="background:#203247;color:#fff;border:0;border-radius:10px;padding:9px 12px">✕</button></div><div style="background:#132234;border-radius:15px;padding:13px;margin-top:10px"><label style="display:flex;justify-content:space-between"><b>Group Routing Enabled</b><input id="egc-enabled" type="checkbox" ${s.enabled!==false?'checked':''}></label><label style="display:flex;justify-content:space-between;margin-top:12px"><span>Only selected groups</span><input id="egc-strict" type="checkbox" ${s.strictGroups===true?'checked':''}></label><div style="font-size:10px;color:#fac748;margin-top:8px">Strict ON karne ke baad selected group ke bahar request reject hogi.</div></div>${box('🎮 Game Entry Group','egc-game','gameEntry','egc-private-game',s.allowPrivate?.gameEntry!==false)}${box('💸 Withdrawal Request Group','egc-withdraw','withdrawal','egc-private-withdraw',s.allowPrivate?.withdrawal!==false)}${box('💳 Deposit Request Group','egc-deposit','deposit','egc-private-deposit',s.allowPrivate?.deposit!==false)}<button id="egc-save" style="width:100%;margin-top:12px;padding:13px;background:#00a884;color:white;border:0;border-radius:12px;font-weight:900">SAVE GROUP ROUTING</button>`;
     document.body.appendChild(m);document.getElementById('egc-save').onclick=save;document.getElementById('egc-close').onclick=()=>m.remove();
   }catch(e){notify('❌ Group Control',String(e.message||e),'danger')}
 }
 function mount(){
   let b=document.getElementById(BTN);
   if(!entriesVisible()){if(b)b.remove();if(!entriesSelected)document.getElementById(MOD)?.remove();return}
   if(b)return;
   b=document.createElement('button');b.id=BTN;b.type='button';b.textContent='👥 GROUP CONTROL';b.setAttribute('aria-label','Entries Group Control');b.style.cssText='position:fixed!important;right:10px!important;top:138px!important;z-index:2147483645!important;background:#2563eb!important;color:#fff!important;border:0!important;border-radius:22px!important;padding:11px 15px!important;font-weight:900!important;display:block!important;visibility:visible!important;opacity:1!important;box-shadow:0 5px 20px #0008!important';b.onclick=open;document.body.appendChild(b)
 }
 new MutationObserver(mount).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style','aria-selected','aria-current']});
 setInterval(mount,500);setTimeout(mount,100);setTimeout(mount,700);setTimeout(mount,1800);
 console.log('✅ Entries group selector visibility fix active');
})();
</script>
'''
