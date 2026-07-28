# Desktop backend production ownership

## Authority

`desktop-backend` is a separate Cloud Run release vector from the Python backend
and GKE listener vector. It has its own binary identity, acceptance boundary,
traffic lock, and rollback surface:

- `.github/workflows/desktop_backend_auto_dev.yml` owns development delivery
  from the current head of `main` only.
- `.github/workflows/desktop_backend_prod.yml` is the protected, manual
  production deployment authority for one exact merged-main SHA.
- `.github/workflows/desktop_backend_recover_prod.yml` is the protected,
  manual traffic-only recovery hatch for one exact retained Ready revision.
- `.github/workflows/desktop_promote_prod.yml` advances only the qualified
  macOS Stable artifact pointer and legacy release bridge. It never deploys
  Cloud Run.

Do not add desktop-backend to the Python backend release-vector verifier. The
two serving planes have different build, rollback, and release lifecycles.
Compatibility is coupled only where it is real: macOS Beta qualification and
Stable promotion require the live desktop-backend to advertise the desktop chat
contract version expected by the app.

## Candidate acceptance and traffic

Both deployment workflows build a digest-pinned image, deploy an exact tagged
revision at zero traffic, wait for `Ready=True`, and verify the revision image
digest before probing it. The candidate must then prove:

1. `/health` reports the admitted backend SHA, lane, and chat contract.
2. `/ready` and a read-only legacy update query prove Redis and Firestore access.
3. A streaming public-web turn reports at least one provider web-search request,
   returns answer text, and terminates within the bounded response budget.
4. A plain follow-up in the same message history completes without reusing web
   search.
5. The OpenAI and Gemini managed realtime-provider probes complete.

Only then may the workflow re-resolve the candidate tag and route 100% traffic.
The prior 100% revision is captured before the candidate deploy. A failed
post-shift serving check restores that revision and verifies the read-back.
Development `candidate_only` runs intentionally stop at zero traffic.

The realtime-provider probes prove the backend/provider dependency boundary;
they are not a substitute for macOS push-to-talk lifecycle qualification. App
PTT, microphone, transcription, cold-start, replacement-turn, and UI
terminalization behavior remain owned by the macOS test and qualification
lanes.

Production dispatch requires `confirm=deploy-desktop-backend-prod`, a reason,
an exact merged-main SHA, and a successful first-attempt Release Eligibility
proof. The standard repository break-glass inputs may waive only that proof;
they never waive merged-main admission or candidate acceptance.

Cloud Run rollback steps cannot run after total runner loss. During an incident,
dispatch `desktop_backend_recover_prod.yml` with the exact retained revision,
`confirm=recover-desktop-backend-prod`, and a reason. The recovery workflow
validates project, canonical service URL, revision ownership, `Ready=True`, and
post-shift health under the same non-cancelling production lock.

Runtime Google authentication uses the Cloud Run revision service account and
metadata server. Service-account JSON must never be copied into an image layer.
Firestore access plus the managed Gemini path are exercised on the zero-traffic
candidate before traffic can move.

Local macOS development remains intentionally separate: `desktop/macos/run.sh`
builds and runs `Backend-Rust/target/release/omi-desktop-backend` on localhost
when the explicit optimized local mode is selected. Do not replace that local
workflow with a Cloud Run dependency.

## Retired GKE plane

`desktop/macos/Backend-Rust/charts/desktop-backend/` is retired. It must not be
reintroduced, and `desktop-api.omi.me` must not be recreated as a GKE Ingress,
NEG, managed certificate, DNS target, Helm release, Deployment, Service, or
ServiceAccount for the desktop backend. The production data-plane routing guard
rejects restoration of that chart.

Do not infer that a checked-in deployment reference proves live ownership. Before
any operational change, inspect the serving Cloud Run revisions and complete
traffic allocation, then separately inspect the named live GKE and DNS resources.
Never read Secret payloads during this audit.

## Retirement and rollback procedure

A production GKE retirement is a separately authorized operation and starts only
after this source guard is merged. Before deleting anything:

1. Confirm the current signed stable and beta macOS artifacts route to the
   canonical production Cloud Run desktop-backend URL.
2. Confirm both production and development Cloud Run desktop-backend services
   are Ready, serve their expected revision at 100% traffic, and have successful
   public health responses. Use the deployment evidence artifacts to bind source
   SHA, image digest, candidate tag, workflow run, and acceptance results.
3. Inspect a meaningful recent load-balancer log window for
   `desktop-api.omi.me`, reporting aggregate route, status, and user-agent
   classes only. Stop if supported desktop traffic or credible client use appears.
4. Determine the authoritative DNS owner and exact record set. Delete a record
   only after proving it targets solely the retired GKE load balancer.
5. Inventory the exact Helm release/resources, non-Helm Ingress, managed
   certificate, NEG/backend service, and DNS records. Preserve non-secret
   rollback identifiers and manifests before mutation.

Use the authoritative owner for each resource and delete only the identified
stale production GKE plane. Do not alter Cloud Run services, local development
tooling, shared Secrets, IAM, unrelated DNS, release pointers, or desktop app
artifacts. If removal has unexpected impact or ownership is ambiguous, stop;
use the preserved rollback material only to restore the retired GKE path.

After cleanup, observe real traffic for at least 30 minutes. Confirm Cloud Run
health/traffic, artifact routing, aggregate macOS outcomes, Cloud Run response
classes, and absence (or completed deletion) of the GKE workload, ingress,
certificate, NEG/backend service, and DNS records. Existing watchdogs must not
retain stale desktop-backend alerts; change only monitoring that exclusively
covered this retired plane.
