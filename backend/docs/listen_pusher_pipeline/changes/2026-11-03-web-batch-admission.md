# Web server batch admission

Web capture can join server batch via `SERVER_BATCH_ONLY_WEB_PERCENT` (default 0).
Admission keys on authenticated platform, because capture source normalizes to
`unknown`. AUTO-language admission also includes web under the shared AUTO
percentage and learned supported-only language profile gate.

The [server batch contract](../../listen_pusher_pipeline.mdx) retains the existing
pusher PCM/original custody and finalization intake: no endpoint or client WAL.
The additive ready-event `server_batch_only` field drives the web recording,
header, widget and transcript pop-out processing message; provider-less deferred streams remain live UI.

The Infra Rollout Coordinator expands 5 → 25 → 100 within 3 days of the web deploy,
after each full clean new-state lookback of the web suppression counter
(`OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL` in `config/server_batch.py`) and
batch timeliness/queue age. Old cached bundles lack this message, so do not expand
before the web deploy is live. Roll back new admissions with the web percentage
at 0; reserved captures continue through batch custody. Consent, BYOK, unsupported
languages, e2ee and pusher availability gates remain in force.

Qualification: hermetic web admission, ready payload, socket mode and recording
lifecycle tests; no production calls or activation in this change.
