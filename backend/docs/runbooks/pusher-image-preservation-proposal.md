# Pusher image-only rollout proposal

SCA-2070 covers the design and offline rehearsal. Production qualification requires
a separate release-owner run. The serving target is Deployment
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
   forward and reverse changes. The live writer needs enforceable exclusion
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
