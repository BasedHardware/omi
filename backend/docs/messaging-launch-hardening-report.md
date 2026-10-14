# Brief Q — messaging launch hardening handoff

Repository: public `BasedHardware/omi`. Worktree:
`/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-msg-launch-hardening-upstream-keep-clean`.
Branch: `lane/msg-launch-hardening`; supplied base `f0d1b5496582`.
Implementation validated through `983d8f636036`. All changes are local commits.
No push, PR, merge, deployment, provider call, production account access, gcloud,
secret read, force push, stash or new GitHub workflow was performed.
The existing untracked `.agent-req-Q.json` was preserved.

## Commits

- **A — `358b9ff655a6`**: backend admission, seats, queue/event storage, guarded replies,
  shared pacing, metrics, cleanup entrypoint and regression tests.
- **B — `c002de48dce4`**: client polling, cleanup Helm chart, alert rules, flag registry,
  operations/architecture documentation and field-index fixture update.
- **C — `bb485677cd3e`**: messaging field-index declaration moved to its owning module;
  central index registry stays at its original size under the repository ratchet.
- **D — `983d8f636036`**: app awareness for either channel policy, additional tests,
  durable suite manifests and operations clarifications.
- This report is committed separately; it changes no serving behavior.

## Per-item result

| Item | Status and behavior | Owning files / commits | Validation |
| --- | --- | --- | --- |
| 1. Channel admission | **Done.** JSON policy is authoritative; malformed config denies. Telegram can admit every valid paid user. iMessage defaults Operator/Architect, with configurable cohort/plans/cap. Absent JSON retains legacy env admission. Optional Firestore kill document is cached <=60s and fails closed. App awareness admits either eligible channel. | `backend/config/messaging.py`, `utils/messaging/access.py`, `app_awareness.py`, `adapters/runtime.py`, `routers/messaging.py`; A, B, D | Plan/cohort/legacy/malformed policy, remote-cache/failure and iMessage-only app tests; V1, V2, V4 |
| 2. iMessage seats | **Done for required cap.** Atomic redemption counts distinct linked users, including dormant users. Multiple identities share one seat; last unlink/deletion releases it. Mint returns typed HTTP 409 and stores a waitlist when full; redemption races are authoritative. Uninitialized counters deny. **Optional dormancy release skipped:** retaining links is conservative and preserves the prohibition on proactive sends. No dormant-user notices or auto-promotions are sent. | `database/messaging.py`, `routers/messaging.py`, `utils/messaging/access.py`, `gateway.py`; A, D | Real last-seat contention, second identity/relink, unlink/deletion, waitlist erasure and typed HTTP error tests; V1, V2 |
| 3. Pending recovery | **Done.** Recovery queries the inbox collection group by status/channel/provider, ordered and limited. Per-turn pending reads filter status and cap 100; unlink queries only associated sessions/messages. A one-time metadata preparation preserves legacy pending rows. | `database/messaging.py`, `messaging_queries.py`, `firestore_index_registry.py`, query-driver registry, root `firestore.indexes.json`; A, C | Emulator query/recovery and legacy metadata tests; generated index/query guard; V2, V4 |
| 4. Event ceiling | **Done.** Awareness reads a forty-event tail. Replay fences use deterministic hashed document IDs and survive pruning. Events carry numeric sequence; legacy fences migrate once before compaction. Huge awareness text is clipped while authoritative messages stay in shared chat storage. No 500 KB hard failure. `/new` / `new chat` rotates the surface session pointer under its lease. | `database/messaging.py`, `gateway.py`, Telegram/Linq parsers; A | Tail pruning, repeated old event, legacy fence retention, fresh session and command-without-model tests; V1, V2 |
| 5. Cleanup | **Done in source; installation required.** Hourly Helm CronJob is opt-in, using an admitted backend image and existing service identity/secret. Each run caps 100 records/category: expired proofs plus mirrors, unknown unlinked identities, old done markers, stale waitlist. Running reconciliation evidence and linked identities remain. No provider is constructed. | `database/messaging.py`, `utils/messaging/maintenance.py`, `charts/messaging-maintenance/`; A, B | Emulator retention/safety tests, entrypoint tests, Helm lint/render; V1, V2, V5 |
| 6. Rate limiting | **Done.** Unknown/invalid-proof instructions are limited once per sender/hour. Ordinary linked turns use the app's same UID and `chat:send_message` limiter (including its boost/shadow/fail-open policy); throttle notices are limited once/minute. | `gateway.py`, `database/messaging.py`; A | No-model throttling, same UID/policy, once-per-window replies and lease release; V1 |
| 7. Visible failures | **Done.** Access-loss notices are reason-specific and throttled, with deletion/revocation guards. Expired pending rows receive one claimed resend-notice attempt respecting reply windows. Malformed Telegram start tokens return 202 and link help. Draft errors record fallback, disable further previews for that turn and preserve final delivery. | `gateway.py`, `database/messaging.py`, Telegram parser, `outbound.py:text`; A | Access loss/FIFO, expiry claim/window, real FastAPI webhook 202, preview degradation and failure regressions; V1, V2 |
| 8. Telegram pacing | **Done.** Runtime defaults to Redis server-clock reservation for global and per-chat pacing across instances, scoped by hashed bot identity. Redis errors deny sends; local mode is only safe for one process/instance. Existing streaming `none` is verified. Every retry is paced and bounded 429 retry_after waits are honored. | `utils/messaging/pacing.py`, `adapters/telegram.py`, `runtime.py`, `transport.py`; A, B | Two Redis clients share reservation deadlines, provider retry/pacing contract and existing streaming tests; V1, V2 |
| 9. Metrics/alerts | **Done in source; installation/export verification required.** Bounded counters for completed/failed inbox turns and failure reasons, provider HTTP attempts/status, latency and queue-age histograms. Prometheus rules cover sustained failure/throttle ratios and queue/turn p95. Runbook covers kill switch, drop_pending_updates, 300s takeover and seats. | `metrics.py`, gateway/transport, `charts/monitoring/messaging/alerts.yaml`, runbook; A, B | Counter assertions on throttle/provider attempts, fixture failures, YAML/render checks and preflight; V1, V2, V4, V5 |
| 10. Client polling | **Done.** Caller is mobile provider + connect-sheet waiter. Entry loads cache for 60s; explicit refresh bypasses it. Proof-only polling backs off to 30s and pauses while backgrounded. Screen-return checks remain. No active desktop/web poller was found; those paths contain generated endpoint wrappers. A backend cache was unnecessary because connect confirmation needs fresh reads. | `app/lib/providers/messaging_channels_provider.dart`, `app/lib/pages/settings/chat_apps/channel_link_waiter.dart`, focused tests; B | Cached-load/explicit-refresh, pending-only backoff/background/stop and existing connect/expiry tests; V3 |
| 11. Forwarded content | **Done.** `forward_origin` sets normalized `forwarded` evidence and an explicit untrusted-content prefix. Private-chat, bot/group, edited-message and signature guards are retained. | Telegram parser, `contracts.py`, `gateway.py:inbound_evidence`; A | Forwarded/parser regression plus existing adapter signature/group/bot contracts; V1 |

## Validation commands and measured layers

All backend test executions used `backend/test.sh` with Google application credentials
unset. Suite lists below are committed; run from the worktree root. These are local
fixtures/emulators, not live provider or production acceptance and not GitHub CI.

**V1 — focused backend + prescribed compatibility suites:** **469 passed, 7 skipped**
(the skipped cases require explicitly requested loopback Firestore/Redis).

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/launch-unit-files.txt" bash backend/test.sh
```

Final log: `/tmp/q-backend-complete.log`.

**V2 — real loopback Firestore transactions + two local Redis clients:** **54 passed**.
The emulator and Redis were started only for this task, on 127.0.0.1 with no persistence
or cloud credentials. The subsequent iMessage-only app-policy test is covered by V1.

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS MESSAGING_TEST_REDIS_HOST=127.0.0.1:16389 MESSAGING_TEST_FIRESTORE_HOST=127.0.0.1:18885 BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/launch-emulator-files.txt" bash backend/test.sh
```

Final log: `/tmp/q-emulator-complete.log`. Standalone query-shape/outside-caller run:
**494 passed, 1 deselected**, `/tmp/q-index-final.log`. Full seven-file index guard also
passed within preflight, including the updated field-count fixture.

**V3 — canonical mobile runner:** **138 spine contracts + 42 focused tests passed**;
its shell configuration/locale guards also passed.

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS bash app/test.sh test/providers/messaging_channels_provider_test.dart test/pages/settings/chat_apps/chat_apps_page_test.dart test/pages/settings/chat_apps/channel_link_waiter_test.dart
```

Final log: `/tmp/q-app-final.log`. The shell guard intentionally prints a rejected
invalid-flavor fixture; the runner exited successfully. No visual layout was changed.

**V4 — repository and draft metadata:** **44 local checks passed** for each command.
The local draft contains `UI-Evidence: none` for polling-only logic and
`Failure-Class: none`; no size exception or other bypass was used. No PR was opened.

```sh
scripts/pr-preflight --suggest
scripts/pr-preflight --pr-body-file /tmp/q-pr-body.md
env -u GOOGLE_APPLICATION_CREDENTIALS OMI_PR_BODY_FILE=/tmp/q-pr-body.md make preflight
```

Logs: `/tmp/q-pr-metadata.log`, `/tmp/q-preflight-complete.log`.
Architecture advisory warnings remain for the large gateway and existing large tests;
all mandatory checks passed. The first attempts exposed a fixed field-count expectation,
the central registry size ratchet and missing local UI metadata; these were resolved.

**V5 — scheduler/artifact checks:** Helm lint passed (one chart, zero failed);
enabled template rendered with synthetic bindings; generated indexes and whitespace
checks passed. Alert rules are a checked-in PrometheusRule, not a deployed alert.

```sh
helm lint backend/charts/messaging-maintenance
helm template q-cleanup backend/charts/messaging-maintenance --set enabled=true --set image=backend:test --set serviceAccountName=test-sa --set secretName=test-secret
backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py --write
git diff --check
```

## Deploy requirements and remaining choices

1. Apply the generated indexes before the runtime depends on the group queries; wait READY.
2. Stop provider delivery, disable both env admission policies and settle/reconcile workers.
   Run `python -m utils.messaging.maintenance --prepare-launch` with the admitted image
   and existing service identity. It backfills content-free legacy inbox metadata and
   reconciles distinct linked iMessage members. Confirm initialized count before reopening.
3. Set `OMI_MESSAGING_CHANNEL_POLICY` to Telegram enabled/cohort `*`; iMessage enabled,
   desired cohort, plans `["operator","architect"]`, seat_cap `180`. Legacy envs alone
   intentionally do not launch all paid users. No deployment manifest was changed to
   activate this automatically before seat reconciliation.
4. Optional hot kill switch: bind `OMI_MESSAGING_KILL_SWITCH_DOC` and create explicit
   per-channel true/false values; absent/read-failed document denies. Otherwise use env rolls.
5. Keep `OMI_TELEGRAM_SHARED_PACING=on`, confirm shared Redis, and prefer existing
   `OMI_TELEGRAM_STREAMING=none` at launch. `off` pacing is not safe for a multi-instance fleet.
6. Install the opt-in maintenance chart with admitted image, existing service account,
   backend secret and retention/cadence. Apply alert rules beside monitoring and verify
   actual Cloud Run metric export/scraping. No new workflow or IAM change is supplied.
7. Linq's actual billable count/seat entitlement must be checked by the operator before
   rollout or increasing 180; this source cap counts Omi linked users. It does not claim
   to replace the provider's billing ledger.

No product decision blocks this implementation: Operator+Architect and 180 seats were
chosen as requested. Dormancy release/proactive notices remain an optional future decision.
The backend typed waitlist response is ready for UI consumption; a new waitlist screen,
client plan-gate copy, chips/buttons, citation stripping and help redesign were deliberately
left to the later UI lane. `rendering.py`, `finish_payload` and `chat_citations.py` were not
changed. This task did not verify live bot/Linq delivery, provider billing or deployment.

Shared `origin/main` advanced to `8df191cdaa76` while this lane stayed on its supplied base.
No sync/rebase was performed: David plans more work and one combined PR. Reconcile the
final combined branch with current upstream and rerun required checks before publication.

## Exact source files touched (against supplied base)

```text
app/changelog/unreleased/20261014-messaging-link-polling.json
app/lib/pages/settings/chat_apps/channel_link_waiter.dart
app/lib/providers/messaging_channels_provider.dart
app/test/pages/settings/chat_apps/channel_link_waiter_test.dart
app/test/providers/messaging_channels_provider_test.dart
backend/charts/messaging-maintenance/Chart.yaml
backend/charts/messaging-maintenance/templates/cronjob.yaml
backend/charts/messaging-maintenance/values.yaml
backend/charts/monitoring/messaging/alerts.yaml
backend/config/messaging.py
backend/database/firestore_index_registry.py
backend/database/messaging.py
backend/database/messaging_queries.py
backend/docs/feature-flag-registry.md
backend/docs/messaging-channels.md
backend/docs/runbooks/messaging-channels.md
backend/routers/messaging.py
backend/testing/messaging/launch-emulator-files.txt
backend/testing/messaging/launch-unit-files.txt
backend/testing/messaging/store.py
backend/tests/support/firestore_query_driver_registry.py
backend/tests/unit/test_firestore_field_indexes.py
backend/tests/unit/test_messaging_adapters.py
backend/tests/unit/test_messaging_adapters_firestore.py
backend/tests/unit/test_messaging_channels.py
backend/tests/unit/test_messaging_firestore.py
backend/tests/unit/test_messaging_launch_hardening.py
backend/tests/unit/test_messaging_live_qa.py
backend/tests/unit/test_messaging_queue.py
backend/tests/unit/test_messaging_threads.py
backend/utils/messaging/ARCHITECTURE.md
backend/utils/messaging/access.py
backend/utils/messaging/adapters/linq.py
backend/utils/messaging/adapters/runtime.py
backend/utils/messaging/adapters/telegram.py
backend/utils/messaging/adapters/transport.py
backend/utils/messaging/app_awareness.py
backend/utils/messaging/contracts.py
backend/utils/messaging/gateway.py
backend/utils/messaging/maintenance.py
backend/utils/messaging/metrics.py
backend/utils/messaging/outbound.py
backend/utils/messaging/pacing.py
config/feature-flags.yaml
firestore.indexes.json
```
