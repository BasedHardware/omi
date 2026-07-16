# INV-CHAT-1: One shared transcript across surfaces

**Status:** locked
**Statement:** Typed chat, notch / floating bar, PTT/realtime, and floating pills
are input/output devices against one kernel-owned conversation transcript. There
is one shared chat mind across surfaces — not per-surface product histories.

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
- Task chat projections that share the user conversation

## Guard tests

- `desktop/macos/agent/tests/surface-session.test.ts` — surface session reuse,
  floating→main merge, owner isolation
- `desktop/macos/agent/tests/chat-continuity-invariant.test.ts` — ratchet against
  a second authoritative transcript store and per-surface history APIs
- Continuity gauntlet (manual / harness): typed → PTT → typed follow-up → spawn →
  status (`desktop/macos/scripts/agent-continuity-gauntlet.sh` when present)
- `desktop/windows/src/main/ipc/voiceHub.test.ts` — Windows voice path: a hub turn
  records into the one main_chat conversation (typed-tail visible), and a hub record
  + a cascade `mainChat:send` sharing one turnId record the human turn EXACTLY ONCE
  (the Windows equivalent of the pi-mono `saveSpy=2` double-record assertion).
- `desktop/windows/src/renderer/src/hooks/useChat.test.tsx` — recordVoiceTurn writes
  the one kernel conversation + the shared/mobile echo, once, and never for an empty
  turn.

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
- `desktop/windows/src/main/agentKernel/**`
- `desktop/windows/src/main/ipc/voiceHub*`
- `desktop/windows/src/main/ipc/mainChat.ts`
- `desktop/windows/src/renderer/src/hooks/useChat.ts`
- `desktop/windows/src/renderer/src/lib/voice/**`
- `desktop/windows/src/renderer/src/components/chat/VoiceHubDriverHost.tsx`

## PR rule

Name `INV-CHAT-1` in the PR body if you touch the path globs above.

## Related

- [`agent-control-plane-invariants.mdx`](../../doc/developer/agent-control-plane-invariants.mdx)
