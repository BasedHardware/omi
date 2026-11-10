# Token lease: batched pre-review fixes

This is the local follow-up to #25018 at `5207fe3ebd3b`. Seven pre-review reports were read from the pipeline-refactor and Firestore-cost lead runs. Fresh main `8141729fccd928b90d16b34c13bcc162fef01fa5` was merged in `f408a309c2c6`; no rebase or force operation. Main's 223 alert payloads and the two token-lease payloads are an exact union of the split files, regenerated through `backend/scripts/provision_monitoring_alerts.py --regenerate`.

## Disposition ledger

| Finding | Disposition | Result / evidence |
|---|---|---|
| Fresh-main alert conflict (both merge reviews) | Fixed | Regenerated exact 225-rule union, including `omi-batch-staged-input-age`; alert/telemetry contracts cover the mirror. |
| #24866 adjacent-file dependency (both merge reviews) | Fixed sequencing | #24866 was confirmed open, head `ff7e36a2a168`; this branch merges main independently. Landing order is #25018 first, then #24866 merges the resulting main and preserves both transaction/scheduling intents. The PR body draft states this explicitly. |
| Unfinished-row retention KeyError (both correctness/custody rounds) | Fixed | Retention requires closed/partial plus aware, ordered datetime bounds before any storage IO; unfinished uploads keep the original successful response. |
| Retain indexes unguarded timestamps | Fixed with same guard | Both timestamps are validated, including missing/null, malformed and naive values; no direct row indexing. |
| Recovery publication fence bypass under worker rollback | Fixed | Separate jobs enter `record_recovery_waiting`, invisible to old `record_pending` workers. Mode-independent transactional promotion waits for original publication; real emulator tests exercise ledger and direct-job authorities. |
| Registration loses late observation after committed reply loss | Fixed | Persist `append_late` on the exact token and return it on idempotent re-registration. Unit and real committed-response-loss proofs retain one revision and one late event after storage. |
| Manifest renews frame producers / shadow can 503 | Fixed | Manifest renewal is serve-cohort only. Custody renewals target custody-source tokens; frame tokens are unchanged. Off/shadow/non-cohort perform no manifest token IO. |
| Partial selected archive becomes false 503 | Fixed | A nonempty selected subset is a durable append; deliberately unselected files preserve route semantics. Genuine partial storage failures remain refusals with no late counter. |
| Renewal error drops live audio | Fixed | Pusher renewal failures return to the storage lane without advancing the successful renewal clock. |
| Renewal error tears down live socket | Fixed with same guard | Every pusher caller uses the guarded method; cancellation still propagates normally. |
| Failed begin resurrected by next frame | Fixed | Track committed registrations separately from candidate tokens retained for abandonment. Failed or in-flight uncommitted candidates cannot renew. |
| fail_recording bookkeeping/gauge leak | Fixed | Retire local clocks, locks, late observations and registration ownership on failure, including an in-flight renewal completing afterward. |
| Custody receipts never expire | Fixed | Active repair deletes receipts after 24h using existing server `recorded_at`, including old receipt versions, under bounded pages/time. Audio and recovery jobs are untouched. No idle worker activation or out-of-band TTL policy. |
| Finish receipt can survive account erasure | Fixed | Enroll `assert_batch_write_allowed` in every new receipt-producing transaction before any write/early mutation. Read-only existing-receipt replay stays read-only. A real emulator test fences erasure before child enumeration and rejects a later finish before it can create an unseen child receipt. |
| Shadow lease_would_expire allegedly missing on active repair | Not a bug | Full planners already increment in `record_seal_repair.plan_seals` and `record_seal_nojob.plan_backfill`; partial finish increments transactionally in `database/record_partial.py`. The cluster wrapper copies the diagnostic. Incrementing there would double-count. Added active-path nojob/pending regressions with/without diagnostics, leaving production counting unchanged. |
| Custody emulator proof absent from CI | Fixed | Named run in the existing emulator proof runner and matching workflow triggers. |
| Nojob emulator proof skips unit shards | Fixed | The existing emulator CI lane now runs it with a real loopback emulator; no skip removed or weakened. |
| Lifecycle property proof absent from CI | Fixed | Invoke the existing hermetic lifecycle runner with the explicit property module; CI installs its Redis/FFmpeg/Opus leaves and triggers on both modules. |
| Real PromQL backtest manual-only | Fixed | New checksum-pinned promtool check in the checks manifest for both local and CI; actual split-file expression is evaluated. |
| 50ms Cloud Tasks deadline race | Fixed | Inject actual timeout expiry only once pipeline/enqueue have entered, with an unresolved event. Keep the exact one-marker-write assertion and assert exactly one enqueue call. No timeout-only increase. |
| Killed-child test still uses real 0.3s budget (nit) | Fixed | Keep the readiness pipe and advance the coordinator's injected clock; row expiry no longer depends on host scheduling. |
| Literal GKE lease env overrides shared rollout vector | Fixed | Explicit producer ConfigMap references replace literal overrides. Protected-environment inputs feed both runtime renderers; rendered off/shadow/serve tests compare sync, pusher, listen and the separately typed repair vector. |

## Protocol and deployment notes

Only current workers can promote a parked recovery after original publication. Flag rollback still promotes; an old-image rollback safely retains the obligation until rollforward. Original jobs/units and raw audio remain immutable. New cleanup deletes metadata receipts only. Its 24h window exceeds the bounded request plus lease margin; it selects the existing `recorded_at` so no receipt backfill is required. The registry declares the collection-group `recorded_at` ascending index and regenerates `firestore.indexes.json`; schema readiness remains a release prerequisite, with no cloud changes performed here.

Apply producer rollout inputs consistently through the protected environment and shared ConfigMap, roll every producer, and only then change the separately typed repair values to the same vector. Checked-in defaults remain off. Preserve the 48h shadow soak, fixed release epoch and approved ramp. #25018 lands first; refactor-lead then reconciles #24866 against that resulting main. The old note's opposite ordering is superseded by this explicit lead-approved sequence.

## Validation

Validation is in progress. Exact commands, pass counts and any remaining limitations will be recorded before the final local handoff. No push or new independent review is performed by this implementation turn.
