# V17 Memory Product Integration — Implementation Tickets

**Created:** 2026-06-18T20:08:24Z  
**Status:** Normative decisions baked in; GO for P0 amendment implementation, BLOCKED for production writes/read switch/vector/API cutover until P0 gates pass  
**Normative Architecture:** `docs/epics/v17_memory_normative_architecture.md`  
**Source Epic:** `docs/epics/v17_memory_product_integration_epic.md`  
**Decision Brief:** `docs/epics/v17_memory_product_integration_decision_brief.md`  
**Repos:**
- Product: `/root/workspace/omi-memory-ingestion-pipeline`
- Benchmark/eval: `/root/workspace/omi-ingestion-benchmark`

---

## Locked product decisions

| Decision | Direction |
|---|---|
| Product terms | **Short-term**, **Long-term**, **Archive** |
| Short-term | Fresh source-backed memory before/during L2 processing; default-access while fresh/relevant |
| Long-term | Stable L2/ledger-backed memory; default-access |
| Archive | Explicit-query historical/source-backed context; not default-access |
| Context-only | Not a normal user-visible tier; internal alias only, normalized to Archive/non-default outcome |
| Canonical store | One tiered `users/{uid}/memory_items/{memory_id}` collection for product items; no separate canonical Short-term/Archive stores |
| Long-term authority | Existing ledger remains Long-term source of truth; `memory_items` is transactional product projection |
| Existing `short_term` store | Legacy/adapter input only, not V17 canonical store |
| Stable identity | Opaque server `memory_id`; one-to-one tier transitions keep ID; many-to-one merges use canonical aliases |
| Rollout | Whitelist first; old memory behavior unchanged for everyone else; `read` is superset of `write` |
| Rollback | `read → write` uses V17-derived compatibility projection; `write → off` requires decommission reconciliation |
| Config | Keep simple external mode; hidden internal safety gates allowed |
| UI | Minimal labels/filter/provenance/edit/delete; users can manage memory by chatting with Omi |
| Agent mode | Memory-management tools: remember, forget, list, search, provenance, visibility/use policy, promote/demote, explicit archive search |
| Third-party/MCP/developer API | Existing broad memory permission maps to Long-term + Short-term; Archive/raw provenance require explicit capability + explicit query |
| Deletion | Follow current product behavior: memory deletion removes memory/projection/vector, not raw source; source/account deletion controls raw deletion |
| Vectors | KISS: existing `ns2` memory namespace only through fail-closed search gateway + authoritative hydration; separate namespace only evidence-driven fallback |
| Raw artifacts | Retain available raw/source artifacts indefinitely for now; copy ephemeral bytes durably where feasible; report already-missing losses honestly |

---

## P0 amendment queue to implement before production writes

The Oracle prescription and David decisions are baked in. The original T00–T28 queue remains useful background, but implementation must first update/split/reorder the queue as follows:

| Order | Ticket | Required decision |
|---:|---|---|
| 0 | A00 | Create normative architecture spec (`v17_memory_normative_architecture.md`) and make it source of truth over historical Epic wording. |
| 1 | T00-R | Define rollout capability state machine: `off`, `shadow`, `write`, `read`; `read` includes writes; rollback uses reconciliation. |
| 2 | T01-R | Define canonical memory state, stable identity, aliases, and derived access policy. |
| 3 | T02-R | Typed evidence/source versions/canonicalization/payload bounds; no untyped evidence persistence. |
| 4 | T03-R/T07-R | Replace separate canonical Short-term/Archive stores with unified `memory_items`; check indexes into source control. |
| 5 | T05-R | Mandatory write and search gateway audit; no direct product vector/ledger mutation bypasses. |
| 6 | T04-R | Central sensitive-data and consumer-access policy; deterministic checks beyond LLM flags. |
| 7 | T06-R | Account/source generation fences plus current-product deletion/export/purge semantics. |
| 8 | T26A | Backend kill switches, telemetry, and metric hygiene before any workers can run. |
| 9 | T28A | Incremental rollout safety verifier before write-mode tickets. |
| 10 | T10-R | Durable raw-artifact copy + lineage; retain available raw/source artifacts indefinitely for now. |
| 11 | T07A | Live source-backed ingestion and reprocessing into Short-term. |
| 12 | T13-R | Typed synthesis results + memory operation journal; no empty-list failures. |
| 13 | T27A | Base-anchored benchmark + online-shadow gate before Long-term apply. |
| 14 | T14/15-R | Atomic Long-term apply transaction + durable outbox; no standalone distributed writer lease. |
| 15 | T17-R | Review/non-active lifecycle; unresolved review defaults to Archive. |
| 16 | T19-R | Short-term lifecycle before write rollout; default expiry 30 days. |
| 17 | T20-R | Shared-namespace search gateway + projection/vector consistency. |
| 18 | T21-R | Unified read/ranking/pagination/rollback compatibility. |
| 19 | T22/23-R | Complete API semantics + app capabilities, including batch/import/public/shared/review routes. |

Production writes/read switch/vector changes/external API cutover remain blocked until the applicable P0 gates above are implemented and verified.

---

## Implementation progress log

| Date | Slice | Status | Verification | Next action |
|---|---|---|---|---|
| 2026-06-19 | T14/15-R Firestore transaction boundary, first production adapter slice | **Complete for first slice**: added `backend/database/v17_memory_apply_store.py`, authoritative reads for control/operation/evidence, atomic writes for operation/control/commit/memory_items/outbox, operation-only write for non-committed source/purge rejection, and `memory_evidence` collection constant. Added CI coverage in `backend/test.sh`. | `pytest tests/unit/test_v17_firestore_apply_store.py -q` → 2 passed; `pytest tests/unit/test_v17_firestore_indexes.py tests/unit/test_v17_normative_foundations.py tests/unit/test_v17_memory_contracts.py tests/unit/test_v17_durable_memory_patches.py tests/unit/test_v17_typed_synthesis.py tests/unit/test_v17_memory_operations.py tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_search_gateway.py tests/unit/test_v17_firestore_apply_store.py -q` → 59 passed; `pytest tests/unit/test_v17_*.py -q` → 80 passed, 1 pre-existing Pydantic deprecation warning. | Continue T14/15-R with emulator/concurrency coverage, authoritative target-memory reads, persisted idempotent committed-result replay, and stricter transaction read-set validation before declaring production write gate complete. |
| 2026-06-19 | T14/15-R persisted committed-result replay metadata | **Complete**: extended `MemoryOperation` to persist committed sequence, committed memory item IDs, and committed outbox event IDs; apply now records this metadata for normal commits and `skip_duplicate` barrier commits, so retry/idempotent paths can return stored commit identity instead of recomputing. | `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_memory_operations.py tests/unit/test_v17_firestore_apply_store.py -q` → 17 passed; `pytest tests/unit/test_v17_*.py -q` → 81 passed, 1 pre-existing Pydantic deprecation warning. | Continue T14/15-R with authoritative target-memory/evidence cross-generation reads and Firestore emulator/concurrency tests. |
| 2026-06-19 | T14/15-R authoritative target-memory read set | **Complete**: Firestore apply adapter now reads every operation target/superseded memory item inside the transaction, fails closed when a target is missing/cross-generation/non-active, and writes only the operation record for that non-committed rejection. | `pytest tests/unit/test_v17_firestore_apply_store.py -q` → 4 passed; `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_memory_operations.py tests/unit/test_v17_firestore_apply_store.py -q` → 19 passed; `pytest tests/unit/test_v17_*.py -q` → 83 passed, 1 pre-existing Pydantic deprecation warning. | Continue T14/15-R with Firestore emulator/concurrency tests, transaction retry behavior, and Security Rules/IAM bypass prevention. |
| 2026-06-19 | T14/15-R committed retry replay ordering | **Complete**: Firestore apply adapter now validates patch/operation binding through the pure apply contract and returns stored idempotent committed results before rereading mutable evidence or target memory state, so already-committed retries are not invalidated by later source purges or target tombstones. | `pytest tests/unit/test_v17_firestore_apply_store.py -q` → 5 passed; `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_memory_operations.py tests/unit/test_v17_firestore_apply_store.py -q` → 20 passed; `pytest tests/unit/test_v17_*.py -q` → 84 passed, 1 pre-existing Pydantic deprecation warning. | Continue T14/15-R with Firestore emulator/concurrency tests, transaction retry behavior, and Security Rules/IAM bypass prevention. |
| 2026-06-19 | T14/15-R deterministic transaction retry IDs | **Complete**: added a RED/GREEN regression proving a Firestore transaction retry over the same control head/operation/patch returns identical commit ID, materialized memory ID, outbox event IDs, and committed replay metadata. Replaced random fallback materialization IDs with deterministic server IDs derived from commit and patch identity. | `pytest tests/unit/test_v17_atomic_apply.py::test_firestore_transaction_retry_produces_identical_memory_commit_and_outbox_ids -q` → 1 passed; `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_firestore_apply_store.py -q` → 14 passed; `pytest tests/unit/test_v17_*.py -q` → 85 passed, 1 pre-existing Pydantic deprecation warning. | Continue T14/15-R with real Firestore emulator/concurrency tests, transaction fault injection, and Security Rules/IAM bypass prevention. |
| 2026-06-19 | T14/15-R Security Rules bypass guard | **Complete first checked-in guard**: added `firebase.json` and `firestore.rules` declaring V17 memory/control/operation/outbox/evidence paths server-owned, denying direct client create/update/delete so clients cannot bypass the apply gateway. Added CI coverage that rules/config exist and include every protected V17 collection. | `pytest tests/unit/test_v17_firestore_security_rules.py -q` → 1 passed. | Continue with real Firebase emulator rules tests and IAM/service-account deployment docs before declaring this production gate complete. |
| 2026-06-19 | T14/15-R Security Rules client read/write lockdown | **Complete**: tightened the checked-in V17 rules guard so protected V17 memory/control/operation/outbox/evidence paths deny direct client reads as well as writes; clients must use backend APIs while the Admin SDK/server path owns authoritative state. Added regression coverage preventing accidental reintroduction of signed-in direct client reads. | RED: `pytest tests/unit/test_v17_firestore_security_rules.py -q` → failed on missing full read/write deny; GREEN: `pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_indexes.py -q` → 2 passed; `pytest tests/unit/test_v17_*.py -q` → 86 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only. | Continue with real Firebase emulator rules tests and IAM/service-account deployment docs before declaring this production gate complete. |
| 2026-06-19 | T14/15-R materialized memory generation fence metadata | **Complete**: added RED/GREEN coverage that committed Long-term `memory_items` carry the authoritative control `account_generation`, then fixed materialization so future target-memory generation checks do not reject freshly committed items as generation `0`. Checked local emulator prerequisites honestly: `firebase` and `java` are absent, `npm` exists, so real Firebase emulator rules tests remain unrun. | RED: `pytest tests/unit/test_v17_atomic_apply.py::test_materialized_memory_item_carries_control_account_generation_for_future_fence_checks -q` → failed with `AssertionError: assert 0 == 7`; GREEN: same command → 1 passed; `black --line-length 120 --skip-string-normalization models/v17_memory_apply.py tests/unit/test_v17_atomic_apply.py` → 2 files left unchanged; `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_firestore_apply_store.py -q` → 15 passed; `pytest tests/unit/test_v17_*.py -q` → 87 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only; `command -v firebase || true; command -v java || true; command -v npm || true; firebase --version 2>/dev/null || true` → `/usr/bin/npm` only. | Continue T14/15-R with transaction fault-injection harness for write failures/retries, then IAM/service-account deployment docs and real Firebase emulator rules tests once Firebase CLI + Java are available. |
| 2026-06-19 | T14/15-R Firestore transaction fault-injection harness | **Complete**: upgraded the Firestore apply unit fake to stage writes until transaction commit, added local fallback transaction begin/commit/rollback semantics when the Google transactional decorator is unavailable, and added RED/GREEN adapter-path coverage injecting a `transaction.set(...)` failure after staged writes. The failure leaves authoritative docs unchanged; retry through `apply_long_term_patch_firestore` commits the same stored operation/control/replay IDs. | RED: `pytest tests/unit/test_v17_firestore_apply_store.py::test_firestore_transaction_set_failure_leaves_store_unchanged_and_retry_commits_same_ids -q` → failed with `Failed: DID NOT RAISE <class 'RuntimeError'>`; GREEN: same command → 1 passed; `black --line-length 120 --skip-string-normalization backend/database/v17_memory_apply_store.py backend/tests/unit/test_v17_firestore_apply_store.py` → 2 files reformatted; `pytest tests/unit/test_v17_atomic_apply.py tests/unit/test_v17_firestore_apply_store.py -q` → 16 passed; `pytest tests/unit/test_v17_*.py -q` → 88 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only. | Continue T14/15-R with IAM/service-account deployment docs and real Firebase emulator rules tests once Firebase CLI + Java are available; then continue emulator/concurrency coverage before declaring production write gate complete. |
| 2026-06-19 | T14/15-R IAM/service-account deployment static gate | **Complete for docs/static slice**: added `docs/epics/v17_firestore_iam_deployment.md` documenting the Admin SDK/server-owned boundary, client Firestore Rules denial, protected V17 collections, least-privilege service-account expectations, rollout/deployment checklist, rollback notes, and emulator prerequisites without claiming real cloud IAM validation. Added CI static coverage and `backend/test.sh` entry. Firebase emulator/cloud IAM validation remains unrun because prerequisites/project access are unavailable. | RED: `pytest tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → failed on missing doc; GREEN: same command → 1 passed; `black --line-length 120 --skip-string-normalization tests/unit/test_v17_firestore_iam_deployment_doc.py` → 1 file reformatted; `pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → 2 passed; `pytest tests/unit/test_v17_*.py -q` → 89 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only; `command -v firebase || true; command -v java || true; command -v npm || true; firebase --version 2>/dev/null || true` → `/usr/bin/npm` only. | Continue T14/15-R with real Firebase emulator Security Rules tests once Firebase CLI + Java are available, then add emulator/concurrency coverage before declaring the production Firestore write gate complete. |
| 2026-06-19 | T14/15-R real Firestore Rules emulator harness | **Complete**: provisioned local Firebase emulator tooling (`firebase-tools`/Rules test SDK dev dependencies plus Java 21 runtime), wired `firebase.json` Firestore emulator config and `npm run test:v17-firestore-rules:emulator`, and added a real emulator harness that starts the Firestore emulator and asserts signed-in client `get`, `set`, `update`, and `delete` are denied for every protected V17 collection. Added static CI coverage and `backend/test.sh` entry so harness coverage cannot drift. | Tooling check before provisioning: `command -v firebase` → empty, `command -v java` → empty, `command -v npm` → `/usr/bin/npm`, `npm --version` → 10.9.8, `node --version` → v22.22.3; RED: `pytest tests/unit/test_v17_firestore_emulator_harness.py -q` → failed on missing `backend/scripts/v17_firestore_rules_emulator_test.mjs`; GREEN: same command → 1 passed; `java -version && npm run test:v17-firestore-rules:emulator` → OpenJDK 21.0.11, Firestore Emulator v1.21.0 started, `PASS: signed-in client read/write denial asserted for 7 V17 collections`, script exited code 0; `black --line-length 120 --skip-string-normalization backend/tests/unit/test_v17_firestore_emulator_harness.py` → 1 file left unchanged; `pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → 3 passed; `pytest tests/unit/test_v17_*.py -q` → 90 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only. | Continue T14/15-R with emulator-backed transaction/concurrency coverage and cloud IAM/project deployment validation before declaring the production Firestore write gate complete. |
| 2026-06-19 | T14/15-R Firestore emulator transaction/concurrency harness | **Complete for emulator semantics slice**: added `npm run test:v17-firestore-transactions:emulator` and `backend/scripts/v17_firestore_transaction_emulator_test.mjs`, which uses the real Firestore emulator REST transaction API to seed the V17 control/operation layout, run two concurrent read-write transactions against the same apply state, assert exactly one transaction commits while the stale contender aborts, verify retry reads the committed operation/control replay state, and assert the losing commit/memory/outbox docs were not partially written. This validates Firestore emulator transaction serialization/no-half-commit semantics for the V17 collection layout; it does **not** claim Python adapter execution. Added static CI coverage and `backend/test.sh` entry. | RED: `pytest tests/unit/test_v17_firestore_transaction_emulator_harness.py -q` → failed on missing `backend/scripts/v17_firestore_transaction_emulator_test.mjs`; GREEN: same command → 1 passed; first real emulator attempt failed honestly with Rules `PERMISSION_DENIED`, fixed by using emulator owner/Admin auth; second attempt exposed transaction lock contention aborting the first sequential commit, fixed by committing both contenders concurrently and asserting one `200`/one `409`; `npm run test:v17-firestore-transactions:emulator` → Firestore Emulator started, `PASS: Firestore emulator transaction contention serialized V17 apply layout`, script exited code 0; `pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_emulator_harness.py tests/unit/test_v17_firestore_transaction_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → 4 passed; `pytest tests/unit/test_v17_*.py -q` → 91 passed, 1 pre-existing Pydantic deprecation warning; `npm run test:v17-firestore-rules:emulator && npm run test:v17-firestore-transactions:emulator` → both emulator scripts exited code 0 with rules denial PASS and transaction serialization PASS; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only. | Continue T14/15-R with cloud IAM/project deployment validation using real project credentials/access, then Python adapter-on-emulator coverage if safe Firestore Python emulator deps can be added without broad churn. |
| 2026-06-19 | T14/15-R Python Firestore apply adapter emulator coverage | **Complete**: added `backend/scripts/v17_firestore_python_apply_emulator_test.py` and `npm run test:v17-firestore-python-apply:emulator`, which starts the real Firestore emulator, seeds V17 control/operation/evidence docs through the Python Firestore client, executes `apply_long_term_patch_firestore`, and verifies committed control/head, operation replay metadata, materialized `memory_items`, commit document, projection/vector outbox docs, and idempotent retry replay. Added static harness coverage and `backend/test.sh` entry. No cloud IAM/project validation claimed. | RED: `pytest tests/unit/test_v17_firestore_python_adapter_emulator_harness.py -q` → failed on missing Python emulator harness; GREEN: same command → 1 passed; dependency check before install: `python3 - <<'PY' ... import google.cloud.firestore ... PY` → `ModuleNotFoundError No module named 'google'`; first install attempt `python3 -m pip install 'google-cloud-firestore==2.20.0' 'google-auth==2.32.0'` → blocked by externally-managed environment; installed exact existing backend requirement versions with `python3 -m pip install --break-system-packages 'google-cloud-firestore==2.20.0' 'google-auth==2.32.0'` → success; `npm run test:v17-firestore-python-apply:emulator` → Firestore Emulator started, `PASS: Python apply_long_term_patch_firestore committed and replayed V17 docs on Firestore emulator (...)`, script exited code 0; `pytest tests/unit/test_v17_firestore_python_adapter_emulator_harness.py tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_emulator_harness.py tests/unit/test_v17_firestore_transaction_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → 5 passed; `pytest tests/unit/test_v17_*.py -q` → 92 passed, 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only; `npm run test:v17-firestore-transactions:emulator` had one transient rerun failure (`[409,409]` instead of `[200,409]`) when chained after rules, then passed on immediate standalone rerun. | Continue T14/15-R by hardening the transaction emulator contention harness against transient double-abort/flakiness, then proceed to cloud IAM/project deployment validation with actual project credentials/access before declaring the production Firestore write gate complete. |
| 2026-06-19 | T14/15-R transaction emulator contention flake hardening | **Complete**: hardened `backend/scripts/v17_firestore_transaction_emulator_test.mjs` against the observed transient `[409, 409]` double-abort by adding bounded contention-round retries that only continue after proving control/operation replay state remains at the seeded pending base and no winner/loser commit, memory item, or outbox docs were partially written. Final success still requires exactly one `200` and one `409`, then verifies retry-read replay state and losing docs absent. Updated static harness coverage; no cloud IAM/project validation claimed. | `npm run test:v17-firestore-transactions:emulator` → Firestore Emulator started, `PASS: Firestore emulator transaction contention serialized V17 apply layout`, exit 0; `npm run test:v17-firestore-rules:emulator && npm run test:v17-firestore-transactions:emulator && npm run test:v17-firestore-python-apply:emulator` → all three emulator scripts exited code 0 with expected rules-denial logs and Python apply replay PASS; transaction repeat loop x3 → three `PASS: Firestore emulator transaction contention serialized V17 apply layout`; `pytest tests/unit/test_v17_firestore_python_adapter_emulator_harness.py tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_emulator_harness.py tests/unit/test_v17_firestore_transaction_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → 5 passed in 0.12s; `pytest tests/unit/test_v17_*.py -q` → 92 passed, 1 pre-existing Pydantic deprecation warning; `black --line-length 120 --skip-string-normalization backend/tests/unit/test_v17_firestore_transaction_emulator_harness.py` → 1 file left unchanged; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only. | Next: proceed to cloud IAM/project deployment validation only when real project credentials/access are available; otherwise continue the next V17 P0 gate without claiming cloud validation. |
| 2026-06-19 | T17-R non-active route persistence/idempotency core store | **Complete for first narrow slice**: added durable Firestore-backed `non_active_memory_routes` collection model/store for review, Archive, internal `context_only`, reject, hidden, and skip outcomes. Store uses deterministic idempotency-key document IDs, persists source IDs/reason/route/run ID/patch ID/audit metadata, rejects same-key payload mismatches, and writes no `memory_items`, so these outcomes are excluded from default Long-term reads by construction. Added `backend/test.sh` coverage. | RED: `pytest tests/unit/test_v17_non_active_routes.py -q` → `ModuleNotFoundError: No module named 'database.v17_non_active_memory_routes'`; GREEN: same command → 3 passed; `black --line-length 120 --skip-string-normalization database/v17_non_active_memory_routes.py database/v17_collections.py tests/unit/test_v17_non_active_routes.py` → 3 files left unchanged; `pytest tests/unit/test_v17_non_active_routes.py -q && pytest tests/unit/test_v17_*.py -q` → 3 passed, then 95 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: wire patch applier/review queue to call this store for actual review/archive/reject/hidden/skip decisions, and expose the collection to no-silent-data-loss / benchmark audit reports. |
| 2026-06-19 | T17-R patch/review queue non-active route-store integration | **Complete for narrow integration slice**: added `persist_non_active_route_for_patch(...)` seam in `v17_patch_adapter` so actual durable patch decisions `review`, internal `context_only`, `reject`, and `skip_duplicate` map into `non_active_memory_routes` with deterministic idempotency keys, source IDs, reason, run ID, patch ID, and audit metadata while active decisions do not write non-active outcomes. Wired `review_queue.resolve_review_conflict` so user/staff `reject` resolutions persist `reject` outcomes and timeout/low-confidence `drop` resolutions persist `skip` outcomes; no `context_only` user-visible tier was introduced and default Long-term `memory_items` remain untouched by these routes. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_patch_adapter.py -q` → failed with `ImportError: cannot import name 'persist_non_active_route_for_patch'`; RED: `pytest tests/unit/test_v17_review_queue_non_active_routes.py -q` → failed on missing `review_queue.persist_non_active_route_outcome`; GREEN: `pytest tests/unit/test_v17_patch_adapter.py tests/unit/test_v17_review_queue_non_active_routes.py -q` → 10 passed, 1 pre-existing Pydantic deprecation warning; `black --line-length 120 --skip-string-normalization backend/database/review_queue.py backend/utils/memory/v17_patch_adapter.py backend/tests/unit/test_v17_patch_adapter.py backend/tests/unit/test_v17_review_queue_non_active_routes.py` → 2 files reformatted, 2 files left unchanged; `pytest tests/unit/test_v17_non_active_routes.py tests/unit/test_v17_patch_adapter.py tests/unit/test_v17_review_queue_non_active_routes.py -q && pytest tests/unit/test_v17_*.py -q` → 13 passed, then 99 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: expose `non_active_memory_routes` to no-silent-data-loss / benchmark audit reports, then locate and wire remaining production Archive/hidden emitters. |
| 2026-06-19 | T17-R non-active route audit/report seam | **Complete for narrow reporting slice**: added `utils/memory/v17_non_active_route_audit.py`, a no-DB helper that consumes fetched `non_active_memory_routes` docs and emits audit-visible counts/evidence for review, Archive, internal `context_only`, reject, hidden, and skip routes. The report marks each route as an accounted terminal outcome, surfaces `counts_by_route`, preserved vs observable-loss defaults, remediation state, missing expected sources, duplicate terminal outcomes, uid mismatches, and fails red if any non-active route is default Long-term visible. Default Long-term reads remain unaffected because the helper only consumes route-store docs passed by admin/benchmark callers. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_non_active_route_audit.py -q` → `ModuleNotFoundError: No module named 'utils.memory.v17_non_active_route_audit'`; GREEN: same command → 2 passed; `black --line-length 120 --skip-string-normalization utils/memory/v17_non_active_route_audit.py tests/unit/test_v17_non_active_route_audit.py` → 1 file reformatted, 1 file left unchanged; `pytest tests/unit/test_v17_non_active_routes.py tests/unit/test_v17_non_active_route_audit.py tests/unit/test_v17_patch_adapter.py tests/unit/test_v17_review_queue_non_active_routes.py -q && pytest tests/unit/test_v17_*.py -q` → 15 passed, then 101 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: wire an admin/no-silent-data-loss or benchmark caller to fetch `non_active_memory_routes` and invoke this helper, then locate and wire remaining production Archive/hidden emitters. |
| 2026-06-19 | T17-R non-active route audit caller/fetcher seam | **Complete for narrow caller integration slice**: added `utils/memory/v17_non_active_route_report.py`, a real admin/benchmark service seam that fetches `users/{uid}/non_active_memory_routes` (optionally scoped by `run_id`) and invokes `build_non_active_route_audit_report(...)`. The returned report exposes accounted terminal outcomes and counts for review, Archive, internal `context_only`, reject, hidden, and skip, without querying or changing default Long-term `memory_items`; `context_only` remains audit-only/internal and Archive remains explicit/product-tier. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_non_active_route_report.py -q` → `ModuleNotFoundError: No module named 'utils.memory.v17_non_active_route_report'`; GREEN: same command → 2 passed; `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_non_active_route_report.py backend/tests/unit/test_v17_non_active_route_report.py` → 2 files left unchanged; `pytest tests/unit/test_v17_non_active_routes.py tests/unit/test_v17_non_active_route_audit.py tests/unit/test_v17_non_active_route_report.py tests/unit/test_v17_patch_adapter.py tests/unit/test_v17_review_queue_non_active_routes.py -q && pytest tests/unit/test_v17_*.py -q` → 17 passed, 1 warning, then 103 passed, 1 warning in 0.79s; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: wire this fetcher into the concrete admin/no-silent-data-loss endpoint or benchmark report runner, then locate and persist remaining production Archive/hidden emitters. |
| 2026-06-19 | T17-R non-active route concrete admin endpoint integration | **Complete for narrow endpoint slice**: added a production FastAPI admin route `GET /v17/admin/users/{uid}/non-active-route-report` that requires `ADMIN_KEY`, parses optional `run_id` and comma-delimited expected source IDs, calls `fetch_non_active_route_audit_report(...)`, and returns JSON audit counts/evidence for review, Archive, internal `context_only`, reject, hidden, and skip. The endpoint reads only `users/{uid}/non_active_memory_routes` through the existing fetcher and does not touch default Long-term `memory_items`; `context_only` remains audit-only/internal and Archive remains explicit/product-tier. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py -q` → failed with `ModuleNotFoundError: No module named 'routers.v17_memory_admin'`; GREEN: same command → 2 passed, then 3 passed after adding route-registration coverage; `black --line-length 120 --skip-string-normalization backend/routers/v17_memory_admin.py backend/tests/unit/test_v17_non_active_route_admin_endpoint.py backend/main.py` → 3 files left unchanged; `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_non_active_route_report.py tests/unit/test_v17_non_active_route_audit.py -q && pytest tests/unit/test_v17_*.py -q` → 7 passed, then 106 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: locate and persist remaining production Archive/hidden emitters, then add a benchmark/no-silent-data-loss runner hook if the external benchmark repo is the next chosen seam. |
| 2026-06-19 | T17-R L1 Archive emitter route persistence | **Complete for narrow Archive emitter slice**: located the production V17 L1 Archive emitter in `utils.llm.working_memory.extract_l1_memory_archive_items_from_text(...)` and wired emitted `L1MemoryArchiveItem`s to `non_active_memory_routes` as `NonActiveRoute.archive`. The idempotency key is deterministic (`l1-archive:{source_id}:{archive_id}`), carries source/run/archive identity, marks Archive as preserved/non-observable-loss/product-tier evidence, and does not materialize default Long-term `memory_items`. Search found no additional concrete V17 hidden-memory production emitter to wire in this slice; current `hidden` matches are read-policy derivation/test fixtures or unrelated subscription/app visibility toggles, so hidden route persistence remains pending until a real memory lifecycle hidden emitter appears. | RED: `pytest tests/unit/test_v17_working_memory_extractor.py::test_l1_archive_extractor_persists_archive_route_outcomes_with_deterministic_identity -q` → failed first with `AttributeError: ... working_memory has no attribute 'persist_non_active_route_outcome'`; GREEN: same command → 1 passed; `black --line-length 120 --skip-string-normalization backend/utils/llm/working_memory.py backend/tests/unit/test_v17_working_memory_extractor.py` → 1 file reformatted, 1 file left unchanged; initial root-path verification attempt `pytest tests/unit/test_v17_working_memory_extractor.py ...` from repo root failed honestly with `ERROR: file or directory not found` because tests live under `backend/`; rerun from `backend/`: `pytest tests/unit/test_v17_working_memory_extractor.py tests/unit/test_v17_non_active_routes.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q && pytest tests/unit/test_v17_*.py -q` → 11 passed, then 107 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: add the benchmark/no-silent-data-loss runner hook that consumes `fetch_non_active_route_audit_report(...)`, and keep watching for any newly introduced concrete hidden lifecycle emitter to persist as `NonActiveRoute.hidden`. |
| 2026-06-19 | T17-R benchmark/no-silent-data-loss non-active route hook | **Complete for benchmark-runner hook slice**: inspected the product repo first and found the product admin/fetcher seam already available; the concrete no-silent-data-loss/benchmark owner is `/root/workspace/omi-ingestion-benchmark/scripts/v17_verifier.py`. Wired that runner to call the product `fetch_non_active_route_audit_report(...)` when invoked with `--non-active-route-uid`, optionally scoped by `--non-active-route-run-id` and comma-delimited `--expected-source-ids`. The runner now writes `non_active_route_audit.json/.md` and mirrors `non_active_route_audit_status` plus `non_active_route_counts` into `summary.json/.md`, making review, Archive, internal `context_only`, reject, hidden, and skip terminal outcomes visible to benchmark/no-silent-data-loss audits. The product default Long-term read path remains unaffected; the benchmark hook only imports the product report fetcher and reads `non_active_memory_routes`. | RED: `/root/workspace/omi-ingestion-benchmark: pytest tests/test_v17_verifier.py::test_non_active_route_audit_hook_consumes_product_fetcher -q` → failed with `ImportError: cannot import name 'run_non_active_route_audit'`; GREEN/format: `black --line-length 120 --skip-string-normalization scripts/v17_verifier.py tests/test_v17_verifier.py` → 2 files reformatted; `pytest tests/test_v17_verifier.py -q` → 4 passed; smoke: `python3 scripts/v17_verifier.py --observations /tmp/missing_obs.jsonl --patches /tmp/missing_patches.jsonl --fresh-search /tmp/missing_search.jsonl --replayed-search /tmp/missing_search.jsonl --output-dir /tmp/v17_verifier_hook_smoke && python3 - <<'PY' ... PY` → `summary_status not_run`, `route_status not_run`, `route_counts {'archive': 0, 'context_only': 0, 'hidden': 0, 'reject': 0, 'review': 0, 'skip': 0}`. No fake benchmark/cloud output claimed; product regression: `/root/workspace/omi-memory-ingestion-pipeline/backend: pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_non_active_route_report.py tests/unit/test_v17_non_active_route_audit.py -q && pytest tests/unit/test_v17_*.py -q` → 7 passed, then 107 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from product repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T17-R slice: run the verifier with real product Firestore credentials/run IDs when available, continue watching for a concrete V17 hidden lifecycle emitter to persist `hidden` outcomes, and then close remaining no-silent-data-loss gates with real migration/backfill fixtures. |
| 2026-06-19 | T19-R Short-term lifecycle pure policy/evaluator | **Complete for first narrow slice**: added `backend/utils/memory/short_term_lifecycle.py`, a pure deterministic evaluator for `short_term` `V17MemoryItem`s. Fresh non-expired Short-term remains default-accessible; expired/stale Short-term is default-excluded and marked `requires_lifecycle_decision`; L2-processed items route to `promote_to_long_term`, `archive`, or `reject_or_hide` only from an explicit disposition; source-tombstoned/purged items route to `source_tombstoned` and are default-excluded. Decisions carry stable audit metadata (`policy_version`, item identity, tier/status/processing/source state, expiry/evaluation time, disposition, reason) and are idempotent for identical inputs. Added `backend/tests/unit/test_short_term_lifecycle.py` and CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_short_term_lifecycle.py -q` → `ModuleNotFoundError: No module named 'utils.memory.short_term_lifecycle'`; GREEN: `pytest tests/unit/test_short_term_lifecycle.py -q` → 5 passed; `black --line-length 120 --skip-string-normalization utils/memory/short_term_lifecycle.py tests/unit/test_short_term_lifecycle.py` → 2 files reformatted; `pytest tests/unit/test_short_term_lifecycle.py -q && pytest tests/unit/test_v17_*.py -q` → 5 passed, then 107 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19-R slice: wire this evaluator into `database/product_memory_items.py`/read filtering (or create the product memory item seam if still absent) so default reads use the policy, then add the lifecycle worker/audit persistence for idempotent transitions. |
| 2026-06-19 | T19-R default read product-memory item seam | **Complete for narrow read-filter slice**: added `backend/database/product_memory_items.py` with `filter_default_product_memory_items(...)`, a minimal authoritative-item helper that keeps default reads to lifecycle-eligible Short-term plus policy-eligible Long-term. It wires `evaluate_short_term_lifecycle(...)`, exposes per-item access decisions plus lifecycle audit metadata for later worker persistence, includes fresh Short-term, excludes expired/stale Short-term, excludes L2-processed Short-term until an explicit lifecycle disposition routes it, excludes source-tombstoned Short-term, and continues to keep Archive out of default reads. Tightened the pure evaluator so processed Short-term without disposition is default-excluded and requires lifecycle decision. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_product_memory_items.py -q` → `ModuleNotFoundError: No module named 'database.product_memory_items'`; first GREEN attempt exposed implementation/test issues and failed with stale reason mismatch plus missing non-active evidence reason; fixed helper/test; GREEN: `pytest tests/unit/test_v17_product_memory_items.py -q` → 2 passed; `black --line-length 120 --skip-string-normalization database/product_memory_items.py utils/memory/short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py tests/unit/test_short_term_lifecycle.py` → 2 files reformatted, 2 files left unchanged; `pytest tests/unit/test_short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 7 passed, then 109 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19-R slice: add lifecycle worker/audit persistence for idempotent Short-term transitions, then wire concrete default read callers/search paths to fetch authoritative `memory_items` through this helper. |
| 2026-06-19 | T19-R Short-term lifecycle worker/audit idempotency seam | **Complete for narrow worker/audit slice**: added `backend/jobs/v17_short_term_lifecycle_worker.py`, a pure/fake-store-testable lifecycle worker seam that evaluates Short-term items, skips fresh default-visible no-op records, and persists deterministic transition/audit records for stale/expired, L2-dispositioned, and source-tombstoned Short-term items. Transition records include uid, memory item ID, outcome, reason, run ID, evaluated timestamp, source refs, policy/audit metadata, deterministic idempotency key, and payload fingerprint. The fake store enforces create-if-absent behavior and rejects same-key/different-fingerprint collisions so rerunning the same item/evaluation/run does not duplicate transition records. Archive/reject/source-tombstoned transitions remain default-excluded by lifecycle/read policy; no Archive default-read exposure was added. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_short_term_lifecycle_worker.py -q` → `ModuleNotFoundError: No module named 'jobs'`; GREEN: same command → 2 passed; `black --line-length 120 --skip-string-normalization jobs/v17_short_term_lifecycle_worker.py tests/unit/test_v17_short_term_lifecycle_worker.py` → 1 file reformatted, 1 file left unchanged; `pytest tests/unit/test_v17_short_term_lifecycle_worker.py tests/unit/test_short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 9 passed, then 111 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19-R slice: add a concrete Firestore-backed lifecycle transition store/runner or wire concrete default read callers/search paths to fetch authoritative `memory_items` through the product read helper, without making stale Short-term or Archive default-visible. |
| 2026-06-19 | T19-R Short-term lifecycle Firestore transition store | **Complete for concrete persistence slice**: added `FirestoreShortTermLifecycleTransitionStore` for the Short-term lifecycle worker. It writes transition/audit records to deterministic `users/{uid}/short_term_lifecycle_transitions/stl_<hash>` docs, replays identical idempotency keys as existing records, and fails closed on same-key/different-fingerprint drift. Stored records include uid, memory item ID, outcome, reason, run ID, evaluated timestamp, source refs, audit metadata, idempotency key, fingerprint, created timestamp, and explicit default/Archive non-visibility flags. Added the new protected V17 collection to `V17Collections`, Firestore Rules/static rules coverage, emulator rules harness, and `backend/test.sh`. No default-read visibility change was made; stale Short-term and Archive remain default-excluded by existing lifecycle/read policy. | RED: `pytest tests/unit/test_v17_short_term_lifecycle_firestore_store.py -q` → failed with `ImportError: cannot import name 'FirestoreShortTermLifecycleTransitionStore'`; GREEN/focused: `pytest tests/unit/test_v17_short_term_lifecycle_firestore_store.py tests/unit/test_v17_short_term_lifecycle_worker.py tests/unit/test_short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py tests/unit/test_v17_firestore_security_rules.py -q` → 12 passed; regression: `pytest tests/unit/test_v17_*.py -q` → 113 passed, 1 pre-existing Pydantic deprecation warning; `black --line-length 120 --skip-string-normalization jobs/v17_short_term_lifecycle_worker.py tests/unit/test_v17_short_term_lifecycle_firestore_store.py tests/unit/test_v17_short_term_lifecycle_worker.py tests/unit/test_v17_firestore_security_rules.py database/v17_collections.py` → 1 file reformatted then all unchanged on rerun; `python3 backend/scripts/scan_async_blockers.py` → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`); `npm run test:v17-firestore-rules:emulator` → Firestore Emulator started, `PASS: signed-in client read/write denial asserted for 8 V17 collections`, script exited code 0. | Next T19-R slice: wire a concrete lifecycle runner/scheduler to fetch authoritative Short-term `memory_items` and use the Firestore store, or wire concrete default read/search callers through `filter_default_product_memory_items(...)` so stale Short-term and Archive are excluded in real product responses. |
| 2026-06-19 | T19-R concrete Short-term lifecycle Firestore runner | **Complete for narrow concrete runner slice**: added `fetch_short_term_memory_items_firestore(...)` to query authoritative `users/{uid}/memory_items` for Short-term tier only, validate uid consistency, and sort deterministic inputs; added `run_short_term_lifecycle_firestore(...)` to evaluate those authoritative Short-term items and persist required transitions via `FirestoreShortTermLifecycleTransitionStore`. Fresh/default-visible Short-term no-ops are skipped, stale/expired Short-term gets an idempotent transition record, reruns replay existing transition docs, and Archive/Long-term docs are excluded at the fetch seam so Archive cannot become default-visible through the runner. | RED: `pytest tests/unit/test_v17_short_term_lifecycle_firestore_store.py -q` → failed with `ImportError: cannot import name 'fetch_short_term_memory_items_firestore'`; GREEN: same command → 4 passed; `black --line-length 120 --skip-string-normalization jobs/v17_short_term_lifecycle_worker.py tests/unit/test_v17_short_term_lifecycle_firestore_store.py` → 1 file reformatted, 1 file left unchanged; focused/regression: `pytest tests/unit/test_v17_short_term_lifecycle_firestore_store.py tests/unit/test_v17_short_term_lifecycle_worker.py tests/unit/test_short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py tests/unit/test_v17_firestore_security_rules.py -q && pytest tests/unit/test_v17_*.py -q` → 14 passed, then 115 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19-R slice: wire a scheduler/cron or production admin/job entrypoint to call `run_short_term_lifecycle_firestore(...)`, and/or wire concrete default read/search callers through `filter_default_product_memory_items(...)` so product responses exclude stale Short-term and Archive by default. |
| 2026-06-19 | T19-R Short-term lifecycle admin/job entrypoint | **Complete for narrow production entrypoint slice**: added `POST /v17/admin/users/{uid}/short-term-lifecycle/run` to the existing V17 admin router. The route requires `ADMIN_KEY`, validates a non-empty `run_id`, ISO timezone-aware optional `evaluated_at`, and a bounded `limit` (1–1000), then calls `run_short_term_lifecycle_firestore(...)` with the concrete Firestore client. The Firestore runner/fetcher now accepts the same limit and continues querying only Short-term `memory_items`; Long-term and Archive remain excluded at the fetch seam, stale Short-term transitions persist with `default_access_allowed=false`, and `archive_default_visible=false` is returned/written so the entrypoint does not make stale Short-term or Archive default-visible. | RED: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_short_term_lifecycle_firestore_store.py -q` → failed with missing POST route, missing `run_short_term_lifecycle_firestore` router seam, and `TypeError: run_short_term_lifecycle_firestore() got an unexpected keyword argument 'limit'`; GREEN: same command → 10 passed; `black --line-length 120 --skip-string-normalization routers/v17_memory_admin.py jobs/v17_short_term_lifecycle_worker.py tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_short_term_lifecycle_firestore_store.py` → 4 files left unchanged; focused/regression: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_short_term_lifecycle_firestore_store.py tests/unit/test_v17_short_term_lifecycle_worker.py tests/unit/test_short_term_lifecycle.py tests/unit/test_v17_product_memory_items.py tests/unit/test_v17_firestore_security_rules.py -q && pytest tests/unit/test_v17_*.py -q` → 20 passed, then 118 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19-R slice: wire concrete default read/search callers through `filter_default_product_memory_items(...)`, or add scheduler/Cloud Run cron invocation around this admin/job entrypoint if deployment patterns are available. |
| 2026-06-19 | T19-R concrete default read/search caller integration | **Complete for narrow read/search callable slice**: added product-memory query seams in `backend/utils/memory/v17_read_api.py`. `query_default_product_memory_items(...)` now accepts authoritative `V17MemoryItem` records, calls `filter_default_product_memory_items(...)` before query matching, and returns default product output only for lifecycle/default-policy-visible Short-term and Long-term items. Added separate `query_archive_product_memory_items(...)` for explicit archive-capable callers only, keeping Archive out of default responses while preserving an explicit Archive search path. Legacy durable/working/L1 archive helpers were left unchanged. | RED: `pytest tests/unit/test_v17_read_api.py -q` → failed with `ImportError: cannot import name 'query_archive_product_memory_items'`; GREEN: `pytest tests/unit/test_v17_read_api.py -q` → 7 passed; format command from repo root succeeded (`black --line-length 120 --skip-string-normalization backend/utils/memory/v17_read_api.py backend/tests/unit/test_v17_read_api.py` → 2 files reformatted) but the immediately chained root-relative pytest command failed honestly with `ERROR: file or directory not found: tests/unit/test_v17_read_api.py`; rerun from `backend/`: `pytest tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 9 passed, then 120 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire a concrete router/service fetcher to load `users/{uid}/memory_items` and call `query_default_product_memory_items(...)` for product API responses/search, then add pagination/ranking compatibility without exposing stale Short-term or Archive by default. |
| 2026-06-19 | T19/T21 concrete product memory read service fetcher | **Complete for narrow service/fetcher slice**: added `utils/memory/v17_product_memory_read_service.py`, which fetches authoritative `users/{uid}/memory_items`, coerces docs to `V17MemoryItem`, validates uid consistency, sorts deterministically by newest `updated_at` then `memory_id`, calls `query_default_product_memory_items(...)`, and paginates after default filtering/query matching. Tests prove fresh Short-term and Long-term are returned while stale Short-term and Archive are excluded by default; Archive remains separate through the existing explicit archive seam. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_product_memory_read_service.py -q` → failed with `ModuleNotFoundError: No module named 'utils.memory.v17_product_memory_read_service'`; first implementation attempt failed honestly because importing `database._client.db` at module import required ADC (`DefaultCredentialsError`), fixed by requiring caller/router to pass the concrete `db_client`; GREEN: `pytest tests/unit/test_v17_product_memory_read_service.py -q` → 3 passed; `black --line-length 120 --skip-string-normalization utils/memory/v17_product_memory_read_service.py tests/unit/test_v17_product_memory_read_service.py` → 1 file reformatted, 1 file left unchanged; focused/regression: `pytest tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 12 passed, then 123 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire this service into a concrete product/router endpoint or chat/MCP/developer search caller with explicit policy construction and, if Archive is exposed, keep it capability-gated through `query_archive_product_memory_items(...)`. |
| 2026-06-19 | T19/T21 concrete product memory router endpoint integration | **Complete for narrow product endpoint slice**: added `GET /v17/memory/search` in a dedicated V17 product router and registered it in `backend/main.py`. The endpoint requires the authenticated user dependency, constructs `MemoryAccessPolicy.for_omi_chat(archive_capability=False)` explicitly, calls `fetch_default_product_memory_search(...)` with the concrete Firestore client, returns policy metadata plus pagination counts, and keeps `archive_default_visible=false`. Archive is not exposed by this route; stale Short-term and Archive remain filtered by the read service. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_product_memory_router.py -q` → failed with `ModuleNotFoundError: No module named 'routers.v17_memory_product'`; GREEN: same command → 3 passed initially, then 4 passed after adding main-registration coverage; `black --line-length 120 --skip-string-normalization routers/v17_memory_product.py tests/unit/test_v17_product_memory_router.py ../backend/main.py` → 2 files reformatted, 1 file left unchanged; focused/regression: `pytest tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 16 passed, then 127 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire concrete chat/MCP/developer search callers or add capability-gated explicit Archive product route only where policy requires it; keep default route Archive-free and legacy behavior untouched. |
| 2026-06-19 | T19/T21 capability-gated explicit Archive product route | **Complete for narrow Archive route slice**: added `fetch_archive_product_memory_search(...)` to the V17 product read service and `GET /v17/memory/archive/search` to the product router. The route is separate from default `/v17/memory/search`, requires authenticated uid plus an explicit `include_archive=true` opt-in before constructing `MemoryAccessPolicy.for_omi_chat(archive_capability=True)`, and rejects missing capability with 403 before Firestore access. Archive responses query authoritative `users/{uid}/memory_items`, return only explicit Archive matches via `query_archive_product_memory_items(...)`, keep `archive_default_visible=false`, and leave legacy/chat/MCP/developer APIs untouched while concrete caller selection remains pending. | RED: `pytest tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_product_memory_router.py -q` → failed at collection with `ImportError: cannot import name 'fetch_archive_product_memory_search'`; GREEN: same command → 11 passed; `black --line-length 120 --skip-string-normalization backend/routers/v17_memory_product.py backend/utils/memory/v17_product_memory_read_service.py backend/tests/unit/test_v17_product_memory_router.py backend/tests/unit/test_v17_product_memory_read_service.py` → 1 file reformatted, 3 files left unchanged; focused/regression/async audit: `cd backend && pytest tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → 20 passed, then 131 passed with 1 pre-existing Pydantic deprecation warning, async audit exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire one mature concrete chat/MCP/developer caller to default V17 product memory search behind explicit policy/rollout controls, keeping Archive unavailable by default and legacy behavior untouched unless tested. |
| 2026-06-19 | T19/T21 MCP default V17 memory search adapter/caller seam | **Complete for narrow MCP caller-adapter slice**: added `search_v17_default_mcp_memories(...)` in `utils/mcp_memories.py` and wired `/v1/mcp/memories/search` to attempt that adapter before the legacy vector path. The adapter requires explicit V17 read rollout capabilities plus the MCP default-memory grant before Firestore access, constructs `MemoryAccessPolicy(consumer=mcp, app_has_default_memory_grant=True, archive_capability=False)`, and calls the default V17 product memory read service. Tests prove fresh Short-term and Long-term V17 product memory are returned in deterministic service order while stale Short-term and Archive are excluded; disabled rollout/default grant returns `None` without reading Firestore so legacy MCP behavior remains the default path. Archive remains unavailable by default and the explicit product Archive route remains separate. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'search_v17_default_mcp_memories' from 'utils.mcp_memories'`; GREEN: same command → 2 passed; `black --line-length 120 --skip-string-normalization backend/utils/mcp_memories.py backend/routers/mcp.py backend/tests/unit/test_v17_mcp_memory_adapter.py` → 3 files left unchanged; focused/regression: `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 15 passed, then 133 passed with 1 pre-existing Pydantic deprecation warning; async audit: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). Exploratory legacy MCP unit command `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_mcp_search_memories.py -q` is currently blocked by missing local `fastapi` dependency before collection, so no router-specific legacy result was claimed. | Next T19/T21 slice: add a persisted rollout-state reader for MCP so V17 read capabilities can be enabled from authoritative per-user gates rather than adapter/test injection, while keeping Archive separate and default-disabled. |
| 2026-06-19 | T19/T21 MCP persisted rollout-state reader | **Complete for narrow persisted-gate slice**: added `read_v17_mcp_default_memory_rollout(...)` in `utils/mcp_memories.py` and switched `/v1/mcp/memories/search` from env-derived rollout injection to the server-owned `users/{uid}/memory_control/state` document before invoking the V17 MCP default-memory adapter. The reader derives `V17RolloutState`/read capabilities from persisted mode, epoch, fallback, writes-blocked, and stage-gate fields, derives the MCP default-memory grant from server-side grants (`grants.mcp.default_memory` or `mcp_default_memory_grant`), and fails closed to legacy MCP search for missing, malformed, uid-mismatched, or grant-less docs without reading `users/{uid}/memory_items`. Archive remains default-disabled (`archive_capability=False`) regardless of persisted archive fields; the explicit Archive product route remains separate. | RED: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'read_v17_mcp_default_memory_rollout' from 'utils.mcp_memories'`; GREEN: same command → 4 passed; focused/regression: `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 17 passed, then 135 passed with 1 pre-existing Pydantic deprecation warning; `black --line-length 120 --skip-string-normalization backend/utils/mcp_memories.py backend/routers/mcp.py backend/tests/unit/test_v17_mcp_memory_adapter.py` → 3 files left unchanged; `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). Exploratory legacy MCP command `pytest tests/unit/test_mcp_search_memories.py tests/unit/test_v17_mcp_memory_adapter.py -q` is blocked in this local environment by missing `fastapi` before collection, so no legacy-router result was claimed. | Next T19/T21 slice: add concrete persisted-policy integration for one chat/developer caller or add observability/admin inspection for per-user V17 read grant decisions; keep stale Short-term and Archive excluded from default reads. |
| 2026-06-19 | T19/T21 admin read-rollout decision observability endpoint | **Complete for narrow admin observability slice**: added `GET /v17/admin/users/{uid}/read-rollout-decision` to the existing V17 admin router. The route requires `ADMIN_KEY`, reads only the server-owned `users/{uid}/memory_control/state` document through the same `read_v17_mcp_default_memory_rollout(...)` decision helper used by `/v1/mcp/memories/search`, and formats the shared decision with `build_v17_mcp_default_memory_rollout_observability(...)` so admin inspection and MCP behavior cannot drift. The response reports enabled/disabled state, fallback reason, mode, V17 read capability, legacy-read authority, MCP default-memory grant, derived capabilities, and `archive_default_visible=false` / `archive_capability=false`. Missing, malformed, uid-mismatched, and grant-less states fail closed and tests assert no `users/{uid}/memory_items` collection read occurs. | RED: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py -q` → 4 failed, 4 passed: missing route plus `AttributeError: module 'routers.v17_memory_admin' has no attribute 'get_v17_read_rollout_decision'`; GREEN: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py -q` → 8 passed; `black --line-length 120 --skip-string-normalization backend/routers/v17_memory_admin.py backend/utils/mcp_memories.py backend/tests/unit/test_v17_non_active_route_admin_endpoint.py` → reformatted test file, other 2 unchanged; focused/regression: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 25 passed, then 138 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire a concrete chat/developer caller to persisted V17 default product memory read policy, keeping stale Short-term and Archive excluded by default; consider adding ops metrics around admin-inspected decisions once a rollout dashboard owner exists. |
| 2026-06-19 | T19/T21 developer default V17 memory caller integration | **Complete for narrow developer caller slice**: added `utils/memory/v17_developer_memory_adapter.py` and wired `GET /v1/dev/user/memories` to attempt persisted V17 default product memory reads before the legacy `users/{uid}/memories` path when no legacy category filter is requested. The adapter reads only server-owned `users/{uid}/memory_control/state` first, requires V17 read capability plus a developer default-memory grant (`grants.developer.default_memory`/`grants.developer_api.default_memory` or `developer_default_memory_grant`), constructs a `developer_api` `MemoryAccessPolicy` with `archive_capability=false`, then calls the default V17 product memory read service over authoritative `users/{uid}/memory_items`. Missing, malformed, disabled, uid-mismatched, or grant-less state returns `None` before any `memory_items` collection read so the developer endpoint keeps legacy behavior. Tests prove fresh Short-term + Long-term are returned while stale Short-term and Archive are excluded by default; explicit Archive remains separate. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → failed with `ModuleNotFoundError: No module named 'utils.memory.v17_developer_memory_adapter'`; first GREEN attempt exposed an ADC import issue from `models.memories.MemoryCategory`, fixed by keeping the adapter free of Firestore-initializing model imports; GREEN: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → 5 passed; exploratory legacy developer pagination command `pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_dev_api_memories_pagination.py -q` is blocked in this local environment by missing `fastapi` before collection of the legacy test; focused/regression after formatting: `pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → 22 passed, then 143 passed with 1 pre-existing Pydantic deprecation warning; async audit exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_developer_memory_adapter.py backend/routers/developer.py backend/tests/unit/test_v17_developer_memory_adapter.py` → reformatted test file, other 2 unchanged. | Next T19/T21 slice: wire the chat retrieval/tool memory caller through the same persisted default-read policy, or factor the MCP/developer rollout readers into a shared default-read decision helper before adding more consumers. |
| 2026-06-19 | T19/T21 shared persisted default-read rollout helper | **Complete for narrow shared-helper refactor**: added `utils/memory/v17_default_read_rollout.py` as the shared persisted default-read decision helper for MCP and developer API reads. It reads/normalizes server-owned `users/{uid}/memory_control/state`, derives V17 read capabilities once, supports consumer-specific default-memory grants (`grants.mcp.default_memory`/`mcp_default_memory_grant`, `grants.developer.default_memory`/`grants.developer_api.default_memory`/`developer_default_memory_grant`), and fails closed for missing, malformed, uid-mismatched, disabled, unsupported, or grant-less states before any `memory_items` read. Refactored `utils/mcp_memories.py` and `utils/memory/v17_developer_memory_adapter.py` to delegate persisted rollout parsing to the helper while preserving their public reader names/properties. Archive remains default-disabled (`archive_capability=false`) and the explicit Archive route remains separate; legacy fallback behavior is unchanged. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_default_read_rollout_decision.py -q` → `ModuleNotFoundError: No module named 'utils.memory.v17_default_read_rollout'`; GREEN/focused: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py -q` → 11 passed; format: `black --line-length 120 --skip-string-normalization utils/memory/v17_default_read_rollout.py utils/memory/v17_developer_memory_adapter.py utils/mcp_memories.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py` → 2 files reformatted, 4 files left unchanged; focused/regression: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 24 passed, then 145 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire a safe mature chat retrieval/default-memory caller through the shared helper and product read service, or add consumer-specific observability for developer API decisions without broadening default Archive access. |
| 2026-06-19 | T19/T21 Omi chat default V17 memory retrieval adapter/caller integration | **Complete for narrow chat caller slice**: added `utils/memory/v17_chat_memory_adapter.py` and wired the mature LangChain chat `search_memories_tool` to attempt persisted V17 default product-memory reads before the legacy vector-memory path. The adapter delegates rollout/grant parsing to shared `utils/memory/v17_default_read_rollout.py`, which now supports `omi_chat`/`chat` default-memory grants (`grants.omi_chat.default_memory`, `grants.chat.default_memory`, `omi_chat_default_memory_grant`, `chat_default_memory_grant`). Missing, malformed, disabled, uid-mismatched, or grant-less rollout state returns `None` before any `users/{uid}/memory_items` read so legacy chat behavior remains the fallback. Enabled rollout constructs an `omi_chat` `MemoryAccessPolicy` with `archive_capability=false` and calls the default V17 product memory read service; tests prove fresh Short-term and Long-term are returned while stale Short-term and Archive are excluded. Archive remains unavailable by default and the explicit Archive product route remains separate. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_chat_memory_adapter.py -q` → `ModuleNotFoundError: No module named 'utils.memory.v17_chat_memory_adapter'`; GREEN: same command → 5 passed; format: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_chat_memory_adapter.py backend/utils/memory/v17_default_read_rollout.py backend/utils/retrieval/tools/memory_tools.py backend/tests/unit/test_v17_chat_memory_adapter.py` → 1 file reformatted, 3 files left unchanged; focused/regression: `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py -q && pytest tests/unit/test_v17_*.py -q` → 29 passed, then 150 passed with 1 pre-existing Pydantic deprecation warning; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: add consumer-specific observability for chat default-memory decisions or wire another concrete agent/tool caller with the same shared helper, keeping Archive explicit-only and legacy fallback unchanged. |
| 2026-06-19 | T19/T21 multi-consumer admin read-rollout observability | **Complete for narrow admin observability enhancement**: extended `GET /v17/admin/users/{uid}/read-rollout-decision` to read `users/{uid}/memory_control/state` once and report shared default-read decisions for `mcp`, `developer_api`, and `omi_chat`. The route still requires `ADMIN_KEY`, delegates per-consumer parsing/grant evaluation to `utils/memory/v17_default_read_rollout.py`, and never reads `users/{uid}/memory_items`. The response now surfaces per-consumer enabled/disabled state, fallback reason, default-memory grant, V17 read capability, legacy-read authority, capabilities, and `archive_default_visible=false` / `archive_capability=false`; missing/malformed/uid-mismatched/no-grant states fail closed for every consumer. The legacy MCP-specific observability formatter now delegates to the shared formatter. | RED: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py -q` → 2 failed, 6 passed with `KeyError: 'consumers'` before implementation; GREEN/focused: `pytest tests/unit/test_v17_non_active_route_admin_endpoint.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_mcp_memory_adapter.py -q` → 14 passed; format: `black --line-length 120 --skip-string-normalization routers/v17_memory_admin.py utils/memory/v17_default_read_rollout.py utils/mcp_memories.py tests/unit/test_v17_non_active_route_admin_endpoint.py` → 2 files reformatted, 2 files unchanged; focused/regression: `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_product_memory_read_service.py tests/unit/test_v17_read_api.py tests/unit/test_v17_product_memory_items.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q && pytest tests/unit/test_v17_*.py -q` → 37 passed, then 150 passed with 1 pre-existing Pydantic deprecation warning; async audit: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: add the next concrete agent/tool caller behind the shared persisted default-read helper or add telemetry counters for these per-consumer decisions; keep Archive explicit-only and stale Short-term default-excluded. |
| 2026-06-19 | T19/T21 default-read rollout audit counters | **Complete for narrow lightweight telemetry/audit slice**: added pure local audit-event/counter builders in `utils/memory/v17_default_read_rollout.py` and surfaced them in `GET /v17/admin/users/{uid}/read-rollout-decision`. The audit payload records one event per consumer (`mcp`, `developer_api`, `omi_chat`) with uid, source path, consumer, enabled/fallback outcome, fallback reason, default-memory grant, V17 read capability, `archive_default_visible=false`, and `archive_capability=false`, plus aggregate enabled/fallback counters by consumer/reason. It is local/admin observability only (no external telemetry dependency), reads the persisted rollout state once, and never queries `users/{uid}/memory_items`; Archive remains explicit-only and stale Short-term remains default-excluded at existing read-service seams. | RED: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q` → collection failed with `ImportError: cannot import name 'build_v17_default_read_rollout_audit_events'`; GREEN/focused: same command → 11 passed; format: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/tests/unit/test_v17_default_read_rollout_decision.py backend/tests/unit/test_v17_non_active_route_admin_endpoint.py` → 3 files left unchanged; regression: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q && pytest tests/unit/test_v17_*.py -q` → 11 passed, then 151 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire the next concrete agent/tool caller through the shared persisted default-read helper, or add Prometheus/ops export for these counters only after choosing a low-cardinality production metric shape; keep Archive explicit-only and stale Short-term default-excluded. |
| 2026-06-19 | T19/T21 default-read rollout low-cardinality metrics export seam | **Complete for narrow ops/export seam slice**: added `render_v17_default_read_rollout_metrics(...)` in `utils/memory/v17_default_read_rollout.py`, a pure Prometheus text renderer for the existing local default-read rollout audit counters. The metric uses only low-cardinality labels (`consumer`, `outcome`, `fallback_reason` bucket), deliberately excludes uid/source_path/app/source labels, buckets unknown dynamic fallback strings as `other`, and is surfaced on the existing admin read-rollout decision response as `decision_metrics_prometheus`. The seam consumes already-aggregated local counters, reads only `users/{uid}/memory_control/state` through the existing helper, and never queries `users/{uid}/memory_items`; Archive remains explicit-only and stale Short-term remains default-excluded at existing read-service seams. | RED: `pytest tests/unit/test_v17_default_read_rollout_decision.py -q` → collection failed with `ImportError: cannot import name 'render_v17_default_read_rollout_metrics'`; GREEN: same command → 5 passed; format: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/tests/unit/test_v17_default_read_rollout_decision.py` → 1 file reformatted, 1 file left unchanged; focused/regression: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q && pytest tests/unit/test_v17_*.py -q` → 13 passed, then 153 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T19/T21 slice: wire another concrete agent/tool caller through the shared persisted helper/product read service, or promote this callable metrics seam into a central `/metrics` collector only after selecting the right process-lifetime aggregation model; keep labels low-cardinality and Archive explicit-only. |
| 2026-06-19 | T20 existing-namespace V17 vector metadata/filter gateway seam | **Complete for first narrow T20 slice**: added `database/v17_vector_metadata.py` with deterministic V17-prefixed vector IDs, authoritative hydration metadata builder, strict default/explicit-Archive Pinecone filter builders, and fail-closed vector-hit parsing into existing `SearchVectorHit`s. Wired `database/vector_db.py` with `query_v17_memory_vector_candidates(...)` over existing `ns2` so V17 vector queries use tier-safe metadata filters and return candidates only; callers must still hydrate authoritative `memory_items` through the existing V17 search gateway before returning results. Default filter is Short-term + Long-term only and excludes Archive, non-active, source-inactive, unknown visibility, and restricted sensitivity metadata; explicit Archive filter is separate. Legacy `search_memories_by_vector(...)` behavior remains untouched. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_vector_metadata.py -q` → failed with `ModuleNotFoundError: No module named 'database.v17_vector_metadata'`; RED: `pytest tests/unit/test_v17_vector_filters.py -q` → failed with `AttributeError: module 'v17_vector_filter_vector_db' has no attribute 'query_v17_memory_vector_candidates'` after stubbing heavy deps; GREEN: `pytest tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py -q` → 6 passed; format: `black --line-length 120 --skip-string-normalization database/v17_vector_metadata.py database/vector_db.py tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py` → 3 files reformatted, 1 unchanged; focused/regression: `pytest tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py tests/unit/test_v17_search_gateway.py -q && pytest tests/unit/test_v17_*.py -q` → 9 passed, then 159 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: wire a hydrated V17 vector search service/caller that invokes `query_v17_memory_vector_candidates(...)`, fetches authoritative `users/{uid}/memory_items`, calls `hydrate_and_filter_vector_hits(...)`, and returns default-visible results only; keep default Archive-free and legacy vector behavior untouched. |
| 2026-06-19 | T20 hydrated V17 vector search service/gateway | **Complete for narrow service slice**: added `utils/memory/v17_vector_search_service.py` with `fetch_default_v17_vector_memory_search(...)`, a fake-injectable service that calls the existing `query_v17_memory_vector_candidates(...)` seam in `SearchMode.default`, loads authoritative `users/{uid}/memory_items`, hydrates candidates through `hydrate_and_filter_vector_hits(...)`, and returns only default-visible V17 memory items with vector scores/decisions. Tests prove stale Short-term and Archive are excluded by authoritative item policy even when vector candidates include them, fresh Short-term and Long-term are included, vector ranking is preserved after filtering, `vector_rejected_count` is surfaced, and `archive_default_visible=false`. Legacy `search_memories_by_vector(...)` remains untouched; explicit Archive search remains separate and was not exposed by default. Added CI coverage in `backend/test.sh`. | RED: `pytest tests/unit/test_v17_vector_search_service.py -q` → failed with `ModuleNotFoundError: No module named 'utils.memory.v17_vector_search_service'`; first GREEN attempt exposed missing local `pinecone` import through eager `database.vector_db` import, fixed with a top-level optional default-query binding while preserving injected tests and production default behavior; GREEN: `pytest tests/unit/test_v17_vector_search_service.py -q` → 2 passed; format: `black --line-length 120 --skip-string-normalization utils/memory/v17_vector_search_service.py tests/unit/test_v17_vector_search_service.py` → 1 file reformatted, 1 file left unchanged; focused/regression: `pytest tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py tests/unit/test_v17_search_gateway.py tests/unit/test_v17_product_memory_read_service.py -q && pytest tests/unit/test_v17_*.py -q` → 15 passed, then 161 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing async audit findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: wire this hydrated vector service into one concrete V17 product/search caller or route behind the existing persisted rollout/read policy, keeping default Archive-free and legacy vector behavior available as fallback. |
| 2026-06-19 | T20 concrete product vector search route integration | **Complete for narrow route/caller slice**: added `GET /v17/memory/vector/search` to the V17 product memory router. The endpoint requires authenticated uid, reads persisted server-owned `users/{uid}/memory_control/state` through the shared default-read rollout helper for `omi_chat`, fails closed with rollout observability when V17 reads/default-memory grant are missing, and only then calls `fetch_default_v17_vector_memory_search(...)` with `MemoryAccessPolicy.for_omi_chat(archive_capability=false)`. Tests prove disabled/missing rollout reads only the rollout state and does not call vector search or `memory_items`; enabled rollout delegates to the hydrated vector service, preserves vector ranking, returns fresh Short-term + Long-term, and excludes stale Short-term + Archive by default. Legacy `search_memories_by_vector(...)` remains untouched and explicit Archive search remains separate. | RED: `pytest tests/unit/test_v17_product_memory_router.py -q` → 3 failed, 7 passed (`/v17/memory/vector/search` route and `search_v17_vector_memory` missing); GREEN: `pytest tests/unit/test_v17_product_memory_router.py -q` → 10 passed; format: `black --line-length 120 --skip-string-normalization routers/v17_memory_product.py tests/unit/test_v17_product_memory_router.py` → 2 files left unchanged after final guard; focused/regression: `pytest tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py tests/unit/test_v17_search_gateway.py tests/unit/test_v17_product_memory_read_service.py -q && pytest tests/unit/test_v17_*.py -q` → 25 passed, then 164 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: wire the same hydrated vector path into the next mature chat/MCP/developer retrieval caller behind the shared persisted rollout helper, or add an explicit Archive vector route only if product policy requires it; keep default Archive-free. |
|| 2026-06-19 | T20 Omi chat hydrated vector caller integration | **Complete for narrow chat vector caller slice**: added `search_v17_default_chat_memories_vector_text(...)` to `utils/memory/v17_chat_memory_adapter.py` and wired the mature LangChain `search_memories_tool` to attempt hydrated V17 vector search before the legacy `vector_db.find_similar_memories(...)` path. The adapter reads persisted server-owned `users/{uid}/memory_control/state` through the shared default-read rollout helper for `omi_chat`, returns `None` before vector search or `users/{uid}/memory_items` reads when rollout is disabled/missing/malformed or the default-memory grant is absent, and only then calls `fetch_default_v17_vector_memory_search(...)` with an `omi_chat` policy and `archive_capability=false`. Tests prove ranking follows vector scores after hydration, fresh Short-term + Long-term are returned, stale Short-term and Archive are excluded by default, and legacy vector behavior remains the fallback when V17 is not enabled. | RED: `pytest tests/unit/test_v17_chat_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'search_v17_default_chat_memories_vector_text'`; GREEN: `pytest tests/unit/test_v17_chat_memory_adapter.py -q` → 7 passed; format/focused/regression: `black --line-length 120 --skip-string-normalization utils/memory/v17_chat_memory_adapter.py utils/retrieval/tools/memory_tools.py tests/unit/test_v17_chat_memory_adapter.py && pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q` → 3 files left unchanged, 24 passed, then 166 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: wire another concrete MCP/developer vector caller through `fetch_default_v17_vector_memory_search(...)` behind the shared persisted helper, or add capability-gated explicit Archive vector search only if product policy requires it; keep default Archive-free. |
| 2026-06-19 | T20 MCP hydrated vector caller integration | **Complete for narrow MCP REST vector caller slice**: added `search_v17_default_mcp_memories_vector(...)` in `utils/mcp_memories.py` and wired `/v1/mcp/memories/search` to try hydrated V17 vector search after the shared persisted MCP rollout read and before the legacy `vector_db.find_similar_memories(...)` path (with the existing product-read adapter retained as a V17 fallback). The adapter is fake-injectable via `vector_query`, requires V17 read capability plus MCP default-memory grant from `users/{uid}/memory_control/state`, constructs an MCP `MemoryAccessPolicy` with `archive_capability=false`, and calls `fetch_default_v17_vector_memory_search(...)`. Disabled rollout/default-grant returns `None` before vector or `users/{uid}/memory_items` reads; hydrated service coverage plus MCP adapter tests prove fresh Short-term/Long-term are returned in vector-score order while stale Short-term and Archive remain excluded by default. Legacy vector behavior remains untouched for non-enabled callers. | RED: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'search_v17_default_mcp_memories_vector'`; GREEN: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → 6 passed, then final focused after route-order coverage → 7 passed; format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/utils/mcp_memories.py backend/routers/mcp.py backend/tests/unit/test_v17_mcp_memory_adapter.py && cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → 3 files left unchanged, 14 passed, 169 passed with 1 pre-existing Pydantic deprecation warning, async audit exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: wire a developer/API vector endpoint or another concrete MCP transport (SSE) through the same hydrated V17 vector service and persisted rollout helper; keep Archive explicit-only/default-unavailable. |
| 2026-06-19 | T20 MCP SSE hydrated vector caller integration | **Complete for narrow distinct MCP transport slice**: wired the streamable HTTP/SSE MCP `search_memories` tool in `routers/mcp_sse.py` to read the shared persisted MCP rollout state (`users/{uid}/memory_control/state`) and call `search_v17_default_mcp_memories_vector(...)` before the legacy `vector_db.find_similar_memories(...)` path. This reuses the hydrated V17 vector service via the existing MCP adapter, so disabled/missing/malformed/no-grant rollout returns `None` before vector or `users/{uid}/memory_items` reads, enabled rollout uses `fetch_default_v17_vector_memory_search(...)` with `archive_capability=false`, and service/adapter coverage continues proving fresh Short-term/Long-term inclusion, stale Short-term/Archive exclusion, vector-score ordering, and legacy fallback for non-enabled callers. Archive remains unavailable by default and no explicit Archive SSE vector route was added. | RED: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → 1 failed, 7 passed (`test_mcp_sse_search_tool_wires_v17_vector_adapter_before_legacy_vector_search` missing `read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)`); GREEN: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → 8 passed; format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/routers/mcp_sse.py backend/tests/unit/test_v17_mcp_memory_adapter.py && cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → 2 files left unchanged, 15 passed, 170 passed with 1 pre-existing Pydantic deprecation warning, async audit exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 vector slice: wire a developer API vector endpoint/caller if a mature endpoint exists, or add explicit capability-gated Archive vector search only after product decision; keep default Archive unavailable. |
| 2026-06-19 | T20 developer API hydrated vector endpoint/caller integration | **Complete for narrow developer API vector slice**: added `search_v17_default_developer_memories_vector(...)` and a concrete `GET /v1/dev/user/memories/vector/search` endpoint. The endpoint uses the existing developer memories auth dependency, reads persisted server-owned `users/{uid}/memory_control/state` through the shared default-read rollout helper for `developer_api`, fails closed with 403 when V17 reads/default-memory grant are disabled/missing/malformed, and only then calls the hydrated `fetch_default_v17_vector_memory_search(...)` service with `archive_capability=false`. Tests prove disabled/no-grant paths return `None` before vector lookup or `users/{uid}/memory_items` reads; enabled rollout preserves vector-score ranking after authoritative hydration and returns fresh Short-term + Long-term while excluding stale Short-term and Archive by default. No explicit Archive developer vector route was added and legacy developer memory listing remains untouched except for the existing V17 default-read fallback. | RED: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'search_v17_default_developer_memories_vector'`; first GREEN run exposed route-order/timestamp issues (`2 failed, 6 passed`), fixed by scoping the route-order assertion to the new endpoint and using `updated_at`/`captured_at` fallback for vector service item timestamps; GREEN: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → 8 passed; format/focused/regression: `black --line-length 120 --skip-string-normalization utils/memory/v17_developer_memory_adapter.py routers/developer.py tests/unit/test_v17_developer_memory_adapter.py && pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q` → 1 file reformatted, 2 unchanged; 15 passed, then 173 passed with 1 pre-existing Pydantic deprecation warning; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next T20 slice: prepare an honest vector readiness/remaining-gates milestone (Oracle/cloud/benchmark only if actually run) or wire only another mature concrete vector caller; keep Archive unavailable by default. |
| 2026-06-19 | T20 vector readiness / remaining-gates milestone artifact | **Complete for milestone-prep slice**: added `docs/epics/v17_t20_vector_readiness_remaining_gates.md` summarizing the concrete T20 default vector implementation chain (`0f22ed289`, `aaee67639`, `4e11d7be8`, `fe67f2380`, `010b7306e`, `e09aafc20`, `a8aac6806`), current default-vector surfaces, tested guarantees, and remaining non-production gates. The artifact states that default vector paths keep stale Short-term and Archive excluded, Archive remains explicit-only with no explicit Archive vector route added, rollout disabled/missing/malformed/no-grant states fail closed before vector/`memory_items` reads where applicable, and legacy vector fallback remains untouched. It also records that Oracle/cloud/real Pinecone/Firestore/benchmark validation was not run or claimed. | `git show -s --format='%h %s'` for the T20 commit chain → exact seven commits found; `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_default_read_rollout_decision.py -q` → 15 passed in 0.11s; `cd backend && pytest tests/unit/test_v17_*.py -q` → 173 passed, 1 pre-existing Pydantic deprecation warning in 1.28s; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0, pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next: submit T20/T19/T21 default-read/vector state for Oracle milestone review; apply required fixes before production cutover. If review is deferred, proceed to the next ticket-source-of-truth P0 gate (`T22/23-R` API semantics/app capabilities) without adding new default Archive/vector exposure. |
| 2026-06-19 | T20/T19/T21 Oracle milestone review | **Complete for review-gate slice; production rollout BLOCKED**: ran `/usr/local/bin/consult-oracle` session `v17-t20-vector-review` against the T20 readiness artifact, ticket source of truth, key default-read/vector code paths, and focused tests. Oracle verdict: ready for architecture/milestone review but **NO-GO for production read/vector cutover**. P0s recorded in `docs/epics/v17_t20_oracle_milestone_review.md`: shared V17 route authorization and server-authorized Archive capability, explicit read-decision semantics instead of unsafe legacy downgrade, T22/T23 write/read convergence, mandatory vector freshness/purge fences, real shared-`ns2` legacy isolation proof, app/key/scope-granular third-party authorization, production-shaped vector hydration/overfetch, and missing real cloud/Pinecone/Firestore/benchmark/metrics evidence. | Oracle run → 10m51s, `gpt-5.5-pro[browser]`, `files=15`, `↑103.84k ↓4.2k ↻0 Δ108.03k`, with model-selection caveat `requested=Pro; resolved=(unavailable); status=unavailable; strategy=select; verified=no`; docs-only verification: `python3 - <<'PY' ...` → artifact/ticket/readiness files exist and contain the Oracle block marker; `git diff --check` → clean. Parent's prior focused/regression verification remains preserved in `docs/epics/v17_t20_vector_readiness_remaining_gates.md` (`15 passed`, then `173 passed, 1 warning`; async scan exit 0 with pre-existing findings only). | Next: do not proceed to production cutover. Start the next narrow implementation slice from Oracle P0-1/P0-2: shared versioned V17 read authorization/Archive capability plus explicit `USE_V17`/`USE_LEGACY_SAFE`/`DENY_MEMORY`/`SHADOW_ONLY` decision semantics and tests. |
| 2026-06-19 | Oracle P0-1/P0-2 explicit read-decision product-route slice | **Complete for first narrow Oracle P0 fix slice; production rollout still BLOCKED**: introduced shared `V17ReadDecision` semantics (`USE_V17`, `USE_LEGACY_SAFE`, `DENY_MEMORY`, `SHADOW_ONLY`) on `V17DefaultReadRolloutDecision`, surfaced the explicit decision in observability/audit payloads, and made malformed/missing/disabled/no-grant rollout states classify as `DENY_MEMORY` rather than implicit legacy fallback. Added an explicit opt-in `legacy_safe_v17_default_read_rollout_decision(...)` constructor for callers that are intentionally legacy-safe, and classified shadow-enabled/read-disabled granted state as `SHADOW_ONLY`. Applied the explicit decision to product `/v17/memory/search` and the existing product `/v17/memory/vector/search`: both now require shared persisted Omi-chat rollout/grant state to return `USE_V17` before any `users/{uid}/memory_items` or vector read; non-`USE_V17` returns 403 with rollout observability. Archive remains default-unavailable and the existing Archive route is unchanged (still explicit route/flag only; persisted server-authorized Archive capability remains a separate P0-1 follow-up). | RED: `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py -q` → collection failed with `ImportError: cannot import name 'V17ReadDecision'`; GREEN: same command after implementation → `17 passed in 0.10s`; focused/regression attempt: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → first command `19 passed`, regression initially `1 failed, 174 passed, 1 warning` because admin audit expected payload lacked new `read_decision`; after updating admin expectations: `pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_non_active_route_admin_endpoint.py -q && pytest tests/unit/test_v17_*.py -q` → `27 passed`, then `175 passed, 1 warning in 1.18s`; format: `black --line-length 120 --skip-string-normalization ...` → `4 files left unchanged` after final formatting; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next: continue Oracle P0-1 by replacing the current explicit-flag-only Archive product route with persisted/server-authorized Archive capability plus explicit query, then proceed to P0-3/T22 write/read convergence and P0-4 vector fences. |
| 2026-06-19 | Oracle P0-1 persisted/server-authorized Archive product-route capability | **Complete for narrow Oracle P0-1 Archive sub-slice; production rollout still BLOCKED**: added shared persisted Archive capability parsing in `utils/memory/v17_default_read_rollout.py` via `read_v17_archive_read_rollout(...)`. The explicit Archive route now requires both `include_archive=true` explicit intent and server-owned `users/{uid}/memory_control/state` authorization: Omi-chat V17 read decision must be `USE_V17`, default-memory grant must be present, and nested/top-level Archive capability must be boolean `true`. Missing control state, malformed Archive capability, V17 reads disabled, no default grant, or no Archive grant all return 403 before Archive `users/{uid}/memory_items` reads. Default product read and vector routes still construct `archive_capability=false`, so Archive remains default-unavailable and no new Archive vector exposure was added. | RED: `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py -q` → collection failed with `ImportError: cannot import name 'read_v17_archive_read_rollout'`; first GREEN attempt after implementation → `2 failed, 18 passed` because explicit `DENY_MEMORY` Archive denial reasons were not surfaced as `fallback_reason`; after fixing fallback reason precedence: `20 passed in 0.09s`; format/focused/regression: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/routers/v17_memory_product.py backend/tests/unit/test_v17_default_read_rollout_decision.py backend/tests/unit/test_v17_product_memory_router.py && cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → 4 files left unchanged, `22 passed in 0.11s`, then `178 passed, 1 warning in 1.18s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next Oracle slice: continue P0-2/P0-1 across fallback callers and add the global emergency kill switch independent of per-user Firestore reads; do not claim production cutover until all Oracle P0s and real cloud/Pinecone/Firestore/benchmark/metrics evidence are complete. |
| 2026-06-19 | Oracle P0-1 global V17 product-read kill switch/gate | **Complete for narrow Oracle P0-1 global gate sub-slice; production rollout still BLOCKED**: added a shared fake-injectable global read gate in `utils/memory/v17_default_read_rollout.py` (`V17_GLOBAL_READ_GATE_PATH = memory_control/v17_global_read_gate`, `read_v17_global_read_gate(...)`). The gate is independent of per-user `users/{uid}/memory_control/state` and fails closed unless persisted global config has boolean `v17_reads_enabled=true` and boolean `kill_switch_active=false`. Missing config, malformed config, disabled global reads, or active kill switch all return explicit `DENY_MEMORY` reasons. Product `/v17/memory/search`, `/v17/memory/vector/search`, and explicit `/v17/memory/archive/search?include_archive=true` now check this global gate before per-user rollout reads, vector calls, or `memory_items` reads. Enabled global gate preserves existing per-user default/Archive decisions; Archive remains default-unavailable and still requires explicit intent plus persisted Archive capability. | RED: `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py -q` → collection failed with `ImportError: cannot import name 'V17_GLOBAL_READ_GATE_PATH' from 'utils.memory.v17_default_read_rollout'`; GREEN/focused after implementation: same command → `24 passed in 0.09s`; format/focused/regression: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/routers/v17_memory_product.py backend/tests/unit/test_v17_default_read_rollout_decision.py backend/tests/unit/test_v17_product_memory_router.py && cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → 2 files reformatted, 2 files left unchanged; `26 passed in 0.15s`; `182 passed, 1 warning in 1.17s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next: start Oracle P0-2 caller fallback conversion by moving one high-risk chat/MCP/developer caller family from implicit `None`/boolean legacy fallback to explicit `USE_V17` / `USE_LEGACY_SAFE` / `DENY_MEMORY` / `SHADOW_ONLY`; preserve legacy only for explicit safe policy. |
| 2026-06-19 | Oracle P0-2 Omi chat vector fallback explicit read-decision semantics | **Complete for one high-risk caller-family slice; production rollout still BLOCKED**: converted the mature Omi chat `search_memories_tool` vector caller from implicit `None` fallback semantics to an explicit `V17ChatMemorySearchResult` carrying `read_decision` (`USE_V17`, `USE_LEGACY_SAFE`, `DENY_MEMORY`, `SHADOW_ONLY`) and fallback reason. Enabled/granted Omi-chat rollout returns `USE_V17` and preserves hydrated V17 vector behavior. Missing/malformed/no-grant/disabled rollout states remain classified by the shared rollout helper as `DENY_MEMORY`/`SHADOW_ONLY` and now return a safe no-memory response from the chat tool instead of silently calling legacy `vector_db.find_similar_memories(...)`. Legacy fallback is preserved only through the explicit `USE_LEGACY_SAFE` opt-in path (`allow_legacy_safe_fallback=True`) used by the compatibility wrapper, not by the production chat tool. Tests prove enabled, denied, and legacy-safe classifications; denied avoids V17 vector search and `users/{uid}/memory_items` reads and source-checks the chat tool so legacy fallback is reached only after `USE_LEGACY_SAFE`. Archive remains default-unavailable. | RED: `cd backend && pytest tests/unit/test_v17_chat_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'V17ChatMemorySearchResult' from 'utils.memory.v17_chat_memory_adapter'`; GREEN: `pytest tests/unit/test_v17_chat_memory_adapter.py -q` → `8 passed in 0.06s`; format: `black --line-length 120 --skip-string-normalization utils/memory/v17_chat_memory_adapter.py utils/retrieval/tools/memory_tools.py tests/unit/test_v17_chat_memory_adapter.py` → `3 files left unchanged`; focused/regression: `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `20 passed in 0.11s`, then `183 passed, 1 warning in 1.19s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next P0-2 slice: convert MCP REST/SSE memory search/list and developer list/category fallback callers so only explicit `USE_LEGACY_SAFE` can downgrade to legacy; then continue P0-3 write/read split-brain. |
| 2026-06-19 | Oracle P0-2 MCP REST/SSE vector fallback explicit read-decision semantics | **Complete for narrow MCP fallback-caller-family slice; production rollout still BLOCKED**: converted the MCP hydrated vector adapter from implicit `None` downgrade semantics to `V17McpMemorySearchResult` with explicit `read_decision` and `fallback_reason`. MCP REST `/v1/mcp/memories/search` and streamable HTTP/SSE `search_memories` now pass the persisted MCP rollout decision into the adapter, return hydrated V17 results only for `USE_V17`, and return an empty safe response for `DENY_MEMORY`/`SHADOW_ONLY` instead of silently calling legacy `vector_db.find_similar_memories(...)` or the legacy default read fallback. Legacy vector fallback is reachable only when the adapter returns explicit `USE_LEGACY_SAFE`. Tests cover enabled, denied/no-grant, and legacy-safe classifications; denied/no-grant avoids vector queries and `users/{uid}/memory_items` reads; route source checks prove legacy calls are after the `USE_LEGACY_SAFE` branch. Archive remains default-unavailable. MCP list (`GET /v1/mcp/memories`) is still legacy-only/not V17-default-read-wired and remains a follow-up before rollout. | RED: `cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'V17McpMemorySearchResult' from 'utils.mcp_memories'`; GREEN: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → `11 passed in 0.09s`; focused/regression: `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `23 passed in 0.12s`, then `186 passed, 1 warning in 1.19s`; format/async: `black --line-length 120 --skip-string-normalization backend/utils/mcp_memories.py backend/routers/mcp.py backend/routers/mcp_sse.py backend/tests/unit/test_v17_mcp_memory_adapter.py && python3 backend/scripts/scan_async_blockers.py` → `4 files left unchanged`, async audit exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). Additional attempted legacy MCP test `pytest tests/unit/test_mcp_search_memories.py tests/unit/test_v17_mcp_memory_adapter.py -q` is blocked by local missing dependency `ModuleNotFoundError: No module named 'fastapi'` before collecting the route tests. | Next P0-2 slice: convert developer list/category fallback semantics and any remaining MCP list/default callers that become V17-wired; then address P0-3 write/read split-brain. |
| 2026-06-19 | Oracle P0-2 developer API fallback explicit read-decision semantics | **Complete for narrow developer fallback-caller-family slice; production rollout still BLOCKED**: converted developer default-list/vector adapters to explicit `V17DeveloperMemorySearchResult` decisions; default list and vector search return V17 only for `USE_V17`, deny `DENY_MEMORY`/`SHADOW_ONLY`, and keep category-filtered developer list explicitly `USE_LEGACY_SAFE` for T22/T23 compatibility. Archive remains default-unavailable. | RED: `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → collection failed with missing `V17DeveloperMemorySearchResult`; GREEN: `11 passed`; focused/regression: `23 passed`, then `189 passed, 1 warning`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-2/P0: MCP list remains legacy-only/not V17-default-read-wired; next recommended Oracle P0 slice: P0-3 external write/read split-brain. |
| 2026-06-19 | Oracle P0-3 developer create-memory write/read split-brain guard | **Complete for first narrow Oracle P0-3 code slice; production rollout still BLOCKED**: added a shared fake-injectable legacy-memory write guard in `utils/memory/v17_default_read_rollout.py` and applied it to the high-risk external developer `POST /v1/dev/user/memories` create path before auto-categorization or `memories_db.create_memory(...)`. The guard reads the same persisted developer default-read rollout decision used by developer V17 reads and blocks legacy `memories` mutation with HTTP 409 when the consumer's read decision is `USE_V17` or `SHADOW_ONLY`, or when control state is missing/malformed/uid-mismatched, unless a server-owned caller explicitly passes `allow_write_convergence=true`. Disabled V17 reads and explicit convergence preserve legacy behavior. This does **not** solve batch/edit/delete, MCP create/edit/delete, durable dual-write/outbox, or V17 write convergence; it only prevents one external developer create split-brain route from mutating legacy state during V17-enabled/shadow read rollout. Archive remains default-unavailable. | RED #1: `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → collection failed with `ImportError: cannot import name 'assert_legacy_memory_write_allowed_for_default_read_decision'`; RED #2 after adding missing/malformed fail-safe test → `1 failed, 14 passed` (`decision.allowed is True` for malformed config), fixed by using an actually malformed rollout fixture and keeping helper fail-safe coverage; GREEN: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `15 passed in 0.09s`; format/focused/regression: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/routers/developer.py backend/tests/unit/test_v17_developer_memory_adapter.py` → `1 file reformatted, 2 files left unchanged`; `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `27 passed in 0.13s`, then `193 passed, 1 warning in 1.17s`; `python3 backend/scripts/scan_async_blockers.py` from repo root → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next Oracle P0-3 slice: extend the same guard/policy to developer batch/edit/delete and MCP REST/SSE create/edit/delete, then decide/implement durable V17 write convergence or dual-write/outbox before any external authoritative read cutover. |
| 2026-06-19 | Oracle P0-3 developer batch-create write/read split-brain guard | **Complete for second narrow Oracle P0-3 code slice; production rollout still BLOCKED**: applied the existing shared legacy-memory write guard to external developer `POST /v1/dev/user/memories/batch` after request shape validation but before auto-categorization, `memories_db.save_memories(...)`, vector upsert, or persona updates. The route now reads the same persisted `developer_api` default-read rollout decision used by developer V17 reads and blocks legacy batch mutation with HTTP 409 for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless a server-owned convergence policy explicitly allows the write through the shared guard. V17-disabled reads preserve existing batch create behavior. Archive remains default-unavailable and no read surface was broadened. | RED: `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `1 failed, 16 passed` (`substring not found` for the batch route guard after the route). GREEN: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `17 passed in 0.07s`. format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/routers/developer.py backend/tests/unit/test_v17_developer_memory_adapter.py && cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → `2 files left unchanged`; `29 passed in 0.11s`; `195 passed, 1 warning in 1.18s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-3: developer edit/delete, MCP create/edit/delete, and durable V17 write convergence / dual-write outbox. Next recommended slice: apply the same guard to developer edit/delete or MCP create/edit/delete. |
| 2026-06-19 | Oracle P0-3 developer edit/delete write/read split-brain guard | **Complete for developer edit/delete guard slice; production rollout still BLOCKED**: applied the existing shared legacy-memory write guard to external developer `DELETE /v1/dev/user/memories/{memory_id}` and `PATCH /v1/dev/user/memories/{memory_id}` before legacy `memories_db.get_memory(...)`, delete, edit, visibility, tag, or category mutation. Both routes now read the same persisted `developer_api` default-read rollout decision used by developer V17 reads and block legacy mutation/delete with HTTP 409 for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless the shared guard is explicitly given server-owned convergence policy. V17-disabled reads preserve existing behavior. Archive remains default-unavailable and no read surface was broadened. | RED: `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `2 failed, 18 passed` (`substring not found` for edit/delete route guard after each route). GREEN: `pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `20 passed in 0.07s`. format/focused/regression: `black --line-length 120 --skip-string-normalization routers/developer.py tests/unit/test_v17_developer_memory_adapter.py && pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 1 file left unchanged`; `32 passed in 0.15s`; `198 passed, 1 warning in 1.21s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). Additional related legacy route test attempt: `pytest tests/unit/test_dev_api_lock_bypass.py tests/unit/test_v17_developer_memory_adapter.py -q` remains blocked in this local environment by missing `fastapi` (`ModuleNotFoundError`). | Remaining P0-3: MCP create/edit/delete and durable V17 write convergence / dual-write outbox. Next recommended slice: inventory and guard MCP REST/SSE write tools before any authoritative external read cutover. |
| 2026-06-19 | Oracle P0-3 MCP REST/SSE create/edit/delete write/read split-brain guard | **Complete for MCP write-surface guard slice; production rollout still BLOCKED**: inspected MCP REST (`routers/mcp.py`) and streamable HTTP/SSE tools (`routers/mcp_sse.py`) and found six legacy mutation surfaces: REST `POST /v1/mcp/memories`, REST `DELETE /v1/mcp/memories/{memory_id}`, REST `PATCH /v1/mcp/memories/{memory_id}`, and SSE tools `create_memory`, `delete_memory`, `edit_memory`. Applied the existing shared `assert_legacy_memory_write_allowed_for_default_read_decision(...)` guard to all six before legacy mutation/delete and before expensive side effects such as auto-categorization, vector upsert/delete, persona update, or legacy `memories_db.get_memory(...)` validation. The guard reads the same persisted `mcp` default-read rollout decision used by MCP V17 reads and blocks legacy `memories` mutation/delete for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless an explicit server-owned convergence policy is passed. REST surfaces return HTTP 409 with the shared guard detail; SSE tools return safe MCP tool errors (`code=-32009`) with the same guard detail. V17-disabled reads preserve existing MCP legacy write behavior. Archive remains default-unavailable and no read surface was broadened. | RED: `cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → `2 failed, 12 passed` (`assert_legacy_memory_write_allowed_for_default_read_decision` missing from REST/SSE write surfaces). GREEN: `pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → `14 passed in 0.07s`. Format/focused/regression: `black --line-length 120 --skip-string-normalization routers/mcp.py routers/mcp_sse.py tests/unit/test_v17_mcp_memory_adapter.py && pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `3 files left unchanged`; `26 passed in 0.14s`; `201 passed, 1 warning in 1.17s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). Additional legacy MCP route-import test attempt: `pytest tests/unit/test_mcp_search_memories.py tests/unit/test_v17_mcp_memory_adapter.py -q` remains blocked in this local environment by missing `fastapi` (`ModuleNotFoundError`). | Remaining P0-3: durable V17 write convergence / dual-write outbox before any authoritative external read cutover. Next recommended Oracle slice: P0-4 mandatory vector freshness/purge fences, unless parent wants to finish write convergence/outbox first. |
| 2026-06-19 | Oracle P0-3 durable write convergence/outbox readiness gate seam | **Complete for narrow convergence-policy seam; production rollout still BLOCKED**: added `V17_WRITE_CONVERGENCE_GATE_PATH = memory_control/v17_write_convergence_gate`, `V17WriteConvergencePolicy`, and `read_v17_write_convergence_gate(...)` in the shared rollout/guard module. External developer and MCP REST/SSE create/edit/delete guards now pass this server-owned gate into `assert_legacy_memory_write_allowed_for_default_read_decision(...)`. For consumers whose reads are `USE_V17`/`SHADOW_ONLY` (or fail-safe missing/malformed/uid-mismatch), legacy mutation remains blocked unless the convergence gate explicitly has boolean `durable_outbox_enabled=true`, `dual_write_projection_ready=true`, `delete_convergence_ready=true`, and `idempotency_contract_ready=true`. Missing/malformed/partial convergence config fails safe and a legacy boolean override is ignored. This concretizes the durable dual-write/outbox readiness gate only; it does **not** implement the full V17 external write service/outbox worker, real Firestore/Pinecone validation, delete projection completion, or production approval. | RED: `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py -q` → collection failed with `ImportError: cannot import name 'V17_WRITE_CONVERGENCE_GATE_PATH'`; GREEN/focused after implementation and route wiring: `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py -q` → `47 passed in 0.12s`; format: `black --line-length 120 --skip-string-normalization backend/utils/memory/v17_default_read_rollout.py backend/routers/developer.py backend/routers/mcp.py backend/routers/mcp_sse.py backend/tests/unit/test_v17_default_read_rollout_decision.py backend/tests/unit/test_v17_developer_memory_adapter.py` → `6 files left unchanged`; regression: `pytest tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `49 passed in 0.14s`, then `204 passed, 1 warning in 1.19s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-3: implement actual external V17 create/edit/delete transaction/outbox contract or disable external writes during pilot; prove projection/vector/delete convergence with emulator and real cloud/Pinecone gates before authoritative external read cutover. Next recommended Oracle P0 slice: P0-4 mandatory vector freshness/purge fences, unless product chooses to continue T22/T23 V17 external write implementation first. |
| 2026-06-19 | Oracle P0-4 mandatory vector freshness/account-generation fence seam | **Complete for first narrow P0-4 code slice; production rollout still BLOCKED**: V17 vector hydration now requires a server-owned `vector_projection_commit_id` on the persisted default-read rollout decision plus a current account-generation fence. `fetch_default_v17_vector_memory_search(...)` requires `required_projection_commit_id` and `required_account_generation`; `hydrate_and_filter_vector_hits(...)` rejects candidates missing mandatory vector metadata (`uid`, `account_generation`, `item_revision`, `source_commit_id`, `content_hash`), candidates from stale account generations, stale projection commits, or stale item revisions/content/source commits. Product vector route, Omi chat vector adapter, MCP vector adapter, and developer vector adapter deny with `missing_vector_projection_commit_id` before vector/memory reads when the rollout lacks the fence. Existing valid fixture hits were updated to include explicit freshness metadata; Archive remains default-unavailable. | RED: `cd backend && pytest tests/unit/test_v17_vector_search_service.py -q` → `2 failed, 2 passed` (`unexpected keyword argument 'required_account_generation'`); partial focused after first implementation exposed fixture failures (`5 failed, 68 passed`) for missing `vector_projection_commit_id`/mandatory hit metadata; GREEN/focused: `pytest tests/unit/test_v17_search_gateway.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q` → `76 passed in 0.24s`; format: `black --line-length 120 --skip-string-normalization <changed python files>` → `14 files left unchanged`; regression: `pytest tests/unit/test_v17_*.py -q` → `206 passed, 1 warning in 1.17s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4/P0: implement/validate real vector purge/repair worker behavior and stale-ID deletion against Pinecone/Firestore; prove shared `ns2` isolation; add app/key/scope third-party auth; overfetch/refill/budgets/telemetry; real cloud/Pinecone/Firestore/benchmark evidence. |
| 2026-06-19 | Oracle P0-4 stale vector repair/purge candidate seam | **Complete for narrow fake-injectable repair/purge seam; production rollout still BLOCKED**: added `VectorRepairPurgeReason` taxonomy and `SearchVectorHit.vector_id` plumbing so Pinecone match IDs can flow through V17 vector hydration. Hydration now returns `repair_purge_candidates` for missing authoritative item, stale projection commit, missing vector freshness metadata, stale account generation, cross-user metadata, stale item revision, stale source commit, stale content hash, and stale vector timestamp. `fetch_default_v17_vector_memory_search(...)` accepts optional `repair_purge_callback` and dispatches one batch only after hydration rejects stale-ID candidates. Missing-fence paths still fail before vector query, `memory_items` reads, or callbacks. Returned items remain hydrated valid `memory_items`; access-policy rejects are not purge candidates; Archive remains default-unavailable. This did not claim real Pinecone delete, Firestore outbox writes, tombstone precedence, shared-`ns2` proof, benchmark evidence, or production approval. | RED: `cd backend && pytest tests/unit/test_v17_vector_search_service.py -q` → collection failed with `ImportError: cannot import name 'VectorRepairPurgeReason'`; GREEN: `pytest tests/unit/test_v17_vector_search_service.py -q` → `6 passed in 0.06s`; focused/regression → `78 passed in 0.24s`, then `208 passed, 1 warning in 1.21s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: durable Firestore outbox, real Pinecone delete/repair worker, idempotency/tombstone/retry telemetry, shared-`ns2` proof, overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 durable fake-injectable repair/purge outbox record seam | **Complete for narrow durable-record seam; production rollout still BLOCKED**: added `backend/database/v17_vector_repair_outbox.py` with deterministic `vector_repair_purge` outbox record construction for `users/{uid}/memory_outbox/{record_id}` and a fake-friendly `write_v17_vector_repair_purge_outbox_records(...)` persistence helper. `record_id`/`idempotency_key` is stable from `uid`, `vector_id`, `memory_id`, `reason`, `required_projection_commit_id`, and `required_account_generation`; records carry observed/authoritative revision/source/content/account fields plus pending retry fields. `fetch_default_v17_vector_memory_search(...)` now builds these records from hydration repair/purge candidates and calls an injected `repair_purge_outbox_writer` exactly once only when records exist. No candidates writes nothing; missing freshness fences still fail before vector query, `memory_items` reads, candidate callbacks, or outbox writer calls. Returned results remain hydrated valid `memory_items`; access-policy rejects are still not outbox candidates; Archive remains default-unavailable. This does **not** call Pinecone, run a real worker, prove tombstone precedence, validate real Firestore/Pinecone/cloud, prove shared `ns2`, or approve production rollout. | RED: `cd backend && pytest tests/unit/test_v17_vector_search_service.py -q` → collection failed with `ModuleNotFoundError: No module named 'database.v17_vector_repair_outbox'`; GREEN: `pytest tests/unit/test_v17_vector_search_service.py -q` → `8 passed in 0.06s`; format/focused/regression: `black --line-length 120 --skip-string-normalization database/v17_vector_repair_outbox.py utils/memory/v17_vector_search_service.py tests/unit/test_v17_vector_search_service.py && pytest tests/unit/test_v17_search_gateway.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 2 files left unchanged`; `80 passed in 0.24s`; `210 passed, 1 warning in 1.17s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: wire the injected writer in production route/worker configuration only after Firestore emulator/cloud validation; implement real idempotent Pinecone delete/repair worker with tombstone precedence, retry/error telemetry, and duplicate stale-ID proof; prove shared `ns2`; add vector overfetch/refill/budgets and real cloud/Pinecone/Firestore/benchmark evidence before any production cutover. |
| 2026-06-19 | Oracle P0-4 server-flagged repair/purge outbox writer wiring seam | **Complete for narrow fake-backed Firestore persistence/wiring seam; production rollout still BLOCKED**: validated the outbox persistence helper with a fake Firestore document seam: repeated writes set the same stable `users/{uid}/memory_outbox/{record_id}` document path with the same `record_id`/`idempotency_key`. Wired the product `/v17/memory/vector/search` surface to pass the real Firestore outbox writer only when persisted server-owned `users/{uid}/memory_control/state.vector_repair_outbox_enabled=true` is present. Missing/no-enable remains fail-closed for persistence: stale-vector candidates build response records for observability, but no Firestore outbox document is written. Enabled flag writes pending `vector_repair_purge` records after vector query and authoritative hydration only; missing freshness-fence and denied rollout paths still fail before vector query, `memory_items` reads, callbacks, or outbox writes. Returned results remain hydrated valid `memory_items`; Archive remains default-unavailable. This does **not** claim emulator/cloud Firestore validation, real Pinecone deletion/repair, tombstone precedence worker behavior, shared `ns2` proof, benchmarks, or production approval. | RED: `cd backend && pytest tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q` → `2 failed, 23 passed` (`KeyError: 'vector_repair_outbox_enabled'`) after adding flag-gated route/persistence tests; GREEN focused: same command → `25 passed in 0.10s`; format/focused/regression: `black --line-length 120 --skip-string-normalization utils/memory/v17_default_read_rollout.py routers/v17_memory_product.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py && pytest tests/unit/test_v17_search_gateway.py tests/unit/test_v17_mcp_memory_adapter.py tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py tests/unit/test_v17_vector_search_service.py -q && pytest tests/unit/test_v17_*.py -q` → `4 files left unchanged`; `83 passed in 0.24s`; `213 passed, 1 warning in 1.24s`; async scan from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: run real Firestore emulator/cloud validation for `users/{uid}/memory_outbox/{record_id}` and IAM/rules assumptions; implement the idempotent Pinecone delete/repair worker with tombstone precedence, retries, dead-letter/error telemetry; prove stale duplicate IDs are removed and shared `ns2` isolation holds; then address vector overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 Firestore emulator validation gate for vector repair outbox persistence | **Complete for local emulator validation sub-slice; production rollout still BLOCKED**: added a real Firebase emulator command for the V17 vector repair/purge outbox writer. The Python harness builds a deterministic `vector_repair_purge` record, persists it twice through `write_v17_vector_repair_purge_outbox_records(...)`, verifies the stable `users/{uid}/memory_outbox/{record_id}` document and unchanged `record_id`/`idempotency_key`, verifies the pending retry fields (`status=pending`, `attempt_count=0`, `last_error=None`), and asserts writer exceptions propagate instead of being silently swallowed. Added a package-script alias for the existing Firestore Security Rules emulator gate proving signed-in client SDK direct read/write/delete is denied for `memory_outbox` and other protected V17 collections; backend/Admin context remains required. Updated `docs/epics/v17_firestore_iam_deployment.md` with exact commands, prerequisites, pass/fail criteria, IAM/rules assumptions, non-claims, and remaining worker/Pinecone/shared-namespace gates. No Pinecone delete/repair worker or production IAM/cloud validation is claimed. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q` → `1 failed` (`missing V17 vector repair outbox emulator harness`). GREEN: same command → `1 passed in 0.03s`. Real emulator persistence: `npm run test:v17-vector-repair-outbox:emulator` → Firebase Firestore emulator started; script printed `PASS: V17 vector repair/purge outbox idempotent Firestore emulator set validated (path=users/v17-vector-repair-outbox-emulator-user/memory_outbox/v17vrp_a9f8abf2b6c7f8409d23f3bc63de76cf, record_id=v17vrp_a9f8abf2b6c7f8409d23f3bc63de76cf); write failure propagated`; exit 0. Real rules emulator: `npm run test:v17-vector-repair-outbox-rules:emulator` → expected `PERMISSION_DENIED` logs for client writes and `PASS: signed-in client read/write denial asserted for 8 V17 collections`; exit 0. Format: `black --line-length 120 --skip-string-normalization backend/scripts/v17_vector_repair_outbox_emulator_test.py backend/tests/unit/test_v17_vector_repair_outbox_emulator_harness.py` → `2 files reformatted`. Focused/regression: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q && pytest tests/unit/test_v17_*.py -q` → `26 passed in 0.12s`; `214 passed, 1 warning in 1.22s`. Docs/static: `pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_iam_deployment_doc.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q` → `3 passed in 0.08s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: cloud IAM/deployed rules validation in the real Firebase project; implement idempotent Pinecone delete/repair worker with tombstone precedence, duplicate stale-ID proof, retries/dead-letter/error telemetry; prove shared `ns2` isolation; add vector overfetch/refill/budgets/central telemetry/app-key-scope auth; produce real benchmark/cloud evidence before rollout. |
| 2026-06-19 | Oracle P0-4 first idempotent vector repair/purge outbox worker seam | **Complete for first narrow worker-seam slice; production rollout still BLOCKED**: added `backend/database/v17_vector_repair_outbox_worker.py`, a pure/fake-injectable processor for prepared pending `vector_repair_purge` outbox records. The seam imports no Pinecone client and requires injected authoritative item loader, vector deleter, vector repairer, and outbox updater. It skips `completed`, `dead_letter`, `in_progress`, non-pending, non-`vector_repair_purge`, and duplicate same-batch `idempotency_key` records before side effects; marks records `in_progress` before an injected action and `completed` with `action=delete|repair` after success; deletes when the authoritative item is missing or tombstone/delete precedence applies (`deleted`, `tombstoned`, `purged`, source missing/tombstoned/purged, or `reason=missing_authoritative_item`); repairs only live authoritative stale projection/revision/source/content records; and records deterministic retry/dead-letter patches (`attempt_count`, `last_error`, `status=pending|dead_letter`) on failures. Added the unit test file to `backend/test.sh`. This does **not** start a production background worker, claim real Pinecone deletion/repair, validate production cloud IAM, prove duplicate physical stale IDs in Pinecone, prove shared `ns2`, or approve rollout. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → collection failed with `ModuleNotFoundError: No module named 'database.v17_vector_repair_outbox_worker'`; GREEN: same command after implementation → `5 passed in 0.05s`; format: `black --line-length 120 --skip-string-normalization backend/database/v17_vector_repair_outbox_worker.py backend/tests/unit/test_v17_vector_repair_outbox_worker.py` → `2 files left unchanged`; focused/regression: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q && pytest tests/unit/test_v17_*.py -q` → `31 passed in 0.15s`, then `219 passed, 1 warning in 1.27s`; async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: production cloud IAM/deployed rules validation; wire a real leased reader/ack writer for `users/{uid}/memory_outbox/*`; real Pinecone delete/upsert implementation and duplicate stale-ID proof; retry scheduling/backoff/central telemetry; shared `ns2` isolation evidence; overfetch/refill/budgets; app/key/scope auth; real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 leased Firestore reader/ack writer seam for vector repair outbox | **Complete for narrow fake-backed Firestore lease/read/ack seam; production rollout still BLOCKED**: added `lease_v17_vector_repair_purge_outbox_records(...)` and `ack_v17_vector_repair_purge_outbox_record(...)` to `backend/database/v17_vector_repair_outbox_worker.py`. The reader targets `users/{uid}/memory_outbox/*`, selects only `pending` `event_type=vector_repair_purge` records whose `available_at` is due, re-reads each document before claim, and marks the stored document `in_progress` with `lease_owner`, `leased_at`, `locked_at`, `lease_expires_at`, and `updated_at`. Returned leased records preserve their original `pending` status so the existing fake-injectable processor can mark/complete/retry/dead-letter them through the ack seam. The ack writer applies patches emitted by `process_v17_vector_repair_purge_outbox_records(...)` to the deterministic outbox path and propagates write failures. Tests prove pending/available selection, terminal/in-progress/future/wrong-event skips, ack path updates, duplicate lease prevention paired with the worker idempotency seam, and deterministic ack failure propagation. The seam documents the fake-backed re-read/conditional-update contract; real Firestore transaction contention validation remains a gate. This does **not** start a production scheduler, claim real Firestore cloud/IAM/deployed-rules validation, call Pinecone, prove duplicate physical stale-ID deletion/repair, prove shared `ns2`, add telemetry/alerts, or approve rollout. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → collection failed with `ImportError: cannot import name 'ack_v17_vector_repair_purge_outbox_record'`; GREEN: same command after implementation → `8 passed in 0.04s`; format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/database/v17_vector_repair_outbox_worker.py backend/tests/unit/test_v17_vector_repair_outbox_worker.py && cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → `1 file reformatted, 1 file left unchanged`; `34 passed in 0.15s`; `222 passed, 1 warning in 1.28s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: Firestore emulator transaction-contention and production cloud IAM/deployed-rules validation for lease/ack, Cloud Run/Tasks scheduling semantics, real injected Pinecone delete/upsert repair functions, duplicate stale-ID proof, retry/dead-letter telemetry/alerts, shared `ns2` isolation, overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 Firestore emulator transaction contention for vector repair outbox lease | **Complete for local emulator contention sub-slice; production rollout still BLOCKED**: hardened `lease_v17_vector_repair_purge_outbox_records(...)` so clients with Firestore transaction support claim pending due `vector_repair_purge` documents by re-reading and updating the same `users/{uid}/memory_outbox/{record_id}` document inside a transaction. Added a real local Firebase emulator contention harness (`backend/scripts/v17_vector_repair_outbox_lease_emulator_test.py`) plus `npm run test:v17-vector-repair-outbox-lease:emulator`; it writes one deterministic pending outbox record, launches eight competing lease attempts, and asserts exactly one returned claim and one stored `in_progress` lease owner/timestamp set. Ack write failure behavior remains explicit/propagating; no Pinecone delete/upsert, production scheduler, Cloud IAM/deployed-rules validation, shared-`ns2` proof, telemetry/alerts, benchmarks, or production approval is claimed. | RED #1: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → `1 failed, 8 passed` (`len(db.transactions) == 0`, proving lease did not use the transactional client path). RED #2: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q` → `2 failed` (missing package script and missing lease contention harness). GREEN focused: `pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q` → `11 passed in 0.18s`. Real emulator contention: `npm run test:v17-vector-repair-outbox-lease:emulator` → Firebase Firestore emulator started and script printed `PASS: V17 vector repair/purge outbox transactional lease contention validated (path=users/v17-vector-repair-outbox-lease-emulator-user/memory_outbox/v17vrp_e52aa735f0ebd7eabe0bc65bdadb651c, record_id=v17vrp_e52aa735f0ebd7eabe0bc65bdadb651c, claimed=1, lease_owner=lease-worker-6); at most one worker claimed the pending record`; exit 0. Focused/regression: `pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q && pytest tests/unit/test_v17_*.py -q` → `36 passed in 0.24s`, then `224 passed, 1 warning in 1.23s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: production cloud IAM/deployed Security Rules validation, explicit Cloud Run/Tasks/scheduler lease-owner contract, real injected Pinecone delete/upsert repair functions, duplicate physical stale-ID proof, retry/dead-letter telemetry/alerts, shared `ns2` isolation evidence, overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 fake-first Pinecone delete/repair adapter seam | **Complete for narrow adapter-mapping seam; production rollout still BLOCKED**: added `backend/database/v17_vector_repair_pinecone_adapter.py`, a pure worker-compatible adapter layer that imports no Pinecone client and requires injected Pinecone-shaped functions. Delete maps `vector_id` to `delete_vectors(ids=[vector_id], namespace="ns2")`; repair maps a live authoritative `V17MemoryItem` plus `required_projection_commit_id` to injected `embed_text(content)` and `upsert_vectors(vectors=[{id, values, metadata}], namespace="ns2")`, using existing V17 vector-id/metadata helpers. Repair raises `V17VectorRepairNotReady` before embedding/upsert when content, source commit, content hash, or projection fence is missing. Tests prove explicit `ns2` propagation, delete/upsert metadata mapping, not-ready no-side-effects behavior, injected failure propagation into retry patches, and duplicate same-batch idempotency with at most one adapter side effect. No scheduler/Cloud Run worker, real Pinecone call, production IAM/deployed-rules validation, duplicate physical stale-ID proof, shared `ns2` proof, telemetry/alerts, benchmarks, or rollout approval is claimed. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → collection failed with `ModuleNotFoundError: No module named 'database.v17_vector_repair_pinecone_adapter'`. GREEN: same command → `13 passed in 0.15s`. Format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/database/v17_vector_repair_pinecone_adapter.py backend/tests/unit/test_v17_vector_repair_outbox_worker.py && cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → `1 file reformatted, 1 file left unchanged`; `40 passed in 0.28s`; `228 passed, 1 warning in 1.26s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: production cloud IAM/deployed rules validation, explicit Cloud Run/Tasks scheduler/lease-owner contract, real Pinecone delete/upsert validation and duplicate stale-ID proof, retry/dead-letter telemetry/alerts, shared `ns2` isolation evidence, overfetch/budgets, app/key/scope auth, and real benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 explicit scheduler/lease-owner worker tick contract | **Complete for narrow execution-contract seam; production rollout still BLOCKED**: added `V17VectorRepairOutboxWorkerTickConfig` and `run_v17_vector_repair_outbox_worker_tick(...)` to `backend/database/v17_vector_repair_outbox_worker.py`. The config defaults disabled/fail-closed, so no due `vector_repair_purge` records are leased unless server-owned config explicitly sets `enabled=true` with a stable worker/lease owner. An enabled tick leases due pending records for one uid through the existing Firestore transaction lease seam, processes them through injected authoritative item loader + vector delete/repair adapter functions via `process_v17_vector_repair_purge_outbox_records(...)`, applies ack/retry/dead-letter patches through `ack_v17_vector_repair_purge_outbox_record(...)`, and returns deterministic summary counts/errors for later low-cardinality telemetry. Updated `docs/epics/v17_firestore_iam_deployment.md` with the proposed Cloud Run/Tasks/scheduler contract, worker identity/env/config, fail-closed enablement flag, telemetry/alert needs, failure modes, and remaining IAM/Pinecone/shared-`ns2` gates. This does **not** deploy a scheduler, create Cloud Run/Tasks resources, call real Pinecone, validate production Firestore IAM/deployed rules, prove duplicate physical stale-ID cleanup, prove shared `ns2`, or approve rollout. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → collection failed with `ImportError: cannot import name 'V17VectorRepairOutboxWorkerTickConfig'`; first implementation run exposed ack-failure fake issue (`1 failed, 16 passed`), fixed by scoping the fake ack failure after lease claim. GREEN: `pytest tests/unit/test_v17_vector_repair_outbox_worker.py -q` → `17 passed in 0.16s`. Format/focused/regression/async: `black --line-length 120 --skip-string-normalization backend/database/v17_vector_repair_outbox_worker.py backend/tests/unit/test_v17_vector_repair_outbox_worker.py && cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q && pytest tests/unit/test_v17_*.py -q && cd .. && python3 backend/scripts/scan_async_blockers.py` → `2 files left unchanged`; `45 passed in 0.21s`; `232 passed, 1 warning in 1.28s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: real disabled-by-default Cloud Run/Tasks wrapper/deployment contract and OIDC/IAM proof, production cloud IAM/deployed rules validation, real Pinecone duplicate stale-ID validation, retry/dead-letter telemetry/alerts, shared `ns2` isolation, and overfetch/refill/budgets. |
| 2026-06-19 | Oracle P0-4 disabled-by-default Cloud Run/Tasks wrapper contract | **Complete for first wrapper-contract slice; production rollout still BLOCKED**: added `backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py`, a fake-injectable env/config wrapper around the one-tick seam. The wrapper defaults disabled/fail-closed when `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` is absent/empty/`false`, prints one deterministic JSON no-op summary, and performs no lease/tick/action side effects. Enabled mode requires explicit `V17_VECTOR_REPAIR_OUTBOX_UID` plus stable `V17_VECTOR_REPAIR_OUTBOX_WORKER_ID` lease-owner identity, bounded positive `LIMIT`/`LEASE_SECONDS`/`MAX_ATTEMPTS`, and injected Firestore/authoritative-item/vector dependencies; malformed config exits nonzero before the tick. Registered `backend/tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py` in `backend/test.sh`, and updated `docs/epics/v17_firestore_iam_deployment.md` plus the Oracle review with the proposed command/env contract, OIDC/IAM assumptions, uid-shard/backlog ownership rule, retry/dead-letter telemetry/alert needs, failure modes, and non-claims. This does **not** deploy Cloud Run/Tasks, create a scheduler, wire real production dependencies, call real Pinecone, validate production Firestore IAM/deployed rules, prove duplicate stale physical-ID cleanup, prove shared `ns2`, or approve rollout. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py -q` → collection failed with `ImportError: cannot import name 'v17_vector_repair_outbox_worker_entrypoint' from 'scripts'`. GREEN: same command after implementation → `6 passed in 0.15s`. Format/CLI smoke/focused/regression/async: `black --line-length 120 --skip-string-normalization scripts/v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py` → `2 files reformatted`, later `2 files left unchanged`; `python3 scripts/v17_vector_repair_outbox_worker_entrypoint.py` → `{"ack_failed_count": 0, "actions": [], "config_valid": true, "enabled": false, "errors": [], "failed_count": 0, "leased_count": 0, "processed_count": 0, "skipped_count": 0, "uid": null, "worker_id": null}`; `pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q && pytest tests/unit/test_v17_*.py -q` → `26 passed in 0.24s`; `238 passed, 1 warning in 1.33s`; `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: wire real production-safe dependencies into the disabled wrapper, add real Cloud Run/Tasks/Scheduler deployment config and OIDC/IAM proof, validate production Firestore IAM/deployed rules, run real Pinecone duplicate stale-ID delete/repair validation, add retry/dead-letter central telemetry/alerts, prove shared `ns2` isolation, and complete overfetch/refill/budgets plus other Oracle P0s. |
| 2026-06-19 | Oracle P0-4 production-safe dependency resolver behind disabled wrapper | **Complete for narrow dependency-factory slice; production rollout still BLOCKED**: wired a production dependency resolver behind the wrapper that is invoked only after `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=true` and wrapper config validation. Disabled/default CLI smoke remains dependency-free for Pinecone/OpenAI/Firestore client initialization. Enabled production resolution now fails deterministically before lease/tick when required dependency env is missing (`PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `OPENAI_API_KEY`). When present, the resolver lazily builds Admin Firestore from `database._client.db`, an authoritative `users/{uid}/memory_items/{memory_id}` loader returning `V17MemoryItem`, and real Pinecone-shaped `delete`/`upsert` adapter functions with the existing embedding provider `utils.llm.clients.embeddings.embed_query` and explicit namespace `ns2`. Tests use monkeypatch/fakes only and prove disabled main does not initialize dependencies, enabled main calls the resolver once, missing dependency config fails before lease, and fake resolver/deps can run a one-tick summary. No real Pinecone/OpenAI/Firestore cloud calls were made or claimed. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py -q` → `4 failed, 6 passed` (`build_v17_vector_repair_outbox_production_dependencies` / `V17VectorRepairOutboxProductionDependencies` missing and `main()` had no injectable env/tick args). GREEN/focused: `pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py -q` → `10 passed in 0.15s`; format/focused regression: `black --line-length 120 --skip-string-normalization scripts/v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → `2 files left unchanged`, `30 passed in 0.26s`; disabled CLI smoke: `python3 scripts/v17_vector_repair_outbox_worker_entrypoint.py` → `{"ack_failed_count": 0, "actions": [], "config_valid": true, "enabled": false, "errors": [], "failed_count": 0, "leased_count": 0, "processed_count": 0, "skipped_count": 0, "uid": null, "worker_id": null}`; full V17 regression `pytest tests/unit/test_v17_*.py -q` → `242 passed, 1 warning in 1.28s`; async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: real Cloud Run/Tasks/Scheduler deployment config and OIDC/IAM proof, production cloud IAM/deployed rules validation, real Pinecone validation with duplicate stale physical IDs, retry/dead-letter telemetry/alerts, shared `ns2` isolation, vector overfetch/refill/budgets, app/key/scope auth, and benchmark/cloud evidence. |
| 2026-06-19 | Oracle P0-4 disabled Cloud Run/Tasks/Scheduler contract and OIDC/IAM proof artifact | **Complete for static deployment/proof artifact slice; production rollout still BLOCKED**: added `docs/epics/v17_vector_repair_outbox_cloud_deployment_contract.yaml`, a checked-in disabled-by-default Cloud Run/Cloud Tasks/Cloud Scheduler contract for the V17 vector repair outbox worker. The artifact specifies command/image/entrypoint, env vars and secrets, `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false`, explicit uid shard and stable worker id placeholders, dedicated worker/scheduler service accounts, Cloud Scheduler `state: PAUSED`, OIDC `serviceAccountEmail` plus `audience`, IAM proof targets (`roles/run.invoker`, `roles/cloudtasks.enqueuer`, `roles/iam.serviceAccountTokenCreator`, `roles/datastore.user` or narrower), retry/backoff/dead-letter routing, log/telemetry pass-fail criteria, and exact `gcloud`/Firebase proof commands to run later. Updated `docs/epics/v17_firestore_iam_deployment.md` and the Oracle review with a candid readiness caveat: the current worker is a CLI one-tick entrypoint, so an HTTP shim or deliberate Cloud Run Job + OAuth trigger pattern must exist before applying the HTTP Cloud Tasks/Scheduler shape. No Cloud Run service, Cloud Tasks queue, Cloud Scheduler job, IAM binding, production Firestore rules validation, Pinecone delete/upsert, shared-`ns2` proof, telemetry alert, benchmark, or production approval was created or claimed. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_deployment_contract.py -q` → `1 failed` (`missing checked-in Cloud Run/Tasks/Scheduler contract artifact`). GREEN: same command after artifact → `1 passed in 0.03s`. Format/focused regression: `black --line-length 120 --skip-string-normalization tests/unit/test_v17_vector_repair_outbox_deployment_contract.py && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_deployment_contract.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → `1 file reformatted`, later `31 passed in 0.24s`. Disabled CLI smoke: `python3 scripts/v17_vector_repair_outbox_worker_entrypoint.py` → `{"ack_failed_count": 0, "actions": [], "config_valid": true, "enabled": false, "errors": [], "failed_count": 0, "leased_count": 0, "processed_count": 0, "skipped_count": 0, "uid": null, "worker_id": null}`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `243 passed, 1 warning in 1.32s`. Async scan: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: add/validate worker HTTP shim or Cloud Run Job trigger, run real OIDC/IAM proof commands against target project, validate production Firestore IAM/deployed rules, prove real Pinecone duplicate stale physical-ID delete/repair/tombstone precedence and shared `ns2` isolation, add retry/dead-letter/backlog telemetry/alerts, vector overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit production rollout gates. |
| 2026-06-19 | Oracle P0-4 disabled HTTP trigger shim for Cloud Run/Tasks OIDC | **Complete for local trigger-surface mismatch slice; production rollout still BLOCKED**: added a minimal ASGI HTTP shim in `backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py` via `create_v17_vector_repair_outbox_worker_app(...)`, `run_v17_vector_repair_outbox_worker_http_tick(...)`, and module-level `app`. The shim exposes `POST /v17-vector-repair-outbox-worker/tick` for Cloud Run service deployments while preserving disabled/fail-closed behavior: absent/false `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` returns deterministic no-op JSON and does not initialize Firestore/Pinecone/embedding dependencies, lease records, process actions, or ack outbox records. Enabled mode still requires server-owned explicit `V17_VECTOR_REPAIR_OUTBOX_UID` and stable `V17_VECTOR_REPAIR_OUTBOX_WORKER_ID`; no uid is accepted from a request body and there is no unbounded scan. Authentication is deliberately delegated to Cloud Run IAM (`roles/run.invoker`) plus Cloud Scheduler/Tasks OIDC `serviceAccountEmail`/`audience`; the app shim does not add a weak app-level bearer-token scheme. Updated the static Cloud Run/Tasks/Scheduler YAML to use `uvicorn scripts.v17_vector_repair_outbox_worker_entrypoint:app --host 0.0.0.0 --port 8080`, updated Firestore/IAM deployment docs and Oracle review to remove the prior CLI-vs-HTTP caveat, and kept worker env disabled plus Scheduler paused. No Cloud Run service, Cloud Tasks queue, Scheduler job, IAM binding, production Firestore rules validation, Pinecone delete/upsert, shared-`ns2` proof, alert, benchmark, or production approval was created or claimed. | RED #1: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py -q` → `5 failed, 10 passed` (`create_v17_vector_repair_outbox_worker_app` missing and Cloud Run IAM documentation absent). RED #2: `pytest tests/unit/test_v17_vector_repair_outbox_deployment_contract.py -q` → `1 failed` (`assert 'uvicorn' in contract`). GREEN/format/focused: `black --line-length 120 --skip-string-normalization scripts/v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_deployment_contract.py && pytest tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_deployment_contract.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q` → `2 files reformatted, 1 file left unchanged`; `36 passed in 0.28s`, then after full-regression import-stub hardening `36 passed in 0.25s`. Disabled CLI smoke: `python3 scripts/v17_vector_repair_outbox_worker_entrypoint.py` → `{"ack_failed_count": 0, "actions": [], "config_valid": true, "enabled": false, "errors": [], "failed_count": 0, "leased_count": 0, "processed_count": 0, "skipped_count": 0, "uid": null, "worker_id": null}`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `248 passed, 1 warning in 1.34s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: run real OIDC/IAM proof commands against the target project, validate production Firestore IAM/deployed rules, run real Pinecone duplicate stale-ID delete/repair/tombstone/shared-`ns2` proof, add retry/dead-letter/backlog telemetry/alerts, and complete broader Oracle P0s (overfetch/budgets, app/key/scope auth, benchmarks/cutover gates). |
| 2026-06-19 | Oracle P0-4 read-only OIDC/IAM proof runner for disabled HTTP worker | **Complete for readiness/proof-runner slice; production rollout still BLOCKED**: added `backend/scripts/v17_vector_repair_outbox_oidc_iam_proof.py`, a safe-by-default OIDC/IAM proof runner for the disabled `POST /v17-vector-repair-outbox-worker/tick` Cloud Run service contract. The runner defaults to `NOT_RUN` inventory mode, requires explicit project/region for target proof, and only executes allowlisted read-only `gcloud` `describe` / `get-iam-policy` commands when `--execute` is passed. It checks the Cloud Run service account and disabled env (`V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false`), restricted ingress and invoker IAM, Scheduler `state=PAUSED`, Scheduler OIDC `serviceAccountEmail`/`audience`, Tasks single-concurrency/bounded retry shape, worker Firestore IAM (`roles/datastore.user` or narrower custom role), absence of owner/editor on the worker SA, and scheduler token-creator policy presence. Updated the deployment YAML and Firestore/IAM doc with exact runner commands, prerequisites, pass/fail criteria, and explicit non-claims. The local environment had no `gcloud` on PATH and no target project/region configured, so no production OIDC/IAM proof was run or claimed; production Firestore IAM/deployed rules validation, real Pinecone duplicate stale physical-ID validation, retry/dead-letter alerting, and shared `ns2` proof remain open. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_oidc_iam_proof.py -q` → `2 failed` (`missing read-only OIDC/IAM proof runner`; deployment contract did not reference the runner). GREEN/static: same command → `2 passed in 0.03s`. Readiness run: `python3 backend/scripts/v17_vector_repair_outbox_oidc_iam_proof.py` → JSON `status: "NOT_RUN"`, `read_only: true`, prerequisites `--project or V17_VECTOR_REPAIR_PROOF_PROJECT is required`, `--region or V17_VECTOR_REPAIR_PROOF_REGION is required`; `command -v gcloud` produced no output; `python3 backend/scripts/v17_vector_repair_outbox_oidc_iam_proof.py --execute` → exit 2 with `status: "NOT_RUN"`, prerequisites included missing project/region and `gcloud CLI is not installed or not on PATH`. Focused/regression/async: `38 passed`, `250 passed, 1 warning`, async scan exit 0 with pre-existing findings only. | Remaining P0-4: run real OIDC/IAM proof against target project, validate production Firestore IAM/deployed rules, real Pinecone duplicate stale physical-ID/tombstone proof, retry/dead-letter alerts, shared `ns2` isolation, overfetch/budgets, app/key/scope auth, and benchmarks. |
| 2026-06-19 | Oracle P0-4 Firestore IAM/deployed Security Rules proof runner | **Complete for readiness/proof-runner artifact; production rollout still BLOCKED**: added `backend/scripts/v17_firestore_rules_iam_proof.py`, a safe-by-default production Firestore IAM/deployed Security Rules validation runner for the V17 vector repair outbox paths. Inventory mode prints exact commands and `status=NOT_RUN`; `--execute` only runs read-only `gcloud firestore databases describe`, `gcloud projects get-iam-policy`, `gcloud iam service-accounts get-iam-policy`, and `firebase firestore:rules:get`. Pass/fail criteria cover client denial on `users/{uid}/memory_outbox/{record_id}`, Admin worker service-account Firestore IAM, server-owned `users/{uid}/memory_control/state`, no client enablement of `vector_repair_outbox_enabled`, and no broad public IAM access. Static tests assert required paths/gates and that generated commands contain no mutating `firebase deploy`, `gcloud firestore databases update/create/delete`, IAM `set-iam-policy`, or IAM binding mutations. Updated Firestore/IAM deployment doc and Oracle review. Local environment had no target project, no `gcloud`, and no `firebase`, so no production Firestore IAM/deployed-rules validation was run or claimed. | RED: `cd backend && pytest tests/unit/test_v17_firestore_rules_iam_proof.py -q` → `2 failed` (`missing read-only Firestore IAM/deployed rules proof runner`; doc missing proof-runner reference). GREEN/static after implementation/doc update: same command → `2 passed in 0.04s`. Readiness run: `python3 backend/scripts/v17_firestore_rules_iam_proof.py` → JSON `status: "NOT_RUN"`, `read_only: true`, prerequisites `--project or V17_FIRESTORE_PROOF_PROJECT is required`; `command -v gcloud` and `command -v firebase` produced no output; `python3 backend/scripts/v17_firestore_rules_iam_proof.py --execute` → exit 2 with `status: "NOT_RUN"`, prerequisites included missing project, `gcloud CLI is not installed or not on PATH`, and `firebase CLI is not installed or not on PATH`. Focused/static regression: `pytest tests/unit/test_v17_firestore_rules_iam_proof.py tests/unit/test_v17_vector_repair_outbox_oidc_iam_proof.py tests/unit/test_v17_vector_repair_outbox_deployment_contract.py tests/unit/test_v17_firestore_iam_deployment_doc.py tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q` → `40 passed in 0.39s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `252 passed, 1 warning in 1.38s`. Async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: run real Firestore IAM/deployed-rules and OIDC/IAM proof runners against target project with exact output; run real Pinecone duplicate stale physical-ID delete/repair/tombstone validation and prove shared `ns2` isolation; add retry/dead-letter telemetry/alerts, overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates. |
| 2026-06-19 | Oracle P0-4 Pinecone repair/shared-ns2 validation readiness runner | **Complete for readiness/non-claim artifact; production rollout still BLOCKED**: added `backend/scripts/v17_pinecone_repair_validation_readiness.py`, a safe-by-default Pinecone validation readiness runner for the duplicate stale physical-ID / tombstone precedence / live repair / retry-dead-letter / shared-`ns2` isolation proof Oracle still requires. Default mode emits `status=NOT_RUN`, `read_only=true`, pass/fail criteria, exact prerequisite env (`PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `PINECONE_INDEX_HOST`), and planned safe commands; it performs no Pinecone delete/upsert/query mutation. Execute mode remains gated by explicit `--allow-throwaway-mutation`, a non-`ns2` `--test-namespace`, a long `v17-proof-...` throwaway vector id prefix, exact prefix confirmation, and optional `--shared-ns2-readonly`; the runner refuses shared `ns2` mutation and broad delete/update terms. Updated Firestore/IAM deployment doc and Oracle review with commands, pass/fail criteria, non-claims, and remaining gates. No real Pinecone validation, vector deletion/upsert, tombstone precedence proof, retry/dead-letter proof, or shared-`ns2` isolation proof was run or claimed. | RED: `cd backend && pytest tests/unit/test_v17_pinecone_repair_validation_readiness.py -q` → `3 failed` (missing safe Pinecone validation readiness runner and doc references). GREEN/static after implementation/doc update: same command → `3 passed in 0.04s`. Readiness run: `python3 backend/scripts/v17_pinecone_repair_validation_readiness.py` → JSON `status: "NOT_RUN"`, `read_only: true`, `mutation_allowed: false`, prerequisites `PINECONE_API_KEY is required`, `PINECONE_INDEX_NAME is required`, `PINECONE_INDEX_HOST is required`. Safety-gated execute attempt: `python3 backend/scripts/v17_pinecone_repair_validation_readiness.py --execute` → exit 2 with `status: "NOT_RUN"`, prerequisites also including `--allow-throwaway-mutation is required for execute mode`, `--test-namespace is required for execute mode`, and `--throwaway-prefix is required for execute mode`. Format/focused regression: `black --line-length 120 --skip-string-normalization scripts/v17_pinecone_repair_validation_readiness.py tests/unit/test_v17_pinecone_repair_validation_readiness.py && pytest tests/unit/test_v17_pinecone_repair_validation_readiness.py tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py tests/unit/test_v17_vector_repair_outbox_worker.py tests/unit/test_v17_vector_search_service.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_firestore_rules_iam_proof.py tests/unit/test_v17_vector_repair_outbox_oidc_iam_proof.py -q` → `64 passed in 0.34s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `255 passed, 1 warning in 1.39s`. Async scan exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: implement/run real throwaway Pinecone fixture validation with exact PASS/FAIL output for duplicate stale physical IDs, delete/repair/tombstone precedence, retry/dead-letter, and post-run absence of prefix-scoped stale vectors; produce read-only shared `ns2` coexistence evidence proving legacy queries exclude V17 schema records and baseline recall remains intact or choose separate namespace/filter; run OIDC/IAM and Firestore proof runners against target cloud projects; add retry/dead-letter alerts, overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates. |
| 2026-06-19 | Oracle P0-4 central retry/dead-letter/backlog telemetry seam | **Complete for narrow telemetry payload/emitter seam; production rollout still BLOCKED**: added `backend/database/v17_vector_repair_outbox_telemetry.py`, a fake-injectable central telemetry contract that converts deterministic V17 vector repair outbox worker tick summaries plus optional backlog/duration inputs into low-cardinality metric/event payloads. It covers lease/processed/skipped/failed counts, delete/repair action counts, retry/dead-letter reasons, ack failures, pending/dead-letter backlog counts, oldest pending age, and duration. `run_v17_vector_repair_outbox_worker_tick(...)` now accepts optional `telemetry_emitter`, `telemetry_config`, backlog, and duration inputs; emitter failures are recorded under `summary["telemetry"]` and do not mask worker cleanup/ack results. Metric labels are bounded to `worker_component`, `status`, `action`, `reason`, and `event_type`; uid, worker_id, vector_id, memory_id, record_id, idempotency_key, and raw error text are forbidden. Updated the Cloud Run/Tasks/Scheduler contract and Firestore/IAM deployment doc with alert thresholds and pass/fail criteria. No Prometheus/OpenTelemetry/Cloud Monitoring sink, dashboard, alert policy, production worker telemetry, Pinecone operation, cloud proof, shared-`ns2` proof, benchmark, or production approval is claimed. | RED: `cd backend && pytest tests/unit/test_v17_vector_repair_outbox_telemetry.py -q` → collection failed with `ModuleNotFoundError: No module named 'database.v17_vector_repair_outbox_telemetry'`. GREEN: same command after implementation → `4 passed in 0.15s`. Focused regression: telemetry/outbox/deployment/doc tests → `38 passed in 0.26s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `259 passed, 1 warning in 1.48s`. Async scan from repo root → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-4: wire this seam to the real metrics/log backend and create alert policies with exact output; run OIDC/IAM and Firestore IAM/deployed-rules proof runners against target projects; run real Pinecone duplicate stale physical-ID/tombstone/repair validation and shared-`ns2` proof; then continue overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates. |
| 2026-06-19 | Oracle P0-1 shared V17 product authorization decision seam | **Complete for first shared product-route authorization seam; production rollout still BLOCKED**: added `backend/utils/memory/v17_product_authorization.py`, a fake-injectable server-side decision seam for V17 product memory routes. The seam carries `uid`, `consumer`, `surface`, optional app/key/scope context, explicit Archive request intent, persisted default rollout/grant state, global gate state, persisted Archive capability, and deterministic fail-closed reasons. It checks the global gate before per-user rollout reads, denies missing/malformed/disabled/no-grant control state with `DENY_MEMORY`, constructs default policies with `archive_capability=false` even if a persisted Archive grant exists, and only constructs Archive policy when both `explicit_archive_request=true` and persisted Archive capability are present. Wired `/v17/memory/search`, `/v17/memory/vector/search`, and `/v17/memory/archive/search` through the shared seam before any vector query or `users/{uid}/memory_items` read; route response behavior remains default Archive-unavailable. This is not production approval and does not solve app/key-specific grant persistence, MCP/developer scope enforcement, overfetch/refill, cloud/IAM/Pinecone proofs, or benchmark evidence. | RED: `cd backend && pytest tests/unit/test_v17_product_authorization.py -q` → collection failed with `ModuleNotFoundError: No module named 'utils.memory.v17_product_authorization'`. GREEN: same command after implementation → `5 passed in 0.06s`. Format/focused regression: `black --line-length 120 --skip-string-normalization utils/memory/v17_product_authorization.py routers/v17_memory_product.py tests/unit/test_v17_product_authorization.py` → `2 files reformatted, 1 file left unchanged`; `pytest tests/unit/test_v17_product_authorization.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py -q` → `34 passed in 0.22s`; full V17 regression `pytest tests/unit/test_v17_*.py -q` → `264 passed, 1 warning in 1.59s`; async scan `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-1/P0-6: persist and enforce app/key/scope-specific memory grants across MCP/developer/third-party surfaces, add real FastAPI dependency/scope tests, and complete product-owner decisions for Archive/app grant semantics. Next recommended slice: start P0-6 app/key/scope authorization contract or P0-7 vector overfetch/budget seam; production rollout remains BLOCKED. |
| 2026-06-19 | Oracle P0-1/P0-6 app/key/scope V17 memory grant contract seam | **Complete for first narrow contract/helper seam; production rollout still BLOCKED**: added a fake-injectable app/key/scope grant contract in `backend/utils/memory/v17_product_authorization.py` with `V17MemoryGrantOperation`, `V17AppKeyScopeGrantDecision`, and `authorize_v17_app_key_scope_memory_grant(...)`. The seam models consumer/surface, app_id, key_id, authenticated scopes, required memory operation (`default_read`, `archive_read`, `write`), and a persisted grant shape at `grants.<consumer>.apps.<app_id>.keys.<key_id>`. External consumers (`developer_api`, `mcp`, `third_party`) fail closed unless both authenticated scopes and persisted grant scopes contain the required scope and the matching boolean operation grant is true; missing app/key identity, missing grant, disabled grant, wrong scope, and malformed persisted grant return deterministic reasons. First-party `omi_chat` remains on the existing rollout/default-grant product authorization path. Default-read external policies do not expose Archive; Archive requires the stronger `memories.archive.read` plus `archive_read=true` and still must be composed with explicit Archive request + persisted Archive capability before any Archive route exposure. Current developer/MCP route inventory shows developer key scopes exist but route dependencies currently return only uid, while MCP API keys do not yet persist scopes, so this slice is a contract/helper and tests only, not route enforcement. | RED: `cd backend && pytest tests/unit/test_v17_product_authorization.py -q` → collection failed with `ImportError: cannot import name 'V17MemoryGrantOperation'`. GREEN: same command after implementation → `11 passed in 0.05s`. Format/focused/regression: `black --line-length 120 --skip-string-normalization utils/memory/v17_product_authorization.py tests/unit/test_v17_product_authorization.py && pytest tests/unit/test_v17_product_authorization.py tests/unit/test_v17_product_memory_router.py tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 1 file left unchanged`; `40 passed in 0.13s`; `270 passed, 1 warning in 1.58s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-1/P0-6: persist server-owned per-app/per-key grants with client write denial proof; carry key id/app id/scopes through developer and MCP REST/SSE auth dependencies; compose this seam before external V17 memory reads/writes; add route-level FastAPI/scope tests; keep Archive explicit plus persisted-capability gated; production rollout remains BLOCKED. |
| 2026-06-19 | Oracle P0-1/P0-6 server-owned app/key grant storage/read helper and local rules proof | **Complete for storage/read helper plus local emulator denial proof; production rollout still BLOCKED**: added `backend/database/v17_app_key_memory_grants.py` with canonical server-owned Firestore path `users/{uid}/memory_control/v17_app_key_memory_grants`, constants, fake-injectable `read_v17_app_key_memory_grants_state(uid, db_client)`, and `build_v17_app_key_scope_grant_contract_state(...)`. The persisted document stores the exact nested contract consumed by `authorize_v17_app_key_scope_memory_grant(...)`: `grants.<consumer>.apps.<app_id>.keys.<key_id>`. Missing docs return `missing_v17_app_key_memory_grants_state`; malformed top-level state returns `malformed_v17_app_key_memory_grants_state` and fails closed through the grant authorization helper. Valid default-read grants feed the app/key/scope helper while keeping `archive_capability=false`; Archive grants require the explicit `ARCHIVE_READ` operation and still do not make Archive default-visible. Extended the local Firestore rules emulator harness and package script to assert signed-in clients cannot read/create/update/delete the app/key grant doc or self-grant `grants.developer_api.apps.client-app.keys.client-key`. Added `docs/epics/v17_app_key_memory_grants_readiness.md` with schema, path conversion, emulator command, route blockers, and non-claims. This is not route enforcement, deployed rules/IAM proof, MCP scope persistence, production approval, or benchmark evidence. | RED #1: `cd backend && pytest tests/unit/test_v17_app_key_grant_store.py -q` → `ModuleNotFoundError: No module named 'database.v17_app_key_memory_grants'`. RED #2: `pytest tests/unit/test_v17_firestore_emulator_harness.py -q` → failed because the app-key self-grant target/script was missing. GREEN/static: `pytest tests/unit/test_v17_app_key_grant_store.py tests/unit/test_v17_product_authorization.py tests/unit/test_v17_firestore_emulator_harness.py tests/unit/test_v17_firestore_security_rules.py -q` → `19 passed in 0.14s`. Local emulator proof: `npm run test:v17-app-key-grants-rules:emulator` → PASS, output included `PASS: signed-in client read/write denial asserted for 8 V17 collections and V17 app/key memory grant self-grant path`. Focused regression: product auth/router/default rollout/app-key store tests → `45 passed in 0.15s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `276 passed, 1 warning in 1.53s`. Async scan from repo root → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-1/P0-6: carry authenticated `app_id`, `key_id`, and verified scopes through developer/MCP/third-party route dependencies; persist MCP key scopes or OAuth token scope introspection; compose storage + grant + product authorization before V17 external reads/writes; run deployed Firestore rules/IAM proof against a real target; keep Archive explicit plus server-capability gated. |
| 2026-06-19 | Oracle P0-1/P0-6 Developer API app/key/scope default-read composition seam | **Complete for one narrow Developer API default-list composition seam; production rollout still BLOCKED**: extended Developer API key lookup/cache/auth context to carry `uid`, stable `app_id`, `key_id`, and verified scopes while preserving existing uid-only helpers that return `auth.uid`. Added `get_developer_v17_default_memory_read_context(...)`, translating verified Developer API scopes (`memories:read`, `memories:write`) into V17 grant scopes (`memories.read`, `memories.write`) and building `V17ProductAuthorizationContext` for `consumer='developer_api'` / `surface='developer_default_memory_read'`. Added `authorize_v17_external_default_memory_read(...)`, which reads `users/{uid}/memory_control/v17_app_key_memory_grants` and composes with `authorize_v17_app_key_scope_memory_grant(..., operation=DEFAULT_READ)`. Wired Developer API `GET /v1/dev/user/memories` without category filters through this composition before V17 default-list reads; missing app/key identity, missing/wrong scope, missing/malformed grant state, or missing persisted default-read grant returns 403 before V17 `memory_items` access. Allowed default-read policies keep `archive_capability=false`; no Archive route/path was exposed. This is not broad developer/MCP route enforcement, not vector enforcement, not MCP scope persistence, not deployed Firestore/IAM proof, not production approval, and not benchmark evidence. | RED: `cd backend && pytest tests/unit/test_v17_product_authorization.py tests/unit/test_v17_developer_auth_context_static.py -q` → failed with `ImportError: cannot import name 'authorize_v17_external_default_memory_read'`. GREEN/focused: `pytest tests/unit/test_v17_product_authorization.py tests/unit/test_v17_app_key_grant_store.py tests/unit/test_v17_developer_auth_context_static.py tests/unit/test_v17_developer_memory_adapter.py -q` → `40 passed in 0.16s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `280 passed, 1 warning in 1.59s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Next: apply the same app/key/scope composition to Developer API vector search before V17 vector reads; then MCP REST/SSE need persisted key scopes or OAuth token introspection plus route context. Deployed Firestore/IAM proof remains not run. |
| 2026-06-19 | Oracle P0-1/P0-6 Developer API vector app/key/scope composition seam | **Complete for Developer API vector route composition; production rollout still BLOCKED**: changed `GET /v1/dev/user/memories/vector/search` from the uid-only `get_uid_with_memories_read` dependency to `get_developer_v17_default_memory_read_context(...)`, then calls `authorize_v17_external_default_memory_read(auth_context, db_client=db)` before reading developer rollout state or calling `search_v17_default_developer_memories_vector(...)`. Missing app/key identity, missing/wrong authenticated `memories.read` scope, missing/malformed server-owned `users/{uid}/memory_control/v17_app_key_memory_grants`, disabled grant, missing persisted scope, or missing `default_read=true` now returns 403 before any V17 vector query, repair/outbox side effect, or `users/{uid}/memory_items` hydration. Valid app/key/scope grant continues to reach the existing V17 vector adapter and mandatory projection/account-generation fences. Default-read response/policy still has `archive_capability=false`; no Archive vector path or default Archive exposure was added. This is not MCP scope persistence, not deployed Firestore/IAM proof, not Pinecone/cloud proof, not benchmark evidence, and not production approval. | RED: `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `1 failed, 19 passed` (`test_developer_vector_route_wires_app_key_scope_grant_before_v17_vector_reads` could not find the vector route app/key context dependency after route decorator). GREEN/focused after code+format: `pytest tests/unit/test_v17_developer_memory_adapter.py tests/unit/test_v17_product_authorization.py tests/unit/test_v17_developer_auth_context_static.py -q` → `35 passed in 0.16s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `280 passed, 1 warning in 1.58s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-1/P0-6: MCP REST/SSE still need persisted key scopes or OAuth token introspection plus route execution context carrying app/key/scope identity; deployed Firestore/IAM proof remains not run. |
| 2026-06-19 | Oracle P0-1/P0-6 MCP REST/SSE app/key/scope context readiness slice | **Complete for narrow MCP context/readiness helper; production rollout still BLOCKED**: added `McpV17VerifiedAuth`, `MCP_V17_DEFAULT_MEMORY_READ_SURFACE`, and `build_mcp_v17_default_memory_read_context(...)` in `backend/utils/mcp_memories.py`. The helper can carry `uid`, stable `app_id`, `key_id`, verified MCP scopes, `consumer='mcp'`, and `surface='mcp_default_memory_read'` into `V17ProductAuthorizationContext` for composition with `authorize_v17_external_default_memory_read(...)`. Existing uid-only MCP compatibility is preserved: REST routes still depend on `get_uid_from_mcp_api_key`, and SSE tool execution still receives `user_id` only. Missing app/key identity or `memories.read` scope fails closed through the shared app/key/scope grant seam; valid injected MCP context plus stored grant allows default read with `archive_capability=false`. Added `docs/epics/v17_mcp_app_key_scope_readiness.md` inventorying MCP REST/SSE routes/tools, advertised OAuth scopes, current uid-only dependencies, MCP key model/storage gaps, required future route wiring, RED tests needed, blockers, and explicit non-claims. This is not MCP route enforcement, not MCP key scope persistence, not OAuth introspection, not deployed Firestore/IAM proof, not Pinecone/cloud proof, not benchmark evidence, and not production approval. | RED: `cd backend && pytest tests/unit/test_v17_mcp_auth_context_static.py -q` → collection failed with `ImportError: cannot import name 'McpV17VerifiedAuth' from 'utils.mcp_memories'`. GREEN/focused after helper: same command → `5 passed in 0.07s`. Format/focused regression: `black --line-length 120 --skip-string-normalization utils/mcp_memories.py tests/unit/test_v17_mcp_auth_context_static.py` → `2 files left unchanged`; `pytest tests/unit/test_v17_mcp_auth_context_static.py tests/unit/test_v17_product_authorization.py tests/unit/test_v17_mcp_memory_adapter.py -q` → `32 passed in 0.13s`. Full V17 regression: `pytest tests/unit/test_v17_*.py -q` → `285 passed, 1 warning in 1.59s`. Async scan from repo root: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing findings only (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). | Remaining P0-1/P0-6: persist MCP key scopes or add OAuth token introspection; then wire REST/SSE execution contexts to deny before V17 vector/default reads. Deployed Firestore/IAM proof remains not run. |

Wave 2 reviewers blocked the first draft because it allowed imports/writes before deletion/purge coverage and snapshot safeguards. This revised order is now superseded by the P0 amendment queue above, but remains as the historical ticket inventory to revise.

| Order | Tickets | Goal | Gate |
|---:|---|---|---|
| 0 | T00–T05 | Config, contracts, evidence schema, indexes, write-path audit, encryption/redaction rules | V17 defaults off; legacy users unchanged; data schema safe |
| 1 | T06 | Minimum deletion/export/account-purge coverage | Required before any staff/customer V17 write |
| 2 | T07–T10 | Short-term/Archive stores, old-memory inventory, snapshot/high-water mark, raw lineage | 100% accounted inventory or explicit outcome |
| 3 | T11–T12 | No-silent-data-loss verifier + old-memory import write path | Import writes only for allowlisted users and only from stable snapshots |
| 4 | T13–T18 | Patch idempotency, writer lease, patch applier, L2 dry-run/write backfill, lifecycle/aging, review/non-active outcomes | Duplicate-proof Long-term pipeline; no blind head writes |
| 5 | T19–T23 | Vector metadata, read service, external write semantics, chat/MCP/tools/developer policies, agent tools | Default reads = Short-term + Long-term; Archive explicit only |
| 6 | T24–T26 | Minimal UI, admin policy controls, telemetry/ops gates | Simple user surfaces; rollout observable; no metric pollution |
| 7 | T27 | Benchmark migration/backfill eval mode | Honest Base-anchored eval and anti-reward-hacking checks |

---

## Hard rollout blockers

Do not enable the next rollout stage if any blocker is true:

- Non-whitelisted users do not follow legacy memory behavior.
- Any Short-term/Archive/Long-term write can occur before minimum deletion/export/account-purge coverage passes.
- Any old-memory import write lacks source snapshot/high-water mark and drift handling.
- Any Long-term write bypasses ledger, idempotency claim, or per-user writer lease/serialization.
- Any default Omi/chat/MCP/developer/third-party read returns Archive without explicit opt-in + explicit archive query.
- Any raw/source artifact has unknown preservation/loss/tombstone outcome.
- Any duplicate Short-term, Archive, vector, patch application, review item, ledger commit, or source tombstone appears on rerun.
- Any active credential/secret enters Long-term or default third-party access.
- Migration/backfill/repair metrics pollute organic memory-created, engagement, notification, search, export, memory-count, or cohort dashboards.

---

# Tickets

## T00 — Simple V17 rollout config and allowlist

**Goal:** Add the smallest rollout control plane that lets us test V17 without changing old memory behavior by default.

**Files:**
- Create: `backend/config/v17_memory.py`
- Modify: `backend/utils/memory_ingestion/rollout.py`
- Test: `backend/tests/unit/test_v17_memory_config.py`
- Test: `backend/tests/unit/test_memory_rollout.py`

**Config surface:**

```text
V17_MEMORY_ENABLED_USERS=<comma-separated uids>
V17_MODE=off|shadow|write|read
V17_BACKFILL_ENABLED=false|true
V17_BACKFILL_DAILY_LIMIT=<int>
V17_ARCHIVE_OPT_IN_ENABLED=false|true
```

**Acceptance criteria:**

- Empty/missing config means no user is on V17.
- Non-whitelisted users use existing old memory paths unchanged.
- `shadow` permits dry-run/shadow artifacts only.
- `write` permits whitelisted V17 writes only after downstream safety gates pass.
- `read` permits whitelisted V17 read service only after read/vector policy gates pass.
- Product rollout depends on allowlist + mode, not many independent toggles.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_config.py tests/unit/test_memory_rollout.py -q
```

---

## T01 — Product memory tier contracts and DTOs

**Goal:** Define canonical product tier metadata and additive DTO fields.

**Files:**
- Create: `backend/models/memory_tiers.py`
- Create: `backend/models/v17_product_memory.py`
- Modify: `backend/models/memories.py`
- Modify: `backend/models/v17_memory_contracts.py`
- Test: `backend/tests/unit/test_memory_tiers.py`
- Test: `backend/tests/unit/test_v17_product_memory.py`
- Test: `backend/tests/unit/test_v17_memory_contracts.py`

**Required fields:**

```text
memory_tier = short_term | long_term | archive
allowed_use = default | explicit_query | admin_debug | export_only
normal_default_access = true|false
explicit_archive_query_only = true|false
source_refs
provenance_summary
risk_flags
source_tombstoned
migration_source
```

**Acceptance criteria:**

- Product terminology is Short-term / Long-term / Archive.
- `context_only` may remain an internal route, but is not a product tier.
- Legacy records without tier fields remain API-compatible.
- Archive defaults to `normal_default_access=false`.
- Short-term + Long-term default to normal access unless sensitivity/privacy blocks.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_tiers.py tests/unit/test_v17_product_memory.py tests/unit/test_v17_memory_contracts.py -q
```

---

## T02 — Canonical evidence/provenance schema

**Goal:** Define one evidence object shape used by patch adapter, ledger, source tombstones, projection repair, read service, export, and deletion.

**Files:**
- Create: `backend/models/memory_evidence.py`
- Modify: `backend/models/v17_product_memory.py`
- Modify: `backend/models/v17_memory_contracts.py`
- Modify: `backend/utils/memory/v17_patch_adapter.py`
- Modify: `backend/database/memory_ledger.py`
- Test: `backend/tests/unit/test_memory_evidence_schema.py`

**Schema must cover:**

```text
source_type
source_id
conversation_id
artifact_refs
quote_refs / span refs
content_hash
lineage_id
source_deleted/source_tombstoned
provenance_visibility
encryption_or_redaction_status
patch_id / commit_id when applicable
```

**Acceptance criteria:**

- Same evidence shape round-trips through V17 patch adapter, ledger commits/fold, source tombstone logic, projection repair, read service, export, and deletion tests.
- Source deletion can identify and tombstone evidence produced by V17 patches.
- Evidence with unavailable raw artifact still has explicit missing/loss reason.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_evidence_schema.py -q
```

---

## T03 — V17 collections and Firestore/index plan

**Goal:** Centralize new collection paths and document query/index shapes before writes.

**Files:**
- Create: `backend/database/v17_collections.py`
- Create: `docs/epics/v17_memory_firestore_indexes.md`
- Test: `backend/tests/unit/test_v17_collections.py`

**Collections:**

```text
users/{uid}/memory_short_term/{short_term_id}
users/{uid}/memory_archive/{archive_id}
users/{uid}/memory_patch_applications/{idempotency_key}
users/{uid}/memory_lineage/{lineage_id}
users/{uid}/memory_backfill_runs/{run_id}
users/{uid}/memory_backfill_cursors/{cursor_id}
users/{uid}/memory_export_jobs/{job_id}
users/{uid}/memory_deletion_jobs/{job_id}
```

Existing Long-term stores remain:

```text
users/{uid}/memory_state/head
users/{uid}/memory_commits/{commit_id}
users/{uid}/memories/{memory_id}  # compatibility projection
```

**Acceptance criteria:**

- No V17 code hardcodes collection names outside `v17_collections.py`.
- Index doc covers Short-term, Archive, patch applications, lineage, backfill cursors, review/status queries.
- Cursor pagination is preferred over offset for high-volume migration paths.
- Production write rollout is blocked until indexes are deployed/tested or manual deployment is documented.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_collections.py -q
```

---

## T04 — Encryption/redaction and sensitive-data policy for new V17 stores

**Goal:** Ensure V17 stores respect existing enhanced-protection and logging/security conventions, with explicit policy for sensitive categories.

**Files:**
- Create: `docs/epics/v17_memory_data_protection.md`
- Create: `backend/utils/memory/v17_redaction.py`
- Modify: `backend/models/v17_product_memory.py`
- Test: `backend/tests/unit/test_v17_memory_redaction.py`

**Stores covered:**

```text
Short-term records
Archive records
Long-term ledger commits
patch applications
lineage
search replay artifacts
review/non-active route payloads
vector metadata
export snapshots
telemetry/error payloads
```

**Sensitive taxonomy:**

```text
credentials/secrets
financial
health
intimate/sexual
minors
third-party personal data
workplace confidential
identity/authentication
safety risk
```

For each category, define whether it may be stored in Short-term, included in default access, backfilled to Long-term, visible in Archive search, exported by default, or exposed to MCP/third-party tools.

**Acceptance criteria:**

- Enhanced-protection users do not get plaintext memory content, evidence quotes, raw artifacts, search replay payloads, review payloads, lineage payloads, vector metadata, or export snapshots stored outside the approved encryption/redaction model.
- Credentials/secrets are never active Long-term and never exposed through default third-party/MCP/developer access.
- Sensitive false positives can be preserved with restricted access rather than silently dropped.
- Logs use sanitized/summarized data only.
- Tests cover sensitive content, error messages, and export snapshots.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_redaction.py -q
```

---

## T05 — Source-of-truth and write-path audit

**Goal:** Identify and gate every current memory mutation path before V17 write mode.

**Files:**
- Create: `docs/epics/v17_memory_write_path_audit.md`
- Create: `backend/services/v17_memory_write_service.py` (skeleton only)
- Test: `backend/tests/unit/test_v17_non_whitelisted_legacy_unchanged.py`

**Audit these files/functions:**

```text
backend/routers/memories.py
backend/routers/developer.py
backend/routers/mcp.py
backend/routers/tools.py
backend/utils/conversations/process_conversation.py
backend/database/memories.py
backend/database/memory_ledger.py
backend/database/review_queue.py
backend/database/vector_db.py
```

**Acceptance criteria:**

- Document every create/edit/delete/review/visibility/source-delete route.
- For each route, classify: legacy-only, V17 shadow, V17 write-service, blocked/deferred.
- Non-whitelisted tests prove old behavior remains unchanged.
- No Long-term write can bypass ledger once V17 write mode is enabled.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_non_whitelisted_legacy_unchanged.py -q
```

---

## T06 — Minimum deletion/export/account-purge coverage gate

**Goal:** Extend existing deletion/export/account-purge conventions to V17 metadata before any staff/customer V17 write.

**Files:**
- Create: `backend/services/memory_deletion_service.py`
- Create: `backend/services/memory_export_service.py`
- Create: `backend/database/v17_account_purge.py`
- Modify: `backend/routers/memories.py`
- Modify: `backend/routers/conversations.py`
- Modify: `backend/routers/users.py`
- Modify: `backend/database/memories.py`
- Modify: `backend/database/vector_db.py`
- Modify: `backend/routers/sync.py`
- Modify: `backend/routers/pusher.py`
- Test: `backend/tests/unit/test_memory_tier_deletion.py`
- Test: `backend/tests/unit/test_memory_tier_account_purge.py`
- Test: `backend/tests/unit/test_memory_tier_export.py`

**Acceptance criteria:**

- No Short-term, Archive, Long-term, lineage, patch application, vector, review, backfill, import metadata, or source-tombstone writes may be enabled for staff/customer users until this ticket’s tests pass.
- Memory deletion follows existing semantics and deletes/tombstones associated tier/vector data.
- Deleting a memory does not silently delete raw source artifacts unless existing flow does so.
- Conversation/source deletion tombstones source refs/evidence according to existing conventions.
- Account purge removes Short-term, Long-term, Archive, lineage, vectors, patch applications, backfill metadata, review records, and source tombstones.
- Export can include Long-term, Short-term, Archive, provenance/source refs, tombstones/deleted history where existing export policy allows.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_tier_deletion.py tests/unit/test_memory_tier_account_purge.py tests/unit/test_memory_tier_export.py -q
```

---

## T07 — Short-term and Archive persistent stores

**Goal:** Store source-backed Short-term and Archive memories with deterministic IDs and tier policy.

**Files:**
- Create: `backend/database/product_memory_items.py`
- Create: `backend/utils/memory/product_memory_import_service.py`
- Modify: `backend/database/short_term_memories.py` or document why not reused
- Test: `backend/tests/unit/test_product_memory_items.py`
- Test: `backend/tests/unit/test_product_memory_import_service.py`

**Storage behavior:**

Short-term:

```text
memory_tier=short_term
normal_default_access=true
explicit_archive_query_only=false
```

Archive:

```text
memory_tier=archive
normal_default_access=false
explicit_archive_query_only=true
```

**Acceptance criteria:**

- Deterministic ID/idempotency key prevents duplicates on rerun.
- Every record has source refs or explicit missing-source reason.
- Sensitive/secret records are not default-access.
- Archive cannot be returned by default policy.
- Raw/source artifacts are not deleted or modified.
- Store choice is unambiguous: either reuse/wrap existing `users/{uid}/short_term` or define the new store as authoritative.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_product_memory_items.py tests/unit/test_product_memory_import_service.py -q
```

---

## T08 — Old Omi memory inventory dry-run

**Goal:** Inventory legacy `users/{uid}/memories` without writes/deletes.

**Files:**
- Create: `backend/database/old_omi_memory_inventory.py`
- Create: `backend/utils/memory/old_omi_memory_inventory.py`
- Create: `backend/migrations/008_old_omi_memory_inventory.py`
- Test: `backend/tests/unit/test_old_omi_memory_inventory.py`

**Terminal outcomes:**

```text
eligible_short_term
eligible_archive
skipped_deleted
skipped_empty
failed_validation
failed_decryption
duplicate_doc_id
duplicate_content_hash
quarantined_sensitive
needs_manual_review
source_missing_but_memory_preserved
explicit_loss
```

**Acceptance criteria:**

- 100% of scanned legacy docs get exactly one terminal outcome.
- Dry-run writes nothing except local report output.
- Deleted/invalidated memories are accounted for but not resurrected.
- Decryption failures and malformed docs are explicit outcomes.
- Report is deterministic across reruns on the same snapshot.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_old_omi_memory_inventory.py -q
```

---

## T09 — Source snapshot and high-water-mark protection

**Goal:** Prevent old-memory imports and any future bulk source migration from missing, duplicating, or resurrecting records during concurrent edits/deletes.

**Files:**
- Create: `backend/database/v17_source_snapshots.py`
- Create: `backend/utils/memory/v17_source_snapshot.py`
- Modify: `backend/utils/memory/old_omi_memory_inventory.py`
- Modify: `backend/utils/memory/old_omi_memory_import.py` (if created later, add interface now)
- Test: `backend/tests/unit/test_v17_source_snapshot.py`

**Snapshot fields:**

```text
snapshot_id
uid
source_collection
created_at
high_water_timestamp_or_cursor
doc_count
schema_fingerprint
per_doc_update_time_or_version
deleted_state_seen
job_id
```

**Acceptance criteria:**

- Import write mode can only import from a recorded snapshot/high-water mark.
- Any bulk migration/import path that reads mutable source rows must use this snapshot/high-water contract, not only old Omi memory import.
- Records changed, deleted, or newly created after snapshot are reported as drift and not silently imported.
- Concurrent user deletes win over migration/import writes.
- Deleted records are not resurrected.
- Drifted records receive terminal outcome: `snapshot_drift_requeue` or `snapshot_drift_skipped`.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_source_snapshot.py -q
```

---

## T10 — Raw artifact accounting and lineage

**Goal:** Track raw/source artifacts and lineage from source → Short-term/Archive → Long-term.

**Files:**
- Create: `backend/database/memory_source_lineage.py`
- Create: `backend/utils/memory/raw_artifact_accounting.py`
- Modify: `backend/routers/sync.py`
- Modify: `backend/routers/pusher.py`
- Modify: `backend/routers/imports.py`
- Modify: `backend/utils/conversations/process_conversation.py`
- Test: `backend/tests/unit/test_raw_artifact_accounting.py`
- Test: `backend/tests/unit/test_memory_source_lineage.py`

**Accounting outcomes:**

```text
preserved
ephemeral_already_missing
dropped_before_copy
deleted_by_user
account_purged
copy_failed
explicit_loss
```

**Acceptance criteria:**

- Raw/source artifacts are kept by default when available.
- Ephemeral sync/pusher losses are observable and not claimed as preserved.
- Artifact hash/size/path recorded when bytes are available.
- Lineage connects source row/doc to Short-term/Archive item and later Long-term patch/commit.
- Logs/API reports do not expose raw sensitive content.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_raw_artifact_accounting.py tests/unit/test_memory_source_lineage.py -q
```

---

## T11 — No-silent-data-loss verifier v1

**Goal:** Produce per-user/job reports proving every source/legacy/raw artifact has lineage or explicit outcome.

**Files:**
- Create: `backend/utils/memory/no_data_loss_verifier.py`
- Create: `backend/routers/memory_admin.py`
- Test: `backend/tests/unit/test_no_data_loss_verifier.py`

**Required report fields:**

```text
uid/account scope
source type/source ID/raw artifact ID
terminal outcome
timestamp
job/run ID
remediation state
preserved vs observable loss
lineage IDs
sample IDs without raw sensitive text
```

**Report chain:**

```text
legacy memory / source row / raw artifact
→ Short-term or Archive item OR explicit skip/loss/tombstone reason
→ L2 packet if selected for backfill
→ search replay hash
→ patch
→ ledger commit OR route outcome
→ projection/vector/card if active Long-term
```

**Acceptance criteria:**

- Unknown outcome makes report red.
- Missing raw artifact accounting makes report red.
- Missing remediation state makes report red.
- Duplicate terminal outcomes make report red.
- Report distinguishes preserved vs observable loss.
- Staff/customer write rollout is blocked until report can run on allowlisted users.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_no_data_loss_verifier.py -q
```

---

## T12 — Old Omi memory import to Short-term/Archive

**Goal:** Import old Omi memories for allowlisted users into Short-term/Archive candidates, never directly Long-term.

**Files:**
- Create: `backend/utils/memory/old_omi_memory_import.py`
- Create: `backend/migrations/009_old_omi_to_short_term_archive.py`
- Modify: `backend/database/import_jobs.py`
- Modify: `backend/models/import_job.py`
- Modify: `backend/routers/imports.py`
- Test: `backend/tests/unit/test_old_omi_memory_import.py`

**Gates before write mode:**

- T06 deletion/export/purge minimum coverage passes.
- T08 dry-run inventory has 100% terminal outcomes.
- T09 source snapshot/high-water mark exists and drift handling passes.
- T11 no-silent-data-loss verifier is green for sampled/cohort users.

**Routing policy:**

| Old memory type | Target |
|---|---|
| Recent/high-confidence/manual | Short-term candidate, prioritized for backfill |
| Older/source-backed | Archive first, backfill eligible |
| Noisy/uncertain/sensitive | Preserved with flags; not default Long-term |
| Deleted/invalidated | Explicit skip/tombstone outcome |

**Acceptance criteria:**

- Non-allowlisted users are not imported.
- Old source docs are untouched.
- No Long-term/ledger active memory is created by import.
- Rerun/resume by job ID does not duplicate Short-term/Archive records.
- Import does not emit organic `Memory Created` or engagement analytics.
- Deleted/invalidated records cannot be imported except as explicit tombstone/skip outcomes.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_old_omi_memory_import.py -q
```

---

## T13 — Patch application idempotency record

**Goal:** Transactionally claim patch idempotency before any Long-term ledger write.

**Files:**
- Create: `backend/database/v17_patch_applications.py`
- Test: `backend/tests/unit/test_v17_patch_applications.py`

**Acceptance criteria:**

- Same `(uid, idempotency_key)` cannot be claimed twice as separate applied patches.
- Status transitions are explicit: `claimed`, `applied`, `skipped`, `conflict`, `failed`.
- Sanitized errors only.
- Account purge/delete coverage includes patch applications before write pilot.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_patch_applications.py -q
```

---

## T14 — Per-user Long-term writer lease/serialization

**Goal:** Ensure only one Long-term writer mutates a user’s ledger head at a time.

**Files:**
- Create: `backend/database/v17_memory_writer_leases.py`
- Create: `backend/services/v17_memory_writer_lease.py`
- Test: `backend/tests/unit/test_v17_memory_writer_lease.py`

**Lease fields:**

```text
uid
lease_id
owner_type=backfill|live_extraction|manual_edit|delete|review|mcp|developer|repair
owner_job_id
expires_at
heartbeat_at
created_at
```

**Acceptance criteria:**

- At most one Long-term ledger writer per user may mutate ledger head at a time.
- Live extraction, backfill, user edits, review accepts, deletes, MCP/developer writes, and repair writes acquire the same lease or equivalent serialized transaction.
- Crash/timeout releases or expires lease safely.
- Tests cover concurrent patch apply, user edit, delete, review accept.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_memory_writer_lease.py -q
```

---

## T15 — Long-term patch applier and ledger write service

**Goal:** Apply L2 patches to Long-term memory through append-only ledger with idempotency and conflict handling.

**Files:**
- Create: `backend/utils/memory/v17_patch_applier.py`
- Create/extend: `backend/services/v17_memory_write_service.py`
- Modify: `backend/utils/memory/v17_patch_adapter.py`
- Modify: `backend/database/memory_ledger.py`
- Modify: `backend/database/review_queue.py`
- Modify: `backend/utils/memory/v17_projections.py`
- Test: `backend/tests/unit/test_v17_patch_applier.py`
- Test: `backend/tests/unit/test_v17_memory_write_service.py`

**Rules:**

- All active Long-term changes go through ledger.
- Idempotency claim from T13 is required.
- Writer lease/serialization from T14 is required.
- `HeadConflict` records conflict and triggers replan/retry; no blind apply.
- Evidence schema from T02 is used consistently.
- Patch applier cannot apply in `V17_MODE=shadow`.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_patch_applier.py tests/unit/test_v17_memory_write_service.py tests/unit/test_memory_ledger.py -q
```

---

## T16 — Progressive Long-term backfill dry-run

**Goal:** Build dry-run Long-term backfill over Short-term/Archive without ledger writes.

**Files:**
- Create: `backend/utils/memory/l2_backfill_orchestrator.py`
- Create: `backend/database/l2_backfill_jobs.py`
- Create: `backend/jobs/v17_l2_backfill_worker.py`
- Create: `backend/routers/memory_backfill.py`
- Test: `backend/tests/unit/test_l2_backfill_orchestrator.py`
- Test: `backend/tests/unit/test_l2_backfill_jobs.py`

**Acceptance criteria:**

- Dry-run writes zero ledger commits and zero active Long-term facts.
- Cursor resumes after crash.
- Sensitive records excluded unless explicit policy enables them.
- Route distribution includes active/review/archive/reject/hidden/skip.
- Anti-reward-hacking metrics count useful memories left in Archive/review/reject.
- Replay hash is stable for same inputs.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_l2_backfill_orchestrator.py tests/unit/test_l2_backfill_jobs.py -q
```

---

## T17 — Review/non-active route persistence and idempotency

**Goal:** Persist review, Archive/context, reject, hidden, and skip outcomes so they are auditable and duplicate-proof.

**Files:**
- Create: `backend/database/v17_non_active_memory_routes.py`
- Modify: `backend/database/review_queue.py`
- Modify: `backend/utils/memory/v17_patch_applier.py`
- Test: `backend/tests/unit/test_v17_non_active_routes.py`

**Acceptance criteria:**

- Same patch/run cannot create duplicate review items.
- Review, Archive/context, reject, hidden, and skip outcomes persist idempotency key, source IDs, reason, route, run ID, and audit metadata.
- Non-active outcomes are visible to no-silent-data-loss reports and benchmark/reward-hacking audits.
- Non-active outcomes never appear in default Long-term reads.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_non_active_routes.py -q
```

---

## T18 — Progressive Long-term write-mode backfill and operational budgets

**Goal:** Enable capped Long-term backfill writes for allowlisted users after T13–T17 pass.

**Files:**
- Modify: `backend/utils/memory/l2_backfill_orchestrator.py`
- Modify: `backend/jobs/v17_l2_backfill_worker.py`
- Modify: `backend/routers/memory_backfill.py`
- Modify: `backend/config/v17_memory.py`
- Test: `backend/tests/unit/test_l2_backfill_write_mode.py`
- Test: `backend/tests/unit/test_v17_backfill_limits.py`

**Budgets:**

```text
users/day
Short-term/Archive imports/day
Long-term backfill items/day
L2 calls/day
global LLM calls/day
review items/day
Firestore reads/writes/day or throughput
vector upserts/deletes/day or throughput
cost/day
support tickets / error rate
queue age
job latency
```

**Acceptance criteria:**

- Write mode processes at most configured batch size/daily cap.
- Document initial threshold values for every listed budget before enabling write mode, even if values are conservative placeholders.
- Exceeding budgets auto-pauses affected stage.
- Duplicate-proof across reruns/crashes.
- Head conflicts do not corrupt state.
- Pause/rollback stops workers without cursor corruption.
- Metrics emitted as migration/backfill, not organic engagement.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_l2_backfill_write_mode.py tests/unit/test_v17_backfill_limits.py -q
```

---

## T19 — Short-term lifecycle and aging policy

**Goal:** Prevent Short-term from becoming an unbounded default-access bucket.

**Files:**
- Create: `backend/utils/memory/short_term_lifecycle.py`
- Create: `backend/jobs/v17_short_term_lifecycle_worker.py`
- Modify: `backend/database/product_memory_items.py`
- Test: `backend/tests/unit/test_short_term_lifecycle.py`

**Lifecycle outcomes:**

```text
remain_short_term
promote_to_long_term
archive
reject_or_hide
source_tombstoned
```

**Acceptance criteria:**

- Short-term records cannot remain default-access indefinitely without explicit lifecycle decision.
- Stale or L2-processed records transition to Long-term, Archive, or hidden/rejected according to policy.
- Default reads exclude stale Short-term.
- Lifecycle transitions are idempotent and auditable.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_short_term_lifecycle.py -q
```

---

## T20 — Existing-namespace vector metadata filters and repair

**Goal:** Use existing `ns2` memory namespace with strict metadata filters for tier-safe retrieval.

**Files:**
- Create: `backend/database/v17_vector_metadata.py`
- Create: `backend/migrations/010_repair_v17_memory_vectors.py`
- Modify: `backend/database/vector_db.py`
- Modify: `backend/utils/memory/v17_projections.py`
- Modify: `backend/database/projection_repair.py`
- Test: `backend/tests/unit/test_v17_vector_metadata.py`
- Test: `backend/tests/unit/test_v17_vector_filters.py`

**Acceptance criteria:**

- Vector IDs are deterministic and collision-proof across Short-term, Long-term, Archive, and legacy records.
- Default Omi/chat/third-party vector search cannot return Archive.
- Explicit archive search returns Archive only.
- Sensitive/hidden/source-tombstoned records excluded by default.
- Rerunning vector repair creates no duplicate vectors.
- Deleting/tombstoning source or memory removes or marks stale vectors so default search cannot return them.
- Drift report includes duplicate IDs, missing vectors, stale vectors, metadata mismatches, orphan vectors, and failed repairs.
- Existing legacy vector behavior unchanged for non-whitelisted users.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_vector_metadata.py tests/unit/test_v17_vector_filters.py -q
```

---

## T21 — Unified memory read service and API compatibility

**Goal:** Centralize read policy so default product reads return Short-term + Long-term; Archive only by explicit query/opt-in.

**Files:**
- Create: `backend/services/memory_read_service.py`
- Create: `backend/models/memory_read.py`
- Modify: `backend/utils/memory/v17_read_api.py`
- Modify: `backend/routers/memories.py`
- Modify: `backend/database/memory_reads.py`
- Test: `backend/tests/unit/test_memory_read_service.py`
- Test: `backend/tests/unit/test_v3_memories_tier_compat.py`

**`GET /v3/memories` optional params:**

```text
tier=short_term|long_term|archive|all
include_archive=false
include_source_refs=false
include_provenance=false
include_review=false
```

**Acceptance criteria:**

- Non-whitelisted users use legacy reads.
- Whitelisted read mode default returns Short-term + Long-term.
- Archive requires explicit params/opt-in.
- Existing clients parse unchanged/additive response shape.
- Old clients ignore unknown tier/provenance fields and existing `limit`/pagination behavior continues during rollout.
- Server-side tier filters and cursor pagination are available before large imports are visible.
- Rollback to legacy read is one config change.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_memory_read_service.py tests/unit/test_v3_memories_tier_compat.py -q
```

---

## T22 — External write semantics for APIs/tools

**Goal:** Define and implement tier-specific write semantics for `/v3`, developer API, MCP, tools, and agent memory tools.

**Files:**
- Modify: `backend/routers/memories.py`
- Modify: `backend/routers/developer.py`
- Modify: `backend/routers/mcp.py`
- Modify: `backend/routers/tools.py`
- Modify: `backend/services/v17_memory_write_service.py`
- Modify: `backend/services/memory_deletion_service.py`
- Test: `backend/tests/unit/test_v17_external_write_semantics.py`

**Routes covered:**

```text
POST /v3/memories
PATCH /v3/memories/{id}
PATCH /v3/memories/{id}/visibility
DELETE /v3/memories/{id}
DELETE /v3/memories
Developer API memory create/edit/delete
MCP memory create/edit/delete
Tools memory create/edit/delete
Agent remember/forget/update
```

**Acceptance criteria:**

- Non-whitelisted users remain legacy-only.
- New manual memories default to Short-term unless explicitly stable/Long-term.
- Long-term writes go through ledger/write service only.
- Deletes go through memory deletion service and existing conventions.
- Archive cannot be created/exposed accidentally.
- Third-party/MCP/developer writes cannot create Archive-visible or Long-term-visible records without policy and tier validation through the write service.
- No V17-enabled external write route mutates `users/{uid}/memories`, vectors, Short-term, Archive, review records, or Long-term ledger directly.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_external_write_semantics.py -q
```

---

## T23 — Chat, tools, MCP, developer API read policies

**Goal:** Apply read service to all product/agent/third-party surfaces.

**Files:**
- Modify: `backend/utils/llms/memory.py`
- Modify: `backend/utils/retrieval/tools/memory_tools.py`
- Modify: `backend/utils/retrieval/tool_services/memories.py`
- Modify: `backend/utils/retrieval/agentic.py`
- Modify: `backend/utils/retrieval/graph.py`
- Modify: `backend/routers/chat.py`
- Modify: `backend/routers/tools.py`
- Modify: `backend/routers/mcp.py`
- Modify: `backend/routers/developer.py`
- Test: `backend/tests/unit/test_chat_memory_policy.py`
- Test: `backend/tests/unit/test_tools_memory_policy.py`
- Test: `backend/tests/unit/test_mcp_memory_policy.py`
- Test: `backend/tests/unit/test_developer_memory_policy.py`
- Test: `backend/tests/unit/test_third_party_memory_policy.py`

**Policy matrix:**

| Consumer | Default tiers | Archive |
|---|---|---|
| Omi chat | Short-term + Long-term | explicit search only |
| Agent mode | Short-term + Long-term | explicit tool/search only |
| MCP/third-party | Short-term + Long-term | opt-in + explicit query only |
| Developer API | Short-term + Long-term | opt-in + explicit query only |
| Admin/eval | configurable | configurable |

**Archive opt-in contract:**

- Admin/app policy must permit Archive.
- Request/tool must explicitly ask for Archive.
- Sensitive/review/hidden/source-tombstoned still excluded unless admin/eval policy explicitly permits.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_chat_memory_policy.py tests/unit/test_tools_memory_policy.py tests/unit/test_mcp_memory_policy.py tests/unit/test_developer_memory_policy.py tests/unit/test_third_party_memory_policy.py -q
```

---

## T24 — Agent-mode memory management tools

**Goal:** Let Omi manage memory conversationally so UI can stay simple.

**Files:**
- Create: `backend/utils/retrieval/tools/memory_management_tools.py`
- Modify: `backend/utils/retrieval/tools/memory_tools.py`
- Modify: `backend/utils/retrieval/agentic.py`
- Modify: `backend/routers/tools.py`
- Test: `backend/tests/unit/test_agent_memory_management_tools.py`
- Test: `backend/tests/unit/test_agent_tools_memory_schema.py`

**Tools:**

```text
remember_memory_tool(content, tier_hint optional)
forget_memory_tool(memory_id or query)
list_memories_tool(tier optional)
search_memories_tool(query, include_archive=false)
search_archive_memories_tool(query)
get_memory_provenance_tool(memory_id)
update_memory_tool(memory_id, content)
set_memory_visibility_or_use_policy_tool(memory_id, policy)
promote_to_long_term_tool(memory_id)
archive_or_demote_memory_tool(memory_id)
review_memory_tool(memory_id, decision)  # only if backend review exists
```

**Acceptance criteria:**

- Remember defaults to Short-term unless user explicitly asks for stable/Long-term memory.
- Forget by query returns candidates and requires confirmation if ambiguous.
- Forget output states whether raw source is affected; default is memory only, following existing deletion conventions.
- Default search returns Short-term + Long-term.
- Archive search is explicit.
- Tool outputs include `memory_id`, `tier`, provenance/source summary, and access policy.
- Tool descriptions use Short-term/Long-term/Archive terms only.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_agent_memory_management_tools.py tests/unit/test_agent_tools_memory_schema.py -q
```

---

## T25 — Minimal user UI surfaces

**Goal:** Add simple tier labels/filter/provenance/delete copy across user-facing surfaces without heavy review UI.

**Mobile files:**
- `app/lib/backend/schema/memory.dart`
- `app/lib/backend/http/api/memories.dart`
- `app/lib/providers/memories_provider.dart`
- `app/lib/pages/memories/page.dart`
- `app/lib/pages/memories/widgets/memory_item.dart`
- `app/lib/pages/memories/widgets/memory_dialog.dart`
- `app/lib/pages/memories/widgets/memory_management_sheet.dart`
- `app/lib/l10n/app_en.arb` and all locale ARBs

**macOS files:**
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoryExportDestinationSheet.swift`

**Web/Windows files:**
- `web/frontend/src/types/memory.types.ts`
- `web/frontend/src/components/memories/*`
- `desktop/windows/src/renderer/src/hooks/useMemories.ts`
- `desktop/windows/src/renderer/src/pages/Memories.tsx`

**Acceptance criteria:**

- UI labels only: Short-term / Long-term / Archive.
- No L1/L2/Durable/Context-only terminology.
- Archive is visually distinct and not implied as default personalization.
- Server-side tier filters and cursor pagination are used before large imports are visible.
- Simple source/provenance shown where available.
- Delete copy says deleting a memory removes Omi’s memory item/projection/vector; it does not delete original conversation/audio/imported file unless source/account deletion does so.
- Source deletion copy says related evidence may be tombstoned and memories may change.
- All mobile strings use l10n.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/app
flutter test test/memory_tier_model_test.dart test/memories_api_tier_test.dart test/memories_page_tier_filter_test.dart
flutter gen-l10n

cd /root/workspace/omi-memory-ingestion-pipeline/desktop/macos
xcrun swift build -c debug --package-path Desktop
xcrun swift test --package-path Desktop --filter MemoryTierModelTests
xcrun swift test --package-path Desktop --filter MemoryPromptPolicyTests

cd /root/workspace/omi-memory-ingestion-pipeline/web/frontend && npm run typecheck
cd /root/workspace/omi-memory-ingestion-pipeline/desktop/windows/src/renderer && npm run typecheck
```

---

## T26 — Admin policy controls, Chat Lab, telemetry, and rollout kill switches

**Goal:** Keep rollout observable, configurable, and safe without complicating user UI.

**Files:**
- Create: `backend/utils/memory/v17_telemetry.py`
- Create: `web/admin/components/dashboard/memory-policy-selector.tsx`
- Modify: `backend/utils/metrics.py`
- Modify: `backend/routers/metrics.py`
- Modify: `backend/jobs/v17_l2_backfill_worker.py`
- Modify: `web/admin/app/(protected)/dashboard/apps/page.tsx`
- Modify: `web/admin/components/dashboard/app-detail-view.tsx`
- Modify: `web/admin/app/(protected)/dashboard/chat-lab/page.tsx`
- Test: `backend/tests/unit/test_v17_telemetry.py`
- Test: `backend/tests/unit/test_v17_rollout_controls.py`
- Test: `backend/tests/unit/test_v17_metrics_hygiene.py`

**Admin policy options:**

```text
No memory
Long-term + Short-term
Long-term + Short-term + Archive opt-in
Admin/debug configurable
```

**Metrics hygiene fields:**

```text
operation_type=migration|backfill|repair|shadow|import
counts_as_user_memory_created=false
counts_as_engagement=false
counts_as_organic_search=false
counts_as_export_activity=false
counts_as_notification_activity=false
counts_as_memory_count_growth=false unless explicitly dashboard-separated
counts_as_cohort_activation=false
```

**Kill switches must cover:**

```text
inventory
source snapshot/high-water jobs
raw artifact copy/accounting
no-silent-data-loss verifier/admin jobs
old-memory import
Short-term/Archive writes
Long-term dry-run
patch apply
source tombstone propagation
vector repair
export/delete/account-purge side-effecting jobs
read switch
benchmark/repair jobs that touch product state
```

**Acceptance criteria:**

- Chat Lab can test default memory vs explicit Archive search vs no memory.
- Third-party app policy defaults to Long-term + Short-term only.
- Bulk events cannot count as organic memory creation, engagement, notification activity, search, export, memory growth, or cohort activation.
- Stage-specific kill switches are tested before corresponding stage can run.
- Dashboard distinguishes Short-term, Long-term, Archive.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_telemetry.py tests/unit/test_v17_rollout_controls.py tests/unit/test_v17_metrics_hygiene.py -q

cd /root/workspace/omi-memory-ingestion-pipeline/web/admin
npm run typecheck
```

---

## T27 — Migration/backfill benchmark mode

**Goal:** Extend benchmark repo to evaluate old Omi export → Short-term/Archive import → Long-term backfill honestly.

**Benchmark files:**
- Create: `/root/workspace/omi-ingestion-benchmark/scripts/v17_migration_backfill_runner.py`
- Create: `/root/workspace/omi-ingestion-benchmark/scripts/v17_migration_report.py`
- Create: `/root/workspace/omi-ingestion-benchmark/tests/test_v17_migration_backfill_runner.py`
- Create: `/root/workspace/omi-ingestion-benchmark/tests/test_v17_migration_report.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/scripts/v17_4_e2e_pipeline.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/scripts/v10_judge.py`
- Modify: `/root/workspace/omi-ingestion-benchmark/docs/v17_implementation_tickets.md`

**Required reports:**

- Base Omi anchor leftmost and clearly labeled.
- Short-term import completeness.
- Archive completeness.
- Long-term active-only yield.
- Active + review yield.
- Active + Archive yield.
- Active + review + Archive yield.
- All proposed non-rejected yield.
- Missed-useful audit for Archive/review/reject/hidden routes.
- Useful-grounded-safe per 100 contexts.
- Harmful/noisy per 100 contexts.
- Source-stratified route distribution.
- Bootstrap confidence intervals or equivalent uncertainty reporting where feasible.
- Replay/idempotency counts.

**Acceptance criteria:**

- Eval cannot claim quality improvement by hiding useful memories in Archive/reject/review.
- No launch claim based only on cleaner Long-term metrics if total useful yield regresses.
- Useful-grounded-safe yield remains Base-like unless explicit tradeoff is documented.
- Harmful/noisy remains below Base Omi projection.
- Active secrets = 0.
- Non-primary active without explicit identity = 0.

**Verification:**

```bash
cd /root/workspace/omi-ingestion-benchmark
pytest tests/test_v17_migration_backfill_runner.py tests/test_v17_migration_report.py -q
```

---

## T28 — End-to-end idempotency and rollout safety verifier

**Goal:** Add one cross-cutting verifier that proves reruns/crashes do not duplicate side effects and rollout gates are met.

**Files:**
- Create: `backend/utils/memory/v17_safety_verifier.py`
- Create: `backend/tests/unit/test_v17_end_to_end_idempotency.py`
- Create: `backend/tests/unit/test_v17_rollout_safety_verifier.py`
- Modify: `backend/test.sh`

**Idempotency matrix:**

```text
old memory inventory
Short-term/Archive import
raw artifact accounting
lineage creation
vector upserts/deletes/repairs
L2 packet generation
search replay hash
patch synthesis
patch application
ledger commit
review queue / non-active outcome creation
source tombstone propagation
export/delete side effects
account purge side effects
```

**Acceptance criteria:**

- Rerun/crash/replay produces no duplicate active facts, no duplicate review/non-active outcomes, no stale duplicate vectors, and no cursor corruption.
- Verifier can answer whether a user/cohort can move from shadow → write → read.
- `backend/test.sh` includes the V17 ticket tests required for rollout gates.

**Verification:**

```bash
cd /root/workspace/omi-memory-ingestion-pipeline/backend
pytest tests/unit/test_v17_end_to_end_idempotency.py tests/unit/test_v17_rollout_safety_verifier.py -q
bash test.sh
```

---

## Spot-check checklist against the Epic

- [x] Short-term / Long-term / Archive product vocabulary.
- [x] No user-visible Context-only state.
- [x] Old memory behavior unchanged for non-whitelisted users.
- [x] Simple config surface.
- [x] Short-term + Long-term default access for Omi/agent/third-party/developer API.
- [x] Archive explicit query/opt-in only.
- [x] Existing deletion conventions extended to V17 tiers before writes.
- [x] Raw/source artifacts kept by default and loss reported honestly.
- [x] Same `ns2` vector namespace with strict metadata filters first.
- [x] No Long-term write bypasses ledger, idempotency claim, or per-user writer lease.
- [x] Patch/ledger/review/vector/source-tombstone idempotency.
- [x] Source snapshot/high-water mark before old-memory import writes and all mutable bulk source migrations.
- [x] Source/legacy/raw no-silent-data-loss verifier.
- [x] Progressive backfill with budgets, documented initial thresholds, pause/resume, rollback, and kill switches.
- [x] Kill switches include snapshot, raw accounting, verifier/admin, source tombstone, export/delete/account-purge side-effecting jobs.
- [x] Benchmarks include Base Omi anchor, uncertainty, route-yield matrix, and anti-reward-hacking missed-useful audits.
- [x] UI stays minimal; memory management available through agent tools.
- [x] Metrics hygiene prevents migration/backfill/repair from polluting organic dashboards.

---

## Wave review log

### Wave 1 — Ticket drafting

Three drafting subagents produced backend/data/control-plane, migration/backfill/eval, and product/API/UI/agent-tool ticket sets.

### Wave 3 — Final review and spot check

Three final review subagents reviewed the revised ticket doc against the Epic and decision brief:

- Backend/data architecture: **APPROVE_WITH_CHANGES**.
- Migration/backfill/eval/ops safety: **APPROVE_WITH_CHANGES**.
- Product/API/UI/agent integration: **APPROVE_WITH_CHANGES**.

Final requested changes incorporated:

- Added Epic supersession note so final Short-term / Long-term / Archive policy overrides older historical Durable/L1/L2/Context-only wording.
- Reaffirmed existing `ns2` + metadata filters as final vector default; separate namespace only fallback.
- Expanded sensitive-data taxonomy in T04.
- Generalized source snapshot/high-water protection to all mutable bulk source migrations, not only old-memory import.
- Required documented initial budget thresholds before write mode.
- Expanded kill switches to source snapshot jobs, raw accounting, no-silent-data-loss verifier/admin jobs, source tombstone propagation, and export/delete/account-purge side-effecting jobs.
- Hardened `/v3` read compatibility for old clients and existing `limit` behavior.
- Added explicit third-party/MCP/developer write-safety criterion.

Final committee outcome before Oracle: **ready to use as the implementation ticket queue**, with the tickets document as the implementation source of truth.

### Oracle review — External architecture/code critique

Oracle critique is recorded in `docs/epics/v17_memory_oracle_review.md`.

Oracle decision prescription is recorded in `docs/epics/v17_memory_oracle_decision_prescription.md`.

Verdict after decision prescription: **GO for P0 amendment implementation, BLOCKED for production writes**. T00–T05 can proceed as design/audit work, but no persistent V17 writes, read switch, vector changes, or external API changes should ship until P0 amendments are incorporated.

Oracle P0 blockers to incorporate before implementation:

1. Define one atomic, fenced Long-term write protocol across idempotency claim, writer lease/fencing token, ledger append, head update, source-version check, purge-generation check, and recovery from every crash point.
2. Replace empty-list synthesis failures with typed, auditable outcomes so provider failures, parse errors, malformed patches, quote-wrapper candidates, and policy rejections cannot silently advance cursors or improve benchmarks by disappearance.
3. Replace/adapt current `L1MemoryArchiveItem` contract so fresh source-backed extraction becomes default-access Short-term, not Archive by default.
4. Define rollout/cutover/rollback reconciliation semantics; a simple `off|shadow|write|read` scalar is not enough to prevent disappearing memories or resurrection after fallback.
5. Add deletion/account-purge generation fences and apply-time source tombstone/version checks so delayed workers cannot recreate deleted data.
6. Add durable outbox/projection/vector consistency and fail-closed shared-namespace search gateway before any V17 vector/read rollout.
7. Define stable logical memory identity across Short-term → Long-term/Archive transitions and cross-tier read/dedup/ranking/pagination behavior.
8. Strengthen sensitive-data enforcement, third-party consent/scopes, raw-artifact copy-before-drop, live conversation-to-Short-term ingestion, review backlog resolution, and quantitative launch gates.

The next planning pass should convert these Oracle findings into new P0/P1 tickets and reorder the queue so safety infrastructure, benchmark gates, vector gateway, and rollout verifier precede write-mode tickets.
