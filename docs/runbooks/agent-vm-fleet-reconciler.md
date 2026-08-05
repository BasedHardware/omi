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
4. Success records the observed release and clears the lease/drain fields by
   compare-and-swap. Three successful five-minute runs advance the rollout
   gate from sentinel (1%) to canary (5%), quarter (25%), and remainder (100%).
   Three failures quarantine that owner and stop it from being retried until an
   operator changes the release or clears the state.

Legacy VMs with absent metadata are ordinary drift and are repaired on their
first selected reconciliation. A missing GCE instance is recorded as `missing`
and is left for the existing provisioning/reaper recovery path; the reconciler
never creates a replacement without the account request path's owner claim.

If the immutable `bootImage` differs from the actual boot disk source, the
reconciler records `recreate_required` and does not stop, replace, or start the
VM. An operator must recreate that dev/prod VM through the owner provisioning
path with the exact image reference before the fleet can converge.

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
is still present and retains the drain fence. `quarantined` requires operator
inspection of the per-owner `agentVm.reconcile.lastError` and a new release or
explicit state repair. The terminal reaper remains a separate, dry-run-first
cleanup backstop for abandoned terminated instances.

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
