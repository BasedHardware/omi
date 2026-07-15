# Ground truth: TTS read-aloud of AI replies + barge-in interrupt

Source: Mac tag `v0.12.72` (worktree `.worktrees/mac-ref`), Windows worktree `.worktrees/track2-voice-bar`, backend `.worktrees/track2-voice-bar/backend`. All line numbers are file-relative at read time.

## 1. Mac TTS streaming model — chunking, filler, fallback

File: `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`

### Chunk-length thresholds (lines 10-20, `nextChunkBoundary` lines 908-955)

```
firstChunkMinimumLength   = 40
firstChunkPreferredLength = 120
firstChunkEmergencyLength = 200

followupChunkMinimumLength   = 320
followupChunkPreferredLength = 520
followupChunkEmergencyLength = 800
```

`nextChunkBoundary(in:isFinal:isFirstChunk:)` logic (only called when `!isFinal`; on `isFinal` it always returns `text.endIndex`, i.e. flush everything):
1. If `text.count < minLength` → no boundary yet (keep buffering).
2. Else take the slice up to `preferredLength`; if it contains `.`/`!`/`?`/`\n`, cut right after the LAST such punctuation in that slice.
3. Else, if `text.count < preferredLength`, wait for more text.
4. Else take the slice up to `emergencyLength`; cut after the last `.!?\n` in it.
5. Else, if `text.count < emergencyLength`, wait for more.
6. Else cut after the last `,;:\n` in the emergency slice.
7. Else cut at the last whitespace in the emergency slice.
8. Else hard-cut at `emergencyLength`.

First chunk is deliberately short (40-200 chars) so playback starts fast; every chunk after that is 320-800 chars ("fewer generated audio clips... far less perceived pausing", comment at lines 14-17).

### Streaming entry point

`updateStreamingResponseIfEnabled(_:isFinal:)` (line 148) is called on every SSE delta from the bar's send flow. It:
- Resets the whole pipeline when `message.id` changes (line 152-157).
- Computes `text = cleanedPlaybackText(from: message)` (whitespace-collapsed message text, or block-derived text for `discoveryCard`/`agentSpawn`/`agentCompletion`; `toolCall`/`thinking` blocks excluded) and bails if `Self.shouldSpeak(text)` is false (blocks generic "Failed to get a response..." and `⚠️`/"warning:" text — lines 848-857).
- On the **first non-empty text** for this response (`!hasStartedRealPlayback && text.count > 0`, line 190): cancels the filler task/audio and calls `tracer?.begin("tts_start")` (line 192) — this is the point real content preempts the filler phrase.
- Appends only the NEW suffix (`text.dropFirst(streamedText.count)`) to `bufferedText`, then calls `drainBufferedText(isFinal:mode:)` which repeatedly calls `nextChunkBoundary` and emits each ready chunk via `enqueueChunk`.

### Filler-phrase-while-first-chunk-synthesizes

`playFillerIfEnabled()` (line 91) is called by `FloatingControlBarWindow` immediately when a query is sent (see §3 below), BEFORE the LLM has produced any text. It picks a random phrase from `fillerPhrases` (line 37-46: "Let me check.", "One moment.", "Looking into it.", "Let me see.", "Checking now.", "Hold on.", "One sec.", "Working on it.") and either:
- `.systemVoice` mode → speaks it immediately via `AVSpeechSynthesizer` (no network round trip).
- `.openAI` mode → synthesizes it via OpenAI TTS (`isFillerSynthesizing = true`); when it resolves, if `hasStartedRealPlayback` is still false (real content hasn't preempted it), it plays the filler through `startPlayback`.

The first real streamed chunk cancels `fillerTask` and stops any playing filler audio (`speechSynthesizer.stopSpeaking(at: .immediate)`, `audioPlayer?.stop()`) at line 193-197, so the filler never overlaps real content — it can only fill the silence before the first chunk arrives.

### OpenAI-TTS → AVSpeechSynthesizer (system voice) fallback

Fallback is triggered from three places, all calling `enqueueSystemSpeech(text)` and logging via `recordSelectedVoiceFallback(to:reason:outcome:)` → `DesktopDiagnosticsManager.shared.recordFallback(...)` (per-repo fallback-telemetry contract):
1. **Chunk synthesis fails** (`startSynthesisIfNeeded`, lines 285-311): `to: "system_voice_fallback"`, `reason: ttsFallbackReason(for: error)` (`"quota"` for HTTP 429, `"auth"`/`"provider_429"`/`"provider_5xx"` from `CredentialHealthError.failureClass`), `outcome: .degraded`.
2. **`AVAudioPlayer` fails to construct/start** (`startPlayback`, lines 512-546): same fallback, `reason: "enqueue_failed"`; `outcome: .degraded` if there's fallback text to speak, `.exhausted` if the fallback text is also empty (line 538-544) — also gated by `forceTTSPlaybackFail`/`forceTTSPlaybackStartFalse` UserDefaults test hooks.
3. **Player finishes unsuccessfully** (`audioPlayerDidFinishPlaying`, line 586-603): `!flag` (i.e. AVAudioPlayer reports failure) with non-empty fallback text → same fallback path, `outcome: .degraded`.

`enqueueSystemSpeech` (line 562) uses `AVSpeechUtterance` with `rate = 0.47`, `pitchMultiplier = 1.02`, `volume = 1.0`, and a preferred-voice search over `["Ava","Allison","Samantha","Karen","Moira"]` (falls back to `AVSpeechSynthesisVoice(language: "en-US")`, lines 740-751).

## 2. Gating — when Mac speaks

File: `desktop/macos/Desktop/Sources/FloatingControlBar/ShortcutSettings.swift`

- `let floatingBarVoiceAnswersEnabled: Bool = true` (line 371) — hardcoded constant, comment: "Push-to-talk replies are always spoken aloud."
- `var hasAnyFloatingBarVoiceAnswersEnabled: Bool { true }` (line 509-511) — ALSO hardcoded true (not derived from the constant above or the typed flag). This is the guard used by `FloatingBarVoicePlaybackService.playFillerIfEnabled()` / `playResponseIfEnabled()` / `updateStreamingResponseIfEnabled()` (lines 92, 144, 149) — so those methods never short-circuit; they always attempt to speak.
- `@Published var floatingBarTypedQuestionVoiceAnswersEnabled: Bool` (line 374, UserDefaults key `shortcut_floatingBarTypedQuestionVoiceAnswersEnabled`, **default `false`**, line 556) — the user-facing settings toggle "speak replies to typed questions too."
- `func shouldSpeakFloatingBarResponse(forVoiceQuery: Bool) -> Bool { forVoiceQuery || floatingBarTypedQuestionVoiceAnswersEnabled }` (line 513-515) — this is the REAL per-query gate. It is read once per query in `FloatingControlBarWindow.swift` (lines 2954 and 4298) as `shouldPlayVoice`, and that captured bool decides whether `playFillerIfEnabled()` / `updateStreamingResponseIfEnabled()` get called for that turn's streaming callback (lines 4301-4306, 4332-4337, 4428-4433). Voice-originated queries (`barWindow.state.currentQueryFromVoice` true, i.e. PTT) always speak; typed queries speak only if the setting is on.
- Voice-only queries (`sendVoiceOnlyQuery`, line 4436) don't even check `shouldSpeakFloatingBarResponse` — they unconditionally call `interruptCurrentResponse()` / `playFillerIfEnabled()` / `updateStreamingResponseIfEnabled(...)` (lines 4461-4463, 4489, 4514, 4516, 4518), since a voice-only turn is always voice-originated.
- Voice speed: `@Published var voicePlaybackSpeed: Float`, UserDefaults key `shortcut_voicePlaybackSpeed`, **default `1.4`** (line 557), steps `[0.8, 1.0, 1.2, 1.4, 1.6, 2.0]` (line 394) with labels Slow/Normal/Fast/Faster/Very Fast/Maximum. Applied as `player.enableRate = true; player.rate = playbackRate` in `startPlayback` (lines 519-520) — playback speed only affects the OpenAI-TTS `AVAudioPlayer` path, not the system-voice fallback (fixed `rate = 0.47` there).
- Voice selection: `@Published var selectedVoiceID`, UserDefaults key `shortcut_selectedVoiceID`, default `openAIShimmerVoiceID` ("openai:shimmer", line 491). Curated list (line 440-489): Onyx (male), Shimmer (female, default), Coral (female), Nova (female) — each an OpenAI voice id + a hand-written `openAIInstructions` tone string, no local-system-voice option in the picker despite `VoiceOption.Provider.localSystem` existing as a case.

## 3. Barge-in — `interruptCurrentResponse()`

Definition: `FloatingBarVoicePlaybackService.swift` lines 485-503.
```swift
@discardableResult
func interruptCurrentResponse(leaseID: VoiceLeaseID? = nil, armNextResponse: Bool = false) -> Bool
```
- If a `leaseID` is passed and doesn't match `activePTTLease?.id`, it's a no-op (stale-lease guard, logs and returns false).
- Marks the current response (if any) as `interruptedResponseID` so any further streaming text for that same message id is swallowed silently (`updateStreamingResponseIfEnabled` lines 161-166: sets `streamedText`/clears `bufferedText`, never re-enqueues audio) — or, if there's no current response yet, arms `shouldInterruptNextResponse` for whatever response comes next.
- Calls `resetPlaybackPipeline(clearMode: false)` (lines 622-659): bumps `playbackGeneration` (invalidates in-flight synthesis/playback closures via the generation check), cancels `playbackTask`/`fillerTask`, clears all queues (`synthesisQueue`, `audioQueue`, `streamedText`, `bufferedText`), stops `audioPlayer` and `speechSynthesizer`, releases the active PTT lease (`VoiceOutputCoordinator.shared.release(lease)`), and sets the floating-pill glow to `false` (`setFloatingPillResponseGlow(false)`).

**Call sites** (every new PTT hold, plus barge-in-adjacent points):
- `PushToTalkManager.swift` line 434 (`startListening()`, i.e. **every** new PTT hold-start) and line 469 (`enterLockedListening()`, double-tap-to-lock entry) — both unconditional, called before the mic capture begins.
- `PushToTalkManager.swift` line 282 (inside `handleVoiceTurnEffect`, `.stopPlayback` effect from the voice-turn state machine) — leased variant, only stops if the lease id matches.
- `FloatingControlBarWindow.swift` lines 4129, 4277 (start of `sendChatQuery`/typed send), 4461 (start of `sendVoiceOnlyQuery`) — every new query interrupts whatever was playing before it, before the filler/streaming path starts.
- `RealtimeHubController.swift` lines 2019, 3558 — realtime-hub turn boundaries also interrupt floating-bar TTS so the two audio sources never overlap.

### Glow / `isVoiceResponseActive`

`FloatingControlBarState.swift`:
- `@Published var isVoiceResponseActive: Bool` (line 282) — didSet clears `isVoiceResponseWaiting` when true, clears `isThinking` when true, and calls `updateVoiceResponseWatchdog()` (a timeout-based auto-clear, not fully read here).
- `var isVoiceResponseGlowActive: Bool { isVoiceResponseActive || isVoiceResponseWaiting }` (line 301-303) — the actual bar-orb glow driver.
- `clearVoiceResponseState()` (line 705-708) sets both `isVoiceResponseWaiting` and `isVoiceResponseActive` false.

The playback service drives this indirectly: `setFloatingPillResponseGlow(_ active:)` (lines 661-668) routes through `VoiceTurnCoordinator.shared.send(.responseActiveChanged(turnID:active:))` when there's an active PTT lease, or `VoiceTurnCoordinator.shared.setUnscopedResponseActive(active)` otherwise; `VoiceTurnCoordinator.swift` line 71 sets `barState.isVoiceResponseActive = true` in response to that effect. So: glow ON is set at the start of every `playFillerIfEnabled`/`updateStreamingResponseIfEnabled`/`speakOneShot`/`speakBackgroundAgentKickoff` call (`setFloatingPillResponseGlow(true)`), and glow OFF happens via `clearFloatingPillResponseGlowIfIdle()` — called whenever a chunk finishes or fails — which only actually clears when `!isSpeaking` (checks `audioPlayer?.isPlaying`, `localSpeechActive`, `speechSynthesizer.isSpeaking`, filler/one-shot/chunk-synthesis in-flight flags, and both queues empty; `isSpeaking` getter lines 81-89).

## 4. Windows current TTS — `speakText`/`playSystemVoice` contract, telemetry, and the bar Ask-AI hook

**Important correction to the audit's premise:** the brief states "Audit says no [path speaks a bar Ask-AI reply]" — that is **stale/wrong** as of this worktree. A full PTT→spoken-reply loop already exists and is wired end-to-end. See below.

### `speakText` (`src/renderer/src/lib/voice/voiceController.ts`, lines 429-464)

```ts
export async function speakText(text: string, voiceId: string = DEFAULT_TTS_VOICE): Promise<void>
```
- Resolves the audio source FIRST: tries `synthesizeTts(text, voiceId)` (backend TTS blob); on failure, records `record('tts-fallback', ...)`, fires `trackEvent('fallback_triggered', { component: 'voice_tts', from: 'openai_tts', to: 'system_voice', reason: 'provider_unavailable', outcome: 'degraded' })` (lines 438-446), and falls back to `playSystemVoice(text)`.
- Injects the text into the capture-side record BEFORE playing (`window.omi?.captureCommand({ type: 'assistant-utterance', utteranceId: 'tts-${ttsSeq++}', text })`, line 449-453) — same echo-gate contract as realtime voice.
- Drives the SAME `EchoGate` used by realtime sessions: `gate.playbackStarted(Date.now()); syncGate()` before playback, `gate.playbackDrained(Date.now()); syncGate()` in a `finally` after `play()` resolves (lines 454-463).
- `MAX_TTS_CHARS = 4096` and 45s axios timeout enforced in `tts.ts` (`synthesizeTts`, lines 9-24) — text is trimmed/sliced to 4096 chars client-side before the POST.

### `playSystemVoice` (voiceController.ts, lines 356-419)

Web Speech API (`SpeechSynthesisUtterance`) with a Chromium-stall workaround: a `resumePump` interval (every 10s) calls `window.speechSynthesis.resume()` to prevent the long-utterance stall bug, plus a hard watchdog timeout (`maxMs = min(120000, max(8000, text.length * 100))`, i.e. ~10 chars/s, floor 8s, cap 120s) that force-cancels and resolves if `onend` never fires. `onerror` treats `'interrupted'`/`'canceled'` as a normal resolve (barge-in), anything else rejects.

### Telemetry field names/values (confirmed via `voiceController.ts` + `tts.ts` + AGENTS.md contract)

- `voice_tts` fallback: `component: 'voice_tts'`, `from: 'openai_tts'`, `to: 'system_voice'`, `reason: 'provider_unavailable'`, `outcome: 'degraded'` (line 439-445) — this is the ONE emission site for TTS-path fallback; matches the repo's shared `fallback_triggered` contract (closed enums for component/from/to/reason/outcome), no ad-hoc counter invented.
- Separate `voice_echo_gate` fallback exists for the watchdog-forced gate release (`component: 'voice_echo_gate'`, `from: 'gated'`, `to: 'released'`, `reason: 'watchdog_max_hold'`, `outcome: 'degraded'`, lines 79-85) — not TTS-specific but shares the gate machinery `speakText` also drives.
- `record(type, detail)` (module-local ring buffer, cap 200) logs `'tts-fallback'`, `'tts-start'`, `'tts-end'` for the live loop-check harness — separate from the PostHog `trackEvent` calls.

### The existing bar Ask-AI → PTT → spoken-reply path (already wired)

Call chain, all in this worktree:
1. `src/renderer/src/components/bar/BarApp.tsx` line 138-146: `usePushToTalk({ onCommit: (text) => sendFromBar(text, true), ... })` — every PTT hold-release commit calls `sendFromBar(text, /* fromVoice */ true)`.
2. `sendFromBar` (`BarApp.tsx` lines 116-121): `window.omiBar.sendChat(text, fromVoice)` → IPC `bar:sendChat` (preload `src/preload/index.ts` line 343-344; main handler `src/main/bar/window.ts` line 892).
3. Main relays it back to the main-window renderer, which `src/renderer/src/components/chat/ChatBridgeHost.tsx` picks up via `window.omi.onBarChatSend(({ text, fromVoice }) => ... sendRef.current(text, { fromVoice }))` (lines 93-97) — `sendRef.current` is the ONE shared `useChat().send`.
4. `src/renderer/src/hooks/useChat.ts` `send(text, { fromVoice })` (line 424): on the success path, after the streamed reply is fully rendered and non-empty, calls `maybeSpeak(assistantText, fromVoice)` (line 651); the plan-executed and plan-error branches also call it (lines 464, 477). `maybeSpeak` (lines 88-100) no-ops unless `fromVoice` is true and text is non-empty, then calls `speakText(text)` fire-and-forget, tracking a `speaking` ref-counted boolean state that `ChatBridgeHost` projects back to the bar as `status: 'speaking'` (`ChatBridgeHost.tsx` line 27) — this is what the bar orb's speaking pose reads.
5. The catch branch (network/stream error, lines 652-663) never calls `maybeSpeak` — matches Mac's "never speak a zombie/error reply" behavior, though Mac does speak certain user-facing error strings via `speakOneShot` in other branches (`FloatingControlBarWindow.swift` lines 4516-4518) that Windows has no equivalent of yet.

**So: PTT bar replies on Windows already speak today**, via `useChat.ts`'s `maybeSpeak`/`speakText`, driven by `fromVoice: true` threaded all the way from the PTT commit. This is Track-1-owned code (`useChat.ts`), already implemented — not a gap to fill.

### The actual gap: typed bar queries never speak, and there is no settings toggle

`src/renderer/src/components/bar/BarApp.tsx` line 377: `onSubmit={(text) => sendFromBar(text, false)}` — the bar's typed-input submit hard-codes `fromVoice: false`. There is no Windows equivalent of Mac's `floatingBarTypedQuestionVoiceAnswersEnabled` setting/toggle anywhere in `src/renderer/src/lib/preferences.ts` (grepped — no `voice`/`tts` keys besides an unrelated VAD-gate comment) or elsewhere in the renderer. A typed bar question can never be spoken on Windows regardless of any setting, whereas Mac lets the user opt in via Settings.

### Where a Track-2 hook COULD live without touching `useChat.ts`

Since `useChat.ts` (Track-1-owned) already does the speaking for `fromVoice` turns, the only remaining Track-2-ownable surface is **deciding what `fromVoice` gets passed as at the call site**, not the speaking logic itself:
- `BarApp.tsx` line 377 (`onSubmit={(text) => sendFromBar(text, false)}`) is the literal line that would need to read a new "speak typed replies" preference and pass it through instead of the hardcoded `false`. `BarApp.tsx` is not `useChat.ts` — it is bar-UI code, plausibly Track-2's to touch (needs confirmation with whoever owns the bar-component boundary, since it's shared with Track 1's `sendFromBar`/PTT wiring).
- Any Mac-parity filler-phrase-while-waiting or barge-in-on-new-PTT-hold behavior (Mac §1/§3 above) is NOT implemented anywhere in `speakText`/`voiceController.ts`/`usePushToTalk.ts` — there is no filler phrase, no chunked/streaming TTS (Windows synthesizes the WHOLE final reply text in one `speakText` call after `isCurrent() && !noReply`, not per-chunk during streaming), and no explicit "new PTT hold barge-in stops in-flight TTS" call — `usePushToTalk.ts` has no `interruptCurrentResponse`-equivalent call; the only interruption path is `teardown()`/`stopCurrentTts` inside `voiceController.ts`, which is invoked by `stopVoiceSession()` (realtime session teardown) and by a new `speakText`/`playSystemVoice` call replacing `stopCurrentTts` at the top of each new play — i.e., calling `speakText` again WILL naturally cut off a prior in-flight TTS (each new `playTtsBlob`/`playSystemVoice` call reassigns `stopCurrentTts` and the old closure is simply orphaned, not explicitly cancelled) but there is no dedicated barge-in entry point analogous to Mac's `interruptCurrentResponse()` called at PTT hold-start. This is a real, verified gap versus Mac's every-hold-start `interruptCurrentResponse()` call sites.

## 5. Backend `/v1/tts/synthesize` contract + platform recognition

**Correction:** the endpoint Windows actually calls is NOT the Python backend's route. `tts.ts`'s `desktopApi` client (`src/renderer/src/lib/apiClient.ts` line 143) targets `VITE_OMI_DESKTOP_API_BASE` (`.env.example` line 13: `https://desktop-backend-hhibjajaja-uc.a.run.app`) — the same Rust "desktop-backend" Cloud Run service macOS's `desktop/macos/Backend-Rust` deploys (confirmed by the shared route path and matching 4096-char/voice-allowlist contract). It is **not** `backend/routers/tts.py`, which is a completely different Python/ElevenLabs route mounted at `/v2/tts/synthesize` (not `/v1/`).

### `/v1/tts/synthesize` (Rust — `desktop/macos/Backend-Rust/src/routes/tts.rs`, shared by macOS and Windows clients)

- **Method:** `POST /v1/tts/synthesize` (route registration line 298).
- **Auth:** `PaywalledAuthUser` extractor (Firebase-authenticated + paywall-checked) — no platform header is read or checked anywhere in this handler.
- **Request body:** `{ text: string, voice_id: string, instructions?: string }` (struct `TtsSynthesizeRequest`, lines 39-45).
- **Validation:** `text` trimmed, must be non-empty; `char_count` (Unicode scalar count) must be `<= 4096` (`MAX_TTS_CHARS`) or 400 "text is too long"; `voice_id` must be one of `alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse, marin, cedar` (`is_allowed_openai_voice`, lines 278-295) or 400 "voice_id is not supported".
- **Key resolution:** BYOK OpenAI key from request headers if active (`byok::get_byok_key_if_active`) — no server-side rate limit applied when BYOK is used; otherwise falls back to the server's `state.config.openai_api_key` (503 "OpenAI TTS is not configured" if unset) and THEN applies server-key rate limiting.
- **Server-key rate limits** (`check_server_tts_rate_limit`, lines 240-276): Redis-backed, `SERVER_TTS_BURST_PER_MINUTE = 20` per 60s window, `SERVER_TTS_DAILY_CHARS = 50_000`/day; 429 on either breach; if Redis is unconfigured, **fails closed** (503 "TTS rate limiting is unavailable") — unlike the Python backend's `/v2/tts/synthesize`, which fails OPEN on Redis errors (`status == -1`, comment "TTS is best-effort").
- **Upstream call:** OpenAI `POST https://api.openai.com/v1/audio/speech`, `model: "gpt-4o-mini-tts"`, `response_format: "mp3"`, bearer-authed with the resolved key. Retries transient statuses (`408, 425, 429, 500, 502, 503, 504, 529`) up to 3 attempts total with `300ms * attempt` backoff (lines 27-34, 152-190); non-transient upstream errors (e.g. 401/400) return immediately as `TtsProxyError::Upstream(status, body)` (body truncated to 500 chars).
- **Response:** whole-blob, NOT streamed — `Body::from(bytes)` after `upstream.bytes().await` fully buffers the OpenAI response (line 196-217), `content-type: audio/mpeg`, status 200.
- **Error shapes:** JSON `{ "error": "<message>" }` with the corresponding HTTP status — 400 (bad request: empty/too-long text, unsupported voice), 503 (`MissingApiKey` or `RateLimitUnavailable`), 429 (`RateLimited`, message either "TTS burst rate limit exceeded" or "TTS daily character limit exceeded"), upstream status passthrough with `"OpenAI TTS request failed: {body}"` message, or 502 (`BadGateway`, network/transport failure to OpenAI).
- **Platform recognition:** none. The handler has zero references to `X-App-Platform`, platform enums, or any Windows/macOS branching — it is fully platform-agnostic (confirmed by grep across `Backend-Rust/src` — the only platform-string references anywhere in that crate are in `routes/updates.rs`, which hardcodes `"macos"` for the Sparkle appcast feed and is unrelated to TTS). Windows and macOS clients hit the identical endpoint/contract with no server-side platform differentiation, so there is no "windows not recognized" risk on this specific route — unlike the general platform-catalog bug documented separately in `platform-variant-divergence-rule` (memory), this endpoint doesn't branch on platform at all.

The Python backend's `/v2/tts/synthesize` (`backend/routers/tts.py`) is a distinct, unrelated route (ElevenLabs-backed, `model_id`/`output_format`/`voice_settings` request shape, streaming `StreamingResponse`, 5000-char cap, different rate limits) that neither client currently calls for this feature — noted only to avoid confusion with the brief's assumption that the Python backend hosts `/v1/tts/synthesize`.
