# Conversation task membership (#20620)

## Behavior and authority

Home rows use a compact accessible badge. Search → Has tasks opens a separate
server-backed browse page; Back restores the existing Home/search state. Query,
date, folder and starred controls intersect before result pagination.

“Has tasks” means at least one **current, undeleted canonical action item** whose
`conversation_id` is this conversation. Completed and manually linked items count.
Unaccepted/rejected Candidates and stale summary suggestions do not. Relinking or
merging follows the canonical link; no historical count, task creation, task text,
new projection or migration is introduced. Locked/deleted/missing/foreign parents
do not expose badges or filtered results. Task-source backlinks remain #19859.

`conversation_task_links` owns the bounded metadata join for both surfaces.
Browse discovery uses the existing chronological index and visibility/codec;
textual discovery reuses the current conversation search owner. Filter cursors
are signed, expire after one hour, and bind the owner and all filter inputs.
Sparse scans may return an empty intermediate page **with continuation**, which
the UI never labels “No results”. A budget failure without progress is retryable.
The presence read uses existing task version invalidation and a 15-second cache.
No new composite-index deployment is required; runtime query guards verify this.

The mobile presence reader batches mounted row IDs (max 100 retained), invalidates
on existing task/conversation notifications, and fences account/revision changes.
A failed read remains unknown and waits for refresh/mutation, rather than spinning
on row rebuilds. Filter loads fence superseded requests and account changes;
400 cursor rejection retries from the beginning with the current filters.

## Verification checklist

- [x] Core sparse browse/search pagination, cursor ownership/filter binding,
  visibility, canonical deletion and completed/manual membership regressions.
- [x] Real local Firestore queries, bookmarks, deletion/relink/lock, and production
  FastAPI HTTP/serialization integration with synthetic authentication.
- [x] Widget/API/provider regressions: failure/retry, empty continuation,
  superseded responses, account switch, task changes, large text and semantic badge.
- [ ] Native simulator acceptance using the production widgets, APIs and local
  routes below, including Home position restoration.
- [ ] Query/contract guards, affected mobile journeys, final diff review and
  required CI for the submitted commit. Keep the PR draft until these pass.

The shared HTTP stale-error guards and regressions are reused from #24182
(`e53adc5fd0`, `6fc6816804`), preserving current main's newer streaming behavior.
They prevent old requests from refreshing/expiring a replacement account while
preserving successful receipts. This is not verification of Firebase OAuth itself.

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
