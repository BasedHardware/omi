# Track 2 (Voice & PTT depth) — Windows codebase inventory + schema ground-truth

Root: `C:\Users\chris\projects\omi\.worktrees\track2-voice-bar\desktop\windows\`
All paths below are relative to that root unless stated otherwise.

## 1. Owned areas — file-by-file map

### `src/renderer/src/lib/voice/**` (realtime voice session)

| File | Responsibility | Key exports |
|---|---|---|
| `voiceController.ts` | Top-level singleton orchestrating a realtime voice session: start/stop, provider fallback (openai↔gemini), echo-gate driver, mute, output-device routing, TTS fallback path. Owns `trackEvent('fallback_triggered', …)` call sites (lines ~79, ~227, ~439). | `getVoiceState`, `subscribeVoiceState`, `getVoiceEvents`, `startVoiceSession`, `stopVoiceSession`, `setVoiceMuted`, `sendVoiceText`, `setVoiceOutputDevice`, `getVoiceOutputDevice`, `playSystemVoice`, `speakText`, type `VoiceEventRecord` |
| `sessionMachine.ts` | Pure state machine for voice session status (idle/connecting/live/error). | `VoiceProvider`, `VoiceSessionState`, `VoiceSessionEvent`, `initialVoiceState`, `transition` |
| `providerSession.ts` | Shared callback/handle contract both provider sessions implement. | `OMI_VOICE_INSTRUCTIONS`, `ProviderSessionCallbacks`, `ProviderSessionHandle` |
| `openaiSession.ts` | OpenAI Realtime session driver (WebRTC/WS transport events → session updates). | `speakingEdgeForTransportEvent`, `completedAssistantText`, `startOpenAiSession` |
| `geminiSession.ts` | Gemini Live session driver. | `startGeminiSession` |
| `tokenMint.ts` | Mints ephemeral realtime tokens per provider; classifies mint failures (including whether to try the other provider). | `OPENAI_REALTIME_MODEL`, `GEMINI_LIVE_MODEL`, `MintedToken`, `MintFailure`, `classifyMintFailure`, `MintError`, `mintRealtimeToken` |
| `echoGate.ts` | Pure gate deciding when the mic should be paused because Omi's own voice is audible (headset vs speaker classification, hold/release timing, watchdog). | `GATE_RELEASE_MS`, `GATE_MAX_HOLD_MS`, `OutputDeviceKind`, `classifyOutputDevice`, `isHeadsetOutput`, `EchoGate` (class) |
| `injectedTranscript.ts` | Formats Omi's own spoken output as a synthetic transcript line injected into the live conversation (not re-transcribed). | `ASSISTANT_SPEAKER`, `INJECTED_LINE_ID_PREFIX`, `isInjectedLineId`, `shouldInjectIntoLive`, `formatAssistantLine` |
| `tts.ts` | Text-to-speech synthesis call (batch, non-realtime TTS). | `DEFAULT_TTS_VOICE`, `MAX_TTS_CHARS`, `synthesizeTts` |
| `pcmPlayer.ts` | Web Audio playback pipeline (AudioWorklet-backed) for streamed PCM from the realtime session. | `GEMINI_OUTPUT_RATE`, `JITTER_CUSHION_MS`, `VoicePlayer` type, `createVoicePlayer`, `int16ToBase64`, `base64ToBytes` |
| `playerCore.ts` | Pure ring-buffer / pull logic behind `pcmPlayer` (jitter buffering, underrun handling) — unit-testable without Web Audio. | `PullResult`, `PlayerCore` (class), `pcm16BytesToFloat32` |
| `playerWorklet.ts` | The actual `AudioWorkletProcessor` (runs off-thread in the audio rendering thread); no top-level exports consumable from Node (registered via `registerProcessor`). | n/a (worklet registration side-effect module) |
| `usageReport.ts` | Maps provider-specific usage payloads to a normalized shape, diffs, and reports realtime session usage to the backend. | `RealtimeUsageBody`, `mapOpenAiUsage`, `mapGeminiUsage`, `usageDelta`, `usageTotal`, `reportRealtimeUsage` |
| `e2eHook.ts` | Attaches `window.__omiVoice` test hook, only under `OMI_E2E=1`. | `attachVoiceE2eHook` |
| Tests | `echoGate.test.ts`, `injectedTranscript.test.ts`, `openaiSession.test.ts`, `playerCore.test.ts`, `sessionMachine.test.ts`, `tokenMint.test.ts`, `usageReport.test.ts`, `voiceController.test.ts` — co-located, one per module above. | |

### `src/renderer/src/lib/ptt/**` (push-to-talk)

| File | Responsibility | Key exports |
|---|---|---|
| `machine.ts` | Pure PTT state machine (idle/holding/draining/streamFinalize/batching) + effect list; the hook (`usePushToTalk`) only drives timers/transports around this. | `PttPhase`, `PttState`, `PttEvent`, `PttEffect`, `initialState`, `assembleTranscript`, `reduce` |
| `capture.ts` | Mic capture lifecycle for a PTT hold: warm (pre-arm), start, release. | `PttCapture`, `PttCaptureOptions`, `warmPttMic`, `releasePttMic`, `startPttCapture` |
| `transport.ts` | Network transports: live stream transcription socket + batch-transcribe fallback POST; prefetches auth token. | `prefetchAuthToken`, `PttStreamCallbacks`, `PttStream`, `startPttStream`, `batchTranscribe`, `batchErrorMessage` |
| `gate.ts` | Pure audio-stats + voiced/silence gate decision (RMS threshold based). | `AudioStats`, `voicedStats`, `GateDecision`, `gateDecision` |
| `constants.ts` | All PTT timing/threshold constants (hold threshold, drain, watchdog, batch endpoint path, etc.). | `HOLD_THRESHOLD_MS`, `DRAIN_MS`, `MIN_TOTAL_AUDIO_SEC`, `MIN_VOICED_SEC`, `VOICED_RMS_THRESHOLD`, `VOICED_FRAME_SAMPLES`, `MAX_BUFFER_BYTES`, `STREAM_FINALIZE_DEADLINE_MS`, `BATCH_TIMEOUT_MS`, `HINT_MS`, `TOO_LONG_HINT_MS`, `ERROR_STRIP_MS`, `WATCHDOG_MS`, `MIC_IDLE_RELEASE_MS`, `MIC_TAP_RELEASE_MS`, `BATCH_TRANSCRIBE_PATH`, `batchTranscribeParams`, `RECORDING_TOO_LONG_MESSAGE`, `DEAD_MIC_PEAK` |
| Tests | `captureClient.test.ts`, `gate.test.ts`, `machine.test.ts`, `transport.test.ts` | |

### `src/main/bar/**` (top-edge bar window, main process)

| File | Responsibility | Key exports |
|---|---|---|
| `window.ts` | Owns the persistent frameless transparent bar HWND: creation, show/hide/mode transitions, paint-ack handshake, peek-watchdog wiring, summon-gesture wiring, IPC registration. This is the biggest file (~920 lines). | `BarMode`, `BarReveal` (also duplicated in `shared/types.ts`), `getBarWindow`, `isBarVisible`, `isBarCleanlyPresented`, `createBarWindow`, `setBarEnabled`, `isBarEnabled`, `showBar`, `setPeekWatchSuspended`, `setBarMode`, `hideBar`, `handleSummonPress`, `setSummonGestureAccelerator`, `endActiveSummonHold`, `isBarInteractive`, `registerBarIpc`, `destroyBar` |
| `gesture.ts` | Polling-based tap/hold detector for the summon hotkey (drives `onPtt` down/up to the renderer). | `GestureKind`, `SummonGestureCallbacks`, `SummonGestureOptions`, `HOLD_THRESHOLD_MS`, `POLL_MS`, `REPEAT_GAP_MS`, `MAX_HOLD_MS`, `SummonGesture` (class) |
| `placement.ts` | Pure geometry: bar bounds per display, peek footprint hit-testing, pill hit-testing. | `Rect`, `DisplayLike`, `BAR_WINDOW_WIDTH`, `BAR_WINDOW_MAX_HEIGHT`, `BAR_MAX_HEIGHT_FRACTION`, `PEEK_FOOTPRINT_WIDTH/HEIGHT`, `isCursorInPeekFootprint`, `PILL_HIT_WIDTH/HEIGHT`, `isCursorOverPill`, `computeBarBounds`, `displayForPoint` |
| `watchdog.ts` | Pure decision logic for the peek-retract watchdog (when to hide, interactivity toggling). | `WatchdogInput`, `WatchdogResult`, `evaluatePeekWatchdog`, `barWatchPlan`, `barGestureSeesOpen`, `clickEdge`, `nextInteractivity` |
| `keyState.ts` | Low-level Win32 key/mouse-state polling helpers used by `gesture.ts` (accelerator parsing, key sampler, mouse-button sampler). | `acceleratorMainKey`, `makeKeySampler`, `makePrimaryMouseButtonSampler` |
| Tests | `gesture.test.ts`, `placement.test.ts`, `watchdog.test.ts` | |

### `src/main/overlay/**` (legacy overlay IPC/shortcut — now backs the bar's expanded content)

| File | Responsibility | Key exports |
|---|---|---|
| `ipc.ts` | Registers the `overlay:*` IPC handlers (hide/setEnabled/focusMain/etc.) — renderer-facing API name retained even though the underlying window was replaced by the bar. | `registerOverlayHandlers` |
| `shortcut.ts` | Global-accelerator registration for the summon shortcut (register/unregister/suspend/resume/get state). | `OVERLAY_ACCELERATOR`, `registerOverlayShortcut`, `unregisterOverlayShortcut`, `setOverlayAccelerator`, `suspendOverlayShortcut`, `resumeOverlayShortcut`, `getOverlayAccelerator`, `getOverlaySummonState` |
| Tests | `ipc.test.ts`, `shortcut.behavior.test.ts`, `shortcut.test.ts` | |

### Components

| File | Responsibility |
|---|---|
| `src/renderer/src/components/bar/BarApp.tsx` | The bar renderer's shell/root: reveal motion, pill⇄panel morph, mounts `usePushToTalk` (always alive), wires the `Orb`, imports `deriveOrbState`/`isBarBusy`/etc. from `barDisplay.ts`. |
| `src/renderer/src/components/bar/BarChatSurface.tsx` | The bar's expanded chat list/inline-conversation surface (viewport over the main window's single chat engine per INV-CHAT-1 — holds no `useChat` itself). |
| `src/renderer/src/components/bar/barDisplay.ts` | Pure display-derivation helpers (orb state from app state, busy flag, agent rows, pill label, next-conversation-draft). |
| `src/renderer/src/components/bar/bar.css` | Bar-specific styles. |
| `src/renderer/src/components/bar/bar.orb.test.ts`, `BarChatSurface.test.tsx`, `barDisplay.test.ts` | Tests. |
| `src/renderer/src/components/voice/VoiceSessionSurface.tsx` | Self-contained realtime-voice-session UI (mic mute, output device picker, stop) driven entirely by `voiceController` singleton state — mountable from Home chat area or the bar. |
| `src/renderer/src/components/orb/Orb.tsx` | React mount for the WebGL2 orb: owns an `OrbAnimator` instance, self-throttled rAF (30fps idle/60fps active/0fps hidden), WebGL-loss retry (60 attempts @ 700ms) with a static-mark fallback, wires real app signals (state/PTT/VAD/amplitude). |
| `src/renderer/src/components/orb/Orb.test.tsx` | Test. |

**Note:** `src/renderer/src/components/overlay/Waveform.tsx` (as named in the brief) **does not exist**. There is no standalone overlay Waveform component — waveform math lives in `src/renderer/src/orb/waveform.ts` and is consumed directly inside `Orb.tsx`/`orbRenderer.ts` (the PTT visualizer is drawn as bars inside the orb canvas itself, not a separate DOM/SVG component). Track 2 should target `orb/waveform.ts` for any waveform-shape work, not a nonexistent `components/overlay/Waveform.tsx`.

### `src/renderer/src/orb/**` (orb engine — waveform/shader/choreography)

| File | Responsibility | Key exports |
|---|---|---|
| `orbAnimator.ts` | Self-throttled rAF driver that steps the choreography and feeds the renderer each frame. | `OrbAnimator` (class) |
| `orbRenderer.ts` | WebGL2 draw calls (compiles/links the shader, uploads uniforms, draws). | `OrbRect`, `DEFAULT_MORPH_RECT`, `OrbRenderer` (class) |
| `shader.ts` | GLSL ES 300 vertex/fragment shader source strings. | `ORB_VERT`, `ORB_FRAG` |
| `choreography.ts` | Pure math: orbit/spin/merge/genesis/whirl envelopes, per-state params, `computeOrbFrame` (the single function that turns `OrbInputs` → `OrbFrame` each tick). Largest orb file (~650 lines). | `OrbState`, `DOT_COUNT`, `OrbParams`, `DEFAULT_ORB_PARAMS`, `RING_DOT_RENDER_RADIUS`, `ORB_PRESETS`, `OrbDot`, `OrbFrame`, `easeInOut`, `easeInOutVelocity`, `orbitAngle`, `orbitVelocity`, `orbitFlowFor`, `FLOW_EASE_TAU`, `AMP_FLOOR`, `WAVE_GAIN_MIN/MAX`, `THINK_WAVE_GAIN`, `shapeAmplitude`, `stepAmplitudeEnvelope`, `stepMergeEnvelope`, `MERGE_XFADE`, `mergeAmount`, `waveMixFor`, `AUDIO_STAGE_SPLIT`, `unrollProgressFor`, `barResponseFor`, `UNROLL_STAGGER`, `UNROLL_ARC`, `UnrollPoint`, `unrollPositions`, `WHIRL_ADD`, `WHIRL_TAU`, `AGENTS_WHIRL`, `spinTargetFor`, `WHIRL_ANCHOR_EPS`, `anchorWhirlStart`, `SPIN_EASE_TAU`, `genesisScale`, `genesisSettled`, `OrbInputs`, `computeOrbFrame` |
| `waveform.ts` | Pure waveform-bar math consumed by the orb canvas for the PTT visualizer: slot count/width by aspect, level shaping/gain/ceiling, history ring buffer, level stepping. | `WAVE_MAX_SLOTS`, `WAVE` (config object), `WAVE_NOISE_GATE`, `WAVE_LEVEL_GAIN`, `WAVE_LEVEL_CEIL`, `shapeBarLevel`, `waveHalfWidth`, `slotCountForAspect`, `WaveBar`, `waveBars`, `historyPush`, `historySlots`, `stepWaveLevels` |
| Tests | `waveform.test.ts` (no `orbAnimator.test.ts`/`orbRenderer.test.ts`/`choreography.test.ts` found — those are exercised indirectly via `Orb.test.tsx` and `bar.orb.test.ts`). | |

### `src/renderer/src/hooks/usePushToTalk.ts`

React hook wrapping `lib/ptt/machine.ts` with timers/transports/React state. Owns: hold-Space capture lifecycle, live-stream + 3s finalize deadline before falling back to batch POST, hint/error auto-clear timers, mic idle/tap release timers, restoring the draft after a hold. Exports `PushToTalk` type and the `usePushToTalk` hook (types: `Options`, `PushToTalk`).

---

## 2. Additive-schema surfaces

### `src/main/ipc/db.ts` — SQLite schema

- **Bootstrap pattern (idempotent, runs every `get()` call the first time):** one big `db.exec(`...`)` template string (lines 80–188) containing every `CREATE TABLE IF NOT EXISTS` + its `CREATE INDEX IF NOT EXISTS` statements, grouped by feature with a `-- comment` header per group (e.g. `-- Onboarding brain-map graph …` at line 134, `-- Local knowledge graph (M2)` heading appears as a code-section comment below at line 496, `-- Rewind: screen-history timeline` at line 809, `-- Proactive Insights` at line 884).
- **Column additions to existing tables:** `ensureColumn(db, table, col, declSql)` calls immediately after the big `exec()` block (lines 190–197) — this is `addColumnIfMissing` from `dbMigrations.ts`, re-exported locally as `ensureColumn`. Use this for a NEW COLUMN on an EXISTING table.
- **Versioned migrations:** anything beyond "create table if missing" / "add column if missing" (e.g. backfills, renames, multi-statement transactional changes) goes in `src/main/ipc/dbMigrations.ts`'s `MIGRATIONS` array — append-only, contiguous `version` starting at 1, each `up()` runs in its own transaction and bumps `PRAGMA user_version`. Currently only 1 migration exists (`local_conversation` cloud-sync outbox columns). `runMigrations(db)` is called at the end of `get()` (line 200).
- **The `get()` function is the single append point** (`src/main/ipc/db.ts:66-202`). New CREATE TABLEs go inside the same `db.exec()` template (best appended right before line 188's closing backtick, or as its own clearly-delimited block — see draft below); new columns on existing tables go in the `ensureColumn(...)` block at lines 190-197; anything needing ordering/backfill goes in `dbMigrations.ts`'s `MIGRATIONS` array (append a new `{ version: 2, ... }` entry).
- **Existing tables relevant to voice/ptt/settings:** NONE currently. There is no `caption_event`-like table for voice turns, no settings table (settings live entirely in renderer `localStorage` via `preferences.ts`, not SQLite), no outbox table for voice. The closest existing pattern to copy is `local_conversation`'s sync-outbox columns (`sync_state`, `segments_json`, `cloud_id`, `sync_attempts`, `sync_error` — see `ConversationSyncState` in `shared/types.ts:109-115`) and its `claimConversationForPosting` atomic compare-and-swap claim (`db.ts:320-329`).
- Existing tables (full list, for dedup awareness): `caption_event`, `local_conversation`, `indexed_files`, `local_kg_nodes`, `local_kg_edges`, `onboarding_kg_nodes`, `onboarding_kg_edges`, `app_usage`, `rewind_frames`, `insights`.

### `src/shared/types.ts` — shared types

- **Pattern:** one flat file (1277 lines), grouped by feature with `// --- Feature Name ---` section-comment headers (e.g. `// --- App usage (foreground-time tracking) ---` at line 910, `// --- Rewind: screen-history timeline ---` at line 1122, `// --- Proactive Insights …` at line 1157). Purely additive — old types are never removed, only added to.
- **Existing voice/PTT-relevant types already here:** `WaveformSource` (line 317), `ListenMode` (`'conversation' | 'ptt' | 'transcribe'`, line 192), `CaptureCommand`'s `ptt-warm`/`ptt-release`/`ptt-start`/`ptt-drain`/`ptt-dispose` variants (lines 240-244), `CaptureEvent`'s `ptt-chunk`/`ptt-drained`/`ptt-capped`/`ptt-error`/`ptt-levels` variants (lines 290-299), `BarMode`/`BarReveal`/`BarChatMessage`/`BarChatStatus`/`BarChatState`/`BarShowPayload`/`OmiBarApi` (lines 377-442), `RecordHotkeyState` (line 449).
- **`OmiBridgeApi`** (the `window.omi.*` renderer-facing API type) is defined at lines 470-772 in this same file — every new preload channel needs BOTH a method signature added here AND the implementation added to `preload/index.ts`'s `omi` object.
- **Append point:** end of file (after line 1277, `PlanRunResult`), as a new `// --- Track 2: Voice & PTT depth ---` section, OR interleaved near the existing `ListenMode`/`CaptureCommand`/`CaptureEvent` types if the new types extend those unions (unions must be edited in place, not appended separately — e.g. adding a new `CaptureCommand` variant is an edit at lines 228-269, not a new export).

### `src/preload/index.ts` — `window.omi.*` bridge

- **Pattern:** `const omi: OmiBridgeApi = { ...methodName: (args) => ipcRenderer.invoke('channel:name', args)... }` — one big object literal (lines 36-283) implementing the `OmiBridgeApi` type from `shared/types.ts`. Two more sibling objects: `omiOverlay: OmiOverlayApi` (lines 285-333) and `omiBar: OmiBarApi` (lines 335-374). All three are exposed via `contextBridge.exposeInMainWorld` (or `window.X =` in non-isolated mode) at lines 376-394.
- **Voice/PTT/audio/screen-related channels already exposed today:**
  - `listenStart` → `omi-listen:start` (invoke), `listenStop` → `omi-listen:stop` (invoke), `listenFeed` → `omi-listen:feed` (send, fire-and-forget PCM chunk), `listenFinalize` → `omi-listen:finalize` (send), `onListenMessage` ← `omi-listen:message` (on/off pattern)
  - `captureCommand` → `omi-capture:cmd` (send) / `onCaptureCommand` ← `omi-capture:cmd` (capture window receives) — this is how `ptt-warm`/`ptt-start`/etc. commands from `CaptureCommand` actually travel
  - `captureEmit` → `omi-capture:event` (send) / `onCaptureEvent` ← `omi-capture:event` — how `ptt-chunk`/`ptt-levels`/etc. events travel back
  - `screenReadText` → `screen:readNow` (invoke) — one-shot OCR-the-screen for chat context
  - `getRecordHotkey`/`setRecordHotkey` → `shortcuts:get-record`/`shortcuts:set-record`, `getSummonHotkey`/`setSummonHotkey` → `shortcuts:get-summon`/`shortcuts:set-summon`
  - `suspendShortcutCapture`/`resumeShortcutCapture` → `shortcuts:suspend-capture`/`shortcuts:resume-capture` (send)
  - `onGpuContextLost` ← `GPU_CONTEXT_LOST_CHANNEL` const (`'gpu:context-lost'`, shared const from `shared/types.ts` line 10, imported not hardcoded)
  - `getCaptureSources` → `capture:getSources` (screen-share source picker, invoke)
- **IPC invoke pattern:** `methodName: (args) => ipcRenderer.invoke('channel:name', args)` for request/response; `methodName: (args) => ipcRenderer.send('channel:name', args)` for fire-and-forget; `onX: (cb) => { const listener = (_e, payload) => cb(payload); ipcRenderer.on('channel:name', listener); return () => ipcRenderer.removeListener('channel:name', listener) }` for subscriptions (always returns an unsubscribe fn).
- **How to add a new channel additively:** (1) add the method signature to `OmiBridgeApi` (or `OmiBarApi`/`OmiOverlayApi`) in `shared/types.ts`; (2) implement it in the matching object literal in `preload/index.ts` following one of the three patterns above; (3) register the actual `ipcMain.handle('channel:name', ...)` / `ipcMain.on('channel:name', ...)` in the main-process side (for voice/PTT that's most likely a new handler set inside `src/main/bar/window.ts`'s `registerBarIpc`, or a new file under `src/main/ptt/` or similar, following the `src/main/overlay/ipc.ts` pattern of one `register*Handlers(...)` function called once at startup).
- **Append point:** inside the `omi` object literal, anywhere (grouped by comment header, e.g. add a `// --- Track 2: Voice & PTT depth ---` group) — the file has no fixed ordering requirement beyond keeping related channels near each other.

### Channel-name registry

**No separate `src/shared/ipc.ts` or channel-constants file exists.** Channel name strings are inline literals duplicated between `preload/index.ts` (renderer side) and each `ipcMain.handle/on` call (main side) — the only exception is `GPU_CONTEXT_LOST_CHANNEL` (`shared/types.ts:10`) and `PCM_PENDING_MAX_BYTES` (`shared/types.ts:5`), which are exported consts specifically because both the main-process sender and preload-side listener needed to share the exact literal without drifting. Track 2 should follow this precedent: if a new channel name is written in two places (main handler + preload), pull it into a shared exported const in `shared/types.ts` near the top (next to `GPU_CONTEXT_LOST_CHANNEL`); a plain string literal is fine when it's a pure `ipcRenderer.invoke` request/response pair with no separate main-side broadcast to keep in sync.

---

## 3. Preferences store

`src/renderer/src/lib/preferences.ts` — client-side, `localStorage` key `'omi-windows-prefs-v1'`, JSON blob. Shape: `export type Preferences = { captionIntervalMs, showRecordingBadge, reduceMotion, displayName?, language, chatHistoryMode, recordingConsentedAt?, goal?, automationConsentedAt?, overlayShortcut?, continuousRecording?, retentionMode?, onboardingCompletedAt?, onboardingStep?, backgroundConsentAt?, vadGateEnabled?, agentCommands? }`.

- **Existing voice/PTT-relevant keys:** `language: string` (transcription language, defaults to `DEFAULT_LANGUAGE`), `vadGateEnabled?: boolean` (local VAD gate for ambient/continuous lanes only — PTT is explicitly passthrough regardless, per the comment at line 55), `overlayShortcut?: string` (the bar summon accelerator), `continuousRecording?: boolean` (always-on mic → `/v4/listen`). **No `ttsEnabled`, `ttsTypedEnabled`, `pttMuteSystemAudio`, or `voiceProviderAuto` keys exist yet** — these are new additions Track 2 would introduce.
- **API:** `getPreferences(): Preferences` (returns the live in-memory cache), `setPreferences(patch: Partial<Preferences>): void` (read-modify-write against a FRESH `load()`, not the cached `current` — deliberately, to avoid cross-window lost-update clobbers; see comment at lines 109-114), `onPreferencesChange(cb): unsubscribe`, plus helpers `isOnboardingComplete`, `clearUserScopedPreferences`, `completeOnboarding`, `resetOnboarding`, `setPendingRoute`/`consumePendingRoute`.
- **Cross-window sync:** a `storage` event listener (lines 96-102) reloads `current` in every OTHER renderer window when one window writes the key — this is how the bar/overlay/capture-window/main-window renderers (separate processes, same localStorage origin) stay in sync without IPC.
- **Append point:** add new optional fields to the `Preferences` type (~line 62, before the closing `}`), with a comment explaining the default when undefined (the codebase convention is "undefined means X" rather than always setting an explicit default in the `defaults` object — only 5 of ~19 fields are in `defaults`).

## 4. Telemetry / fallback helper

**There is no dedicated Windows `recordFallback(...)` wrapper function** (unlike the Python/Swift/Rust emitters AGENTS.md documents). The Windows renderer's actual pattern — already used correctly by `voiceController.ts` (lines 79, 227, 439) and `lib/capture/captureEngine.ts` (lines 49, 86) — is calling `trackEvent` from `src/renderer/src/lib/analytics.ts` directly with the event name `'fallback_triggered'` and the AGENTS.md-mandated field shape:

```ts
import { trackEvent } from '../analytics' // or relative path to lib/analytics.ts

trackEvent('fallback_triggered', {
  component: 'realtime_mint',      // closed-enum area name, e.g. 'realtime_mint' | 'voice_echo_gate' | 'tts' | new PTT-specific ones
  from: 'openai',                  // or 'none'
  to: 'gemini',                    // or 'none'
  reason: 'provider_unavailable',  // shared bounded reason set, else 'other'
  outcome: 'recovered'             // 'recovered' | 'degraded' | 'exhausted'
})
```

`analytics.ts`'s `trackEvent(event: string, properties: Record<string, unknown> = {})` POSTs directly to PostHog's capture API (`https://us.i.posthog.com/capture/` by default, fire-and-forget, swallows errors) — this is the Windows analog of `desktop_health_event`/`fallback_triggered` on macOS Swift, just without an intermediate typed wrapper. Track 2 should call `trackEvent('fallback_triggered', {...})` with the same 5-field shape (`component`, `from`, `to`, `reason`, `outcome`) for any new voice/PTT fallback branch — do not invent a new event name, per AGENTS.md.

## 5. Test setup

- Vitest config: `vitest.config.ts` (repo root of `desktop/windows/`). Tests are co-located `*.test.ts`/`*.test.tsx` next to the source file (e.g. `src/renderer/src/lib/voice/echoGate.test.ts` next to `echoGate.ts`). `.tsx` suites opt into `jsdom` per-file via a `// @vitest-environment jsdom` pragma comment (not a global jsdom config) — see `vitest.config.ts:34`.
- Run the full suite: `pnpm test` (→ `vitest run`). Watch mode: `pnpm test:watch`.
- Run a single test file: `pnpm vitest run <path-to-file>.test.ts` (or `npx vitest run <path>`), e.g. `pnpm vitest run src/renderer/src/lib/voice/echoGate.test.ts`. `pnpm test:watch <path>` for watch mode on one file.
- Live/E2E scripts (NOT part of `pnpm test`, need real credentials/services): `pnpm test:e2e:ptt` (live PTT E2E, self-fetches auth token from a running app debug port), `pnpm test:e2e:voice-smoke` (`scripts/run-voice-smoke.mjs`), `pnpm voice:loop-check` (`scripts/run-voice-loop-check.mjs`), `pnpm fixtures:audio` (regenerates SAPI-synthesized speech fixtures consumed by the live E2E).
- `dbMigrations.test.ts` is the pattern to follow for schema-migration tests: it builds a fixture DB with the OLD schema using plain `node:sqlite` (no Electron/better-sqlite3 ABI dependency) and asserts the migration brings it forward — reuse this pattern for any new Track 2 migration.

---

## 6. DRAFT — additive `db.ts` schema block (NOT YET WRITTEN TO CODE)

Everything below is a draft for review only. It follows the exact pattern already in `db.ts`: a labeled `CREATE TABLE IF NOT EXISTS` block inside the big `get()` bootstrap `exec()`, plus `ensureColumn` calls for anything added to an existing table, plus (if truly needed) a new `MIGRATIONS` entry in `dbMigrations.ts`.

### 6a. New table: durable voice-turn outbox

Insert this block **inside the existing `db.exec(`...`)` template in `db.ts`**, right before the closing backtick at line 188 (i.e. after the `insights` table/index, before the template literal ends):

```sql
    -- Track 2: Voice & PTT depth
    -- Durable outbox for a voice turn (PTT or realtime-session utterance) that
    -- must survive an app restart mid-flight. Mirrors local_conversation's
    -- sync-outbox column pattern (sync_state/cloud_id/sync_attempts/sync_error)
    -- but as its own table since a voice turn is not a conversation row.
    CREATE TABLE IF NOT EXISTS voice_turn_outbox (
      id TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      transcript TEXT NOT NULL,
      origin TEXT NOT NULL DEFAULT 'ptt',      -- 'ptt' | 'realtime' | 'typed-tts'
      partial INTEGER NOT NULL DEFAULT 0,       -- 0/1: interim (not yet finalized) vs final
      status TEXT NOT NULL DEFAULT 'pending',   -- 'pending' | 'sending' | 'done' | 'failed'
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_voice_turn_outbox_status ON voice_turn_outbox(status, created_at);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_turn_outbox_idem ON voice_turn_outbox(idempotency_key);
```

Rationale for fields:
- `idempotency_key` is `UNIQUE` (not just an app-level check) so a crash-retry double-insert is rejected by SQLite itself — same intent as the `claimConversationForPosting` compare-and-swap pattern already in `db.ts:320-329`, but simpler here since the client generates the key up front rather than racing state transitions.
- `status` intentionally mirrors `ConversationSyncState`'s vocabulary (`pending`/`posting`≈`sending`/`done`/`failed`) rather than inventing new words, per the existing convention.
- `partial` as `INTEGER` (0/1) matches the codebase's existing SQLite boolean convention (`indexed`, `dismissed` columns use the same idiom, never a `BOOLEAN` type).

### 6b. New columns: voice/PTT settings

**These are almost certainly better placed in `preferences.ts` (localStorage), not SQLite** — every existing boolean/setting toggle in this codebase (`vadGateEnabled`, `continuousRecording`, `retentionMode`, etc.) lives in `Preferences`, and SQLite in this app is reserved for data rows (conversations, frames, usage), not settings. Recommend against a `settings` table unless there's a specific reason SQLite is needed (e.g. needing it queryable from the read-only `execSafeSelect` chat-agent path, which `preferences.ts` cannot offer since it's renderer-only localStorage). If Track 2 still wants them queryable from main/SQLite, the `ensureColumn` additions would go in `db.ts` right after line 197 (before `runMigrations(db)` at line 200):

```ts
  // Track 2: Voice & PTT depth (only if these must be queryable/joinable from
  // main-process SQL — otherwise prefer Preferences in lib/preferences.ts).
  ensureColumn(db, 'voice_turn_outbox', 'tts_enabled', 'INTEGER')
```

— but this doesn't fit `voice_turn_outbox` semantically (that's a per-turn row, not a settings row). **Recommendation: add these as new optional `Preferences` fields instead** (see §6c).

### 6c. DRAFT `src/shared/types.ts` additions

```ts
// --- Track 2: Voice & PTT depth ---

/** A durable voice-turn outbox row (see voice_turn_outbox in db.ts). */
export type VoiceTurnOrigin = 'ptt' | 'realtime' | 'typed-tts'
export type VoiceTurnStatus = 'pending' | 'sending' | 'done' | 'failed'

export type VoiceTurnOutboxRow = {
  id: string
  idempotencyKey: string
  transcript: string
  origin: VoiceTurnOrigin
  partial: boolean
  status: VoiceTurnStatus
  createdAt: number
  updatedAt: number
  attempts: number
  lastError?: string | null
}

export type VoiceTurnOutboxPatch = {
  status: VoiceTurnStatus
  lastError?: string | null
  incrementAttempts?: boolean
}
```

Add corresponding methods to `OmiBridgeApi` (near the existing `insertLocalConversation`/`claimConversationForPosting` block, ~line 473-488):

```ts
  insertVoiceTurn: (row: VoiceTurnOutboxRow) => Promise<void>
  updateVoiceTurnStatus: (id: string, patch: VoiceTurnOutboxPatch) => Promise<void>
  listPendingVoiceTurns: () => Promise<VoiceTurnOutboxRow[]>
```

And extend `Preferences` in `src/renderer/src/lib/preferences.ts` (not `shared/types.ts` — `Preferences` is defined there) with:

```ts
  // Track 2: Voice & PTT depth. Undefined = default per comment.
  ttsEnabled?: boolean            // undefined = on (spoken replies enabled by default)
  ttsTypedEnabled?: boolean       // undefined = off (TTS for typed, not just spoken, input)
  pttMuteSystemAudio?: boolean    // undefined = off (don't ducking/mute system audio during a PTT hold)
  voiceProviderAuto?: boolean     // undefined = on (auto-pick/fallback openai<->gemini; false = pin to last-used provider)
```

### 6d. DRAFT preload channel names

Following the existing `db:*` namespace convention (`db:insertLocalConversation`, `db:claimConversationForPosting`, etc.):

```
db:insertVoiceTurn
db:updateVoiceTurnStatus
db:listPendingVoiceTurns
```

registered as `ipcRenderer.invoke(...)` in `preload/index.ts`'s `omi` object (request/response, matches the `db:*` pattern exactly), with matching `ipcMain.handle('db:insertVoiceTurn', ...)` etc. added on the main side (likely in a new `src/main/ipc/` handler file, following how the existing `db:*` handlers are registered — grep `ipcMain.handle('db:` in `src/main/` to find the exact registration file before adding).

---

## 7. Exact append points (file:line)

| File | Append point | What goes there |
|---|---|---|
| `src/main/ipc/db.ts` | Line 188 (just before the closing `` ` `` of the big `db.exec()` template) | New `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` blocks, labeled `-- Track 2: Voice & PTT depth` |
| `src/main/ipc/db.ts` | Lines 190-197 (the `ensureColumn(...)` calls, right after the big `exec()`, before `runMigrations(db)` at line 200) | New columns on an EXISTING table |
| `src/main/ipc/dbMigrations.ts` | `MIGRATIONS` array, line 55-69 (append a new `{ version: 2, ... }` entry after the existing version-1 entry) | Anything needing backfill/ordering beyond simple additive CREATE/ALTER |
| `src/shared/types.ts` | End of file, after line 1277 (`PlanRunResult`) | New standalone types, as a `// --- Track 2: Voice & PTT depth ---` section |
| `src/shared/types.ts` | `OmiBridgeApi` type, insert near lines 473-488 (next to the conversation-outbox methods, which are the closest existing analog) | New preload method signatures |
| `src/shared/types.ts` | `CaptureCommand` union, lines 228-269 (edit in place, not appended separately, if extending PTT command variants) | New `CaptureCommand`/`CaptureEvent` variants |
| `src/preload/index.ts` | Inside the `omi` object literal, lines 36-283 (anywhere, grouped under a new comment header) | New channel implementations |
| `src/renderer/src/lib/preferences.ts` | `Preferences` type, ~line 62 (before the closing `}`) | New optional settings fields |
| `src/renderer/src/lib/preferences.ts` | `defaults` object, ~line 65-74 (only if the field needs a non-`undefined` default) | Default values |
