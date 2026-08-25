# Mac→Windows Parity Audit — Floating Bar / Ask AI / PTT

> Scope: depth comparison of the Mac `FloatingControlBar` (bar shell, drag/resize, shortcuts,
> launch policy, usage limiter) vs the Windows top-edge bar; the Ask-AI text/voice input and
> response rendering; PTT ergonomics (lifecycle, vocabulary boosting, language ID, TTS
> playback); and screen-context capture feeding Ask AI. Excludes RealtimeHub/RealtimeOmni
> continuous-voice-conversation internals (owned by the realtime-voice audit) and
> AgentPill/AgentDelegation spawn mechanics (owned by the chat-agent audit) — both referenced
> only where they intersect the bar surface.
>
> Windows baseline checked: `src/renderer/src/components/bar/{BarApp,AskPanel}.tsx`, `bar.css`,
> `src/main/bar/{window,placement,gesture,keyState}.ts`, `src/main/overlay/{ipc,shortcut}.ts`,
> `src/renderer/src/lib/ptt/{machine,gate,capture,transport,constants}.ts`,
> `src/renderer/src/hooks/{usePushToTalk,useChat}.ts`, `src/renderer/src/components/orb/Orb.tsx`,
> `src/renderer/src/orb/{orbAnimator,orbRenderer}.ts`, `src/renderer/src/components/overlay/Waveform.tsx`,
> `src/renderer/src/components/chat/ChatMessages.tsx`, `src/renderer/src/components/TranscriptPopup.tsx`,
> `src/renderer/src/lib/{screenContext,capture/systemAudio}.ts`.

## Summary table

| Feature | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| Chat-quality rendering (tool-call cards, agent-spawn/completion cards, discovery cards, resource strip, metadata popover) | `AIResponseView.swift` | **Absent** (plain markdown bubbles only) | H |
| Voice output / TTS read-aloud of AI replies + barge-in | `FloatingBarVoicePlaybackService.swift`, `PTTVoiceOutputCoordinator.swift` | **Absent** in the bar's hold-to-talk flow | H |
| Screen context is a real image (multimodal) vs OCR text only | `ScreenCaptureManager.swift` (WebP/JPEG capture attached to the query) | **Weaker** (`screenContext.ts` — OCR text only, no image) | H |
| Usage limiter / paywall UI in the bar | `FloatingBarUsageLimiter.swift` | **Absent** (no client-side quota gate found) | H |
| PTT context-vocabulary boosting (screen OCR + recent activity + user vocabulary → STT correction) | `PTTContextVocabularyProvider.swift` | **Absent** | H |
| Spoken-language auto-detection for PTT | `PTTLanguageIdentifier.swift` | **Absent** (static preference language param only) | M |
| System-audio mute/duck during PTT recording (echo prevention) | `SystemAudioMuteController.swift` | **Absent** | M |
| Rating (thumbs up/down) + share-link on responses | `AIResponseView.swift` (`MessageHoverOverlay`, `shareLink()`) | **Absent** | M |
| File-attachment drag-and-drop on Ask input | `AskAIInputView.swift` | **Absent** (text only) | M |
| Draggable bar + resizable response surface | `DraggableAreaView.swift`, `ResizeHandleView.swift` | **Absent** (fixed top-center, fixed max-height with internal scroll) | L |
| Background material (blur/vibrancy vs flat fill) | `FloatingBackgroundModifier.swift` (NSVisualEffectView HUD material) | **Weaker** (flat `rgba(12,12,12,.96)`, no blur) | L |
| Two independent global shortcuts (Ask AI vs PTT) with per-preset customization | `GlobalShortcutManager.swift`, `ShortcutSettings.swift` | **Weaker** (one shared accelerator, tap=toggle/hold=PTT; only the accelerator itself is rebindable) | M |
| Snooze ("disable for 2 hours") | `FloatingBarLaunchPolicy`/`FloatingControlBarManager.snooze` | **Absent** | L |
| PTT lock/hands-free mode (double-tap to lock listening) | `PushToTalkManager.swift` (`doubleTapForLock`) | **Absent** (hold-only) | L |
| Live cross-monitor cursor-follow while the bar is open | `FloatingControlBarWindow.checkCursorScreen` (250ms poll) | **Weaker** (display picked once at reveal, not re-tracked) | L |
| About-User contextual profile injected into voice/AI context | `AboutUserCard.swift` | **Absent** in bar/PTT scope (Mac wiring is actually in `RealtimeHubController`, out of my scope too — flagged, not confirmed as a hard gap) | M |
| Waveform / orb visuals | `VoiceWaveformBars.swift` (5-bar spring physics) | **Present-different** (24-bar adaptive-noise-gate `Waveform.tsx` + WebGL2 `Orb.tsx`/`orbAnimator.ts`) — not a gap, just a different design | — |

## Chat-quality rendering (tool calls, agent cards, resources, metadata)

**What it is:** How a rendered AI response in the bar shows more than plain text — background
agent activity, discovery cards, attached resources, and a debug/metadata popover.

**Where (Mac):** `AIResponseView.swift`. Content arrives as typed `contentBlocks` (`.text`,
`.toolCalls`, `.thinking`, `.discoveryCard`, `.agentSpawn`, `.agentCompletion`), each rendered by
a dedicated component (`ToolCallsGroup`, `ThinkingBlock`, `DiscoveryCard`, `AgentSpawnCard`,
`AgentCompletionCard`). `message.displayResources` renders as a `ChatResourceStrip`. A
`MessageMetadataPopover` (behind an "info" button) shows model name, screenshot size, memory/task
counts, tool names used, and the full system prompt.

**Windows status: Absent** as inline chat UI. `ChatMessages.tsx` renders every message as one of
two things: a plain user bubble (`whitespace-pre-wrap`) or an assistant bubble running through a
small dependency-free custom `Markdown.tsx` (headings, lists, fenced code as `<pre><code>` with no
syntax highlighting/copy button/language tag, bold/italic, and `http(s)/mailto`-only links —
anything else, including `file://`, renders as literal text, an explicit defense against OCR'd
screen content steering the model into emitting a dangerous href) with a char-by-char reveal
(`RevealMarkdown`). There is no content-block model, no tool-call card, no discovery/agent card,
no resource strip, and no metadata popover — `useChat.ts` has no
`rating`/`share`/`citation`/`toolCall`/`resource`/`attachment` handling at all (confirmed by grep).
**Nuance:** Windows chat isn't incapable of taking action — a message that looks like an action
request is planned and executed through a **native OS approval dialog** (not in-panel UI), with
only a static outcome string ("Done." / "I couldn't finish that: …" / "Okay, I won't do that.")
appended to the chat afterward (`useChat.ts:198-217`). So the gap here is specifically "no inline
rich-content rendering," not "no automation capability at all." The backend also streams ephemeral
`think:`-prefixed status lines ("Checking action items", "Searching memories") that are explicitly
dropped rather than rendered — so even that lightweight "what am I doing" signal never reaches the
UI.

**Value: H.** This is the single biggest capability gap in this audit area — Mac's bar surfaces
the full agentic assistant experience (background agents, tool use, structured resources);
Windows' bar is a plain chat window.

## Voice output / TTS read-aloud of AI replies

**What it is:** Whether the bar speaks its answer back to the user, and whether the user can
interrupt it by talking again.

**Where (Mac):** `FloatingBarVoicePlaybackService.swift` (chat-reply TTS) +
`PTTVoiceOutputCoordinator.swift` (turn-scoped lane arbiter, owned by the separate realtime hub
path). Speaks whenever `ShortcutSettings.hasAnyFloatingBarVoiceAnswersEnabled` is on — always for
voice-originated (PTT) queries, optionally for typed ones. Streams OpenAI TTS (or falls back to
`AVSpeechSynthesizer`) in sentence-sized chunks so playback starts before the full reply is
ready; a short filler phrase can play while the first chunk synthesizes. `interruptCurrentResponse()`
is called at the start of every new PTT hold, so pressing the hotkey again cuts off playback
(barge-in). Playback state drives the bar's visual glow (`isVoiceResponseActive`).

**Windows status: Absent** in this flow. `usePushToTalk.ts`/`AskPanel.tsx` only handle the
input side (mic → transcript → send); no code path in the bar plays synthesized speech for an
assistant reply. `lib/voice/tts.ts` exists but is part of the separate continuous-voice-session
stack (realtime-voice audit scope) — a bare hold-Space-to-ask-then-read exchange in the bar never
gets a spoken answer.

**Value: H.** For a voice-first "ask and hear back" flow — the headline PTT use case — Windows
users must read every reply; there's no hands-free round trip.

## Screen context: real image vs OCR text only

**What it is:** What visual information about the screen actually reaches the model when a
query needs it.

**Where (Mac):** `ScreenCaptureManager.swift` captures the actual display (`CGDisplayCreateImage`
under the cursor) as a WebP/JPEG image, gated by a screenshot-cue heuristic in
`FloatingControlBarWindow.queryNeedsScreenshot` (only ~30% of queries trigger it, to save the
~225ms + payload cost) — the model gets real pixels, so it can reason about diagrams, images, UI
layout, colors, anything non-textual.

**Windows status: Weaker.** `screenContext.ts`'s `readCurrentScreen()` is called on **every**
`useChat` send (`useChat.ts:254`) but only returns OCR **text** (capped 4000 chars) via
`window.omi.screenReadText()` — no image is ever attached to an Ask-AI request. The model can
answer about text that was on screen, but not about anything visual (a chart, a photo, a UI
element's color/position, handwriting an OCR engine mangles).

**Value: H.** This caps what "look at my screen" queries can actually do on Windows — text-only
context is a real capability ceiling for a stated feature (Ask AI referencing the screen), not
just a smaller optimization difference.

**Note (parity, not a gap):** on Windows, the live per-message `readCurrentScreen()` path does
NOT apply the PII/sensitive-app redaction that exists elsewhere in the codebase
(`lib/screenRedact.ts` — password managers, bank/payment app titles, email/card/SSN/token regexes)
— that redaction only runs in a separate, unrelated background memory-extraction job
(`lib/screenSynthesis.ts`), not on the OCR text sent live to Ask AI. Raw OCR (including anything
sensitive visible on screen) goes straight into the prompt. This is not a Windows-specific
regression, though — Mac's `ScreenCaptureManager.swift` was independently confirmed to have "no
redaction/privacy filtering" either, so both platforms currently send unredacted screen content
on the live Ask-AI path. Worth flagging to product as a joint follow-up, not scored in the table
since it isn't a cross-platform delta.

## Usage limiter / paywall

**What it is:** Whether free-tier chat/voice usage is capped in the bar with an in-context
upgrade prompt.

**Where (Mac):** `FloatingBarUsageLimiter.swift`, a shared pool with the main chat page
(`/v1/users/me/usage-quota`). Non-BYOK users past their monthly question/spend limit get a local
assistant message — "You've reached \<limit\>. Upgrade to keep chatting without restrictions." —
and a `.showUsageLimitPopup` notification (upgrade CTA), both for typed and PTT queries.

**Windows status: Absent.** No `quota`/`isLimitReached`/paywall logic was found anywhere in the
bar, `useChat.ts`, or `apiClient.ts` — grepping for usage/limit/quota terms in the renderer only
turns up unrelated retention/rewind/usage-tracking code, none of it gating or messaging a chat
cap.

**Value: H.** Flagging as high-value because it's user-facing monetization/UX, not just polish —
worth confirming with product/billing whether enforcement exists purely server-side (and
Windows just lacks the friendly client message), or whether the cap isn't enforced at all for
this surface.

## PTT context-vocabulary boosting

**What it is:** Feeding recent on-screen/app context into STT so it recognizes names, app
terms, and jargon it would otherwise mishear.

**Where (Mac):** `PTTContextVocabularyProvider.swift`. Per PTT turn, gathers up to 100 keywords
from three sources: user-configured vocabulary (`AssistantSettings.effectiveVocabulary`),
immediate OCR of the active window/screen at PTT start, and OCR of recent-activity screenshots
from the last 120 seconds (via `RewindDatabase`). Keywords feed a local deterministic
`PTTTranscriptContextualCorrector` (brand-name fixes, name-matching for "hey \<name\>" phrases)
applied to every final transcript, and are passed to Deepgram's batch/fallback calls as biasing
context.

**Windows status: Absent.** `usePushToTalk.ts`/`lib/ptt/*` have no vocabulary-collection or
transcript-correction step — `batchTranscribe` posts raw PCM with only a fixed `language` param
(`batchTranscribeParams`); nothing derived from screen OCR or recent activity is passed to STT.

**Value: H.** Directly affects transcription accuracy for proper nouns (app names, contacts,
project terms) — a meaningful everyday-accuracy gap for voice queries.

## PTT spoken-language identification

**What it is:** Auto-detecting which language the user is speaking, per PTT turn.

**Where (Mac):** `PTTLanguageIdentifier.swift`. Two-stage on-device: decode the turn's PCM with a
multilingual Parakeet v3 ASR model, then run Apple's `NLLanguageRecognizer` on the decoded text,
biased toward the user's configured candidate languages. Used to hint the realtime provider and
reconcile transcript language for code-switched phrases.

**Windows status: Absent.** PTT transcription uses a single static `language` value from
`getPreferences().language` (`transport.ts`/`constants.ts`) — no per-utterance detection, no
multi-language candidate set, no code-switch handling.

**Value: M.** Matters mainly for multilingual users; monolingual users see no difference.

## System-audio muting during PTT recording

**What it is:** Silencing whatever's playing through the speakers while the mic records, so
media playback doesn't bleed into the recording or force the user to pause things manually.

**Where (Mac):** `SystemAudioMuteController.swift`. CoreAudio-based, system-wide (default output
device), gated by `ShortcutSettings.pttMuteSystemAudio` (default on). Mutes only if audio is
actually playing and the device isn't already user-muted; falls back to zeroing volume if the
device has no settable mute property; restores exactly on release/cancel.

**Windows status: Absent** in the PTT path. `lib/capture/systemAudio.ts` exists but is loopback
**capture** for meeting recording (feeding the mic-shaped stream for transcription of what's
playing), an unrelated feature — there is no mute/duck of system output while PTT is recording.

**Value: M.** A correctness/polish gap (echo/bleed into the recording, and media doesn't pause
during a quick voice query) rather than a blocking one.

## Rating (thumbs up/down) and share-link on responses

**What it is:** Per-message feedback and a one-click shareable link for a response.

**Where (Mac):** `AIResponseView.swift`'s `MessageHoverOverlay` — hover-revealed thumbs
up/down (toggle semantics, "Thank you!" confirmation), copy button, and a share-link button that
calls `onShareLink?()` and copies the returned URL with a banner confirmation.

**Windows status: Absent.** `ChatMessages.tsx` has no hover actions at all — no rating, no copy
button, no share affordance; confirmed by grep across `useChat.ts` for
rating/share/citation-related terms.

**Value: M.** Feedback loop and shareability are both retention/quality-signal features, not
core-path blockers.

## File-attachment drag-and-drop on Ask input

**What it is:** Dropping a file onto the Ask-AI input to attach it to the query.

**Where (Mac):** `AskAIInputView.swift` — `.onDrop(of: [UTType.fileURL], ...)` on the whole
input, staged via `ChatAttachment.from(url:)`, capped at `kMaxChatAttachments`, previewed inline,
removable, pushed to the provider on send. The follow-up input in `AIResponseView.swift` supports
the same flow.

**Windows status: Absent.** `AskPanel.tsx`'s input is a plain `<textarea>` with no `onDrop`/file
handling; `useChat.ts` has no attachment plumbing for the bar surface.

**Value: M.** Useful but not a core-path feature — most Ask-AI queries are text/voice only.

## Draggable bar position and resizable response surface

**What it is:** Whether the user can move the bar off its default position, and resize the
opened response panel.

**Where (Mac):** `DraggableAreaView.swift` (opt-in via `ShortcutSettings.draggableBarEnabled`,
off by default; position persisted to `UserDefaults`) and `ResizeHandleView.swift` (always
active while a conversation is open; drag-resizes the response window with min 430×250, size
persisted).

**Windows status: Absent — by design, per the code's own comments.** The bar window is
`movable: false`/`resizable: false` (`main/bar/window.ts`); `bar.css` states the surface
"anchors to the top edge" and content "scrolls internally" instead of the window resizing;
`BAR_WINDOW_MAX_HEIGHT = 640` / `BAR_MAX_HEIGHT_FRACTION = 0.7` cap height with internal scroll
in `AskPanel.tsx` (`max-h-[340px]` message list).

**Value: L.** Reads as an intentional simplification (transparent fixed-canvas window
architecture) rather than an oversight — worth confirming with product whether user-repositioning
is wanted, but not clearly a bug.

## Background material (blur/vibrancy vs flat fill)

**What it is:** The visual material behind the bar surface.

**Where (Mac):** `FloatingBackgroundModifier.swift` — `NSVisualEffectView` with `.hudWindow`
material + `.behindWindow` blending (real vibrancy/blur of what's behind the bar), or a flat dark
color if the user enables `solidBackground`. The notch-island surface uses a separate hand-drawn
flat-black shape instead.

**Windows status: Weaker.** `bar.css`: `.bar-surface { background: rgba(12, 12, 12, 0.96); ... }`
— a flat near-opaque fill with a 1px border, no blur/acrylic material (the window itself is
`transparent: true` with no DWM material applied, per the file's own top comment: "no DWM
material — the renderer paints the bar surface itself").

**Value: L.** Visual-polish delta; Windows' flat surface still reads as intentional/clean, just
less "native-blur" than Mac's HUD vibrancy.

## Two independent global shortcuts vs one shared accelerator

**What it is:** How many distinct hotkeys exist for Ask AI vs PTT, and how customizable each is.

**Where (Mac):** `GlobalShortcutManager.swift` registers one Carbon hotkey for Ask Omi
(default ⌘O); PTT is a separate mechanism (its own hold/lock detection, default modifier-only
Option ⌥, configurable to Right-⌘/Fn/Control). `ShortcutSettings.swift` exposes per-preset pickers
for both, plus independent toggles (`askOmiEnabled`, `pttEnabled`, `doubleTapForLock`,
`pttSoundsEnabled`, `pttMuteSystemAudio`, `pttTranscriptionMode`, voice selection/speed, etc.).

**Windows status: Weaker/simpler.** One accelerator (`OVERLAY_ACCELERATOR = 'Shift+Space'`,
rebindable via `overlay:setAccelerator`) drives both: a **tap** toggles the bar open/closed, a
**hold** (detected via `SummonGesture` + `GetAsyncKeyState` sampling in `keyState.ts`) drives PTT.
There is no second independently-bindable shortcut, no modifier-only-key option, and no
per-action enable/disable toggles — only the single accelerator itself is user-configurable.

**Value: M.** Functionally covers both actions with one gesture (arguably simpler for users), but
loses independent rebinding and the granular PTT behavior toggles Mac exposes. **Note:** this
isn't a technical ceiling — Windows' shortcut infrastructure already supports registering a
second, independently-rebindable global accelerator (default **Ctrl+Space**, `main/shortcuts.ts`,
wired in `main/index.ts`) for a *different* feature (a full-conversation recording toggle, out of
this doc's scope). Splitting Ask AI and PTT onto two shortcuts the way Mac does would be additive
work on an existing pattern, not new plumbing.

## Snooze ("disable for 2 hours")

**What it is:** A quick way to temporarily silence the bar without turning it off permanently.

**Where (Mac):** Right-click context menu → "Disable for 2 hours"
(`FloatingControlBarManager.snooze`, `FloatingBarLaunchPolicy`/`FloatingBarUsageLimiter`-adjacent
plumbing) — persists a timestamp, clears pending notifications, re-shows automatically when it
expires (survives relaunch).

**Windows status: Absent.** `main/bar/window.ts` only exposes `setBarEnabled`
(on/off, no timer) via the `overlay:setEnabled` IPC channel; no snooze/auto-re-enable timer
exists.

**Value: L.** A convenience affordance, not core functionality.

## PTT lock/hands-free mode

**What it is:** Locking the mic open (hands-free) instead of physically holding the key down for
long dictation.

**Where (Mac):** `PushToTalkManager.swift` — opt-in `doubleTapForLock`: a quick tap-release
under 0.22s enters a pending-lock window; a second tap within 0.4s locks listening open until the
next press.

**Windows status: Absent.** `lib/ptt/machine.ts`'s state machine is strictly
`HOLD_START`→`RELEASE`-driven — no lock/toggle phase exists; `usePushToTalk.ts`'s Space handling
only supports a physical hold (350ms threshold, then record until key-up).

**Value: L.** A convenience mode for long dictation; hold-to-talk still covers the core PTT use
case.

## Live cross-monitor cursor-follow while the bar is open

**What it is:** Whether the visible bar relocates if the user moves the cursor to a different
monitor while it's already open.

**Where (Mac):** `FloatingControlBarWindow.checkCursorScreen()`, polled every ~250ms, actively
relocates the bar (or grows it out of the notch) to whichever screen the cursor is currently on.

**Windows status: Weaker.** `showBar()` in `main/bar/window.ts` picks the target display once,
at reveal time (`screen.getDisplayNearestPoint(screen.getCursorScreenPoint())`) — there is no
ongoing tracking that relocates an already-visible bar if the user changes monitors mid-session.

**Value: L.** Edge case (multi-monitor users switching screens while the bar is already open);
each new reveal already lands on the correct display.

## About-User contextual profile

**What it is:** A compact local snapshot (name, memory facts, overdue/due-today task counts)
injected into the assistant's context so replies can be lightly personalized without a live
backend call.

**Where (Mac):** `AboutUserCard.swift` — a pure text-block builder (`<about_user>...</about_user>`),
sourced from `AuthService`, `MemoryStorage.getLocalMemories(limit: 8)`, and
`TasksStore.loadDashboardTasks()`. **Caveat:** grepping `FloatingControlBarWindow.swift` and
`FloatingControlBarView.swift` directly found zero references — its only production consumer is
`RealtimeHubController.swift` (realtime-voice audit's file, not read here), so this card feeds
the continuous-voice hub's system instruction, not necessarily the typed/PTT-to-text Ask-AI path
covered by this doc. Flagging its existence and value, not confirming exactly which Mac surface
uses it.

**Windows status: Absent.** No equivalent local profile-snapshot builder was found anywhere in
the Windows renderer/main (searched for `about_user`/`AboutUser`/`userFacts` patterns).

**Value: M.** Personalization signal for response quality; exact user-visible impact depends on
which Mac surface(s) actually consume it (worth the realtime-voice audit confirming, since its
only found call site is in that file).

## Waveform / orb visuals (not a gap — noted for completeness)

**Mac:** `VoiceWaveformBars.swift` — 5 bars, real mic RMS blended with a spring-physics idle
bounce/wobble and an auto-gain envelope so bars stay lively regardless of absolute mic loudness.

**Windows:** Two distinct components, both real-signal-driven: `overlay/Waveform.tsx` (24 bars,
an adaptive learned-noise-floor gate so only above-ambient energy activates the bars, symmetric
mirroring around center) used inline in `AskPanel.tsx` while `ptt.recording`; and a separate
WebGL2 `orb/Orb.tsx` (`OrbAnimator`, 30fps idle / 60fps active) driving the bar's persistent orb
icon across idle/listening/thinking/speaking states, sampled from the same PTT analyser at ~30Hz.
Windows' orb is arguably a richer, more persistent visual identity element than Mac has in this
exact form — not scored as a gap either direction, just architecturally different.

## Spotted outside my scope

- **Agent delegation / background-agent spawn cards** (`AgentSpawnCard`, `AgentCompletionCard`,
  `AgentPill`/`AgentDelegationResolver`/`AgentDelegationExecutor` on Mac) — the *rendering* of
  these cards is covered above under "chat-quality rendering" as absent on Windows, but the
  underlying spawn/delegation mechanics themselves belong to the chat-agent audit.
- **RealtimeHub/RealtimeOmni continuous voice session** (`RealtimeHubController.swift`,
  `RealtimeHubSession.swift`, `RealtimeHubTools.swift`) and its Windows counterpart
  (`src/renderer/src/lib/voice/*`) — out of scope per the realtime-voice audit; referenced above
  only where a Mac PTT/bar file explicitly calls into it (STT routing lane, `AboutUserCard`
  consumer, `PTTVoiceOutputCoordinator`).
- **Proactive notifications rendered in the bar** (`FloatingBarNotification`, the 6s-auto-dismiss
  card, task "Execute" button spawning an agent) — a real Mac-only surface living in the same
  `FloatingControlBarView.swift`/`Window.swift` files, but it's a notification-delivery feature
  more than an Ask-AI/PTT ergonomics one; flagging for whichever audit covers proactive
  notifications (likely `01-proactive-focus-insight.md`) to confirm Windows parity.
- **Query router (chat vs. background-agent classification)** — `FloatingControlBarManager.routeQuery`/
  `AgentPillsManager.classify` is the single largest code block in
  `FloatingControlBarWindow.swift` by line count; not deep-read here since it's agent-delegation
  infrastructure, not bar/Ask-AI/PTT UI — flagging its existence for the chat-agent audit.
