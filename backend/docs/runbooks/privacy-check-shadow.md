# Session privacy checks: measurement and shadow rollout

Owner: infracost. Initiative: Security & trust.

The new enforcement levers are absent/off by default. This change does not
alter production configuration. Ship writer tokens everywhere before enabling
shadow, and qualify shadow before any enforcement. The rollout lead merges and
deploys; this lane does neither.

## Safety contract

Every privacy authority write on the SDK Commit/BatchWrite surfaces carries an
opaque `memo_token` plus `memo_schema` in the same atomic Commit. The document
is `batch_pipeline_privacy/{sha256(owner)}`, outside the recursively erased
user subtree. This token is independent of the admission/erasure `generation`.
Source CAS preconditions and result positions are preserved. A failed source
write cannot commit its token. Nonatomic bulk authority writes become individual
atomic source/token Commits; unrelated bulk writes keep their original shape.
Labeled authority BatchWrite requests are rejected before writing because Commit
cannot preserve those labels.

Covered authorities: account deletion markers (including grace transitions),
legal holds and deletion gates, protection/migration fields, speaker consent
version, conversation existence/ownership/privacy/redirect fields, conversation
tombstones, and privacy epoch/purge state. This includes dynamic payloads,
field transforms and deletes. Metadata-only updates with an exists precondition
are excluded when they cannot change the decision. Full-row `snapshots=`
consumers always read live, including episode and recorded-time metadata.

Each cached decision re-reads the durable token and checks its server revision,
including nanoseconds. Missing or malformed tokens/revisions cause live reads.
Opaque-token replay cannot revive a previous decision after a new commit.
Unknown schemas and `blocked`, `purging` or `memo_blocked` also disable reuse.
Token read failures propagate on enforcement; shadow failures are counted and
leave the original live result/exception intact.

Batch memo entries belong to one sync/pump attempt and close on every exit.
Every authorizing transaction reads the token in its conflict set. Existing
transactional legal-hold fences retain both live authority reads. Nontransactional
provider-STT checks remain live (the deferred admission-write fix in
`1219b0ed1b22` is retained). Nothing caches query/list tombstone results or
memory-plane tombstones.

**Lead ruling 93d4a1 (2026-11-02):** Redis writer invalidation is insufficient
when both invalidations fail. All new privacy caches validate the durable token
per decision. Zero-Firestore-read session reuse is excluded. A strict writer
fence that refuses source writes when Redis cannot fence them would be a
separate proposal; it would couple writes to Redis availability and requires
fault-injection evidence and measured savings before approval.

`legal_hold_fence_cache` stores only clear decisions for the marker plus gate.
Gate placement, acquisition (including stale takeover), and finish use
`cache_writer`. `tombstone_negative_cache` stores only per-ID negatives under a
per-owner generation; absence for one conversation never proves owner-wide
absence. `record_deletion` invalidates it. These hints remain bounded to 30
seconds and never authorize reuse without the durable token. No deletion TTL
cap is raised. Per-session memo entries on listen/pusher are bounded and closed
on teardown; late executor leaves cannot reuse a closed holder.

## Measurement

All labels are closed enums with no owner, conversation, job or session IDs.

| Metric | Meaning |
| --- | --- |
| `privacy_check_calls_total{family,mode}` | Calls, including invalid inputs and nested fences |
| `privacy_checks_total{family,mode,reason}` | Allow/block/error decisions |
| `privacy_check_reads_total{family,mode,result}` | Issued point reads, hit/miss/error |
| `privacy_conversations_walked_total{mode}` | Distinct conversation nodes walked per check |
| `privacy_session_cycle_operations{plane,family,mode,kind}` | Listen census over each completed 60-second interval after bootstrap |
| `privacy_shadow_checks_total{family,result}` | Match/mismatch/error denominator |
| `privacy_memo_requests_total{family,result}` | Hit/miss/ineligible repeat-key denominator |
| `privacy_decision_mismatch_total{family,reason}` | Decision disagreement; never a read-count comparison |

Mismatch logs contain only fixed family and decision names and are sampled to
one line per family/minute. Shadow reads have their own `mode=shadow` label so
they do not inflate the live baseline. Do not interpret a zero mismatch counter
without a nonzero comparison denominator as qualification.

## Deploy and ramp

1. Lead deploys writer code: **listen → pusher → Cloud Run** (backend,
   backend-sync, backend-sync-backfill, desktop-backend and other serving
   writers) **→ jobs/operator producers**. Verify the running artifact at
   every writer plane; no mixed old writer can remain before shadow qualification.
   Standalone scripts that bypass `database._client` must install the write
   fence before creating a client; the signup-platform backfill does so here.
   Staging/migration tools are not authority to enable production caching.
2. Record each slice's pre-ramp live read baseline. Enable
   `privacy_checks_shadow` for the sampled cohorts, then all planes. The memo
   candidate runs **after** live allow/block, never changes it and never exports
   snapshots. Shadow wins if an enforcement lever is also present.
3. Require **at least 14 days** of all-plane shadow and **zero unexplained
   `decision_mismatch`**, plus the emulator writer matrix and privacy contracts.
   Count/classify benign concurrent ordering rather than discarding it.
4. Infracost owns expansion and the first enforcement decision is due **14 days
   after shadow reaches all planes**. Remove shadow for the qualified cohort,
   then ramp each independent lever (`bpp_generation_memo`,
   `legal_hold_fence_cache`, `privacy_session_token`, `tombstone_negative_cache`)
   to **5% → PASS on two ticks → 100%**, against its own pre-ramp baseline.
   Keep `privacy_decision_mismatch` clean; any unexplained mismatch stops ramp.
5. Roll back by turning the new enforcement and shadow levers off. The reader
   path uses the same live Firestore reads in the same order as before; mandatory
   writer tokens remain. There is no data migration to reverse.

The reviewed scope's **$45–58/day** is an estimate, not a result of this PR.
Batch reuse is the main candidate saving. The safe external fence can reduce
two point reads to one on warm decisions. A tombstone check still needs one
token read (versus one original tombstone read), and cold candidates add reads;
do not book the original slice-3 savings. Report absolute readouts and vendor
spend against each baseline, without double-counting NOT_FOUND reads. Strict
Redis writer fencing could remove the warm token read, but has no approved
saving until measured and is not implemented here.
The always-on token adds writes and potential per-owner contention; include
`batch_pipeline_privacy` write volume from the existing write probe in the net
cost readout. The scope's dollar estimate does not measure that new write cost.

## Verification

Run unit files through `backend/test.sh` with `BACKEND_UNIT_TEST_FILE_LIST` and
the workspace `bin/omi-heavy run -- nice -n 19` wrapper. The batch writer
matrix in `tests/integration/test_bpp_generation_fence_emulator.py` requires an
explicit loopback Firestore emulator, has no cloud fallback, and tests actual
writer families, failed CAS, transaction retry, bulk writes and subtree erasure.
`test_privacy_shadow_and_session.py` includes deliberate missing-token-bump
mutations: shadow must report stale allow while returning the live block.
Run the hermetic listen/sync e2e harness and privacy-contract tests before push.
