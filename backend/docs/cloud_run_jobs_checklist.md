# Cloud Run Jobs checklist

**One domain → one Cloud Run Job.** Do not add unrelated work to an existing job.

Use this checklist when adding a new periodic Cloud Run Job. Prefer cloning the landed `memory-maintenance-job` (or `x-connector-sync-job`) as the template. Agents can bootstrap stubs with `backend/scripts/scaffold_cloud_run_job.sh`.

## Checklist

1. Thin `backend/modal/<name>_job.py` entrypoint that initializes Firebase and calls **one** module/runner.
2. `backend/modal/Dockerfile.<name>_job` with `CMD ["python", "<name>_job.py"]`.
3. Register the image in `backend/runtime_images.json` (dockerfile, workflows, entrypoints, smoke env).
4. Add `cloud_run.jobs.<name>` in `backend/deploy/runtime_env/_base.yaml` (+ env overlays), list the workflow in `workflow_files`, then run `python3 backend/deploy/compose_runtime_env.py`.
5. `.github/workflows/gcp_<name>_job.yml` — render/validate env with `--job <name>`, deploy with `job:`, checkout-SHA image tags, VPC vars for prod network flags.
6. Unit coverage for render outputs (`*_env_vars` / `*_secrets`) and scheduler validator if Scheduler is in-repo.
7. Runbook: first deploy, `gcloud run jobs execute`, Cloud Scheduler create/update.
8. Update the Backend Service Map in `backend/AGENTS.md`.
9. Add the deploy concurrency lock in `.github/scripts/check-deployment-concurrency.py` when applicable.

## Host shapes (do not unify)

| Shape | Use for |
|-------|---------|
| Cloud Run Job + Scheduler | Periodic batch (notifications, memory maintenance, X sync) |
| Cloud Tasks → Cloud Run Service | Durable request work (sync, audio-merge, account-deletion) |
| GKE CronJob | Infra shell (agent-vm-reaper) |

## Explicit non-goals

- No shared Python `BaseCronJob` / plugin registry / multi-task bag.
- Do not hitchhike new domains onto `notifications-job` or other existing jobs.
- Scaffold scripts must **not** create GCP resources or enable schedulers.
