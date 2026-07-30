# Omens / projections runtime contract

Omens turn a bounded window of an owner's recent context into one generated image and imperative.
The internal projection pipeline interprets recent context; it does not forecast what will happen.
This is an owner-authenticated surface, and neither the projection document nor its image is a
public sharing mechanism.

## Ambient lifecycle

The existing hourly `notifications-job` owns the schedule. At each invocation it considers only
the exact Firebase UIDs in `PROJECTION_ENABLED_USERS` and generates for a user when their stored
IANA timezone has reached 08:00 local time. Later invocations on the same local day retry
transient failures; the deterministic id and Firestore reservation make completed days no-ops.
An empty cohort disables the job.

Each scheduled document has a deterministic UUID derived from `(uid, local calendar date)`.
Firestore atomically reserves that id with a unique attempt token and bounded expiry before any
model or image work. Redis is only a best-effort optimization. Every attempt writes a distinct
object path, and finalization succeeds only while the same unexpired token still owns the
reservation. A missing or ungrounded evidence packet is a normal no-artifact outcome.

The macOS page fetches the latest artifact when opened and on app activation. Activation bursts
use the shared 60-second cooldown. The Generate button exercises the hidden
`/v1/users/projections/test` route only in explicit local development; hosted development and
production return 404. Manual generation runs subject selection, emotion rating, and image
generation in one request. The desktop gives that pipeline a 120-second request budget instead
of its shared 30-second API budget.

The image prompt keeps three visual responsibilities separate. The shared aesthetic owns the
rendering register; the selected stage owns the previously validated palette, tonal hierarchy,
symbol, and composition; and the measured emotional charge inflects intensity, edge energy, and
light direction and quality within those optical bounds. The person's selected situation and
recognisable setting remain the subject. Do not replace the stage palette/value contract with a
generic emotion-derived scheme: that removes the measured series safeguards and allows the image
model to collapse toward its default treatment.

The Resurrection stage intentionally uses violet as a principal colour inside its generated
artwork to represent the union of opposites. This art-direction exception does not add violet to
the app's UI chrome or design tokens.

## Image storage and delivery

Set `BUCKET_PROJECTION_IMAGES` to the same private GCS bucket on both the `backend` Cloud Run
service and `notifications-job`.

- `notifications-job` needs object create/write access.
- `backend` needs object read access.
- Keep uniform bucket-level access and public access prevention enabled. No object receives a
  public ACL.
- Scheduled objects use the attempt-specific owner path
  `{uid}/{projection_id}/{attempt_token}.png`; local manual artifacts retain
  `{uid}/{projection_id}.png`.
- The document exposes only `/v1/projection-images/{projection_id}.png`. That route requires a
  Firebase ID token, looks up the projection under the authenticated UID, validates the exact
  persisted path against that owner and projection, and returns `Cache-Control: private, no-store`.
- The macOS client never uses the persisted URL as an authorization destination. It validates
  the projection UUID and constructs the image route from that UUID plus its configured Python
  API base before attaching a Firebase token.
- Account deletion removes every object under the exact `{uid}/` prefix before the authoritative
  Firestore wipe. Local fallback deletion removes only that owner's hashed directory.

When `BUCKET_PROJECTION_IMAGES` is empty in a local process, images fall back to
`PROJECTION_LOCAL_IMAGE_DIR` (or the OS temporary directory) under a hashed-owner directory with
`0700` directories and `0600` files. Hosted runtimes refuse this fallback because separate job
and API instances cannot share local disk.

An attempt that writes an object and loses its Firestore reservation can leave unreferenced
bytes. Before enabling a cohort, define an operator-owned retention/lifecycle policy for the
private bucket that bounds those orphaned objects and matches the intended retention of
historical Omens. Bucket lifecycle and deployed IAM remain rollout gates rather than properties
verified by the repository test suite.

## Configuration

| Variable | Runtime | Purpose |
|---|---|---|
| `BUCKET_PROJECTION_IMAGES` | API and notifications job | Shared private image bucket |
| `PROJECTION_ENABLED_USERS` | notifications job | Exact comma-separated rollout cohort; empty is off |
| `BASE_API_URL` | local API generation and notifications job | Absolute API origin persisted in image links |
| `OMI_LLM_GATEWAY_URL` | notifications job | Production image-generation gateway |
| `OMI_LLM_GATEWAY_SERVICE_TOKEN` | notifications job secret | Authenticates gateway calls |
| `REDIS_DB_HOST`, `REDIS_DB_PASSWORD` | notifications job | Best-effort generation lease |
| `PROJECTION_LOCAL_IMAGE_DIR` | local only | Optional private local fallback root |

The checked-in deployment source accepts the bucket and cohort as GitHub environment variables.
The bucket variable is explicitly optional while the cohort is empty so a disabled rollout does
not block unrelated backend or notifications deployments. This does not enable hosted local-disk
fallback: a hosted scheduler with a non-empty cohort refuses to run without the bucket. Before
activating a cohort, provision the bucket and lifecycle policy, grant the two service identities
only their required roles, set the bucket variable, set the exact `PROJECTION_ENABLED_USERS`, and
deploy the API and notifications job from the same revision. The gateway-token binding is emitted
only for a non-empty cohort, and the Redis-password binding is emitted only when `REDIS_DB_HOST`
enables that optimization, so an off rollout does not add secret-access requirements to the
existing notifications job.

The notifications job does not enable global feature-mode gateway routing: subject selection and
emotion rating follow the existing `get_llm` provider configuration, while projection image
generation always uses the gateway. Its `OMI_LLM_GATEWAY_URL` comes from the checked-in repository
variable; validate that value before enabling a cohort because a stale URL fails only after the
selector and emotion calls have completed.

## Verification

Focused checks:

```bash
backend/.venv/bin/pytest -q \
  backend/tests/unit/test_projection_reservations.py \
  backend/tests/unit/test_projection_image_authorization.py \
  backend/tests/unit/test_projection_scheduler.py \
  backend/tests/unit/test_projection_feedback.py \
  backend/tests/unit/test_projection_runtime_contract.py
npm run test:projection-reservation:emulator

cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py \
  --manifest route_policy_manifest.yaml --enforce-missing-baseline
scripts/openapi_runner.sh scripts/export_openapi.py \
  --surface app-client --check ../docs/api-reference/app-client-openapi.json
```

For a local end-to-end run, leave the bucket empty, set `OMI_ENV_STAGE=local` and
`PROJECTION_LOCAL_IMAGE_DIR` to a private temporary directory, authenticate as one test owner,
generate through the local route, then verify
that unauthenticated and different-owner image reads return 401/404 while the owner receives the
image with private no-store headers.

The deterministic desktop presentation proof uses the typed `projections.yaml` flow. Launch the
isolated `omi-omens` named bundle, note its automation port, then run:

```bash
cd desktop/macos
../../backend/.venv/bin/python scripts/omi-harness run e2e/flows/projections.yaml \
  --lane visual --port <automation-port> \
  --bundle-id com.omi.omi-omens
```

Its bridge actions change only local UI state on non-production bundles. Backend API transport,
owner authorization, and generation are verified separately by the focused checks above.
