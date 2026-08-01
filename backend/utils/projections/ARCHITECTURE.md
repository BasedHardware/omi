# Projection utilities

This package owns the evidence-to-image pipeline for one owner-scoped projection: the internal
model behind a grounded Omen. HTTP authentication and response shaping live in
`backend/routers/projections.py`; Firestore persistence lives in
`backend/database/projections.py`.

## Generation path

```text
generation.py:generate_projection
  sources.py                         read bounded owner evidence and recent projections
  evidence.py                        type, cap, and tier the evidence packet
  selector.py                        rank subjects and deterministically validate citations
    register.py                      product-authored verbal examples
    stages.py                        approved projection-stage vocabulary
  emotions.py                        rate the packet's emotional dimensions
  image_prompt.py                    assemble the typed prompt graph
    archetypes.py                    stage-owned form
    aesthetic.py                     fixed rendering style
  generation.py                      call the image gateway and build the document
  storage.py                         write an owner-scoped private GCS object or local fallback
```

`selector.py` is the grounding authority. A model-reported `grounded` value is never sufficient:
every cited reference must exist in the exact `EvidencePacket`, and at least one citation must
refer to conversation or action-item material. `NoProjectionSubject` from `errors.py` is a normal
no-artifact outcome when the packet is empty or no candidate passes that gate.

`image_prompt.py` preserves one owner per prompt slot. Subject and action come from the selected
projection, environment from its setting, lighting from the rated emotional signal, form from
the approved stage archetype, and style from `aesthetic.py`. Do not let a new module write a
second value into one of those slots or casually rewrite the product-authored register.

## Ambient path

`backend/utils/other/jobs.py` invokes `scheduler.py` from the existing hourly notifications job.
The scheduler evaluates only the explicit `PROJECTION_ENABLED_USERS` cohort after 08:00 in each
owner's stored IANA timezone. Later hourly invocations retry transient failures for the same
local day. A UUID derived from owner and local date is reserved atomically in Firestore with an
expiring attempt token. Redis only avoids unnecessary contention. Each attempt owns a distinct
image path, and only the current reservation owner may finalize the document. Projection
exceptions are isolated at the shared-job boundary so unrelated hourly integrations still run;
non-`Exception` process-control signals continue to propagate.

The manual route composes the same `generate_projection` function but exists only in explicit
local development. Hosted development and production return 404; hosted scheduled generation
requires shared GCS storage so the job and API never pretend instance-local disk is a delivery
path.

## Privacy and delivery boundary

`storage.py` accepts the owner, projection id, and optional attempt token. Scheduled objects use
`{uid}/{projection_id}/{attempt_token}.png`; GCS objects remain private. Local fallback hashes
the owner into a private directory and uses private file modes.

Stored documents expose an authenticated API URL, not a public object URL. The router first
loads the projection under the Firebase-authenticated UID, validates its persisted image path
against that UID and projection id, then downloads exactly that path. Raw evidence prose and
generation prompts remain internal; only the compact validated receipt assembled by
`generation.py` is served as `why_this`. The macOS API client independently pins authenticated image downloads to
its configured Python API origin by constructing the projection-image route from the validated
projection UUID, so a malformed stored URL can never receive a Firebase bearer token.
Account deletion purges the owner's exact GCS prefix or hashed local directory before Firestore
removes the user record.

## Change rules

- Keep datastore reads in `sources.py`, selection policy in `selector.py`, prompt composition in
  `image_prompt.py`, and transport/storage in `generation.py` plus `storage.py`.
- Add new model-backed steps to the shared model-feature registry and route provider traffic
  through the gateway.
- Preserve the empty/thin/rich evidence ladder and the normal no-artifact outcome.
- Pair changes with hermetic unit coverage under `backend/tests/unit/test_projection_*.py`.
- Run `npm run test:projection-reservation:emulator` when changing reservation or
  finalization semantics.
- Treat `register.py`, `aesthetic.py`, and the approved archetypes as product-owned visual
  register; do not expand or rewrite them as infrastructure cleanup.
