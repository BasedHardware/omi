# Dream v2

Dream runs one bounded shaped-agent session per admitted owner. It can hunt
through history after the dirty queue empties. The shared capability layer lives
in `utils/agent_capabilities/`; scheduling, provider selection, verifier policy,
attention ranking and telemetry remain in Dream. Chat will mount the same tools
in a later PR; this change does not mount them in chat.

## Session and authority

The sanctioned `utils/llm/shaped_agent.run_loop` owns turns, tool-call ceilings
and graceful stops. The six tools are `search`, `read`, `propose_edit`, `ask`,
`learn_term` and `finish`. Schemas are in `models/agent_tools.py`; edits and
uniform owner refs are in `models/agent_edit.py` and `models/agent_refs.py`.

Search supports lexical, semantic, temporal, people and vocabulary filters, with
bounded snippets and opaque continuation cursors. A session tracks seen refs;
full reads admit record snapshots. Unknown refs, stale cursors, unreadable records
and exhausted read budgets produce structured feedback. Proposal validation
checks schema, grounding, protected targets, source/generation fences, suppression,
caps and current snapshots immediately. Rejected proposals can be repaired and
resubmitted in the same session. No autonomous proposal writes during planning.

The caller supplies `authority`, never the model. `dream` stages proposals for
verification. `user` represents the signed-in owner's explicit request and applies
guarded mutations with the same journal and Undo. That authority is temporarily
scoped to the owner through the writer; it neither grants another owner's access
nor depends on autonomous Review admission. Immediate user edits still consume
the session edit cap. Chat integration remains outside this PR.

Seed data contains the owner profile, vocabulary, confirmed people, dirty targets,
recent Undo/feedback and short persisted notes on where to look next. Instructions,
seed records and tool responses explicitly mark evidence as untrusted data.
Previous notes cannot grant authority or override guards. Empty-backlog sessions
still hunt for recurring names, extraction junk, stale facts, duplicate people,
tasks and captures. Owners with no usable history finish without a model call.

## Verification and effects

At graceful finish, two independent verifier calls see only each staged edit,
its cited evidence and minimal context, never planner history, seed notes or each
other's response or the proposer's reason. The two mounts use distinct audit/falsification framing. Batches use server proposal IDs; duplicate/missing IDs fail
verification. Staging budgets reserve verification capacity, so turn/tool/read
exhaustion can still verify accepted proposals.

Both agree plus auto eligibility plus no Undo-rate demotion permits journaled
apply. Both disagree drops the proposal and increments a count. A true boolean split or agreed demoted proposal can use Review. Missing, invalid and zero-vote results are unverified and neither apply nor enter Review. Eligible proposals are ranked by value then verifier support.
Values 1–2 are never offered; proposal/answer attention shares three UTC-day
slots. User-authored facts (`direct_user_statement`, `explicit_remember`,
`onboarding`) require explicit Review acceptance even when both verifiers agree.

Automatic kinds are `spelling`, `title`, `overview`, `vocabulary`,
`merge_memories`, `retire_memory`, `supersede_memory`, `dismiss_person`,
`merge_people`, `merge_tasks`, `retire_task`, `merge_conversations`, and
`set_language`. `memory`, `entity_summary` and `close_task` stay Review-only for
autonomous sessions. No cleanup kind hard-deletes a captured source.

Memory lifecycle edits retain canonical status/history, source and account
generation fences, head/item/graph/outbox transactions, and encrypted Undo
receipts. Supersede replacements bind every cited conversation to their source
cohort, retain sensitivity labels and use evidenced effective dates. Background
tails use the reconciliation authority; explicit acceptance uses the agent
conclusion authority. Reversals keep semantic fields and stamp the reversal
commit so vector hydration matches its outbox.

Generated-task cleanup protects manual, edited, recurring and linked tasks.
Duplicate captures require completed, uncurated, overlapping records with
matching speech; apply hides the duplicate with a link while retaining audio and
source rows. Redo checks that a merge survivor is still current. People cleanup
protects manual/confirmed/pinned/voice identities. Language edits require bounded
tags and enough completed speech. Autonomous title/overview edits retain their
generated-field guards; explicit user authority can update populated fields.

Every applied change exposes kind, before/after or merged/retired items, actual
surrounding speech where available, and Undo. The mobile Review entry remains
available when only applied changes exist. Changes are owner-scoped; receipts
and visible text are encrypted at rest. Undo checks newer edits and dependencies,
keeps the 30-day window and preserves semantic suppression.

## Captured speech and projections

Captured `transcript_segments` are never rewritten by a new correction. An
owner-scoped encrypted `transcript_corrections/<conversation_id>` document holds
segment anchors, before/after, kind, source, change ID, creation time, dependencies
and undone state. New writes mirror the encrypted overlay inline on the conversation, avoiding a per-row read on lists. Product reads render original speech plus active corrections. Read/decode/anchor failures increment `agent_overlay_read_failures_total` and render captured speech; transactional writers remain strict. The 500-entry limit applies to autonomous entries, leaving owner edits separate headroom.
Segment APIs expose `original_text` alongside the corrected `text`; old clients
continue displaying `text`. Read tools, MCP/dev APIs, summaries, reprocessing and
index readers use the same projection. Storage encoding removes in-memory
projections. Manual segment edits use the same journaled overlay, including
legacy virtual segment IDs, without adding IDs to the captured array.

Correction commits invalidate stale summary source refs and client-processing
projections atomically. New client output binds its existing v5 speech digest to
the projected transcript in a transaction that reads the overlay. Undo marks
entries inactive; dependent later corrections cannot be reversed underneath
their input. Old in-place Dream receipts retain their existing reversal path;
no historical rows or receipts are silently migrated.
Alternative-provider diagnostic segments are separate records with an identity
projection and `original_text`; primary-capture overlay anchors do not rewrite
those alternative recognizer outputs.

New receipts fence only their captured anchors, so unrelated speech appended to
the capture does not block Undo. Capture writers preserve corrected anchors;
speaker-only final-pass promotion preserves those same IDs, text and clocks. Explicit manual merges transactionally relocate overlay anchors and Undo receipts after processing; once receipts move, recovery retains the destination. Ingest append checks only the existing corrected anchors. Dream duplicate cleanup retains both captures with a reversible link.
Apply and Undo rebuild transcript chunk vectors from the projection as well as syncing the conversation index. Deleting a conversation also purges its sibling correction document.

## Admission, fairness and budgets

`DREAM_AGENT_ENABLED` and the operator document `dream_control/global.enabled` jointly control the global kill switch (10-second last-known cache; async callers refresh in the DB executor; deny until the first successful read): false prevents admission,
dispatch and effects, including late executor completions. Code defaults false;
the prod overlay ships true with `DREAM_AGENT_ELIGIBILITY=all`. Eligibility also
supports `paid` and `allowlist`; invalid settings deny admission. Release-channel
metadata is informational and cannot exclude Store users.

An hourly sweep drains a durable `dream_due` queue ordered by due time, which
combines backlog and staleness. Product writes enqueue immediately. Independent
discovery scans 20 pages of 499 owners (9,980/hour), committing each page in
100-owner transactions so a fully eligible page stays inside the 3 s RPC
deadlines, without overwriting dirty work or waiting for model sessions. Each
chunk reads every owner's queue row (both the no-clobber skip and the stale-row
delete need it) but reads `dream_users` state only for eligible owners not
already queued — no state read at all when none qualify, so a steady-state sweep
that mostly re-finds queued owners costs about two reads per scanned owner
instead of three. A
discovery failure (for example a Firestore `DeadlineExceeded`) or its 120 s
wall budget only degrades that sweep to the already-due queue — one payload-free
warning plus a `record_fallback` — and never fails the sweep; the cursor
advances only with a page's final chunk, so failed or budget-stopped pages
re-scan from their start (chunk commits are idempotent under that replay).
Future hunts remain queued (24 hours, six for heavy owners); daily-capped owners
are deferred rather than blocking the queue head. Each drain admits up to 5,000
owners with concurrency derived from reserved TPM and expected tokens (334 at
defaults, configurable, bounded at 512). Minute capacity uses 64 independent
`dream_scheduler/headroom-N` documents whose integer quotas sum to the TPM ceiling.
Each owner/run starts at a hashed shard and claims further shards only as needed,
so large turns can span quotas. Settlement touches only its held shards and
refunds unused tokens; late settlement cannot refund a newer minute's counters.
Stale leases reclaim after 1740 seconds with unknown charges retained.

| Owner bucket | Size | Turns | Tools | Read bytes | Token ceiling |
| --- | --- | --- | --- | --- | --- |
| Empty/light | 0–19 | 64 | 128 | 64,000 | 96,000 |
| Medium | 20–79 | 64 | 192 | 192,000 | 160,000 |
| Heavy | 80+ | 64 | 256 | 512,000 | 256,000 |

Each read call is capped at 64,000 bytes; edits cap at 25, questions at three.
Session ceilings also obey `DREAM_AGENT_TOKENS_PER_PASS` and
`DREAM_AGENT_EDITS_PER_PASS`. Default admission caps are two passes and three
manual runs per UTC day, $10 per owner/day, $15,000 globally/day, and configured
reserved headroom of 2,000,000 tokens/minute. The conservative USD ceiling uses
`DREAM_AGENT_MAX_USD_PER_TOKEN` (default 0.00001); it is a reservation upper
bound, not a provider price quote. Admission holds the expected 12,000 tokens ($0.12), not the session ceiling. Per-turn reservation atomically tops up both owner and a fixed hash shard before dispatch; 64 disjoint shard quotas sum to the global cap. Turns settle observed usage as they occur;
unknown or failed attempts retain their conservative charge. Search debits only the hit payload returned to the model. Hydration for that snippet is bounded and is not charged; `read` debits the full record. A hit payload that does not fit is reported in `skipped_refs`, marked truncated, and left uncharged while scanning continues. Missing or non-visible rows are reported as unavailable and do not fail the rest of the page. A transient hydration failure degrades that path and the search is incomplete. Reported refs can be read individually under the normal read limits. Lexical next-page cursors are published only after visiting the whole page; an unvisited tail is also exposed in `skipped_refs` if the result slots fill first. Fixed search-control metadata is outside that data budget. Embedding work is bounded and included in accounting. Turns are a loose backstop; token/USD accounting controls spend. Never clear an unknown lease merely
because its HTTP caller timed out.

Pass 1620s < drain 1680s < HTTP 1710s < Scheduler 1740s. Reasoning turns have a
480s ceiling; verifier calls have 120s. Budget exhaustion ends planning gracefully.

Burst reservation 429s pause the pending call inside its existing session. History,
tool results and staged proposals remain in memory; the retry does not acquire a
new owner pass. Each call has at most five capacity retries. Capacity rechecks use
exponential equal jitter (5–10s initially, capped at 15–30s), at most six checks per
wait, and require 20s of pass headroom. The planner/verifier's own timeout and the
outer pass deadline still cancel waits. Every attempt rechecks the kill switch,
owner lease and capacity policy, then reserves minute/daily headroom again.
Known-zero rejections release their minute hold; billed or unknown usage remains
charged before retry. Exhausted waits return the existing capacity-wait outcome.
The 3.8 local and shared saturation cooldown is 10s; new-admission worker parking
uses the same interval instead of 60s. Legacy 2.5 retains 120s.
No retry changes the reserved-only route or enables on-demand/shared spillover.

## Gateway and cache

Reasoning uses `omi:auto:dream-reasoning`; verification uses
`omi:auto:dream-verify`. Tool declarations, nested schemas, assistant tool calls
and tool results pass through the gateway's Vertex translation and accounting.
Gemini routes are reserved capacity only, with no shared/pay-as-you-go Gemini
fallback. The configured non-Gemini fallback policy is preserved.

The synthetic 3.8 reservation probe uses the same reserved verifier route with
service auth and no owner identity, rather than the backend's Vertex ADC. The
gateway publishes strict completed PT evidence to shared Redis; HTTP success
alone cannot create evidence. Auth and transport failures are inconclusive and
do not create a failed-probe admission veto. Fresh shared evidence, readable
headroom and shared concurrency slots remain required. Legacy 2.5 discovery
keeps its direct dedicated probe.

Quiet-hour admission targets stale 3.8 evidence even while its day-long routing
state remains ACTIVE. Generic discovery does not claim against evidence fresh
within 900 seconds. A targeted waiter records bounded priority in the same Redis
transaction, so generic discovery cannot renew a non-teaching lease ahead of it.
The existing 600-second lease is never stolen or cleared on failure. Priority
expires 630 seconds after the last targeted check if the waiter goes away.
The drain rechecks 22 times at 30-second intervals (660 seconds): a full remaining
lease, the 30-second probe deadline, and a final read. The global kill switch is
checked again after each sleep. These waits share the 1680-second drain deadline;
they do not extend it or an owner's pass deadline.

Reservation scope is `vertex-reservations:v1:<project>:<address-digest>`.
`OMI_VERTEX_RESERVATION_PROJECT` overrides `GOOGLE_CLOUD_PROJECT` for the key;
the digest covers every declared model, order and resolved location (including
`OMI_VERTEX_PT_TARGET_LOCATION`). Gateway and backend must use the same Redis
host/port, project and digest. Gateway inference still uses its own compute
project, with the Dream route pinned to 3.8 in `us`. A completed dedicated
response with `usageMetadata.trafficType=PROVISIONED_THROUGHPUT` updates
`evidence[gemini-3.8-flash].success_at` using Redis TIME. Missing/contradictory PT
metadata, unfinished responses and plain HTTP 200 do not update it. No admission
override or local success substitutes for that strict shared read.

Rebuild and release every reservation writer (backend, desktop-backend and
llm-gateway) from this source before assessing fleet fairness. Older reducers
discard the new targeted-priority field when rewriting the shared document;
the existing per-model lease still prevents duplicate probes during rollout.

After deploy, in a quiet-hour sweep expect the following payload-free messages
(timestamps and scope vary):

```text
vertex_reservation_probe_claim model=gemini-3.8-flash scope=<key> decision=claimed lease_until=<epoch> success_at=<old-epoch> source=admission
vertex_reservation_probe_start model=gemini-3.8-flash scope=<key> location=us
vertex_reservation_evidence model=gemini-3.8-flash scope=<same-key> storage=redis outcome=dedicated_success success_at=<new-epoch>
dream_capacity_probe source=gateway model=gemini-3.8-flash status=200
dream_capacity_probe outcome=inconclusive model=gemini-3.8-flash
vertex_reservation_probe_complete model=gemini-3.8-flash scope=<key> outcome=inconclusive
```

With `DREAM_GATEWAY_PROBE_ENABLED=false` none of the probe lines appear (admission
does not claim), and the only signal is `dream_capacity_decision reason=no_states`;
check that switch before suspecting a missing writer.

A pass that starts late in a sweep receives only the drain's remaining budget
(minus `FINISH_MARGIN_SECONDS`), so it ends through its own deadline rather than
being cancelled; below `MIN_PASS_SECONDS` the owner stays due for the next sweep.

The evidence line is on the gateway; the caller intentionally remains
`inconclusive` because it does not infer PT from HTTP success. The next check
must emit `dream_capacity_decision` with `decision=admit`,
`reason=fresh_reservation_saturation_clear`, `source=evidence`. An outstanding
lease first emits `decision=leased`, then one `decision=claimed` after expiry;
other replicas must not claim again in that 600-second window. A scope/override
change before execution emits `vertex_reservation_probe_skip`; unexpected probe
errors emit only their exception class. A shared-store failure emits
`vertex_reservation_store_unavailable` and cannot claim a probe.

The configured production backend/gateway scopes agree in source. An eight-hour
absence of the old probe log alone cannot identify the production lease holder,
prove a scope mismatch, or distinguish a skipped/cancelled task from missing
shared publication. Confirm the claim/start/publication sequence and matching
scopes after deploy before calling this incident resolved.

The stable contract, instructions, tool schemas and seed prefix are repeated
unchanged across turns for Vertex implicit caching on provisioned throughput.
No explicit cache resource is needed for this route. Hits come from reported
`cachedContentTokenCount`; absent usage is tracked separately, never fabricated
as a hit. Thought, cached/uncached input and multiple provider attempts participate
in token accounting without changing another lane's fallback behavior.

## Retired jobs and preserved work

The canonical semantic consolidation planner, candidate retrieval, semantic
retries/quarantine, dreaming state/cooldown and overflow orchestration are removed.
The maintenance-host Dream drain is removed. Consolidation tuning reads,
`MEMORY_CANONICAL_CONSOLIDATION_ENABLED` and
`MEMORY_CANONICAL_MAINTENANCE_FLEX` bindings/registry entries are removed.

The mixed maintenance host remains for TTL, explicit required intake and committed
outboxes/recurrence delivery. DB claim/settlement and model normalization borrow
separate executor steps; outbox ticks do not hold a worker across a whole drain.
Ledger accounts retain daily-sweep lifecycle authority and still drain outboxes.
The daily sweep retains new-fact formation, local-day/onboarding receipts, standing
triggers, summaries and filing. Stranded finalization, ingest-time prevention,
speaker teaching, task refresh, frame retention, X ingestion and compliance stay
with their owning pipelines. No Scheduler entry or `.github` workflow becomes
dead; the dev maintenance schedule still owns required work. Workflow files are
not edited. See [cleanup inventory](dream-cleanup-fold.md).

## Operations and evidence

Internal OIDC routes are `POST /v2/dream-agent/sweep` and
`POST /v2/dream-agent/canary`. Owner-authenticated routes are
`GET /v1/dream/runs` and `POST /v1/dream/runs`; they never accept another UID.
Count metrics cover outcomes, size buckets, turns, tools, rejection reasons,
successful resubmits, verifier outcomes, applied/undone kinds, cache usage and
stale reclaim. Metric labels never contain owner IDs, refs or content.

The canary stages a fixed synthetic correction through real tools, calls the
reserved verifier lane, and checks admission, execution, journal, Undo and report.
Its marked synthetic owner is required; semantic agreement or an empty model
choice cannot decide pipeline health. Canary data is separate from real owners.
Before reseeding, it clears only its fixed fixture receipts after proving the
synthetic owner marker; a failed Undo cannot poison the next probe.

The deterministic offline replay uses scripted turns and synthetic records for
hunting, guards, resubmission, verification, apply/Undo, budgets and kill behavior.
Replay token/cost reports are fixture accounting with configured upper bounds;
they do not establish actual provider billing, model precision or deployment.
Run unit/SDK evidence through `backend/test.sh` and documented loopback emulators.

The operator-only `backend/scripts/dream-replay.py --uid <authorized-owner>`
runs a real dry session in an isolated pod and prints counts/proposals to operator
stdout. It writes no admission, budget ledger, Review, notes or reports in product
storage; gateway provider accounting still applies. Agents must not run it on a
real UID or call the production account API. No real content belongs in fixtures,
shared logs or PR text.

Rollback is the kill switch plus the previous image. Keep correction overlays
and receipts intact; an older image may lack their display projection. Do not
rewrite captured speech or erase reservations to simulate rollback. A kill switch
is operational containment; changing source alone is not deployed recovery.


## Dream cohort read failures

Unreadable Dream membership is distinct from revocation. Declared `all` and
paid percentage/entitlement admission continue without an allowlist override;
unknown membership never grants on-demand authority. Allowlist-only admission
waits and retains the due row on an unavailable membership read. Empty discovery
and read failures emit `event=dream_cohort_health` and shared fallback metrics.
Do not change `allowlist` to `all` as an outage workaround.


## Memory intake is independent of Dream cleanup

Ordinary compatibility-mode observations receive a bounded canonical intake
route after extraction commits, for free and paid owners alike. The maintenance
worker rotates through pending observations to retry failures, including rows
past their former TTL. Explicit submissions retain their required-processing
receipt path. Ledger-mode accounts retain the daily sweep as their formation
owner. Intake uses the existing memory L2 gateway lane (Flex on maintenance),
not the Dream reasoning/capacity/paid-cohort budget.
`MEMORY_OBSERVATION_INTAKE_ENABLED` defaults on; false stops both observation
entrypoints before DB/model work, leaving capture and required intake intact. Dream still owns verified
retrospective cleanup. A promotion admission receipt binds the canonical
content, evidence and graph plan; it is not a Dream session receipt.

`MEMORY_UNDECIDED_VISIBLE` defaults on. Undecided and Review observations remain
Short-term and TTL maintenance cannot reject them for age alone. Historical
active Review archives project as Short-term in default lists without rewriting
their audit records. Explicit owner rejection, source/privacy tombstones,
processing blocks, sensitivity policy and third-party grants still apply. Set
it to `false` to restore TTL handling and archive routing for new Review outcomes;
expired active Short-term reads remain visible pending TTL adjudication.
See [memory decision recovery](memory-decision-recovery.md) for incident evidence,
backfill bounds and post-deployment verification.
