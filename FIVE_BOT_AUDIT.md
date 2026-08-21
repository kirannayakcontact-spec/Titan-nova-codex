# Titan Nova 5-Bot System Audit

## Executive conclusion

The current system is a **hybrid architecture**, not a fully independent five-bot platform. `owner_bot` remains the legacy monolithic socket in `whatsapp_multi_session.js`, while `finance_bot`, `game_bot`, `result_bot`, and `ledger_bot` are managed by the modular `TitanMultiSessionManager`. Each isolated role receives its own auth directory, but the handlers still reuse legacy functions that depend on process-global `sock` and `connected` variables.

The architecture can work in light traffic, but it is not yet fully correct for production-grade isolation. The largest risks are **global socket mutation during concurrent handlers, a duplicate-processing gap for the four isolated bots, bypass of the central safe-send/reliability pipeline, incomplete WhatsApp message normalization, and weak readiness/persistence guarantees**.

## Current topology

| Bot | Current session ownership | Current handler | Main concern |
|---|---|---|---|
| `owner_bot` | Legacy socket and legacy auth directory in `whatsapp_multi_session.js` | Legacy control/owner command handler | Monolith remains coupled to all global runtime state. |
| `finance_bot` | Isolated Baileys socket and `auth_info_baileys/finance_bot` | Deposit proof/image and withdrawal handlers | Uses `withRoleSocket()` to mutate global `sock`; no isolated dedupe. |
| `game_bot` | Isolated Baileys socket and `auth_info_baileys/game_bot` | Smart user command, spam guard, entry handler | Global socket dependency and serialized behavior are not explicit. |
| `result_bot` | Isolated Baileys socket and `auth_info_baileys/result_bot` | `#declare` command handler | Restricted role allowlist can silently block commands. |
| `ledger_bot` | Isolated Baileys socket and `auth_info_baileys/ledger_bot` | Ledger/schedule/audit/accounting command handler | Restricted role allowlist can silently block commands. |

## Findings

| Severity | Finding | Evidence and impact | Corrective action |
|---|---|---|---|
| Critical | **Global socket mutation breaks true isolation.** | `withRoleSocket()` temporarily assigns an isolated socket to global `sock` and `connected`. Any overlapping handler, timer, background callback, or legacy function that reads `sock` can send through the wrong bot. The `finally` block restores the previous socket, but it cannot protect asynchronous work that escaped the awaited handler. | Remove global socket reads from role handlers. Pass an immutable `BotContext` containing `socket`, `role`, `send`, `reply`, `presence`, and `group` helpers into every handler. Do not use `withRoleSocket()` as the long-term isolation mechanism. |
| Critical | **Isolated sends bypass the central safety pipeline.** | `TitanMultiSessionManager.send()` directly calls `rec.socket.sendMessage()`. The canonical `sendText()` pipeline performs target resolution, WhatsApp validation, safety checks, serial queueing, reliability recording, and durable outcome handling. The bot API route bypasses these protections. | Inject a role-aware `sendForRole()` callback into the manager and route every outbound message through the same validation, safety, queue, idempotency, and reliability pipeline. |
| High | **No duplicate guard for four isolated bots.** | The legacy owner socket calls `rememberIncomingMessage()`, but `TitanMultiSessionManager.onMessages()` processes every message without a per-role message-id cache. Baileys retries, reconnect replay, or duplicate upserts can repeat deposits, withdrawals, entries, or commands. | Add a persistent per-role LRU/dedup store keyed by `role + remoteJid + participant + messageId`, with TTL, bounded size, and a “mark before handler” rule. Persist only the minimum required identifiers. |
| High | **Message normalization is incomplete in modular code.** | `bot/message_utils.js` reads only `conversation`, `extendedTextMessage`, image caption, and document caption. It does not unwrap `ephemeralMessage`, `viewOnceMessage`, or `viewOnceMessageV2`, and it does not cover all media/button/list variants used by the legacy parser. Commands or payment images can therefore be ignored. | Create one shared `unwrapMessage()` and `extractMessageText()` implementation and use it in both owner and isolated paths. Add fixtures for text, extended text, ephemeral text, view-once image, document caption, buttons, and list responses. |
| High | **WhatsApp command authorization is separate from HTTP direct-open mode.** | `finance_bot`, `result_bot`, and `ledger_bot` remain in `RESTRICTED_ROLES`. Their commands are accepted only when the sender number is in environment allowlists. If those variables are missing, commands are silently ignored. Removing HTTP tokens does not remove this WhatsApp role authorization. | Make authorization explicit in status output and logs. Return a clear configured/not-configured state per role. Normalize `participantPn`, `senderPn`, `participantAlt`, and group participant IDs before comparison. Do not silently drop an administrator’s command. |
| High | **Sender identity extraction is too narrow.** | `senderNumber()` checks only `key.participant` or `key.remoteJid`. WhatsApp multi-device messages can provide alternate participant fields such as `participantPn`, `senderPn`, or other LID-linked values. Legitimate restricted-role administrators can be denied. | Build a `senderCandidates()` resolver, normalize phone/JID/LID forms, and match against both role allowlists and verified group metadata. |
| High | **Startup has no five-session readiness barrier.** | `startAll()` starts four sessions and returns immediately; it does not await all startup attempts or expose a clear `ready/starting/failed/logged_out` aggregate state. The dashboard can report a partially initialized system as if startup completed. | Return `Promise.allSettled()` results, record per-role startup phase and timestamps, and expose `/api/bots/readiness` with required/optional role policy. |
| High | **Redis auth persistence is not authoritative or atomic.** | `hydrate()` overlays Redis files on top of any existing local files and does not remove stale local files. `persist()` reads and writes files without a role lock or temporary-file atomic swap. A failed Redis connection remains stored as a rejected `clientPromise`, so later retries cannot recover in-process. | Decide whether Redis or local disk is the source of truth. Add per-role distributed/local locks, atomic writes, stale-file cleanup, reconnectable Redis client state, bounded credential file validation, and explicit persistence health in bot status. |
| Medium | **Duplicate processes can share the same auth directories.** | There is no process-level lock covering the gateway and the per-role auth directories. Starting two gateway instances can cause concurrent credential writes and conflicting sockets. | Add a gateway PID/lock file and refuse a second process. Include the process owner and start timestamp in diagnostics. |
| Medium | **One slow message blocks the whole upsert batch.** | `onMessages()` awaits each message serially in the received array. A slow Firebase read or WhatsApp response delays later messages and can cause backlogs. | Add a bounded per-role queue with concurrency policy: sequential for money operations, controlled parallelism for read-only commands, and backpressure metrics. |
| Medium | **Handler failures are dropped without durable retry or dead-letter state.** | Handler errors are logged through a promise catch, but the message is not recorded as failed, retried, or surfaced in role health. Financial messages can disappear from the operational view after a transient failure. | Record message outcome as `received`, `processing`, `succeeded`, `failed`, or `dead_letter`; add bounded retry rules and operator-visible failure counters. Money operations must be idempotent before retry. |
| Medium | **QR state is memory-only and external QR rendering is fragile.** | Isolated QR strings live in the manager process and the Flask proxy redirects to `api.qrserver.com`. A restart loses QR state, and a network failure prevents the dashboard QR image from rendering. | Keep QR expiry/status per role, expose a local QR image endpoint, and show exact age/error state. Avoid depending on a third-party QR image service for local login. |
| Medium | **The API route is too powerful for direct-open mode.** | `/api/bots/send` and reset endpoints are open after direct-open mode was enabled. The send endpoint can trigger arbitrary bot messages, and reset can delete role auth state. | Keep direct-open bound to localhost only. If LAN access is needed, add a separate network boundary or restore authentication for control endpoints even if the dashboard remains open. Add action audit logs and role-specific permissions. |
| Low | **The current tests are mostly source assertions.** | Existing architecture tests confirm strings and wiring but do not simulate concurrent sockets, duplicate messages, Redis failure, QR expiry, handler failures, or real HTTP route behavior for all roles. | Add fake-socket integration tests, concurrency tests, auth persistence tests, route tests, and a deterministic end-to-end test harness with no real WhatsApp account. |

## What is currently “wrong” in practical terms

The most likely user-visible failures are that one bot may reply through another bot, a payment or entry may be processed twice, a command may be ignored even though the sender is configured as admin, an image sent as view-once may not be recognized, the dashboard may show a bot as disconnected while it is still starting, and a bot may lose or corrupt its session after Redis/local-auth recovery. These are architectural reliability problems rather than just syntax bugs.

## Correct implementation sequence

### Phase 1: Establish strict boundaries

Create a `BotContext` object for every role. It should contain the role name, socket reference, connection state, normalized sender identity, and role-scoped operations. Refactor handlers so they accept `context` and never read or mutate the process-global `sock` or `connected` values. Keep the legacy owner handler behind an adapter until it is fully migrated.

### Phase 2: Build one inbound pipeline

Every session should use the same ordered pipeline: unwrap and normalize the message, derive all sender candidates, reject status/from-me messages, deduplicate by message key, authorize the role, enqueue the message, run the handler, and persist an outcome. This prevents the owner path and isolated paths from behaving differently.

### Phase 3: Build one outbound pipeline

Every send—including `/api/bots/send`, scheduled messages, replies, moderation notices, and result declarations—must use one role-aware queue. The queue should validate recipient, apply rate limits and safety rules, add idempotency metadata, send through the correct socket, record the result, and expose retry state. Direct `socket.sendMessage()` calls should be limited to the queue implementation and explicitly tested adapters.

### Phase 4: Make persistence and lifecycle deterministic

Use one auth directory per role, enforce a single gateway process, and expose a per-role state machine: `idle`, `starting`, `qr_ready`, `connecting`, `connected`, `reconnecting`, `logged_out`, and `failed`. `startAll()` should return a structured `Promise.allSettled()` result. Redis failure must either fail closed with a visible state or fall back according to an explicit policy; it must not remain a permanently rejected hidden promise.

### Phase 5: Add real integration coverage

Test five fake sockets concurrently. Send the same message twice and verify one handler execution. Run finance and game handlers simultaneously and verify that each outbound message uses its own socket. Test view-once images, group participants, LID/phone identity variants, reset during reconnect, Redis unavailable/reconnected, and failed money handlers. Add route tests for status, QR, reset, and send behavior.

## Recommended priority

The first production fixes should be the global socket removal, the shared deduplication layer, and the safe outbound send callback. These three changes address the highest risk of cross-bot messages and duplicate money actions. The next priority should be sender normalization and explicit role authorization status. Persistence locks, readiness state, local QR rendering, and comprehensive integration tests should follow before treating the five-bot system as production-complete.

## References

[1]: https://github.com/kirannayakcontact-spec/Titan-nova-codex "Titan Nova Codex repository"
[2]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/bot/session_manager.js "Titan multi-session manager"
[3]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/bot/message_utils.js "Titan message utilities"
[4]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/redis_auth_state.js "Titan Redis authentication state adapter"
[5]: https://github.com/kirannayakcontact-spec/Titan-nova-codex/blob/main/whatsapp_multi_session.js "Titan canonical WhatsApp gateway"

Author: **Manus AI**
Date: **2026-08-20**

This audit is based on the selected repository [1], its modular session manager [2], message utilities [3], Redis auth adapter [4], and canonical gateway [5].

## Remediation status

The following fixes have now been implemented in the repository: shared wrapped-message normalization, per-role persistent message deduplication, multi-device sender-candidate authorization, a role-aware safe outbound callback, serialized handler execution around the legacy compatibility adapter, awaited `Promise.allSettled()` startup results, explicit per-role readiness reporting, reconnect-on-start-failure behavior, reconnect timer ownership, Redis client recovery after connection failure, serialized/atomic Redis credential persistence, stale-file cleanup when Redis contains authoritative credentials, and a single gateway process lock.

The current direct-open mode remains intentional. HTTP token protection is disabled, but restricted WhatsApp role allowlists remain active for `finance_bot`, `result_bot`, and `ledger_bot`; this prevents arbitrary WhatsApp users from invoking privileged commands. Keep the gateway bound to localhost or a trusted private network.

Verification after remediation: `npm run check`, `npm test`, `python3 -m unittest discover -s tests -v`, `python3 -m compileall -q .`, `python3 runtime_syntax_check.py`, `python3 scripts/single_source_audit.py --result-source-only`, `bash -n deploy.sh termux_diagnose.sh`, and `git diff --check` all pass. The test suite currently contains 11 Python tests plus the Node session-manager regression suite, including wrapped-message parsing, duplicate suppression, multi-device admin identity, safe-send callback routing, reset behavior, and route validation.
