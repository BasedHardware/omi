# On-demand transcript translation

Translation remains display-only. The original `transcript_segments[].text` is the
input to summaries, memory, and vector processing. Live on-demand translation
uses transcript-view demand and accepts lease-v1 reports. The viewed policy is
always `viewed_v1`, and every eligible user can use the feature. The bounded
per-UID and global daily character budgets still limit provider spend.
`TRANSLATION_DEMAND_GATE_ENABLED=false` is the live-translation stop lever and
restores legacy always-translate behavior. `TRANSLATION_ONOPEN_ENABLED=false`
stops detail generation and leaves stored translations and coverage readable.

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

`GET /v1/conversations/{id}?include_translations=true` reports translation
coverage for the server-side language preference on the authorized canonical
detail. Without the exact `X-Omi-Recording-Detail: 1` signal, it returns the
stored transcript and display translations, and scans their coverage without
translation reservations, provider calls, or writes. Stored coverage is
available with spend disabled or the generation switch off. The ordinary GET
still returns the existing detail shape without translation status headers.

Generation requires both the opt-in and exact GUI signal on every request,
including continuations. One request attempts at most 50 segments and 12,000
source characters within the configured 3-second provider deadline. Oversized
single segments are deferred without truncation. Provider failure leaves raw
text and current display translations readable.

The response body remains `Conversation`. `X-Translation-Status` is
`complete`, `partial`, `deferred`, or `unavailable`. Stored coverage returns
`partial` with `X-Translation-Cursor` while more segments remain to scan,
then `complete` if covered or `deferred` if eligible translations are missing.
Pass the cursor in `translation_cursor`. It is signed for the UID and binds
the canonical ID, target, revisions, policy, and coverage or generation mode.
Stale, legacy, or other-mode cursors restart selection. An invalid signature
returns HTTP 400. A cursor carries pagination state only.

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


## SCA-3677 release checklist

- Run through Release: Omi prod with joined merge disabled. Record the deployed
  commit, UTC observation window, query time, and monitoring scrape coverage.
- With translation spend configured, exercise authorized detail fixtures with
  stored translations, missing coverage, and a continuation. Use both an absent
  signal and a non-exact signal, including a replay of a GUI-issued cursor.
  Confirm stored data and coverage pagination. Use a fresh GUI opt-in miss to
  confirm generation and persistence. Verify stored coverage with
  `TRANSLATION_ONOPEN_ENABLED=false`.
- Query `sum by (event, gui_signal) (increase(omi_detail_translation_total[24h]))`.
  Require positive `detail_returned` volume and zero `reservation_attempted`,
  `provider_called`, and `materialization_committed` with `gui_signal="absent"`.
  Verify all three paid events advance for the GUI positive control over its
  observation window. `provider_called` counts calls into the Luna client after
  cache selection, including failures. Use billing data for cost attribution.
- On eligible deferred transcript fixtures, confirm headerless reads return
  stored transcripts and that a GUI open starts FIRST_OPEN. Query
  `sum by (event, gui_signal) (increase(omi_first_open_transcript_total[24h]))`.
  Require positive `detail_returned` and zero `enrich_started` with
  `gui_signal="absent"`, plus a present-signal start for the GUI control.
- Book **$0/day demonstrated savings** until production attribution supports a
  savings figure.
