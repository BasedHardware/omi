# Phase B ground truth — voice-turn outbox, interrupted-turn capture, in-session tool surface

Mac source read in full: `RealtimeVoiceTurnOutbox.swift` (97 lines), the outbox/interruption
sections of `RealtimeHubController.swift` (3725 lines total — read targeted regions covering
init/outbox-drain, turn-start/barge-in, `hubDidFinishTurn`, `hubDidRequestTool`), and
`RealtimeHubTools.swift` (435 lines, full). Tool schemas pulled from the generated
`GeneratedRealtimeTools.swift` (703 lines, full). Windows side: read
`injectedTranscript.ts` (46 lines, full), `useChat.ts` (current send path), and
`src/main/ipc/db.ts` (table/pattern survey) to confirm there is no existing outbox, kernel
write path, or tool registry on Windows yet.

All Mac paths below are relative to
`desktop/macos/Desktop/Sources/FloatingControlBar/` unless stated otherwise.

---

## 1. Outbox durability contract

### Entry shape (`RealtimeVoiceTurnOutbox.swift:3-13`)

```swift
struct RealtimeVoiceTurnOutboxEntry: Codable, Equatable, Sendable {
  let ownerID: String
  let surfaceKind: String       // AgentSurfaceReference.surfaceKind, e.g. "main_chat"
  let externalRefKind: String   // AgentSurfaceReference.externalRefKind
  let externalRefID: String     // AgentSurfaceReference.externalRefId
  let idempotencyKey: String    // UUID string, one per logical turn
  let userText: String
  let assistantText: String
  let interrupted: Bool         // true only for a barge-in-captured partial turn
  let createdAtMs: Int64
}
```

No `partial`/status flag beyond `interrupted` — a turn is either a normal completed turn
(`interrupted: false`) or a barge-in-truncated one (`interrupted: true`). No separate origin
field is stored in the entry itself; `origin: "realtime_voice"` is a hardcoded literal passed
at the `recordSurfaceTurn` call site (`RealtimeHubController.swift:1448`), not persisted in the
outbox record.

### Storage (`RealtimeVoiceTurnOutbox.swift:19-96`)

- Backing store: `UserDefaults.standard`, key `"realtimeVoiceTurnOutbox.v1"`, JSON-encoded
  `[RealtimeVoiceTurnOutboxEntry]` blob (`JSONEncoder`/`JSONDecoder`, whole-array
  read-modify-write on every mutation — no per-entry granularity).
- `@MainActor final class RealtimeVoiceTurnOutbox`, singleton `.shared`. Loads all entries
  synchronously in `init()` from the UserDefaults blob (or empty array if missing/undecodable)
  — this is the "replay" seed; entries left over from a killed/crashed app session are still
  in `UserDefaults` on next launch and get loaded back into memory here.
- `enqueue(_:)` (line 41-45): dedupes on `idempotencyKey` (no-op if already present), else
  appends + persists.
- `acknowledge(idempotencyKey:)` (line 47-52): removes matching entry, persists only if the
  count actually changed.
- `entries(ownerID:)` / `entries(ownerID:surface:)`: read-only filters, no mutation.
- `seedContext(...)`: builds a reversed (newest-first internally, output oldest-first),
  character-budgeted (`maxCharacters`, default 24_000) text block of `"User: ..."` /
  `"Omi[ (interrupted)]: ..."` lines from an owner+surface's outbox entries, for priming a
  fresh voice session with continuity before the kernel round-trip lands. Used at
  `RealtimeHubController.swift:1276` (`voiceTurnOutbox.seedContext(...)`, merged with
  `excludingIdempotencyKeys` so entries already reflected server-side aren't double-seeded).

### Replay-on-restart (actual mechanism — no separate "replay" method exists)

There is **no explicit replay function**. Replay is the composition of two things:
1. `RealtimeVoiceTurnOutbox.init()` loading the persisted UserDefaults blob back into
   `entries` at process start (i.e., at next app launch or `RealtimeHubController` singleton
   construction).
2. `RealtimeHubController`'s setup path calling `scheduleVoiceTurnOutboxDrain()` once, at
   `RealtimeHubController.swift:805` (inside its init/setup routine, run every app launch,
   not gated on any "was there a crash" check).

`scheduleVoiceTurnOutboxDrain(delayNanoseconds:)` (line 1496-1520):
- No-ops if there's no signed-in owner, a drain task is already running, or the owner's
  outbox is already empty.
- Otherwise spawns a `Task` that (after an optional delay) loops `drainVoiceTurnOutbox` with
  `maximumAttempts: 1` per iteration, sleeping 2s between failed attempts, until the owner's
  outbox is empty, the owner changes, or the task is cancelled.

`drainVoiceTurnOutbox(ownerID:through:maximumAttempts:)` (line 1524-1551) — the actual
replay/drain loop:
- **Single-writer ordering invariant**: "Only the oldest pending turn for an owner may write.
  Later turns cannot overtake it, whether this is the bounded foreground path or background
  replay." It always takes `entries(ownerID:).first` (insertion order = chronological), never
  reorders or parallelizes.
- Per entry: calls `recordTurnToKernelAwaiting(entry)` → `FloatingControlBarManager.shared
  .recordSurfaceTurn(surface:ownerID:userText:assistantText:origin:"realtime_voice"
  :interrupted:idempotencyKey:)` → ... → `KernelTurnProjection.recordSurfaceTurn` →
  `AgentClient.recordSurfaceTurn` (an RPC to the kernel/bridge process) which `throws` on
  failure and returns `Bool` (ack) on success.
- On ack (`true`): `voiceTurnOutbox.acknowledge(idempotencyKey:)` removes the entry — **this
  is the only removal path**; nothing is ever removed from the outbox without a positive ack
  from the kernel RPC.
- On failure: retries up to `maximumAttempts`, sleeping 250ms between attempts within one
  `drainVoiceTurnOutbox` call; the outer `scheduleVoiceTurnOutboxDrain` loop retries again
  after 2s if the background drain task is still active.

### Idempotency key generation & lifecycle

- Generated once per **input turn start**, not per persisted attempt:
  `turnIdempotencyKey = UUID().uuidString` at `RealtimeHubController.swift:1987`, inside the
  turn-start method (`beginTurn`-equivalent), every time a new PTT hold begins.
- The SAME key is captured and reused for both possible outcomes of that turn:
  - Normal completion: `hubDidFinishTurn` (line 3319) reads `let completedTurnIdempotencyKey
    = turnIdempotencyKey` (line 3349) before persisting.
  - Barge-in/interruption: `captureInterruptedTurnPayloadIfNeeded()` (line 2138) reads
    `let idempotencyKey = turnIdempotencyKey` (line 2146) — i.e. it captures the **outgoing**
    turn's key (captured at line 1951, BEFORE the new turn overwrites `turnIdempotencyKey` at
    line 1987).
- Immediate optimistic UI staging uses the same key: `FloatingControlBarManager.shared
  .stageRealtimeVoiceTurn(userText:assistantText:idempotencyKey:)` (called at
  `persistTurnToKernelThroughTransientFailures`, line 1479) → `historyChatProvider?
  .stageOptimisticTurn(continuityKey: idempotencyKey, ...)`. The kernel's later
  `turn_recorded` event with the same key promotes (not appends to) that staged message —
  this is INV-6 rule 3/4 (`desktop/macos/AGENTS.md`): one idempotency key per logical turn,
  staged first for instant UI, promoted in place when the kernel ack arrives.
- The outbox entry's `idempotencyKey` is this same UUID string — so an outbox replay after a
  restart reuses the exact key the optimistic UI staged (or would have staged) before the
  crash, meaning kernel-side dedup (`appliedKernelTurnKeys` in `KernelTurnProjection.swift`)
  makes replay safe even if the kernel actually received a request before the crash but the
  ack never reached the client.

### `persistTurnToKernelThroughTransientFailures` — write orchestration (line 1457-1494)

This is the single entry point both the completed-turn path and the interrupted-turn path
call into:
1. Resolve `ownerID` from `RuntimeOwnerIdentity.currentOwnerId()` — **no owner → the turn is
   dropped with only a log line, never enqueued** (there is no "queue until signed in" path).
2. Build the `RealtimeVoiceTurnOutboxEntry` (surface = `mainChatSurfaceReference()`, i.e. the
   canonical main-chat `AgentSurfaceReference`, not a voice-specific surface).
3. `voiceTurnOutbox.enqueue(entry)` — durable write happens BEFORE any network/RPC attempt.
4. `FloatingControlBarManager.shared.stageRealtimeVoiceTurn(...)` — optimistic UI update,
   also before the RPC.
5. `await drainVoiceTurnOutbox(ownerID:through: idempotencyKey, maximumAttempts: 2)` — bounded
   foreground attempt (2 tries) to get an ack on the critical path.
6. If not acknowledged: log + `scheduleVoiceTurnOutboxDrain(delayNanoseconds: 1_000_000_000)`
   — falls off the voice-session critical path into the background drain loop described above.

### Recommended Windows storage approach

Windows already has an additive-migration SQLite pattern in `src/main/ipc/db.ts`
(`CREATE TABLE IF NOT EXISTS ...`, `better-sqlite3`, exposed to renderer via preload/IPC —
see e.g. `insertLocalConversation`, `updateLocalConversationSync`). **Recommend a SQLite table
over a durable-JSON blob**, mirroring the Mac entry shape 1:1:

```sql
CREATE TABLE IF NOT EXISTS voice_turn_outbox (
  idempotency_key TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  surface_kind TEXT NOT NULL,
  external_ref_kind TEXT NOT NULL,
  external_ref_id TEXT NOT NULL,
  user_text TEXT NOT NULL,
  assistant_text TEXT NOT NULL,
  interrupted INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL
);
```

Rationale over a UserDefaults-equivalent (e.g. `electron-store` JSON blob): Windows already
persists conversations relationally in this same file (`local_conversation` table at
`db.ts:90`), better-sqlite3 gives per-row insert/delete instead of whole-blob
read-modify-write on every enqueue/ack (relevant since PTT turns can be frequent), and it
survives the same crash-recovery story (SQLite file on disk, loaded fresh on next launch —
equivalent to `UserDefaults` surviving a kill). Keep the query surface minimal and mirror the
Mac API 1:1: `enqueueVoiceTurn(entry)` (dedupe on `idempotency_key`, `INSERT OR IGNORE`),
`acknowledgeVoiceTurn(idempotencyKey)` (`DELETE WHERE idempotency_key = ?`),
`listVoiceTurnOutbox(ownerId[, surface])` (ordered by `created_at_ms ASC` — oldest first, to
preserve the single-writer-ordering invariant), and a `seedContext` equivalent built in JS from
the query result (no need to push that formatting into SQL).

Main-process ownership: put this next to the other `db.ts` tables (main process owns
SQLite), expose enqueue/acknowledge/list via IPC to the renderer's voice-turn write path,
same as other renderer→main DB calls in this file.

---

## 2. Interrupted-turn capture

### Trigger condition (`RealtimeHubController.swift:1940-1951`)

Captured at the **start of a new PTT/voice turn**, only when barging in on a still-active
previous turn:

```swift
let providerResponseInFlight = responding
let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking
let bargeIn = responding || realtimePlaybackActive || voicePlaybackActive
...
let interruptedTurnTask = bargeIn ? captureInterruptedTurnPayloadIfNeeded() : nil
```

`bargeIn` is true if the provider is still generating a response (`responding`), realtime
audio is still playing (`realtimePlaybackActive`), or local TTS playback is still speaking
(`voicePlaybackActive`) at the moment the user starts a new hold. This runs BEFORE any of the
new turn's state resets (`turnTranscript = ""`, `assistantText = ""`,
`turnIdempotencyKey = UUID().uuidString` all happen afterward, lines 1977-1987), so the
capture function reads the OLD (about-to-be-clobbered) turn's in-flight state.

### Capture function (`captureInterruptedTurnPayloadIfNeeded`, line 2138-2159)

```swift
private func captureInterruptedTurnPayloadIfNeeded() -> Task<InterruptedTurnPayload?, Never>? {
  guard !turnRecorded else { return nil }
  let providerText = turnTranscript
  let localTask = fullLIDTask
  guard !providerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || localTask != nil
  else { return nil }
  let preferredLanguages = AssistantSettings.shared.voiceBaseLanguages
  let partialAssistantText = assistantText
  let idempotencyKey = turnIdempotencyKey
  return Task {
    let resolution = await Self.resolveTranscript(
      providerText: providerText, preferredLanguages: preferredLanguages, localTask: localTask)
    guard !resolution.userText.isEmpty else { return nil }
    return InterruptedTurnPayload(
      userText: resolution.userText,
      assistantText: InterruptedTurnPayload.visibleAssistantText(
        partialAssistantText: partialAssistantText),
      idempotencyKey: idempotencyKey)
  }
}
```

Guards (either short-circuits to `nil`, i.e. nothing captured):
- `turnRecorded` already true → the outgoing turn already finished normally and was recorded;
  nothing to capture (avoids double-recording the same turn).
- No provider transcript text AND no in-flight local-language-ID task → nothing was said this
  turn, nothing to capture.
- After async transcript resolution, an empty resolved `userText` also yields `nil` (checked
  by the caller before persisting).

### Payload shape (`InterruptedTurnPayload`, line 249-258)

```swift
struct InterruptedTurnPayload: Equatable {
  let userText: String        // resolved via the same provider/local-transcript policy as a completed turn
  let assistantText: String   // trimmed PARTIAL streamed assistant text only — never fabricated/completed
  let idempotencyKey: String  // the OUTGOING turn's turnIdempotencyKey, captured before overwrite
}
```

`visibleAssistantText(partialAssistantText:)` is deliberately just a trim — no truncation
marker, no "..." — the barged reply is recorded exactly as far as it got and no further.

### Recording path (asynchronous, deferred to `enqueueTurnPersistence`)

Two call sites persist the captured task's resolved value, both wrapping
`persistTurnToKernelThroughTransientFailures(..., interrupted: true, ...)`:
1. **Normal barge-in** (line 1988-1998): if not superseding a pending replacement session,
   and (not `providerResponseInFlight` or the session isn't using the Gemini
   `.freshSession` barge-in strategy), enqueue immediately via `enqueueTurnPersistence`.
2. **Fresh-session replacement barge-in** (Gemini `.freshSession` strategy — line 1627-1636,
   inside `completeBargeInReplacementAfterContinuity`): the interrupted turn is recorded as
   part of `RealtimeHubBargeInContinuity.prepareReplacementSession`'s
   `recordInterruptedTurn` callback, which runs BEFORE the seed-context refresh and BEFORE the
   replacement session starts — guaranteeing the interrupted turn is durably queued (outbox
   `enqueue` happens synchronously inside `persistTurnToKernelThroughTransientFailures`) prior
   to the new session's seed context being fetched, so the new session's continuity seed can
   include it if the kernel ack already landed.

Either way, the interrupted turn goes through the exact same
`persistTurnToKernelThroughTransientFailures` → outbox-enqueue → stage-optimistic →
bounded-foreground-drain → background-drain-fallback pipeline as a normally completed turn;
`interrupted: true` is the only distinguishing field carried through to the
`RealtimeVoiceTurnOutboxEntry` and ultimately to `recordSurfaceTurn`'s `interrupted:` param.

---

## 3. Complete Mac realtime tool surface (23 tools = 21 general + 2 permission)

Source of truth: `desktop/macos/Desktop/Sources/Generated/GeneratedRealtimeTools.swift`
(generated by `agent/scripts/generate-tool-surfaces.mjs` — do not hand-edit on Mac; Windows
Phase B should treat this JSON schema block as the canonical spec to port, and dispatch targets
below come from the `switch` in `hubDidRequestTool`, `RealtimeHubController.swift:2749-3116`).
One shared JSON-schema tool list is declared to BOTH providers: OpenAI Realtime gets it as-is
(`session.tools`); Gemini gets it transformed (uppercase JSON-schema `type`, drop
`additionalProperties`/`$schema`/`default`/`title`/`pattern`/`const` keys) via
`RealtimeHubTools.geminiFunctionDeclarations` (`RealtimeHubTools.swift:347-405`).

| # | Tool (`HubTool` enum) | Params (name: type, required in **bold**) | Dispatch target |
|---|---|---|---|
| 1 | `search_screen_history` | **query**: string; days: number (default 7); app_filter: string | `ChatToolExecutor.execute("search_screen_history", …)` — same executor chat uses |
| 2 | `get_daily_recap` | days_ago: number (0=today, default 1) | `ChatToolExecutor.execute("get_daily_recap", …)` — on-device activity DB |
| 3 | `list_agent_sessions` | status: enum[open,archived,closed]; surfaceKind: enum[main_chat,task_chat,realtime,delegated_agent,background_agent,floating_bar,floating_pill]; limit: number (default 50) | `agentControlService.executeVoiceTool(name:arguments:)` — canonical agent control plane |
| 4 | `get_agent_run` | agentRef: string; runId: string; includeEvents: boolean (default true); eventLimit: number (default 100) | `agentControlService.executeVoiceTool` |
| 5 | `cancel_agent_run` | agentRef: string; runId: string | `agentControlService.executeVoiceTool` |
| 6 | `inspect_agent_artifacts` | agentRef/artifactRef/artifactId/sessionId/runId/attemptId: string; role: enum[input,result,checkpoint,tool_output,log,other]; limit: number (default 50) | `agentControlService.executeVoiceTool` |
| 7 | `update_agent_artifact_lifecycle` | **state**: enum[retained,dismissed,opened]; artifactRef/artifactId/sessionId/runId/attemptId: string; reason: string | `agentControlService.executeVoiceTool` |
| 8 | `spawn_agent` | **objective**: string; provider: enum[openclaw,hermes] (only listed if a local provider is actually available); parent_run_id, title, brief: string; visible: boolean (default true) | `handleRealtimeDelegationRequest(...)` → `AgentDelegationResolver.shared.resolve(...)` (resolver may spawn, continue an existing agent, or ask for missing info) — NOT a direct spawn |
| 9 | `set_desktop_attention_override` | **subjectKind**, **subjectId**: string; ownerId: string (defaults to signed-in owner); dismissed: boolean (default true); hiddenUntilMs: number; reason: string | `agentControlService.executeVoiceTool` — gated: dismissal requires `userExplicitlyRequestedPillManagement` heuristic on the transcript, else blocked with an explicit refusal string |
| 10 | `get_conversations` | start_date/end_date: string (ISO+tz); limit: number (default 20); offset: number; include_transcript: boolean | `APIClient.shared.toolGetConversations(limit: 3, includeTranscript: false)` — backend REST, capped for voice regardless of requested `limit` |
| 11 | `search_conversations` | **query**: string; start_date/end_date: string; limit: number (default 5, max 20); include_transcript: boolean | `APIClient.shared.toolSearchConversations(query:limit:5, includeTranscript:false)` — backend REST |
| 12 | `get_memories` | limit: number (default 50); offset: number; start_date/end_date: string | `APIClient.shared.toolGetMemories(limit: 15)` — backend REST |
| 13 | `search_memories` | **query**: string; limit: number (default 5, max 20) | `APIClient.shared.toolSearchMemories(query:limit:5)` — backend REST |
| 14 | `get_action_items` | limit/offset: number; completed: boolean; start_date/end_date/due_start_date/due_end_date: string | `APIClient.shared.toolGetActionItems(limit:25, completed:dueStartDate:dueEndDate:)` — backend REST |
| 15 | `create_action_item` | **description**: string; due_at: string (ISO); conversation_id: string | `APIClient.shared.toolCreateActionItem(description:dueAt:)` — backend REST write |
| 16 | `update_action_item` | **id**: string (must come from a prior `get_tasks`); completed: boolean; description: string; due_at: string | `APIClient.shared.toolUpdateActionItem(id:completed:description:dueAt:)` — backend REST write |
| 17 | `check_permission_status` | type: enum[screen_recording,microphone,notifications,accessibility,automation,full_disk_access] (omit = all) | `ChatToolExecutor.execute(...)` via `RealtimeHubTools.permissionExecutorRoute` — same native permission flow as main chat |
| 18 | `request_permission` | **type**: same enum as #17 | `ChatToolExecutor.execute(...)` — opens native prompt / System Settings pane |
| 19 | `get_tasks` | *(no params)* | Local: `TasksStore.shared.loadDashboardTasks()` then reads `overdueTasks`/`todaysTasks` directly — no backend call, no agent |
| 20 | `create_calendar_event` | **title**, **start_time**, **end_time** (ISO-8601 w/ tz); description, location, attendees: string | `APIClient.shared.toolCreateCalendarEvent(title:startTime:endTime:description:location:attendees:)` — backend REST write; app-side validates title/start/end are non-empty before calling |
| 21 | `ask_higher_model` | **query**: string; context: string | `escalateToHigherModel(query:context:aboutUser:)` → `POST /v2/chat/completions` using `ModelQoS.Claude.defaultSelection`; app-side rejects if `shouldRejectEscalationQueryForLanguage` flags the query as outside the user's configured voice languages |
| 22 | `screenshot` | *(no params)* | OpenAI only: `ScreenCaptureManager.captureScreenJPEG()` (or reuses `speculativeScreenshot` captured at turn start) then `session?.injectImage(shot)` into the live session. Gemini: no-op (`shot = nil`) — Gemini gets screen frames via a different in-session video path, not this tool |
| 23 | `point_click` | **x**, **y**: number (pixel coords) | `Self.click(at: CGPoint(x:y:))` — local mouse-click simulation; validates finite coordinates first |

Notes for Windows porting:
- Reads (`get_tasks`, `get_memories`, `search_memories`, `search_conversations`,
  `get_conversations`, `get_action_items`, `search_screen_history`, `get_daily_recap`) and
  simple writes (`create_action_item`, `update_action_item`, `create_calendar_event`) all run
  **synchronously in-turn and speak the result** — they do NOT go through `spawn_agent`.
  Everything else (multi-step, other-app work) is explicitly routed to `spawn_agent`, which
  itself is a **resolver call, not a direct dispatch** (may ask a clarifying question instead
  of spawning).
- `spawn_agent`'s `provider` enum is dynamically populated based on which local providers
  (`openclaw`, `hermes`) are actually detected as available (`availableDirectedProviderRawValues()`)
  — the schema sent to the model changes per-session, not a static enum.
- Permission tools (`check_permission_status`, `request_permission`) and agent-control tools
  (`list_agent_sessions`, `get_agent_run`, `cancel_agent_run`, `inspect_agent_artifacts`,
  `update_agent_artifact_lifecycle`, `set_desktop_attention_override`) are explicitly documented
  in the system prompt as "never spawn an agent for this" — they must be direct, fast, in-turn
  tool calls even on Windows.
- Every tool result flows back through `sendToolResultIfCurrent(source:callId:name:output:
  expectedTurnEpoch:)`, which discards stale results if the turn has since moved on
  (`turnEpoch` fencing) — Windows' tool-registry consumer needs an equivalent turn-generation
  guard so a slow tool call from turn N can't land after turn N+1 has started.

---

## 4. Track-1 interfaces to request/stub

Windows currently has **no chat/kernel write path at all** for voice —
`injectedTranscript.ts` only formats assistant TTS text into the ambient always-on
transcription record (`window.omi.captureCommand`), which is a different, non-conversational
store (confirmed: no `ChatMsg`/conversation append call anywhere in that file). `useChat.ts`'s
`send()` is the only real chat write path today, and it has no idempotency key, no kernel
concept, no tool registry, and is not consumable from a background voice turn (it owns its own
React state, not an exported append function).

To implement Phase B (voice turns landing in Track 1's shared chat/kernel history, plus
in-session tool-calling riding Track 1's registry) I need Track 1 to publish:

1. **`appendVoiceTurnToChat(...)` (or equivalent exported function)** — the Windows analog of
   `FloatingControlBarManager.recordSurfaceTurn` / `KernelTurnProjection.recordSurfaceTurn`.
   Needs: `surface` reference (chat/conversation id equivalent to `AgentSurfaceReference`),
   `ownerId`, `userText`, `assistantText`, `origin` string, `interrupted: boolean`,
   `idempotencyKey: string` — and must return/resolve a boolean (or throw) indicating whether
   the kernel/store actually acknowledged the write, so the outbox knows when it's safe to
   `acknowledge()`/delete the row.
2. **An optimistic-stage / promote-on-ack pair** — Mac's `stageOptimisticTurn(continuityKey:
   userText:assistantText:origin:turnOwner:)` + kernel-driven promotion keyed on the same
   `continuityKey`. Windows needs the equivalent so the chat UI shows the voice turn instantly
   while the durable write is still in flight/retrying.
3. **A `mainChatSurfaceReference()`-equivalent accessor** — resolves "the" canonical main-chat
   surface/conversation id to attach voice turns to, so Phase B doesn't have to hardcode or
   guess a conversation id.
4. **A voice-seed-context fetch** (Mac: `kernelVoiceSeedSnapshot()` /
   `fetchVoiceSeedSnapshot(surface:)` returning `{conversationId, context, idempotencyKeys}`)
   — used to prime a fresh voice session with recent chat continuity and to know which
   idempotency keys are already reflected server-side (so the local outbox's `seedContext`
   doesn't double-inject them).
5. **The tool-call dispatch/registry surface** — an equivalent of `hubDidRequestTool` /
   `ChatToolExecutor.execute(ToolCall)` that Phase B's realtime tool handler can call into for
   the read/write tools in section 3 (ideally the SAME executor Track 1's typed-chat tool
   calling uses, per Mac's "same code path for voice and chat" pattern), plus whatever
   turn-generation/epoch fencing mechanism Track 1 uses to drop stale tool results.
6. **A turn-recorded / promotion event or callback** — something Phase B can hook so the chat
   UI updates when a background-outbox-drained (as opposed to foreground) turn finally lands,
   mirroring Mac's `turn_recorded` kernel event → `KernelTurnProjection.apply` →
   `promoteOptimisticTurn`.

If Track 1 hasn't published these yet, Phase B should build the outbox (SQLite table,
enqueue/acknowledge/list — section 1) and the interrupted-turn capture logic (section 2) now,
since both are self-contained and storage-only, but must stub the actual kernel-write call
behind the six interfaces above rather than writing directly to `useChat.ts`'s local state or
inventing a parallel conversation store.
