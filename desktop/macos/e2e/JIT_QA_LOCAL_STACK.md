# `omi-jit-qa` local-dev-gcp stack

`local-dev-gcp` is a safe hybrid QA target. The Python and desktop backends
run on fixed loopback ports, Firebase ID tokens are verified against the
configured Auth project, and a narrow loopback Vertex broker is the only
process that receives development ADC. The main and desktop backends use
private HOME/XDG roots, cannot discover host cloud credentials, and route
supported text inference through that broker. Firestore is always forced to
the stack-owned local emulator; Redis is always a stack-owned loopback process.
No flag enables a shared Firestore or production API path.

The launcher owns its process groups, per-run ownership nonces, logs, generated
Firebase config, local Redis data, and private local secrets below
`.dev/jit-qa-local-dev-gcp/`.

## Prerequisites

Run the repository setup first so the backend virtual environment and pinned
dependencies exist:

```bash
make setup
```

The host also needs Java and `redis-server`. Run `npm ci` at the repository
root; the launcher requires the exact `firebase-tools` version pinned in the
root lockfile and never downloads an unpinned CLI at launch time.
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

Explicit service-account files and JSON are rejected. The launcher validates
the ADC project and Auth project before it creates a process or writes stack
state.

Firebase Admin is mechanically verification-only in this target: the app can
verify a real Firebase ID token, but every Auth mutation (including account
deletion, custom tokens, claims, and user updates) is denied before a network
request. The named QA bundle also starts with an empty Rewind profile; it never
copies production screenshots, videos, or history into a dev-routed app.

## Commands

From the repository root:

```bash
# Validate tools, ADC, project identity, endpoints, and emulator-only data mode.
desktop/macos/scripts/jit-qa-local-backend check

# Start Firestore, Redis, the ADC-isolated Vertex broker, and both backends.
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
The Vertex broker uses `127.0.0.1:18084`; its local bearer token is private
stack state and its only cloud-capable provider is Gemini on Vertex in
`based-hardware-dev`.

If ADC, the selected Auth project, Java/Firebase tooling, or a required local
dependency cannot be proved, `check`/`up` fail closed. This is intentional:
use the existing `deployed-dev` target for a deliberate cloud-dev session,
not a local launcher override.

This hybrid target proves local Firestore/Redis state transitions, history,
and supported text-only Vertex-backed Gemini paths without giving the backend
broad ADC. It intentionally omits PostHog and third-party model credentials.
Tool-calling, multimodal ambient-proactivity, exact production provider routing,
and server-authoritative cohort-on behavior require deployed development;
exercise those slices with `deployed-dev`, not by weakening this local boundary.
