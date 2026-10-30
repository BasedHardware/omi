# On-demand transcript translation

Translation remains display-only. The original `transcript_segments[].text` is the
input to summaries, memory, and vector processing. Live on-demand translation
uses transcript-view demand and accepts lease-v1 reports. The viewed policy is
always `viewed_v1`, and every eligible user can use the feature. The bounded
per-UID and global daily character budgets still limit provider spend.
`TRANSLATION_DEMAND_GATE_ENABLED=false` is the live-translation stop lever and
restores legacy always-translate behavior. `TRANSLATION_ONOPEN_ENABLED=false`
stops explicit detail-read translation and returns untranslated text with
status `unavailable`.

## Live listen admission

The authenticated `/v4/listen` socket accepts the existing `client_state` fields
`foreground` and `transcript_visible` as booleans. Visibility requires foreground.
The optional `translation_demand_version: 1` opts into a renewable lease. The
server accepts lease-v1 reports. A lease-v1 client sends a full snapshot on
connect, on every visibility change, and every 20 seconds while connected,
including when hidden. Receipt time starts a 60-second lease.

With `TRANSLATION_DEMAND_GATE_ENABLED=true`, a fresh unversioned visible report
selects the viewed policy and a fresh hidden report suppresses new work. After
60 seconds without an unversioned report, the socket returns to legacy
translation. Lease-v1 expiry suppresses new work until renewal. Missing,
malformed, or unsupported state remains legacy. Each recording socket has its
own demand; a report never controls another socket or a historical detail read.
The phone-call interpreter retains legacy admission. Closing the socket cancels
queued work. Already dispatched work may finish but must pass the source fence
before persistence. Repeated renewals do not start another catch-up page.

Viewed demand always uses the Luna-backed `viewed_v1` whole-segment policy
through the configured translation route. Viewed cache entries have a separate
policy, source-hint, target, and mode identity in memory and Redis; legacy cache
keys stay intact. Demand metrics are recorded only while the live demand gate is
enabled and are labeled `enforced`.

## Explicit detail read

`GET /v1/conversations/{id}?include_translations=true` is opt-in and separately
controlled by `TRANSLATION_ONOPEN_ENABLED`. The ordinary GET, list, sync, share,
and summary paths do not request translation. The authorized canonical detail
and its first-open processing are resolved before bounded translation. The
server's user language preference selects the target; the client cannot set it.

One request attempts at most 50 segments and 12,000 source characters within
the configured 3-second provider deadline. Oversized single segments are
deferred without truncation. The response body remains `Conversation`.
`X-Translation-Status` is `complete`, `partial`, `deferred`, or `unavailable`.
`X-Translation-Cursor`, when present, can be passed as `translation_cursor` on
a later visible open. It is signed for the UID and binds the canonical ID,
target, source revision, and policy. A changed revision restarts selection.
Provider failure leaves raw text and current display translations readable.

## Limits, persistence, and rollout

Every eligible user is admitted; there is no cohort percentage or UID
allowlist. The live demand gate and on-open switch control their separate spend
paths. Redis reservations fail closed for new on-demand provider spend; legacy
traffic keeps its existing behavior. A per-UID in-flight lock and content lease
cover both live and detail work. Translation-only Firestore transactions compare
the exact source, merge one target language, and store encrypted private
provenance. They leave raw text, speaker/timing fields, client projections, and
processing jobs untouched. A legacy result cannot replace a valid viewed result.

The two stop switches default on. Disable `TRANSLATION_DEMAND_GATE_ENABLED` to
restore legacy live behavior, or disable `TRANSLATION_ONOPEN_ENABLED` to stop
opt-in detail generation. Env changes on a fleet require rolling propagation.
Stored translations remain readable.

Current Flutter and macOS clients send visibility changes but do not renew a
lease or request `include_translations`. Sustained lease behavior and the
first-open transcript UI need a separate client release. This backend contract
does not establish shipped UI acceptance or GPU cost savings.
