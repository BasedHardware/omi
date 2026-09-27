# Omi Product Principles

Short north star for humans and agents. Read this before proposing features or
landing PRs that change product behavior. Engineering standards live in
[`AGENTS.md`](AGENTS.md). Locked product rules live in
[`product/invariants/`](product/invariants/).

## Principles

1. **Memory-first.** Protect the core loop:
   **Capture → Understand → Remember → Retrieve → Act**.
   If Omi fails to capture or preserve memory, nothing else matters.

2. **Trust over cleverness.** Prefer reliable capture, sync, and retrieval over
   flashy features. Silent data loss and dual sources of truth are product bugs.

3. **One product mind.** Surfaces are input/output against one shared product
   experience — not separate products with their own histories.

4. **Harness over heuristics.** Where we integrate with surfaces we do not own,
   invest in durable harnesses and contracts, not brittle one-off automation.

5. **Taste floor.** Stay on-brand. Prefer deleting dual paths over
   feature-flagging them forever.

## Proposed universal memory lifecycle

The enforceable design note is
[`INV-MEM-4`](product/invariants/memory-promotion-authority.md), together
with the universal-authority rule in
[`INV-MEM-5`](product/invariants/universal-memory-task-authority.md). Both
remain `proposed` for the required seven-day unchanged period.

All new memory intake starts as broad Short-term capture. Maintenance gives
each pending item exactly one consolidation route: promote, archive, review, or
reject. Promotion is the only route into Long-term, and it is admitted only
when one atomic ledger transaction records the server-authored promotion
receipt and the memory's structured graph assertion. There is no direct,
generic, or fast-track promotion path.

Default retrieval includes eligible Short-term and Long-term memory, collapsed
by canonical lineage so one logical memory appears once. Search/vector and
compatibility projections are derived views: their updates are committed to
the outbox with canonical state and retried from authoritative memory, never
treated as memory authority themselves.

This lifecycle is the product behavior for every authenticated account. A UID
allowlist, dogfood cohort, store origin, client, or rollout document must not
select a different memory or task-intelligence system. Historical flat memory
documents remain readable through one read-only compatibility adapter so users
retain their existing data without a bulk backfill. They are not a second
mutation authority: all new intake and every mutation use canonical apply,
privacy, lineage, graph, and outbox rules. The complete convergence and removal
ledger lives in
[`backend/docs/epics/universal_memory_task_convergence.md`](backend/docs/epics/universal_memory_task_convergence.md).

## Mobile own-voice enrollment direction

Keep speech-profile enrollment in first-run onboarding. Offer four optional
sentence starters to reduce the effort of speaking, plus alternatives and Skip.
Personal-life answers are never enrollment requirements. Prompt completion,
audio activity, voice enrollment, and confirmed answer saving have separate
visible states. Users review and choose which transcribed statements to keep.
Next starts the following prompt automatically. The fourth answer is a qualitative
goal and is saved through the goal system, separately from personal memories.
Review uses one Save and finish action with automatic completion. Goal wording
is conservatively cleaned before review and can be edited or restored.
A successful upload, not navigation through All Done, is the enrollment outcome.
The [approach and verification plan](.github/agent-docs/mobile-voice-enrollment.md)
describes the capture, memory consent, and quality boundaries.

## Before you build

- Large or ambiguous features start as a GitHub issue
  ([Contribution guide](docs/doc/developer/Contribution.mdx)).
- Check the [invariant registry](product/invariants/) for locked rules that
  apply to your change.
- A product rule without a guard surface is taste advice, not a locked
  invariant.
- Keep a new or changed product rule as a proposed design note until its
  behavior and guard have remained unchanged for seven days; only then may it
  be locked.

## Maintainer operating rule

When declining a PR for direction or taste, either cite an existing invariant
by ID or open a `proposed` invariant in `product/invariants/` the same
week. Tribal “no” becomes written law.

## Proposed offline fragment policy

Without an existing explicit target, offline speech follows the same default
silence boundary as realtime: a speech gap of at least 120 seconds starts a new
conversation; shorter gaps stay connected.
Speaker enrollment and own-voice attribution are not prerequisites. Short,
filler-only fragments stay out of the default conversation list and search,
without automatic summarization. Their original transcript and audio remain
recoverable through Show discarded; later meaningful content automatically
promotes the merged recording. Explicitly restored or curated recordings stay
visible. Duration alone never establishes irrelevance: brief meaningful speech
must remain available. Uncertain content stays kept. Long narration is not reliable
evidence of irrelevance, so it remains one retained recording rather than being
silently discarded. Implementation and limits: `backend/utils/sync/ARCHITECTURE.md`.

Silence-only audio creates nothing and cannot bridge conversations.
Without an existing explicit target, sync intake groups connected speech intervals
independently of arrival order within the same source/device/lock partition. Missing
client target IDs do not partition that intake. Unknown device identity is not a
wildcard. Late bridges retain redirects and fence stale enrichment. The shared
boundary predicate is used on both paths, but realtime currently observes callback
wall time while sync observes VAD/word ends. Realtime can configure its timeout per session; WALs do not
carry that setting, so sync uses the default. Shared, photo-bearing and user-curated
records remain separate from automatic bridges. This change neither uses own-voice
labels nor debounces LLM work.

The 2026-09-19 fragmentation mechanism was sync adopting empty live-flap stubs:
STT failures caused reconnects about every 35 seconds, and legacy lookup chose a
different stub per WAL. Cross-job assignment races are a separate, older class.
Timestamp hints never adopt live rows. A provenance-compatible, non-deleted explicit
target is honored and keeps its ID even when empty: fresh admission can verify
server capture proof before live STT produces words. Missing or tombstoned targets
use ordinary temporal assignment; retry-lineage deletion fences remain intact.
Appending chunks keeps the existing sync conversation ID; genuine bridges retain redirects.
Known limitation: different existing live target IDs can still split one continuous
recording. Sync cannot bridge live-owned targets while sockets may write to them.
Realtime reconnects with the same durable origin now reuse a compatible in-progress
continuation inside the window without rebinding a completed original. Expired empty
continuations are reaped through content/lock/revision fences on reconnect. Historical
distinct targets and anonymous cross-device discovery remain separate follow-ups.
