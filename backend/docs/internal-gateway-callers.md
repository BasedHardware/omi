# Shared Gateway caller migration

A separate commit in the same PR migrates NLLB, VAD and speaker embeddings in
both environments. Parakeet STT stays on its existing hostname; only Parakeet's
speaker-embedding fallback moves. A read-only refresh on 2026-10-14 found dev's
newly reserved `dev-ml-gateway-ilb-ip` at `172.16.48.49`; prod uses
`172.16.160.20`. Both environments now bind concrete IPs. Reservation alone does
not prove Gateway programming, health or caller reachability. Qualify every
route from GKE and Cloud Run before deploying these caller values.

Deploy order (dev first, then prod):

1. Install/qualify the Gateway and NLLB, VAD and embedding routes using the
   Gateway runbook. Preserve legacy Ingresses/DNS for at least seven days.
2. Deploy NLLB and VAD caller bindings via `gcp_backend_listen_helm.yml`, watching
   each service's errors, p95 and fallback rate for at least 30 minutes before
   proceeding. New values are `/nllb` and `/vad/v1/vad`; VAD takes the full URL.
3. Switch **all** embedding hosts as one coordinated cohort:
   backend-listen, pusher, Cloud Run backend/backend-sync/backend-sync-backfill/
   backend-integration, plus Parakeet's chart fallback. Use the listen/pusher
   workflows, `gcp_backend.yml`, and `gcp_parakeet.yml`. All use `/diarizer` and
   clients append `/v2/embedding`. Verify equal effective values and observe for
   at least 30 minutes. Apply the combined caller commit via staged workflow
   releases; if listen deploys all three URLs at once, qualify all routes first
   and require separate NLLB/VAD metric readouts before the embedding cohort.
4. Independently qualify/deploy the batch cohort A and its subsequent stages.
   Do not switch `HOSTED_PARAKEET_API_URL` during this rollout.

Rollback the caller commit alone and redeploy **all** affected hosts, including
Parakeet's chart. It restores dev/prod NLLB to `http://nllb.omiapi.com` /
`http://nllb.omi.me`, VAD to `http://vad.omiapi.com:80/v1/vad` /
`http://vad.omi.me:80/v1/vad`, and embeddings to
`http://diarizer.omiapi.com:80` / `http://diarizer.omi.me:80`.
Parakeet fallback restores
`http://dev-omi-diarizer.dev-omi-backend.svc.cluster.local:8080` /
`http://prod-omi-diarizer.prod-omi-backend.svc.cluster.local:8080`.
Confirm recovery via legacy paths before rolling routes back. This revert keeps
the independent batch cohort binding on `/diarizer-batch`; never remove the shared
Gateway while that cohort still uses it. Conversely, reverting the cohort commit
leaves these caller bindings intact. Each commit includes its own runbook section.

For either rollback, regenerate `backend/deploy/runtime_env.yaml` after reverting
the owning overlay. If Git reports a generated-manifest conflict while reverting
the cohort commit, resolve it by running
`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`, stage the generated
file and continue the revert. Do not restore the generated manifest from before
both commits: that would undo the independently retained caller migration.
