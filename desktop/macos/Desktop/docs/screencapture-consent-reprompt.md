# Screen-recording consent re-prompt: design note

## Defect

macOS repeatedly shows the "Omi Beta would like to record this computer's screen and
audio" re-confirmation dialog even though the Screen Recording grant is intact
(`tccd`: `Allowed (System Set)`, `DB Action: None`, `promptType: 1`). Two compounding
causes, both ours:

1. **Sampling amplifier.** The app never opens a persistent capture stream. Every
   frame — the ~1 Hz capture tick, the ≤80 px previews, dwell refreshes, PTT OCR,
   suggestion probes — is a brand-new one-shot session: a fresh
   `SCContentFilter(desktopIndependentWindow:)` plus `SCScreenshotManager.captureImage`.
   Measured: **267 `kTCCServiceScreenCapture` authorization requests in 180 s**
   (~5,000/hour), each with a full `SecStaticCodeCheckValidity()`. macOS ties its
   periodic re-confirmation of app-built content filters to session creation, so a
   consent Apple intends to surface rarely is sampled thousands of times an hour and
   fires the instant it comes due.
2. **Retry loop re-arms the dialog.** `captureWindowCGImage` collapsed every error into
   `.failed`, including "The user declined TCCs…". The 3 s tick then opened another
   session, which re-armed the dialog — observed three times in ten minutes.

## Prescription

**A. One long-lived `SCStream` scoped to the frontmost window** (`WindowCaptureStreamEngine`,
behind `ScreenCaptureStreamFeature`). One stream = one authorization at
`startCapture`; window switches go through `updateContentFilter` on the live stream and
resizes through `updateConfiguration`, not new sessions. All existing capture entry
points (`captureWindowCGImage`, including the ≤80 px preview requests, which are served
by downscaling the stream's latest full-size frame) route through it, so the auth
sampling rate drops from ~1.5/s to roughly one per stream start.

- **Privacy is unchanged.** The filter stays `desktopIndependentWindow` — the stream
  never sees more than the single window the one-shot path saw. A display-scoped
  stream with client-side cropping was rejected precisely because it would move the
  per-window privacy boundary (Rewind exclusions, filtered browser windows) from
  OS-enforced to app-enforced.
- **Cross-window frames: an armed epoch, not a tag.** The stream does not switch
  windows atomically. Between `updateContentFilter(B)` being called and its completion,
  ScreenCaptureKit is still delivering window A's pixels, so a sink that starts tagging
  deliveries with B up front hands a caller asking for B a screenshot of A — possibly a
  Rewind-excluded app. `CaptureFrameSink` therefore accepts frames only inside an armed
  epoch: `beginRetarget()` (before the await) drops the cached frame, releases any
  parked waiter with `nil`, and makes the sink accept NOTHING; `endRetarget(windowID:)`
  (after the await returns) re-arms it for the new target. Everything delivered in
  between is discarded, not relabelled. Pinned by `WindowCaptureFrameSinkTests`.
  Residual, undocumented by Apple: a frame produced under the old filter but queued
  before the change landed could still arrive after `endRetarget`, and nothing in the
  sample buffer identifies which filter produced it. Dogfood check: fast-switch between
  two visually distinct windows and watch for a one-frame lag of the wrong window.
- **Lifecycle.** Torn down on sleep, lock, and `stopMonitoring` (existing pause hooks),
  and after 60 s without a capture request (user idle), so the OS
  screen-recording indicator does not outlive actual use. Rebuilt lazily on the next
  request. A stream the OS stops is torn down and its error classified.
- **Rejected alternatives.** `SCContentSharingPicker` (system window picker) removes the
  re-consent entirely but requires a user gesture per target — incompatible with
  automatic frontmost-window capture. Throttling one-shot captures only lowers the
  sampling rate; the amplifier remains. Display capture + crop regresses privacy.
- **Concurrency.** Every mutation of the stream runs under an actor-internal lock
  (`withStreamLock`). Actor isolation alone is not sufficient — every one of these
  operations awaits a ScreenCaptureKit call and an actor is reentrant across `await`,
  so without the lock a second request interleaves with a half-built stream: two live
  streams, a leak, and a second authorization. The lock is held across configuration
  only, never across the frame wait, and it is bounded (5 s) so a wedged `startCapture`
  degrades to failed ticks rather than a silent hang. `stopCapture()` is awaited
  in-line under the lock rather than detached: awaiting never blocks an actor's
  executor, and holding the lock is what keeps a rebuild from racing the stop and
  briefly running two streams. One `CaptureFrameSink` per stream, never shared — a
  departing stream can emit a late frame or a late `didStopWithError` after its
  replacement exists, and a shared sink would let those poison the new stream's state.
- **Honest caveat.** Whether `updateContentFilter` on a live stream re-runs the TCC
  check is not documented and cannot be established without a live machine; even if it
  does, sampling drops from per-second to per-window-switch (orders of magnitude).
  Dogfood verification: watch tccd `kTCCServiceScreenCapture` request volume
  before/after.

- **Preview semantics shift.** Flag-on, the ≤80 px preview is a downscale of the
  stream's latest frame rather than its own capture, so the preview-similarity skip
  decision can be one frame stale. It self-corrects on the next tick, and the whole
  point is that a preview must not cost a capture session. If the downscale itself
  fails the request fails rather than returning the full-size frame — an off-size image
  would alias differently under `previewScaleDHash` and poison the similarity history.

**B. "User declined TCCs" is terminal, not retried.** New
`WindowCaptureResult.permissionDeclined`, classified from the `SCStreamError`
domain/code (`.userDeclined`) with a message-substring fallback. Outside the known
special system modes (Exposé / Mission Control, which produce the same error
transiently and already had a carve-out), a declined capture now stops monitoring
immediately — no 3 s retry, no 5 s recovery poll, no 60 s background poll — and posts
one banner per session ("Screen Recording Paused") whose click restarts monitoring.
Restart also happens naturally on the existing app-activation path, i.e. at human
timescale rather than timer timescale. The recovery and background-polling loops now
use the classified capture API so a decline mid-recovery exits instead of re-arming
the dialog every 5–60 s. The same applies to the two remaining timer-cadence capture
paths: the dwell refresh (which otherwise backdates its anchor and re-attempts in
~10 s) and the ≤80 px preview (which otherwise falls through to a second, full-size
capture session in the same tick). The one-banner guard is per EPISODE — cleared on
the first successful capture — because a process that runs for weeks meets more than
one re-confirmation and the second must still be explained.

## Flag

`ScreenCaptureStreamFeature`: non-production bundles default ON
(`OMI_PERSISTENT_CAPTURE_STREAM=0` turns it off) for dogfooding; production reads the
PostHog flag `desktop_persistent_capture_stream`, fail-closed, resolved at monitoring
start and cached for the non-MainActor capture path. Flag off = byte-identical
one-shot behavior (plus the terminal declined state, which ships unflagged as a
straight bug fix).

## Verification watchlist (dogfood)

- tccd `kTCCServiceScreenCapture` request rate (was ~1.5/s).
- No recurrence of the `universalAccessAuthWarn` dialog with the grant intact.
- `videoEncoder_restartCount` / `rewind_droppedFrames` churn should drop.
- Capture health UI still recovers across sleep/lock/unlock and window switches.
