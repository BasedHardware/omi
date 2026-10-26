# Shape-only live Parakeet canary — op1 apply packet

Owner: rollout lead / op1. This packet grants no production authority. The lane
only prepares code and tests; lead merges, schedules and authorizes each apply.
Estimated incremental saving is ~$916/month at the existing schedule, **$0
booked** until actual node-hours/SKUs and vendor fallback costs confirm it on
D+1 and D+3. No GPU time-sharing, floor, admission, model, precision or decoder
change belongs in this experiment.

## Preconditions and identity

Run only outside **13:00–22:00 UTC**, including pool creation, cold-start and
ramp. Reserve enough time for the actual harness: four stages of at least
15 minutes **per arm**, then at least 60 minutes **per arm**, plus 15-minute
watcher qualification, startup and drain. This is at least four hours, and
long clips, sample collection or HOLD can extend it. Do not schedule by the
one-hour soak alone. End/rollback before 13Z; do not rush a HOLD into PASS.

Use a fresh `KUBECONFIG`, an explicit context on every kubectl/Helm command,
and the lead-approved operator tier. Read-only lane preparation uses no GCP
tier and performs no cluster calls. IAM/secrets changes remain separately
approval-gated. Never print workload YAML, pod env values, credentials or UIDs.

Before changes, retain aggregate-only receipts outside any worktree: baseline
serving image digest, source/config hash, model/decoder/precision settings,
driver/CUDA versions, HPA/floor schedule and pool counts. Pin the **currently
served** image digest; the S3 snapshot digest is historical evidence, not an
apply-time authority. Compare canary environment/command to the baseline in
memory, retaining only hashes. Do not dump secrets or environment values.
The watcher repeats image/config/readiness checks and hashes candidate pod,
node labels, shape and routing revision into the experiment identity. A new
pod, config, image, node or routing revision resets the full 900-second window.
The operator must also verify driver/CUDA equality, one physical L4, actual
allocatable CPU/RAM and DaemonSet reservations; the watcher does not attest
the driver from node labels. Preserve all baseline warm nodes.

The commands below run from the merged, pinned product checkout. Set these
operator variables from the approved receipt, without printing their values:

```bash
export KUBECONFIG="$(mktemp /Volumes/Ephemeral/scratch/parakeet-g24-kube.XXXXXX)"
gcloud container clusters get-credentials prod-omi-gke --region us-central1 --project based-hardware
export G24_CONTEXT=gke_based-hardware_us-central1_prod-omi-gke
export G24_RECEIPTS=/Volumes/Ephemeral/scratch/parakeet-g24-op1
mkdir -p "$G24_RECEIPTS"
# Set BASE_NODE_SA, BASE_NODE_VERSION, BASE_IMAGE_TYPE, BASE_DISK_GB,
# BASE_NETWORK_TAGS and BASE_SCOPES from the current baseline pool receipt.
# Set SERVED_DIGEST to sha256:<64 hex>, and LISTEN_DIGEST to the qualified
# listener image containing this PR. Match source/config to those images.
```

The dedicated pool has no `service=parakeet` label and carries a new taint;
baseline node affinity and taint handling exclude it. Candidate nodeSelector
pins both pool and machine type. A separate release/service keeps candidate
out of baseline Service and headless discovery, HPA and global pressure inputs.
Single-zone creation plus total-max1 avoids a regional one-node-per-zone trap.
These flags follow the [gcloud node-pool create reference](https://docs.cloud.google.com/sdk/gcloud/reference/container/node-pools/create).

```bash
test "$(date -u +%H)" -lt 13 || test "$(date -u +%H)" -ge 22
# Continue only after the preceding off-peak check succeeds and lead approves.
gcloud container node-pools create parakeet-g24-canary \
  --project based-hardware --cluster prod-omi-gke --region us-central1 \
  --node-locations us-central1-a --machine-type g2-standard-4 \
  --accelerator type=nvidia-l4,count=1,gpu-driver-version=default \
  --num-nodes 1 --enable-autoscaling --total-min-nodes 1 --total-max-nodes 1 \
  --service-account "$BASE_NODE_SA" --scopes "$BASE_SCOPES" \
  --node-version "$BASE_NODE_VERSION" --image-type "$BASE_IMAGE_TYPE" \
  --disk-size "$BASE_DISK_GB" --tags "$BASE_NETWORK_TAGS" \
  --workload-metadata GKE_METADATA --enable-private-nodes \
  --node-labels env=prod,omi.ai/parakeet-shape-canary=g24 \
  --node-taints omi.ai/parakeet-shape-canary=g24:NoSchedule \
  --max-surge-upgrade 0 --max-unavailable-upgrade 1

helm upgrade --install prod-omi-parakeet-g24 backend/charts/parakeet \
  --kube-context "$G24_CONTEXT" --namespace prod-omi-backend \
  -f backend/charts/parakeet/prod_omi_parakeet_values.yaml \
  -f backend/charts/parakeet/g24_canary_values.yaml \
  --set-string image.digest="$SERVED_DIGEST" --wait --timeout 20m
```

Use the lead's normal listen train for the qualified listener image and add
`parakeetShapeCanary.enabled=true` to its approved Helm values. This mounts
`parakeet-shape-route` as a **directory**, not `subPath`, and initializes it to
0%. Do not replace listener env/volume arrays with a small overlay. Render and
inspect locally first. Verify every receiving listener runs LISTEN_DIGEST,
has the mount, exports the new metrics, and can reach the internal candidate.
An ordinary Helm upgrade resets the route to 0%; it must never silently ramp.

## Routing, watcher, and reversible dry-run trip

`PARAKEET_SHAPE_CANARY_FILE` is the only serving opt-in. The ConfigMap holds
`percent` (0..5, default 0), a SHA-256 `identity`, the fixed internal candidate
URL, and `expires`. Selection is random per managed listen session, pinned
across its replacement window legs. No UID/session labels are exported.
The assignment series counts each session once, not one replica out of eight.
Existing control sessions never enter the experiment mid-session.

Every subsequent window checks the lease on an executor. Invalid/missing or
expired config, 0%, or a changed identity permanently drains that session to
baseline. A POST already accepted by the candidate finishes with its original
timeout. Kubernetes projection is eventually consistent: rollback is bounded
by the last lease's **300-second expiry**, even if ConfigMap propagation or
the watcher fails. There is no forced pod kill, scale-down or active-work
eviction. Keep the pool intact until drain is proved.

Run the watcher from a durable copied script and keep its receipts/owner lease
outside the worktree. Only the watcher writes the routing ConfigMap; an owner
renews `owner.json` with an `expires` epoch no more than 300 seconds ahead.
An absent/stale owner forces HOLD. Do not create a cron that silently keeps
the owner alive. Confirm the owner can receive the watcher output/alert and
acknowledge the deliberate trip before nonzero admission.

```bash
cp backend/scripts/parakeet_shape_watch.py "$G24_RECEIPTS/watch.py"
# Prometheus must be the existing aggregate read route or an operator-owned
# loopback port-forward; no production account API is used.
python3 -I "$G24_RECEIPTS/watch.py" --context "$G24_CONTEXT" \
  --prometheus "$PROMETHEUS_URL" --owner-lease "$G24_RECEIPTS/owner.json" \
  --status-file "$G24_RECEIPTS/watch-status.json" \
  --revision g24-qualification-001 --percent 0 --seconds 21600
```

The owner explicitly renews its readiness receipt while awake:

```bash
printf '{"expires":%s}\n' "$(( $(date +%s) + 240 ))" > "$G24_RECEIPTS/owner.json"
```

Warm both isolated endpoints with approved public/synthetic probes during the
initial lookback so startup peaks and nonzero loaded GPU samples are captured.
The observer must complete the full window before the acceptance harness starts.

First run without `--apply`: it performs aggregate reads only. It requires all
listener scrape targets, fresh first-text/POST and candidate GPU/queue/readiness
series. It deduplicates DCGM by physical UUID and requires nonzero loaded GPU
samples and >=54 samples per 15-minute window. First-text decisions require
>=100 samples in **each** arm. Missing/stale data is HOLD. Candidate restart,
readiness loss, any non-success POST, queue age >=0.75s, throttle >10%, first
text p95 >=30s / POST p95 >=3s, or >20% relative latency is an emergency stop.
These are emergency limits, **not** acceptance margins.

At 0%, a full-window HOLD solely for insufficient first-text samples may keep
observing during direct synthetic qualification. It never enables live work.
The harness checks this fresh status and the same identity. Any other HOLD,
ABORT, STOPPED or identity change invalidates qualification. Prove a deliberate
dry-run bad reading returns ABORT/HOLD, and a controlled operator test of the
writer sets the lease to 0; verify listener new-request routing and drain,
not just command exit status. No live ramp until alert/owner delivery and the
real kill path have receipts.

## Acceptance harness and corpus

Run from the exact qualified listener runtime against an isolated matched
g2-8 control and the g2-4 candidate, with no account API or persistence. Reuse
the actual served `WindowedParakeetSocket`, real paced PCM, public gold speech
spans, model POST payloads and speaker embedding path. Keep model/precision,
decoder, pace, context and speaker settings equal. The harness uses direct
service URLs; it never routes synthetic traffic through a signed-in account.

Supply a fixed JSON manifest list with >=4 fixtures. Each entry has `file`,
`sha256`, `source_kind` (`public` or `synthetic`), `source` (provenance),
`reference` (gold text), `language`, `first_speech_seconds`, and `speech_spans`
(`start`, `end`, integer `speaker`). Mono PCM16/16kHz only. Require >=2
languages, a clip with >=2 speakers, short <=10s and long >=120s inputs, and
a >=1s silence→speech transition. The existing one-voice English route clip
is insufficient. Do not download customer recordings. Corpus sourcing and
gold labels are an operator precondition; no full corpus or GPU evidence was
created by this infrastructure PR.

`identities.json` contains the retained identity evidence, a true
`matched_image_config_driver` only after comparison, and `watcher_identity`
from the fresh 0% watcher. False/missing values block qualification.

```bash
nice -n 19 python -m scripts.qualify_parakeet_shape \
  --control http://ISOLATED_CONTROL_SERVICE.prod-omi-backend.svc.cluster.local:8080 \
  --candidate http://prod-omi-parakeet-g24.prod-omi-backend.svc.cluster.local:8080 \
  --manifest "$G24_RECEIPTS/corpus/manifest.json" \
  --identities "$G24_RECEIPTS/identities.json" \
  --watcher-status "$G24_RECEIPTS/watch-status.json" \
  --representative-concurrency 8 --step-seconds 900 --soak-seconds 3600 \
  --output "$G24_RECEIPTS/acceptance.json"
```

Use representative concurrency supported by aggregate arrival/cadence data,
not the fleet's count of connected sessions. Whole waves alternate randomized
arm order, with the same fixtures and producer count; no independently
randomized producer may silently split endpoint concurrency. The final phase
requires >=60 minutes of wall exposure on **each** arm. Record actual achieved
cadence and the mixed long/short busy period; extend if that is not representative.

First-text is measured from fixture first speech to the first **emitted
nonempty transcript**, not HTTP completion. Every clip must stay <30s. The
harness records live POST and v2 latency (<3s), counts exact WER/CER edit
distances, and rejects any text/omission/tail/timestamp/speaker difference
against control; v2 output (including language/speakers) must match exactly.
This deliberately holds nondeterministic differences for investigation.

At every ladder phase (1,2,4,8) and soak, compare p95 using exact binomial
order-statistic intervals, both pooled and separately for every fixture (so
language/speaker/input-length regressions cannot average away). Bonferroni
alpha=.05/(60 times the number of pooled/fixture cohorts) per tail covers two
arms, three metrics, five phases, two tails and all cohorts. Accept only if the candidate upper
bound <= control lower bound: zero worsening margin. Infinite/overlapping
intervals are HOLD, a separated regression ABORT. No post hoc margin or sample
floor reduction. A short or sparse run cannot pass by lasting an hour.

## Lead-only live ramp and rollback

After synthetic PASS and the real kill/owner drill, start a **new revision**
with `--percent 5 --apply` (or a smaller percentage) under the lead-approved
operator tier. The writer starts at 0 until its prechecks succeed, then renews
the bounded lease. The 15-minute arming window restarts with that identity.
Inspect measured session/work share; a configured 5% is not proof of 5% work.
Keep baseline default and warm capacity unchanged. If the sample floor is
unmet after a full window it routes 0% and exits HOLD. Sparse live traffic
does not waive acceptance. No promotion/replacement beyond this one node is
authorized by this packet; peak/busy-period qualification remains separate.

Rollback first: stop the writer (its `finally` zeros the route), or explicitly
patch only the owned ConfigMap data to 0. Do not change HPA min or delete the
candidate first. An expired lease also sends new requests to baseline.

```bash
kubectl --context "$G24_CONTEXT" -n prod-omi-backend patch configmap parakeet-shape-route \
  --type merge -p '{"data":{"route.json":"{\"percent\":0,\"expires\":0}"}}'
```

Stop/collect the writer before a manual patch so it cannot renew over the kill.
Wait past the last positive lease expiry (up to 300s), then prove all listener
canary-inflight gauges, candidate active/queued requests and streams are zero
for a full two minutes with fresh complete scrapes. Include direct synthetic
producers: stop them and collect their result first. Missing metrics or active
work means retain pool and HOLD. Only after those receipts and the lead's
delete-after-rollback approval:

```bash
helm uninstall prod-omi-parakeet-g24 --kube-context "$G24_CONTEXT" --namespace prod-omi-backend
gcloud container node-pools delete parakeet-g24-canary --project based-hardware \
  --cluster prod-omi-gke --region us-central1
```

Leave listener routing at 0 (or disable its optional mount through the normal
train). Record live serving identities, node/SKU inventory, aggregate results,
alert/owner acknowledgment, HOLD/ABORT reasons and final drain status. Report
observed savings only after baseline capacity actually falls under a separate
lead decision and D+1/D+3 evidence excludes vendor fallback cost increases.
