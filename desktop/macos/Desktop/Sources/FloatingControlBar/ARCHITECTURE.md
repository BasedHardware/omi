# Floating control bar architecture

This package owns the compact/notch presentation, Push-to-Talk coordination, and
the realtime voice transport. UI views render `FloatingControlBarState`; they do
not own a second chat provider or make semantic routing decisions.

## Push-to-talk entry points

`PushToTalkManager` owns the one microphone and turn lifecycle. Every ingress
enters that same state machine and none of them opens a second capture path or
transcript writer: the global shortcut monitor, the automation bridge, and the
composer mic button. `PushToTalkButtonTrigger` holds the click policy — which
existing transition a click resolves to, given the authoritative reducer phase —
and `PushToTalkMicButton` renders it for both the main-window composer and the
floating ask bar. A click carries no hold, so it takes the hands-free lane the
double-tap shortcut already drives: first click locks, next click finalizes.

## Voice typing ("type <text>")

A push-to-talk turn that opens with the spoken word "type" dictates into
whichever app owns the caret instead of asking Omi. It works the way Wispr
Flow does: the hold is recorded whole, nothing is typed while the key is held,
and at key-up the turn is transcribed once with the most accurate recognizer
that can be reached, cleaned up, and pasted in one piece. `VoiceTypeSession`
owns the dictate-or-ask decision and the delivery, and nothing else does.

- **Hold:** the microphone only records. Every route that can end as a
  dictation appends its chunks to the shared turn buffer (`batchAudioBuffer`),
  and that buffer is the one recording the close reads. The realtime hub still
  receives audio until the turn is known to be a dictation.
- **Wake-word probe (advisory).** `VoiceTypeWakeWordProbeSchedule` runs the
  on-device Parakeet model (`PTTLanguageIdentifier.transcribe`) over the first
  few seconds of the hold, at the five voiced-byte thresholds in
  `VoiceTypeWakeWordProbeSchedule.voicedByteThresholds` (from ~0.45 s through
  ~2.3 s of voice). A locked turn's silent lead-in does not trigger them. A
  probe that hears the wake word claims the turn, releases the hub turn
  (`cancelTurn`) so minutes of dictation are not streamed to a model whose
  answer will be cancelled, and publishes `dictationRecognized` so the notch's
  eight dots ease to red (`NotchVoiceMorphGeometry.dictationTintDuration`,
  0.28 s ease-in) while
  keeping whatever motion they have — the waveform while listening, the ring
  while the paste is prepared. When the dictation ends the red eases back out
  over `dictationTintFadeDuration` (0.55 s) into whatever colour the dot is
  returning to (`NotchDictationTint` owns the phases); it never snaps to
  white. A probe that misses is harmless: the closing transcript decides on
  its own.
- **The decision latches one way** (`VoiceTypeSession.claim`): once typing,
  always typing for that turn. Not-typing never latches, because a probe hears
  a couple of seconds of a sentence the user has barely started.
  `VoiceTypeCommandParser` is tri-state for the same reason. A turn already
  claimed reads its closing transcript leniently
  (`payloadAssumingDictation`): the backend may spell the wake word "Tie" or
  "Typed", and losing the dictation over that would be worse than one stray
  word.
- **Key-up.** `continueFinalization` records the paste target
  (`noteRelease`, the frontmost app) before any recognizer runs, then closes
  the turn through one path on every route, `finishVoiceTypingTurn`. The
  reducer stays in `.finalizing` (the bar shows it thinking) until the paste
  lands, exactly as it does for a batch-transcribed question, and every path
  ends the turn.
  1. **Transcribe** (`DictationTranscriber`): the backend's pre-recorded
     recognizer (`/v2/voice-message/transcribe`, `velma-2` first) with the
     on-screen keywords as vocabulary, bounded to 12 s; on failure, timeout,
     or an empty result, the on-device model. With no network only the
     on-device model runs, and a route that latched offline at key-down stays
     offline even if a path comes back mid-hold. A route that already
     produced a backend transcript (omni STT, batch STT after a warm-wait)
     hands it in as `knownTranscript` so the audio is not transcribed twice.
     Every fallback is recorded (`area=voice_typing`). The 12 s cap (and the
     polisher's 6 s) is enforced at the boundary by `DeadlinedOperation`: a
     request stuck before its first cancellation check is abandoned at the
     cap, not waited for. Cancelling the turn cancels the transcription and
     tries no fallback.
  2. **No chat corrector.** `PTTTranscriptContextualCorrector` is not run on
     a dictation. Its greeting rule respells the first word of "<word>, …"
     from on-screen text; live it turned "So, this is a test" into "Sil, …"
     and "hello there" into "hello then". Names are the polisher's job.
  3. **Format** (`DictationFormatter`, always): spoken fillers out, the
     punctuation they leave behind repaired, first letter capitalized.
     English-only fillers ("er") are stripped only for English.
  4. **Polish** (`DictationPolisher`, online only): the lightweight Gemini
     model through the backend proxy (`GeminiClient`, thinking off, 6 s cap)
     rewrites the transcript as the user would have typed it — self-
     corrections applied, spoken "new paragraph" honoured, numbers and
     addresses written out — with the target app and the keywords as context.
     Its output is *accepted*, never trusted: `accept` strips wrapped quotes
     and refuses empty, narrated, unrecognisably resized, or lexically
     unrelated rewrites (at least 60 % of the rewrite's ordinary words must be
     the speaker's; numbers and addresses are exempt, being what the model is
     meant to rewrite), and any refusal, failure, or timeout keeps the
     formatted text.
  5. **Deliver** (`VoiceTypeSession.deliver` → `PasteboardTextInsertionSink`):
     the text goes onto the pasteboard, marked transient for clipboard
     managers, one ⌘V is posted from a private-state event source (a locked
     turn is finished by a chord press, so Option may still be physically
     held), and the previous clipboard is put back 0.6 s later unless the user
     has copied something since. If focus has moved since key-up — live, a
     dock click brought Omi's own window forward mid-hold — the text is
     copied instead and the bar says "Copied — press ⌘V to paste". The
     target is the frontmost app *and its key window* (from the window list,
     no permission needed), so a document or thread switched inside the same
     app while the recognizer ran also copies; an unreadable current focus
     after a known release target is treated the same way. A caret sitting
     right after a word or closing punctuation gets a separating space first
     (`caretNeedsSeparatingSpace`, one character read through
     `AXStringForRange`); after whitespace or an opener — bracket, quote,
     slash, "@" — it does not.
- **Hub commits are gated.** Before any hub commit (`commitHubTurn`, and the
  buffered warm-wait commit), `gateHubCommitOnFinalDictationCheck` decodes
  the opening of the turn on-device and claims a dictation the probes missed.
  Observed live without it: "type what is on my calendar" committed as a
  question, and the model spawned an agent to do the typing itself — not a
  missed dictation but an unrequested action. The gate reads the decode
  leniently, like the probes: it is the same model on the same opening and
  mishears "type" the same ways, so a strict test would re-open exactly the
  gap the probes' lenient test closes.
- **Probe slots are spent when a probe starts**, not when it falls due
  (`beginProbe`): one decode runs at a time, and a slow model load must not
  silently consume the thresholds that pass while it is busy.
- **Offline dictation.** `PTTRoutePolicy.decide` picks the route at key-down
  and checks the network first and unconditionally: with no path
  (`NetworkReachability`, an `NWPathMonitor` started at launch so the first
  turn already knows), the turn takes the `.onDeviceASR` route, is
  transcribed by the on-device model at key-up, and is formatted without the
  polisher. Only dictation completes offline: a question ends as
  `noNetwork` ("No network — say “type …” to dictate offline") rather than
  pretending to be in flight or blaming a provider that was never reached.
- A claimed hub turn is **cancelled, never committed**, so the model never
  answers a dictation out loud.
- A finished turn is journaled as `Typed: <text>` (or `Copied to clipboard:
  <text>`) through the ordinary `recordExchange` on the realtime voice
  surface, so a dictation persists and enters conversation context exactly
  like a spoken question. The continuity key is derived from the turn. The
  write is awaited before the turn ends (bounded to 3 s; at the bound the
  write finishes in the background and the miss is logged), so a lifecycle
  change at turn end cannot drop it.
- Every dictation close terminates the capture lifecycle exactly once
  (`terminateVoiceTypingLifecycle`), whatever the outcome, and a
  backend-transcribed dictation's terminal bookkeeping belongs to that close
  alone — the STT finalization path does not emit its own first.
- `voice_typing_dictate` (automation) runs the same pipeline with no voice
  turn. It is refused while a turn is active and abandoned before delivery if
  one starts mid-run; the real turn's session state is never touched.

Guards: `Tests/VoiceTypingTests.swift` (parser, session, formatter, polisher
acceptance and hint filtering, transcriber fallback order, probe schedule,
route policy).
Harness: `omi-ctl action ptt_manager_turn pcm=<s16le 16k> pace_ms=100 settle_ms=4000`
drives a real-time hold through the production chunk path and reports
`voice_typing_*` diagnostics (`delivery`, `transcriber`, `polished`).

## The pill's glass

`NotchGlassChrome.swift` owns every colour and surface value this package draws
with, and it is the only file here that may. It is `InkGlass` with **two** values
overridden — the appearance the material renders in, and the scrim painted over
it — because the notch pill is **black glass in both themes** (`SBTheme.pillBackground`)
while the rest of the app is pinned light. Everything else (the material, the
corner, the edge alpha, the Reduce Transparency behaviour) is deferred to, not
restated.

- Ink inside the pill is `NotchGlass.primary` / `.secondary` / `.quiet` — the
  white-on-black scale. `Ink.primary` is dynamic and resolves *dark* on the app's
  pinned-light panels, so a run of it here is near-black type on near-black glass.
- A surface that renders on **both** grounds (`PushToTalkMicButton`,
  `VoiceWaveformBars`, shared with the main-window composer) uses `Ink.*` instead,
  precisely because those tokens invert with the ground they land on.
- `floatingBackground(cornerRadius:)` applies the panel. Apply it once per
  **surface**, never per card: docked to the notch every card sits on
  `unifiedFloatingSurface`'s black dock shape, but undocked a notification is a
  bare sibling of the pill with no shared ground, so a card that does not paint
  its own renders over the desktop. Grounding at the call site that knows the
  presentation is what keeps a new card from being born invisible; grounding a
  card as well stacks a second scrim.
- **The panel matches the current rendered surface.** SwiftUI owns the hover
  morph; AppKit snaps once to the entering or settled size so it does not resize
  per animation frame or leave a transparent maximum-size window intercepting
  unrelated controls. The window keeps `hasShadow = false` and the glass draws
  no ambient shadow of its own.

Guards: `Tests/FloatingGlassChromeTests.swift`.

## Realtime hub

`RealtimeHubController` is the single owner of mutable voice-session state and
the facade used by `PushToTalkManager`. Its files are separated by lifecycle,
PTT ingress, provider callbacks, and authorized tool effects, but each
`RealtimeHubController` extension operates on that one state owner. Keep the
dependency direction as follows:

- `RealtimeHubController+SessionLifecycle` owns warm-session creation,
  replacement, context refresh, and output cleanup.
- `RealtimeHubController+PushToTalk` owns begin/feed/commit/cancel ingress.
- `RealtimeHubController+SessionDelegate` translates provider callbacks into
  reducer events and durable tool requests.
- `RealtimeHubController+Tools` performs only already-authorized local effects.
- Policy and value types (`RealtimeHubInputAdmission`, `RealtimeHubTools`,
  `RealtimeHubSessionPolicies`, and `RealtimeTurnPersistence`) stay pure or
  independently testable; they never acquire a second controller instance.

The controller may call the kernel-facing manager for typed context and durable
journal operations, but it must not reach directly into `ChatProvider` or make
agent-routing decisions. Provider tools remain untrusted until the kernel
returns an authorized command.

## Verification

Run the focused Swift tests with `xcrun swift test --package-path Desktop`, then
run `desktop/macos/scripts/agent-logic-harness.sh`. For PTT behavior changes,
also exercise a named `omi-*` development bundle; never target the production
Omi app.
