from pathlib import Path
import argparse
from titan_runtime_files import ensure_runtime_file

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "flask_app.py"
ensure_runtime_file("flask_app.py")
MARKER = "TITAN_WHATSAPP_UI_PATCH_V1"

PATCH = r'''

# TITAN_WHATSAPP_UI_PATCH_V1
# WhatsApp-style UI theme injector. This is a local visual layer only; it does not
# change routes, Firebase keys, ledger logic, or Gateway behavior.
TITAN_WHATSAPP_UI_CSS = r"""
<style id="titan-whatsapp-ui-v1">
:root{
  --wa-bg:#0b141a; --wa-panel:#111b21; --wa-card:#202c33; --wa-card2:#1f2c34;
  --wa-green:#00a884; --wa-green2:#25d366; --wa-text:#e9edef; --wa-muted:#8696a0;
  --wa-border:rgba(134,150,160,.22); --wa-danger:#ff6b6b;
  --primary:#00a884!important; --accent:#25d366!important; --bg:#0b141a!important;
  --surface:#111b21!important; --surface-light:#202c33!important; --border:rgba(134,150,160,.22)!important;
  --text:#e9edef!important; --text-muted:#8696a0!important;
}
html,body{background:var(--wa-bg)!important;color:var(--wa-text)!important;font-family:Inter,Roboto,Arial,sans-serif!important;}
body{background:
  radial-gradient(circle at 16% 0%, rgba(0,168,132,.22), transparent 30%),
  radial-gradient(circle at 88% 12%, rgba(37,211,102,.10), transparent 26%),
  linear-gradient(180deg,#0b141a 0%,#111b21 48%,#0b141a 100%)!important;
  background-attachment:fixed!important;}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background-image:
  linear-gradient(135deg, rgba(233,237,239,.025) 25%, transparent 25%),
  linear-gradient(225deg, rgba(233,237,239,.025) 25%, transparent 25%),
  linear-gradient(45deg, rgba(233,237,239,.018) 25%, transparent 25%),
  linear-gradient(315deg, rgba(233,237,239,.018) 25%, rgba(11,20,26,.04) 25%)!important;
  background-position:12px 0,12px 0,0 0,0 0!important;background-size:24px 24px!important;opacity:.68!important;}
header,.header,.topbar,.top-bar,.app-header,[class*="header"],[class*="top"]{background:#075e54!important;border-color:rgba(255,255,255,.08)!important;color:#fff!important;box-shadow:0 8px 26px rgba(0,0,0,.22)!important;}
.native-card,.card,.panel,.box,[class*="native-card"],[class*="glass"],[class*="surface"]{
  background:linear-gradient(160deg,rgba(32,44,51,.98),rgba(17,27,33,.98))!important;
  border:1px solid var(--wa-border)!important;border-radius:18px!important;box-shadow:0 10px 24px rgba(0,0,0,.28)!important;color:var(--wa-text)!important;
}
.native-card::before,.card::before{border-radius:18px!important;opacity:.15!important;}
input,textarea,select,.input,[contenteditable="true"]{background:#2a3942!important;border:1px solid rgba(134,150,160,.28)!important;color:var(--wa-text)!important;border-radius:14px!important;box-shadow:none!important;}
input::placeholder,textarea::placeholder{color:#8696a0!important;}
button,.btn,[role="button"]{border-radius:999px!important;font-weight:800!important;letter-spacing:.02em!important;box-shadow:none!important;}
button:not(.danger):not([class*="fail"]),.btn-primary,.active,[class*="primary"]{background:linear-gradient(135deg,#00a884,#25d366)!important;color:#06140f!important;border-color:rgba(37,211,102,.45)!important;}
button[class*="fail"],.danger,[class*="danger"]{background:#ff6b6b!important;color:#fff!important;border-color:rgba(255,107,107,.45)!important;}
.bottom-nav,.tabbar,.footer-nav,nav[class*="bottom"],.fixed.bottom-0,.fixed[class*="bottom"]{
  background:#111b21!important;border-top:1px solid var(--wa-border)!important;box-shadow:0 -10px 30px rgba(0,0,0,.30)!important;color:var(--wa-muted)!important;
}
.bottom-nav .active,.tabbar .active,nav .active{color:#25d366!important;background:rgba(0,168,132,.13)!important;}
.toast,.notification,[class*="toast"],[class*="notification"]{
  background:#202c33!important;color:#e9edef!important;border:1px solid rgba(37,211,102,.28)!important;border-radius:18px!important;box-shadow:0 14px 42px rgba(0,0,0,.45)!important;
}
.toast::before,.notification::before{background:#00a884!important;}
.badge,.pill,[class*="badge"],[class*="pill"]{background:rgba(0,168,132,.18)!important;color:#25d366!important;border:1px solid rgba(37,211,102,.25)!important;border-radius:999px!important;}
.table,.list,.row,[class*="list"]{border-color:var(--wa-border)!important;}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#374045;border-radius:999px}::-webkit-scrollbar-track{background:#111b21}
#titan-wa-brand{position:fixed;left:50%;top:9px;transform:translateX(-50%);z-index:9999;color:#fff;font-weight:900;font-size:14px;letter-spacing:.02em;pointer-events:none;text-shadow:0 1px 4px rgba(0,0,0,.35)}
@media(max-width:700px){.native-card,.card,.panel,[class*="native-card"]{margin:10px!important;border-radius:18px!important}button,.btn{min-height:40px!important}.bottom-nav,.tabbar{min-height:72px!important}}
</style>
<script id="titan-whatsapp-ui-v1-js">
(function(){try{document.documentElement.classList.add('titan-whatsapp-ui');function brand(){if(document.getElementById('titan-wa-brand'))return;var b=document.createElement('div');b.id='titan-wa-brand';b.textContent='TITAN NOVA';document.body.appendChild(b);}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',brand);else brand();}catch(e){}})();
</script>
"""

@app.after_request
def titan_whatsapp_ui_theme(resp):
    try:
        enabled = str(os.environ.get('TITAN_WHATSAPP_UI', '1')).strip().lower() not in ('0', 'false', 'no', 'off')
        if not enabled:
            return resp
        ctype = str(resp.headers.get('Content-Type') or '')
        if 'text/html' not in ctype.lower():
            return resp
        html = resp.get_data(as_text=True)
        if 'titan-whatsapp-ui-v1' in html:
            return resp
        if '</head>' in html:
            html = html.replace('</head>', TITAN_WHATSAPP_UI_CSS + '</head>', 1)
        else:
            html = TITAN_WHATSAPP_UI_CSS + html
        resp.set_data(html)
        try:
            resp.headers['Content-Length'] = str(len(resp.get_data()))
        except Exception:
            pass
    except Exception:
        pass
    return resp
# /TITAN_WHATSAPP_UI_PATCH_V1
'''


def apply_patch(text: str) -> tuple[str, bool]:
    if MARKER in text:
        return text, False
    anchor = "def titan_no_store_realtime_api(resp):"
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError("after_request anchor not found")
    return_pos = text.find("\n    return resp", pos)
    if return_pos < 0:
        raise RuntimeError("after_request return anchor not found")
    insert_at = text.find("\n", return_pos + 1)
    if insert_at < 0:
        insert_at = return_pos + len("\n    return resp")
    new_text = text[:insert_at] + PATCH + text[insert_at:]
    return new_text, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    original = TARGET.read_text(encoding="utf-8", errors="replace")
    patched, changed = apply_patch(original)
    if not changed:
        print("WhatsApp UI patch already present")
        return 0
    print("WhatsApp UI patch can be applied")
    if args.apply:
        backup = TARGET.with_suffix(TARGET.suffix + ".wa-ui.bak")
        backup.write_text(original, encoding="utf-8")
        TARGET.write_text(patched, encoding="utf-8")
        print(f"Applied WhatsApp-style UI patch. Backup: {backup.name}")
    else:
        print("Dry-run only. Use --apply to modify flask_app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
