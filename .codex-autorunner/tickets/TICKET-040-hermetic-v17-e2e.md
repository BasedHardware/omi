---
ticket_id: "tkt_hermetic_v17_e2e"
agent: "codex"
done: false
title: "Extend hermetic E2E with V17 memory scenarios"
goal: "The backend hermetic E2E suite covers core V17 route-selection and fail-closed behavior without network access."
context:
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 18000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 12000
---

## Tasks

- Add V17 scenario tests to `backend/testing/e2e/`.
- Reuse the existing socket guard so accidental external network calls fail.
- Cover default-off, enabled happy path, Archive default exclusion, stale Short-term exclusion, kill-switch fail-closed, malformed cursor, and cross-user isolation.
- Emit a local proof report labelled `HERMETIC_E2E` or `LOCAL_ONLY`.

## Acceptance criteria

- Focused V17 hermetic E2E can run independently.
- The suite proves no V17 writes are attempted on tested GET paths inside the harness.
- The report cannot be confused with dev-cloud Gate 2 evidence.

## Tests

- `bash backend/testing/e2e/run.sh -k "v17"`
- Full hermetic E2E if runtime is reasonable.
