# Shared chat edit receipts

Backend-managed app chat and channels use the same CORE_TOOLS edit catalog,
projected by `project_runtime_tools`. The legacy desktop proxy
(`backend/routers/desktop_chat.py` `_request` / `_anthropic_client_tools`)
forwards only tools the macOS client supplied and executes on device. It does
not use that projection. Putting the shared edit tools on the proxy request
would advertise calls the client cannot run. The remaining work is to route
desktop chat through `execute_chat_stream`, or to execute those tool calls
inside the proxy and teach the macOS client to render `editReceipt` and call
the undo endpoint. UI PR #21234 does not own that client. A write is allowed only after the
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

The app receipt store also supports legacy turns without a chat-session ID through
an owner-only receipt scope, without creating a visible session or enabling
channel continuity. Undo updates the persisted message block so history reloads
retain the undone state. Audit rows live at `users/{uid}/chat_edit_audit`, with uid,
tool, target, before/after SHA-256 hashes, surface and timestamp; summaries and
inverse payloads stay out of the audit.

Memory removal through chat is reversible removal from current knowledge, not
privacy erasure. It preserves content/history under the canonical MemoryService
and denies normal reads through the common access policy. Undo restores product
metadata through canonical apply. Memory corrections and their undo retain the
immutable ledger history and advance canonical revisions; they never restore old
ledger sequence/commit identifiers. Non-ledger content undo currently restores
content through the existing correction service and reapplies its reprocessing
semantics; promotion/tier metadata is not an exact rollback. `update_canonical_memory_content`
demotes the item to short-term and writes a new pending promotion. Restoring the
previous long-term tier is a short-term to long-term transition, which
`apply_long_term_patch_transaction` admits only for a current synthesis receipt.
The pre-edit receipt is bound to the old revision, and direct user patches cannot
write `tier` or the graph identity cleared by `clear_graph_assertion`. Exact
restore needs a canonical undo mutation that copies the before product snapshot
forward as a new revision without promotion re-admission and without rewinding
ledger sequence or commit ids. That is an INV-MEM-4 change, not a contained
patch. Ledger edits still use `revert_superseded_ledger_fact`. Removal undo
still restores `promotion_audit` because it does not change tier. Permanent
app/MCP privacy-purge deletion is unchanged. Clients must describe this
distinction when permanent erasure is asked for. New chat tools never call
the privacy-purge deletion method.

Conversation corrections are owner-confirmed durable notes, compressed (and
protected for enhanced users) alongside the conversation. Regeneration preserves
those notes and explicit title/overview overrides and includes the corrections
as evidence for subsequent summaries. No transcript segment is changed.

App edit outcomes use the receipt summaries as their canonical message text.
Mobile recognizes the same fallback body and renders each native receipt once;
older clients still receive readable text. Channel prose and existing create-only
blocks keep their existing behavior. Person receipts have Undo, but no item URL
or open-item button because there is no person deep-link route.

Combined mobile acceptance was run with UI PR #21234 at
`9d6fd1f4db3c218c0227d12ee653b8cd838a3a6c` in an isolated integration worktree.
The branches merge cleanly after separating their changelog filenames. Both
light/dark receipt render tests, real backend fixture decoding and Undo state
updates passed alongside the receipt interaction/state suite (46 tests); the hermetic app runner also passed 138 spine tests.
Backend receipt/edit/rendering/app-parity tests passed on the combined tree.
Before/after-Undo PNGs were inspected in both themes. Fixtures live at
`app/test/fixtures/backend_edit_receipts.json` and are pinned against the real
serializer in `testing.messaging.receipt_payloads`. Merge UI #21234 first so
native receipt rendering and Undo exist before this backend emits edit blocks.
