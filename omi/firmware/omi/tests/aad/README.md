# Connected AAD host coverage

Run `bash omi/firmware/omi/tests/aad/run.sh` from the repository root. Requires a
C compiler with ASan/UBSan. C99 matches the NCS target dialect. Registered in
the existing checks manifest for both local and CI lanes.

- Exhausts the 64 enable/connection/subscription/live/charger/transfer policy
  combinations, including flag-off legacy behavior and live timeout bounds.
- Reuses #14156's pre-roll host tests: oldest-first replay, onset debounce,
  immediate hardware-wake forwarding, stale pre-roll reset, invalid input and
  emit failures. Production `software_vad.c/.h` are the same shared algorithm.
- Includes production `mic.c` through a deterministic kernel/driver seam:
  120000 ms boundary, speech in the final STOP read, quiet sleep entry, WAKE to
  immediate resume, first block without debounce, no SD queue on connected
  wake, batch/CCC transition wake, stale policy generation, cooperative timeout,
  and legacy charging settle. Executes the actual mic and AAD event loops.
- Syntax-checks production `mic.c` with the connected feature off/on and offline
  storage absent. Checks the compile guard that would otherwise call
  `storage_transfer_active()` when its declaration/implementation is disabled.

The seam is single-threaded. It verifies control flow and buffer ownership, not
concurrent kernel scheduling, memory ordering, IRQ timing, driver/DT APIs, GATT
validation or wire sequencing. It does not provide a native_sim/Twister target.
The unrun NCS board builds and all physical acceptance steps are listed in
[PR_DRAFT_NOTES.md](../../docs/PR_DRAFT_NOTES.md). Do not interpret passing host
tests as a measured <300 ms wake bound or proof of preserved first words.
