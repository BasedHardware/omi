# Structured logging rollout

`omi_logging.configure_logging(service, ...)` is the dependency-free foundation.
Entrypoints migrate one deployment at a time after consumer admission. The fleet
guard in `scripts/check_logging_entrypoints.py` discovers Docker launchers and
Helm overrides; `logging_rollout_pending.json` records the remaining legacy
violations. Remove each entry on adoption. The local/CI ratchet rejects increases
and requires unconditional module-level shared setup, no print/basicConfig, and
`log_config=None` for direct Uvicorn calls. Infrastructure probes are excluded.

Images must copy `backend/omi_logging.py` into their Python application import root;
use `from omi_logging import configure_logging, TraceContextMiddleware`. Do not
import through `utils`: the Parakeet NeMo image provides a competing top-level
`utils` package. Validate each image with the runtime-image registry smoke path.
Call setup before heavy imports; reapply after libraries that install handlers.
Install `TraceContextMiddleware` around the ASGI app to carry validated Cloud Trace
or W3C trace IDs through request handling. Set the project explicitly or through
`GOOGLE_CLOUD_PROJECT`, `GCP_PROJECT`, or `GCLOUD_PROJECT`; trace resource names
are omitted if no project is known. Set `OMI_ENV_STAGE` or pass `environment`.

Executor adoption gate: `run_in_executor` does not inherit contextvars. Before
switching Parakeet or another executor caller, capture a fresh
`contextvars.copy_context()` per submission and dispatch
`loop.run_in_executor(pool, context.run, function, *args)`; bind keyword arguments
with `functools.partial`. Never reuse one context for concurrent submissions.
Verify worker logs retain the request trace and unrelated work does not inherit
it. Middleware alone does not provide thread or process context propagation;
process workers require explicit validated trace metadata at their boundary.

GCP runtime markers select one-line JSON on stdout. `OMI_LOG_FORMAT=json|text`
overrides detection. Cloud text rollback retains the legacy stdout/stderr severity
split; JSON is required for precise WARNING severity on GKE. Exceptions include
the traceback in `message` and Error
Reporting type/service fields only at ERROR or above. Local output defaults to readable text. Preserve
message strings while migrating so downstream filters retain their meaning.
Unhandled exceptions retain their validated trace IDs for the outer Uvicorn log
after request context resets. The requested level also constrains named loggers.
Cloud Run uses platform request logs. GKE suppresses successful health/metrics
probes and uses LB logs for diarizer, nllb, parakeet, pusher and vad. Keep general
access records for listen, llm-gateway and diarizer-batch until actual route
coverage is proven. A local project ID alone does not suppress general access
records. Exceptions and ERROR records are never suppressed by noise filters.

## Consumer admission

Before switching any service, update and read back the current live filters for:

- `backend_from_segments_returned`, `backend_tombstone_guard_firing`
- `daily_summary_recap_generated`, `daily_summary_user_failed`
- `firestore_missing_index_errors`, `firestore_missing_index_errors_gke`
- `omigtp-api-requests`
- sink `vad-streaming-to-bigquery`

Preserve resource predicates and widen message predicates with
`(textPayload:"phrase" OR jsonPayload.message:"phrase")` (or the same regex).
Preserve broader SEARCH semantics when adding explicit message matches. Dry-run
with `gcloud logging read` using timestamp-only output; no matches establishes
syntax acceptance only. Recheck counters on known events after every deployment.
The daily-summary metrics also extract `retry`, `reason`, and `error_type` from
textPayload. Widening filters alone does not preserve these label series: their
producer/extractor transition needs a separate verified compatibility gate before
notifications-job migration. Do not silently accept empty label values.

`sync_backfill_uid_sequencer_scheduler_failure` selects Cloud Scheduler platform
AttemptFinished records, not application messages. Preserve `severity>=ERROR`,
`jsonPayload."@type"`, job ID and resource predicates unchanged.

## Adopted in text mode

`main.py` (backend Cloud Run services and listen), `llm_gateway/main.py`,
`pusher/main.py` and `utils/messaging/maintenance.py` call
`configure_logging(..., default_format='text')` (plan B B2: the role images
must pass this guard). Text mode keeps the INFO-stdout / WARNING-stderr split
and `textPayload`, so the filters above keep matching; the visible change is
the line prefix (`INFO logger: message` instead of `INFO:logger:message`) and
Uvicorn's own records routing through the root handler. Pusher passes
`access_policy='keep'`. The JSON switch for each of these services is
`OMI_LOG_FORMAT=json` in its runtime env, after the consumer admission above;
install `TraceContextMiddleware` in the same change so JSON lines carry traces.

## Per-service acceptance

Migrate separately in this order: diarizer, nllb, llm-gateway, diarizer-batch,
pusher, parakeet, vad, backend-listen, desktop-backend, shared Cloud Run backends,
Modal HTTP/jobs and messaging maintenance. Use existing deployment workflows,
record immutable rollback images/revisions first, and wait for any concurrent
release on the same service. Listen rollout targets only the main deployment.

Compare exact before/after windows: severity counts, JSON share, single-entry
tracebacks, Error Reporting grouping, metric labels/counters, sink delivery,
request coverage, and log bytes/day by container. Watch at least 15 minutes;
compare 5xx and restarts with the preceding 24–48 hours. Capped log samples are
not complete rates or billed-byte measurements. Roll back the affected image if
signal is lost; retain widened filters through the rollback window.

Diarizer adoption explicitly keeps general access logs: the live Gateway backend
has logging disabled while its separate Ingress backend enables it. Request metrics use the service network-endpoint-group name, which differs
from the Compute backend-service name. Recheck the active route and matching backend before suppressing it.

For diarizer, dispatch `gcp_diarizer.yml` from protected `main` with
`environment=prod` and `branch=<full merged source SHA>`. The existing branch
input controls checkout and the image tag comes from that checkout. Roll back
through the same workflow using the recorded previous source SHA.

NLLB records the currently serving immutable digest in the deployment annotation
`omi.me/previous-image-digest` before each normal workflow rollout. Normal releases deploy the resolved candidate
digest; retries of an already-serving candidate retain the original rollback receipt. To recover,
dispatch the same `gcp_nllb_translation.yml` workflow with `environment=prod` and
`rollback_digest=<recorded sha256 digest>`. This uses protected-main tooling,
validates the receipt and registry artifact, and replays the existing image without
rebuilding historical sources that predate the runtime-image registry. Rollback
remains available when the new image fails readiness. Normal releases still build
and smoke the image; both paths wait for rollout and strict deployment status.
