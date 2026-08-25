# `omi-jit-qa` local-dev-gcp stack

`local-dev-gcp` is a safe hybrid QA target. The Python and desktop backends
run on fixed loopback ports, Firebase ID tokens are verified against the
configured Auth project, and a narrow loopback Vertex broker is the only
process that receives development ADC. The main and desktop backends use
private HOME/XDG roots, cannot discover host cloud credentials, and route
supported text inference through that broker. Firestore is always forced to
the stack-owned local emulator; Redis is always a stack-owned loopback process.
A hermetic PostHog-compatible decide service runs on loopback with a fixed demo
project key, so the production rollout provider can be exercised without a
real PostHog flag or cohort mutation. No flag enables a shared Firestore or
production API path.

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

# Start Firestore, Redis, the ADC-isolated Vertex broker, the hermetic PostHog
# control plane, and both backends.
desktop/macos/scripts/jit-qa-local-backend up

# Inspect owned PIDs and health without exposing environment values.
desktop/macos/scripts/jit-qa-local-backend status
desktop/macos/scripts/jit-qa-local-backend health

# Run the reserved bundle against that stack.
desktop/macos/scripts/omi-jit-qa local-dev-gcp --fast-only

# With the signed-in QA bundle running, exercise the integrated app/control
# path plus the complete emulator-backed JIT contract matrix.
FIRESTORE_EMULATOR_HOST=127.0.0.1:18082 \
GOOGLE_CLOUD_PROJECT=demo-omi-jit-qa \
backend/.venv/bin/python backend/scripts/jit_qa_orchestrated_dogfood.py \
  --control-plane-url http://127.0.0.1:18085 \
  --output .dev/jit-qa-local-dev-gcp/orchestrated-dogfood-evidence.json

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
The hermetic PostHog control plane uses `127.0.0.1:18085`; its control token
and mutable flag state are private stack files. It starts with rollout unknown
and the kill switch disabled, and the dogfood driver restores that initial
state after testing fail-closed, rollout-on, kill-switch, and roll-forward
decisions through the production provider.

If ADC, the selected Auth project, Java/Firebase tooling, or a required local
dependency cannot be proved, `check`/`up` fail closed. This is intentional:
use the existing `deployed-dev` target for a deliberate cloud-dev session,
not a local launcher override.

This hybrid target proves local Firestore/Redis state transitions, the real
PostHog SDK decision path, signed-in canonical memory create/list, and supported
text-only Vertex-backed Gemini paths without giving the backend broad ADC. The
dogfood report labels history/reopen, daily sweep, first-open, proactivity,
keyframe/request, and writer-transition groups as emulator-only; it does not
misrepresent them as app-driven flows. Because no Pinecone authority exists,
synthetic app-memory cleanup may fall back to deleting and re-scanning only
documents containing the fixed harness marker in the demo Firestore emulator.

Real PostHog cohorts, third-party model providers, full multimodal ambient
proactivity, and representative deployed-development metrics still require a
deliberate `deployed-dev` session. Do not weaken the local boundary to simulate
those external gates.
