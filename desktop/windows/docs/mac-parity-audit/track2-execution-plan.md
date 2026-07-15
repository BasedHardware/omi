# Track 2 (Voice & PTT depth) — Execution Plan

Status: durable planning doc, synthesized from `track2-groundtruth/01`–`10` (all 10 present, including `08-reconnect-devicechange-silentmic.md`). Read those docs for full citations; this doc is the scannable synthesis + sequencing layer on top.

Frozen Mac reference: tag `v0.12.72+12072-macos` at `.worktrees/mac-ref/`. Windows worktree: `.worktrees/track2-voice-bar/desktop/windows/`. Backend: `.worktrees/track2-voice-bar/backend/`.

---

## 1. Mission & scope

Deepen voice/PTT **capability** on top of the exempt Windows bar/orb UI — never restyle the bar or orb, only extend what it's driven by and what it can do. In scope: ground-truth areas 01–05, 08, 09 (TTS, warm-hub/turn state machine, per-provider barge-in, PTT transcribe contract, language-ID + system-audio mute, reconnect/device-change/silent-mic, Phase B outbox+tools), plus 06+07 **minus chat-rendering** (auto-model selection + system-instructions/about-user card + usage-limiter capability — the actual chat bubble rendering belongs to Track 1). Out of scope: chat UI rendering, memory/goals UI (Track 3), billing UI (settings-parity, consume-only), and any bar/orb visual restyle.

Ground-truth doc map: `01-tts-readaloud.md`, `02-warmhub-voiceturn-statemachine.md`, `03-per-provider-bargein.md`, `04-ptt-vocab-transcribe-contract.md`, `05-language-id-system-audio-mute.md`, `06-automodel-systeminstructions-aboutuser.md`, `07-usage-limiter.md`, `08-reconnect-devicechange-silentmic.md`, `09-phaseB-voiceturn-outbox-tools.md`, `10-windows-inventory-schema.md`.

---

## 2. Ground-truth corrections to the original brief

The original brief contained factual errors. Ground truth wins — do not build against the brief's assumptions below.

| # | Brief assumed | Ground truth (source) |
|---|---|---|
| a | No path speaks a bar Ask-AI reply — TTS is a from-scratch build | **The PTT→spoken-reply loop already works**: `BarApp.tsx` PTT commit → `sendFromBar(text, true)` → `useChat.ts` `send()` → `maybeSpeak()` → `speakText()`. Not a gap. Real gaps: chunked/streaming synth, filler-phrase-while-waiting, explicit barge-in-on-new-PTT-hold, and the typed-query voice-answer toggle. (`01`) |
| b | `/v2/voice-message/transcribe` response has NEW `stt_provider`/`stt_model` fields | **These fields do not exist anywhere in the backend response.** Grepped `backend/routers/chat.py` — response is exactly `{transcript: str, language?: str}`. Mac's own client code has dead `Optional` fields for them that always decode to `nil`. Do not port. (`04`) |
| c | A `503 stt_provider_configuration_error` exists and must be handled | **Does not exist.** Grepped the entire backend tree — zero matches. Do not build handling for it. (`04`) |
| c′ | (bonus, same doc) | Response DOES have an optional `language` field — this is the field A3 (language-ID reconcile stage) should consume when present, instead of inventing a second transcript source. (`04`, `05`) |
| d | `effective_desktop_access_tier` / `desktop_free`/`desktop_full`/`desktop_architect` tier enum drives the usage gate | **Do not exist anywhere** (Mac, Windows, or backend — grepped all three). Real contract: `ChatUsageQuota.plan_type: 'basic'|'unlimited'|'architect'|'operator'` plus a separate `allowed: bool`. The gate is effectively a **binary `allowed` check**; `plan_type` is display/copy only. (`07`) |
| e | `/v1/auto/model-pick` can return `"auto"` | **Never returns `"auto"`.** Response `provider` is always a concrete pick: `"geminiFlashLive"` or `"gptRealtime2"`. `.auto` is a client-side settings sentinel only (Mac's `selectedProvider` vs `effectiveProvider` split), never a server value. (`06`) |
| f | Gemini barge-in needs a missing session-replace (socket-discard) mechanism ported to Windows | The load-bearing bug is smaller: **a missing `responsePending`/generation gate**. Windows' `player?.clear()` only flushes what's queued *at that instant* — it does not stop trailing audio chunks for the same (already-interrupted) generation from being re-enqueued on later `onmessage` calls. Fix = a `currentGenerationInterrupted` boolean gate (mirrors Mac's `geminiResponsePending`), not a socket-replace port. Windows' continuous-session architecture may not even need session-replace (no `activityStart`/`activityEnd` framing) — flag for live verification, don't assume. (`03`) |
| g | `windows` platform may not be recognized on these endpoints | **It is recognized everywhere checked**: `backend/utils/subscription.py:119` `DESKTOP_PLATFORMS = {'macos', 'windows'}` is the single source of truth, used by trial-paywall (`04`), usage-quota (`07`), and `/v1/auto/model-pick` doesn't even check platform (`06`). No platform-variant-divergence risk found on any Track 2 endpoint — contrast with the prior windows-plan-catalog incident, which was a different code path (`/v1/users/me/subscription`'s plan catalog). |

---

## 3. Decisions locked (by the orchestrator)

These resolve open questions the ground-truth docs raised. Do not re-litigate; implement against these.

- **Settings storage**: all new Track 2 settings (`ttsEnabled`, `ttsTypedEnabled`, `pttMuteSystemAudio`, `voiceLanguages`, `voiceProviderAuto`, etc.) go in `Preferences` / `localStorage` (`src/renderer/src/lib/preferences.ts`), matching every existing Windows settings toggle (`vadGateEnabled`, `continuousRecording`, etc.). **Not SQLite.** SQLite is reserved for data rows. The one exception is the Phase-B `voice_turn_outbox` table (§4/9 of `09`, §6 of `10`) — that's a per-turn durable-write queue, not a setting.
- **Fallback telemetry**: use the established Windows pattern — direct `trackEvent('fallback_triggered', { component, from, to, reason, outcome })` from `lib/analytics.ts`. **No `recordFallback()` wrapper exists on Windows and none should be invented** for this track; five existing call sites (`voiceController.ts:79,227,439`, `captureEngine.ts:49,86`) already establish the convention. Field name is `component` (not `area` — that's the Swift-side name; Windows convention differs and should stay consistent with itself). (`08` §D, `10` §4)
- **Language-ID (A3)**: no on-device ASR, no new JS lang-detect dependency for v1. Use the backend response's `language` field when present (§2c′ above) plus a new `voiceLanguages: string[]` preference implementing Mac's exact gating contract (empty = inert, 1 entry = pass-through, ≥2 = detect/gate). Feed the detected/preferred language forward into the *next* turn's `language` param on both batch (`constants.ts`) and stream (`transport.ts`) transports. True same-turn dual-transcript reconciliation (Mac's local-decode swap) is a documented, accepted gap for v1 — not built. (`05`)
- **Gemini barge-in fix**: implement the generation/`responsePending` gate in `geminiSession.ts` (§2f above). Do not build session-replace/socket-discard machinery.
- **A5 (warm-hub reducer)**: a faithful TypeScript port of `VoiceTurnReducer` + `VoiceTurnCoordinator`, including porting the Swift test suite's assertions (typed-ID fencing, deadline-per-turn-ID isolation, atomic-apply+FIFO-drain, terminal-reason taxonomy). This is additive next to `sessionMachine.ts`, not a replacement — whether `sessionMachine.ts` becomes the session-level wrapper under the new turn-level reducer, or is retired, is an implementation decision inside the PR, not dictated here. (`02`)
- **System-audio mute mechanism (A4)**: **deferred to A4's own implementation-design step.** Ground truth recommends a long-lived C# helper process (reusing the existing OCR/automation-helper build pattern) over raw koffi/COM vtable calls, but this is a new build artifact and should be confirmed with the build-pipeline owner before implementation — not decided unilaterally by this plan. (`05` Topic B)

---

## 4. PR wave sequence

**Wave 1 — disjoint, fully parallelizable** (separate worktrees, no shared files):

| PR | Features | Files touched | Depends on | Parallel-safe |
|---|---|---|---|---|
| `PR-schema` | Phase B storage groundwork | `src/main/ipc/db.ts` (new `voice_turn_outbox` table), `src/shared/types.ts` (`VoiceTurnOutboxRow` etc.), `src/preload/index.ts` (`db:insertVoiceTurn`/`db:updateVoiceTurnStatus`/`db:listPendingVoiceTurns`) | — | Yes — primary worktree `feat/win-voice-depth` |
| `PR-ptt-transcribe` | A2 (keywords param) + A3 (language-ID gating + feed-forward) | `lib/ptt/transport.ts`, `lib/ptt/constants.ts` | — | Yes — worktree `feat/win-voice-ptt` |
| `PR-system-audio-mute` | A4 (PTT-down mute / PTT-up restore) | new C#-helper build script + `main/` invocation glue + `preferences.ts` (`pttMuteSystemAudio`) | Build-pipeline owner sign-off on helper approach (§3) | Yes — own worktree |
| `PR-gemini-gate` | A6 (barge-in trailing-audio fix) | `lib/voice/geminiSession.ts` | — | Yes — own worktree |

**Wave 2 — realtime cluster, SERIALIZE** (all touch the shared `lib/voice/{voiceController,sessionMachine,providerSession}.ts` triad — do not run in parallel, land one at a time onto the same base):

| PR | Features | Files touched | Depends on | Parallel-safe |
|---|---|---|---|---|
| `PR-bar-tts` | A1 (chunked TTS, filler phrase, barge-in-interrupt-on-new-hold) + A10 (usage-limiter pre-send gate) | `lib/voice/voiceController.ts`, `components/bar/BarApp.tsx` (both features touch `BarApp.tsx`) | Wave 1 merged | **No** — serialize with `PR-realtime-grounding` |
| `PR-realtime-grounding` | A8 (auto-model selector) + A9 (system-instructions + about-user card) | `lib/voice/voiceController.ts`, `lib/voice/sessionMachine.ts`, new `lib/voice/autoModelSelector.ts`, new about-user assembler | Wave 1 merged | **No** — serialize with `PR-bar-tts` |

Reason for serialization: both PRs land changes in `voiceController.ts`/`sessionMachine.ts`/`providerSession.ts` — the shared realtime-session core. Sequential landing avoids a 3-way merge across the session lifecycle state.

**Wave 3 — big reducer port, absorbs the realtime cluster:**

| PR | Features | Files touched | Depends on | Parallel-safe |
|---|---|---|---|---|
| `PR-warmhub` | A5 (VoiceTurnReducer + VoiceTurnCoordinator port, ported Swift tests) | new `lib/voice/voiceTurnMachine.ts`, new `lib/voice/voiceTurnCoordinator.ts`, extends `voiceController.ts` | Wave 2 merged (rebases/absorbs both realtime-cluster PRs — largest, most disruptive change, must land on the settled cluster) | No |
| `PR-reconnect` | A7 (idle/wake reconnect, strike budget, device-change rebuild, silent-mic escalation) | `voiceController.ts`, `capture/pttGraph.ts`, `lib/ptt/gate.ts` (or new `deadMicPolicy.ts`) | `PR-warmhub` merged | No |

**Wave 4 — blocked on Track 1:**

| PR | Features | Files touched | Depends on | Parallel-safe |
|---|---|---|---|---|
| `PR-phaseB-outbox` | B2 (interrupted-turn capture + outbox drain wired to real kernel write) | consumes `PR-schema`'s table; wires to Track-1-published `appendVoiceTurnToChat` etc. | Track 1 publishes the 6 interfaces in §5 | No |
| `PR-voice-tools` | B1 (in-session tool surface, 23-tool port) | new tool registry/dispatch in `lib/voice/`, turn-epoch fencing | Track 1's tool executor + turn-epoch mechanism; `PR-warmhub` (needs turn IDs) | No |

Note: `PR-schema` (Wave 1) can land standalone since it's pure storage with no kernel-write dependency — the outbox table + enqueue/acknowledge/list can exist and be tested well before Track 1's interfaces are ready; only `PR-phaseB-outbox`'s actual drain-to-kernel wiring blocks on Track 1.

---

## 5. File-ownership & cross-track dependencies

**Track 2 owns:**
- `lib/voice/**` (voiceController, sessionMachine, providerSession, openaiSession, geminiSession, tokenMint, echoGate, injectedTranscript, tts, pcmPlayer, playerCore, playerWorklet, usageReport, e2eHook + new voiceTurnMachine/voiceTurnCoordinator/autoModelSelector)
- `lib/ptt/**` (machine, capture, transport, gate, constants)
- `main/bar/**` (window, gesture, placement, watchdog, keyState) and `main/overlay/**` (ipc, shortcut)
- `components/{bar,voice,orb}/**` (BarApp.tsx, BarChatSurface.tsx, barDisplay.ts, VoiceSessionSurface.tsx, Orb.tsx)
- `orb/**` (orbAnimator, orbRenderer, shader, choreography, waveform.ts)

**Correction from the original brief**: `components/overlay/Waveform.tsx` **does not exist** — the waveform is `src/renderer/src/orb/waveform.ts`, consumed directly inside `Orb.tsx`/`orbRenderer.ts`. Target `orb/waveform.ts` for any waveform-shape work. (`10` §1)

**Must NOT edit** (request from owner instead):
- `useChat.ts`, `ChatMessages.tsx`, `screenContext.ts` — Track 1
- `useMemories.ts`, `lib/goals.ts` — Track 3
- `billing.ts`, `usageLimit.ts` — settings-parity track; consume only (`fetchChatQuota`, `chatQuotaView`, `onUsageLimit`/`showUsageLimit`/`dismissUsageLimit`)

**Cross-track needs:**
- **A9 (about-user card)** needs a memory-facts source. Two viable paths, neither touching Track-1/Track-3 files directly: (a) a synchronous cache-getter on Track 3's `useMemories.ts` module-level cache (if one is exposed — confirm before assuming), or (b) an off-hot-path direct `GET /v3/memories?limit=8` call inside the new about-user assembler, independent of the Memories page. Task-count (overdue/due-today) has **no existing shared hook on Windows at all** — this is new code either way (small fetch+bucket logic mirroring `Tasks.tsx`'s `bucketOf()`), not a cross-track ask. (`06` §B3)
- **Typed-voice-toggle settings UI** (the Settings-page checkbox for "speak replies to typed questions too", Mac's `floatingBarTypedQuestionVoiceAnswersEnabled` equivalent) is a **Track-6 settings-UI concern** — Track 2 only needs to read the resulting preference and thread it into `BarApp.tsx`'s `sendFromBar(text, fromVoice)` call.
- **Phase B needs Track 1 to publish 6 interfaces** before `PR-phaseB-outbox` can wire real kernel writes (full detail in `09` §4): `appendVoiceTurnToChat(...)` with idempotency-key + ack-boolean return; an optimistic-stage/promote-on-ack pair; a `mainChatSurfaceReference()`-equivalent canonical-conversation accessor; a voice-seed-context fetch (recent chat continuity + already-reflected idempotency keys); the tool-call dispatch/registry surface (ideally the same executor typed-chat uses) with turn-epoch fencing; a turn-recorded/promotion event/callback for background-drained turns. Until published, Track 2 can still build the outbox table and interrupted-turn-capture logic (self-contained) but must stub the kernel-write call behind these six interfaces rather than writing to `useChat.ts` state directly.

---

## 6. Parked / Chris-reserved

- Nothing in Track 2 hits a `G-A`..`G-G` decision gate directly.
- Typed-voice-answer **default** (on/off out of the box) is a Track-6 settings-UI product decision, not Track 2's to set.
- **BYOK realtime (client-direct connect)** is deferred — needs a Windows BYOK key store, which Track 1 builds; Track 2's `tokenMint.ts` stays managed-token-only until that lands.
- **Same-turn dual-language transcript reconciliation** (Mac's local-decode-swap for a mislabeled provider transcript) is deferred per §3 — documented gap, not silently dropped, revisit if a JS language-ID dependency is deliberately added later.
- `AutoModelSelector.applyServerPick(_:)`-equivalent (a push-override path bypassing the poll) has no confirmed Mac call site either — do not build a Windows equivalent unless/until Mac actually wires one up. (`06` "Open items")

---

## 7. Verification approach

Per surface, before any PR:

1. **4-angle simplify + Opus audit** on all changes (per project standard) — run `/simplify` first, then a fresh Opus audit agent; fix Critical/Major before proceeding.
2. **Hermetic vitest** for all pure logic (reducers, gates, formatters, telemetry payload shape) — co-located `*.test.ts`, matches existing pattern (`echoGate.test.ts`, `sessionMachine.test.ts`, etc.). Port the Swift test *assertions* for A5 (typed-ID fencing, per-turn-ID deadline isolation, atomic-apply+FIFO-drain, terminal-reason coverage), not just the reducer shape.
3. **Live-verify on the built app** — worktree renderer port (this worktree's derived port; the primary-checkout instance is `:5204`/CDP `9259` per the worktree's own dev-instance derivation — confirm with `pnpm dev:instance` before assuming a fixed number). Seed auth via `pnpm seed:auth` from the primary running app (CDP-based session clone), not a fresh web login.
4. **Skeptical Sonnet screenshot review** for any UI-adjacent change (bar TTS glow states during chunked playback, usage-limit inline message/popup) at 1280×720 desktop + a narrow/mobile-width viewport + both 125% and 150% Windows DPI scaling — separate subagent, default-assumes failure, per the Frontend Design Toolkit rule. This is capability-driven UI feedback (glow/message correctness), not a bar/orb restyle — stays in scope.
5. **Gemini barge-in (A6)** — verify live: start a long Gemini reply, barge in mid-speech, confirm no stale/trailing audio chunks from the interrupted generation reach the player after the gate fires. Optionally cross-check the same sequence against the Mac reference build on the shared Mac mini oracle (`192.168.1.236`, `ssh omi-mac` / `mac-run`) to confirm Gemini's trailing-audio-after-interrupted behavior is a real provider quirk (per `03` §5's reproduction hypothesis) and that the fix eliminates it on Windows.
6. **Reconnect/silent-mic (A7)** — exercise via a scripted device-change (`navigator.mediaDevices` mock or an actual USB mic unplug/replug) and a forced idle-close/kill of the realtime socket; confirm the strike budget, 60s-survival reset, and dead-mic escalation ladder behave per `08`'s ported thresholds, not just that no crash occurs.
