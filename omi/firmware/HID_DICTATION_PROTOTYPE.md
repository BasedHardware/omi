# Pendant HID Dictation Prototype (experimental, opt-in)

One-click dictation from the Omi CV1 pendant into an iPhone's focused text
field — **without** a custom software keyboard. The pendant stays a normal Omi
recording device; when the prototype is explicitly enabled it additionally
acts as a standard BLE HID keyboard that types the transcript of what you just
said.

**Status: draft, software testing only. Not merged or released. Do not OTA
this prototype onto an only/daily-use pendant.** Hardware testing waits for a
spare CV1 and a verified wired recovery setup. A cable alone is not proof of
recovery: establish the correct debug/programming connection and successfully
restore stock firmware on the spare before testing this image.

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
 1. Tap the pendant button, speak, then tap again to finish.
 2. The app (existing transcription infra) transcribes the utterance.
 3. The app validates the transcript is printable US ASCII and writes it to
    the pendant as bounded GATT frames (new 19B10042).
 4. The pendant types it into the focused field via standard HID key reports.
    No Enter/Return is ever sent — you review and send yourself.
```

Audio capture and segmentation run through the app's existing paths; the
pendant only gains a text-injection channel and an (opt-in) HID keyboard
service. **Transcription is remote:** the utterance audio is uploaded to the
Omi backend (`/v2/voice-message/transcribe`) and the transcript comes back —
both traverse Omi's servers exactly like any other voice message. Only the
final text injection is local (phone → pendant → focused field). Network is
required.

## Firmware

- New Kconfig `CONFIG_OMI_ENABLE_HID_DICTATION` (default **n**). Production
  `omi.conf` does not enable it; the feature exists only in prototype builds.
- `src/lib/core/hid_dictation.c` — GATT control plane + NCS HIDS keyboard +
  typing engine. `src/lib/core/hid_dictation_core.c` — pure protocol/mapping
  logic, host-tested (`test/host`, `scripts/test-host-hid-dictation.sh`).
- Opt-in state is **RAM-only**: enable via the app, effective after one
  reconnect; a successful reboot removes keyboard mode. This is **not firmware
  rollback** and cannot help if the image cannot boot. The opt-in is not
  persisted; Bluetooth bonds may be persisted.
- With the prototype compiled in, the GATT table is NOT identical to stock:
  the small dictation control service (19B10040 family, encrypted perms) is
  always present, and the build enables bond storage / service-changed /
  encrypted HID permissions. With the runtime opt-in OFF (the default) the
  HID service itself is absent, advertising matches stock, and disconnect
  behavior is stock-equivalent — but "byte-for-byte" only holds for builds
  that do not compile the feature in at all (production config).
- Intended safety invariants (software checks below; device behavior unverified):
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

## Safe testing now (no pendant needed)

Run from the repository root:

```bash
bash omi/firmware/scripts/test-host-hid-dictation.sh
HID_SANITIZE=1 bash omi/firmware/scripts/test-host-hid-dictation.sh
```

The normal runner requires a C compiler. The optional sanitizer run requires
AddressSanitizer and UndefinedBehaviorSanitizer support. Both run entirely on
the host; neither connects to a device, transcribes audio, nor flashes anything.

- Pure protocol suite: 540 checks for framing, ASCII mapping and session rules.
- Runtime fault harness: 26 scenarios executing production `hid_dictation.c`
  with test replacements for Zephyr work scheduling, connection management and
  NCS HIDS/GATT calls. Tests inject send/registration failures, missing
  subscriptions, frame and typing timeouts, cancellation at every report
  boundary, disconnect/reconnect without queued replay, and enable/disable.
- The harness records reports **accepted by a fake stack**, not reports delivered
  to an iPhone. Timers are deterministic and locks track nesting; it does not
  exercise thread races, actual Zephyr/NCS APIs, pairing, flash writes or power loss.
  The existing manifest runs this harness in both local and CI check lanes.
- NCS 2.9.0 includes nRF5340 BabbleSim board support, but no full CV1 radio/OTA
  simulation is configured or validated here. That would require the simulator
  components and a dedicated board/peripheral test application. Even a passing
  radio simulation would not establish physical recovery or iOS interoperability.

## Why OTA is deferred

The current source configures MCUboot **overwrite-only**, with updates for both
application and network cores (`omi/sysbuild.conf`). The generated prototype
bootloader has `CONFIG_BOOT_UPGRADE_ONLY=y`, no swap-based revert, and neither
serial recovery nor a firmware loader enabled. The installed bootloader on the
user's pendant has **not** been identified. An OTA transfer succeeding therefore
does not establish that an unbootable image can be recovered wirelessly.

Do not change the bootloader or flash layout through this experiment to try to
add rollback. Before a future hardware run, use the spare to establish its exact
board/bootloader, the matching stock image, and a demonstrated wired restore.
Then test prototype boot, BLE reconnection, ordinary recording and disabling
HID before the typing matrix. OTA and interrupted-update testing remain a later
step on that recoverable spare. Never intentionally interrupt the only pendant.

## Future hardware procedure (blocked until recovery is demonstrated)

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

### App build

Both halves must come from this PR; the App Store build lacks this controller.
Follow [the app's iPhone build instructions](../../app/README.md#building-and-deploying-to-iphone)
and use an AOT profile/release build so it opens without a debugger attached:

```bash
cd app
OMI_MOBILE_BUILD_MODE=profile bash setup.sh ios
```

Use the setup wrapper's validated backend/profile configuration and ensure the
phone can reach that backend for one-shot transcription. This task does not
install the app or publish a TestFlight build.

### Flash (spare fixture only)

After a successful stock restore on the spare, use its verified J-Link/SWD
procedure and the matching images described in
[`BUILD_AND_OTA_FLASH.md`](BUILD_AND_OTA_FLASH.md). Do not assume a charging cable
provides programming access. `dfu_application.zip` is a build output, **not an
approved OTA candidate**. No OTA installation instructions are provided until
the spare's recovery and installed bootloader have been verified.

### Pair

1. Flash, then let the pendant boot (green "ready" pulse) and connect it in
   the Omi app as usual.
2. Do **not** pair from iOS Settings first — the prototype is enabled from
   the app (below), and iOS pairing (for the HID half) is expected to happen
   when the HID service is active.

### Enable

1. Use the app built from this PR, with the pendant connected and live
   recording enabled. Turn off **Transcribe Later** for this test.
2. App → Settings → Developer → Experimental → **Pendant HID Dictation** ON.
   Accept the iOS Bluetooth pairing prompt if shown. The app sends ENABLE,
   explicitly disconnects/reconnects, and verifies the resulting HID state.
   Wait for **HID active on the pendant** below the toggle. Activation failure
   leaves the preference off; the status line remains visible for retry.
3. Select a US hardware-keyboard layout and leave Caps Lock off. Focus an
   empty iOS Notes field, tap the pendant button, speak a short English
   phrase, then tap again. Text should appear without an Enter/Send action.
4. Repeat in Messages, then test with the Omi app backgrounded. Background
   execution and HID/audio coexistence are unverified device-test results,
   not guarantees from the passing software tests.

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
| Prototype disabled (default) | pendant behaves stock-equivalent (see firmware notes) |
| macOS / iPad host (cross-check) | UNVERIFIED HYPOTHESIS: standard HID hosts should accept the keyboard; no hardware test has confirmed it |

### Disable

Toggle **Pendant HID Dictation** OFF in Developer settings (pendant
connected): the app cancels any in-flight dictation, writes DISABLE, cycles
the link, and verifies the HID service is gone (status line confirms). If
verification fails, the toggle remains on and pendant taps remain reserved
for dictation; retry or power-cycle the pendant before disabling again.

### Recover

- If the firmware still boots, a normal CV1 power-cycle clears runtime HID
  opt-in. Prototype control characteristics and bond storage remain.
- If boot or BLE fails, power-cycling is not rollback and OTA may be unavailable.
  Use the spare fixture's previously demonstrated wired stock restore.
- Do not test on an only/daily-use pendant without that recovery path.

## Known limits (explicit)

- **iPhone + HID coexistence is the experiment.** iOS reserves HID-over-GATT
  devices for the OS. Whether the Omi app's CoreBluetooth link survives with
  an HID service in the pendant's table (and after iOS bonding) is exactly
  what device testing must establish. The macOS/iPad host row in the test
  matrix is an optional cross-check, not a known-good result.
- The experimental developer diagnostics are English-only in this draft.
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

- `test/host/test_hid_dictation_core.c` — 540 assertions on the pure core:
  mapping completeness/rejections, all-or-nothing validation, session
  duplicate/busy/cancel rules, frame bounds, abort semantics.
- `test/host/test_hid_dictation_runtime.c` — 26 deterministic fault scenarios
  around production GATT/workqueue glue with mocked OS/stack boundaries.
- `app/test/unit/hid_dictation_protocol_test.dart`,
  `app/test/unit/pendant_dictation_controller_test.dart` — wire-format
  parity and the tap→transcribe→validate→send→status loop, including the
  reject paths.
- Firmware compile: stock build and HID-prototype build both build via the
  Docker NCS 2.9.0 pipeline (see PR body for the exact commands and SHAs).
- Physical device behavior: **not yet verified** — that is the point of this
  draft; the test matrix above is the acceptance script.
