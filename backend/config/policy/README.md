# Batch unit policy (E1)

`resolve_batch_policy(uid)` is the admission boundary. `BatchUnitPolicy` is frozen,
versioned and serialized as a dict; `policy_id` hashes the canonical sorted field
values, including the schema version. The identity contains no owner or clock.
Unknown fields are ignored on read; absent fields use the original code defaults,
never the reader's environment. `flags=` supplies a complete environment for replay.
The configured rollout-cohort cache remains the membership authority at admission.

Sync upload routing resolves once and passes that same object to the record-upload
router and intake. Intake records it in `ProjectionBinding.policy` and the scheduler
job's `policy`. Redis sync jobs store `policy` beside `ledger_fence_mode`. Native
record pending jobs record policy at registration and carry it into the binding.
Admission compares the recorded batch decision; a later cohort rollback cannot
abort admitted work. It still checks live ownership and privacy data.

Old Redis sync jobs use a compare-and-set read repair that preserves progress and
the existing TTL; a concurrent persisted policy wins. Old Firestore rows resolve once in `database/batch_pipeline_policy.py`. The
transaction serializes through the first extant, privacy-eligible sibling and copies the chosen
snapshot into the current binding/job. Other siblings adopt that same winner
before use, without rewriting 128 sibling documents for every queue visited. Pre-E1 sibling
bindings adopt that recorded policy during immutable-binding comparisons; their
other identity fields must still match. Fenced rows cannot obstruct healthy queues. Rows record `policy_source=fallback`;
committed loads emit `omi_batch_unit_policy_total{policy_source="fallback"}` and a
bounded log. New admissions record `policy_source=admission`. No policy hash is a
metric label. An old row with no snapshot cannot reconstruct a historical env;
its first reader chooses the fallback and subsequent stages retain it.

## Read map

| Before | After |
| --- | --- |
| Sync route, record-upload route, intake and transactional admission independently call cohort getters | Router's one policy flows through intake and binding; admission compares its decision |
| Projection reads contention, async mode, labels, live target and phase timing at each step | Projection and its transactional retry wrapper read the binding's policy; follow-up discovery filters each job's recorded async decision |
| Scheduler construction/pull/failure reads max attempts, shared-live and head priority | Job policy controls attempts and eligibility; live capacity and privacy remain current data checks |
| Recovery checks owner/mode before and after download and at task delivery | Persisted job policy controls eligibility and recovery provider/disposition; paid-intent and privacy checks stay live |
| First-summary obligations/grades consult the current percent | Batch enrichment records creation policy and retains it while coalescing the obligation; sim grades the upload's policy |
| Final-pass arm/promote decision in transcription shadow can read two configs | The shadow invocation captures both final-pass decisions once |

Recovery discovery uses a bounded global document cursor, then authorizes each
candidate with its policy; it must not miss admitted owners after cohort removal.
Dispatch page size, process startup, auth audiences, provider packing, metrics and
worker dispositions are explicitly outside E1 in `guard.DEFERRED_READS`. The page
size is a serving-pass work bound, not a decision attached to a candidate.

## Cohorts

| Cohort | Salt | Membership |
| --- | --- | --- |
| batch-pipeline | empty (legacy sha256 first four bytes / 2**32 * 100) | unchanged |
| batch-live-stt-retire | same empty salt | nested: percent clamped to batch percent; selection also requires batch admission |
| first-summary (`summary_guarantee`) | empty, existing compatibility exception | unchanged |
| transcription-final-pass | empty, existing compatibility exception | unchanged |
| batch-pipeline-recovery | allowlist only | unchanged; no percentage hash |

Re-salting either compatibility exception would move existing users and is not
behavior-neutral. Every new percentage cohort needs a distinct nonempty salt.
The registry and policy tests guard the nested-retire rule and the exception set.
Clamping an unsafe retire configuration is the intentional safety exception.

`kill_switch(name)` is the only live E1 stop-lever read. Its allowlist is
`kill_switches.KILL_SWITCHES`, checked against registry `lifecycle: ops_kill`:
recovery task dispatch and projection pagination. Worker validation/process switches
remain with their existing owners in E1b. Privacy/deletion checks are data fences.

## Verification and rollback

`python3 backend/config/policy/guard.py` runs in local and CI manifest lanes.
`tests/unit/test_batch_unit_policy.py` exercises serialization, hash stability,
legacy cohort membership, nested retirement, rollback after admission, durable
fallback and policy-window grading. Run it through the normal file-isolated
`backend/test.sh` runner. Pipeline characterization keeps the original JSON files;
its configurations explicitly retain their historical dispatch page size of 1,
before #22321 changed the process default to 16. The policy-window golden adds the
10-18 creation-percent-zero case. Emulator batch admission injects a serialized
policy; serving/worker processes consume the recorded job snapshot.

Rollback is a code revert. Existing dict fields are additive; old readers ignore
them and E1 readers fill missing snapshots once. No prod/dev environment values
change. `pump.py`, `diarizer/batch_pipeline.py`, `EMPTY_ASR_*` and worker-disposition
knobs remain with the worker series and the E1b follow-up.
