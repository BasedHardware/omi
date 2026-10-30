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
Standard Markdown is rendered as Telegram HTML, then split at UTF-16 boundaries
with balanced tags and intact entities. Definite entity-parser rejection falls back
to plain text; ambiguous delivery failures never trigger a second send. Group/bot/edited messages are ignored.

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
Startup/periodic recovery drains only pending jobs. Failed running jobs remain fenced.
Handled worker failures, including a finished turn's CancelledError, release the
lease. In-flight task cancellation and process loss keep the lease for operator
reconciliation.

## Media, tools and presentation

Inbound media references are encrypted in the inbox and downloaded only after linking,
entitlement admission and lease acquisition. Telegram fetches through `getFile`; Linq
accepts only HTTPS `cdn.linqapp.com`. Redirects and credentials in URLs fail. Files are
bounded at 20 MB. Voice bytes enter Omi's existing prerecorded STT before the turn.
Photos/documents enter `FileChatTool.upload` and the existing per-user chat file collection;
file IDs join the channel session so `search_files_tool` can find them.
Videos (including Telegram video notes) are read as stills plus speech, in parallel
(`utils/media/video_frames.py`): up to six distinct frames become one numbered contact
sheet stored as the chat file, every sampled frame is kept in a filmstrip for
`search_files_tool(start_seconds=, end_seconds=)`, and the clip itself is not stored.
A muted clip still answers from its frames; a picture-less clip falls back to its transcript.

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

Shared memory/task tools emit structured `ActionReceipt` values from the confirmed
write's canonical object ID and outcome data. They reuse the in-app `memoryLink`
(`MemoryLinkSpec`) and `taskCard` (`TaskCardSpec`) vocabulary. No model text is parsed
into write authority. Memory preference and task creation/update, playbook/trigger
creation, and standalone fact closure record an encrypted inverse per action.
The assistant answer has no undo footer or controls. Each action gets a separate
confirmation bubble. Telegram attaches `Undo` with that receipt's opaque ID, not a
"last write" command. The adapter acknowledges every supported callback immediately.
After successful undo it edits the persisted confirmation message to `— Undone` and
removes its button. A second tap never repeats the inverse; an interrupted edit can
be retried separately. Legacy unscoped Telegram controls cannot reverse a newer write.

Linq has no inline buttons: it renders a plain action receipt and accepts text `undo`
only when the latest write turn contains exactly one receipt. Multiple writes are
ambiguous and fail closed. A subsequent write invalidates the text selector before
mutation. Specific Telegram receipts survive later writes. The inverse admission
window remains five minutes, without model narration of commands/time windows.
App behavior adds no inverse IO. Each new write deletes up to 100 receipts expired
for more than a day, bounding active-session snapshot accumulation while preserving
a day for cleanup/edit reconciliation. Idle sessions retain receipts until the next
write or session removal; no Firestore TTL policy is assumed. Receipts are removed
with their session on unlink or account deletion. Repeated Linq text undo replies
“Already undone”; acknowledged Telegram taps remain no-ops.

An inverse atomically claims its own receipt once. A tracked async coordinator runs
that domain operation on `postprocess_executor`, outside the chat lease and DB worker
pool, because canonical privacy cleanup may take minutes. Other chat turns can proceed.
The memory content check is not in the same transaction as `MemoryService` delete or
update, so a concurrent correction during that cleanup can still be overwritten.
That race is limited to one user's fact, the five-minute receipt window, and one
claim; it is not cross-user. It remains a rollout risk, not a reason to hold the
chat lease.
Inverse exceptions send a guarded short error and leave that inverse `running` for
reconciliation; ambiguous effects are never replayed. Ordinary settled turn failures
retain the running inbox row for reconciliation, try an error reply only before accepted
delivery, and release the surface lease. A settled FIFO marker allows the next update
without replaying this row. Shutdown cancellation retains fencing when executor/provider work may still be alive.

Task restoration compares the complete observed row inside a transaction and cancels
or restores scheduled reminders. Memory inverses use the universal `MemoryService`;
closed facts use its lineage-preserving reopen operation. Changed/historical memories
fail closed. Calendar/external writes retain their existing tools and are outside these
local inverse receipts. A memory content check can race a separate mutation before
service entry; full conditional memory inverse admission remains a rollout risk.

Dated reminders use the same `create_action_item_tool` and existing reminder data/push
path as Omi chat. Delivery is through Omi's reminder system, not an unsolicited Telegram
message (this rollout permits replies only). The channel skill explains that limit;
a Telegram-only delivery request must get an explicit limitation, not a promise.

## First-message feedback

Typing begins immediately after linked-account admission, before session creation,
media preparation, history/digest work and model setup. It refreshes every four seconds
on Telegram; provider typing failures have a two-second budget and cannot abort the turn.
A content-free `Messaging phase=typing` elapsed time is logged. First-use awareness reads
only twenty recent messages; older context remains available through history/memory
tools. Channels skip the unused legacy prompt/context load because `chat_mount` is their
sole prompt authority. App prompt selection and bytes remain unchanged.

The first live QA evidence and fixture measurements are recorded in
[the channel runbook](runbooks/messaging-channels.md#first-live-qa-2026-10-11).

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

## Ordered backlog and reminder clock

An identity's inbox is admitted in `created_at` order inside the claim transaction.
The oldest pending or unsettled running job is the only eligible head. Settled
failures retain their running row and carry `fifo_settled_at`; they are never replayed
and no longer block admission of the next job. Recovery scans in
that order; after release, the worker wakes the next pending head. An ambiguous
running head still needs operator reconciliation, never TTL stealing. Private
channel identities have one thread, so this also serializes their normal replies.
Undo cleanup edits its original receipt; stale/duplicate callbacks do not emit new
unscoped replies. Linq text undo pins the selected receipt before background work.
Confirmed receipts and undo requests enter the ordered channel history.

The channel runtime carries the original message time. Telegram normal messages
use the verified update's `message.date`; callbacks lack a tap timestamp and use
first webhook admission time. Linq uses the message `sent_at` (`data.sent_at` on
`2026-02-03`, `data.message.sent_at` on `2025-01-01`), not webhook `created_at`
or worker time. Admission clamps a provider clock more than five minutes ahead
to server time, and raises a clock older than one day up to that one-day floor,
so a skewed or replayed stamp cannot schedule a far-future reminder or be
rewritten onto processing time. A relative reminder whose due time is already
past is saved at that instant and reported as missed; the tool does not ask the
model to pick a new future time. Shaped evidence
includes a server-verified request clock in the user's timezone. Relative reminders
use `create_action_item_tool(due_in_minutes=N)`, which computes `due_at` from that
original time. A reminder is an action item, not a separate scheduled-message object.
Future confirmations state phone delivery through Omi's silent FCM/local-notification
path. If backlog makes the original time past, save that due time, report the missed
time, and do not reschedule it or claim a phone notification was scheduled.
`omi_initiated` remains denied: no later Telegram reminder message is sent.

The FIFO query adds composite index `messaging_inbox_fifo` on collection `inbox`
(`status ASC`, `created_at ASC`, `__name__ ASC`), declared in
`database/messaging_queries.py` and generated into `firestore.indexes.json`.
Deploy index reconcile creates it; the backend shipment gate requires that
composite READY on the target project before rollout. No index or
production-state changes are performed by this PR.

A busy surface lease requeues the inbox head and does not wake that same head.
The lease holder wakes the oldest pending row on release. The thirty-second
pending drain covers a leaked lease. That avoids a claim/wake spin.

A newer plain message replaces a running reply that nobody has seen yet. Enqueue
stamps a content-free `supersedes` flag on each row (false for commands, button
callbacks, link proofs and album parts). While a turn streams, a side task checks
every `SUPERSEDE_POLL_SECONDS` for a newer flagged pending row, using the same
`status`/`created_at` index as the drain. The turn stops at its next frame only if
the sink has delivered nothing and no tool wrote anything. It sends no apology,
completes its row and releases the lease, so the newer message is answered next
with the replaced one still in the session history. Otherwise the queue stays FIFO.

For the October 11 burst, logs establish the callback's canonical cleanup at
09:17:36 / 09:22:34 UTC and two provider failures at 09:24:39 / 09:25:06. Task creation
resumed at 09:31:21 and 09:31:27 on another already-existing instance of the same
revision. The deployed lease has no TTL and no Firestore TTL policy for its collection,
recovery polls every thirty seconds, no
Cloud Tasks dispatcher exists for this inbox, and request-only CPU throttling was
disabled. Those mechanisms do not supply a ten-minute automatic release. Historical
lease release/reset was not logged and Firestore audit evidence is unavailable;
its exact owner and trigger remain unresolved. New content-free lease acquisition,
release, and queue-age events make future recovery timing distinguishable.

The last task's stored due time was 09:35 UTC, not its message-time target 09:29.
A reminder-cancellation send for the QA principal followed at 09:31:31. Together
with the old single overwritten inverse document and the reported second successful
undo, this strongly suggests the newer task was reversed by a stale callback.
The cancellation log contains no task identifier, so this is an inference, not an
audited object-level reversal record. Canonical-memory cleanup proves a memory
inverse ran earlier; the available logs do not independently identify its fact.
