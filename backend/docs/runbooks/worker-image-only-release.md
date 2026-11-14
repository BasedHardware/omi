# Preserve-live GPU worker releases

Use the canonical `Deploy Diarizer to GKE` workflow's opt-in
`preserve_live_worker=true` mode when a release admits an image move while
requiring the live runtime configuration to remain intact. The default remains
the existing Helm deployment. This mode targets only
`prod-omi-backend/prod-omi-batch-pipeline-worker`, container `worker`, strategy
`Recreate`. It never renders chart values, touches Helm Secrets, modifies
repair policy, or rolls sibling consumers.

This mode does not grant release or activation authority. Keep the existing
merged-source, immutable-image/tree, index-readiness, eligibility, hold,
prod-train lock, environment approval and own-run approval controls. The workflow
retains its existing environment and concurrency controls; external Release
admission/approval controls remain external. Do not dispatch while held or
approve your own run. SCA-2149 repairs the preservation mechanism; SCA-1841
separately owns lever activation. No lever map is installed by this mode.

## Prepare the existing release packet

After the tooling PR is independently reviewed at its final head, passes CI and
is merged, use the helper **from that merged workflow revision**, with existing
read-only production access and the correct GKE context:

```bash
python3 .github/scripts/worker_image_only.py inventory > worker-baseline.json
```

The inventory emits only target UID/image/spec hash and shared-image consumer
bindings, never environment values or a private Deployment snapshot. It reads
Deployments, StatefulSets, DaemonSets, Jobs and CronJobs in the named namespace,
including init containers and suspended record-seal jobs. No new permissions
are installed: unavailable reads fail closed. Review the inventory against the
release packet, including `record-seal-worker`, repair/sweeper CronJobs and any
T4/Spot/borrowed-pool siblings that exist. Record-seal image/config/source and
repair-flags verification remain part of the existing consumer gates; retaining
a sibling binding is not proof that the sibling runs the new source.

All discovered sibling templates must remain on their admitted identities,
images and spec hashes. The worker alone moves. An active T4 fallback or required
companion must already have the candidate image or this mode refuses before the
write; a release requiring a joint roll needs a separately admitted carrier.
Job creation/deletion, autoscaling or a config change may invalidate the packet;
refresh and re-admit it instead of retrying blindly. The namespace inventory is
not a claim about consumers in other namespaces or systems: reconcile those in
the existing shared-artifact release gate before dispatch.

For a qualified, already-built worker digest, Release dispatches once:

```bash
gh workflow run gcp_diarizer.yml --ref main \
  -f environment=prod -f service=batch-pipeline-worker \
  -f branch="$MERGED_SOURCE_SHA" -f image_digest="$QUALIFIED_WORKER_DIGEST" \
  -F preserve_live_worker=true \
  -f worker_live_baseline="$(cat worker-baseline.json)"
```

The full source SHA must be merged on main. A digest promotion still checks the
image's source tree against that source. Omitting `image_digest` uses the existing
build/smoke/push path for that exact source. The preservation helper itself is
checked out at `github.workflow_sha`, so the product source may predate this mode.

The helper compares the admitted baseline, prints the safe image patch and
rollback identity, checks the server dry-run for admission changes, rechecks sibling bindings, and submits one JSON Patch with
UID, resourceVersion and prior-image tests. A concurrent target write fails
atomically. Only the worker container image is replaced; all other spec fields,
including env/valueFrom, replicas, strategy, volumes, resources and scheduling,
remain intact. API admission that changes the expected spec fails verification;
the workflow never attempts an automatic corrective write or second restart.
Sibling reads and the target patch are not a multi-object transaction: existing
prod-train serialization remains necessary, and post-roll verification also
refuses sibling drift. The workflow waits for the existing rollout/status gates,
then compares the target spec hash and all sibling bindings again.

## Verification and rollback custody

The workflow logs and step summary contain the safe JSON image diff and rollback
receipt. Retain the `rollback` object as `worker-image-receipt.json` in the
existing release packet, even if rollout fails. This contains only images, UIDs
and hashes; do not export full runtime snapshots. A successful mechanical roll
does not clear canary gates. Release still performs the previously approved
`repair-flags-apply.sh` reapply and drain/record-seal/source/consumer verification
in the existing order. This mode supplies no new repair flags or policy.

A rollback uses the **same canonical workflow and writer** as a forward release.
After Release admits rollback under the existing hold/eligibility/approval rules,
capture a fresh inventory and dispatch the recorded prior digest with its full
merged source SHA and the saved receipt:

```bash
python3 .github/scripts/worker_image_only.py inventory > worker-rollback-baseline.json
gh workflow run gcp_diarizer.yml --ref main \
  -f environment=prod -f service=batch-pipeline-worker \
  -f branch="$PRIOR_MERGED_SOURCE_SHA" -f image_digest="$RECORDED_PRIOR_DIGEST" \
  -F preserve_live_worker=true \
  -f worker_live_baseline="$(cat worker-rollback-baseline.json)" \
  -f worker_rollback_receipt="$(cat worker-image-receipt.json)"
```

Both directions mechanically require source ancestry at or above
`f3902ec5435809d95ac7c15f6be7e9f056564d3d`. Rollback also requires an explicit
digest and full merged source SHA, and the existing image-tree check binds that
digest to the admitted source. It enters the same prod environment approval,
prod-train concurrency group, index gate, server dry-run, consumer checks,
CAS writer and rollout verifier. Rollback rejects `break_glass_lock=true`.
The prior digest must equal the saved receipt, the current baseline must equal
its `after` identity, and the resulting spec
must equal its `before` identity. The standalone reverse-patch command has been
removed; there is no documented direct `kubectl patch` write path.

The writer uses a freshly read resourceVersion so ordinary rollout status
updates do not invalidate the receipt. If runtime config has changed,
stop for owner reconciliation; do not overwrite it with an old full snapshot.
There is no automatic rollback, bypass or rollback below the release's source
floor. Helm history is unchanged; future chart deployments still require their
own config-diff admission and must not accidentally restore chart defaults.

Offline verification:

```bash
python3 .github/scripts/test_worker_image_only.py
actionlint .github/workflows/gcp_diarizer.yml
make preflight
```

The fake Kubernetes API exercises real JSON Patch preconditions, preservation,
consumer refusal and exact reverse-image behavior. Workflow tests exercise input
scope validation and assert success-only ordering/control bindings. They do not
simulate GitHub environment approvals, external holds or paid runtime behavior.
