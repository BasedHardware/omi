# Messaging channels rollout

Telegram paid-user launch and David-only iMessage without a seat cap. New channel policies override
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
Cloud Run `backend` in `based-hardware`, `us-central1`. Telegram admits all valid paid
users; iMessage retains only `vi7SA9ckQCe4ccobWNxlbdcNdC23`. Adapter wakeups and pending recovery execute in
that process; no GKE listen/pusher or other worker needs these settings. Prebind
`TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest`,
`TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest`,
`LINQ_API_KEY=LINQ_API_KEY:latest`, and `LINQ_WEBHOOK_SECRET=LINQ_WEBHOOK_SECRET:latest`
on the live service before deployment preflight. The parent operator owns this step.

## Register webhooks

Do this after the backend revision that contains the adapters is serving, and
for the admitted environment. Do not print tokens or response bodies
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
secret bindings are still required. The following seat preparation applies only when
enabling a numeric iMessage cap. The approved Telegram launch below uses `seat_cap:"off"`
and does not require `--prepare-launch` or an initialized counter:

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
   records a degraded fallback to local pacing on Redis failure; Telegram 429 responses
   still enforce provider pacing. `off` is safe only with one backend process/instance.
6. Install the Cloud Run cleanup job and its explicitly selected Scheduler trigger
   using [the production operations sequence](#production-maintenance-and-alert-install).
   Each execution selects at most 100 records per category; unknown identity
   subtrees can contain additional records. Running inbox evidence blocks an unknown
   identity purge. Retention defaults to 30 days,
   minimum 7. Do not delete running reconciliation evidence.
7. Install the declared Cloud Monitoring policies through that same sequence. The
   Kubernetes chart and PrometheusRule remain optional GKE-only resources; neither is
   the production Cloud Run installation path.

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
open to the existing plain cache-aligned window. Eligible app/channel turns start
stored continuity and digest IO before router metadata and prompt/tool setup. Each
has a one-second overlapping window on a dedicated four-worker, zero-queue context
executor. Cancellation does not free a worker until its blocking call finishes.
Every context RPC has an explicit timeout and a Retry predicate that never retries.
The model samples ready results, then checks fresh session/account/deletion/link and
generation/revision/incarnation fences in one projected BatchGet (150 ms maximum).
A failed, late or saturated check discards both components; cap exhaustion is
`summary_pending`. A pending/failed digest preserves a freshly validated summary. Direct runner callers without the router retain the 150 ms bounded prepare
seam. Summarization only runs
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
3. Only before enabling a numeric iMessage cap: with admissions disabled, run the
   documented `--prepare-launch` reconciliation for inbox metadata and linked-user
   capacity. An initialized counter is required for numeric-cap admission. The
   approved no-cap David cohort continues without this step.
4. Before enabling the maintenance Cloud Run job, wait for `messaging_done_retention`
   (inbox group), `messaging_unknown_retention` (identities collection) and the
   `messaging_waitlist_expiry` expires_at field index. The messaging recovery indexes
   above also serve expiry notices. Install the job only after these are READY.

No new config means legacy admission/cohort/seat behavior stays in force. Existing
shaped app turns keep the same plain 10–17-message window; optional summaries/digest
can degrade safely while indexes build. There is no index-dependent app send gate,
summary model call before streaming or new admission requirement. Router prefetch
adds no wait for unfinished prefetched data, but the fresh fence check at model mount
adds up to 150 ms (the pre-prefetch foreground cap). This supersedes the earlier
zero-wait mount claim. The amount of useful overlap depends on actual
setup time; measure it with `omi_chat_context_setup_overlap_seconds`. A ready summary
and digest can change provider input and caching, so provider bytes need not match.

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


## Approved all-paid Telegram configuration (Brief S)

The prod overlay and composed manifest contain this exact policy:

```json
{"telegram":{"enabled":true,"cohort":"*"},"imessage":{"enabled":true,"cohort":["vi7SA9ckQCe4ccobWNxlbdcNdC23"],"seat_cap":"off"}}
```

`seat_cap:"off"` is the only accepted explicit disable spelling. With this setting,
omitted `plans` means every valid paid plan, preserving legacy admission. Other
spellings, null caps, invalid types and malformed policy deny admission. Numeric
caps still default to Operator/Architect and require initialized capacity. Mint,
redemption and turn guards perform no capacity reads in no-cap mode. If a previously
capped environment changes to no-cap, reconcile again before re-enabling its numeric
cap; do not reuse counts collected while accounting was off.

Prod explicitly sets `OMI_TELEGRAM_STREAMING=none` and
`OMI_TELEGRAM_SHARED_PACING=on`. The composed backend service inherits existing
`REDIS_DB_HOST`, `REDIS_DB_PORT` and `REDIS_DB_PASSWORD` bindings. No new Redis
credentials or endpoint is introduced. Unknown-sender notices are throttled to once
per hour by default. Linked chat turns, including lightweight acknowledgements, use
the existing UID `chat:send_message` limit; refusal notices are limited to once per minute.

Manual operator steps (not executed by this change):

1. Deploy the reviewed backend image/config through the existing release path.
   Verify the existing FIFO/recovery indexes are READY before widening admission;
   this is an operational prerequisite, not a request to run seat preparation.
2. Expand the existing PostHog `mobile-chat-apps` entry to the intended paid Telegram
   audience so users can discover/link the bot. The backend remains authoritative:
   non-cohort iMessage mint is denied. No client binary change is needed.
3. Confirm shared Redis connectivity and provider webhook registration with the
   admitted revision. Source bindings establish configuration, not runtime health.
4. Install cleanup and alerts using the production operations sequence below, after
   retention indexes are READY. Cloud Run owns scheduled backend jobs; do not also
   enable the optional GKE maintenance chart.

## Inbound media contract and acceptance

Each turn accepts up to **10 attachments**; each attachment is limited to
**20,000,000 bytes** (20 MB decimal). Audio and video
are limited to **600 seconds** (10 minutes), checked both against provider metadata
and actual decoded PCM. Channel FFmpeg comes from the pinned `imageio-ffmpeg==0.6.0`
platform wheel in both the runtime and CI locks; it does not depend on a runner's
system packages and never downloads executables at runtime. A validated system
FFmpeg is the fallback, recorded through the shared fallback event. Enabled channel
startup probes the decoder off the event loop; a missing or unusable decoder logs
ERROR `Messaging audio decoder unavailable` but never blocks API startup — text
turns continue and voice notes get the typed decode reply.
Repair by syncing the locked dependencies (`make setup-backend`) or reinstalling
the existing system FFmpeg package. Disabled channels need no decoder probe.
FFmpeg has a 30-second decode deadline, one decoder/filter
thread, an explicit container allowlist (no playlists), and bounds output to cap+1
before reading it. A loop-owned media semaphore admits at most eight attachment preparations
(including downloads and image ingestion) per serving process, bounding retained
buffers as users overlap. The shared STT semaphore also bounds audio work. No provider/model work occurs on the webhook request path.

Audio MIME types or common filename extensions route to audio extraction, including
Telegram `voice`, `audio`, `video`, `video_note`, audio documents and Linq `media`.
OGG/Opus, M4A/AAC, CAF, AMR, MP3, WAV, WebM and MOV/MP4 audio tracks become 16 kHz,
mono, signed 16-bit PCM. The existing prerecorded provider router receives explicit
`encoding=linear16`, `sample_rate=16000`, `channels=1`, `diarize=False`; its Parakeet
and Modulate adapters wrap PCM into WAV. Channel audio calls the app's `transcribe_pcm_bytes` helper, including normalized
`text` postprocessing and user language preferences (default `multi`). Decode/STT
runs on `sync_executor`, as app voice transcription does, behind the shared STT
semaphore; it does not hold a GCS/storage thread. `/v2/voice-messages` first decodes Omi's length-prefixed device frames through
`decode_files_to_wav`; that decoder is not a standard-container decoder and cannot
be used on OGG/CAF bytes. Channel container decoding supplies that missing boundary.

Empty/STT/decode failure replies: “I couldn't make out that voice note — could you
try again or type it?” Size, duration, download, image conversion and unsupported
file failures have their own fixed replies. If every attachment fails and there is no existing readable media, media refusals
complete the inbox row and release the lease after the fixed reply, without an LLM.
For partial album failure, successful attachments still reach the agent with a
specific notice identifying the failed item by its position. The answer can use
the readable items and briefly mention that failure. Neither case sends the generic
worker apology. Delivery failures retain the normal reconciliation evidence.

HEIC/HEIF is converted to oriented RGB JPEG before the existing owned file uploader.
Images sent as Telegram documents use the image path. FileChatTool already supports
PDF/text/CSV and DOCX/XLSX/PPTX. Locations and contact cards become bounded untrusted
text evidence; contacts are never automatically saved. Telegram stickers and
animations, GIFs, emoji-only messages and optional Linq sticker hints get a lightweight “Got it 🙂” without an LLM. Linq documents incoming inline stickers
as ordinary media and exposes no sticker discriminator in `MediaPartResponse`;
unmarked sticker images follow the photo path. They cannot be distinguished safely
from photos with that payload alone. The optional sticker-hint test is defensive
coverage, not a claim that Linq currently supplies that field. Reactions, polls, dice, games, payments,
service messages and unknown non-content events are ignored. Unsupported Linq parts
or file attachments receive one specific supported-format reply.

Telegram albums use one encrypted inbox row with a 1.2-second quiet window, bounded
by three seconds from first arrival. Per-part content-free dedup tombstones survive
completion. The existing transactional FIFO claim and surface lease prevent competing
workers from answering twice. Request handlers schedule a timer without waiting;
periodic recovery handles process loss. Pending or running batches accept late parts
until a transaction seals the prepared attachment snapshot immediately before the
model turn. Media IO processes only newly appended parts. Admission after that fence
creates one debounced follow-up batch; subsequent late parts join it, including while
it is waiting behind the original turn. Each provider part retains its dedup tombstone.
Out-of-order delivery does not lose parts. Other user messages remain separate turns.
A part arriving after a follow-up itself starts generation joins the next coalesced
batch: arbitrary lateness cannot be folded into an answer already being generated.
Pre-change running rows are never made appendable during rolling deployment.

Telegram quotes supply bounded provider text. Linq `reply_to.message_id` resolves
against at most forty encrypted session events, matching only accepted assistant
delivery IDs or earlier inbound IDs. Older/pre-change/pruned quotes explicitly say
context is unavailable; no remote history fetch or cross-session search occurs.
Quotes, files, locations and contacts are evidence, never tool authorization.

### Incident mechanisms and local evidence

The reported deployed SHA was `909bfd7`, with Telegram `ValueError` and Linq
`UnsupportedChatFileError` on October 14. Source inspection finds two matching bugs:
Telegram voice passed encoded OGG bytes to `prerecorded_from_bytes` with no encoding;
Parakeet/Modulate label that unchanged payload `audio.wav`. Empty words then raised
`ValueError('Voice transcription empty')`. This is an input-format contract failure,
not proof that every provider assumes raw PCM. Linq classified only `voice_memo`
parts as voice; documented audio `media` parts instead reached FileChatTool, whose
allowlist rejects audio. The old Linq voice fixture covered only `voice_memo` and
hid that branch; it now represents an audio `media` part.

Provider sources: [Linq voice formats and media attachments](https://docs.linqapp.com/channel/imessage/api/resources/chats/methods/send_voicememo/),
[Linq message parts and reply metadata](https://docs.linqapp.com/channel/imessage/api/resources/chats/),
[Telegram message fields](https://core.telegram.org/bots/api#message).
Tests run real FFmpeg on committed synthetic OGG/Opus, M4A, CAF, MP3, WAV, WebM and
MP4 fixtures; only STT IO is stubbed. HEIC conversion also runs its real decoder.
The fixtures verify PCM shape, provider kwargs, empty/error handling, worker completion
and lease release. These reproduce the code-level mechanisms; no production trace,
provider response or real user audio was read, so exact production causality remains
an inference from the supplied logs and matching source behavior.

The 1.2-second quiet window and 3-second maximum wait remain admission bounds.
The generation fence extends merging through media preparation without sleeping on
the request path. A queued follow-up is still serialized by the existing inbox/lease.

## Production maintenance and alert install

Decision verified 2026-10-16: `backend` runs on Cloud Run with the existing GMP
collector. `prod-omi-gke` has namespace `prod-omi-backend`, Ready ExternalSecret
`prod-omi-backend-secrets`, and KSA `prod-omi-backend-listen` mapped to
`backend-listen-runtime@based-hardware.iam.gserviceaccount.com`; no backend CronJobs
are installed. Existing notification/X/FinOps jobs use Cloud Run. Keep cleanup on that
platform and Scheduler under `backend/deploy/scheduler/jobs.yaml`. The installed
`messaging-maintenance-hourly` trigger omits `lifecycle`, like other
active jobs. Full CI reconciliation now checks and maintains it; `planned` is only
for jobs not yet installed. Its invoker is `msg-maintenance-scheduler` (25 characters;
IAM [service-account IDs](https://docs.cloud.google.com/iam/docs/service-accounts-create)
must be 6–30 characters). No new workflow is needed.

Install status on 2026-10-16: the job, job-scoped invoker SA, enabled hourly
Scheduler trigger and six log counters are already installed. One manual cleanup
succeeded (`proofs=3`); runtime secret access was already present. Do not recreate
these resources, repeat the secret grant, or repeat that execution. Steps 2–3 below
are the new-install reference; existing installs need only a reviewed image update
when the admitted digest changes. The nine operational alerts are also live; keep
the tenth (context rate) held until the context rollout gate below passes.

The earlier 12:23 UTC audit found that the trigger-SHA label described a newer
commit than the admitted image. That deployment mismatch has since been corrected:
production now reports `OMI_BACKEND_RELEASE_SHA=5b0f5a9`, containing #21820, and
exports the new context metrics. Always use the revision's release SHA, admitted
workflow receipt and immutable image contents to verify source. A trigger label
alone is insufficient. Release further context changes through normal GitHub Actions.

`OMI_SHAPED_AGENT_MODE=on` routes all eligible `/v2/messages` app chats to non-shadow
shaped execution; channel LLM turns always take that runner. Requests rejected
before execution, ignored events and lightweight acknowledgements do not prepare
context. Session/history-less invocations are `unscoped`. The single uvicorn process
and loopback metrics thread share the default registry; no multiprocess or label
initialization workaround is indicated. Labelled series appear after observations.

The first corrected-release sample (four eligible app turns) lost optional context
on every turn. At 14:25 UTC, GMP p50/p95 in seconds were: digest .088/.099,
summary_load .10/.27, refresh_load .225/.86, source_page .6/3. Foreground samples
are censored by the old 75/150 ms deadlines. The uncensored refresh_load uses the
old guarded state loader and informed the one-second overlapping window. The old
loader used three serial document reads for app, four for channel, plus transaction
overhead. Request prefetch now uses two bounded RPCs: a projected session link lookup
and a BatchGet of session/user/deletion/link. At use, one additional projected BatchGet
checks those fences against the snapshot. Background refresh keeps its transaction.
No request prefetch uses `db_executor`; context capacity cannot queue behind or ahead
of setup work. Guard reads remain point-in-time: a mutation after the fresh snapshot
and before/during the provider call can still race, as with any read-based authorization.
There are no intervening setup awaits after this validation. Digest is one bounded 20-candidate query plus local decryption.
Background source paging adds guarded access, a logical-ID boundary query, a source
page and model work; its latency does not belong on the foreground path. No per-RPC
production timing is available; these counts come from the guarded call graph.

`backend-runtime@based-hardware.iam.gserviceaccount.com` already has
`roles/datastore.user`. Cleanup needs only Firestore and the existing
`ENCRYPTION_SECRET` import binding, not provider tokens, Redis or the broad Kubernetes
secret. Use the admitted backend image by digest, one task, 600 seconds, one retry,
30-day retention, maximum 100 candidates per category (unknown identity subtrees can contain more
records). A transaction refuses to purge an unknown identity while any running inbox
row remains, including FIFO-settled reconciliation evidence. Cleanup is idempotent and sends
nothing. Hourly scheduling exceeds the bounded 20-minute execution/retry window;
operators must not start overlapping manual executions.

The existing GMP collector exports `omi_*`. Read-only checks at 2026-10-16 06:10 UTC
confirmed 39 current backend chat-token series in GMP, with newest sample age about
4.6 seconds, and a current messaging-turn series. The GKE bridge did import data
within 24h (531 token series and 11 turn series), but it is currently unhealthy:
`up{job="cloud-run-application-metrics"}=0`, one down target, zero scrape samples,
connection refused, and no instant messaging/token series in Prometheus. The actual
Prometheus service is `prod-omi-kube-prometheus-s-prometheus`; its read-only API works.
The exporter pod was Ready at the later metadata snapshot, with restart count 59
and last termination reason `OOMKilled`; readiness alone is not scrape acceptance.
Historical samples do not establish live ingestion or healthy alert evaluation.

Production alerts therefore use Cloud Monitoring directly, bypassing the unhealthy
bridge: six content-free log-based counters for worker/maintenance failures by reason,
webhook 5xx, delivery, stale heads and recovery; a decoder startup log condition;
GMP PromQL for per-surface shaped-context degradation and queue age; built-in job
failures also catch process/import/OOM errors. No new exporter is needed. Installing `alerts.yaml` while the
bridge is down would leave those rules without current Cloud Run samples. Repair
and notification acceptance for the broader Prometheus/Grafana bridge are separate
operator work; this install establishes an independent alert path.

Cloud Monitoring's `LogMatch` checks one matching entry and cannot express a count
floor; a notification rate cap does not delay the first incident. Google explicitly
requires [log-based metrics to count logs](https://docs.cloud.google.com/logging/docs/alerting/log-based-alerts).
`backend/deploy/messaging/log-metrics.json` declares six DELTA/INT64 counters, with
only bounded `reason` labels where needed. [ALIGN_SUM and REDUCE_SUM](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.alertPolicies#Aggregation)
sum matching entries across instances in each alignment window; `COMPARISON_GT 2`
means at least three entries, not three time series. These are observations, not
necessarily distinct failed turns. No raw payload or customer label is extracted.

| Policy | Count floor | Rationale |
| --- | --- | --- |
| Worker failures, webhook 5xx, outbound failures, stale queue head, recovery unavailable | >=3 entries / 15-minute alignment window (worker failures per reason) | Suppress a lone transient at the observed low traffic volume. |
| Maintenance failure by reason | >=2 entries / 60-minute alignment window, per reason | One failed attempt can recover on the configured retry; repeated same-reason failures merit investigation. |
| Decoder unavailable | One exact startup-readiness failure, hourly notification cap | The once-per-startup decoder probe proves that instance cannot decode voice; text health does not offset this outage. |
| Cleanup execution failed | >=1 failed completed execution / 5 minutes | The hourly job has already exhausted its retry. Requiring multiple executions would conceal an outage for hours; import/OOM may emit no application failure log. |

The shaped-context 20-turn minimum and 10-minute dwell, and queue p95's 10-minute
dwell, are unchanged. Counter alerts have no additional dwell after their count floor.
Counter data starts at installation, with [no historical backfill](https://docs.cloud.google.com/logging/docs/logs-based-metrics).
Allow ingestion/evaluation delay; an absent series before a match is not a zero or
proof of notification delivery. Install and verify the counters before enabling the
policies. The tool refuses policy writes until all six metric definitions MATCH.
Logging has no validate-only metric write API: `log-metrics --check` is the no-write
plan; `--apply` uses [metrics.update PUT/upsert](https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/projects.metrics/update)
and verifies each resource. It refuses incompatible existing metric schemas before
writing. The existing operator needs `logging.logMetrics.get` and
`logging.logMetrics.update`; no backend runtime permission is added.

Cloud Run v2 [jobs.patch](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/patch)
accepts the complete `Job` body with `validateOnly`/`allowMissing`, and has no
`updateMask` parameter. The official [UpdateJobRequest schema](https://github.com/googleapis/googleapis/blob/master/google/cloud/run/v2/job.proto)
also has no field mask. This tool owns the declared job configuration and sends its
complete desired body, including the image and task template; do not use it to
preserve ad hoc sidecars or other untracked job configuration. For an existing job,
`--validate` sends PATCH with `validateOnly=true`; `--apply` sends the same body with
`validateOnly=false`. Neither starts an execution. Regression tests exercise both
existing-job paths and the CLI validation path. Creation sends the identity in
`jobId` and omits `Job.name` from the POST body; GET/comparison/PATCH retain the name
([CreateJobRequest](https://github.com/googleapis/googleapis/blob/master/google/cloud/run/v2/job.proto)).

The sequence below is **for the authorized operator**, from the repository root.
The operations tool uses the explicitly selected gcloud identity; Scheduler
commands below opt into the same behavior with `--gcloud-auth`. Tokens stay in
process memory and are never printed. A separate ADC login is not needed.
All local checks and production reads in this lane used `ro-prod`; no commands that
write production were run. Use the existing release process first to admit/build the
changed backend image. Set `ADMITTED_BACKEND_IMAGE` to that receipt's full
`gcr.io/based-hardware/backend@sha256:...` (after the plan B B3 cutover, the
`gcr.io/based-hardware/backend-workers@sha256:...` digest; `messaging_operations.py`
admits exactly those two repositories).
Do not substitute `latest` or the previously serving image: it lacks the new
maintenance failure logging/context telemetry. Normal backend deployment starts the
new context/album behavior; the cleanup job is a separate install.

1. Readiness and dry-run. All seven messaging index requirements were READY at the
   audit. Recheck from the exact admitted source; no index mutation is required by
   this change. Exit 1 from an operations `--check` means a reviewed planned diff;
   other errors must be resolved before applying. `--validate` sends Cloud Run's
   `validateOnly=true`, never creates a job and never executes cleanup
   ([create API](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/create),
   [patch API](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/patch)).

```sh
source ~/.local/bin/gcp-agent-env.sh ro-prod
: "${ADMITTED_BACKEND_IMAGE:?Set the admitted backend image digest}"
backend/.venv/bin/python backend/scripts/reconcile_firestore_indexes.py \
  --manifest firestore.indexes.json --source-root "$PWD" \
  --project based-hardware --database '(default)' --check-only
backend/.venv/bin/python backend/scripts/messaging_operations.py job \
  --image "$ADMITTED_BACKEND_IMAGE" --check
backend/.venv/bin/python backend/scripts/messaging_operations.py log-metrics --check
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --check \
  --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
```

The channels above were the existing production external Grafana dead-man channels
at audit time, read without destination details. Verify they remain the intended
operator destinations. The `ro-prod` account currently lacks `cloudscheduler.jobs.list`;
a Scheduler check may need the operator identity. Do not expand the read-only bot's
permissions as part of this change. Monitoring has no validate-only create API;
`alerts --check` is the no-write diff. A missing new metric is expected before the
backend rollout, not proof of zero fallbacks. Run the job validation as operator if
read-only IAM denies Cloud Run validation; do not interpret that denial as job drift.

2. Create/update the job using the human operator identity, or an identity with
   `iam.serviceAccounts.actAs` on `backend-runtime@based-hardware.iam.gserviceaccount.com`
   plus the required Cloud Run job permissions. The `prod-operator` tier does **not**
   have that actAs grant and fails with HTTP 403; do not use it for job validation
   or apply. No execution starts. Recheck after the asynchronous operation finishes, and require MATCH.
   The read-only identity could not inspect Secret Manager IAM. If validation reports
   missing runtime access to `ENCRYPTION_SECRET`, the human IAM operator must inspect
   that secret's policy and, only if absent, grant its accessor role on that secret:

```sh
source ~/.local/bin/gcp-agent-env.sh human
gcloud secrets get-iam-policy ENCRYPTION_SECRET --project=based-hardware \
  --flatten='bindings[].members' \
  --filter='bindings.members=serviceAccount:backend-runtime@based-hardware.iam.gserviceaccount.com' \
  --format='value(bindings.role)'
# Only if runtime access is absent / validation confirms permission denial:
gcloud secrets add-iam-policy-binding ENCRYPTION_SECRET --project=based-hardware \
  --member='serviceAccount:backend-runtime@based-hardware.iam.gserviceaccount.com' \
  --role=roles/secretmanager.secretAccessor
```

   No secret payload is read. Do not add project-wide Secret Accessor. Then rerun
   validate-only and apply with that actAs-capable human operator identity:

```sh
source ~/.local/bin/gcp-agent-env.sh human
backend/.venv/bin/python backend/scripts/messaging_operations.py job \
  --image "$ADMITTED_BACKEND_IMAGE" --validate
backend/.venv/bin/python backend/scripts/messaging_operations.py job \
  --image "$ADMITTED_BACKEND_IMAGE" --apply
gcloud run jobs describe messaging-maintenance-job --project=based-hardware \
  --region=us-central1 --format='yaml(status.conditions)'
backend/.venv/bin/python backend/scripts/messaging_operations.py job \
  --image "$ADMITTED_BACKEND_IMAGE" --check
```

3. Least-privilege Scheduler identity. IAM requires the human identity. First
   inspect whether the dedicated account already exists; create only when absent.
   Grant `roles/run.invoker` **on this job only**, never on the project. The existing
   Cloud Scheduler service agent retains its existing service-agent role. Do not
   grant KMS/storage/Firestore roles to this invoker. No context repair IAM grant
   is needed: its reproducible PermissionError is a logical-ID/address mismatch.

```sh
source ~/.local/bin/gcp-agent-env.sh human
gcloud iam service-accounts list --project=based-hardware \
  --filter='email:msg-maintenance-scheduler@based-hardware.iam.gserviceaccount.com' \
  --format='value(email)'
# Only if the account is absent:
gcloud iam service-accounts create msg-maintenance-scheduler \
  --project=based-hardware --display-name='Messaging cleanup Scheduler invoker'
gcloud run jobs add-iam-policy-binding messaging-maintenance-job \
  --project=based-hardware --region=us-central1 \
  --member='serviceAccount:msg-maintenance-scheduler@based-hardware.iam.gserviceaccount.com' \
  --role=roles/run.invoker
# CI's scheduler reconciler (omi-ci-deployer-prod) patches oauthToken on drift and
# must be able to act as this account, like the other Scheduler invokers:
gcloud iam service-accounts add-iam-policy-binding \
  msg-maintenance-scheduler@based-hardware.iam.gserviceaccount.com --project=based-hardware \
  --member='serviceAccount:omi-ci-deployer-prod@based-hardware.iam.gserviceaccount.com' \
  --role=roles/iam.serviceAccountUser
backend/.venv/bin/python backend/scripts/scheduler_reconcile.py \
  --gcloud-auth --environment prod --project based-hardware --check --jobs messaging-maintenance-hourly
backend/.venv/bin/python backend/scripts/scheduler_reconcile.py \
  --gcloud-auth --environment prod --project based-hardware --apply --jobs messaging-maintenance-hourly
backend/.venv/bin/python backend/scripts/scheduler_reconcile.py \
  --gcloud-auth --environment prod --project based-hardware --check --jobs messaging-maintenance-hourly
```

4. Install the six log counters first. Apply the nine operational policies separately
   from the shaped-context rate policy using `--alert-group` below. After the counters
   MATCH and notification destinations are approved, the nine can be applied without
   waiting for shaped traffic. Confirm the admitted source is actually in both serving
   backend and cleanup images before claiming their new logging is covered. Apply the
   rate policy only after the release containing prefetch isolation and fresh mount fences is verified, old
   instances have drained, and a full 30-minute window contains only new outcome
   semantics. Verify fresh context/read/overlap samples by surface. Require at least
   20 eligible turns in that window and a summary-loss fraction at or below 5% before
   calling the fix accepted and applying the tenth policy. If the gate fails, keep it
   held and investigate setup overlap; do not hide pending summaries in the denominator.
   The alert itself fires above 5% with a 10-minute dwell. Low-volume surfaces remain
   below its evaluation floor and need an explicit observation window, not a healthy claim.
   Missing data cannot validate the alert. Review only the six declared counters and ten named Monitoring policies. The tool refuses
   duplicate managed display names, preserves condition identities on update,
   verifies writes, and leaves every other policy alone. It never prints API error
   bodies. Use the existing authorized Monitoring operator identity; this example
   continues the human operator session from the IAM step.

```sh
backend/.venv/bin/python backend/scripts/messaging_operations.py log-metrics --check
backend/.venv/bin/python backend/scripts/messaging_operations.py log-metrics --apply
backend/.venv/bin/python backend/scripts/messaging_operations.py log-metrics --check
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --check --alert-group operational \
  --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --apply --alert-group operational \
  --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --check --alert-group operational \
  --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
```

The nine operational policies are already live: use their check command to verify
them and apply only for reviewed drift. After the rollout gate above, install only
the tenth policy with this branch's updated summary-loss numerator:

```sh
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --check \
  --alert-group context-rate --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --apply \
  --alert-group context-rate --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
backend/.venv/bin/python backend/scripts/messaging_operations.py alerts --check \
  --notification-channels \
  projects/based-hardware/notificationChannels/7795172925536204487 \
  projects/based-hardware/notificationChannels/4018667585736557040
```

Selection never deletes or disables the unselected policies. Keep the denominator
as eligible `prepare()` outcomes, not app HTTP requests, completed channel turns or
provider-token callbacks: these include rejected/lightweight turns or multiple model
calls and would dilute the context failure rate. Track a separate shaped-traffic/export
coverage signal when eligible traffic is expected; do not interpret no series as healthy.
For low-volume channels below the 20-turn floor, consider a separate absolute
failure-count warning, rather than diluting the rate with unrelated chat traffic.

5. Execute one bounded cleanup, verify success and counts-only output, then observe
   the next scheduled execution. Never run `--prepare-launch` for this no-cap cohort.

```sh
gcloud run jobs execute messaging-maintenance-job --project=based-hardware \
  --region=us-central1 --wait
gcloud run jobs executions list --job=messaging-maintenance-job \
  --project=based-hardware --region=us-central1 \
  --format='table(metadata.name,status.conditions[0].type,status.conditions[0].status)'
```

Inspect only `Messaging maintenance counts=` aggregates or
`outcome=failed reason=... error_type=...`, not arbitrary execution logs. Verify the
Scheduler invocation identity and job-level invoker binding. Verify the ten policies
show the intended notification channels. Test notification delivery through an
approved test destination; policy creation alone does not prove delivery. Do not
inject synthetic prod errors or send a test page without the operator's approval.

After rollout, query GMP directly (or Grafana after its bridge is repaired):

```promql
sum by (surface, outcome) (increase(omi_chat_context_turns_total{cluster="__run__",namespace="backend"}[24h]))
histogram_quantile(0.50, sum by (surface, phase, le) (rate(omi_chat_context_read_seconds_bucket{cluster="__run__",namespace="backend"}[1h])))
histogram_quantile(0.95, sum by (surface, phase, le) (rate(omi_chat_context_read_seconds_bucket{cluster="__run__",namespace="backend"}[1h])))
histogram_quantile(0.50, sum by (surface, le) (rate(omi_chat_context_setup_overlap_seconds_bucket{cluster="__run__",namespace="backend"}[30m])))
```

`unscoped` is excluded from eligible-turn rates. `summary` means stored continuity
was available and the digest read succeeded; `empty` means the state read succeeded
without an existing summary. `digest_degraded` means a stored summary survived but
the digest failed or was not ready. `empty_digest_degraded` means there was no prior
summary and the digest failed or was not ready; empty-rate dashboards should include
both `empty` and `empty_digest_degraded`. Both require a successful fresh fence check. `degraded` means
a state/fence read failed or the snapshot was invalidated; `summary_pending` means
a read/check was unfinished or context capacity was exhausted at model mount.
Only `degraded|summary_pending` enter the alert numerator; every non-unscoped outcome
enters the denominator. The managed policy name stays unchanged. Never mix old
`degraded` semantics (which included digest-only failures) into the acceptance window.

Read histograms include executor admission and are censored at the read deadline
(or cancellation), not raw Firestore RPC latency. Compare
`omi_chat_context_setup_overlap_seconds` with read latency by surface: a one-second
window cannot help a 100 ms setup consume a 270 ms load. Full ready outcomes should
dominate when setup overlap exceeds those reads; the four-turn sample cannot establish
a post-fix percentage. If summary_pending remains high, begin prefetch earlier in the
request or investigate batching guarded reads, preserving transaction/generation fences.
The mount guard costs one fresh projected RPC, capped at 150 ms, and no fresh read
waits for pool admission. Direct runner helpers without router prefetch keep the
150 ms total prepare cap; their already-guarded snapshots can be at most that old
when consumed. All production shaped turns enter through the router and use the
fresh mount fence. A digest uses a false-predicate Retry rather than `retry=None`,
which the installed Firestore Query error handler dereferences and masks with an
AttributeError on GoogleAPICallError.

Persisting a per-session activity digest is deferred: it requires cross-session freshness
and invalidation rules, adds writes and does not remove the guarded session read.
Simply extending an awaited foreground budget to one second would add up to one
second; router prefetch does not add that wait, while its fresh guard adds at most
150 ms. Verify first-token latency and the `fence_check` histogram after release;
optional context no longer competes for setup's database workers.

Warning logs carry only bounded surface/phase, exception type and code site. Analyze
refresh warnings separately. `summary capped` is informational: the model's soft length
instruction can overrun, but the summary is deterministically clipped to 2,400 characters
before every checkpoint/save. Empty/invalid summaries still fail without advancing
the partially summarized page.

Rollback maintenance by pausing only `messaging-maintenance-hourly`; retain the job,
indexes and all data. Disable these named Monitoring policies if their routing needs
repair. Backend code rollback uses the normal release mechanism; existing appendable
album rows must finish under the new worker before rolling back that protocol.
