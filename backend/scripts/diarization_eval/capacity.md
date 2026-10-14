# Community-1 final-pass capacity receipt

Measured 2026-10-13 UTC on the dev GKE NVIDIA L4, one request at a time through
`/v2/diarization`, including overlap extraction and v2 centroid naming evidence.
The API received raw 16 kHz mono PCM16. Public AMI EN2002a/b/c/d Mix-Headset
recordings were concatenated chronologically and cropped to 5/30/120 minutes;
no short clip tiling, private audio, production API or backend writer was used.

| Minutes | Inference seconds | Request seconds | RTF | Peak CUDA allocated GiB | Peak whole-device GiB | OOM |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 5 | 8.916 | 8.959 | 0.02972 | 1.616 | 6.312 | No |
| 30 | 53.156 | 53.395 | 0.02953 | 1.616 | 6.312 | No |
| 120 | 225.952 | 226.886 | 0.03138 | 1.616 | 6.312 | No |

All returned four voices and four centroids. Ten seconds warmed the model first;
model load and public download are outside timed cells. Pipeline 4.0.3, Torch and
torchaudio 2.8.0; Python 3.12.3 in an isolated venv on the existing dev Parakeet
pod. Shipping diarizer image uses Python 3.11: these are API/pipeline capacity
measurements, not an immutable-image qualification. Shared GPU baseline was
4052 MiB. A per-process 40% CUDA memory cap protected its service; these runs
stayed well below that cap. Device peak includes the other process and CUDA
allocator reservations. Afterward device memory returned to 4052 MiB.

At 6,300 audio-h/day and measured 45% multi-speaker share (range 12–50%), 2,835 h/day × worst
measured RTF 0.03138 requires 89.0 GPU-h/day: 3.71 continuously busy workers.
Use the **separate batch app/deployment**, preserving the concurrent live
embedding/v1 endpoint on its own GPU. Only batch inference holds a lock; upload
and decoding do not. Same-GPU live embedding latency is not qualified by this run. Use **six L4 batch replicas** as an initial floor (62% average inference occupancy),
**max eighteen**, one inference worker per pod, two waiting uploads. This excludes
triage, existing embedding traffic, burst distributions, network and retries;
qualify those during the gated cohort rather than treating arithmetic as an SLO.

Enable `podMonitoring`, configure a custom-metrics adapter for
`omi_diarization_v2_queue_depth`, and set `autoscaling.queueDepthAverageValue=1`.
The metric counts running plus admitted waiting/upload work. Use scale-up delay
0s and scale-down stabilization 900s, with gradual scale-down. Alert on rejection,
failure, queue saturation and p95 end-to-record latency. Raise
`backendConfig.timeoutSeconds` to 900 before ingress-backed long requests.
Chart defaults preserve one replica, disabled HPA/metrics discovery and 30s timeout.

The same additive image contains separate embedding/v1 and batch entrypoints.
Production installation now requires a dedicated tainted L4 pool, in-cluster
Prometheus scrape/adapter mapping, a separate internal ingress reachable from
Cloud Run, and the registered model-free built-image import/decode probe.
The opt-in batch overlay starts at **one replica for David-only shadow**. Raise
the floor to six/max eighteen only after cohort qualification. Exact lead-only
commands, metric checks, separate cohort env bindings and rollback are in
[`batch_install.md`](batch_install.md). No infrastructure or flag is applied by
these prerequisites.
Lead-local raw receipts and scripts live in
`/Volumes/Ephemeral/scratch/pyannote-final-pass-2026-10-13/`. The dev benchmark
added no node after GCE capacity rejection; it used existing capacity. Cleanup
removes only its owned Job (already removed) and `/tmp/sol-pyannote-capacity`.
