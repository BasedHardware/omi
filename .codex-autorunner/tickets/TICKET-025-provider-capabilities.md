---
ticket_id: "tkt_provider_capabilities"
agent: "codex"
done: false
title: "Define real-default providers and offline provider fallback"
goal: "Manual QA uses real dev-keyed providers by default, while an easy offline mode reuses hermetic fake providers and no external provider holds harness state."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 22000
  - path: "docs/epics/local_first_full_stack_dev_harness_epic.md"
    required: true
    max_bytes: 26000
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 18000
---

## Tasks

- Define provider modes such as `PROVIDER_MODE=real|offline`, with `real` as the default for local manual QA/product use.
- Make `offline` reuse the same fake/offline provider implementation used by the hermetic test environment wherever possible.
- Ensure `PROVIDER_MODE=offline make dev-up` starts the same local stack without external provider credentials.
- Add a credential checker for real-provider mode that prints every missing required dev key and where to configure it.
- Add allowlists for external provider endpoints and capabilities.
- Require synthetic or developer-created local QA inputs, timeouts, request-count limits, and cost bounds for real provider calls.
- Explicitly prohibit callbacks, webhooks, queues, vector/index writes, or any durable external side effect.
- Ensure hosted vector databases and other external indexes are classified as stateful and disallowed for local-harness state.
- Ensure provider keys remain backend-side and are never copied into desktop app bundles or local session summaries.
- Ensure local session summaries and `make dev-status` prominently show provider mode and enabled external providers.

## Acceptance criteria

- `make dev-up` defaults to real-provider mode and fails fast with a clear missing-dev-credential checklist when required keys are absent.
- `PROVIDER_MODE=offline make dev-up` starts without external-provider credentials.
- Offline providers are shared with, or thin wrappers around, the hermetic fake-provider implementation rather than a second fake stack.
- Real-provider calls are bounded and use only synthetic or developer-created local QA data.
- No external provider can hold harness-authoritative mutable state.

## Tests

- Credential checker tests for real and offline modes.
- Endpoint/capability allowlist tests.
- Failure test for hosted vector/index write attempts.
- Secret-scan test proving provider keys are not emitted in desktop bundle config or session summaries.
- Offline mode smoke using hermetic-shared fake providers.
- `git diff --check`
