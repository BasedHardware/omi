# D7 — fixture audio into simulator and emulator microphones

Status: contract pinned; platform injection is stopped pending two asks
(virtual audio device, capture-source seam). Rebuild timing uses the
gitignored `.local/ios-smoke-rebuild-trigger.dart` /
`.local/android-smoke-rebuild-trigger.dart` touch files, never
`app/lib/main.dart`.

## Injection (honesty)

| Platform | What D7 will feed | Kind | Blocker this turn |
|---|---|---|---|
| Android emulator | QEMU/emulator host audio into `AudioRecord` (16 kHz PCM16 mono) | `platform_mic` | V3 boots with `-no-audio`. That flag cannot be labelled a microphone. V3 is not on `origin/main` yet; dropping `-no-audio` belongs with the emulator lane, not a silent copy onto this branch. |
| iOS simulator | No `simctl` audio-in API. A deterministic file into the simulator mic is the Mac default input fed by a **virtual audio device**. | `platform_mic` only with that device | Adding BlackHole/Loopback is a new dependency. Stopped. |

An in-app capture-source swap (feeding PCM into `CaptureController` /
`PhoneMicSource`) is a **fake**. It is useful for WAL/frame identity and must
be labelled `in_app_fake` with `platform_path_proven: false`. It has not
proven AVAudioEngine or AudioRecord. That seam touches
`app/lib/services/capture/capture_controller.dart`, which App core is
changing for C1 step 4 — D7 will not take the file. Spec for handover, if
approved: a `local_dev`-only, `OMI_DEV_CONTROLS=1` injection port that
accepts 16 kHz PCM16 frames **without** replacing the native start path, so a
later platform_mic run can keep the same journey assertions.

Semantic controls today can observe `captureIdle` and cannot start recording.
A live journey should tap the production record control (Marionette), not add
a `startCapture` RPC, unless App core wants that control as part of the
handover.

## What the journey asserts

Acceptance is **the app heard the fixture**, not that a file played.

- Required: `fixture_audio.heard == true`, the fixture sha256, and
  `content_evidence` of `captured_pcm` (WAL/PCM identity of the 4.9 s clip)
  or `transcript_phrase` (the known LibriSpeech sentence).
- Weak "afplay exited 0" / `file_played` is refused by `validate_injection_receipt`.
- Transcript of the known phrase is the strong form. `local_dev` offline STT
  may be a stub; if the session backend does not transcribe, assert on
  captured PCM/WAL identity instead and say so on the receipt. Do not imply
  STT ran.

j5 (`hermetic-replay` + fake native host) is already an in-app fake. D7 does
not treat a j5 pass as platform microphone proof.

## Fixture

Reuse `backend/testing/release_fixtures/transcription-release-probe.wav`
(exception to the repo `*.wav` gitignore). Manifest
`transcription-release-probe.json`:

- LibriSpeech test-clean `61-70968-0000`, CC-BY-4.0
- uncompressed PCM, **16 kHz, mono, 16-bit** — the same shape
  `PhoneMicSource` / Android `PhoneMicCaptureEngine` / iOS AVAudioEngine
  capture at. Unmodified; we do not transcode before injection.
- 4.905 s
- expected phrase: "He began a confused complaint against the wizard who had vanished behind the curtain on the left."

Do not invent a second clip. Native-event JSON vectors under
`app/test/fixtures/phone_mic_native_events/` are synthetic LCG frames for C5
lifecycle replay, not speech.

## Cost (not yet measured on device)

The clip itself is ~5 s. D7 add-on vs existing cold numbers, once injection
is unblocked:

| Lane | Existing cold `app.started` | D7 add-on (predicted floor) |
|---|---|---|
| iOS simulator | 412 s | clip 5 s + permission/start; not measured this turn |
| Android emulator | 970 s | clip 5 s + dropping `-no-audio` (unknown qemu cost); not measured this turn |

A double of either lane would come from enabling host audio on the emulator,
not from the 5 s clip. Report measured numbers before making D7 routine.

## Stopped (ask before continuing)

1. **New dependency:** virtual audio device for iOS (BlackHole or equivalent).
2. **App seam:** capture-source injection in `capture_controller.dart`.
   Handover spec above if App core should own it.
3. Not a new class: no `Failure-Class` on this branch; ask first.
