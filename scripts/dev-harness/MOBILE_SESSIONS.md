# Mobile sessions — isolated local app sessions for agents and contributors

One command owns a uniquely-leased local mobile session end to end:

```bash
make mobile-session ARGS="doctor --platform android --platform ios"
make mobile-session ARGS="start oms-mytask"          # services (+ device when the lane is ready)
make mobile-session ARGS="seed oms-mytask"           # synthetic Auth-emulator user, fixture v1
make mobile-session ARGS="evidence oms-mytask --artifact app/build/app/outputs/flutter-apk/app-dev-debug.apk"
make mobile-session ARGS="reset oms-mytask"          # only this session's state; idempotent
make mobile-session ARGS="stop oms-mytask"           # idempotent
make mobile-session ARGS="recover oms-mytask"        # take over a lease whose owner died on this host
make mobile-session ARGS="release oms-mytask"        # stop + free ports + remove state; idempotent
```

Direct form: `scripts/dev-harness/mobile-session.sh <op> …` (add `--json` to any
op for machine-readable output). Exit codes: 0 ok, 1 doctor-degraded
(agent-remediable), 2 refusal/blocked (fail closed).

## What a session is

A session = one harness instance + port offset + device lease + seed receipt +
evidence receipt. Nothing is shared between concurrent sessions:

| Resource | Isolation |
| --- | --- |
| Ports | unique offset claimed in `<state>/mobile-sessions/ports/<offset>.json` (atomic `O_EXCL`); base ports belong to the default desktop harness |
| Backend/Auth/Firestore/Redis/Typesense | separate harness instance state root per session (`OMI_LOCAL_INSTANCE`, existing harness semantics) |
| Storage/logs/receipts | `<state>/mobile-sessions/<session-id>/` |
| Device | Android: session-owned AVD lease; iOS: `simctl create/boot` of `omi-session-<id>`, deleted on stop |
| Evidence | `evidence.json` (session-evidence-v1, see `contracts/session/`) |

Ownership is fail-closed: leases record owner host/user/pid; a **live foreign
owner is never reclaimed**; a **foreign process occupying a port is refused,
not killed**; `recover` only takes over a same-host lease whose owner pid is
provably dead, bumping the lease generation; stop/reset/release only touch
processes and paths recorded in the session's own manifests (harness ownership
guards apply underneath).

## Synthetic auth (integration with open PR #11784)

Seeding reuses the local-development sign-in contract from
[PR #11784](https://github.com/BasedHardware/omi/pull/11784)
(`feat/app+backend local-development sign-in without OAuth`, head
`9ae7d36e172c9123d4ac6d19815d9b07f5f8dfc4` at the time of writing — still OPEN
and conflicting with `main`):

- the session backend exposes `POST /v1/auth/local-dev/custom-token`,
  structurally gated by `FIREBASE_AUTH_EMULATOR_HOST` (the endpoint 404s
  without the emulator — nothing to probe in production);
- `seed` posts the fixture uid/email to that endpoint and records a receipt
  (`seed.json`) that **never contains the minted token**.

**Integration plan (coordinator action):** this lane consumes the PR's backend
router + app `signInWithLocalDevToken` path; do not open a competing endpoint.
Once the PR's commits are integrated into the canonical
`codex/sca-486-mobile-foundation` branch (or merged upstream), the live
`seed`/sign-in path is exercised end to end; until then `seed` fails closed
with a precise reason (backend unreachable / endpoint 404). The contract tests
in `tests/test_mobile_fixtures.py` pin the request/receipt shape so the
integration cannot silently drift.

## Fixtures

`fixtures/mobile/v1.json` — deterministic synthetic identity: one Auth-emulator
user (`omi-fixture-v1-user-1@local.test`, RFC-reserved domain so it can never
collide with a real account). The fixture version is pinned in the lease and in
every evidence receipt. No real Google/Apple user, provider key, or copied
token is involved at any point.

## Doctor

`doctor` classifies every prerequisite exactly one of `ready`,
`agent-remediable` (remedy command included), or `operator-action-needed`
(privileged install/license/host capacity), per lane (`backend`, `android`,
`ios`). Pins: Flutter version comes from `.github/workflows/mobile-app-checks.yml`
(never "latest"); the backend venv must be Python 3.11; JDK ≥ 21 for the
Firebase emulators. Capacity: emulator lanes require ≥ 12GiB free on the
shared Data/scratch container — below that the check is an operator gate and
contract/unit work continues without it.

## Evidence

Every session can emit a `session-evidence-v1` receipt
(`contracts/session/session-evidence-v1.schema.json`, validated by
`dev_harness.session_evidence`). The receipt binds source SHA + dirty digest,
the built artifact hash (required for `ready`/`running` — a stale build cannot
be reported ready), loopback-only endpoints, fixture version, runner versions,
real timestamps, status/blocked reason and execution counts. Credential-shaped
keys are rejected anywhere in the document.

## Status of emulator/device-dependent acceptance

On the m1-mac-studio host at freeze time, Android emulator images/cmdline-tools
were not installed and shared capacity was ~15GiB — device-attach paths are
implemented and unit-tested with injected runners, and the live Android lane
fails closed through `doctor`/`start` with the exact remedy. iOS simulator
attach is implemented (`simctl create/boot/shutdown/delete` of a session-owned
device); live boots were deferred by the same capacity gate. Concurrency
(two live sessions), physical-device and untethered-signing acceptance remain
open and are tracked in SCA-487/SCA-491.
