# Telegram and iMessage adapters (Stage B)

This adds real providers to the [foundation](messaging-channels.md). The feature,
provider flags and exact UID cohort remain off/empty by default.
Production config enables only David on Cloud Run `backend`; provider setup remains
a separate operator step. Admission accepts every valid paid catalog plan.

## Provider choices and verification (2026-10-10)

Telegram uses the official [Bot API](https://core.telegram.org/bots/api#sendmessagedraft).
`sendMessageDraft` supports private chats, a nonzero stable draft ID, and a temporary
preview. It does not require Business mode or a topic. Default streaming is `draft`;
`OMI_TELEGRAM_STREAMING=edit` explicitly selects edit previews; `none` buffers. Every
final reply uses `sendMessage`. Drafts are throttled, never counted as final receipts.
Plain Markdown is normalized and fully escaped to MarkdownV2, then split safely at
UTF-16 and escape boundaries. This conservative dialect preserves readable prose;
it does not preserve every Markdown style. Group/bot/edited messages are ignored.

Linq's current [index](https://docs.linqapp.com/llms.txt) and
[authentication](https://docs.linqapp.com/channel/imessage/guides/authentication/)
confirm `https://api.linqapp.com/api/partner/v3` and Bearer auth.
[Webhooks](https://docs.linqapp.com/channel/imessage/guides/webhooks/) specify decoded
`whsec_` keys, raw-byte `id.timestamp.body` HMAC, and Standard Webhooks headers.
The adapter requires Standard Webhooks and accepts multiple v1 signatures; timestamps
outside +/-300 seconds fail. Legacy-only headers fail closed: the conflicting legacy
scheme is deliberately not guessed, and invalid Standard headers never downgrade.
Both documented payload versions (2025-01-01 and 2026-02-03) normalize to the same
message identity. Unknown versions fail. Subscribe to `message.received`; edits and
receipt events cannot re-execute a turn. iMessage replies request `iMessage` service.
Provider fallback behavior still needs confirmation with the sandbox/account.

`IMessageProvider` keeps Linq-specific parsing, verification and API calls replaceable.
`OMI_IMESSAGE_PROVIDER=linq` selects the implemented provider. Sendblue is an interface
extension, not an untested implementation pretending to be supported.

## Runtime configuration

Runtime secret values come from the existing deployment secret bindings, never checked-in
files. Enabling a provider without credentials fails startup.
Production bindings are declared only for Cloud Run `backend`.

| Setting | Default / meaning |
| --- | --- |
| `OMI_MESSAGING_CHANNELS` / `OMI_MESSAGING_CHANNELS_UIDS` | off / empty, foundation admission |
| `OMI_TELEGRAM_ENABLED` | off |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_WEBHOOK_SECRET` | runtime secrets |
| `OMI_TELEGRAM_STREAMING` | draft; explicit edit or none |
| `OMI_IMESSAGE_ENABLED` / `OMI_IMESSAGE_PROVIDER` | off / linq |
| `LINQ_API_KEY` / `LINQ_WEBHOOK_SECRET` | runtime secrets |
| `OMI_IMESSAGE_MAX_SEND_RECEIVE_RATIO` | 3; accepted range 1–5 |
| `OMI_IMESSAGE_CONTACT_CARD` | off; enable only after configuring the Linq contact card |

The actual registered routes are `/v1/messaging/webhooks/telegram` and
`/v1/messaging/webhooks/imessage`; setup-guide `/v1/channels/...` paths were placeholders.
Startup/periodic recovery drains only pending jobs. Running jobs and leases remain fenced.

## Media, tools and presentation

Inbound media references are encrypted in the inbox and downloaded only after linking,
entitlement admission and lease acquisition. Telegram fetches through `getFile`; Linq
accepts only HTTPS `cdn.linqapp.com`. Redirects and credentials in URLs fail. Files are
bounded at 20 MB. Voice bytes enter Omi's existing prerecorded STT before the turn.
Photos/documents enter `FileChatTool.upload` and the existing per-user chat file collection;
file IDs join the channel session so `search_files_tool` can find them.

Outbound files are looked up under the current principal UID; metadata and size must match.
A model-supplied path or URL is never accepted. Telegram chooses document/photo/voice.
Linq pre-uploads bytes to `uploads.linqapp.com`, honors required upload headers, and sends
the resulting attachment ID. OGG is excluded from iMessage output. Linq contact-card
sharing is available only when configured. Tools accept no destination or foreign message
ID; reactions are restricted to the current inbound message. Every action passes the same
reply policy and current link guard, including on retries after rate backoff.

Indexed citations become inline source phrases (title when supplied, generic Omi source
phrase otherwise). Telegram follow-up suggestions use inline callbacks when they fit the
64-byte limit; iMessage drops them. Device-only charts (`create_chart_tool`) are excluded
from channel advertisement and execution by the same projection; app tools are unchanged.

## Ratio, retries and recovery

The content-free ledger lives beneath each channel identity's `delivery_chats/{chat_hash}`.
Inbound message-ID markers credit exactly once. Outbound reservations atomically enforce
`sent + 1 <= received * ratio` for iMessage. Link/help/error/status texts, files, tapbacks
and contact cards count; typing does not. There are no unsolicited sends. Credit lasts
for the linked chat lifetime; unlink removes it. The limit can block a very long answer
or a tool-heavy turn; request a new inbound message rather than bypass it.

429s honor retry_after / Retry-After within a bounded four-attempt, 60-second delay budget.
Linq text sends retry 5xx/transport faults with stable idempotency keys. Telegram sends
cannot safely retry ambiguous 5xx/network outcomes; a reserved receipt blocks replay.
Linq reactions/contact/upload creation have no assumed idempotency and fail ambiguously.
HTTP/provider exceptions contain no body or credential URL; provider HTTPX receipts are
filtered to prevent Telegram-token or signed-CDN-URL logs.

To recover a running job: first prove the worker stopped, inspect its receipt state and
provider ID, reconcile delivery/effects with the sandbox/dashboard, then deliberately
reset the specific job/lease. Never blindly reset reserved Telegram receipts. An accepted
Linq receipt suppresses repeats, and a reserved Linq text receipt may use the same provider
idempotency key. Pending recovery uses the existing bounded Firestore contention-retry
primitive. No deploy, queue workflow or automatic ambiguous replay is added.

## Undo

Memory preference and task creation/update, playbook/trigger creation, and standalone
fact closure record a surface-scoped encrypted inverse receipt. User-visible text reports
the write and a five-minute undo window; Telegram adds an undo callback. App behavior
adds no inverse IO. Receipts are removed with their session on unlink/account deletion.
Undo claims once; ambiguous inverse outcomes remain `running` and are never replayed.
Task restoration compares the complete observed row inside a transaction and cancels or
restores scheduled reminders. Memory inverses use the universal `MemoryService`; closed
facts use its lineage-preserving reopen operation. Changed/historical memories fail closed.
Calendar/external writes retain their existing tools and are outside these local inverse
receipts. A memory content check can race a separate surface mutation before service entry;
full conditional cross-surface memory inverse admission remains a rollout risk.

## Verification layers

Unit/fixture: `BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/adapter-unit-files.txt" bash backend/test.sh > /tmp/msg-adapters-unit.log 2>&1`.
The adapters run Stage A's contract suite with replayed provider transport. The contract
checks invalid authentication headers (Telegram has no body signature) and compares rendered
status text, with separate raw-body tampering tests for Linq. Fixture provenance is in
`testing/messaging/fixture-provenance.md`: documented synthetic payloads, no real messages.

Emulator: start a loopback Firestore emulator, select `test_messaging_firestore.py` and
`test_messaging_adapters_firestore.py` through `backend/test.sh`, set
`MESSAGING_TEST_FIRESTORE_HOST=127.0.0.1:<port>`, and log output. Tests use anonymous
credentials and unique `demo-` projects; no cloud database is contacted.

## Live dev harness (manual, never CI)

`testing/messaging/live_adapters.py` listens on loopback; an already-configured dev webhook
must tunnel to it. It uses the real adapters, gateway, shared turn service and providers.
A human sends messages from separate QA Telegram/iMessage clients. Bots cannot impersonate
an inbound Telegram user, so a scripted fake POST is not claimed as live coverage.

Create a non-secret local JSON config with `test_uid`, `test_account_verified: true`,
`telegram_test_user_id`, `telegram_dev_bot_id`, `linq_test_handle`, `linq_dev_line`,
`webhook_origin` (HTTPS origin only), and `secret_project: "based-hardware-dev"`.
All identities must be dedicated test identities. The harness rejects non-test senders
before persistence; its storage and recovery paths cannot address another user's account
or another identity. It verifies Telegram bot/webhook and Linq line before readiness.
The existing backend dev environment and test account must support valid paid-plan admission.
Do not use David's real account, `?rig=dev`, or signed-in `api.omi.me` calls.

Run `--check-only` to validate non-secret configuration without cloud IO. Runtime secrets
are read only by the four `-dev` Secret Manager names from the setup guide. The current
`gcp-agent-env.sh` explicitly reserves payload reads for the `human` tier; read-only agent
metadata access does not authorize payload access. The human operator selects that tier
for a live run. The harness never silently switches identity, prints secrets, changes
webhooks, writes secrets, deploys or creates provider accounts.

From `backend/`, run `.venv/bin/python testing/messaging/live_adapters.py --config <local.json> --transcript <new-local.jsonl>`.
Link using the app's proof flow, then run help, ordinary text, a long answer, citations,
voice, photo, document, send-file, tapback, task write, undo, and unlink. Record observed
client rendering and any provider quirks alongside the transcript; add each discovered
issue as a sanitized fixture before rerunning. Only synthetic QA content is permitted.
The transcript is mode 0600, redacts link proofs, and contains accepted outbound text and
content-free failures. Do not commit it or use it for training/datasets.

Live dev is **not run** until setup is confirmed. Missing values at implementation time:
`test_uid` and test-account verification, `telegram_test_user_id`, `telegram_dev_bot_id`,
`linq_test_handle`, `linq_dev_line`, and `webhook_origin`; also confirmation of test-account
paid-plan entitlement/cohort, the configured webhook tunnel/subscriptions, and authorized
runtime payload access. The dev secret project and four secret names are known from the
setup guide; their existence/enabled versions remain unconfirmed because `ro-dev` metadata
reads returned permission denied. Linq's written AI-use,
retention, fallback and production-number assurances also remain provider rollout risks.
