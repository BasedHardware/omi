# Round 8: translator outside accepted sends

Branch `lane/capture-window-translator`, in the prescribed Ephemeral worktree.
Pinned base `cb319aff0f73f39d218553d0050c5c01fb5bfb1e` equals the supplied
`origin/main`. No fetch/sync, push, remote PR, deployment, cloud/data/credential
access, or flag enablement. No forbidden-path edits. `AUDIO_TIMELINE_V2` remains
false in every deployment declaration. Tests use only explicit `backend/test.sh`
file lists or `backend/scripts/run-unit-ci.sh`, with the network guard intact.

## Findings and ranking

The supplied 18% is a distinct stored-segment attribution share, not a provider
callback failure rate. The new sibling counter counts outside-send rejected
segment translations; neither it nor these offline reproductions establishes
the fleet's provider/session mix.
The earlier 12% and later 18% cover different durations. Merge union changes
window survival, not provider timestamps or accepted-send registration. Those
percentages alone cannot establish a new clock defect or assign 15 percentage
points to one cause.

Ranking below is by plausible fleet reach under the checked-in configuration,
with mechanism proof kept separate from likelihood. Live settings were not read.
The prod listen values and prod overlay declare `STT_CONNECT_ORDER_FROM_CONFIG`
true, `STT_ROUTING_MODE=shadow`, `STT_FAILOVER_RECOVERY_ENABLED=false` and
`STT_RESILIENT_RECONNECT=false`; idle close is unbound/default-off. Ordinary
non-BYOK, single-channel sessions therefore use managed legs, even while the new
router/recovery features are dark. Managed legs already record replay sends.

1. **Soniox/provider axis or genuine timestamp overshoot: broadest possible
   reach, causal split unproven.** Compact send time excludes VAD-withheld PCM;
   capture/elapsed time includes it. A 40 s withheld interval followed by one
   accepted second maps compact 1.2–1.8 s to capture 41.2–41.8 s. Feeding
   41.2–41.8 s instead is outside the compact map for every adapter. That proves
   the consequence of an elapsed-looking response, not that Soniox actually
   emits that clock. Its existing `SONIOX_ELAPSED_AXIS=shadow` is expressly
   unverified. Shadow wall gaps do not prove the provider's origin or its clock
   during paced replay. Genuine tail/start/end overshoot produces the same
   after-last-send geometry. Soniox tokens and Deepgram words are passed through
   without a new offset; Modulate uses `start_ms + duration_ms`. These mechanisms
   could affect a substantial fraction of ordinary gated sessions and thus
   plausibly reach 15%, but no supplied observation distinguishes them. No axis
   guess, elapsed-map promotion, duration-based shift or clipping repair added.
2. **Missing raw replay prefix: strongest proven bookkeeping cause, high loss
   within affected epochs, limited declared prod reach.** Both the paced pump
   and old cross-provider rebuild replay `raw` before installing the legacy send
   wrapper. Unmanaged sockets have no prefix ledger. A two-second prefix creates
   `empty_map`; its subsequent one-second tail is erroneously registered at
   provider 0–1 instead of 2–3 and creates `after_last_send`. A delayed prefix
   callback at 0.2–0.8 can even appear known while borrowing tail capture samples
   5.2–5.8 instead of prefix samples 3.2–3.8. This is a reproducible offset caused
   by registration, not provider drift. If roughly 15% of segments were emitted
   on affected raw replay epochs, near-total early loss there could produce
   roughly 15 percentage points. The checked-in managed chain makes that an
   unsupported fleet assumption: normal managed replacements bypass this defect.
   Raw/legacy/BYOK traffic or live overrides would be needed to make it dominant.
3. **Accepted managed PCM followed by finalize failure: proven, probably small.**
   `LiveLegSocket.send` originally registered spans only after `raw.finalize()`.
   If PCM admission succeeds and flush raises, that accepted span is absent from
   the map and a pending final loses its window. The existing gate wrapper
   registers before finalize; the managed wrapper did not. Roughly 15% would
   require unusually frequent failing flushes plus useful callbacks from those
   failing legs. No such frequency is supplied. Failed/raised PCM admission
   itself remains unobserved and is not repaired.
4. **Reconnect/idle origin drift or other tail registration: not reproduced as
   an independent ordinary loss.** Fresh callbacks create a fresh translator;
   replay origin is capture-relative and provider time restarts at zero. The
   unpaced same-provider reconnect already wraps its prefix. Managed replay,
   normal managed/gated sends and `send_admitted_audio` register their spans.
   The ordered tail's normal packets reach the installed wrapper, and admitted
   onsets retain their existing registered spans. Idle Soniox resumes at
   `last_send_provider_start`, before its logical callback reaches translation;
   its word ranges receive the same offset. Existing idle tests cover compact,
   shadow and experimental elapsed modes. Queuing/pacing by themselves do not
   consume provider sample time. No guessed reconnect or wall-clock offset added.
5. **Eviction/anchor compaction:** separately identified, not a new outside-axis
   repair. Send eviction keeps its existing `send_map_evicted` attribution.
   Anchor compaction refuses projection. No retention bound was changed.

Provider specifics: Soniox uses final token `start_ms/end_ms` (live connectors
leave `preseconds=0`); keepalive/finalize frames register no PCM. Deepgram uses
actual word offsets and its SDK callback hops back to the listen loop. Modulate
is normally VAD passthrough and uses raw utterance milliseconds; its final
partial has the existing 1 ms tail shape. Parakeet websocket frames are passed
through, batch offsets add the consumed PCM cursor, and the windowed path uses
`job.start + relative_offset` on received provider bytes. Window capacity/anchor
trimming retains that absolute provider-byte cursor; capture silence advances
its separate capacity policy, not emitted provider timestamps. Windowed Parakeet
already rejects starts beyond its posted window and clips ends to the posted
window; this lane changes neither policy. Genuine downstream overshoot still
receives no repair.

## Code evidence

Source locations on the behavior/proof revision:

| Mechanism | Owning path |
|---|---|
| Paced raw prefix before live wrapper | `backend/routers/listen/receiver.py:1380`, replay admission at 1425 |
| Legacy cross-provider raw prefix | `backend/routers/listen/legacy_recovery.py:119` |
| Managed admission and finalize ordering | `backend/utils/stt/live_session.py:819` |
| Raw accepted-send recorder and observed bounds | `backend/utils/stt/replay_capture_accounting.py:28` |
| Exact coverage and capture-wall refusal | `backend/utils/audio_timeline.py:848` |
| Soniox token clock | `backend/utils/stt/soniox.py:524` |
| Deepgram word clock | `backend/utils/stt/streaming.py:1115` |
| Parakeet absolute received-byte cursor/materializer | `backend/utils/stt/parakeet_window.py:577`, 798, 1196 |
| Managed idle-resume provider origin | `backend/utils/stt/live_session.py:932` |

## Implemented contract

One new switch: **`LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS`**, default false in
code, all base/dev/prod runtime bindings, all four listen/pusher Helm values,
the feature registry and deployment classification. Generated runtime manifest
and flag registry were regenerated from their sources.

- The new STT utility delegates raw replay admission unchanged and registers only
  `True` PCM sends with valid receiver-observed capture references. It is wired
  before paced-prefix delivery and old cross-provider replay. Managed legs and
  absent capture clocks retain their existing path, preventing double accounting.
- Managed PCM accepted by `raw.send` is recorded before finalize when ON. The
  same finalize exception still returns failure and retains recovery policy.
- Repaired epochs require exact provider sample coverage plus strict capture-wall
  projection. No edge tolerance extends this new proof. Failed sends, samples
  beyond receiver observation, capture holes, elapsed/provider holes, wall hiatuses,
  compacted anchors and even tolerance-sized overshoot refuse capture mapping
  while preserving text. Existing accepted evidence remains attached to an epoch
  if the flag later turns off; new repair registrations stop. Fresh flag-OFF runs
  preserve the old send ordering and mapping behavior exactly.

The attribution-only commit adds
`omi_audio_timeline_outside_sends_total{provider,send_path,subreason}` with exactly
five subreasons: `empty_map`, `before_first_send`, `after_last_send`,
`interior_hole`, `evicted`. These are map geometry, not guessed root causes.
No session, UID, text, offset or other high-cardinality labels. Existing rejection,
past-send and persisted-segment metric names/labels/semantics remain intact.
A failing telemetry callback cannot affect text or placement.

Public/storage schemas, speaker-resolution status, audio format, embedding caches,
provider selection, transport pacing and rollout settings are unchanged. The
pipeline doc owns the new switch and telemetry semantics.

## Offline proof

The reusable R8 suite drives actual Soniox token and Modulate utterance parsers,
Deepgram's extracted real callback (connector replaced locally), and Parakeet's
actual window materializer. Fully local transports supply accepted-send receipts;
there are no provider connections or cloud clients. The actual paced pump,
legacy rebuild, receiver callback factory, transcript ticks and StrictFirestore
persistence are exercised. Managed finalize tests use the real managed send
boundary and receiver factory; they do not claim a remote provider result or an
end-to-end managed connector handshake. VAD admission/scoring and speaker
assignment at the test boundary are deterministic local seams.

Cases cover all four providers, replay at nonzero capture origin, prefix and tail
finals separately, queued tails, reconnect with recovery ON/OFF, accepted PCM then
flush failure, delayed-prefix misplacement, managed non-duplication, failed sends,
unobserved audio, VAD/capture gaps, wall hiatuses, provider overshoot and compact
versus elapsed-looking timestamps. Existing suites additionally cover idle
suspension/resume, queued admitted onsets, frozen writes, recovery tails and
Parakeet capacity/replay state. No new slow marks or duration-guard relaxations.

Controlled synthetic recovery outcome per provider: a two-second replay prefix
at capture 3–5 s and a one-second tail at 5–6 s yield 0/2 correctly known prefix
and tail rows OFF and 2/2 ON; a separate true overshoot remains unknown. A delayed
prefix final that main wrongly marks known is moved from tail samples back to
its accepted prefix samples. Accepted-PCM/failing-finalize scenario: 0/1 known OFF,
1/1 ON, with unchanged failure return. These are cause-specific simulations, not
an estimate of fleet recovery or a claim that the supplied 18% will disappear.

## Validation receipts

Pinned behavior source: `56dce59ac474e909b728d5352ccdc4179243945d`.
Final proof revision: `3d18b0cca37cd6c4d1b5ab602b2f05c8d63b1e79`; this changes
only two test assertions to disable relative tolerance on Unix epoch values.
Both now require absolute one-sample precision. Production source is byte-identical
between these revisions. The report-only commit follows terminal validation.

Local commits, in order:

- `7ef4674a90`: independent bounded attribution counter.
- `8554161eda8f823e7259a99e44f61a12ca60f762`: one default-off switch,
  accepted-send repairs, strict proof, offline tests, declarations and owning doc.
- `56dce59ac474e909b728d5352ccdc4179243945d`: callable typing of the raw replay
  admission; runtime behavior unchanged.
- `3d18b0cca37cd6c4d1b5ab602b2f05c8d63b1e79`: sample-precise test assertions.

### Red/green and OFF proof

`.agent-brief/r8-proof.py` substitutes the five exact pinned-main behavior
sources from `git show`, runs the explicit two-file `backend/test.sh` list,
then restores candidate bytes in `finally`. Its source hashes and restoration
witness are in `r8-base-proof.json`.

- Main red selection: **25 failed, 27 passed, 60 deselected**, no collection or
  infrastructure errors (the separate parity file was also deselected). Failures are the 16 raw paced/legacy prefix/tail cases
  across all four providers, four accepted-PCM/failing-finalize cases, one paced
  same-provider reconnect case, and four delayed-prefix placement cases.
- Candidate R8 suite: **112 passed**. Attribution suite: **6 passed**. Their
  explicit two-file final run is `r8-final-boundary-tests.log`.
- Main and candidate OFF selection each: **55 passed, 57 deselected**, plus the
  existing OFF parity file **1 passed**. The complete decoded persisted rows
  and all exercised existing `omi_*_total` counter deltas match exactly across
  16 provider/phase/replay-mode recovery receipts and three earlier parity
  payloads. Only the new sibling counter is excluded. See `r8-parity-result.json`,
  `r8-main-off.log`, `r8-candidate-off.log` and their per-case JSON receipts.
- Focused 37-file run: **1762 passed, 3 deselected, zero failures/errors/skips**,
  using `BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r8-focused.txt"
  PYTHON=.venv/bin/python bash backend/test.sh`; terminal exit 0 in
  `r8-focused-result.json` and `r8-focused-final.log`. This preceded the type-only
  and test-precision commits. Final canonical shards cover the resulting revision.

### Canonical final shards

All four commands ran sequentially from `backend/`, with
`PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/k`
for each `k=1,2,3,4`. Every terminal command used HEAD
`3d18b0cca37cd6c4d1b5ab602b2f05c8d63b1e79` and selected 399 files;
1596 selected files in total. No source changes during this run.

| Shard | Passed | Failed/errors | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| 4/1 | 7750 | 0/0 | 5 | 76 | 0 | 190.84 |
| 4/2 | 7275 | 0/0 | 19 | 1320 | 0 | 120.12 |
| 4/3 | 7450 | 0/0 | 2 | 43 | 0 | 121.4 |
| 4/4 | 7149 | 0/0 | 1 | 653 | 0 | 131.45 |

Total: **29624 passed, 27 skipped, 2092 deselected, zero failures/errors**.
`r8-shard-{1,2,3,4}.log` and `r8-shard-counts.json` hold the terminal receipts.
Independent recount agrees: `r8-all-shards-result.json`.


### Preflight and environment

`OMI_PR_BODY_FILE="$PWD/.agent-brief/pr-body-r8.md" make preflight` ran
standalone at the same final proof HEAD: **45 checks passed**, exit 0,
87.4 seconds wall time (87.25 seconds reported by the checks runner).
Local PR metadata includes `INV-MEM-4`,
`Failure-Class: FC-transcript-and-audio-on-independent-clocks`, and the narrow
receiver import line-count exception. `scripts/pr-preflight --suggest` and local
body validation preceded this gate. Receipts: `r8-preflight-result.json`,
`r8-preflight.log`, `pr-body-r8.md`. The declared switch remains false.

`r8-final-source-hashes.json` records the validated source and test bytes.
The subsequent report-only commit does not alter them. No remote CI is claimed.

The initial venv was absent. Per Mac setup guidance, `hostctl context` preceded
`make setup-hooks lane-backend`. The local setup route uses the available wheel
requirements, not the full macOS lock-hash installation. Canonical shard collection
then exposed missing local test dependencies; installed the versions from the
macOS lock (`fake-firestore==0.13.1`, `fakeredis==2.36.2`, `lupa==2.8`) into this
worktree's venv. No requirements/lock-file changes. Python 3.11.15, pytest 9.1.1,
pyright 1.1.403. Canonical dependency preflight: 17 passed, 9 optional warnings,
zero failures. Pyright: zero errors, 12909 warnings, zero information.

Earlier failed receipts are retained rather than presented as successful tests:
`r8-initial-shard-*-typecheck.log` (the two lane-owned callable type errors, fixed
in 56dce), `r8-env-incomplete-shard-{1,2}.log` (missing local fakes/Lua support),
and `r8-concurrent-preflight.log`. That preflight failed the OpenAPI side-effect
witness because a simultaneous unit shard wrote `backend/_temp`; the standalone
rerun passed. A later test-only assertion improvement required a fresh four-shard
and standalone preflight run, reported above. Timing guards, selection filters,
network guard and unrelated source stayed unchanged.

The named Soniox typed-402 failure is already fixed by the supplied base's
`#20693` commit (`cb319aff0f`). It passes in the focused suite and final shard 1;
this lane does not edit its test, circuits or provider selection. No interaction
was observed. The admitted-send ledger change does not alter the failure return
or failover decision.

## Release surface and remaining uncertainty

The owning behavior executes in the backend listen process, primarily the active
GKE `backend-listen` workload and any same-image service serving this listen path.
The pusher declarations mirror the false flag but do not invoke these repairs.
Runtime Cloud Run backend, backend-sync, backend-sync-backfill and
backend-integration bindings are also false. New code must ship with the backend
release image before an enablement could do anything; this lane ships nothing.
No artifact, remote CI, deployment, live override, canary or prod acceptance is
claimed. No flag was enabled and no network-guard bypass was added.

The provable repair removes two bookkeeping mechanisms without inferring a new
provider axis. Whether raw replacement epochs or managed flush failures can
explain roughly 15% of distinct fleet segments remains unknown. The declared
managed chain makes the raw-prefix bug a limited-reach hypothesis in prod. The
bounded geometry counter can distinguish empty maps from edge/hole/eviction
refusals, but after-last-send alone cannot distinguish elapsed timestamps from
missing prefix offset or genuine overshoot. Actual per-provider rejection and
accepted-send evidence is needed for that split; this task's safety rules
exclude acquiring it from production.
