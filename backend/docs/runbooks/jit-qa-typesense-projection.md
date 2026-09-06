# JIT QA Typesense lexical projection

`.github/workflows/jit_qa_typesense_projection.yml` owns one development-only
Typesense Cloud Run service named `typesense-jit-qa`. It is manually dispatched
from an exact `main` SHA with a first-attempt Release Eligibility proof. The
workflow accepts only a reviewed `docker.io/typesense/typesense@sha256:...`
image (the repository's local harness currently pins version `27.1`), wraps it
with `backend/Dockerfile.jit_qa_typesense`, and publishes the resulting image
to the development registry by digest.

The service has one container, one warm instance, a maximum of one instance,
1 CPU, 1 GiB memory, and an ephemeral `/tmp/typesense` data directory. Its
only credential is `jit-qa-typesense-api-key`, which must be explicitly labeled
as owned by the QA plane. The wrapper reads that key from the environment and
passes it to the Typesense server without logging it. No Firestore, Firebase,
customer credential, queue, Redis, or production Typesense binding is given to
the service.

The rehydrate step runs the existing
`utils.memory.atom_keyword_index.rebuild_atom_keyword_index` against the named
`based-hardware-dev/jit-qa` Firestore database and fixed QA UID. It verifies the
collection schema, inventories only non-content document metadata, hashes the
projection, runs a real `keyword_search_ledger_memory_ids` producer query, and
then invokes the real `search_knowledge` consumer path with the same query.
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

## Dispatch and restart proof

Resolve and review the digest for the pinned upstream `27.1` tag before
dispatch. Pass an actual term from an active QA ledger row and a unique,
lowercase run id. A service restart loses `/tmp/typesense`; rerun the workflow
rehydration step with a new run id and compare the new content-free receipt's
projection digest/count against the authoritative Firestore-backed result. Do
not hand-inject a document or treat an empty search as readiness.

The workflow deliberately does not modify the existing
`.github/workflows/jit_qa_cloud_run.yml`. After this service is ready, its
application integration needs the following narrow additions in that workflow's
QA backend and desktop deployment path:

```sh
# Resolve and validate the service in the existing deploy/verify job.
typesense_url="$(gcloud run services describe "$QA_TYPESENSE_SERVICE" \
  --project "$QA_PROJECT" --region "$QA_REGION" --format='value(status.url)')"
[[ "$typesense_url" =~ ^https://typesense-jit-qa-[a-z0-9-]+\.run\.app$ ]]
typesense_host="${typesense_url#https://}"

# Append these literals to the existing QA HTTP-service environment.
TYPESENSE_HOST="$typesense_host"
TYPESENSE_HOST_PORT=443
TYPESENSE_PROTOCOL=https
MEMORY_TYPESENSE_COLLECTION=jit_qa_canonical_memory_atoms

# Append this dedicated secret to the existing QA HTTP-service bindings.
TYPESENSE_API_KEY=jit-qa-typesense-api-key:latest
```

The integration owner must carry the resolved host into both `backend-jit-qa`
and `desktop-backend-jit-qa`, retain the existing `jit-qa` Firestore fence, and
add a post-deploy resource check using
`validate_typesense_cloud_run_resource` plus an app-level `search_knowledge`
probe. The projection workflow's readiness receipt remains the source of the
expected immutable Typesense image digest; no normal-dev or production
Typesense endpoint is an acceptable substitute.

To retire the QA projection, first stop any QA execution, then delete only the
`typesense-jit-qa` service and dedicated key secret in `based-hardware-dev`.
The named Firestore database remains governed by the existing QA cleanup and
seed runbook.
