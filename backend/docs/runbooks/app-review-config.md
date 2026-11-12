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

Do not put the ASC or Play credentials in Codemagic. Deploy the backend after
the secrets and accessor bindings exist, then verify the sweep route is mounted
on `backend-sync`. The scheduler must remain paused during these probes.

## Activation order after merge

Keep this sequence as a hard gate. Enabling the scheduler requires the held
Android draft fix from PR #25131 to be merged and present in the deployed
revision.

1. Confirm PR #25131's write-side fix is merged: held manual Android
   production promotions default to `draft`, and only completed releases count
   as live. Keep manual promote and daily-train submissions frozen.
2. Create the secrets and accessor bindings above, deploy the backend revision,
   and confirm `/v2/app-review-config/sweep` is mounted on `backend-sync`.
   Complete the ASC JWT probe and Play edit/read/delete role probe before
   continuing.
3. Before the first scheduler tick, capture a read-only snapshot of
   `app_review_config/ios` and `app_review_config/android` for rollback and
   comparison. Keep the snapshot in the operator's secure incident records.
4. In a reviewed scheduler-manifest change, remove `lifecycle: planned` and set
   `state: ENABLED` on `app-review-config-sweep-hourly`. The job runs at minute
   17 UTC. Before applying, verify the deployed backend revision contains
   PR #25131's held-draft fix. Apply with the existing
   `gcp_scheduler_reconcile.yml` workflow and typed `APPLY_PROD_SCHEDULER`
   confirmation.
5. Confirm the first tick succeeds and the Prometheus gauge
   `omi_app_review_config_last_sweep_timestamp_seconds` advances on
   `https://monitor.omi.me`. If needed, force one tick with
   `gcloud scheduler jobs run app-review-config-sweep-hourly --location=us-central1 --project=based-hardware`.
   Verify the route response and backend-sync logs before proceeding.
6. Enable the `omi-app-review-config-sweep-silent` deadman rule only after the
   successful first tick. Verify the rule is unpaused in Grafana and its
   provisioned definition reads back correctly. A paused deadman is not a
   completed activation gate.
7. Validate token authentication without writing a submission: send a validly
   shaped but stale receipt to `/v2/internal/app-review-config/submissions`
   through the approved operator runner, with the token supplied from Secret
   Manager without printing it. Expect HTTP 409 (`submission receipt is stale`)
   and confirm neither Firestore document changed. A 401 means the token is
   missing or mismatched and must be fixed before continuing.
8. Add the same token to the pre-created Codemagic `app_review_config` group.
   Verify the group is attached only to `mobile-store-promote` and
   `mobile-daily-train`, then release the submission freeze.

The Codemagic hook treats a missing token or failed receipt as best effort so a
successful store submission does not become a failed build. The first-sight
Android reconciliation is the fallback for a missing receipt, but it does not
replace the activation gates.

## Receipt behavior and alerting

Receipts are accepted only for 15 minutes after submission, with at most five
minutes of future clock skew. Replayed receipts do not extend an active lease.
The sweep retries Play edit conflicts five times with exponential backoff; the
Grafana paging rule requires three lifecycle failures within three hours, so a
single collision is visible in logs and metrics without paging. It covers
`credentials_unavailable`, `store_api_error`, `submission_token_unavailable`,
and `submission_token_rejected`. Routine repairs and live clears do not page.

During token rotation, freeze manual and daily-train submissions first. Update
the Secret Manager value, wait at least 60 seconds for backend token caches to
refresh, then update the Codemagic group to the same value. Repeat the stale
receipt authentication check above, confirm the two Firestore documents did
not change, and resume submissions. A missing secret reports
`submission_token_unavailable`; a missing or mismatched request token reports
`submission_token_rejected`. Resolve either page before resuming submissions.

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
