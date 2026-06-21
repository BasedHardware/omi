# Local-First Full-Stack Dev Harness Epic

**Status:** Proposed infra epic
**Primary customer:** V17 memory development and validation
**Long-term customer:** Any Omi feature that needs backend + desktop/app integration testing
**Related V17 docs:** `docs/rollout/v17-v3-proof-order.md`, `docs/runbooks/v17-v3-dev-cloud-proof.md`, `docs/epics/v17_memory_product_integration_epic.md`

## Problem

Omi has useful local gates, but developers still need a deployed GCP/Firebase environment to honestly test some full-stack behavior. For V17 memory in particular, this slows iteration because:

- the desktop app can run locally, but normally points at cloud backends;
- the backend has a hermetic E2E harness, but it fakes Firestore/Redis/GCS/vector services;
- local live backend setup is credential-heavy and not scenario-driven;
- V17 dev-cloud proof is intentionally strict and should remain a promotion gate, not every developer's inner loop.

The result is a gap between fast local unit/hermetic tests and expensive dev-cloud proof.

## Goal

Create a local-first development harness that lets developers run, seed, reset, and test realistic Omi memory scenarios without waiting on GCP deploys, while preserving dev-cloud proof for the things only GCP can prove.

## Non-goals

- Do not weaken V17 dev-cloud or production proof requirements.
- Do not use production data, production UIDs, production tokens, or production Firestore projects.
- Do not make local fakes count as IAM, Cloud Run revision, deployed index, telemetry sink, or rollback proof.
- Do not make V17 a dumping ground for general developer-infra work.

## Target developer experience

```bash
make dev-up
make seed-v17-scenario SCENARIO=happy_path
make test-v17-local
OMI_APP_NAME="Omi Dev Local" make desktop-run-local
make dev-reset
```

The exact command names may change to match repo conventions, but the developer loop must stay one-command and scenario-driven.

## Architecture

The harness should provide:

- Python backend on localhost.
- Rust desktop backend when desktop flows need it.
- Firestore emulator or a stricter fake with V17-compatible query/index behavior.
- Firebase Auth emulator or a signed test-token shim.
- Redis/fakeredis or local Redis.
- deterministic provider fakes for LLM, STT, embeddings, vector search, and external HTTP integrations.
- checked-in synthetic scenario fixtures for V17 memory gates, projections, cursors, cross-user isolation, and rollback/kill-switch behavior.
- desktop `.env` profile that points "Omi Dev Local" to localhost services.
- clear evidence labels that distinguish local/emulator proof from dev-cloud proof.

## Local vs dev-cloud boundary

Local-first proof can claim:

- route-selection logic;
- fail-closed semantics;
- no legacy fallback after V17 selection;
- no V17 writes in GET paths under the harness;
- desktop request/response shape compatibility;
- deterministic scenario behavior.

Local-first proof must not claim:

- real Cloud Run runtime identity;
- real Firestore IAM or least privilege;
- real deployed Firestore index readiness;
- real Firebase Auth issuer/audience behavior;
- real telemetry sinks or rollback propagation;
- production or dev-cloud activation readiness.

## Ticket pack

Executable tickets live under `.codex-autorunner/tickets/`.

| Ticket | Outcome |
|---|---|
| `TICKET-010-local-first-spec.md` | Establish the local-first harness contract and command surface. |
| `TICKET-020-dev-up-foundation.md` | Add `dev-up` / `dev-reset` foundation for backend-local services. |
| `TICKET-030-v17-scenario-fixtures.md` | Add synthetic V17 scenario fixtures and seed/reset tooling. |
| `TICKET-040-hermetic-v17-e2e.md` | Extend hermetic backend E2E with V17 scenario coverage. |
| `TICKET-050-desktop-local-profile.md` | Add a desktop local profile for "Omi Dev Local". |
| `TICKET-060-dev-cloud-preview-bridge.md` | Define optional branch preview deploy/proof bridge without weakening gates. |
| `TICKET-070-docs-and-adoption.md` | Document the developer loop and proof boundary. |

## Acceptance

- A new contributor can run at least one V17 memory happy-path and one fail-closed scenario locally without GCP deploy access.
- The desktop app can be launched against the local stack with a named dev profile.
- CI can run the hermetic V17 E2E subset without real network access.
- The docs explicitly state that local proof supplements, but does not replace, V17 dev-cloud proof.
