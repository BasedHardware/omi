# D7 — fixture audio into simulator and emulator microphones

Status: contract pinned; platform injection is stopped pending two asks
(virtual audio device, capture-source seam). Rebuild timing uses the
gitignored `.local/ios-smoke-rebuild-trigger.dart` /
`.local/android-smoke-rebuild-trigger.dart` touch files, never
`app/lib/main.dart`.

## Injection (honesty)

| Platform | What D7 will feed | Kind | Blocker this turn |
|---|---|---|---|
| Android emulator | QEMU wav-in (`-audio wav`, `QEMU_WAV_IN_PATH`) into the emulated mic, then `AudioRecord` | `platform_mic` | Owner-authorized on this lane. `-no-audio` is gone. Label `platform_mic` only if AudioRecord actually ran and content evidence exists. |
| iOS simulator | No `simctl` audio-in API. A deterministic file into the simulator mic would be a **virtual audio device**. | not authorized | Owner declined BlackHole/equivalent (system audio driver, admin rights). Do not pick a lighter package. iOS keeps `in_app_fake` with `platform_path_proven: false`; the iOS microphone path stays unproven (L2 gap). |

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
| iOS simulator | 412 s | clip 5 s + permission/start; mic path unproven (no virtual device) |
| Android emulator | 970.1 s | qemu wav-in boot is +1.48 s first / −4.42 s warm vs `-no-audio`; clip ~5 s. Cold app.started not re-run this turn. |

A double of either lane would come from enabling qemu audio, not from the
4.9 s clip. Measured boot deltas live in `LANE.md` / the V3 report.

## Owner rulings (do not reopen here)

1. **iOS virtual audio device: not authorized.** Do not install BlackHole or a
   lighter equivalent. iOS stays `in_app_fake` / unproven mic (L2 gap).
2. **Capture seam:** specified in `.local/inputs/d7-capture-seam-request.md`
   for the architect. Do not edit `capture_controller.dart`.
3. Not a new class: ask before defining a `Failure-Class`.
