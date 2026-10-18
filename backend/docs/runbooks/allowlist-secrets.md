# Private production allowlists

Production uses one Secret Manager secret per allowlist, named exactly like the
env variable. The initial migration pins immutable version `1` everywhere.
Cloud Run declares these under `cloud_run.services.*.secrets` in
`deploy/runtime_env/prod.overlay.yaml`; the renderer emits `secretKeyRef` state
and deploy-cloudrun secret inputs. GKE uses the existing backend-secrets
ExternalSecret/SecretStore and required `valueFrom.secretKeyRef` entries in the
listen/pusher prod values. Runtime policy validation is reused by deployment gates; application parsing and feature defaults are unchanged. The mobile batch selector and
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

1. Freeze allowlist rotation for the migration. This source pins version `1`;
   verify each create command produces that version and that it remains enabled.
   Capture the current serving
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
   `create --data-file` creates both the secret and immutable version `1`. If any
   name already exists, stop and verify the pinned version `1` payload, enabled
   state and IAM specifically. If the intended payload is in a different
   version, revise the Cloud Run and chart pins together through review before
   deploying. Do not overwrite it or add another version blindly.

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
identity and the attached runtime service accounts that consume that key. Set
`BACKEND_DEPLOYER_SA` to the production GitHub backend deploy principal. It also
needs accessor on Cloud Run cohort secrets so preflight can validate payloads
in memory; missing access blocks deployment. No key material belongs in this variable. The
following lead-only script resolves Cloud Run identities rather than assuming
that backfill shares sync's identity. The chart's normal ESO identity is
`prod-omi-backend-eso-gsa@based-hardware.iam.gserviceaccount.com`; confirm the live
SecretStore uses it before applying. If the deployed identity differs, stop and
resolve the deployment inputs first.

```python
# Run from repository root with the attended human credential tier.
import json
import os
import subprocess
import yaml

project = 'based-hardware'
# Exact service account used by the existing production GitHub backend deploy.
# The lead resolves this from the configured deployment credential, not a guessed name.
deployer = os.environ['BACKEND_DEPLOYER_SA']
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
        consumers[key].add(deployer)
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
   Secret Manager existence and private payload checks must pass. The Cloud Run
   preflight reads each distinct private version in memory, rejects empty parsed
   CSV cohorts or invalid/empty policy JSON, applies the runtime messaging schema and recovery-owner ID rules, and emits a fixed error message without data-derived identifiers.
   This includes the lineage empty-value case that would otherwise widen admission.
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
   an ExternalSecret refresh, waits, and checks target Secret keys and decoded private payloads without printing values. A production refresh
   timeout fails closed, and production cannot bypass the refresh wait. Observe
   a fresh Ready sync and all thirteen nonempty payloads before listen upgrade,
   even if keys already existed.
4. Helm replaces the env list: the prod listen/pusher values therefore contain
   explicit required `secretKeyRef` entries. An omitted key is not repaired by
   `envFrom`; this PR retains the binding in the rendered list. Missing Secret
   keys prevent the new pod from starting rather than admitting an empty cohort.
   Verify ExternalSecret readiness before the separate owning pusher deployment
   too. Its existing deploy-backend-config helper validates the decoded private
   cohorts before both the proposed canary ConfigMap and the shared ConfigMap,
   so an invalid rotation stops before either Helm install. Shared Dream and
   speaker-grouping sources must match exactly across listen and pusher.
   Keep the secret chart installed; do not roll it back independently.

The legacy `sync_cloudrun_secrets_from_chart.sh` helper excludes all private
cohorts; normal per-service manifest deploys own these bindings and their atomic
type migration. Reviewed stage data stores public knobs only, with membership
removed; the co-host gate validates required private sources separately. The
flag registry includes Cloud Run service and job secret declarations.

The dev composed manifest is semantically unchanged. Historical literal lineage
manifests remain replayable; current secret manifests must agree by name/version
on four Cloud Run hosts and the listener, including the rendered Helm entry.
The source gate rejects mutable aliases, divergent Cloud Run versions, or an
ExternalSecret version that differs from its Cloud Run consumers. The same
immutable version is selected by ExternalSecret `remoteRef.version`.

Do not bind private cohorts to `latest`: Cloud Run resolves env secrets when an
instance starts, so an existing revision could otherwise change cohort during
scale-out. [Google recommends pinned env-secret versions](https://docs.cloud.google.com/run/docs/configuring/services/secrets).
The [ExternalSecret remote reference API](https://external-secrets.io/latest/api/spec/#externalsecretdataremoteref)
supports a version selector. Secret refs identify immutable bytes, not verified
membership: compare cohorts privately before rollout. Creating version `2`
changes neither these Cloud Run refs nor the pinned ExternalSecret. A later
rotation must update every affected Cloud Run version and the chart's per-key
version together, validate candidate revisions and a fresh ESO sync, then roll
all affected pods and promote under the owning release gates. Keep admission
off and drain accepted cohort work when changing admission/recovery/lineage
membership; do not mix active old/new routing cohorts. Existing instances/pods
retain their prior env until replaced. Keep old versions enabled for rollback.

## Verification and rollback

Offline: run `backend/scripts/pre-deploy-check.sh` and
`python -m pytest backend/tests/unit/test_allowlist_secret_deploy.py
backend/tests/unit/test_sync_lineage_rollout_deploy.py -q` using the pinned backend
environment. The regression tests render both real Helm charts and follow the
four existing Cloud Run deploy inputs, including backfill's clone. They reject
mixed, missing, or divergent lineage refs and nonempty public UID allowlists.

After an authorized deploy: verify each serving Cloud Run revision reports the
reviewed `OMI_BACKEND_RELEASE_SHA`, 100% traffic on the expected promoted revision,
and one same-name `secretKeyRef:1` per declared allowlist with no literal or
duplicate. Verify backend-listen and pusher's image digests/release identity,
ready pod env refs, current ExternalSecret Ready/refresh and all required target
keys. Compare actual cohorts privately, emitting only equality/cardinality
results. Observe a new aggregate metric/log from the running revision. Keep
live admission off; a fresh live-session canary is a separately authorized gate.
Never call the signed-in production API or inspect account documents for this.

For migration failure before promotion, leave Cloud Run traffic on the captured
previous revisions. If already promoted, restore the captured per-service
traffic map using the owning traffic rollback procedure. For GKE, prefer the
prior compatible image with these current secret bindings. Use a captured prior
Helm revision only after checking its rendered env retains every required
selector; do not roll back to a chart revision that drops the batch admission
reference and relies on out-of-band kubectl env state. Do not remove/disable Secret Manager
versions, revoke their IAM, or roll back backend-secrets while any pods or
Cloud Run revisions reference them. Avoid redeploying historical source that
would reintroduce public literals. Do not widen an allowlist or turn off recovery
protections to make a rollout pass. A later live-only rollback turns the live
admission flag off while accepted work drains; see the batch pipeline runbook.

For a later cohort-version rollback, keep admission off and drain accepted work.
Restore the captured Cloud Run revisions and select the prior immutable versions
in the current ExternalSecret chart without removing any keys. Require a fresh
ESO sync and roll all affected GKE pods before resuming cohort routing. Never
change a Secret Manager alias to perform a cohort rollback.
