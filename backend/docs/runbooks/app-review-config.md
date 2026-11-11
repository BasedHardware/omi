# App review visibility lifecycle

`app_review_config.hidden_versions` remains the serving contract. The lifecycle
records successful submissions from `mobile-store-promote` and
`mobile-daily-train`, reconciles iOS App Store Connect and Android Play
production state, and gives each active hide a 14-day lease. A recorded review
adopts an already-hidden version; TTL expiry removes that version's hide and
leaves a tombstone. After expiry, the subscription UI stays visible for that
version until a new submission receipt is recorded. A live or terminal store
state clears the matching hide and its lifecycle entries immediately.

## Pre-merge Codemagic prerequisite

The YAML references the `app_review_config` environment group on exactly the
two submission workflows above. Codemagic rejects a workflow whose declared
group does not exist, before its script can run. Create the group before merge,
but leave it empty: do not add the submission token until the backend sweep is
enabled and a successful tick has been confirmed. The hook treats a missing
token or failed receipt as best effort, so a successful store submission does
not become a failed Codemagic run.

## Credentials to create after merge

Create these Secret Manager secrets in project `based-hardware`:

| Secret | Value | Use |
| --- | --- | --- |
| `APP_REVIEW_CONFIG_SUBMISSION_TOKEN` | A new random high-entropy token | Authenticates only `/v2/internal/app-review-config/submissions`; after the first successful sweep, put the same value in the Codemagic `app_review_config` group. |
| `APP_REVIEW_ASC_API_KEY_JSON` | JSON object with `issuer_id`, `key_id`, and `private_key` from a dedicated App Store Connect API key | Read-only version-state polling for app `6502156163`. Probe the narrowest app-scoped role that can read versions before activation; do not default to the broader App Manager role without confirming Developer cannot read them. |
| `APP_REVIEW_PLAY_SERVICE_ACCOUNT_JSON` | JSON key for a dedicated Google service account | Read-only production-track polling for package `com.friend.ios`. The exact Play Console role required to open and delete an uncommitted edit has not been verified; do not assume “app-information viewing” is sufficient. |

Grant `roles/secretmanager.secretAccessor` on only these three secrets to
`backend-runtime@based-hardware.iam.gserviceaccount.com`. Do not put the ASC or
Play credentials in Codemagic. The submission token cannot call admin APIs; its
endpoint writes only the matching `app_review_config` document. Authentication
uses a 60-second in-process secret cache, so rotation can take up to 60 seconds
to reach every backend instance. To rotate, update the Secret Manager version
and Codemagic group to the same new value, wait at least 60 seconds (or restart
all backend instances), verify a receipt in staging, then revoke the old value.
Receipts carry the submission time and are accepted only for 15 minutes after
submission (with at most five minutes of future clock skew); replaying an old
receipt cannot create a fresh lease. Repeated receipts for an active lease do
not extend its expiry.

## Activation order after merge

Keep this order as a hard precondition: the Codemagic token must not be added
until the scheduler is enabled and a successful sweep tick has completed.

1. Create the App Store Connect and Play credentials above and grant the scoped
   Secret Manager bindings. Deploy the backend revision containing the
   submission and sweep routes. Confirm `/v2/app-review-config/sweep` is mounted
   on `backend-sync`.
2. Verify the Play role against a staging app before production activation: use
   the same service-account role to create a temporary edit, read its
   production track, and delete the edit without committing it. If any step is
   denied, determine the narrowest app-scoped role that passes this probe; do
   not activate Play polling based on an assumed view-only permission.
3. In a reviewed scheduler-manifest change, remove `lifecycle: planned` and set
   `state: ENABLED` on `app-review-config-sweep-hourly`. The job runs at minute
   17, away from the rollout-watch and daily-train edit windows. Apply it using
   the existing `gcp_scheduler_reconcile.yml` workflow with typed
   `APPLY_PROD_SCHEDULER` confirmation. Confirm a successful route response and
   an advancing `last_sweep_timestamp` before continuing. With missing store
   credentials the sweep still enforces TTL, but it reports a credential alert.
4. Only after that successful tick, create the submission-token secret and add
   its value to the pre-created Codemagic group. Verify the group remains
   attached only to `mobile-store-promote` and `mobile-daily-train`. The hook
   endpoint can be pointed at staging with `APP_REVIEW_CONFIG_ENDPOINT` or
   `--endpoint` during validation.
5. Enable the `App Review Config - sweep silent` Grafana rule after the first
   successful tick. The paging rule fires only for unavailable credentials or
   store API errors; routine reconciliation repairs and live clears do not page.

The Play API requires an edit ID to read a track. Each poll opens a temporary
uncommitted edit, reads only the `production` track, and deletes the edit in a
`finally` path. It never commits an edit. Only releases with
`status == "completed"` count as live; an `inProgress`, `draft`, or held release remains
hidden during review. The 14-day TTL remains the backstop for staged rollouts.
Internal and alpha tracks are not queried. An edit conflict is retried once.

## Existing entries and manual cleanup

The iOS lifecycle adopts a matching pre-existing hide when that version enters
review and clears it when App Store Connect reports the semantic version live
or terminal. It uses the same semantic/build comparison as the app reader, so
an iOS entry such as `1.0.547+20` is cleared when App Store Connect reports
`1.0.547`. The current poller does not query the `macos` document; its existing
entry (`1.0.80+501`) remains a separate manual cleanup decision after checking
its store state. Unmatched legacy iOS entries also require a separate manual
decision. Do not delete them as part of deployment or activation.

Do not run the store clients against real accounts, write Firestore, create
credentials, deploy, or activate the scheduler as part of PR validation. The
scheduler is declared `planned` and `PAUSED` so merge alone cannot activate it.
