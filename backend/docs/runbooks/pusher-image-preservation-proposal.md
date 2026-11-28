# Pusher image-only rollout proposal

SCA-2070 covers the design and offline fixture. SCA-3161 closed the isolated
rehearsal route (GKE Warden's webhooks run in the managed control plane), so the
protected workflow uses live production server dry-runs instead; see
[Protected workflow operation](#protected-workflow-operation). Release owns live qualification,
authorization and dispatch. The serving target is Deployment
`prod-omi-pusher` in `prod-omi-backend`. The shared dependency is
`prod-omi-backend-config` in that namespace.

## Canonical entry point

Add a mutually exclusive preservation mode to
`.github/workflows/gcp_backend_pusher.yml`. Keep the protected production
environment and its own per-target Pusher concurrency group. A Cloud Run train
keeps `prod-train` while Pusher qualifies and rolls (David's 2026-11-28 slot
ruling, SCA-4763); the carve-out covers only the isolated canary and the
protected image-only modes, never the ordinary full Pusher deploy. Require a
full reviewed source
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
references. For the isolated image-only producer,
`backend/scripts/pusher_canary_from_live.py` does this literally:
it copies the live Deployment's PodTemplate and the live runtime ConfigMap,
changes only the Pusher image, the canary identity labels and the ConfigMap
references (redirected to the copied map), and creates a plain ClusterIP that
selects only the canary. Nothing is rendered from the dispatching main. A
canary rendered from main carries chart and ConfigMap values an image-only
promote never applies, which is exactly why the first protected canary
verification refused with `effective_environment_differs` (run 46139487564).
An ordinary full deploy keeps the previous behaviour: its canary renders and
exercises the proposed configuration that the deploy will apply.
Changes needed to isolate the canary's traffic must pass the
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

The protected workflow no longer uses this route (SCA-3161); it is kept as the
reference for `pusher_image_rehearsal.py`. The rehearsal command uses the same five-operation JSON Patch for both
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

## Protected workflow operation

This path is for the pinned SCA-4763 baseline. The default dispatch continues
to use the existing workflow. Release must keep the hold until David has
approved the reviewed workflow and the exact candidate. Do not publish
kubeconfigs or raw admission responses.

Use `gcp_backend_pusher.yml` from main, with `environment=prod`,
`service=pusher`, `branch=<full qualified source SHA>`,
`pusher_image_digest=<sha256 digest>`, and
`pusher_dev_qualification_run_id=<automatic development qualification run>`.
Select `pusher_image_only=preview`, `canary`, `promote`, or `rollback`. The job
uses the existing prod environment and the per-target `deploy-gke-pusher-prod`
lock, which it shares with the isolated canary and break-glass Pusher deploys.
It does not build,
push, tag, install charts, apply configuration, or create or delete a canary.

No secret is staged for this mode. The evidence is the non-secret dispatch
input `pusher_image_only_evidence`, a JSON object of ids only (schema 2):

```json
{
  "schema": 2,
  "mode": "promote",
  "source_sha": "<full qualified source SHA>",
  "prior_image": "gcr.io/based-hardware/pusher@sha256:f26e8757759fe6907a9ef0e4c31d0a08a8ed527d777db5f472b33bffcff6d925",
  "candidate_image": "gcr.io/based-hardware/pusher@sha256:<candidate digest>",
  "qualification_run_id": 1234,
  "reviewed_preview": {"run_id": 5678},
  "canary": {"run_id": 9012}
}
```

`mode` must equal `pusher_image_only`. Preview and rollback omit
`reviewed_preview` and `canary`; canary and promote require both. The packet
carries no run id of its own (the dispatching run is `GITHUB_RUN_ID`) and no
review, approval or hash field: the job resolves those itself.

- Every referenced run is fetched from the GitHub API and must be this
  repository on `main` with its producer event: the automatic development
  qualification (`gcp_backend_pusher_auto_deploy.yml`) on `push`, and the
  preview and canary runs (`gcp_backend_pusher.yml`) on `workflow_dispatch`, first
  attempt, concluded `success`.
- Preview and canary runs are accepted only from a main revision whose
  evidence producers and verifiers are byte-identical to the dispatching
  revision (`CONTROL_PATHS` in `pusher_image_only.py`).
- Approval comes from `GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals`
  (`actions: read`): the prod environment approval of the preview run, of the
  canary run and of the current run. The approver logins are recorded in the
  redacted receipt. Agents and humans share one GitHub account, so this proves
  that a prod environment approval happened, not who in particular approved.
- Custody is unchanged by that check. The GitHub prod approval only lets the
  jobs start. Before promote, Release still reviews the posted preview and
  canary receipts, and David's authorization of the exact candidate must be in
  Release custody, as stated at the top of this section. The job's approval
  check does not replace either.
- The qualification run's revision must already carry this revision's canary
  inverse helper byte for byte (`INVERSE_HELPER_PATHS`). The first pilot
  therefore needs a successful automatic qualification after this change merges;
  a qualification from before it (for example the run at `1fe2c81a`) is refused.
- Receipts come from those runs' artifacts and bind the candidate digest,
  source SHA, workflow revision and the target Deployment UID.

Run preview first. Its receipt (artifact `pusher-image-only-receipt`) records
live forward server admission projected to exactly one image change, and the
baseline→baseline server dry-run on `prod-omi-pusher`. That dry-run is
current-state evidence: today's admission still accepts the baseline object.
It is not a rehearsal of the reverse transition. Warden evaluates the object,
so the `oldObject` difference does not change that baseline verdict; a scoped
ruling accepts the residual risk for `oldObject` on the target Deployment.

Canary verifies the canary run below and its inverse receipt and writes nothing.
After the canary is removed, promote requires the reviewed preview, the canary
evidence, a fresh guarded forward dry-run and live surge check, and an
effective-environment comparison. The comparison refuses unless, per input
class, the canary's startup inputs equal the live Pusher's:

- `runtime_config_map`: the canary's ConfigMap hash equals the hash of live
  `prod-omi-backend-config`, the same comparison the regular Helm path makes;
- `pod_template`: every parity class in the canary inverse receipt is `equal`;
- `dependency_versions`: every referenced Secret and ConfigMap other than the
  runtime ConfigMap keeps the metadata identity (UID and resourceVersion) the
  canary held from before its first pod started through its probe. A Secret
  rotated between canary and promote refuses. Only digests of that identity
  list are in the receipt;
- `live_template_since_canary`: the live Deployment UID and Pod template are
  the ones that parity measured.

Only `equal`/`differs` is recorded. The job then patches only the Pusher image,
dry-runs the exact live inverse, and checks readiness for every serving Pusher
replica at the approved digest.

Once the forward write has been attempted, every failure goes through recovery;
none ends as an ordinary refusal:

- The inverse dry-run is refused, or the write, the post-write read or the
  probe does not answer (for example a timeout). The job re-reads the
  Deployment. If it has the same UID and the candidate image, the job makes
  exactly one guarded reverse patch with fresh preconditions: it tests the same
  UID, the current resourceVersion, the container name and the candidate image.
  If the reverse is admitted, it verifies the baseline rollout and readiness and
  ends `REVERSED` (the promote failed).
- The state cannot be read or is not that candidate object, the reverse is
  refused or unconfirmed, or the reverse rollout is not proven. The job ends in
  HOLD (`REFUSED_INVERSE` after a refused inverse, otherwise
  `UNCERTAIN_AFTER_WRITE`) with no further patch.
- The forward rollout wait or its readiness check fails. The job holds
  (`UNCERTAIN_AFTER_WRITE`) instead of reversing: the single rollout wait is
  spent, and a second rollout would run past the job ceiling.

Final serving verification, forward and reverse, requires the Deployment UID
that was patched: a replacement object with the same image and generation ends
in HOLD, never PASS or REVERSED. Before each live patch the job makes a
write-attempt marker durable in the run's temp directory. If the process dies
before printing its receipt, the detector (`pusher_image_only_detect.py`) sees
the marker with a missing, empty or invalid receipt and pages
`UNCERTAIN_AFTER_WRITE`.

The receipt records `deployment_uid_before`, `deployment_uid_observed`,
`patched_deployment_uid`, `serving_image_observed` and `reverse_patch` (`not_attempted`,
`rejected_on_preconditions`, `rejected`, `unconfirmed` or `succeeded`). Every
HOLD writes the run summary and pages the deploy channel with those fields and
the manual recovery below.

Each path has at most one 160-minute rollout wait, because the post-move inverse
is decided before the forward wait. The job ceiling is 220 minutes: the rollout
wait, two 5-minute status reports, about 20 minutes of checks, and about 30
minutes so the receipt, summary and page land first. It also bounds how long the
run holds the Pusher lock.

### Canary qualification run

Dispatch the regular deploy job with `pusher_canary_only=true`, for prod
Pusher, with the exact `pusher_image_digest` and
`pusher_dev_qualification_run_id` and no break-glass option. That run:

- promotes the qualified digest into the production registry;
- creates the isolated canary and runs the canonical semantic probe;
- records the candidate→baseline inverse server dry-run on the canary,
  including a redacted equal/differs parity check of the canary Pod template
  against live `prod-omi-pusher` per field class, excluding the image. The
  canary's release name and isolated ConfigMap name are mapped to the live
  names first, and a catch-all class compares every field no other class names
  (for example `hostNetwork`);
- records the metadata-only UID and resourceVersion of every Secret and
  ConfigMap the canary will reference, its isolated runtime ConfigMap
  included, before the canary Deployment exists (so before its first pod loads
  its environment). It records them again when the inverse is recorded and
  after the semantic probe, and fails unless the full inventory is unchanged.
  The isolated and production runtime ConfigMaps are different objects, so
  promote compares those two by content hash;
- uploads the canary evidence, uploads the inverse receipt as its own artifact
  `pusher-prod-canary-inverse-receipt`, and removes the canary.

The inverse helper and its import (`pusher_canary_inverse.py`,
`pusher_image_rehearsal.py`) run from the immutable workflow-control revision
that the receipt names, and the runtime checkout's copies must be byte-identical.
Source admission binds both paths, and the automatic qualifier runs when either
changes.

It then stops before "Apply non-secret pusher runtime config": no shared
ConfigMap apply and no Helm. A green conclusion means "canary qualified", and
the image-only promote accepts only a `canary_only` canary receipt. The inverse
step runs only on this stop; a regular deploy can redeploy the serving image,
where a candidate→baseline inverse does not apply.

### Manual recovery after a HOLD

The job may already have made its one reverse attempt; the receipt's
`reverse_patch` says whether it was not attempted, rejected on preconditions,
rejected, unconfirmed or succeeded. Do not run an unpinned `rollout undo`: after
a committed reverse it would move back to the candidate. Instead:

1. Confirm the Deployment UID equals the receipt's `deployment_uid_before`. If
   it differs (`deployment_uid_observed`), the object was replaced: stop, change
   nothing, and escalate to Release.
2. If the pusher image already reads the pinned baseline, do not patch. Go to
   the rollout status and readback.
3. Otherwise find the revision whose pusher image is verified to read the pinned
   baseline digest and restore exactly that revision with `--to-revision`.

Under R44 the Pusher operator performs this restore with the prod environment
credentials. Prerequisites: the prior production ReplicaSet is still retained
(unexpired `revisionHistoryLimit`), release custody is unchanged, and admission
accepts the baseline object. Keep the Helm values untouched.

```sh
kubectl -n prod-omi-backend get deployment prod-omi-pusher -o jsonpath='{.metadata.uid}{"\n"}'
kubectl -n prod-omi-backend get deployment prod-omi-pusher \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="pusher")].image}{"\n"}'
kubectl -n prod-omi-backend rollout history deployment/prod-omi-pusher
# For a candidate revision N, verify its pusher image is the pinned baseline digest:
kubectl -n prod-omi-backend rollout history deployment/prod-omi-pusher --revision=<N> \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="pusher")].image}{"\n"}'
# Only if the UID matched, the image above was not the baseline, and N verified:
kubectl -n prod-omi-backend rollout undo deployment/prod-omi-pusher --to-revision=<N>
kubectl -n prod-omi-backend rollout status deployment/prod-omi-pusher --timeout=9600s
kubectl -n prod-omi-backend get deployment prod-omi-pusher \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="pusher")].image}{"\n"}'
python3 backend/scripts/deploy_status_report.py --env prod --include-gke --gke-service pusher
```

Required serving readback: the Pusher container image reads
`gcr.io/based-hardware/pusher@sha256:f26e8757759fe6907a9ef0e4c31d0a08a8ed527d777db5f472b33bffcff6d925`,
the rollout reports the new ReplicaSet ready with no active old-replicaset pods,
and `deploy_status_report.py` exits clean. If the restore is refused or the
readback does not match, leave traffic as it is and escalate to Release; do not
attempt another patch.

Rollback uses a separately approved protected run. It accepts the same
candidate identity (a schema-2 packet without `reviewed_preview` or `canary`),
verifies the pinned prior image in
the production registry, checks the exact live candidate and inverse
admission, and restores only the original Pusher image field. It does not
depend on the candidate being healthy. For either write, a patch error or
post-patch verification failure requires Release to reconcile the actual
Deployment and pods under the approved writer exclusion before attempting
another write. A failed workflow can follow a successful API patch.
