# Parakeet — streaming capacity per ready replica

**What it means:** Production Parakeet has less streaming headroom per ready
replica than intended. This is an infrastructure signal: it can precede live
transcription delay or rejected streams, but does not by itself prove a user
outage.

**Owner:** speech-processing / platform team.

The `/v3/stream` server owns a hard per-pod admission gate. Every one of the
27 backend-listen replicas connects to that boundary, and each Parakeet pod
runs one Uvicorn process for its GPU, so listener count cannot multiply the
configured limit. Rejected handshakes close with code `1013` and reason
`capacity_full` or `allocation_rejected`; listeners may then connect to
Modulate before accepting audio.

## Deployment settings

The Parakeet Helm values and `backend/deploy/runtime_env.yaml` explicitly own:

| Setting | Production value | Meaning |
| --- | --- | --- |
| `PARAKEET_STREAM_CAPACITY` | `25` | Maximum admitted `/v3/stream` sessions in one Parakeet pod. |
| `PARAKEET_STREAM_ALLOCATION_PERCENT` | `100` | Percentage of new Parakeet handshakes eligible for admission. |

Both settings are validated at service startup and the server fails to start
when either is absent or invalid. Changing either setting requires the normal
Parakeet Helm rollout; it is not a live runtime switch. Keep the HPA target
strictly below the hard capacity so scaling starts before rejection.

**Dashboard:** Grafana → Parakeet ASR Monitoring → **Streaming capacity per
ready replica**. Compare it with **HPA Replicas (Ready / Total / Desired)**,
GPU utilization, queue duration, request latency, and request errors.

**PromQL:**

```promql
sum(parakeet_active_streams{container="parakeet", namespace="prod-omi-backend"}) / clamp_min(sum(kube_deployment_status_replicas_ready{deployment="prod-omi-parakeet", namespace="prod-omi-backend"}), 1)
```

The metric is the sum of active WebSocket streams divided by ready deployment
replicas. It deliberately follows the currently serving replica count, so a
cluster-total stream count cannot hide a per-pod capacity problem while the HPA
is catching up.

| Alert | Threshold | Duration | Meaning |
| --- | --- | --- | --- |
| Warning | 15 active streams per ready replica | 5 minutes | Headroom is reduced; confirm HPA progress and pod readiness. |
| Critical | 20 active streams per ready replica | 2 minutes | Near the configured 25-stream per-replica hard limit; act after corroborating the dashboard. |

No data is healthy for these capacity alerts. Missing metrics are not proof of
saturation; investigate scrape, deployment, or readiness separately if the
dashboard is unexpectedly empty.

## First checks

1. Confirm the capacity panel remains above the alert threshold for its full
   duration and that the displayed ready-replica value is current.
2. Compare HPA desired, total, and ready replicas. A desired-versus-ready gap
   points to scheduling, image startup, readiness, or node-capacity delay—not a
   reason to change the capacity threshold.
3. Inspect Parakeet pod readiness, restarts, GPU utilization, GPU OOM events,
   queue duration, latency, and request error rate. Correlate with production
   traffic before declaring user impact.
4. Allow the HPA to add healthy replicas first. If it has reached its configured
   maximum with sustained demand, change the deploy-owned capacity only after
   confirming node and GPU availability, then use the normal Parakeet Helm
   rollout.

Do not force-scale, change alert thresholds, or state that users are affected
from this metric alone. The alert measures serving headroom; request errors,
latency, and queueing provide the user-path corroboration.
