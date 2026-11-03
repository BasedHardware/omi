# CV1 application safe mode (3.0.22)

This is the small recovery release ahead of the firmware backlog release, per
David's 2026-11-03 decision. It does not provide MCUboot rollback or repair a
bootloader/network image. Ship only the application image after build-only QA
and jig qualification. No hardware was flashed while implementing this change.

## Behavior

The default limit is three failed boots: the fourth attempt enters recovery.
`PRE_KERNEL_2` priority 0 records the attempt and starts WDT0 (30 seconds).
Watchdog/lockup resets and software resets marked by the fatal handler count;
pin reset, ordinary software reboot, OFF wake and POR start a fresh trial.
The fatal handler uses only retained RAM, a barrier and `NVIC_SystemReset()`.
Pre-hook `PRE_KERNEL_1` hangs remain outside coverage. Recovery also depends on
vendor kernel/device initialization and the network core remaining functional.

Main loads app settings before other app startup, then samples P0.26 for a
continuous three-second hold. A held button latches recovery. The recovery
branch powers SD and PDM enable low, initializes the LED, enables Bluetooth,
loads identity/bonds, registers diagnostics and starts connectable advertising
at 1–2 seconds. SMP, DIS and the configured static BAS service are registered
by Zephyr; application audio/settings/features/time/storage/button/haptic
services and connection callbacks are skipped. No SD initialization, mic,
codec, capture, ring writer, pusher thread or battery work runs. NOR/SPI3 stays
awake for the secondary slot. The existing advertising payload/name stays
unchanged, including its audio service UUID; do not treat that advertisement
alone as proof of capture availability. Read diagnostics.

The red LED pulses for 50 ms each second. Release the entry gesture, then hold
for three seconds and release to enter System OFF. This path samples the GPIO
directly, without the normal button workqueue or capture/storage teardown. It
keeps feeding WDT until System OFF. WDT cannot stop on nRF5340; the normal
`turnoff_all()` path now logs that failure and continues to `sys_poweroff()`.
The jig must verify WDT/power behavior, including whether wake restores SAFE.

On a normal boot, successful advertising plus reaching the main loop starts
a 60-second trial (`CONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S`). Passing clears the RAM
attempt count and stamps GOOD once for that version. No BLE connection is
required. An advertising error still allows the existing offline startup but
cannot pass the self-test. No repeated NVS retry loop is added.

`omi/bootstate` is one 24-byte settings value: LE32 state (1 SAFE, 2 GOOD,
3 TRIAL), LE32 latch reason (0 none, 1 crash loop, 2 button, 3 simulator), and
a NUL-terminated 16-byte firmware string. A SAFE transition writes once;
subsequent SAFE boots compare the cached value and write nothing. Counters
never write flash, including before settings is available. Completed DFU adds
a TRIAL write to clear durable SAFE even for the same firmware version. GOOD
is stamped after the new trial. Failed persistence retains the RAM latch and
logs `Bootstate write failed`; failed settings loading permits recovery with
re-pairing but cannot promise cold-power latch persistence. Only settings/NVS
is used; littlefs, SD metadata and the MCUboot trailer are untouched.

The callback is the pinned Zephyr `MGMT_EVT_OP_IMG_MGMT_DFU_PENDING` event:
it means upload finished writing, not successful cryptographic validation,
activation or a healthy image. It clears latch/count for the *next* boot; the
current recovery session keeps running. An interrupted/failed upload doesn't
clear it. A new firmware string also starts a fresh version trial. The next
bad image can latch again. Never update image 1 (network) during recovery
unless deliberately qualifying that separate operation.

## Retained RAM placement and evidence

The record is 36 bytes inside a 64-byte DTS `zephyr,retained-ram` reservation
at `0x2006FF00–0x2006FF40`. The application linker owns it as `.omi_retained`
NOLOAD. Link assertions reject overlap with data/BSS/noinit (including static
stacks/heaps) and excess size. The node is excluded
from MCUboot's DTS with `CONFIG_MCUBOOT`; bootloader configuration is unchanged.
The PM map is deliberately unchanged; a reserved-memory node by itself would
**not** exclude bytes from NCS Partition Manager's RAM allocation, hence the
explicit linker reservation/assertions instead of shrinking `sram_primary`.

Source evidence: `tools/cv1/pinned-partitions.yml`, retained generated-map
SHA256 `345f6b77aa32407ed2aaf33c8d2d7809b37e37a68f920ad30fd5fb647a4d1f5a`:

| Owner | SRAM range (end exclusive) |
| --- | --- |
| PCD, locked by MCUboot | `0x20000000–0x20002000` |
| Application arena | `0x20002000–0x20070000` |
| Safe-mode record reservation | `0x2006FF00–0x2006FF40` |
| rpmsg/IPC | `0x20070000–0x20080000` |

These ranges prove separation from PCD/IPC, **not** from MCUboot runtime RAM.
No generated MCUboot `.map` or full CV1 SDK was available on the implementation
host. The requested fielded-loader map proof and warm-reset retention test are
therefore still qualification gates, not a claimed pass. Before release, take
the map from the build corresponding to the installed jig baseline (not a
new/unrelated loader), record its artifact/source identity and run:

```sh
python3 omi/firmware/tests/check_retained_ram.py \
  --mcuboot-map "$BASELINE_BUILD/mcuboot/zephyr/zephyr.map" \
  --app-map "$BUILD/omi/zephyr/zephyr.map" \
  --baseline-app-map "$BASELINE_BUILD/omi/zephyr/zephyr.map" > retained-ram-evidence.json
python3 omi/firmware/tests/check_ota_slot_geometry.py \
  --generated "$BUILD/partitions.yml"
```

Archive the JSON with build artifacts. Inspect MCUboot's stack/heap ranges and
any explicit memory clears/copies as well as allocated sections. A map checks
allocations, not arbitrary writes. Reject the slice if any intersects it;
do not move it or change the loader without review. Then use J-Link `mem32
0x2006FF00 16` over WDT, software and lockup resets to demonstrate that the
installed loader does not clobber it. Cold RAM is not guaranteed; durable NVS
SAFE, rather than RAM, provides the cold-power guarantee. The existing source
`boards/omi/pm_static.yml` has a documented inconsistent app address; this
change preserves it and pins the retained generated map rather than repairing
flash geometry.

## Host and native simulation

From the checkout root, route tests/builds through the workspace gate:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- make -C omi/firmware/tests test
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  python3 omi/firmware/omi/sim/run.py \
  --cache /Volumes/Ephemeral/scratch/cv1-lab/safemode/sim --safe-mode
```

Host tests execute the production state machine against reset-register, clock,
settings and callback-registration stubs. They assert zero NVS writes in 100
pre-settings crashes; SAFE writes once across 100 subsequent recovery boots;
cold reload; failed and completed DFU callbacks; same-version recovery;
version change; uptime/advertising gates; saturation; normal reset classes;
and no false latch over 100 sporadic watchdog resets separated by good trials.
The suite also runs the existing audio-packet and nine-milestone parser tests,
slot geometry and the release build guard. It does not emulate torn NVS writes,
WDT enforcement, Nordic faults, Bluetooth or MCUboot.

`--safe-mode` first checks the unchanged nine normal-boot tokens. It then
boots `safe-mode.conf`, boots `dfu-finished.conf` without forcing the latch (so
SAFE must reload from real simulated NVS), delivers a synthetic mcumgr callback,
and boots normally again to check TRIAL → GOOD. All runs share the cache's
flash backing file. It requires `Safe mode initialized: BLE DFU only`,
`Safe mode feed loop started`, and a second watchdog feed, and rejects
codec/mic/SD startup in recovery. Normal tokens are not fabricated on safe
boots. Only callback delivery and hardware boundaries are stubbed; NVS is real
Zephyr. Simulator RAM does not survive process exit. Use a dedicated cache;
delete its flash backing file to clear durable state. See `omi/sim/README.md`
for the Linux/amd64 Docker requirement and disposable engine setup.

## Jig bench plan (requires separate flash authorization)

Use the DK-probed board, J-Link, no antenna, and a reachable BLE central. Keep
an app-only known-good OTA package ready before loading a fault build. Do not
replace the fielded MCUboot, UICR, network image, partition map or keys. Full
factory hex is only for an independently authorized baseline restore; follow
`omi/BUILD.md`/`FLASH_3.0.8/` (network hex then app hex) in that case.

1. **Baseline.** Build per `omi/BUILD.md`, retaining maps/configs. Check release
   version `3.0.22` through DIS. Use the baseline jig console profile and
   locate the control block from its map/J-Link RTT discovery; decode with `tools/cv1/startup_replay.decode_snapshot`/`observe`: all nine
   normal milestones must pass unchanged. Run `tools/cv1/ble_central` scan and
   session with `--expect-serial` per its README. Read `19B10041`: `active=0`,
   `latched=0`; after 60 seconds in the main loop require RTT
   `Safe mode self-test passed` and `omi/bootstate=GOOD`. A later reboot of
   the same version must not print another GOOD write.
2. **Fault builds.** Use a separate build directory per fault. Append a small
   overlay with `CONFIG_DEBUG=y`, `CONFIG_OMI_FAULT_INJECT=y`, and exactly one
   of `CONFIG_OMI_FAULT_INJECT_HARD_FAULT=y`,
   `CONFIG_OMI_FAULT_INJECT_DRIVER_HANG=y`,
   `CONFIG_OMI_FAULT_INJECT_WDT_STARVE=y`. Pass
   `-DEXTRA_CONF_FILE=/absolute/fault.conf -DOMI_DEVELOPMENT_BUILD=ON` to the
   app CMake invocation (with sysbuild, use the app image's `omi_` cache
   variable prefix, e.g. `-Domi_EXTRA_CONF_FILE=...` and
   `-Domi_OMI_DEVELOPMENT_BUILD=ON`). Use the production `omi.conf` as the base.
   Do not publish these artifacts. Omission of the development opt-in must
   fail CMake with `OMI_FAULT_INJECT is forbidden in release builds`;
   the default Kconfig value is n. Inspect the final app `.config` before use.
   The hard-fault variant executes an undefined instruction before BLE:
   `FAULT_INJECT: fatal before BLE`, followed by an immediate fatal reset.
   The driver variant spins at POST_KERNEL priority 0 after the early WDT:
   `FAULT_INJECT: driver init hang`, reset within 30 seconds. The starvation
   variant prints `FAULT_INJECT: watchdog starvation` at uptime 30 seconds,
   then resets by the watchdog about 30 seconds later. After three failed
   boots, require the recovery banner/feed-loop line and `omi/bootstate=SAFE`.
   Injection skips latched recovery. Read retained words with J-Link across
   resets; count must rise, never be clobbered by the loader. Diagnostics
   must report `active=1`, `latched=1`, reason 1, count >= 4 and reset cause.
   Verify 1–2 second advertising, DIS and SMP availability under the existing
   permission policy; record all `CONFIG_MCUMGR_TRANSPORT_BT_PERM_*` values.
   Exercise disconnect/reconnect and a fresh unbonded central as well.
3. **Manual and false-latch checks.** Hold P0.26 throughout the first three
   seconds of main startup; require latch reason 2. Power cycle: SAFE must
   reload. Recover; then repeat watchdog resets more than 60 healthy seconds
   apart and require count cleared each time, no false SAFE. Pin resets and
   ordinary software/OFF reboots must not accumulate failed attempts.
4. **Recovery.** Transfer a good **application/image-0-only** package using
   the Omi phone app or nRF Connect. `ble_central` has no SMP/DFU by policy.
   Require `omi/bootstate=TRIAL` and
   `Safe mode DFU finished: fresh trial on next boot`, then reboot, normal
   milestones and after 60 seconds GOOD. Repeat with a same-version image.
   Interrupt an upload before completion: SAFE must stay set. A failed
   bootstate write must log a warning and must not claim latch clearance.
5. **Power.** Measure average current and compare recovery against a crash
   loop. Confirm P1.10 SD power low and P1.4 PDM enable low. Release the entry
   gesture, hold button for three seconds, then release: require
   `Safe mode entering system off`, System OFF current, no WDT wake after
   more than 30 seconds, and button wake back into SAFE. Also verify the
   normal long-press path reaches `Entering system off; press usr_btn to
   restart` despite the expected watchdog-disable warning. No battery ADC or
   critical-battery shutdown was added to the minimal recovery path.
6. **Custody.** With preexisting recordings, record ring INFO `read_seq`,
   `write_seq`, `ring_id` before entry and compare after recovery. Safe mode
   never calls SD/storage/capture initialization or mutates the raw ring.
   Existing backlog durability improvements are outside this release. Safe
   mode suspends new capture visibly (red pulse/diagnostics); it cannot
   recover recordings lost before entry or promise recording while repairing.
7. **Release.** Run `firmware_release.yml` with publish omitted for build-only
   QA per `AGENTS.md`. Check app artifact version, maps and all bench evidence
   before a separately authorized publish. Retain the installed loader and
   network core; do not flash a sysbuild merged image merely to install this
   app-only release.

## Differences from the scoping snapshot

This origin/main has no diagnostics module, `19B10041` service, GATT-map doc,
or general firmware host-stub test directory. Diagnostics is added at the end
of normal dynamic-service registration; existing UUIDs, attributes and their
order are unchanged. Safe mode advertises the same payload but exposes only
its subset. The small test harness is new; existing audio-packet tests remain.
This snapshot's settings code has no muted fail-closed branch.

Counting only in main, as scoped, would miss every pre-main driver hang.
The count/reset capture therefore moved into the PRE_KERNEL_2 watchdog hook;
main handles settings/manual selection. Settings now load early for the durable
latch. The production transport previously swallowed advertising failures;
its behavior is preserved, with a separate successful-advertising witness for
GOOD. The approved text's DFU-finished event is named DFU_PENDING in NCS 2.9.0.
Recovery needs an explicit TRIAL NVS write (in addition to SAFE/GOOD) for
same-version cold-reset escape. Latch persistence is unavailable if settings
fails; recovery still advertises for re-pairing. No firmware or map claim in
this document substitutes for the remaining real-board qualification.

The RTT claim also differs from code: `startup_replay.decode_snapshot()` checks
`0x20002010` against the *up-buffer descriptor pointer*, not the control-block
address. Production `omi.conf` selects UART console and `CONFIG_LOG=n`, with no
RTT options. This release preserves that configuration. The new BOOTSTATE,
SAFE/GOOD/TRIAL transitions, self-test and DFU witness lines use `printk()` so
they remain observable on the selected console. To observe all existing normal
LOG milestones use the established jig debug/RTT profile with `CONFIG_LOG=y`;
record the real control-block and up-buffer addresses from the baseline map.
The map checker compares RTT symbols against that map, rather than pinning
the control block to a pointer that the decoder uses for a different object.
No RTT backend, sizing or address configuration is changed here.

The scoping claim about default authenticated SMP also needs correction: the
pinned Nordic sample supplies a `MCUMGR_TRANSPORT_BT_PERM_RW` choice default,
whereas Zephyr's transport supplies an authenticated default. This change
preserves the existing permission choice; inspect the final generated config
rather than promising authentication from the upstream default alone. Bonds
are still loaded. Notification hooks and image status hooks are both explicitly
enabled for the completed-upload callback; the build checks those dependencies.
