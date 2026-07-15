# Task intelligence architecture map

This package owns task-intelligence policy and orchestration. HTTP routes live
in `backend/routers/`; durable records, leases, and transaction boundaries live
in `backend/database/`; public request and stored-record contracts live in
`backend/models/`. Callers must resolve the user’s server-owned rollout before
performing feature work and must not substitute a client claim or a default-on
fallback.

## Rollout and cohort authority

`chat_first_eligibility.py` loads the persisted task-workflow control and is
the reusable, fail-closed authority for Chat-first ingress. It passes that
control's workflow mode and account generation to `rollout.py`, which resolves
canonical-memory cohort membership; the derived capability is enabled only for
the canonical read-mode task-intelligence cohort with the explicit UI flag on.
A control read, rollout, or memory-system error disables the feature. The
returned generation is part of the capability fence, so Chat-first stores,
providers, metrics, and intent creation must be downstream of that decision;
they must not substitute a client claim or cached enablement.

## Capture and candidate lifecycle

- `capture_policy.py` is the pure confidence and ownership policy used by every
  capture adapter.
- `backend_capture.py` adapts backend payloads into that policy; `conversation_capture.py`
  owns the legacy conversation extraction/reconciliation boundary.
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
