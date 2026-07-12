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
- Treat backend message rows as authoritative for agent context or continuity
  (backend chat may be a downstream projection/export only).
- Let Swift own session identity, model context assembly, or run truth.

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
