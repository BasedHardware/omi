# GitHub Workflow Agent Guide

These rules apply to GitHub Actions workflows and custom actions under `.github/`.

## CI/CD Deploy Safety

- Use immutable image tags for deploys. Build and push the short SHA tag, then deploy that exact tag.
- Do not deploy Cloud Run services from an untagged image path; use `image:...:${SHORT_SHA}` so revisions show the source commit.
- Do not let Helm chart-only deploys reset GKE workloads to `latest`. Preserve the currently deployed immutable tag or require an explicit tag input.
- Every GKE Deployment deploy must wait for rollout completion with `kubectl rollout status ... --timeout=...` and fail on timeout.
- For chart-only backend-listen deploys, fail if the current deployed image tag is missing or `latest`; use the backend deploy workflow to establish an immutable tag first.
- Keep rollout checks close to the deploy step they verify, especially for `backend-listen`, `pusher`, `agent-proxy`, `llm-gateway`, `parakeet`, `diarizer`, and `vad`.
- Use `backend/scripts/deploy_status_report.py` as a strict gate on success paths; use it with `|| true` only after a primary rollout/traffic command already failed.
- Before restarting GKE workloads that depend on `backend-secrets`, wait for ExternalSecret Ready and run `backend/scripts/verify_k8s_secret_keys.py`; never print secret values.
- When editing workflows, keep `actionlint` coverage in CI so YAML and GitHub expression mistakes fail before merge.
