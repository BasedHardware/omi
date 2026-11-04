# Episode batch 2: qualification and cost model

Recorded at **2026-11-04 16:14:06 UTC**. Owner: planscost.
Repository: `BasedHardware/omi`, lane `lane/epbatch2`.
Qualification refreshed at **2026-11-04 17:24:03 UTC**.
Qualified source: `7a8c6fda8fe50b66789c7549fcd442f24e0e53e0`.
Typed telemetry API follow-up: `8b9a9487e65409183999220df5b924465e970b1c`,
qualified at **2026-11-04 18:54:04 UTC** with **68 focused tests** and the canonical
full backend typecheck (**zero errors**). It exposes the existing bounded-label
behavior through a typed public entry point; emitted label values are unchanged.
Expanded acceptance source: `1711c10017bd0582450cc1259bf1b201405449f3`,
qualified at **2026-11-04 20:13:43 UTC**: the complete selected command exited green.
Current-main integration: `fc02a9b9b7640126e7ef0625dac9d3c185bf0097`, based on
`26585edc50db6a67f0553d2c7dbae6cbd6584f04`, qualified at **2026-11-04 21:10:04 UTC**.
Two complete green unit commands passed **5,115 cases** across 128 test-bearing
files (131 selected paths, including three support modules); full backend typecheck
has zero errors. The collector conflict retains both privacy and episode families.
Review follow-up: `f0679c22d463b52860f090d8d629fc8c3cc30311`, qualified at
**2026-11-04 21:16:56 UTC** with **203 focused tests**, including five new cases. Shared
fallback telemetry covers enqueue failures at the wake boundary. Cached Home
recovery excludes contained duplicate episodes while retaining fully hidden
rows for stale-note cleanup. The integrated unit counts above precede this
follow-up; these targeted reruns cover its affected boundaries. Current-head
publication and complete CI remain owned by the PR.
Cross-platform CI fixture follow-up: `0d5c3fdca6af93624401f559d784dc30bff5c1bb`,
qualified at **2026-11-04 22:04:16 UTC**. The notification label renders before its async
settings load; waiting for that text could click a disabled switch. Its test now
waits for the loaded master value and explicitly controls a delayed settings load.
Application code is unchanged; no sleeps, timeout increases or skip changes were
added. With Node 22.23.2 and pinned pnpm 10.34.5: **six focused cases passed**,
full Electron unit suite **5,548 passed / 33 existing conditional skips**, complete
node/web typecheck and targeted ESLint/Prettier passed. Commands ran from
`desktop/windows/` through `omi-heavy`: `npx --yes pnpm@10 test --maxWorkers=2`,
`npx --yes pnpm@10 typecheck`, and single-file lint/format checks.
[PR #24607](https://github.com/BasedHardware/omi/pull/24607) owns current head,
review and CI state. This is a dated qualification/forecast record, not a live
cost meter or a deployment receipt. Re-measure before any production ramp.

## Forecast inputs and assumptions

Forecast revised at **2026-11-04 19:31:24 UTC** to respect the 64-fact drain limit.
The earlier 50,000-drain scenario could not sustain its own fact volume; this
revision uses 100,000 drains without changing the runtime or the budget envelope.

The supplied planscost `arch-data.md` snapshot is dated 2026-11-04 and describes
aggregates from 2026-11-03/04, with its fleet write comparison from 2026-11-02.
It reports 71.1 million episode-family reads corresponding to $38 and 37.7
million fleet writes corresponding to $53. The supplied `arch-flow.md` uses a
105 million/$57 read run-rate and an estimated 12 million/$19 write run-rate.
These imply historical effective ratios of approximately **$0.54/million reads**
and **$1.4–1.6/million writes**. They are model inputs, not current list prices or
newly measured production usage. The exact intraday source cutoff was not supplied.

Source fingerprints, for the user-provided architecture snapshots:

- `arch-data.md`: `656e03d028ea3422aaf59fba8dfc8126aab6cdaac8fcea2f95c5e29e97510211`
- `arch-flow.md`: `2d1860409f6cd207baa4063adaaa56002b6c50750b5976eba1947f656fa76909`

The following workload is a **budget scenario**, not an observed daily volume:

| Scenario input | Assumed per day |
| --- | ---: |
| New input/dirty facts, I | 1.0 million |
| Committed legacy decision facts, D | 1.4 million |
| Tracked member edits, E | 1.0 million |
| Successful drain batches, P | 100,000 |
| Changed views and links per drain | 5 each |
| Members per changed view | 5 |
| Checkpoint payload parts per drain | 1 |

The decision scenario uses the supplied study's rough 380,000 full attachments
and one million update CAS operations as a conservative envelope. The remaining
inputs are explicit assumptions. At 4.4 million facts/day, the 64-fact cap
requires at least 68,750 successful drains/day; this scenario averages 44 facts
per drain, so its assumed drain volume can keep up. The model intentionally
charges independent comparison reads instead of assuming they are free or reusing stale policy data.

- Fact and owner writes: `2I + 2D + 4E = 8.8 million/day`. Each policy edit fences
  reads before the existing write and releases with refresh debt afterward: two
  transactions, four writes and three owner reads, in addition to the original
  writer. This is intentional correctness overhead, including shadow users.
- Claim/publication/checkpoint/view/link writes: `14P = 1.4 million/day`, plus an
  assumed 100,000 scan-rotation writes. Total approximately **10.30 million writes**.
- Input dedupe/owner reads, legacy capture reads, policy fences, sequenced fact
  reads, independent legacy comparison rows, two member projection passes and
  bounded control reads:
  `2I + D + 3E + (I + D + 2E) + 65P = 17.30 million reads/day` before account fences.
  The per-drain allowance is 50 member reads (two projection passes), five legacy
  rows and ten bounded control reads; it is a budget assumption, not a measured trace.
  Uncached deletion-authority reads add an estimated `I + 2E + 5P = 3.50 million`;
  total approximately **20.80 million reads/day** in this scenario.
- The supplied worker de-risk allowance is **$0–2/day** for task/wake/compute
  overhead. Neither task volume nor CPU has been measured after deployment.

This gives approximately **$26–30/day of additional shadow operations**. A rough
30% workload sensitivity remains inside the rounded **$15–40/day** budgeting
envelope, before retained storage/index growth, ingestion/logging charges, transaction retries,
backfill, additional checkpoint parts, and any workload outside these assumptions.
This supersedes the earlier draft allowance, which omitted policy-barrier and
independent member-comparison amplification. It is not an all-in daily quote.

Append-only storage is cumulative and unmeasured. The scenario has approximately
`I + D + 2E = 4.4 million facts/day`. At 1 KiB/fact this is about 4.2 GiB/day;
at 10 KiB/fact, about 42 GiB/day, before document/index overhead. Snapshot-heavy
facts may be larger. Measure encrypted bytes/fact and retained/index bytes before
claiming a total daily cost. No retention or deletion mechanism is included.

The drain introduces **no model call or paid-once authority**. Existing composer
and transcription vendor spend continues through the legacy authority. No fresh
vendor invoice/usage data was read for this implementation. Verify vendor usage
and receipt continuity after deployment; do not infer savings from model-call
counters alone. The supplied Home target is $6–10/day read savings after app/cohort
adoption. Broader consolidation/composer architecture savings are not realized
by retaining legacy consolidation during shadow dual-write.

## Local qualification

No production account data was read or written. No GCP tier was used. All emulator
owners and HTTP requests were synthetic. Nothing was merged or deployed by this lane.

- Episode/merge/sync/flag acceptance: **2,905 tests passed** in one complete green
  run, 80 test-bearing files from 83 checked-in selected paths (three support
  modules have no tests). This includes the corrected explicit ownership contract
  for partial legacy stores, all nine payload index exemptions, legacy title/audio/
  summary mutations, tracked-owner coverage, and the projector/worker/API suite.
  Earlier qualification found one inherited evaluator-inventory omission and then
  four CI files absent from the prior selection; those declarations and fixtures
  are corrected and included in this full run. No production behavior was disabled
  to make the legacy fixtures pass. Current-head CI remains owned by the PR.
- Current-main refresh: **2,952 passed** for the checked-in acceptance scope plus
  privacy TTL/cache and flag-budget tests, then **2,163 passed** across 46 disjoint
  incoming-main unit files. Both commands exited green; counts exclude reruns.
  The extra files are the changed `backend/tests/unit/test_*.py` paths in
  `cb8cf29ab9a97a5a9007eea03752c431610a3a15..fc02a9b9b7640126e7ef0625dac9d3c185bf0097`,
  excluding the acceptance selection and the two explicitly added compatibility files.
- Scoped deletion/visibility follow-up: **51 passed** before the full acceptance
  rerun, including accepted/malformed deletion, restored access and publication
  fenced after lease claim.
- Query/index guard: **831 passed**, including 547 query-shape cases, on the review
  changes before the final scoped compose/off-path, visibility and deletion additions.
  Current-head guard evidence belongs to the guarded push and PR checks.
- Real loopback Firestore emulator: **33 passed** across episode log and recorded
  timeline proofs, including aborted atomic capture,
  competing claims, stale publication, bounded contiguous facts and transactional
  whole-document BatchGet through a fixed episode window, and deletion accepted
  after a claim but before publication. Batch-close replay, pending-deadline
  stamping and concurrent recorded placement also pass on the qualified source.
  The final refresh used Firebase CLI 15.30.1 / Firestore emulator 1.22.0; all
  33 tests passed and the emulator shut down. An earlier refresh and a logging-off
  control both hit transaction lock timeouts in the mixed live/recorded race.
  The source had opposing owner/timeline read order; canonical and fallback
  attachment now reuse one owner-first capture, checked by deterministic unit
  tests. Because the disabled control also failed, the passing refresh is not
  proof that log capture alone caused those timeouts or a production retry-rate forecast.
- Current-main emulator diagnostic: initial enabled run **32 passed, one failed**:
  `test_simultaneous_late_devices_converge_on_one_closed_episode` exhausted its
  existing transaction lock retries. A full disabled control passed **33/33**;
  one declared enabled repeat passed **33/33** on identical source. All five new
  episode-log atomic/lease proofs passed in all three runs. Both successful runs
  shut down the emulator. No retry budget or concurrency was changed. The initial
  failure remains an unresolved contention signal: these samples neither establish
  equal on/off failure rates nor prove that log capture cannot amplify contention.
  Inspect legacy transaction retry/exhaustion and serving latency during the train;
  disable capture if it regresses. Do not erase this failure with the passing repeat.
- Earlier guarded publication on `0af0ee8128bee662a17f351e054979419b5fc2f1` passed
  local PR preflight, type checking with zero errors, selected backend tests,
  API/generated contracts, web tests and a Swift debug compile. Current-head
  publication/CI evidence belongs to the PR, not this historical receipt.

The checked-in [acceptance selection](../../testing/episode_log_acceptance.txt)
reproduces the focused backend scope. From `backend/`, through the workspace's
`bin/omi-heavy` runner, use:

```bash
BACKEND_UNIT_TEST_FILE_LIST=testing/episode_log_acceptance.txt \
  BACKEND_UNIT_FILE_BUDGET_SECONDS=1800 BACKEND_PYTEST_WORKERS=1 bash test.sh
```

Use `backend/scripts/run_firestore_index_guard.py` for query/index qualification.
The canonical `backend/scripts/run-emulator-proofs.sh` now includes the episode
log proof, under the existing loopback Firebase emulator. Unit tests and emulator
proofs are separate layers; neither claims installed or deployed behavior.

## Review decisions and limits

All four named prerequisites are merged and integrated: #24577, #24579, #24582
and #24544. Metadata-only batch-close proof hits append member refresh debt,
and cache validity includes the transcription deadline. Expired policy clocks
are skipped/redriven instead of counted as geometry drift.

View-backed live/detail reads use the same canonical member-visibility function
as legacy. New independent fact/policy writers, lease admission/publication and
backfill completion check the existing durable deletion authority on their own
Firestore plane. Publication reads that authority in its transaction, so accepted
deletion fences an already-running worker against recreating erased views. No
deletion routine is added. Atomic legacy capture remains joined to its producer.

Bounded discard-only batch projection explicitly opts out of episode capture;
serving assignment imports the storage seam only when executing its transaction.
Metric outcomes use the existing reviewed closed-vocabulary helper. Legacy
single-document fakes explicitly model absence of a log owner, and enabled
policy/search hook ordering has its own regression.

The reviewed fixes cover repeat-span growth, fixed-boundary clipping and retained
ends, duplicate discard projection, uncertain X→Y→X inputs, link-only mutation
capture, safe policy-release and post-commit dispatch failures, fresh batched drift
comparison, missing row IDs, primed alert series, remote Firestore flag writes,
RFC conditional validators, invalid-Home refresh debt, and independent sweep errors.
The oracle now projects the same candidate fields as production. Index set pins
and full switch-off merge-read assertions remain in place.

Legacy link clears already write `episode_id: None`; the fold/publication carries
that tombstone. No link deletion code is needed or added. The 128-clock capacity
limit remains fail-closed for the entire user's projection, with retry/deadline
telemetry, alerts and legacy read fallback. Truncation could admit stale visibility
policy. Large-user partitioned checkpoints/clocks require a separately qualified
capacity extension. The full before/after fact payload and retained-log footprint
also require measurement before scaling; a clean drift counter is not a cost proof.

## After the authorized train

Verify the release SHA and traffic percentage of every receiving revision and a
new drain metric/log from that artifact. Verify collector delivery, OIDC queue
binding, the existing sweep, indexes, alert installation and meaningful comparison
volume. Planscost owns 5/25/50/100 read cohorts with drift zero for a full day at
each step. Check Home 200/304 behavior, policy refresh/recovery, pending composition,
receipt continuity, vendor usage, per-caller billed operations and retained bytes.
The [runbook](../runbooks/episode-log.md) owns the operational ramp and rollback order.
