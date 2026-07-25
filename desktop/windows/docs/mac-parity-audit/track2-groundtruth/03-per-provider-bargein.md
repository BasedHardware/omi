# Ground truth: per-provider barge-in (OpenAI vs Gemini)

Mac source: frozen tag v0.12.72, `desktop/macos/Desktop/Sources/FloatingControlBar/{RealtimeHubController,RealtimeHubSession}.swift` (worktree `mac-ref`).
Windows source: `desktop/windows/src/renderer/src/lib/voice/{openaiSession,geminiSession,tokenMint,sessionMachine,voiceController}.ts` (worktree `track2-voice-bar`).
Backend contract: `desktop/macos/Backend-Rust/src/routes/realtime.rs` (shared Rust backend — serves both Mac and Windows; no platform discrimination).

## 0. Architectural framing — this is not an apples-to-apples port

**Mac is a PTT (push-to-talk), per-turn architecture.** Every user utterance is an explicit `beginTurn()` → `beginInputTurn()` → `commitInputTurn()` cycle driven by a physical PTT press. "Barge-in" on Mac means: *the user pressed PTT again while the previous reply was still generating/playing*. `RealtimeHubController.beginTurn()` (`RealtimeHubController.swift:1936`) explicitly detects this (`responding`, `realtimePlaybackActive`, `voicePlaybackActive`) and branches per provider.

**Windows (track2-voice-bar) is a continuous, always-open realtime session with no PTT/turn boundary at the session-machine layer.** `sessionMachine.ts` (`desktop/windows/.../sessionMachine.ts:15-19`) has exactly four states (`idle`/`connecting`/`live`/`error`) and no turn concept; `voiceController.ts` has no `beginTurn`/`cancelActiveResponse`/turn-identity logic (grep for `interrupt|bargeIn|cancel` in both files returned zero hits outside of unrelated TTS `speechSynthesis.cancel()` calls). Windows currently depends **entirely** on each provider's own server-side VAD to detect and signal an interruption — there is no client-initiated "I am starting a new turn, kill the old one" call on either lane.

This is the single most important gap: Mac's barge-in machinery is a PTT-turn-boundary system; Windows has no equivalent boundary to hang a barge-in decision on yet. The findings below describe what each side does with what it has.

---

## 1. OpenAI barge-in

### Mac (PTT-triggered, in-session cancel)
`RealtimeHubSession.bargeInStrategy` (`RealtimeHubSession.swift:117-119`): `provider == .gemini ? .freshSession : .inSessionCancel` — OpenAI is always `.inSessionCancel`.

On `beginTurn()`, if `providerResponseInFlight` (a reply is still streaming) and strategy is `.inSessionCancel` (`RealtimeHubController.swift:2039-2044`):
```
session?.cancelActiveResponse()
```
which (`RealtimeHubSession.swift:274-302`) sends, over the **same warm socket**:
```json
{"type": "response.cancel"}
```
then clears any uncommitted mic buffer:
```json
{"type": "input_audio_buffer.clear"}
```
and resets local bookkeeping (`openAIResponseActive = false`, clears pending tool-call ids, removes the stale response identity). The comment at `RealtimeHubController.swift:2041-2042`: *"OpenAI exposes an explicit response.cancel path, so the warm socket and conversation context survive while the next input buffer starts clean."* No reconnect, no re-mint, no audio buffering — cheapest possible path.

### Windows (server-VAD only, no explicit cancel)
`openaiSession.ts` never sends `response.cancel` or `input_audio_buffer.clear`. The file header states the design explicitly (`openaiSession.ts:8-9`): *"Barge-in is the provider's server VAD: the mic is NEVER gated locally."* Windows uses `@openai/agents-realtime`'s `RealtimeSession` over WebRTC (`OpenAIRealtimeWebRTC` transport); the SDK's own server-VAD turn-detection issues cancellation internally when it detects user speech over an active response — the app only observes the *result* via `output_audio_buffer.cleared` (mapped to a "speaking end" edge for the echo gate, `openaiSession.ts:30-34`) and `audio_interrupted` (`openaiSession.ts:117`).

### Are they equivalent?
**Functionally similar outcome, structurally different mechanism.** Mac explicitly triggers the cancel in response to a client-observed event (PTT press while `responding`); Windows has no such client-side trigger and relies 100% on OpenAI's own realtime server VAD to both detect the barge-in and cancel server-side — this only works because OpenAI's WebRTC session has continuous server-VAD turn detection enabled, which is the same mechanism the SDK uses regardless. Since Windows never runs a PTT/turn-boundary layer, there is no "was a reply in flight when this new turn started" question for it to answer at the client level — it is not choosing to skip Mac's explicit cancel, it structurally has no turn boundary that would trigger it. **This is very likely fine for OpenAI** because the WebRTC session's built-in server VAD already owns full-duplex barge-in end-to-end (this is standard behavior for the Realtime API in `server_vad`/semantic-VAD turn-detection mode) — Mac's explicit `response.cancel` is largely a *belt-and-suspenders* / PTT-specific optimization (skips waiting for the round-trip VAD detection latency on an explicit user action), not compensating for a broken default.

---

## 2. Gemini barge-in — Mac's session-replace, step by step

### Why no in-session cancel
`RealtimeHubSession.cancelActiveResponse()` for `.gemini` is a no-op (`RealtimeHubSession.swift:296-299`):
```swift
case .gemini:
  // Gemini can't cleanly cancel a streaming reply (it keeps speaking), so the
  // controller interrupts Gemini by reconnecting a fresh socket instead.
  break
```
Gemini Live's manual-VAD protocol requires bracketing every user turn with `activityStart…activityEnd`; you cannot safely open a new `activityStart` while the model is still mid-generation on the old turn without risking the server closing the socket with policy code **1008** (dangling/duplicate activity window — see `RealtimeHubSession.swift:494-498` comment block and `RealtimeHubController.swift:2046-2048`: *"Gemini Live has no reliable in-session cancel for a streaming reply. Reusing that socket can leave the next PTT turn queued behind the old generation…"*). So Mac's workaround is `RealtimeHubBargeInStrategy.freshSession` — throw away the whole socket and open a new one.

### Decision point
`RealtimeHubBargeInAction.decide()` (`RealtimeHubController.swift:354-363`): if `providerResponseInFlight` and `strategy == .freshSession` → `.replaceSession`.

### Step-by-step sequence (`RealtimeHubController.beginTurn`, lines 2016-2124)
1. **Capture interrupted-turn payload** — `captureInterruptedTurnPayloadIfNeeded()` snapshots the partial user/assistant text + an idempotency key for the reply that's about to be killed, *before* any teardown (line 1951).
2. **Stop local playback immediately** — `pcmPlayer?.stop()` (only for a real barge-in) + `FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()` (lines 2016-2019). This happens synchronously, before the socket swap even starts.
3. **`restartSessionForBargeIn(interruptedTurnTask:)`** (line 2049) → `prepareBargeInReplacement()` (`RealtimeHubController.swift:1592-1611`):
   - Captures `provider`, `auth` (BYOK key or ephemeral), `turnID`, `responseID` from the *current* session.
   - **Immediately `session?.detach()` then `session?.stop()`, `session = nil`.** `detach()` (`RealtimeHubSession.swift:229-231`) nils the session's delegate so any subsequent close/error/message event from the doomed old socket can never reach the controller — this is why the `serverContent.interrupted` handling in `RealtimeHubSession.swift:1146-1152` is essentially moot for the PTT-barge-in path: the socket carrying that event has already been detached by the time (if ever) it would fire.
   - Sets `pendingBargeInReplacement = PendingBargeInReplacementTurn(turnID:, responseID:)` — **this is what starts buffering the new turn** (struct at `RealtimeHubController.swift:202-222`, cap `maxBufferedAudioBytes = 3_840_000` = 120s @ 16kHz s16le).
4. **`completeBargeInReplacementAfterContinuity()`** spawns an async task running `RealtimeHubBargeInContinuity.prepareReplacementSession()` (`RealtimeHubController.swift:366-383`):
   - `resolveInterruptedTurn()` awaits step 1's payload.
   - `recordInterruptedTurn()` persists that interrupted turn to the chat kernel (so the interrupted partial reply is saved to history, marked `interrupted: true`) — via `enqueueTurnPersistence`/`persistTurnToKernelThroughTransientFailures`.
   - Loop: `refreshVoiceSeed()` (awaits a turn-persistence fence, then refreshes voice seed context) — retries until it returns true.
   - `startReplacementSession()`: **branches on auth type** (`RealtimeHubController.swift:1650-1655`):
     - `.byokKey` → `startReplacementSessionForBargeIn(provider:auth:)` → directly `startSession(provider:, auth:)` reusing the same static user-supplied key. **No re-mint.**
     - `.ephemeral` → `remintReplacementSessionForBargeIn(provider:)` — **mints a brand-new ephemeral token.**
5. **While the replacement connects, incoming user audio is buffered, not dropped.** `feedAudio`/`sendAudio` paths check `pendingBargeInReplacement != nil` (`RealtimeHubController.swift:2175-2179`, `2269-2271`) and call `pendingBargeInReplacement?.appendAudio(pcm16k)` instead of writing to a (nonexistent) socket. If the user finishes their utterance (PTT release → commit) before the new socket is ready, `pending.pendingCommit = true` is recorded instead of actually sending `activityEnd`.
6. **On session-ready** (`finishBargeInReplacementAfterSessionReady()`, `RealtimeHubController.swift:1775-1804`):
   - Clears `pendingBargeInReplacement`.
   - If `pendingBegin`: calls `live.beginInputTurn(turnID:, responseID:, interrupting: false)` — opens a **fresh** `activityStart` window on the new socket. `interrupting: false` because there's no old generation on *this* socket to reset local Gemini bookkeeping against.
   - **Flushes the buffered audio in order**, via `flushBargeInReplacementAudioBuffer()` → `sendAudio(pcm16k, to: s)` for each chunk (`RealtimeHubController.swift:1861-1866`).
   - If `pendingCommit`: sends `commitInputTurn()` (→ `activityEnd`) now that the socket exists, sets `responding = true`, notifies `VoiceTurnCoordinator`.
7. **Failure path** — `failBargeInReplacement()` (line 1844): if the mint or connect fails (including provider failover attempts via `failoverBargeInReplacement`), clears replacement state, stops local playback, exits voice UI, finishes the turn with reason `.providerFailed`.

### Server-side `interrupted` (secondary/defense-in-depth path)
`RealtimeHubSession.handleGemini()` (`RealtimeHubSession.swift:1145-1152`) still handles a `serverContent.interrupted == true` event by clearing `geminiResponsePending` and pending tool-call ids — but this is for Gemini's *own* automatic interruption of a still-attached, still-current session (not the detached, doomed-socket case above), and critically it gates further reply audio: `emitAudio` only forwards `modelTurn.parts` audio while `geminiResponsePending == true` (`RealtimeHubSession.swift:1177`), and `interrupted` sets that flag `false` immediately. **This is a hard gate on trailing audio for the interrupted generation, not just a one-time local-buffer clear.**

### Token re-mint: **yes, required and implemented, but only for ephemeral (managed) sessions**
Confirmed at `RealtimeHubController.swift:1650-1655` and `1670-1756` (`remintReplacementSessionForBargeIn`): a fresh ephemeral token is minted via `APIClient.shared.mintRealtimeToken(provider:)` — the *same* mint call the initial connect uses, not a special "replace" endpoint. BYOK sessions skip the mint and reuse the static key directly (no re-mint needed since the key isn't single-use/short-lived). The mint is serialized with a `minting` guard, is generation-tagged (`bargeInReplacementGeneration`) so a stale mint response for an already-superseded replacement is discarded/redriven, and on failure attempts provider failover before giving up.

---

## 3. Windows Gemini today — what's present and what's missing

`geminiSession.ts:92-119` (`onmessage` handler), the entire barge-in surface:
```ts
const sc = msg.serverContent
if (sc?.interrupted) {
  // Barge-in: stale audio must never keep playing over the user.
  player?.clear()
}
for (const part of sc?.modelTurn?.parts ?? []) {
  const data = part.inlineData?.data
  if (typeof data === 'string' && data.length > 0) {
    player?.enqueuePcm16(base64ToBytes(data))
  }
}
```
That is the *entire* mechanism. No PTT boundary, no session replace, no audio buffering, no re-mint call site.

**Enumerated gaps vs Mac (in order of how load-bearing they are for correctness):**

1. **No gating of post-interrupt trailing audio (the critical bug).** Mac's `geminiResponsePending` flag (set `false` the instant `interrupted` fires) hard-blocks any further `modelTurn.parts` audio for that generation from reaching the player, *for the life of that turn*. Windows's `player?.clear()` is a **one-time, point-in-time flush of whatever is currently queued** — it does nothing to prevent audio chunks that arrive in *subsequent* `onmessage` calls (same generation, same socket) from being enqueued right back into the player afterward. Mac's own code comments explicitly document that Gemini keeps streaming trailing audio after signaling completion/interruption (`RealtimeHubSession.swift:1153-1156`: *"do NOT finish on generationComplete — Gemini sends it while the spoken audio is still streaming"*), i.e. this is a known, documented Gemini Live quirk, not a hypothetical. Windows has no state variable analogous to `geminiResponsePending` to suppress this.
2. **No session-replace / socket-discard.** Not necessarily wrong in isolation (Windows's continuous server-VAD-driven session doesn't use `activityStart/activityEnd` manual-VAD framing the way Mac's PTT turns do — grep of `geminiSession.ts` shows no `activityStart`/`activityEnd` sends at all, only continuous `sendRealtimeInput({ audio: ... })`), so the specific 1008-close risk Mac is working around (dangling activity window from a second `activityStart` on a busy socket) may not even apply to Windows's continuous mode. This gap may be a non-issue rather than a missing feature — flag for live verification rather than assume it needs porting.
3. **No token re-mint on replace** — moot given #2 doesn't apply; `tokenMint.ts`'s `mintRealtimeToken(provider)` (`tokenMint.ts:86-106`) is a stateless, side-effect-free function taking only `provider` and returning `{provider, token, expiresAt}` — it is trivially reusable to mint a fresh token mid-session if a replace path is ever added; no changes needed to support it.
4. **No interrupted-turn persistence.** Mac explicitly records the killed partial reply to chat history as `interrupted: true` before replacing the session (step 4 above). Not verified whether Windows's chat-persistence layer (outside this file set) has an equivalent; out of scope for this doc but worth a follow-up ground-truth pass if Windows's continuity/persistence path is audited separately.

---

## 4. Backend contract (`/v2/realtime/session`)

`desktop/macos/Backend-Rust/src/routes/realtime.rs` (shared Rust backend, used by both Mac and Windows clients — confirmed no platform discrimination anywhere in the route: auth is `PaywalledAuthUser` extractor only, no `platform` field read from the request).

- `POST /v2/realtime/session` body: `{ "provider": "openai" | "gemini" }` (`MintRequest`, line 44-48).
- 200 response: `{ provider, token, expires_at? }` — OpenAI: `token` = `"ek_…"` (OpenAI's `client_secrets` `value` field, used as Bearer). Gemini: `token` = `"auth_tokens/…"` (Gemini's `auth_tokens.name`, used as `?access_token=` / SDK `apiKey`).
- Error taxonomy (`mint_error_body`, lines 124-149; all responses include `backend_route: "/v2/realtime/session"` and `retryable: bool`):
  - `400 bad_provider` — provider not `"openai"`/`"gemini"`.
  - `503 provider_not_configured` — server-side key missing for that provider (includes `provider` field capitalized, e.g. `"OpenAI"`/`"Gemini"` — note the casing mismatch vs the lowercase `provider` field elsewhere, confirmed in test `missing_key_error_body_includes_provider`).
  - Upstream 4xx/5xx classified into `provider_quota_exceeded` (429/"quota"), `provider_auth_failed` (401/403/"invalid api key"/"permission denied"), `provider_mint_unavailable` (5xx), `provider_mint_rejected` (other 4xx) — `retryable = 429 or 5xx`.
  - `502 provider_mint_transport_error` — network/transport failure calling the upstream provider.
  - 402/403 (`trial_expired`/BYOK mismatch) happen *before* this handler, via the `PaywalledAuthUser` extractor.
- This mint call is exactly what Mac's `remintReplacementSessionForBargeIn` re-invokes for a Gemini session-replace, and exactly what Windows's `tokenMint.mintRealtimeToken()` already wraps — same endpoint, same contract, reusable as-is for either client's replace path.
- Gemini token TTLs (server-enforced, not client-controlled): `newSessionExpireTime` = mint+2min (window to *start* using the token), `expireTime` = mint+30min (session max runtime) — relevant if a Windows fix were to buffer a slow reconnect: the re-minted token must be used to open the new session within 2 minutes of mint.

---

## 5. Reproduction hypothesis for the Gemini stale-audio bug on Windows

**Claim:** After Gemini signals `serverContent.interrupted`, Windows will still play back audio from the interrupted generation if further `modelTurn.parts` audio arrives in a *later* `onmessage` call for the same (now-interrupted) generation, because `player?.clear()` only flushes what's already queued at the moment `interrupted` was seen — it does not gate anything that arrives afterward.

**To trigger it:**
1. Start a Windows Gemini voice session (`startGeminiSession`), get Omi mid-reply with a long enough response that TTS audio is actively streaming/queued in `pcmPlayer` (a multi-sentence answer, e.g. ask it to explain something at length).
2. While Omi is still speaking, start talking (barge-in) — loud/clear enough that Gemini's server VAD detects it and emits `serverContent.interrupted: true`.
3. **Instrument/observe:** log every `onmessage` call after the first `interrupted: true` is seen for that turn — specifically whether any subsequent message for the *same generation* still carries `modelTurn.parts` with `inlineData` audio (`mimeType` audio/pcm), and whether that audio actually reaches `player.enqueuePcm16()`.
4. **Expected buggy behavior:** audible resumption of the old (interrupted) reply — a fragment of stale audio plays over or immediately after the user's new utterance, because `player?.clear()` already ran and the loop below it unconditionally re-enqueues whatever `modelTurn.parts` arrive next, with nothing checking "is this generation still the one I should be playing."
5. **Mac comparison to run on the mini oracle:** reproduce the identical sequence against the Mac reference build and confirm Gemini really does keep sending trailing audio after `interrupted: true` for the same generation (this validates the premise, since Mac's own source comments assert it for `turnComplete`/`generationComplete` but the barge-in `interrupted` case is asserted only by the presence of the `geminiResponsePending` gate, not directly commented). If Mac's `geminiResponsePending` gate can be temporarily bypassed/logged (or observed via `RealtimeHubTestHarness`/debug snapshot hooks already in `RealtimeHubSession.swift` `#if DEBUG`), confirm whether trailing audio actually arrives post-`interrupted`, or whether Mac's freshSession replace makes it moot in practice (old socket is detached before more audio would arrive) — this determines whether the *specific* fix needed on Windows is "add a `geminiResponsePending`-equivalent gate" (cheap, in-place) vs "Windows also needs some form of session/generation invalidation" (bigger).

**Fastest concrete fix to test once confirmed:** add a `currentGenerationInterrupted` (or similar) boolean in `geminiSession.ts`, set `true` on `sc.interrupted`, checked before `player?.enqueuePcm16(...)` in the parts loop, and reset `false` at the start of the next turn (mirrors `geminiResponsePending`'s set-on-commit/clear-on-interrupt/clear-on-turnComplete lifecycle in `RealtimeHubSession.swift:167`). This does not require porting Mac's socket-replace machinery — it directly closes the gap identified in finding #1 above, which is the load-bearing gap; findings #2-3 are lower priority (and #2 may not even apply to Windows's continuous-session architecture).
