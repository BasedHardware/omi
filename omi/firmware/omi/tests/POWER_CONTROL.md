# Power-control host regression

Run `bash omi/firmware/omi/tests/run_power_control_test.sh` from the repository root.
It compiles the production ATT contract with the real settings and mute owners,
faultable NVS and storage-pause shims. It reuses the mute durability suite, tests
cross-characteristic pause/resume, failed writes, malformed ATT writes, and
idempotent shutdown requests. A separate seam compiles the actual shutdown worker
extracted from transport.c and asserts one queued request, the grace delay and
orderly-shutdown dispatch. Source guards pin the UUID and forbid disconnect unmute.
Run `make -C omi/firmware/omi/tests run` for the storage/custody regressions.

The characteristic uses 19B10016 and feature bit 11 (9 is reserved for rename,
10 is mute). Commands 0/2 resume/pause through capture_mute_set(), so pause stays
across disconnect and reboot and gates both TX and storage. Sampling may continue;
there is no second PDM pause/AAD state machine. Command 1 queues turnoff_all() on
a dedicated thread, allowing the system workqueue to keep servicing teardown.
Pending shutdown reads as 1; repeated off commands are idempotent and pause/resume
are rejected once shutdown is queued. The existing 50 ms grace allows an ATT
response to queue; host tests cannot prove over-air acknowledgement delivery.

No target build, flash or hardware access is performed. CV1 qualification must
check shutdown/SD flush, rebooted pause, AAD wake, radio ACK timing, thread stack
headroom and app support for the new UUID/feature bit. No partition, bootloader,
network-core, UICR or signing configuration changes are needed by this branch.
