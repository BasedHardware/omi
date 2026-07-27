# Audio storage and RTC durability tests

These host-native tests exercise production state machines without BLE or SD
hardware. They cover frame packing, ring transfer integrity, SD durability and
recovery, control-response retention, and RTC trust after reboot.

## Contracts covered

| Boundary | Contract |
| --- | --- |
| Frame packing | A rejected SD enqueue cannot consume, duplicate, or reorder the next Opus frame. |
| Storage-first capture | Live preview never precedes local ownership; temporary storage backpressure retains the exact frame and terminal SD failure alone permits live fallback. |
| Voice gate | Silence and isolated noise stay before Opus/SD; debounced activity opens capture and the configured hangover preserves conversational pauses. |
| Transfer completion | CRC32-extended `DONE` bytes stay pinned, and transient notify backpressure retains the response. |
| SD commit ordering | Payload, barrier, CRC/header, barrier, metadata, barrier execute in that order. |
| SD fault matrix | Each of the six write/sync stages is fault-injected before a successful retry. |
| SD recovery | Transient and permanent failures, bounded remounts, no-card boot, terminal live-BLE escape, wrap, legacy partial-tail quarantine, and two-reboot marker replay are covered. |
| Metadata ownership | Active quarantine versus pending ADVANCE performs no metadata callback, sync, or cursor mutation before idempotent reboot recovery. |
| Loss accounting | Wire `dropped_packets` counts only previously durable records made unreachable; a never-committed RAM tail remains diagnostics-only. |
| RTC reboot validity | Repeated boots leave a persisted epoch invalid and records timestamp zero. Live phone sync establishes valid, increasing time; rejected updates are transactional and uptime/epoch arithmetic clamps or rejects its boundaries. |
| RTC marker safety | The production elapsed-recovery seam consumes a one-shot marker before apply, rejects ordinary-reset provenance, fails closed for every IMU prerequisite, and rejects unbounded, wrap-ambiguous, or overflowing elapsed estimates. |

## Run on the host

Use a fresh build directory:

```sh
build_dir=$(mktemp -d /tmp/omi-audio-storage-packer-tests.XXXXXX)
cmake -S omi/firmware/omi/tests/audio_storage_packer -B "$build_dir"
cmake --build "$build_dir"
ctest --test-dir "$build_dir" --output-on-failure
```

Run the same tests with the pinned firmware-release compiler:

```sh
docker run --rm \
  -v "$PWD/omi/firmware:/omi/firmware" \
  ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb \
  bash -lc 'build_dir=$(mktemp -d /tmp/omi-audio-storage-packer-tests.XXXXXX);
    cmake -S /omi/firmware/omi/tests/audio_storage_packer -B "$build_dir";
    cmake --build "$build_dir";
    ctest --test-dir "$build_dir" --output-on-failure'
```

The complete CV1 build gate runs this suite before the NCS sysbuild:

```sh
docker run --rm \
  -v "$PWD/omi/firmware:/omi/firmware" \
  -e CMAKE_PREFIX_PATH=/opt/toolchains \
  ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb \
  bash /omi/firmware/scripts/ci/build-cv1.sh
```

## Hardware-only gaps

Host tests cannot prove SD-controller behavior during physical power loss. Run
power cuts at every commit phase and verify the next boot exposes only the last
durable cursor.

CV1's IMU timestamp is a 24-bit modulo counter at 6.4 ms per tick and wraps
after about 29 h 49 m. System-off duration has no independent upper bound, so a
single wake sample cannot prove how many wraps elapsed. Production therefore
does not restore UTC from this counter: it consumes any legacy one-shot marker
and leaves timestamps zero until live phone synchronization. The host seam
retains bounded-policy fault coverage, but it cannot be enabled on CV1 without
a separate hardware-enforced sub-wrap duration bound.

Hardware RTC qualification must cover normal reboot, DFU, and system-off wake:
all remain invalid until live phone synchronization, marker-clear failure must
not make time valid, and reconnect sync must restore increasing timestamps.
BLE disconnect and toggle tests do not substitute for those power and
clock-source cases.
