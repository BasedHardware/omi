# Mac→Windows Parity Audit — Floating Bar / Ask AI / PTT

> **Re-audited 2026-08-22** (original: 2026-08-20). This pass re-verified every claim
> against current source rather than trusting the prior file — see "Changed since the
> 2026-08-20 audit" immediately below. Ground truth reconciled against
> `track2-execution-plan.md` and its `track2-groundtruth/01,04,05,06,07` docs, whose own
> claims were in turn re-checked against source (they were themselves written against a
> feature-branch worktree, not always this repo's actual head).

> Scope: depth comparison of the Mac `FloatingControlBar` (bar shell, drag/resize, shortcuts,
> launch policy, usage limiter) vs the Windows top-edge bar; the Ask-AI text/voice input and
> response rendering; PTT ergonomics (lifecycle, vocabulary boosting, language ID, TTS
> playback); and screen-context capture feeding Ask AI. Excludes RealtimeHub/RealtimeOmni
> continuous-voice-conversation internals (owned by the realtime-voice audit) and
> AgentPill/AgentDelegation spawn mechanics (owned by the chat-agent audit) — both referenced
> only where they intersect the bar surface.
>
> Windows baseline checked (current paths — several differ from the 2026-08-20 file, see
> callout): `src/renderer/src/components/bar/{BarApp,BarChatSurface,barSend}.tsx?,.ts`,
> `bar.css`, `src/main/bar/{window,placement,gesture,keyState,barContextMenu,barContextMenuTemplate}.ts`,
> `src/main/overlay/{ipc,shortcut}.ts`,
> `src/renderer/src/lib/ptt/{machine,gate,capture,transport,constants,vocabulary,userVocabulary,systemAudioMute}.ts`,
> `src/renderer/src/lib/voice/{voiceController,ttsChunker,tts,aboutUser,systemInstruction,taskCounts}.ts`,
> `src/renderer/src/lib/chatQuotaGate.ts`, `src/main/audio/systemAudioMute.ts`,
> `src/renderer/src/hooks/{usePushToTalk,useChat}.ts`, `src/renderer/src/components/orb/Orb.tsx`,
> `src/renderer/src/orb/{orbAnimator,orbRenderer,waveform}.ts`,
> `src/renderer/src/components/chat/{ChatMessages,AgentThreadCard,ChatAttachmentStrip,ChatBridgeHost}.tsx`,
> `src/renderer/src/lib/{screenContext,screenRedact,capture/systemAudio}.ts`.

## Changed since the 2026-08-20 audit

The single biggest finding of this pass: **almost every "Absent, H-value" row in the old
table was already shipped when the audit was written.** Nine separate features below carry
commit dates of **2026-07-14 through 2026-07-19** — three to five weeks before the
2026-08-20 audit date — meaning the previous pass either read a stale checkout or never
grepped for the new files (`lib/voice/ttsChunker.ts`, `lib/ptt/vocabulary.ts`,
`lib/ptt/systemAudioMute.ts`, `components/bar/barSend.ts`, `lib/chatQuotaGate.ts`,
`components/chat/AgentThreadCard.tsx`, etc. — none of which existed under the names the old
audit searched for, but all of which existed under new ones). This is a much larger version
of the "audit described weeks-old code as absent" pattern flagged in the reconciliation
brief — it turns out to apply to nearly this entire file, not one isolated item.

| # | Item | Old verdict | Current verdict | Landed |
|---|---|---|---|---|
| 1 | Voice output / TTS + barge-in | Absent (H) | **Present** — chunked synth, filler phrase, PTT-hold barge-in, typed-reply opt-in pref | 2026-07-14 |
| 2 | Usage limiter / paywall in the bar | Absent (H) | **Present** — pre-send gate (typed) + pre-capture veto (PTT), cross-window IPC to the shared modal | 2026-07-14 |
| 3 | PTT context-vocabulary boosting | Absent (H) | **Present** — user vocabulary + immediate OCR + 120s rewind-frame OCR, capped/deduped, sent as `keywords` | 2026-07-14 |
| 4 | Spoken-language auto-detection for PTT | Absent (M) | **Present (feed-forward variant)** — `voiceLanguages` candidate-set gate + detected-language-forwards-to-next-turn | 2026-07-14 |
| 5 | System-audio mute during PTT | Absent (M) | **Present** — WASAPI via a long-lived C# helper, mute-gate/restore-unconditional exactly mirroring Mac | 2026-07-14 |
| 6 | About-User contextual profile | Absent (M) | **Present** — feeds the realtime voice session's system instruction (same scope caveat as Mac) | 2026-07-14 |
| 7 | Snooze ("disable for 2 hours") | Absent (L) | **Present-different** — right-click menu item ships, but silences proactive *notifications*, not the bar itself | 2026-07-16 |
| 8 | PTT lock/hands-free (double-tap) | Absent (L) | **Present** — tap-to-lock reducer with Mac's exact 220ms/400ms windows, **default ON** (Mac defaults off) | 2026-07-15 |
| 9 | Chat-quality rendering — agent spawn/completion cards specifically | Absent (H, as a blanket claim) | **Partially present** — spawn/completion cards + hover-copy + attachment-strip rendering now exist; tool-call cards, discovery cards, resource strip, and metadata popover remain genuinely absent | 2026-07-16/19 |

Two smaller corrections, not status flips:
- The old file's Windows-baseline citation list names `AskPanel.tsx` and
  `components/overlay/Waveform.tsx` — **neither file exists**. The input surface is now
  `components/bar/BarChatSurface.tsx`, and the waveform was merged into the WebGL orb itself
  (`orb/waveform.ts`, design pivot dated 2026-07-11 in-source) rather than living as a
  separate 24-bar DOM component.
- File-attachment drag-and-drop now exists in the app — but on the **main-window** Hub Ask
  bar (`components/home/hub/HubAskBar.tsx`, landed 2026-07-16-ish alongside the attachment
  strip), not on the floating bar's input. The bar-specific gap the old audit described is
  still real; it's just no longer true that the feature is absent from Windows entirely.

What did **not** change, verified against current source: chat-quality rendering (tool-call
cards, discovery cards, resource strip, metadata popover), rating/share-link on responses,
file-attachment drag-and-drop on the *bar's own* input, draggable/resizable bar window,
background blur/vibrancy, the two-shortcuts-vs-one split, and live cross-monitor cursor
follow. All eight remain genuinely absent or weaker, exactly as the old audit described,
just re-verified against today's file layout and line numbers.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Chat-quality rendering (tool-call cards, agent-spawn/completion cards, discovery cards, resource strip, metadata popover) | `AIResponseView.swift` | **Partially present** — agent spawn/completion cards, hover-copy, and an attachment strip now render (`AgentThreadCard.tsx`, `ChatMessages.tsx`); tool-call cards, discovery cards, resource strip, metadata popover still absent | H |
| Voice output / TTS read-aloud of AI replies + barge-in | `FloatingBarVoicePlaybackService.swift`, `PTTVoiceOutputCoordinator.swift` | **Present** — chunked synth, filler phrase, PTT-hold barge-in; typed-reply speech is an opt-in pref with no Settings UI yet | H → now a UI-polish gap, not a capability gap |
| Screen context is a real image (multimodal) vs OCR text only | `ScreenCaptureManager.swift` (WebP/JPEG capture attached to the query) | **Weaker** (`screenContext.ts` — OCR text only, no image) — unchanged | H |
| Usage limiter / paywall UI in the bar | `FloatingBarUsageLimiter.swift` | **Present** — typed pre-send gate + PTT pre-capture veto, cross-window IPC to the shared modal (`barSend.ts`, `chatQuotaGate.ts`) | H → resolved |
| PTT context-vocabulary boosting (screen OCR + recent activity + user vocabulary → STT correction) | `PTTContextVocabularyProvider.swift` | **Present** for keyword collection/biasing (`lib/ptt/vocabulary.ts`); Mac's deterministic post-STT text corrector (`PTTTranscriptContextualCorrector`) has no Windows port | H → mostly resolved |
| Spoken-language auto-detection for PTT | `PTTLanguageIdentifier.swift` | **Present (feed-forward, no on-device decode)** — candidate-set gating + detected-language-forwards-to-next-turn; true same-turn dual-transcript reconciliation is a documented, accepted gap | M → mostly resolved |
| System-audio mute/duck during PTT recording (echo prevention) | `SystemAudioMuteController.swift` | **Present** — WASAPI mute/restore via a long-lived C# helper process | M → resolved |
| Rating (thumbs up/down) + share-link on responses | `AIResponseView.swift` (`MessageHoverOverlay`, `shareLink()`) | **Absent** — a hover Copy button now exists, but no thumbs up/down and no share-link | M |
| File-attachment drag-and-drop on Ask input | `AskAIInputView.swift` | **Absent on the bar specifically** — the main-window Hub Ask bar gained drag-drop attachments; the floating bar's `BarChatSurface.tsx` input still has no `onDrop` | M |
| Draggable bar + resizable response surface | `DraggableAreaView.swift`, `ResizeHandleView.swift` | **Absent — by design, per the code's own comments** (unchanged) | L |
| Background material (blur/vibrancy vs flat fill) | `FloatingBackgroundModifier.swift` (NSVisualEffectView HUD material) | **Weaker** — flat `rgba(15,15,15,.96)`, no blur/DWM material (unchanged in substance) | L |
| Two independent global shortcuts (Ask AI vs PTT) with per-preset customization | `GlobalShortcutManager.swift`, `ShortcutSettings.swift` | **Weaker** (unchanged) — one shared `Shift+Space` accelerator, tap=toggle/hold=PTT | M |
| Snooze ("disable for 2 hours") | `FloatingControlBarManager.snooze`, `FloatingBarLaunchPolicy` | **Present-different** — bar right-click menu offers "Disable notifications for 2 hours," but it silences proactive notifications (`setNotificationSnooze`), not the bar's own summonability the way Mac's does | L → mostly resolved |
| PTT lock/hands-free mode (double-tap to lock listening) | `PushToTalkManager.swift` (`doubleTapForLock`) | **Present** — tap-to-lock latch reducer, Mac's exact 220ms/400ms windows, **default ON** (Mac ships it off by default) | L → resolved |
| Live cross-monitor cursor-follow while the bar is open | `FloatingControlBarWindow.checkCursorScreen` (250ms poll) | **Weaker** (unchanged) — display picked once at reveal, not re-tracked | L |
| About-User contextual profile injected into voice/AI context | `AboutUserCard.swift` | **Present** — `lib/voice/aboutUser.ts` feeds the realtime voice session's system instruction, same "not the typed/PTT-to-text Ask-AI path" scope caveat Mac's own code carries | M → resolved (with the same scope caveat as Mac) |
| Waveform / orb visuals | `VoiceWaveformBars.swift` (5-bar spring physics) | **Present-different** — a single WebGL2 orb (`Orb.tsx`/`orbRenderer.ts`) now renders both the idle orb AND the scrolling waveform (`orb/waveform.ts`, a 2026-07-11 design pivot that folded the old separate `Waveform.tsx` into the orb) — not a gap, a design consolidation | — |

## Chat-quality rendering (tool calls, agent cards, resources, metadata)

**What it is:** How a rendered AI response in the bar shows more than plain text — background
agent activity, discovery cards, attached resources, and a debug/metadata popover.

**Where (Mac):** `AIResponseView.swift`. Content arrives as typed `contentBlocks` (`.text`,
`.toolCalls`, `.thinking`, `.discoveryCard`, `.agentSpawn`, `.agentCompletion`), each rendered by
a dedicated component (`ToolCallsGroup`, `ThinkingBlock`, `DiscoveryCard`, `AgentSpawnCard`,
`AgentCompletionCard`). `message.displayResources` renders as a `ChatResourceStrip`. A
`MessageMetadataPopover` (behind an "info" button) shows model name, screenshot size, memory/task
counts, tool names used, and the full system prompt.

**Windows status: Partially present — corrected from the old audit's blanket "Absent."**
`ChatMessages.tsx` (194 lines as of this pass, up from a much smaller plain-bubble renderer)
now branches on `m.blocks`: a message carrying `agentSpawn`/`agentCompletion` blocks renders as
one or more `AgentThreadCard` components (`components/chat/AgentThreadCard.tsx`, landed
2026-07-19, "B4 / INV-CHAT-1") — a bordered card with a Bot icon, title, a spinning "Running"
indicator or a terminal status pill (`succeeded`/`stopped`/`failed`), and a truncated objective
line. This exists in BOTH the main window and the bar (`compact` prop trims it for the bar's
narrower panel) and directly contradicts the old audit's claim (repeated in its own
"Spotted outside my scope" section) that this rendering is absent. Plain-text bubbles also
gained a hover-revealed Copy button (`CopyMessageButton`, landed 2026-07-16) and user messages
with file attachments render a `ChatAttachmentStrip` above the bubble (landed 2026-07-16).

**What's still genuinely absent, confirmed by grep of `shared/types.ts` and the chat
components:** there is no `toolCalls`/`discoveryCard`/`thinking` block type at all (only
`agentSpawn`/`agentCompletion` exist as card-worthy block types) — so tool-call cards,
discovery cards, a `ChatResourceStrip`-equivalent, and a metadata popover are all still
missing. `Markdown.tsx`'s rendering behavior (headings/lists/fenced code with no syntax
highlighting, `http(s)/mailto`-only links) is unchanged from the old audit's description.
`useChat.ts` still drops `think:`-prefixed status lines rather than rendering them
(`hooks/useChat.ts:1242`, `if (content.startsWith('think:')) return null`) and still resolves
action requests through a native OS approval dialog with a static outcome string appended to
chat afterward (`"Okay, I won't do that."` / `` `I couldn't finish that: ${...}` `` at
`hooks/useChat.ts:1055-1058`, current line numbers — the file has grown substantially since
the old audit's `useChat.ts:198-217` citation, another sign those line numbers were already
stale).

**Value: H, but narrower than before.** Windows' bar/chat surface is no longer "a plain chat
window" — background-agent lifecycle is now visible as a first-class card type. The remaining
gap is specifically tool-call transparency (what the model actually called and with what
arguments), discovery-card structured results, and the metadata/debug popover — real, but a
smaller slice of "agentic experience" than the old audit implied.

## Voice output / TTS read-aloud of AI replies

**What it is:** Whether the bar speaks its answer back to the user, and whether the user can
interrupt it by talking again.

**Where (Mac):** `FloatingBarVoicePlaybackService.swift` (chat-reply TTS) +
`PTTVoiceOutputCoordinator.swift`. Speaks whenever `ShortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled`
is on — always for voice-originated (PTT) queries, optionally for typed ones (default off).
Streams OpenAI TTS in sentence-sized chunks (40-200 char first chunk, 320-800 char follow
chunks, cut at the highest-priority available punctuation boundary) so playback starts before
the full reply is ready; a filler phrase plays while the first chunk synthesizes.
`interruptCurrentResponse()` runs at the start of every new PTT hold (barge-in).

**Windows status: Present — corrected from the old audit's "Absent" (this was the single
largest miss in the prior pass).** `lib/voice/ttsChunker.ts` (landed 2026-07-14, "Track 2 A1")
is a byte-for-byte port of Mac's chunk-boundary algorithm: `FIRST_CHUNK = {min:40, preferred:120,
emergency:200}`, `FOLLOW_CHUNK = {min:320, preferred:520, emergency:800}`, same
sentence-then-clause-then-whitespace-then-hard-cut boundary search. `lib/voice/voiceController.ts`'s
`runChunkedTts` (line 638) pipelines synthesis (kicks chunk N+1's synth while chunk N plays) and
plays a filler phrase for multi-chunk replies only (`useFiller = chunks.length > 1`, line 646).
`interruptCurrentResponse` (voiceController.ts:570) bumps a generation counter and aborts the
in-flight fetch so a barge-in lands promptly. Call chain for the barge-in itself: PTT hold-start
→ `BarApp.tsx:187` `onHoldStart: () => window.omiBar.interruptTts()` → main → renderer's
`ChatBridgeHost.tsx:109` `window.omi?.onBarChatInterrupt?.(() => interruptCurrentResponse())`.

The PTT→spoken-reply loop itself: `BarApp.tsx` PTT commit → `sendFromBar(text, true)` → IPC →
`ChatBridgeHost.tsx` → the shared `useChat().send` → `maybeSpeak(assistantText, true)`
(`hooks/useChat.ts:191-206`) → `speakText(text)` (`voiceController.ts:672`), fire-and-forget,
with a ref-counted `speaking` boolean projected back to the bar orb as the speaking pose.
`speakText` resolves backend TTS first (`/v1/tts/synthesize`, `MAX_TTS_CHARS = 4096`,
`lib/voice/tts.ts:10`), falling back to Web Speech API (`playSystemVoice`, `voiceController.ts:448`)
on failure, with telemetry (`fallback_triggered`, `component: 'voice_tts'`).

**What's still a real, smaller gap:** typed-question replies. `BarChatSurface.tsx`'s submit now
reads `typedVoice` state (`BarApp.tsx:96-98`, `!!getPreferences().floatingBarTypedVoiceEnabled`)
instead of hardcoding `false` — so the *preference* exists and is wired
(`onSubmit={(text) => sendFromBar(text, typedVoice)}`, `BarApp.tsx:691`) — but **no Settings UI
exposes it** (grepped `components/settings/` for `floatingBarTypedVoiceEnabled` — zero hits).
Mac's user-facing toggle has no Windows equivalent yet; the capability is present, the
affordance to turn it on isn't.

**Value: H → now essentially resolved as a capability**, with a residual **L-value UI-polish
gap** (no Settings toggle for the typed-reply case) rather than a hands-free-round-trip-missing
gap.

## Screen context: real image vs OCR text only

**What it is:** What visual information about the screen actually reaches the model when a
query needs it.

**Where (Mac):** `ScreenCaptureManager.swift` captures the actual display as a WebP/JPEG image
— the model gets real pixels.

**Windows status: Weaker — unchanged from the old audit.** `lib/screenContext.ts` is still 36
lines and still does nothing but OCR text: `readCurrentScreen()` calls
`window.omi.screenReadText()` (line 21-24) with no image path anywhere. Called on every
`useChat` send (`hooks/useChat.ts:834,1163`, current line numbers). This file is Track-1-owned
(explicitly flagged "do not edit" in the reconciliation plan) and was not touched by any of the
Track 2 work verified above — the multimodal gap the old audit identified is real and current.

**Value: H.** Unchanged assessment — text-only context is a real capability ceiling for "look
at my screen" queries.

**Note (parity, not a gap, unchanged):** the live per-message OCR path still does not apply
`lib/screenRedact.ts`'s PII/sensitive-app redaction (confirmed both files still exist, still
disconnected from `screenContext.ts`) — redaction only runs in the separate background
memory-extraction job (`lib/screenSynthesis.ts`). Not scored in the table; this affects Mac too
per the original audit's independent Mac-side confirmation.

## Usage limiter / paywall

**What it is:** Whether free-tier chat/voice usage is capped in the bar with an in-context
upgrade prompt.

**Where (Mac):** `FloatingBarUsageLimiter.swift`, gating both typed and PTT bar queries, with an
EARLIER pre-mic-open gate for PTT specifically (`PushToTalkManager.isBlockedByUsageLimit`) plus
a post-transcription belt-and-suspenders check.

**Windows status: Present — corrected from the old audit's "Absent."** `components/bar/barSend.ts`
(landed 2026-07-14, "Track 2 A10") is the single choke point both send paths funnel through
(`BarApp.tsx:175` PTT commit, `BarApp.tsx:691` typed submit both call `sendFromBar` →
`sender.send`). `createBarSender` wraps a `ChatQuotaGate` (`lib/chatQuotaGate.ts`): `send()`
checks `gate.check()` before dispatching, and — matching Mac's earlier PTT-specific gate — a
SEPARATE, synchronous `checkSync()` is wired into `usePushToTalk.ts`'s `startHold()` (line
469-470: "Pre-capture usage veto ... checked BEFORE onHoldStart so a blocked hold neither
barges in on a playing reply nor opens capture") so a hold-start over the cap never opens the
mic at all — the exact two-layer PTT gating (mic-level + post-send) the old audit noted only
Mac had.

A blocked send raises the shared modal via a real cross-window IPC bridge the old audit's
ground-truth doc flagged as needed-but-missing: `barSend.ts:57` calls
`window.omiBar.notifyUsageLimit({message, spoken, popup})` → preload
(`src/preload/index.ts:765` sends `bar:usageLimit`) → main (`src/main/bar/window.ts:989`
`ipcMain.on('bar:usageLimit', ...)`) → forwarded to the main-window renderer →
`ChatBridgeHost.tsx:118` `onBarUsageLimit` raises the popup and, for a voice turn, speaks the
line instead (`spoken: fromVoice, popup: !fromVoice`) — mirroring Mac's split between the
inline/spoken bar notice and the modal-on-main-window popup exactly.

**Value: H → resolved.** This flips one of the two largest items in the old table; the
"confirm with product whether enforcement exists" framing from the old audit is moot — the
client-side gate exists and is wired end to end, both surfaces, both PTT gate layers.

## PTT context-vocabulary boosting

**What it is:** Feeding recent on-screen/app context into STT so it recognizes names, app
terms, and jargon it would otherwise mishear.

**Where (Mac):** `PTTContextVocabularyProvider.swift` — user vocabulary + immediate OCR + 120s
of rewind-frame OCR, capped/deduped to 100 collected / 40 wire-sent keywords, plus a
deterministic client-side `PTTTranscriptContextualCorrector` regex pass on the returned
transcript (brand-name fixes, greeting-target name correction).

**Windows status: Present for collection and wire transport — corrected from the old audit's
"Absent."** `lib/ptt/vocabulary.ts` (landed 2026-07-14, "Track 2 A2") collects from the same
three sources: user vocabulary (`getUserVocabulary()`, from `userVocabulary.ts`, added first for
priority), immediate screen OCR (`window.omi.screenReadText()`), and 120s of rewind frames
(`window.omi.rewindFrames()`). Constants match Mac exactly: `PTT_VOCAB_MAX_COLLECTED = 100`,
`PTT_VOCAB_MAX_WIRE = 40`, `PTT_VOCAB_LOOKBACK_MS = 120_000` (`lib/ptt/constants.ts:89,122,126,129`
— note: same numeric values as Mac's `maxKeywords`/40-term wire cap/120s lookback, independently
confirmed against the ground-truth doc's Mac citations). Collection starts at hold-start
(`startPttKeywordCollection()`, called from `usePushToTalk.ts:322`) and is consumed and joined
into the `keywords` query param at commit (`consumePttKeywords()` → `pttKeywordsParam()` →
`transport.ts:176,180`, sent via `batchTranscribeParams(language, keywords)` to
`/v2/voice-message/transcribe`). All three sources are timeout-guarded and non-throwing (a dead
source contributes nothing, never breaks a turn).

**What's still absent:** Mac's deterministic POST-transcription text corrector
(`PTTTranscriptContextualCorrector` — the "Home are you"→"How are you" style fixes and
greeting-target name correction) has no Windows port; grepped for
`correctOmiBrand`/`PTTTranscriptContextualCorrector`/`contextualCorrect` across `lib/` — zero
hits. This was explicitly flagged as "not requested by this brief, noting only" in the
ground-truth doc rather than built, so it remains a real, smaller, and knowingly-deferred gap
(server-side keyword biasing happens; client-side regex cleanup of the returned text does not).

**Value: H → mostly resolved.** The accuracy-relevant half (biasing the STT provider toward the
right proper nouns) is done; the smaller deterministic-cleanup half is a documented, deliberate
deferral, not an oversight.

## PTT spoken-language identification

**What it is:** Auto-detecting which language the user is speaking, per PTT turn.

**Where (Mac):** `PTTLanguageIdentifier.swift` — two-stage on-device (Parakeet v3 decode →
`NLLanguageRecognizer` classify, biased to the user's configured candidate languages), used to
hint the realtime provider and reconcile a provider transcript that lands outside the candidate
set by swapping in a local decode.

**Windows status: Present, in a feed-forward form that intentionally skips the on-device
decode step — corrected from the old audit's "Absent (static preference language param
only)."** `preferences.ts` gained `voiceLanguages?: string[]` (line 42) as the exact
candidate-set gate Mac's `hasExplicitVoiceLanguages` implements: empty/unset = feature inert,
which is why the OLD audit's observation ("static `language` param") was true for every default
user and remains true for them today — the gate is deliberately opt-in. Once `voiceLanguages`
has ≥1 entries, `lib/ptt/transport.ts` (`resolveTranscribeLanguage`, line 141-147; `rememberDetectedLanguage`,
line 150-153, "Track 2 A2+A3") feeds the last-detected-and-in-candidate-set language into the
NEXT turn's `language` param instead of the fixed preference value — i.e. the provider's own
returned `language` field (confirmed to exist on `/v2/voice-message/transcribe`'s response by
the ground-truth doc's direct read of `backend/routers/chat.py`) is reused as the per-turn
signal, exactly the "prefer what the STT backend already returns over building a local
detector" path the ground-truth doc recommended.

**What remains a documented, accepted gap (not built, and not claimed to be):** there is no
on-device ASR or text-language-ID library, so there is no mid-hold "early hint" and no
same-turn dual-transcript reconciliation (Mac's local-decode swap when the provider's own
transcript lands outside the candidate set) — a turn's OWN transcript can't be retroactively
improved on Windows, only the NEXT turn benefits from what was learned. This matches the
ground-truth doc's own recommendation to treat that as an accepted v1 gap rather than build a
new JS language-ID dependency speculatively.

**Value: M → mostly resolved for the behavioral contract that matters (biasing future turns);
the pure latency/reconciliation optimizations remain absent by design, not oversight.**

## System-audio muting during PTT recording

**What it is:** Silencing whatever's playing through the speakers while the mic records.

**Where (Mac):** `SystemAudioMuteController.swift` — CoreAudio, gated on
`ShortcutSettings.pttMuteSystemAudio` (default true), mute-only-if-playing,
never-touch-a-user-muted-device, unconditional restore.

**Windows status: Present — corrected from the old audit's "Absent."** `preferences.ts` gained
`pttMuteSystemAudio?: boolean` (line 108, default-true via `!== false` reads). The renderer-side
policy module `lib/ptt/systemAudioMute.ts` (landed 2026-07-14, "Track 2 A4") maps PTT machine
effects to mute/restore actions (`systemAudioActionFor`: `startCapture`→mute,
`startDrain`/`stopCapture`→restore), fire-and-forget over IPC so a slow helper never delays a
hold, with the same "restore is always unconditional, mute is pref-gated" split Mac has. The
actual WASAPI work lives in `src/main/audio/systemAudioMute.ts` + a long-lived C# helper
(`src/main/audio/helper/win-audio-helper.csproj`, built via `scripts/build-audio-helper.ps1`) —
exactly the implementation path the ground-truth doc recommended over raw koffi/COM vtable
calls, and it was actually built rather than left as a recommendation.

One deliberate architecture deviation, called out in-source: Mac restores at PTT teardown AND
defensively again right before TTS playback (because its teardown timing isn't fully
deterministic); Windows' comment (`systemAudioMute.ts:18-22`) explains it restores only at the
deterministic PTT-END effects because the STT→LLM→TTS round trip takes seconds, leaving no
self-mute window — "Do NOT add [a restore-before-TTS hook]." This is a reasoned simplification,
not a gap.

**Value: M → resolved.** No Settings UI exposes the `pttMuteSystemAudio` toggle yet (grepped
`components/settings/` — zero hits), matching the same "capability present, Settings-UI
affordance not yet built" pattern seen elsewhere in this file.

## Rating (thumbs up/down) and share-link on responses

**What it is:** Per-message feedback and a one-click shareable link for a response.

**Where (Mac):** `AIResponseView.swift`'s `MessageHoverOverlay` — thumbs up/down, copy, and a
share-link button.

**Windows status: Absent — largely unchanged, with one partial addition.** `ChatMessages.tsx`
now has a hover-revealed `CopyMessageButton` (landed 2026-07-16) — so "copy" parity exists — but
there is still no thumbs up/down anywhere, and no share-link affordance on a chat message.
`lib/shareLinks.ts` exists in the current tree but is scoped to *conversation* share links
(`conversationShareUrl`), not chat/Ask-AI message share links — a different feature that
happens to share a similar name. `ChatMsg`'s type comment ("Server (Firestore) message id — the
handle for rating/report/share," `hooks/useChat.ts:51`) documents an id that COULD support
rating/report/share, but no rating/report/share logic consumes it anywhere in the renderer
(grepped for `thumbsUp`/`rating`/`ThumbsUp`/`ThumbsDown` — no chat-message hits).

**Value: M.** Unchanged from the old audit apart from Copy now existing; feedback loop and
shareability are still absent.

## File-attachment drag-and-drop on Ask input

**What it is:** Dropping a file onto the Ask-AI input to attach it to the query.

**Where (Mac):** `AskAIInputView.swift` — `.onDrop` on the whole input, staged attachments,
capped, previewed, removable.

**Windows status: Absent on the bar specifically — a real correction to where this gap lives,
not to whether it exists.** The floating bar's own input (`components/bar/BarChatSurface.tsx`)
still has no `onDrop`/file handling anywhere (grepped the whole file — no `onDrop`,
`dataTransfer`, or `attachment` reference on the input path). But drag-and-drop DOES now exist
elsewhere in the app: the **main-window** Hub Ask bar (`components/home/hub/HubAskBar.tsx`) has
a real `onDrop` handler (line 82) reading `e.dataTransfer.files`, backed by a shared attachment
layer (`usePendingAttachments()`, `MAX_CHAT_ATTACHMENTS`) — and `ChatMessages.tsx` /
`ChatAttachmentStrip.tsx` render the resulting attachments in the message thread (confirmed
these ARE wired into the main window's chat, landed 2026-07-16). `usePendingAttachments` and the
attachment-strip rendering are never referenced by any `components/bar/**` file — the bar
surface just doesn't hook into that pipeline.

**Value: M.** The old audit's verdict was accurate for the bar specifically, though the
premise that Windows lacks this feature entirely no longer holds — it's a bar-specific gap now,
not an app-wide one.

## Draggable bar position and resizable response surface

**What it is:** Whether the user can move the bar off its default position, and resize the
opened response panel.

**Where (Mac):** `DraggableAreaView.swift` (opt-in, off by default), `ResizeHandleView.swift`
(always active, min 430×250).

**Windows status: Absent — by design, per the code's own comments. Unchanged.** The bar window
is still `movable: false`/`resizable: false` (`src/main/bar/window.ts:212-213`); the max-height
constants moved files (`BAR_WINDOW_MAX_HEIGHT = 640`, `BAR_MAX_HEIGHT_FRACTION = 0.7`, now in
`src/main/bar/placement.ts:13-14` rather than `window.ts` where the old audit cited them) but
carry the identical values, and `BarChatSurface.tsx` now sizes its scrollable list via a
`maxListHeight` prop rather than a fixed `max-h-[340px]` Tailwind class — a refactor, not a
behavior change. Still internal-scroll, still no window resize.

**Value: L.** Unchanged assessment — reads as an intentional simplification, not a bug.

## Background material (blur/vibrancy vs flat fill)

**What it is:** The visual material behind the bar surface.

**Where (Mac):** `FloatingBackgroundModifier.swift` — `NSVisualEffectView` HUD material +
blur/vibrancy.

**Windows status: Weaker — unchanged in substance, one cosmetic value shift.** `bar.css`'s
`.bar-surface` rule is now `background: rgba(15, 15, 15, 0.96)` (line 63; the old audit cited
`rgba(12,12,12,.96)` — a minor since-adjusted shade, not a material change) with the same 1px
border and no blur. The file's own top-of-file comment is unchanged in substance: "The top-edge
bar window is TRANSPARENT (no DWM material) — the page paints everything" (`bar.css:1`).

**Value: L.** Unchanged assessment.

## Two independent global shortcuts vs one shared accelerator

**What it is:** How many distinct hotkeys exist for Ask AI vs PTT, and how customizable each is.

**Where (Mac):** `GlobalShortcutManager.swift` (Ask Omi, ⌘O default) + `PushToTalkManager.swift`
(separate mechanism, Option ⌥ default) + per-preset settings pickers.

**Windows status: Weaker/simpler — unchanged.** `OVERLAY_ACCELERATOR` still resolves to a
single shared accelerator (`DEFAULT_SUMMON_HOTKEY = 'Shift+Space'`,
`src/shared/hotkeyDefaults.ts:7`, wired at `src/main/overlay/shortcut.ts:9`); a tap toggles the
bar, a hold drives PTT (`SummonGesture` + `keyState.ts` sampling, unchanged). `src/main/shortcuts.ts`
still independently maintains a second, separately-rebindable global accelerator for the
full-conversation recording toggle (`Ctrl+Space`, referenced at `shortcuts.ts:138`) — confirming
the old audit's note that the infrastructure for a second Ask-AI/PTT-specific shortcut already
exists in the codebase, just not applied to this feature pair.

**Value: M.** Unchanged assessment.

## Snooze ("disable for 2 hours")

**What it is:** A quick way to temporarily silence the bar without turning it off permanently.

**Where (Mac):** Right-click context menu → "Disable for 2 hours"
(`FloatingControlBarManager.snooze`) — persists a timestamp, clears pending notifications,
re-shows automatically when it expires.

**Windows status: Present-different — corrected from the old audit's "Absent."** The bar now
has a native right-click context menu (`src/main/bar/barContextMenu.ts` +
`barContextMenuTemplate.ts`, landed 2026-07-16, explicitly "ported from macOS
`FloatingControlBarView.barContextMenu`") offering **"Disable notifications for 2 hours"**
(`BAR_SNOOZE_LABEL`, `barContextMenuTemplate.ts:16`), wired to
`setNotificationSnooze(Date.now() + BAR_SNOOZE_MS)` (`BAR_SNOOZE_MS = 2 * 60 * 60 * 1000`,
`barContextMenuTemplate.ts:11,35`) in `src/main/assistants/core/notify.ts:113`.

The in-source comment is explicit about the scope difference: "Windows' snooze silences
proactive NOTIFICATIONS ..., not the bar itself" (`barContextMenuTemplate.ts:13-15`) — i.e. this
silences the proactive-notification pipeline (the audit area covered by
`01-proactive-focus-insight.md`), not the bar's own summonability/launch-policy the way Mac's
`FloatingControlBarManager.snooze` does. A follow-up-worthy question for whoever owns that other
audit area is whether Mac's bar-launch-policy snooze has a distinct Windows equivalent still
missing — out of scope to resolve here, but the affordance the old audit flagged as entirely
absent does now exist under this file's own scope (the bar's context menu).

**Value: L → mostly resolved**, modulo the scope-of-what-gets-silenced nuance above.

## PTT lock/hands-free mode

**What it is:** Locking the mic open (hands-free) instead of physically holding the key down.

**Where (Mac):** `PushToTalkManager.swift` — opt-in `doubleTapForLock`: tap-release under 0.22s
enters a pending-lock window; a second tap within 0.4s locks listening open.

**Windows status: Present — corrected from the old audit's "Absent (hold-only)."**
`lib/ptt/machine.ts` gained a second, orthogonal pure reducer (lines 252-330, "port of macOS
PushToTalkManager's tap-to-lock latch") with `LockPhase = 'idle' | 'pendingLock' | 'locked'` and
handling for `TAP_RELEASED { holdMs, doubleTapForLock }`. The timing constants are an exact
match to Mac's: `TAP_TO_LOCK_MAX_MS = 220` and `DOUBLE_TAP_WINDOW_MS = 400`
(`lib/ptt/constants.ts:89,94` vs. Mac's 0.22s/0.4s). Wired into the hook at
`hooks/usePushToTalk.ts:666-668` (`doubleTapForLock: getPreferences().doubleTapForLock !== false`).
Landed 2026-07-15 ("Track 2" tap-to-lock commit).

**One real behavioral deviation, deliberate and documented in-source:** Mac ships this
opt-in/off-by-default; Windows' `preferences.ts:139-143` comment says plainly "DEFAULT ON —
read as `!== false` so an unset pref latches. Hold-to-talk is unchanged either way." Every
Windows user gets tap-to-lock by default unless they explicitly disable it, the opposite of
Mac's default. No Settings UI exposes the toggle either way yet (grepped
`components/settings/` — zero hits for `doubleTapForLock`).

**Value: L → resolved**, with a worth-flagging default-polarity difference from Mac (product
call, not obviously a bug, but worth confirming was intentional).

## Live cross-monitor cursor-follow while the bar is open

**What it is:** Whether the visible bar relocates if the user moves the cursor to a different
monitor while it's already open.

**Where (Mac):** `FloatingControlBarWindow.checkCursorScreen()`, polled ~250ms, actively
relocates.

**Windows status: Weaker — unchanged.** `showBar()` in `src/main/bar/window.ts:328` still
resolves the target display once, at reveal time
(`screen.getDisplayNearestPoint(screen.getCursorScreenPoint())`); grepped `window.ts` for any
later re-resolution/relocation call (`getDisplayNearestPoint`, `setBounds` used for
DPI-correction and show/hide only, never for a mid-session monitor switch) — none found. The
file's periodic polls (`peekWatch`/`clickWatch`, `window.ts:523,540`) exist for click-through
hit-testing while a collapsed bar is visible, an unrelated concern from cursor-follow.

**Value: L.** Unchanged assessment.

## About-User contextual profile

**What it is:** A compact local snapshot (name, memory facts, overdue/due-today task counts)
injected into the assistant's context so replies can be lightly personalized.

**Where (Mac):** `AboutUserCard.swift` — name / up-to-8 memory facts / task counts, no network
calls at build time, feeding `RealtimeHubController`'s system instruction (Mac's own code has
zero references to this card from the bar/floating-window files directly — its only confirmed
consumer is the realtime hub).

**Windows status: Present — corrected from the old audit's "Absent."** `lib/voice/aboutUser.ts`
(landed 2026-07-14, "Track 2 A9") is a close port: `renderAboutUserCard` produces the identical
`<about_user>` template (name line only if non-empty, up-to-8 facts or "Nothing saved yet.",
overdue/due-today line), sourced from Firebase Auth's `displayName` (via `auth.currentUser`),
`GET /v3/memories` (capped at 8, 120-char truncation), and a new `lib/voice/taskCounts.ts`
(`countDueBuckets`, mirroring the Tasks page's own due-date bucketing logic) for overdue/due-today
counts. `lib/voice/systemInstruction.ts` (same commit) assembles it into the realtime session's
full system instruction alongside persona framing, spoken-language hints (`userLanguagesLine`),
and current datetime/timezone — and, notably, goes further than the ground-truth doc's
"Phase A, no tools" recommendation by also naming real Windows-advertised voice tools
(`get_action_items`, `get_work_context`, `capture_screen`, `semantic_search`, `spawn_agent`),
matching them against what `buildVoiceHubToolCatalog` (`src/main/ipc/voiceTool.ts`) actually
lets the realtime voice session call.

**Same scope caveat the old audit already flagged for Mac applies to Windows too, now
confirmed on both sides:** `getAboutUserCard()` is consumed only from
`lib/voice/voiceController.ts:330`, i.e. it feeds the realtime voice hub's system instruction —
not the typed/PTT-to-text Ask-AI path this doc otherwise centers on (`useChat.ts` has no
`aboutUser` import). The old audit's hedge ("flagging its existence and value, not confirming
exactly which Mac surface uses it") turns out to describe the Windows port equally well.

**Value: M → resolved**, with the same realtime-voice-hub scope caveat Mac's own implementation
carries.

## Waveform / orb visuals (not a gap — noted for completeness)

**Mac:** `VoiceWaveformBars.swift` — 5 bars, real mic RMS + spring-physics idle bounce.

**Windows — corrected description from the old audit, which cited a component that does not
exist.** The old audit described a standalone `overlay/Waveform.tsx` (24-bar, adaptive
noise-gate) used "inline in `AskPanel.tsx`." Neither `overlay/Waveform.tsx` nor `AskPanel.tsx`
exist in the current tree (confirmed by `find` across the whole renderer). What exists instead:
a single WebGL2 orb (`components/orb/Orb.tsx`, driven by `orb/orbAnimator.ts`/`orb/orbRenderer.ts`)
that renders BOTH the idle/listening/thinking/speaking orb states AND the scrolling waveform —
the two were unified. `orb/waveform.ts`'s own header comment dates this explicitly: "the
scrolling amplitude-history visualizer that REPLACES the merged speech blob (design pivot, Chris
2026-07-11...)." Silent samples render as a small dot; audio-active states (recording OR TTS
playback) render evenly spaced rounded-capsule bars sized by live level, with new samples
entering from the right (a "voice-memo row" look) — a materially different visual design from
the old audit's "24-bar adaptive-noise-gate" description, though the same underlying idea
(real-signal-driven bars, not decorative). `BarChatSurface.tsx` and `AgentPillView.tsx` both
consume this same orb, not a separate waveform component.

Not scored as a gap either direction — a design consolidation, and if anything a richer,
single-surface visual identity than Mac's separate 5-bar component.

## Spotted outside my scope

- **Agent delegation / background-agent spawn cards** — the *rendering* of these cards (now
  present on Windows, see "Chat-quality rendering" above) is a Track-1/chat-agent-audit-owned
  correction worth relaying to whichever audit covers `04-chat-agent-runtime.md`: the old
  claim there may carry the same "described as absent, actually shipped mid-July" pattern this
  file's items did.
- **Auto realtime-model selection ("Auto")** — `lib/voice/autoModelSelector.ts` (landed
  2026-07-14) exists and matches the ground-truth doc's contract (`GET /v1/auto/model-pick`
  never returns `"auto"`, always a concrete `geminiFlashLive`/`gptRealtime2` pick, 24h
  client-cache with keep-last-good-pick-on-error fallback) — this is realtime-voice-session
  scope (`07-realtime-voice.md`'s territory per this doc's own excluded-scope note), flagging
  for that audit rather than re-auditing it here.
- **PTT reconnect / device-change / silent-mic escalation** (`lib/ptt/deadMicPolicy.ts`,
  landed 2026-07-14) — also verified to exist in current source, also realtime/continuous-voice
  adjacent territory bordering this doc's PTT-lifecycle scope; flagging for whichever audit
  covers voice-session resilience rather than re-auditing depth here.
- **Proactive notifications rendered in the bar** — unchanged from the old audit's note; still
  flagging for `01-proactive-focus-insight.md`, now with the added wrinkle that the bar's new
  snooze menu item (`barContextMenu.ts`) silences exactly this notification pipeline, so that
  audit should account for it when assessing proactive-notification parity.
- **Query router (chat vs. background-agent classification)** — unchanged from the old audit's
  note; still flagging for the chat-agent audit, not deep-read here.
