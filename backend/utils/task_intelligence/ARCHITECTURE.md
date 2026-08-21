# Task intelligence architecture map

This package owns task-intelligence policy and orchestration. HTTP routes live
in `backend/routers/`; durable records, leases, and transaction boundaries live
in `backend/database/`; public request and stored-record contracts live in
`backend/models/`. Every authenticated owner uses this authority. Callers must
preserve account-generation, malformed-control, ownership, idempotency, device,
and proactive-choice fences; memory cohort or storage origin is never a task
entitlement.

## Universal workflow authority

`chat_first_eligibility.py` loads persisted task-workflow control and is the
reusable, fail-closed authority for Chat-first ingress. `rollout.py` validates
workflow mode, account generation, and explicit proactive/UI choice for any
authenticated UID. A missing or malformed generation disables mutation rather
than selecting another task system. The returned generation fences Chat-first
stores, providers, metrics, and intent creation; callers must not substitute a
client claim or cached enablement.

## Capture and candidate lifecycle

- `capture_policy.py` is the pure confidence and ownership policy used by every
  capture adapter.
- `backend_capture.py` adapts backend payloads into that policy;
  `conversation_capture_policy.py` owns the database-free action-item signal
  adapter and public policy-evaluation seam used by production and hermetic
  fixtures. `conversation_capture.py` owns the universal conversation
  extraction/reconciliation boundary. For deterministically matched wake-word
  segments it runs the independent classifier in
  `utils/llm/wake_word_adjudication.py` and applies the classifier plus extractor
  as a conjunction gate. A classifier verdict never creates or scores a task by
  itself; questions and task verdicts without an intersecting extraction are
  measured but intentionally produce nothing. Candidate capture either owns the
  whole extracted batch or declines it explicitly so the compatibility writer
  cannot create mixed duplicates or silent drops.
- `candidate_service.py` owns candidate acceptance, rejection, expiry, and the
  post-commit task-integration handoff. `staged_migration.py` migrates only the
  legacy staged-task representation through that lifecycle.
- `task_links.py`, `workstream_association.py`, and `workstream_index.py` bind
  validated tasks to canonical goals and workstreams. They may read resolvers
  owned by the database layer but must not become alternate persistence owners.

## Recommendations and proactive Chat-first behavior

`recommendations.py` produces deterministic task/recommendation snapshots and
dedupe keys. `live_recommendation_judgment.py` is the injectable structured
LLM-judgment seam; its output is constrained by the deterministic snapshot.

`proactive_engine.py` owns the eligibility- and generation-fenced proactive
intent paths. Its agent tier converts post-commit wake triggers into a
deterministic shortlist, then uses the injectable judge; the empty judge is the
safe default. Ordinary task completion never creates a follow-up by itself; a
meaningful, judged trigger may. Its closed deterministic tier persists
capture-arrival and daily-opener intents, and releases due deferrals before
agent judgment. A separate generation-bound cold-start path persists its
deterministic first-run intent. These functions persist intents only; the
desktop kernel remains the sole owner that materializes a visible Chat row.
`fixture_runner.py` provides deterministic fixture adapters for those policies
and must never be bound as production judgment.

## Contract changes

`contracts.py` validates the task-intelligence contract and writer manifests.
When adding a feature-specific writer or adapter, update its manifest/fixture
and tests in the same change. Keep raw user content out of rollout diagnostics,
intent metrics, and fixtures; feature-disabled paths must be inert before any
feature store or provider is touched.

Task production modules must not import `canonical_memory_cohort`,
`memory_system`, or UID inventory helpers. Recurrence evidence may flow from
memory consolidation into a workstream Candidate, but failure or absence of
that handoff never disables tasks.
