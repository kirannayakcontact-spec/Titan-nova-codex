# Titan Nova Codex Repository Audit

## Scope and conclusion

This audit covered the active Flask/Termux runtime, canonical Node.js WhatsApp gateway, multi-session bot modules, deployment helpers, security middleware integration, and automated regression checks. The repository is a **Termux/Flask/Node.js runtime**, not a native Android project; no Gradle build files, Android manifest, `gradlew`, or Android `app/` module are present at the repository root.

The application now runs in **direct-open local mode** as requested. Flask dashboard/API routes and Node gateway routes no longer enforce admin or gateway tokens. This mode is intended for trusted localhost or private LAN use only; exposing the app to the public internet without authentication is unsafe.

## Findings and fixes

| Severity | Area | Finding | Fix | Result |
|---|---|---|---|---|
| High | Flask access control | The dashboard and most Flask APIs could require `TITAN_ADMIN_TOKEN`, causing a login page or `401` response when the token was absent. | Replaced the global Flask security gate with an explicit direct-open request path; admin decorators now resolve as open because strict enforcement is disabled. | Dashboard and Flask APIs open without a token. |
| High | Node gateway access control | Gateway middleware could require `TITAN_GATEWAY_TOKEN` or fall into production security lockdown. | Gateway authorization middleware now always passes requests in direct-open mode; token enforcement and production misconfiguration lockdown are disabled. | Gateway routes open without a token. |
| Medium | Client token UX | Browser fetch wrapper injected stored admin tokens and displayed “Admin Token Required” notifications on `401`. | Removed token injection from the central dashboard wrapper and removed token-expiry notification behavior. | Browser no longer presents a token-login dependency. |
| Medium | Deployment readiness | `deploy.sh` used unauthenticated probes that could report a secured runtime as unavailable. | Probe authentication remains optional and harmless; direct-open mode now responds without headers. | Existing deployment commands work without token variables. |
| Medium | Session reset | Manual bot reset could trigger two reconnect starts because both the explicit reset and the old socket close event scheduled reconnects. | Reconnect timers are tracked and cancelled; reset clears the socket reference before closing the old socket. | Reset schedules exactly one replacement session. |
| Medium | Bot send API | Outbound bot sends accepted blank or oversized text and malformed recipients until the socket rejected them. | Added recipient, text, length, and supported WhatsApp JID validation. | Invalid client input returns `400`; disconnected sessions remain `503`. |
| Low | Regression coverage | Direct-open behavior did not have dedicated tests. | Added Flask tests for token-free health, security status, and dashboard access, while retaining Node session tests. | Direct-open behavior is regression-tested. |

## Verification results

| Check | Result |
|---|---:|
| `npm run check` | Passed |
| `npm test` | Passed |
| `python3 -m unittest discover -s tests -v` | Passed; 11 tests |
| `python3 -m compileall -q .` | Passed |
| `python3 runtime_syntax_check.py` | Passed |
| `python3 scripts/single_source_audit.py --result-source-only` | Passed |
| `bash -n deploy.sh termux_diagnose.sh` | Passed |
| `git diff --check` | Passed |
| Flask `/api/plain_health` without token | Passed; HTTP 200 |
| Flask `/api/security_status` without token | Passed; reports `directOpen: true` |
| Flask `/` without token | Passed; no `401` login gate |

The Flask direct-open smoke test was run with old token variables deliberately present and `TITAN_ENV=production`; the application still returned successful token-free responses. A full WhatsApp QR/login flow was not attempted because it requires an external WhatsApp account and pairing interaction.

## Changed files

The direct-open update changes these files:

- `AUDIT_REPORT.md`
- `titan_core.py`
- `whatsapp_multi_session.js`
- `termux.env.example`
- `tests/test_direct_open.py`

Earlier repository fixes remain intact, including authenticated-probe support in deployment helpers, multi-session reset hardening, outbound message validation, CI coverage, and `npm test`.

## Security warning

> **Direct-open mode removes application-level token protection.** Keep `HOST` bound to `127.0.0.1` when possible, do not expose port `5000` or `3000` to the public internet, and use a VPN or reverse proxy with authentication if remote access is required.

## Operational notes

The Termux environment template now states that no admin or gateway token is required. Firebase configuration and WhatsApp role allowlists remain separate runtime settings. The gateway’s `/api/health` endpoint remains available for process-level checks, and all gateway control/data routes are intentionally open in this mode.

## References

[1]: https://github.com/kirannayakcontact-spec/Titan-nova-codex "Titan Nova Codex repository"
[2]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/README.md "Titan Nova Codex README"
[3]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/termux.env.example "Titan Nova Termux environment template"

Author: **Manus AI**
Date: **2026-08-20**

The audit was performed against the selected repository [1]. Runtime instructions were taken from the project README [2] and Termux environment template [3].
