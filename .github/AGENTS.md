# GitHub Workflow Agent Guide

These rules apply to GitHub Actions workflows and custom actions under `.github/`.

## CI/CD Deploy Safety

- Every workflow that mutates a persistent Cloud Run service/job, GKE Helm
  release, or traffic/promotion state must use a workflow-level concurrency
  group scoped to the exact target and logical environment. Manual and
  automatic entry points for the same target must resolve to the same group.
- Deployment group names are a cross-workflow API. Keep them aligned with
  `.github/scripts/check-deployment-concurrency.py`; use
  `cancel-in-progress: false` so a newer run cannot interrupt a remote mutation
  or a staged validation/traffic promotion.
- `deploy-backend-stack-<environment>` intentionally covers the four backend
  Cloud Run services, traffic repair, backend-listen, LLM gateway, and
  backend-secrets. Those paths share mutable releases, while unrelated services
  retain their own groups and may deploy in parallel.
- GitHub concurrency is serialization, not a FIFO queue: only one pending run is
  retained and ordering is not guaranteed. Deploy workflows must not assume
  that every intermediate commit will run.
- Use immutable image tags for deploys. Build and push the short SHA tag, then deploy that exact tag.
- Development desktop-backend acceptance signs Firebase probe tokens via IAM `signJwt` on `vars.FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT` (a `@based-hardware` SA matching `FIREBASE_AUTH_PROJECT_ID`); the deploy identity needs `roles/iam.serviceAccountTokenCreator` on it. Never stage service-account key files in runners or deploy them as runtime configuration.
- Do not deploy Cloud Run services from an untagged image path; use `image:...:${SHORT_SHA}` so revisions show the source commit.
- Do not let Helm chart-only deploys reset GKE workloads to `latest`. Preserve the currently deployed immutable tag or require an explicit tag input.
- Every GKE Deployment deploy must wait for rollout completion with `kubectl rollout status ... --timeout=...` and fail on timeout.
- For chart-only backend-listen deploys, fail if the current deployed image tag is missing or `latest`; use the backend deploy workflow to establish an immutable tag first.
- Keep rollout checks close to the deploy step they verify, especially for `backend-listen`, `pusher`, `llm-gateway`, `parakeet`, `diarizer`, and `vad`.
- Use `backend/scripts/deploy_status_report.py` as a strict gate on success paths; use it with `|| true` only after a primary rollout/traffic command already failed.
- Full backend deploys must derive one immutable Cloud Run plus `backend-listen` release vector and run `backend/scripts/verify_backend_release_vector.py` after traffic promotion; a mixed or partially applied serving vector must fail the workflow and emit evidence for a retry.
- Before restarting GKE workloads that depend on `backend-secrets`, wait for ExternalSecret Ready and run `backend/scripts/verify_k8s_secret_keys.py`; never print secret values.
- Before any pusher Helm mutation, verify `${ENV}-omi-backend-config` exists so a missing shared runtime ConfigMap cannot replace the healthy replica.
- Backend deploy workflows may only run Firestore index readiness through the shared `.github/actions/firestore-readiness` composite, staged from immutable `github.workflow_sha` into .github/firestore-workflow after the runtime-source checkout and bound to the exact checked source SHA before any image build, push, or rollout. It `--check-only`s against `RUNTIME_GCP_PROJECT_ID` with `GCP_FIRESTORE_READONLY_CREDENTIALS` (set in both `development` and `prod` Environments) in an isolated gcloud config; JIT QA lanes use `env.QA_PROJECT`/`env.QA_FIRESTORE_DATABASE` instead. `gcp_backend_listen_helm.yml` runs the gate only when its explicit-tag path resolves `env.BACKEND_LISTEN_SOURCE_SHA`; kept-tag and rollback lanes replay an image already served in the same environment, the index pipeline is create-only, and rollback must not gain new failure modes. A failed gate may upload only a locally revalidated, bounded, redacted proposal. Index writes belong solely to `gcp_firestore_indexes.yml`, which keeps its own `firestore-schema-${environment}` lock and the typed `APPLY_FIRESTORE_INDEXES` confirmation. Detail: `agent-docs/firestore-queries-and-indexes.md`.
- When editing workflows, keep `actionlint` coverage in CI so YAML and GitHub expression mistakes fail before merge.
