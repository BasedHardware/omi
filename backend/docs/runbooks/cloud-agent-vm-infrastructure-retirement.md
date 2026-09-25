# Cloud Agent VM infrastructure retirement

Last reviewed: 2026-08-19

This runbook retires the production infrastructure left behind after PR #11795
removed the Cloud Agent VM control-plane source. It is an operator procedure;
merging this document does not change production.

## Why this runbook exists

The source tree and the live infrastructure diverged. PR #11795 deleted the
Agent VM guest, proxy, reconciler, reaper, firewall charts, and deploy workflows,
but the previously installed GKE release continued running its old image.

The incident evidence supplied on 2026-08-19 showed:

- 52 surviving `omi-agent-*` instances and 56 disks (2,800 GB);
- 24 starts and 82 resets in 24 hours, with no inserts, stops, or deletes;
- 20 RUNNING instances, up from 7 approximately 18 hours earlier;
- a 2/2 `prod-omi-agent-proxy` Deployment still exposing
  `wss://agent.omi.me/v1/agent/ws`;
- all observed starts/resets attributed to the JSON-key principal used by that
  Deployment and to `python-httpx/0.28.0`;
- a Cloud Run `agent-vm-reconciler` job that exists but has never executed; and
- a deleted release-artifact bucket, so a reset VM cannot download its pinned
  startup artifact.

Repository review agrees with the mechanism but not with calling sole-source
attribution proved. Historical revision `874d796552` posts directly to the GCE
`start` and `reset` endpoints, and current `main` has no start/reset call for
this fleet. The remaining
`backend/services/users/agent_vm_account_cleanup.py` path performs fenced
deletes only. However, an external copy of the same JSON key or an uninspected
Scheduler target could produce indistinguishable audit entries. The quiet-period
test below closes that gap before credentials are revoked.

The missing bucket is a strong explanation for failed guest health, not yet a
proved root cause for every VM. The retired provisioner installed a startup
wrapper that downloads the pinned startup script from GCS and exits on download
failure. Proving it for a survivor requires inspecting that instance's metadata
and serial-port output without exposing its name or user identity.

## Safety and data-retention boundary

Run these commands from a private operator shell. Do not paste instance lists,
Firebase UIDs, decoded Kubernetes Secrets, or command output containing either
into issues, PRs, or chat. The commands below write resource names only to an
owner-readable temporary directory.

Stopping an instance is reversible and preserves its disks. Deleting an
instance or disk is irreversible unless a separately retained snapshot/export
exists. The disks contain plaintext user workspace data. Do not snapshot,
export, or delete them until the data owner has made an explicit retention and
user-export decision; snapshots preserve both the privacy exposure and storage
cost.

Use Bash, `jq`, `gcloud`, `kubectl`, and `helm`:

```bash
set -euo pipefail
umask 077

export PROJECT_ID="based-hardware"
export REGION="us-central1"
export CLUSTER="prod-omi-gke"
export NAMESPACE="prod-omi-backend"
export PROXY_RELEASE="prod-omi-agent-proxy"
export PROXY_RESOURCE="prod-omi-agent-proxy"
export SCHEDULER_JOB="agent-vm-reconciler-5m"
export RECONCILER_JOB="agent-vm-reconciler"

INCIDENT_DIR="$(mktemp -d /tmp/omi-agent-retirement.XXXXXX)"
export INCIDENT_DIR
gcloud container clusters get-credentials "$CLUSTER" \
  --region="$REGION" --project="$PROJECT_ID"
kubectl config current-context
```

`get-credentials` changes only the operator's local kubeconfig. Confirm the
printed context is the production cluster before continuing.

## Phase 0: capture rollback evidence

These commands are read-only against production. They intentionally do not
read the credential Secret payload.

```bash
helm -n "$NAMESPACE" get all "$PROXY_RELEASE" \
  > "$INCIDENT_DIR/proxy-helm-all.txt"
helm -n "$NAMESPACE" get values "$PROXY_RELEASE" -o yaml \
  > "$INCIDENT_DIR/proxy-values.yaml"
helm -n "$NAMESPACE" history "$PROXY_RELEASE" -o json \
  > "$INCIDENT_DIR/proxy-history.json"
kubectl -n "$NAMESPACE" get horizontalpodautoscaler "$PROXY_RESOURCE" -o yaml \
  > "$INCIDENT_DIR/proxy-hpa.yaml"

gcloud compute instances list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" \
  --format="csv[no-heading](zone.basename(),name,status)" \
  > "$INCIDENT_DIR/instances-before.csv"
gcloud compute disks list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" \
  --format="csv[no-heading](zone.basename(),name,status,sizeGb)" \
  > "$INCIDENT_DIR/disks-before.csv"

gcloud run jobs describe "$RECONCILER_JOB" --region="$REGION" \
  --project="$PROJECT_ID" --format=export \
  > "$INCIDENT_DIR/reconciler-job.yaml"
gcloud compute firewall-rules describe allow-omi-agent-vm-8080 \
  --project="$PROJECT_ID" --format=json \
  > "$INCIDENT_DIR/firewall-before.json"
gcloud compute addresses describe prod-agent-proxy-ip-address --global \
  --project="$PROJECT_ID" --format=json \
  > "$INCIDENT_DIR/proxy-address-before.json"
if kubectl -n "$NAMESPACE" get managedcertificate agent-proxy-cert \
  -o yaml > "$INCIDENT_DIR/proxy-certificate.yaml" 2>/dev/null; then
  echo "Captured managed certificate"
else
  : > "$INCIDENT_DIR/proxy-certificate.absent"
fi
```

Blast radius: none in production; the local files contain sensitive resource
identifiers and must remain private. Verification:

```bash
jq -s 'group_by(.[2]) | map({status: .[0][2], count: length})' \
  <(jq -R 'split(",")' "$INCIDENT_DIR/instances-before.csv")
wc -l < "$INCIDENT_DIR/instances-before.csv"
wc -l < "$INCIDENT_DIR/disks-before.csv"
```

Do not display either CSV. The expected inventory at incident time is 52
instances and 56 disks.

Cloud Scheduler is unverified. A permission error is not evidence that the job
is absent:

```bash
if scheduler_json="$(gcloud scheduler jobs describe "$SCHEDULER_JOB" \
  --location="$REGION" --project="$PROJECT_ID" --format=json \
  2> "$INCIDENT_DIR/scheduler-describe.err")"; then
  printf '%s\n' "$scheduler_json" > "$INCIDENT_DIR/scheduler-before.json"
  jq '{name, state, schedule, timeZone, targetType:
      (if .httpTarget then "http" elif .pubsubTarget then "pubsub" else "appEngine" end)}' \
    "$INCIDENT_DIR/scheduler-before.json"
elif grep -q 'NOT_FOUND' "$INCIDENT_DIR/scheduler-describe.err"; then
  printf '%s\n' '{"state":"ABSENT"}' > "$INCIDENT_DIR/scheduler-before.json"
  echo "Scheduler job is absent"
else
  printf '%s\n' '{"state":"UNKNOWN"}' > "$INCIDENT_DIR/scheduler-before.json"
  echo "WARNING: Scheduler remains unverified; assign jobs.get/pause to the incident operator" >&2
fi
unset scheduler_json
```

## Phase 1: stop the bleeding now

### 1. Pause the Scheduler target

If the captured job state is `ENABLED`, pause it:

```bash
SCHEDULER_STATE="$(jq -r '.state' "$INCIDENT_DIR/scheduler-before.json")"
if [[ "$SCHEDULER_STATE" == "ENABLED" ]]; then
  gcloud scheduler jobs pause "$SCHEDULER_JOB" --location="$REGION" \
    --project="$PROJECT_ID" --quiet
fi
if [[ "$SCHEDULER_STATE" != "ABSENT" ]]; then
  gcloud scheduler jobs describe "$SCHEDULER_JOB" --location="$REGION" \
    --project="$PROJECT_ID" --format='value(state)'
fi
unset SCHEDULER_STATE
```

Effect and blast radius: prevents future invocations of this one reconciler
schedule; it does not interrupt a currently running execution. Expected state:
`PAUSED`. Rollback:

```bash
gcloud scheduler jobs resume "$SCHEDULER_JOB" --location="$REGION" \
  --project="$PROJECT_ID" --quiet
```

Do not resume it during retirement. Its source is gone and the production job
has no proven cleanup execution. If the captured state is `UNKNOWN`, proceed to
the proxy kill switch below, but have an authorized operator inspect and pause
the Scheduler in parallel; do not interpret the permission failure as absence.

### 2. Remove the HPA, then scale the proxy to zero

Deleting the HPA first matters: its minimum of two replicas can undo a manual
Deployment scale-down.

```bash
CUTOVER_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export CUTOVER_UTC

kubectl -n "$NAMESPACE" delete horizontalpodautoscaler "$PROXY_RESOURCE"
kubectl -n "$NAMESPACE" scale deployment "$PROXY_RESOURCE" --replicas=0

kubectl -n "$NAMESPACE" get deployment "$PROXY_RESOURCE" -o json | \
  jq '{desired: .spec.replicas,
       ready: (.status.readyReplicas // 0),
       available: (.status.availableReplicas // 0)}'
kubectl -n "$NAMESPACE" get pods \
  -l "app.kubernetes.io/instance=$PROXY_RELEASE" -o json | \
  jq '{pods: (.items | length), running:
       ([.items[] | select(.status.phase == "Running")] | length)}'
```

Effect and blast radius: no new proxy connection can issue a VM start/reset.
Kubernetes sends `SIGTERM` to both pods; open WebSockets close during the pod
termination grace period and old clients retry. While the Service/Ingress
remain, retries receive an unavailable-backend response. There is no healthy
cloud session to drain, so keeping a pod alive would prolong the leak without
preserving a working session.

Expected verification: desired, ready, available, pods, and running converge
to zero. If any replica returns, find the controller that recreated the HPA or
Deployment before proceeding.

Rollback (reintroduces the start/reset leak and is not a functional service
rollback while the release bucket is absent):

```bash
kubectl -n "$NAMESPACE" scale deployment "$PROXY_RESOURCE" --replicas=2
kubectl apply -f "$INCIDENT_DIR/proxy-hpa.yaml"
```

### 3. Stop every surviving fleet instance

Nothing left in `main` will do this. Use the private inventory captured before
cutover and submit all stops asynchronously:

```bash
while IFS=, read -r zone instance_name status; do
  if [[ "$status" == "RUNNING" ]]; then
    gcloud compute instances stop "$instance_name" --zone="$zone" \
      --project="$PROJECT_ID" --async --quiet --format=none
  fi
done < "$INCIDENT_DIR/instances-before.csv"
```

Effect and blast radius: stops the 52 inventoried cloud Agent VMs. Open guest
processes end; persistent disks and plaintext workspace data remain. This is
reversible and is the immediate compute-cost stop.

Poll aggregate state without printing instance names:

```bash
while true; do
  fleet_json="$(gcloud compute instances list --project="$PROJECT_ID" \
    --filter="name~'^omi-agent-'" --format=json)"
  echo "$fleet_json" | jq \
    'group_by(.status) | map({status: .[0].status, count: length})'
  [[ "$(echo "$fleet_json" | jq '[.[] | select(.status != "TERMINATED")] | length')" == 0 ]] && break
  sleep 15
done
unset fleet_json
```

Rollback is a per-instance `gcloud compute instances start` using the private
inventory. Do not do that unless the proxy, release artifacts, and guest health
contract have first been restored; otherwise it recreates the same cost leak.

### 4. Prove attribution and steady state

Allow Cloud Audit Logs to ingest, then query from the cutover timestamp. The
query emits counts only, never resource names:

```bash
sleep 300
LOG_FILTER="resource.type=\"gce_instance\" AND
  (protoPayload.methodName=\"v1.compute.instances.start\" OR
   protoPayload.methodName=\"v1.compute.instances.reset\") AND
  timestamp>=\"$CUTOVER_UTC\""
gcloud logging read "$LOG_FILTER" --project="$PROJECT_ID" --format=json | jq \
  'group_by(.protoPayload.methodName) |
   map({method: .[0].protoPayload.methodName, count: length})'
unset LOG_FILTER
```

Repeat after 60 minutes, longer than the observed approximately four resets per
hour. Expected result: `[]`, and the aggregate fleet state remains 52
`TERMINATED` instances. Any start/reset after `CUTOVER_UTC` disproves sole-source
attribution. Do not revoke the key or delete the proxy evidence until the new
caller is identified by principal, caller IP, and user agent.

## Phase 2: remove the last live serving path

### 5. Uninstall the Helm release, preserving rollback history

Do this after Phase 1 is stable:

```bash
HELM_REVISION="$(jq -r 'max_by(.revision | tonumber).revision' \
  "$INCIDENT_DIR/proxy-history.json")"
export HELM_REVISION
helm -n "$NAMESPACE" uninstall "$PROXY_RELEASE" --keep-history --wait

for kind in deployment service ingress horizontalpodautoscaler serviceaccount; do
  if kubectl -n "$NAMESPACE" get "$kind" "$PROXY_RESOURCE" >/dev/null 2>&1; then
    echo "ERROR: $kind still exists" >&2
    exit 1
  fi
done
```

Effect and blast radius: deletes the proxy's Deployment, Service, Ingress,
BackendConfig-related chart objects, HPA, and KSA. The Ingress load balancer can
take minutes to release. It does not delete the separately created credential
Secret or any VM. Rollback is:

```bash
helm -n "$NAMESPACE" rollback "$PROXY_RELEASE" "$HELM_REVISION" --wait
```

That rollback recreates a minimum of two pods and therefore reopens the leak;
use it only as an explicit incident rollback. The deleted GCS artifacts mean it
cannot by itself restore healthy guest sessions.

### 6. Remove DNS after the Ingress is gone

DNS is not the kill switch: cached answers would continue reaching the Ingress,
and DNS rollback is TTL-delayed. Removing it after the workloads and Ingress
are gone gives the fast Kubernetes rollback boundary first and then retires the
public name.

```bash
DNS_ZONE="$(gcloud dns managed-zones list --project="$PROJECT_ID" \
  --filter='dnsName=omi.me.' --format='value(name)' --limit=1)"
export DNS_ZONE
test -n "$DNS_ZONE"
gcloud dns record-sets describe agent.omi.me. --type=A --zone="$DNS_ZONE" \
  --project="$PROJECT_ID" --format=json > "$INCIDENT_DIR/agent-dns-before.json"

gcloud dns record-sets delete agent.omi.me. --type=A --zone="$DNS_ZONE" \
  --project="$PROJECT_ID" --quiet
gcloud dns record-sets list --zone="$DNS_ZONE" --project="$PROJECT_ID" \
  --filter='name=agent.omi.me.' --format=json | jq 'length'
```

Effect and blast radius: new DNS lookups for the retired proxy hostname return
no A record after caches expire. Existing cached clients only reach the already
empty/deleted Ingress. Expected count: zero.

Rollback recreates the exact captured record; propagation is not immediate:

```bash
DNS_TTL="$(jq -r '.ttl' "$INCIDENT_DIR/agent-dns-before.json")"
DNS_RRDATA="$(jq -r '.rrdatas | join(",")' \
  "$INCIDENT_DIR/agent-dns-before.json")"
gcloud dns record-sets create agent.omi.me. --type=A --zone="$DNS_ZONE" \
  --project="$PROJECT_ID" --ttl="$DNS_TTL" --rrdatas="$DNS_RRDATA"
unset DNS_TTL DNS_RRDATA
```

## Phase 3: cleanup that can wait

### 7. Revoke the mounted JSON key and delete its unreferenced Secret

First prove no other Kubernetes workload refers to the Secret:

```bash
kubectl get deployments,statefulsets,daemonsets,jobs,cronjobs -A -o json | jq \
  '[.items[] as $workload |
    (($workload.spec.template.spec.volumes // [])[]? |
      select(.secret.secretName == "agent-proxy-gcp-credentials")) |
    {kind: $workload.kind, namespace: $workload.metadata.namespace,
     name: $workload.metadata.name}]'
```

Expected result after uninstall: `[]`. Then extract only the key identity into
shell variables, never print or persist the decoded credential, and revoke it:

```bash
KEY_ACCOUNT="$(kubectl -n "$NAMESPACE" get secret agent-proxy-gcp-credentials \
  -o jsonpath='{.data.google-credentials\.json}' |
  base64 --decode | jq -r '.client_email')"
KEY_ID="$(kubectl -n "$NAMESPACE" get secret agent-proxy-gcp-credentials \
  -o jsonpath='{.data.google-credentials\.json}' |
  base64 --decode | jq -r '.private_key_id')"
test -n "$KEY_ACCOUNT" && test -n "$KEY_ID"

gcloud iam service-accounts keys delete "$KEY_ID" \
  --iam-account="$KEY_ACCOUNT" --project="$PROJECT_ID" --quiet
kubectl -n "$NAMESPACE" delete secret agent-proxy-gcp-credentials
unset KEY_ACCOUNT KEY_ID
```

Effect and blast radius: every external copy of this exact private key stops
working, and the cluster copy is removed. Key deletion is **irreversible**; a
new key would be required for rollback. Do not delete the service account
itself merely because its key was mounted here—its name does not prove exclusive
ownership, and deleting a shared principal has a wider blast radius.

Verify the key is absent with `gcloud iam service-accounts keys list` using the
account identifier captured in a fresh secure shell. Do not print the key list
into incident artifacts.

### 8. Release the retired proxy address and certificate

After the DNS TTL and Helm rollback window have elapsed, verify the GKE Ingress
controller removed its forwarding rule, target proxy, URL map, backend service,
and NEG. Those generated names vary; inspect the load-balancer inventory rather
than deleting by a broad prefix. Then remove the separately reserved address
and managed certificate:

```bash
kubectl -n "$NAMESPACE" delete managedcertificate agent-proxy-cert \
  --ignore-not-found
gcloud compute addresses delete prod-agent-proxy-ip-address --global \
  --project="$PROJECT_ID" --quiet
```

Effect and blast radius: releases only the retired proxy's static public IP and
certificate declaration. The old IP can be allocated to another customer after
release, so restoring the same endpoint address is not guaranteed. Attempted
rollback, while the address is still available:

```bash
PROXY_IP="$(jq -r '.address' "$INCIDENT_DIR/proxy-address-before.json")"
gcloud compute addresses create prod-agent-proxy-ip-address --global \
  --project="$PROJECT_ID" --addresses="$PROXY_IP"
if [[ -s "$INCIDENT_DIR/proxy-certificate.yaml" ]]; then
  kubectl apply -f "$INCIDENT_DIR/proxy-certificate.yaml"
fi
unset PROXY_IP
```

Losing the exact address is irreversible if it has been reallocated. Do not
delete unrelated load-balancer resources based only on a name fragment.

### 9. Delete the dormant Scheduler and Cloud Run jobs

After the proxy and fleet have remained stopped:

```bash
SCHEDULER_STATE="$(jq -r '.state' "$INCIDENT_DIR/scheduler-before.json")"
if [[ "$SCHEDULER_STATE" != "ABSENT" && "$SCHEDULER_STATE" != "UNKNOWN" ]]; then
  gcloud scheduler jobs delete "$SCHEDULER_JOB" --location="$REGION" \
    --project="$PROJECT_ID" --quiet
fi
unset SCHEDULER_STATE
gcloud run jobs delete "$RECONCILER_JOB" --region="$REGION" \
  --project="$PROJECT_ID" --quiet
```

Effect and blast radius: removes only the never-proven reconciler trigger and
job. Scheduler deletion is reversible only by recreating its captured target
and schedule. Cloud Run rollback is possible while its referenced container
image remains:

```bash
gcloud run jobs replace "$INCIDENT_DIR/reconciler-job.yaml" \
  --region="$REGION" --project="$PROJECT_ID"
```

Do not execute the restored job: current source no longer contains it, and it
was never validated against production.

### 10. Decide retention, then delete the fleet and residual disks

This is the irreversible privacy boundary. Obtain the explicit export/retention
decision first. The safe options are:

1. keep the instances stopped for a time-bounded export window and accept disk
   cost/privacy exposure; or
2. export only specifically authorized user data, then delete; or
3. delete immediately if the data owner confirms no export obligation.

After approval, recapture the inventory to avoid acting on stale names, keep it
private, and delete the instances:

```bash
gcloud compute instances list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" \
  --format="csv[no-heading](zone.basename(),name)" \
  > "$INCIDENT_DIR/instances-approved-for-delete.csv"

while IFS=, read -r zone instance_name; do
  gcloud compute instances delete "$instance_name" --zone="$zone" \
    --project="$PROJECT_ID" --quiet --format=none
done < "$INCIDENT_DIR/instances-approved-for-delete.csv"

gcloud compute instances list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" --format=json | jq 'length'
```

Expected count: zero. This is **irreversible** without snapshots. Instance
deletion removes disks marked auto-delete, but not detached state/source clones
or legacy disks. Inventory the residual set and confirm it is detached before
deletion:

```bash
gcloud compute disks list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" --format=json | jq \
  '{count: length,
    attached: ([.[] | select((.users // []) | length > 0)] | length),
    totalGb: ([.[].sizeGb | tonumber] | add // 0)}'

gcloud compute disks list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" \
  --format="csv[no-heading](zone.basename(),name)" \
  > "$INCIDENT_DIR/disks-approved-for-delete.csv"

while IFS=, read -r zone disk_name; do
  gcloud compute disks delete "$disk_name" --zone="$zone" \
    --project="$PROJECT_ID" --quiet --format=none
done < "$INCIDENT_DIR/disks-approved-for-delete.csv"

gcloud compute disks list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" --format=json | jq 'length'
```

Proceed only if `attached` was zero and the approved disk count matches the
private inventory. Expected final count: zero. Disk deletion is
**irreversible** without snapshots.

The current account-deletion cleanup path must remain until both counts are
zero and the associated Firestore migration/late-cleanup records have been
handled. It may delete one user's fenced resources when that account is erased;
it is not a fleet sweeper and will not stop or delete the 52 survivors merely
because the proxy is gone.

### 11. Delete fleet-only firewall and images

Only after the instance and disk counts are zero:

```bash
gcloud compute firewall-rules delete allow-omi-agent-vm-8080 \
  --project="$PROJECT_ID" --quiet
gcloud compute images delete omi-agent-base-v2 omi-agent-base-v3 \
  --project="$PROJECT_ID" --quiet
```

Effect and blast radius: removes the legacy VM ingress rule and both boot
images. Image deletion is **irreversible** unless a separate image export
exists. The firewall rule can be recreated from
`$INCIDENT_DIR/firewall-before.json`, but no fleet remains to use it. Verify:

```bash
gcloud compute firewall-rules describe allow-omi-agent-vm-8080 \
  --project="$PROJECT_ID" >/dev/null 2>&1 && exit 1 || true
gcloud compute images list --project="$PROJECT_ID" \
  --filter="family=omi-agent" --format=json | jq 'length'
```

Expected image-family count: zero.

### 12. Remove dedicated Agent VM IAM identities

Only after the fleet is empty, inspect the bindings for the three dedicated
identities. Keep the proxy's mounted-key service account out of this list; it
may be shared and only its exact retired key was authorized for revocation.

```bash
for account_name in agent-vm-reconciler agent-vm-reaper omi-agent-vm-bootstrap; do
  account_email="${account_name}@${PROJECT_ID}.iam.gserviceaccount.com"
  gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten='bindings[].members' \
    --filter="bindings.members=serviceAccount:${account_email}" \
    --format='table(bindings.role,bindings.condition.title)'
done
unset account_name account_email
```

Verify that every returned binding is Agent VM-only. If an unrelated binding
appears, stop and resolve ownership. Otherwise delete the dedicated accounts
and custom roles:

```bash
for account_name in agent-vm-reconciler agent-vm-reaper omi-agent-vm-bootstrap; do
  gcloud iam service-accounts delete \
    "${account_name}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" --quiet
done

for role_id in omiAgentVmReconciler omiAgentVmReconcilerOperations \
  omiAgentVmReconcilerSubnetwork omiAgentVmSelfStop; do
  gcloud iam roles delete "$role_id" --project="$PROJECT_ID" --quiet
done
unset account_name role_id
```

Effect and blast radius: removes only the former reconciler, reaper, and guest
self-stop authorities. Service-account and custom-role deletion enter GCP
soft-deleted states for their provider-defined recovery windows; after those
windows they are **irreversible**. IAM policy bindings to deleted principals or
roles may remain as inert entries, so remove those exact bindings in a separate
IAM-reviewed change rather than bulk-editing the project policy here.

### 13. Final proof and follow-up

Record aggregate evidence only:

```bash
gcloud compute instances list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" --format=json | jq 'length'
gcloud compute disks list --project="$PROJECT_ID" \
  --filter="name~'^omi-agent-'" --format=json | jq \
  '{count: length, totalGb: ([.[].sizeGb | tonumber] | add // 0)}'
gcloud run jobs list --region="$REGION" --project="$PROJECT_ID" \
  --filter="metadata.name=$RECONCILER_JOB" --format=json | jq 'length'
```

All counts must be zero. Separately verify that `agent.omi.me` has no DNS
record, the proxy Helm release is uninstalled, and no start/reset audit entries
appear after `CUTOVER_UTC`.

After the fleet is empty, open a separate privacy-reviewed change to sweep the
retired Firestore `agentVm`/migration/late-cleanup state and only then remove
`agent_vm_account_cleanup.py`. That change is deliberately not part of live
infrastructure teardown.
