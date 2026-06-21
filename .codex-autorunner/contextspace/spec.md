# Local-First Full-Stack Dev Harness Spec

## Objective

Build a reusable local-first harness for Omi full-stack development. V17 memory is the first customer, but the harness must be usable for future backend + desktop/app features.

## Required capabilities

- Start the local backend stack with one command.
- Reset the local stack to a clean state with one command.
- Seed named synthetic scenarios.
- Run a focused local V17 E2E suite without outbound network access.
- Launch a named desktop dev app profile against the local stack.
- Preserve the V17 proof boundary: local/emulator proof is not dev-cloud proof.

## Required local services

- Python backend.
- Rust desktop backend when a desktop scenario requires it.
- Firestore emulator or a strict fake that catches unsupported V17 query/index assumptions.
- Firebase Auth emulator or deterministic test-token shim.
- Redis/fakeredis or local Redis.
- Deterministic provider fakes for LLM, STT, embeddings, vector search, and external HTTP integrations.

## V17 scenario coverage

At minimum, local V17 scenarios must cover:

- default-off legacy-safe behavior;
- enabled happy path with synthetic Short-term, Long-term, and Archive data;
- Archive excluded from default reads;
- stale Short-term excluded from default reads;
- kill switch fail-closed after selection;
- malformed cursor fail-closed;
- cross-user isolation with at least two synthetic users;
- GET path performs no V17 writes in the harness.

## Non-goals

- No production data or production credentials.
- No claim that local proof satisfies V17 dev-cloud Gate 2.
- No broad refactor of V17 product semantics.
- No hidden dependency on a developer's ambient GCP project.

## Proof labels

Every generated report must state one of:

- `LOCAL_ONLY`
- `HERMETIC_E2E`
- `EMULATOR_E2E`
- `DEV_CLOUD_PROOF`

Only `DEV_CLOUD_PROOF` may be used for V17 Gate 2 evidence.
