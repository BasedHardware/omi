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
