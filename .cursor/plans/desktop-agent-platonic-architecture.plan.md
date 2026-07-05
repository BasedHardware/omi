# Desktop Agent Platonic Architecture — Coordination Plan

**Status:** COMPLETE — gap-closure G1–G12 @ branch HEAD. See `.cursor/plans/desktop-agent-platonic-gap-closure.plan.md`.
**Branch train:** `desktop-agent-platonic` (stacked phase branches).
**Base commit:** `9dd2eae62`

### Progress tracker

| Phase | Status | Branch | Commit | Notes |
|-------|--------|--------|--------|-------|
| 0 — Gauntlet runner | ✅ Done | `desktop-agent-p0-gauntlet` | `b2250eccb` | `agent-continuity-gauntlet.sh` + automation hooks |
| 1 — Tool manifest codegen | ✅ Done | `desktop-agent-p1-tool-manifest` | `654e27730` | 4→1 declaration sites; generated Swift surfaces |
| 2 — Session identity (+8 facade) | ✅ Done | `desktop-agent-p2-session-identity` | `a3501a07f` | `surface_conversations` + `AgentClient`; changelog added |
| 2-review | ✅ PASS WITH GAPS | — | — | See blockers 1–5 in review notes |
| 2-fix | ✅ Done | `desktop-agent-p2-gap-fix` | `928a16109` | All 5 review blockers closed |
| 3 — Turn context authority | ✅ Done | `desktop-agent-p3-turn-context` | `612970342` | ChatProvider −281 lines; kernel `turn-context.ts` |
| 3-review | ✅ PASS WITH GAPS | — | — | Voice deferred to Phase 4; no hard blockers |
| 4 — PTT unified transcript | ✅ Done | `desktop-agent-p4-ptt-transcript` | `bab22b261` | ~495 lines deleted; kernel `turn_recorded` events |
| 4-review | ✅ PASS WITH GAPS | — | — | Barge-in race + ChatProvider voice wrappers |
| 4-fix | ✅ Done | `desktop-agent-p4-gap-fix` | `107d48893` | Barge-in ordering + `KernelTurnProjection` |
| 5 — Pills as projections | ✅ Done | `desktop-agent-p5-pills` | `2a8a5fdc2` | −1043 lines; TaskAgent execution partial |
| 5-review | ✅ PASS WITH GAPS | — | — | TaskAgent loop, dual spawn tools, stale tests |
| 5-fix | ✅ Done | `desktop-agent-p5-gap-fix` | `71f9fea4f` | TaskChatRuntime + single spawn tool |
| 6 — Burn compat layer | ✅ Done | `desktop-agent-p6-compat-burn` | `17dfc751c` | v2-only protocol; −360 lines |
| final-review | ✅ COMPLETE WITH GAPS | — | — | See §7 remaining debt |
| 7-8-cleanup | ✅ Done | `desktop-agent-p78-cleanup` | `d7a95a221` | AgentClient.Session; kernel split |

### §7 Remaining debt (post-audit)

| Item | Severity | Status |
|------|----------|--------|
| Live gauntlet E2E + evidence bundle | Medium | ✅ `20260705T055200Z` @ `83b0ba57b` | gap-closure G3 |
| ChatProvider → AgentClient (Phase 8) | Medium | ✅ `d7a95a221` |
| `kernel.ts` split / shrink (Phase 7) | Low–Med | ✅ re-export barrel + modules |
| `AgentPillsManager` hybrid execution state | Low–Med | ✅ closed — `AgentPill.swift` projections only; spawn/continue/stop delegate to kernel |
| Migration shims (`import_legacy_*`, sqlite legacy cols) | Low | scheduled burn — delete ship+2 after platonic release (gap-closure G6) |
**Scope:** `desktop/macos/` — Swift app (`Desktop/Sources`), TS agent runtime (`agent/`), realtime/PTT surfaces, floating pills, task chat, onboarding, reader services.
**Audience:** Any agent or human implementing any phase. Read this whole document before touching code.
**Written:** 2026-07-04, from a full architecture review of the current tree (commit ~`9dd2eae62`).

---

## 0. How to read this document

This plan is **prescriptive, not advisory**. Words are used precisely:

- **MUST / MUST NOT** — hard requirement. Violating it means the phase is not done, even if tests pass.
- **DELETE** — remove the code entirely in the same PR. Do not comment out, do not feature-flag off, do not keep "just in case". Deletion is the deliverable.
- **FORBIDDEN** — a tempting shortcut that has been explicitly considered and rejected. If you find yourself doing it, stop and re-read the phase.

If a phase seems too big, the correct response is to split the phase into smaller PRs **that each still respect every invariant**, not to weaken the invariant. If an invariant genuinely cannot be satisfied, stop, write down why, and escalate to the plan owner — do not silently deviate.

**This plan supersedes the deferrals in `desktop/macos/docs/agent-coordinator.md` Phase 0** where they conflict (specifically: floating-pill replacement and PTT parent-turn routing are no longer deferred; they are Phases 5 and 4 here). All other Phase 0 invariants in that doc remain binding and are strengthened below.

---

## 1. The platonic ideal (north star)

The end state is four sentences. Every phase moves monotonically toward it; no phase may move away from it "temporarily".

1. **One state machine.** The TypeScript runtime kernel + `omi-agentd.sqlite3` is the *only* authority for agent sessions, runs, attempts, transcripts, tool grants, artifacts, and delegations. No authoritative agent state persists anywhere else — not UserDefaults, not Swift-side caches that outlive a render, not per-surface rings. Downstream product projections may exist only under INV-9.
2. **One tool manifest.** Every tool that any model on any surface can see is declared exactly once, in `agent/src/runtime/omi-tool-manifest.ts` (plus `control-tool-manifest.ts` for kernel control tools). All other representations — Swift prompt docs, realtime tool JSON, executor dispatch tables — are *generated or served* from it. A human or agent adding a tool edits one file.
3. **One transcript per user conversation.** Typed chat, PTT/realtime, and the floating bar are *input/output devices* against the same kernel-owned conversation history. There is no mirroring, no reconciliation of "early bubbles", no per-surface continuity ring, no sanitized text-blob seeding. Context for any turn on any surface is assembled by the kernel from its own store, in one place.
4. **Swift is a pure renderer and event source.** Swift sends `(ownerId, surfaceRef, user input)` and renders event streams and projections. Swift never resolves session identity, never assembles model context, never decides tool availability, never owns run truth.

The current codebase violates each of these in a specific, enumerable way. Each phase below closes one violation **and deletes the machinery of the violation** so it cannot regress.

### 1.1 Global invariants (binding in every phase, every PR)

- **INV-1 (No second store):** No new persistent or semi-persistent store of agent/session/transcript state outside `omi-agentd.sqlite3` may be introduced, for any reason, including "as a cache", "for offline", or "temporarily during migration". Existing extra stores are only ever deleted.
- **INV-2 (Delete with the replacement):** Any PR that lands a replacement mechanism MUST delete the mechanism it replaces in the same PR (or the same stacked PR train landing together). "Old path kept behind a flag" is FORBIDDEN. The single allowed exception is an explicit kill-switch env var with a scheduled deletion date written into this plan (see per-phase notes).
- **INV-3 (Net-negative duplication):** Every phase must end with strictly fewer sources of truth than it started with. Count them in the PR description.
- **INV-4 (Prompts don't teach architecture):** If a system prompt or tool doc has to explain to the model which of two internal mechanisms to use (e.g. today's "do not treat spawn_agent as an alias for delegate_agent"), that is a defect of the architecture, not a prompting task. Fix the mechanism; never add more prompt text to arbitrate between internal mechanisms.
- **INV-5 (Kernel-authoritative identity):** After Phase 2, no Swift code may pass, store, or fall back on a session identifier. Grep-able enforcement: the strings `sessionKey`, `omiSessionId`, `legacyClientScope`, `resume:` must not appear in `Desktop/Sources` outside the generated protocol layer.
- **INV-6 (Test before merge):** Every phase runs `cd desktop/macos && ./scripts/agent-logic-harness.sh` plus the phase's own acceptance tests, plus a real end-to-end self-test in a named `omi-*` bundle exercising: typed turn → PTT turn → typed follow-up referencing the PTT turn → background agent spawn → status query about that agent. This 5-step "continuity gauntlet" is the standing smoke test for the whole plan and MUST pass at the end of every phase.
- **INV-7 (No new capabilities mid-refactor):** Phases 1–6 are refactors. Do not add new tools, new surfaces, or new model features inside them. New capability work waits for the end state or lands orthogonally.
- **INV-8 (Projection is not authority):** Swift may keep ephemeral render state only: streaming buffers, optimistic rows, selection/window state, and event cursors that can be discarded and rebuilt from kernel events. Anything used to resume a run, reconcile identity, construct model context, answer a status query, or survive app restart is not a render cache and is FORBIDDEN outside the kernel.
- **INV-9 (Backend chat is downstream):** This desktop-local wave does not redesign backend/mobile chat sync. Backend message persistence may remain as a product projection/export for visible chat history, but agent context and continuity MUST never read from backend message rows. The kernel transcript is authoritative for agent turns; backend sync consumes kernel/UI events, not the reverse.

### 1.2 Canonical terminology (use these names; rename code toward them)

| Term | Meaning | The only ID that survives |
|---|---|---|
| **Conversation** | A user-visible thread (main chat session, task chat, onboarding). Kernel-owned. | `conversationId` (kernel) |
| **Surface** | An input/output device: `main_chat`, `realtime_voice`, `floating_bar`, `task_chat`, `onboarding`, `service:<name>` | `surfaceRef` (kind + external ref) |
| **AgentSession / AgentRun / RunAttempt / AdapterBinding** | As today, kernel tables | kernel IDs |
| **Adapter-native session id** | Private to adapters; never crosses into Swift | n/a (internal) |

The words `sessionKey`, `legacyClientScope`, `resume` (as a parameter), `harnessMode` (as a per-callsite string) are **legacy vocabulary** and are scheduled for deletion (Phases 2 and 6).

---

## 2. Current-state defect map (why each phase exists)

Findings from the 2026-07-04 review, with anchors. Verify anchors before editing; line numbers drift.

| # | Defect | Evidence |
|---|---|---|
| D1 | Tool surface defined in ≥4 places, two languages | `agent/src/runtime/omi-tool-manifest.ts`, `agent/src/runtime/control-tool-manifest.ts`, `Desktop/Sources/FloatingControlBar/RealtimeHubTools.swift` (~22 hand-written JSON schemas), `Desktop/Sources/Chat/DesktopCapabilityRegistry.swift` (prose docs + its own surface matrix; self-admits drift risk at top comment), executors split across `ChatToolExecutor.swift` and `omi-tools-stdio.ts` |
| D2 | Session identity resolved from 7 concepts across 3 stores | `ChatProvider.swift:4127-4151` fallback chain; `MainChatRuntimeSessionStore.swift` (UserDefaults!); `AgentRuntimeStatusStore.swift`; kernel sqlite. Violates the projection rule in `docs/agent-coordinator.md` |
| D3 | Turn context triple-tracked + 3 pre-query IPC round trips | adapter-native history (ACP/pi-mono resume) + `buildMainChatContextPacketPrompt` (`ChatProvider.swift:2439`, embeds last 6 messages) + coordinator route/delta preambles (`ChatProvider.swift:2522-2610`) |
| D4 | PTT/typed context bridged by mirroring + two history mechanisms | `beginVoiceUserMessage`/`recordVoiceTurn` early-bubble reconciliation; local ring `rememberVoiceContinuityTurn`/`combinedTopLevelVoiceContinuityContext` (`RealtimeHubController.swift:1712-1746`); sanitized seed blob `buildTopLevelVoiceContinuityContext` (`ChatProvider.swift:2413`) with different caps/sanitizers |
| D5 | Three subagent systems | floating pills (`spawn_agent`/`manage_agent_pills`), kernel delegations (`delegate_agent`), ProactiveAssistants TaskAgent; prompt text arbitrates between them (`DesktopCapabilityRegistry.swift` delegation guidance) |
| D6 | Legacy protocol/compat debt | protocol v1+v2 (`index.ts` `withQueryCorrelation`), `legacyAdapterSessionId`, `legacy-permission-policy.ts`, `JsonlCompatibilityFacade`, deprecated `QueryResult.sessionId` (`AgentBridge.swift:48`), checked-in build artifact `acp-bridge/dist/index.js` with no live references |
| D7 | God objects | `ChatProvider.swift` 5,210 lines (930-line `sendMessage`), `FloatingControlBarWindow.swift` 4,016, `kernel.ts` 3,303, `RealtimeHubController.swift` 2,042, `ChatPrompts.swift` 1,464 with ~10 prompt variants of unknown liveness |
| D8 | Bridge client sprawl | `GmailReaderService`, `CalendarReaderService`, `AppleNotesReaderService`, `OnboardingChatView`, `TaskChatState` each construct `AgentBridge(harnessMode:)` and re-implement conventions |

---

## 3. Phase plan

Phases MUST land in order 1 → 2 → 3 → 4 → 5 → 6. Phase 7 (decomposition) rides along continuously. Do not start a phase before the previous phase's Definition of Done is fully met on `main`.

Each phase specifies: **Goal · Design · Deletions · FORBIDDEN moves · Acceptance · Definition of Done.**

---

### Phase 0 — Make the standing gauntlet executable

**Goal:** Before the refactor train starts, turn INV-6 from a prose requirement into a repeatable local test artifact. This phase changes no architecture and adds no product capability.

**Design (prescriptive):**

1. Add a gauntlet runner, either `desktop/macos/scripts/agent-continuity-gauntlet.sh` or an equivalent `omi-ctl` automation suite, that drives a named `omi-*` bundle through:
   - typed turn;
   - PTT turn;
   - typed follow-up that references the PTT turn;
   - background agent spawn;
   - status query about that agent.
2. The runner MUST capture evidence in a timestamped directory: app log excerpt, runtime sqlite path/hash, screenshots or automation snapshots, and the exact user/assistant text for each step.
3. The runner MUST fail non-zero when the typed follow-up cannot see the PTT turn, when the status query cannot see the spawned agent, or when any step silently falls back to a different surface/conversation.
4. After Phase 2 lands, extend the same runner with an owner-switch check: user A typed/PTT context must not appear for user B after sign-out/sign-in.

**FORBIDDEN:**
- Hand-running the gauntlet differently per phase. If manual fallback is needed for a one-off local limitation, record the limitation and add the missing automation hook before merging the phase.
- Treating screenshots alone as evidence. The model-visible request/context trace must be captured where the phase claims continuity improved.

**Definition of Done:** every later phase can invoke one command and get a durable evidence bundle for INV-6.

---

### Phase 1 — One tool manifest, everything else generated

**Goal:** `omi-tool-manifest.ts` (+ `control-tool-manifest.ts`) becomes the *only* place a tool's name, schema, description, prompt snippet, surface availability, and executor binding is declared. Kills defect D1 and the entire "inconsistent tool availability" bug class.

**Design (prescriptive):**

1. Extend `OmiToolManifestEntry` with the fields the Swift representations currently own and the manifest lacks:
   - `surfaces: Array<"desktop_chat" | "realtime_voice" | "onboarding" | "task_chat">` — replaces `DesktopCapabilityRegistry.Surface` sets. (Adapter availability stays as-is; surfaces are orthogonal to adapters.)
   - `voice?: { schemaOverride?: OmiToolInputSchema; speakGuidance?: string }` — only where the realtime schema genuinely differs (audit `RealtimeHubTools.swift`; most don't).
   - `capabilityDoc: { title: string; summary: string; bullets: string[] }` — absorbs `DesktopCapabilityRegistry.Capability` verbatim.
2. Write a codegen script `agent/scripts/generate-tool-surfaces.mjs` that emits, at build time (wired into `run.sh` and the Codemagic build, same slot where other `Desktop/Sources/Generated/` files are produced):
   - `Desktop/Sources/Generated/GeneratedToolCapabilities.swift` — replaces the hand-written arrays in `DesktopCapabilityRegistry.swift`. The registry file keeps only the prompt-assembly functions (`scopedDesktopToolPrompt`, `realtimeSelfModelPrompt`), now reading from generated data.
   - `Desktop/Sources/Generated/GeneratedRealtimeTools.swift` — the OpenAI-realtime-format tool JSON currently hand-written in `RealtimeHubTools.swift:312-695`. `RealtimeHubTools.swift` keeps only execution code and imports generated typed identifiers.
   - `Desktop/Sources/Generated/GeneratedToolExecutors.swift` — typed tool identifiers plus an exhaustiveness table that maps manifest entries with `executor.kind == "swiftTool"` to Swift executor cases. The hand-written executor may contain behavior, but not hand-written tool names.
   - A `tool-manifest.json` snapshot consumed by tests.
3. The generator MUST fail the build (non-zero exit) if: a manifest entry has no executor binding; two entries share a name or alias; a `surfaces` entry references an unknown surface; or the generated output differs from what is checked in (CI runs generator + `git diff --exit-code`, mirroring how other generated code is verified).
4. Executor dispatch: add a static exhaustiveness test asserting every manifest entry with `executor.kind == "swiftTool"` resolves through generated Swift identifiers, and every `nodeTool`/`runtimeControl` entry resolves in the TS registries. Missing = test failure, not a runtime "unknown tool" string.

**Deletions (same PR train):**
- The hand-written capability array in `DesktopCapabilityRegistry.swift` (~330 lines).
- The hand-written tool JSON dictionaries in `RealtimeHubTools.swift`.
- Any duplicate per-tool doc strings discovered in `ChatPrompts.swift` that restate manifest content.

**FORBIDDEN:**
- Serving the manifest to Swift at runtime *for this phase* instead of codegen. (Runtime serving is acceptable as a *later* simplification, but codegen is deterministic, works offline, and keeps Swift compile-time-checked. Do not bikeshed this; codegen is the decision.)
- Keeping the Swift arrays "as fallback if generation fails". Generation failure fails the build.
- "Aligning" the copies by hand instead of generating. If your diff edits tool descriptions in two languages, you are doing it wrong.

**Acceptance:**
- Adding a dummy tool touches exactly one hand-written file (the manifest) + regenerated artifacts; verified by actually doing it in a test.
- `agent-logic-harness.sh` green; continuity gauntlet (INV-6) green; realtime voice can still call `get_tasks`, `search_screen_history`, `spawn_agent` in a named-bundle self-test.

**Definition of Done:** no tool name string literal exists in `Desktop/Sources` outside `Generated/` and the single generated-dispatch consumption point (enforce with a grep-based unit test listing allowed files).

---

### Phase 2 — Session identity collapses into the kernel

**Goal:** Swift never resolves, stores, or transmits session identity again. Kills defect D2 and the primary "agent forgot the last turn" failure class.

**Design (prescriptive):**

1. Add a kernel table `surface_conversations(owner_id, surface_kind, external_ref_kind, external_ref_id, conversation_id, agent_session_id, created_at, last_active_at)` with a UNIQUE key on `(owner_id, surface_kind, external_ref_kind, external_ref_id)`. Migration lives with the other kernel migrations in `sqlite-store.ts`.
2. New kernel API (over the existing runtime protocol): `resolveSurfaceSession({ ownerId, surfaceRef })` → `{ conversationId, agentSessionId }`. The kernel creates-on-first-use, revalidates adapter bindings (using the existing `AdapterBinding` + capability-matrix resume logic), and is the *only* code that decides "same conversation or new one".
3. `AgentBridge.query` signature shrinks: DELETE parameters `sessionKey`, `omiSessionId`, `resume`, `legacyClientScope`. Swift passes `ownerId` (implicit via registered client) + `surfaceRef` + prompt. The kernel does everything else, including warm-session reuse (fold `session-manager.ts`'s prewarmed-map semantics into kernel binding reuse — the warm map keyed by `sessionKey` is deleted, its warmth behavior preserved by keeping bindings open keyed by the kernel session).
4. One-time migration: on first launch, import any `MainChatRuntimeSessionStore` UserDefaults entries into `surface_conversations`, then delete the UserDefaults key unconditionally. The importer itself is deleted two releases later (write the removal into the release checklist now).
5. Sign-out: kernel exposes `clearOwnerState(ownerId)`; Swift's sign-out observer calls it and does nothing else session-related.
6. Sleep/wake: DELETE the "restart bridge on wake to clear stale session" behavior (`ChatProvider.swift:~1197`). Staleness is a kernel/binding concern; the kernel revalidates bindings on `resolveSurfaceSession`. If a wake-specific adapter bug exists, fix it in the adapter, not by nuking all sessions from Swift.

**Deletions (same PR train):**
- `MainChatRuntimeSessionStore.swift` (entire file, minus the temporary importer).
- `AgentRuntimeStatusStore.knownSessionId(for:)` and every session-id fallback in `ChatProvider.swift:4127-4151`. (`AgentRuntimeStatusStore` may survive *only* as a display projection with no identity role.)
- `session-manager.ts` prewarmed map + its tests (behavior folded into kernel).
- `AgentBridge.QueryResult.sessionId` deprecated accessor.
- The onboarding "persist ACP session ID for resume" special case (`ChatProvider.swift:~4356`) — onboarding becomes `surfaceRef = onboarding`, resolved like everything else.

**FORBIDDEN:**
- Keeping any Swift-side session-id cache "to avoid an IPC round trip". `resolveSurfaceSession` may be *combined into the query call itself* (single round trip) — that is the sanctioned optimization.
- Mapping `sessionKey` strings 1:1 into the new table "to preserve behavior". Model the four real surfaces (`main_chat` per chat id, `onboarding`, `task_chat` per task, `floating`) explicitly.
- Adding a second resolver for "special" surfaces. Reader services, onboarding, task chat all go through the same call (see Phase 8 note on `service:*` surfaces).

**Acceptance:**
- Continuity gauntlet passes across: app restart, sign-out/sign-in (different user gets fresh context — extend the gauntlet with this check), system sleep/wake, bridge crash + respawn.
- INV-5 grep test added to CI/tests: forbidden identifiers absent from `Desktop/Sources`.
- The global gauntlet's owner-switch check is active: user A typed/PTT context never appears for user B after sign-out/sign-in.

**Definition of Done:** `AgentBridge.query` has no identity parameters beyond `surfaceRef`; `omi-agentd.sqlite3` is the only place a session id is stored on disk.

---

### Phase 3 — The kernel assembles turn context (one context authority)

**Goal:** Exactly one code path constructs what the model sees for a turn. Kills defect D3 (double-fed history, fragile pre-query IPC chatter, nondeterministic context source).

**Design (prescriptive):**

1. The kernel persists the conversation transcript. Extend the kernel schema with `conversation_turns(conversation_id, turn_id, role, surface_kind, content, created_at, metadata_json)`. On every run the kernel appends the user turn and the final assistant turn. (Runs already flow through the kernel; this is a write in the run lifecycle, not a new pipeline.)
2. New kernel module `agent/src/runtime/turn-context.ts` — the *single* assembler. Given `(conversationId, surfaceRef, userInput, attachmentsMeta)`, it decides and produces, server-side:
   - whether the adapter binding carries native history (then inject **nothing** redundant) or the binding is fresh (then inject a bounded transcript tail from `conversation_turns`);
   - the `DesktopContextPacket` (moves wholesale from `ChatProvider.buildMainChatContextPacketPrompt` into TS, reusing `desktop-context-packet.ts`; the packet's snippets come from `conversation_turns`, not from Swift-shipped message arrays);
   - the coordinator route context and completed-agent delta (moves from `ChatProvider.buildMainChatCoordinatorRouteContextIfNeeded` / `...CompletionDeltaIfNeeded` into the kernel, calling `desktop-intent-router.ts` in-process — the fail-open timeout dance across IPC is deleted because there is no IPC anymore).
3. `AgentBridge.query` from Swift therefore sends: `surfaceRef`, raw user text, attachment metadata, optional image. **No prompt preambles.** Swift-side prompt assembly for turn context is deleted. (System-prompt *identity/persona* content remains Swift-supplied for now; it moves in Phase 7's prompt audit. Context ≠ persona.)
4. One IPC round trip per turn, total. The kernel does route→context→execute internally.

**Deletions (same PR train):**
- `buildMainChatContextPacketPrompt`, `buildMainChatCoordinatorRouteContextIfNeeded`, `buildMainChatCoordinatorCompletionDeltaIfNeeded`, `routeIntentJSONWithFailOpenTimeout`, `sanitizedCoordinatorRouteContext`, `buildConversationHistory` in `ChatProvider.swift` (~350 lines).
- The `bridgePromptContexts` concatenation block (`ChatProvider.swift:4152-4172`).
- Any duplicate "recent messages" shipping from Swift to TS.

**FORBIDDEN:**
- Having the kernel *and* Swift both inject history "during transition". The cutover is atomic per surface; main chat converts first, then task chat/onboarding in the same phase.
- Sending the full Swift message array to the kernel "so it has everything". The kernel reads its own `conversation_turns`. If kernel history is missing something (e.g. pre-migration messages), backfill once at migration, bounded to the last 50 turns per conversation — do not build a live sync.
- Reintroducing per-turn pre-flight IPC calls for "just one" coordinator feature.

**Acceptance:**
- A logged/traced turn (QueryTracer stays, as observation only) shows the model receives recent history exactly once, from exactly one mechanism, in both fresh-binding and warm-binding cases. Add a kernel unit test asserting no duplicate history injection when the binding is native-resumable.
- p50 time-to-first-token for a typed turn does not regress (the removed IPC round trips should improve it; measure with QueryTracer before/after).
- Continuity gauntlet green.

**Definition of Done:** grep of `Desktop/Sources` shows zero call sites that concatenate conversation history into a prompt string.

---

### Phase 4 — One transcript: PTT/realtime joins the conversation

**Goal:** Voice is an I/O device on the same kernel conversation. Kills defect D4 (mirroring, early-bubble reconciliation, dual continuity rings, sanitized seed blobs) — the "bad context between typed chat and PTT chat" footgun dies here.

**Design (prescriptive):**

1. PTT turns write to the kernel like typed turns: when a realtime turn finalizes (final user transcript + final assistant text), the Swift realtime layer calls one new bridge method `recordSurfaceTurn(surfaceRef: mainChat, userText, assistantText, origin: realtime_voice)`; the kernel appends both to `conversation_turns` of the *same conversation* main chat uses. Interrupted turns record with `metadata.interrupted = true` — the kernel keeps the semantics `RealtimeHubController.preserveInterruptedTurnForContinuity` implements today, in one place.
2. Realtime session seeding: when the hub mints/re-mints a session (including barge-in replacement), it requests `getVoiceSeedContext(conversationId)` from the kernel — a single projection function in `turn-context.ts` that owns the cap policy (message count, char budget, sanitization) for voice seeds. One sanitizer, one cap, unit-tested in TS.
3. Swift chat UI renders voice turns because they arrive as kernel conversation events (extend the existing event stream with `turn_recorded` events), not because the hub pushes bubbles into `ChatProvider`. The UI updates from the projection like any other turn.
4. Voice tool calls keep their warm low-latency path (the realtime session's native tool loop is untouched); only *history/continuity* unifies. Do not route realtime audio through the kernel.

**Deletions (same PR train):**
- `ChatProvider.beginVoiceUserMessage`, `recordVoiceTurn`, `persistRecordedTurnMessage`'s voice-specific branches, `buildTopLevelVoiceContinuityContext`.
- `FloatingControlBarManager.beginVoiceUserMessage` / `recordVoiceTurn` shims and `topLevelVoiceContinuityContext` (`FloatingControlBarWindow.swift:3256-3340`).
- `RealtimeHubController`: `earlyUserMessageId` plumbing, `rememberVoiceContinuityTurn`, `replaceVoiceContinuityTurn`, `combinedTopLevelVoiceContinuityContext`, `localVoiceContinuityContext`, `sanitizeContinuityText` (~200 lines of reconciliation machinery).

**FORBIDDEN:**
- Keeping the local voice ring "as a fallback if the kernel is slow". If seed fetch latency matters, the hub pre-fetches the seed when PTT is *armed* (key-down), not by keeping a shadow history.
- Reconciling bubbles by id. There are no early bubbles to reconcile; if the product wants an optimistic user bubble while transcription streams, render it from hub state and let the kernel `turn_recorded` event replace it via the normal projection diff — no cross-object id handshake.
- Writing voice turns to a *different* conversation and merging in the UI.

**Acceptance:**
- Gauntlet step "typed follow-up referencing the PTT turn" works with the typed model demonstrably seeing the voice turn via kernel history (assert via QueryTracer capture).
- Barge-in, interrupted turns, and provider failover still preserve continuity (extend hub tests; the barge-in replacement session must seed from the kernel and include the interrupted turn).
- Voice-turn persistence is idempotent per turn (kernel-side dedupe test replaces today's comment-documented idempotence in `RealtimeHubController.swift:1578`).

**Definition of Done:** `ChatProvider` contains zero voice-specific code paths; the string "continuity" appears in `RealtimeHubController.swift` only in comments describing the kernel seed call.

---

### Phase 5 — One subagent system: pills become projections of kernel runs

**Goal:** A single way to start, observe, and manage background agents. Kills defect D5. This *overrides* the Phase 0 deferral in `docs/agent-coordinator.md` — pill replacement is now in scope.

**Design (prescriptive):**

1. `spawn_agent` is re-implemented as sugar over the kernel: it creates a canonical AgentSession/AgentRun with `surfaceKind = "floating_bar"` and (when called from within a run) a delegation edge to the parent run. There is no separate pill lifecycle object with its own truth.
2. `AgentPillsManager` becomes a pure projection: it renders the set of kernel runs with `surfaceKind = floating_bar` (+ attention overrides) from the coordinator's derived action queue (`desktop-action-queue.ts`), which is already specified as derived-not-authoritative. Pill dismissal writes an attention override / artifact-lifecycle event to the kernel; it never deletes run state.
3. Tool consolidation, in the manifest (Phase 1 makes this a one-file edit):
   - `spawn_agent(objective, provider?, parent_run_id?, visible: bool = true)` — the only way to start background work. `visible: false` covers today's `delegate_agent spawn`.
   - `delegate_agent` is DELETED as a distinct tool; its `call` (synchronous structured child result) mode becomes `run_agent_and_wait(objective, parent_run_id)`; its `continue` mode is already covered by `send_agent_message`.
   - `manage_agent_pills` is DELETED; `list_agent_sessions` / `cancel_agent_run` / `update_agent_artifact_lifecycle` (with a `dismissed` state) cover it. `get_task_agent_status` merges into `list_agent_sessions` output (task-chat agents are kernel sessions with `surfaceKind = task_chat` after Phase 2).
4. ProactiveAssistants TaskAgent: its execution moves onto kernel sessions (`surfaceKind = task_chat`, `externalRefKind = task`) per the Phase 0 decision that was already made but not executed. `TaskChatState` keeps UI state only.
5. Delete the delegation-guidance paragraphs from capability docs (INV-4): with one spawn tool there is nothing to arbitrate.

**FORBIDDEN:**
- Keeping legacy pills operational alongside projected pills "until confidence is high". The cutover is: project kernel runs into the existing pill UI first (pure additive), then flip `spawn_agent` to kernel-backed and delete the legacy pill lifecycle **in the same PR train**.
- Inventing a new "pill" table in the kernel. Runs + attention overrides + the derived action queue are sufficient by design.
- Letting TaskAgent keep a private bridge/loop because "it works".

**Acceptance:**
- Gauntlet steps 4–5 (spawn + status question) work with the model using only the consolidated tools; the status answer must correctly cover chat-spawned, voice-spawned, and task-chat agents in one `list_agent_sessions` call.
- Kill the app mid-run: on relaunch, the pill reflects kernel reconciliation (orphaned/resumable per adapter capability matrix), not a stale Swift cache.

**Definition of Done:** one spawn tool, one list tool, one cancel tool in the manifest; `AgentPillsManager` holds no state that survives its own deallocation; the word "legacy" does not appear in pill-related code.

---

### Phase 6 — Burn the compatibility layer

**Goal:** The runtime speaks exactly one protocol; migration-era vocabulary is gone. Kills defect D6. This phase is deliberately last: phases 2–5 remove the last *consumers* of the legacy fields, so this is pure deletion.

**Actions (all DELETE):**
1. Protocol v1: `protocolVersion` checks and `withQueryCorrelation`'s v1 branch in `index.ts`; make v2 fields mandatory in `protocol.ts` types; the Swift encoder always sends them (it ships in lockstep with the runtime — there are no old clients; state this in the PR description and move on).
2. `legacyAdapterSessionId`, `legacyClientScope` fields end-to-end (Swift protocol layer, TS protocol, kernel columns if any).
3. `legacy-permission-policy.ts` + its test — fold whatever is still load-bearing into `desktop-tool-policy.ts` first; if nothing is load-bearing, delete outright.
4. `JsonlCompatibilityFacade` → rename/refactor to what it now actually is (the JSONL transport server); remove every code path guarded on "old client" behavior.
5. `acp-bridge/` checked-in `dist/index.js` — delete the directory. If `PiMonoWiringTests.swift` references it, update the test to reference the real runtime. If someone believes it is live, they must produce the run-time reference; absence of references was verified 2026-07-04.
6. `agent/src/runtime/control-tool-manifest.js` (stale compiled twin of the `.ts`).
7. `AgentBridge` error-string sniffing (`agentError` lowercased substring matching, `AgentBridge.swift:362-379`) → replace with typed `RuntimeFailure` codes from `failures.ts` end-to-end; the kernel already models failures.
8. All bridge/runtime/user-visible errors crossing from TS to Swift become typed failure envelopes. Swift may localize/display them, but it must not infer behavior from substring matching or collapse distinct runtime failures into generic "AI not available" without preserving the typed code.

**FORBIDDEN:** deprecation warnings instead of deletion; "keep v1 parsing but log". Two-version protocol support is a server-with-independent-clients pattern; this is a bundled subprocess.

**Definition of Done:** `rg -i "legacy|compat|protocolVersion" desktop/macos/agent/src desktop/macos/Desktop/Sources` returns only historical comments and G6-scheduled shims (target: zero other code hits); adapter stderr substring matching is limited to the documented exception in `failures.ts`; the harness and gauntlet are green.

---

### Phase 7 — Continuous decomposition (rides along; never a standalone rewrite)

**Rules, not a schedule:**
- Every phase above MUST extract the code it touches out of the god objects rather than editing in place. Target seams (already visible in MARKs): from `ChatProvider` → `SessionListStore`, `TurnStreamingController` (streaming buffer + stall detection + tool activity), `AttachmentManager`, `MessageSyncService` (cross-platform polling); Phases 2–4 already remove the context/identity/voice thirds of it.
- Hard ceiling once a phase touches a file: it must leave the file **smaller than it found it**. Track in PR descriptions.
- `ChatPrompts.swift` audit (during Phase 3): delete prompt variants with zero call sites (`qaRag`, `simpleMessage`, one of `agenticQA`/`agenticQACompact`, etc. — verify liveness first); persona/system content that survives gets a single documented owner.
- `kernel.ts` (3.3k lines): split by aggregate (`kernel-sessions.ts`, `kernel-runs.ts`, `kernel-artifacts.ts`, `kernel-coordinator.ts`) when Phase 2/3 touch it. Pure file moves + re-exports; no behavior edits in the split commits.
- FORBIDDEN: a dedicated "big refactor" PR that only moves code while other phases are in flight.

---

### Phase 8 — Unified client facade (small, do with Phase 2)

The five ad-hoc `AgentBridge(harnessMode:)` constructions (D8: Gmail/Calendar/AppleNotes readers, onboarding, task chat) are replaced by one Swift entry point:

```swift
AgentClient.run(surface: .service("gmail_reader"), prompt: …, model: …) async throws -> AgentResult
```

— a thin wrapper over the bridge that standardizes error mapping, quota, and token refresh **once**. Reader services get `surfaceRef = service:<name>` (kernel sessions like everything else, giving auditability of what background readers asked models to do — a current blind spot). DELETE the five bespoke constructions. FORBIDDEN: leaving any direct `AgentBridge(...)` construction outside `AgentClient` and `ChatProvider` (enforce by grep test; `ChatProvider`'s own usage collapses into `AgentClient` by end of Phase 3).

---

## 4. Execution mechanics

- **Branching:** one feature branch per phase (`desktop-agent-p<N>-<slug>`), stacked PRs within a phase allowed but the phase merges as a train satisfying INV-2. Nothing lands on `main` without explicit user go-ahead (repo rule).
- **Verification per phase:** `./scripts/agent-logic-harness.sh` → clean release build (`rm -rf .build && xcrun swift build -c release --triple arm64-apple-macosx`) → named-bundle continuity gauntlet (INV-6) with evidence (screenshots/logs) → phase acceptance items.
- **Docs in the same PR:** update `docs/agent-coordinator.md` (it currently encodes the deferrals this plan overrides), `desktop/macos/AGENTS.md` if commands change, and the listen/pusher doc is *not* affected (no backend pipeline changes in this plan).
- **Changelog:** phases 2, 4, 5 have user-visible reliability impact → one `changelog/unreleased/*.json` fragment each ("Improved chat memory across typed and voice conversations", etc.). Phases 1, 3, 6, 7 are internal → no fragment.

## 5. Review checklist (apply to every PR under this plan)

1. Does the PR delete the mechanism it replaces? (INV-2) List of deleted files/symbols present in the description?
2. Did any session/transcript/tool state land outside `omi-agentd.sqlite3` / the manifest? (INV-1)
3. Sources-of-truth count: strictly decreased? (INV-3)
4. Any new prompt text arbitrating between internal mechanisms? (INV-4) → reject.
5. Forbidden identifiers grep clean for the phases already landed? (INV-5)
6. Harness + gauntlet evidence attached? (INV-6)
7. Any new capability smuggled in? (INV-7) → split it out.
8. Any Swift state used as authority instead of ephemeral render projection? (INV-8) → reject.
9. Any backend chat read used to construct agent context? (INV-9) → reject.
10. Every touched god-object file smaller than before? (Phase 7)

## 6. What this plan explicitly does NOT do

- No backend (`backend/`) or mobile changes; kernel/coordinator stay desktop-local per the Phase 0 scope. Cross-device transcript sync is a *future* wave that becomes tractable precisely because Phase 3/4 give it a single export surface — do not start it here.
- No adapter additions/removals (acp, pi-mono, hermes, openclaw stay; `a2a` stays a placeholder).
- No model routing changes, no new tools, no UI redesign of the pill/notch surfaces (Phase 5 changes what pills *are*, not how they look).
