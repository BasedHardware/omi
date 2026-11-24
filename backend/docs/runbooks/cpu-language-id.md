# CPU language ID rollout handoff

Owner: planscost. Review by 2026-11-30. David approved the CPU LID separation on
2026-11-03. The rollout lead owns deployment; this change was tested offline only.

## Serving contract

`HOSTED_LID_API_URL` is an optional HTTP base URL. If nonempty it takes precedence
for `/v2/language`, even with `STT_GPU_FLEET_OFF=true`. It does not enable ASR or
change provider admission. Empty/unset retains the shared Parakeet endpoint while
the fleet is on, or the vendor LID path while the fleet is off. A failed CPU call
returns to the existing vendor path without retrying the GPU endpoint.

The independent `prod-omi-parakeet-lid` release uses the Parakeet image with
`PARAKEET_DEVICE=cpu`, `PARAKEET_LID_ONLY=true`, `PARAKEET_LID_MODEL=whisper-base`.
It skips batch/stream ASR, embeddings, stream warmup and the batch engine. Only
`/v2/language`, `/health`, and `/metrics` remain. `/health` stays 503 until Whisper
preloads successfully, including when its model is disabled or fails to load.
There is no Hugging Face token dependency for the public Whisper-base model.
Model fetching still requires outbound access or a prepopulated cache.

## Sizing and acceptance

CPU endpoint throughput is **unmeasured**: the local Hugging Face cache contains
faster-whisper-base, not the Transformers `openai/whisper-base` weights used by
this image. No model was downloaded. Mac CPU timing would also not qualify GKE
CPU performance. The initial bounded budget is four to sixteen pods, each with
2 vCPU, 4 GiB, two OpenMP/MKL threads, and one LID request at a time. HPA targets
60% CPU; overload returns 503 so the existing paid vendor path remains available.
This reserves 8 vCPU / 16 GiB at the floor and caps at 32 vCPU / 64 GiB
(excluding one rolling-update surge pod). Node placement uses the existing
backend-listen CPU labels (`service=backend-listen, env=prod, type=high-cpu`),
never a GPU request or toleration. The lead must check spare CPU pool capacity;
these values do not authorize adding nodes or raising the cap.

Inference sees at most 30 seconds at 16 kHz, using float32 on CPU; Whisper pads
short clips to its fixed encoder window. With measured mean service time S
seconds, the serial ceiling is 4/S to 16/S requests/s. At 60% utilization, budget
about 2.4/S to 9.6/S requests/s. These are planning formulas, not measured rates.
The backend retains its 6-second read timeout (2-second connect); qualify p95
below 3 seconds and p99 below 6 seconds on representative 30-second speech and
sustained peak probe arrival rate before switching traffic. CPU HPA alone does
not prove low busy/fallback rates when requests arrive in bursts.

## Lead steps (do not reverse the order)

1. Publish the Parakeet image containing this commit using the approved image
   build path, and record its immutable tag/digest. Existing images do not contain
   LID-only mode. Avoid an automatic backend URL release before the CPU service
   is ready. No streaming-fleet shutdown or cohort expansion is authorized here.
2. On the rollout lead's authorized cluster context, install a **separate** release:

   ```bash
   helm upgrade --install prod-omi-parakeet-lid backend/charts/parakeet \
     --namespace prod-omi-backend \
     -f backend/charts/parakeet/prod_omi_parakeet_lid_values.yaml \
     --set-string image.tag=<published-tag-containing-this-commit> \
     --wait --timeout 20m
   ```

   Use chart defaults plus this values file only. Do not reuse streaming prod or
   fleet-off values. Confirm ready replicas, CPU placement, `/health`, `/metrics`,
   and the `/lid` route on `prod-omi-internal-gateway`. The release has its own
   BackendConfig and Service names, avoiding ownership collisions with streaming.
3. From the real backend VPC path, POST a known 30-second WAV to
   `http://172.16.160.20/lid/v2/language`. Verify meaningful language probabilities,
   latency under the unchanged caller deadline, and ASR/stream endpoints absent.
   Run the sizing acceptance above on the actual serving image; retain vendor
   fallback if busy/errors/latency exceed budget. This IP is the checked-in
   shared internal Gateway binding, not a newly allocated address.
4. Release the backend URL **after** the CPU service passes acceptance. The prod
   runtime overlay and the listen and pusher charts hold `HOSTED_LID_API_URL` empty
   until then; set it to `http://172.16.160.20/lid` on backend,
   backend-sync, backend-sync-backfill, backend-integration, backend-listen and pusher.
   Regenerate `python3 backend/deploy/compose_runtime_env.py`, use normal backend
   release workflows/renderers, and verify the running releases receive the URL.
   The dev declaration remains empty. Do not deploy this backend overlay first.
5. Keep `omi_stt_language_gate_shadow_total` dangerous-direction disagreement
   (self Parakeet, vendor unsupported at >=0.9 confidence) at or below the existing
   0.1% threshold; keep `omi_stt_language_gate_enforced_total` route distribution
   and vendor_fallback share no worse than baseline. Watch
   `omi_stt_language_gate_self_total{outcome}` and
   `parakeet_language_id_requests_total{status}` for unavailable, busy and timeout
   regressions, and `parakeet_language_id_duration_seconds` p95/p99. Compare route
   shares and paid fallback spend with baseline before any auto-language ramp.
   These observations must also remain clean after the separately approved
   fleet-off transition; this PR does not change that switch or ramp percentages.

Rollback: unset/empty `HOSTED_LID_API_URL` on the affected callers, update the
prod overlay and compose it so the next release preserves the rollback. With the
GPU fleet off this restores vendor probes. With it on this restores the shared
Parakeet endpoint. The CPU release can remain idle until the lead removes it.
