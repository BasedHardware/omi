# Mac→Windows Parity Audit — Realtime Voice

> Scope: depth comparison of the RealtimeOmni/RealtimeHub voice stack (speak to Omi, hear
> Omi back) — provider transport, session lifecycle, playback, echo handling, tool-calling,
> model selection, barge-in. Windows baseline checked (has realtime voice, Phase 6):
> `src/renderer/src/lib/voice/*.ts` (voiceController, providerSession, sessionMachine,
> openaiSession, geminiSession, echoGate, tokenMint, tts, injectedTranscript, pcmPlayer,
> playerCore/playerWorklet, usageReport, e2eHook), `src/renderer/src/components/voice/VoiceSessionSurface.tsx`.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| In-session tool-calling / model-as-router | `RealtimeHubTools.swift`, `RealtimeHubController.swift`, `RealtimeHubSession.swift` | **Absent** | H |
| System-wide PTT-driven warm hub session | `RealtimeHubController.swift` (beginTurn/commitTurn/warm socket) | **Weaker** (continuous button-triggered session, no PTT, no warm/idle mgmt) | H |
| Rich per-session system instructions (about-user, chat continuity, calendar, capability self-model) | `RealtimeHubTools.systemInstruction`, `RealtimeHubController.voiceSessionSeedContext` | **Absent** | H |
| Voice turns recorded into shared chat/kernel history (incl. barge-in partial turns) | `RealtimeHubController.recordTurnToKernel*`, `InterruptedTurnPayload` | **Absent** | H |
| In-turn screen/vision context | `RealtimeHubController.attachGeminiScreenFrameAfterActivityStartIfNeeded`, `.screenshot` tool, `voiceTurnScreenContextEnvelopeJSON` | **Absent** | H |
| Automatic model selection ("Auto" provider pick) | `AutoModelSelector.swift` | **Absent** | M |
| Mid-conversation provider failover (auth/quota) | `RealtimeHubController.failoverToAlternateProvider`, reconnect-strike budget | **Partial** (fallback only at initial token mint) | M |
| Client-direct BYOK realtime connection | `RealtimeHubSettings.canConnect`, `HubAuth.byokKey` | **Absent** | M |
| System-output audio ducking while listening | `SystemAudioMuteController.swift` | **Absent** | L/M |
| TTS filler phrases / deterministic agent-ack phrases / playback speed | `FloatingBarVoicePlaybackService.swift` | **Partial** (fallback path exists, but no filler/ack system — moot without tools) | L |

## In-session tool-calling / model-as-router

**What it is:** On Mac, the realtime model itself is "the hub" — it doesn't just converse, it
decides what to do by calling tools, replacing a separate Haiku-based router entirely.

**Where (Mac):** `RealtimeHubTools.swift` declares one shared tool surface to both providers
(`openAITools` for OpenAI Realtime `session.tools`, `geminiFunctionDeclarations` derived from
the same list with OpenAPI-schema conversion for Gemini). Tools: `ask_higher_model`,
`get_tasks`, `get_memories`, `search_memories`, `search_conversations`, `get_conversations`,
`get_daily_recap`, `get_action_items`, `search_screen_history`, `create_action_item`,
`update_action_item`, `create_calendar_event`, `spawn_agent`, `screenshot`, `point_click`,
`set_desktop_attention_override`, `list_agent_sessions`, `get_agent_run`, `cancel_agent_run`,
`inspect_agent_artifacts`, `update_agent_artifact_lifecycle`.

**How it works:** `RealtimeHubController.hubDidRequestTool` (`RealtimeHubController.swift:1661`)
dispatches each tool call against **existing** app code/backend endpoints (no new routes) —
fast local reads (`get_tasks` from `TasksStore`), backend calls (`APIClient.shared.toolGet*`),
the agent control plane (`AgentControlService`), or a full delegation handoff
(`spawn_agent` → `AgentDelegationResolver` → `AgentDelegationExecutor`, which can start a
background agent, continue an existing one, or ask the user for missing detail).
`ask_higher_model` escalates to Claude via the same prompt-cached `/v2/chat/completions` route
chat uses. The system prompt (`RealtimeHubTools.systemInstruction`) is an extensive decision
tree telling the model exactly when to answer directly vs. call which tool vs. delegate, plus
a "never go silent during a tool call — give a varied, specific spoken heads-up" behavioral
rule.

**Windows status: Absent.** `openaiSession.ts` constructs `RealtimeAgent({ name: 'Omi',
instructions: OMI_VOICE_INSTRUCTIONS })` with no `tools` array; `geminiSession.ts`'s
`ai.live.connect` config has no `tools`/`functionDeclarations` field either
(`src/renderer/src/lib/voice/geminiSession.ts:85-90`). `grep` across `src/renderer/src/lib/voice/*.ts`
for `tools|functionDeclaration|function_call` returns nothing. The realtime voice session is a
pure conversational loop — it cannot read tasks, memories, conversations, screen history, or
daily recap, cannot create/update tasks or calendar events, and cannot spawn a background
agent. Any of that requires leaving voice and using text chat instead.

**Value: H.** This is the single largest capability gap — the entire "hub" concept (voice as a
first-class way to operate Omi, not just talk to it) doesn't exist on Windows.

## System-wide PTT-driven warm hub session

**What it is:** How a voice turn starts, stays warm, and reacts to the user talking over Omi.

**Where (Mac):** `RealtimeHubController.swift` (`beginTurn`/`commitTurn`/`cancelTurn`), driven
by a global push-to-talk hotkey from the floating control bar (accessible from anywhere on the
Mac, not tied to one window). The WebSocket is kept **warm between turns** — `ensureWarm()` /
`sendSessionSetup()` — so pressing PTT again doesn't pay a fresh handshake. Idle-close (Gemini
~2.5 min, close 1008) triggers re-warm with a bounded reconnect-strike budget
(`maxReconnectStrikes`); waking from sleep proactively drops a possibly-zombie socket
(`systemDidWake`); a stale conversation seed (new chat context since the session opened)
triggers a reconnect (`reconnectWarmSessionIfSeedStale`). Barge-in strategy is
provider-specific: OpenAI gets an in-session `response.cancel` (keeps context, cheap); Gemini
has no reliable in-session cancel for a streaming reply, so the controller replaces the whole
socket (`RealtimeHubBargeInStrategy.freshSession`) while buffering the new turn's audio/commit
until the replacement connects.

**Windows status: Weaker / architecturally different.** `VoiceSessionSurface.tsx` is mounted
only inside the Home chat page (`src/renderer/src/pages/Home.tsx:457`), not from a global
hotkey or system-wide surface — grep confirms no PTT wiring anywhere in
`src/renderer/src/lib/voice/*.ts`, and Windows' separate PTT hotkey path
(`usePushToTalk.ts`/`AskPanel.tsx`) never calls into `voiceController`. Instead the user clicks
"Start voice chat," which opens a **continuous, always-listening** session (`sessionMachine.ts`
has only `idle → connecting → live → error`, no per-turn states) that stays open until the user
clicks "End" or the surface unmounts (`VoiceSessionSurface.tsx:61` stops the session on
unmount). There is no warm-socket-between-turns concept (there are no discrete turns — one
session is the whole conversation), no idle-reconnect budget, no wake-from-sleep zombie
detection, and no provider-specific barge-in strategy: both lanes rely entirely on the
provider's own server VAD/interruption signal (OpenAI: WebRTC `output_audio_buffer.cleared`;
Gemini: `serverContent.interrupted` clears the local player buffer). This works for barge-in
audio-cutoff, but none of the turn-boundary bookkeeping Mac does (per-turn transcript capture,
idempotency keys, interrupted-turn payloads) exists because there's no turn boundary at all.

**Value: H.** Beyond the missing warm/reconnect mechanics, the bigger gap is reach: Mac's voice
hub is available system-wide via a hotkey; Windows' is a button inside one chat page.

## Rich per-session system instructions (context grounding)

**What it is:** What the model actually knows about the user and the moment when a voice turn
starts.

**Where (Mac):** `RealtimeHubController.startSession` builds instructions from
`RealtimeHubTools.systemInstruction(aboutUser:topLevelConversationContext:userLanguages:)`,
which bakes in: an About-User card (`AboutUserCard.build()`, refreshed off the hot path), a
`<recent_top_level_conversation>` block of the session's recent main-chat + PTT transcript for
continuity (so "that", "the last thing", "continue" resolve correctly), current floating-agent
status, current local datetime/timezone, `DesktopCapabilityRegistry.realtimeSelfModelPrompt`
(what Omi can/can't do on this device), an explicit user-languages line so short utterances
aren't misheard as a third language, and detailed tool-selection/behavioral coaching (vary the
verbal heads-up before a tool call; never speak before a tool returns; when to escalate vs.
delegate vs. answer directly).

**Windows status: Absent.** `providerSession.ts` defines a single constant,
`OMI_VOICE_INSTRUCTIONS`: *"You are Omi, a personal AI companion speaking with the user on
their Windows computer. Be warm, natural, and concise... If the user interrupts you, stop and
listen."* No per-user data, no chat-history continuity, no calendar/time, no capability
self-model, no tool-use coaching (there are no tools to coach). Every session starts from the
same generic prompt regardless of who the user is or what they were just doing.

**Value: H.** Directly limits how "personal" the Windows voice experience can feel, independent
of the tool-calling gap above.

## Voice turns recorded into shared chat/kernel history

**What it is:** Whether a spoken exchange becomes part of the durable, cross-surface chat
record (so it's visible in Main Chat later, and so "what did we just talk about" works).

**Where (Mac):** `RealtimeHubController.recordTurnToKernel`/`recordTurnToKernelAwaiting` write
each completed turn to `FloatingControlBarManager.shared.recordSurfaceTurn(... origin:
"realtime_voice" ...)`, which is the same continuity-invariant (INV-6) write path chat and
notch/floating surfaces use — so a PTT voice exchange shows up in Main Chat history. Even a
**barged-in, interrupted** turn is captured (`InterruptedTurnPayload`, `captureInterruptedTurnPayloadIfNeeded`)
so a half-finished reply the user talked over still leaves a record instead of vanishing.

**Windows status: Absent.** The Windows lane only writes into the **ambient continuous
transcription record** (`injectedTranscript.ts` formats `Omi`-speaker lines injected via
`window.omi?.captureCommand({ type: 'assistant-utterance', ... })`, consumed by the
always-on/continuous-recording store, not by any chat conversation). There is no call anywhere
in `src/renderer/src/lib/voice/*.ts` that appends a voice turn to a chat/message history the
user can browse as a conversation. A realtime voice exchange on Windows leaves no chat-visible
record at all — it only exists (if continuous recording happens to be on) as lines in the
ambient activity transcript.

**Value: H.** User-visible behavioral gap: on Mac you can talk to Omi by voice and later see
(and continue) that exchange in chat; on Windows a voice conversation is not retrievable as a
conversation afterward.

## In-turn screen/vision context

**What it is:** Whether the voice model can see the screen.

**Where (Mac):** For Gemini, `attachGeminiScreenFrameAfterActivityStartIfNeeded` proactively
sends a screen JPEG as an in-turn video frame right after `activityStart` on **every** turn
(Gemini Live only accepts video frames inside the open speech-activity window, so this can't be
deferred to a tool call). For OpenAI, the `screenshot` tool captures on request and
`session.injectImage` adds it as a user message item. Independently, every voice turn also gets
a hidden `<auto_voice_screen_context>` text block
(`voiceTurnScreenContextEnvelopeJSON`/`sendVoiceTurnScreenContextIfNeeded`) with a bounded
recent-activity timeline, OCR-derived vocabulary hints, and screen-recording permission state,
so deictic references ("what's this", "what am I looking at") resolve without an extra
tool round-trip. `point_click` lets the model act on what it sees.

**Windows status: Absent.** Nothing in `openaiSession.ts` or `geminiSession.ts` touches screen
capture, video frames, or `point_click`-style automation — the realtime session is audio-only
in both directions (mic in, PCM/WebRTC audio out). A Windows voice session cannot answer
"what's on my screen" or "click that" at all.

**Value: H.** Combined with the missing tool surface, Windows realtime voice is strictly
audio-conversation-only; Mac's is audio + vision + action.

## Automatic model selection ("Auto")

**What it is:** Picking which realtime provider/model to use without the user choosing.

**Where (Mac):** `AutoModelSelector.swift` refreshes a daily pick from the omi backend
(`/v1/auto/model-pick`, which runs Artificial Analysis quality/speed scoring server-side) with
a `applyServerPick` override hook and a same-day cache; `RealtimeOmniSettings.effectiveProvider`
resolves `.auto` through it, falling back to Gemini (cheapest/fastest) only when no pick has
ever been fetched. This is the default for both `RealtimeOmniSettings` and
`RealtimeHubSettings.provider` (the hub provider follows the same "Voice Model" picker).

**Windows status: Absent.** `startVoiceSession(preferred: VoiceProvider = 'openai')` just
defaults to a hardcoded `'openai'`; the only provider switching is a **one-time, mint-time**
fallback to the other provider when the preferred one's ephemeral-token mint fails
(`voiceController.ts:217-237`, gated on `MintFailure.tryOtherProvider`). There is no
quality/speed benchmark-driven selection, no daily refresh, no backend override, and no
persisted user "Auto" concept.

**Value: M.** Lower priority than the tool/context gaps, but it means Windows can never
benefit from a backend-driven "best model today" pick and always starts on OpenAI.

## Mid-conversation provider failover on live errors

**What it is:** What happens when the connected provider fails *after* a session is already
live (auth revoked, quota exceeded), not just at initial connect.

**Where (Mac):** `RealtimeHubController.hubDidError` classifies the close (via
`CredentialHealthManager.classifyProviderClose`) and, for `providerAuthFailed`/
`providerQuotaExceeded` specifically, calls `failoverToAlternateProvider` to switch to the
other realtime provider and re-warm — with `DesktopDiagnosticsManager.recordFallback`
telemetry (`area: "realtime_hub"`, `outcome: .degraded`/`.recovered`/`.exhausted`) and a
reconnect-strike budget so a genuinely dead credential doesn't loop forever.

**Windows status: Partial.** Provider fallback (`voiceController.ts`) only happens **before**
a session connects, during token minting. Once `startOpenAiSession`/`startGeminiSession`
succeeds and the session later drops (`transport_event 'connection_change' === 'disconnected'`
→ `onFatal`, or Gemini `onclose`/`onerror` → `fail`), the state machine goes straight to
`{ status: 'error' }` with a manual "Try again" button — no automatic switch to the other
provider, no reconnect budget, no distinction between an auth/quota failure and a transient
network blip.

**Value: M.** A live-session failure on Windows always surfaces to the user instead of quietly
recovering on the other lane.

## Client-direct BYOK realtime connection

**What it is:** Whether a user with their own OpenAI/Gemini API key can connect straight to the
provider, bypassing the backend's managed/ephemeral-token lane.

**Where (Mac):** `RealtimeHubSettings.canConnect` checks `APIKeyService.byokKey(...)`;
`RealtimeHubController.ensureWarm` prefers a BYOK key (`HubAuth.byokKey`) over minting an
ephemeral backend token, and only mints (`HubAuth.ephemeral`) for managed/signed-in users
without a configured key.

**Windows status: Absent.** `tokenMint.ts`'s `mintRealtimeToken` unconditionally
`POST`s `/v2/realtime/session` to the desktop backend for every session — there is no
client-direct connection path in `openaiSession.ts`/`geminiSession.ts` that would take a raw
user-supplied API key instead of a backend-minted token. `grep -rn "BYOK|byok"` across the
voice lib only turns up a comment describing a backend error code, not an implemented path.

**Value: M.** Backend-managed-only is simpler and arguably fine as a starting point, but it
means BYOK users get no cost/quota benefit for voice on Windows the way they do on Mac.

## System-output audio ducking while listening

**What it is:** Automatically quieting other system audio (e.g. music) while the user is
talking to Omi, so it doesn't compete with or bleed into the mic.

**Where (Mac):** `SystemAudioMuteController.swift` mutes the default CoreAudio output device
(preferring the device's native mute property, falling back to zeroing volume) only if audio
is actually playing and the user hasn't already muted it themselves, restoring the exact prior
state when PTT listening ends (mirrors Wispr Flow's "mute audio while dictating").

**Windows status: Absent.** Windows' `echoGate.ts` solves a different, narrower problem — it
pauses the app's own always-on **transcription feed** while Omi's voice is audibly playing, so
Omi doesn't transcribe itself. Nothing in the voice lib touches the OS output-device volume or
mute state of unrelated audio (e.g. Spotify) while the user is speaking to Omi.

**Value: L/M.** Nice-to-have UX polish; not a functional blocker, but competing audio can make
the mic input noisier without it.

## TTS filler phrases / deterministic agent-ack phrases / playback speed

**What it is:** Extra polish around the non-realtime TTS fallback path (spoken replies when the
model produced text but no native audio, or for tool-latency filler).

**Where (Mac):** `FloatingBarVoicePlaybackService.swift` has randomized filler phrases spoken
while waiting on a slow step (`fillerPhrases`, played via `playFillerIfEnabled`), a randomized
set of deterministic "starting a background agent" acknowledgement phrases spoken specifically
after a successful `spawn_agent` with no native audio this turn
(`backgroundAgentKickoffPhrases`, `speakBackgroundAgentKickoff`), and a user-configurable
`playbackRate` (`ShortcutSettings.shared.voicePlaybackSpeed`).

**Windows status: Partial.** The core fallback contract exists and is structurally the same as
Mac's: `voiceController.speakText` tries backend TTS (`tts.ts` → `/v1/tts/synthesize`) then
falls back to `playSystemVoice` (Web Speech API/SAPI) on failure, with `fallback_triggered`
telemetry — matching Mac's "OpenAI TTS → system voice" fallback contract. What's missing is the
polish layer: no filler-phrase system (moot today since there are no tools to wait on — see the
tool-calling gap above) and no deterministic agent-kickoff phrases (moot for the same reason),
and no exposed playback-speed control in this module.

**Value: L.** Mostly downstream of the tool-calling gap; revisit once/if Windows gets tools.

## Spotted outside my scope

- Windows' PTT hotkey path (`usePushToTalk.ts`, `AskPanel.tsx`, `capture/PttCaptureHost.ts`) is
  a completely separate STT/dictation feature that never calls into `voiceController` — it
  looks like Windows' analogue of Mac's legacy Deepgram-STT-cascade (pre-hub) voice path, not
  the realtime hub. Worth a teammate confirming whether that's the intended Windows "PTT"
  parity target instead of (or in addition to) `VoiceSessionSurface`.
- Windows has its own headless E2E hook (`e2eHook.ts`, `window.__omiVoice`) comparable in spirit
  to Mac's `RealtimeOmniTestHarness`/`RealtimeHubTestHarness`, but drives turns via typed text
  (`sendUserText`) rather than injected synthetic PCM audio. Test-infra parity, not a
  user-facing feature, so not scored above.
- Mac's `RealtimeOmniService.swift` (the separate STT/TTS-only "omni" shell used when the hub
  itself is disabled) wasn't compared in depth — it's a fallback-of-a-fallback on Mac and has no
  obvious Windows analogue; flagging in case another area's audit touches the legacy cascade.
