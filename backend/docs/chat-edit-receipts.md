# Shared chat edit receipts

Every chat agent uses the same edit tools. A write is allowed only after the
user asks for it or confirms an agent-proposed correction. Whole-conversation
deletion is excluded and transcripts are never rewritten by these tools.

The backend authors `editReceipt` content blocks in `Message.content_blocks`:

```json
{"type":"editReceipt","id":"<block id>","receiptId":"<uuid hex>","targetKind":"conversation|memory|task|person","action":"created|updated|deleted|completed|uncompleted|renamed","targetId":"<id>","summary":"<short human text>","undoable":true,"undoneAt":null}
```

Existing `memoryLink` and `taskCard` create blocks stay available. Edits and
deletes use `editReceipt`. Clients must tolerate unknown content-block types.

`POST /v1/chat/receipts/{receipt_id}/undo` uses the authenticated uid. No uid,
session, target or inverse is accepted from the client. The receipt lookup is
under `users/{uid}/chat_receipts`; another owner's receipt returns 404. The
response is `{ "status": "undone|already_undone|unavailable", "block": <editReceipt> }`.
A second successful call returns `already_undone`, retaining `undoneAt`.
The five-minute receipt window and once-only claim semantics are shared with
channel undo. Ambiguous inverses require reconciliation and are never replayed.

UI integration: render the block's summary and Undo control, replace its state
with the returned block after undo. Item links use `https://h.omi.me/conversation/<id>`,
`https://h.omi.me/task/<id>` and `https://h.omi.me/memory/<id>`. Paths contain only
opaque IDs. The UI lane owns authenticated web fallbacks and mobile routing.
