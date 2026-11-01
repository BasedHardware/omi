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
implementation is that shared C helper, which is not compiled into the firmware
until the `transport.c` switch above lands.

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

# Codec and diagnostics host checks

From the monorepo root:

```sh
python3 omi/firmware/omi/tests/run_host_regressions.py
```

Requires Python 3 and a C11 compiler with UBSan support. It does not install tools,
load signing keys or access hardware. CC may select the compiler. On a shared
Omi workspace, wrap the command with the workspace bin/omi-heavy runner.

The command retains an isolated temporary build directory and results.json. To
choose an evidence directory outside the checkout, use --output PATH; PATH must
not already exist. The report records source hashes, every command, expected exit
status, stdout/stderr and the measured host-test layer. A failed compiler or
missing sanitizer is a failure, never silently treated as a hardware pass.

Coverage uses the current production source:
- Codec state-size boundaries; assertion expressions evaluated once; init/control
  failures abort before thread/ring initialization; encoder error/zero/positive
  length behavior. Opus and kernel calls are explicit stubs, not the real codec.
- Actual diagnostics snapshot and packet serializer, unavailable defaults,
  counters, reserved bytes, sentinels and 100000 deterministic value combinations.
- The actual production diagnostics GATT callback block, extracted at reviewed
  markers. Tests cover split MTU 23-sized reads across counter updates, refresh,
  invalid/direct offsets, independent synthetic connections, slot reuse and
  pthread read/reset stress. Markers or lifecycle hooks changing require review.
- EATT-enabled compilation must fail at the explicit single-ATT-bearer guard.

The cache fixture uses two synthetic connection slots; the reviewed production
profile currently permits one. GATT copying, Zephyr atomics and spinlocks have
explicit host substitutes. These tests do not prove Zephyr scheduling, the real
ATT implementation, RF reception, audio quality, NAND integrity, OTA/recovery or
release eligibility. An embedded build and separate bounded hardware/OTA evidence
are still required for the corresponding claims.
