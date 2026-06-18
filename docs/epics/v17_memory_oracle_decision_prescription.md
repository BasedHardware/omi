# V17 Memory Product Integration — Oracle Decision Prescription

**Date:** 2026-06-18  
**Reviewer:** Oracle (`oracle` CLI, browser-backed `gemini-3.5-flash`; same prior browser session could not be followed up because Oracle had no recoverable ChatGPT conversation URL, so this was a new Oracle run using the prior review plus the Epic/tickets/code context)  
**Purpose:** Convert Oracle's critique into concrete architecture/product/implementation decisions and identify which remaining choices need David's input.

**Inputs:**
- `docs/epics/v17_memory_oracle_review.md`
- `docs/epics/v17_memory_product_integration_epic.md`
- `docs/epics/v17_memory_implementation_tickets.md`
- `docs/epics/v17_memory_product_integration_decision_brief.md`
- V17 contract/patch code excerpts from `backend/models/v17_memory_contracts.py` and `backend/utils/llm/durable_memory_patches.py`
- V17 unit test excerpts

---

# 1. Executive verdict

## Verdict

**Move from “BLOCKED on architecture” to “GO for P0 implementation, BLOCKED for production writes.”**

The core product direction is already settled: Short-term is fresh/default-access, Long-term is stable synthesis, Archive is explicit-query history, Context-only is not user-visible, rollout is allowlist-first, non-whitelisted users remain legacy, `ns2` is the initial vector namespace, raw artifacts are preserved where technically available, and evaluation stays anchored to Base Omi with anti-reward-hacking audits.   

The following architecture decisions can now be locked:

* Use **one tiered product-memory collection**, not separate Short-term and Archive collections.
* Keep the existing ledger as the **Long-term source of truth**.
* Replace separate patch claim, lease, and ledger steps with **one atomic Firestore apply transaction**.
* Do **not** build a distributed writer lease. Transactional contention on the per-user ledger head/control document provides serialization.
* Introduce one server-owned **memory operation journal** for active and non-active outcomes.
* Add account-generation and source-version checks to every write transaction.
* Update the Long-term product projection in the same transaction as the ledger commit; use a durable outbox for vectors and other external side effects.
* Use `ns2` only through one fail-closed search gateway that hydrates authoritative product-memory records before returning anything.
* Define `read` as a superset of `write`; rollback from `read` goes to a reconciled compatibility projection, not the original stale legacy dataset.
* Replace `L1MemoryArchiveItem` as the generic extraction contract with a neutral source-backed candidate whose initial tier is Short-term.
* Replace empty-list synthesis behavior with typed, auditable outcomes.
* Keep review internal for MVP; unresolved review defaults to Archive, not a new user-facing state.

The Oracle review correctly identified that the current tickets are unsafe as an executable production plan, particularly around atomic application, silent synthesis failure, rollback, deletion races, projection consistency, and the source-backed contract. 

## What remains blocked

Production writes, vector changes, V17 reads, and external API cutover remain blocked until the P0 amendments below pass.

Only three matters require David-level product or legal input:

1. The exact legal/account-deletion promise for encrypted append-only history.
2. The raw-artifact retention period.
3. Whether MVP should expose an Archive-to-Long-term button or dedicated review UI instead of relying on chat/agent tools.

Two additional items require investigation, but **not David’s taste**:

* Locate the repository’s actual Firestore index deployment mechanism; create a checked-in standard configuration if none exists.
* Verify the prescriptions against the full repository and run integration/failure-injection tests. The attached code is excerpted, and the prior review did not execute the repository. 

---

# 2. Decision table

| Area                           | Prescribed decision                                                                                                                                                                                                                                                                                                                                                                                | Rationale                                                                                                                               | Ticket/doc changes required                                          | David input needed |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------ |
| Product tiers                  | Canonical tiers are exactly `short_term`, `long_term`, and `archive`. `context_only`, `review`, and `reject` are processing outcomes, not tiers.                                                                                                                                                                                                                                                   | Prevents product state and pipeline state from becoming one inconsistent taxonomy.                                                      | Revise T01 and normative Epic section.                               | no                 |
| Canonical product store        | Create one `users/{uid}/memory_items/{memory_id}` collection containing all three tiers. Do not create separate `memory_short_term` and `memory_archive` collections.                                                                                                                                                                                                                              | Simplifies tier transitions, pagination, deletion, identity, API reads, and vector repair.                                              | Replace T03 collection plan; revise T07.                             | no                 |
| Tier authority                 | `memory_items` is authoritative for Short-term and Archive. The ledger is authoritative for Long-term; its `memory_items` record is a transactionally synchronized projection.                                                                                                                                                                                                                     | Retains the stable ledger without imposing ledger complexity on high-volume source-backed records.                                      | Revise T01, T03, T15, T21.                                           | no                 |
| Existing short-term store      | Do not reuse `users/{uid}/short_term` as the V17 canonical store. Treat it as a legacy input/adapter only.                                                                                                                                                                                                                                                                                         | Existing semantics such as pending/consolidated do not cleanly match the final tier model. Two authoritative stores would create drift. | T07 must explicitly reject reuse as canonical.                       | no                 |
| Stable identity                | Mint an opaque server-generated `memory_id` at first persistence. Retain it for one-to-one Short-term→Long-term and Short-term→Archive transitions. For many-to-one merges, the target Long-term ID wins and old IDs become resolvable aliases.                                                                                                                                                    | Preserves links and edit/delete semantics without pretending many source records can all retain one canonical ID.                       | Revise T01; add alias behavior to T15/T21/T22.                       | no                 |
| Record versions                | Use a separate monotonically increasing `version` and immutable operation/commit IDs. Never encode content or tier into the public ID.                                                                                                                                                                                                                                                             | Supports optimistic edits, vector version checks, and safe transitions.                                                                 | T01, T20, T22.                                                       | no                 |
| Access policy                  | Remove persisted `normal_default_access`, `explicit_archive_query_only`, and free-form `allowed_use` from the canonical model. Compute access from tier, status, visibility, sensitivity, consumer scope, and source state. Compatibility DTOs may expose a derived value.                                                                                                                         | Redundant flags can disagree with each other and currently use conflicting vocabularies.                                                | Revise T01 and T04; add central policy service.                      | no                 |
| Source-backed extraction       | Replace generic use of `L1MemoryArchiveItem` with `SourceBackedMemoryCandidate`, initially `tier=short_term`. Keep `L1MemoryArchiveItem` only as a deprecated fixture/import adapter.                                                                                                                                                                                                              | The current contract forces all extracted records into Archive, contradicting the product model.                                        | T01 plus new live-ingestion ticket; patch `working_memory.py`.       | no                 |
| Archive search                 | Delete product use of `filter_l1_archive_for_normal_search`. Archive retrieval must go through an explicit Archive query path.                                                                                                                                                                                                                                                                     | “Normal archive search” is incompatible with explicit-query-only Archive.                                                               | Revise contracts, T20, T21, T23 and tests.                           | no                 |
| Short-term lifecycle           | Initial server-side freshness window: 30 days. A record leaves Short-term earlier when L2 processes it; unprocessed records age into Archive. No user-facing TTL toggle.                                                                                                                                                                                                                           | Prevents Short-term becoming an unbounded default-access store without adding UI complexity.                                            | Move revised T19 before any Short-term write pilot.                  | no                 |
| Internal Context-only          | Keep the existing enum as a legacy/internal alias if needed, but normalize it to the `archive` route. Never persist `context_only` as a product tier or show it to users.                                                                                                                                                                                                                          | Minimizes code/benchmark churn while enforcing the final product model.                                                                 | T01, T13, T17, T25.                                                  | no                 |
| Review route                   | A review outcome creates an operation/review record and moves affected source candidates to Archive. It does not create an active Long-term fact or remain default-access Short-term.                                                                                                                                                                                                              | Safe default with no new visible tier.                                                                                                  | Revise T17.                                                          | no                 |
| Review UX                      | MVP review is internal/admin and conversational. No mandatory user review queue. Auto-close unresolved items as “keep Archive” after 30 days.                                                                                                                                                                                                                                                      | Avoids burdening users and prevents review becoming a permanent holding area.                                                           | Split backend review controls from optional later UI in T25.         | yes                |
| Rollout mode semantics         | `off`: legacy only. `shadow`: legacy authoritative; isolated audit artifacts only. `write`: legacy reads remain authoritative; V17 sidecar writes occur. `read`: includes all `write` behavior and makes V17 reads authoritative.                                                                                                                                                                  | Preserves one simple external mode while removing ambiguity.                                                                            | Rewrite T00.                                                         | no                 |
| Rollback                       | `read → write` is supported by one config change, but reads use a reconciled V17-derived legacy compatibility projection. `write → off` is blocked after V17 writes until an explicit decommission reconciliation succeeds.                                                                                                                                                                        | Prevents disappearing V17 memories and resurrection of deleted legacy values.                                                           | New rollback/reconciliation acceptance criteria in T00/T21.          | no                 |
| Non-whitelisted users          | No new collection reads, writes, filters, metrics, or vector behavior for non-whitelisted users.                                                                                                                                                                                                                                                                                                   | This is a locked rollout requirement.                                                                                                   | T00/T05 architectural tests.                                         | no                 |
| Old-memory migration           | Old memories never become Long-term directly. Recent/manual records become prioritized Short-term candidates; older records become Archive; all remain backfill-eligible.                                                                                                                                                                                                                          | Preserves data without silently promoting stale facts.                                                                                  | Keep T08–T12, revise model/store targets.                            | no                 |
| New explicit user memory       | A first-party explicit “remember this” request creates Long-term directly as a user assertion. Automated extraction and generic third-party POSTs default to Short-term.                                                                                                                                                                                                                           | Explicit user intent is stronger than inferred stability; forcing it through backfill adds latency and surprises.                       | Revise T22/T24.                                                      | no                 |
| Long-term serialization        | Remove the standalone distributed lease design. Every Long-term mutation must transact on the same per-user head/control document.                                                                                                                                                                                                                                                                 | Firestore transaction contention provides the actual correctness boundary; a lease adds failure modes without improving correctness.    | Replace T14 with transaction control/fencing tests; merge with T15.  | no                 |
| Idempotency                    | The LLM supplies no IDs. Persist a server-created `operation_id`; compute a stable proposal fingerprint without head ID or array index. Retries reuse the operation ID. Materially changed replans supersede the prior operation.                                                                                                                                                                  | Stable across output ordering, head changes, and worker retries.                                                                        | Rewrite T13 and current patch code.                                  | no                 |
| Atomic apply                   | One transaction reads account generation, source versions, operation, and ledger head; then writes commit, head, operation result, affected `memory_items`, and outbox event.                                                                                                                                                                                                                      | Eliminates ambiguous “claimed but not committed” states.                                                                                | Merge/rewrite T13–T15.                                               | no                 |
| “Exactly once” claim           | Claim **idempotent externally visible application**, not exactly-once LLM execution. Synthesis may run more than once.                                                                                                                                                                                                                                                                             | Accurately describes what the system guarantees.                                                                                        | Revise Epic/ticket wording.                                          | no                 |
| Account purge fence            | Add `memory_control/state` with `account_generation` and `writes_blocked`. Every queued job captures a generation and every mutating transaction rechecks it.                                                                                                                                                                                                                                      | Prevents delayed workers from recreating purged data.                                                                                   | Revise T06 and all worker tickets.                                   | no                 |
| Source deletion race           | Evidence carries source version. Apply must verify active source state and exact expected version. Changed/deleted evidence becomes `source_changed` or `source_tombstoned`, never an applied patch.                                                                                                                                                                                               | Snapshot protection alone does not cover delayed L2 application.                                                                        | T02, T06, T09, T15.                                                  | no                 |
| Projection consistency         | Update the Long-term `memory_items` projection in the ledger transaction. Use an outbox for vectors, analytics, and other external effects.                                                                                                                                                                                                                                                        | API state is immediately coherent; only external projections can lag.                                                                   | New outbox work in T15/T20.                                          | no                 |
| Vector namespace               | Lock `ns2` as the initial implementation. Do not create another namespace unless adversarial tests demonstrate that the gateway/filter model is unsafe.                                                                                                                                                                                                                                            | Matches the product preference and avoids premature operational complexity.                                                             | Revise T20 and remove historical separate-namespace recommendations. | no                 |
| Vector access                  | All product search must use one gateway. UID is server-derived, metadata is mandatory, missing fields fail closed, and vector hits are hydrated from `memory_items` before return.                                                                                                                                                                                                                 | A stale vector must never be treated as authoritative.                                                                                  | Rewrite T20; add call-site architectural test.                       | no                 |
| Default retrieval              | Default Omi reads use Long-term + Short-term. Archive contributes zero results unless the caller invokes an explicit Archive operation.                                                                                                                                                                                                                                                            | Locked product behavior.                                                                                                                | T21/T23.                                                             | no                 |
| Cross-tier dedup               | Suppress a Short-term result when it is superseded by or linked as evidence to a returned Long-term memory. User-authored correction > current Long-term > extracted Short-term.                                                                                                                                                                                                                   | Prevents duplicated or contradictory prompt context.                                                                                    | T21 acceptance criteria.                                             | no                 |
| Prompt budget                  | Initial default: 70% Long-term and 30% Short-term, with unused capacity flowing to the other tier. Archive gets 0% unless explicitly queried.                                                                                                                                                                                                                                                      | Stable memories should dominate while fresh source-backed recall remains meaningful.                                                    | T21/T23; tune only through benchmark evidence.                       | no                 |
| API pagination                 | Product list pagination comes from unified `memory_items`, ordered by `(updated_at DESC, memory_id DESC)`. Cursor contains both fields.                                                                                                                                                                                                                                                            | Avoids fragile cross-store merged cursors.                                                                                              | T21/T25.                                                             | no                 |
| Sensitive data                 | Credentials/authentication secrets never become Long-term or default-access memory. Health, intimate, minors, financial identifiers, workplace-confidential and sensitive third-party data may be preserved encrypted but are excluded from automatic Long-term promotion and third-party default access. Explicit user assertion may permit restricted first-party Long-term, except credentials. | Concrete privacy boundary without deleting useful source context.                                                                       | Strengthen T04 and deterministic policy code.                        | no                 |
| Third-party relationship facts | Remove the blanket “all third-party facts become Context-only” rule. User-relevant close relationships and cared-about entities may become Long-term; incidental or unlinked third-party facts go to Archive/review.                                                                                                                                                                               | The current guard is too blunt and contradicts the synthesis rubric.                                                                    | Patch current guard; revise T04/T13.                                 | no                 |
| Third-party scopes             | Existing broad memory permission maps to `memory:default` = Short-term + Long-term. Archive requires a distinct `memory:archive` grant and explicit archive query. Source quotes require a separate provenance permission.                                                                                                                                                                         | Matches the stated default-access model without exposing Archive or raw evidence.                                                       | T23 and app-policy docs.                                             | yes                |
| Raw artifacts                  | For bytes observed after V17 rollout and legally retainable, perform encrypted copy-before-ack/drop into content-addressed storage. Historical or already-dropped artifacts remain explicit loss outcomes.                                                                                                                                                                                         | Accounting alone does not preserve ephemeral bytes.                                                                                     | Rewrite T10.                                                         | no                 |
| Raw retention                  | Retain raw artifacts according to the source/account retention policy by default, rather than creating a separate memory-specific user toggle.                                                                                                                                                                                                                                                     | Simple and predictable, but the actual retention promise is product/legal.                                                              | T04/T10/data-retention doc.                                          | yes                |
| Memory deletion                | Tombstone the product item, append a Long-term retraction when applicable, and enqueue vector deletion. Do not delete raw source by default.                                                                                                                                                                                                                                                       | Follows existing user semantics while covering V17.                                                                                     | T06/T22.                                                             | no                 |
| Source deletion                | Hide/tombstone source-backed items. Machine-extracted Long-term memories with no surviving evidence leave default access and go to review; explicit user assertions remain unless the memory itself is deleted.                                                                                                                                                                                    | Distinguishes evidence removal from explicit user intent.                                                                               | T06/T17.                                                             | no                 |
| Account deletion               | Block writes and increment generation first; destroy the user content-encryption key; delete hot-store records, vectors, jobs and artifacts; retain at most a non-content purge receipt if legally permitted.                                                                                                                                                                                      | Prevents resurrection and provides practical crypto-erasure.                                                                            | T04/T06.                                                             | yes                |
| Live ingestion                 | Add an explicit conversation/source → Short-term ticket. Reprocessing supersedes prior extraction versions rather than creating duplicates.                                                                                                                                                                                                                                                        | Current queue can migrate old data without implementing the actual ongoing product flow.                                                | New T07A.                                                            | no                 |
| API completeness               | Include batch create, import paths, review resolution, public/shared routes, idempotency keys, version preconditions and mixed-tier bulk delete.                                                                                                                                                                                                                                                   | The current external-write ticket is incomplete.                                                                                        | Rewrite T22.                                                         | no                 |
| UI                             | Default list shows Long-term and recent Short-term with simple labels. Archive is a separate search/filter. No Context-only or processing-route labels.                                                                                                                                                                                                                                            | Minimal user complexity.                                                                                                                | T25.                                                                 | no                 |
| Safety controls                | Move backend kill switches, telemetry and metrics hygiene ahead of all writes. Keep the later admin UI separate.                                                                                                                                                                                                                                                                                   | Safety controls cannot gate work that has already shipped.                                                                              | Split T26 into T26A/T26B.                                            | no                 |
| Benchmark                      | Move the Base-anchored benchmark runner before Long-term write mode. Report active-only and total route yield, with complete missed-useful audits.                                                                                                                                                                                                                                                 | Prevents route hiding from looking like quality improvement.                                                                            | Move/split T27.                                                      | no                 |
| Firestore indexes              | Check indexes into source control and validate them in CI/emulator. If the repo lacks an existing location, create root `firestore.indexes.json`.                                                                                                                                                                                                                                                  | Manual undocumented deployment is not an acceptable rollout dependency.                                                                 | Revise T03.                                                          | no                 |

---

# 3. P0 amendment plan

## Order 0 — `A00: Normative V17 architecture specification`

**New document:** `docs/epics/v17_memory_normative_architecture.md`

**Changes:**

* Make this the normative source of truth.
* Move Wave 1–3 historical material in the Epic to a clearly non-normative appendix.
* State the collection model, state model, mode semantics, identity behavior, access derivation, write transaction and retrieval path.

**Acceptance criteria:**

* No normative section says L1 is always Archive.
* No normative section says default reads are Long-term-only.
* No normative section recommends a separate vector namespace.
* No product record state named Context-only exists.
* Every existing open question is marked either decided, assigned to infrastructure/security, or requiring David/legal.

---

## Order 1 — `T00-R: Rollout capability state machine and reconciliation`

**Revises:** T00.

**Acceptance criteria:**

* `read` includes V17 writes.
* `write` keeps legacy reads authoritative until cutover.
* A per-user rollout document records mode epoch, cutover epoch, expected account generation, last reconciled legacy revision and whether fallback projection is ready.
* `read → write` immediately switches to the reconciled compatibility projection.
* `write → off` is rejected after persistent V17 writes unless a decommission reconciliation succeeds.
* Non-whitelisted users never read the rollout document and remain on legacy paths.
* Failure tests cover mode change during active workers.

---

## Order 2 — `T01-R: Canonical memory state, stable identity and aliases`

**Revises:** T01.

**Canonical product fields:**

```text
memory_id
canonical_memory_id          # null unless aliased/superseded
version
tier                         # short_term | long_term | archive
status                       # active | superseded | hidden | tombstoned
processing_state             # pending | processed | blocked
content
evidence[]
source_state                 # active | missing | tombstoned | purged
sensitivity_labels[]
visibility
user_asserted
captured_at
updated_at
expires_at                   # required for Short-term
ledger_commit_id             # required for active Long-term
ledger_sequence
```

**Acceptance criteria:**

* Access is derived, not stored as drifting booleans.
* Short-term requires an expiry and source/evidence or explicit missing-source reason.
* Active Long-term requires a ledger commit and sequence.
* Archive can never satisfy default-access policy.
* One-to-one tier transitions retain `memory_id`.
* Many-to-one merges create aliases that keep old IDs resolvable.
* Legacy DTOs remain additive and parseable.

---

## Order 3 — `T02-R: Evidence, source versions, canonicalization and payload bounds`

**Revises:** T02.

**Acceptance criteria:**

* Evidence is typed; no `Dict[str, Any]` crosses a persistence or API boundary.
* Evidence includes `source_id`, `source_version`, source type, span/quote reference, artifact ID/checksum, tombstone state, provenance visibility and redaction state.
* Evidence IDs in model output must be a subset of the supplied packet.
* Target memories must belong to the authenticated user.
* Unsupported values fail canonical serialization rather than falling back to `str()`.
* Unicode is NFC-normalized; timestamps use canonical UTC; semantically unordered IDs are sorted.
* Content/evidence fingerprints use HMAC-SHA256 or an equivalent keyed digest.
* Enforce limits for content length, evidence count, quote length, source references, artifact metadata and patches per response.
* Truncation creates an explicit manifest and outcome.

---

## Order 4 — `T03-R/T07-R: Unified product-memory store and index plan`

**Revises:** T03 and T07.

**Collections:**

```text
users/{uid}/memory_items/{memory_id}
users/{uid}/memory_operations/{operation_id}
users/{uid}/memory_outbox/{event_id}
users/{uid}/memory_control/state
users/{uid}/memory_lineage/{lineage_id}
users/{uid}/memory_runs/{run_id}
users/{uid}/memory_legacy_fallback/{memory_id}
```

Existing Long-term ledger collections remain.

**Acceptance criteria:**

* No separate canonical Short-term or Archive collection.
* No V17 code hardcodes collection names.
* All required indexes are checked into source control.
* Emulator/CI tests validate default tier queries, Archive queries, lifecycle jobs, operation status, outbox scans and cursor pagination.
* Existing `users/{uid}/short_term` is documented as legacy/non-authoritative.

---

## Order 5 — `T05-R: Mandatory write and search gateway audit`

**Revises:** T05.

**Acceptance criteria:**

* Every memory create, edit, delete, review, visibility change, source deletion, vector search and repair call site is classified.
* All V17 Long-term writes call one write service.
* All V17 product vector searches call one search gateway.
* Architectural tests or static checks fail when product code directly imports restricted raw ledger/vector mutation functions.
* Non-whitelisted golden tests prove byte-for-byte-equivalent legacy DTO behavior where deterministic.

---

## Order 6 — `T04-R: Central sensitive-data and consumer-access policy`

**Revises:** T04.

**Acceptance criteria:**

* One policy function evaluates tier, consumer, app grant, visibility, sensitivity, source state and item status.
* Model-supplied risk labels are signals, not authorization.
* Deterministic checks cover credentials, financial identifiers, health, intimate data, minors, workplace-confidential data, identity/authentication and third-party personal data.
* Credentials cannot become active Long-term under any automatic or external API route.
* Restricted source data may be preserved encrypted without being default-access.
* Existing free-form `allowed_use` fields are treated as deprecated compatibility output.

---

## Order 7 — `T06-R: Account/source generation fences, deletion, export and purge`

**Revises:** T06 and extends T09/T15.

**Acceptance criteria:**

* Purge first sets `writes_blocked=true` and increments `account_generation`.
* Every write transaction checks the expected account generation.
* Every evidence-backed operation checks exact source version and non-tombstoned state.
* Queued jobs with stale generation fail terminally and cannot recreate records.
* Source deletion wins over imports, L2 application, vector repair and delayed API writes.
* Purge destroys the user content-encryption key before asynchronous physical cleanup.
* Backup/restore testing proves purged content is not made readable again.
* Post-purge audit evidence contains no plaintext, raw IDs or reversible user identity.

---

## Order 8 — `T26A: Backend kill switches, telemetry and metric hygiene`

**Split from:** T26. Admin UI becomes later T26B.

**Acceptance criteria:**

* Kill switches exist before corresponding workers are executable.
* Separate controls cover source ingestion, migration, raw copy, L2 synthesis, apply, outbox/vector projection, read switch, source tombstones and purge/export jobs.
* Migration/backfill/repair events cannot increment organic creation, engagement, notification, search, export or cohort metrics.
* Initial canary auto-pause defaults: retryable synthesis failures over 2% of 100 packets; open review rate over 20% of 200 operations; projection lag over five minutes; any duplicate commit; any Archive leak; any purge resurrection.

---

## Order 9 — `T28A: Incremental rollout safety verifier`

**Moves ahead of writes:** T28.

**Acceptance criteria:**

* The verifier initially covers config isolation, generation fences, source versions, storage invariants and metric hygiene.
* Each later P0 ticket adds its checks to the same verifier.
* The verifier outputs an explicit per-user/cohort decision: `shadow_allowed`, `short_term_write_allowed`, `long_term_write_allowed`, `read_allowed`.
* A red gate cannot be bypassed solely by configuration; overrides require an audited owner and reason.

---

## Order 10 — `T10-R: Durable raw-artifact copy and lineage`

**Revises:** T10.

**Acceptance criteria:**

* Ephemeral bytes are copied to encrypted object storage before the source path is acknowledged or eligible for eviction, where technically and legally possible.
* Artifact identity uses a keyed content digest to avoid cross-user hash correlation.
* Copy, checksum verification and lineage record are completed atomically or represented as a retryable state.
* Backpressure and copy failures produce explicit `copy_failed` or `dropped_before_copy` outcomes.
* Already-expired or historically dropped data is never labeled preserved.
* Purge and source deletion behavior is defined for the object and its encryption key.

---

## Order 11 — `T07A: Live source-backed ingestion and reprocessing`

**New ticket.**

**Files:** `process_conversation.py`, `working_memory.py`, the new product-memory service and lineage code.

**Acceptance criteria:**

* Shadow mode creates audit artifacts only.
* Write mode creates Short-term records for allowlisted users only.
* V17 extraction failure never blocks or changes the legacy pipeline.
* The ingestion key is stable across delivery retries and based on source ID, source version, extractor version and source span identity.
* Transcript edits, speaker corrections and extractor-version changes supersede prior candidates; they do not produce uncontrolled duplicates.
* Source deletion during extraction prevents persistence.
* New Short-term records have a 30-day default expiry and are backfill-eligible.

---

## Order 12 — `T13-R: Typed synthesis results and memory operation journal`

**Replaces:** current T13 design and part of T17.

**Canonical synthesis statuses:**

```text
success
partial
retryable_failure
permanent_failure
```

**Canonical per-candidate outcomes:**

```text
proposed
archive
review
reject
skip
invalid
```

**Acceptance criteria:**

* Missing client, timeout, provider error, malformed outer JSON, invalid candidate, quote wrapper, privacy rejection and genuine no-action are distinguishable.
* A packet cursor advances only when every input candidate has an auditable terminal outcome.
* Outer JSON is parsed once; candidates are validated independently.
* One invalid candidate cannot erase valid candidates.
* Quote wrappers become explicit rejects with reason `quote_wrapper_quality_guard`.
* The server owns packet/run/head/operation/idempotency fields.
* The operation journal is canonical for active and non-active outcomes.
* No `claimed` state can remain ambiguously between operation and commit.

---

## Order 13 — `T27A: Base-anchored benchmark and online-shadow gate`

**Moves the runner/reporting portion of T27 before apply work.**

**Initial launch gates:**

* Base Omi remains the visible anchor.
* All non-rejected useful-grounded-safe yield has a non-inferiority margin of five memories per 100 contexts relative to Base.
* Active Long-term harmful/noisy output is no more than 25 per 100 contexts.
* Active credentials/secrets: zero.
* Archive returned by default-policy tests: zero.
* Duplicate logical operation or commit on replay: zero.
* All non-active candidates in the fixed offline set receive a missed-useful audit.
* Reports separately show active, active+review, active+Archive and all non-rejected yield.

The current documents show why this is necessary: V17.9 is substantially cleaner but slightly below the Base projection on broad useful-grounded-safe yield. 

---

## Order 14 — `T14/15-R: Atomic Long-term apply transaction and durable outbox`

**Merges and replaces:** T14 and T15. Remove the standalone lease service.

**Transaction reads:**

```text
memory_control/state
memory_state/head
memory_operations/{operation_id}
all referenced source/memory versions
```

**Transaction writes:**

```text
memory_commits/{commit_id}
memory_state/head
memory_operations/{operation_id}
affected memory_items/{memory_id}
memory_outbox/{event_id}
memory_legacy_fallback/{memory_id}  # when cutover state requires it
```

**Acceptance criteria:**

* Same operation can apply at most once.
* Head mismatch creates `needs_replan`, not a blind retry.
* Stale account generation or source version prevents commit.
* A process crash before the transaction leaves a retryable operation.
* A process crash after transaction commit is harmless; replay returns the stored result.
* No commit can exist without the matching head, operation result and product projection.
* Commit ID is derived from the server operation ID, not from model output or array position.
* Failure-injection tests cover concurrent add/edit/delete/review, transaction retries and projector crashes.

---

## Order 15 — `T17-R: Review and non-active lifecycle`

**Revises:** T17.

**Acceptance criteria:**

* The operation journal is canonical; the existing review queue is a projection/index.
* Review, Archive, reject and skip outcomes never appear in default reads.
* Review inputs transition to Archive.
* Maximum initial open review backlog is 20 per user.
* More than three new review outcomes per user/day pauses that user’s backfill.
* Oldest unresolved review over seven days raises an operational warning.
* At 30 days, unresolved review auto-resolves to `keep_archive`.
* Accept/edit/reject/keep-Archive operations are idempotent.
* Review cannot be used to exclude candidates from benchmark denominators.

---

## Order 16 — `T19-R: Short-term lifecycle before write rollout`

**Moves:** T19 ahead of T12.

**Acceptance criteria:**

* Default expiry is 30 days from capture or last corroboration.
* Successful Long-term promotion transitions or supersedes the source item atomically.
* `context_only`/archive route moves the item to Archive.
* Unprocessed expiry moves the item to Archive with reason `expired_unprocessed`.
* Hidden, tombstoned and superseded Short-term records are excluded from default access.
* Lifecycle reruns are idempotent.

---

## Order 17 — `T20-R: Shared-namespace search gateway and projection consistency`

**Revises:** T20.

**Acceptance criteria:**

* Only the gateway may query `ns2` for product memory.
* Authenticated UID and consumer policy are server-derived.
* Missing tier, status, user, version or source-state metadata fails closed.
* Vector results are candidate IDs only; authoritative `memory_items` hydration is mandatory.
* Hydration rejects stale version, Archive in default mode, hidden/tombstoned records and cross-user records.
* Deletes and tombstones outrank upserts in outbox processing.
* Outbox consumers are idempotent and version-checked.
* Repair cannot overwrite a newer item version.
* Adversarial tests cover Archive leakage, cross-user leakage, stale vectors and malformed metadata.

---

## Order 18 — `T21-R: Unified read, ranking, pagination and rollback compatibility`

**Revises:** T21.

**Acceptance criteria:**

* Default result set is active Long-term + eligible Short-term.
* Archive requires an explicit Archive operation; `tier=all` is insufficient for third parties.
* Alias resolution and lineage suppress duplicate Short-term/Long-term content.
* Explicit user correction outranks current Long-term; current Long-term outranks inferred Short-term.
* Prompt retrieval initially reserves 70% for Long-term and 30% for Short-term.
* Product list pagination uses the unified collection and stable `(updated_at, memory_id)` cursor.
* Released-client golden fixtures parse the additive DTO.
* Read-after-write sees the transactionally updated product item.
* Read rollback uses the V17-derived compatibility projection and cannot resurrect old deleted values.

---

## Order 19 — `T22/23-R: Complete API semantics and app capabilities`

**Revises:** T22 and T23.

**Acceptance criteria:**

* Covers `/v3/memories/batch`, imports, public/shared routes, review resolution and all developer/MCP/tool routes.
* Retryable third-party POST/batch requests require `Idempotency-Key`.
* PATCH and DELETE support version/ETag preconditions.
* Bulk delete specifies whether Archive is included; default excludes it.
* First-party explicit “remember” can create Long-term.
* Generic automated/API creation defaults to Short-term.
* No API can directly create Archive; Archive is a lifecycle/import outcome.
* Existing broad memory grant maps to default memory; Archive and raw provenance require separate capabilities.
* Revocation takes effect immediately through server-side policy, irrespective of cached vector results.

---

## Existing tickets after the P0 amendment

* T08, T09 and T11 may run after Orders 0–10.
* T12 Short-term/Archive import write may run only after Orders 0–11, 16 and the relevant T28A gates.
* T16 dry-run backfill may run after Orders 12–13.
* T18 Long-term write mode may run only after Orders 14–19 and a green benchmark/safety report.
* T24 and T25 remain post-read-service product work.
* T26B is the later admin UI portion only.

---

# 4. Code-level decisions for the current V17 contract/patch code

The current code trusts model-supplied control fields, computes IDs before deterministic guards, includes output index and observed head in idempotency, filters quote wrappers silently, returns `[]` for provider and parsing failures, validates the whole batch together, and hard-codes source-backed items as Archive. The current tests explicitly expect some of those silent-empty behaviors. 

## Changes to make now

### A. `backend/models/v17_memory_contracts.py`

1. Add canonical enums:

```python
class MemoryTier(str, Enum):
    short_term = "short_term"
    long_term = "long_term"
    archive = "archive"

class MemoryItemStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    hidden = "hidden"
    tombstoned = "tombstoned"

class SourceState(str, Enum):
    active = "active"
    missing = "missing"
    tombstoned = "tombstoned"
    purged = "purged"
```

2. Add `SourceBackedMemoryCandidate`; initial tier must be Short-term unless an import explicitly supplies Archive.

3. Deprecate `L1MemoryArchiveItem`:

* Keep deserialization for existing benchmark fixtures.
* Do not use it as the return contract of new extraction.
* Do not use its validator to decide product access.
* Remove product calls to `filter_l1_archive_for_normal_search`.

4. Replace untyped `artifact_ref` and `source_refs` dictionaries with typed evidence/source models.

5. Require trusted identity:

* `user_id` cannot default to empty.
* `source_id` and `source_version` are required, or a typed missing-source reason is required.
* Public IDs are opaque server-owned values.

6. Stop forcibly setting general records to normal-searchable.

7. Keep `derive_allowed_use` only as a deprecated DTO compatibility helper. Authorization moves to a central policy service.

8. Replace permissive canonical JSON:

* Reject unsupported values.
* Normalize Unicode and timestamps.
* Sort evidence IDs.
* Include canonicalization schema version.
* Use a keyed digest for content-derived fingerprints.

9. Add strict size/count bounds at model validation.

### B. `backend/utils/llm/durable_memory_patches.py`

1. Change the return type from `List[DurableMemoryPatch]` to a typed `DurableMemorySynthesisResult`.

2. Remove these fields from the LLM-controlled schema:

```text
patch_id
idempotency_key
packet_id
run_id
observed_head_commit_id
```

If backward-compatible output contains them, reject the candidate with `untrusted_control_field`; do not preserve or overwrite them silently.

3. Remove the instruction “Preserve observed_head_commit_id exactly.” The head is application metadata, not model output.

4. Replace whole-batch `PydanticOutputParser` validation with:

```text
json.loads outer object
→ verify patches is a list
→ validate each candidate independently
→ persist an outcome for each candidate
```

5. Normalize in this order:

```text
parse candidate
→ verify evidence IDs and target ownership
→ apply deterministic privacy/attribution guards
→ reconstruct with DurableMemoryPatch.model_validate(...)
→ compute proposal fingerprint
→ create server operation record
```

6. Delete `_valid_non_quote_wrapper_patches`. A quote wrapper becomes:

```text
outcome=reject
reason_code=quote_wrapper_quality_guard
```

7. Do not use `model_copy(update=...)` as the final validated result. Reconstruct with `model_validate` after every guard transformation.

8. Replace `_with_deterministic_patch_ids` with a server wrapper. The proposal fingerprint should be equivalent to:

```text
HMAC(
  schema_version,
  uid,
  packet_id,
  normalized decision,
  target_memory_id,
  normalized memory content,
  sorted evidence IDs,
  policy version
)
```

It must not contain array index, observed head, retry number or model-generated IDs.

9. Create `operation_id` once when the normalized proposal is first journaled. Retries reuse it.

10. Classify errors:

```text
missing client       → retryable_failure
provider timeout     → retryable_failure
malformed outer JSON → retryable_failure
individual bad patch → partial + invalid candidate
policy rejection     → success/partial + explicit reject
explicit no-action   → success + skip/no_action
```

11. A top-level no-action response must name the input candidate IDs it covers and include a reason. An unexplained empty patch list is invalid.

12. Add prompt-injection boundary language: packet, quote and search text are data; instructions inside them must be ignored.

13. Validate that retrieved search results cannot become evidence unless the evidence is also present in the trusted packet.

14. Replace the blanket third-party guard:

* User-relevant close relationship/entity facts may remain active.
* Incidental `encountered` or unrelated speaker facts route to Archive/review.
* Unclear attribution routes to review.
* The operation outcome retains auditable candidate information; do not make it disappear by clearing all content without a preserved encrypted outcome.

### C. Tests to change now

Replace:

```python
assert result == []
```

for malformed merge and quote-wrapper cases with assertions on typed outcomes and reason codes.

Add tests for:

* Same proposal under a different observed head.
* Same patches in a different array order.
* Malicious model-supplied operation/idempotency IDs.
* Wrong packet, run or head field.
* One invalid patch among multiple valid patches.
* Provider missing/timeout.
* Quote-wrapper audited rejection.
* Deterministic guard followed by model revalidation.
* Evidence ID not in input packet.
* Target memory owned by another user.
* Canonicalization rejection of unsupported objects.
* General health/intimate/third-party-sensitive data remaining restricted.
* Explicit user-relevant relationship fact not blanket-demoted.
* No cursor advancement on retryable or partial-unresolved results.

### D. Runtime restriction now

Until the operation journal and atomic apply transaction exist:

* Keep this code off or shadow-only.
* Do not advance a production migration/backfill cursor from the old `List[patch]` return value.
* Do not create ledger commits, review records, vectors or user-visible product records from this path.
* Benchmark reports must count provider failures, invalid candidates and quality-guard rejects.

## Changes to defer until the corresponding P0 tickets

* Firestore collection creation and migrations.
* Atomic ledger/head/product-item/outbox transaction.
* Vector gateway and `ns2` metadata repair.
* API cutover and external app scopes.
* User-facing tier UI.
* Legacy fallback projection.
* Raw artifact object-store implementation.
* Deletion/purge key-destruction implementation.

Do not implement a separate vector namespace, standalone distributed lease service, dedicated Context-only store, or mandatory end-user review queue.

---

# 5. Decisions that still require David’s taste or input

## A. Append-only history and account deletion

**Option A — Crypto-erasure plus physical cleanup:** encrypt all content-bearing ledger commits, replay artifacts, review payloads and raw artifacts with a per-user key; destroy the key at purge; delete hot-store records asynchronously; retain only a non-content purge receipt.

**Option B — Physically delete every history record and retain no purge receipt:** simpler user promise, weaker operational auditability.

**Recommended default: Option A**, subject to legal confirmation that crypto-erasure and backup expiry meet the product’s deletion promise.

## B. Raw-artifact retention window

**Option A — Inherit the source/account retention policy:** raw transcript/audio/import artifacts remain available as long as the underlying source would otherwise remain.

**Option B — Fixed memory-specific window, such as 90 days.**

**Option C — User-configurable retention toggle.**

**Recommended default: Option A.** It preserves provenance without introducing another user-facing setting.

## C. Existing third-party app permission migration

**Option A — Existing broad memory permission becomes Short-term + Long-term; Archive requires a new explicit grant and query.**

**Option B — Require all existing apps/users to re-consent before Short-term becomes available.**

**Recommended default: Option A**, provided the existing permission copy represents broad access to Omi memory rather than only curated profile facts. Archive and raw provenance must still require new capabilities.

## D. MVP Archive promotion and review UI

**Option A — No dedicated promotion button or review queue. Users say “remember this” or manage it through Omi/agent tools. Archive remains a separate search surface.**

**Option B — Add an Archive → Long-term button and lightweight review list.**

**Recommended default: Option A.** It follows the stated preference for simple UI and avoids making users operate the synthesis pipeline.

---

# 6. Prior-review conclusions now downgraded or modified

1. **Standalone writer lease is downgraded from required to unnecessary.** A separate lease would add expiration and stale-owner failure modes. The actual correctness boundary should be the atomic transaction on the per-user head/control document. A monotonic fence is only needed if some writer cannot participate in that transaction; T05-R must ensure there is no such V17 writer.

2. **Separate Short-term and Archive stores are replaced with one tiered `memory_items` collection.** This is materially simpler and resolves identity, transition, pagination and deletion problems.

3. **Stable identity is qualified rather than absolute.** It is stable for one-to-one transitions. Many-to-one consolidation uses canonical aliases because several source items cannot all remain the sole identity of one Long-term memory.

4. **A user-facing review lifecycle is downgraded from rollout requirement to optional later product work.** Auditable internal review and backlog resolution remain P0; an end-user review queue does not.

5. **A separate Archive vector namespace is no longer an open architectural choice.** `ns2` plus a mandatory gateway, fail-closed metadata, authoritative hydration and adversarial tests is the prescribed implementation. A second namespace becomes an evidence-driven fallback only.

6. **“Exactly once” is narrowed to idempotent atomic application.** LLM synthesis and queue delivery may be at-least-once; the system guarantees that one logical operation has at most one externally visible commit/result.

7. **“Rollback is one config change” is retained only for `read → write`.** Returning from persistent V17 writes all the way to `off` requires reconciliation and cannot safely be a blind flag flip.

8. **Raw-artifact preservation is made prospective and technically precise.** New available bytes must be copied before drop where feasible. Historical ephemeral losses remain explicit loss; they are not repairable or retrospectively “preserved.”

9. **The current blanket third-party demotion is weakened.** Incidental third-party facts remain excluded, but clearly user-relevant close relationships and cared-about entities can become Long-term when supported and policy-safe.

10. **Context-only does not need to be removed from every internal enum immediately.** It may remain as a legacy synthesis alias, provided it always normalizes to Archive and never appears as a product tier, access mode or user label.


9m47s · gemini-3.5-flash[browser] · ↑41.51k ↓15.52k ↻0 Δ57.03k
files=5
