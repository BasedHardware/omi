# Systemic bug hardening

This record captures the recurring failure classes found in macOS and backend
bug-fix PRs reviewed in July 2026, and the guard hierarchy used to prevent them
from returning. It is intentionally about contracts and prevention layers, not
individual symptoms.

## What recent fixes taught us

| Recurring PR cluster | Violated contract | Durable prevention layer |
| --- | --- | --- |
| Desktop agent/PTT lifecycle (`#9402`, `#9411`, `#9420`, `#9424`, `#9428`) | A state transition must publish atomically; synchronous callbacks must not recursively advance a half-published transition | FIFO, non-reentrant event draining plus reducer-level behavioral tests and the complete agent runtime test suite |
| Duplicate-ID crashes (`#9288` and adjacent call sites) | Data crossing an API, persistence, or runtime boundary cannot be assumed unique | Named `Dictionary(lastWriteWins:)` policy, migration of trapping constructors, duplicate-input behavior tests, and a fail-all static check |
| Main-thread and actor stalls (`#9306`, `#9378`) | Actor isolation prevents data races; it does not make synchronous I/O non-blocking | Controllable seams and behavior tests are required for touched paths; wall-clock waits can no longer grow unnoticed |
| Backend event-loop stalls | A blocking call remains blocking when hidden behind a synchronous helper | Module-local transitive call-graph analysis, full call-chain diagnostics, and diff-scoped no-increase enforcement |
| Runtime/provider drift (`#9296`, `#9308`, `#9358`, `#9385`, `#9421`, `#9422`) | Provider selection and its required endpoint/credentials are one deployable contract | One pure provider contract shared by runtime routing and deployment validation; clients initialize lazily |
| Released-client compatibility (`#9425`) | Backend schema evolution must remain readable by the oldest supported app payloads | Directional app-client OpenAPI compatibility check in CI, independent of schema freshness |
| False-green selective CI | A test that exists but is not discovered or selected is not protection | Rename/deletion-aware changed-file discovery, conservative backend selection, full agent Vitest discovery, and workflow contract tests |
| Flaky backend duration failures | Parallelism must have one owner; nested native thread pools corrupt per-test CPU attribution and oversubscribe file-isolated workers | The unit runner pins BLAS/OpenMP pools to one thread per pytest process, and runtime validation reuses its parsed manifest instead of repeating structural work |
| Brittle source-string regressions | Implementation text is not runtime behavior | No-increase source-inspection ratchet, reasoned static-tripwire escapes, and explicit behavioral-test guidance |

PR numbers above are evidence samples, not a complete incident list. Their value
is the repeated shape: local fixes accumulated until the missing shared contract
became visible.

## Guard hierarchy

Use the highest layer that can express the invariant and keep lower layers as
backstops:

1. **Single owner or typed policy.** Make illegal ownership and collision
   behavior difficult to represent.
2. **Hermetic behavioral test.** Invoke production code through a controllable
   clock, scheduler, provider, or state-machine seam.
3. **Boundary compatibility test.** Compare producer and consumer contracts in
   the direction data actually flows.
4. **Static tripwire.** Reject a dangerous syntax or wiring pattern when runtime
   tests cannot enumerate every future call site.
5. **CI and local harness parity.** Discover the same tests locally and in CI;
   changed-file optimization must fail toward broader coverage.
6. **Real-path exercise.** Run the named desktop bundle or local backend path and
   record the result. This validates packaging and wiring that hermetic tests do
   not cover.

No single layer substitutes for the others. In particular, static source checks
do not prove behavior, and a live smoke run does not prove deterministic edge
cases.

## Rules for future bug fixes

- Search recent fixes in the same subsystem before editing. State the failed
  owner, identity, transition, or boundary contract in the PR.
- When the same cause appears twice, add a shared policy, harness, compatibility
  check, or static guard in the fix PR.
- Selective CI is an optimization only. Unknown production changes, deleted
  tests, and changed selector logic must run the full relevant suite.
- Configuration selectors are ordinary, reviewable configuration—not secrets.
  If a selector remains opaque, deployment validation must conservatively
  require every dependency it can activate.
- Keep high-blast-radius migrations separate when they need their own rollout
  and rollback plan, but land the enforceable compatibility or safety boundary
  first.

The executable rules live in `AGENTS.md`, component guides, checkers, and test
harnesses. If this record and an executable guard disagree, fix both in the same
PR.
