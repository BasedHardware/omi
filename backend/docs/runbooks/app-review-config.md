# App review visibility lifecycle

`app_review_config.hidden_versions` remains the serving contract. This lifecycle adds
metadata alongside it, reports successful store submissions from the two approved
Codemagic workflows, and reconciles iOS App Store Connect and Android Play production
state hourly. Temporary entries expire after 14 days. Entries that the lifecycle did
not add (including existing iOS/macOS entries) are never removed by TTL cleanup.

## Credentials to create before activation

Create these Secret Manager secrets in project `based-hardware`:

| Secret | Value | Where it is used |
| --- | --- | --- |
| `APP_REVIEW_CONFIG_SUBMISSION_TOKEN` | A new random high-entropy token | Same value in the Codemagic `app_review_config` environment group as `APP_REVIEW_CONFIG_SUBMISSION_TOKEN`; authenticates only the narrow submission receipt endpoint. |
| `APP_REVIEW_ASC_API_KEY_JSON` | JSON object with `issuer_id`, `key_id`, and `private_key` from a dedicated App Store Connect API key | Read-only App Store version state polling for app `6502156163`. Grant the key the minimum App Store Connect role that can view this app's versions (App Manager if Developer cannot read versions). |
| `APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON` | JSON key for a dedicated Google service account | Read-only production track polling for package `com.friend.ios`. Add it to Play Console with app-information viewing only; do not grant release or publishing permissions. |

Grant `roles/secretmanager.secretAccessor` on only these three secrets to
`backend-runtime@based-hardware.iam.gserviceaccount.com`. Do not put the ASC or Play
credentials in Codemagic. The Codemagic token cannot call admin APIs; the backend
accepts it only on `/v2/internal/app-review-config/submissions` and writes only the
matching `app_review_config` document.

The Play API requires an edit ID to read a track. Each poll opens a temporary
uncommitted edit, reads only the `production` track, and deletes the edit in a `finally`
path. It never commits an edit. A Play code in production clears its matching hide,
including staged rollouts at any fraction. Internal and alpha tracks are not queried.

## Activation after merge

1. Create the three secrets and grant the scoped accessor bindings above. Add the
   submission token to the Codemagic `app_review_config` group. Verify Codemagic exposes
   that group only to `mobile-store-promote` and `mobile-daily-train`.
2. Deploy the backend revision containing the submission and sweep routes. Confirm
   `/v2/app-review-config/sweep` is mounted on `backend-sync`.
3. In a follow-up reviewed scheduler-manifest change, remove `lifecycle: planned` and
   set `state: ENABLED` on `app-review-config-sweep-hourly`. Then run the existing
   `gcp_scheduler_reconcile.yml` workflow for prod with the typed
   `APPLY_PROD_SCHEDULER` confirmation. The PR deliberately ships this job as planned
   and paused so merge alone cannot activate a production poller.
4. Enable the `App Review Config - sweep silent` Grafana rule after the first
   successful tick. The app-review alert rule pages for missing store credentials,
   store API errors, repaired review hides, and hides cleared after the store reports
   a live/terminal version.
5. Check the next run in Cloud Scheduler, confirm the app-review lifecycle metrics are
   present, and verify the Codemagic receipt hook reports accepted submissions. Do not
   run the store clients against real accounts as part of PR validation.

The hourly job applies TTL expiry even when either store API is unavailable. In that
case it logs and pages, skips reconciliation for that platform, and keeps the app
serving its current config. A review that lasts beyond the TTL is allowed to show the
subscription UI until a later successful reconciliation writes a fresh 14-day hide.

## Existing entries and manual cleanup

The existing iOS and macOS entries predate lifecycle ownership and are intentionally
left in place. Decide separately whether those stale entries should be manually
removed from Firestore after checking their current store and review status. This
worker will not infer ownership or delete them.
