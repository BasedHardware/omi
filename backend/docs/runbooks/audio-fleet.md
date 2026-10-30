# Audio-path fleet: lead-owned rollout and retirement

Owner: audio-path lead (Claude). One fleet PR; apply only after the 5% batch
cohort is stable. The author executed read-only inspection, rendering and tests.
Commands below that change resources are for the lead, not evidence of execution.
Keep immutable served images; never use `latest` for a chart-only installation.

## Evidence and stop conditions (2026-10-14 UTC)

- Prometheus reproduced listen **21/24 at 09:57:30Z**, not 10:15Z. Unready pods
  `xb82f`, `gqqpz`, `hmfzt` (prefix `prod-omi-backend-listen-868fb5c96-`) became
  NEG-healthy at 09:57:37/38Z. Two had startup connection-refused events.
  This was startup during HPA expansion, not three persistently failed replicas.
  At 10:15Z the scrape was 28/28; live 10:26Z was 22/22. Separate scheduling
  events show CPU/memory pressure, and zone-b `FailedScaleUp: GCE out of resources`.
- Parakeet is 5/7, with two GPU-Pending pods and insufficient L4 capacity.
  Old pools are a: 2–4, b: 1–3. Do not destroy those five serving GPUs.
- Seven-day peak **50 active requests**, 24-hour peak 32, six-hour peak 19.
  Requests include batch/window work; they are not listen session counts.
  The cost baseline's 408 peak listen sessions cannot size ASR capacity.
- Current request p99 was 3.25s. No higher per-pod throughput is qualified by this
  snapshot. Ratified scaling targets remain **2 requests/pod and 35% GPU**;
  `PARAKEET_MAX_INFLIGHT=1` is unchanged. A target is not a throughput receipt.
- Deepgram (cloud and self-hosted) retired 2026-08-27. 2026-10-22 audit (P69):
  30 days of `omi_stt_provider_connect_total{provider="deepgram"}` are zero on
  every service, no `deepgram` log entries cluster-wide, no deepgram pods or
  node pools, `DEEPGRAM_SELF_HOSTED_ENABLED=false` on listen and pusher, and the
  deploy strips both self-hosted env keys. The self-hosted chart is deleted;
  remaining cloud residue is the Secret Manager key plus one orphan subnet
  (`omi-deepgram-gke-us-central1-prod-vpc-1-subnet-1`) for the lead.

Read-only refresh (the kubectl default context is prod; never rely on it):

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
FLEET_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
FLEET_PROJECT=based-hardware
FLEET_REGION=us-central1
FLEET_CLUSTER=prod-omi-gke
FLEET_NAMESPACE=prod-omi-backend
kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" get deploy,hpa,pdb
kubectl --context="$FLEET_CONTEXT" get nodes \
  -L cloud.google.com/gke-nodepool,topology.kubernetes.io/zone
backend/.venv/bin/python backend/scripts/audit_audio_fleet_callers.py \
  --context "$FLEET_CONTEXT" --project "$FLEET_PROJECT" \
  > /tmp/audio-fleet-caller-audit.json
# Exit 1 means no teardown. The output contains classifications, not env values.
```

## New pools and fallback decision

Use new pools rather than changing old pool locations underneath sessions.
Total min/max below are **across all zones**, never per-zone. Create with zero initial nodes; ANY provisions only in response to Pending
probe/workload demand and favors stock and reservations. Soft spread
prefers diversity but does not promise evenly populated zones. Require at least
two populated zones before removing the old availability domain.

| Pool | Machine / GPU | Eligible zones | Total floor / cap | Labels |
| --- | --- | --- | --- | --- |
| `backend-listen-pool-v4` | `n4-highcpu-4` | a/b/c/f | 12 / 25 | `service=backend-listen,env=prod,type=high-cpu` |
| `pusher-pool-v4` | `n4-highmem-2` | a/b/c/f | 8 / 20 | `service=pusher,env=prod,version=v3` |
| `backend-listen-pool-v4-n2` | `n2-standard-4` | a/b/c/f | 0 / 25 | same listen labels |
| `pusher-pool-v4-n2` | `n2-highmem-2` | a/b/c/f | 0 / 20 | same pusher labels |
| `parakeet-pool-v2` | `g2-standard-8`, 1 L4 | a/b/c | 3 / 12 | `service=parakeet,env=prod` |

N2 fallback shapes already serve these workloads on n2rescue; placement in new
zones still needs Ready probes and the existing load/health qualification. Use
fallback only for the N4 shortfall; floors are fleet totals, not additive floors
for primary and fallback. Capacity planning uses requests and allocatable nodes:
listen requests 1 CPU/1.5Gi (about three pods/N4 node before other workloads),
pusher 0.45 CPU/2Gi (about three pods/node after DaemonSet requests; memory limits must keep co-located limit sums under allocatable). Include the LLM gateway sharing listen
labels, kube/system overhead, HPA maxima (listen 60), and one-node loss. Confirm
actual bin-packing with Pending events before evacuation.

**GPU qualification:** L4 on `g2-standard-8` is the existing production shape.
`g2-standard-12` is a candidate using the same L4, not qualified ASR capacity;
probe the exact served image, resources, DCGM, model warmup, POST p95<3s and
streaming contract before giving it `service=parakeet`. Try zone c first when a/b
are out of stock. T4 is qualified for batch diarization only; it is **not**
qualified for Parakeet. No T4/A100/other-GPU spillover is enabled. If all L4 probes
fail, retain old L4 nodes and current vendor overflow, and stop the rollout.

Lead commands; inspect inherited service account, scopes, network, image type,
system config and quota first. N4 uses hyperdisk-balanced; N2/G2 use pd-balanced.
These commands preserve the observed default node SA and GKE metadata mode.
Do not grant IAM permissions as part of pool creation.

```bash
# Lead switches to its own authorized operator tier, outside the author's ro session.
source ~/.local/bin/gcp-agent-env.sh prod-operator
create_cpu_pool() {
  local name="$1" machine="$2" disk="$3" labels="$4" floor="$5" cap="$6"
  gcloud container node-pools create "$name" --project="$FLEET_PROJECT" \
    --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION" \
    --node-locations=us-central1-a,us-central1-b,us-central1-c,us-central1-f \
    --location-policy=ANY --enable-autoscaling \
    --num-nodes=0 --total-min-nodes="$floor" --total-max-nodes="$cap" \
    --machine-type="$machine" --disk-type="$disk" --disk-size=100 \
    --service-account=default --workload-metadata=GKE_METADATA \
    --scopes=gke-default --enable-autorepair --enable-autoupgrade \
    --node-labels="$labels"
}
create_cpu_pool backend-listen-pool-v4 n4-highcpu-4 hyperdisk-balanced \
  service=backend-listen,env=prod,type=high-cpu 12 25
create_cpu_pool pusher-pool-v4 n4-highmem-2 hyperdisk-balanced \
  service=pusher,env=prod,version=v3 8 20
# If N4 is short, provision only the measured deficit on the existing N2 shapes:
# create_cpu_pool backend-listen-pool-v4-n2 n2-standard-4 pd-balanced \
#   service=backend-listen,env=prod,type=high-cpu 0 25
# create_cpu_pool pusher-pool-v4-n2 n2-highmem-2 pd-balanced \
#   service=pusher,env=prod,version=v3 0 20
# GPU pool is gated by the floor/cost/qualification decision below:
: "${FLEET_CAPACITY_RECEIPT:?Set the reviewed qualified-capacity and cost receipt path}"
test -s "$FLEET_CAPACITY_RECEIPT"
gcloud container node-pools create parakeet-pool-v2 \
  --project="$FLEET_PROJECT" --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION" \
  --node-locations=us-central1-a,us-central1-b,us-central1-c \
  --location-policy=ANY --enable-autoscaling --num-nodes=0 \
  --total-min-nodes=3 --total-max-nodes=12 --machine-type=g2-standard-8 \
  --accelerator=type=nvidia-l4,count=1,gpu-driver-version=latest \
  --disk-type=pd-balanced --disk-size=100 --service-account=default \
  --workload-metadata=GKE_METADATA --scopes=gke-default \
  --enable-autorepair --enable-autoupgrade --node-labels=service=parakeet,env=prod
```

Start bounded synthetic Pending demand for each **new** pool; the following
lead-only probe requests one node per replica using hostname anti-affinity.
Use the chosen pool floor as the probe count (12 listen, 8 pusher, or the approved
GPU floor). For Parakeet add a one-GPU request to the container resources. Do not
copy customer env/secrets or expose a Service for these probes. Record Ready node
counts before deleting probes, and ensure the accepted pool floor prevents
immediate removal of replacement capacity. An N2 fallback floor of zero must be
raised to the measured N4 deficit before removing its probes.

```bash
: "${FLEET_PROBE_POOL:?Set one new pool name from the table}"
: "${FLEET_PROBE_COUNT:?Set the bounded approved probe node count}"
cat <<EOF | kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fleet-capacity-probe
spec:
  replicas: $FLEET_PROBE_COUNT
  selector:
    matchLabels: {app: fleet-capacity-probe}
  template:
    metadata:
      labels: {app: fleet-capacity-probe}
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: $FLEET_PROBE_POOL
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels: {app: fleet-capacity-probe}
              topologyKey: kubernetes.io/hostname
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.10
          resources:
            requests: {cpu: 100m, memory: 64Mi}
EOF
# GPU probe: edit requests to add "nvidia.com/gpu": 1 and the existing GPU
# toleration, then apply the reviewed manifest (not the CPU probe above).
kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" rollout status \
  deployment/fleet-capacity-probe --timeout=35m
kubectl --context="$FLEET_CONTEXT" get nodes \
  -l "cloud.google.com/gke-nodepool=$FLEET_PROBE_POOL" \
  -L topology.kubernetes.io/zone
# After recording actual Ready capacity and verifying retained floor:
kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" delete deployment fleet-capacity-probe
```

A RUNNING pool is not capacity. Verify actual Ready nodes, allocatable GPU/CPU/
memory, labels, zones, MIG target/current size and `list-errors` in each zone.
A stockout or Pending replacement is a stop, not permission to remove n2rescue.
Keep old pools as rollback capacity for 24–48 hours after successful migration.
After idle-session proof and that observation, set old Parakeet a/b floors to zero
and retire their empty capacity; otherwise their three-node floor adds to the new
three-node floor. Until then, retaining five old GPUs adds about $102.43/day list-price
equivalent to the new pool. Count all old/new/fallback nodes in the cost receipt.
Listen/pusher scheduling is unchanged: empty nodeSelector, the existing required
service/env/type/version affinity, and no new topology spread or tolerations.
Current pools and correctly labelled new pools remain eligible; creating pools
does not evict or move existing pods. Parakeet pod templates are identical to
main; only its HPA changes. Current pools already have L4. Only give qualified
L4 pools the existing Parakeet service/env labels; no new accelerator affinity
or scheduling change is introduced. Caller/env deployment still rolls pods, so the lead must
observe the session gate below before applying those changes.

Reference: [GKE create flags](https://docs.cloud.google.com/sdk/gcloud/reference/container/node-pools/create)
and [autoscaler total bounds and ANY policy](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler).

## Parakeet floor, latency guard and cost gate

Production values and the replacement pool use **floor 3, cap 12**. The ratified
**2 active requests/pod or 35% GPU** are scale-out triggers, not hard capacity.
Today's 5–7 pods carry the seven-day peak; dividing peak requests by the trigger
would incorrectly require 26 pods. The ceiling provides headroom for the
demand-routing ramp that moves background sessions to Parakeet.

Retain 900-second down stabilization, one-pod down steps every 900s, and the
existing adapter p99 latency guard at **3 seconds**, not milliseconds. HPA takes
the highest recommendation; latency may raise replicas but cannot guarantee an
SLO. Ready capacity, real DCGM and POST p95<3s remain rollout qualification gates;
never relax the ratified 2/35 targets to fit available stock.

Dev defaults remain floor/cap 1 and request target 20; they cannot qualify this
production policy. For a bounded dev experiment, the lead uses an explicit
qualification overlay with floor 3/cap 4, request/GPU targets 2/35, the 3s latency
guard and 900s down behavior from prod. Provision its approved GPU capacity first
and use the served prod image/model/resource settings with dev identity and URLs.
Record real DCGM and per-pod throughput; restore the dev release after the test.
The bounded dev overlay is sufficient to test stabilization; production cap 12
is demand-ramp headroom, not a required test allocation.

Check external metrics `parakeet_request_latency_p99` and `parakeet_gpu_utilization`
and per-pod `parakeet_active_requests_total`; a missing metric/adapter error blocks
application. Prove scale-out under paced/burst peak traffic, then 900s stabilization
and active-session-safe scale-down in dev. Merely rendering an HPA is not this proof.

### Dark workload-only HPA option

`autoscaling.workloadOnly: false` preserves the policy above. After mixed-load
qualification, changing that one production value to `true` omits only
`parakeet_request_latency_p99`. Request concurrency (Pods AverageValue 2),
GPU utilization (External Value 35), floor 3/cap 12, and both scaling behaviors
remain unchanged. This option is independent of packing and of
`autoscaling.demand.enabled`; it does not activate the demand scaler or change
its existing queue-age metrics.

The omitted metric combines request durations across callers and audio lengths.
It includes upload/file work, queuing and response processing; `/v2` can also
include diarization. An External Value recommendation multiplies the current
replica count by latency/target, so an intrinsic processing tail can request
extra GPUs without a backlog. A value below target is not a permanent replica
floor: tolerance, tail spikes and down stabilization also determine the result.
Do not simply convert this global percentile to External AverageValue, which
divides a single fleet percentile across replicas. Preserve the GPU Value type:
the adapter already returns a fleet average percentage.

Observe live POST p95/p99 (`omi_stt_window_post_seconds_bucket`), lane queue p99
(`parakeet_batch_lane_queue_wait_seconds_bucket{lane="live"}`), refusals, ready
capacity, and real DCGM alongside this option. A lane queue percentile is useful
for diagnosis but is not an additive queue-size metric. First qualify any new
scaling target and adapter semantics separately. The existing demand scaler's
queue-age policy is a separate experiment.

Before production activation, demonstrate POST p95 <3s under paced and burst
live traffic plus legacy sync/recovery traffic at the proposed minimum. Use the
live routing runbook's stricter sustained 2s warning/abort gate during a trial;
also verify first text <30s, transcript success and vendor fallback exposure.
Low current utilization or a read-only counterfactual does not qualify three
pods, especially while cost routing benches Parakeet and suppresses its demand.

Deploy path: workflow `gcp_parakeet.yml` (Deploy Parakeet ASR to GKE), input
`environment=prod`, service `parakeet`, Helm release `prod-omi-parakeet` in
`prod-omi-backend` on `based-hardware/us-central1/prod-omi-gke`. Dispatch the
approved ref; the workflow checks out the dispatch ref (its `branch` input is
not used by checkout). It builds an image and upgrades the whole release, so
review image and chart drift as well as the HPA diff before dispatching.
Rollback: restore `workloadOnly: false` and deploy the reviewed ref through the
same workflow; verify all three HPA metrics return. Avoid an unrelated historical
Helm rollback that could also revert runtime configuration. No deployment or
flag activation is implied by adding this dark option.

At the baseline's L4 node list price $0.8536/hour, floor 3 is **$61.46/day**
and cap 12 is **$245.84/day**. The ceiling is headroom, not expected steady spend.
The 6.2-node baseline mean is $127.02/day list equivalent; reaching three nodes
would reduce that by $65.56/day, but neither this mean nor cash savings is
qualified. The rejected 26-node floor's approximately +$405.63/day is avoided.
Keep actual old/new overlap in the cost receipt; commitments may leave $0 cash
savings. CPU multi-zone placement alone has
no demonstrated cash saving; temporary overlap costs more. Idle Deepgram pools
already have zero nodes, so their VM deletion saves $0/day at this snapshot;
load-balancer/IP savings require actual billing reconciliation after teardown.

## Session-preserving evacuation: blocked until qualified

Listen `preStop` is `sleep 15`, termination grace 120s. Pusher calls local
`POST /__internal/drain`, then sleeps 15; grace is 120s, LB draining timeout 60s.
`backend/utils/readiness.py` and `backend/docs/pusher_rolling_update_operations.md`
explicitly say the ALB/NEG path cuts existing WebSockets; reconnect is recovery,
not a zero-drop drain. PDB 80% protects availability, not session continuity.
Longer sleeps or a one-at-a-time `kubectl drain` cannot establish zero dropped
sessions. **No evict/delete/Helm pod-template rollout on active sessions.** Cordon only
prevents scheduling; it does not drain admission or migrate existing sessions.

Required sequence:

1. Prove replacement Ready capacity in >=2 zones with N-1 headroom. Keep all
   old CPU/GPU nodes. Freeze automatic downscaling/node removal during the lead's
   controlled migration; cordon the old rescue nodes only after replacement capacity
   is Ready, so evicted idle pods cannot return there. Do not use a routine rollout
   as the evacuation primitive.
2. In dev, qualify an admission-only drain that stops new sessions while keeping
   existing transport/backend health and sockets alive, or establish a truly
   traffic-free window. The current readiness-based pusher drain does not satisfy
   this condition. Synthetic overlapping long sessions must retain IDs and deliver
   every sequenced PCM frame and final transcript through the transition, without
   close/reconnect events. Check both listen and downstream pusher paths.
3. Only after that proof, stop new admission to one old listen pod, leave it
   serving existing connections, and wait for its `backend_listen_active_ws_connections`
   to reach zero plus all finalization work to finish. Then use normal eviction
   with its existing preStop/grace, PDB and replacement readiness checks. Never
   bypass PDB, force-delete, or shorten the grace deadline. If zero is never
   reached, retain that pod/node; this runbook has no forced timeout.
4. Finish listen migration **before** pusher, since old listen sessions hold
   downstream pusher connections. Gate each pusher eviction on
   `pusher_active_ws_connections=0` and completed audio/finalization drains.
   Resolve any co-located LLM gateway/other pods independently before node removal.
5. Observe stable session IDs, no missing frames/transcripts, zero abnormal close
   increase, zero reconnect/degraded increase, latency and vendor fallback rates.
   Roll back admission/routing immediately on failure. Keep rescue capacity 24–48h;
   only then scale empty pools to zero and delete them with the lead's commands.

Lead-only removal after every rescue application pod is idle and evacuated:

```bash
# Record an empty application-pod inventory on these nodes first; retain
# separate evidence for co-located workloads. Never rely on pool status alone.
for pool in backend-listen-pool-n2rescue pusher-pool-n2rescue; do
  gcloud container node-pools update "$pool" --project="$FLEET_PROJECT" \
    --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION" --no-enable-autoscaling
  gcloud container clusters resize "$FLEET_CLUSTER" --project="$FLEET_PROJECT" \
    --region="$FLEET_REGION" --node-pool="$pool" --num-nodes=0
  # Verify zero actual nodes before deletion, after the 24–48h observation.
  kubectl --context="$FLEET_CONTEXT" get nodes \
    -l "cloud.google.com/gke-nodepool=$pool"
  gcloud container node-pools delete "$pool" --project="$FLEET_PROJECT" \
    --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION"
done
```

An instantaneous zero gauge with continued admission is not safe. Step 2 is a
hard prerequisite, so a fully automated zero-drop n2rescue exit is **not qualified
by this chart PR**. The lead must not mark evacuation complete from preStop alone.

## Self-hosted Deepgram retirement

**Closed 2026-10-22 (P69):** the post-deploy caller audit came back clean (zero
traffic 30d, no pods, no node pools), so this runbook's precondition is met and
the `backend/charts/deepgram-self-hosted` chart is deleted from the repo.
Cloud Deepgram is retired the same day at the policy layer
(`config/stt_provider_policy.py`): no surface admits it, `dg-*` slots are
refused, and the pre-recorded client raises.

Source audit: streaming chooses the self-hosted endpoint only when
`DEEPGRAM_SELF_HOSTED_ENABLED` is true; default is false. The prerecorded SDK and
BYOK streaming use the cloud vendor independently. This PR sets prod pusher
false, removes its URL, retires all Omi Nova2/Nova3 overlays/install instructions,
and enforces removal of both self-hosted env keys from all four Cloud Run owners.
Cloud credential bindings, model order, BYOK behavior and cloud SDK endpoint are
unchanged. Vendored upstream charts and historical dashboards are archival.

Lead deploys the pusher configuration and `gcp_backend.yml` owners, including
backend-sync-backfill. Rerun `audit_audio_fleet_callers.py`: it checks all cluster
workload templates and nonterminal pods, ConfigMap envFrom, every region-local Cloud Run service and
**every traffic-serving revision**, plus Deepgram replicas and Gateway routes.
It prints no env values or secrets; unresolved bindings/read failures block it.
Do not fetch Secret Manager payloads to make this audit pass. If a secret-based
endpoint exists, remove the obsolete reference through its owning deployment.
Confirm all running caller pods belong to the new revision and old serving
revisions/zero-replica canary templates cannot be reactivated with old bindings.
Check internal ingress/backend metrics for seven days after the last caller
migration; missing telemetry is not zero traffic. Only a clean audit plus zero
requests permits teardown. Old Parakeet Ingress/IP/DNS remain for >=7 days too.

Observed retirement inventory: namespace `prod-omi-dg-self-hosted`, deployments
`deepgram-api`, `deepgram-engine`, `deepgram-license-proxy` all 0/0; ingress
`deepgram-api-ingress`, host `dg.omi.me`, address `172.16.175.250`; regional reserved
address `prod-omi-deepgram-ilb-ip-address`; empty `engine-pool` (`g2-standard-12`,
max 25) and `license-proxy-pool` (max 2). Verify again before deletion.

```bash
# Lead only, AFTER clean audit + observation; no forced finalizer removal.
kubectl --context="$FLEET_CONTEXT" -n prod-omi-dg-self-hosted \
  delete ingress deepgram-api-ingress
# Verify the ingress's forwarding rule/backend resources disappear, then:
kubectl --context="$FLEET_CONTEXT" delete namespace prod-omi-dg-self-hosted
kubectl --context="$FLEET_CONTEXT" wait --for=delete \
  namespace/prod-omi-dg-self-hosted --timeout=15m
# Confirm no nodes/pods/other consumers in these exact pools before deletion.
gcloud container node-pools delete engine-pool --project="$FLEET_PROJECT" \
  --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION"
gcloud container node-pools delete license-proxy-pool --project="$FLEET_PROJECT" \
  --cluster="$FLEET_CLUSTER" --region="$FLEET_REGION"
gcloud compute addresses describe prod-omi-deepgram-ilb-ip-address \
  --project="$FLEET_PROJECT" --region="$FLEET_REGION" --format='value(status,users)'
# Stop unless RESERVED with no users. Remove only the reviewed dg DNS record.
gcloud compute addresses delete prod-omi-deepgram-ilb-ip-address \
  --project="$FLEET_PROJECT" --region="$FLEET_REGION"
```

Do not delete `api-pool`, cloud-vendor secrets, other Deepgram-named VPC resources,
or Parakeet legacy ingress/IPs as part of this teardown.

## Deferred branch: Parakeet Gateway caller switch

The caller switch is **excluded from #21486** and parked on
`lane/parakeet-gateway-callers`, based on main. No PR is open for that branch.
The lead opens its separate PR only after Gateway and legacy probes pass in
**both dev and prod**. Use the same synthetic corpus and four-stream probe in
dev with its verified Gateway/legacy URLs, served image and VPC network; never
reuse prod namespace/network bindings for dev. This avoids main's automatic dev listen/pusher deployment
switching URLs before qualification. All existing caller URLs remain unchanged
in this fleet PR. Apply the separate caller change after qualification, CPU/GPU
capacity and the service-by-service Gateway rollout.
Prod VIP `172.16.160.20` was verified live Programmed; dev VIP `172.16.48.49` is
from the lead's 2026-10-14 STATE receipt (ro-prod is denied dev reads). Lead must
reverify both named addresses and their Gateway Programmed conditions immediately
before deployment. Preserve the `/parakeet` prefix. Switch listen, all four Cloud
Run services and pusher in both environments in one caller commit. Deploy through
`gcp_backend.yml`, `gcp_backend_listen_helm.yml` and `gcp_backend_pusher.yml`.

Use [internal-gateway README](../../charts/internal-gateway/README.md)'s route
installation/verification helpers. Require Accepted/ResolvedRefs, Attached policies,
healthy backends and exact immutable images before caller rollout. From a GKE
synthetic probe and VPC-attached Cloud Run probe, qualify:

- `/parakeet/v1/transcribe`: real window PCM POST, text/segments and p95<3s;
- `/parakeet/v2/transcribe`: prerecorded audio, expected transcription contract;
- `/parakeet/v3/stream`: real WebSocket 101, correct query configuration and ready frame, ordered
  bidirectional PCM/text, normal finalization, and reconnect/idle behavior.

The wire protocol is implemented in `backend/parakeet/main.py` and
`backend/utils/stt/streaming.py`; use their current clients/fixtures, not an
invented generic WebSocket payload. Test the Gateway URL with the prefix and the
legacy URL on the same synthetic corpus; include concurrent window/stream load,
sessions across a service rollout, and the existing 120s backend timeout/130s
draining policy. Health=200 or 101 alone does not qualify audio delivery. Never
call `api.omi.me` as a user. Retain per-probe receipts from both networks and
observe >=30 minutes on real switched traffic before advancing.

Rollback: revert the separately deployed caller commit and redeploy all caller owners to
old per-environment Parakeet URLs; confirm recovered bidirectional audio through
old ingress. Roll back Parakeet route revision using the captured Helm history
only after restoring callers. Never remove the shared Gateway or another service's
route while they still serve callers.

## Executable pre-merge route gate

**#21486 must remain unmerged until the lead obtains all-pass receipts for both
URLs from both networks.** Run `python -m scripts.qualify_parakeet_route --base
<url>` in the backend image's `/app` working directory. The image copies
`backend/` into `/app`, so imports are `utils.stt.*`, not `backend.utils.*`.
The bundled 174,114-byte synthetic speech WAV needs no TTS/download/user data.
Default concurrency is four paced streams (maximum eight); do not increase it
while stockout persists. A refusal is `outcome=refused`, blocks qualification,
and exits 1 without retrying. Do not treat admission refusal as route success.

The pinned client validates HTTP 101 and `{"type":"ready"}`; sample rate is
configured by `?sample_rate=16000`, **not** a made-up start/config frame. It sends
ordered mono PCM16 and literal `finalize`. The gate preserves wire order and requires non-empty text **before** finalize,
finite nonnegative non-inverted spans, settled client tasks and the lead-ratified legacy-parity finish below.
`parakeet/main.py` forwards `StreamSession.feed`/`flush` results unchanged.
`stream_handler.py` removes the shared text of cumulative RNNT hypotheses, but
`_build_segments` keeps utterance spans; suffixes/revisions can overlap. The
`_speech_start_s or _stream_offset_s` expression also replaces a zero start with
the current stream offset, moving the reported right edge beyond sent audio.
Partial decoder chunks are right-padded, and spans are not word alignment.
`utils/stt/streaming.py` forwards text-bearing frames without a timing filter;
`TranscriptSegment.combine_segments` merges chronological overlapping spans and
retains late arrivals separately. The probe therefore imposes no disjointness or
bytes-sent timestamp ceiling. It reports overlap/right-edge counts as observations.
Every stream receipt includes at most five `segment_spans` (start/end only) and
`is_connection_dead`; failures identify the condition and expose no transcript.
**Finalize ownership:** `main.py` breaks on literal `finalize`, flushes pending
segments, cleans the session, releases admission and returns. It sends no
application close frame/status and no finalize acknowledgment. The ASGI/transport
may close on return; an empty close frame is decoded as 1005 (never sent as wire
status 1005). Otherwise the client closes. `ParakeetWebSocketSocket._run` waits
five seconds after sending finalize; drain sets `_closed`, bounds sender/receiver
cleanup at ten seconds and cancels stragglers. Context exit and `_run` finally
call `ws.close()`. A timeout can initiate client close before a server close frame;
there is no promised server frame to await. Production listen teardown awaits this
drain and does not demand a server 1000 acknowledgment.
**Legacy parity ruling:** the lead's `probe-gke-e7c002b1.jsonl` reports 1006 with
an empty reason for all twelve GKE v3 checks across Gateway and legacy routes.
The gate accepts this only after a successfully sent literal `finalize`, valid
non-empty speech received before finalize, and both sender/receiver tasks
completed without cancellation or exception. Such a receipt records
`close_kind=server_dropped_after_finalize` and `finalize_sent=true`. This qualifies
parity with today's legacy behavior; it does not certify a clean close handshake.
1006 before finalize, missing speech, malformed segments, dead connections,
cancelled/unfinished/error tasks in the 1006 case, and 1011 still fail. Standard
1000/1001/empty-frame 1005 closes remain clean; bounded cleanup cancellation is
reported for those clean codes. Receipts retain actual close code/reason, task
states (exception type only), and transcript-free failure diagnostics.
The clean-close server correction is a separate PR based on main; it is excluded
from #21486 and must not be merged or deployed by this qualification run.
There is no server finalize-ack frame to invent. After parallel streams release
leases, one connection idles for 35s (crossing the server's 30s receive interval),
then transcribes; a new connection must transcribe again. Per-check deadline is
120s. JSONL includes latency, first words, corpus hash, status and outcome.
`/v1` uses the live-window client's AGC/WAV and admission-budget headers; `/v2`
uses the prerecorded client's multipart/diarize payload and response normalizer.
Its probe-only response observer rejects non-200 or v2-to-v1 fallback; it restores
the client module after use. No served STT code is modified.

Before merge the served image cannot contain this new script. Stage only the
reviewed script and corpus into that **exact immutable image**, using a ConfigMap
for GKE and a read-only artifact volume for the job. No application secrets,
customer env or provider keys are copied. Run from the reviewed PR checkout:

```bash
# LEAD ONLY: creates temporary synthetic probes/artifacts, never a service rollout.
FLEET_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
FLEET_PROJECT=based-hardware
FLEET_REGION=us-central1
FLEET_NAMESPACE=prod-omi-backend
FLEET_PROBE_SHA=$(git rev-parse HEAD)
FLEET_PROBE_ID="audio-fleet-probe-${FLEET_PROBE_SHA:0:12}-$(date -u +%H%M%S)"
FLEET_PROBE_DIR=$(mktemp -d)
mkdir -p "$FLEET_PROBE_DIR/scripts/fixtures"
: > "$FLEET_PROBE_DIR/scripts/__init__.py"
cp backend/scripts/qualify_parakeet_route.py "$FLEET_PROBE_DIR/scripts/"
cp backend/scripts/fixtures/parakeet_route_synthetic.wav "$FLEET_PROBE_DIR/scripts/fixtures/"

# Only image identifiers/traffic are read; never print workload env or secrets.
FLEET_GKE_IMAGE=$(kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" \
  get pods -l app.kubernetes.io/name=backend-listen --field-selector=status.phase=Running \
  -o 'jsonpath={.items[0].status.containerStatuses[0].imageID}')
FLEET_GKE_IMAGE=${FLEET_GKE_IMAGE#docker-pullable://}
case "$FLEET_GKE_IMAGE" in *@sha256:*) ;; *) echo 'Require served image digest'; exit 1;; esac
kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" create configmap "$FLEET_PROBE_ID" \
  --from-file="__init__.py=$FLEET_PROBE_DIR/scripts/__init__.py" \
  --from-file="qualify_parakeet_route.py=$FLEET_PROBE_DIR/scripts/qualify_parakeet_route.py" \
  --from-file="parakeet_route_synthetic.wav=$FLEET_PROBE_DIR/scripts/fixtures/parakeet_route_synthetic.wav"

FLEET_GKE_FAILED=0
for route in gateway legacy; do
  case "$route" in gateway) base=http://172.16.160.20/parakeet;; legacy) base=http://parakeet.omi.me;; esac
  name="$FLEET_PROBE_ID-$route"
  python3 - "$name" "$FLEET_GKE_IMAGE" "$FLEET_PROBE_ID" "$base" > "$FLEET_PROBE_DIR/pod.json" <<'PY'
import json, sys
name, image, configmap, base = sys.argv[1:]
print(json.dumps({'apiVersion': 'v1', 'spec': {
    'activeDeadlineSeconds': 600, 'restartPolicy': 'Never',
    'containers': [{'name': name, 'image': image, 'workingDir': '/app',
        'command': ['python'],
        'args': ['-c', "import sys,runpy;sys.path.insert(0,'/probe');runpy.run_module('scripts.qualify_parakeet_route',run_name='__main__')",
                 '--base', base, '--concurrency', '4', '--timeout', '120', '--idle-seconds', '35'],
        'resources': {'requests': {'cpu': '250m', 'memory': '512Mi'},
                      'limits': {'cpu': '1', 'memory': '1Gi'}},
        'volumeMounts': [{'name': 'probe', 'mountPath': '/probe', 'readOnly': True}]}],
    'volumes': [{'name': 'probe', 'configMap': {'name': configmap, 'items': [
        {'key': '__init__.py', 'path': 'scripts/__init__.py'},
        {'key': 'qualify_parakeet_route.py', 'path': 'scripts/qualify_parakeet_route.py'},
        {'key': 'parakeet_route_synthetic.wav', 'path': 'scripts/fixtures/parakeet_route_synthetic.wav'}]}}]
}}))
PY
  if kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" run "$name" \
    --image="$FLEET_GKE_IMAGE" --restart=Never --attach=true --rm --quiet \
    --pod-running-timeout=2m --overrides="$(cat "$FLEET_PROBE_DIR/pod.json")" \
    > "$FLEET_PROBE_DIR/gke-$route.jsonl"; then
    cat "$FLEET_PROBE_DIR/gke-$route.jsonl"
  else
    FLEET_GKE_FAILED=1
    cat "$FLEET_PROBE_DIR/gke-$route.jsonl"
  fi
 done
kubectl --context="$FLEET_CONTEXT" -n "$FLEET_NAMESPACE" delete configmap "$FLEET_PROBE_ID"
test "$FLEET_GKE_FAILED" -eq 0
```

Cloud Run uses the backend's observed direct-VPC network/subnet and attached
runtime identity. Reverify these fields before execution without printing env.
Use an existing artifact bucket that this identity can read; no new IAM grant is
part of these commands. The bucket prefix contains only the reviewed probe files.
If backend traffic is split, repeat for **every** serving revision/image.

```bash
: "${FLEET_PROBE_BUCKET:?Set an existing synthetic-artifact bucket readable by backend-runtime}"
FLEET_PROBE_PREFIX="audio-fleet/$FLEET_PROBE_SHA"
FLEET_CR_REVISION=$(gcloud run services describe backend \
  --project="$FLEET_PROJECT" --region="$FLEET_REGION" --format='json(status.traffic)' \
  | python3 -c 'import json,sys; t=json.load(sys.stdin)["status"]["traffic"]; r=[x["revisionName"] for x in t if x.get("percent",0)>0]; assert len(r)==1,"Repeat for every serving revision"; print(r[0])')
FLEET_CR_IMAGE=$(gcloud run revisions describe "$FLEET_CR_REVISION" \
  --project="$FLEET_PROJECT" --region="$FLEET_REGION" --format='value(spec.containers[0].image)')
case "$FLEET_CR_IMAGE" in *@sha256:*) ;; *) echo 'Require served image digest'; exit 1;; esac
# The exact served backend image imports the mounted probe, not a new backend image.
gcloud storage cp "$FLEET_PROBE_DIR/scripts/__init__.py" "gs://$FLEET_PROBE_BUCKET/$FLEET_PROBE_PREFIX/scripts/__init__.py"
gcloud storage cp "$FLEET_PROBE_DIR/scripts/qualify_parakeet_route.py" "gs://$FLEET_PROBE_BUCKET/$FLEET_PROBE_PREFIX/scripts/qualify_parakeet_route.py"
gcloud storage cp "$FLEET_PROBE_DIR/scripts/fixtures/parakeet_route_synthetic.wav" "gs://$FLEET_PROBE_BUCKET/$FLEET_PROBE_PREFIX/scripts/fixtures/parakeet_route_synthetic.wav"

# Cloud Run may ingest JSON stdout as jsonPayload, not textPayload.
cat > "$FLEET_PROBE_DIR/extract-receipts.py" <<'PYRECEIPT'
import json, sys
receipts = []
for entry in json.load(sys.stdin):
    payload = entry.get('jsonPayload')
    if not isinstance(payload, dict):
        try:
            payload = json.loads(entry.get('textPayload', ''))
        except (ValueError, TypeError):
            continue
    if isinstance(payload, dict) and 'check' in payload:
        receipts.append(payload)
        print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if len(receipts) == 8 and all(r.get('outcome') == 'pass' for r in receipts) else 1)
PYRECEIPT

FLEET_CR_FAILED=0
for route in gateway legacy; do
  case "$route" in gateway) base=http://172.16.160.20/parakeet;; legacy) base=http://parakeet.omi.me;; esac
  job="$FLEET_PROBE_ID-cr-$route"
  gcloud run jobs create "$job" --project="$FLEET_PROJECT" --region="$FLEET_REGION" \
    --image="$FLEET_CR_IMAGE" --workdir=/app \
    --service-account=backend-runtime@based-hardware.iam.gserviceaccount.com \
    --network=omi-prod-vpc-1 --subnet=omi-us-central1-prod-vpc-1-subnet-1 \
    --vpc-egress=private-ranges-only --tasks=1 --parallelism=1 --max-retries=0 \
    --task-timeout=600s --cpu=1 --memory=1Gi \
    --add-volume="name=probe,type=cloud-storage,bucket=$FLEET_PROBE_BUCKET,readonly=true,mount-options=only-dir=$FLEET_PROBE_PREFIX" \
    --add-volume-mount=volume=probe,mount-path=/probe --set-env-vars=PYTHONPATH=/probe \
    --command=python \
    --args="-m,scripts.qualify_parakeet_route,--base,$base,--concurrency,4,--timeout,120,--idle-seconds,35"
  if ! gcloud run jobs execute "$job" --project="$FLEET_PROJECT" --region="$FLEET_REGION" --wait; then
    FLEET_CR_FAILED=1
  fi
  if ! gcloud run jobs logs read "$job" --project="$FLEET_PROJECT" --region="$FLEET_REGION" \
    --order=asc --limit=100 --format='json(jsonPayload,textPayload)' \
    | python3 "$FLEET_PROBE_DIR/extract-receipts.py" > "$FLEET_PROBE_DIR/cloud-run-$route.jsonl"; then
    FLEET_CR_FAILED=1
  fi
  cat "$FLEET_PROBE_DIR/cloud-run-$route.jsonl"
  gcloud run jobs delete "$job" --project="$FLEET_PROJECT" --region="$FLEET_REGION" --quiet
 done
test "$FLEET_CR_FAILED" -eq 0
```

If log ingestion is delayed, reread logs before deleting the job; retry log
retrieval, not an admission-refused workload. Retain all four JSONL receipts with image digests and reviewed probe SHA before
removing the temporary artifact prefix. Require eight `pass` receipts per run at
default concurrency, zero `fail/refused`, and exit 0. A transport timeout, wrong
ready frame, empty transcript, disordered timestamps or abnormal close blocks
merge. Existing rollout-across-sessions and p95/900s scale-down qualifications
remain separate operational gates; this short probe does not prove zero-drop
evacuation or sustained-load latency.

## Local verification

```bash
backend/.venv/bin/python -m pytest -q backend/tests/unit/test_audio_fleet_helm.py \
  backend/tests/unit/test_qualify_parakeet_route.py \
  backend/tests/unit/test_internal_gateway_helm.py \
  backend/tests/unit/test_verify_pusher_config_references.py \
  backend/tests/unit/test_monitoring_adapter_hpa_contract.py \
  backend/tests/unit/test_parakeet_helm_contract.py \
  backend/tests/unit/test_backend_runtime_env_validator.py
backend/.venv/bin/python backend/scripts/validate-backend-runtime-env.py --env dev --check-workflows
backend/.venv/bin/python backend/scripts/validate-backend-runtime-env.py --env prod --check-workflows
make preflight
```

Rendering/CI green does not establish stock, throughput, a zero-drop drain or
post-deployment retirement proof. Each blocked gate above remains lead-owned.
