# Future-clock recovery: token-required batch subset

V2 may recover timestamps strictly more than 24 hours ahead of server receipt.
The existing 600-second skew tolerance is unchanged; the interval between that
skew and 24 hours still gets HTTP 400 `invalid_capture_time`. V1 is unchanged.
`SYNC_FUTURE_CAPTURE_CLAMP_ENABLED` defaults on in code, but all ten dev/prod
admission overlay values and both listener chart values are explicitly false.

## Narrow admission contract

Recovery requires a stable client device identity and an explicit `_clke<run>_`
filename token on **every** file in a wholly future-dated upload. Unmarked or
mixed-clock bundles retain the typed 400. A conversation-targeted upload or an
upload declined by existing batch cohort/language/capacity policy also stays
refused: this extension cannot enter the legacy pipeline. Missing device
identity gives a retryable 503. No timestamp, original file, existing collision
normalizer or content identity is rewritten by this policy.

Do not infer a run from out-of-order arrival. An unmarked backward reset is
indistinguishable from an older backlog slice. Current LittleFS code supplies
no run for positive device timestamps; this subset therefore does not promise
recovery of existing unmarked 2038 files. Existing recorded files stay on the
phone. No app-version attribution or retroactive run assignment is assumed.

The future decoder reuses main's strict frame and canonical PCM helpers and
same-source frame coverage. It freezes one owner/device/run offset using the
first decoded original end minus receipt. Later files use that same offset,
preserving device-clock differences and gaps across requests. Each source
file yields separate bounded units, avoiding invented silence or cross-run
packing. Trims inherit the full source's offset and source-frame proof.

The trusted lower bound is Firebase Auth account creation metadata. A span
mapping before that bound is refused before a new anchor or any unit is
staged. An existing anchor never moves. A mapped end ahead of trusted server
processing time waits with 503; a jump more than a day ahead requires a new run
and gets the typed refusal. The client must assign a new token at a reset.
A reused explicit token cannot prove a hidden backward reset; it is the
client's assertion that timestamps still belong to the same monotonic run.

Account metadata or anchor storage failures, including exhausted first-writer
Firestore retries, give HTTP 503 with `Retry-After: 30` before staging/admission.
There is no alternative offset and no success ACK. The phone retains its
local audio and uses its existing transient retry/backoff path. Typed 400s
retain the refusal retry path; the app's separate indefinite retry fix is not
implemented here. All original raw archives, lineage and custody proofs stay
under their existing owners.

Only explicit future-policy contexts add `capture_time_trust=untrusted` to a
WorkItem. New projection/context/assignment guards keep that coordinate out of
nearest/overlap binding; exact retry identity and same-source frame proof keep
their separate checks. A synthetic time never proves other phone audio covered.

## Existing traffic and rollout

**Early-clock behavior is unchanged, with the future switch off or on.** Main's
legacy pipeline, batch coverage adapter and WAL coverage module are retained
byte-for-byte. The early decoder implementation is also unchanged; one public
alias exports its existing strict frame counter for the future decoder. Early admissions emit main's receipt field, no
future policy and no new trust marker. Tests execute main and candidate HTTP
admission through the real admission transaction and compare job, intake and
embedded context documents for early-only and mixed early/trusted bundles.
Thus code may deploy in any service order while future admissions remain off;
there is no reader-first rollout prerequisite for existing early traffic.

Before a later config-only activation, qualify the CPU projectors and recovery
handlers that can process future work. They must preserve/read the new marker.
The GPU scheduler deserializes WorkItems but does not make trust-sensitive
projection decisions; its completion/merge updates the original job map.
The independent review confirmed that existing GPU path compatible, so this
change neither upgrades the GPU image nor requires a new GPU reader image.

Flip only these values from `'false'` to `'true'`, after qualification:

- `backend/deploy/runtime_env/{dev,prod}.overlay.yaml`:
  `overlay.gke.backend-listen.env.SYNC_FUTURE_CAPTURE_CLAMP_ENABLED.value` and
  `overlay.cloud_run.services.<service>.env.SYNC_FUTURE_CAPTURE_CLAMP_ENABLED.value`
  for `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`.
- `backend/charts/backend-listen/{dev,prod}_omi_backend_listen_values.yaml`:
  `env[name=SYNC_FUTURE_CAPTURE_CLAMP_ENABLED].value`.

Regenerate `backend/deploy/runtime_env.yaml` with
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, update the
staged test and registry note, and run the deployment/pre-push gates. The lead
owns activation, targeted within the next two days after reader qualification;
no activation occurs merely because that date passes. Serving revision source
SHA/build-proven digest, 100% traffic, listener pod imageIDs, recovery task
URLs and current marker-compatible CPU source must be recorded. A service
spec, tag or latest-ready revision alone is insufficient. Runtime deployment
or activation has not been performed by this lane.

Rollback admission with the same twelve false values. Already admitted future
units retain their offset, frozen times and trust independently of the flag.
Keep compatible CPU readers until that work drains; admission rollback does
not authorize rolling processors back to marker-dropping versions.

## Separate early-clock follow-up

Main's early-clock helper packs each request in raw source order ending at that
request's receive time, so newest-first backlog slices can reverse or overlap
across requests. Repairing that existing defect needs its own clock-run and
migration contract for pending, already admitted and newly uploaded slices,
plus activation/rollback tests across that migration. This PR deliberately
leaves early placement and documents unchanged and does not solve that defect.
