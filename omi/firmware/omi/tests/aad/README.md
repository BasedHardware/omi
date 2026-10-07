# Connected AAD host coverage

Run `bash omi/firmware/omi/tests/aad/run.sh` from the repository root. Requires a
C compiler with ASan/UBSan. C99 matches the NCS target dialect. Registered in
the existing checks manifest for both local and CI lanes.

- Exhausts the 128 enable/retention/connection/subscription/live/charger/transfer policy
  combinations, including flag-off legacy behavior and live timeout bounds.
- Reuses #14156's pre-roll host tests: oldest-first replay, onset debounce,
  immediate hardware-wake forwarding, stale pre-roll reset, invalid input and
  emit failures. Production `software_vad.c/.h` are the same shared algorithm.
- Includes production `mic.c` through a deterministic kernel/driver seam:
  120000 ms boundary, speech in the final STOP read, quiet sleep entry, WAKE to
  immediate resume, first block without debounce, no SD queue on connected
  wake, batch/CCC transition wake, stale policy generation, cooperative timeout,
  and legacy charging settle. Runs both retention-on/off, including first-wake
  durable routing without a subscriber and preservation of sampled quiet. Executes
  the actual mic and AAD event loops.
- Syntax-checks production `mic.c` with the connected feature off/on and offline
  storage absent. Checks the compile guard that would otherwise call
  `storage_transfer_active()` when its declaration/implementation is disabled.

- Exhausts 64 transport routing combinations, covering live/subscribed,
  live/unsubscribed, batch, quiet residuals and charging-independent destination
  ownership. Verifies durable-before-notify ordering, send-failure fallback,
  capability enabled/ready truth table and legacy phone Opus parser compatibility.
- Compiles fresh unedited pusher/features function slices from `transport.c` with
  GATT/ring mocks. Executes real producer queue -> pusher -> complete `sd_card.c`
  write API -> raw batch/WAL/media sync for unsubscribe, CCC-on stalled TX,
  AAD residual frames, retained-gap fragment reservation/wrap, timestamps and
  read-handler capability off/unready/on. Full service registration stays outside
  this bounded seam; no copied pusher implementation is tested instead.
- Includes complete production `sd_card.c` against a volatile disk cache plus
  durable disk image. Tests write/sync error ACK rejection and same-frame retry,
  unsynced RTC, reset recovery after dropping every RAM/cache byte, several raw
  slot wraps, whole-batch eviction, cumulative dropped count and recovered frame
  identity. Physical SD power loss/atomicity is not simulated by this model.

The seam is single-threaded. It verifies control flow and buffer ownership, not
concurrent kernel scheduling, memory ordering, IRQ timing, driver/DT APIs, GATT
registration/board API validation or concurrent wire sequencing. It does not provide a native_sim/Twister target.
The unrun NCS board builds and all physical acceptance steps are listed in
[PR_DRAFT_NOTES.md](../../docs/PR_DRAFT_NOTES.md). Do not interpret passing host
tests as a measured <300 ms wake bound or proof of preserved first words.
