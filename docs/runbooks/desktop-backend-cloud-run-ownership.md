# Desktop backend production ownership

## Authority

Production `desktop-backend` is a Cloud Run service. There is no checked-in
production deployment authority for a new desktop-backend revision:
`.github/workflows/desktop_promote_prod.yml` is a Stable artifact-pointer
promotion and may use the existing backend only to bridge a qualified release;
it must not deploy Cloud Run. Development delivery is owned by
`.github/workflows/desktop_backend_auto_dev.yml`.

Do not dispatch the development workflow against production or treat a Stable
pointer promotion as a backend rollout. A production backend change requires a
separately reviewed, protected production deployment workflow with explicit
image identity, Cloud Run traffic verification, rollback evidence, and owner
approval before it can be performed.

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
   public health responses.
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
