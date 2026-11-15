# Episode context and notes review follow-up

The composer layers a stricter filter over chat's shared eligibility predicate: explicit unknown/third-party subjects and non-fact kinds are excluded, including legacy rows. Legacy rows require all three explicit stamps: fact kind, primary_user scope and user attribution. Missing stamps, legacy_assumed attribution and categories such as interesting or manually_added establish no owner attribution and are rejected. Loader tests exercise mixed canonical and legacy rows through both list and vector paths, and recheck untrusted search adapter results.

Chat still admits visible noncanonical legacy rows without checking their kind or subject at `backend/models/knowledge_ledger_policy.py:121`; its legacy prompt renderer consumes them at `backend/utils/llms/memory.py:74`. This change leaves that chat behavior untouched so the chat owner can assess and address the gap separately.

Notes use prompt version notes-4 with a pinned source digest (including the scaling configuration). A deploy schedules zero regenerations: dedupe is consulted only inside an already requested processing attempt. Exact short and switch-off notes-3 checkpoints with identical routing/dependencies/inputs are accepted and restamped without an LLM call; only eligible scaled packets add a scaled-detail discriminator, so old long output is recomputed once when independently reprocessed.


One eight-second deadline bounds owner context, vector retrieval, hydration and rendering before the composer call. The measured owner composes took 8–43 seconds; eight extra seconds leave at least 39 seconds of the 90-second request budget at that observed upper end. This is a caller deadline, not a claim that SDK cancellation works: an in-flight SDK may drain after the caller returns. The existing optional-context executor has four workers and zero queue; slots remain occupied until the actual work exits, saturated callers omit memories immediately, late results are discarded, and every subsequent provider step checks remaining time. Failures and timeouts return only the original name and language, discarding partially loaded profile, goals, people and memories; they never fall back to a memory list. A successful empty vector search may use an owner-scoped list of at most 60 candidates. The shared `omi_fallback_total{component="conversation_notes",from_mode="episode_memories",to_mode="without_memories"}` metric counts `timeout`, `capacity_full`, `transport_error` and `provider_budget_exhausted` outcomes without account/content labels.

The composer opts into canonical vector search only. This removes the second historical embedding/vector search (redundant after authoritative canonical hydration) and Typesense keyword search; chat retains its default hybrid and historical behavior. Every candidate is hydrated and checked by both the shared eligibility predicate and the stricter composer filter. The query is capped at 1,000 cl100k tokens; profile and memory blocks total at most 4,500 output-prompt tokens. No result cache can retain revoked/private memory context.

## Cost model, 2026-11-15 UTC

At the supplied 27,000 composes/day baseline, logical retrieval calls decrease from up to 54,000 embeddings + 54,000 Pinecone queries + 27,000 Typesense queries/day to at most 27,000 embeddings + 27,000 Pinecone queries + zero Typesense queries/day. The optional composer search uses one whole-operation attempt, so a typed transient failure cannot repeat embedding and vector retrieval. Circuit/admission checks remain active, chat retains its existing retry policy, and provider-internal retries remain separate from this logical-call count. The context data budget is 160 document reads, including profile (1), at most five active goals, at most 20 transcript-bound people, authoritative candidate/lineage hydration, and any healthy-empty list intake. Empty queries and missing documents count too. Existing Pinecone owner routing adds one document read in steady state (161 context-plus-route reads maximum in the modeled successful path, 4.347 million/day); first-seen routing can instead do two reads and one registration write. Existing BYOK/quota/control reads and Firestore index-entry billing are outside this document-read model; actual production usage was not measured.

`backend/config/rate_card_v1.json` prices composer Luna input at $0.10/million tokens and output at $0.60/million. Thus the full 4,500-token context costs at most $0.00045/compose, $12.15/day of uncached composer input. Each additional 1,000 generated tokens costs $0.00060/compose, $16.20/day if every compose adds that many; the fleet's long-episode fraction/output delta has not been measured. Short notes keep their packet and cached prefix unchanged, and deploy creates no regeneration jobs.

The repository rate cards do **not** provide per-operation embedding, Pinecone, Typesense or Firestore prices. The following are explicitly vendor-list-price scenarios rather than invented repository rates or a measured invoice:

- [OpenAI text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large) lists $0.13/million tokens: the capped query is $0.00013/compose or $3.51/day before SDK retries.
- [Firestore Standard pricing](https://cloud.google.com/firestore/pricing) lists $0.03/100,000 document reads for us-central1: the 161-read model is $0.0000483/compose, $1.3041/day, before index entries/control reads/retries. Use the actual database region and contract to price production.
- [Pinecone's list pricing](https://www.pinecone.io/pinecone-answers/) starts at $16/million read units. [Query cost depends on namespace size](https://docs.pinecone.io/guides/cost/understand-cost), with a minimum 0.25 RU; lowering top_k is not a read-unit ceiling. At price P dollars/million RU and r RU/query, daily vector spend is 0.027*P*r: at P=16, 1 RU/query is $0.432/day, 10 RU is $4.32/day, and 100 RU is $43.20/day. Actual namespace RU and contract price are unmeasured.

At 1 RU/query and regional Firestore list pricing the modeled retrieval increment is $5.2461/day ($0.0001943/compose), or $17.3961/day ($0.0006443/compose) including maximum composer context input, before extra summary output, SDK retries, control reads and any additional fixed infrastructure. At 10 RU/query those figures become $9.1341/day and $21.2841/day. These are scenario estimates, not a hard production spend cap. The context kill switch disables this retrieval increment; the detail switch independently controls longer output. A production acceptance pass must measure RU/query and compare the shared fallback rate, latency and vendor usage before treating this estimate as an actual cost change.

The new People projection was audited as read-only: one owner-scoped batch of at most 20 transcript-bound IDs, selecting only name, relationship, description and dismissal state. It performs no People writes, learning projection, generation mutation or shared-cache change; its reviewed body is pinned in the People inventory and a test rejects write/transaction calls. The bounded active-goals builder also has a real Firestore query driver; its single-field predicate requires no additional index.

## Integration with capture ledger and tunable notes hold

Main `7f944b6d38059` includes the lifecycle ledger writers from #25304. Scaled
conversation notes retain the existing lifecycle persistence owner:
`persist_processed_conversation` calls `persist_processing_result_with_lifecycle`,
which records `noted` and `done` in one fenced ledger write after the actual
summary commit. Overview and section-only long notes both exercise this path.
Episode composition writes the separate `episodes` collection; it is not a
capture summary receipt and must not create a capture ledger row for an episode
ID or claim that a member's individual notes have completed.

A committed transcript receipt starts the episode's existing settle window
immediately, independently of the member-notes quiet window. Both windows run
from the same content arrival; the configurable notes hold does not defer the
receipt or start a second episode window when member notes finish. Regression
tests use 120, 300 and 600 second notes holds and both completion orders. They
verify one paid episode call, no restarted episode deadline, and no paid replay
when the member notes finish or their completion is retried. Deploy changes
neither hold's default and schedules no notes regeneration.

## Projection hot path and review evidence

The projector now publishes a bounded, coalescing process-local receipt marker through a stdlib-only module, without importing the composer, memory, vector or LLM stack and without doing database IO. The composer poller drains those markers in its existing worker pool and re-reads the committed member before scheduling. Assignment metadata and Home recovery remain the durable restart/overflow recovery path. Import-graph and fresh-process tests enforce the producer boundary. Active transcript waits retain their membership signature; membership, visibility and explicit regeneration invalidations bypass wait suppression immediately. An unchanged wait still adds zero composer reads to a Home request.

The production embedding proxy accepts text only. Budgeted retrieval calls that real signature, checks the deadline after embedding and before vector IO, and uses autospec tests against the production embedding proxy, owner index and Firestore profile/people/hydration interfaces. The earlier paid replay injected selected memories from the private snapshot directly into assembled prompts; it contained memory context but bypassed this production embedding/vector path and did not validate its availability. No new paid replay was run after the gateway token was removed.

## Durable batch transcript recovery

Batch intake marks its existing assignment transaction to stamp
`episode_transcript_updated_at` in the same conversation write as newly accepted
speech, including append and rollover outputs. Exact retries do not advance the
marker. Live capture replacement retains its existing transactional stamp. The
process-local queue is only a fast path: neither a crash before enqueue nor a
crash after dequeue can remove the committed revision signal. Projection adds
no transaction, document write, or heavy import.

Home list/page reconciliation reads that existing member metadata and queues a
closed episode whose transcript revision exceeds its covered revision. A
successful or evidence-identical compose acknowledges the revision in
`composed_transcript_updated_at`, with member-revision fencing. Fast-path and
read recovery share the existing evidence/fingerprint dedupe and paid-call
lease. Removed, moved and hidden members contribute no recovery signal; Home
clears its private aggregate marker rather than erasing the conversation's
historical revision timestamp or waking a former episode.

After process loss, recovery is triggered by the next Home list/page read that
includes the episode. There is no periodic durable episode-receipt sweep and
therefore no wall-clock bound without such a read. Closed episodes must be at
least 60 seconds old; each read admits at most the configured per-read cap,
then existing executor availability and the existing quiet/max-settle window
apply. Queue polling is a best-effort one-second fast path, not an end-to-end
latency guarantee. The six-hour transcript wait does not suppress a newer
blocking-member receipt on a qualifying read.
