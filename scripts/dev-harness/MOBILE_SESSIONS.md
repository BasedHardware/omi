# Mobile sessions — isolated local app sessions for agents and contributors

One command owns a uniquely-leased local mobile session end to end:

```bash
make mobile-session ARGS="doctor --platform android --platform ios"
make mobile-session ARGS="acquire --name mytask"        # session lease first (id: oms-mytask)
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

## Synthetic auth (reuse of open PR #11784 — not merged or closed)

Seeding and the app's `signInWithLocalDevToken` reuse the local-development
sign-in contract from [PR #11784](https://github.com/BasedHardware/omi/pull/11784)
(`feat/app+backend local-development sign-in without OAuth`, head
`9ae7d36e172c9123d4ac6d19815d9b07f5f8dfc4` — still OPEN and conflicting with
`main`). That PR is **not** merged or closed by this program. Its reviewed
backend router, route-policy row, and client path are copied onto this
integration branch against current `main`:

- the session backend exposes `POST /v1/auth/local-dev/custom-token`,
  structurally gated by `FIREBASE_AUTH_EMULATOR_HOST` (the endpoint 404s
  without the emulator — nothing to probe in production);
- `seed` posts the fixture uid/email to that endpoint and records a receipt
  (`seed.json`) that **never contains the minted token**.

A loopback HTTP stub is not auth acceptance. Unit tests pin the request/receipt
shape and the 404-not-403 gate; live `seed` against a session-owned Auth
emulator is the remaining acceptance for this seam.

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
(never "latest"); the backend venv must be Python 3.11 **and** able to import
`yaml` and `dotenv` (a `.venv` directory is not enough); JDK ≥ 21 for the
Firebase emulators. `app/.dev.env` with a non-loopback `API_BASE_URL`, or
`OMI_APP_PROFILE`/`OMI_APP_FLAVOR` other than `local_dev`/`dev`, is
`operator-action-needed` — the doctor will not rewrite the file. Capacity:
emulator lanes require ≥ 12GiB free on the
shared Data/scratch container — below that the check is an operator gate and
contract/unit work continues without it. Android image inventory is three-way:
the emulator binary missing is `emulator engine missing`; a successful
`sdkmanager --list_installed` (semicolon or slash paths) or on-disk
`system-images/android-36/google_apis/arm64-v8a` with no image is `no
system-images package installed`; a missing sdkmanager or a nonzero inventory
with no parseable listing and no on-disk tree is `cannot determine` — not a
finding that the engine or image is absent. cmdline-tools 23 deprecation
warnings on stderr are not a failed inventory (this host exits 0).

Fresh linked worktree: `make lane-bootstrap` (see `LANE_BOOTSTRAP.md`).

## Evidence

Every session can emit a `session-evidence-v1` receipt
(`contracts/session/session-evidence-v1.schema.json`, validated by
`dev_harness.session_evidence`). v1 is frozen by Spine A/V8; see `contracts/session/README.md` for its
immutable validation rules and optional live-operation fields. The receipt binds source SHA + dirty digest,
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

## Live session contract

[LIVE_SESSIONS.md](LIVE_SESSIONS.md) defines V1; explicit `live` commands are
currently an exit-2 skeleton. [PENDING_CONTRACTS.md](PENDING_CONTRACTS.md) explains
the strict pending acceptance tests. Ordinary commands retain their behavior.
