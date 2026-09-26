# Mac→Windows Parity Audit — Realtime Voice

> Rewritten 2026-08-22. Scope unchanged from the 2026-08-20 version: depth comparison of the
> RealtimeOmni/RealtimeHub voice stack (speak to Omi, hear Omi back) — provider transport,
> session lifecycle, playback, echo handling, tool-calling, model selection, barge-in. Windows
> baseline checked, this pass: `src/renderer/src/lib/voice/**` (now split across the legacy
> continuous-session files — `voiceController.ts`, `sessionMachine.ts`, `providerSession.ts`,
> `openaiSession.ts`, `geminiSession.ts` — and a parallel `hub/**` + `turn/**` warm-hub
> architecture: `hub/hubController.ts`, `hub/hubSession.ts`, `hub/openaiHubSession.ts`,
> `hub/geminiHubSession.ts`, `turn/voiceHubTurnDriver.ts`, `turn/voiceTurnMachine.ts`,
> `turn/voiceTurnCoordinator.ts`, `turn/voiceOutputCoordinator.ts`, `supervisor/voicePlaneSupervisor.ts`,
> `autoModelSelector.ts`, `systemInstruction.ts`, `aboutUser.ts`, `taskCounts.ts`,
> `ttsChunker.ts`, `audibleOutputArbiter.ts`), `src/main/ipc/voiceTool.ts`, `src/main/ipc/voiceHub.ts`,
> `src/main/audio/systemAudioMute.ts`, `src/renderer/src/components/chat/VoiceHubDriverHost.tsx`,
> `src/renderer/src/components/voice/VoiceSessionSurface.tsx` (now the legacy-design fallback only).

## Changed since the 2026-08-20 audit

**Headline finding: the 2026-08-20 audit missed an entire second voice architecture that had
already shipped weeks earlier.** `git log` shows `lib/voice/hub/**`, `lib/voice/turn/**`,
`autoModelSelector.ts`, `systemInstruction.ts`, `aboutUser.ts`, and the `VoiceHubDriverHost.tsx`
wiring were all added between **2026-07-14 and 2026-07-20** (e.g. `hub/hubController.ts` first
committed `2026-07-15`, `06a6bbc829`; `turn/voiceTurnMachine.ts` first committed `2026-07-14`,
`f9df858602`) — a full four to five weeks before the 2026-08-20 audit was written. The old audit
evaluated only the pre-existing continuous-session stack (`voiceController.ts` /
`sessionMachine.ts` / `geminiSession.ts` / `openaiSession.ts` / `VoiceSessionSurface.tsx`, all
still present and now the **legacy fallback** behind `useLegacyHomeDesign`), and as a result
called "Absent" or "Weaker" on six of the ten items below — every one of which had already been
built, tested, and wired into the default PTT path (`pttHubEnabled: true`,
`desktop/windows/src/renderer/src/lib/preferences.ts:161`) by the time the audit ran. This is a
materially different situation from "not built yet": it is already live for every user.

What actually changed status, and why:

1. **In-session tool-calling** — was "Absent," now **Present** (narrower catalog than Mac).
   `src/main/ipc/voiceTool.ts` + the shared `omiToolManifest` wire ~17 tools into the warm hub
   session via the same in-process host executor typed chat uses.
2. **System-wide PTT-driven warm hub session** — was "Weaker/architecturally different," now
   **Present**. `hub/hubController.ts` implements warm-socket-between-turns, idle-teardown
   survival, a bounded reconnect-strike budget with a circuit breaker, and OS-wake refresh —
   all mechanics the old audit said were missing.
3. **Rich per-session system instructions** — was "Absent," now **Present**.
   `systemInstruction.ts` + `aboutUser.ts` + `taskCounts.ts` build a Mac-structured instruction
   (about-user card, continuity block, tool-routing rules) fed to every hub session.
4. **Voice turns recorded into shared chat history** — was "Absent," now **Present**.
   `useChat.ts`'s `recordVoiceTurn`/`getVoiceSeedContext` (added 2026-07-15/16) write real hub
   turns into the one kernel-backed chat timeline, including interrupted/barged-in turns.
5. **In-turn screen/vision context** — was "Absent," now **Partial**: a text/OCR
   screen-awareness tool (`get_work_context`) is callable, but no pixels or video frames are
   ever fed into the realtime model itself (see detail section below) — this part of the old
   finding still holds, just for a narrower reason.
6. **Automatic model selection ("Auto")** — was "Absent," now **Present**, and matches the
   track2-groundtruth correction exactly: `autoModelSelector.ts` treats `'auto'` as a
   client-only sentinel and the backend pick is always a concrete provider id.
7. **Mid-conversation provider failover** — status label unchanged ("Partial") but the
   mechanism underneath was completely rebuilt: same-provider reconnect now has a real
   strike-budget + circuit breaker (`hub/hubController.ts:208-217,337-345`); what is still
   missing is specifically *cross-provider* failover on a live auth/quota-classified error
   (`hub/hubClose.ts:13-17` says this is deliberately deferred).
8. **Client-direct BYOK realtime** — unchanged, confirmed still **Absent**.
9. **System-output audio ducking** — was "Absent," now **Present**. A native WASAPI helper
   (`src/main/audio/systemAudioMute.ts`) mutes/restores the system output device around each
   PTT hold, gated on `pttMuteSystemAudio` (default on).
10. **TTS filler / agent-ack / playback speed** — was "Partial," still **Partial** but improved:
    filler phrases now exist (`voiceController.ts:84-91`) and a chunked, fast-first-start TTS
    pipeline was added (`ttsChunker.ts`); no deterministic agent-kickoff acknowledgement and no
    exposed playback-speed control were found.

**The single most significant correction**, and the one that directly validates
`track2-execution-plan.md`'s §2 item (f): the old audit assumed Windows' Gemini barge-in gap
needed Mac's full session-replace (`freshSession`) ported. It doesn't, and — per the dates
above — this was never actually built that way even in the new architecture. Reading
`hub/geminiHubSession.ts` shows a `bargeInStrategy: 'freshSession'` field is declared (line 31,
carried over as a label from Mac's vocabulary) but nothing in `hub/hubController.ts`'s
`beginTurn` (line 557) or `GeminiHubSession.onBeginTurn` (line 99) ever tears down and
reconnects the socket on barge-in — it calls `beginTurn` on the *same* warm session with an
`interrupting: true` flag, which does nothing but reset the local `responsePending`
gate (line 100-102) and clear pending tool-call ids. The actual fix that prevents an interrupted
generation's trailing audio from leaking is exactly the small boolean gate
track2-groundtruth's `03-per-provider-bargein.md` said was sufficient (`responsePending`,
declared line 39, checked at lines 175/206/213-215) — not a socket replacement. This landed
2026-07-14 (`c6748d75e1`, "gate trailing Gemini audio after barge-in interrupt (Track 2 A6)"),
so it too predates the 2026-08-20 audit; the ground-truth doc's correction and the shipped code
agree, and the old audit's framing of this as an unbuilt, heavyweight port was wrong on both
counts.

On the other three track2-execution-plan corrections named for this reconciliation pass: no
occurrence of `stt_provider`/`stt_model` response fields, a `503 stt_provider_configuration_error`,
or `effective_desktop_access_tier` was found anywhere under `lib/voice/**`, `hub/**`, `turn/**`,
or the voice IPC handlers (`grep -rn` for all three across those trees returns nothing) —
consistent with the ground-truth docs' claim that none of these exist in the backend at all.
None of the three were referenced in the 2026-08-20 version of this file either, so there is
nothing to correct in *this* document beyond confirming their absence; they are load-bearing for
`06-floating-bar-ask-ptt.md`'s usage-limiter/PTT-transcribe territory, not this one. One adjacent
observation worth flagging for whoever owns that file: no usage-quota check of any kind exists
on the hub voice path today (`grep -rln "usageLimit|fetchChatQuota|ChatUsageQuota"` across
`lib/voice/**` and the voice IPC files returns nothing) — a realtime voice session is never
gated by the chat quota that gates typed/cascade PTT, matching neither an explicit parity
decision nor Mac's `PushToTalkManager.isBlockedByUsageLimit`. Flagging, not scoring, since it
wasn't in scope for this file's original table and is really a `06`/usage-limiter question.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| In-session tool-calling / model-as-router | `RealtimeHubTools.swift`, `RealtimeHubController.swift`, `RealtimeHubSession.swift` | **Present** — narrower catalog (no `ask_higher_model`, `create_calendar_event`, or `point_click`; screen search is `semantic_search`, not `search_screen_history`) | L |
| System-wide PTT-driven warm hub session | `RealtimeHubController.swift` (beginTurn/commitTurn/warm socket) | **Present** — warm socket, idle-teardown survival, strike-budget reconnect + circuit breaker, OS-wake refresh, per-provider barge-in | L |
| Rich per-session system instructions (about-user, chat continuity, calendar, capability self-model) | `RealtimeHubTools.systemInstruction`, `RealtimeHubController.voiceSessionSeedContext` | **Present** — about-user card + real continuity seed + tool-routing rules; no explicit capability self-model block | L |
| Voice turns recorded into shared chat/kernel history (incl. barge-in partial turns) | `RealtimeHubController.recordTurnToKernel*`, `InterruptedTurnPayload` | **Present** — real kernel writes, interrupted turns included | L |
| In-turn screen/vision context | `RealtimeHubController.attachGeminiScreenFrameAfterActivityStartIfNeeded`, `.screenshot` tool, `voiceTurnScreenContextEnvelopeJSON` | **Partial** — text/OCR summary tool callable (`get_work_context`); no pixels/video ever reach the model; no `point_click` | M |
| Automatic model selection ("Auto" provider pick) | `AutoModelSelector.swift` | **Present** — daily backend pick, client-side "auto" sentinel, matches Mac's fallback-to-Gemini behavior | L |
| Mid-conversation provider failover (auth/quota) | `RealtimeHubController.failoverToAlternateProvider`, reconnect-strike budget | **Partial** — real same-provider reconnect + circuit breaker now exists; cross-provider failover on a classified live auth/quota error still not ported | M |
| Client-direct BYOK realtime connection | `RealtimeHubSettings.canConnect`, `HubAuth.byokKey` | **Absent** (unchanged) | M |
| System-output audio ducking while listening | `SystemAudioMuteController.swift` | **Present** — native WASAPI helper mutes/restores system output around each PTT hold | L |
| TTS filler phrases / deterministic agent-ack phrases / playback speed | `FloatingBarVoicePlaybackService.swift` | **Partial** — filler phrases + chunked/fast-start TTS now ship; no agent-kickoff acks, no playback-speed control | L |

## In-session tool-calling / model-as-router

**What it is:** On Mac, the realtime model itself is "the hub" — it doesn't just converse, it
decides what to do by calling tools, replacing a separate Haiku-based router entirely.

**Where (Mac):** `RealtimeHubTools.swift` declares one shared tool surface to both providers.
Tools: `ask_higher_model`, `get_tasks`, `get_memories`, `search_memories`, `search_conversations`,
`get_conversations`, `get_daily_recap`, `get_action_items`, `search_screen_history`,
`create_action_item`, `update_action_item`, `create_calendar_event`, `spawn_agent`, `screenshot`,
`point_click`, `set_desktop_attention_override`, `list_agent_sessions`, `get_agent_run`,
`cancel_agent_run`, `inspect_agent_artifacts`, `update_agent_artifact_lifecycle`.

**Windows status: Present, narrower catalog.** `src/main/ipc/voiceTool.ts`'s
`buildVoiceHubToolCatalog` (line 101) builds the provider-neutral tool list a warm hub session
advertises by walking the shared `omiToolManifest`, keeping only entries that are (a) serviceable
on Windows (`WINDOWS_SERVICEABLE_PRODUCT_TOOLS`, backed by a real Windows executor) and (b)
explicitly tagged `surfaces: ['realtime_voice']` — the same "VT1 gate" that keeps admin tools
(`execute_sql`, `save_knowledge_graph`) off the voice surface on Mac too. `executeVoiceHubTool`
(line 151) dispatches each call through `executeHostTool`, the same in-process executor typed
chat uses, authority resolved host-side from the `main_chat` surface session (never
model/renderer-claimed) — a close structural match to Mac's `hubDidRequestTool` in-process
dispatch. The system prompt (`systemInstruction.ts`) — a direct, line-cited port of
`RealtimeHubTools.systemInstruction`'s routing rules — tells the model to use
`get_action_items`, `get_goals`, `get_memories`/`search_memories`, `get_conversations`/
`search_conversations`, `get_daily_recap`, `semantic_search`/`get_work_context`,
`create_action_item`/`update_action_item`/`complete_task`/`delete_task`, `search_tasks`, and
`spawn_agent` for everything else — all confirmed present with `realtime_voice` in their
manifest entry (`src/main/agentKernel/omiToolManifest.ts`) and a Windows executor.

Three Mac tools are confirmed genuinely absent from the Windows voice surface, not just
unlisted: `ask_higher_model` and `create_calendar_event` are declared in the shared manifest
with `voice.realtimeDescription` fields (`omiToolManifest.ts:1465` area and `:478-500`) but both
have `executor: { kind: 'swiftTool' }` — a macOS-only executor kind that never lands in
Windows' `WINDOWS_SERVICEABLE_PRODUCT_TOOLS` registry, so `buildVoiceHubToolCatalog`'s
serviceability check drops them even though their surface tag says voice-eligible. `point_click`
(act on what the model sees) has no Windows manifest entry at all. `systemInstruction.ts:19-27`
documents this scoping decision explicitly as load-bearing: "Every tool named here MUST be one
that `buildVoiceHubToolCatalog` actually advertises... naming an uncallable tool makes the
model promise work it cannot do."

**Value: L** (down from H). The core capability gap the old audit called the single largest
Windows shortfall is closed; what remains is a handful of named tools, not the tool-loop
architecture itself.

## System-wide PTT-driven warm hub session

**What it is:** How a voice turn starts, stays warm, and reacts to the user talking over Omi.

**Where (Mac):** `RealtimeHubController.swift` (`beginTurn`/`commitTurn`/`cancelTurn`), a
warm-kept WebSocket between turns, idle-close re-warm with a bounded reconnect-strike budget,
wake-from-sleep zombie detection, and provider-specific barge-in (OpenAI in-session
`response.cancel`; Gemini a fresh session since it has no reliable in-session cancel).

**Windows status: Present.** The turn boundary Mac has now exists on Windows too, in a parallel
architecture the bar's PTT hold routes into by default. `preferences.ts:161` sets
`pttHubEnabled: true`; `BarApp.tsx:199` and `usePushToTalk.ts:83-90` gate the hold on that flag
and delegate to `VoiceHubDriverHost` (mounted at the `App.tsx:148` root, not inside any one
page) via `window.omiBar.voiceHubBegin`. `hub/hubController.ts`'s `ensureWarm()` (line 317)
resolves the effective provider, builds the instruction + about-user card, mints a token, and
warms the session — idempotent and eager-callable on bar summon/hover. The warm socket survives
between turns (`voiceTurnDidTerminate` releases only per-turn state); `hub/hubClose.ts`
classifies each close as `expected_idle_teardown`, `policy_fast`, or `transient` (a 1:1 port of
Mac's `RealtimeHubCloseClassifier`, module header lines 1-17), and `hubController.ts`'s
`scheduleReconnectForClose` (line 838) re-warms freely on an idle teardown but spends a strike
(`MAX_RECONNECT_STRIKES = 5`, line 208) on a real failure, opening a 60-second circuit-breaker
cooldown (`CIRCUIT_COOLDOWN_MS = 60_000`, line 217) once the budget is spent — matching Mac's
`maxReconnectStrikes` mechanic, plus a circuit-breaker Mac's own controller doesn't document.
Wake-from-sleep handling is wired end to end: `src/main/index.ts:1305-1306` binds
`powerMonitor.on('resume'/'unlock-screen', refreshHubOnWake)`, which reaches
`VoiceHubDriverHost.tsx:136`'s `onVoiceHubWake` → `driver.requestSessionRefresh('system_wake')`
(`turn/voiceHubTurnDriver.ts:317`) → `hub/hubController.ts:533`'s `requestSessionRefresh`.
Per-provider barge-in is real and matches Mac's split: OpenAI gets in-session
`response.cancel` (`hub/openaiHubSession.ts:127-148`); Gemini gets the `responsePending`
gate described in the callout above.

**Value: L** (down from H). Reach, warm-socket economics, reconnect resilience, and
provider-specific barge-in are all now present; residual differences (see the failover section)
are narrower than the old "architecturally different" framing implied.

## Rich per-session system instructions (context grounding)

**What it is:** What the model actually knows about the user and the moment when a voice turn
starts.

**Where (Mac):** `RealtimeHubController.startSession` builds instructions from
`RealtimeHubTools.systemInstruction`, baking in an About-User card, a recent-conversation
continuity block, floating-agent status, current local datetime/timezone, a capability
self-model (`DesktopCapabilityRegistry.realtimeSelfModelPrompt`), a user-languages line, and
tool-selection/behavioral coaching.

**Windows status: Present**, with one explicit gap. `systemInstruction.ts`'s
`buildVoiceSystemInstruction` (line 244) assembles, in Mac's own order: persona + spawn_agent
directive + user-languages line (`userLanguagesLine`, line 34), the `<about_user>` card, the
continuity block (`continuityBlock`, line 105), current local datetime/timezone
(`currentCalendarContext`, line 87, angle-bracket-escaped against injection), the read-tools
block, the tool-use spoken-heads-up protocol, and the full per-intent routing rules (lines
161-242) — a close, line-cited structural port of `RealtimeHubTools.systemInstruction`.
`aboutUser.ts` builds the `<about_user>` card itself from the user's name, up to 8 memory facts
(`MAX_FACTS`, line 15), and overdue/due-today task counts (`taskCounts.ts`), cached and
refreshed off the hot path exactly like Mac's `AboutUserCard`. The continuity block is fed real
data, not a stub: `VoiceHubDriverHost.tsx` wires `fetchSeed: () => getSeedRef.current()` into
`HubController`, and `useChat.ts:1476`'s `getVoiceSeedContext` calls
`window.omi.voiceHubGetSeedContext`, which `src/main/ipc/voiceHub.ts:103`'s
`readVoiceHubSeedContext` answers from the real kernel-backed conversation (up to 8 turns /
3500 characters, lines 40-41) — this closes what an inline code comment in `systemInstruction.ts`
(lines 8-10) still describes as a "seam only... today it is always empty," which is itself
stale relative to the 2026-07-15/16 wiring commits.

The one piece confirmed still missing is an explicit capability self-model block (Mac's
`DesktopCapabilityRegistry.realtimeSelfModelPrompt` — "what Omi can/can't do on this device");
Windows communicates capability only implicitly, through which tools are advertised and their
descriptions.

**Value: L** (down from H). The personalization gap the old audit flagged is closed; the
capability self-model omission is a narrower, cosmetic gap.

## Voice turns recorded into shared chat/kernel history

**What it is:** Whether a spoken exchange becomes part of the durable, cross-surface chat
record.

**Where (Mac):** `RealtimeHubController.recordTurnToKernel`/`recordTurnToKernelAwaiting` write
each completed turn to the same continuity-invariant write path chat uses; a barged-in,
interrupted turn is captured too via `InterruptedTurnPayload`.

**Windows status: Present.** `useChat.ts:1401`'s `recordVoiceTurn` writes a completed hub turn
into the one chat/kernel timeline the typed path uses (INV-CHAT-1, per the function's own
comments), recording whenever *either* side has text (matching Mac's `hubDidFinishTurn`
unconditional-record semantics, line 1409-1414) and threading an `interrupted` flag so a
barged-in partial reply is still captured rather than dropped (line 1404, `interrupted = false`
parameter; `VoiceHubDriverHost.tsx` threads this through on a barge-in). `src/main/ipc/voiceHub.ts`
records straight to the kernel store — "no second transcript store," per its own header comment
(line 11-12) — which is also what makes the continuity-seed read in the previous section a
readback of the same real data a chat-history browse would show. This shipped 2026-07-15/16
(`eec3bcb193`, `bea6bbbc49`), a month before the 2026-08-20 audit called it absent.

**Value: L** (down from H). The old audit's exact complaint — "a voice conversation is not
retrievable as a conversation afterward" — no longer holds for the default (hub) path.

## In-turn screen/vision context

**What it is:** Whether the voice model can see the screen.

**Where (Mac):** For Gemini, a screen JPEG is sent as an in-turn video frame right after
`activityStart` on every turn; for OpenAI, the `screenshot` tool captures on request and injects
an image message. A hidden `<auto_voice_screen_context>` text block adds a recent-activity
timeline + OCR vocabulary hints to every turn regardless. `point_click` lets the model act on
what it sees.

**Windows status: Partial** — real, but text-only. `get_work_context` is in the manifest with
`surfaces: ['desktop_chat', 'realtime_voice']` (`omiToolManifest.ts:609-618`) and returns
"availability, a screenshot_id for follow-up, OCR preview, and recent timeline without raw image
bytes" — a callable analogue of Mac's hidden screen-context envelope, gated behind a tool call
rather than injected automatically every turn. `capture_screen` also carries the voice surface
tag and can return a saved screenshot file path "after approval," but its own manifest
instructions (`omiToolManifest.ts:516-518,1128-1130`) say to view it "use the Read tool" —
i.e. it is designed for an agentic/code-executor context (spawn_agent's world), not for feeding
pixels back into a realtime audio session's context window; `executeVoiceHubTool` (`voiceTool.ts:151`)
returns a plain string tool result in every case, and neither `hub/geminiHubSession.ts` nor
`hub/openaiHubSession.ts` contains any image/video-frame injection path (confirmed by grep for
`inlineData`/`video`/`injectImage` across both — the one `inlineData` hit is Gemini's own
*inbound* tool-response framing, not an outbound frame). `point_click` has no manifest entry on
Windows at all, matching the tool-calling section above.

**Value: M** (down from H, but not closed). Windows voice can now ask a text-shaped question
about the screen instead of nothing; it still cannot literally see pixels or act on them within
a voice turn the way Mac's Gemini/OpenAI lanes do.

## Automatic model selection ("Auto")

**What it is:** Picking which realtime provider/model to use without the user choosing.

**Where (Mac):** `AutoModelSelector.swift` refreshes a daily pick from
`/v1/auto/model-pick` with a same-day cache, falling back to Gemini only when no pick has ever
been fetched.

**Windows status: Present**, and matches the track2-groundtruth correction precisely.
`autoModelSelector.ts`'s `refresh()` (line 102) calls `GET /v1/auto/model-pick`, typed as
returning one of exactly two concrete ids — `AutoModelProviderId = 'geminiFlashLive' |
'gptRealtime2'` (line 21) — with an explicit comment that "the pick is ALWAYS one of these two
concrete ids, never 'auto'" (line 20). `resolveEffectiveVoiceProvider()` (line 121) is the
`RealtimeOmniSettings.effectiveProvider` port: a concrete `voiceProvider` preference
('openai'/'gemini') bypasses the selector; `'auto'` (the default,
`preferences.ts` `voiceProvider: 'auto'`) resolves via the 24-hour-cached pick
(`REFRESH_INTERVAL_MS`, line 26), falling back to `'geminiFlashLive'` only when no pick has ever
been stored (line 108-113) — a 1:1 behavioral match to Mac. `hub/hubController.ts` calls
`resolveEffectiveVoiceProvider` + `refreshIfStale` on every `ensureWarm()` (lines 37-40).

**Value: L** (down from M). Fully present; no remaining gap found.

## Mid-conversation provider failover on live errors

**What it is:** What happens when the connected provider fails *after* a session is already
live, not just at initial connect.

**Where (Mac):** `RealtimeHubController.hubDidError` classifies the close and, for
`providerAuthFailed`/`providerQuotaExceeded` specifically, calls `failoverToAlternateProvider`
to switch to the other realtime provider and re-warm, with a reconnect-strike budget.

**Windows status: Partial**, but the underlying mechanism is now far more capable than the old
audit's "goes straight to an error state" description, in a different dimension than Mac's gap.
Two failover paths exist. At mint time, `hub/hubController.ts:444`'s `failoverOnMintFailure`
switches to the alternate provider when a mint failure is provider-scoped
(`failure?.tryOtherProvider`), tracking a `fallback_triggered` event with `outcome: 'degraded'`
on the switch and `'exhausted'` if the alternate also fails (lines 449-471) — this closely
mirrors Mac's `failoverToAlternateProvider` but is still gated to the pre-connect mint step, as
the old audit described. Once a session is live, however, `handleError` (line 796) →
`scheduleReconnectForClose` (line 838) now implements a real strike-budget + circuit-breaker
policy that Mac's own controller doesn't even document: a socket that survived past the idle
threshold resets the strike count to 0 and clears any standing failover (line 838-845); a real
failure spends one of `MAX_RECONNECT_STRIKES = 5`, and exhausting the budget opens a 60-second
circuit (`CIRCUIT_COOLDOWN_MS`) during which every PTT press falls through to the batch cascade
instead of retrying the dead socket. What is explicitly and deliberately **not** built is
auth/quota *classification* driving a same-turn switch to the other provider — `hub/hubClose.ts`
lines 13-17 states this is "the dependency for cross-provider failover... which this MINIMAL
slice does not implement," so every non-idle 1008 or other close is treated as `policy_fast`/
`transient` and retried on the *same* provider, never failed over mid-session the way Mac does
for a classified auth/quota close.

**Value: M** (unchanged). Reconnect resilience on a live failure is now substantially better
than before; the specific Mac behavior of switching provider on a live auth/quota error is still
absent.

## Client-direct BYOK realtime connection

**What it is:** Whether a user with their own OpenAI/Gemini API key can connect straight to the
provider, bypassing the backend's managed/ephemeral-token lane.

**Where (Mac):** `RealtimeHubSettings.canConnect` checks a configured BYOK key;
`RealtimeHubController.ensureWarm` prefers it over minting an ephemeral backend token.

**Windows status: Absent, confirmed unchanged.** `tokenMint.ts` unconditionally mints a
backend-issued ephemeral token for every hub or legacy session; the only BYOK-adjacent text in
the entire voice lib is a comment describing the `403 byok mismatch` auth-extractor error code
(`tokenMint.ts:9`), not an implemented client-direct path. This also matches
`track2-execution-plan.md`'s own "Parked" note: BYOK realtime is deferred pending a Windows BYOK
key store that a different track owns; `tokenMint.ts` is explicitly meant to stay
managed-token-only until that lands.

**Value: M** (unchanged).

## System-output audio ducking while listening

**What it is:** Automatically quieting other system audio while the user is talking to Omi.

**Where (Mac):** `SystemAudioMuteController.swift` mutes the default CoreAudio output device
while PTT is listening, restoring the exact prior state when listening ends.

**Windows status: Present.** `src/main/audio/systemAudioMute.ts` is a new WASAPI bridge to a
warm-spawned helper process (`win-audio-helper.exe`), explicitly built because "src/main has no
COM/vtable precedent" (module header, lines 8-9), with fire-and-forget MUTE/RESTORE verbs, a
crash-backoff/re-spawn ladder bounded at `MAX_STRANDED_RECOVERIES = 3` (line 29), and a
hard invariant that "THE USER IS NEVER LEFT MUTED" (line 19) — restore fires on the PTT-end
effects, on helper stdin EOF/exit, and is unconditional regardless of the `pttMuteSystemAudio`
preference (renderer half: `lib/ptt/systemAudioMute.ts`, lines 18-22, "RESTORE is UNCONDITIONAL
— never pref-gated"). The preference defaults on (`pttMuteSystemAudio` undefined ⇒ enabled, per
`preferences.ts` comment lines 103-107 and `systemAudioMute.ts`'s `muteEnabled()`, line 28).
Both the cascade PTT path (`applyPttSystemAudio`) and the warm-hub PTT path
(`muteSystemAudioForHubCapture`, line 68) drive the same mute/restore primitive.

**Value: L** (down from L/M). Fully present; matches Mac's UX intent via a native helper rather
than a COM/CoreAudio-style in-process call, which is a reasonable platform-appropriate deviation.

## TTS filler phrases / deterministic agent-ack phrases / playback speed

**What it is:** Extra polish around the TTS fallback/cascade path.

**Where (Mac):** `FloatingBarVoicePlaybackService.swift` has randomized filler phrases while
waiting on a slow step, a randomized set of deterministic "starting a background agent"
acknowledgement phrases after a successful `spawn_agent` with no native audio, and a
user-configurable `playbackRate`.

**Windows status: Partial, improved.** Filler phrases now exist:
`voiceController.ts:84-91` defines a fixed `FILLER_PHRASES` list ("Let me check.", "One
moment.", …, ported explicitly from `FloatingBarVoicePlaybackService.fillerPhrases` per the
inline comment at line 82) spoken via the system voice while the first TTS chunk is still
synthesizing, covering only multi-chunk replies (lines 644-645) and preempted the instant real
audio is ready (line 654). A `ttsChunker.ts` module was added to split long replies into a small,
fast first chunk (`FIRST_CHUNK = { min: 40, preferred: 120, emergency: 200 }`, line 16) followed
by larger follow chunks, cutting at sentence/clause/whitespace boundaries — a genuine latency
improvement beyond what the old audit described, plus a full output-lane arbitration system
(`turn/voiceOutputCoordinator.ts`, `audibleOutputArbiter.ts`) that manages which of
filler/TTS/system-voice/realtime-audio may speak at once. Two pieces are still confirmed absent:
no deterministic agent-kickoff acknowledgement tied to a successful `spawn_agent` call (`grep`
for "kickoff" across the voice lib returns nothing outside doc comments), and no exposed
playback-speed/rate control (`grep` for `playbackRate`/`voicePlaybackSpeed`/`speechRate` across
the voice lib returns nothing).

**Value: L** (unchanged). Still downstream polish; the fixed (non-randomized) filler set and
the missing kickoff/rate pieces are minor relative to the now-real tool-calling loop they'd be
polishing.

## Spotted outside my scope

- Realtime voice now has **two parallel implementations** live in the tree: the legacy
  continuous-session stack (`voiceController.ts`/`sessionMachine.ts`/`geminiSession.ts`/
  `openaiSession.ts`/`VoiceSessionSurface.tsx`, still mounted from `LegacyHome.tsx` behind the
  `useLegacyHomeDesign` preference) and the warm-hub/turn architecture this document mostly
  describes (mounted system-wide via `VoiceHubDriverHost` at the `App.tsx` root, delegated to
  from the bar's PTT hold). A reader of this file should confirm which surface a given user
  actually sees before assuming hub behavior applies — `useLegacyHomeDesign` defaults to off, so
  the hub is the default, but the legacy path is not dead code.
- No usage-quota gate exists on the realtime-voice/hub path at all (see the callout section
  above) — worth a teammate confirming whether that's an intentional decision or a gap, and if a
  gap, whether it belongs in this file or in `06-floating-bar-ask-ptt.md`'s usage-limiter
  territory (where the actual quota contract — `ChatUsageQuota.allowed`, no
  `effective_desktop_access_tier` — is already ground-truthed).
- Windows' `e2eHook.ts` (`window.__omiVoice`) headless test harness was not re-audited this pass;
  no indication it changed since 2026-08-20.
- Mac's `RealtimeOmniService.swift` (the separate STT/TTS-only "omni" shell used when the hub is
  disabled) still wasn't compared in depth — same caveat as the 2026-08-20 version.
