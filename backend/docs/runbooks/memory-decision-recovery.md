# Memory decision recovery, 2026-10-23

Scope: code and Git history in BasedHardware/omi, starting at
`312b4f734c22`. No production API, account, logs, metrics or credentials were
accessed. GCP tier: **none**. The supplied `.rca-report.md` and
`.fleet-aggregate.txt` are other agents' claims, not independently verified
production evidence. No backfill, deployment, push or PR was performed.

## Proven mechanism and limits of the attribution

There are two different pipelines:

1. Conversation extraction (`utils/conversations/process_conversation.py:1414`)
   produces grounded, processed Short-term observations, atomically replacing
   that conversation's canonical source via `MemoryService.replace_conversation_memories`.
2. Canonical intake must decide each observation. `apply_consolidation_decision`
   (`utils/memory/canonical_consolidation.py:313`) applies the route through the
   canonical transaction. `_promotion_audit` (:217) builds the
  `admission_receipt` only for promote: it binds source revision, output content
  hash, exact evidence, graph plan and supersedes. This is **not** proof of a
  Dream run. `complete_required_intake` (:447) only completes items with
   `promotion.required`, processed metadata and a valid required-processing
  receipt; ordinary extracted observations are explicitly skipped.

The audit still uses `processed_by=canonical_batched_consolidation` through this
shared primitive. That label alone does not prove the retired model planner is
present in an image, contrary to the initial agent report.

The proven ordinary-decision regression is `5ccac79357d` (committed
2026-10-15 07:02:42 UTC). Its parent ran `run_canonical_consolidation` from
Short-term maintenance; the commit removed that planner and replaced its call
with `complete_required_intake`. The Dream capability registry supplies
verified cleanup and Review-only new facts, but no replacement caller of
`apply_consolidation_decision` for ordinary extracted rows. The only other
production caller left was the TTL rejection path. The same omission exists at
the supplied production source ref `a941331`.

Before that retirement, the canonical planner could promote, review, archive or
reject ordinary observations for any owner independently of Dream membership.
Thus random free-user promotion receipts do not imply fleet Dream eligibility.
The supplied date of the observed inflection is compatible with a later deploy
of the retirement, but **Git does not prove when an artifact reached production**.
The claimed pre/post production image contents and deployment dates need exact
revision/image-source evidence before naming a deployment as causal.

The cohort migration `f356d1d4ebe` (2026-10-18 05:47:19 UTC) replaced the finite
Dream env allowlist with cached Firestore membership and removed legacy secret
bindings. Under declared `allowlist`, an absent seed, unreadable cache or unbound
resolver could deny everyone, making `dream_store.mark_dirty` return false
before enqueue. That is a reproduced configuration failure mechanism, **not
proof that the seed/read actually failed in prod**. `de3796e6` added awaited
refreshes; `300533371d3` injected the resolver at the serving composition root.
Current `main.py:101` binds that runtime for backend-sync too. Synchronous dirty
hooks warm cold reads themselves; `run_pass` awaits the async warmup. No examined
migration diff removed `DREAM_AGENT_ENABLED` or `DREAM_AGENT_ELIGIBILITY`.

The dirty path is `after_write` → `notify` (`database/dream_dirty.py:32,65`) →
`dream_store.mark_dirty` (`database/dream_store.py:89`). It requires the env
switch plus `dream_control/global.enabled`, then `may_be_eligible`, then the
owner's authoritative `eligible` policy. `all` does not require membership;
`paid` requires its percentage/entitlement or a listed exception. Free owners
outside the declared paid cohort correctly get no Dream dirty enqueue. The
25% paid cleanup ramp is not an all-user memory-intake policy.

Consequently code alone cannot prove that `f356d1d4` caused both fleet-wide
observations. A missing cohort cannot veto declared `all`, and the later paid
ramp intentionally excludes most free owners. The production global control
state, member seed, read failures, service env and deployed revisions remain
unverified. The code fixes the missing ordinary intake owner and the silent
unknown-membership failure rather than asserting that temporal coincidence is
causal proof.

A second correction to the supplied evidence: the starting main already made
expired **active** Short-term rows readable pending adjudication
(`models/product_memory.py`, `is_default_access_eligible`). The TTL worker could
still explicitly reject them, and Review routed to Archive. An aggregate
visibility estimate based only on `expires_at` does not establish what the
current default read endpoint returned.

## Implemented recovery

`utils/memory/canonical_consolidation.py:701` owns bounded, ordinary intake independently
of Dream's cleanup rollout. Extraction invokes it **after** capture commits;
maintenance rotates a separate capture/id cursor over the existing registered
query, scanning at most 100 rows and deciding at most 25 per pass. It does not
filter out expired rows. Maintenance separates DB reads, model work and
settlement across executor steps and retains the existing Flex router. Ledger
accounts keep their daily-sweep formation owner.

One complete model partition is validated before any apply. Intake may not
reference, supersede, merge or replace other facts. Promotion requires exact
owned evidence, high confidence, a durable basis and agreement with authoritative
owner attribution. Captured content is preserved. Restricted observations route
to Review without sending them to the new model call. Locks, explicit owner
rejections, blocked processing, deleted sources and already-decided rows never
reach planning. Errors keep committed captures and emit shared fallback
telemetry; maintenance can replay their IDs. Current revision, content hash,
source/account generation, writer mode, account deletion, destructive-operation
coordination, graph and outbox fences remain in the canonical transaction.

Dream membership errors now raise a typed unknown result. Independent declared
`all` and paid eligibility survive without fabricated allowlist overrides;
unknown membership never grants on-demand spending. Allowlist-only admission
waits and retains its due row instead of treating an outage as revocation.
Empty member discovery and unavailable reads emit health logs and fallback
metrics. An explicit false still revokes membership. An actually empty
allowlist is never widened to all users.

`MEMORY_UNDECIDED_VISIBLE` is registered in `config/feature-flags.yaml`, defaults
on, and carries the all-owner rollout/verification note. While on, pending
observations and Review remain Short-term, and age alone cannot make TTL
maintenance reject them. Historical active Review archives project as
Short-term in default lists without rewriting history; indexed reads include
archive candidates and recheck the same access policy. Privacy, source deletion,
owner rejection, blocked processing, restricted sensitivity and third-party
grants still win. `false/0/off/no` restores TTL handling and archive routing for
subsequent Review outcomes. Reverting the lane commit rolls back the code;
source rows and audit receipts are retained.

## Backfill plan — report only

After deployment acceptance and separate operator authorization:

1. Inventory rows captured since **2026-10-19 00:00 UTC**, paginating owners and
   each owner's collection with count-only output and opaque checkpoint IDs.
   Separate ordinary decisionless rows, explicit pending/processed intake,
   Review, TTL-only rejection and genuine owner/privacy terminal states. Confirm
   query indexes and any live Firestore TTL policy first; neither was read here.
2. Re-drive active, processed, source-active, decisionless Short-term IDs through
   `complete_observation_intake`, at most 25 per batch, including rows past 48 h.
   The maintenance recovery cursor is another bounded entrypoint, but this work
   did not create or verify a production maintenance schedule. Explicit owed
   submissions go through normalization/receipt completion instead. Retain
   revision/generation fences and drain committed projection outboxes.
3. Do not re-decide pending Review. The visibility projection makes active
   historical Review rows list-visible immediately. Acceptance/correction uses
   the existing owner Review workflow and required-processing receipts.
4. TTL-hidden rows are not automatically resurrected by this fix. Inventory
   their retained content/evidence and prove the route came solely from the
   former TTL policy. Reopening requires a separately reviewed, canonical,
   revision/generation-fenced operation that preserves prior decision history
   and emits projection outboxes, followed by normal intake. Do not clear
   promotion/status fields with raw Firestore updates, invoke user APIs as an
   owner, or override owner rejection, suppression or privacy/deletion receipts.
5. Code expiry hides/archives through canonical apply; it does not hard-delete
   the memory content. An expired or TTL-hidden row with preserved active
   evidence is potentially recoverable. A privacy-scrubbed/purged row is not
   recoverable from that document and must never be resurrected. Re-extraction
   from still-authorized original sources is a separate decision, subject to
   the same deletion fences. Live external TTL configuration could change
   physical recoverability and remains unverified.

Sizing from the **supplied** 1,743/163,588 owner sample: 441 decisionless rows
across 10-19..10-22 projects to roughly **41,400 rows**. This is a user-clustered
rough extrapolation, not a measured fleet count or confidence interval. At 25
items/batch its ideal packing lower bound is ~1,656 model batches; batching must
stay owner-scoped, so practical calls will be higher (many owners have few rows).
Request input is capped at 64 KB; inline model timeout is 60 s with no model
retry. Measure an authorized small replay's billed input/output/cache tokens,
provider rates and outcome distribution before setting a global replay budget.
No spend estimate here assumes the old planner or Dream's rates apply.

## Post-deployment acceptance

Verify every receiving service's running `OMI_BACKEND_RELEASE_SHA` (or image
source) and traffic share first. A merged source commit is not recovery. Then
check newly emitted, content-free lines:

```text
event=memory_observation_intake outcome=committed route=promote
event=memory_observation_intake outcome=committed route=review
event=memory_observation_intake outcome=committed route=archive
event=memory_observation_intake outcome=committed route=reject
```

Use a separately authorized free-owner canary and paid-owner canary; require a
persisted canonical decision, a promotion admission receipt/graph/outbox for a
promote, and visible pending/Review behavior past 48 h. Empty-model output or a
successful Dream pass alone is insufficient. These failure signals must be
absent or explicitly resolved:

```text
event=memory_observation_intake outcome=failed error_type=...
event=dream_cohort_health outcome=unavailable
event=dream_cohort_health outcome=empty
event=dream_admission outcome=waiting reason=eligibility_unavailable
```

Inspect increases in the existing metric:

```promql
sum(increase(omi_fallback_total{component="memory_analytics",from_mode="observation_intake",to_mode="pending_decision"}[15m]))
sum(increase(omi_fallback_total{component="agent_tools",from_mode="dream_cohort",to_mode="declared_eligibility"}[15m]))
sum(increase(omi_fallback_total{component="agent_tools",from_mode="dream_admission",to_mode="retry_eligibility"}[15m]))
sum(increase(omi_dream_dirty_enqueue_total{outcome="ok"}[15m]))
sum(increase(omi_dream_pass_total{status="complete"}[1h]))
```

The last two are cleanup-cohort health only. Aggregate ordinary-intake commits
and the age/count of decisionless rows separately. Do not declare success from
Dream metrics while ordinary free-user intake is stalled.

## Local verification

All test executions used `backend/test.sh` with an actual
`BACKEND_UNIT_TEST_FILE_LIST` file, under `nice -n 19 taskpolicy -b`.
The broad selection covered memory/Dream/canonical/Short-term suites, the seven
Firestore guard files, reason-label checks and flag-registry fixtures.
Counts below are per execution and overlap; they are not a sum of unique tests.

| Execution | Result |
| --- | --- |
| Broad, 186 files | 3,192 passed; five initial assertion failures corrected in the focused runs below |
| Final changed/failed set, 15 files | 182 passed |
| Latest atomic intake and authority-race suite | 29 passed |
| Final visibility/read/lifecycle set | 38 passed |
| Additional memory invariant/privacy/hardening suites, eight files | 198 passed |
| Full Firestore guard, seven files, including its slow sentinel | 780 passed |
| Reason-label suite | 19 passed |
| Flag-registry fixtures | 42 passed |
| Whole-repository LLM inventory/provider scans, slow-marked cases | 2 passed |

The slow-marked inventory scans first passed their assertions but exceeded the
fast lane's one-second CPU ceiling. Their final run used the repository's slow
lane timing policy (no fast CPU ceiling), still through `test.sh`, selecting
only `slow and not integration`. Fast suites kept the default CPU ceiling.
The standard Firestore guard supplies its own documented timing policy.

The unchanged import-isolation test file passes all three assertions but fails
the default one-second CPU guard: 1.35 s locally. The same unchanged test with
the original `origin/main` production modules overlaid also fails at 1.43 s.
This pre-existing timing failure was not allowlisted or hidden. Initial timing
attempts were stopped after three failures, followed by the baseline comparison.

The extraction wiring regression was also run against the original production
modules: capture completed, but the decision mock was called **zero times**,
failing its assertion. Current wiring and the real canonical transaction tests
pass. The original source overlay was local only and did not change this lane.

Preflight fixture scripts were routed through `test.sh` using a temporary
manifest that preserved every selected check; a temporary pytest fixture
preserved their original repository-root working directory. No `.github/`
source was changed. The tier guard recognizes only the exact operator-gated
Review-to-Short-term reclassification; a negative mutation proves that widening
its route condition is still rejected. This implements the authorized visibility
policy while other Archive outcomes remain excluded. The legacy-memory ratchet initially
rejected route calls in a new producer file; placing intake with the existing
canonical owner passes the unchanged ratchet. Local execution receipts are
`/tmp/memory-decisions-*.log` on this host. Production acceptance remains unrun.
