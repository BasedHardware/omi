# Canonical integration recipe (not yet executed with native)

The standalone Firestore18085/HTTP8600 integration run is finished and both
processes have stopped. Its HTTP receipt used synthetic fixture Bearer auth and
must not be cited as real OAuth/native proof. Do not start that stack again.

Use the native owner's existing `sim` or `sim.2` canonical MUX slot and backend
lifecycle. The native owner runs normal `mux_preflight` and acquires the lane;
this helper additionally checks the actual lease. No private lane/emulators.

From this worktree, after exporting the **existing** lane and owner:

```bash
source ~/mobile-ux-agent/pipeline/env.sh
source ~/mobile-ux-agent/pipeline/lib/guard.sh
mux_preflight
# Owner must already hold MUX_LANE. Do not acquire another lane.
# Stop the existing canonical backend via its normal owner lifecycle first.
OMI_LOCAL_INSTANCE="$MUX_HARNESS_INSTANCE" OMI_HARNESS_PORT_OFFSET="$MUX_PORT_OFFSET" \
PROVIDER_MODE=offline MUX_STRIPE_PORT="$MUX_STRIPE_PORT" MUX_STRIPE_PRICES="$MUX_STRIPE_PRICES" \
PYTHONPATH="$PWD/scripts/dev-harness" backend/.venv/bin/python \
  backend/testing/referral_campaign/mux.py up
```

`mux.py` calls the existing `pipeline/lib/harness_up.py` and changes only the
backend import target to the test-only factory. It keeps the canonical process
supervisor, project, ports, Firestore/Auth emulators, Stripe stub, and other
services. The factory imports actual `main:app`, preserves production auth
verification with the actual Firebase Auth emulator JWT, and injects only the
local checkout adapter/policy. It does not add product debug routes or synthetic
auth overrides. Normal main.py auth ownership code remains unchanged.

Use the normal owner `backend.sh down` lifecycle for teardown (same harness
instance). Do not run `backend.sh up` while this modified canonical up is running;
it would start the ordinary backend instead of the injected commerce fixture.
The native harness owns any backend.json bookkeeping and slot release.

Seed/advance in a separate terminal while the canonical emulator is running:

```bash
export OMI_ENV_STAGE=local
export FIRESTORE_EMULATOR_HOST="127.0.0.1:$MUX_FIRESTORE_PORT"
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:$MUX_AUTH_PORT"
export FIREBASE_PROJECT_ID=demo-omi-local
PYTHONPATH=backend backend/.venv/bin/python backend/testing/referral_campaign/control.py seed
PYTHONPATH=backend backend/.venv/bin/python backend/testing/referral_campaign/control.py purchase --buyer buyer-1
PYTHONPATH=backend backend/.venv/bin/python backend/testing/referral_campaign/control.py purchase --buyer buyer-2
```

Seed/create the Firebase emulator account with UID `owner` using the canonical
native harness auth fixture. The app sends its actual SDK `getIdToken()` JWT.
The backend resolves UID from that token; body UID is never used. For another
canonical account UID, update the test-only fixture owner parameter before
claiming evidence; do not weaken production auth or pass a client user ID.

Native sequence: status0; pay two signed local order fixtures; status2/claim2;
claim three times/reenter; pay buyer3/4/5; status5/claim3; repeat/reenter; compare
stored award+grant+commercial subscription. `control.py refund --buyer buyer-N`
uses a signed refund payload through production HMAC and ledger functions.
`paid-owner`/`free-owner` manipulate only emulator fixture subscription state to
exercise deferred claim, never a production account. No control action sets a
progress counter directly. The emulator project must start `demo-` and hosts
must be loopback. All seeding remains test-only; no fixture mutation endpoint.

Disabled/error scenarios require stopping/restarting the factory without fixture
enablement or using focused route tests; the campaign has no debug flag endpoint.
Full native+canonical path remains **UNVERIFIED** until the native owner runs it.
