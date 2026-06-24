# V17 Milestone 2 Oracle Review — Typed Synthesis and Operation Journal

**Date:** 2026-06-19  
**Milestone:** Typed synthesis outcomes, source-backed candidate contract, server-owned operation journal.  
**Initial verdict:** BLOCKED.  
**Resolution:** Required P0 fixes incorporated after this review: separate untrusted proposal schema, fail-closed evidence/memory reference checks, retryable all-invalid/empty/malformed semantics, no synthesis cursor-advance field, IDs generated after safety guards from complete logical payload, generation-scoped operation IDs, operation integrity/status validation, and secret-risk source candidates excluded from default access.

---

## Verdict: **BLOCKED**

There is a deterministic packet-loss path: the LLM is instructed using the final patch schema, which requires server-owned IDs; non-empty IDs are then rejected; and an all-invalid response is classified as `success` with `cursor_may_advance=True`. ([GitHub][1])

## Required fixes

1. **Separate the untrusted LLM proposal schema from the trusted patch schema.**

Create `DurableMemoryPatchProposal` without:

```python
patch_id
idempotency_key
packet_id
run_id
observed_head_commit_id
new_memory_id
evidence_refs
```

Use that proposal type in `PydanticOutputParser`, with `ConfigDict(extra="forbid")`. After validation and safety guards, construct the final `DurableMemoryPatch` entirely server-side. The current final schema requires several control fields while the synthesis loop rejects model-supplied values for two of them. ([GitHub][1])

2. **Fail closed on evidence and memory references.**

Change:

```python
if evidence_ids and allowed_evidence and not evidence_ids.issubset(allowed_evidence):
```

to a fail-closed check:

```python
if not evidence_ids.issubset(allowed_evidence):
```

For active/review proposals, require at least one canonical `evidence_id`. Do not accept model-authored `evidence_refs`; resolve quotes, source IDs, source versions, and artifact references from a server-owned `evidence_by_id` map.

Also validate `target_memory_id` and every `supersedes` ID against the retrieved same-user memory set. Repeat that authorization at the Milestone 3 apply gateway. Currently evidence-reference-only patches bypass packet membership checking, and target IDs need only be non-empty. ([GitHub][1])

3. **Correct terminal, retry, and cursor semantics.**

Required behavior:

```text
provider error                 -> retryable_failure
JSON/shape/schema error         -> retryable_failure
empty output without explicit no-op -> retryable_failure
all candidates invalid          -> retryable_failure
valid + invalid candidates      -> partial
explicit reject/skip/context outcomes -> success
```

After a configurable bounded retry count, the journal may convert the operation to `permanent_failure`/dead-letter.

Remove `cursor_may_advance` from the synthesis result, or rename it to something such as `synthesis_terminal`. Actual cursor advancement must only occur inside the Milestone 3 atomic apply/journal transaction. As written, empty and all-invalid output returns success and allows advancement, while a transient malformed model response is incorrectly permanent. ([GitHub][2])

4. **Generate IDs from the final guarded operation, using the complete logical body.**

Safety guards currently run **after** IDs are generated, even though they can change `decision`, `result_status`, and `memory_text`. The resulting IDs can describe a different operation from the returned patch. ([GitHub][2])

Apply this order:

```text
proposal validation
→ evidence/reference resolution
→ deterministic safety guards
→ final patch validation
→ canonical logical payload
→ server IDs
```

The canonical payload must include every field that affects persistent state, including at least:

```text
decision, result_status, target_memory_id, memory_text,
evidence_ids, predicate, arguments, supersedes,
confidence, relationship_to_user, subject_entity_id,
subject_label, aboutness
```

The current fingerprint omits `result_status`, `new_memory_id`, `supersedes`, `evidence_refs`, `confidence`, and `subject_label`, permitting distinct operations to collide. Prefer deriving `new_memory_id` from the final operation ID rather than accepting it from the model. ([GitHub][2])

5. **Scope journal identity by generation and enforce journal integrity.**

Add `account_generation` and `source_generation` to `build_operation_id()`. Otherwise an operation recreated after deletion/reset can collide with an operation committed in an older generation. Make generations mandatory rather than defaulting them to zero. ([GitHub][3])

Also:

* Verify on model construction that `operation_id` equals the server-recomputed ID.
* Use a typed/canonical JSON logical payload rather than unrestricted mutable `Dict[str, Any]`.
* Enforce legal status transitions and state invariants.
* Reject blank committed-head and error codes.
* Do not use `model_copy(update=...)` for state transitions; Pydantic explicitly does not validate update data. ([GitHub][3])

For example, `mark_committed("")` is currently accepted, and a committed operation can be changed back to retryable.

6. **Make source-backed candidates privacy- and time-safe.**

`risk_flags` currently has no effect on `default_access_candidate`; therefore a candidate marked `secret` or `credential` still defaults to short-term default access. Secret-risk candidates must enter an explicit restricted/hidden lane and must never be default-access candidates.

Use `AwareDatetime` for `captured_at` and `expires_at`, normalizing both to UTC before comparison. Plain `datetime` permits naive timestamps. ([GitHub][4])

7. **Remove the compatibility wrapper from any cursor-owning production path.**

`synthesize_durable_memory_patches()` still collapses typed failure results back to `[]`. Either migrate every production caller to `synthesize_durable_memory_patch_result()` or make the wrapper raise on non-terminal results. This commit changes no production caller files, so the new semantics are not yet demonstrated end-to-end. ([GitHub][2])

## Milestone 3 deferrals

These belong in Milestone 3 and need not be implemented in this patch:

* Atomic journal insertion, generation/head comparison, patch mutation, outbox write, and cursor advancement.
* Same-user database authorization of target and superseded memories.
* Projection/vector outbox consumers and retries.
* Search-gateway and read-policy enforcement.
* Deletion-fence transactions.
* Persisted retry scheduling, backoff, and dead-letter handling.

However, Milestone 2 must expose contracts that make those checks unavoidable; it must not return an “apply-ready” patch containing untrusted provenance or identifiers.

## Decisions needed from David

**None for P0.** I would set the policy to: explicit no-op required; all-invalid output retries; three failed synthesis attempts dead-letter with audit; mixed valid/invalid output may advance only after valid patches and invalid outcomes are atomically journaled; secret-risk candidates are never in default access.

[1]: https://github.com/BasedHardware/omi/blob/7a4259526f7aff6e7fbf1d64bdb98383b187a5a5/backend/models/v17_memory_contracts.py "omi/backend/models/v17_memory_contracts.py at 7a4259526f7aff6e7fbf1d64bdb98383b187a5a5 · BasedHardware/omi · GitHub"
[2]: https://github.com/BasedHardware/omi/blob/7a4259526/backend/utils/llm/durable_memory_patches.py "omi/backend/utils/llm/durable_memory_patches.py at 7a4259526f7aff6e7fbf1d64bdb98383b187a5a5 · BasedHardware/omi · GitHub"
[3]: https://github.com/BasedHardware/omi/blob/7a4259526f7aff6e7fbf1d64bdb98383b187a5a5/backend/models/v17_memory_operations.py "omi/backend/models/v17_memory_operations.py at 7a4259526f7aff6e7fbf1d64bdb98383b187a5a5 · BasedHardware/omi · GitHub"
[4]: https://github.com/BasedHardware/omi/commit/7a4259526 "feat: add V17 typed synthesis outcomes and operation journal · BasedHardware/omi@7a42595 · GitHub"


8m52s · gpt-5.5-pro[browser] · ↑10k ↓1.82k ↻0 Δ11.82k
files=1
