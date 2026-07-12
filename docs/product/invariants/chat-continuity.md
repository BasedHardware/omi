# INV-CHAT-1: One shared transcript across surfaces

**Status:** locked
**Statement:** Every canonical conversation has one kernel-owned transcript.
Typed chat, notch / floating bar, PTT/realtime, and floating pills are input/output
devices against the shared main conversation; they never fork it. A workstream is
an explicit product conversation boundary: every task view linked to that
workstream resolves the same kernel conversation and artifact history.

## MUST NOT

- Introduce a second persistent or semi-persistent store of agent/session/transcript
  state outside `omi-agentd.sqlite3` (including “as a cache,” “for offline,” or
  “temporarily during migration”).
- Build per-surface continuity rings, early-bubble reconciliation, or
  sync-by-mirroring between notch and main chat.
- Treat backend message rows as authoritative for agent context or continuity.
  Backend chat is the journal's downstream mirror plus an event-triggered import
  feed for genuinely remote client turns; imported rows become canonical only
  after the kernel accepts their stable remote/canonical identity.
- Let Swift own session identity, model context assembly, or run truth.

A bounded, decode-only upgrade reader may consume a store written by an older
release. It must never accept new writes, must preserve the original canonical
turn identity, checkpoint an entry only after journal acceptance, and must have
a behavioral migration test. It may retain the source read-only for the bounded
rollback window; this is migration input, not a second store.

## Canonical journal contract

- `conversation_turns` is the current turn projection; the monotonic
  `(conversationGeneration, turnSeq)` revision stream is the replay contract.
- Journal mutations and backend-outbox insertion commit atomically. Backend chat
  writes are a downstream projection with a payload hash. Event-triggered remote
  reconciliation reads owner-scoped pages, deduplicates by stable remote and
  canonical turn IDs, and advances a durable ID frontier—never a timestamp.
  The physical backend reader uses an owner/filter-validated Firestore document
  cursor, so a newer insertion between pages cannot shift or skip older turns.
  Backend rows preserve canonical client ID, structured blocks, and resources.
  Outbox delivery uses the existing desktop-message wire shape with the
  canonical turn ID in `client_message_id`, so a reverted release reads ordinary
  backend history rather than an incompatible journal-only format.
- Swift notifications are wakeups. `KernelTurnProjection` resumes from its
  contiguous sequence checkpoint, detects gaps, and replays by sequence.
- Main chat, floating chat, realtime voice, and Task Chat record and update
  through the same journal RPCs. Journal acceptance publishes the immediate
  pending projection; Swift cannot append a pre-journal optimistic row, persist
  it independently, or acknowledge it.
- Pre-journal backend and Task Chat history have bounded, checkpointed one-time
  import paths. After migration, main-chat list/resolve and owner activation may
  request a cooldown-coalesced remote reconciliation; an idle timer never polls
  backend history. The kernel journal remains the sole mutation owner.
- For one rollback-readable release, daemon startup repairs old-binary session
  rows without immutable profiles and journal rows without sequence/producer/
  hash revisions. Orphaned pending/streaming turns terminalize once rather than
  rendering an immortal spinner or entering the backend outbox.
- A logical surface exchange records its zero-to-two visible turns in one
  kernel transaction. Swift projects only the committed receipt; rejection of
  either half leaves neither a canonical row nor a visible orphan. Projection
  replay is fenced by immutable owner identity plus a local epoch, so suspended
  owner-A reads cannot mutate checkpoints or UI after owner B takes over.

## Surfaces

- Desktop main chat
- Notch / floating control bar chat
- PTT / realtime
- Floating agent pills
- Task views: the shared main conversation when unlinked, or the task's one
  canonical workstream conversation when linked

## Guard tests

- `desktop/macos/agent/tests/surface-session.test.ts` — surface session reuse,
  floating→main merge, owner isolation
- `desktop/macos/agent/tests/workstream-continuity.test.ts` — one conversation
  per workstream, compatibility migration, minimized continuation
- `desktop/macos/agent/tests/chat-continuity-invariant.test.ts` — ratchet against
  a second authoritative transcript store and per-surface history APIs
- `desktop/macos/agent/tests/conversation-journal.test.ts` — monotonic replay,
  generation fencing, idempotent producers, and atomic backend delivery
- `desktop/macos/agent/tests/convergence-authority-ratchet.test.ts` — no Swift
  transcript writer, voice outbox, or timestamp cursor can return
- Continuity gauntlet (manual / harness): typed → PTT → typed follow-up → spawn →
  status (`desktop/macos/scripts/agent-continuity-gauntlet.sh` when present)

## Path globs

- `desktop/macos/agent/src/runtime/**`
- `desktop/macos/Desktop/Sources/Chat/**`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatToolExecutor.swift`
- `desktop/macos/Desktop/Sources/FloatingControlBar/**`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/ChatPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/Chat*.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Components/TaskChatPanel.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/TaskChatMessageStorage.swift`
- `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskAgent/**`

## PR rule

Name `INV-CHAT-1` in the PR body if you touch the path globs above.

## Related

- [`agent-control-plane-invariants.mdx`](../../doc/developer/agent-control-plane-invariants.mdx)
