# PR #25024 pre-review dispositions — 2026-11-10

Reviewed inputs: `prereview-25024-correctness.md` (C), `prereview-25024-tests.md` (T),
`prereview-25024-mergerisk.md` (F), head 7c165d69497500f08999579ef11ef96c10d3576c.
Authority: relay 718fe8 approves prior renders; relay 66d9fd adds episode ownership.
This record covers the batched follow-up; tests/commands and renders are in README.md.

| Finding | Disposition |
| --- | --- |
| C1 / F3 — rollback on failed/404/missing snapshot | Fixed. Constructor, absent wire field and generated schema default false; only successful enabled explicit true enables placement. Every typed or thrown read failure resets placement; 404 clears pending rows, other failures retain them. Account changes reset and generation-fence old responses. Backend explicitly sends its default-on switch. |
| C2 — today row past Home wait | Fixed through #25013 integration: explicit projected failed rows remain one terminal, openable Home row. Activity does not synthesize a duplicate from stale pending data. A same-day 01:00→08:00 regression covers this plus older writing_notes removal. |
| F1 — #25013 conflict | Merged fresh origin/main (8141729fccd928b90d16b34c13bcc162fef01fa5), then open #25013 head a52e6a2b691dace3acf76c9e98d33f9f1e313916. Retained its failure predicate and applied today filtering after folding. #25013 should land first; this PR includes its head as an integration parent. No PR was merged. |
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
| Addition — episode_id / row flash | Fixed: ServerConversation parses generated episodeId, carries it through transcript/detail copies, generated conversion and cache. Home reconstructs the episode owner before the episode list arrives and supplements stale member ids; ready, processing and failed owned rows never appear standalone. Tests cover all stages and pre/post episode fetch; new render pair 009/010. |

No cloud/deploy/merge action; no production account data. Physical device behavior and
live account query latency remain unmeasured. Historical episode/unstamped debt discovery
requires a separate API design; it is not represented as fixed here.
