# Conversation task membership (#20620)

## Behavior and authority

Home rows use a compact accessible badge. Search → Has tasks opens a separate
server-backed browse page; Back restores the existing Home/search state. Query,
date, folder and starred controls intersect before result pagination.
The existing Show Discarded Conversations preference is forwarded to the server.

“Has tasks” means at least one **current, undeleted canonical action item** whose
`conversation_id` is this conversation. Completed and manually linked items count.
Unaccepted/rejected Candidates and stale summary suggestions do not. Relinking or
merging follows the canonical link; no historical count, task creation, task text,
new projection or migration is introduced. Deleted, missing or foreign parents
are excluded. Locked parents are hidden from badges. A filtered page can return
a locked parent only after the existing paid-access policy restores it.
Task-source backlinks remain #19859.

`conversation_task_links` owns the bounded metadata join for both surfaces.
Browse discovery uses the existing chronological index and visibility/codec;
textual discovery reuses the current conversation search owner. Both scans are
read-only. Access recovery checks eligibility for linked matches and writes only
the selected response page. Text discovery advances by the raw index page even
when hydration drops stale or inaccessible hits. Public search continues to
report pagination from visible results. Text hydration, membership and recovery
eligibility share the request budget. Filter cursors
are signed, expire after one hour, and bind the owner and all filter inputs.
Sparse scans may return an empty intermediate page **with continuation**, which
the UI never labels “No results”. A budget failure without progress is retryable.
The presence read uses existing task version invalidation and a 15-second cache.
Its 120/hour limit is exempt from the global rate-limit multiplier by default.
No new composite-index deployment is required; runtime query guards verify this.

The mobile presence reader batches mounted row IDs (max 100 retained), invalidates
on existing task/conversation notifications, and fences account/revision changes.
Cheap selected keys ignore task selection, ordinary capture ticks and other
unrelated notifications; listeners never fingerprint a whole history per tick.
A failed read remains unknown and waits for refresh/mutation, rather than spinning
on row rebuilds. Filter loads fence superseded requests and account changes;
400 cursor rejection retries from the beginning with the current filters.
Terminal access/auth failures hide cached rows; a failed request after an owner
replacement cannot retain the prior account's results.

## Verification checklist

- [x] Core sparse browse/search pagination, cursor ownership/filter binding,
  visibility, canonical deletion and completed/manual membership regressions.
- [x] Real local Firestore queries, bookmarks, deletion/relink/lock, and production
  FastAPI HTTP/serialization integration with synthetic authentication.
- [x] Widget/API/provider regressions: failure/retry, empty continuation,
  superseded responses, account switch, task changes, large text and semantic badge.
- [x] Native simulator acceptance using the production widgets, APIs and local
  routes below, including Home position restoration.
- [x] Query/contract guards and all 31 selected mobile journeys.
- [x] Final source review, including current canonical authority, cursor progress,
  redaction, async offload, account revocation and released-client compatibility.
- [x] Guarded 401 refresh and replay across account replacement, raw index
  pagination past hidden/stale results, and selected-page-only unlocks.
- [ ] Final repository preflight and required CI for the submitted commit. Keep
  the PR draft until these pass.

Local evidence: Flutter 3.44.5/Dart 3.12.2; iPhone 17 Pro simulator/iOS 26.5;
Python 3.11; isolated `demo-fs-p1` Firestore emulator. The final native flow passed
with real loopback HTTP, including a 503 fault and deletion refresh. 34 focused
mobile regressions and 31 selected journeys passed. The query/contract batch
passed 611 tests; the separate compatibility/rate-limit batch passed 149 with one
pre-existing skip. Three production-query/HTTP emulator cases passed. These
batches overlap; their counts are not a unique-test total. Analyzer reports only
the existing private-return-type info in `main.dart`; new sources have no errors.

The shared HTTP stale-error guards and regressions are reused from #24182
(`e53adc5fd0`, `6fc6816804`), preserving current main's newer streaming behavior.
The owner check extends through token refresh and replay so a delayed 401
cannot expire a replacement session. Successful receipts remain available to
their original callers. This is not verification of Firebase OAuth itself.

## Reproduce local native acceptance

Use a task-owned simulator and the local Firestore emulator. Never point this
fixture at a cloud project. The server rejects non-loopback hosts and any project
other than `demo-fs-p1`, and blocks outbound Python network access. It substitutes
auth/provider/Redis boundaries and seeds only its synthetic QA namespace.

```sh
# Terminal 1: the cached Firebase emulator, or equivalent firebase-tools launcher
java -jar ~/.cache/firebase/emulators/cloud-firestore-emulator-v1.21.0.jar \
  --host=127.0.0.1 --port=8798 --project_id=demo-fs-p1
# Terminal 2, backend/
FIRESTORE_EMULATOR_HOST=127.0.0.1:8798 GCLOUD_PROJECT=demo-fs-p1 \
  .venv/bin/python -m testing.e2e.task_filter_qa_server
# Terminal 3, app/ (generated local test configuration; dev/local_dev pairing)
flutter test integration_test/conversation_tasks_e2e_test.dart \
  -d <owned-simulator-id> --flavor dev --dart-define=OMI_APP_PROFILE=local_dev
```

The native flow uses real loopback HTTP and emulator data. It checks the Home
badge, matches outside Home's loaded rows, starred filtering, 503 retry, deletion
refresh and Back position. Separate widget regressions exercise Android platform
semantics and large text; an iOS simulator run is not physical Android TalkBack
evidence. No customer recordings or production mutations are used.

## Release and closure

Deploy the backend before publishing the mobile build; older clients keep their
unchanged contracts. A new client against an old backend shows retryable filter
failure and no speculative badges. Backend rollback therefore does not mutate or
lose tasks/recordings. Mobile rollback removes the new surface. No backfill or
provider-configuration change is needed. Close the technical issue after the
verified fix reaches main; store release and customer confirmation remain separate
release/Support states, not evidence that code is already shipped.
