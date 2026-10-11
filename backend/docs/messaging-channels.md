# Messaging channels foundation

Stage A provides channel-neutral contracts, shared turn execution, durable admission,
and a loopback harness. [Stage B adapters](messaging-adapters.md) add opt-in Telegram
and iMessage providers; no channel is enabled by default.

## Shared turn and mobile compatibility

`utils/chat_turn.py:run_chat_turn(uid, surface, session, message, reply_sink, *, principal)`
extracts the existing `/v2/messages` implementation. `TurnOptions` holds app selection,
platform, headers and optional analytics request context. Background callers need no
FastAPI Request. Synchronous preparation runs on `db_executor`; the response iterator
is consumed asynchronously while the caller owns the surface lease. `MobileReplySink`
preserves the existing SSE wrapper. Channel sinks consume text and terminal frames.
The service still owns session resolution, quota enforcement/accounting/release,
`execute_chat_stream`, citation cleanup, answer persistence and terminal error framing.

The flag-off mobile path retains existing document fields, prompt inputs, SSE bytes,
quota behavior, cancellation, file handling and timezone synchronization. Executable
parity tests compare a frozen pre-extraction handler to the current route. Existing
quota and stream-fallback tests exercise the extracted service. An absent `surface`
field means `app`; old records are not rewritten. The compatibility tests do not
claim provider determinism or a production canary.

`_run_shaped_chat_stream` **does ignore `system_prompt`**. It uses `chat_mount()` and
untrusted evidence. This is intentionally unchanged. Channels force that shaped path
without changing mobile's `OMI_SHAPED_AGENT_MODE` selection. The mount remains the
same Omi instructions and chat skills, plus stable adapter channel identity and
capability-derived format/length instructions. Channel names never enter
`_get_platform_context_section`. `Mount`, `Budget`, and `run_loop` remain the sole
agent loop, including the one-turn digest summarizer.

## Adapter and delivery contracts

`contracts.py` defines immutable `ChannelMessage`, `ChannelCapabilities`, `Artifact`,
`Principal`, `ReentryEvent`, and the `Adapter` / `ReplySink` protocols. Adapter parsing
maps provider link commands to `link_proof` and unlink commands to `unlink`; the core
never branches on a provider/channel name. Provider identity verification, escaping,
length-aware rendering, draft/edit transport, credentials and SDKs belong in Stage B.
Media must already be normalized to owned file-store references; adapters must verify
file ownership before publishing or delivering an artifact. No arbitrary filesystem
path or model-supplied remote URL is an artifact authority.

`register_adapter` installs at most sixteen configured adapters. The generic webhook
route verifies the signature before accepting any message. Unknown adapters return
404. A 1 MB body limit applies. The loopback adapter is never registered in production.

Every draft, final text and artifact passes `authorize_send` and the current link
revocation guard. `reply` and `deferred_reply` require the declared initiation,
free-reply-window and template conditions. `omi_initiated` is always denied. Capability
rate limits are declarations for the adapter; the asynchronous guard is the admission
hook for future rate/ratio policies. There is no proactive cross-channel delivery.
Unsupported artifact MIME types are rejected. Buffered sinks send only at completion;
draft/edit sinks receive cumulative rendered text followed by a committed final reply.
Stage B must maintain the provider draft/edit identity across calls and rate-limit it.

## Durable asynchronous mechanism

Admission encrypts a normalized message in a Firestore inbox using atomic `create`.
The dedup key includes channel, provider, external sender, external chat and provider
message id because provider ids may be chat-local. Only after that durable write does
the webhook return 202. A tracked `start_background_task` wakes workers; acknowledgement
never awaits model inference, tool execution or provider sending. This uses the existing
backend executor/task primitives without adding Cloud Tasks infrastructure or workflows.
An injected `wake(paths)` may instead publish content-free task pointers in Stage B.

`Gateway.drain()` recovers pending inbox rows after a missed wake or process restart.
Stage B must call it on startup and periodically for each registered adapter. A job
moves `pending -> running -> done`. Completed jobs retain content-free dedup tombstones.
A running job with ambiguous tool/delivery outcomes is **not automatically replayed**.
Surface leases use atomic create and a random ownership token. They cannot be stolen,
even after a timeout: operator recovery must first establish the previous worker is
stopped, reconcile effects, then reset the affected job/lease. This follows the existing
dream worker's safety model. A contender returns the job to pending without running it.
The key is `(uid, surface)`; independent surfaces/users can progress independently.
No in-process lock is relied on for multi-worker correctness.

Exactly-once external delivery is not claimed. A process can fail after a provider send
and before inbox completion. Stage B should use provider idempotency keys or reconcile
provider receipts before recovering ambiguous jobs. Re-entry uses a stable event id,
a task principal, and a `deferred_reply` sink. A completed reply event suppresses repeated
re-entry; recovery must reconcile a reply event whose external delivery was interrupted.

## Data model and privacy

| Collection | Fields and purpose |
| --- | --- |
| `channel_identities/{sha256(channel,provider,external_id)}` | Reverse index: uid, channel, provider, external_id, active, generation, linked_at, visible_in_app, voice_notes (default on), keep_private_memories_in_app (default on), insights (default off, not honored), display_handle. Unlinked admission creates a content-free provider marker. |
| `users/{uid}/channel_links/{identity_id}` | Mirror for listing, revocation, settings and deletion; visibility defaults false. |
| `channel_link_proofs/{sha256(proof)}` | uid, audience, kind, expires_at. Raw proof never persisted. |
| `users/{uid}/channel_link_proofs/{proof_id}` | Cleanup inventory for pending proofs. |
| `channel_identities/{identity_id}/inbox/{dedup_id}` | Encrypted normalized payload, created_at, pending/running/done. Done removes the payload. |
| `users/{uid}/chat_sessions/{surface_hash}` | Existing session fields plus surface, channel, channel_link_id, link_generation; reserved plugin_id `__channel__` keeps default app histories separate. |
| `users/{uid}/messages/{id}` | Existing chat fields plus surface, channel_link_id, data_usage=`user_serving_only`; channel text is encrypted using existing per-user encryption. |
| `users/{uid}/chat_sessions/{id}/channel_events/{sequence}` | Encrypted append-only model events: id, kind, at, role, content. Digests and re-entry evidence are hidden from message listing. |
| `users/{uid}/channel_turn_leases/{surface_hash}` | token and created_at; fail-closed serialization. |

Both proof types are authenticated-app minted, ten-minute, high-entropy, audience-bound
and single-use in a Firestore transaction. The token supports app-to-channel deep links;
the human-copyable code supports user-initiated channel-to-app proof. A phone number
alone is never proof. Linking cannot transfer another uid's existing identity. The
transaction reads everything before any write. App endpoints expose mint/list/unlink
and per-link settings; OpenAPI and generated Dart wire models include those schemas.
Mint returns `deep_link` and `address` from `OMI_MESSAGING_LINK_TARGETS` when that
channel entry is configured, and nulls otherwise. `GET /v2/chat-sessions` includes
optional `channel`, `channel_link_id` and `surface`. Channel retrieval drops memories
marked private and memories with a restricted sensitivity label while
`keep_private_memories_in_app` is on. Insights is stored and not yet applied.
Revocation/listing remain available if the feature is disabled or entitlement is lost.

Channel content is solely user-serving data. It must never enter model training,
evaluation datasets, or content-bearing analytics. This implements the brief's Telegram
§4.3 restriction as an application data-use contract; this change makes no new legal
interpretation or vendor-retention claim. Stage B must use approved inference-only
provider configurations and redact provider request/error logging. User-requested data
export remains allowed. No channel-specific dataset/feedback producer is introduced.

Unlink revokes the generation first, then removes associated messages, sessions, hidden
events, inbox payloads and both link records. Channel message/event writes transactionally
check the active link and existing session, so a stale worker cannot recreate a deleted
session. Account deletion calls `MessagingStore.delete_account` in
`services/users/account_deletion.py:background_wipe_user_data` before deleting credentials
and the user tree. It removes reverse indexes and pending proof records; recursive user
wipe removes mirrors, session events and leases. Deletion markers block further channel
admission. External provider retention/deletion is an adapter-specific Stage B obligation.
Unconsumed expired proofs and anonymous inbox tombstones need a bounded TTL janitor before
public rollout; this foundation does not deploy a Firestore TTL policy.

## Cross-surface continuity and cache behavior

App listing excludes channel sessions by default. Per-link `visible_in_app` opt-in
merges the selected channel sessions into the session list; no channel transcript is
silently mirrored into the default app conversation. Linking visibility does not grant
another account access. Existing app sessions logically have `surface=app`.

A returning surface appends hidden activity from other sessions since its last event.
Activity comes from the existing decrypted message iterator, paging until the surface
watermark (100 messages per page). Under 800 tokens it is verbatim; larger activity uses a cheap `chat_graph` model
through a one-turn shaped mount. The resulting digest is persisted once. It never edits
an earlier event. The stable mount prefix and all earlier serialized model messages
remain byte-identical across a surface switch. Enabled linked app turns use the same
append-only event log; the default mobile history-window contract is unchanged when off.
`search_chat_history` searches across history, returning the newest 20 matches.
These paginated scans are not a new full-text index; large accounts may need an index.

A surface event log has a 500 KB ceiling. Exhaustion fails closed and requires an explicit
new session; silently truncating/re-summarizing the cached prefix is forbidden. Long-lived
session epoch rollover and a full-history search index are extension points before wide
rollout. No historical messages are rewritten or migrated.

## Tool and workspace compatibility

The projection is `CORE ∪ SURFACE ∪ ENTITLED − UNRUNNABLE`, followed by the task principal's
allowed subset when one is present. Core is imported from `CORE_TOOLS`, not copied.
Installed-app tools occupy the existing entitled/connected lane. Adapters register surface
tools through `Adapter.tools(sink)`; future workspace tools can join the entitled input.
A name collision with a different implementation is an error, never silent replacement.
Channel turns have no live device callback and omit device tools. The enabled app surface
retains declared device tools. Existing tool-level JIT/privacy/entitlement gates still apply.

One immutable `ToolProjection.registry` supplies schemas and `_execute_tool` authority.
The harness test advertises a surface-only tool, scripts its provider call through the real
shaped runner and executes that same tool. `Principal` binds uid, optional tool subset,
expiry and task id, and is rechecked at every execution. Task principals require a subset
and expiry; they are internal server-created values, not accepted from request JSON.
A future workspace broker must authenticate/sign its transport token before constructing
one. This stage does not expose an unauthenticated task-token mint/execute API.

Artifacts are owned file-store references with MIME type, byte size and name. A background
workspace calls `Gateway.reenter(origin_message, ReentryEvent(...), principal=...)` and the
shared turn service produces a deferred reply under the originating surface lease. It
cannot use re-entry to bypass expiry, link revocation or channel reply windows.

## Rollout, evidence, and design differences

`OMI_MESSAGING_CHANNELS=off` by default, an empty exact uid allowlist, and the existing
`get_user_valid_subscription(..., provision=False)` authority fail closed. Admission uses
`is_paid_plan(subscription.plan)` for every paid catalog plan, rather than copying billing
or expiry logic. Basic/free and expired subscriptions are rejected by the existing
subscription authority. Production config enables only David's exact uid on Cloud Run
`backend`; other services and environments retain their default-off behavior.

The knowledge-base README's “no implementation authorized” and undecided defaults are
superseded by this brief. Its early calendar-off policy is also superseded: channels
receive all core tools. Its “mobile already on shaped” statement is a deployment claim;
source still has flag-controlled routing. This PR does not verify deployment state.
The shared history window and proactive/undo proposals in older notes are not expanded
here; real adapters, Flutter UI, media ingestion, provider credentials, deployments and
sandbox execution remain Stage B or later projects.

Tests live in `tests/unit/test_messaging_{channels,mobile_parity,firestore}.py`.
`testing/messaging/adapter_contract.py` is the reusable base suite; each real adapter
supplies `adapter` and `signed_message` fixtures plus provider-specific raw webhook
fixtures. `loopback.py` supplies the reference adapter and scripted provider. The
Firestore suite runs only with `MESSAGING_TEST_FIRESTORE_HOST=127.0.0.1:<port>` and uses
anonymous credentials and a random `demo-` project. It exercises real emulator
transactions, duplicate claims, lease ownership, proof replay races and deletion.

## Reproduce validation

```sh
BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/unit-files.txt" bash backend/test.sh > /tmp/messaging-unit.log 2>&1
rg 'passed|failed|ERROR' /tmp/messaging-unit.log
# Start a local Firestore emulator first; this host is explicitly loopback-only.
printf '%s\n' tests/unit/test_messaging_firestore.py > /tmp/messaging-emulator-files.txt
MESSAGING_TEST_FIRESTORE_HOST=127.0.0.1:18885 BACKEND_UNIT_TEST_FILE_LIST=/tmp/messaging-emulator-files.txt bash backend/test.sh > /tmp/messaging-emulator.log 2>&1
rg 'passed|failed|ERROR' /tmp/messaging-emulator.log
make preflight
```

Enabled app turns acquire their surface lease before quota or persistence. A concurrent
app request gets 409 before any write; channel contenders remain pending in the inbox.
An app stream cancelled after admission retains its lease for ambiguous-work recovery,
like channel workers. No such lease or new IO is added to flag-off mobile requests.
