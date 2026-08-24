# `omi-jit-qa` local-dev-gcp stack

`local-dev-gcp` is a safe hybrid QA target. The Python and desktop backends
run on fixed loopback ports, Firebase ID tokens are verified against the
development Auth project, and Vertex requests use development ADC when the
credentials are available. Firestore is always forced to the stack-owned local
emulator; Redis is always a stack-owned loopback process. No flag enables a
shared Firestore or production API path.

The launcher owns its PIDs, logs, generated Firebase config, local Redis data,
and private local secrets below `.dev/jit-qa-local-dev-gcp/`.

## Prerequisites

Run the repository setup first so the backend virtual environment and pinned
dependencies exist:

```bash
make setup
```

The host also needs Node/npm (or Firebase CLI), Java, and `redis-server`.
Before starting, authenticate ADC for the development GCP project. The check
refreshes a token but never prints it:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project based-hardware-dev
export GOOGLE_CLOUD_PROJECT=based-hardware-dev
```

The default Firebase Auth project is `based-hardware`. To use the explicitly
supported dev Auth project instead, set:

```bash
export JIT_QA_FIREBASE_AUTH_PROJECT_ID=based-hardware-dev
```

Any explicit credential file must be owner-readable only (`0600` or stricter).
The launcher validates the ADC project and Auth project before it creates a
process or writes stack state.

## Commands

From the repository root:

```bash
# Validate tools, ADC, project identity, endpoints, and emulator-only data mode.
desktop/macos/scripts/jit-qa-local-backend check

# Start Firestore emulator, Redis, Python backend, and desktop backend.
desktop/macos/scripts/jit-qa-local-backend up

# Inspect owned PIDs and health without exposing environment values.
desktop/macos/scripts/jit-qa-local-backend status
desktop/macos/scripts/jit-qa-local-backend health

# Run the reserved bundle against that stack.
desktop/macos/scripts/omi-jit-qa local-dev-gcp --fast-only

# Stop only processes recorded as owned by this stack.
desktop/macos/scripts/jit-qa-local-backend down
```

The main API is `http://127.0.0.1:18080`; its liveness probe is
`/v1/health`. The desktop backend is `http://127.0.0.1:18081`; its liveness
probe is `/health` and its Redis-backed readiness probe is `/ready`. Firestore
uses `127.0.0.1:18082`; Redis uses `127.0.0.1:18083`.

If ADC, the selected Auth project, Java/Firebase tooling, or a required local
dependency cannot be proved, `check`/`up` fail closed. This is intentional:
use the existing `deployed-dev` target for a deliberate cloud-dev session,
not a local launcher override.
