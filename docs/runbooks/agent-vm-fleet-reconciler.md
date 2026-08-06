# Agent VM fleet reconciler

The Agent VM fleet is converged by an immutable release manifest and a
five-minute Cloud Run Job. A desktop-backend deploy publishes the image by
digest and a content-addressed startup artifact, verifies the new backend
revision, then advances `agent-vm/releases/active.json`. The active pointer is
the only mutable release object; the previous accepted pointer is retained for
operator rollback. The legacy `startup.sh` compatibility object is not updated
before acceptance, so an unaccepted candidate cannot escape the staged gate.

## Lifecycle

1. The reconciler reads the active manifest and takes an environment-wide
   Firestore lease. Each owner is then claimed with the `{vmName, authToken}`
   deletion/owner fence.
2. Provider drift includes a missing dedicated service account, startup
   metadata, release identity, image digest, or runtime health identity.
3. A drifted running VM is marked `draining`. Agent Proxy rejects new sessions
   and existing sessions retain a 90-second renewable lease. A VM is stopped
   only after the lease set is empty; stopped VMs are prepared without booting,
   then started and verified against `/health` with the owner token over the
   private VM network. The reconciler job must use direct VPC egress to the
   Agent VM subnet and set `AGENT_VM_TRUSTED_HEALTH_CHANNEL=private-vpc`; it
   refuses to send the bearer token over a NAT address. A healthy
   stopped VM with no drift remains stopped so idle self-stop is preserved.
4. A provider-confirmed missing VM is recorded with `missingSince`. The
   reconciler selects that terminal record independently of the rollout cohort
   and deletes only its Firestore `agentVm` pointer after the configured grace
   period, zero active session leases, no queued start/drain demand, and a
   final account-deletion, `{vmName, zone, authToken}`, ready/stopped creation
   outcome, owner-lease, and `missingSince` compare-and-swap all succeed. It
   never creates a replacement;
   the normal account provisioning path owns replacement creation. Development
   uses a five-minute grace to exercise this exact cleanup path after each
   merged auto-deploy. Production uses the same code with a 24-hour grace.
5. Success records the observed release and clears the lease/drain fields by
   compare-and-swap. Three successful five-minute runs advance the rollout
   gate from sentinel (1%) to canary (5%), quarter (25%), and remainder (100%).
   Three failures quarantine that owner and stop it from being retried until an
   operator changes the release or clears the state.

Legacy VMs with absent metadata are ordinary drift and are repaired on their
first selected reconciliation. A missing GCE instance is recorded as `missing`
before it becomes eligible for the fenced terminal-cleanup path. The
reconciler never creates a replacement without the account request path's
owner claim.

If the immutable `bootImage` differs from the actual boot disk source, the
reconciler records `recreate_required` and does not stop, replace, or start the
VM. An operator must recreate that dev/prod VM through the owner provisioning
path with the exact image reference before the fleet can converge.

## Development-only boot-image replacement

Ordinary release rollout is never permission to replace a VM. A manifest may
carry a separate `bootImageMigration` object only for a deliberately selected
development owner:

```json
{
  "bootImageMigration": {
    "enabled": true,
    "allowedUids": ["development-only-owner"],
    "maxConcurrency": 1,
    "soakSeconds": 600
  }
}
```

The job rejects this object outside development, requires a non-empty explicit
allowlist, and only considers an already stopped owner with no session/start or
drain demand. It journals a deterministic replacement candidate, verifies its
private authenticated health and release identity, then atomically cuts the
owner pointer over. The predecessor remains stopped and labelled during the
soak window, then the same migration journal deletes it only after its numeric
instance ID, label, active pointer, account-deletion, and lease fences still
match. Candidate health retries reuse the journaled name and bearer token; a
candidate that exhausts the normal retry budget is identity-fenced deleted
before the owner record is quarantined. Production replacement is hard-disabled
in code.

Generate the opt-in manifest with the checked-in renderer; do not hand-edit a
manifest after it receives `manifestSha256`:

```bash
python3 backend/scripts/agent_vm_release.py \
  --output /tmp/agent-vm-migration.json \
  --environment development \
  --source-sha "$SOURCE_SHA" --image-digest "$IMAGE_DIGEST" \
  --startup-uri "$STARTUP_URI" --startup-sha256 "$STARTUP_SHA256" \
  --boot-image "$BOOT_IMAGE" --service-account "$SERVICE_ACCOUNT" \
  --boot-image-migration-allowed-uid development-only-owner \
  --boot-image-migration-soak-seconds 600
```

Activate it only with the checked-in dev-only, generation-guarded control:

```bash
AGENT_VM_MIGRATION_APPLY=1 \
  AGENT_VM_MIGRATION_PROJECT=based-hardware-dev \
  AGENT_VM_MIGRATION_BUCKET=based-hardware-dev-agent \
  AGENT_VM_MIGRATION_MANIFEST=/tmp/agent-vm-migration.json \
  bash backend/scripts/activate-agent-vm-dev-migration.sh
```

It refuses any other project, uploads a content-addressed immutable artifact,
uses the current active-pointer generation for the compare-and-swap, and reads
the activated generation back byte-for-byte. The next normal release manifest
omits this flag, so migration cannot persist accidentally.

## Installation order

Deploy Agent Proxy with session leases first. Before the desktop-backend
deployment, provision the dedicated job identity and grant the environment's
CI deploy service account permission to attach exactly that identity to the
Cloud Run Job. The helper refuses to infer the deployer or grant project-wide
Service Account User:

```bash
AGENT_VM_RECONCILER_IAM_APPLY=1 \
AGENT_VM_RECONCILER_PROJECT=based-hardware-dev \
AGENT_VM_RECONCILER_BUCKET=based-hardware-dev-agent \
AGENT_VM_RECONCILER_DEPLOYER=local-development-joan@based-hardware-dev.iam.gserviceaccount.com \
bash backend/scripts/apply-agent-vm-reconciler-iam.sh
```

Use the corresponding CI deploy service account and bucket in each environment.
Then deploy the desktop backend (which creates or updates the Job), and install
the Scheduler trigger only after the Agent Proxy lease check succeeds:

```bash
AGENT_VM_RECONCILER_SCHEDULER_APPLY=1 \
AGENT_VM_RECONCILER_PROXY_LEASES_READY=1 \
AGENT_VM_RECONCILER_PROJECT=based-hardware-dev \
AGENT_VM_RECONCILER_SCHEDULER_SA=agent-vm-reconciler-scheduler@based-hardware-dev.iam.gserviceaccount.com \
bash backend/scripts/apply-agent-vm-reconciler-scheduler.sh
```

Repeat for `based-hardware`. The scheduler identity must be allowed to invoke
the Cloud Run Job. The scheduler helper creates the scheduler service account
when absent and grants it `roles/run.invoker` on the named Cloud Run Job. The
job identity is provisioned per environment with
`backend/scripts/apply-agent-vm-reconciler-iam.sh`; it receives Firestore
read/write, bucket object-read, and condition-scoped Agent VM Compute lifecycle
permissions. The CI deploy identity receives `roles/iam.serviceAccountUser`
only on that reconciler identity, so it can deploy the Job without being able
to attach unrelated service accounts. The reconciler job uses its attached
identity and Application Default Credentials; it does not mount the desktop
backend's Firebase key.
Replacement additionally preserves the default Agent VM subnet and its
external NAT, so the installer creates a two-permission subnet role and binds
it directly to that exact regional subnet. Because the replacement request
also names the VPC network, the installer creates a separate one-permission
network role bound directly to the default network; it does not grant
project-wide network access.
Validate the installed trigger with
`backend/scripts/validate_agent_vm_reconciler_scheduler.py` before the first
live execution.

After both environments have broker-capable startup artifacts and a successful
reconciliation sample, revoke the transitional direct VM stop permission:

```bash
AGENT_VM_BOOTSTRAP_IAM_REVOKE=1 bash backend/scripts/revoke-agent-vm-bootstrap-stop.sh
```

The guest no longer calls Compute directly. It presents a full-format,
audience-bound Compute Engine identity token to `/v2/agent/vm/stop-self`; the
backend verifies the project, zone, instance name, runtime service account, and
current Firestore owner before issuing the exact stop operation.

## Recovery

`retry` uses bounded exponential backoff. `deferred` means an active session
is still present and retains the drain fence. `cleanup_pending` means a
provider-confirmed missing VM is inside its grace period; it is an expected
successful job outcome, not a rollout failure. A missing VM with active demand
or a live session remains visible and fails closed rather than being deleted.
The reconciler consumes an observed start request only after it receives the
provider 404 for that exact owner generation; the transactional timestamp fence
preserves a newer request. That makes the impossible request terminal rather
than leaving an uncleanable missing pointer.
`quarantined` requires operator inspection of the per-owner
`agentVm.reconcile.lastError` and a new release or explicit state repair. The
terminal reaper remains a separate, dry-run-first cleanup backstop for
abandoned terminated instances.

To roll the fleet back to the previous accepted release, inspect the active
and previous manifests, then run the refuse-by-default helper in the target
environment:

```bash
AGENT_VM_RELEASE_ROLLBACK=1 \
AGENT_VM_RECONCILER_BUCKET=based-hardware-dev-agent \
bash backend/scripts/rollback-agent-vm-release.sh
```

The next scheduled run reads `active.json` and converges selected owners back
to that release. A deployment workflow also restores the prior pointer if
post-activation promotion or verification fails.
