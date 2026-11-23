# Pusher image-only rollout proposal

SCA-2070 covers the design and offline fixture. SCA-3161 uses the isolated
rehearsal below for pre-dispatch rollback evidence. Release owns live qualification,
authorization and dispatch. The serving target is Deployment
`prod-omi-pusher` in `prod-omi-backend`. The shared dependency is
`prod-omi-backend-config` in that namespace.

## Canonical entry point

Add a mutually exclusive preservation mode to
`.github/workflows/gcp_backend_pusher.yml`. Keep the protected production
environment and `prod-train` concurrency group. Require a full reviewed source
SHA admitted on main by `verify_backend_release_admission.py`, a successful
automatic development qualification run, and the immutable qualified image
digest. Reuse `verify_pusher_promotion_evidence.py`, the exact development
deployment receipt, `verify_pusher_source_closure.py`, registry digest parity,
Firestore readiness, runtime capability admission, surge capacity, and
promotion evidence. Bind the preview, canary, serving receipt and rollback
receipt to the reviewed source, exact repository and digest, and invocation.
Treat source or chart closure changes after qualification as requiring a fresh
development bake. Compare the candidate's startup and image defaults with the
serving release, including absence-sensitive policy and lease settings.

Use the live Deployment as the sole template input for this mode. Skip the
shared-config apply and Helm upgrade steps for both the serving workload and
the canary's configuration. Inside the canonical workflow, an API JSON Patch
changes only the primary container image. Record the intentional divergence
from Helm's stored image with the exact serving receipt. Teach later train
preflights to consult the receipt and refuse an implicit Helm reconciliation
that would revert the image or apply the held config drift.
`--accept-drift` is outside this mode.

## Proof before canary and promotion

1. Read the live Deployment, its ReplicaSets and serving Pods, dependency
   identities and versions, and current release receipts. Verify the serving
   Pods agree on the exact rollback image and that their effective startup
   environment agrees with a replacement using the current inputs. Updating a
   ConfigMap can leave an existing environment stale until pod replacement.
   A template and current map alone cannot prove the running baseline.
2. Inventory the namespace using paginated API discovery. Enumerate current
   Pods and owners, all built-in pod template controllers (Deployments,
   ReplicaSets, ReplicationControllers, StatefulSets, DaemonSets, Jobs,
   CronJobs and PodTemplates), and installed operators and custom controllers
   that can generate Pods, including scaled-to-zero templates. Follow owner
   chains. Inspect ConfigMap key selectors, `envFrom`, direct and projected
   volumes for regular, init and ephemeral containers where applicable.
   Explicitly account for API-reading consumers using their permissions and
   application inventory. A forbidden list, unknown generator, missing page
   or unclassified API reader is a refusal. A chart search can seed this
   inventory. The redacted receipt includes each observed consumer's kind and
   name, and the observed and expected coverage for that inspection.
3. Compare ordered `env`, `envFrom`, pod metadata, volume sources and mounts
   across serving, candidate and reverse admission. Compare final startup
   environments privately with the old pods. Resolve source precedence,
   prefixes, optional missing objects and keys, explicit empty strings, ordered
   expansion, downward API/resource fields, injected service environment and
   every possible serving platform's OCI image defaults. Verify entrypoint and
   application defaults for absent and empty policy keys. Permit the existing
   rollout pod-template hash to vary only as controller-generated telemetry
   with its original binding. Unknown or unproven inputs are a refusal.
4. Run Kubernetes server dry-run on the guarded Deployment update and
   representative Pods through their actual admission context. Check both
   forward and reverse changes. Use the isolated rehearsal below for the
   candidate-state inverse before dispatch. The live writer needs enforceable exclusion
   of competing template, config, secret, inventory and relevant admission
   changes from snapshot through the last replacement or rollback Pod. Prove
   that the existing writer controls cover each dependency and reconcile
   discrepancy before any mutation. GitHub concurrency covers participating
   workflow runs only. Repeated checks and Deployment resourceVersion tests
   alone cannot fence changes across objects. If the existing controls cannot
   prove this exclusion or equivalent server enforcement, refuse the run.
   Preserve read coverage and exclusion during canary cleanup too.
5. Keep input values and full admission payloads in restricted process memory.
   Emit categorical refusals and stable public identifiers only. Suppress
   command echo, raw errors, manifests, dumps of process environment, and
   value hashes. Bind dependency UID and resourceVersion privately. Record
   equality, digest and source, inventory identities, and gate results in the
   redacted preview. Prove that access and audit handling are already suitable.
   Missing proof is a refusal.

[Kubernetes API dry-run and conditional updates](https://kubernetes.io/docs/reference/using-api/api-concepts/)

## Canary and exact reverse

Use the existing production Pusher canary and semantic probe framework. Derive
the canary Pod from the same preserved live template and exact candidate
digest, in the same namespace, with the same environment and external
references. Changes needed to isolate the canary's traffic must pass the
same environment and admission proof. The canary must restrict work to the
canonical synthetic probe without changing custody, retention, lease behavior,
privacy policy or access. If isolation would require a config or reference
change or permit customer work, refuse. Validate effective input equality on
the admitted and running canary before its probe. Require the canonical
semantic and observability receipts for this exact candidate and baseline.

After canary cleanup, recheck the inventory, dependency versions, admission
and Deployment baseline under the same writer exclusion. The serving patch
tests Deployment UID and resourceVersion, container name at the resolved
index, and old exact image before replacing that one image field. Confirm the
admitted specification and the final pods' exact digest, readiness, effective
environment, references, semantic checks and shared-consumer scope before
reporting success.

The reverse uses the same guarded patch and admission path, from the recorded
new image back to the exact prior repository and digest. It tests the current
UID, fresh resourceVersion for the expected promoted template, exact expected
image and container identity. Revalidate the recorded dependencies and the
reverse-admitted Pod against the original runtime baseline before allowing the
reverse. Follow through to prior image readiness and effective-environment
equality. The shared map and unrelated consumers are outside the write set
in both directions. On an ambiguous response, re-read and prove whether the
exact transition committed before deciding whether to retry. Stop on any
unexplained change. The release owner qualifies rollback and authorizes its
execution as part of the separate release.

## Isolated admission rehearsal

The rehearsal command uses the same five-operation JSON Patch for both
directions. The tests bind Deployment UID, resourceVersion, container name and
expected digest. The sole replacement is the Pusher container image. It uses
production only for reads and deployment server dry-runs. It persists the
candidate and restores the prior digest only in the isolated API server. The
isolated inverse runs as an actual update from a persisted candidate so webhook
`oldObject` contains the candidate digest. On production, the prior-image dry
run before dispatch is a baseline admission check. The exact production inverse
is dry-run immediately after an independently authorized move.

### Release inputs

Use the fresh, reviewed helper with the ordinary canonical production gates.
Run from a full checkout with Python 3.11, PyYAML, authenticated `gh`, `gcloud`
and `kubectl`. Fetch `origin/main` before rehearsal. The helper fetches the
successful automatic development qualification and exact receipt from GitHub,
checks first-attempt release eligibility and source closure on fresh main, and
compares the immutable development and production registry digests. The
candidate must already be present at the approved production registry reference.
Release verifies the selected source contains the intended change.

Provide two protected kubeconfigs and an existing isolated admission server
with the same Deployment and namespace names, object and namespace labels,
annotations, full Deployment spec, and effective Kubernetes user including UID,
groups and extras. Supply the original references verbatim. The isolated server
must use distinct storage, have no workload controllers or kubelets able to
start the copied workload, and have no path to customer work. Prepare it using
an approved environment and keep it intact through verification. If setup
requires different selectors, webhook behavior, effective privileges, runtime
inputs or unapproved data access, stop. A cloned Deployment in production or a
different namespace cannot satisfy these requirements.

Release must review and retain the following evidence in the protected release
packet before declaring the rehearsal eligible:

- Admission and isolation evidence. Compare API server admission flags, policy
  bindings and parameters, namespace/object selectors, match conditions, both
  `oldObject` and `object`, and the user/authorizer context. Account for
  cluster-dependent UID, status, resourceVersion, and dry-run treatment. Verify
  applicable webhook backend code and configuration, authorization, dependencies
  and routing. Reconcile webhook or audit traces for each transition, including
  any fail-open, skipped or timed-out call. Include the controller-generated Pod
  admission context and the actual isolation controls. The helper compares the
  observed Kubernetes version, namespace labels/metadata, policy and webhook
  objects, deployment projection and effective actor in both contexts. Matching
  objects alone cannot establish equivalent webhook backend behavior.
- Startup and consumer evidence. Privately compare the running baseline and
  prospective replacement inputs, including image and app defaults, missing
  versus empty values, injected inputs, mounted data and the expected old and
  new serving digests. Enumerate and protect all shared ConfigMap consumers
  using the inventory above. The helper compares full Deployment specs and
  checks direct ConfigMap and Secret references, including projected and
  optional references. Include all other relevant namespace dependencies in
  the reviewed packet. Keep runtime values out of the packet and receipts.
- Writer exclusion evidence. Identify the enforcing controls, their scope,
  owner and expiration. Show how they exclude competing writes to the target,
  startup dependencies, relevant admission state and consumer inventory from
  snapshot through rehearsal, the authorized move and verification. Include
  direct/API and automated writers such as reconcilers and secret controllers.
  Record the observed object bindings under that exclusion. The helper checks
  object versions, drift, the packet deadline and the target patch preconditions.
  Config object checks are independent API reads. Release needs enforceable
  cross-object exclusion throughout the window.

The proof JSON links that independently reviewed evidence to the concrete
objects. Place it in protected custody along with the kubeconfigs and the
redacted receipt. The fields below show its shape using placeholders:

```json
{
  "schema": 1,
  "id": "release-packet-id",
  "evidence": {
    "admission_and_isolation": "admission-record-id",
    "effective_startup_inputs": "startup-record-id",
    "shared_consumer_inventory": "consumer-record-id",
    "writer_exclusion": "fence-record-id"
  },
  "valid_until": "2099-01-01T00:00:00Z",
  "prior_image": "gcr.io/based-hardware/pusher@sha256:<prior digest>",
  "candidate_image": "gcr.io/based-hardware/pusher@sha256:<candidate digest>",
  "source_sha": "<full qualified source SHA>",
  "qualification_run_id": 1234,
  "effective_user": {"username": "<reviewed user>", "groups": ["<reviewed group>"]},
  "server_urls": ["https://<production>", "https://<isolated>"],
  "namespace_uids": ["<production namespace UID>", "<isolated namespace UID>"],
  "live_deployment": ["<production UID>", "<production resourceVersion>"],
  "isolated_deployment": ["<isolated UID>", "<isolated resourceVersion>"],
  "extra_admission_resources": [],
  "live_dependencies": [
    {
      "resource": "configmap",
      "name": "prod-omi-backend-config",
      "version": ["<ConfigMap UID>", "<ConfigMap resourceVersion>"]
    }
  ]
}
```

Set `effective_user` to the complete `status.userInfo` from `kubectl auth whoami`.
List additional cluster-scoped policy or parameter resource types in
`extra_admission_resources` and account for other admission dependencies in the
reviewed record. Use `null` for a deliberately absent optional dependency.
Every direct reference requires an entry, including referenced Secrets. Reads
may require existing protected permissions. An API denial or unproven coverage
requires a hold.

```sh
umask 077
python3.11 .github/scripts/pusher_image_rehearsal.py rehearse \
  --proof "$PROOF" \
  --live-kubeconfig "$LIVE_KUBECONFIG" --live-context "$LIVE_CONTEXT" \
  --isolated-kubeconfig "$ISOLATED_KUBECONFIG" --isolated-context "$ISOLATED_CONTEXT" \
  > "$REHEARSAL_RECEIPT"
```

A successful invocation records source, candidate and prior image, the proof
binding, and the observed isolated candidate/restored revisions. The inverse
must return the same Deployment metadata and specification, including startup
inputs and ConfigMap references, with only the prior digest restored. Review
the admission traces and hold the current production digest pending independent
review, live qualification and authorization. If an isolated request has an
ambiguous response, reconcile the isolated object under the fence before retrying.

Immediately after the authorized move, run the same command with
`verify-inverse --rehearsal-receipt "$REHEARSAL_RECEIPT"` and save stdout to a
different protected receipt. Keep the same proof and isolated restored object.
The helper reads the observed production candidate and fresh resourceVersion,
server-dry-runs the exact inverse against that live object, compares the result
with the rehearsed baseline, and rechecks the protected state. The post-move
comparison accounts for a forward change to the Deployment controller’s
`deployment.kubernetes.io/revision` annotation. The inverse dry run must
preserve the live annotation, and a resourceVersion change during verification
still refuses. On any failure,
stop progression, retain the failure receipt, and reconcile the live object
before another write. Actual rollback requires a separately authorized action.

## Fixture entry point

```sh
bin/omi-heavy run --wait 15 --timeout 45 -- python3.11 -B \
  backend/testing/release_fixtures/test_pusher_image_preservation.py -v
```

The fixture models an admitted Pod and guarded state transitions. It compares
startup state at baseline, isolated canary, promoted replacement and reverse
replacement. It uses a synthetic default-on memo switch, an absent optional
lease key, an explicit empty override and synthetic private data. It verifies
that forward and reverse leave shared data and all other templates intact. It
also exercises mismatched qualification and canary receipts, unavailable
effective inputs, admission drift and concurrent changes. The fixture's
coverage and writer-exclusion flags model preconditions that the production
adapter must independently prove.
