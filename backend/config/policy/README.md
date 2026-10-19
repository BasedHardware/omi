# Batch unit policy parts (E1)

The 2026-10-19 owner ruling splits the snapshot by owner. Admission processes and
serving revisions have different settings; admission must not stamp another
role's values. Every part is a frozen dataclass with a schema version,
`source_role` and stable `policy_id` hashing its sorted field values. Unknown
fields are ignored; missing fields use original code defaults, never current env.
`flags=` is a complete, explicit environment for replay.

| Part | Owner / first stamp | Durable record |
| --- | --- | --- |
| `BatchUnitPolicy` | Sync or native-record admission: batch/cohort, live-record admission, nested retire, local final-pass decision | `ProjectionBinding.policy`, batch job `policy`, Redis sync job beside `ledger_fence_mode` |
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

Pre-E1 admission rows acquire a durable fallback and `policy_source=fallback`,
with bounded telemetry. Redis repair preserves TTL and concurrent progress. Old
Firestore bindings adopt the recorded admission policy during comparison while
retaining all other identity checks. Missing stage parts are resolved by their
owner on first use; a partial recorded dict is already a stamp and uses defaults.
Privacy/deletion and paid-intent checks always remain live.

## Before / after reads

| Before | After |
| --- | --- |
| Route, intake and admission transaction independently read cohorts | Admission snapshot flows through the binding; transaction compares its batch decision |
| Projection and follow-ups re-read five knobs | First projection owner persists a part, then passes it through assignment and completion |
| Scheduler pulls/failures re-read knobs | First scheduler handling records a part; attempts and eligibility use it |
| Recovery checks current owner/mode before and after download / at delivery | Recovery owner records a part; dispatch and delivery retain it |
| First-summary grader consults current percent | Creation part controls the obligation and replay grade |
| Final-pass arm and promotion can differ | One local invocation captures both admission-owned decisions |

Recovery discovery uses a bounded global cursor and checks each candidate's
recorded part, so an owner-cohort rollback cannot hide accepted debt. Dispatch
page size, startup, auth, provider packing, metrics and worker dispositions remain
explicit process/worker exceptions in `guard.DEFERRED_READS`.

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
pagination. Its allowlist must match registry `lifecycle: ops_kill`. Worker-only
switches, `EMPTY_ASR_*` and worker dispositions remain E1b. The worker-owned
`pump.py` and `diarizer/batch_pipeline.py` are unchanged by E1.

## Verification, follow-up and rollback

The AST policy boundary runs in local and CI manifest lanes. Policy tests cover
owner isolation, first-writer persistence, partial dicts, fallback and the 10-18
policy window. Sim accepts admission plus recorded owner parts, or resolves each
part from explicit flags on first use. Existing goldens stay byte-identical to
current main; the policy-window golden grades creation at percent zero against
that stamp. The emulator persists admission and stage parts on actual job rows.

When workstream B supplies a canonical stage profile, these parts can move to
admission without changing their consumers. E1 adds no RPC or env/config/IAM
mutation. The train must upgrade policy-consuming readers before enabling the
new admission writers, because the predecessor binding decoder is strict.
Rollback reverts decision wiring while retaining the additive policy
value type, `ProjectionBinding.policy` and binding decoder until E1 jobs drain.
The predecessor's strict `ProjectionBinding(**raw)` cannot read a new binding
without that reader compatibility; an unmodified predecessor artifact is safe
only after E1 bindings have drained. E1 readers handle pre-E1 rows through the
recorded fallback path. No durable policy fields are deleted for rollback.
Deployment belongs to the lead's two-lane train.
