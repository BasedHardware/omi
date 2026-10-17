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
discovery scans 20 pages of 499 owners (9,980/hour), initializing missing rows
transactionally without overwriting dirty work or waiting for model sessions.
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

## Gateway and cache

Reasoning uses `omi:auto:dream-reasoning`; verification uses
`omi:auto:dream-verify`. Tool declarations, nested schemas, assistant tool calls
and tool results pass through the gateway's Vertex translation and accounting.
Gemini routes are reserved capacity only, with no shared/pay-as-you-go Gemini
fallback. The configured non-Gemini fallback policy is preserved.

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
