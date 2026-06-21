# Oracle Review 2: Real-Default Manual-QA Local Emulator Harness

**Verdict:** CONDITIONAL GO / LIMITED GO
**Review scope:** compact second review after changing strategy to manual-QA/product-use harness with real providers default and offline hermetic-shared fallback.
**Model caveat:** Oracle reported `requested=Pro; resolved=(unavailable); verified=no`; use as advisory feedback, not authoritative proof.

## Summary

Oracle agreed with the updated framing:

- keep manual QA/product-use scope;
- keep hermetic E2E as deterministic regression authority;
- keep `demo-omi-local`, Firestore `(default)`, loopback binding, state sentinel, owned-process shutdown, and sanitized child environments;
- keep explicit `PROVIDER_MODE`; never infer mode from key presence;
- share fake-provider implementation between local offline mode and hermetic E2E.

Key conditional: **real providers can be the interactive default only if provider-safety P0s land with the implementation; otherwise temporarily default to offline.**

## Required amendments

1. **Narrow the local-state claim.**
   - Application-authoritative mutable state is local.
   - In `PROVIDER_MODE=real`, prompts/media/responses/request metadata may leave the machine, incur cost, and be retained by provider policy.
   - `dev-reset` does not delete provider-retained records.

2. **Manual QA is not a safety-testing exemption.**
   - Deterministic product tests remain hermetic.
   - Harness safety controls still need automated tests: credential isolation, offline no-egress, budget enforcement, project assertions, reset safety.

3. **Mode semantics must fail closed.**
   - `real` is default for interactive developer invocations that pass provider preflight.
   - CI/non-interactive automation must specify a mode explicitly and must not use real by default.
   - Missing/rejected real credentials are startup errors; never silently fall back to offline.
   - Offline mode removes provider credentials from child processes and enforces provider/network egress denial.

4. **Provider broker required.**
   - Every provider call routes through one broker/governor.
   - Desktop renderer, local API, seed scripts, workers, logs, crash reports, and session manifests never receive or print secrets.

5. **Cost/request governor required.**
   - Initial default: `$2/session`, `$10/day/developer`, concurrency 2, one retry only for idempotent calls, zero retries for non-idempotent calls.
   - Per-modality limits for tokens/upload bytes/audio duration.
   - Circuit breaker for repeated failures and queue storms.
   - No automatic replay of pending provider jobs after restart.

6. **Provider matrix required.**
   - provider/account/project, billing owner/quota, training/data-use setting, retention policy/region, allowed stateful resources/jobs.
   - Defaults: synthetic/local-QA data only, raw content logging off, metadata-only logging, trace capture local-only and short-lived.

7. **Offline sharing required.**
   - One transport-neutral provider contract and deterministic fake implementation shared by hermetic E2E and local offline mode.
   - Contract tests prove both entry points expose identical behavior.
   - Negative test proves offline mode cannot establish outbound provider connections.

## Recommended status/session summary fields

```text
environment=LOCAL_EMULATOR_DEV
activation_eligible=false
provider_mode=real
provider=<provider>
model=<resolved-model-id>
credential_fingerprint=<non-secret hash>
external_egress=provider-allowlist
data_policy=synthetic-or-local-qa-only
raw_trace=off
session_budget_usd=2
estimated_session_cost_usd=<value>
firebase_project=demo-omi-local
firestore_database=(default)
seed_version=v17
git_sha=<sha>
```

## Unsafe approaches

Do not use shared team keys, production provider projects, direct renderer-to-provider calls, ambient cloud credentials, raw-content logs by default, silent real/offline fallback, unbounded retries, provider-managed mutable prompts, automatic tunnels for webhooks, duplicated fake stacks, or real-provider runs as a release gate.

## Decisions / recommended defaults

| Decision | Recommended default |
|---|---|
| Realism vs safety | Real by default only for interactive invocations with provider preflight; offline/explicit mode for automation. |
| Provider retention | Cannot be made local; default synthetic/local-QA-only and stateless. |
| Production parity vs reproducibility | Pinned dev profile by default; explicit `PROVIDER_PROFILE=prod-parity`. |
| Stateful provider features | Disabled; require explicit override, namespace/manifest/TTL, and best-effort cleanup if ever needed. |
| No approved low-quota dev account | Real mode must not start. |
