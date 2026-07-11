const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const API = {
  state: '/api/state', save: '/save', market: '/api/market_action', registry: '/api/market_registry', scrape: '/api/scrape_market',
  ledger: '/api/ledger_card_update', wallet: '/api/wallet_transaction', credit: '/api/wallet_credit_limit', pay: '/api/approve_payment',
  rejectPay: '/api/reject_payment', withdraw: '/api/withdrawal_action', entries: '/api/entry_settings', risk: '/api/risk_settings',
  result: '/api/save_result', retryResult: '/api/gateway_result_retry', resultSettings: '/api/save_result_settings', resultTargets: '/api/save_result_targets',
  scheduleTargets: '/api/schedule_targets', guard: '/api/save_spam_guard', safety: '/api/save_whatsapp_safety', pause: '/api/whatsapp_safety_pause',
  resume: '/api/whatsapp_safety_resume', forward: '/api/save_load_forwarder', preview: '/api/load_report_preview', sendForward: '/api/load_forwarder_send',
  backup: '/api/backup_audit', health: '/api/health_monitor', gateway: '/api/gateway_status', waTargets: '/api/wa_targets', clearAudit: '/api/clear_audit_log'
};

const tabs = [
  ['ledger', 'Ledger', 'fa-table'], ['clients', 'Clients', 'fa-users'], ['finance', 'Finance', 'fa-wallet'], ['entries', 'Entries', 'fa-pen-to-square'],
  ['results', 'Results', 'fa-trophy'], ['markets', 'Markets', 'fa-store'], ['forward', 'Forward', 'fa-share-nodes'], ['guard', 'Guard', 'fa-shield-halved'],
  ['backup', 'Backup', 'fa-database'], ['health', 'Health', 'fa-heart-pulse'], ['ai', 'Smart AI', 'fa-wand-magic-sparkles']
];

let state = window.__BOOT_STATE__ || {};
let active = localStorage.titanActiveTab || 'ledger';
let financeSub = 'summary';
let ledgerSub = 'ANK';
let picker = { selected: [], cb: null };
let deferredInstall = null;

const esc = v => String(v ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const arr = v => Array.isArray(v) ? v : [];
const obj = v => v && typeof v === 'object' && !Array.isArray(v) ? v : {};
const money = n => '₹' + Number(n || 0).toLocaleString('en-IN');
const today = () => new Date().toISOString().slice(0, 10);

function toast(title, msg = '', kind = 'success') {
  const el = document.createElement('div');
  el.className = `card p-3 ${kind === 'danger' ? 'border-red-400/30' : 'border-green-400/30'}`;
  el.innerHTML = `<b>${esc(title)}</b>${msg ? `<p class="text-xs text-slate-400">${esc(msg)}</p>` : ''}`;
  $('#toastWrap').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
async function fetchJson(url, opt = {}) {
  const res = await fetch(url, { cache: 'no-store', headers: { 'Content-Type': 'application/json', ...(opt.headers || {}) }, ...opt });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.status === 'error') throw new Error(data.message || data.error || res.statusText);
  return data;
}
async function load(silent = false) {
  try { state = await fetchJson(`${API.state}?ts=${Date.now()}`); render(); if (!silent) toast('State refreshed'); }
  catch (e) { toast('Render/load failed', e.message, 'danger'); }
}
async function post(url, payload = {}, ok = 'Saved') {
  const out = await fetchJson(url, { method: 'POST', body: JSON.stringify(payload) });
  toast(ok); await load(true); return out;
}

function marketItems() {
  const mr = obj(state.marketRegistry);
  const items = Array.isArray(mr) ? mr : Object.values(obj(mr.items || mr.markets || mr));
  const fallback = arr(state.markets).concat(arr(state.marketList));
  return (items.length ? items : fallback).filter(m => m && m.deleted !== true && m.disabled !== true).map((m, i) => ({ id: m.id || m.key || m.name || `market_${i}`, ...m }));
}
function profiles() { return Object.entries(obj(state.profiles)).filter(([id]) => !/^admin/i.test(id)); }
function walletFor(id) { return obj(state.wallets)[id] || obj(obj(state.finance).wallets)[id] || {}; }
function paymentList() { return arr(state.payments).concat(arr(obj(state.finance).payments)); }
function withdrawalList() { return arr(state.withdrawals).concat(arr(obj(state.finance).withdrawals)); }
function allTargets() {
  const raw = [state.scheduleTargets, state.resultTargets, state.forwardTargets, state.groups, state.whatsappTargets, state.waTargets].flatMap(arr);
  marketItems().forEach(m => ['entryTargets', 'scheduleTargets', 'resultTargets', 'forwardTargets', 'bookieTargets'].forEach(k => raw.push(...arr(m[k]))));
  return [...new Set(raw.map(t => typeof t === 'string' ? t : (t.id || t.name || t.title || '')).filter(Boolean))];
}
function typeKey(t) { t = String(t || 'ANK').toUpperCase(); return /PANEL|PENEL|PANNEL/.test(t) ? 'PANEL' : /JODI/.test(t) ? 'JODI' : 'ANK'; }
function apiType(t) { return typeKey(t) === 'PANEL' ? 'pannel' : typeKey(t).toLowerCase(); }
function rateFor(t, amt = 0) {
  const key = typeKey(t), rates = obj(state.rates), pm = obj(obj(state.settlementSettings).payoutMultipliers);
  const configured = Number(rates[key] || rates[key.toLowerCase()] || pm[key.toLowerCase()] || pm[apiType(key)] || 0);
  if (configured) return configured;
  const base = { ANK: 9.5, JODI: 95, PANEL: 1400 }[key];
  return amt >= 5000 ? Math.round(base * 1.03 * 100) / 100 : amt >= 1000 ? Math.round(base * 1.015 * 100) / 100 : base;
}
function marketName(m) { return String(m.displayName || m.websiteName || m.name || m.id || '').replace(/\s+(OPEN|CLOSE)$/i, '').trim(); }
function dateKey() { return $('#datePicker')?.value || today(); }

function panel(title, body, icon) { return `<div class="mb-3 flex items-center gap-2"><i class="fa-solid ${icon} text-[#2AABEE]"></i><h2 class="text-xl font-black">${title}</h2></div>${body}`; }
function nav() {
  const html = tabs.map(([id, label, icon]) => `<button data-tab="${id}" class="${active === id ? 'tab-active' : ''} touch shrink-0 rounded-2xl border border-white/10 bg-white/5 px-3 text-xs font-black text-slate-300"><i class="fa-solid ${icon} mr-1"></i>${label}</button>`).join('');
  $('#navTabs').innerHTML = html; $('#sideTabs').innerHTML = html;
  $$('[data-tab]').forEach(b => b.onclick = () => { active = b.dataset.tab; localStorage.titanActiveTab = active; render(); closeMenu(); });
}
function stats() {
  const balance = Object.values(obj(state.wallets)).reduce((a, w) => a + Number(w.balance || 0), 0);
  $('#stats').innerHTML = [['Markets', marketItems().length, 'fa-store', '#2AABEE'], ['VIPs', profiles().length, 'fa-users', '#00C26F'], ['Wallet', money(balance), 'fa-wallet', '#FAC748'], ['Entries', arr(state.entries).length, 'fa-pen', '#FF5D5D']]
    .map(s => `<div class="card p-3"><i class="fa-solid ${s[2]}" style="color:${s[3]}"></i><p class="mt-2 text-xs text-slate-400">${s[0]}</p><b>${s[1]}</b></div>`).join('');
}

function ledgerRecord(m, t, idx) {
  const dict = typeKey(t) === 'PANEL' ? 'pannelData' : typeKey(t) === 'JODI' ? 'jodiData' : 'data';
  const prof = obj(obj(state.profiles)[state.activeId || 'admin1']);
  return obj(obj(obj(prof.dayRecords)[dateKey()])[dict])[idx] || obj(obj(obj(state.dayRecords)[dateKey()])[dict])[idx] || {};
}
function recovery(m, t, idx) { const r = ledgerRecord(m, t, idx); const loss = Number(r.loss || r.r || r.amount || 0); const rate = rateFor(t, loss); return { loss, rate, stake: Math.max(10, Math.ceil((loss + 100) / Math.max(rate - 1, 1))) }; }
function ledgerCard(m, idx) {
  const t = typeKey(ledgerSub), rec = ledgerRecord(m, t, idx), plan = recovery(m, t, idx), id = esc(m.id);
  return `<section class="card p-3"><div class="flex justify-between gap-2"><div><b>${esc(marketName(m))}</b><p class="text-[11px] text-slate-400">${t} · Open ${esc(obj(m.times).open || m.openTime || '-')} · Close ${esc(obj(m.times).close || m.closeTime || '-')}</p><p class="text-[11px] text-[#FAC748]">Rate ${plan.rate} · Recovery stake ${money(plan.stake)}</p></div><span class="pill">${esc(rec.status || rec._markStatus || 'READY')}</span></div>
  <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3"><input id="dig-${id}-${t}" class="input" value="${esc(rec.d || rec.digit || '')}" placeholder="${t} digit/card"><input id="amt-${id}-${t}" class="input" type="number" value="${esc(rec.r || rec.amount || '')}" placeholder="Amount"><input id="rate-${id}-${t}" class="input" value="${esc(rec.rate || plan.rate)}" placeholder="Rate"></div>
  <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-6"><button class="btn btn-blue" onclick="scrapeLedger('${id}','${t}',${idx})">Scrape</button><button class="btn btn-yellow" onclick="combineLedger('${id}','${t}',${idx})">Combine</button>${['T1','T2','T3','T4'].map(x => `<button class="btn btn-ghost" onclick="trick('${id}','${t}','${x}',${idx})">${x}</button>`).join('')}</div>
  <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-5"><button class="btn btn-yellow" onclick="applyRecovery('${id}','${t}',${idx})">Recovery</button><button class="btn btn-green" onclick="markLedger('${id}','${t}','pass',${idx})">PASS</button><button class="btn btn-red" onclick="markLedger('${id}','${t}','fail',${idx})">FAIL</button><button class="btn btn-ghost" onclick="markLedger('${id}','${t}','skip',${idx})">SKIP</button><button class="btn btn-ghost" onclick="saveLedger('${id}','${t}',${idx})">Reset/Save</button></div></section>`;
}
function ledger() { const t = typeKey(ledgerSub); return panel('Ledger', `<div class="sticky top-[69px] z-20 -mx-3 mb-3 border-b border-white/10 bg-[#0B1118]/95 px-3 py-2 backdrop-blur"><div class="grid grid-cols-3 gap-2">${['ANK','JODI','PANEL'].map(x => `<button class="btn ${t === x ? 'btn-blue' : 'btn-ghost'}" onclick="ledgerSub='${x}';render()">${x}</button>`).join('')}</div></div><div class="grid gap-3 lg:grid-cols-2">${marketItems().map(ledgerCard).join('') || empty('No markets found')}</div>`, 'fa-table'); }

function clients() { return panel('Clients (VIPs)', `<div class="grid gap-3 lg:grid-cols-2">${profiles().map(([id, p]) => `<div class="card p-3"><div class="flex gap-3"><div class="grid h-12 w-12 place-items-center rounded-2xl bg-[#2AABEE]/20 font-black">${esc((p.name || id)[0])}</div><div class="min-w-0 flex-1"><b>${esc(p.name || id)}</b><p class="break-all text-xs text-slate-400">${esc(p.phone || '-')} · ${esc(id)}</p><p class="text-xs">${esc(p.approvalStatus || 'pending')} · Exp ${esc(p.expiryDate || 'not set')} · ${money(walletFor(id).balance)}</p></div></div><div class="mt-3 grid grid-cols-2 gap-2"><button class="btn btn-green" onclick="vip('${id}','approve')">Approve</button><button class="btn btn-red" onclick="vip('${id}','reject')">Reject</button><input id="exp-${id}" type="date" class="input"><button class="btn btn-blue" onclick="expiry('${id}')">Set Expiry</button><button class="btn btn-ghost" onclick="access('${id}',${p.vipAccessEnabled === false})">${p.vipAccessEnabled === false ? 'Enable' : 'Disable'}</button><button class="btn btn-red" onclick="deleteVip('${id}')">Delete</button><button class="btn btn-yellow col-span-2" onclick="share(location.origin+'/?vip=${id}')">Share App Link</button></div></div>`).join('') || empty('No VIP profiles')}</div>`, 'fa-users'); }
function finance() { const subs = ['summary','wallets','payments','withdrawals']; return panel('Finance', `<div class="no-scrollbar mb-3 flex gap-2 overflow-x-auto">${subs.map(s => `<button class="btn ${financeSub === s ? 'btn-blue' : 'btn-ghost'} shrink-0" onclick="financeSub='${s}';render()">${s}</button>`).join('')}</div>${({ summary: finSummary, wallets, payments, withdrawals })[financeSub]()}`, 'fa-wallet'); }
function finSummary() { return `<div class="grid gap-3 md:grid-cols-3"><div class="card p-4"><p>Wallet balance</p><b class="text-2xl text-[#00C26F]">${money(Object.values(obj(state.wallets)).reduce((a,w)=>a+Number(w.balance||0),0))}</b></div><div class="card p-4"><p>Pending payments</p><b>${paymentList().filter(p=>/pending/i.test(p.status||'pending')).length}</b></div><div class="card p-4"><p>Pending withdrawals</p><b>${withdrawalList().filter(p=>/pending/i.test(p.status||'pending')).length}</b></div></div>`; }
function wallets() { return profiles().map(([id,p]) => `<div class="card mb-3 p-3"><b>${esc(p.name || id)}</b><p class="text-sm text-[#00C26F]">${money(walletFor(id).balance)}</p><div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4"><input id="amt-${id}" class="input" placeholder="Amount"><button class="btn btn-green" onclick="walletTx('${id}','credit')">Add</button><button class="btn btn-red" onclick="walletTx('${id}','debit')">Subtract</button><button class="btn btn-yellow" onclick="creditLimit('${id}')">Set Credit</button></div></div>`).join('') || empty('No wallets'); }
function payments() { return paymentList().map((p,i) => `<div class="card mb-3 p-3"><b>${esc(p.name || p.userId || 'Payment')}</b><p class="text-xs text-slate-400">${money(p.amount)} · ${esc(p.status || 'pending')} · UTR ${esc(p.utr || '-')}</p><button class="btn btn-green mt-2" onclick="payment('${p.id || i}','approve')">Approve</button> <button class="btn btn-red mt-2" onclick="payment('${p.id || i}','reject')">Reject</button></div>`).join('') || empty('No payments'); }
function withdrawals() { return withdrawalList().map((p,i) => `<div class="card mb-3 p-3"><b>${esc(p.name || p.userId || 'Withdrawal')}</b><p class="text-xs text-slate-400">${money(p.amount)} · ${esc(p.status || 'pending')}</p><button class="btn btn-green mt-2" onclick="withdraw('${p.id || i}','approve')">Approve</button> <button class="btn btn-blue mt-2" onclick="withdraw('${p.id || i}','paid')">Mark Paid</button> <button class="btn btn-red mt-2" onclick="withdraw('${p.id || i}','reject')">Reject</button></div>`).join('') || empty('No withdrawals'); }
function entries() { const totals = {}; arr(state.entries).forEach(e => { const k = e.market || e.marketName || 'Unknown'; totals[k] = (totals[k] || 0) + Number(e.amount || 0); }); return panel('Entries', `<div class="card mb-3 p-3 flex items-center justify-between"><div><b>WhatsApp Parser</b><p class="text-xs text-slate-400">Market/digit/user limits + auto-lock</p></div>${sw('parser', obj(state.entrySettings).parserEnabled !== false, v => post(API.entries, { ...obj(state.entrySettings), parserEnabled: v }))}</div><div class="card mb-3 p-3"><b>Market Load Totals</b><div class="mt-2 grid gap-2">${Object.entries(totals).map(([k,v])=>`<p class="text-sm">${esc(k)} <b class="float-right">${money(v)}</b></p>`).join('') || '<p class="text-sm text-slate-400">No load</p>'}</div><div class="mt-3 grid gap-2 sm:grid-cols-4"><input id="marketLimit" class="input" placeholder="Market limit"><input id="digitLimit" class="input" placeholder="Digit limit"><input id="userLimit" class="input" placeholder="User limit"><button class="btn btn-blue" onclick="saveRisk()">Save Risk</button></div></div><div class="grid gap-3 lg:grid-cols-2">${arr(state.entries).slice(-80).reverse().map(e=>`<div class="card p-3"><b>${esc(e.market || e.marketName || '-')}</b><p class="text-xs text-slate-400">${esc(e.userId || e.phone || '-')} · ${esc(e.type || '-')} · ${money(e.amount)}</p><p class="text-sm">${esc(e.text || e.raw || '')}</p></div>`).join('') || empty('No accepted entries')}</div>`, 'fa-pen-to-square'); }
function results() { return panel('Results', `<div class="card mb-3 p-3 grid gap-2 sm:grid-cols-3"><button class="btn btn-blue" onclick="post('${API.resultSettings}',{autoScrape:true,settlementEngine:true,autoLedgerMark:true})">Enable Auto Engines</button><button class="btn btn-yellow" onclick="post('/api/ledger_auto_mark',{})">Run Auto-Ledger Mark</button><button class="btn btn-red" onclick="post('/api/clear_invalid_auto_results',{})">Clear Old Results</button></div><div class="grid gap-3 md:grid-cols-2">${marketItems().map(m=>`<div class="card p-3"><b>${esc(marketName(m))}</b><div class="mt-2 grid grid-cols-2 gap-2"><input id="ro-${esc(m.id)}" class="input" placeholder="Open result"><input id="rc-${esc(m.id)}" class="input" placeholder="Close result"><button class="btn btn-green" onclick="saveResult('${esc(m.id)}','open')">Declare Open</button><button class="btn btn-blue" onclick="saveResult('${esc(m.id)}','close')">Declare Close</button><button class="btn btn-yellow" onclick="retryResult('${esc(m.id)}')">Retry Send</button><button class="btn btn-ghost" onclick="openTargets(${JSON.stringify(arr(m.resultTargets))},v=>saveRoleTargets('${esc(m.id)}','result',v))">Targets</button></div></div>`).join('')}</div>`, 'fa-trophy'); }
function marketsTab() { return panel('Markets', `<div class="card mb-3 p-3"><div class="grid gap-2 md:grid-cols-4"><input id="mn" class="input" placeholder="Market name"><input id="mo" class="input" placeholder="Open HH:MM"><input id="mc" class="input" placeholder="Close HH:MM"><button class="btn btn-green" onclick="addMarket()">Add Market</button></div></div><div class="grid gap-3 lg:grid-cols-2">${marketItems().map(m=>`<div class="card p-3"><div class="flex justify-between"><b>${esc(marketName(m))}</b><span class="pill">${m.enabled === false ? 'OFF' : 'ACTIVE'}</span></div><p class="text-xs text-slate-400">${esc(m.id)} · ${esc(obj(m.times).open || m.openTime || '-')} / ${esc(obj(m.times).close || m.closeTime || '-')}</p><div class="mt-2 flex flex-wrap gap-2">${['entry','schedule','result','forward','bookie'].map(r=>`<button class="btn btn-ghost" onclick="openTargets(${JSON.stringify(arr(m[r+'Targets']))},v=>saveRoleTargets('${esc(m.id)}','${r}',v))">${r}</button>`).join('')}</div><button class="btn btn-yellow mt-2" onclick="marketAction('${esc(m.id)}','archive')">Disable</button> <button class="btn btn-red mt-2" onclick="marketAction('${esc(m.id)}','delete')">Delete</button></div>`).join('')}</div>`, 'fa-store'); }
function forward() { return panel('Forward', `<div class="card p-3"><div class="grid gap-2 sm:grid-cols-3"><input id="forwardTime" class="input" value="${esc(obj(state.loadForwarder).time || obj(state.forwardSettings).time || '')}" placeholder="Schedule time"><button class="btn btn-ghost" onclick="openTargets(arr(state.forwardTargets),v=>{state.forwardTargets=v;toast('Targets selected',v.length+' selected')})">Targets</button><button class="btn btn-blue" onclick="previewLoad()">Preview</button></div><textarea id="forwardPreview" class="input mt-2 min-h-40">${esc(loadReport())}</textarea><button class="btn btn-green mt-2" onclick="saveForward()">Save</button> <button class="btn btn-yellow mt-2" onclick="sendForward()">Send Load Report</button></div>`, 'fa-share-nodes'); }
function guard() { return panel('Guard', `<div class="grid gap-3 md:grid-cols-2">${['duplicateBlock','dailyLimits','autoPause','targetSafety'].map(k=>`<div class="card p-3 flex items-center justify-between"><b>${k}</b>${sw(k, obj(state.spamGuardSettings)[k] !== false, v => { const s={...obj(state.spamGuardSettings),[k]:v}; state.spamGuardSettings=s; post(API.guard,s); })}</div>`).join('')}<div class="card p-3"><b>WhatsApp Safety</b><p class="text-xs text-slate-400">Pause/resume protects targets and daily limits.</p><button class="btn btn-red mt-2" onclick="post('${API.pause}',{})">Pause</button> <button class="btn btn-green mt-2" onclick="post('${API.resume}',{})">Resume</button></div></div>`, 'fa-shield-halved'); }
function backup() { return panel('Backup', `<div class="grid gap-2 md:grid-cols-3"><a class="btn btn-blue text-center" href="/api/download_backup">Download ZIP</a><a class="btn btn-green text-center" href="/api/export_csv">Export CSV</a><button class="btn btn-red" onclick="post('${API.clearAudit}',{})">Clear Audit</button></div><div class="mt-3 grid gap-2">${arr(state.auditLog || state.audit).slice(-50).reverse().map(a=>`<div class="card p-3 text-xs"><b>${esc(a.action || a.type || 'event')}</b><p class="text-slate-400">${esc(a.time || a.createdAt || '')} ${esc(JSON.stringify(a.detail || a).slice(0,180))}</p></div>`).join('') || empty('No audit events')}</div>`, 'fa-database'); }
function health() { setTimeout(loadHealth, 50); return panel('Health', `<div id="healthBox" class="grid gap-3 md:grid-cols-2"><div class="card p-4">Checking gateway, WhatsApp, scrape and counts...</div></div>`, 'fa-heart-pulse'); }
function ai() { return panel('Smart AI', `<div class="card p-3"><textarea id="aiText" class="input min-h-52" placeholder="Bulk entries paste karo..."></textarea><button class="btn btn-blue mt-2" onclick="parseAI()">Parse ANK / JODI / PANEL</button><div id="aiOut" class="mt-3"></div></div>`, 'fa-wand-magic-sparkles'); }
function empty(text) { return `<div class="card p-4 text-sm text-slate-400">${esc(text)}</div>`; }
function render() { nav(); stats(); const map = { ledger, clients, finance, entries, results, markets: marketsTab, forward, guard, backup, health, ai }; $('#content').innerHTML = (map[active] || ledger)(); }
function sw(id, checked, cb) { setTimeout(() => { const e = $(`#sw-${id}`); if (e) e.onchange = () => cb(e.checked); }, 0); return `<label class="switch"><input id="sw-${id}" type="checkbox" ${checked ? 'checked' : ''}><span></span></label>`; }

async function commitLedger(marketId, type, idx, action, extra = {}) {
  const m = marketItems().find(x => String(x.id) === String(marketId)) || { id: marketId };
  const t = typeKey(type);
  const rec = { ...ledgerRecord(m, t, idx), marketId, market: marketName(m), d: $(`#dig-${marketId}-${t}`)?.value || '', r: $(`#amt-${marketId}-${t}`)?.value || '', rate: $(`#rate-${marketId}-${t}`)?.value || rateFor(t), status: extra.status || 'saved', updatedAt: new Date().toISOString(), ...extra };
  return post(API.ledger, { activeId: state.activeId || 'admin1', profileId: state.activeId || 'admin1', type: apiType(t), idx, marketKey: marketId, date: dateKey(), action, record: rec, applyToVips: true }, 'Ledger updated');
}
window.applyRecovery = (id,t,idx) => { const m = marketItems().find(x => String(x.id) === String(id)) || { id }; const p = recovery(m,t,idx); $(`#amt-${id}-${typeKey(t)}`).value = p.stake; $(`#rate-${id}-${typeKey(t)}`).value = p.rate; toast('Recovery suggested', money(p.stake)); };
window.trick = (id,t,tr,idx) => { const inp = $(`#dig-${id}-${typeKey(t)}`); const xs = String(inp.value || '').split(/[\s,]+/).filter(Boolean); if (xs.length) inp.value = xs.slice(Number(tr[1]) - 1).concat(xs.slice(0, Number(tr[1]) - 1)).join(','); return commitLedger(id,t,idx,'trick_apply',{ trick: tr }); };
window.scrapeLedger = async (id,t,idx) => { const m = marketItems().find(x => String(x.id) === String(id)) || {}; const data = await fetchJson(API.scrape,{method:'POST',body:JSON.stringify({market:marketName(m)})}); const val = typeKey(t)==='ANK' ? (data.open || data.close || data.combined) : typeKey(t)==='JODI' ? (data.jodi || data.combined) : (data.panel || data.pannel || data.combined); if (val) $(`#dig-${id}-${typeKey(t)}`).value = val; return commitLedger(id,t,idx,'scrape_digits',{scrape:data}); };
window.combineLedger = async (id,t,idx) => { const m = marketItems().find(x => String(x.id) === String(id)) || {}; const data = await fetchJson(API.scrape,{method:'POST',body:JSON.stringify({market:marketName(m)})}); $(`#dig-${id}-${typeKey(t)}`).value = data.combined || [data.open,data.close,data.jodi].filter(Boolean).join(','); return commitLedger(id,t,idx,'combo_scrape',{scrape:data}); };
window.markLedger = (id,t,status,idx) => commitLedger(id,t,idx,`manual_${status}`,{status,_markStatus:status,autoMark:true});
window.saveLedger = (id,t,idx) => commitLedger(id,t,idx,'manual_input');
window.marketAction = (id, action) => post(API.market, { id, marketId: id, action });
window.saveRoleTargets = (id, role, targets) => post(API.market, { action: 'set_role_targets', id, marketId: id, role, targets });
window.addMarket = () => post(API.market, { action: 'direct_add_full', name: $('#mn').value, openTime: $('#mo').value, closeTime: $('#mc').value });
window.vip = (userId, action) => post(action === 'approve' ? '/api/approve_vip_profile' : '/api/reject_vip_profile', { userId, profileId: userId });
window.expiry = userId => post('/api/set_expiry', { userId, profileId: userId, expiryDate: $(`#exp-${userId}`).value });
window.access = (userId, vipAccessEnabled) => { const s={...state,profiles:{...obj(state.profiles),[userId]:{...obj(state.profiles)[userId],vipAccessEnabled}}}; return post(API.save,s); };
window.deleteVip = userId => confirm('Delete/disable VIP?') && window.access(userId, false);
window.walletTx = (userId, kind) => post(API.wallet, { userId, kind, amount: Number($(`#amt-${userId}`).value || 0), description: 'Admin dashboard' });
window.creditLimit = userId => post(API.credit, { userId, creditLimit: Number($(`#amt-${userId}`).value || 0) });
window.payment = (id, action) => post(action === 'reject' ? API.rejectPay : API.pay, { id, paymentId: id, action });
window.withdraw = (id, action) => post(API.withdraw, { id, withdrawalId: id, action });
window.saveRisk = () => post(API.risk, { marketLimit: $('#marketLimit').value, digitLimit: $('#digitLimit').value, userLimit: $('#userLimit').value, autoLock: true });
window.saveResult = (id, stage) => post(API.result, { marketId: id, stage, value: $(`#r${stage[0]}-${id}`).value, date: dateKey() });
window.retryResult = id => post(API.retryResult, { marketId: id });
window.previewLoad = async () => { const p = await fetchJson(API.preview).catch(() => ({ text: loadReport() })); $('#forwardPreview').value = p.text || p.preview || JSON.stringify(p, null, 2); };
window.saveForward = () => post(API.forward, { ...obj(state.loadForwarder), time: $('#forwardTime').value, targets: state.forwardTargets || [] });
window.sendForward = () => post(API.sendForward, { text: $('#forwardPreview').value, targets: state.forwardTargets || [] });
window.openTargets = (selected = [], cb = null) => { picker = { selected: [...selected], cb }; $('#targetModal').classList.remove('hidden'); drawTargets(); };
function drawTargets() { const q = ($('#targetSearch').value || '').toLowerCase(); $('#targetList').innerHTML = allTargets().filter(t => !q || t.toLowerCase().includes(q)).map(t => `<label class="mb-2 flex items-center gap-2 rounded-xl bg-white/5 p-3"><input type="checkbox" value="${esc(t)}" ${picker.selected.includes(t) ? 'checked' : ''}><span class="break-all text-sm">${esc(t)}</span></label>`).join('') || '<p class="text-sm text-slate-400">No targets found. Gateway se groups load hone ke baad yahan dikhenge.</p>'; }
function share(txt) { $('#shareText').value = txt; $('#shareModal').classList.remove('hidden'); } window.share = share;
function loadReport() { return marketItems().map(m => `${marketName(m)}: Open ${obj(m.times).open || m.openTime || '-'} Close ${obj(m.times).close || m.closeTime || '-'}`).join('\n'); }
window.parseAI = () => { const lines = $('#aiText').value.split(/\n+/).map(x=>x.trim()).filter(Boolean); $('#aiOut').innerHTML = lines.map(l => `<div class="card mb-2 p-3"><b>${/panel|pannel|\d{3}/i.test(l) ? 'PANEL' : /jodi|\b\d{2}\b/i.test(l) ? 'JODI' : 'ANK'}</b><p class="text-xs text-slate-400">${esc(l)}</p></div>`).join('') || empty('No lines parsed'); };
async function loadHealth() { try { const [h,g] = await Promise.all([fetchJson(API.health).catch(e=>({error:e.message})), fetchJson(API.gateway).catch(e=>({error:e.message}))]); $('#healthBox').innerHTML = `<div class="card p-4"><b>Gateway / WhatsApp</b><pre class="mt-2 whitespace-pre-wrap text-xs text-slate-400">${esc(JSON.stringify(g,null,2).slice(0,700))}</pre></div><div class="card p-4"><b>System Health</b><pre class="mt-2 whitespace-pre-wrap text-xs text-slate-400">${esc(JSON.stringify(h,null,2).slice(0,700))}</pre></div><div class="card p-4"><b>Counts</b><p>Markets ${marketItems().length} · VIP ${profiles().length} · Entries ${arr(state.entries).length}</p></div>`; } catch(e) { $('#healthBox').innerHTML = empty(e.message); } }
function closeMenu() { $('#sidebar').classList.add('-translate-x-full'); $('#scrim').classList.add('hidden'); }

$('#refreshBtn').onclick = () => load();
$('#sidebarToggle').onclick = () => { $('#sidebar').classList.remove('-translate-x-full'); $('#scrim').classList.remove('hidden'); };
$('#closeSidebar').onclick = $('#scrim').onclick = closeMenu;
$$('[data-close-modal]').forEach(b => b.onclick = () => b.closest('.modal').classList.add('hidden'));
$('#targetSearch').oninput = drawTargets;
$('#saveTargets').onclick = () => { const v = $$('#targetList input:checked').map(x => x.value); if (picker.cb) picker.cb(v); $('#targetModal').classList.add('hidden'); };
$('#copyShare').onclick = async () => { await navigator.clipboard?.writeText($('#shareText').value); if (navigator.share) navigator.share({ text: $('#shareText').value }).catch(()=>{}); toast('Copied'); };
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; $('#pwaBanner').classList.remove('hidden'); });
$('#installBtn').onclick = () => deferredInstall?.prompt();
$('#datePicker').value = today();
render();
load(true);
