# Messaging channels rollout

Telegram and iMessage chat for one production uid. The backend switch, the uid
allowlist, and the valid paid-plan gate all fail closed. This runbook
does not deploy, merge, or read secret payloads.

The mobile entry is a separate PostHog flag, `mobile-chat-apps`. The server
does not trust that flag. A uid outside `OMI_MESSAGING_CHANNELS_UIDS`, or a
backend with the switch off, gets 403 on mint and no channel turns.

## Enable the David-only cohort

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

## Kill switch

1. Set `OMI_MESSAGING_CHANNELS=off` and roll the backend. Admission and new
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
local waitlist. Insights is stored and not honored. There is no clear-history
route separate from unlink.
