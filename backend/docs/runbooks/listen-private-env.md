# Private backend-listen env (Secret Manager)

Private listen env values are the uid-bearing STT cap fallback cohort
`STT_CAP_DISPATCH_COHORT` and media/noise digest serve list
`MEDIA_NOISE_MODE_SERVE_UID_SHA256S`, plus `STT_CAP_DISPATCH_ENFORCEMENT`, which
stays private by ruling (lead2 4e5e71/45689e, b2cf73) so that a code deploy can
never change it. Their **names** live in Git; their **values** live only in
Secret Manager.

| piece | where |
|---|---|
| names | `backend/charts/backend-listen/prod_omi_backend_listen_values.yaml` `privateSecretEnv.keys` (and `prod.overlay.yaml` `secret:` entries) |
| values | Secret Manager `LISTEN_PRIVATE_ENV` (project `based-hardware`): one JSON object `{"NAME": "string", ...}` |
| sync | `backend/charts/backend-secrets/templates/listen-private-env.yaml`: ExternalSecret `prod-omi-backend-listen-private-env`, `dataFrom.extract`, `refreshInterval: 0s` |
| Kubernetes Secret | `prod-omi-backend-listen-private-env` (ns `prod-omi-backend`), referenced only by backend-listen |
| pod env | one `secretKeyRef` per name (`optional: false`) rendered by the listen chart |
| deploy guard | `.github/scripts/listen_private_env.py guard`, step "Prove private listen env is unchanged" |

A code deploy renders references only, so the train's drift gate compares
public values and references and never needs the values. The chart refuses a
non-empty `privateEnv` (the retired `LISTEN_PRIVATE_VALUES_YAML` overlay) while
`privateSecretEnv` is set.

Never print, paste or post a value, a hash of a value, or a cohort list. Report
names and `same`/`changed` only.

## Change a private value (audited operation, not a deploy)

Who: the owner of the value's ruling, with a human or `prod-operator` login that
holds `secretmanager.versions.add` on `LISTEN_PRIVATE_ENV`. Off-peak for listen
(the restart reconnects every live stream: before 13:00Z or after 22:00Z).

1. Write the whole new document as a new version, from a file that never lands in
   Git or a log (`umask 077`; delete it afterwards):
   `gcloud secrets versions add LISTEN_PRIVATE_ENV --project based-hardware --data-file <file>`
   The document must contain every name in `privateSecretEnv.keys`, each non-empty.
   An empty `STT_CAP_DISPATCH_COHORT` with enforcement on denies every capped dispatch.
2. Sync it into the cluster (refresh interval is 0, so nothing moves until you do):
   `kubectl -n prod-omi-backend annotate externalsecret prod-omi-backend-listen-private-env force-sync=$(date +%s) --overwrite`
   and wait for `Ready=True` with a new `status.syncedResourceVersion`.
3. Restart listen so every pod reads the same value (new pods would otherwise
   mix with old ones only after an HPA scale-up):
   `kubectl -n prod-omi-backend rollout restart deploy/prod-omi-backend-listen`
   then `kubectl -n prod-omi-backend rollout status deploy/prod-omi-backend-listen --timeout=4200s`.
4. Record the change (who, ruling, version number, time) on the owning tracker.

Rollback: add the previous document again as a new version (the ExternalSecret
reads `latest`), then steps 2–3. Do not rely on disabling the newest version.

Between steps 2 and 3 every listen deploy refuses at "Prove private listen env is
unchanged" with `effect=pending-restart`: the Secret holds a value no serving pod
reads yet, and a roll must never apply it unannounced. Finish step 3 first.

An **empty** value is not a supported state. The guard reports it as
`missing-from-secret` and refuses every listen deploy until it is non-empty. To
stop STT cap admission, set `STT_CAP_DISPATCH_ENFORCEMENT` to `false`, not an
empty cohort. To stop serving the media/noise list, set
`MEDIA_NOISE_MODE_SERVE_PERCENT` to `0` in the chart. To retire a name, remove it
through a reviewed PR (below).

## Add or remove a private name

A reviewed PR: add the name to `privateSecretEnv.keys` and the `secret:` entry
in `backend/deploy/runtime_env/prod.overlay.yaml` (then
`python3 backend/deploy/compose_runtime_env.py`). Add the value to the document
(steps 1–2 above) **before** the listen roll: the deploy guard refuses a
declared name the synced Secret lacks, and `optional: false` would keep new pods
from starting. Removing a name: remove it from the chart first, roll, then from
the document.

## One-time migration from LISTEN_PRIVATE_VALUES_YAML (2026-11)

The protected workflow mode `private-env-migrate` of
`.github/workflows/gcp_backend_listen_helm.yml` (prod only; rolls nothing):

1. reads the retired GitHub secret inside the protected job and requires every
   declared private value to be non-empty and byte-identical to its literal in
   the Deployment and every serving ReplicaSet. It also checks folded public
   values against the chart, then writes one `LISTEN_PRIVATE_ENV` version through
   the deployer's Workload Identity (`roles/secretmanager.secretVersionAdder`
   on that one secret);
2. renders and applies only the listen-private ExternalSecret from the
   backend-secrets chart, then force-syncs it;
3. runs the deploy guard against the serving templates. Every private name must report
   `effect=same`.

The first listen roll after that renders `secretKeyRef`s; its guard proves the
values are byte-identical to the live literals before Helm runs. Rollback of
that roll: `mode=rollback` (Helm restores the previous revision, whose stored
values still carry the literals). After a clean soak, delete the GitHub secret
and the `private-env-migrate` and `evidence` modes.
