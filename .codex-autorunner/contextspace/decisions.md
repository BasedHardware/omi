# Local Emulator Harness Decisions

- This is a general infra epic, not V18 and not an extension of V17 product semantics.
- V17 is the first customer and provides the initial scenario set because it needs high-confidence full-stack local development before cloud promotion.
- The repo already has a fully fake hermetic E2E harness. This epic should focus on the next layer up: local emulator full-stack development.
- Dev-cloud proof remains mandatory for V17 activation. Local emulator evidence can supplement confidence but never replace it.
- Evidence from this harness should be labelled `LOCAL_EMULATOR_DEV`, not `DEV_CLOUD_PROOF`.
- Top-level `make` commands are the stable developer interface; heavy implementation should live under `scripts/`.
- Scenario fixtures should be Python-authored for type checking, easy authoring, and reuse in seed/test tooling.
- Desktop macOS is the first surface target. Mobile, web, and hardware can be added later.
- Local auth should use Firebase Auth emulator, with a pre-populated default local test user and easy multi-user test profiles.
- Real dev providers are enabled by default for interactive manual QA and product use after provider preflight. `PROVIDER_MODE=offline` provides an easy switch to hermetic-shared offline providers for missing keys, outages, demos, and provider-independent debugging.
- Provider modes fail closed: never infer mode from key presence, never silently fall back between modes, and require automation/non-interactive invocations to specify a provider mode explicitly.
- Real-provider mode requires a local provider broker/governor, approved dev account fingerprints, cost/request/time bounds, metadata-only default logging, and no shared team keys or production provider projects.
- All harness-owned mutable state must live locally. External dependencies must not hold harness-authoritative state; hosted vector/index services are disallowed as local-harness state dependencies.
- The v1 local Firebase boundary is fixed to project ID `demo-omi-local` and Firestore database `(default)`, with loopback emulator endpoints and sanitized child-process environments.
- This harness is for manual QA and using the product locally, not deterministic pass/fail product testing; hermetic E2E remains the deterministic test layer.
- Desktop testing should use a named local profile such as `Omi Dev Local` so it does not collide with production, beta, or existing dev installs.
