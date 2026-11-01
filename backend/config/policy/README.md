# Batch unit policy parts (E1)

The 2026-10-19 owner ruling splits the snapshot by owner. Admission processes and
serving revisions have different settings; admission must not stamp another
role's values. Every part is a frozen dataclass with a schema version,
`source_role` and stable `policy_id` hashing its sorted field values. Unknown
fields are ignored; missing fields use original code defaults, never current env.
`flags=` is a complete, explicit environment for replay.

| Part | Owner / first stamp | Durable record |
| --- | --- | --- |
| `BatchUnitPolicy` | Sync or native-record admission: batch/cohort, live-record admission, nested retire, local final-pass decision | Batch job `policy`, Redis sync job beside `ledger_fence_mode` |
| `ProjectionPolicy` | Projection's first handling: contention, async, labels, live target, timing | Batch job `policy_parts.projection` |
| `SchedulerPolicy` | Scheduler's first pull/failure: head priority, shared live, max attempts | Batch job `policy_parts.scheduler` |
| `RecoveryPolicy` | Quarantine owner's first handling: mode/cohort, multilingual and terminal-empty decisions | Batch job `policy_parts.recovery` |
| `FirstSummaryPolicy` | Enrichment owner when creating the obligation: cohort and deadline | Outbox `first_summary_policy` (sim: recorded obligation part) |

Admission remains immutable. Later cohort changes cannot abort admitted work.
Stage parts are compare-and-set: the first committed writer wins; a later stage
read uses the persisted part, including after restart or env rollback. Sibling
segments serialize through one privacy-eligible canonical job and copy its part
before use. Only the anchor and visited row are written, keeping bounded queue
transactions below Firestore's write ceiling. Adding one part preserves all
other parts. First-summary coalescing retains the original obligation's stamp;
a new obligation gets a new stamp at creation.

Only an admitting role may resolve and persist admission fallback on pre-E1 rows (`policy_source=fallback`),
with bounded telemetry. Redis repair preserves TTL and concurrent progress;
status, scheduler and projection reads remain pure. `load_sync_job_policy` is
an admission-only CAS repair helper; consuming roles never backfill admission. Policy never enters `projection_binding`; its pre-E1 strict constructor and
immutable identity comparisons remain unchanged. Scheduler, projection and
recovery handling leave missing admission fields unset. Legacy stage repair records
`policy_part_sources.<stage>=fallback` and emits fallback telemetry without
resolving or writing admission decisions. Missing stage parts are resolved by their
owner on first use; a partial recorded dict is already a stamp and uses defaults.
Privacy/deletion and paid-intent checks always remain live.

## Before / after reads

| Before | After |
| --- | --- |
| Route, intake and admission transaction independently read cohorts | Admission snapshot is passed separately and recorded on jobs; transaction uses its batch decision |
| Projection and follow-ups re-read five knobs | First projection owner persists a part, then passes it through assignment and completion |
| Scheduler pulls/failures re-read knobs | First scheduler handling records a part; attempts and eligibility use it |
| Recovery checks current owner/mode before and after download / at delivery | Recovery owner records a part; dispatch and delivery retain it |
| First-summary grader consults current percent | Creation part controls the obligation and replay grade |
| Final-pass arm and promotion can differ | One local invocation captures both admission-owned decisions |

Recovery discovery uses a bounded global cursor and checks each candidate's
recorded part, so an owner-cohort rollback cannot hide accepted debt. Dispatch
page size, startup, auth, provider packing, metrics and worker dispositions remain
outside E1 snapshot ownership. The guard fails direct reads of `SNAPSHOT_ENV_KEYS`
and the live-switch keys outside `config/policy/`. Other `BATCH_PIPELINE_*` reads
print nonblocking E1b-candidate warnings; no worker-key allowlist is required.

## Cohorts and live switches

| Cohort | Salt / assignment |
| --- | --- |
| batch-pipeline | Empty legacy salt; exact sha256 first-four-byte bucket, unchanged |
| live-STT retire | Same batch salt; percent clamped to batch percent and batch admission required |
| first-summary (`summary_guarantee`) | Empty legacy salt; existing membership retained |
| transcription-final-pass | Empty legacy salt; existing membership retained |
| recovery | Named allowlist only, unchanged |

Existing summary/final-pass cohorts are explicit compatibility exceptions;
re-salting would reassign users. Every new percentage cohort needs its own salt.
Registry and policy tests enforce the nested-retire rule and exception set.

`kill_switch(name)` is the live E1 reader for recovery-task dispatch and projection
pagination and the maintenance leader lease. Its allowlist must match registry `lifecycle: ops_kill`. Worker-only
switches, `EMPTY_ASR_*` and worker dispositions remain E1b. The worker-owned
`pump.py` and `diarizer/batch_pipeline.py` are unchanged by E1.

## Verification, follow-up and rollback

The AST policy boundary runs in local and CI manifest lanes. Policy tests cover
owner isolation, first-writer persistence, partial dicts, fallback and the 10-18
policy window. Sim accepts admission plus recorded owner parts, or resolves each
part from explicit flags on first use. Existing goldens stay byte-identical to
current main; the policy-window golden grades creation at percent zero against
that stamp. The `role_policy` golden includes policy fields, source roles and
content hashes from two role environments; separate mutations of projection and
recovery ownership must each break it. Historical traces keep their existing
format and byte-identical golden files. The emulator persists admission and stage parts on actual job rows.

When workstream B supplies a canonical stage profile, these parts can move to
admission without changing their consumers. E1 adds no RPC or env/config/IAM
mutation. Revert the snapshot wiring for rollback; policy metadata stays on job
rows, outside the strict pre-E1 binding constructor. The frozen constructor
fixture from main 0d8e1258 accepts E1's written bindings. Old rows use admission
fallback only when an admitting role handles them; stage owners stamp only their
own part. No durable policy fields need deletion. Deployment belongs to the
lead's two-lane train.

## Listen sessions (E2)

`ListenSessionPolicy` is one frozen, schema-versioned, content-hashed record on
`ListenSessionState`. Session tasks inherit its `ContextVar`; routing helpers read
that stamp without changing the routing algorithm. `STT_SERVICE_MODELS` comes
from the listen process's existing provider-order getter, so another role cannot
stamp its order. The raw mode is retained because legacy consumers normalize it
differently. Registry targets (including static routing permission/ramp and replay
limits) parse once at admission/load. The serialized field contains the complete
normalized resolved list, even when env was empty, so later code-default changes
cannot reinterpret an existing record. Credentials, provider health, account
benches, privacy and capacity remain live operational inputs.

`routers/listen/policy.py` loads before STT selection. Redis keys are
`listen:session-policy:v1:sha256(JSON([uid, conversation_or_recording_id]))`.
The TTL is 24 hours, renewed on reconnect: six times the four-hour desktop
recording rotation and the maximum conversation continuation timeout. The server
has no hard socket lifetime limit; a socket retains its in-memory policy even
past Redis expiry. Conversation creation/rollover writes additive aliases for both conversation
and recording UUIDs with SET NX; they are distinct after a rollover. Legacy clients reuse the existing authoritative in-progress lookup before
selection; `prepare()` consumes that same row rather than issuing another lookup.
The legacy ownership, source, device and continuation fences still apply.

Redis reuses `database.redis_db.get_async_redis_client()` and its process-owned
async connection pool, with a 75 ms **total** pool-acquisition/get/CAS/read deadline.
Session boundaries never close the shared client. SET NX makes simultaneous reconnects use the first writer. A
usable stored snapshot wins even if TTL renewal fails. A healthy first write records source `resolved`; reconnect loads record `redis`.
Corrupt or unavailable state resolves once using current listen inputs; source `fallback`
is recorded in `omi_listen_session_policy_total{policy_source}` and shared
fallback telemetry. The one `listen_session_policy` line contains only bounded
source/arm values, the content hash and a count. No UID, transcript, endpoint,
credential, or environment payload is logged. The source metric never labels a
UID, session or policy hash.

No policy Redis call or resolver is added to frames. I/O occurs only at startup,
reconnect and conversation lifecycle alias writes. Routing and the session-end
window/cost outcome metrics use recorded arms. Mid-session env changes apply to
new conversations after their current recorded session ends, rather than
changing the current arm. All `STT_ROUTING_*` and window allocation raw reads are
rejected outside `config/policy/` by the existing local/CI AST guard.

Listen also records paid-spillover admission and its three provider caps, failover recovery, connect shedding/probes/account cooldown,
no-text diagnostics/rescue, language hint/learning cohort and demand-routing
admission/dwell controls. Parakeet-window uses `cohort_bucket(..., bits=64)` with
its original `parakeet-window:` salt and first eight sha256 bytes. E1's batch
32-bit default is unchanged. Window membership is characterized over 260 fixed
UIDs and eight percentage boundaries, including fractional percentages.

The registry still marks `PARAKEET_WINDOW_ALLOCATION_PERCENT` as `rollout`, so
it is frozen rather than promoted to a live kill switch by this change. E1's
registry-checked ops_kill allowlist also includes #22514's live `PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED`, retaining its original false/0/off semantics and logging the policy ID. Rollback is a revert: old code
ignores the additive Redis namespace and state fields; sessions without a usable
record fall back to deterministic resolution. No env or deployment changes are
part of E2; the lead owns the canary/deploy train.

## Generated policy invariants (E3)

`generator.py` builds immutable `BatchUnitPolicy` and `ListenSessionPolicy`
objects directly. The policy modules own the relationships that constrain
generation, including nested batch/live-STT retirement and listen routing,
allocation and demand dependencies. `covering_array.py` creates a seeded,
constrained all-pairs array without a third-party dependency.

The normal backend unit test runs a fixed-seed slice through
`testing.pipeline_sim` with policy objects, then checks owner result ordering,
single paid recovery, privacy/deletion fences, stale-target spend and equality
between the used and recorded policy. Its listen harness reuses the E2 Redis
boundary to prove reconnect stability and that `policy_source=fallback` appears
only when Redis fails. The `policy_window` characterization is also replayed
from its stored policy part and policy ID.

Run the complete matrix from `backend/` with
`python scripts/policy_pairwise_sweep.py --seed 1`. The script prints factor,
feasible-pair, row, simulation, spend and runtime totals. Scheduling that sweep
nightly remains pending David; E3 adds no workflow.
