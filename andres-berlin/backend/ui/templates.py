"""HTML templates for the Titan Nova dashboard."""

HOME_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Titan Nova Dashboard</title>
  <style>
    :root { color-scheme: dark; --bg:#07141f; --panel:#0f2233; --panel2:#132b40; --text:#f4fbff; --muted:#9fb7c8; --green:#25d366; --blue:#35a7ff; --warn:#ffd166; --border:#25465f; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; background:linear-gradient(135deg,#06111b 0%,#0b2134 55%,#06291d 100%); color:var(--text); font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header { padding:22px 16px 18px; background:rgba(7,20,31,.92); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:2; backdrop-filter:blur(14px); }
    .wrap { width:min(1120px,100%); margin:0 auto; }
    .topline { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
    h1 { margin:0; font-size:clamp(28px,6vw,46px); letter-spacing:-.04em; }
    .badge { display:inline-flex; align-items:center; gap:8px; border:1px solid rgba(37,211,102,.45); background:rgba(37,211,102,.13); color:#bcffd5; border-radius:999px; padding:8px 12px; font-weight:800; }
    main { padding:18px 16px 34px; }
    .hero { display:grid; grid-template-columns:1.3fr .7fr; gap:16px; margin:10px 0 16px; }
    .card { background:rgba(15,34,51,.9); border:1px solid var(--border); border-radius:22px; padding:18px; box-shadow:0 18px 50px rgba(0,0,0,.25); }
    .card h2 { margin:0 0 8px; font-size:22px; }
    .muted { color:var(--muted); line-height:1.5; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }
    .module { min-height:138px; display:flex; flex-direction:column; justify-content:space-between; }
    .module strong { font-size:18px; }
    .status { margin-top:12px; font-size:13px; color:var(--muted); word-break:break-word; }
    .module-actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
    button, a.btn { appearance:none; border:0; border-radius:14px; padding:12px 14px; background:var(--blue); color:#001423; font-weight:900; text-decoration:none; display:inline-flex; justify-content:center; cursor:pointer; }
    a.secondary { background:var(--panel2); color:var(--text); border:1px solid var(--border); }
    .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
    .ok { color:var(--green); } .warn { color:var(--warn); }
    @media (max-width:720px) { .hero { grid-template-columns:1fr; } header { position:static; } }
  </style>
</head>
<body>
  <header><div class="wrap topline"><h1>⚡ Titan Nova Dashboard</h1><span class="badge">● Dashboard live</span></div></header>
  <main class="wrap">
    <section class="hero">
      <div class="card">
        <h2>Dashboard aa gaya ✅</h2>
        <p class="muted">Starter page hata diya gaya hai. Yahan se Wallet, Ledger, Markets, Payments, Withdrawals aur WhatsApp gateway status directly check kar sakte ho.</p>
        <div class="actions">
          <a class="btn" href="/health">Health</a>
          <a class="btn secondary" href="/api/whatsapp/status">WhatsApp status</a>
          <a class="btn secondary" href="/api/markets/status">Markets</a>
        </div>
      </div>
      <div class="card">
        <h2>System</h2>
        <div id="health" class="status">Checking backend...</div>
        <div id="whatsapp" class="status">Checking WhatsApp gateway...</div>
      </div>
    </section>
    <section class="grid" id="modules"></section>
  </main>
  <script>
    const modules = [
      ['Wallet', '/api/wallet/summary', 'User balances aur transactions summary.'],
      ['Ledger', '/api/ledger/summary', 'Accounts ledger entries aur totals.'],
      ['Markets', '/api/markets/status', 'Market quotes/status module.'],
      ['Payments', '/api/payments/status', 'Recent payment credits.'],
      ['Withdrawals', '/api/withdrawals/status', 'Recent debit/withdrawal requests.'],
      ['Admin', '/api/admin/status', 'Admin API status; token ho to protected rahega.']
    ];
    const box = document.getElementById('modules');
    const short = (data) => JSON.stringify(data).slice(0, 180) + (JSON.stringify(data).length > 180 ? '…' : '');
    async function load(url) {
      const res = await fetch(url, {cache:'no-store'});
      const data = await res.json().catch(() => ({status:'error', error:'Invalid JSON'}));
      return {ok: res.ok, data};
    }
    function paintModule([name, url, desc], summary = {}) {
      const el = document.createElement('article');
      el.className = 'card module';
      const status = summary.status || 'ready';
      el.innerHTML = `<div><strong>${name}</strong><p class="muted">${desc}</p></div><div class="status"><span class="${status === 'ok' ? 'ok' : 'warn'}">${status === 'ok' ? 'Summary ready' : 'Ready'}</span> ${short(summary)}</div><div class="module-actions"><button type="button">Load details</button><a class="btn secondary" href="${url}">Open API</a></div>`;
      const statusEl = el.querySelector('.status');
      const detailButton = el.querySelector('button');
      detailButton.addEventListener('click', async () => {
        detailButton.disabled = true;
        statusEl.innerHTML = 'Loading details...';
        try {
          const result = await load(url);
          statusEl.innerHTML = `<span class="${result.ok ? 'ok' : 'warn'}">${result.ok ? 'OK' : 'Needs attention'}</span> ${short(result.data)}`;
        } catch (err) {
          statusEl.innerHTML = `<span class="warn">Unavailable</span> ${err.message}`;
        } finally {
          detailButton.disabled = false;
        }
      });
      box.appendChild(el);
    }
    load('/health').then(r => health.innerHTML = `<span class="ok">OK</span> ${short(r.data)}`).catch(e => health.innerHTML = `<span class="warn">Unavailable</span> ${e.message}`);
    function paintWhatsappStatus(result) {
      const data = result.data || {};
      const unavailable = data.status === 'unavailable' || data.gatewayReachable === false || !result.ok;
      const stale = data.stale ? ' stale cached status shown;' : '';
      whatsapp.innerHTML = `<span class="${unavailable ? 'warn' : 'ok'}">${unavailable ? 'Gateway unavailable' : 'Gateway OK'}</span>${stale} ${short(data)}`;
    }
    function refreshWhatsappStatus() {
      whatsapp.innerHTML = `<span class="warn">Refreshing WhatsApp gateway in background...</span>`;
      load('/api/whatsapp/status')
        .then(paintWhatsappStatus)
        .catch(e => whatsapp.innerHTML = `<span class="warn">Gateway unavailable</span> ${e.message}`);
    }
    window.setTimeout(refreshWhatsappStatus, 0);
    load('/api/dashboard/summary')
      .then(r => {
        const summary = r.data.modules || {};
        modules.forEach(([name, url, desc]) => paintModule([name, url, desc], summary[name.toLowerCase()] || {}));
      })
      .catch(() => modules.forEach(module => paintModule(module)));
  </script>
</body>
</html>
"""
