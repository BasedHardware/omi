# Chat, Listen, and Settings wire proposal

Status: proposal only; no route, contract, or authority decision is made here.

Evidence baseline: read-only `core-foundation` commit
`df9155acfc2629b1292882756757c99d502bb190`. The production entry point says all
three surfaces are fixture-only because no ratified backend serves them
(`core/packages/surfaces/src/production/main.tsx:236-259`). Consequently, the
types below are surface-facing composition ports, not an already-ratified HTTP
or WebSocket wire. Method names are not proposed route names.

## Chat

### Shape the client already assumes

The surface consumes `ProductionChatStore`
(`core/packages/surfaces/src/production/ProductionChatStore.ts:18-38`):

- Common lifecycle: synchronous `status()`, change subscription, and async
  `refresh()`.
- `history()` and `loadOlder(opaqueCursor)` each return `{ messages, hasOlder,
  olderCursor }`. The cursor is server-issued, opaque, and nullable
  (`chat-reconcile.ts:21-26`).
- A message is `{ role: "user" | "assistant", text, delivery, streaming? }`.
  Delivery is a closed union: canonical messages have a server id and optional
  client-message id; local echoes have a client-message id; terminal failures
  add `retryable` (`chat-reconcile.ts:6-19`).
- `send()` accepts trimmed text, a client-generated message id, and an array of
  attachment strings. `retry()` addresses the failed send by client-message id.
  `capabilities()` supplies `maxAttachmentsPerMessage`; `null` means attachments
  must remain unavailable (`ProductionChatStore.ts:30-38`,
  `chat-reconcile.ts:28-31`).
- The client preserves server order. A canonical row with the same
  client-message id replaces its echo/failure; unacknowledged local rows remain
  after the canonical tail. Older pages prepend without duplicates
  (`chat-reconcile.ts:49-91`).

The fixtures exercise empty, normal, streaming, pending echo, retryable send
failure, older-page, unknown attachment-cap, and unavailable states
(`chat-fixtures.ts:13-22`).

There is also a separate domain/platform client adapter. It currently labels
`/v1/chat/messages` and `/v1/chat/messages/reconcile` **provisional** and says no
platform service serves them (`core/packages/adapters-platform/src/chat.ts:12-24,
39-47`). Its domain row is materially richer than the surface row: identity,
human/AI sender, type, timestamps, session/app scope, journal revision, payload
hash, source, rating/reporting, and server revision
(`core/contracts/src/domain/chat.ts:60-115`). This adapter is evidence about
requirements, not a route family this proposal ratifies.

### What a server-backed adapter would be owed

- A newest-page and older-page read that preserves canonical server order,
  returns an opaque backward cursor, declares whether an older page exists, and
  is duplicate-free across page boundaries.
- Send idempotency keyed by the client-message id, with the canonical record
  echoing that id so the UI can replace its optimistic row without remounting.
- An explicit terminal outcome for every send: canonical success or a failure
  classified as retryable/permanent. A retry must preserve the original
  client-message identity and must not create a duplicate.
- A generation update mechanism capable of representing an in-progress
  assistant row and a complete canonical terminal row. Reconnect must heal from
  canonical history rather than leaving a permanent partial row.
- A capabilities payload that reports an attachment cap before attachment
  selection is enabled.
- Enough status/error information for the adapter to truthfully expose the
  shared refresh and queue states. `subscribe()` itself is local observer
  plumbing, not a server endpoint.
- If the richer domain adapter is selected, its existing identity conflict,
  journal revision, payload hash, and canonical-record requirements must be
  reconciled with the smaller surface row rather than discarded.

### COULD NOT DETERMINE from the client alone

- Exact paths, verbs, status codes, response envelopes, authentication, or
  whether history and generation share one transport.
- Conversation/session selection: `ProductionChatStore` has no conversation id,
  while the domain row has nullable session and app scope.
- Whether the surface's `olderCursor` maps to the provisional adapter's
  `next_cursor`, and the precise snapshot/completeness contract.
- The attachment strings' identity and lifecycle: local path, uploaded object
  id, URL, MIME metadata, upload ordering, size limits, and cleanup are absent.
- Streaming frame grammar, delta versus replacement semantics, cancellation,
  reconnect token, and terminal error body.
- Whether `retry()` replays a retained request client-side or invokes a
  server-side retry operation.

## Listen

### Shape the client already assumes

The surface consumes `ProductionListenStore`
(`core/packages/surfaces/src/production/ProductionListenStore.ts:6-23`): common
lifecycle methods plus synchronous `captureState()` and async `start()` / `stop()`.
There is deliberately no user pause operation.

`CaptureState` is a closed union (`capture-state.ts:6-21`):

- `idle`
- `capturing { elapsedSeconds }`
- `paused-for-entitlement { elapsedSeconds, untranscribedSeconds }`
- `offline-buffering { elapsedSeconds, bufferedSeconds,
  untranscribedSeconds }`
- `stopped-at-ceiling { untranscribedSeconds }`
- `error { retryable }`

The fixtures cover every union arm, both retryable and permanent errors, and an
unavailable refresh (`listen-fixtures.ts:9-18`). Start is accepted only from idle
or retryable error; stop is accepted only while capturing, entitlement-paused,
or offline-buffering (`listen-fixtures.ts:91-110`).

Separately, core already has a generated Listen WebSocket contract and a
client-side stream port. The schema names native `/v4/listen` and web
`/v4/web/listen` paths (`core/contracts/wire/listen/listen-protocol.schema.json:17-78`).
The stream port exposes ordered transcript segments, connection state,
normalized entitlement state, close advice, and degradation evidence
(`core/packages/wire-listen/src/listen_capture_stream.ts:224-289`). That port
accepts server text frames and close codes; binary audio never enters its text
decoder. It is not currently adapted into `ProductionListenStore`, whose UI
does not render transcript segments.

### What a server-backed adapter would be owed

- A coherent source of every `CaptureState` value and its counters, with
  transitions observable after start, stop, connectivity changes, entitlement
  changes, storage ceiling, and failure.
- Start/stop outcomes that are safe to retry or explicitly reject, so the
  adapter never claims capture is idle while audio is still being accepted (or
  capturing after it has stopped).
- If the existing Listen WebSocket is the transport, conformance to its
  handshake, binary-audio, text-event, close-code, entitlement, ordering,
  reconnect, and degradation rules. A new parallel HTTP state machine is not
  implied by this surface port.
- Truthful backlog and elapsed counters. Entitlement pause must preserve the
  distinction between “transcription paused, capture continuing” and a stopped
  socket; a storage-ceiling stop must not degrade to idle.
- Enough lifecycle/error information for the adapter to expose refresh and
  queue status. Observer subscription remains local plumbing.

### COULD NOT DETERMINE from the client alone

- Whether `start()` / `stop()` are shell/device operations, WebSocket lifecycle,
  service commands, or a composition across all three; therefore no REST route
  is proposed.
- Which component owns microphone permission, audio framing/codec, buffering,
  persistence, retransmission, and storage-ceiling enforcement.
- The exact mapping from low-level transcript/connection/entitlement events to
  each `CaptureState` arm and counter, including counter clock authority.
- Whether apps/service hosts the existing WebSocket, proxies it, or only
  supplies account/entitlement data to a shell-owned capture connection.
- Authentication and resume tokens, multi-device arbitration, start/stop
  idempotency keys, and error response bodies.
- Whether transcript segments will become visible on this surface; the current
  UI contract contains no transcript collection.

## Settings

### Shape the client already assumes

The surface consumes `ProductionSettingsStore`
(`core/packages/surfaces/src/production/ProductionSettingsStore.ts:19-34`):

- `snapshot()` returns identity, appearance, and optional entitlement.
- `patch()` is a keyed partial update; currently the only writable key is
  `appearance`.
- `signOut()` is an explicit operation.
- Common status, subscription, and refresh methods plus dead-letter list and
  discard operations.

The snapshot types are (`settings-merge.ts:1-29`):

```ts
type AppearanceSelection = "default" | "system" | "light" | "dark";
type AccountIdentity = { displayName: string; email: string } | null;
type EntitlementState = {
  planLabel: string;
  limitKey: string;
  used: number;
  limit: number | null; // null means unmetered
  limitReached: boolean;
  upgradeAvailable: boolean;
};
type SettingsSnapshot = {
  identity: AccountIdentity;
  appearance: AppearanceSelection;
  entitlement: EntitlementState | null;
};
type SettingsPatch = { appearance?: AppearanceSelection };
```

An absent patch key means unchanged; explicit `undefined` is ignored
(`settings-merge.ts:26-44`). Fixtures cover signed in/out, reached limit,
unmetered, unavailable upgrade, unavailable refresh, and failed save
(`settings-fixtures.ts:15-23`). The client renders server-structured entitlement
data and does not derive plan logic (`settings-merge.ts:9-18`).

### What a server-backed adapter would be owed

- One coherent snapshot with the exact nullability and closed appearance values
  above. Identity absence must remain distinct from empty display fields;
  entitlement absence must remain distinct from an unmetered entitlement.
- Keyed appearance mutation where an omitted field is unchanged; no accidental
  full replacement. A successful response must allow the subsequent snapshot
  to converge to the selected value.
- A sign-out outcome that lets the adapter converge identity and entitlement to
  null and accurately report any failure.
- Authoritative, internally consistent entitlement fields. The client must not
  have to infer `limitReached` or upgrade availability from plan labels.
- Durable write outcomes sufficient for queue status and dead-letter
  visibility/discard if the selected implementation uses the shared outbox.
  Subscriptions and dead-letter storage are adapter concerns, not automatically
  server endpoints.

### COULD NOT DETERMINE from the client alone

- Whether appearance is account-scoped server state, shell-local state, or a
  merged preference; consequently this proposal does not assign its authority
  to apps/service.
- Exact paths, verbs, envelopes, authentication/session invalidation, cookie or
  token cleanup, status codes, and error bodies.
- Snapshot versioning, concurrent patch behavior, idempotency, and whether a
  patch returns a row, an outcome, or no body.
- The upstream sources and refresh cadence for identity and entitlement, or how
  inconsistent upstream reads are made atomic.
- Upgrade destination/routing. The surface receives `limitKey` through an
  `onUpgrade` callback; no URL or server action is assumed.
- Whether settings dead letters share a server-visible operation id or are
  wholly local outbox records.

## Ratification questions

Before implementation, a ratifier must choose, per surface:

1. Authority and composition boundary: what belongs to apps/service versus a
   shell/device adapter or another service.
2. Transport family and exact versioned paths; for Chat, whether to ratify,
   replace, or remove the explicitly provisional adapter paths; for Listen,
   whether the existing WebSocket is the only server wire.
3. Request, success, and failure envelopes including idempotency, authentication,
   cursor, reconnect, and concurrency rules.
4. The mapping from transport/domain records into the smaller surface-facing
   stores, including attachment identity, Chat streaming, Listen state, and
   Settings preference scope.

No implementation should begin until those choices are ratified.
