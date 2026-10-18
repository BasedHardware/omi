# Private production allowlists

Production uses one Secret Manager secret per allowlist, named exactly like the
env variable. Cloud Run declares these under `cloud_run.services.*.secrets` in
`deploy/runtime_env/prod.overlay.yaml`; the renderer emits `secretKeyRef` state
and deploy-cloudrun secret inputs. GKE uses the existing backend-secrets
ExternalSecret/SecretStore and required `valueFrom.secretKeyRef` entries in the
listen/pusher prod values. No application parsing or feature defaults change. The mobile batch selector and
messaging cohorts also contain owner identities: `MOBILE_STANDARD_BATCH_UIDS` and
`OMI_MESSAGING_CHANNELS_UIDS` use their own secrets; `OMI_MESSAGING_CHANNEL_POLICY`
keeps its complete JSON policy in a same-name secret. Preserve the complete JSON
bytes and all existing channel/seat/plan settings when seeding this policy.

This is a dark configuration migration. Leave live admission false, batch
percent zero, shared-live false, and all other switches at their reviewed
values. Pusher receives its existing private cohorts, not batch admission
controls. First-summary bindings go only to sync, backfill and integration.

## Lead-only preparation (human credential tier)

Do this **before merge or any prod deployment of this source**. Do not create
secrets or change IAM from an agent read-only tier. Do not place payloads in Git,
logs, shell history, arguments, or a CI artifact. Disable shell tracing.

1. Freeze allowlist rotation for the migration. Capture the current serving
   revision identities and traffic, and prior Helm release revisions, privately.
   Compare each allowlist across its consumers in memory; stop if values differ.
   Preserve exact CSV bytes, including cohort order and lack of a newline.
   For admission, recovery and first-summary, verify the intended singleton and
   equality across admission/recovery/summary hosts before provisioning. Do not
   assume all thirteen allowlists have the same membership.
2. Set `ALLOWLIST_PAYLOAD_DIR` to a private scratch directory (mode 0700) with
   one mode-0600 file per env name below. Populate it from the verified serving
   config through an in-memory/private-file extractor, never `echo <UID>`.
   For source-managed cohorts compare with the pre-migration overlay as well.
   BATCH_PIPELINE_UID_ALLOWLIST and FIRST_SUMMARY_UID_ALLOWLIST currently come
   from retained runtime config. Use those verified values. Never seed an empty
   payload: some consumers interpret empty as a wider rollout.
3. The lead runs these exact commands using the attended human credential tier.
   `create --data-file` creates both the secret and its first version. If any
   name already exists, stop and verify its payload and IAM; do not overwrite it
   or add another version blindly.

```bash
set -euo pipefail
set +x
: "${ALLOWLIST_PAYLOAD_DIR:?set to the private verified payload directory}"
gcloud secrets create BATCH_PIPELINE_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/BATCH_PIPELINE_UID_ALLOWLIST"
gcloud secrets create BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST"
gcloud secrets create FIRST_SUMMARY_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/FIRST_SUMMARY_UID_ALLOWLIST"
gcloud secrets create DREAM_AGENT_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/DREAM_AGENT_UID_ALLOWLIST"
gcloud secrets create SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST"
gcloud secrets create STT_LIVE_DEMAND_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/STT_LIVE_DEMAND_UID_ALLOWLIST"
gcloud secrets create SYNC_LEGACY_FRESH_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/SYNC_LEGACY_FRESH_UID_ALLOWLIST"
gcloud secrets create SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST"
gcloud secrets create TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST"
gcloud secrets create TRANSCRIPTION_SHADOW_UID_ALLOWLIST --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/TRANSCRIPTION_SHADOW_UID_ALLOWLIST"
gcloud secrets create MOBILE_STANDARD_BATCH_UIDS --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/MOBILE_STANDARD_BATCH_UIDS"
gcloud secrets create OMI_MESSAGING_CHANNELS_UIDS --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/OMI_MESSAGING_CHANNELS_UIDS"
gcloud secrets create OMI_MESSAGING_CHANNEL_POLICY --project=based-hardware --replication-policy=automatic --data-file="$ALLOWLIST_PAYLOAD_DIR/OMI_MESSAGING_CHANNEL_POLICY"
```

Grant `roles/secretmanager.secretAccessor` on each secret to the existing ESO
identity and the attached runtime service accounts that consume that key. The
following lead-only script resolves Cloud Run identities rather than assuming
that backfill shares sync's identity. The chart's normal ESO identity is
`prod-omi-backend-eso-gsa@based-hardware.iam.gserviceaccount.com`; confirm the live
SecretStore uses it before applying. If the deployed identity differs, stop and
resolve the deployment inputs first.

```python
# Run from repository root with the attended human credential tier.
import json
import subprocess
import yaml

project = 'based-hardware'
manifest = yaml.safe_load(open('backend/deploy/runtime_env.yaml'))['environments']['prod']
chart = yaml.safe_load(open('backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml'))
keys = {row['secretKey'] for row in chart['externalSecret']['secretKeys']
        if row['secretKey'].endswith('UID_ALLOWLIST') or row['secretKey'] in {
            'MOBILE_STANDARD_BATCH_UIDS', 'OMI_MESSAGING_CHANNELS_UIDS', 'OMI_MESSAGING_CHANNEL_POLICY'}}
consumers = {key: {'prod-omi-backend-eso-gsa@based-hardware.iam.gserviceaccount.com'} for key in keys}
for name, config in manifest['cloud_run']['services'].items():
    doc = json.loads(subprocess.check_output([
        'gcloud', 'run', 'services', 'describe', name, '--project='+project,
        '--region=us-central1', '--format=json']))
    # Deployment may intentionally move to a declared keyless runtime identity.
    identity = config.get('service_account') or doc['spec']['template']['spec'].get('serviceAccountName')
    if not identity:
        number = subprocess.check_output(['gcloud', 'projects', 'describe', project,
                                          '--format=value(projectNumber)'], text=True).strip()
        identity = number + '-compute@developer.gserviceaccount.com'
    for key in keys & config['secrets'].keys():
        consumers[key].add(identity)
for key, identities in sorted(consumers.items()):
    for identity in sorted(identities):
        subprocess.run(['gcloud', 'secrets', 'add-iam-policy-binding', key,
                        '--project='+project, '--member=serviceAccount:'+identity,
                        '--role=roles/secretmanager.secretAccessor', '--quiet'], check=True)
```

Verify enabled versions, payload equality and access for all runtime identities
and ESO before deploying. Keep payloads private and remove the temporary files
after verification. Secret resources and versions remain for rollback.

## Deployment order and why there is no missing-allowlist revision

Use one reviewed source SHA containing the literal removal **and** replacement
bindings. Never deploy an intermediate overlay-only deletion or issue a
removal-only `gcloud run services update`. Normal production images ship through
the owning GitHub Actions workflow; this document does not authorize dispatch.

1. Provision and verify all thirteen secrets and IAM first. The normal prebuild
   Secret Manager existence check must pass; existence alone is not proof of
   payload correctness or runtime IAM access.
2. Deploy the complete backend stack (`deploy_targets=all`) at the reviewed SHA.
   Cloud Run deploy inputs use the existing merge strategy: unrelated retained
   env survives; secret names replace only declared allowlists. The renderer
   appends these same names to `--remove-env-vars`, alongside `--update-secrets`
   in the **same** deploy action invocation. gcloud prunes literals first, then
   adds secret refs, before submitting the new revision. Re-running is safe:
   literal removal does not remove an already-secret binding. No removal-only
   revision is created. All four services deploy with `no_traffic: true`; the
   existing composition validation and explicit promotion gate still apply.
   Backfill's clone receives its own secret overlay, so inherited sync literals
   cannot reintroduce the migrated names.
3. The stack deploys backend-secrets **before** backend-listen. Its script forces
   an ExternalSecret refresh, waits, and checks target Secret keys. A refresh
   timeout may fall back to checking current keys; missing new keys fails closed
   before listen upgrade. For this migration require an observed fresh Ready
   sync and all thirteen nonempty payloads, even if keys already existed.
4. Helm replaces the env list: the prod listen/pusher values therefore contain
   explicit required `secretKeyRef` entries. An omitted key is not repaired by
   `envFrom`; this PR retains the binding in the rendered list. Missing Secret
   keys prevent the new pod from starting rather than admitting an empty cohort.
   Verify ExternalSecret readiness before the separate owning pusher deployment
   too. Keep the secret chart installed; do not roll it back independently.

The dev composed manifest is semantically unchanged. Historical literal lineage
manifests remain replayable; current secret manifests must agree by name/version
on four Cloud Run hosts and the listener, including the rendered Helm entry.
Secret refs establish a common source, not payload equality: freeze `latest`
while rolling out. ESO refresh does not update a running process's env; later
rotation requires controlled Cloud Run revisions and GKE pod rollouts.

## Verification and rollback

Offline: run `backend/scripts/pre-deploy-check.sh` and
`python -m pytest backend/tests/unit/test_allowlist_secret_deploy.py
backend/tests/unit/test_sync_lineage_rollout_deploy.py -q` using the pinned backend
environment. The regression tests render both real Helm charts and follow the
four existing Cloud Run deploy inputs, including backfill's clone. They reject
mixed, missing, or divergent lineage refs and nonempty public UID allowlists.

After an authorized deploy: verify each serving Cloud Run revision reports the
reviewed `OMI_BACKEND_RELEASE_SHA`, 100% traffic on the expected promoted revision,
and one same-name `secretKeyRef:latest` per declared allowlist with no literal or
duplicate. Verify backend-listen and pusher's image digests/release identity,
ready pod env refs, current ExternalSecret Ready/refresh and all required target
keys. Compare actual cohorts privately, emitting only equality/cardinality
results. Observe a new aggregate metric/log from the running revision. Keep
live admission off; a fresh live-session canary is a separately authorized gate.
Never call the signed-in production API or inspect account documents for this.

For migration failure before promotion, leave Cloud Run traffic on the captured
previous revisions. If already promoted, restore the captured per-service
traffic map using the owning traffic rollback procedure. Roll GKE back to the
captured prior Helm revisions if needed, or deploy the prior compatible image
with these current secret bindings. Do not remove/disable Secret Manager
versions, revoke their IAM, or roll back backend-secrets while any pods or
Cloud Run revisions reference them. Avoid redeploying historical source that
would reintroduce public literals. Do not widen an allowlist or turn off recovery
protections to make a rollout pass. A later live-only rollback turns the live
admission flag off while accepted work drains; see the batch pipeline runbook.
