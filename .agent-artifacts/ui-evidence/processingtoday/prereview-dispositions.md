# PR #25024 pre-review dispositions — 2026-11-10

Reviewed inputs: `prereview-25024-correctness.md` (C), `prereview-25024-tests.md` (T),
`prereview-25024-mergerisk.md` (F), head 7c165d69497500f08999579ef11ef96c10d3576c.
Authority: relay 718fe8 approves prior renders; relay 66d9fd adds episode ownership.
This record covers the batched follow-up; tests/commands and renders are in README.md.

| Finding | Disposition |
| --- | --- |
| C1 / F3 — rollback on failed/404/missing snapshot | Fixed. Constructor, absent wire field and generated schema default false; only successful enabled explicit true enables placement. Every typed or thrown read failure resets placement; 404 clears pending rows, other failures retain them. Account changes reset and generation-fence old responses. Backend explicitly sends its default-on switch. |
| C2 — today row past Home wait | Superseded by David relay 9e09f1 at 11:53Z: the expired today wait is hidden on Home and appears once in Activity with retry. Loaded/pending/episode failures dedupe against the existing ledger; completion overrides stale snapshots. The switch restores #25013's previous Home placement. |
| F1 — #25013 conflict / revert integration | Fixed. Main revert #25037 is d24d101cae0239838413bf537a80d5d68cf52018; merged fresh main 35e63b5d701f94396cd166ef22db8df37aa947d4 in 474edfb1b3efe9e6902e005c0699df9bee8627c1. Preserved every adapted source/test/changelog file from checkpoint 86b59df35fb11e878527d72c1869a9cd88688ce5; no independent post-revert edits existed on those paths. Failed default Home UI is replaced by Activity-only retry on mobile/web/macOS; rollback/direct-detail compatibility remains. Rejected old Home screenshots stay removed. |
| F2 — registry/contract | Fixed. Updated config/feature-flags.yaml, regenerated feature-flag-registry.md, rewrote backend/docs/pending-work.md with switch, candidate sources, cursor rules, placement and limits. |
| T3 — PR timezone coverage | Fixed. Ordinary PR Dart job now runs these unit/widget tests in America/New_York, Pacific/Kiritimati and Pacific/Pago_Pago. Assertions exercise 23/25-hour DST days, UTC instants crossing local dates, and both real pages crossing midnight while open. |
| C3 — capture crosses midnight | Intended recorded-start-day rule, now explicit in contract and PR. At local midnight an unfinished recording from the previous day moves to Activity. |
| C4 / T8 / F8 — civil-clock changes and timers | Fixed. Shared cancellable watcher schedules midnight +1s and checks civil day/offset at most once a minute while foreground; resume re-arms. Widget tests cover both pages, clock jumps, single change notification and cancellation. |
| C5 — episode-only composition debt beyond loaded Home range | Deferred. Requires a bounded episode-debt API rather than widening the Home range or scanning history. Documented owning-contract limitation. Loaded episodes retain their Activity links. |
| C6 — stored-terminal page blocks later live jobs | Fixed. Stored exclusions on processing/merging pages advance the cursor, alongside owner exclusions. A full-terminal-page regression verifies the next live job. Stale completed debt does not trigger history walking. |
| C7 — capped summary_due_at order | Retained bounded default single-field index order (earliest due first), now explicitly documented. Reordering cannot eliminate the cap; all-history pagination is deferred. |
| C8 — legacy empty completed capture without stamps | Deferred historical discovery; query cannot safely identify these without a new indexed discriminator/backfill or history scan. Loaded rows already supplement Activity; contract now states the unstamped history limit. Classification/deadlines unchanged. |
| C9 — queued label | Fixed: queued maps to Transcribing; only summarizing maps to Writing notes. Unit regression included. |
| C10 — cached home_step | Fixed: fetch-specific home_step is no longer persisted in ServerConversation.toJson. episode_id remains serialized; API decode and in-memory copy retain the current projection. |
| C nit — repeated now / selection | Fixed: local day is hoisted for fallback insertion. Selection mode retains exact matches. |
| T1 / T2 / F6 — PCM CPU guard / CI prediction | Left unchanged as instructed. Review reports identical main failure; all assertions pass and only load-sensitive CPU duration trips. Prior owning run: https://github.com/BasedHardware/omi/actions/runs/42782215635/job/129714715607. No threshold, allowlist or pusher changes. New-head CI remains authoritative. |
| T4 — owner pagination default-on untested | Fixed: owned-page test runs with switch on and off and verifies start_after. |
| T5 — impossible stale fixture | Fixed: stale summary candidates carry summary_due_at. |
| T6 — ambient env | Fixed: test_enabled_http_get_shapes explicitly removes HOME_STEP_PROJECTION. |
| T7 / F7 — wire default and hardening | Fixed: manual/generated adapters test absent/false/true; generated wire-hardening check tests absence and both round-trips. Absence now restores old Home. |
| T9 — one-query name | Renamed to same query footprint; comment describes three/on versus one/off. |
| T10 — render wall clock | Fixed: render fixtures use an injected fixed clock (2026-11-10 16:00), and production Home passes that clock to the projection. |
| T11 — capture global state | Fixed: capture helper no longer clears platform override; each test restores it after captures and disposal. |
| F4 — widened pending consumers | Audited; retained existing meaning through note completion. Catch-up and On the Way already include server summarization. Contract and PR explicitly state summary debt may contribute its recording duration even after upload; this is not a bytes-in-transit estimate. No new wire discriminator for released clients. |
| F5 — pending cap + loaded supplement | Covered: Activity receives all loaded conversations independently of pending cap. Regression fills the 100-item server window and verifies a loaded outside-window row hidden on Home appears in Activity. Unloaded all-history discovery remains bounded as documented. |
| Addition — episode_id / row flash | Fixed: ServerConversation parses generated episodeId, carries it through transcript/detail copies, generated conversion and cache. Home reconstructs the episode owner before the episode list arrives and supplements stale member ids; ready and processing owned rows never appear standalone; failed members now appear only in Activity under relay 9e09f1. Tests cover all stages and pre/post episode fetch; new render pair 009/010. |

No cloud/deploy/merge action; no production account data. Physical device behavior and
live account query latency remain unmeasured. Historical episode/unstamped debt discovery
requires a separate API design; it is not represented as fixed here.

## Relay 9e09f1 superseding ruling

David at 11:53Z: no failed rows on mobile Home, including episode members, filtered views and local processing fallback. Activity lists ledger and projected failures with retry, deduplicated. Retry uses the existing fenced endpoint, disables double taps, keeps errors retryable, and updates the shared provider on success. Pending items optionally carry home_step so an expired job does not need its Home day loaded. No new query, stored state or flag. Confirmed switch off/missing/error restores previous Home placement and pending consumers.

Relay 714b03 expands this to mobile Home/Activity, web /conversations All/Activity, and native macOS Conversations/existing Memory hub Activity. Web /home is chat/tasks/goals and remains unchanged. New pairs 011/012 show failed Home before/after, and 013/014 show Activity before/after with retry.

Final reachability checks include search-only failed rows and locked failures. Locked rows keep a generic label and date; private titles are not rendered. Retry still uses server authorization/entitlement checks.

## Relay 714b03: re-land after #25013 revert

Wanted #25013 parts: optional Home projection decode and copying; authoritative list/detail/search reconciliation; terminal failure watcher stop; shared retry-response replacement; web and macOS model/presentation compatibility. Dropped as default UI: failed rows on Home. Confirmed placement routes failures only to Activity with retry on all three clients. The prior presentation remains available for the kill-switch rollback. Web has an Activity tab in its existing conversation gallery; macOS uses its existing Activity destination (INV-NAV-1, no composer or new chat).

Schema inventory: main run [42812549326](https://github.com/BasedHardware/omi/actions/runs/42812549326) failed `test_inventory_openapi_route_response_decode_migration_complete` because the search route moved its generated decode behind a Dart part helper. The route now directly decodes GeneratedSearchConversationsResponse and passes it into the helper that carries home_step. All 14 inventory tests pass. No assertion, schema allowlist or CPU threshold was weakened.

Renders 015/016 exercise actual web tabs/gallery/tiles and admission, with external requests blocked; 017/018 render the actual native SwiftUI components used by their destinations. They are component evidence rather than a signed full-app session. Fixture retry proves the web failure leaves Activity after success. Native retry and read-failure tests exercise injected dependencies with no network. The main revert and final merge/re-land order are recorded above and in the PR body.

Web completion hardening: authoritative retry results replace list/search state and the list cache before refresh; older in-flight reads are fenced. Failed refresh/cache remount and older list/search response regressions pass. Native Activity observes AppState changes and the spine ingests the emitted placement value, preserving exclusive placement as the switch changes.

## Luna FIX-FIRST on published head 591c10fc

Fixed the native retry replacement retaining a stale `home_step: failed` when the
reprocess response is active and omits that list-only field. Authoritative
`ConversationRepository.replace` now replaces the projection at both replacement
layers. Ordinary detail/cache reads still retain known failures; explicit incoming
failure projections remain authoritative. The native regression covers failed
stored and projected rows restarting as in-progress, processing or merging, plus
completion, immediate Activity removal, Home admission and processing display.

Mobile Activity already uses `applyConversationReprocessResult`, which clears the
remembered failure id before placing the response in processing; detail retry uses
`preserveHomeStep: false`. Web list/search retry already replaces whole objects
and the list cache, fencing older reads. Added regressions for projection-omitting
processing responses on mobile and both web paths, including Activity removal and
web failed-refresh/cache-remount survival. No mobile/web production change was
needed. No layout, copy or render fixture changed; the approved PNGs are unchanged.
Fresh main was fetched; its newer backend-only work does not overlap this native
replacement fix, so no additional merge was needed.

Follow-up verification: 104 native tests passed (105 executed, one opt-in PNG
skip); web typecheck, six smoke tests and 1,041 Vitest tests passed; all 148
focused Flutter tests passed. Full preflight and normal push result are recorded
in the PR body. The PCM CPU guard remains unchanged.

## Scope addition: notes failed with outputs kept — 94a9ed / 4ddd04

| Finding / requirement | Disposition |
| --- | --- |
| #25034 overlap and conflicting main | Merged main 7ebd8450b6 (including #25034) as 0bb9d47e424477fcd185e5d3dd83738dfc49c868. home_step.py and the generated registry doc auto-merged. Resolved the config conflict by retaining #25024's cross-client HOME_STEP_PROJECTION entry and #25034's HOME_EMPTY_OUTPUT_NOISE entry once each; regenerated the doc. Main's overview OR section-body, banked-output/debt, curated-row and failure guards remain intact. Further fresh-main integration is recorded in the PR body. |
| L4b eligibility pitfalls | Clients consume the new ledger kind; no title/overview-only inference, no treating every noise row as attention, no client-side banked receipt/debt predicate, and no new candidate query/history scan. Backend eligibility and notes-only execution remain pipeline-driver's separate responsibility. |
| 010/011/012 hidden notes failures | Added Needs attention rows with Re-run notes on mobile, web Activity and native macOS Activity, using the item retry endpoint. Saved task/event models and destinations are unchanged. Web/native also honor explicit noise on Home without adding it to failed Activity. |
| One row per conversation | Ledger rows prefer the notes-only kind over legacy duplicates, suppress projected failed-row duplicates, and remember accepted retries against stale ledger/list snapshots. A new notes ledger generation or confirmed failed operation can surface again. |
| Unknown kind merge safety | Unknown kind strings decode and display without retry, regardless of retryable=true. Mobile bulk retry dispatches known-item calls when any non-legacy kind is present, preventing an implicit unknown-kind retry. |
| Retry success and error | Accepted in-progress/succeeded notes retries remove the row. 409, transport and failed-operation results keep an actionable error. Busy state fences double taps; mobile/web keep ambiguous idempotency keys; account changes and older reads are fenced. Ordinary failed-row retry keeps its existing path. |
| Kill switch and API order | Existing successful explicit pending-work confirmation gates the new notes placement; off/missing/error restores previous placement. No new flag. The optional/minimal ledger contract decodes without a new backend enum; the separate server kind must be published for discovery. |
| Evidence | Added 019–027 to evidence.json: three cases each on mobile/web/macOS. Mobile uses the real ActivityPage and unchanged task/event arrays; browser uses production sections/hooks with all external requests blocked; native uses actual SwiftUI ledger components. These are fixtures, not paid notes runs or signed full-app sessions. |

Tests and final repository gates are recorded in README.md and the PR body. The
pre-existing PCM CPU guard, thresholds, allowlists and pusher code were not edited
for this addition; upstream-only changes stay part of the main merge.

Fresh-main completion: after the addition commit 44d470e980f19fee32992a9a31e3539b2454cf14,
merged main 8a9f00b975f3828134bb63a3952e4afb9affb0cd as
c6013b4b597faed1dc7e1500aaed5cbe8cb5719f, normally and without conflicts.
The separate #25034 registry conflict had already been resolved in 0bb9d47e42.
Addition-only non-test delta: +954/-81 (1,035 changed lines), excluding upstream
merges, tests/e2e and UI evidence/render harness; includes source, config, docs
and localization/generated files (+205 localization lines). The immutable
measurement and reproduction method are in notes-addition-line-delta.json.


## Luna FIX-FIRST at 3840beec — macOS ledger idempotency

**Fixed.** macOS now generates an in-memory UUID per attention item on its first
retry, sends it as `Idempotency-Key` through the authenticated POST helper and
reuses it after transport errors. A confirmed in-progress/succeeded/failed
operation or `409 {"state":"not_retryable"}` clears the key; account reset also
clears it. Failed requests keep the error row. The HTTP parser recognizes the
contract's state-only 409 body. Unknown kinds remain display-only.

Four new native tests exercise the actual request endpoint/header, transport-error
replay, key renewal after confirmation, and account reset. The selected native
run passed 185 tests, with two opt-in PNG tests skipped (187 executed). Mobile's
22 focused notes/pending-store tests and web's nine API/hook tests pass, including
notes-only header assertions. Both clients already send a key for
`conversation_notes_failed_with_outputs`; neither needed a production change.
Desktop test-quality checks pass. Full preflight and the one normal full-hook
push are reported in the PR body. UI code, fixtures and approved PNGs are unchanged.
Fresh fetch confirmed GitHub reports MERGEABLE, so this follow-up does not merge
main, as requested. No force push, hook bypass or PR merge is authorized.


## Luna FIX-FIRST at 6206927c — web off-page retry reconciliation

**Fixed.** Conversation retries now acknowledge the account-scoped remembered-failure
cache directly when the authoritative response is non-failed, including processing
without `home_step`, or an explicit `409 {"state":"not_retryable"}`. This works when
the conversation came from an earlier search and is absent from both current lists.
Old loaded object snapshots cannot immediately restore the cleared tile; a fresh
failure can be discovered again. Failed results, generic conflicts and transport
errors keep the failed tile and error. Kill-switch rollback keeps the old Home path.

The notes-only ledger calls the same reconciliation on accepted in-progress/succeeded
retries and explicit terminal conflicts. A terminal conflict clears its old projected
duplicate while the ledger item retains its error, as required by the attention
contract. Ambiguous errors keep their retry key; terminal acknowledgments clear it.
The HTTP error type preserves only the structured state needed to distinguish the
explicit terminal conflict from other 409 responses.

Mobile and macOS do not have the same successful-retry bug: mobile applies the result
to shared provider state even without a current list match; macOS Activity explicitly
remembers the authoritative replacement outside the repository's loaded query. Their
notes stores suppress accepted retries by conversation ID independent of loaded pages.
Added off-page regressions on both; no mobile/native production change was needed.
Existing notes acceptance, failure, deduplication and idempotency tests remain passing.

Validation: web type checking, six Bun smoke tests and 1,071 Vitest tests; 69 focused
Flutter tests; 70 native tests passed (72 executed, two opt-in PNG tests skipped).
New web coverage includes off-page processing/completed responses, explicit terminal
409, generic conflicts, failed/transport retries, notes-only acknowledgments and HTTP
state decoding. Full preflight and the single full-hook push are recorded in the PR
body. No layout, fixture or PNG changed; existing commit-pinned renders remain valid.
GitHub reported MERGEABLE after the fresh fetch, so main was not merged for this fix.
The PR remains unmerged and on hold for David's render verdict.
