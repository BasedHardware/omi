# Dev callers restored to the legacy Ingress endpoints

The dev shared internal model Gateway (VIP `172.16.48.49`) was deleted on
2026-11-02, but `origin/main` still bound every dev speaker-ID, VAD and NLLB
caller to that VIP, so those dev calls blackholed. This change repoints the dev
bindings to the documented rollback endpoints and changes no prod value:

- `HOSTED_SPEAKER_EMBEDDING_API_URL` → `http://diarizer.omiapi.com:80` on
  backend-listen, pusher, Cloud Run backend/backend-sync/backend-sync-backfill/
  backend-integration (`runtime_env/dev.overlay.yaml` plus the listen/pusher
  chart literals).
- `HOSTED_VAD_API_URL` → `http://vad.omiapi.com:80/v1/vad` (backend-listen
  chart only).
- `HOSTED_TRANSLATION_API_URL` → `http://nllb.omiapi.com` (dev backend-listen
  overlay plus chart literal).

Parakeet's chart fallback is intentionally NOT repointed: the audio-fleet
contract (`test_audio_fleet_helm`) freezes the parakeet chart against main, so
its dev fallback still binds the dead VIP (`http://172.16.48.49/diarizer`).
Repointing it to
`http://dev-omi-diarizer.dev-omi-backend.svc.cluster.local:8080` is a follow-up
for the audio-fleet owner's separately qualified change; the dev parakeet
deployment is 0/0, so nothing in dev executes that binding today.

Clients append `/v2/embedding` and `/v1/vad` exactly as before; only the
prefix route disappears because the legacy Ingresses serve native paths.

The legacy `dev-omi-diarizer`, `dev-omi-vad` and `dev-nllb-nllb-translation`
Ingress rules, services and DNS records are retained as the live rollback
path. The 2026-11-02 ic-devlb map measured the diarizer/vad/nllb backends at
0/0 replicas (operator-controlled maintenance) and `nllb.omiapi.com` without a
public A record; restoring dev traffic end-to-end still needs those replicas
and that name resolvable from Cloud Run and GKE.

The same map identified `dev-omi-llm` as an orphaned Helm release (`llm-0.1.0`,
no chart on main, zero traffic, no covenant). Its Ingress, DNS record
`llm.omiapi.com` and reserved address `dev-llm-ilb-ip-address` are removed by
an operator, not by this repo change; see
[internal-gateway-callers](../../internal-gateway-callers.md).

Rollout: regenerating `backend/deploy/runtime_env.yaml`
(`backend/.venv/bin/python backend/deploy/compose_runtime_env.py`) plus the
owning dev deploys (`gcp_backend_listen_helm.yml`, `gcp_backend_pusher.yml`,
`gcp_parakeet.yml`, `gcp_backend.yml`). Contract:
[Shared Gateway caller routes](../../listen_pusher_pipeline.mdx#shared-gateway-caller-routes).
