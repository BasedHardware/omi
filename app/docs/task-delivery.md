# Conversation tasks on mobile

Tasks and integrations share the existing `ActionItemsProvider` owner. Mobile
conversation extraction keeps the backend's conservative direct-task writer
(#12424). Desktop capture remains suggestion-only (INV-TASK-2); mobile readers
approve its canonical Candidates rather than issuing manual task-create calls.

The production provider factory wires `TaskSuggestionsApi` alongside
`ActionItemsApi`. Tasks shows the server's bounded Suggested projection even
when no task exists. Add Task and Dismiss use generation-fenced accept/reject
receipts. Approval reads the exact returned task ID and upserts it into Tasks
and Home. An acknowledged save whose point read fails stays visibly saved and
retries only that read. A session reset fences all outstanding requests.

A write revision prevents earlier Tasks, pagination and Home reads from
replacing a newly acknowledged task. Resolved Candidate IDs suppress stale
suggestion responses. A receipt that invalidates the initial Tasks snapshot
schedules a replacement read rather than leaving existing tasks unloaded.
A task revealed by its receipt does not advance the
pagination offset until a server page includes it; the same applies to pending
creates and restored point-read tasks. A newer full read owns the current query,
so an earlier refresh or page cannot replace it. Query changes clear page
provenance, and account reset fences loading state as well as returned data.
Existing deletion tombstones remain authoritative;
identical descriptions never imply identical tasks.

Completed may be shown automatically when all loaded tasks are finished. New
incomplete tasks arriving by refresh, pagination or Undo return that automatic
view to open tasks; a manually selected Completed view is respected. Account
reset clears this view state as well as the task/suggestion data.

Desktop summary readers can also recover an older action item explicitly.
The client submits its stored conversation, row index and expected description
to `/v1/candidates/from-conversation`, then separately accepts the prepared
Candidate with the same reference. The server validates the current stored row
and persists its task link. Repeating after reopening uses that durable link;
there is no description-matching or manual-create fallback. This control is
excluded from phone summaries, locked/discarded conversations and app-result
summaries. Phone extraction already has a direct writer and must not acquire a
second unlinked creation path.

Summary retries retain their idempotency key after ambiguous failures. An
expired or rejected proposal returned by preparation is replaced once during
the next explicit gesture; an acceptance conflict uses a canonical Candidate
read to retire the key only when its terminal state can be confirmed.

The summary adapter records each valid row's original storage index before
skipping malformed rows. Cache JSON retains that coordinate and completion /
deletion state in object rows; older string caches still decode. The private
cache coordinate stays out of generated wire models and task-write payloads.
Fresh server rows use their actual array position. The recovery picker uses
these stored coordinates for both preparation and acceptance, including after
a full conversation cache round trip.

Task Integrations keeps its Tasks header entry and gains a named overflow entry,
a Settings → Integrations row, and a localized Settings search destination.

## Backend compatibility and release order

Every authenticated account is eligible for the existing Candidate APIs; workflow
control supplies the generation fence and does not require enrollment or a UID
allowlist. Real production FastAPI routers over a loopback Firestore emulator
verify control, Suggested list, Candidate point read, summary prepare/accept,
canonical task point read, Tasks refresh/pagination and Task Integrations reads.
Concurrency, transaction retries, expiry, generation changes and replay retain
one task and its durable summary link.

The backend also accepts historical text summary rows. Preparation leaves them
unchanged; acceptance converts only the selected row to an object retaining its
description and canonical task link. Candidate create/accept use the shared
bounded contention retry helper, without retrying unknown/ambiguous failures.
No bulk migration or index change is needed. Deploy this PR's backend before
releasing mobile: the text-row and contention fixes are new backend code.

Read-only production logs checked on 2026-10-20 show successful responses from
`/v1/candidates/control` and `/v1/candidates/from-conversation`. The production
OpenAPI document also publishes all nine route boundaries used here. A local
`curl` smoke through uvicorn and the production routers verified legacy-row
prepare/accept, exact task read, refresh, integrations and one-task replay.
That confirms existing route availability and source compatibility, not
deployment of this PR or recovery of either
customer's records. After backend deployment, run an authenticated synthetic
prepare/accept/read/refresh smoke and verify the released app on a physical phone.

## Implementation and verification checklist

- [x] Keep capture origin policy and canonical acceptance authority intact.
- [x] Expose pending desktop suggestions on empty and populated Tasks lists.
- [x] Recover older desktop summary rows through the durable server promoter.
- [x] Retain saved receipts across list/hydration outages; fence stale reads.
- [x] Clear suggestion, receipt and in-flight state on account reset.
- [x] Make Task Integrations discoverable from Settings and localized search.
- [x] Run provider/widget regression tests, mobile journeys and preflight.
- [x] Capture native iOS UI evidence with synthetic transport.
- [x] Verify backend wire/route contracts and real Firestore transactions.
- [x] Handle historical text rows and definite transaction contention safely.
- [x] Run summary recovery and expiry suites in the existing emulator CI lane.
- [ ] Merge, deploy the backend and verify an authenticated synthetic smoke.
- [ ] Release mobile and verify the complete flow on a physical phone.
- [ ] Verify affected customer conversations appear and remain after reopening.

`test/providers/task_delivery_test.dart` exercises production composition,
receipts, retries, stale reads and account reset. It is supplemented by
`test/providers/task_projection_ownership_test.dart` for
overlapping refresh/page requests, query changes and account switching.
The offline native target is
`integration_test/task_delivery_capture.dart`; it uses the real provider factory
and widgets with a synthetic HTTP boundary, never customer credentials or data.
Its cached summary has invalid leading rows, and the transport rejects any
prepare/accept request that does not identify stored row 3. The schema and widget
regressions cover both fresh and cached summaries.
