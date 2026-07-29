# Projections runtime contract

Projections turn a bounded window of an owner's recent context into one generated image and
imperative. They are a first-party, owner-authenticated surface; neither the projection document
nor its image is a public sharing mechanism.

## Ambient lifecycle

The existing hourly `notifications-job` owns the schedule. At each invocation it considers only
the exact Firebase UIDs in `PROJECTION_ENABLED_USERS` and generates for a user when their stored
IANA timezone is at 08:xx local time. An empty cohort disables the job.

Each scheduled document has a deterministic UUID derived from `(uid, local calendar date)`.
Redis holds a two-hour best-effort lease to avoid duplicate model and image work, while the
deterministic Firestore ID is the durable duplicate authority if Redis is unavailable. A missing
or ungrounded evidence packet is a normal no-artifact outcome.

The macOS page fetches the latest artifact when opened and on app activation. Activation bursts
use the shared 60-second cooldown. The Generate button and `/v1/users/projections/test` route are
non-production demo seams; hosted development also requires shared bucket storage. Manual
generation runs subject selection, emotion rating, and image generation in one request. The
desktop gives that pipeline a 120-second request budget instead of its shared 30-second API
budget, so a valid long image call does not surface a false timeout while the backend finishes
and persists it.

The image prompt keeps three visual responsibilities separate. The shared aesthetic owns the
rendering register; the selected stage owns the previously validated palette, tonal hierarchy,
symbol, and composition; and the measured emotional charge inflects intensity, edge energy, and
light direction and quality within those optical bounds. The person's selected situation and
recognisable setting remain the subject. Do not replace the stage palette/value contract with a
generic emotion-derived scheme: that removes the measured series safeguards and allows the image
model to collapse toward its default treatment.

## Image storage and delivery

Set `BUCKET_PROJECTION_IMAGES` to the same private GCS bucket on both the `backend` Cloud Run
service and `notifications-job`.

- `notifications-job` needs object create/write access.
- `backend` needs object read access.
- Keep uniform bucket-level access and public access prevention enabled. No object receives a
  public ACL.
- Objects use the owner-scoped name `{uid}/{projection_id}.png`.
- The document exposes only `/v1/projection-images/{projection_id}.png`. That route requires a
  Firebase ID token, looks up the projection under the authenticated UID, and returns
  `Cache-Control: private, no-store`.
- The macOS client never uses the persisted URL as an authorization destination. It validates
  the projection UUID and constructs the image route from that UUID plus its configured Python
  API base before attaching a Firebase token.

When `BUCKET_PROJECTION_IMAGES` is empty in a local process, images fall back to
`PROJECTION_LOCAL_IMAGE_DIR` (or the OS temporary directory) under a hashed-owner directory with
`0700` directories and `0600` files. Hosted runtimes refuse this fallback because separate job
and API instances cannot share local disk.

## Configuration

| Variable | Runtime | Purpose |
|---|---|---|
| `BUCKET_PROJECTION_IMAGES` | API and notifications job | Shared private image bucket |
| `PROJECTION_ENABLED_USERS` | notifications job | Exact comma-separated rollout cohort; empty is off |
| `BASE_API_URL` | API and notifications job | Absolute API origin persisted in image links |
| `OMI_LLM_GATEWAY_URL` | notifications job | Production image-generation gateway |
| `OMI_LLM_GATEWAY_SERVICE_TOKEN` | notifications job secret | Authenticates gateway calls |
| `REDIS_DB_HOST`, `REDIS_DB_PASSWORD` | notifications job | Best-effort generation lease |
| `PROJECTION_LOCAL_IMAGE_DIR` | local only | Optional private local fallback root |

The checked-in deployment source accepts the bucket and cohort as GitHub environment variables.
`BUCKET_PROJECTION_IMAGES` is required by the deployment renderer even while the cohort is empty;
this prevents a hosted API or job revision from silently falling back to instance-local disk.
Before activating a cohort, provision the bucket, grant the two service identities only their
required roles, set the bucket variable, set the exact `PROJECTION_ENABLED_USERS`, and deploy the
API and notifications job from the same revision.

## Verification

Focused checks:

```bash
backend/.venv/bin/pytest -q \
  backend/tests/unit/test_projection_image_authorization.py \
  backend/tests/unit/test_projection_scheduler.py \
  backend/tests/unit/test_projection_feedback.py \
  backend/tests/unit/test_projection_runtime_contract.py

cd backend
scripts/openapi_runner.sh scripts/route_policy_inventory.py \
  --manifest route_policy_manifest.yaml --enforce-missing-baseline
scripts/openapi_runner.sh scripts/export_openapi.py \
  --surface app-client --check ../docs/api-reference/app-client-openapi.json
```

For a local end-to-end run, leave the bucket empty, set `PROJECTION_LOCAL_IMAGE_DIR` to a private
temporary directory, authenticate as one test owner, generate through the demo route, then verify
that unauthenticated and different-owner image reads return 401/404 while the owner receives the
image with private no-store headers.

The deterministic desktop presentation proof uses the typed `projections.yaml` flow. Launch the
isolated `omi-track3-projection-mvp` named bundle, note its automation port, then run:

```bash
cd desktop/macos
../../backend/.venv/bin/python scripts/omi-harness run e2e/flows/projections.yaml \
  --lane visual --port <automation-port> \
  --bundle-id com.omi.omi-track3-projection-mvp
```

Its bridge actions change only local UI state on non-production bundles. Backend API transport,
owner authorization, and generation are verified separately by the focused checks above.
