# Track 2 ground truth — PTT language auto-detection & system-audio mute

Mac source read at `desktop/macos/Desktop/Sources/FloatingControlBar/PTTLanguageIdentifier.swift`,
`SystemAudioMuteController.swift`, `RealtimeHubController.swift`, `RealtimeHubTools.swift`,
`PushToTalkManager.swift`, `ShortcutSettings.swift`, `ProactiveAssistants/Services/AssistantSettings.swift`
(all under `.worktrees/mac-ref/`). Windows current state read at
`desktop/windows/src/renderer/src/lib/{ptt/constants.ts,ptt/transport.ts,capture/systemAudio.ts,preferences.ts}`
and `desktop/windows/src/main/bar/keyState.ts` (all under `.worktrees/track2-voice-bar/`).

## TOPIC A — Per-turn spoken-language auto-detection

### Mac algorithm (exact)

File: `PTTLanguageIdentifier.swift`.

1. **Two-stage pipeline**, deliberately isolated from the ambient transcription pipeline (own `AsrManager`, always multilingual v3 — L1-18):
   - Stage 1 — decode: `manager.transcribe(samples, decoderState:, language: nil)` using Apple's on-device **Parakeet v3** multilingual ASR (`AsrModels.downloadAndLoad(version: .v3)`, L44-47), lazily loaded and cached (`loadedManager()`, L39-62), with an explicit `prewarm()` entry point called from the hub warm-up so the first turn doesn't eat model-load latency (L35-37, called at `RealtimeHubController.swift:811,1002`).
   - Stage 2 — classify: `NLLanguageRecognizer` (`dominantLanguage(of:hints:)`, L118-130) runs on the decoded text, biased via `recognizer.languageHints` — each candidate language gets weight `0.3` (L122-125).
2. **Gating** (`identify(pcm16k:candidates:clipSeconds:)`, L71-103):
   - Refuses buffers `< 6,400` int16 samples (`< 0.4s` at 16kHz) — not enough signal for either stage (L78).
   - Strips literal `"<unk>"` tokens the TDT decoder emits for OOV audio before using the text as a chat-bubble fallback (L86-89).
   - Refuses text with no letters (L90-92).
   - `detectLanguage(of:candidates:)` (L108-112) is the **gated** call: returns the dominant language **only if it's IN the candidate set**; anything outside the set returns `nil` ("no match → let the provider decide"). The transcript itself is still returned regardless — it's used as a bubble-fallback even when the language verdict is nil.
   - `dominantLanguage(of:hints:)` (L118-130) is the **ungated** primitive: returns whatever NLLanguageRecognizer thinks is dominant, hints or not, with no candidate-set filtering. Used to classify the *provider's own* transcript (biased so code-switched utterances like "play Despacito" still classify into the user's set — comment at L114-117).
   - Code normalization: NLLanguage codes differ from Omi's settings codes in a couple of spots (`"nb"` (Norwegian Bokmål) vs `"no"`); `normalizedBaseCode`/`nlCode(for:)` map both directions (L132-143).

### Where the verdict is used (three call sites, `RealtimeHubController.swift`)

1. **Early mid-hold hint** (`bufferTurnAudio`, L2218-2241): once ~1.5s of PTT audio has accumulated (`earlyLIDBytes`) AND the user has >1 candidate language (`candidates.count > 1`, L2227 — single-language users skip LID entirely, no ambiguity to resolve), kick a detached `identify()` task. Its result lands in `turnEarlyVerdictCode` on the main actor, keyed by `turnEpoch` so a stale verdict from a superseded turn is dropped (L2236-2240). This runs *while the key is still held*, so it's ready before PTT-up.
2. **Hint the provider at commit** (L1819-1822): at PTT-up, if the realtime provider supports it (`live.supportsInputTranscriptionLanguage`) and there's more than one candidate, `setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)` — i.e. a single candidate is passed directly (no LID needed); multiple candidates pass the early verdict (may be `nil`, meaning "still auto-detect").
3. **Reconcile the transcript after the turn** (`resolveTranscript` L2385-2406, policy in `RealtimeHubTranscriptPolicy.resolve` L268-297): after the provider returns its own transcript, `PTTLanguageIdentifier.dominantLanguage(of: providerText, hints: [])` (ungated, ***no*** candidate bias applied here for the provider's own text) classifies the provider's language. If the provider transcript is empty OR its language is outside the user's candidate set (`providerMismatches`), the code awaits the **full-buffer** decode (`fullLIDTask`, kicked at commit over the whole turn buffer, L2259-2267, with a 20s timeout via `value(of:timeoutMs:)`) and swaps in the LOCAL transcript+language IF the local language matches the candidate set (`localMatchesPreference`). This is the "code-switch handling" / cross-check: the provider's own auto-detect regularly mislabels short utterances (doc comment L7-9, e.g. Russian → Italian), so a mismatching provider transcript is replaced by the local Parakeet+NL verdict when that verdict lands in-language.
4. Also used defensively in **escalation-query language rejection** (`RealtimeHubTools.shouldRejectEscalationQueryForLanguage`, L300-314) — ungated `dominantLanguage(hints: allowed)` on the query text to decide whether to reject a tool call whose query language doesn't match the user's voice languages.

### Candidate-language source

`AssistantSettings.swift` (L138-177):
- `voiceLanguages: [String]` — ordered, primary-first, user-configured languages for the **voice assistant** (distinct key `voiceAssistantLanguages`, distinct from ambient `transcriptionLanguage`/`transcriptionAutoDetect` — deliberately decoupled, own notification `voiceLanguagesDidChange` so it never restarts the ambient pipeline, L153-155). Falls back to `[transcriptionLanguage]` when empty so existing users keep prior behavior (L148).
- `hasExplicitVoiceLanguages: Bool` (L164-168) — true only if the user explicitly set `voiceLanguagesKey` in UserDefaults. **This is the master gate**: system-instruction language pinning, whisper hints, and per-turn LID are ALL gated on this, so default-config users get exactly today's provider auto-detect with no forced-English-only behavior (comment L159-163).
- `voiceBaseLanguages: [String]` (L173-177) — the actual candidate array LID consumes: base ISO-639-1 codes (region stripped, `"en-US"` → `"en"`), deduped, order-preserving, **empty unless `hasExplicitVoiceLanguages`**.
- `baseLanguageCode(_:)` (L179-181): `code.split(separator: "-").first` lowercased.

### Windows-portable recommendation

Windows has **no on-device multilingual ASR** and **no NLLanguageRecognizer**. Building either is out of scope (Parakeet-on-device would need an ONNX/DirectML port; a text-language-ID library is a real but separate dependency, e.g. `franc`/`cld3`-style n-gram detectors — none are currently in `package.json`).

**Pragmatic Windows path — rely on the backend/STT provider's own auto-detect, applied to the returned transcript, replacing the "local decode" stage with "reuse what already came back":**

1. **Candidate-set gate**: add a `voiceLanguages: string[]` (or similarly named) array to `Preferences` (today Windows has only a single `language: string`, `desktop/windows/src/renderer/src/lib/preferences.ts:14`). Keep the same semantics as Mac: empty/unset = feature inert, single entry = pass it straight through (no detection needed), only ≥2 entries triggers any LID logic. This alone ports the *gating* contract even without a decoder.
2. **Text-level detection stage**: since there's no local decode step to run mid-hold, the "early hint" stage (Mac §1 above) has no Windows equivalent unless a lightweight JS n-gram language-ID package is added (e.g. `franc-min`, small and dependency-free, MIT). If added, run it on **interim/partial transcript text** from the stream lane (`transport.ts`'s `onFinal` callbacks already surface segment text — `desktop/windows/src/renderer/src/lib/ptt/transport.ts:73-77`) instead of on decoded PCM, biased toward the candidate set by simply intersecting the detector's top-N guesses with the candidate list (approximates NLLanguageRecognizer's `languageHints` weighting without needing per-language priors).
3. **Reconcile stage** (the part that matters most for the "Russian rendered as Italian" bug class Mac is guarding against): after the batch/stream transcript returns, run the SAME text-level detector against the returned transcript text; if the detected language is outside the candidate set, treat it as a mismatch. Windows currently only has ONE transcript source (the backend `/v2/voice-message/transcribe` response) — there's no cheap second "local" transcript to fall back to the way Mac has (Parakeet decode). Two options:
   - **(a) Simplest, matches Mac's outcome path even without a second transcript source:** if the STT provider itself reports a detected-language field (check whether `/v2/voice-message/transcribe`'s response includes one — worth confirming with a subagent reading `backend/routers/`), prefer that over running local text-ID. Many STT backends (Deepgram, Parakeet) already return language detection; Windows should just plumb it through rather than reinventing.
   - **(b) If no provider-side language field exists:** run the text detector on the returned transcript itself and simply gate the CANDIDATE parameter passed to the *next* call (see step 4) — Windows can't retroactively get a better transcript for the SAME turn without a second STT call, so the mismatch signal only feeds forward, not backward. This is a real (acceptable) behavioral gap versus Mac's true dual-transcript reconciliation; document it as a known deviation rather than silently dropping the mismatch-swap behavior.
4. **Feed forward into the next call**: pass the last-detected/last-preferred language as the `language` param on `batchTranscribeParams()` (`desktop/windows/src/renderer/src/lib/ptt/constants.ts:80-82`) and `listenStart`'s `language` field (`transport.ts:90`) for the NEXT turn, instead of the current static `getPreferences().language` (`constants.ts` comment L1-3 already flags this file as "the single source of truth… mirror the proven macOS tuning" but the language field itself is NOT per-turn detected today). This is the behavioral core worth porting even without decoding audio locally: bias the provider per-turn based on what was actually said last, not a fixed setting.
5. Do **not** attempt to port the mid-hold "early hint" latency optimization (Mac stage 1) unless/until a local detector is added — Windows's stream lane's `onFinal` interim segments already arrive with meaningfully lower latency than Mac's full local decode, so the "hint before commit" motivation is weaker here; the batch lane's real transcript response is the only trustworthy signal.

Summary: **candidate-set gating** (empty = inert, 1 = pass-through, N = detect) and **feed-detected-language-forward-into-next-turn** are the two behavioral contracts worth porting immediately with zero new dependencies (using whatever the transcribe endpoint already returns). Adding a text-only language detector (`franc-min` or similar) is a reasonable follow-up to approximate the "reconcile against candidates" mismatch check, but is a new dependency decision that should be confirmed with the user, not assumed.

## TOPIC B — System-audio mute/duck during PTT capture

### Mac exact contract

File: `SystemAudioMuteController.swift`. `@MainActor final class`, singleton `SystemAudioMuteController.shared`.

**Gating** (`ShortcutSettings.swift`):
- `pttMuteSystemAudio: Bool`, UserDefaults key `"shortcut_pttMuteSystemAudio"`, **default `true`** (L544: `UserDefaults.standard.object(forKey:) as? Bool ?? true`). Exposed as a toggle in Settings → Shortcuts (`ShortcutsSettingsSection.swift:221`).
- Call sites (`PushToTalkManager.swift`) wrap EVERY mute call in `if ShortcutSettings.shared.pttMuteSystemAudio { SystemAudioMuteController.shared.muteForListening() }` — L435-437 (`startListening`, tap-hold PTT begin) and L470-472 (`enterLockedListening`, lock-mode PTT begin). Restore calls are **unconditional** (no settings check) — always safe to call.

**`muteForListening()` gating** (L39-61), idempotent:
1. `guard mutedDevice == nil` — already holding a mute, no-op (safe to call repeatedly).
2. `guard let device = defaultOutputDevice()` — resolve via `kAudioHardwarePropertyDefaultOutputDevice`; bail if none.
3. `guard isDeviceRunningSomewhere(device)` — **"mute only if audio is actually playing"**: reads `kAudioDevicePropertyDeviceIsRunningSomewhere` (any process actively doing I/O on the device); if nothing is playing, do nothing.
4. `guard deviceIsMuted(device) != true` — **"never touch a device the user has muted themselves"**: if the device's mute property already reads muted, leave it alone (don't unmute later either — `mutedDevice` is never set, so `restore()` becomes a no-op for this listen).
5. Preferred path: `setMute(device, muted: true)` via `kAudioDevicePropertyMute` (checks `AudioObjectIsPropertySettable` first, L133-144). On success, records `mutedDevice = device`, `usedVolumeFallback = false`.
6. **Fallback** (device has no settable mute property): `zeroVolume(device)` — reads+zeros the master volume element first (`kAudioObjectPropertyElementMain`), or per-channel [1,2] (stereo) if no master element is settable (L177-189). Saves the prior values into `restoreVolumes`; sets `usedVolumeFallback = true`.

**`restore()`** (L76-87), safe to call even when not muted (no-op if `mutedDevice == nil`):
- If `usedVolumeFallback`: replays each saved `(channel, value)` via `setVolume`.
- Else: `setMute(device, muted: false)`.
- Always clears `mutedDevice`, `restoreVolumes`, `usedVolumeFallback` after, regardless of the underlying call's success.

**Restore call sites** (`PushToTalkManager.swift`):
- L535, `performTerminalCleanup()` — comment: "Always restore audio on teardown (cancel, error, cleanup) so we never leave it muted." Unconditional, no settings check, covers every PTT-end path (cancel, error, cleanup).
- L838, after a tap-to-lock decision resolves as "dictation is over" — comment: "restore any audio we muted so the track resumes immediately."
- `RealtimeHubController.swift:2629`, inside the turn-completion/response path — comment: "If PTT muted music/system output while listening, make sure the model's reply is audible even if capture teardown restore is delayed by hardware." This is a **defensive second restore call** at the point the assistant's spoken reply is about to play, independent of PTT-manager teardown timing — i.e. Mac restores at BOTH (a) PTT lifecycle teardown and (b) right before the reply needs to be audible, because it can't guarantee (a) always lands before hardware-level restore latency would clip the reply.

**Mute timing relative to PTT lifecycle**: mute begins at PTT-DOWN (both hold-start and lock-start), i.e. the instant capture begins — not at some later "confirmed speech" point. Restore happens at PTT-UP / teardown / cancel, AND defensively again right before the assistant's audio reply plays.

**Readiness introspection** (`defaultOutputReadiness()`, L64-73), used only for onboarding UX (`OnboardingVoiceDemoView.swift:234` — "turn up your volume" hint), not part of the mute/restore lifecycle itself:
- Returns `.audible` while WE hold a mute (so the UI doesn't tell the user to turn up volume for a mute WE caused).
- `.muted` if the device's mute property reads true (independent of us).
- `.zeroVolume` if readable volume is `≤ 0.001` on all channels.
- `.unavailable` if no default device or no readable volume property.

### Windows current state confirmed unrelated

`desktop/windows/src/renderer/src/lib/capture/systemAudio.ts` is confirmed **unrelated** — it's loopback CAPTURE (grabs system audio as an input stream via `getDisplayMedia({video:true, audio:true})`, drops the video track) for the meeting-transcription feature, not output muting. No existing Windows code mutes or ducks the default render (output) device. `desktop/windows/src/main` has no COM/WASAPI bindings today — `src/main/bar/keyState.ts` is the only koffi precedent and it's flat `user32.dll` function calls (`GetAsyncKeyState`, `GetSystemMetrics`) with no COM/vtable interface use anywhere in `src/main`.

### Windows WASAPI implementation approach

The direct API-for-API port target is **`IAudioEndpointVolume`** (mute) + **`IAudioMeterInformation`** (playing/level detection) on the default render endpoint, obtained via `IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eConsole)` → `IMMDevice::Activate(IID_IAudioEndpointVolume)`. Concretely:

- **Resolve default output device**: `MMDeviceEnumerator` COM object (CLSID `MMDeviceEnumerator`, IID `IMMDeviceEnumerator`), `GetDefaultAudioEndpoint(eRender=0, eConsole=0)` → `IMMDevice`.
- **Mute** (maps to Mac's `setMute`/`deviceIsMuted`): `IMMDevice::Activate(IID_IAudioEndpointVolume)` → `IAudioEndpointVolume::GetMute(&bool)` / `SetMute(bool, &GUID)`. This is a direct, always-settable analog of `kAudioDevicePropertyMute` — Windows render endpoints reliably expose a settable master mute, so the **fallback volume-zeroing path Mac needs (for devices with no settable mute property) is unlikely to be necessary on Windows**, but `IAudioEndpointVolume::GetMasterVolumeLevelScalar`/`SetMasterVolumeLevelScalar` is the equivalent fallback (mirrors Mac's `zeroVolume`/`restoreVolumes`) if a defensive fallback is still wanted.
- **"Audio actually playing" gate** (maps to Mac's `isDeviceRunningSomewhere`): `IAudioMeterInformation::GetPeakValue` (via `Activate(IID_IAudioMeterInformation)` on the same `IMMDevice`) — a peak > ~0 indicates active output; poll it once at mute-time the same way Mac does a single point-in-time check, not continuous polling. Alternative: `IAudioSessionManager2`/`IAudioSessionEnumerator` to check if any session `GetState()` returns `AudioSessionStateActive`, closer to "is anything actively rendering" semantics; the meter-peak check is simpler and closer to Mac's single-device-level check.
- **"Already muted by the user" gate**: `IAudioEndpointVolume::GetMute` before setting — same as Mac's `deviceIsMuted` check.
- **Restore**: `SetMute(FALSE, &GUID)` — same unconditional-safe, idempotent, always-call-on-teardown contract as Mac's `restore()`.

**koffi feasibility — direct vtable calls are possible but nontrivial and not what the codebase does today.** koffi 3.x can call through COM by treating the interface pointer as `void**`, reading the vtable (also `void**`), and indexing to the right method's function pointer (koffi supports `koffi.pointer`, `koffi.opaque`, and casting an address to a `koffi.proto`), but this requires: manually laying out `IUnknown`/`IAudioEndpointVolume`/`IMMDevice`/`IMMDeviceEnumerator` vtable offsets (fixed per COM interface but must be hand-verified against Windows SDK headers — a transcription error silently corrupts calls), correct `CoInitializeEx`/`CoUninitialize` lifecycle from Node, and correct GUID/struct marshaling (`PROPVARIANT`-style unions for `SetMute`'s event-context GUID param). This is a materially different complexity class from the existing `keyState.ts` precedent (flat exported DLL functions, no interface/vtable indirection, no COM apartment lifecycle).

**Recommendation: reuse the project's existing C# native-helper pattern instead of raw koffi/COM.** The Windows app already builds two small C# helpers via the .NET SDK (`scripts/build-ocr-helper.ps1`, `scripts/build-automation-helper.ps1`, referenced in `AGENTS.md` → Desktop (Windows) tooling / `CLAUDE.local.md`). C#'s `NAudio` (or the built-in `System.Runtime.InteropServices` COM interop, which the CLR handles natively without manual vtable math) makes `IAudioEndpointVolume`/`IAudioMeterInformation` a few lines of idiomatic code instead of hand-rolled vtable offsets. A third helper (`build-audio-mute-helper.ps1`-style) invoked the same way the OCR/automation helpers are (spawned as a short-lived process, or a small persistent stdin/stdout or named-pipe service if latency matters — mute must happen at PTT-down with no perceptible delay, so a **long-lived helper process** avoiding per-call .NET startup cost is preferable to a cold spawn-per-mute) is the pragmatic path. This should be confirmed with whoever owns the C#-helper pattern/build pipeline before implementation, since it's a new build artifact, not a decision this document makes unilaterally.

## TOPIC C — Settings keys and defaults to carry over

| Mac key | Storage | Default | Windows equivalent to add |
|---|---|---|---|
| `ShortcutSettings.pttMuteSystemAudio` | UserDefaults `"shortcut_pttMuteSystemAudio"` | `true` | New boolean in `Preferences` (`desktop/windows/src/renderer/src/lib/preferences.ts`), e.g. `pttMuteSystemAudio?: boolean`, default `true` (read with `?? true` at call sites per the existing `vadGateEnabled?`-style optional-with-fallback pattern already used in that file, L52-57) |
| `AssistantSettings.voiceLanguages` | UserDefaults `"voiceAssistantLanguages"` | `[]` (empty → falls back to `[transcriptionLanguage]`) | New `Preferences.voiceLanguages?: string[]`, default unset/empty. Windows has no separate ambient-transcription-language setting to fall back to yet — fall back to the existing single `language: string` field (`preferences.ts:14`) the same way Mac falls back to `transcriptionLanguage` |
| `AssistantSettings.hasExplicitVoiceLanguages` | derived (non-empty check) | — | Derive the same way: `(preferences.voiceLanguages?.length ?? 0) > 0` — the master gate; do not run any LID/detection logic when false |
| `AssistantSettings.voiceBaseLanguages` | derived | — | Derive the same way: dedupe + strip region suffix (`code.split('-')[0].toLowerCase()`) from `voiceLanguages` |

No other settings keys are load-bearing for these two features on Mac.

## Summary (for the caller)

**Language ID**: Mac runs a two-stage on-device pipeline (Parakeet v3 multilingual ASR decode → NLLanguageRecognizer classification biased toward the user's configured voice languages) to hint the realtime provider mid-hold and reconcile/replace a mislabeled provider transcript at turn-end. Windows has no on-device ASR or NL framework equivalent; the pragmatic path is (1) port the *candidate-set gating contract* exactly (empty=inert, single=pass-through, multi=detect) via a new `voiceLanguages` preference, (2) prefer any language field the STT backend already returns over building a new local detector, (3) feed the detected/preferred language forward into the next turn's `language` param on both the batch (`constants.ts:80`) and stream (`transport.ts:90`) transports instead of the current static `getPreferences().language`, and (4) treat true same-turn transcript reconciliation (Mac's dual-transcript swap) as a documented gap unless a lightweight JS language-ID library is deliberately added — that's a dependency decision for the user, not assumed here.

**System-audio mute**: Mac mutes (or zero-volumes as fallback) the default CoreAudio output device at PTT-down, gated on `pttMuteSystemAudio` (default true), only when audio is actually playing and not already user-muted, and unconditionally restores at PTT teardown/cancel/error AND defensively again right before the assistant's spoken reply plays. The Windows equivalent is `IAudioEndpointVolume`/`IAudioMeterInformation` on the default render endpoint via `IMMDeviceEnumerator`. Direct koffi/vtable COM calls are technically possible but a real complexity jump from the existing flat-DLL-call precedent (`keyState.ts`); reusing the project's existing C#-helper build pattern (OCR/automation helpers) is the recommended implementation path, ideally as a long-lived helper process so mute has no perceptible PTT-down latency — confirm the helper approach with the build-pipeline owner before implementing.

Settings to carry over: `pttMuteSystemAudio` (bool, default `true`) and `voiceLanguages` (string array, default empty/inert), both new `Preferences` fields following the existing optional-field-with-fallback convention in `preferences.ts`.
