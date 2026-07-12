# Backend v0.12.70 Production After-Action

This record preserves the July 11, 2026 `.70` production rollout evidence and
the decisions that are easy to lose between incidents. The reusable procedure
lives in [backend-deploy-rollout-safety.md](backend-deploy-rollout-safety.md).

## Release identity and current status

| Item | Value |
| --- | --- |
| Desktop release | `v0.12.70+12070-macos` |
| Desktop source | `2bdd18a7e397b4c7aab8199443def178c0e9b0e0` |
| Initial backend release source | `b939eab902c88abc6cc64501747485d6aec428d3` |
| Initial backend child digest | `sha256:d8f84c25c9e6c73bad08d118da41b9cd141a78a523e75c4f15edaf595dabeb65` |
| Initial successful guarded resume | GitHub Actions run `29167029709` |
| Contention-hotfix source | `f92baff14418bfa46b64ac84f1eb64715855d32e` |
| Contention-hotfix child digest | `sha256:9738b4594a9d8b59a5ee8cbe09487f12668f606f5738e612ee27cc11df364bcc` |
| Successful candidate preparation | GitHub Actions run `29172379402`, attempt 2 |
| Successful hotfix resume | GitHub Actions run `29173381925` |
| Current serving revisions | `backend{-integration,-sync,-sync-backfill}-f92baff-29172379402-2` and `backend-f92baff-29172379402-2` |

The runtime-project, signing, and backfill-memory failures are closed. Capacity
is mitigated, not closed: the zone-B pool and NEG are live, and its autoscaler
ceiling was raised from 5 to 7 after a fresh zone-A stockout during hotfix
preparation. The observed `5 + 7` or `4 + 8` load-balancer counts are dynamic
healthy NEG endpoint distributions, not node-pool bounds. IaC ownership,
provider-stock-aware preflight, and headroom alerts remain required.

The post-cutover soak then exposed a separate release-introduced Firestore
contention class on concurrent memory-ledger and action-item transactions. The
no-schema bounded-retry hotfix is now deployed through the guarded prepare and
resume lanes. All four services converged to the exact `f92baff...-2` revisions
at 100% in spec and status with no traffic tags; the public health endpoint is
200, backend-listen is 12/12 with zero restarts, and both zonal NEGs are fully
healthy. Do not confuse this application-write fix with the signed-URL or
capacity work, and do not treat the live capacity mitigation as durable until
the follow-up controls land.

## What happened

| Phase | Evidence and decision |
| --- | --- |
| GKE rollout stalled | New backend-listen pods emitted `RESOURCE_PROJECT_INVALID`. The prod GitHub environment omitted `RUNTIME_GCP_PROJECT_ID`, so Helm rendered an empty runtime project. Added `RUNTIME_GCP_PROJECT_ID=based-hardware`, `API_URL=https://api.omi.me`, and `CONTROL_PLANE_URL=https://api.omi.me`; rendered dev/prod validation found no other required value missing. |
| Capacity investigation | Zone `us-central1-a` had a real `n4-highcpu-4` stockout. Repeated rollout/autoscaler retries amplified demand, so the incident was real scarcity plus artificial retry pressure, not stale capacity numbers alone. Shrinking 1.5 CPU / 2 GiB pods would not add a safe third slot per node without unvalidated CPU and memory cuts. |
| Reversible capacity repair | Added `backend-listen-pool-v2-b` in `us-central1-b` (`n4-highcpu-4`, initially autoscaling max 5, labels `env=prod`, `service=backend-listen`, `type=high-cpu`) and attached the zone-B NEG to the existing global backend service. The pool and NEG attachment remain live and require IaC ownership. |
| First Cloud Run cutover | `b939eab-1` passed health/OpenAPI checks, then real `GET /v1/users/people?include_speech_samples=true` traffic returned 500 because compute ADC cannot sign GCS V4 URLs. Backfill showed the same signing failure and exceeded its 512 MiB limit. Rolled all four services back in reverse dependency order and verified old traffic at 100%. |
| Failed legacy credential recovery | `b939eab-2` restored Secret Manager `GOOGLE_APPLICATION_CREDENTIALS:1`, but that secret contains only the filename `google-credentials.json`; the file is absent from the image. Integration failed startup before any traffic changed. Tags were cleaned and old traffic remained intact. |
| Correct credential recovery | Verified, without printing it, that `SERVICE_ACCOUNT_JSON:1` is enabled service-account JSON for the runtime project and can generate all required V4 signature fields. Bound that numeric version to all four services and removed the deployed legacy GAC binding. Startup materializes `/tmp/omi-google-credentials.json` with mode 0600 and sets process-local GAC; the temporary path is not a Cloud Run secret binding. |
| Backfill resource repair | Raised backfill from 512 MiB to 1 GiB at concurrency 1. The corrected candidate processed real jobs without OOM or 5xx. |
| Resume workflow repair | Added immutable source/digest/suffix validation, zero-traffic readiness checks, tag identity and cleanup, GKE dwell gates, dependency-order promotion, per-service reconciliation, and reverse-order rollback. Removed a duplicate `--remove-secrets=GOOGLE_APPLICATION_CREDENTIALS` path that gcloud would reject on future full deploys. |
| Corrected cutover | Run `29167029709` promoted integration, backfill, sync, then backend. Candidate and live contracts matched `SERVICE_ACCOUNT_JSON:1`, runtime project, resources, source, and digest; GAC was absent. |
| Real-traffic soak | The signed-URL path first produced at least 90 successful people responses and backfill produced at least 63 successful responses, both with zero related 5xx/OOM. Concurrent `.70` memory and action-item writes exposed Firestore pre-commit `ABORTED` contention that the SDK does not retry. In the later `21:12:18Z`–`22:32:56Z` pre-hotfix baseline, people produced 281×200 with zero signing 500s, backfill produced 260×200 plus five expected 429s with zero 5xx/OOM, and no new memory/action contention occurred. The three remaining backend 500s were pre-existing classes: two `/v2/messages` index-entry-limit failures and one app-enable closed-transport failure. |
| Contention hotfix | Added a bounded fresh-transaction outer retry for direct or causal Firestore `Aborted`, isolated the SDK transactional wrapper per call, preserved idempotency, and mapped exhausted contention to a generic 503. Memory ledger and action-item concurrency/error-path tests, runtime validators, scanners, type checking, and an independent review passed. |
| Hotfix prepare attempt 1 | Run `29172379402`, attempt 1, created zero-traffic `f92baff-29172379402-1` candidates for backend, sync, and backfill; integration was never created. A fresh zone-A `n4-highcpu-4` stockout plus zone B at its max-5 ceiling delayed the last pod until the edge of the 900-second wall-clock gate. The required fresh 120-second dwell timed out at `23:56:50Z`; Cloud Run traffic never moved from `b939eab-3`. The workflow targeted snapshot Helm revision 186, recorded the restored old image as deployed revision 188, converged at `00:00:57Z`, and held the mandatory rollback dwell through `00:03:12Z`. |
| Capacity adjustment for retry | Raised only `backend-listen-pool-v2-b` autoscaling max from 5 to 7 with `BALANCED` location policy. Zone B reached 7/7 Ready nodes before retry; no pod requests, HPA bounds, or production traffic were weakened. Keep max 7 until IaC owns it or representative headroom evidence supports a reviewed change. |
| Hotfix prepare attempt 2 | Re-running the same Actions run produced suffix `f92baff-29172379402-2`, proving that `GITHUB_RUN_ATTEMPT` is part of candidate identity. GKE deployed Helm revision 189 and held 12/12 Ready with zero restarts. All four exact candidates were Ready, latest-created, same-digest, exact-source, and zero traffic; the prior `...-1` revisions remained zero traffic. |
| Hotfix guarded resume | Run `29173381925` revalidated GKE, activated and smoke-tested the URL-enabled tagged candidates, identity/warmup-validated the URL-disabled backend, removed all tags, reconfirmed GKE, then promoted integration, backfill, sync, and backend in order. After backend promotion, exact-revision attribution and the control-plane health/OpenAPI/405 smoke passed. Backend converged at `00:34:09Z`; the run completed successfully at `00:34:36Z` with no rollback. |

## Root causes and durable guards

| Failure class | Root cause | Guard landed or required |
| --- | --- | --- |
| Wrong GKE project | Required prod environment value was absent and rendering allowed it to reach rollout | Exact rendered dev/prod identity contract and pre-deploy validation |
| Unschedulable surge | Zonal stockout plus retry-amplified demand; the alternate pool then reached its configured max 5 | Cross-zone pool/NEG with live max 7 now; IaC, topology spread, alternate-zone or machine-family headroom, stock-aware schedulability preflight, and saturation alerts next |
| Signed-URL 500s | Health probes never exercised signing; compute ADC lacks a private signing key | Numeric `SERVICE_ACCOUNT_JSON` interim binding, GAC removal, semantic credential/V4 probe, and eventually keyless IAM `signBlob` |
| Backfill OOM | 512 MiB was below observed 517–561 MiB real-job use | 1 GiB reversible mitigation; capture p95/peak before retuning |
| Unsafe fresh deploy | Ordinary deploy flow could not prove candidate identity or reconcile every service | Explicit fresh-image prepare lane leaves Cloud Run at zero traffic while rolling GKE safely, then hands immutable identity to guarded resume; consolidate the two dispatches later |
| Write contention | New per-user ledger/control transactions can collide; Firestore 2.20 retries commit-time `Aborted` but not `Aborted` raised during transactional reads | Fresh-transaction bounded outer retry for direct/causal `Aborted`, per-call SDK wrapper isolation, idempotency tests, 503 exhaustion mapping, and a longer-term hotspot/serialization design |

## Change and rollback ledger

| Change | Classification | Revert or replacement condition |
| --- | --- | --- |
| Zone-B backend-listen pool, max 7, and NEG attachment | Live incident mitigation; backend infrastructure owns it until codified | Do not remove or lower while zone A remains stock-constrained. Capture the pool, autoscaler max, NEG, backend-service attachment, topology policy, and quota in reviewed IaC before the next backend deploy; then use the IaC rollback plan. |
| Prod runtime-project/API/control-plane variables | Required permanent configuration | Revert only with a coordinated topology/API contract change and rendered validator update. |
| `SERVICE_ACCOUNT_JSON:1` | Interim signing credential | Replace only after the runtime identity has narrow self-`signBlob` permission and authenticated signed-URL probes pass without a private key. Rotate/remove the key after migration. |
| Backfill 1 GiB / concurrency 1 | Bounded resource mitigation | Change only from representative memory telemetry with headroom and an OOM rollback trigger. |
| HPA normal bounds | Restored after rollout | No temporary HPA increase remains. |
| Attempt-1 zero-traffic candidates | Safe inactive deployment residue | Keep zero traffic. Add a revision retention/cleanup policy, then remove only after proving no spec/status traffic or tags reference them. |

## Production acceptance evidence

For the initial corrected cutover, acceptance required all of the following:

- four exact `b939eab-3` revisions at 100% in Cloud Run spec and status;
- exact initial source and digest, `GOOGLE_CLOUD_PROJECT=based-hardware`,
  `SERVICE_ACCOUNT_JSON:1`, and no Cloud Run GAC binding;
- integration 2 GiB, backend/sync 8 GiB, backfill 1 GiB at concurrency 1;
- no temporary traffic tags and the backend default URL still disabled;
- API health 200, backend-listen 12/12, HPA 12/12, no restart/OOM/unready
  signal, and both zones healthy behind the load balancer;
- zero people signed-URL 500s and zero signing/credential errors;
- real backfill work at 200 with zero OOM/5xx.

The contention hotfix added a second acceptance gate: after its cutover, require
zero `outcome=exhausted`, allow bounded `outcome=recovered`, and watch affected
write-route 5xx, latency, executor saturation, partial-write evidence, signed
URLs, backfill, GKE, and load-balancer health. Roll back the hotfix revision on
any exhausted same-class request, partial write, or material p95/thread-pool
regression. The immediate post-cutover sample contained thousands of backend
requests with zero 5xx; action-item and signed-URL requests were 200, real
backfill jobs were 200, and no contention-exhaustion, signing, OOM, GKE, or NEG
failure signal appeared.

The bounded hotfix soak covered `00:34:09Z` through `00:46:06Z` (11m57s) on the
exact `f92baff-29172379402-2` revisions:

- action items produced 81 list GET 200s, 51 item GET 200s, 11 POST 200s, and
  one PATCH 200; four OPTIONS requests returned 405, with no 5xx. POST p95 was
  0.762s and the maximum was 0.799s. The write-path sample had no contention
  retry, recovered, exhausted, `ABORTED`, or partial-write signal;
- no `/v3/memories/batch` request occurred naturally in this short window, so
  its same-class write behavior remains supported by the concurrent regression
  suite rather than claimed as production-traffic evidence;
- authenticated people requests with `include_speech_samples=true` produced
  33×200 with zero signing/credential error, and backfill processed 33 real
  `/v2/sync-jobs/run` requests at 200 with zero OOM/5xx;
- the backend handled 23,926 requests with zero HTTP 5xx, and all four exact
  revisions produced zero severity-ERROR log entries. Backend p50/p95/p99 were
  4ms/112ms/554ms; every request above 10s was a successful 200 on an existing
  messages, voice-messages, or agent-keepalive path, not a failure cluster;
- backend-listen and HPA remained 12/12, all pods were Ready with zero
  pending, terminating, or restarting pods; zone-A and zone-B NEGs remained
  5/5 and 7/7 healthy, the zone-B max-7 pool was Running, and public
  `/v1/health` remained 200.

## Ordered follow-up

### P0: before the next production backend deploy

1. Preserve the bounded Firestore contention hotfix's exact rollout and soak
   evidence, and keep denominator-based recovered/exhausted alerts current.
2. Use and verify the new zero-traffic `prepare-cloud-run` plus guarded resume
   path; then consolidate those two explicit phases into one fail-closed fresh
   deploy without reviving the ordinary raw traffic-shift path.
3. Put the zone-B pool, autoscaler max 7, NEG, backend-service attachment,
   topology policy, and alternate-zone or machine-family headroom in IaC.
4. Make credential semantics fail closed: numeric version enabled, accessor IAM,
   service-account JSON shape, dummy V4 signing, candidate binding, and GAC
   absence without printing secret values.
5. Add an authenticated candidate smoke that generates and fetches a real
   signed URL.

### P1: reliability and observability

1. Pin GKE to immutable digests and verify pod `imageID`.
2. Add NEG/LB health, websocket acceptance, 502, reconnect amplification, and
   request-denominator gates.
3. Remove Stripe/network work from startup and enforce a measured cold-start SLO.
4. Add a phase-aware status report so pre-cutover smoke failures are not obscured
   by expected zero-traffic diagnostics.
5. Preserve first-failure revision conditions and startup logs before tag cleanup.
6. Add denominator-based alerts for memory/action-item contention and test
   concurrent same-user writes in the Firestore emulator.
7. Make the fast-unit duration gate deterministic across the file-isolated
   runner. The current 120 ms CPU threshold produces unrelated first-import
   failures during full parallel runs; preserve exact serial reruns as evidence
   now, then fix the harness instead of growing incident-time allowlists.
8. Add a durable prepare-run lease/finalizer or an operator cleanup command for
   force-canceled GitHub jobs. Step-level `failure()` rollback protects ordinary
   failures but cannot run after a hard cancellation.
9. Emit every GKE-dwell reset reason, the longest healthy interval, HPA state,
   pending pods, and remaining wall-clock budget. Alert on pool-at-max,
   unschedulable pods, fresh stockouts, HPA demand above schedulable slots,
   unhealthy NEGs, and dwell timeout rate.
10. Add an explicit retention/cleanup policy for superseded zero-traffic
    candidates from failed or rerun prepare attempts.

### P2: security and simplification

1. Replace private-key signing with narrow IAM `signBlob`, rotate the interim
   key, and remove `SERVICE_ACCOUNT_JSON` from runtime.
2. Build a restricted validation route for default-URL-disabled backend
   candidates.
3. Add one verifier for queue, IAM, TTL, log metric, alert, and notification
   configuration.
