#!/usr/bin/env python3
"""
Apply #43 Setup blank/render guard fix to flask_app.py.

This is intentionally a narrow, string-checked patcher for the current Titan Nova
single-file runtime. It does not rewrite app behavior; it wraps Setup rendering so
Setup shows a recovery card instead of a blank page when any optional helper/state
is missing or Gateway/Firebase config is incomplete.

Run from repo root:
    python3 scripts/apply_setup_blank_guard.py
    python3 scripts/titan_smoke_test.py
    node --check Gateway.js
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "flask_app.py"
MARKER = "SETUP_BLANK_GUARD_VERSION"

HELPERS = r'''
        // ======================================================
        // SETUP BLANK GUARD v43
        // Setup must never render as a blank page. Any missing
        // optional helper/state now falls back to a recovery card.
        // ======================================================
        const SETUP_BLANK_GUARD_VERSION = '2026-07-06-setup-blank-guard-v43';
        function setupSafeHtml(value){
            try { if(typeof htmlEscape === 'function') return htmlEscape(String(value ?? '')); } catch(e) {}
            return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
        }
        function setupSafeNotify(title, msg, type='info'){
            try { if(typeof showRealNotification === 'function') return showRealNotification(title, msg, type); } catch(e) {}
            try { console.log('[Setup]', title, msg); } catch(e) {}
        }
        function setupSafeNav(tab){
            try { if(typeof setMainNav === 'function') return setMainNav(tab); } catch(e) {}
            setupSafeNotify('Setup Recovery', 'Navigation helper unavailable: ' + tab, 'warning');
        }
        function ensureSetupStateDefaults(){
            try {
                if(typeof appState !== 'undefined' && appState){
                    if(!appState.ledgerSchedules || typeof appState.ledgerSchedules !== 'object' || Array.isArray(appState.ledgerSchedules)) appState.ledgerSchedules = {};
                    if(!appState.whatsappSafetyTargets || typeof appState.whatsappSafetyTargets !== 'object') appState.whatsappSafetyTargets = {};
                    if(!appState.backupSummary || typeof appState.backupSummary !== 'object' || Array.isArray(appState.backupSummary)) appState.backupSummary = {};
                    if(!appState.whatsappSafetySettings || typeof appState.whatsappSafetySettings !== 'object' || Array.isArray(appState.whatsappSafetySettings)) appState.whatsappSafetySettings = {};
                    if(!appState.healthMonitor || typeof appState.healthMonitor !== 'object' || Array.isArray(appState.healthMonitor)) appState.healthMonitor = {};
                    if(!appState.marketRegistry && typeof baseMarkets !== 'undefined' && Array.isArray(baseMarkets)) appState.marketRegistry = baseMarkets;
                }
                if(typeof state !== 'undefined' && state){
                    if(!state.config || typeof state.config !== 'object' || Array.isArray(state.config)) state.config = {};
                    ['ank','jodi','pannel'].forEach(k => { if(!state.config[k] || typeof state.config[k] !== 'object' || Array.isArray(state.config[k])) state.config[k] = {tgt:0}; });
                    if(typeof state.config.capital === 'undefined') state.config.capital = 0;
                    if(typeof state.config.dayTarget === 'undefined') state.config.dayTarget = 0;
                }
            } catch(e) {
                try { console.warn('Setup default guard warning:', e); } catch(_e) {}
            }
        }
        function renderSetupErrorCard(err){
            const message = setupSafeHtml((err && (err.stack || err.message)) || err || 'Unknown setup render error');
            return `<div class="px-3 py-4 pb-24">
                <div class="native-card p-5 mb-3" style="border-color:rgba(250,199,72,0.35);background:rgba(250,199,72,0.06)">
                    <div class="flex items-start gap-3">
                        <div class="w-11 h-11 rounded-xl bg-[rgba(250,199,72,0.14)] text-[var(--amber)] flex items-center justify-center shrink-0"><i class="fas fa-triangle-exclamation"></i></div>
                        <div class="min-w-0">
                            <h3 class="text-white font-black text-[14px] uppercase">Setup Recovery Mode</h3>
                            <p class="text-[10px] text-[var(--text-muted)] leading-relaxed mt-1">Setup tab blank hone se roka gaya. App running hai, lekin Setup render me optional state/helper missing hai.</p>
                        </div>
                    </div>
                    <pre class="mt-3 text-[9px] text-[var(--amber)] whitespace-pre-wrap break-words bg-[#17212B] rounded-xl p-3 border border-[rgba(250,199,72,0.18)] max-h-36 overflow-y-auto">${message}</pre>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3">
                        <button onclick="setupSafeNav('health')" class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-heart-pulse mr-1 text-[var(--primary)]"></i>Health</button>
                        <button onclick="setupSafeNav('backup')" class="w-full bg-[var(--surface-light)] border border-[var(--border)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-file-export mr-1 text-[var(--primary)]"></i>Backup</button>
                        <button onclick="location.reload()" class="w-full bg-[var(--primary)] text-white py-3 rounded-xl font-black text-[10px] uppercase"><i class="fas fa-rotate-right mr-1"></i>Reload</button>
                    </div>
                </div>
            </div>`;
        }
'''

OLD_TARGET_COUNTS = r'''        function setupTargetCounts(listLike){
            const ids = Array.isArray(listLike) ? listLike : Object.values(listLike || {}).map(x => x && (x.id || x.target)).filter(Boolean);
            return ids.reduce((acc, id) => {
                if(normalizeTargetType(targetTypeFromId(id), id) === 'group') acc.groups += 1;
                else acc.contacts += 1;
                return acc;
            }, {groups:0, contacts:0});
        }
'''

NEW_TARGET_COUNTS = r'''        function setupTargetCounts(listLike){
            let ids = [];
            try {
                if(Array.isArray(listLike)) ids = listLike;
                else if(listLike && typeof listLike === 'object') ids = Object.values(listLike).map(x => x && (x.id || x.target || x.jid || x.phone || x)).filter(Boolean);
            } catch(e) { ids = []; }
            return ids.reduce((acc, id) => {
                let kind = 'contact';
                try {
                    if(typeof normalizeTargetType === 'function' && typeof targetTypeFromId === 'function') kind = normalizeTargetType(targetTypeFromId(id), id);
                    else if(String(id || '').includes('@g.us')) kind = 'group';
                } catch(e) { if(String(id || '').includes('@g.us')) kind = 'group'; }
                if(kind === 'group') acc.groups += 1;
                else acc.contacts += 1;
                return acc;
            }, {groups:0, contacts:0});
        }
'''

OLD_RENDER_DECL = "        function renderSetupTab(){\n"
NEW_RENDER_DECL = "        function renderSetupTabUnsafe(){\n"

OLD_AFTER_RENDER = "        }\n\n        function renderBackupAuditTab(){"
NEW_AFTER_RENDER = r'''        }

        function renderSetupTab(){
            try {
                if(!IS_MASTER) return '';
                ensureSetupStateDefaults();
                return renderSetupTabUnsafe();
            } catch(e) {
                try { console.error('Setup render failed:', e); } catch(_e) {}
                return renderSetupErrorCard(e);
            }
        }

        function renderBackupAuditTab(){'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Setup blank guard already present; nothing to do.")
        return 0

    anchor = "        function setupStatusBadge(ok, text){\n"
    text = replace_once(text, anchor, HELPERS + "\n" + anchor, "setup helper anchor")
    text = replace_once(text, OLD_TARGET_COUNTS, NEW_TARGET_COUNTS, "setupTargetCounts block")
    text = replace_once(text, OLD_RENDER_DECL, NEW_RENDER_DECL, "renderSetupTab declaration")
    text = replace_once(text, OLD_AFTER_RENDER, NEW_AFTER_RENDER, "renderSetupTab wrapper insertion anchor")

    TARGET.write_text(text, encoding="utf-8")
    print("Applied #43 Setup blank/render guard fix to flask_app.py")
    print("Next: python3 scripts/titan_smoke_test.py && node --check Gateway.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
