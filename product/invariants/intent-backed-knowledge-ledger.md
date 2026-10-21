# INV-MEM-6: Intent-backed knowledge ledger

**Status:** proposed

**Proposed on:** 2026-08-23

**Statement:** New user knowledge is an append-oriented fact, document, or
trigger row written through universal canonical apply only when backed by
demonstrated user intent, explicit action, onboarding, or the bounded daily
reconciliation contract. Capture finalization never extracts knowledge.

This statement becomes lockable only when its named guards hold on all required
clients and the migration/cutover gates prove that it can replace, rather than
silently bypass, the currently locked tiered lifecycle.

## MUST NOT

- Extract memory during conversation finalization, first conversation open,
  passive X ingestion, or continuous screen processing.
- Create a parallel collection, profile snapshot authority, or client-local
  mutation authority beside canonical `MemoryService` apply.
- Label an agent-derived conclusion as a direct user assertion.
- Put third-party facts, closed facts, unslotted episodic observations,
  playbook bodies, or trigger bodies into the rendered user profile.
- Mutate an old fact's semantic content in place. Amend by appending a new row
  and closing the prior row in the same canonical commit.
- Reopen a standalone closed fact in place. An explicit user reopen may append
  one fresh current tail, but the closed source remains immutable history and
  a source-keyed receipt prevents duplicate tails.
- Run scheduled Short-term consolidation or standalone profile synthesis as a
  user-knowledge writer.
- Send screen pixels for interpretation until text/vector retrieval identifies
  a relevant frame, except the one policy-compliant conversation keyframe.
- Delete compatibility readers, writers, schedules, indexes, or rollback seams
  only when their owning decision explicitly retires the path or consumer
  adoption and zero-read/zero-write evidence exists. The JIT retrieval and
  first-open paths were explicitly retired on 2026-10-18; stored ledger data
  remains available to export and privacy-deletion paths.

## Surfaces

- Canonical memory models, apply transaction, evidence, outbox, privacy,
  deletion, export, and released adapters
- Conversation finalization, supported chat tools, daily summary,
  integrations, MCP, and developer APIs
- Mobile, macOS, Windows, web, Rewind, evidence rendering, and supported trigger
  flows
- Runtime schedules, deploy manifests, indexes, runbooks, and migration tools

## Foundation contract tests

These tests make the contract executable. The agent preference tool is the
first scoped production writer on the intent-backed path. JIT retrieval,
first-open processing, and entity-timeline test suites were retired with the
2026-10-18 JIT kill; eager extraction and canonical memory lifecycle coverage
remain in scope.

- `backend/tests/unit/test_knowledge_ledger.py` — durable intent-backed schema,
  bounded deterministic renderers, and third-party isolation
- `backend/tests/unit/test_knowledge_ledger_migration.py` — deterministic
  migration/resume decisions and fail-closed Short-term adjudication
- `backend/tests/unit/test_atomicity_lifecycle_regressions.py` — agent preference
  writes use retry-stable ledger provenance and fail closed without user authority
- `backend/tests/unit/test_universal_memory_service.py` and
  `backend/tests/unit/test_memory_apply_store.py` — standalone closed-row
  reopen policy, privacy fences, exact retry, and duplicate-tail receipt

## Path globs

- `backend/models/memory_*.py`
- `backend/models/product_memory.py`
- `backend/utils/memory/**`
- `backend/utils/conversations/**`
- `backend/utils/retrieval/tools/**`
- `backend/utils/social.py`
- `backend/deploy/runtime_env*`
- `app/lib/backend/schema/memory.dart`
- `app/lib/models/**`
- `desktop/macos/Desktop/Sources/**`
- `desktop/windows/src/**`
- `backend/docs/memory/**`

## PR rule

Do **not** require naming. The guard suite carries this whole-product rule;
whole-client-tree citation would become ritual rather than evidence.

## Compatibility

The stored `tier` field remains a directional compatibility projection while
supported released clients migrate. A ledger row uses `long_term` there but
does not participate in Short-term promotion. This is a time-bounded adapter,
not a second lifecycle or authority. Removal requires the adoption/deletion
proof named above.
