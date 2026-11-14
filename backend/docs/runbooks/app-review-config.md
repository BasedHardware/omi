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

## Activation prerequisites and order

The scheduler remains `lifecycle: planned` and GCP `PAUSED` through source
repair, review, merge, and deployment. Merging either PR does not authorize
activation. Before any separately authorized activation, the stacked parent
PR #25123 must land before child PR #25131, and the child's final repaired code
must be merged and deployed. Confirm that deployed child code preserves all of
these behaviors: held Android releases are written as drafts; a fresh receipt
renews an expired lease; reconciliation repairs a missing receipt on first
sight without reviving an expired tombstone; unavailable and rejected
submission tokens reach the real paging rule; and the rollout brake proves
Cloud Scheduler is `PAUSED` with no active writer runs. Use the child
regressions and deployment receipts for this check. Do not use a successful
parent-only check as evidence for these child gates.

After those release gates pass, and only under separate activation
authorization, use this order. The submission and sweep routes run on
`backend-sync` under `backend-runtime`; do not grant the `backend-listen`
identity access for them.

1. Create the App Store Connect and Play secrets above and grant only the
   scoped Secret Manager bindings to `backend-runtime`. Deploy the final
   stacked backend revision and confirm both routes are mounted on
   `backend-sync`.
2. Verify the Play role against a staging app: create a temporary edit, read
   its production track, and delete the edit without committing it. If a step
   is denied, establish the narrowest app-scoped role that passes before
   enabling store polling.
3. Verify the deployed metric scrape and alert path, including
   `submission_token_unavailable` and `submission_token_rejected`, and retain
   the successful child brake-quiescence receipt.
4. In a separately reviewed scheduler-manifest change, remove
   `lifecycle: planned` and set `state: ENABLED` on
   `app-review-config-sweep-hourly`. The job runs at minute 17, away from the
   rollout-watch and daily-train edit windows. Apply it with the existing
   `gcp_scheduler_reconcile.yml` workflow and typed
   `APPLY_PROD_SCHEDULER` confirmation. Confirm a successful route response
   and advancing `last_sweep_timestamp`. With missing store credentials, the
   sweep still enforces TTL and reports a credential alert.
5. After the first successful sweep tick, create the submission-token secret
   and add its value to the pre-created Codemagic group. Verify the group is
   attached only to `mobile-store-promote` and `mobile-daily-train`. The hook
   can target staging with `APP_REVIEW_CONFIG_ENDPOINT` or `--endpoint`.
6. Enable the `App Review Config - sweep silent` Grafana rule after the first
   successful tick. Confirm that the paging rule covers credential, store API,
   and submission-token failures; routine reconciliation repairs and live
   clears do not page.

## Monitoring and TTL-only fallback

The Cloud Run scrape contracts declare all four app-review lifecycle metrics:
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
