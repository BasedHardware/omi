# Episode context and notes review follow-up

Owner ruling 2026-11-15 replaces the earlier attribution restriction: every memory in the user's own account can inform that user's episode summary. Categories (including interesting), unknown/third-party attribution, unstamped legacy rows and canonical documents/triggers are background information, not admission filters. The composer reuses chat's shared `is_prompt_memory_visible` quality/paywall predicate, rather than its separate self-profile/slot predicate. Deleted/tombstoned, explicitly rejected and invalidated rows remain excluded. Locked means a paid-plan entitlement (`MemoryService.get` returns402); chat withholds locked rows and the composer does too. Account scoping, authoritative hydration, deletion/suppression and cross-account rules remain unchanged.

Category, kind, subject, attribution and date accompany selected content. Missing metadata stays unknown; external wisdom is not asserted as a fact about the owner. Memories remain background and cannot establish episode events. Chat's policy is unchanged; this owner-summary background use is not a change to canonical ledger admission or profile-slot authority.

Notes use prompt version notes-4 with a pinned source digest (including the scaling configuration). A deploy schedules zero regenerations: dedupe is consulted only inside an already requested processing attempt. Exact short and switch-off notes-3 checkpoints with identical routing/dependencies/inputs are accepted and restamped without an LLM call; only eligible scaled packets add a scaled-detail discriminator, so old long output is recomputed once when independently reprocessed.


One eight-second deadline bounds owner context, vector retrieval, hydration and rendering before the composer call. The measured owner composes took 8–43 seconds; eight extra seconds leave at least 39 seconds of the 90-second request budget at that observed upper end. This is a caller deadline, not a claim that SDK cancellation works: an in-flight SDK may drain after the caller returns. The existing optional-context executor has four workers and zero queue; slots remain occupied until the actual work exits, saturated callers omit memories immediately, late results are discarded, and every subsequent provider step checks remaining time. Failures and timeouts return only the original name and language, discarding partially loaded profile, goals, people and memories; they never fall back to a memory list. A successful empty vector search may use an owner-scoped list of at most 60 candidates. The shared `omi_fallback_total{component="conversation_notes",from_mode="episode_memories",to_mode="without_memories"}` metric counts `timeout`, `capacity_full`, `transport_error` and `provider_budget_exhausted` outcomes without account/content labels.

Owner ruling 2026-11-15 expands this operation to all account-owned tiers and both canonical and historical memory stores. Up to three deterministic queries cover the whole episode, named people/projects and recurring topics/commitments; each is capped at1,000 cl100k tokens. Results merge by memory identity and rank into the existing3,500-token memory block, alongside a1,000-token profile block. There is no planning-model turn and no result cache. Canonical authority must succeed before historical search; a canonical failure never admits legacy content. Canonical suppression still wins over any legacy duplicate.

The owner-summary option is explicit and internal to MemoryService; chat, default vector-only search, third-party access and canonical write/ledger-profile rules retain their prior behavior. Its vector filter spans the owner's tiers and sensitivity labels; authoritative hydration excludes deleted/tombstoned, superseded/invalidated, rejected and chat-locked memories. Categories, kind, subject, attribution and date inform the prompt instead of narrowing account background. Ordinary default Archive policy is unchanged; INV-MEM-1 documents this owner-summary exception.

The owner profile always starts with name/language. Successful optional gathering additionally supplies timezone, stored ai_user_profile.profile_text, up to five active goals, and up to20 transcript-bound people with name/relationship/description. Any timeout, provider failure or read exhaustion discards every optional result and retains name/language only. One8-second deadline covers all queries/providers and rendering. SDK work that ignores a timeout keeps its bounded executor slot; it cannot publish late context or start a subsequent budgeted step after the deadline.

## Cost and tool feasibility, owner ruling 2026-11-15

The managed episode_composer lane is gpt-6-luna but gateway config_loader.py permits tools only for chat_agent/memory_l2/conv_structure; the composer lane currently rejects tools. This change therefore uses bounded multi-query retrieval and leaves an audited read-only chat-registry tool mount as the immediate follow-up. No gateway policy change or unbounded tool loop ships here.

At most3 logical searches,10 results/search and a shared640-document budget replace the prior1+1+160 design. Both canonical and historical vectors are required to cover both physical memory generations: at most6 embeddings+6 Pinecone queries+0 Typesense queries per compose, each optional search with one whole-operation attempt. Every embedding call matches the real text-only production proxy; deadline checks precede vector RPCs, and hydration/suppression reads share the same absolute deadline. At27,000 composes/day, the logical maxima are162,000 embeddings and162,000 vector queries. These are bounded maxima, not measured usage; empty/deduplicated queries can cost less. Existing SDK-internal retries and provider owner-routing/control reads are additional.

The repository rate card prices Luna input at$0.10/M tokens and output at$0.60/M. Unchanged maximum context input4,500 tokens costs$0.00045/compose or$12.15/day. Each extra1,000 generated tokens adds$0.00060/compose or$16.20/day if every compose grows equally. The repo does not supply retrieval unit prices. Using the previously documented vendor-list scenarios ([OpenAI embeddings](https://developers.openai.com/api/docs/models/text-embedding-3-large) $0.13/M tokens, [regional Firestore](https://cloud.google.com/firestore/pricing) $0.03/100k reads, [Pinecone](https://www.pinecone.io/pinecone-answers/) $16/M RU): six1,000-token embeddings cost$0.00078/compose;640 context reads plus conservatively six routing reads cost$0.0001938; six1-RU queries cost$0.000096. Total retrieval is$0.0010698/compose or$28.8846/day at1RU/query, compared with the old$0.0001943/$5.2461. At10RU/query retrieval is$0.0019338/compose or$52.2126/day. Full maximum context adds$12.15/day to either. Actual namespace RU, contract/region, caching, control reads and retries are unmeasured; this is not an invoice or production spend cap. Caller-added context latency remains bounded by8 seconds; retrieval success/recall under that deadline has not been live-benchmarked.

A real three-search tool loop would have the same retrieval maxima plus model turns. If it resent the supplied21k-token baseline three extra times, uncached input alone adds$0.0063/compose, before tool-result/output tokens; caching and shorter follow-up packets could lower this. It requires gateway tool capability, a hard model/lease deadline and a bounded runner, and is not implemented tonight.

Analysis-only follow-up: reuse an allowlisted subset of the existing chat tool registry, bound to configurable.user_id outside model arguments. Memory/conversation/graph and stored calendar/action/screen reads are candidates; writes, send/share/device actions and interactive authorization flows stay excluded from a background job. Suggested bound:3 tool calls,4k combined result tokens, one deadline. Cheap deterministic candidates are overlapping stored meeting title/attendees (<=5 reads,200–600 tokens), resolved people (already<=20 reads,200–1,200 tokens), and1–2 earlier episodes with the same people (bounded recent-page lookup, roughly20 metadata+2 body reads,500–1,500 tokens; index availability unverified). None of those new context sources is implemented in this change.


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

Active transcript waits also persist all pending blocker IDs. Home already
holds a bounded per-member timestamp map, so it checks only those blockers;
unrelated ready-member receipts neither clear the wait nor schedule another
attempt. Membership/visibility changes and explicit regeneration requests
still bypass suppression. Existing waits without blocker IDs retain the
compatible episode-wide timestamp check until they are re-evaluated. This
adds zero database reads to the Home wait check.

### Final provider-boundary review (2026-11-15)

Owner-summary retrieval alone uses cancellable single-attempt clients. Installed/locked versions: Pinecone 7.3.0, aiohttp-retry 2.9.1, OpenAI 2.38.0, langchain-openai 1.1.14, HTTPX 0.28.0. Pinecone's dedicated IndexAsyncio receives a copied configuration and a private JitterRetry(attempts=1) option before any request; redirects are disabled on that private transport. It reuses the configured host, without a controller/discovery request. Pinecone 7.3.0 ignores `_request_timeout` on its async transport, so asyncio.timeout bounds the complete async query, including response-body reads. Shared REST clients keep their existing retry policy.

Direct summary embeddings bypass LangChain's retry/chunking layer: a fresh AsyncOpenAI uses max_retries=0 and timeout=remaining, with AsyncHTTPTransport(retries=0). The already token-bounded query is one input/request. The gateway path uses an isolated no-retry HTTPX client, one input batch and no BYOK/default-key/route-absent fallback; the existing gateway embedding lane pins max_attempts=1. Both paths run inside the remaining absolute context deadline. Other callers retain existing clients, retries and fallbacks.

True maxima are six embedding provider attempts and six Pinecone attempts per compose, with no SDK or whole-operation retries. Gateway routing additionally has up to six backend-to-gateway HTTP hops. Caller latency remains eight seconds; in-flight provider coroutines are cancelled at that deadline and closed before their summary worker returns. There is no retry tail. Cancellation/transport teardown is cooperative, so this is not an OS-level hard real-time guarantee for a stalled resolver/kernel; no unbounded retry loop holds the worker. Real HTTP/SDK failure and stalled-request tests prove one outbound attempt and no active request after return, before deadline plus one per-request timeout. Cost scenarios above now refer to actual provider attempts, rather than logical calls that could hide SDK retries.

Finalized member notes have a separate content watermark, excluding title/emoji/category and transcript bookkeeping. A finalization event whose notes differ from the last composed watermark persists the existing regeneration invalidation; duplicate events do not pay again. A notes-only refresh bypasses a new speech quiet window; an already pending speech window retains its original timing. For fixed membership and speech, N members each finalizing once after the initial compose can require at most N+1 successful episode composes; if all notes finish first, one. Existing parse repairs/failure retry bounds are unchanged. Proven capture-end processing (#25309) narrows the race but cannot eliminate it, so it does not replace the watermark. Existing episodes without the new watermark are not proactively invalidated, and deploying schedules no fleet recompose. No new jobstore read was added.

The optional async SDK is materialized through Pinecone.IndexAsyncio only when a summary query runs. Ordinary vector imports therefore require no asyncio extras in the GPU worker or hermetic read/export environments. The private retry object is replaced with its real pinned class constructed with attempts=1 before any request; no provider HTTP operation occurs during this setup.

Summary embeddings live in a separate helper, leaving llm/clients.py byte-identical to main. That file participates in the existing notes/L1 routing digest, so this separation preserves historical checkpoints and kill-switch parity without accepting a new routing identity.
