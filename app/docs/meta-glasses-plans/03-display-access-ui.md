# 03 — Ray-Ban Display on-lens UI

## Goal
Replace the static "Listening" text on Ray-Ban Display glasses with useful live
content: capture state, the latest transcript snippet, and a subtle recording
indicator. This is the "built-in app" payoff for Display-capable glasses.

## Grounding (verified)
- Facade: `startDisplaySession({String? deviceUUID})`, `sendDisplayView(DisplayView)`, `stopDisplaySession()`, `displayStateStream()`.
- Declarative widgets in `third_party/meta_wearables_dat_flutter/lib/src/models/display/display_components.dart`: `FlexBox`, `DisplayText` (styles: heading/body/meta), `DisplayImage`, `DisplayButton`, `DisplayIcon`. `DisplayView = DisplayNode` (typedef).
- Only glasses with `kind == DeviceKind.rayBanDisplay` support this. Provider already has `_startDisplayStatus()`/`_stopDisplayStatus()` gated on that kind.
- Transcript source: `CaptureProvider` (a `CaptureController`) exposes `segments` (`List<TranscriptSegment>`). The provider already holds `_captureController`.

## Steps
1. In `MetaWearablesProvider`, add `void updateDisplayFromCapture()` that builds a `FlexBox` with: a `DisplayText(captureStateLine, style: heading)` and, if segments exist, `DisplayText(lastSegmentText, style: body)` (truncate to ~80 chars). Call `sendDisplayView(...)` only when `_displaySessionActive`.
2. Drive updates: after `startCapture` succeeds, subscribe to capture-segment changes. Simplest: expose a lightweight callback/notifier from `CaptureController` (it's a `ChangeNotifier`) and, while capturing on a Display device, throttle-send (max ~1 update/2s — the display is not a video surface) the newest segment.
3. Respect `displayStateStream()`: only send views once state reaches `DisplayState.started`; stop sending on `stopped`.
4. Keep it minimal and legible: 1–2 text lines, no images initially. No purple. Localize the state line (`context.l10n.listening` etc. — pass the string in from the page as today via `displayStatusText`).
5. Teardown: `stopCapture()` already calls `_stopDisplayStatus()`; ensure the segment subscription is cancelled there.

## Tests
- Unit-test the view-builder pure function (segments + state → expected `FlexBox` JSON via `toJson`) without a real device.
- Contract test: provider references `sendDisplayView` and throttles (a `Duration` constant present).

## Acceptance
- On a Ray-Ban Display (or Mock display device, plan 06), capturing shows a live-updating transcript snippet on-lens, updated no more than ~once/2s.
- Non-Display glasses are unaffected (no display session attempted).
- Analyze clean; tests green; l10n 0 untranslated.
