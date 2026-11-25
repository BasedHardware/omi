# App review visibility lifecycle

`app_review_config.hidden_versions` remains the serving contract. Successful
manual promotion and daily-train submissions emit receipts; the lifecycle sweep
reconciles iOS App Store Connect and Android Play production state and gives
each active hide a 14-day lease. A recorded receipt adopts an already-hidden
version. TTL expiry removes that version's hide and leaves a tombstone, so a
sweep cannot silently re-arm an expired lease. A fresh, authenticated receipt
starts a fresh lease when it races an already-past deadline.

For Android, only a production release with `status == "completed"` counts as
live. A first-seen production code on a draft, in-progress, or halted release
creates a bounded hide even if its receipt was lost. Existing active entries
are repaired without extending their deadline; expired tombstones prevent
first-sight recreation. The lease starts when the held submission is recorded,
not when an operator later presses Send for review. If the receipt is missing,
it starts when the sweep first observes the non-completed production release.

## Submission freeze before activation

Do not submit to either store through manual promote or the daily train between
merging the lifecycle change and completing every activation gate below. This
keeps store state from advancing while the backend, scheduler, alert, and
Codemagic receipt path are only partially active.

If a submission already happened, stop further submissions and inspect its
production status and version code. Before the first tick, snapshot both
`app_review_config/ios` and `app_review_config/android`. A held, non-completed
Android release without an expired tombstone should be hidden by first-sight
reconciliation; verify the resulting active entry and expiry after the tick.
If a tombstone already exists, do not remove it automatically: the operator
must decide whether a fresh bounded manual hide is warranted and record that
decision through the approved Firestore change process.

## Pre-merge Codemagic prerequisite

The YAML references the `app_review_config` environment group on exactly the
two submission workflows above. Codemagic rejects a workflow whose declared
group does not exist, before its script can run. Create the group before merge,
but leave it empty. Do not attach the submission token until the scheduler,
deadman alert, and receipt-authentication gates below have passed.

## Credentials and pre-activation probes

After merge, create these Secret Manager secrets in project `based-hardware`
and grant `roles/secretmanager.secretAccessor` on only these three secrets to
`backend-runtime@based-hardware.iam.gserviceaccount.com`. Create the submission
token secret early with the other credentials; keep the Codemagic group empty
until full activation.

| Secret | Value | Use |
| --- | --- | --- |
| `APP_REVIEW_CONFIG_SUBMISSION_TOKEN` | A new random high-entropy token | Authenticates only `/v2/internal/app-review-config/submissions`; stored in Secret Manager before deployment, added to Codemagic only after the gates below. |
| `APP_REVIEW_ASC_API_KEY_JSON` | JSON object with `issuer_id`, `key_id`, and `private_key` from a dedicated App Store Connect API key | Read-only version-state polling for app `6502156163`. Before activation, perform a read-only JWT probe of the app's versions endpoint using the intended app-scoped role. Confirm the narrowest role that can read versions; do not wait for a first-tick credential alert to discover a role problem. |
| `APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON` | JSON key for a dedicated Google service account | Read-only production-track polling for package `com.friend.ios`. Verify the role against a staging app by opening a temporary edit, reading its production track, and deleting the edit without committing it. |

### Store-credential setup for a human GCP operator

Enabling `androidpublisher.googleapis.com` in Cloud Console only permits API
traffic from the project. It does not give a caller access to a Play app. GCP
IAM ownership and Play Console app permissions are separate: a human with GCP
Owner can perform the setup below but is not thereby a supported runtime
credential. This service loads a service-account JSON with
`Credentials.from_service_account_info`; it has no human-OAuth/ADC flow. Follow
[Google's API setup guide](https://developers.google.com/android-publisher/getting_started),
which no longer requires linking the Play developer account to this GCP project.

For the Play reader, a human GCP operator must:

1. Open
   [Service accounts in `based-hardware`](https://console.cloud.google.com/iam-admin/serviceaccounts?project=based-hardware)
   and create a dedicated account such as `app-review-play-reader`. Give it no
   GCP project role; it only needs Play Console app permission. Create a JSON
   key and transfer it directly into the secret payload. Delete the downloaded
   key after the verified upload; never print, commit, or paste it into chat.
2. Open
   [Play Console → Users and permissions](https://play.google.com/console/users-and-permissions).
   Invite the service-account email as a user. Limit its app access to Omi
   (`com.friend.ios`), with **View app information and download reports
   (read-only)**. Do not grant release-writing, signing, financial, or account
   administration permissions. Existing release-writer credentials are not a
   substitute for this dedicated reader.
3. Validate on the designated staging app, not production: open a temporary
   edit, read only the `production` track, and delete the edit without
   committing. Do this before the first production sweep. If the minimal
   permission is insufficient, stop and obtain a reviewed permission change;
   do not silently broaden it to a release role.

The App Store Connect credential uses issuer ID, key ID, and private key from a
dedicated API key with the narrowest app-scoped role that can read app versions.
Keep iOS and Android credentials in their separate Secret Manager payloads.
The submission token is a new high-entropy random value, not a store credential.

A GCP operator with secret-administration access can create the payload and its
single accessor binding with commands of this form. Replace the JSON filename
with the protected one-time input path, and use `versions add` if the named
secret already exists. `ro-prod` and `prod-operator` do not have the secret/IAM
or service-account-key grants needed for this bootstrap; use the authorized
human GCP session rather than broadening either agent tier.

```bash
PROJECT=based-hardware
RUNTIME=backend-runtime@based-hardware.iam.gserviceaccount.com

openssl rand -hex 32 | gcloud secrets create APP_REVIEW_CONFIG_SUBMISSION_TOKEN \
  --project=$PROJECT --replication-policy=automatic --data-file=-
gcloud secrets create APP_REVIEW_ASC_API_KEY_JSON \
  --project=$PROJECT --replication-policy=automatic --data-file=/protected/asc-key.json
gcloud secrets create APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON \
  --project=$PROJECT --replication-policy=automatic --data-file=/protected/play-reader-key.json

for SECRET in \
  APP_REVIEW_CONFIG_SUBMISSION_TOKEN \
  APP_REVIEW_ASC_API_KEY_JSON \
  APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON
do
  gcloud secrets add-iam-policy-binding "$SECRET" --project=$PROJECT \
    --member="serviceAccount:$RUNTIME" \
    --role=roles/secretmanager.secretAccessor --condition=None --format=none
done
```

Do not put the ASC or Play credentials in Codemagic. The submission and
sweep routes run on `backend-sync` under `backend-runtime`; do not grant the
`backend-listen` identity access for them. Deploy the backend after the secrets
and accessor bindings exist, then verify both routes are mounted on
`backend-sync`. The scheduler must remain paused during these probes.

## Activation prerequisites and order

The scheduler remains `lifecycle: planned` and GCP `PAUSED` through source
repair, review, merge, and deployment. Merging either PR does not authorize
activation. Before any separately authorized activation, parent PR #25123 must
land before child PR #25131, and the child's final repaired code must be merged
and deployed. Confirm the deployed child code preserves all of these behaviors:
held Android submissions write `draft`; a fresh receipt renews an expired
lease; first-sight reconciliation repairs a missing receipt without reviving an
expired tombstone; unavailable and rejected submission tokens reach the real
paging rule; and the rollout brake can read the app-review job as `PAUSED`.
The brake's scheduler check does not prove full writer quiescence. Before
invoking the brake, separately deploy the still-planned job in `PAUSED` state
by explicitly selecting `app-review-config-sweep-hourly` with the reconciler's
`--jobs` argument; default reconciliation skips planned jobs. Confirm the job
exists and remains `PAUSED`. Use the existing `gcp_scheduler_reconcile.yml`
workflow with its `jobs` input set to `app-review-config-sweep-hourly`, along
with the production environment approval and typed confirmation. Parent-only
checks do not satisfy these gates.

Before the brake check, record the exact `google_play` Codemagic principal and
verify its existing `cloudscheduler.jobs.get` permission for this job. Do not
create or broaden IAM bindings. Separately retain Scheduler history or
backend-sync log evidence that any already-started sweep request has finished,
and terminal build receipts for previously dispatched Codemagic writers. A
`PAUSED` job and the brake result do not replace these drain receipts.

After those release gates pass, and only under separate activation
authorization, keep manual promote and daily-train submissions frozen while
following this order:

1. Confirm the final repaired child revision is deployed, both
   `/v2/internal/app-review-config/submissions` and
   `/v2/app-review-config/sweep` are mounted on `backend-sync`, and both run
   under `backend-runtime`. Keep the scheduler `PAUSED` during credential and
   role probes.
2. Separately deploy `app-review-config-sweep-hourly` while it remains
   `lifecycle: planned` and GCP `PAUSED`, explicitly selecting it with
   `--jobs app-review-config-sweep-hourly`. A default reconciliation skips
   planned jobs. Use the existing `gcp_scheduler_reconcile.yml` workflow with
   its `jobs` input set to `app-review-config-sweep-hourly`. Confirm the
   deployed job is `PAUSED` before the brake check.
3. Record the `google_play` principal and verify its existing
   `cloudscheduler.jobs.get` permission. Separately confirm through Scheduler
   history or backend-sync logs that any started sweep request has finished,
   and retain terminal build receipts for dispatched Codemagic writers. The
   brake result is not proof of these independent drain checks. Then run the
   authorized brake status check and retain its receipt.
4. Create the secrets and scoped accessor bindings above. Verify the ASC role
   against its versions endpoint and the Play role against a staging app by
   opening a temporary edit, reading its production track, and deleting the
   edit without committing it.
5. Before the first scheduler tick, capture the documented read-only snapshot
   of `app_review_config/ios` and `app_review_config/android` for rollback and
   comparison through the approved operator process.
6. Before enabling the job, record the operator review of any legacy
   completed-but-held production releases and hand-created releases with names
   the lifecycle cannot parse. The poller treats `status == "completed"` as
   live, so these cases need an explicit manual disposition. Record that the
   submission token is intentionally absent until the first successful tick;
   after attaching it, verify it is present and that missing/rejected-token
   alerts page before resuming submissions.
7. In a separately reviewed scheduler-manifest change, remove
   `lifecycle: planned` and set `state: ENABLED` on
   `app-review-config-sweep-hourly`. The job runs at minute 17 UTC. Apply with
   the existing `gcp_scheduler_reconcile.yml` workflow, selecting
   `app-review-config-sweep-hourly` in its `jobs` input, and the typed
   `APPLY_PROD_SCHEDULER` confirmation.
8. Confirm the first tick succeeds and
   `omi_app_review_config_last_sweep_timestamp_seconds` advances. If separately
   authorized and needed, run the job through the approved scheduler workflow;
   verify its response and backend-sync logs. With missing store credentials,
   the sweep still enforces TTL and reports a credential alert.
9. Enable the `omi-app-review-config-sweep-silent` deadman rule only after the
   successful first tick, then verify the provisioned rule is unpaused.
10. Validate token authentication without writing a submission: send a validly
   shaped but stale receipt to `/v2/internal/app-review-config/submissions`
   through the approved operator runner, with the token supplied from Secret
   Manager without printing it. Expect HTTP 409 (`submission receipt is stale`)
   and confirm neither Firestore document changed. A 401 means the token is
   missing or mismatched and must be fixed before continuing.
11. Add the same token to the pre-created Codemagic `app_review_config` group.
   Verify the group is attached only to `mobile-store-promote` and
   `mobile-daily-train`, then release the submission freeze.

The Codemagic hook treats a missing token or failed receipt as best effort so a
successful store submission does not become a failed build. First-sight Android
reconciliation repairs a missing receipt but does not replace the activation
gates.

## Receipt behavior and alerting

Receipts are accepted only for 15 minutes after submission, with at most five
minutes of future clock skew. Replayed receipts do not extend an active lease.
The sweep retries Play edit conflicts five times with exponential backoff; the
Grafana paging rule requires three lifecycle failures within three hours, so a
single collision remains visible in logs and metrics without paging. It covers
`credentials_unavailable`, `store_api_error`, `submission_token_unavailable`,
and `submission_token_rejected`. Routine repairs and live clears do not page.

During token rotation, freeze manual and daily-train submissions first. Update
the Secret Manager value, wait at least 60 seconds for backend token caches to
refresh, then update the Codemagic group to the same value. Repeat the stale
receipt authentication check above, confirm the two Firestore documents did
not change, and resume submissions. A missing secret reports
`submission_token_unavailable`; a missing or mismatched request token reports
`submission_token_rejected`. Resolve either page before resuming submissions.
Scrape contracts declare all four app-review lifecycle metrics:
`omi_app_review_config_alert_total`,
`omi_app_review_config_last_alert_timestamp_seconds`,
`omi_app_review_config_sweep_total`, and
`omi_app_review_config_last_sweep_timestamp_seconds`. The backend-sync scrape
keeps these `omi_` metrics. Credential and store API failures route to the
human Telegram paging receiver; the silent-sweep rule remains paused until its
first successful tick.

When store credentials are unavailable or the store API fails, the sweep still
runs TTL cleanup and emits `omi_fallback_total` with
`component=app_review_config`, `to_mode=ttl_only`, and the bounded reason
`store_credentials_unavailable` or `store_api_error`. The app-review alert
counter reports the store error separately. A TTL-only tick does not mean store
reconciliation succeeded; restore read-only store access and verify a
successful sweep before enabling the silent-sweep alert.

The Play API requires an edit ID to read a track. Each poll opens a temporary
uncommitted edit, reads only the `production` track, and deletes the edit in a
`finally` path. It never commits an edit. Only completed production codes
clear Android hides; drafts, in-progress releases, and held releases remain
hidden. The 14-day TTL remains the backstop for long reviews. Internal and
alpha tracks are not queried.

## Existing entries and manual cleanup

The iOS lifecycle adopts a matching pre-existing hide when that version enters
review and clears it when App Store Connect reports the semantic version live
or terminal. It uses the same semantic/build comparison as the app reader, so
an iOS entry such as `1.0.547+20` is cleared when App Store Connect reports
`1.0.547`. The current poller does not query the `macos` document; its existing
entry (`1.0.80+501`) remains a separate manual cleanup decision after checking
its store state. Unmatched legacy iOS entries also require a separate manual
decision. Do not delete them as part of deployment or activation.

A held manual Android production release is a `draft`. Such a draft blocks
`BRAKE_ACTION=stage`, which requires completed production releases beside the
halted release. During an incident, handle the draft and halted rollout in Play
Console; do not try to stage through the brake until the track has the expected
completed base plus the halted release.

## Rollback

Freeze store submissions, then use this order:

1. Remove the submission token from the Codemagic `app_review_config` group
   first. This stops new receipt attempts while the lifecycle is being paused.
2. Re-pause `app-review-config-sweep-hourly` through a reviewed scheduler
   manifest change and apply it through the scheduler reconcile workflow.
   Confirm the job is `PAUSED`.
3. Explicitly inspect and decide each existing iOS and Android lifecycle entry:
   retain the hide, remove it through the approved change process, or arrange
   bounded cleanup. Pausing the sweep leaves existing entries
   **TTL-unenforced**; their expiry will not be processed until the sweep runs
   again.

Do not run store clients against real accounts, write Firestore, create
credentials, deploy, or activate the scheduler as part of PR validation. The
scheduler remains `planned` and `PAUSED` until the reviewed activation gates
above are completed.
