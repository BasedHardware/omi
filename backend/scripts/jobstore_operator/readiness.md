# LIFECYCLE: permanent
# One metadata-only readiness probe

This is preparation for one exact session, not a runtime or serving admission.
The candidate image in `readiness_contract.py` has a verified local OCI export.
Its `qualification_run` remains null until the existing Release executor supplies
actual native AMD64 qualification and immutable publication receipts for this
exact digest. The original `a79982bb…` base passed native qualification and immutable publication in
[Actions run 43960712883](https://github.com/BasedHardware/omi/actions/runs/43960712883);
that receipt does not qualify the derivative candidate. Its frozen source expects the exact migration 0001..0008 vector. Main also has
0009 for a separate PostgreSQL-primary worker roll; never run migrations or
substitute main's source/vector to make this probe pass. A readiness-helper
change requires a new exact artifact and fresh qualification as described below.

`readiness_probe.py` is a local renderer and verifier. It has no Kubernetes,
cloud, SQL, credential or execution interface. It does not initialize state.
Its UID-precondition DELETE request refuses deletion of a later Pod that reuses
the name. It neither sends the request nor proves cleanup succeeded.

`qualification_run` is provenance metadata, deliberately not an authorization
input to this offline renderer/verifier. It remains null while qualification is
pending. Rendering a manifest grants no execution permission: the existing Release
executor must separately verify exact-candidate native qualification, publication
and fresh packet admission before any create. An image-pull result is not that gate.

Use one bare Pod created once with a fresh 128-bit random run token. It has
no replacement controller, `restartPolicy: Never`, a 90-second active deadline
and 15-second termination grace. The frozen process guard bounds its only
child to 60 seconds and cleans descendants. Even a Job configured for one
completion can sometimes start a program twice, so it is unsuitable for this
one-attempt contract. See the [Kubernetes Job guarantee](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

The Pod uses the existing `batch-pipeline-worker` KSA, UID/GID 1000, hostname
`jobstore-reconcile-0` and immutable image. It mounts only a 64Mi temporary
directory; the API's standard native KSA token projection is allowed. No PVC,
canonical state mount, ports, sidecar, init container, credential override or
copy/index admission is allowed. There is no reconcile or supervisor command.

Placement is an independent admission, not an argument supplied on trust.
Release must freshly verify the exact cluster/context, namespace and KSA UIDs,
GSA binding, Linux AMD64 node UID, Ready/no-pressure/uncordoned status, taints,
requested and actual headroom, quota/LimitRange, network and admission policies.
The node's fresh region and zone labels must equal `us-central1` and
`us-central1-a`. These exact topology labels are rendered explicitly following
the 2026-11-16 admission dry-run; they are not inferred from the Pod or accepted
as arbitrary injected metadata. A node UID or topology change holds execution
until placement and the pinned literals are reviewed again.
The 100m CPU/256Mi request and 500m/512Mi limit are ceilings to review against
that placement, not an approved serving budget. `nodeName` pins the existing
node and prevents this unscheduled workload from requesting an autoscaler
addition; it also bypasses the scheduler, so it must never bypass its taint,
resource or policy checks. Do not resize, add capacity, alter access, relax
admission or change a node to fit it. Escalate any genuinely ungranted guarded
delta as a concrete action. The sole existing Release executor owns execution.

## Source-check correction and qualification gate

The earlier cached-image attempt on `8b0bf0de…` terminated with exit 2 and
`TimeoutExpired`; its exact UID cleanup was verified. No SQL-readiness or rollback
receipt was accepted. The previous qualification's wrong-host refusal did not
exercise the real source checks at the admitted resource limit.

`runner_readiness.py` is the versioned candidate for the in-image `readiness.py`.
It retains full HEAD and tracked/untracked cleanliness checks, bounds HEAD to 5s
and status to 30s within the unchanged 50s probe deadline, and adds fixed failure
stages and bounded error categories only to HOLD reports. Each Git call is also
capped by the actual remaining overall budget; the source allowance does not
reserve a fixed amount of time for credentials or SQL. The successful metadata
report stays unchanged.

A source-only GKE diagnostic on 2026-11-17 completed the strict status scan cleanly
in 14.641372s, after an earlier metadata attempt timed out at the former 15s cap.
The 30s allocation gives that stage headroom without changing the total deadline,
Pod deadline or resources. One observation does not bound future scans, establish
a root cause, or prove SQL readiness. The rebuilt image requires fresh native
acceptance and a separately reviewed actual metadata attempt.

The candidate uses a readiness-only derivative of the verified `a79982bb…` base.
Its original 13 layers remain byte-for-byte identical; the sole added filesystem
layer replaces `/opt/runner/readiness.py`. Runtime configuration differs only in
three provenance labels: the new build-input hash and the explicit original
base manifest/build-input hashes. The frozen source, dependencies, supervisor,
process guard and original `/build/` inputs remain unchanged. The fixture includes
the actual derivative recipe, verifier, closed input manifest and provenance.
The attempted full rebuild's offline dependency install failed with local Docker
VM ENOSPC; that failed receipt is retained and is not qualification evidence.

Before publication, qualification now runs the exact new image with the correct
hostname, UID1000, read-only root, no network, 0.5 CPU and 512Mi without extra swap. It executes the
real source checks before an injected credential refusal; no real ADC or SQL call
is needed. This check runs before the broader 2-CPU smoke, avoiding that smoke's
source access as a prerequisite. It is not a guarantee of cold host page cache or
future Kubernetes startup latency. Its exact runner hash and fixed refusal proof
are required by publication admission, in addition to all 58 native fixture tests
without skips and exact image identity/cleanup checks.
Proof-critical checks use explicit failures and refuse optimized Python, so `-O`
cannot suppress them. A malformed runner hash refuses before host/container access.

Any source-stage timeout holds before publication. Do not drop tracked-file
content checks, untracked-file checks, or extend the global/Pod/waiter deadlines
or resources to clear the gate. A new image/build/fixture contract and actual
native publication receipt are required before another separately reviewed live
metadata attempt. Old image receipts remain historical evidence. No source change
here admits persistent state, serving, or a Firestore authority flip.


## Concrete execution packet

Before creation, bind the reviewed source commit, manifest hash, fresh placement
receipt, run token, namespace/KSA/node UIDs, exact API context and scope authority.
An offline manifest or unsigned receipt does not itself grant permission.
Recheck those UIDs and controls at execution. A server dry-run must first pass
`check-manifest --pod-receipt server-dry-run.json` with the same token/node and
a new `--output` receipt: unexpected mutation
or a collision holds the attempt. No server dry-run is implicit in these tools.
Labels and annotations must match exactly, and nonempty finalizers refuse.
Missing, changed or additional topology labels refuse at both dry-run and
completed-Pod validation; there is no topology wildcard or normalization.
Only enumerated API defaults are normalized: the KSA mirror, default scheduler,
zero priority, default preemption policy, the two standard 300-second NoExecute
tolerations, false container stdin/tty flags, false container `privileged`,
false mount `readOnly`, empty `emptyDir.medium`, and omitted false-valued
`hostNetwork`/`hostPID`/`hostIPC` fields. Other spec fields hold the
attempt until reviewed; no admission annotation is implicitly trusted.

Render locally with a new output file:

```sh
python backend/scripts/jobstore_operator/readiness_probe.py render \
  --run-token "$PROBE_TOKEN" --node-name "$ADMITTED_NODE" --output pod.json
```

Then Release creates only that exact Pod once with `kubectl create`, the
reviewed explicit context/namespace and a bounded request. Do not use `apply`,
`generateName`, a controller, an automatic retry or an existing worker. If the
create result is uncertain, inspect the exact name/token and reconcile custody;
never issue a second creation. Capture the API-returned Pod UID immediately.
Keep an independent bounded cleanup waiter armed before sending the create.

Wait on that exact UID for a terminal phase with an overall 120-second deadline,
exiting immediately on failure. Capture the exact Pod JSON and at most 64KiB
of its sole container's output privately. Do not publish raw unknown output,
environment dumps, tokens, customer IDs or state. Validate locally:

```sh
python backend/scripts/jobstore_operator/readiness_probe.py validate \
  --run-token "$PROBE_TOKEN" --node-name "$ADMITTED_NODE" --pod-uid "$CAPTURED_UID" \
  --pod-receipt completed-pod.json --log-file readiness.json --output validated.json
```

Success requires the captured UID/name/namespace/node/KSA/spec and running image
digest, zero restarts, exit 0, the guard's `COMPLETED` result, and the probe's
`METADATA_READY_ONLY` result: fixed database/user/private address, TLS, exact
eight migration names/checksums, all three indexes ready/valid, rollback true
and unchanged interpreter/source/supervisor. A close failure makes the frozen
probe return HOLD. Boolean/numeric substitutions, unexpected fields, another
image identity or schema drift are rejected, not silently normalized.

## Cleanup on every outcome

Prepare the UID-fenced cleanup request even if the probe or validation fails:

```sh
python backend/scripts/jobstore_operator/readiness_probe.py cleanup \
  --run-token "$PROBE_TOKEN" --pod-uid "$CAPTURED_UID" --output cleanup-request.json
```

The request contains the sole permitted API path and a `DeleteOptions` body with
the captured UID precondition, foreground propagation and 15-second grace.
Release sends precisely that body to that path using the reviewed context
(for example `kubectl delete --raw PATH -f DELETE_OPTIONS_FILE` after extracting
the generated body). No selector, name-pattern, unconditioned delete, force,
grace-zero or finalizer change is allowed. On an uncertain create, establish
the exact token/spec/UID before using this request; report custody uncertainty
instead of deleting an unrelated object.

After deletion, require NotFound for the exact name/UID and confirmation that
the bound node remained healthy through cleanup. A successful DELETE response
alone does not prove the process ended. Name reuse, unreachable API/node,
timeout or unfinished termination leaves cleanup UNVERIFIED and blocks another
attempt. Retain the receipt and ownership until resolved. No server, watcher,
Pod or temporary file created by this attempt may be abandoned.

The local acceptance result is deliberately `READINESS_PROBE_ONLY_CLEANUP_PENDING`. Only Release's
separate verified absence receipt can close that step. Even complete probe
success proves only this image/identity/session. Later persistent placement
needs its own readiness and retained-state first-install/fencing acceptance.
No state adoption, copy, index serving, schema grant, authority flip or savings
claim follows. Fleet writer/deletion coverage, erasure reserves, privacy/restore,
cohort and absolute operating limits remain separate gates.
# Source and failure receipt details

The runner explicitly requests all nonignored untracked files from Git, so a local or global `status.showUntrackedFiles=no` setting cannot hide them. SQL-stage failures, including rollback and close failures, emit the same bounded HOLD fields as pre-SQL failures; successful metadata receipts retain their exact schema.

Native source qualification uses the probe's shared environment values, captures stdout separately from stderr, and requires stdout to contain exactly one JSON proof. Additional stdout is refused rather than discarded. Missing or malformed runner hashes refuse in preflight, qualification and publication.
