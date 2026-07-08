# Workflow Contracts

High-risk workflows must have local contracts that run from source-only changes.

A workflow is high-risk when correctness depends on checkpoint/resume behavior,
idempotent retries, side-effect fanout, rollout state, or external service
repair. Add it to `backend/testing/workflow_contracts.json` with:

- source globs that own the workflow
- focused contract tests that must run locally before PR
- invariants the tests own
- static checks such as `no_large_tuple_results` when useful

Contract tests should cover the smallest deterministic version of:

- first run
- retry after partial failure
- completed resume or repair rerun
- idempotent skip
- failure accounting for required side effects

Do not report `completed`, `verified`, or `ok` when required side effects failed
silently. Either make the side effect durable through an outbox or return a
structured failure that keeps the workflow recoverable.

Remote smoke tests should verify deployed wiring only. Core workflow invariants
belong in local contract tests.
