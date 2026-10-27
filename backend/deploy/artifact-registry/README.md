# Source-deploy registry cleanup proposal (dry run only)

Owner: release operator. Deletion decisions belong to David.

`scripts/registry_cleanup_dry_run.py` renders a **local proposal**, with
`cleanupPolicyDryRun: true`. It never calls Google Cloud, installs a policy,
changes an existing policy, deletes images, or changes scanning. There is no
active-mode argument. A merged change to this file has no runtime effect.

Scope is only `based-hardware/us-central1/cloud-run-source-deploy`, and the
delete condition is further limited to package prefix `omi/omi`, older than
30 days. The live Japan subscription repository is outside this scope, as
are GCR, staging, Deepgram, Functions, and build-source buckets.

Retention is the union of 100 most recent versions **per package**, release
tags (`release*`, `v*`, `stable*`, `prod*`, `latest*`), and an explicit full
digest inventory. Keep policies override delete policies. The source build
package uses source-SHA tags, so an untagged-only delete policy would leave
most of that history in place. Preserve every other named tag by adding its
digest to the protected inventory; source-SHA tags are not automatically releases.

Before producing that inventory, enumerate both prod and dev references to
both projects' images: every retained Cloud Run revision, every service and
Job template, retained Job executions in the 30-day rollback window, GKE
Pods (including image IDs, init and ephemeral containers), Deployments,
ReplicaSets, StatefulSets, DaemonSets, ReplicationControllers, Jobs and CronJobs.
Include scale-zero controllers, all containers, and referenced parent/child
OCI manifests. Resolve mutable tags against the registry, and hold a whole
package when a runtime or rollback tag cannot be resolved. Protect rollback
receipts from the last 30 days, mapping source commits to image tags where
necessary. A count limit alone cannot protect an old deployed image.

Input example (digest is illustrative; use a fresh, complete inventory):

```json
{
  "repository": "projects/based-hardware/locations/us-central1/repositories/cloud-run-source-deploy",
  "observed_at": "2026-10-27T04:00:00Z",
  "protected_digests": ["sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
  "coverage": {
    "cloud_run_revisions": true,
    "gke_workloads_both_projects": false,
    "cloud_run_jobs": true,
    "rollback_receipts_30d": false
  }
}
```

Render from `backend/`:

```bash
python scripts/registry_cleanup_dry_run.py /path/to/protected-snapshot.json > /path/to/proposal.json
```

Missing/false coverage adds a repository-wide `KEEP ANY` hold, so incomplete
evidence proposes no deletion candidates. Stale (>24h), future, empty-digest,
or out-of-scope inputs are rejected. The booleans are operator attestations,
not evidence that this renderer has independently collected or verified coverage.

No policy installation is authorized by this proposal. Before separately
approved installation, resolve coverage gaps, preserve current policy state,
review tag naming, validate Docker digest version matching and API payload
limits, and verify the target has no competing policy changes. If approved,
install only in dry-run mode; inspect `validateOnly=true` results after at
least one full daily cleanup interval. Do not enable DATA_WRITE audit logs
without approval for that access change. Removing the proposal or restoring
the prior policy reverses a dry-run installation. Deletion has no rollback.

Never derive savings by summing image sizes: Docker layers are shared.
Attribute settled storage billing and measure bytes no longer referenced by
any retained manifest. Registry cleanup does not stop CI cache downloads,
retroactively refund image scans, or reduce build CPU usage.

References: [cleanup policy semantics and dry runs](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy),
[Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing).
