# JIT QA Typesense lexical projection

`.github/workflows/jit_qa_typesense_projection.yml` owns one development-only
Typesense Cloud Run service named `typesense-jit-qa`. It is manually dispatched
from an exact `main` SHA with a first-attempt Release Eligibility proof. The
workflow accepts only the reviewed
`docker.io/typesense/typesense@sha256:5c12af89130b8ee0be11541321ba8a3a7c7a538d7c6cd95e0409dc2d75ca6455`
manifest-list image (Typesense `27.1` for the linux/amd64 Cloud Run service), wraps it
with `backend/Dockerfile.jit_qa_typesense`, and publishes the resulting image
to the development registry by digest.

The service has one container, one warm instance, a maximum of one instance,
1 CPU, 1 GiB memory, and an ephemeral `/tmp/typesense` data directory. Its
only credential is `jit-qa-typesense-api-key`, which must be explicitly labeled
as owned by the QA plane. The wrapper reads that key from the environment; the
pinned Typesense 27.1 server maps `TYPESENSE_API_KEY` to its API-key setting,
so the secret never appears in the process argument list. No Firestore, Firebase,
customer credential, queue, Redis, or production Typesense binding is given to
the service.

The workflow stores exactly 64 lowercase hexadecimal bytes. Secret Manager
preserves uploaded bytes, so new keys pass through
`backend/scripts/jit_qa_typesense_key_shape.py` before upload rather than being
piped directly from a newline-terminated command. An existing labeled QA secret
may be repaired only when it has the one known historical shape (64 lowercase
hex bytes followed by one LF); a valid 64-byte key is reused and every other
shape fails closed. The build smoke runs the same legacy-shape normalization
before starting the server, then authenticates collection and export requests
with the normalized bytes.

The rehydrate step runs the existing
`utils.memory.atom_keyword_index.rebuild_atom_keyword_index` against the named
`based-hardware-dev/jit-qa` Firestore database and fixed QA UID. It verifies the
collection schema, exports the bounded document set, hashes the projection
including content in process (content is never persisted in the receipt), runs
a real `keyword_search_ledger_memory_ids` producer query, and then invokes the
real `search_knowledge` consumer path with the same query.
The artifact contains counts, schema/projection digests, and query/result
digests; it never contains query text, document bodies, or provider responses.
A query with no active current ledger result fails the run. The receipt also
records the one-instance resource bounds, explicit `cost_attribution:
not_measured` status, and whether a post-restart replay has run. A `ready`
receipt therefore proves the current lexical rebuild and query only; cost
billing and restart replay remain named gates until their receipts are
present. The existing QA seed's legacy-migration rows are intentionally insufficient; use a real
active/open `knowledge_ledger.v1` fact, document, or trigger row written by the
approved ledger path. Pinecone is absent from QA, so this receipt qualifies
lexical retrieval only and records semantic/vector retrieval as unavailable.

Each prove run deletes the prior readiness marker before purging or rebuilding
the projection. It writes a new marker only after the complete Firestore
rebuild, projection count/digest, and producer keyword proof have succeeded,
immediately before the consumer proof. If `search_knowledge` fails or receipt
validation fails, the marker is deleted again. The application therefore
remains fail-closed during rebuilds and after handled incomplete consumer
verification. A process crash or interruption after the marker write and
before the consumer receipt can leave a rebuild-ready marker without a
qualified receipt; run `prove` while the QA app is idle, require the final
content-free receipt, and then verify an actual QA app query before treating
the projection as qualified.

## Dispatch and restart proof

Resolve and review the pinned upstream `27.1` manifest-list digest before
dispatch. Pass an actual term from an active QA ledger row and a unique,
lowercase run id. A service restart loses `/tmp/typesense`; the separate
readiness marker is lost with it, and the QA backend fails closed for
current-ledger search. Rerun the workflow rehydration step with a new run id
and verify the new content-free rebuild receipt plus an actual QA app query
against the authoritative Firestore-backed result. The projection digest is
evidence for that rebuild snapshot; it is not a live content-hash invariant
that the app must recompute or export on every chat query. Do not hand-inject a
document or treat an empty search as readiness.

The projection workflow deliberately does not deploy application services. The
existing `.github/workflows/jit_qa_cloud_run.yml` resolves and validates this
service before deploying the QA backend and desktop services, then applies the
following narrow environment and secret bindings to both:

```sh
# Resolve and validate the service in the existing deploy/verify job.
typesense_url="$(gcloud run services describe "$QA_TYPESENSE_SERVICE" \
  --project "$QA_PROJECT" --region "$QA_REGION" --format='value(status.url)')"
[[ "$typesense_url" =~ ^https://typesense-jit-qa-([a-z0-9-]+-uc\.a\.run\.app|[0-9]+\.us-central1\.run\.app)$ ]]
typesense_host="${typesense_url#https://}"

# Append these literals to the existing QA HTTP-service environment.
TYPESENSE_HOST="$typesense_host"
TYPESENSE_HOST_PORT=443
TYPESENSE_PROTOCOL=https
MEMORY_TYPESENSE_COLLECTION=jit_qa_canonical_memory_atoms
MEMORY_TYPESENSE_READINESS_REQUIRED=true
MEMORY_TYPESENSE_READINESS_COLLECTION=jit_qa_typesense_readiness
MEMORY_TYPESENSE_READINESS_SOURCE_SHA="$SOURCE_SHA"

# Append this dedicated secret to the existing QA HTTP-service bindings.
TYPESENSE_API_KEY=jit-qa-typesense-api-key:latest
```

The integration owner must carry the resolved host into both `backend-jit-qa`
and `desktop-backend-jit-qa`, retain the existing `jit-qa` Firestore fence, and
add a post-deploy resource check using
`validate_typesense_cloud_run_resource` plus an app-level `search_knowledge`
probe. Resolve the live service image from the immutable development registry
tag `gcr.io/based-hardware-dev/typesense-jit-qa:$SOURCE_SHA`, and require its
digest to match the service image. No normal-dev or production Typesense
endpoint is an acceptable substitute.

Dispatch `mode=bootstrap` first when the named QA database does not yet contain
an active intent-backed ledger row. This builds, smoke-tests, and deploys the
Typesense service, then emits a `not_qualified` receipt only after confirming
that both the readiness marker and projection collection are absent. The
backend's readiness gate therefore remains closed while QA Chat creates the
first row; ordinary Chat write and extraction paths are unaffected because the
gate applies only to current-ledger search. Once QA Chat has saved a real
current fact, document, or trigger, dispatch `mode=prove` with a matching
lexical query to rebuild, write the readiness epoch, and emit the lexical proof
receipt.

The build job runs the wrapper image locally before publishing it: it starts
the pinned Typesense server with a synthetic smoke key, checks health, creates
and upserts a synthetic document, and verifies the real JSONL export endpoint.
In `prove` mode it also runs the projection runner's `--help` under a harmless
encryption-secret fixture so import failures stop before publication. The local
smoke is an image check only; it does not access Firestore, QA secrets, Chat,
or a model provider.

To retire the QA projection, first stop any QA execution, then delete only the
`typesense-jit-qa` service and dedicated key secret in `based-hardware-dev`.
The named Firestore database remains governed by the existing QA cleanup and
seed runbook.
