# Release and recovery

This PR implements the provider change and the capacity needed to serve it. No production release has been executed. The existing production release eligibility and explicit approval boundary still apply; merging alone is not evidence of deployment.

## Routing contract

Single-channel live sessions in the 25 supported TDT v3 languages, including default multilingual sessions, select Parakeet first, then Modulate and Deepgram cloud on failure. Unsupported language/feature combinations retain supported vendor routing. Multi-channel routing remains outside the first Parakeet-primary cohort. Supported explicit-provider and BYOK paths retain their contracts; an explicit Parakeet request does not override a capability exclusion.

PTT selects Parakeet then Modulate; there is no Deepgram PTT dispatcher. Batch retains Parakeet then Modulate with its separate multilingual TDT pipeline. The stream deployment explicitly loads TDT v3 through the buffered streaming decoder; it does not rely on the batch instance.

Both initial connection and mid-session rebuilds must reach the vendor fallback chain. Previously failed providers are excluded within a session. Existing replay, timestamp, speaker and finalization semantics remain part of the acceptance contract; a connection-only test cannot establish transcript continuity. Retain shared `record_fallback` telemetry.

## Release ordering

1. Resolve the intended backend source and immutable Parakeet image, and obtain passing realtime qualification evidence for that exact image and configured admission capacity.
2. Verify or promote the qualified digest into the target environment registry, checking that copying preserves its digest. Check GPU quota and the dedicated node pool's ownership, total warm floor and maximum including surge. Create or verify capacity before changing routing; keep existing batch capacity independent.
3. Extend the existing Prometheus adapter while retaining unrelated live rules and its chart version. Deploy the dedicated stream Helm release with the immutable image.
4. Require the configured warm floor to be updated, ready and available, with actual model warmup health, ready service endpoints and valid per-pod stream metrics. Pending replicas and empty metric responses cannot pass.
5. Resolve the internal load-balancer endpoint for Cloud Run and cluster service DNS for backend-listen. Publish the dedicated runtime URL only after capacity validation. The listener image must contain this PR's fallback implementation before it receives the primary configuration.
6. Promote through the existing environment's deployment gate and verify the serving vector and real transcription path. Recover the prior compatible route/vector on a failed deployment or bake.

The executable release helper and workflow are authoritative for supported flags and operations. Run its source-only plan mode during review. This document is not an instruction to invoke a production command during PR preparation.

## Promotion evidence

Attach the exact-source GPU run, image digest, per-concurrency latency/completion/VRAM results, routing tests and independent review to the PR. Record the capacity floor and actual ready node/pod counts at release. Keep customer load samples and negotiated rates private; public charts contain planning envelopes.

The sustained fixture test proves a bounded serving workload. It does not establish representative accuracy, diarization, accents/noise, client receipt/render, 99.9% reliability or region-failure tolerance. Use the [benchmark plan](benchmark-plan.md) for those distinct claims. Retain enough vendor concurrency/rate quota to absorb the entire eligible workload during a Parakeet outage.

## Stop and recover

Stop promotion on missing qualification, insufficient warm capacity, missing custom metrics, exhausted fallback quota, unsupported-language routing, silent loss, duplicate committed text or wrong-speaker identity. Do not raise the admission cap to make readiness or capacity checks pass.

Before routing changes, preserve the previous backend image/configuration and Parakeet/adapter Helm revisions. Recover new sessions to the known-good vendor route and drain existing healthy sessions. Environment-backed routing changes require rollout and are not instantaneous feature flags. Keep GPU and vendor resources during recovery until the restored serving path has been verified; deleting capacity is not a routing rollback.

Observe a representative peak after release and separately exercise initial and midstream fallback, rolling termination and one-node loss. Only live serving evidence can establish completion of the migration. GitHub owns review, CI and release status; these docs do not create a second status tracker.
