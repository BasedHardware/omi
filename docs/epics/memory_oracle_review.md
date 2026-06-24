# memory Memory Product Integration — Oracle Review

> **Historical:** 'v17' was the internal codename for the canonical memory system; fully renamed to neutral vocabulary on 2026-06-24.

**Date:** 2026-06-18  
**Reviewer:** Oracle (`oracle` CLI, browser-backed `gemini-3.5-flash`; model-selection evidence reported by Oracle as unresolved/unverified, but a complete response was returned)  
**Inputs:**
- `docs/epics/memory_product_integration_epic.md`
- `docs/epics/memory_implementation_tickets.md`
- `docs/epics/memory_product_integration_decision_brief.md`
- memory contract/patch code excerpts from `backend/models/v17_memory_contracts.py` and `backend/utils/llm/durable_memory_patches.py`
- memory unit test excerpts

---

## 1. Verdict: **BLOCKED**

The product direction is sound, and the ticket set is unusually strong on migration accounting, deletion gating, whitelist rollout, ledger-first Long-term writes, and anti-reward-hacking evaluation. However, it is **not yet safe to use these tickets as the executable implementation plan**.

The blockers are not cosmetic. The plan does not fully specify the atomic Long-term write protocol, rollback behavior, canonical tier/lifecycle model, source-deletion races, or projection consistency. The current patch code also has paths that silently turn failures or rejected outputs into an empty result. Those gaps could cause duplicate memories, lost memories, resurrection after deletion, privacy leaks, or misleading benchmark gains.

T00–T05 may proceed as design/audit work, but no persistent memory writes, read switch, vector changes, or external API changes should ship until the P0 changes below are incorporated. This review is based on the attached Epic, tickets, decision brief, and supplied code/test excerpts; I did not have the full repository or execute its test suite.    

## 2. Top risks, ordered by severity

### 1. P0 — The Long-term “exactly once” protocol can both lose and duplicate writes

T13, T14, and T15 separately introduce an idempotency claim, a per-user lease, and a ledger append, but they do not define one atomic transaction or recovery protocol spanning those pieces.

Failure cases currently left unspecified include:

* Process dies after setting the patch application to `claimed` but before appending the ledger commit.
* Ledger commit succeeds but patch application remains `claimed`.
* A lease expires while the old worker is still running, and both the stale and new writer attempt a commit.
* A head conflict causes replanning and produces a new idempotency key for the same logical operation.
* Source deletion or account purge occurs after synthesis but before application.

The current ID code makes this worse: the generated idempotency payload includes the observed head and the patch’s array index. A changed head or output ordering therefore changes the idempotency key even when the logical mutation is the same. It also accepts a nonempty `patch.idempotency_key` supplied by the model instead of always computing it from trusted server state.  

A lease without a monotonic fencing token is advisory, not a correctness guarantee.

### 2. P0 — The current synthesizer silently drops failures and rejected candidates

The current implementation returns an empty list when:

* The LLM client is unavailable.
* Invocation fails.
* Parsing or validation fails.
* Any other exception occurs.
* A candidate looks like a quote-wrapper card.

The broad `except (ValidationError, Exception)` is effectively `except Exception`, and `_valid_non_quote_wrapper_patches` simply removes candidates without creating a reject/review outcome. If a worker interprets `[]` as “nothing useful” and advances its cursor, the memory is silently lost. The same omission could make benchmarks look cleaner by removing difficult candidates from the denominator. 

One malformed patch also appears capable of invalidating the whole parsed batch. The tests currently encode empty-output behavior for invalid merges and quote wrappers rather than requiring an auditable terminal outcome. 

### 3. P0 — The current source-backed contract contradicts the final product model

The final product rule is:

* Fresh source-backed memory is **Short-term** and default-access.
* Only older/processed historical context is **Archive** and explicit-query only.

The existing `L1MemoryArchiveItem` always describes an archive item, assigns `allowed_use="archive_search"` for general records, and labels it as archived evidence. It also has a helper explicitly named `filter_l1_archive_for_normal_search`. That is incompatible with using fresh L1 extraction as default-access Short-term memory.  

The new tickets introduce tier fields but do not explicitly replace or adapt the current L1 extractor output contract. Without that bridge, implementers could either hide fresh useful memories in Archive or accidentally include Archive in default retrieval.

### 4. P0 — Rollout and rollback semantics are underdefined

`MEMORY_MODE=off|shadow|write|read` is a single mutually exclusive value. It is not defined whether `read` includes memory writes, whether normal user writes continue during `read`, or how an account moves back to legacy reads after receiving memory-only edits, deletes, Short-term memories, or Long-term commits.

“Rollback to legacy read is one config change” is not sufficient. A config rollback could:

* Make memory-created memories disappear.
* Resurrect a memory deleted only in memory.
* Re-expose an older legacy value after a memory edit.
* Lose visibility of Short-term memories that were never projected into the legacy store.

The decision brief explicitly requires rollback for whitelisted users, but the tickets specify no data reconciliation or compatibility projection guarantee for rollback.  

### 5. P0 — Deletion and purge can race with imports, queued patches, and delayed workers

T06 covers many stores, but it does not define a user-level deletion generation or purge fence checked by every worker at commit time. A delayed backfill/MCP/manual-write job could recreate data after deletion or account purge.

Similarly, an L2 patch synthesized from valid evidence can become invalid if the source is deleted before application. T09 protects bulk source snapshots, but T15–T18 do not require an apply-time source-version and tombstone check.

The append-only ledger also needs an explicit erasure model. “Delete the projection” is materially different from deleting or cryptographically erasing plaintext content in commits, replay artifacts, review payloads, backups, and logs.

### 6. P1 — Projection and vector lag can expose Archive, sensitive, or deleted data

The ledger, compatibility projection, vectors, review records, and lifecycle state are updated through separate components. There is no explicit durable outbox or projection watermark.

Consequences include:

* Ledger write succeeds but API projection is stale.
* Delete succeeds in the ledger but a stale vector remains searchable.
* Archive transition succeeds but the old Short-term vector still appears in default search.
* Projection repair reintroduces an item after a newer delete.

This is particularly dangerous with the required shared `ns2` namespace. Strict metadata filters are a valid starting decision, but only if all product search goes through one fail-closed wrapper, the UID is server-derived, missing metadata is denied, and authoritative tombstones are rechecked before returning results.  

### 7. P1 — Stable identity and cross-tier retrieval behavior are not defined

The plan does not say whether a memory keeps the same public `memory_id` as it moves:

```text
Short-term → Long-term
Short-term → Archive
Long-term → Archive
```

Without a stable logical identity, promotions can break UI links, delete/edit calls, external references, provenance links, and idempotency. They can also leave both the Short-term source-backed item and the synthesized Long-term item in the default prompt.

The read service also lacks a specified algorithm for:

* Deduplicating Short-term against Long-term.
* Resolving contradictions.
* Prioritizing user edits over extracted observations.
* Allocating prompt/search budgets by tier.
* Producing a stable cursor across multiple stores.
* Preserving deterministic ordering while records transition tiers.

### 8. P1 — Sensitive-data policy is not enforced strongly enough at the current code boundary

The current secret handling depends on a small exact-match risk set. A general archive item is forcibly changed to `normal_search_allowed=True`, overriding a caller that attempted to restrict it. Health, intimate, minor, financial, workplace-confidential, and ordinary third-party personal data do not automatically receive equivalent protection. 

Other weaknesses include:

* `source_refs` and `artifact_ref` are untyped dictionaries.
* Source/evidence fields have no visible size or content restrictions.
* Raw evidence quotes may flow into prompts and persistence.
* Third parties receive Short-term by default, but the tickets do not require a user-granted Short-term scope, revocation audit, or per-app capability test.
* Current IDs can be based partly on sensitive plaintext hashes rather than opaque server-generated identities.

T04 is directionally good, but the enforcement points and consent model need to be acceptance criteria, not just a policy document. 

### 9. P1 — The ticket queue omits the actual live conversation-to-Short-term integration

The Epic identifies `process_conversation.py` and the existing extraction pipeline as a primary integration seam and calls for shadow/dual-write behavior. In the tickets, that file appears in the write-path audit and raw-lineage ticket, but there is no dedicated ticket that implements:

```text
new conversation/source
→ memory extraction
→ Short-term persistence
→ lifecycle/backfill eligibility
```

There is also no complete source-reprocessing contract for transcript edits, speaker corrections, repeated extraction, or extractor-version changes. 

As written, the queue can implement old-memory migration and backfill without implementing the core ongoing product ingestion path.

### 10. P1 — Critical safety infrastructure is sequenced after write tickets

T26 contains kill switches, telemetry, metrics hygiene, and rollout controls, but it is placed after T12 and T18, which perform Short-term/Archive and Long-term writes. T26 itself says stage-specific kill switches must exist before the corresponding stage runs.

Likewise:

* T27, the honest benchmark mode, comes after write-mode backfill.
* T28, the cross-cutting rollout safety verifier, comes at the end even though earlier stages need its guarantees.
* T20 comes after Long-term write-mode backfill even though T15 modifies projections and may trigger vector side effects.

The sequencing is internally inconsistent with the hard rollout blockers.  

### 11. P1 — Raw-artifact accounting is not the same as preservation

T10 records hashes, sizes, paths, and loss outcomes, but it does not clearly require a durable copy-before-drop mechanism for ephemeral sync/pusher artifacts.

A path and checksum for a blob that expires tomorrow do not satisfy “preserved by default.” The plan needs an encrypted content-addressed copy service or an explicit decision that a given source class is outside the preservation guarantee. 

## 3. Missing implementation tickets or acceptance criteria

### A. Atomic and fenced Long-term operation protocol

Rewrite T13–T15 as one defined transaction protocol.

Required acceptance criteria:

* The server, never the LLM, generates the logical operation ID and idempotency key.
* Logical idempotency is stable across head changes, worker retries, and patch-output ordering.
* A separate attempt ID may include the observed head and retry number.
* One transaction verifies the current writer fencing token, account/purge generation, source versions, observed ledger head, and idempotency state before writing the commit and new head.
* A stale writer cannot commit after a newer lease is issued.
* Failure-injection tests cover every crash point before and after claim, commit, head update, and final status update.
* `claimed` operations have a deterministic recovery path; they never remain permanently ambiguous.

### B. Rollout/cutover and rollback reconciliation

Add a ticket defining a capability state machine rather than relying on the ambiguous scalar mode.

It must specify:

* Whether `read` implies memory writes.
* Which stores receive writes in each mode.
* Whether whitelisted accounts dual-write compatibility projections.
* How memory edits/deletes are represented in legacy fallback.
* How rollback avoids disappearing memories or resurrecting deleted ones.
* How a cohort is moved forward and backward with a reconciliation report.

### C. Canonical memory state machine and stable identity

Add a normative transition model separating:

* Product tier.
* Processing/lifecycle state.
* Access policy.
* Visibility.
* Sensitivity.
* Source/tombstone state.
* Projection state.

Impossible combinations must be rejected—for example, `tier=archive` with default access enabled.

A stable logical `memory_id` should survive tier transitions; tier-specific record/version IDs should be separate. The ticket must also define the product mapping for internal `context_only`, such as “remain Short-term until processed, then Archive.”

### D. Live memory extraction and source reprocessing

Add a dedicated ticket for `process_conversation.py` and `working_memory.py`.

Acceptance criteria:

* Shadow mode produces audit artifacts without changing product behavior.
* Write mode creates Short-term records for allowlisted users only.
* memory extraction failure cannot block the legacy pipeline.
* Conversation reprocessing supersedes/tombstones prior extracted versions rather than duplicating them.
* Speaker correction or transcript edit invalidates affected evidence and queued patches.
* Legacy usage tracking, KG behavior, and vector behavior remain unchanged outside the allowlist.

### E. Durable outbox and projection consistency

Add a ticket for ledger-to-projection/vector propagation.

Acceptance criteria:

* Ledger commit and outbox event are recorded atomically.
* Projection/vector consumers are idempotent and version-checked.
* Deletes and tombstones take priority over ordinary upserts.
* Read paths reject stale vectors using authoritative source/tombstone state.
* The system exposes a projection watermark and a bounded staleness SLO.
* Repair cannot overwrite a newer edit/delete.

### F. Source deletion and account-purge race barrier

Extend T06/T09/T14/T15 with:

* User/account deletion generation checked by all writers.
* Apply-time verification of evidence source versions and tombstones.
* Cancellation of queued jobs on purge.
* A rule preventing delayed delivery from recreating a purged account.
* Exact treatment of ledger commits, replay artifacts, model inputs, backups, object-store artifacts, caches, and logs.
* A restore/backup test that does not restore purged data.

### G. Shared-namespace authorization boundary

Strengthen T20 with:

* One mandatory vector/search gateway for all product code.
* No direct product access to raw memory-vector search functions.
* UID and consumer policy derived from authenticated server context, never request metadata.
* Missing or malformed tier metadata fails closed.
* Cross-user, Archive-leak, sensitive-leak, and stale-tombstone adversarial tests.
* A lint or architectural test enumerating every vector call site.

### H. Cross-tier read, ranking, and pagination contract

Extend T21 to specify:

* Long-term versus Short-term precedence.
* Deduplication and contradiction handling.
* Stable ordering and cursor format across heterogeneous stores.
* Context/token budget allocation.
* Freshness and lifecycle cutoffs for Short-term.
* Read-after-write behavior.
* Semantic compatibility tests, not merely “old clients can parse new fields.”

Released mobile, desktop, web, MCP, and developer clients should be tested against golden API fixtures.

### I. Third-party consent and app scopes

Extend T23/T26 with:

* Explicit app capability for Short-term access.
* Existing memory permission migration behavior.
* User-visible consent and revocation.
* Per-app audit records.
* No Archive access unless both app policy and request explicitly allow it.
* Sensitivity and third-party-personal-data restrictions that cannot be overridden by query parameters.

### J. Review lifecycle and backlog resolution

T17 persists review outcomes but does not define how they are resolved.

Add criteria for:

* Review backlog caps and age SLOs.
* Admin or agent resolution before large write rollout.
* Auto-pause if review rate or age exceeds threshold.
* Idempotent accept/edit/reject/keep-as-Archive operations.
* Benchmark reporting for unresolved review items.
* No indefinite use of review as a place to hide useful memories.

### K. Durable raw-artifact preservation

Add an implementation ticket, not only accounting:

* Copy-before-ack/drop for ephemeral sources where feasible.
* Encrypted content-addressed object storage.
* Atomic checksum verification.
* Copy retry/backpressure behavior.
* Object retention and deletion rules.
* Explicit preservation classes for sources that cannot legally or technically be retained.

### L. API route completeness

T22 must also cover at least:

* `POST /v3/memories/batch`.
* Review-resolution endpoints.
* Public/shared memory routes.
* Import paths.
* Idempotency headers/request IDs for retryable POST/PATCH/DELETE calls.
* Version or ETag preconditions for edits.
* Mixed-tier bulk deletion semantics.

The Epic lists the batch route, but the concrete external-write ticket omits it. 

### M. Quantitative launch and online-shadow gates

T27 needs numerical non-inferiority criteria rather than “Base-like.”

At minimum define:

* Non-inferiority margin for useful-grounded-safe yield.
* Maximum harmful/noisy rate with confidence bounds.
* Maximum Archive/review missed-useful rate.
* Minimum source-stratified sample sizes.
* Maximum Long-term duplication and contradiction rate.
* Default-read latency and context-size budgets.
* Online shadow answer-quality and privacy-leak evaluation.
* Explicit owner approval for any launch tradeoff.

## 4. Conflicts and inconsistencies

1. **Normative product policy versus historical Epic sections.** The Epic’s opening update correctly says default reads are Short-term + Long-term and `ns2` is the first vector approach. Later sections still say normal chat is L2-only, call the user state “Durable memory,” expose Context-only UI, and prefer a separate L1 namespace. The supersession note helps humans, but an implementation plan should not contain contradictory normative-looking sections.  

2. **Short-term store conflict.** T03 defines `users/{uid}/memory_short_term`, while T07 permits reusing `users/{uid}/short_term` or defining a new authoritative store. This architectural decision must not be delegated to whichever engineer picks up T07.  

3. **Mode conflict.** `write` and `read` are separate scalar modes, but the read rollout clearly requires continued memory creation and edits. The capability semantics are undefined.

4. **Access-policy vocabulary conflict.** T01 defines `allowed_use` as `default|explicit_query|admin_debug|export_only`. Current code uses values such as `read_with_status`, `stable_profile_fact`, `context_only`, `review_only`, `archive_search`, and `restricted_archive_only`. Filters written against either vocabulary will behave incorrectly against the other.  

5. **L1/archive conflict.** Current extraction contracts call every source-backed item an archive item, while the decision brief explicitly says fresh source-backed items are Short-term and must be available by default.  

6. **Context-only versus Archive routing.** T16 reports an `archive` route, T17 says “Archive/context,” but the current patch decision enum contains `context_only`, not `archive`. The safety guard produces `context_only` and clears `memory_text`, with no defined product transition to an Archive record.  

7. **Safety sequencing conflict.** T26’s kill switches, T27’s benchmark, and T28’s rollout verifier are placed after write-mode tickets even though their own acceptance criteria say they gate those stages.

8. **Deletion-history conflict.** T06 says account purge removes source tombstones and patch history, while T11 uses those records to prove no silent loss. The plan needs a privacy-safe post-purge proof strategy that does not retain user content.

9. **User-facing delete promise versus append-only ledger.** T25 says deletion removes Omi’s memory item/projection/vector. It does not say whether the deleted plaintext remains in ledger commits or replay artifacts. That ambiguity affects both UX truthfulness and erasure compliance.

10. **Current tests encode behavior contrary to the product decisions.** The tests affirm a “normal” L1 archive search and expect quote-wrapper or malformed patch batches to return no outcomes. Those should be explicit-query and explicit audited routes respectively.  

11. **Third-party opt-in ambiguity.** The global `V17_ARCHIVE_OPT_IN_ENABLED` flag is not equivalent to per-user and per-app Archive consent. T23/T26 partially address app policy, but the configuration naming invites an unsafe implementation.

12. **Epic status conflict.** The Epic remains marked Draft and retains unresolved decisions about erasure, Firestore index deployment, manual-memory promotion, and Context-only, while the ticket document calls itself finalized and ready to use.

## 5. Specific changes before implementation starts

### Required document and ticket redlines

1. Create a short **normative architecture specification** at the top of the Epic. Move Wave 1–3 historical plans to a clearly non-normative appendix.

2. Resolve and record these decisions before assigning implementation work:

   * Canonical Short-term store.
   * Stable logical memory ID and version model.
   * Exact tier/lifecycle/access state machine.
   * Meaning of each rollout mode and rollback behavior.
   * Append-only ledger erasure/retention policy.
   * Mapping of internal `context_only` to Short-term or Archive.
   * Direct user-requested Long-term write semantics.
   * Review backlog ownership and resolution path.

3. Rewrite T13–T15 around one atomic, fenced Long-term operation protocol.

4. Split T26:

   * Move backend kill switches, metrics hygiene, telemetry, alerting, and stage controls into the initial safety phase.
   * Leave the admin UI work in the later UI phase.

5. Move the benchmark runner and baseline report portion of T27 before any L2 write pilot. Move the T28 verifier skeleton to the first phase and extend it incrementally after each ticket.

6. Move T20 before any code path is allowed to upsert memory vectors. Until then, T15/T18 must explicitly prohibit memory vector side effects.

7. Add the missing live-ingestion, raw-artifact-copy, projection-outbox, search-authorization, and source-reprocessing tickets.

8. Replace “manual Firestore index deployment is documented” with checked-in index configuration, CI validation, emulator tests, and production load-test evidence. Include Firestore/security-rule changes in the ticket.

9. Add integration and failure-injection tests. Unit tests alone are inadequate for:

   * Concurrent writers.
   * Lease expiry.
   * Transaction retries.
   * Process crashes.
   * Delayed queue delivery.
   * Source deletion during backfill.
   * Account purge during active jobs.
   * Projection/vector lag.
   * API compatibility with released clients.

10. Set actual rollout thresholds and owners. “Conservative placeholders” are not a production gate. Each threshold should state who can approve an override and how the decision is audited.

### Immediate implementation restriction

Keep the current memory code in **off/shadow-only** use. It should not be allowed to advance a production cursor, create review outcomes, or apply a ledger mutation until synthesis failures become explicit terminal/retry outcomes and server-controlled idempotency is implemented.

## 6. Code-level issues to fix now

### 1. Never trust model-supplied IDs or concurrency fields

The synthesizer currently preserves model-provided values when nonempty:

```python
patch.idempotency_key or generated_key
patch.patch_id or generated_id
patch.observed_head_commit_id or trusted_head
patch.packet_id or trusted_packet_id
```

That allows malformed or prompt-injected model output to select an existing idempotency key, spoof a packet/run, or supply a wrong observed head.

Always overwrite these fields from trusted caller state. If the model includes them, validate exact equality and reject the item on mismatch.

### 2. Generate IDs after all deterministic guards

IDs are currently generated before `_with_production_safety_guards`. A patch can receive an ID for:

```text
decision=add
status=active
memory_text=...
```

and then be changed to:

```text
decision=context_only
status=context_only
memory_text=None
```

while retaining the old ID and idempotency key. Compute normalized semantics and policy routing first, validate them, and only then generate identifiers. 

### 3. Remove `observed_head_commit_id` and array index from logical idempotency

The observed head belongs to an application attempt, not the semantic identity of the desired mutation. The list index is unstable under output reordering.

Use two identifiers:

* `logical_operation_id`: stable across retries and replanning.
* `attempt_id`: may include head, run, and retry count.

Canonicalize and sort evidence identifiers before hashing.

### 4. Replace empty-list failure with a typed synthesis result

Return something like:

```python
SynthesisResult(
    status="success|retryable_failure|permanent_failure|partial",
    patches=[...],
    outcomes=[...],
    error_code=...,
    retry_after=...,
)
```

Missing client, timeout, provider failure, parse failure, schema failure, policy rejection, and “no useful patch” must be distinguishable.

A cursor may advance only when every input has an auditable terminal outcome.

### 5. Parse and validate patches independently

One malformed candidate must not erase valid candidates from the same response. Parse the outer JSON, validate each patch separately, and persist a validation outcome for invalid elements.

### 6. Do not silently filter quote-wrapper candidates

`_valid_non_quote_wrapper_patches` should convert the candidate to an explicit `review` or `reject` outcome with a reason such as `quote_wrapper_quality_guard`. It must remain visible to no-silent-data-loss and missed-useful audits.

The existing test expecting `[]` should be replaced.

### 7. Revalidate after `model_copy(update=...)`

Pydantic’s `model_copy(update=...)` does not re-run all model validation by default. The safety guard can therefore create a decision/status/content combination that the normal constructor would reject.

Reconstruct using `DurableMemoryPatch.model_validate(...)` after each deterministic transformation.

### 8. Replace `L1MemoryArchiveItem` as the generic extraction output

Introduce a neutral source-backed candidate contract, for example:

```text
SourceBackedMemoryCandidate
candidate_id
logical_memory_id
source_version
captured_at
expires_at
initial_tier=short_term
evidence
risk assessment
policy version
```

Archive should be a lifecycle result, not the name hard-coded into every extracted record.

### 9. Do not force all general records to normal-searchable

The current validator overwrites `normal_search_allowed=True` for all general items. That defeats caller policy and fails for many non-secret sensitive categories.

Access should be determined by a centralized, versioned policy engine using:

* Consumer.
* User/app grants.
* Tier.
* Visibility.
* Sensitivity category.
* Source state.
* Review state.

Model validation should enforce invariants, not make final authorization decisions.

### 10. Require identity and provenance fields

`user_id`, `source_id`, and `source_type` currently default to empty strings. Require trusted user scope and either a valid source identity or a typed missing-source reason.

Do not allow caller-supplied `archive_id` or patch IDs to overwrite another item.

Vector IDs should include a server-derived tenant component and tier/type prefix. Use an opaque ID for public references and a separate internal content hash.

### 11. Replace untyped evidence dictionaries

Use the canonical evidence model everywhere. Add:

* Source version/update time.
* Span coordinates.
* Artifact checksum.
* Encryption/redaction state.
* Tombstone state and reason.
* Size/count limits.
* Provenance visibility.

`Dict[str, Any]` should not cross persistence or API boundaries.

### 12. Make canonical hashing actually canonical

`json.dumps(..., default=str)` permits arbitrary Python objects whose string representation may differ between versions or environments.

Reject unsupported types. Normalize Unicode, timestamps, enum values, list ordering where order is semantically irrelevant, and schema versions before hashing.

### 13. Add deterministic secret and privacy checks

Do not rely solely on LLM-supplied risk flags. Run deterministic policy checks over proposed Long-term content and evidence before application.

At minimum, test credentials/tokens, financial identifiers, health/intimate data, minors, workplace-confidential data, third-party personal data, and identity/authentication material.

### 14. Rework the blanket third-party guard

The prompt allows Long-term memory about close relationships or entities the user cares about, but the current guard demotes any `aboutness=="third_party"` or `relationship_to_user in {"encountered", "other_speaker"}`. It also converts some review outcomes directly to context-only.

That will hide useful memories such as explicitly user-relevant relationship facts and can reduce measured active yield by routing them away. Add richer relationship semantics and privacy policy, and preserve `review` when uncertainty is the reason for the route. 

### 15. Harden prompt and output trust boundaries

Evidence and retrieved memories are untrusted user-derived text. The system prompt should explicitly state that instructions inside packet/search content are data, not instructions.

Post-validation must ensure:

* Evidence IDs belong to the input packet.
* Target memory belongs to the same authenticated user.
* Retrieved context cannot become evidence for a new claim.
* No patch references an unseen source or memory.
* Search results and prompt/model versions are recorded by hash.

### 16. Add payload bounds and explicit truncation outcomes

Set limits for:

* Memory text length.
* Number and length of evidence quotes.
* Source-reference count.
* Artifact metadata size.
* Patch count per packet.
* Prompt token budget.

When data must be truncated, record a manifest and explicit reason rather than silently discarding provenance.

### 17. Expand the current tests

Add tests for:

* Same logical patch under a different head.
* Same patches returned in a different order.
* Guard changes decision after synthesis.
* LLM supplies malicious duplicate idempotency key.
* Wrong packet/run/head supplied by model.
* Evidence ID not present in the packet.
* Cross-user target memory.
* Partial batch validation.
* Missing LLM/provider timeout.
* Quote wrapper producing an audited outcome.
* General but health/intimate/third-party-sensitive record remaining restricted.
* Empty or mismatched user/source identity.
* Context-only mapping to Archive.
* Source deleted between synthesis and apply.
* Lease expiry and stale-writer fencing.
* Purge concurrent with delayed patch delivery.

Once the atomic write protocol, canonical state model, cutover behavior, live-ingestion path, and safety sequencing are incorporated, the plan would move to **GO_WITH_CHANGES**. As currently written, it should not drive production implementation.


9m13s · gemini-3.5-flash[browser] · ↑34.59k ↓7.85k ↻0 Δ42.44k
files=4

9m13s · gemini-3.5-flash[browser] · ↑34.59k ↓7.85k ↻0 Δ42.44k | files=4 | slug=memory-plan-oracle-gemini2
