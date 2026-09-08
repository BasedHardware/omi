# Firmware timing and queue tests

Run `bash omi/firmware/omi/tests/host/run.sh` from the repository root for the
button edge/deadline controller and SD worker queue/wait contract tests. They
compile production code as C99 (matching the NCS 2.9.0 target flags) against a
controllable host kernel seam with ASan and UBSan, requiring a C compiler; the existing checks manifest runs them locally
and in CI. This verifies timing, idle scheduling, and queue wakeup behavior,
not Zephyr integration or physical battery consumption.

The button retains GPIO edge timestamps while the system workqueue is busy,
uses 40 ms debounce, and schedules only active gesture deadlines (300 ms tap,
600 ms release-to-release double window, 3 s hold). A single tap is decided at
300 ms after press unless a second press is underway; release follows after
40 ms. An idle released button has no timer. SD request producers notify a
shared semaphore after publication; the worker checks the connect-flush flag,
priority queue, inactivity flush deadline, then normal writes. Keep all queue
puts routed through `enqueue_sd_request` so neither queue can strand an idle
worker. Power-off write draining and remount sequencing remain owned by
`sd_card.c`.

Use the [NCS 2.9.0 sysbuild lane](../../../scripts/ci/README.md) for target
compilation. Hardware validation must separately measure idle/AAD-sleep current and exercise button gestures,
recording/sync, and SD sleep/wake with buffered audio before release.
