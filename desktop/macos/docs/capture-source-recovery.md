# Desktop capture source recovery

## Ownership and scope

`AppState` owns the recording session, conversation and capture attempt. The
microphone and system tap own independent CoreAudio drivers. Cloud capture
feeds their PCM into one `AudioMixer`; local STT feeds independent microphone
and system transcription services.

A microphone watchdog trip requests `Scope.microphone` through
`rebuildCoreAudioCaptureStack`. Only the microphone driver is replaced. The
system tap, mixer buffers/clock, STT services and recording identity stay intact.
The old microphone's physical HAL teardown completes before replacement opens;
session stop or owner replacement during that await revokes recovery.

Explicit stack recovery and local conversation rotation retain
`Scope.allSources`. Rotation must rebind both callbacks to its new local STT
services. Deferred recovery carries its scope with its reason, and a queued
full recovery cannot be downgraded by a later microphone-only request.

## Silent input is evidence, not a hardware diagnosis

The watchdog observes two consecutive quiet PCM windows (peak at or below five
Int16 counts). This can be a muted/quiet input, a permission/route problem or a
driver failure. It does not establish which one happened. Keep authorization
checks before opening HAL and retain all-transport bounded recovery.

The October 8 diagnostics from desktop 0.12.447 showed a USB microphone
repeatedly triggering this policy while local system transcription still
produced segments. Each recovery unnecessarily stopped both capture drivers;
the third detection finalized the entire session as `silent_mic_exhausted`.
The causal defect addressed here is that a microphone-only signal failure
took independently working system capture down with it. The diagnostics do
not prove why the microphone itself was quiet.

At exhaustion, continue the same session only when the current system tap is
capturing and has delivered PCM within the last five monotonic seconds.
`CaptureStreamActivity` belongs to that driver, resets on start/stop, and cannot
be inherited by its replacement. A started tap or old transcript alone is not
liveness evidence. Silent system PCM is valid: later computer speech must still
be captured. No live tap retains the existing stop/armed recovery behavior.
An armed retry still requires live microphone signal before its outbound audio
gate opens; it cannot claim system-only continuation while that gate is closed.

When continuing, leave the microphone open so returning signal is captured.
Expose `isMicrophoneSignalMissing` through the existing Audio status/tooltip,
not a modal and not a global STT error. Its recovery callback is one-shot per
silent episode and current-driver fenced. Live microphone PCM clears the
warning; starting or stopping a session also clears it. Generic stack rebuilds
and PTT policy are not replaced by this continuation rule.

## HAL and watchdog lock ordering

Native fault injection exposed a separate lock inversion: the main thread held
`silentMicWatchdogLock` while resolving the device description through HAL, while
the HAL microphone IO thread waited for that watchdog lock. System PCM continued,
but both microphone recovery and the UI were frozen. This was verified by a
native thread sample, not inferred from the customer's diagnostic export.

Resolve built-in/Bluetooth route facts on `audioQueue` before starting an IOProc,
including route reconfiguration. Watchdog classification and the microphone
callback read the bound facts without calling HAL. Recovery callbacks remain
outside the watchdog lock; physical teardown still runs on the device queue.

## Verification checklist

- [x] Microphone-only recovery preserves pending cloud mixer bytes, tap and
  session/attempt identity
- [x] Full rotation recovery still rebinds both sources
- [x] Deferred full recovery cannot be downgraded
- [x] Stop/new-owner races during physical teardown cannot resurrect capture
- [x] Exhaustion continues a live tap, reports no microphone signal and clears
  the warning on live PCM without restarting
- [x] Never-started, stopped or stale tap cannot authorize continuation
- [x] Permission and no-live-source terminal behavior remain covered
- [x] Watchdog route classification uses bound metadata rather than querying
  HAL while holding its lock; start and reconfiguration both bind the route
- [ ] Named-bundle native microphone/system-audio path exercised, separately
  from synthetic owner/driver tests

Focused regressions: `SharedCaptureSourceRecoveryTests`,
`CaptureStreamActivityTests`, `SilentMicWatchdogRearmTests` and
`SharedCaptureSilentMicRecoveryPolicyTests`. Native QA steps live in
`e2e/flows/audio-recording.yaml`; the existing synthetic capture-lifecycle flow
does not prove microphone or system-tap negotiation.

Customer diagnostic exports can contain transcript text despite their redacted
header. Never commit the export, its transcript text, or account/session IDs.
