# Messaging channels rollout

Telegram paid-user launch and seat-capped iMessage. New channel policies override
the legacy global switch/cohort below; both modes keep the valid paid-plan gate. This runbook
does not deploy, merge, or read secret payloads.

The mobile entry is a separate PostHog flag, `mobile-chat-apps`. The server
does not trust that flag. In legacy env-only mode, a uid outside `OMI_MESSAGING_CHANNELS_UIDS`, or a
backend with the switch off, gets 403 on mint and no channel turns. See paid launch
preparation below before configuring the new policy.

## Legacy uid-only cohort

Set these on the backend runtime, then roll the backend so the process picks
them up. `cohort_enabled` reads the environment on each admission.

| Variable | David-only value |
| --- | --- |
| `OMI_MESSAGING_CHANNELS` | `on` |
| `OMI_MESSAGING_CHANNELS_UIDS` | David's exact uid, no spaces, no other uids |
| `OMI_TELEGRAM_ENABLED` | `on` only after the bot token and webhook secret are bound |
| `OMI_TELEGRAM_STREAMING` | `draft` (or `edit` / `none`) |
| `OMI_IMESSAGE_ENABLED` | `on` only after the Linq key and webhook secret are bound |
| `OMI_IMESSAGE_PROVIDER` | `linq` |
| `OMI_IMESSAGE_MAX_SEND_RECEIVE_RATIO` | `3` (allowed 1–5) |
| `OMI_IMESSAGE_CONTACT_CARD` | `off` until a Linq contact card is configured |
| `OMI_MESSAGING_LINK_TARGETS` | JSON below |

`OMI_MESSAGING_LINK_TARGETS` is public addressing, not a secret. The bot token
does not belong in it.

```json
{
  "telegram": {
    "provider": "telegram",
    "address": "omi_chat_bot",
    "deep_link_template": "https://t.me/{address}?start={proof}"
  },
  "imessage": {
    "provider": "linq",
    "address": "+12062808403"
  }
}
```

Mint returns `deep_link` and `address` from this map. The app prefers those
values and uses the PostHog payload only when the API field is empty.

Turn the PostHog flag `mobile-chat-apps` on for the same uid, with the same
addresses in the payload as a fallback:

```json
{
  "telegram": {"provider": "telegram", "address": "omi_chat_bot"},
  "imessage": {"provider": "linq", "address": "+12062808403"}
}
```

Admission requires a valid paid subscription: legacy Unlimited, Plus, Unlimited v2,
Operator or Architect (including the legacy `pro` alias). Basic/free and expired
subscriptions are rejected. The app uses its existing `plan.isPaid` helper for eligibility;
its existing localized "Omi Pro" marketing copy is unchanged by this logic-only rollout.

The committed prod configuration scopes these settings and the four secret bindings to
Cloud Run `backend` in `based-hardware`, `us-central1`, with uid
`vi7SA9ckQCe4ccobWNxlbdcNdC23` only. Adapter wakeups and pending recovery execute in
that process; no GKE listen/pusher or other worker needs these settings. Prebind
`TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest`,
`TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest`,
`LINQ_API_KEY=LINQ_API_KEY:latest`, and `LINQ_WEBHOOK_SECRET=LINQ_WEBHOOK_SECRET:latest`
on the live service before deployment preflight. The parent operator owns this step.

## Register webhooks

Do this after the backend revision that contains the adapters is serving, and
only for the David cohort environment. Do not print tokens or response bodies
that echo them.

Telegram, official Bot API. `secret_token` must equal `TELEGRAM_WEBHOOK_SECRET`.
The token is in the URL; do not paste the command line into a ticket.

```sh
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://<backend-host>/v1/messaging/webhooks/telegram" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query"]'
```

Confirm with `getWebhookInfo` that the URL matches and `last_error_message` is
empty. Edits are ignored. Groups and bots are ignored.

Linq: subscribe `message.received` to
`https://<backend-host>/v1/messaging/webhooks/imessage`. The signing secret is
`LINQ_WEBHOOK_SECRET` and must be a `whsec_` Standard Webhooks secret. Accept
the documented payload versions only (`2025-01-01` and `2026-02-03`). Unknown
versions fail closed. Timestamps outside ±300 seconds are rejected.

## Rotate secrets

Rotate one side at a time. Bind the new value in the existing secret manager
entry, roll the backend, then update the provider. Do not commit values and do
not read the payload back into an agent log.

| Secret | Provider step after the backend roll |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Revoke the old bot token in BotFather. `setWebhook` again with the new token. |
| `TELEGRAM_WEBHOOK_SECRET` | `setWebhook` again with the new `secret_token`. Old deliveries start failing signature checks immediately. |
| `LINQ_API_KEY` | Revoke the old key in Linq after the new revision is healthy. |
| `LINQ_WEBHOOK_SECRET` | Update the Linq subscription signing secret to the same `whsec_` value. |

A signature failure is `401` with `Invalid webhook signature`. It does not
include the header, the body, or the expected digest.

## What to watch

Logs must stay content-free: uid, provider, status, and `error_type` only.
Link proofs, bot tokens, webhook secrets, and message text must not appear.
Provider HTTP errors are raised without response bodies.

Useful queries, after the log labels that the process actually emits:

- `Messaging recovery paused` — pending drain is failing for a provider.
- `Invalid webhook signature` / status 401 on `/v1/messaging/webhooks/` — secret mismatch or replay outside the Linq timestamp window.
- status 403 on `POST /v1/messaging/link-proofs` — flag, allowlist, deletion, or plan rejected the uid.
- status 202 on the webhook with no following reply — worker still running, or the surface lease is held. Do not reset a `running` inbox row or a lease until the worker is confirmed stopped.

There is no new dashboard in this change. Use the existing backend request logs
and the mobile `chat-apps-funnel` events (`Chat App Connect Started`,
`Chat App Connected`, `Chat App Disconnected`). Those events do not carry
message text.

iMessage: the send/receive ledger blocks a turn that would exceed
`OMI_IMESSAGE_MAX_SEND_RECEIVE_RATIO`. A long answer can stop mid-thread until
David sends another message. That is the ratio guard, not a retry bug.

## Linq sandbox activation and accepted-but-silent webhooks

Linq's sandbox activation reply is provider-owned; it is not Omi's
`Account linked. You can chat with Omi here.` acknowledgement. Check the active
`users/{uid}/channel_links` mirror (the source for `GET /v1/messaging/links`)
to establish Omi linking. Do not infer a link from the activation message.
If activation did not reach Omi, mint a fresh code in the app and send the code
again after activation. An unlinked sender receives instructions to link in Omi.
Never bypass proof verification or the send/receive ratio to activate a sender.

On 2026-10-11 the sandbox did deliver the code: the Linq link became active at
09:24:39.483Z. Accepted webhooks at 09:24:39Z and 09:24:52Z were followed by
content-free worker `ProviderError` logs at 09:24:39.945Z and 09:25:06.421Z.
The next inbound at 09:25:28Z remained pending behind the failed turn's lease.
The old logs did not retain provider status codes, so they cannot establish
sandbox quota rejection. The adapter sent the wrong v3 body shape: `parts` and `idempotency_key` were
not inside `message`. The chat-scoped `POST /api/partner/v3/chats/{chatId}/messages` envelope proven by
PR #21172's October 11 repair keeps `parts` and `idempotency_key` inside `message`
and `preferred_service: "iMessage"` at the top level. Synthetic transport replay
requires this proven shape. Protocol-selection documentation for the separate
`POST /v3/messages` endpoint does not establish the chat-scoped service placement.
`message.reply_to` follows the [sending-messages guide](https://docs.linqapp.com/channel/imessage/guides/messaging/sending-messages/)
but is unverified live; definite 400/404/422 thread rejections retry a plain send,
retaining the top-level service. Ambiguous outcomes never trigger this fallback.

Current worker logs report provider, bounded reason, exception type and HTTP
status only, including terminal 429 responses. A handled turn failure attempts one short guarded failure reply,
closes the stream in its owning task, stops typing, and releases the surface
lease. The failed inbox row remains running and is never automatically replayed.
A finished turn that raises `CancelledError` follows that same path. A worker
task that is still cancelling retains its lease, because thread-pool work may
still be running. A settled deferred reentry stores a failure fence, sends at
most one notice, and releases the lease so the chat is not stuck; a retry sees
the fence and does not run the turn again. Process loss still retains the lease.
Only delivered assistant replies enter model event history. A failure to complete
the inbox tombstone after successful delivery does not send a contradictory apology.
Error frames are drained for a terminal fallback before being treated as silent failure.
Failure-notice delivery records degraded/exhausted outcomes through the shared fallback helper.
If the provider rejects the failure reply too (including exhausted ratio credit),
`Messaging failure reply failed` records that outcome without provider bodies.

Operator action for already-stuck jobs: confirm the old worker is stopped,
reconcile each running job's delivery receipts/effects, then deliberately clear
only its retained lease. Pending jobs may then drain; do not reset running jobs
or reserved receipts blindly. No production data was changed by this diagnosis.
After the fix is deployed, verify a new inbound reply on the sandbox and inspect
status-only failures. A 400 suggests schema validation; 401/403 requires checking
provider authorization or sandbox activation/recipient restrictions; 429 requires
checking the sandbox limit in Linq. Those are diagnostic leads, not proof of the
provider's rejection reason. Use the dashboard or read-only provider receipts;
never paste credentials, handles or message bodies into incident notes.

## Kill switch

1. Use the fast channel kill switch below, or disable each JSON policy entry and
   roll the backend. In legacy env-only mode, set `OMI_MESSAGING_CHANNELS=off`. Admission and new
   adapter registration stop. Listing, unlink, and disconnect stay available.
2. Turn PostHog `mobile-chat-apps` off. The Integrations entry remains if a
   link already exists, so disconnect still works.
3. Delete the provider subscriptions so they stop posting:

```sh
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

Remove the Linq `message.received` subscription in the Linq dashboard (or the
partner webhook API) for the same URL.

In-flight `running` jobs are not replayed. Pending jobs stay pending until the
switch is on again and recovery drains them.

## Rollback

Do not delete channel data as part of rollback. Unlink and account deletion
already purge links and channel sessions.

```sh
# 1. Stop admission. Roll the backend after the env change.
#    OMI_MESSAGING_CHANNELS=off
# 2. Stop provider delivery.
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
# 3. Remove the Linq message.received subscription for
#    https://<backend-host>/v1/messaging/webhooks/imessage
# 4. Turn PostHog mobile-chat-apps off for the cohort.
```

To roll the code back, deploy the previous backend revision with the switch
off. Do not force-push the PR branches. Channel documents left in Firestore
are inert while the switch is off; they are removed when the user unlinks or
deletes the account.

## Not in this rollout

Live provider testing waits on David's bot and Linq setup. WhatsApp stays a
local waitlist. Insights is stored and not honored. Fresh channel sessions use `/new` or `new chat`; unlink still removes channel data.


## First live QA, 2026-10-11

Read-only Cloud Logging evidence for 09:14–09:40 UTC showed revision
`backend-433b2d6-38108932764-1`, rather than the earlier revision in the brief.
All reported Telegram webhooks returned 202. The unanswered requests were admitted
at 09:19:03, 09:22:33 and 09:22:45 UTC. CPU throttling was disabled; request-only CPU
allocation does not explain this incident.

On the instance handling the 09:17:23 callback, memory inverse vector cleanup was
logged at 09:17:36, graph-citation pruning at 09:22:34, and the background messaging
worker reported `ProviderError` at 09:25:06. This supports slow inverse cleanup
holding the surface lease, followed by a settled send failure retaining that lease.
The old gateway held its lease across `UndoStore.undo` and deliberately skipped
release on every exception. Logs do not contain per-phase timings or a stack for
that provider error, so they do not prove the precise cleanup substep or rejected
provider method. No production data/leases were changed for this investigation.
Existing stranded jobs/leases still require operator reconciliation before any reset.

On the first user turn, `get_memories_tool` used the expected principal at 09:15:35,
reported zero visible rows at 09:15:43, and memory search returned empty at 09:15:45.
There was no logged retrieval exception in that window. The historical tool text
suggested that no saved personal facts existed, although the channel digest supplied
personal context. Channel-only empty-result guidance now distinguishes unavailable
retrieval from absent knowledge. The logs cannot distinguish privacy/review/temporal
filtering from an empty underlying store; this investigation did not read account data.

Synthetic timing regressions, run through `backend/test.sh` on the original and
changed source, measured first typing at **176.2 ms → 0.7 ms** with 80 ms session
and 80 ms digest delays. The same fixture's full turn still takes about 170 ms;
this is feedback timing, not a production model latency claim. A separate channel
setup fixture with an 80 ms discarded legacy-prompt read measured **101.6 ms →
16.9 ms**, and prompt reads **1 → 0**. These are local measurements, not deployed
acceptance. Production phase instrumentation can verify feedback latency after rollout.

`test_messaging_live_qa.py` exercises no-write callback → message, memory receipt →
slow undo → another message, duplicate callbacks, provider/inverse errors, distinct
confirmation bubbles, bounded bootstrap history, and a dated reminder through the
real shared tool projection. `test_messaging_adapters_firestore.py` exercises encrypted
per-action receipts, expiry, cross-session scope, multiwrite text-undo ambiguity and
concurrent once-only claims against the loopback Firestore emulator.

## Paid launch preparation and seat operations

This source supports a channel policy; it does not change live configuration.
Without `OMI_MESSAGING_CHANNEL_POLICY`, the original global switch/exact-uid cohort
and all-paid plan gate remain unchanged. A malformed new policy denies admission.
With the new policy, iMessage defaults to Operator and Architect, and 180 linked
users. Legacy Unlimited is not included automatically; edit `plans` deliberately.
The catalog's Operator plan is the $49 tier. Telegram has no seat cap.

```json
{"telegram":{"enabled":true,"cohort":"*"},"imessage":{"enabled":true,"cohort":"*","plans":["operator","architect"],"seat_cap":180}}
```

An exact uid array can replace either `cohort`. Adapter enable flags and provider
secret bindings are still required. Do not enable the new policy before these steps:

1. Apply the generated Firestore indexes and wait until READY. New collection-group
   inbox queries use status/channel/provider/created_at; expiry notices and retention
   have separate indexes. `channel_waitlist.expires_at` has a group field index.
2. Stop provider delivery and disable admission for both channels. Wait for workers to
   settle; reconcile ambiguous running jobs. Env `OMI_MESSAGING_CHANNELS=off` works
   only when the new JSON policy is absent; otherwise set each policy's `enabled:false`.
3. With the admitted backend image and its existing service identity, run
   `python -m utils.messaging.maintenance --prepare-launch` once. This refuses enabled
   env admission. It backfills only content-free inbox channel/provider/done timestamps
   and unknown-identity retention metadata, then reconciles distinct active iMessage
   users into `channel_capacity/imessage` and `members/{uid}.link_ids`. Do this with
   provider delivery/workers stopped, including during any retry. Counts only are logged.
   Existing encrypted messages, running status, proofs and generations are preserved.
4. Confirm `initialized:true` and the reconciled count before enabling the policy.
   Mint fails closed if the counter is uninitialized. If already at/above the configured
   cap, existing members retain seats and new users enter the waitlist.
5. Set `OMI_TELEGRAM_SHARED_PACING=on` (runtime default), confirm shared Redis access,
   and prefer `OMI_TELEGRAM_STREAMING=none` for launch/load shedding. Shared pacing
   fails closed on Redis failure; `off` is safe only with one backend process/instance.
6. Install the opt-in `backend/charts/messaging-maintenance` chart using the admitted
   backend image, existing service account and backend secret name, `enabled:true`.
   The hourly job deletes at most 100 records per category per run. Retention is
   `OMI_MESSAGING_RETENTION_DAYS` / chart `retentionDays` (default 30, minimum 7).
   Raise cadence for backlog; do not delete running reconciliation evidence.
7. Apply `backend/charts/monitoring/messaging/alerts.yaml` beside the monitoring release.
   Verify Cloud Run Prometheus export/scraping before treating absent alerts as health.
   This task does not configure a new Cloud Run exporter or deploy the monitoring rules.

The seat counter counts distinct linked users, including dormant users. Multiple
identities for one uid share a seat; the last unlink and account deletion release it.
Atomic redemption is authoritative: a successfully minted proof can still lose a race
for the last seat. Mint then returns HTTP 409 with `detail.reason=seat_cap` and
`detail.message="iMessage is full — join the waitlist"`; redemption sends a waitlist
notice. `users/{uid}/channel_waitlist/imessage` is refreshed with a 30-day expiry and
removed on admission/account deletion. No automatic waitlist promotion or outbound
invitation is sent. Dormancy release is intentionally not implemented: retaining
linked users conservatively avoids surprise seat loss and proactive provider sends.

To raise the cap, change `seat_cap` only after the Linq plan supports the new limit.
To reconcile counts again, stop delivery/admission/workers and rerun preparation;
never overwrite a live counter or delete member records to reclaim seats. User deletion
and unlink own seat release. A missing member denies channel turns with one notice.

## Fast channel kill switch

Optional `OMI_MESSAGING_KILL_SWITCH_DOC=messaging_config/channels` reads a content-free
Firestore document `{"telegram":true,"imessage":true}`. Once this env binding exists,
operators can set either value to false without redeploying. Cache lifetime is at most
60 seconds; a missing document, missing channel or read failure denies admission and
send guards. Restore explicit true to resume. Listing/unlink remain available.
Turning a channel off does not permit resetting running jobs or reserved delivery receipts.

For Telegram emergency delivery shutdown, use the existing secret-bound operator
session and `deleteWebhook` with `drop_pending_updates=true`. Tokens must never appear
in logs, tickets or agent output. This drops queued provider updates permanently.

```sh
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" \
  --data-urlencode 'drop_pending_updates=true'
```

Linq: disable/remove the `message.received` subscription. Env-only shutdown still
requires a runtime roll; the JSON policy takes precedence over legacy global envs.
Leases take over after **300 seconds**; old workers cannot release the replacement.
Settled failures release promptly. Do not manually clear a lease before the worker is
stopped and external effects are reconciled.

## Launch diagnostics and expected replies

- `omi_messaging_turns_total{channel,outcome}`, `omi_messaging_failures_total{channel,reason}`:
  completed inbox turns and failed/denied work, without text or provider bodies.
- `omi_messaging_provider_http_total{provider,status}`: every provider HTTP attempt,
  including 429. Retry waits honor the provider's `retry_after` within the bounded
  worker deadline; an exhausted budget never retries early.
- `omi_messaging_turn_seconds` and `omi_messaging_queue_age_seconds`: latency and
  claimed-message age histograms. Idle recovery checks also contribute worker latency;
  use queue age plus turn counters to interpret low-volume p95 values.
- Unknown senders receive link instructions once per hour; access-denied linked users
  receive one explanation per hour. Linked ordinary turns share the app's UID-based
  `chat:send_message` policy. A throttle gets a short reply, at most once per minute.
- Pending messages older than 30 minutes move to `expired`. Recovery claims a notice
  once, removes the encrypted payload, and attempts “please resend” within the reply
  window. A crash after claiming a notice can lose it; it never replays a model turn.
- Malformed Telegram `/start` arguments are accepted durably with HTTP 202 and link help.
  Groups, bots, edited messages and invalid signatures retain their original rejection.
- Draft preview failures record degraded fallback and preserve the final reply. Set
  streaming to `none` for load shedding; final sends still use shared pacing.
- `/new` (Telegram) or `new chat` (iMessage) starts a fresh surface session. Long-lived
  chats no longer need this to recover from the former event-log ceiling.
- Client link-list reads happen on entry/focus with a 60-second load cache; connect sheets
  poll only with a pending proof, back off to 30 seconds, and pause in the background.

## Shaped context and cache operations

The backend can be deployed while the new indexes build: optional context fails
open to the existing plain cache-aligned window. Foreground optional reads are
bounded at 150 ms total, with at most 75 ms for digest IO. Summarization only runs
after the turn in tracked background tasks, at most two per process and 60 seconds
per job. Failed/missing indexes, model errors, CAS conflicts and timeouts are logged
by error type and record degraded fallback; they do not fail the answer.

Deployment order:

1. Apply the generated indexes. `chat_context_summary_source` (messages collection:
   session id, created_at, document name ascending) must be READY for successful
   background summaries. It is not required for app sends or a config flip.
2. Before enabling channel adapters or expanding `OMI_MESSAGING_CHANNEL_POLICY`, wait
   for `messaging_inbox_fifo` (inbox collection), `messaging_pending_recovery` and
   `messaging_expired_notices` (inbox collection group). With these still building,
   a current admitted reply can work, but queued heads/recovery can stall.
3. With admissions disabled, run the documented `--prepare-launch` reconciliation
   for existing inbox metadata and linked-user capacity. Then enable the policy,
   including iMessage seat cap; an initialized counter is required before cap admission.
4. Before enabling the maintenance Helm job, wait for `messaging_done_retention`
   (inbox group), `messaging_unknown_retention` (identities collection) and the
   `messaging_waitlist_expiry` expires_at field index. The messaging recovery indexes
   above also serve expiry notices. Install the job only after these are READY.

No new config means legacy admission/cohort/seat behavior stays in force. Existing
shaped app turns keep the same plain 10–17-message window; optional summaries/digest
can degrade safely while indexes build. There is no index-dependent app send gate,
summary model call before streaming or new admission requirement. Optional reads
may add up to 150 ms; this is a bounded degradation, not identical provider bytes.

Session `shaped_context` is encrypted. History report/clear/delete/journal edits remove
it in the same atomic write and bump generation/revision. CAS and active-link/account
fences prevent stale background writers from restoring removed data. Unlink/account
wipe removes session state; `/new` copies no summary. Original messages stay searchable.
Only fully summarized source pages advance the checkpoint, so later jobs resume after
timeout without skipping a partially summarized page. Summaries remain lossy.

Keep `OMI_CHAT_PROMPT_CACHE_TTL=30m` or unset. Unsupported values log and omit explicit
cache options/breakpoints rather than fail turns. Verify token hit rates using daily
`llm_usage` surface buckets, `chat_agent_turns` children and
`omi_chat_agent_tokens_total{surface,kind}`. Cache_read/input is the observed ratio;
unreported cache-write fields on other transports are recorded as zero. Local
synthetic prefix tests establish eligibility, not deployed hit rate.

Redis pacing errors record fallback and use local global/chat pacing for that API
attempt. Shared pacing remains preferred; Telegram 429 retry_after remains the
cross-instance authority during outages. Deliberate full-backlog 429 stays a typed
admission refusal rather than being treated as a Redis outage. Streaming `none`
reduces preview traffic while preserving final replies.
