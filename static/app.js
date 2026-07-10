const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const API={state:'/api/state',save:'/save',market:'/api/market_action',scrape:'/api/scrape_market',ledgerUpdate:'/api/ledger_card_update',wallet:'/api/wallet_transaction',pay:'/api/approve_payment',withdraw:'/api/withdrawal_action',result:'/api/save_result',targets:'/api/schedule_targets',registry:'/api/market_registry',gateway:'/api/gateway_status',backup:'/api/backup_audit'};
const tabs=[['ledger','Ledger','fa-table'],['clients','Clients','fa-users'],['finance','Finance','fa-wallet'],['entries','Entries','fa-pen-to-square'],['results','Results','fa-trophy'],['markets','Markets','fa-store'],['forward','Forward','fa-share-nodes'],['guard','Guard','fa-shield-halved'],['backup','Backup','fa-database'],['health','Health','fa-heart-pulse'],['ai','Smart AI','fa-wand-magic-sparkles']];
let state=window.__BOOT_STATE__||{}, active='ledger', financeSub='summary', ledgerSub='ANK', picker={cb:null,selected:[]}, deferredInstall=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const arr=x=>Array.isArray(x)?x:[], obj=x=>x&&typeof x==='object'&&!Array.isArray(x)?x:{}, money=n=>'₹'+Number(n||0).toLocaleString('en-IN');
function toast(t,m='',kind='success'){const el=document.createElement('div');el.className=`card p-3 border-${kind==='danger'?'red':'green'}-400/30`;el.innerHTML=`<b>${esc(t)}</b><p class="text-xs text-slate-400">${esc(m)}</p>`;$('#toastWrap').append(el);setTimeout(()=>el.remove(),3500)}
async function fetchJson(url,opt={}){const r=await fetch(url,{cache:'no-store',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok||j.status==='error')throw Error(j.message||r.statusText);return j}
async function load(){try{state=await fetchJson(API.state+'?ts='+Date.now());render();toast('State refreshed')}catch(e){toast('Load failed',e.message,'danger')}}
async function post(url,p){const j=await fetchJson(url,{method:'POST',body:JSON.stringify(p)}); await load(); return j}
function markets(){return Object.values(obj(obj(state.marketRegistry).items)).filter(m=>m&&m.deleted!==true)}
function profiles(){return Object.entries(obj(state.profiles)).filter(([id])=>!['admin1','admin2','admin3'].includes(id))}
function targets(){const xs=[...arr(state.scheduleTargets),...arr(state.resultTargets),...arr(state.forwardTargets),...arr(state.groups),...arr(state.whatsappTargets)]; markets().forEach(m=>['entryTargets','scheduleTargets','resultTargets','forwardTargets','bookieTargets'].forEach(k=>arr(m[k]).forEach(x=>xs.push(x)))); return [...new Set(xs.map(x=>typeof x==='string'?x:(x.id||x.name||'')).filter(Boolean))]}
function setTab(t){active=t; render(); $('#sidebar').classList.add('-translate-x-full'); $('#scrim').classList.add('hidden')}
function nav(){const b=tabs.map(([id,l,i])=>`<button data-tab="${id}" class="${active===id?'tab-active':''} touch shrink-0 rounded-2xl border border-white/10 bg-white/5 px-3 text-xs font-black text-slate-300"><i class="fa-solid ${i} mr-1"></i>${l}</button>`).join(''); $('#navTabs').innerHTML=b; $('#sideTabs').innerHTML=b; $$('[data-tab]').forEach(x=>x.onclick=()=>setTab(x.dataset.tab));}
function stats(){const w=Object.values(obj(state.wallets)).reduce((a,v)=>a+Number(v.balance||0),0); $('#stats').innerHTML=[['Markets',markets().length,'fa-store','#2AABEE'],['VIPs',profiles().length,'fa-users','#00C26F'],['Wallet',money(w),'fa-wallet','#FAC748'],['Entries',arr(state.entries).length,'fa-pen','#FF5D5D']].map(s=>`<div class="card p-3"><i class="fa-solid ${s[2]}" style="color:${s[3]}"></i><p class="mt-2 text-xs text-slate-400">${s[0]}</p><b>${s[1]}</b></div>`).join('')}
const panel=(title,body,icon='fa-circle')=>`<div class="mb-3 flex items-center gap-2"><i class="fa-solid ${icon} text-[#2AABEE]"></i><h2 class="text-xl font-black">${title}</h2></div>${body}`;
function ledgerTypeKey(type){const k=String(type||ledgerSub||'ANK').toUpperCase(); return k==='PANEL'||k==='PENEL'||k==='PANNEL'?'PANEL':k==='JODI'?'JODI':'ANK'}
function ledgerApiType(type){const k=ledgerTypeKey(type); return k==='PANEL'?'pannel':k.toLowerCase()}
function ledgerDictName(type){const k=ledgerTypeKey(type); return k==='PANEL'?'pannelData':k==='JODI'?'jodiData':'data'}
function currentDateKey(){return ($('#datePicker')?.value)||new Date().toISOString().slice(0,10)}
function marketBaseName(m){return String(m.websiteName||m.displayName||m.name||m.id||'').replace(/\s+(OPEN|CLOSE)$/i,'').trim()}
function ledgerRecord(m,type,idx){const date=currentDateKey(), dn=ledgerDictName(type); const prof=obj(obj(state.profiles)[state.activeId||'admin1']); return obj(obj(obj(prof.dayRecords)[date])[dn])[idx]||obj(obj(obj(state.dayRecords)[date])[dn])[idx]||{} }
function rateFor(type, amount=0){
  const rates=obj(state.rates), key=ledgerTypeKey(type);
  const direct=Number(rates[key]||rates[key.toLowerCase()]||rates[ledgerApiType(key)]||0);
  if(direct) return direct;
  const pm=obj(obj(state.settlementSettings).payoutMultipliers);
  const configured=Number(pm[key.toLowerCase()]||pm[ledgerApiType(key)]||0);
  if(configured) return configured;
function rateFor(type, amount=0){
  const rates=obj(state.rates), key=String(type||'').toUpperCase();
  const direct=Number(rates[key]||rates[key.toLowerCase()]||0);
  if(direct) return direct;
  const defaults={ANK:9.5,JODI:95,PANEL:1400};
  const base=defaults[key]||1;
  return amount>=5000?Math.round(base*1.03*100)/100:amount>=1000?Math.round(base*1.015*100)/100:base;
}
function recoveryPlan(marketId,type){
  const idx=markets().findIndex(x=>String(x.id)===String(marketId));
  const rec=ledgerRecord({id:marketId},type,Math.max(idx,0));
  const loss=Number(rec.loss||rec.r||rec.amount||0);
  const rate=rateFor(type,loss);
  const stake=Math.max(10,Math.ceil((loss+100)/Math.max(rate-1,1)));
  return {loss,rate,stake,next:`${ledgerTypeKey(type)} next stake ${stake} @ ${rate}`};
}
function ledgerTypePanel(m,type,idx){
  type=ledgerTypeKey(type);
  const rec=ledgerRecord(m,type,idx), plan=recoveryPlan(m.id,type);
  const digit=esc(rec.d||rec.digit||rec.card||''), amt=esc(rec.r||rec.amount||''), rate=esc(rec.rate||plan.rate), status=esc(rec.status||rec._markStatus||'READY');
  return `<section class="rounded-2xl border border-white/10 bg-black/20 p-3">
    <div class="flex items-start justify-between gap-2"><div><b>${esc(m.displayName||m.name||m.id)}</b><p class="text-[11px] text-slate-400">${type} · Open ${esc(obj(m.times).open||'-')} · Close ${esc(obj(m.times).close||'-')}</p><p class="text-[11px] text-[#FAC748]">Auto rate ${rate} · Recovery ${money(plan.stake)} · ${esc(plan.next)}</p></div><span class="pill">${status}</span></div>
    <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
      <input id="dig-${m.id}-${type}" class="input" value="${digit}" placeholder="${type} digit/card">
      <input id="amt-${m.id}-${type}" class="input" type="number" value="${amt}" placeholder="Amount" oninput="suggestRate('${m.id}','${type}')">
      <input id="rate-${m.id}-${type}" class="input" value="${rate}" placeholder="Rate">
    </div>
    <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-6">
      <button id="scrape-${m.id}-${type}" class="btn btn-blue" onclick="scrapeLedger('${m.id}','${type}',${idx})"><i class="fa-solid fa-satellite-dish mr-1"></i>Scrape</button>
      <button id="combine-${m.id}-${type}" class="btn btn-yellow" onclick="combineLedger('${m.id}','${type}',${idx})">Combine</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T1',${idx})">T1</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T2',${idx})">T2</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T3',${idx})">T3</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T4',${idx})">T4</button>
    </div>
    <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-5">
      <button class="btn btn-yellow" onclick="applyRecovery('${m.id}','${type}')"><i class="fa-solid fa-calculator mr-1"></i>Recovery</button>
      <button class="btn btn-green" onclick="markLedger('${m.id}','${type}','pass',${idx})">PASS</button>
      <button class="btn btn-red" onclick="markLedger('${m.id}','${type}','fail',${idx})">FAIL</button>
      <button class="btn btn-ghost" onclick="markLedger('${m.id}','${type}','skip',${idx})">SKIP</button>
      <button class="btn btn-ghost" onclick="saveLedgerCard('${m.id}','${type}',${idx},'manual_input')">Save</button>
    </div>
  </section>`;
}
function ledger(){const type=ledgerTypeKey(ledgerSub);return panel('Ledger',`<div class="sticky top-[69px] z-20 -mx-3 mb-3 border-b border-white/10 bg-[#0B1118]/95 px-3 py-2 backdrop-blur"><div class="grid grid-cols-3 gap-2">${['ANK','JODI','PANEL'].map(t=>`<button onclick="ledgerSub='${t}';render()" class="btn ${type===t?'btn-blue':'btn-ghost'}">${t}</button>`).join('')}</div><p class="mt-2 text-xs text-slate-400">Ek screen par sirf selected ${type} cards dikh rahe hain. Scroll me ANK/JODI/PANEL mix nahi hoga.</p></div><div class="grid gap-3 lg:grid-cols-2">${markets().map((m,i)=>ledgerTypePanel(m,type,i)).join('')}</div>`,'fa-table')}
  const cards=arr(state.ledgerCards).filter(c=>(c.marketId||c.market)==marketId && String(c.type||'').toUpperCase()===type);
  const last=cards.slice(-1)[0]||{};
  const loss=Number(last.loss||last.amount||0);
  const rate=rateFor(type,loss);
  const stake=Math.max(10,Math.ceil((loss+100)/Math.max(rate-1,1)));
  return {loss,rate,stake,next:`${type} next stake ${stake} @ ${rate}`};
}
function ledgerTypePanel(m,type){
  const plan=recoveryPlan(m.id,type);
  const cards=arr(state.ledgerCards).filter(c=>(c.marketId||c.market)==m.id && String(c.type||'').toUpperCase()===type).slice(-3).reverse();
  return `<section class="rounded-2xl border border-white/10 bg-black/20 p-3">
    <div class="flex items-center justify-between gap-2"><div><b>${type}</b><p class="text-[11px] text-slate-400">Auto rate ${plan.rate} · Recovery ${money(plan.stake)}</p></div><span class="pill">${cards[0]?.status||'READY'}</span></div>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <input id="dig-${m.id}-${type}" class="input" placeholder="${type} digit/card">
      <input id="amt-${m.id}-${type}" class="input" type="number" placeholder="Amount" oninput="suggestRate('${m.id}','${type}')">
      <input id="rate-${m.id}-${type}" class="input" value="${plan.rate}" placeholder="Rate">
      <button class="btn btn-yellow" onclick="applyRecovery('${m.id}','${type}')"><i class="fa-solid fa-calculator mr-1"></i>Recovery</button>
    </div>
    <div class="mt-2 grid grid-cols-4 gap-2">
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T1')">T1</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T2')">T2</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T3')">T3</button>
      <button class="btn btn-ghost" onclick="trick('${m.id}','${type}','T4')">T4</button>
    </div>
    <div class="mt-2 grid grid-cols-5 gap-2">
      <button class="btn btn-blue" onclick="scrapeLedger('${m.id}','${type}')">Scrape</button>
      <button class="btn btn-yellow" onclick="combineLedger('${m.id}','${type}')">Combine</button>
      <button class="btn btn-green" onclick="markLedger('${m.id}','${type}','pass')">PASS</button>
      <button class="btn btn-red" onclick="markLedger('${m.id}','${type}','fail')">FAIL</button>
      <button class="btn btn-ghost" onclick="markLedger('${m.id}','${type}','skip')">SKIP</button>
    </div>
    <div class="mt-2 grid gap-2">${cards.map(c=>`<div class="rounded-xl bg-white/5 p-2 text-xs"><b>${esc(c.digit||c.card||'-')}</b> · ${money(c.amount)} · ${esc(c.status||'new')} <button class="float-right text-[#00C26F]" onclick="markLedgerCard('${c.id||''}','pass')">auto PASS</button><button class="float-right mr-3 text-[#FF5D5D]" onclick="markLedgerCard('${c.id||''}','fail')">auto FAIL</button></div>`).join('')||'<p class="text-xs text-slate-500">No recent cards. Use scrape/combine or T1-T4.</p>'}</div>
  </section>`;
}
function ledger(){return panel('Ledger',`<div class="mb-3 rounded-3xl border border-[#FAC748]/30 bg-[#FAC748]/10 p-3 text-sm text-slate-200"><b>ANK, JODI aur PANEL ab alag-alag panels hain.</b><br>Har panel me Scrape, Combine, T1-T4 trick buttons, auto-rate suggestion, recovery calculator, next-card hint aur PASS/FAIL auto-mark actions available hain.</div><div class="grid gap-3 xl:grid-cols-2">${markets().map(m=>`<div class="card p-3"><div class="flex justify-between gap-2"><div><b>${esc(m.displayName||m.name||m.id)}</b><p class="text-xs text-slate-400">Open ${esc(obj(m.times).open||'-')} · Close ${esc(obj(m.times).close||'-')} · Target ${arr(m.scheduleTargets).length}</p></div><span class="pill">${m.enabled===false?'OFF':'ACTIVE'}</span></div><div class="mt-3 grid gap-3">${['ANK','JODI','PANEL'].map(k=>ledgerTypePanel(m,k)).join('')}</div><div class="mt-3 grid grid-cols-2 gap-2"><button class="btn btn-blue" onclick="openTargets(['${arr(m.scheduleTargets).join("','")}'],v=>saveRoleTargets('${m.id}','schedule',v))">Schedule Targets</button><button class="btn btn-ghost" onclick="marketAction('${m.id}','reset')">Reset Market</button></div></div>`).join('')}</div>`,'fa-table')}
function clients(){return panel('Clients (VIPs)',`<div class="grid gap-3 lg:grid-cols-2">${profiles().map(([id,p])=>`<div class="card p-3"><div class="flex gap-3"><div class="grid h-12 w-12 place-items-center rounded-2xl bg-[#2AABEE]/20 font-black">${esc((p.name||id)[0])}</div><div class="min-w-0 flex-1"><b>${esc(p.name||id)}</b><p class="break-all text-xs text-slate-400">${esc(p.phone||'-')} · ${esc(id)}</p><p class="text-xs">${esc(p.approvalStatus||'pending')} · Exp ${esc(p.expiryDate||'not set')} · ${money(obj(state.wallets)[id]?.balance)}</p></div></div><div class="mt-3 grid grid-cols-2 gap-2"><button class="btn btn-green" onclick="vip('${id}','approved')">Approve</button><button class="btn btn-red" onclick="vip('${id}','rejected')">Reject</button><input id="exp-${id}" type="date" class="input"><button class="btn btn-blue" onclick="saveExpiry('${id}')">Set Expiry</button><button class="btn btn-ghost" onclick="toggleAccess('${id}',${p.vipAccessEnabled===false})">${p.vipAccessEnabled===false?'Enable':'Disable'}</button><button class="btn btn-red" onclick="delVip('${id}')">Delete</button><button class="btn btn-yellow col-span-2" onclick="share('/?vip=${id}')">Share App Link</button></div></div>`).join('')}</div>`,'fa-users')}
function finance(){const subs=['summary','wallets','payments','withdrawals'];return panel('Finance',`<div class="no-scrollbar mb-3 flex gap-2 overflow-x-auto">${subs.map(s=>`<button onclick="financeSub='${s}';render()" class="btn ${financeSub===s?'btn-blue':'btn-ghost'} shrink-0">${s}</button>`).join('')}</div>${financeSub==='wallets'?wallets():financeSub==='payments'?payments():financeSub==='withdrawals'?withdrawals():summary()}`,'fa-wallet')}
function summary(){return `<div class="grid gap-3 md:grid-cols-3"><div class="card p-4"><p>Wallet balance</p><b class="text-2xl text-[#00C26F]">${money(Object.values(obj(state.wallets)).reduce((a,w)=>a+Number(w.balance||0),0))}</b></div><div class="card p-4"><p>Pending payments</p><b>${arr(state.payments).filter(p=>String(p.status).toLowerCase().includes('pending')).length}</b></div><div class="card p-4"><p>Pending withdrawals</p><b>${arr(state.withdrawals).filter(p=>String(p.status).toLowerCase().includes('pending')).length}</b></div></div>`}
function wallets(){return profiles().map(([id,p])=>`<div class="card mb-3 p-3"><b>${esc(p.name||id)}</b><p class="text-sm text-[#00C26F]">${money(obj(state.wallets)[id]?.balance)}</p><div class="mt-2 grid grid-cols-3 gap-2"><input id="amt-${id}" class="input" placeholder="Amount"><button class="btn btn-green" onclick="walletTx('${id}','credit')">Add</button><button class="btn btn-red" onclick="walletTx('${id}','debit')">Subtract</button></div></div>`).join('')}
function payments(){return arr(state.payments).map((p,i)=>`<div class="card mb-3 p-3"><b>${esc(p.name||p.userId||'Payment')}</b><p class="text-xs text-slate-400">${money(p.amount)} · ${esc(p.status||'pending')} · UTR ${esc(p.utr||'-')}</p><button class="btn btn-green mt-2" onclick="payment('${p.id||i}','approve')">Approve</button> <button class="btn btn-red mt-2" onclick="payment('${p.id||i}','reject')">Reject</button></div>`).join('')||'<div class="card p-4">No payments</div>'}
function withdrawals(){return arr(state.withdrawals).map((p,i)=>`<div class="card mb-3 p-3"><b>${esc(p.name||p.userId||'Withdrawal')}</b><p class="text-xs text-slate-400">${money(p.amount)} · ${esc(p.status||'pending')}</p><button class="btn btn-green mt-2" onclick="withdraw('${p.id||i}','approve')">Approve</button> <button class="btn btn-blue mt-2" onclick="withdraw('${p.id||i}','paid')">Mark Paid</button> <button class="btn btn-red mt-2" onclick="withdraw('${p.id||i}','reject')">Reject</button></div>`).join('')||'<div class="card p-4">No withdrawals</div>'}
function entries(){return panel('Entries',`<div class="card mb-3 p-3 flex items-center justify-between"><b>WhatsApp Parser</b>${sw('entryParserEnabled',obj(state.entrySettings).parserEnabled!==false,async v=>{state.entrySettings={...obj(state.entrySettings),parserEnabled:v};await post(API.save,state)})}</div><div class="grid gap-3 lg:grid-cols-2">${arr(state.entries).slice(-80).reverse().map(e=>`<div class="card p-3"><b>${esc(e.market||e.marketName||'-')}</b><p class="text-xs text-slate-400">${esc(e.userId||e.phone||'-')} · ${esc(e.type||'-')} · ${money(e.amount)}</p><p class="text-sm">${esc(e.text||e.raw||'')}</p></div>`).join('')}</div>`,'fa-pen-to-square')}
function results(){return panel('Results',`<div class="grid gap-3 md:grid-cols-2">${markets().map(m=>`<div class="card p-3"><b>${esc(m.displayName||m.name)}</b><div class="mt-2 grid grid-cols-2 gap-2"><input id="ro-${m.id}" class="input" placeholder="Open result"><input id="rc-${m.id}" class="input" placeholder="Close result"><button class="btn btn-green" onclick="saveResult('${m.id}','open')">Declare Open</button><button class="btn btn-blue" onclick="saveResult('${m.id}','close')">Declare Close</button><button class="btn btn-yellow" onclick="retryResult('${m.id}')">Retry Send</button><button class="btn btn-red" onclick="clearResult('${m.id}')">Clear Old</button></div></div>`).join('')}</div>`,'fa-trophy')}
function marketsTab(){return panel('Markets',`<div class="card mb-3 p-3"><div class="grid gap-2 md:grid-cols-4"><input id="mn" class="input" placeholder="Market name"><input id="mo" class="input" placeholder="Open HH:MM"><input id="mc" class="input" placeholder="Close HH:MM"><button class="btn btn-green" onclick="addMarket()">Add Market</button></div></div><div class="grid gap-3 lg:grid-cols-2">${markets().map(m=>`<div class="card p-3"><b>${esc(m.displayName||m.name)}</b><p class="text-xs text-slate-400">${esc(m.id)} · ${esc(obj(m.times).open)} / ${esc(obj(m.times).close)}</p>${['entry','schedule','result','forward','bookie'].map(r=>`<button class="btn btn-ghost m-1" onclick="openTargets(${JSON.stringify(arr(m[r+'Targets']))},v=>saveRoleTargets('${m.id}','${r}',v))">${r} targets</button>`).join('')}<div><button class="btn btn-yellow mt-2" onclick="marketAction('${m.id}','archive')">Disable</button> <button class="btn btn-red mt-2" onclick="marketAction('${m.id}','delete')">Delete</button></div></div>`).join('')}</div>`,'fa-store')}
function forward(){return panel('Forward',`<div class="card p-3"><input id="forwardTime" class="input" value="${esc(obj(state.loadForwarder).time||'')}" placeholder="Schedule time"><textarea id="forwardPreview" class="input mt-2 min-h-40">${loadReport()}</textarea><button class="btn btn-blue mt-2" onclick="share($('#forwardPreview').value)">Preview / Share</button><button class="btn btn-green mt-2" onclick="post(API.save,{...state,loadForwarder:{...obj(state.loadForwarder),time:$('#forwardTime').value}})">Save</button></div>`,'fa-share-nodes')}
function guard(){return panel('Guard',`<div class="grid gap-3 md:grid-cols-2">${['duplicateBlock','dailyLimits','autoPause','targetSafety'].map(k=>`<div class="card p-3 flex items-center justify-between"><b>${k}</b>${sw(k,obj(state.spamGuardSettings)[k]!==false,async v=>{state.spamGuardSettings={...obj(state.spamGuardSettings),[k]:v};await post(API.save,state)})}</div>`).join('')}</div>`,'fa-shield-halved')}
function backup(){return panel('Backup',`<div class="grid gap-2 md:grid-cols-3"><a class="btn btn-blue text-center" href="/api/backup.zip">Download ZIP</a><button class="btn btn-green" onclick="exportCsv()">Export CSV</button><button class="btn btn-red" onclick="state.auditLog=[];post(API.save,state)">Clear Audit</button></div><div class="mt-3 grid gap-2">${arr(state.auditLog).slice(-50).reverse().map(a=>`<div class="card p-3 text-xs"><b>${esc(a.action||a.type||'event')}</b><p class="text-slate-400">${esc(a.time||a.createdAt||'')} ${esc(JSON.stringify(a.detail||{}).slice(0,160))}</p></div>`).join('')}</div>`,'fa-database')}
function health(){return panel('Health',`<div id="healthBox" class="grid gap-3 md:grid-cols-2"><div class="card p-4">Gateway: checking...</div></div>`,'fa-heart-pulse')}
async function loadHealth(){try{const g=await fetchJson(API.gateway); $('#healthBox').innerHTML=`<div class="card p-4"><b>Gateway</b><p class="text-xs text-slate-400">${esc(JSON.stringify(g).slice(0,300))}</p></div><div class="card p-4"><b>Counts</b><p>Markets ${markets().length} · VIP ${profiles().length} · Results ${Object.keys(obj(state.resultRecords)).length}</p></div>`}catch(e){$('#healthBox').innerHTML=`<div class="card p-4 text-[#FF5D5D]">Gateway error: ${esc(e.message)}</div>`}}
function ai(){return panel('Smart AI',`<div class="card p-3"><textarea id="aiText" class="input min-h-52" placeholder="Bulk entries paste karo..."></textarea><button class="btn btn-blue mt-2" onclick="parseAI()">Parse ANK / JODI / PANEL</button><div id="aiOut" class="mt-3"></div></div>`,'fa-wand-magic-sparkles')}
function render(){nav();stats(); const map={ledger,clients,finance,entries,results,markets:marketsTab,forward,guard,backup,health,ai}; $('#content').innerHTML=map[active](); if(active==='health')loadHealth();}
function sw(id,checked,cb){setTimeout(()=>{const e=$(`#sw-${id}`); if(e)e.onchange=()=>cb(e.checked)},0);return `<label class="switch"><input id="sw-${id}" type="checkbox" ${checked?'checked':''}><span></span></label>`}
async function commitLedger(marketId,type,idx,action,extra={}){
  type=ledgerTypeKey(type);
  const m=markets().find(x=>String(x.id)===String(marketId))||{id:marketId};
  const rec={...ledgerRecord(m,type,idx),_ledgerKey:String(m.id||marketId),marketId:String(m.id||marketId),market:marketBaseName(m),n:marketBaseName(m),d:$(`#dig-${marketId}-${type}`)?.value||'',r:$(`#amt-${marketId}-${type}`)?.value||'',rate:$(`#rate-${marketId}-${type}`)?.value||rateFor(type),updatedAt:new Date().toISOString(),...extra};
  await fetchJson(API.ledgerUpdate,{method:'POST',body:JSON.stringify({activeId:state.activeId||'admin1',profileId:state.activeId||'admin1',type:ledgerApiType(type),idx,marketKey:String(m.id||marketId),date:currentDateKey(),action,record:rec,applyToVips:true})});
  toast('Ledger saved',`${type} ${marketBaseName(m)}`);
  await load();
}
window.suggestRate=(marketId,type)=>{type=ledgerTypeKey(type);const amt=Number($(`#amt-${marketId}-${type}`).value||0); const r=$(`#rate-${marketId}-${type}`); if(r)r.value=rateFor(type,amt)};
window.applyRecovery=(marketId,type)=>{type=ledgerTypeKey(type);const plan=recoveryPlan(marketId,type); $(`#amt-${marketId}-${type}`).value=plan.stake; $(`#rate-${marketId}-${type}`).value=plan.rate; toast('Recovery suggested',plan.next)};
window.trick=async(marketId,type,trickName,idx)=>{type=ledgerTypeKey(type); const inp=$(`#dig-${marketId}-${type}`); const raw=String(inp?.value||'').split(/[\s,]+/).filter(Boolean); const rotated=raw.length?raw.slice(Number(trickName.slice(1))-1).concat(raw.slice(0,Number(trickName.slice(1))-1)):[]; if(inp&&rotated.length)inp.value=rotated.join(','); await commitLedger(marketId,type,idx,'trick_apply',{trick:trickName});};
window.scrapeLedger=async(marketId,type,idx)=>{type=ledgerTypeKey(type); const m=markets().find(x=>String(x.id)===String(marketId))||{}; const btn=$(`#scrape-${marketId}-${type}`); const old=btn?.innerHTML; try{if(btn){btn.disabled=true;btn.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Scraping'} const data=await fetchJson(API.scrape,{method:'POST',body:JSON.stringify({market:marketBaseName(m)})}); const digits=type==='ANK'?(data.open||data.close||data.combined):type==='JODI'?(data.jodi||data.combined):(data.combined||data.jodi); if(!digits)throw Error('Scrape data empty'); $(`#dig-${marketId}-${type}`).value=digits; await commitLedger(marketId,type,idx,'scrape_digits',{scrape:data}); toast('Scrape complete',`${type}: ${digits}`)}catch(e){toast('Scrape failed',e.message,'danger')}finally{if(btn){btn.disabled=false;btn.innerHTML=old}}};
window.combineLedger=async(marketId,type,idx)=>{type=ledgerTypeKey(type); const m=markets().find(x=>String(x.id)===String(marketId))||{}; const btn=$(`#combine-${marketId}-${type}`); const old=btn?.innerHTML; try{if(btn){btn.disabled=true;btn.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i>'} const data=await fetchJson(API.scrape,{method:'POST',body:JSON.stringify({market:marketBaseName(m)})}); const combined=data.combined||[data.open,data.close,data.jodi].filter(Boolean).join(','); if(!combined)throw Error('Combined scrape empty'); $(`#dig-${marketId}-${type}`).value=combined; await commitLedger(marketId,type,idx,'combo_scrape',{scrape:data}); toast('Combine complete',combined)}catch(e){toast('Combine failed',e.message,'danger')}finally{if(btn){btn.disabled=false;btn.innerHTML=old}}};
window.markLedger=async(marketId,type,status,idx)=>{await commitLedger(marketId,type,idx,`manual_${status}`,{status,_markStatus:status,autoMark:true})};
window.markLedgerCard=(cardId,status)=>post(API.ledgerUpdate,{activeId:state.activeId||'admin1',action:`manual_${status}`,record:{status,_markStatus:status,autoMark:true},date:currentDateKey()});
window.saveLedgerCard=(marketId,type,idx,action='manual_input')=>commitLedger(marketId,type,idx,action);
window.suggestRate=(marketId,type)=>{const amt=Number($(`#amt-${marketId}-${type}`).value||0); const r=$(`#rate-${marketId}-${type}`); if(r)r.value=rateFor(type,amt)};
window.applyRecovery=(marketId,type)=>{const plan=recoveryPlan(marketId,type); $(`#amt-${marketId}-${type}`).value=plan.stake; $(`#rate-${marketId}-${type}`).value=plan.rate; toast('Recovery suggested',plan.next)};
window.trick=(marketId,type,trick)=>post(API.market,{action:'ledger_trick',marketId,id:marketId,type,trick,digit:$(`#dig-${marketId}-${type}`).value,amount:Number($(`#amt-${marketId}-${type}`).value||0),rate:Number($(`#rate-${marketId}-${type}`).value||rateFor(type))});
window.scrapeLedger=(marketId,type)=>post(API.market,{action:'ledger_scrape',marketId,id:marketId,type});
window.combineLedger=(marketId,type)=>post(API.market,{action:'ledger_combine',marketId,id:marketId,type,digit:$(`#dig-${marketId}-${type}`).value,amount:Number($(`#amt-${marketId}-${type}`).value||0),rate:Number($(`#rate-${marketId}-${type}`).value||rateFor(type))});
window.markLedger=(marketId,type,status)=>post(API.market,{action:'ledger_mark',marketId,id:marketId,type,status,autoMark:true,digit:$(`#dig-${marketId}-${type}`).value});
window.markLedgerCard=(cardId,status)=>post(API.market,{action:'ledger_card_mark',cardId,status,autoMark:true});
window.marketAction=(id,action)=>post(API.market,{id,action}); window.saveRoleTargets=(id,role,v)=>post(API.market,{action:'set_role_targets',id,role,targets:v});
window.vip=(userId,status)=>post('/api/vip_control/update',{userId,approvalStatus:status,vipAccessEnabled:status==='approved'}); window.saveExpiry=userId=>post('/api/vip_control/update',{userId,expiryDate:$(`#exp-${userId}`).value}); window.toggleAccess=(userId,on)=>post('/api/vip_control/update',{userId,vipAccessEnabled:on}); window.delVip=userId=>confirm('Archive/delete VIP?')&&post('/api/vip_control/archive',{userId});
window.walletTx=(userId,kind)=>post(API.wallet,{userId,kind,amount:Number($(`#amt-${userId}`).value||0),description:'Admin dashboard'}); window.payment=(id,action)=>post(API.pay,{id,paymentId:id,action}); window.withdraw=(id,action)=>post(API.withdraw,{id,withdrawalId:id,action});
window.saveResult=(marketId,stage)=>post(API.result,{marketId,stage,value:$(`#r${stage[0]}-${marketId}`).value}); window.retryResult=marketId=>post('/api/gateway_result_retry',{marketId}); window.clearResult=marketId=>{delete obj(state.resultRecords)[marketId];return post(API.save,state)}; window.addMarket=()=>post(API.market,{action:'direct_add_full',name:$('#mn').value,openTime:$('#mo').value,closeTime:$('#mc').value});
window.openTargets=(selected,cb)=>{picker={selected:[...selected],cb}; $('#targetModal').classList.remove('hidden'); drawTargets()}; function drawTargets(){const q=($('#targetSearch').value||'').toLowerCase();$('#targetList').innerHTML=targets().filter(t=>!q||t.toLowerCase().includes(q)).map(t=>`<label class="mb-2 flex items-center gap-2 rounded-xl bg-white/5 p-3"><input type="checkbox" value="${esc(t)}" ${picker.selected.includes(t)?'checked':''}><span class="break-all text-sm">${esc(t)}</span></label>`).join('')||'<p class="text-sm text-slate-400">No targets found</p>'}
function share(txt){$('#shareText').value=location.origin+txt;$('#shareModal').classList.remove('hidden')} window.share=share;
function loadReport(){return markets().map(m=>`${m.displayName||m.name}: Open ${obj(m.times).open||'-'} Close ${obj(m.times).close||'-'}`).join('\n')} function exportCsv(){share(arr(state.entries).map(e=>Object.values(e).join(',')).join('\n'))} window.exportCsv=exportCsv;
window.parseAI=()=>{const txt=$('#aiText').value; const lines=txt.split(/\n+/).filter(Boolean); $('#aiOut').innerHTML=lines.map(l=>`<div class="card mb-2 p-3"><b>${/panel/i.test(l)?'PANEL':/jodi|\d{2}/i.test(l)?'JODI':'ANK'}</b><p class="text-xs text-slate-400">${esc(l)}</p></div>`).join('')};
$('#refreshBtn').onclick=load; $('#sidebarToggle').onclick=()=>{$('#sidebar').classList.remove('-translate-x-full');$('#scrim').classList.remove('hidden')}; $('#closeSidebar').onclick=$('#scrim').onclick=()=>{$('#sidebar').classList.add('-translate-x-full');$('#scrim').classList.add('hidden')}; $$('[data-close-modal]').forEach(b=>b.onclick=()=>b.closest('.modal').classList.add('hidden')); $('#targetSearch').oninput=drawTargets; $('#saveTargets').onclick=()=>{const v=$$('#targetList input:checked').map(x=>x.value); picker.cb&&picker.cb(v); $('#targetModal').classList.add('hidden')}; $('#copyShare').onclick=async()=>{await navigator.clipboard?.writeText($('#shareText').value); if(navigator.share)navigator.share({text:$('#shareText').value}).catch(()=>{}); toast('Copied')};
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('#pwaBanner').classList.remove('hidden')}); $('#installBtn').onclick=()=>deferredInstall?.prompt(); $('#datePicker').value=new Date().toISOString().slice(0,10);
render(); load();
