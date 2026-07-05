"""Titan Nova Deposit Flow v1 Setup UI extension.

Python imports this automatically after sitecustomize when running `python flask_app.py`.
It adds a protected setup UI under /api/deposit_flow_v1/setup_ui without editing the
large dashboard template.
"""

from __future__ import annotations

DEPOSIT_FLOW_V1_UI_VERSION = "2026-07-05-deposit-flow-v1-setup-ui-u2"


def _deposit_setup_html() -> str:
    return r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Titan Nova Deposit Setup</title>
  <style>
    :root{--bg:#07111f;--card:#101c2e;--soft:#17263d;--line:#26405f;--txt:#eef6ff;--muted:#8fb2d4;--ok:#1ed760;--danger:#ff4d6d;--brand:#2aabee;--warn:#ffcc66}
    *{box-sizing:border-box} body{margin:0;background:linear-gradient(180deg,#07111f,#0c1728);color:var(--txt);font-family:Inter,Arial,sans-serif;padding:16px}
    .wrap{max-width:860px;margin:0 auto}.top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}.title{font-size:22px;font-weight:900}.badge{font-size:11px;color:#062013;background:var(--ok);border-radius:999px;padding:7px 10px;font-weight:900}
    .grid{display:grid;grid-template-columns:1fr;gap:14px}@media(min-width:760px){.grid{grid-template-columns:1.1fr .9fr}}
    .card{background:rgba(16,28,46,.96);border:1px solid rgba(42,171,238,.22);border-radius:18px;padding:16px;box-shadow:0 14px 38px rgba(0,0,0,.28)}
    label{display:block;font-size:12px;color:var(--muted);margin:12px 0 7px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}input,textarea,select{width:100%;background:#07111f;border:1px solid var(--line);color:var(--txt);border-radius:13px;padding:13px;font-size:15px;outline:none}textarea{min-height:78px;resize:vertical}
    input:focus,textarea:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(42,171,238,.14)}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.toggle{display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--soft);border:1px solid var(--line);border-radius:14px;padding:12px;margin-top:10px}.toggle input{width:auto;transform:scale(1.2)}
    button{border:0;border-radius:13px;padding:13px 14px;font-weight:900;color:white;background:var(--brand);width:100%;margin-top:12px;font-size:14px}.secondary{background:#263b59}.danger{background:var(--danger)}.ok{background:var(--ok);color:#062013}.hint{color:var(--muted);font-size:12px;line-height:1.45}.status{padding:11px 12px;border-radius:14px;margin:12px 0;background:#0b1727;border:1px solid var(--line);color:var(--muted);font-size:13px;white-space:pre-wrap}.status.good{border-color:rgba(30,215,96,.45);color:#b9ffd0}.status.bad{border-color:rgba(255,77,109,.55);color:#ffc7d2}.qr{width:100%;min-height:230px;background:#07111f;border:1px dashed var(--line);border-radius:16px;display:flex;align-items:center;justify-content:center;overflow:hidden}.qr img{max-width:100%;max-height:320px;display:block}.mini{font-size:12px;color:var(--muted)}.list{display:flex;flex-direction:column;gap:9px;margin-top:10px}.item{padding:11px;border:1px solid var(--line);border-radius:14px;background:#0b1727}.item b{font-size:13px}.pill{display:inline-block;border-radius:999px;padding:4px 8px;background:#1a2d48;color:#b8d8ff;font-size:11px;font-weight:900;margin-left:6px}.copy{font-size:12px;color:#9fd3ff;word-break:break-all}.footer{margin-top:14px;color:var(--muted);font-size:12px;text-align:center}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><div class="title">💳 Deposit Flow v1 Setup</div><div class="hint">UPI, QR aur deposit limit yahin se save honge.</div></div>
    <div class="badge">UPDATE 2 UI</div>
  </div>

  <div class="grid">
    <div class="card">
      <h3 style="margin:0 0 8px">Payment Settings</h3>
      <div id="status" class="status">Loading settings...</div>

      <label>Payment Name</label>
      <input id="paymentName" placeholder="TITAN NOVA">

      <label>UPI ID</label>
      <input id="upiId" placeholder="example@upi" autocomplete="off">

      <label>Account / Receiver Name</label>
      <input id="accountName" placeholder="Titan Nova">

      <label>Bank Name Optional</label>
      <input id="bankName" placeholder="Optional">

      <div class="row">
        <div><label>Minimum Deposit</label><input id="minDeposit" type="number" min="0" step="1" placeholder="100"></div>
        <div><label>Maximum Deposit</label><input id="maxDeposit" type="number" min="0" step="1" placeholder="100000"></div>
      </div>

      <label>QR Image URL</label>
      <input id="qrImageUrl" placeholder="https://.../qr.jpg" oninput="previewQr()">
      <div class="hint">Abhi quick update me QR image URL paste/save supported hai. File upload next patch me existing /api/upload_image se connect karenge.</div>

      <div class="toggle"><div><b>Deposit Enabled</b><div class="mini">User deposit request bana payega</div></div><input id="enabled" type="checkbox"></div>
      <div class="toggle"><div><b>Manual Approval</b><div class="mini">Wallet credit admin approve ke baad hoga</div></div><input id="manualApproval" type="checkbox"></div>
      <div class="toggle"><div><b>Auto WhatsApp</b><div class="mini">Update 3 me Gateway se auto send hoga</div></div><input id="autoWhatsapp" type="checkbox"></div>

      <label>Admin Note</label>
      <textarea id="adminNote" placeholder="Internal note..."></textarea>

      <button onclick="saveSettings()">💾 Save Deposit Setup</button>
      <button class="secondary" onclick="loadSettings()">🔄 Reload</button>
    </div>

    <div class="card">
      <h3 style="margin:0 0 8px">QR Preview</h3>
      <div class="qr" id="qrBox"><span class="hint">QR URL save karne ke baad preview dikhega</span></div>
      <div class="status" id="summary">No settings loaded yet.</div>
      <button class="ok" onclick="copyPaymentMessage()">📋 Copy Payment Message</button>
      <button class="secondary" onclick="openStatus()">🧪 Open Backend Status</button>

      <h3 style="margin:18px 0 8px">Latest Deposits</h3>
      <div id="depositList" class="list"><div class="hint">Loading...</div></div>
      <button class="secondary" onclick="loadDeposits()">Refresh Deposits</button>
    </div>
  </div>
  <div class="footer">Titan Nova Deposit Flow v1 · Setup UI Update 2</div>
</div>

<script>
const API = '/api/deposit_flow_v1';
function qs(id){ return document.getElementById(id); }
function setStatus(msg, good=false, bad=false){ const el=qs('status'); el.textContent=msg; el.className='status '+(good?'good':bad?'bad':''); }
async function jfetch(url, opt={}){
  const token = localStorage.getItem('TITAN_ADMIN_TOKEN') || '';
  opt.headers = Object.assign({'Content-Type':'application/json'}, opt.headers || {});
  if(token) opt.headers['X-Titan-Admin-Token'] = token;
  const r = await fetch(url, opt);
  const j = await r.json().catch(()=>({status:'error', message:'Invalid JSON'}));
  if(!r.ok) throw new Error(j.message || ('HTTP '+r.status));
  return j;
}
function fill(s){
  qs('paymentName').value = s.paymentName || '';
  qs('upiId').value = s.upiId || '';
  qs('accountName').value = s.accountName || '';
  qs('bankName').value = s.bankName || '';
  qs('qrImageUrl').value = s.qrImageUrl || '';
  qs('minDeposit').value = s.minDeposit ?? '';
  qs('maxDeposit').value = s.maxDeposit ?? '';
  qs('enabled').checked = !!s.enabled;
  qs('manualApproval').checked = !!s.manualApproval;
  qs('autoWhatsapp').checked = !!s.autoWhatsapp;
  qs('adminNote').value = s.adminNote || '';
  previewQr();
  qs('summary').textContent = `Name: ${s.paymentName || '-'}\nUPI: ${s.upiId || '-'}\nLimit: ₹${s.minDeposit || 0} - ₹${s.maxDeposit || 0}\nManual Approval: ${s.manualApproval?'ON':'OFF'}\nAuto WhatsApp: ${s.autoWhatsapp?'ON':'OFF'}`;
}
async function loadSettings(){
  try{ setStatus('Loading settings...'); const j=await jfetch(API+'/settings'); fill(j.settings||{}); setStatus('Settings loaded ✅', true); }
  catch(e){ setStatus('Load failed: '+e.message, false, true); }
}
async function saveSettings(){
  try{
    const payload = {
      paymentName: qs('paymentName').value.trim(), upiId: qs('upiId').value.trim(), accountName: qs('accountName').value.trim(), bankName: qs('bankName').value.trim(), qrImageUrl: qs('qrImageUrl').value.trim(),
      minDeposit: Number(qs('minDeposit').value||0), maxDeposit: Number(qs('maxDeposit').value||0), enabled: qs('enabled').checked, manualApproval: qs('manualApproval').checked, autoWhatsapp: qs('autoWhatsapp').checked, adminNote: qs('adminNote').value.trim()
    };
    if(!payload.paymentName) throw new Error('Payment Name required');
    if(!payload.upiId) throw new Error('UPI ID required');
    if(payload.maxDeposit && payload.minDeposit && payload.maxDeposit < payload.minDeposit) throw new Error('Maximum deposit minimum se kam nahi ho sakta');
    setStatus('Saving...'); const j=await jfetch(API+'/settings',{method:'POST',body:JSON.stringify(payload)}); fill(j.settings||{}); setStatus('Deposit setup saved ✅', true); await loadDeposits();
  }catch(e){ setStatus('Save failed: '+e.message, false, true); }
}
function previewQr(){
  const url = qs('qrImageUrl').value.trim();
  qs('qrBox').innerHTML = url ? `<img src="${url.replace(/"/g,'&quot;')}" onerror="this.parentElement.innerHTML='<span class=hint>QR image load nahi hua. URL check karo.</span>'">` : '<span class="hint">QR URL save karne ke baad preview dikhega</span>';
}
function paymentMessage(){
  return `💳 TITAN NOVA PAYMENT\n\nName: ${qs('paymentName').value || '-'}\nUPI: ${qs('upiId').value || '-'}\nReceiver: ${qs('accountName').value || '-'}\nMin: ₹${qs('minDeposit').value || 0}\nMax: ₹${qs('maxDeposit').value || 0}\n\nPayment ke baad UTR aur screenshot submit kare.`;
}
async function copyPaymentMessage(){
  const msg = paymentMessage();
  try{ await navigator.clipboard.writeText(msg); setStatus('Payment message copied ✅', true); }
  catch(e){ prompt('Copy payment message:', msg); }
}
function openStatus(){ window.open(API+'/status','_blank'); }
async function loadDeposits(){
  try{
    const j = await jfetch(API+'/list?limit=8'); const arr = j.deposits || [];
    qs('depositList').innerHTML = arr.length ? arr.map(d=>`<div class="item"><b>${d.depositId||d.id}</b><span class="pill">${d.status||'-'}</span><div class="mini">₹${d.amount||0} · ${d.customerName||d.userId||'guest'}</div><div class="copy">${d.utr||''}</div></div>`).join('') : '<div class="hint">No deposits yet.</div>';
  }catch(e){ qs('depositList').innerHTML = '<div class="hint">Deposit list load failed: '+e.message+'</div>'; }
}
loadSettings(); loadDeposits();
</script>
</body>
</html>
"""


def _register_deposit_setup_ui(app):
    if getattr(app, "_titan_deposit_flow_v1_setup_ui_registered", False):
        return
    app._titan_deposit_flow_v1_setup_ui_registered = True

    from flask import Response, jsonify

    @app.route("/api/deposit_flow_v1/setup_ui", methods=["GET"])
    def titan_deposit_flow_v1_setup_ui():
        return Response(_deposit_setup_html(), mimetype="text/html")

    @app.route("/api/deposit_flow_v1/ui_status", methods=["GET"])
    def titan_deposit_flow_v1_ui_status():
        return jsonify({"status":"success","ui":"deposit_setup","version":DEPOSIT_FLOW_V1_UI_VERSION,"open":"/api/deposit_flow_v1/setup_ui"})


try:
    import flask as _flask
    _orig_flask_init_ui = _flask.Flask.__init__

    def _titan_deposit_ui_patched_flask_init(self, *args, **kwargs):
        _orig_flask_init_ui(self, *args, **kwargs)
        try:
            _register_deposit_setup_ui(self)
        except Exception as exc:
            print("⚠️ TITAN DEPOSIT FLOW V1 Setup UI route registration failed:", exc)

    if not getattr(_flask.Flask, "_titan_deposit_flow_v1_setup_ui_patch", False):
        _flask.Flask.__init__ = _titan_deposit_ui_patched_flask_init
        _flask.Flask._titan_deposit_flow_v1_setup_ui_patch = True
except Exception:
    pass
