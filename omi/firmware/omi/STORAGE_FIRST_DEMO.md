# Storage-first CV1 demo firmware

This experimental CV1 build applies the same reliability boundary used by
offline-first recorders: the pendant's SD ring is the authoritative audio
source, and the phone is a resumable synchronization peer.

## Behavior

- Every encoded Opus frame is accepted by the ordered storage packer before any
  optional live BLE preview.
- Temporary SD power, mount, queue, or write backpressure retains the exact
  frame and prevents later frames from overtaking it.
- Terminal SD failure may fall back to live BLE so simultaneous media failure
  does not force avoidable loss.
- Live preview is disabled in this demo. This avoids duplicating the same audio
  through the live stream and subsequent ring drain until both paths share a
  capture identity that the apps can deduplicate.
- The existing bounded ring protocol remains the retrieval path: READ_BEGIN,
  exact sequence range, byte CRC, durable phone registration, then ADVANCE.

The demo reports firmware `3.0.29`. It must not be published as a production
release. Flash it only onto the designated second CV1. Retain a hardware
recovery path because an older OTA image may be rejected as a downgrade.

## Build

Run the regular CV1 gate from this branch:

```sh
docker run --rm \
  -v "$PWD/omi/firmware:/omi/firmware" \
  -e CMAKE_PREFIX_PATH=/opt/toolchains \
  ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb \
  bash /omi/firmware/scripts/ci/build-cv1.sh
```

Use `dfu_application.zip` for an app-driven OTA and `merged.hex` for a wired
full flash.

## Physical validation

Use a fresh or fully drained test CV1 so old ring records cannot contaminate the
result.

1. Record a timestamped reference track for 10 minutes while connected.
2. Disable phone Bluetooth for 2 minutes without stopping the reference track.
3. Re-enable Bluetooth, background the app, and let ring synchronization finish.
4. Repeat with app force-stop, phone reboot, CV1 reboot, weak RF, and a one-hour
   backlog.
5. Compare recovered Opus frames against the reference timeline and the
   firmware's start/end ring sequence.

Required outcomes:

- No silent source-range loss.
- No ADVANCE before the exact range is durably registered on the phone.
- Interrupted ranges restart from their last durable sequence.
- Audio remains chronologically ordered across connected, disconnected, and
  recovered periods.
- Storage saturation or terminal media failure is explicit in diagnostics.

This firmware intentionally sacrifices live transcription latency. Adding live
preview requires one monotonic capture identity stored with each frame and sent
in its BLE header, plus native Android/iOS deduplication before preview is
enabled.
