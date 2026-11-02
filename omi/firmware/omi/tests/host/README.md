# Audio packet logic host checks

These tests compile `audio_packet_logic.c`, a shared seam for audio fragmentation and
offline block packing. It is not linked into the firmware until `transport.c` is switched
over in a separate change that needs BLE audio evidence.
They are host unit tests, not nRF5340 emulation or device qualification.

From the repository root:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
  -Iomi/firmware/omi/src/lib/core \
  omi/firmware/omi/src/lib/core/audio_packet_logic.c \
  omi/firmware/omi/tests/host/audio_packet_logic_test.c \
  -o /tmp/cv1-audio-packet-tests
/tmp/cv1-audio-packet-tests
```

For ASan/UBSan replace `-O2` with `-g -fsanitize=address,undefined`.
In ptrace-based containers LeakSanitizer may fail at process exit; run with
`ASAN_OPTIONS=detect_leaks=0` there and report that leak detection was not run.

The suite checks 222,745 table/exhaustive cases plus explicit invalid-input
and boundary assertions. Case count is not a count of independent tests.
It exercises ATT/application-header capacity, all packing offsets for a 440-byte
block and codec lengths 0–160, rejected/short/full enqueue results, and repeated
failures. A literal legacy packer is a byte-compatibility oracle only; the tested
implementation is the same C helper used by firmware.

Packing keeps the existing lossy policy: rejected blocks are not retried, and an
incoming frame survives in the next block on overflow. `ENQUEUED` means the
queue accepted the block, not that media persistence succeeded. The existing
padding/overflow-marker representation is deliberately unchanged. This patch
makes rejection observable; it does not eliminate drops or expand buffers.

Uncovered: Zephyr adapter compilation, radio negotiation and throughput,
sequence/retry/connection concurrency, RTOS queue timing, physical SD persistence,
startup, OTA, power loss, audio quality, and full end-to-end capture. The monitor
counter still counts write attempts rather than durable writes. No firmware
metadata or checksum format is changed.
