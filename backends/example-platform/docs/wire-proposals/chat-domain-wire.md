# Chat domain wire proposal

Status: **proposal for ratification; not a contract and not an implementation**.

This document designs a fresh Chat wire from
`core/contracts/src/domain/chat.ts:60-115`. It does not adopt, alias, or reserve
the provisional `/v1/chat/messages` and `/v1/chat/messages/reconcile` paths in
`adapters-platform/src/chat.ts`.

Evidence coordinates:

- platform: `d9b91c0f9ab25ad91e45d0b7b8482042f7943534`
- read-only core-foundation: `8e2e1c52b24fb1a80334c700dfb006db827a32a5`
- domain record: `core/contracts/src/domain/chat.ts:60-115`
- create operation and terminal frame: `core/contracts/src/domain/chat.ts:129-176`
- surface row/reconciliation: `core/packages/surfaces/src/production/chat-reconcile.ts:6-105`
- surface port: `core/packages/surfaces/src/production/ProductionChatStore.ts:18-38`

The inherited field names carry the pending markers already attached to the
domain contract: `sender` is `domain-pending(DIV-CHAT-SENDER-001)`, `type` is
`domain-pending(DIV-CHAT-TYPE-001)`, `chatSessionId` is
`domain-pending(DIV-CHAT-SESSION-001)`, `journalRevision` is
`domain-pending(DIV-CHAT-REV-001)`, `payloadHash` is
`domain-pending(DIV-CHAT-HASH-001)`, and `messageSource` is
`domain-pending(DIV-CHAT-SOURCE-001)`. The proposal uses those legacy names so a
later ratification can rename them mechanically.

## Ratified inputs this proposal does not reopen

- The backend is the canonical Chat record; local state is a durable mirror.
- `ChatMessage` is the source record. The smaller production surface row is an
  adapter projection, not a competing persistence contract.
- A client-supplied message id is the durable record id. Journal revision plus a
  payload hash makes replay idempotent and detects identity reuse.
- The terminal successful stream frame carries the complete canonical message,
  never the last delta.
- History pagination is concurrent-insert-safe, keyset based, and duplicate-free.
- The server owns quota enforcement, attachment count, size, and MIME policy.
- This proposal does not use the existing provisional paths as a shortcut.

## Shape the client already assumes

The surface needs:

- newest history and an older-page read;
- oldest-to-newest canonical server order within the returned collection;
- an opaque backward cursor and `hasOlder`;
- canonical rows that can replace an optimistic row by client message id;
- a terminal failed row with `retryable: boolean`;
- an in-progress assistant row followed by a complete canonical row;
- send and retry keyed by the original client message id; and
- `maxAttachmentsPerMessage`, with `null` keeping attachment selection disabled.

The surface row is intentionally smaller than the domain record:

| Domain record | Surface projection |
| --- | --- |
| `id` | `delivery.serverId`; for a human-authored send it also supplies `delivery.clientMessageId`. |
| `sender: "human"` | `role: "user"` |
| `sender: "ai"` | `role: "assistant"` |
| `text` | `text` |
| complete streamed AI record | canonical row with `streaming` absent/false |
| advisory generation snapshot/delta | local assistant row with `streaming: true` |
| timestamps, scope, revisions, hash, source, rating, reporting | retained in the domain mirror; not rendered by this surface row |

`sender: "unknown"` cannot be honestly mapped to the surface's closed
`"user" | "assistant"` role. The adapter must retain the domain record, omit it
from this particular surface projection, and report degraded refresh evidence;
it must not coerce unknown to user or assistant. Extending the surface role is a
separate contract event.

## What apps/service would owe

- Authenticated, scope-bound history reads whose pages do not overlap or skip
  under concurrent insertion.
- A send admission that is idempotent by the client-supplied message id and
  never starts a second generation on replay.
- A canonical human record echoing that id, or an explicit failure with a
  retryable/permanent disposition.
- One streaming supervisor with a reconnectable frame log and a complete
  canonical terminal success.
- Server-side cancellation rather than “disconnect means cancel.”
- A capabilities payload that carries the enforced attachment cap and policy.
- No hidden truncation of attachment ids or model context.

## Recommended route family

The proposed resource name follows the source record directly:

| Route | Verb | Success | Purpose |
| --- | --- | --- | --- |
| `/v1/chat-messages` | `GET` | `200` JSON | Newest or older canonical page plus capabilities. |
| `/v1/chat-messages` | `POST` | `201` or `200` SSE | Admit one human message and stream its generation. |
| `/v1/chat-generations/{generationId}/events` | `GET` | `200` SSE | Reconnect to an admitted generation. |
| `/v1/chat-generations/{generationId}` | `DELETE` | `202` or `204` JSON/empty | Request cancellation; idempotent by generation id. |
| `/v1/chat-attachments` | `POST` | `201` JSON | Stage an upload and receive an opaque attachment id. |

All routes require `Authorization: Bearer <credential>` and return
`Cache-Control: no-store`. The service reads `x-omi-contract-version` under the
existing app-facing convention. No request accepts an account id.

`/v1/chat-messages` is intentionally different from provisional
`/v1/chat/messages`. No alias is proposed: no consumer has integrated against a
platform implementation, and an alias would turn a provisional spelling into a
permanent compatibility obligation.

Except where a successful SSE response has already begun, Chat failures use the
same fixed envelope as send failures:

```json
{
  "error": {
    "code": "unauthorized",
    "retryable": false,
    "action": "reauthenticate"
  }
}
```

Common statuses are `400 bad_request`, `401 unauthorized`, `403 forbidden`,
`404 not_found`, `410 cursor_expired` or `generation_replay_expired`,
`429 rate_limited`, and `503 service_unavailable`. `429` and `503` are
retryable and carry a fixed `Retry-After`; the others are not blind-retryable
and carry the recovery action named in their route section. Ownership mismatch
collapses to `404 not_found`. No body contains an account id, scope, stored
record, provider error, or internal denial reason.

## History read

### Request

```text
GET /v1/chat-messages?limit=50
GET /v1/chat-messages?limit=50&olderCursor=<opaque>
```

`limit` is a decimal integer from 1 through 100. `olderCursor` is absent for the
newest page and is the exact opaque value returned by the prior page for an
older page. Repeated or unknown parameters are `400 bad_request`.

The current surface has no selector, so absence of both `appId` and
`chatSessionId` selects the main Chat scope (`null`/`null`). If non-main scopes
are exposed later, they should be explicit single-valued query parameters and
must be cryptographically bound into the cursor. They are not added by this
proposal merely because the domain record can represent them.

### Success envelope

```json
{
  "messages": [
    {
      "id": "client-message-01",
      "text": "What did I decide yesterday?",
      "sender": "human",
      "type": "text",
      "createdAt": 1786352400000,
      "updatedAt": 1786352400000,
      "chatSessionId": null,
      "appId": null,
      "journalRevision": 1,
      "payloadHash": "sha256:example",
      "messageSource": "desktop_chat",
      "rating": null,
      "reported": false,
      "revision": "server-revision-01"
    }
  ],
  "page": {
    "olderCursor": "opaque-or-null",
    "hasOlder": true
  },
  "capabilities": {
    "maxAttachmentsPerMessage": 9,
    "maxAttachmentBytes": 52428800,
    "allowedAttachmentMimeTypes": ["image/png", "image/jpeg", "application/pdf"]
  }
}
```

The concrete numbers and MIME list above are illustrative, not proposed values.
The ratified schema supplies them. The surface adapter reads only
`maxAttachmentsPerMessage`; the other fields prevent a client from discovering
server policy only after upload.

`createdAt` and `updatedAt` are proposed as non-negative integer Unix epoch
milliseconds. The source contract requires numbers but does not state their
unit, so this encoding remains an explicit ratification choice below.

### Ordering and cursor obligations

- `messages` is in canonical ascending order: oldest to newest within every
  page. The client never sorts.
- A newest-page request returns the newest `limit` records, then orders those
  records ascending for display.
- `olderCursor` points strictly before the oldest record returned. It is `null`
  exactly when `hasOlder` is false.
- The cursor binds account, main/app/session scope, page direction, snapshot
  ceiling, and a deterministic `(createdAt, id)` keyset boundary. It is signed,
  opaque, and never constructed or parsed by the client.
- Concurrent inserts newer than the snapshot ceiling cannot shift an older-page
  boundary. A message id appears at most once while walking one cursor chain.
- Replaying the same cursor returns the same ordered page while that cursor is
  valid. An invalid cursor is `400`; an expired cursor is `410` with
  `action: "refresh_history"`.
- Deletion or hiding may shorten a page but may not cause the server to pull a
  record from the other side of the cursor boundary and duplicate it.

The history response is the reconnect source of truth. Streaming state never
licenses a different canonical order.

## Send and idempotency

### Request body

The JSON body follows the create arm of `ChatMessageOp`; the attachment ids are
the one acknowledged domain-contract gap:

```json
{
  "op": "create",
  "opId": "outbox-op-01",
  "id": "client-message-01",
  "at": 1786352400000,
  "text": "What did I decide yesterday?",
  "sender": "human",
  "journalRevision": 1,
  "type": "text",
  "appId": null,
  "chatSessionId": null,
  "messageSource": "desktop_chat",
  "metadata": null,
  "attachmentIds": ["attachment-opaque-01"]
}
```

- `id` is the client message id and durable Chat record id. It is the primary
  idempotency key for this logical send.
- `opId` identifies one outbox operation; it does not permit a second record or
  generation for the same `id`.
- This endpoint accepts only `sender: "human"`; `"ai"` is server-authored and
  `"unknown"` is read tolerance only.
- The server canonicalizes the authored immutable fields, derives
  `payloadHash`, and returns the hash in the canonical record. A client-supplied
  digest is not trusted as the content check.
- Attachment count, membership, ownership, size, and MIME are validated before
  the user message is admitted. Nothing is silently truncated.

### Admission and replay

- First application returns `201` and starts exactly one generation.
- Exact replay returns `200`, the same canonical human record, and the same
  generation id. It resumes or replays that generation; it never starts another.
- Same `id` with a different canonical payload hash returns `409` permanent
  `client_message_id_conflict`.
- A lower journal revision cannot overwrite a higher one. A higher revision
  with the same immutable payload may advance journal metadata but still refers
  to the same record and generation.
- Quota usage and generation billing are keyed so replay of the same `id` is not
  counted twice.

The first SSE event is the terminal outcome of **send admission**:

```text
event: accepted
id: <opaque-event-cursor>
data: {"kind":"accepted","message":{...complete canonical human ChatMessage...},"generation":{"id":"generation-opaque-01"}}
```

The canonical `message.id` echoes the request `id`; the surface adapter uses it
as both `serverId` and `clientMessageId` for the human row. Generation frames
that follow belong to the assistant turn, not to send admission.

### Send failures

Failures before SSE begins use one fixed envelope:

```json
{
  "error": {
    "code": "attachment_rejected",
    "retryable": false,
    "action": "edit_request"
  }
}
```

The body never includes provider messages, account state, quota numbers, or
stored payloads.

| Status | `code` | `retryable` | Required behavior |
| --- | --- | --- | --- |
| `400` | `bad_request` | `false` | Permanent malformed envelope. |
| `401` | `unauthorized` | `false` | Pause the outbox; `action: "reauthenticate"`, not a user retry button. |
| `403` | `forbidden` | `false` | Permanent for this authorization context. |
| `402` | `entitlement` | `false` | Permanent send outcome; server remains quota authority. |
| `409` | `client_message_id_conflict` | `false` | Permanent identity/payload conflict. |
| `413` | `attachment_too_large` | `false` | Permanent until the request changes. |
| `422` | `validation` or `attachment_rejected` | `false` | Permanent; includes count/MIME rejection, never truncation. |
| `429` | `rate_limited` | `true` | Retry no earlier than `Retry-After`. |
| `503` | `service_unavailable` | `true` | Preserve the exact op and retry with backoff. |

The surface's failed row is created only for a terminal send failure. Auth loss
is carried by store status while the outbox remains paused. The adapter retains
the full authored operation—including attachment ids—keyed by `id`; a retryable
row containing only display text is insufficient replay state.

## Streaming and generation

### Transport recommendation

The initiating `POST` returns `text/event-stream` after admission. This preserves
the existing “stream over the initiating connection” behavior. Because a POST
stream cannot rely on browser `EventSource` auto-reconnect, the accepted event
also supplies a generation id for the authenticated reconnect `GET`.

The server maintains one ordered event log per generation. Every event has an
opaque SSE `id`. Heartbeats are SSE comments and never enter the frame grammar.

### Recommended frame grammar

```ts
type ChatGenerationFrame =
  | { kind: "accepted"; message: ChatMessage; generation: { id: string } }
  | { kind: "snapshot"; text: string }
  | { kind: "delta"; text: string }
  | { kind: "done"; message: ChatMessage }
  | { kind: "failed"; error: { code: string; retryable: boolean } }
  | { kind: "cancelled"; message: ChatMessage | null };
```

- `snapshot` is a replacement of the advisory assistant text accumulated so
  far. It is the first generation frame on every reconnect.
- `delta` appends advisory text after the latest snapshot. Duplicate event ids
  are ignored. Deltas are never persisted or treated as a canonical record.
- `done` is the successful terminal frame already fixed by
  `ChatTerminalFrame`: `message` is the complete canonical AI record.
- A model/tool failure normally persists the ratified degraded fallback and
  terminates with `done`. `failed` exists for the case where no canonical reply
  can be persisted; it is terminal and explicitly retryable/permanent.
- `cancelled` is terminal for cancellation. If partial assistant text was
  intentionally retained, `message` is its complete canonical record; otherwise
  it is `null`. This retention choice is open below and cannot be inferred from
  the current `ChatMessage` type.
- Exactly one of `done`, `failed`, or `cancelled` terminates a generation.

### Reconnect

```text
GET /v1/chat-generations/generation-opaque-01/events
Last-Event-ID: <opaque-event-cursor>
```

- The credential must resolve to the same account and scope as the send.
- The server replays events strictly after `Last-Event-ID`. With no cursor it
  sends a current `snapshot` and then live events.
- If already complete, reconnect returns `done` and closes.
- If the replay cursor expired but canonical completion exists, the server sends
  `done` from history and closes.
- If neither replay nor canonical completion can heal the stream, return `410`
  JSON with `generation_replay_expired`, `retryable: false`, and
  `action: "refresh_history"`. The adapter removes the speculative streaming
  row and reconciles canonical history; it never leaves a permanent partial row.
- A network disconnect does not cancel generation.

### Cancellation

```text
DELETE /v1/chat-generations/generation-opaque-01
```

- `202` with `{"cancellation":{"state":"accepted"}}` means cancellation was
  durably requested but the supervisor has not reached a terminal frame.
- `204` means that same cancellation was already applied or the generation was
  already terminal. Repeating DELETE is safe.
- `404 {"error":{"code":"not_found","retryable":false}}` hides both absence
  and ownership mismatch.
- The supervisor, not the socket, stops model/tool work. It then emits exactly
  one terminal `cancelled` frame (or `done` if completion won the race).

Whether cancellation retains partial AI text is a data-lifecycle choice. This
proposal recommends retaining a non-empty partial as a complete canonical
message and returning `null` when no assistant content exists, but that choice
requires David's explicit data-disposition ratification before implementation.

## Capabilities and attachments

The newest and older history envelopes both carry the effective capabilities
used by send validation:

```ts
type ChatCapabilitiesWire = {
  maxAttachmentsPerMessage: number;
  maxAttachmentBytes: number;
  allowedAttachmentMimeTypes: string[];
};
```

The values are server-owned and scope/entitlement aware. The adapter exposes
`maxAttachmentsPerMessage`; until a valid payload arrives it exposes `null`, so
selection stays disabled. The server still validates every send even when the
client has a fresh capability snapshot.

### Attachment identity recommendation

Use opaque server-issued upload ids, not local paths, caller-provided URLs, or
inline data in the message send:

```text
POST /v1/chat-attachments
Content-Type: multipart/form-data

201
{
  "attachment": {
    "id": "attachment-opaque-01",
    "mimeType": "application/pdf",
    "sizeBytes": 12345,
    "state": "staged",
    "expiresAt": "2026-08-10T08:00:00.000Z"
  }
}
```

The upload route authenticates ownership, sniffs and validates MIME rather than
trusting a filename, enforces size, and returns an id that can be bound once to
an admitted human message. Send verifies that every id is staged, owned by the
same account, in the same scope, and not already bound incompatibly.

After admission, attachment records follow the owning Chat message's retention
and deletion policy; this proposal does not invent that policy. Unbound staged
upload expiry and cleanup are destructive data-disposition choices. A bounded
expiry is the recommended operational model, but its duration, user warning,
and recovery behavior require David's explicit ratification. No delete route is
proposed until that disposition is signed.

## `retry()` recommendation

`ProductionChatStore.retry(clientMessageId)` should be **client replay**, not a
server `/retry` operation:

1. The adapter loads the retained exact create operation by client message id.
2. It replays `POST /v1/chat-messages` with the same `id`, `opId`, immutable
   payload, attachment ids, and journal revision.
3. The server either returns the existing admission/generation or admits the
   previously unrecorded send. It cannot create a duplicate.

A server retry endpoint would need a retained failed request, a new generation
identity rule, quota/billing semantics, and authorization to rerun old content.
It adds a second idempotency system without helping failures that occurred
before the server recorded anything. A new logical user send gets a new client
message id; it is not `retry()`.

## Open choices for ratification

### 1. Route family

- **A — `/v1/chat-messages` plus `/v1/chat-generations`.**
- B — the provisional `/v1/chat/messages*` family.
- C — retrofit legacy `/v2/messages` in the new service.

**Recommendation: A.** It follows the `ChatMessage` source record without
adopting a deliberately provisional path or inheriting legacy `/v2/messages`
stream semantics. Choosing B would be a SPEC DIVERGENCE from the instruction to
design fresh and is not proposed here.

### 2. Send/stream transport

- **A — POST SSE for the initiating connection plus authenticated GET replay.**
- B — POST JSON followed by GET-only SSE.
- C — one WebSocket carrying send, stream, reconnect, and cancellation.

**Recommendation: A.** It preserves immediate streaming while giving reconnect
an explicit resource. B is simpler but adds a round trip; C adds full-duplex
state where only server-to-client streaming is required.

### 3. Advisory frames

- **A — replacement snapshot on connect, append-only deltas afterward, complete
  canonical `done`.**
- B — replacement frames only, then `done`.
- C — deltas only, then `done`.

**Recommendation: A.** A reconnect can render immediately without replaying an
unbounded delta log, while live traffic remains compact. C cannot heal if the
client misses a delta; B is correct but unnecessarily expensive.

### 4. Attachment identity

- **A — opaque staged upload ids bound by send.**
- B — caller-provided remote URLs.
- C — local paths interpreted by a privileged shell bridge.
- D — inline base64/multipart content in every send replay.

**Recommendation: A.** It gives every surface one identity, lets the server
enforce ownership/MIME/size before generation, and keeps retries small. Its
unbound-upload disposal still needs owner ratification.

### 5. Retry ownership

- **A — client replays the retained idempotent create operation.**
- B — `POST /v1/chat-messages/{id}/retry` asks the server to reconstruct it.
- C — retry always creates a new client message id.

**Recommendation: A.** It uses the universal idempotency contract and works
whether or not the failed request reached the server. C duplicates a logical
message; B invents a second operation model.

### 6. Cancellation retention

- **A — retain non-empty partial AI text as a complete canonical record; retain
  nothing when no content exists.**
- B — always discard partial AI text.
- C — always persist a synthetic cancellation message.

**Recommendation: A, pending David.** It avoids losing visible generated content
and avoids manufacturing copy when nothing was produced. This is explicitly a
data-disposition decision and cannot be bound by a stand-in ratifier.

### 7. Capabilities delivery

- **A — include effective capabilities in every history page.**
- B — add a separate capabilities route.
- C — hardcode the cap in each client.

**Recommendation: A.** It keeps the cap in the authenticated, scope-aware read
the adapter already needs and avoids a second freshness race. C violates the
server-authority invariant.

### 8. Timestamp encoding

- **A — non-negative integer Unix epoch milliseconds.**
- B — non-negative integer Unix epoch seconds.
- C — change the wire to RFC 3339 strings while the domain record remains a
  number.

**Recommendation: A.** It preserves the numeric domain shape, matches the
JavaScript client clock without lossy conversion, and keeps sub-second ordering
available. The schema must bind the unit; a bare `number` is not a wire contract.

## COULD NOT DETERMINE

- The ratified numeric attachment count/size caps and MIME allowlist.
- The complete attachment record, encryption, scanning, download, retention,
  unbound-expiry, and deletion lifecycle. `ChatMessage` explicitly identifies
  attachments as a foundation gap.
- Whether a cancelled generation's partial AI output is user data to retain.
  The recommendation above is not authority to implement a disposition.
- The retention window for generation event replay and opaque event cursors.
- The timestamp unit; the recommendation above is not stated by the current
  domain type.
- Whether non-main `appId`/`chatSessionId` scopes belong on this first surface
  route or a later route family.
- The client presentation for `sender: "unknown"`; the current smaller surface
  row cannot represent it without false attribution.
- Whether generation failure needs more machine-readable outcomes than
  retryable/permanent. The domain record has no generation outcome field.
- The exact contract version, product cancellation copy, and fixed Retry-After
  values.

These are explicit ratification items. None may be silently filled in during
route implementation.
