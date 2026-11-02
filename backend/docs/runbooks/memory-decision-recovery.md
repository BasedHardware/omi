# Memory decision recovery, 2026-10-23

Scope: code and Git history in BasedHardware/omi, starting at
`312b4f734c22`; round 2 includes origin/main `26099580cc96`. No production API, account, logs, metrics or credentials were
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

`complete_observation_intake` in `utils/memory/canonical_consolidation.py` owns bounded, ordinary intake independently
of Dream's cleanup rollout. Extraction invokes it **after** capture commits;
maintenance rotates a separate capture/id cursor over the existing registered
query, scanning at most 100 rows and deciding at most 25 per pass. It does not
filter out expired rows. Maintenance separates DB reads, model work and
settlement across executor steps and retains the existing Flex router. Ledger
accounts keep their daily-sweep formation owner.

`MEMORY_OBSERVATION_INTAKE_ENABLED` is an independent, registered kill switch,
on unless explicitly `false/0/off/no`. All three observation entrypoints check
it before DB reads, cursor writes or provider work. Off leaves capture committed
and rows pending; it does not change visibility, required intake, Dream cleanup
or ledger authority. Re-enable to recover pending decisions. This switch stops
new calls, not a call already in flight; canonical fences still govern settlement.

The 64 KB serialized evidence budget applies to each provider request. Larger
partitions split in half recursively down to individual items. A single item
still too large receives a canonical Review route locally, retains its complete
content/evidence and stays visible under the visibility mitigation; it is never
sent to the provider. Each partition is recombined and fully validated before
any apply. Budget splits and local Review emit content-free logs and the shared
fallback counter; rows no longer fail forever at the same batch budget.

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
subsequent Review outcomes. Expired active Short-term rows remain readable as
`short_term_expired_pending_adjudication` with the switch off, matching main,
until the TTL worker applies a terminal disposition. Reverting the lane commits rolls back the code;
source rows and audit receipts are retained.

## Steady-state inline L2 volume and cost — planning estimate

The supplied rough 1% owner sample has 84–156 new rows/day. Linear expansion to
~163,000 owners (~1,630 sampled owners) gives **8,400–15,600 rows/day**, or
0.052–0.096 rows per fleet owner per day. This is an owner-clustered extrapolation,
not a measured fleet total or a count of conversations. The exact supplied sample
elsewhere is 1,743/163,588; using that fraction instead gives ~7,884–14,641 rows/day.
Use the requested rough 1% figures below for capacity planning.

Code bounds and model routing:

- `utils/llm/working_observations.py::MAX_WORKING_OBSERVATION_ITEMS` is **32**;
  finalization captures at most 32 rows. `process_conversation.py` calls intake
  once after nonempty, unlocked capture, not once per fleet owner or per row.
- Each intake entrypoint takes at most **25** undecided items. Remaining rows
  are recovered by the bounded maintenance cursor. A normal inline request is
  one call; a budget split may make up to one call per eligible item. Restricted
  and oversized singleton Review routes make no model call. Ledger accounts,
  locked, already-decided and fenced rows also reduce call volume.
- With all new rows eligible and successful, 25-item perfect owner packing
  would need at least **336–624 total decisions calls/day**; one row per call
  needs **8,400–15,600 calls/day**. Inline conversation count alone has a
  theoretical 32-row packing floor of ~263–488/day, but recovery of rows beyond
  each inline 25 adds calls. Neither ideal floor predicts actual packing.
- Inline uses `get_llm('memory_l2', request_timeout=60, max_retries=0)`.
  `utils/llm/model_config.py` and
  `llm_gateway/config/generated_route_overrides.yaml` route it to OpenAI
  **gpt-6-luna**, reasoning medium. Maintenance uses the existing Flex router.
  Timeout is not a dollar cap; model output/reasoning tokens are not explicitly
  capped by this intake call. Failed or raced batches can incur replay spend.

The committed `llm_gateway/config/cost_rate_cards.yaml` card
`openai.gpt-6-luna.2026-09-22` assumes **$0.10/M uncached input** and
**$0.60/M output** tokens (operator-directed planning rates, pending official
published prices). This is a code-based estimate, not verified vendor usage.
`utils/memory/maintenance_cost.py` supplies existing planning scenarios of
2,500 input + 400 output tokens and 8,000 + 1,200 for a larger batch. Include
system/schema tokens in input and billed reasoning in output. They are planning
assumptions, not measurements of this new prompt. At standard inline rates:

| Average rows per successful call | Calls/day | 2,500 in + 400 out ($0.00049/call) | 8,000 in + 1,200 out ($0.00152/call) |
| --- | --- | --- | --- |
| 1 | 8,400–15,600 | $4.12–$7.64/day | $12.77–$23.71/day |
| 2 | 4,200–7,800 | $2.06–$3.82/day | $6.38–$11.86/day |
| 25, ideal owner packing only | 336–624 | $0.16–$0.31/day | $0.51–$0.95/day |

Formula: `daily USD = calls × (input_tokens × 0.10 + output_tokens × 0.60) / 1e6`.
For the explicit **1–2 rows/call** assumption, budget **$2–$8/day** at the small
scenario or **$6–$24/day** at the larger scenario, before retries, backfill,
provider rate changes or reasoning overruns. Neither is a hard upper bound.
The table adds L2 vendor spend only; extraction spend is unchanged. It assumes
no prompt-cache benefit and no Flex discount; successful maintenance Flex
requests use the existing 50% planning multiplier, so are cheaper at equal tokens.

David must accept incremental steady-state inline spend before choosing the
intake option. The visibility-first branch makes zero new intake model calls.
On the intake branch, the independent kill switch can stop both new intake
lanes while visibility stays on. It does not provide a maintenance-only mode.
After an authorized small canary, replace assumptions with billed
input/output/reasoning/cache tokens, effective provider prices, actual batch
sizes, inline latency, failures and replay calls; reconcile the existing gateway
attempt ledger and vendor usage before expanding a replay budget.

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
Each request evidence payload is capped at 64 KB and oversized partitions split;
oversized individual items route locally to Review. Inline model timeout is 60 s
with no model retry. Measure an authorized small replay's billed input/output/cache tokens,
provider rates and outcome distribution before setting a global replay budget.
Backfill uses the same explicitly qualified rate assumptions above, not Dream's reasoning budget.

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
successful Dream pass alone is insufficient. Investigate sustained failure rates
and growing pending age. A competing legitimate writer can win a canonical
revision/generation fence; its loser may log a failed intake. Confirm the row's
persisted decision before treating that individual event as an outage. Cohort
read timeouts/cache saturation also intentionally produce unavailable bursts.
These signals require diagnosis, rather than an absolute zero-event bar:

```text
event=memory_observation_intake outcome=failed error_type=...
event=memory_observation_intake outcome=split reason=context_budget item_count=...
event=memory_observation_intake outcome=review reason=context_budget item_count=1
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

Round 2 final targeted runs: visibility-first **253 passed** across 18 files;
intake **342 passed** across 23 files. Each branch also passed all seven
Firestore guard files (**780 tests**) and flag-registry fixtures (**42 tests**).
Reason-label tests are included in each targeted run. Intake regressions include
all four off values across all three entrypoints and three oversized-partition
shapes. Logs: `/tmp/memory-a-{targeted-tests,guards,registry}.log` and
`/tmp/memory-b-{targeted-final,guards,registry}.log`. The initial intake run's
three fixture/assertion failures were corrected and the entire targeted set
rerun green. The table below records round 1 executions and overlapping reruns.

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
