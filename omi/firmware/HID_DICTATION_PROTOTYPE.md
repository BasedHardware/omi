# Pendant HID Dictation Prototype (experimental, opt-in)

One-click dictation from the Omi CV1 pendant into an iPhone's focused text
field — **without** a custom software keyboard. The pendant stays a normal Omi
recording device; when the prototype is explicitly enabled it additionally
acts as a standard BLE HID keyboard that types the transcript of what you just
said.

**Status: draft prototype for David's device testing. Not merged, not
released. Default off — production firmware behavior is unchanged.**

## How it works

```
        ┌─────────────── BLE (one link) ───────────────┐
        │                                              │
 iPhone │ audio service 19B10001 (opus, unchanged)     │ Omi CV1
        │ button service 23BA7925 (press/release)      │ (nRF5340)
        │ dictation ctl 19B10041 (status, enable)      │
        │ dictation text 19B10042 (frames)             │
        │ HID service   0x1812 (keyboard reports)      │
        └──────────────────────────────────────────────┘
 1. Hold the pendant button and speak; release to finish.
 2. The app (existing transcription infra) transcribes the utterance.
 3. The app validates the transcript is printable US ASCII and writes it to
    the pendant as bounded GATT frames (new 19B10042).
 4. The pendant types it into the focused field via standard HID key reports.
    No Enter/Return is ever sent — you review and send yourself.
```

Audio capture, segmentation, and transcription all run through the app's
existing paths; the pendant only gains a text-injection channel and an (opt-in)
HID keyboard service. The transcript never travels anywhere except phone →
pendant → focused field.

## Firmware

- New Kconfig `CONFIG_OMI_ENABLE_HID_DICTATION` (default **n**). Production
  `omi.conf` does not enable it; the feature exists only in prototype builds.
- `src/lib/core/hid_dictation.c` — GATT control plane + NCS HIDS keyboard +
  typing engine. `src/lib/core/hid_dictation_core.c` — pure protocol/mapping
  logic, host-tested (`test/host`, `scripts/test-host-hid-dictation.sh`).
- Opt-in state is **RAM-only**: enable via the app, effective after one
  reconnect; any reboot/power-cycle returns the pendant to stock (also the
  recovery path). Nothing is persisted.
- While disabled (the default), the GATT table, advertising payload, and
  disconnect behavior are byte-for-byte stock. The only compiled-in change is
  the small always-present dictation control service (19B10040 family), which
  no stock client reads.
- Safety invariants (all enforced in code and tested):
  - printable US ASCII only; anything else is rejected **whole**, before any
    keypress — no transliteration, no truncation, no Enter;
  - one key held at a time; every press is followed by a release report;
  - every exit path (done / cancel / error / frame timeout / typing budget /
    disconnect / pendant-button panic stop) releases all keys and forgets the
    session — nothing replays after reconnect;
  - bounded: ≤256 chars per session, ≤244 firmware-side frame bytes (the app
    sends conservative 17-byte payloads that fit any negotiated MTU), 3 s inter-frame
    timeout, 30 s typing budget;
  - duplicate session ids are rejected explicitly (each retry uses a new id);
  - HID characteristics require an encrypted link (standard for HID hosts).

## Mobile app

- Developer settings → Experimental → **Pendant HID Dictation** (off by
  default).
- With the toggle on and a supporting pendant connected: tap the pendant
  button once to start an utterance, tap again to finish; the transcript is
  typed into whatever text field has focus on the phone. In HID mode the app
  consumes ALL pendant button events (double tap, long press, raw
  press/release) so no assistant voice command fires from a dictation click.
- Status and every rejection are user-visible in Developer settings under the
  toggle (capturing/transcribing/typing/done/error) and via pendant haptics
  (one pulse on capture start, two on typed, three on failure).
- Lifecycle safety: cancelling, disabling, starting a new capture, or a link
  drop voids any in-flight transcription/send (generation-checked after every
  await, scoped on-device session cancel when frames already went out), and
  the controller never reconnects a dropped link to deliver old text.
- Transcription uses the existing one-shot `/v2/voice-message/transcribe`
  path (network required).

## Build / flash / pair / enable / test / disable / recover

### Build (prototype firmware)

```bash
# from the repo root; Docker required
docker run --rm \
  -v "$PWD/omi/firmware:/omi/firmware" \
  -e CMAKE_PREFIX_PATH=/opt/toolchains \
  ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb \
  bash /omi/firmware/scripts/ci/build-cv1-hid-prototype.sh
```

Outputs in `omi/firmware/v2.9.0/build-hid/`:
`dfu_application.zip` (OTA), `merged.hex` (full flash), `merged_CPUNET.hex`.

### Flash

- **J-Link / nrfjprog (dev fixtures):** flash `merged.hex` (and
  `merged_CPUNET.hex` for a blank network core) per
  [`BUILD_AND_OTA_FLASH.md`](BUILD_AND_OTA_FLASH.md).
- **OTA from a running Omi app:** side-load `dfu_application.zip` via the
  normal firmware update flow. (Downgrade back to release firmware afterwards
  the same way — releases have a higher version string.)

### Pair

1. Flash, then let the pendant boot (green "ready" pulse) and connect it in
   the Omi app as usual.
2. Do **not** pair from iOS Settings first — the prototype is enabled from
   the app (below), and iOS pairing (for the HID half) is expected to happen
   when the HID service is active.

### Enable

1. App → Settings → Developer → Experimental → **Pendant HID Dictation** on.
2. Open the device page / toggle recording off-on so the pendant reconnects.
   The app writes the opt-in to the pendant before disconnecting; on
   reconnect the pendant's GATT table includes the standard HID service and
   its advertisement carries the HID UUID. If iOS shows a pairing prompt,
   accept it (the HID half needs an encrypted link).
3. Focus a text field (e.g. a new iOS Note), tap the pendant button once,
   speak, tap again. The transcript should appear keystroke by keystroke.

### Test matrix (run on device)

| Case | Expected |
|---|---|
| iOS Notes, empty note | transcript types at cursor; no Enter sent |
| Messages chat field | transcript types; user sends manually |
| Third-party app field (e.g. search bar) | transcript types |
| Cancel mid-typing (press pendant button) | typing stops, keys released |
| Non-ASCII speech (accents/emoji in transcript) | app refuses to send (explicit rejection, nothing typed) |
| Reconnect mid-typing | typing stops, nothing retyped after reconnect |
| Repeated dictations back-to-back | each tap-pair is a fresh session |
| Double tap / long press while enabled | consumed by dictation; no assistant action |
| Prototype disabled (default) | pendant behaves exactly like stock firmware |
| macOS / iPad host (cross-check) | keyboard works on any HID host |

### Disable

Toggle off in the app and reconnect the pendant once more (the app writes the
opt-out; the HID service is removed from the GATT table at that disconnect).

### Recover (if anything wedges)

- **Power-cycle the pendant** (long-press to power off, or replug). The
  opt-in is RAM-only, so a reboot always returns to stock behavior.
- Worst case (device unreachable): reflash stock release firmware from
  `BUILD_AND_OTA_FLASH.md` or the OTA archive.

## Known limits (explicit)

- **iPhone + HID coexistence is the experiment.** iOS reserves HID-over-GATT
  devices for the OS. Whether the Omi app's CoreBluetooth link survives with
  an HID service in the pendant's table (and after iOS bonding) is exactly
  what device testing must establish. The macOS/iPad host row in the test
  matrix gives a known-good HID path to separate "HID works" from "iOS allows
  the app link".
- Print transcripts only: US ASCII 0x20–0x7E. Accented characters, emoji, and
  newlines are rejected before typing (by design, no silent mangling).
- No Enter/Return/backspace is ever typed; long transcripts (>256 chars) are
  refused, not truncated.
- Network required for transcription (existing one-shot endpoint).
- Typing pace is bounded (~2 reports per char); long utterances take a few
  seconds to finish typing after the transcript arrives.
- The app must be running and the pendant connected for the full loop; this
  prototype does not work app-less.
- Text lands wherever the caret is — if no field has focus, nothing (visible)
  happens. Some apps swallow HID input or steal focus oddly.

## For reviewers

- `test/host/test_hid_dictation_core.c` — 513 assertions on the pure core:
  mapping completeness/rejections, all-or-nothing validation, session
  duplicate/busy/cancel rules, frame bounds, abort semantics.
- `app/test/unit/hid_dictation_protocol_test.dart`,
  `app/test/unit/pendant_dictation_controller_test.dart` — wire-format
  parity and the press→transcribe→validate→send→status loop, including the
  reject paths.
- Firmware compile: stock build and HID-prototype build both build via the
  Docker NCS 2.9.0 pipeline (see PR body for the exact commands and SHAs).
- Physical device behavior: **not yet verified** — that is the point of this
  draft; the test matrix above is the acceptance script.
