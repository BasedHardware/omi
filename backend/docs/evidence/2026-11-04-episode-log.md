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
Fractional wake-deadline follow-up: `eb3fd560811d4e23639072e576e87e3ab25cf1ae`, qualified at
**2026-11-04 22:19:44 UTC** with **208 focused backend cases**. Integer truncation could
schedule a deadline at `00:03:00.500` into the `00:03:00` bucket, causing an early
`not_due` exit and sweep-only recovery. The new boundary proof failed for 1 us
and 500 ms offsets before the fix. Ceiling the deadline before bucket rounding
passes all five boundary/dedupe cases without changing the debounce, age cap,
retry budget or concurrency. The final focused scope also rechecks fallback
telemetry, cached compose containment, Home policy, composer and label contracts.
[PR #24607](https://github.com/BasedHardware/omi/pull/24607) owns current head,
review and CI state. This is a dated qualification/forecast record, not a live
cost meter or a deployment receipt. Re-measure before any production ramp.

## Round-3 review qualification and cost floor/ceiling

Recorded **2026-11-05 01:06:23 UTC**, on the round-3 working tree based on
`8c8f313abdd37c120caf5196f394cb29807d9600`; [PR #24607](https://github.com/BasedHardware/omi/pull/24607)
owns the final pushed SHA and CI. This section supersedes the round-2 default-on,
synchronous append and operator-only capture-drop recovery descriptions below.

Recorded candidate reads now include all fixed-row member geometry. Capture and
policy-refresh work use the shared lazy four-worker/64-queued bounded executor;
request handlers never wait for append or refresh. The pre-write policy fence
remains synchronous. Drops/overflow/cancellation persist `capture_dirty`, clear
read readiness and advance the epoch. A failed policy entry also retains a
metadata barrier until the writer finishes or deadline recovery occurs, so a
repair cannot run ahead of the original writer. A full bounded authoritative
reconciliation is the only publication that clears a capture gap; it replaces
stale views/links and leaves legacy records untouched. Capacity failure remains
on legacy. Facts/checkpoints stay content-free; current speech is hydrated only
into sealed views. Capture defaults false and requires verified ACTIVE TTL at
flag-on and runtime (60-second cache); the periodic guard logs and measures facts
without active TTL even when capture is off. Remote kill is normally about 60s,
can take longer after refresh failures, and does not cancel a committing publish.
The drain rechecks its cached admission immediately before publish.

Validation uses synthetic owners only and no GCP tier. Commands run through
`/Users/dazheng/workspace/omi/bin/omi-heavy`; cloud credential variables are
removed for the emulator, preflight and guarded push. No merge, deployment,
production account access or writes, or TTL apply is performed.

- The checked-in acceptance selection completed **2,950 passing cases** using
  `BACKEND_UNIT_TEST_FILE_LIST=testing/episode_log_acceptance.txt
  BACKEND_UNIT_FILE_BUDGET_SECONDS=1800 BACKEND_PYTEST_WORKERS=1 bash test.sh`
  from `backend/`. Subsequent narrow policy-entry fencing and pure-geometry
  reconciliation fixes are rechecked in the final focused suite/emulator.
- **156 final focused cases passed** across `test_episode_log_round3.py`, `round2`, worker,
  review, API, projector, telemetry and `test_omi_flags.py`. It proves Home at
  100% chooses legacy after capture/entry/refresh/overflow failure and chooses the
  log after full repair, preserves neighboring fixed members, blocks premature
  repair of an active original writer, fences old repair epochs, refuses facts
  before ACTIVE TTL, enforces the flag-on precondition, checks cached TTL/error
  behavior, emits the missing-retention signal, returns while append/refresh IO
  is blocked, and uses a real saturated executor to exercise overflow fencing.
- The loopback Firestore emulator independently passed **14/14 log proofs**,
  including real candidate projections, full collection/receipt reconciliation,
  stale-view/link deletion and content-free checkpoints. Command:
  `firebase emulators:exec --only firestore --project demo-omi-isolated-tests
  'backend/.venv/bin/python -m pytest -q backend/tests/integration/test_episode_log_emulator.py'`
  with synthetic offline encryption and `EPISODES_ENABLED=on EPISODES_PERCENT=100`.
  The earlier combined log+timeline command was **41/42**: all 14 log proofs
  passed, while legacy `test_simultaneous_late_devices_converge_on_one_closed_episode`
  exhausted existing lock retries. This repeats the documented legacy contention
  signal; no retry budgets, concurrency levels or skips were changed. Both owned
  emulator processes shut down through Firebase after their commands completed.
- Canonical `PYTHON=.venv/bin/python bash scripts/typecheck.sh` has **zero errors**.
  The query guard registers real bounded reconciliation/retention query drivers;
  its focused discovery/runtime selection passed **13 cases**. New queries are
  unfiltered scans and need no new composite index. Full preflight and normal
  guarded-push receipts are owned by the final PR qualification.

### CI test-isolation follow-up

The first guarded push at `fc3f0a42059d53952dd46f7d4889603ffeac9554`
passed the canonical emulator, but full CI found a test-harness regression:
the new autouse scheduling fixture imported `utils.episodes` into legacy unit
suites that intentionally replace `utils` with a narrow stub. The fixture now
requires explicit opt-in through episode-log module marks or the existing
`untracked_episode_log` fixture. Production code is unchanged by this follow-up.
The exact **17 CI-reported files passed all 127 cases** through isolated
`backend/test.sh` processes after the fix. The expanded log-focused selection
(including backfill CLI tests) passed **158 cases**. The complete acceptance
selection was then rerun with the scoped fixture and passed **2,951 cases**,
including the extra active-writer fencing regression. Final current-head CI remains
owned by the PR; the initial failed run is retained as evidence rather than hidden.

### Explicit operations floor and historical ceiling

Pricing checked live at **2026-11-05 01:06:23 UTC** on Google's
[Firestore Standard pricing page](https://cloud.google.com/firestore/pricing).
The displayed **us-central1 default USD** rates are **$0.03 per 100K reads,
$0.09 per 100K writes and $0.01 per 100K TTL deletes**. The actual customer
database location/effective rates were not queried. Keep the existing scenario
explicit: **26.60M reads, 11.30M writes, 4.90M TTL deletes/day**, not measured fleet
volumes. Moving the work to the bounded executor does not change its regular
Firestore document operation counts.

| Scenario cost per day | Current list-rate floor | Historical effective-rate ceiling |
| --- | ---: | ---: |
| Reads | $7.98 | $14.364 (at $0.54/M) |
| Writes | $10.17 | $18.08 (at $1.60/M; $15.82 at $1.40/M) |
| TTL deletes | $0.49 | $0.49 reference allowance |
| **Operations** | **$18.64** | **$32.934 maximum ($30.674 lower historical case)** |
| Same small-payload storage scenario | about $0.02 | about $0.02 |
| Supplied task/compute allowance | $0–2 | $0–2 |
| **Comparable modeled total** | **$18.66–20.66** | **$30.69–34.95** |

Thus Luna's **$18.64/day operations floor** and the conservative **$31–35/day
historical total** describe different rate assumptions applied to the same
scenario. Neither is a fresh production bill. The historical ratios remain
traceable to the supplied dated study below. Drop invalidations add two reads
(deletion authority/owner) and one owner write per event; full repairs add bounded
legacy/projection/member reads and replacement writes. Their frequency, retry
amplification, TTL lag, actual view/checkpoint/index bytes, network/ingestion and
vendor usage remain unmeasured and are additional. ACTIVE periodic guard checks
use the admin policy surface rather than a document scan; a missing policy adds
at most one bounded fact-existence query per process per minute.

Rollout order in the runbook and PR is **TTL apply (ops) -> capture on -> drift
soak -> read ramp**. TTL is only declared, never applied by this round.

## Round-2 review qualification

Recorded **2026-11-04 23:42:30 UTC**, on the round-2 working tree based on
`4972db0013241bbc6bf7680f99d1d7efae8fbd20`. The PR owns the final pushed SHA.
This section supersedes historical claims below about atomic serving capture,
retention absence and the previous cost allowance; those earlier receipts remain
historical evidence rather than current architecture.

- **2,934 unit cases passed** in the complete checked-in acceptance selection,
  through `omi-heavy`, `BACKEND_UNIT_TEST_FILE_LIST=testing/episode_log_acceptance.txt
  BACKEND_UNIT_FILE_BUDGET_SECONDS=1800 BACKEND_PYTEST_WORKERS=1 bash test.sh` from
  `backend/`. The initial run found four expectations requiring the removed
  in-transaction owner read in `test_conversation_smart_merge_audit.py`; those
  now assert the legacy-only serving read set. The complete rerun exited zero.
- **166 focused cases passed**, including actual geometry payloads above the
  64 KiB encrypted fact limit, append/encryption/telemetry failures, unchanged
  committed composer responses, exactly-once original policy writers, hard-delete
  and tombstone privacy, TTL expiry, idle scan removal, zero-percent Home and
  remote capture admission. A final telemetry/allowlist follow-up rechecks the
  log-specific selection separately (**112 passed**). The current ten-test log
  emulator suite also exited green on its own, including actual oversized
  structural payloads with the real serving write committed before rejection.
  A final reference-hydration regression passed **113 log-focused cases**: a
  title-only composer write refreshes the view without putting speech into the
  checkpoint; lease-only churn emits no fact. This follow-up is separate from
  the earlier complete acceptance run.
- Canonical `bash backend/scripts/typecheck.sh`, through `omi-heavy`: **zero
  errors** (existing warning inventory remains). No typecheck bypass was used.
- Two full loopback emulator commands each passed **37/38**: first
  `test_concurrent_live_and_recorded_attachments_preserve_timeline`, then
  `test_simultaneous_late_devices_converge_on_one_closed_episode` exhausted the
  existing serving transaction lock retries. Each run passed all ten log-specific
  proofs. A separately declared disabled control passed **28/28** legacy timeline
  cases. These samples do not establish equal enabled/disabled failure rates or
  rule out timing amplification. The shared legacy contention signal remains
  unresolved; no retry budget, concurrency or skip was changed. Both emulator
  processes exited and shut down. Full commands used Firebase CLI 15.30.1 and
  emulator 1.22.0 via `firebase emulators:exec --only firestore --project
  demo-omi-isolated-tests`, then Python pytest over
  `backend/tests/integration/test_episode_log_emulator.py` and
  `backend/tests/integration/test_recorded_episode_timeline_emulator.py`, with
  `EPISODES_ENABLED=on EPISODES_PERCENT=100`, loopback credentials only.
- TTL operator plan was rendered for the reviewed episode-log policy; it names
  only `episode_facts.expires_at` and `ttl_config`. **No --apply, live TTL,
  production data access or GCP tier was used.** Production retention requires
  the separately authorized train owner to activate and verify the policy.

## Forecast inputs and assumptions

Forecast revised at **2026-11-04 23:37:00 UTC** for round-2 post-commit
capture, content-free geometry deltas and one-day retention. This replaces the
unbounded snapshot-storage estimate and includes separate capture transactions,
authoritative speech hydration and a distinct sync-refresh allowance. The
workload is still a scenario, not a current production measurement.

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
| Decorated tracked member edits, E | 1.0 million |
| Sync/smart-merge post-commit refreshes for existing log owners, S | 0.5 million |
| Successful drain batches, P | 100,000 |
| Changed views and links per drain | 5 each |
| Members per changed view | 5 |
| Checkpoint payload parts per drain | 1 |

`S` is an explicit new allowance, not an observed volume. The decision envelope
still approximates the supplied study's attachments/update CAS operations.
All other inputs are assumptions. `N = I + D + 2E + S = 4.9M facts/day` needs at
least 76,563 drains at the 64-fact cap; 100,000 drains averages 49 facts/batch.

- Fact and owner writes: `2N = 9.8M/day`. Independent claim/publication/view/link/
  checkpoint writes: `14P = 1.4M/day`. Keep a conservative 100,000 scan-rotation
  write allowance, though idle owners now leave the sweep. **11.30M writes/day**.
- Each independent append reads deletion authority, owner and dedupe key:
  `3I + 3D`. Each decorated edit checks the owner once and enters/releases two
  separate barriers (two owner + two deletion reads): `5E`. Each tracked sync
  refresh checks owner existence after commit then appends: `4S`.
  Fact reads cost `N`. Independent Home projection/comparison/control reads remain
  budgeted at `70P`, and reference-based speech hydration adds `5P`.
  Total: `3I + 3D + 5E + 4S + N + 75P = 26.60M reads/day`.
- At the supplied historical effective read/write ratios this is **$30.18–32.44/day**
  in read/write operations. Keep the supplied **$0–2/day** task/compute allowance.
  Separate post-commit transactions increase reads; smaller facts reduce bytes,
  not Firestore write counts. No serving owner lock is retained during append.
- TTL eventually deletes `N = 4.9M facts/day`. As an explicitly identified regional
  reference, the Google **us-central1 default USD** table checked at this forecast
  lists TTL deletes at $0.01/100,000 and stored data at $0.000205479/GiB-hour
  (about $0.15/GiB per 30 days). This adds **$0.49/day** TTL deletes. The actual
  customer database location/effective delete/storage rates were not read; these
  are scenario rates, not an account quote. [Official Firestore pricing](https://cloud.google.com/firestore/pricing).

The revised central allowance is **$31–35/day including modeled TTL deletion and
small-payload storage**, with a rounded **$20–50/day** workload sensitivity envelope.
For direct comparison, excluding the new `S` allowance, the original workload now
costs approximately **$28–32/day** with TTL deletes. Each additional million
tracked sync refreshes adds five million reads, two million writes and one million
TTL deletes: about **$5.6–6.0/day**, before bytes/retries/tasks.

Synthetic ciphertext sizes were measured locally at **2026-11-04 23:35:16 UTC**
using production `compact_events`, `dumps` and `encrypt` (synthetic UID/key only):

| Synthetic fact shape | Prior ciphertext | New ciphertext |
| --- | ---: | ---: |
| member with a repeated synthetic structured title | 14,556 B | 104 B |
| five-member compose mutation with title/bullets/lede in before and after | 90,064 B | 2,000 B |
| policy/member refresh reference | 104 B | 104 B |

The fixture used five `c0..c4` members, five-minute geometry, and the literal
`'synthetic content ' * 600` per speech field. These are repeatable fixture
measurements, **not fleet averages**. A weighted scenario with I/S/2E refreshes
at 104 B and D deltas at 2,000 B gives **2.95 GiB/day** encrypted payload plus
**1.17 GiB/day** at a separate assumed 256 B/document overhead: about **4.12 GiB**
retained at one day, before indexes and expiry lag. At the cited regional rate
that modeled document footprint is approximately **$0.02/day** in storage.
At the hard 64 KiB encrypted-payload cap, the same workload instead implies
**299.1 GiB** of one-day payload (about **$1.50/day** at that reference rate),
not an expected mean. TTL lag scales both footprints; two days of lagged retention
doubles these estimates. Storage is no longer cumulative by design, but physical
bounds depend on an ACTIVE TTL policy and measured deletion lag. No live TTL was
activated here. Account-wide erasure remains recursive under `users/{uid}`.

Indexes, checkpoints/views/links, ingestion/logging/network, retry amplification,
backfill and workloads outside these assumptions remain additional/unmeasured.
The TTL declaration and activation prerequisite are in the runbook. A full day
of drift comparison is the retained fact window; stale workers need a new
baseline after a retained-window sequence gap. Reducing Home read percent to zero
also stops sampled-log reads and expiry-triggered facts/wakes from Home.

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
legacy deletion routine is added. Round-2 capture uses an independent transaction
after the serving commit; errors are counted and dropped.

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
capacity extension. Content-free structural deltas, references and one-day fact expiry replace full
before/after speech snapshots. Retained/index bytes and expiry lag still need
measurement before scaling; a clean drift counter is not a cost proof.

## After the authorized train

Verify the release SHA and traffic percentage of every receiving revision and a
new drain metric/log from that artifact. Verify collector delivery, OIDC queue
binding, the existing sweep, indexes, alert installation and meaningful comparison
volume. Planscost owns 5/25/50/100 read cohorts with drift zero for a full day at
each step. Check Home 200/304 behavior, policy refresh/recovery, pending composition,
receipt continuity, vendor usage, per-caller billed operations and retained bytes.
The [runbook](../runbooks/episode-log.md) owns the operational ramp and rollback order.
