# CV1 application safe mode (3.0.24 behavior)

**3.0.24 changes.** 3.0.23 persisted SAFE to NVS and restored it on a cold
boot, and a three-second hold at power-on latched it. A pendant powered on
with a long press, or powered off from SAFE, came back in SAFE on every boot
(the field report behind 3.0.24). 3.0.24 makes recovery RAM-only and the manual
gesture deliberate:

- SAFE is never restored from flash. Only a retained-RAM latch that survived a
  crash-class reset (watchdog, lockup, fatal handler) or a software reset
  selects SAFE. Power-on, OFF wake and pin reset always start a normal trial,
  including when a 3.0.23 image left `omi/bootstate=SAFE` behind.
- Manual entry needs a 10-second hold at power-on **while the charger pin
  reports charging**, sampled throughout. A hold without the charger, or with
  the charger plugged or unplugged mid-hold, boots normally.
- The three-second hold inside SAFE clears the RAM latch before System OFF,
  so the next wake boots normally. The normal long-press power-off waits for
  release before arming the wake interrupt, so a still-held button cannot
  immediately wake the pendant.

The scenario suite in `omi/sim` (README "Scenario suite") encodes each of
these, with the 3.0.23 behavior recorded as `baseline_bug` and reproduced on
the 3.0.23 sources. Older candidate notes below are kept where still accurate.

Background (3.0.23 candidate):

This candidate integrates the firmware backlog with the 3.0.22 recovery release
and its bounded interrupted-DFU retry fix. The recovery state machine is retained, with an SD bus initialization fix and
boot/update/storage diagnostics appended to the recovery packet. Qualification of either parent does not qualify this
combined image; it needs fresh build and jig evidence before release. It does not
provide MCUboot rollback or repair a bootloader/network image. Ship only the
application image after build-only QA and jig qualification.

## Behavior

The default limit is three failed boots: the fourth attempt enters recovery.
`PRE_KERNEL_2` priority 0 records the attempt and starts WDT0 (30 seconds).
Watchdog/lockup resets and software resets marked by the fatal handler count;
pin reset, ordinary software reboot, OFF wake and POR start a fresh trial.
The fatal handler uses only retained RAM, a barrier and `NVIC_SystemReset()`.
Pre-hook `PRE_KERNEL_1` hangs remain outside coverage. Application-only DTS
`zephyr,deferred-init` removes non-recovery devices from automatic boot
initialization. Normal mode calls `device_init()`
before any application use. SAFE initializes only the SD host and its MMC
child to quiet the shared bus; the injected hang device remains normal-only. A repeatable deferred-driver
hang therefore counts until the fourth boot selects SAFE and bypasses that
init. Recovery still depends on the eager kernel/devices and network core.

Main decides from CRC-validated retained RAM **before** `app_settings_init()`.
A valid latch enters SAFE without loading application settings, identities or
bonds. Unencrypted SMP is intentional (David's decision); recovery can create
an ephemeral BLE identity and accept a fresh unbonded central. A cold
boot never restores SAFE from `omi/bootstate` (3.0.24). An interrupted DFU
transaction has the narrow TRIAL check described below. A 10-second P0.26
hold at power-on while charging also latches recovery (reason 2).

The recovery branch powers PDM enable low, leaves the SD rail on (as the boot
hog and MCUboot leave it), initializes `sdhc0`, then its `mmc` child, then
attempts `disk_access_init("SDMMC")` before any application NOR read. The
2026-11-06/07 jig measurement found an uninitialized card driving shared SPI3
MISO while deselected. Initialization attempts quieted the bus even when disk
init returned `-134`. Returned errors are counted and never abort recovery.
Each stage is attempted once, with watchdog feeds between calls and the SDK's
finite SD command/retry timeouts; a wedged driver still falls back to the
30-second hardware watchdog. No new retry/wait loop is added.
The slot check compares two 32-byte reads (blank slots are allowed), counts
read errors/mismatches and logs whether the secondary slot is readable,
initializes the LED, enables
Bluetooth, registers diagnostics and starts connectable advertising at 1–2
seconds. SMP, DIS and the configured static BAS service are registered by
Zephyr; application audio/settings/features/time/storage/button/haptic services
and application connection callbacks are skipped; SAFE registers only cache
invalidation callbacks for diagnostic long reads. No SD mount, mic, codec,
capture, ring writer, pusher thread or battery work runs. NOR/SPI3 stays awake
for the secondary slot. Do not switch the SD rail off here: on the CV1 jig that
made every SPI3 NOR transfer time out, so phone DFU in SAFE could never stage an
image (`Safe mode secondary slot: UNREADABLE`). The fault proofs require the
`readable` line on the SAFE boot. The existing advertising payload/name stays unchanged,
including its audio service UUID; do not treat that advertisement alone as
proof of capture availability. Read diagnostics.

NCS 2.9.0's pinned Zephyr `1f8f3dc291420c70cd39e77a5cdc954561d4a08f`
(`v3.7.99-ncs2`, Zephyr 3.7 lineage) supplies `device_init()` and deferred
`DEVICE_DT_DEFINE`/`DEVICE_DT_INST_DEFINE` initialization unconditionally.
There is **no `CONFIG_DEVICE_DEFERRED_INIT` symbol** in that pinned release;
adding it causes a fatal Kconfig warning. Use the DTS property alone with this
SDK. `include/zephyr/device.h` places marked entries in `.z_deferred_init`, and
`kernel/init.c::z_impl_device_init()` invokes them manually. The app overlay defers:

| Node | Driver / normal order |
| --- | --- |
| `i2c2` | nrfx I2C, before its sensor children (when enabled) |
| `pdm0`, `i2s0` | nrfx DMIC and I2S (enabled instances only) |
| `adc` | nrfx SAADC, before battery application startup |
| `lsm6ds3tr_c` | LSM6DSL IMU/sensor (when enabled) |
| `sdhc0`, `sdhc0/mmc` | SPI SD host (including the CMD12 replacement), then SDMMC disk registration |

The software Opus codec has no Zephyr device init; it already starts only in
normal application code. T5838, haptic and battery application initialization
also remain normal-only. There is no separate eager codec device in this DTS.
The optional Wi-Fi driver is not enabled in `omi.conf`.

Residual risks: clock, interrupt/GPIO, UART console, PWM for the safe LED,
SPI3/external NOR, internal flash, IPC/Bluetooth and other kernel/system init
required by recovery remain eager. A repeatable hang there cannot be bypassed.
PWM is kept for the recovery LED, and SPI3/NOR must remain ready for DFU; no
required driver was deferred. NVS/backend access can also hang: cold/invalid
RAM needs one restore attempt; a warm valid latch skips it. After advertising, a separate CRC-covered telemetry
access guard permits one isolated telemetry load/save per boot; if it hangs,
subsequent warm SAFE boots skip it. It never loads application or bond settings.
See [gatt-map.md](gatt-map.md) for the record, persistence cadence and limits.
3.0.24 writes no SAFE state to `omi/bootstate`; after advertising, SAFE only
opens boot telemetry under the CRC-covered attempt bit above. Completion may
retry backend initialization once for its TRIAL write.

The red LED pulses for 50 ms each second. Release the entry gesture, then hold
for three seconds and release to enter System OFF; the latch is cleared first,
so the next wake is a normal boot. This path samples the GPIO
directly, without the normal button workqueue or capture/storage teardown. It
keeps feeding WDT until System OFF. WDT cannot stop on nRF5340; the normal
`turnoff_all()` path now logs that failure and continues to `sys_poweroff()`.
The jig must verify WDT/power behavior, including that wake boots normally.

On a normal boot, successful advertising plus reaching the main loop starts
a 60-second trial (`CONFIG_OMI_SAFE_MODE_GOOD_UPTIME_S`). Passing clears the RAM
attempt count and stamps GOOD once for that version. No BLE connection is
required. An advertising error still allows the existing offline startup but
cannot pass the self-test. No repeated NVS retry loop is added.

`omi/bootstate` is one 24-byte settings value: LE32 state (1 SAFE, 2 GOOD,
3 TRIAL), LE32 latch reason (0 none, 1 crash loop, 2 button, 3 simulator), and
a NUL-terminated 16-byte firmware string. 3.0.24 never writes SAFE and never
reads SAFE back; a SAFE value left by 3.0.23 is ignored and replaced by the
next TRIAL/GOOD stamp. Counters never write flash, including before settings
is available. Completed DFU writes TRIAL (the interrupted-DFU check below reads
it). GOOD is stamped after the new trial. Only settings/NVS is used; littlefs,
SD metadata and the MCUboot trailer are untouched.

The upload-check hook `MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK` rejects image 1 (and
all non-application targets) in SAFE before erase/write. It checks both the
request image number and the inspected `action.area_id` against the application
secondary slot: continuation chunks can omit `image` and default to 0 even
while continuing a network-core upload. Normal-mode upload policy is preserved.

The completion callback is the pinned Zephyr `MGMT_EVT_OP_IMG_MGMT_DFU_PENDING` event:
it means upload finished writing, not successful cryptographic validation,
activation or a healthy image. It clears latch/count for the *next* boot; the
current recovery session keeps running. PENDING has no payload in NCS 2.9.0,
so only an image-0/application-slot check immediately preceding completion may
clear the latch; STOPPED, rejected/failed chunks, unknown completions and
image-1 completions cannot clear it. An interrupted/failed upload doesn't
clear it. A new firmware string also starts a fresh version trial. The next
bad image can latch again. Network-core uploads are forbidden in SAFE.

Before writing TRIAL, completion seals a retained `dfu_pending` intent. If reset
lands after the NVS commit but before clearing the RAM latch, the next boot
reads only bootstate: TRIAL for this firmware overrides the stale latch and
starts a fresh count-1 trial. A successful read without a matching TRIAL
(including SAFE or no value) clears the retry budget and retains the latch.
Resolving has a budget of three backend attempts, including failed initialization
or reads. Before each attempt, RAM is sealed with the remaining budget and a
mandatory bypass boot. If the attempt fails or hangs, the following warm boot
skips the backend read and reaches SAFE; only a later boot may retry. Thus reads
can occur on boots 1, 3 and 5 after the interrupted transaction, with SAFE
reachable on boots 2, 4 and every boot after exhaustion even if every read hangs.
No automatic reboot is added: a bypass boot stays reachable in SAFE until reset.
SAFE persistence is deferred while a retry is outstanding so it cannot overwrite
the committed TRIAL. Exhaustion leaves the latch in SAFE with no further reads.
Ordinary warm latches do not reread settings: an old TRIAL must not erase a
later crash loop. This is the sole warm-latch settings exception, needed to
resolve the interrupted transaction; no `app_settings_init()` or bond loading
is involved. Main's SAFE/GOOD writes and the SMP worker's TRIAL write are
serialized; SAFE persistence rechecks the latch under that lock, so a late
persistence attempt cannot overwrite a completed DFU's TRIAL.

## Retained RAM placement and evidence

The record is 64 bytes inside the existing 64-byte DTS `zephyr,retained-ram` reservation
at `0x2006FF00–0x2006FF40`. The application linker owns it as `.omi_retained`
NOLOAD. CRC-32/ISO-HDLC covers every preceding byte (including magic, reset
cause, full firmware field and transaction/persistence fields). Count saturates
at 255, latch reason must be 0–3, fatal, telemetry-fatal and persistence/access guard bits must be 0–1.
The existing 32-bit `dfu_pending` word at byte offset 36 encodes only these states:
0 idle, 1 initial resolve, 2 bypass with two retries remaining, 3 retry with two
remaining, 4 bypass with one retry remaining, 5 final retry. All other values
invalidate the record, even with a matching CRC. The original pending value 1
still starts resolution. The original fields through `persist_attempted` at offset 40 retain their
offsets. This telemetry extension adds a backend-hang guard at 44, lifetime
warm-boot count at 48 and fatal-history indication at 52, and an NVS-baseline-seeded bit at 56; CRC covers
bytes 0–59 and occupies 60–63. Lifetime fields survive trial/DFU clears, saturate,
and merge with the durable telemetry record on open. Magic,
version, CRC or range mismatch invalidates the whole record; no field from it
can supply a latch. A cold/invalid record can still restore a separately valid
NVS SAFE. All mutations, including fatal, reseal the CRC. The format magic is
changed to `0x53414633`, invalidating prior 36/48-byte records safely. Link assertions reject overlap with data/BSS/noinit (including static
stacks/heaps) and excess size. The node lives in `omi/app.overlay`, selected
only by the application; shared board DTS and bootloader configuration are
unchanged. Kconfig conditionals in shared DTS are not a valid isolation guard
because Zephyr processes devicetree before Kconfig.
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
Warm-reset retention through the installed jig MCUboot was measured on
2026-11-03. Four fault-injection runs (driver hang, settings hang, watchdog
starvation, hard fault) each observed the CRC-valid record count go 1, 2, 3, 4
across watchdog and fatal resets, and the bootloader region hash matched the
pinned baseline in every run. No generated MCUboot `.map` was available, so the
static map proof is still open. To close it, take
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

From the checkout root (heavy runs go through the workspace's heavy-work gate
where one exists):

```sh
make -C omi/firmware/tests test
python3 omi/firmware/omi/sim/scenario_runner.py --cache /absolute/scratch/cv1-sim
```

Host tests execute the production state machine against reset-register, clock,
settings and callback-registration stubs. They assert zero NVS writes in 100
pre-settings crashes; no SAFE write across 100 subsequent recovery boots;
power-on, OFF-wake and pin resets clearing the latch, a 3.0.23 SAFE left in
NVS booting normally; failed and completed DFU callbacks; same-version recovery;
version change; uptime/advertising gates; saturation; normal reset classes;
and no false latch over 100 sporadic watchdog resets separated by good trials.
They also corrupt each retained byte with magic intact, check ranges independently
of CRC, reject image-1 and resumed network-slot chunks, ignore unknown/stopped
completions, and reproduce reset after committing same-version TRIAL while RAM
still says latched. A later crash loop with that old TRIAL must still latch.
Resolve tests cover transient read failure followed by TRIAL, three-attempt
exhaustion for read/init errors, watchdog resets inside read/init with a mandatory
SAFE boot after each hang, successful non-TRIAL cancellation, deferred SAFE
persistence, and retry range validation with recomputed CRCs.
The suite also exercises the boot-record codec, image-outcome classification,
saturating counters, NVS checkpoint throttling (including failed writes),
lifetime boot-count restoration, telemetry backend-hang bypass, and coherent
recovery long reads. The SD seam checks host → MMC → disk ordering for both SD
host drivers with the injected hang device present, returned errors, and NOR
read errors/mismatches. These checks do not measure driver latency on hardware.
The suite also runs the existing audio-packet and nine-milestone parser tests,
slot geometry and the release build guard. It does not emulate torn NVS writes,
WDT enforcement, Nordic faults, Bluetooth or MCUboot.

The simulator scenario suite (`omi/sim/README.md`, "Scenario suite") boots the
production `main.c`, `safe_mode.c`, `button.c`, settings, capture mute and SD
worker across multi-boot chains: power-on holds with and without the charger,
cold power cycles, OFF wake with the button still held, watchdog, panic and
driver/settings hang crash loops (real deferred Zephyr fault device), and a
synthetic DFU completion. Retained RAM is carried between boots only for warm
resets; NVS is real Zephyr over a flash file. Each scenario asserts per-boot
state and cross-boot invariants (`no-stuck-safe`, `manual-entry-needs-charger`,
`poweroff-waits-release`). This proves selection and control flow at the
source level, not Nordic watchdog/reset enforcement or the signed image.

## Jig bench plan (requires separate flash authorization)

Use the DK-probed board, J-Link, no antenna, and a reachable BLE central. Keep
an app-only known-good OTA package ready before loading a fault build. Do not
replace the fielded MCUboot, UICR, network image, partition map or keys. Full
factory recovery requires an independently authorized procedure; follow
[the bootloader runbook](cv1-bootloader.md). For this fault campaign, preserve the
installed loader by using only the exact OTA signed app bytes. A staged release
HEX also replaces the bootloader and belongs to a separately authorized repair
procedure. Never substitute release HEX into the archived two-core flasher.

1. **Baseline.** Build per `omi/BUILD.md`, retaining maps/configs. Check release
   version `3.0.23` through DIS. Use the baseline jig console profile and
   locate the control block from its map/J-Link RTT discovery; decode with `tools/cv1/startup_replay.decode_snapshot`/`observe`: all nine
   normal milestones must pass unchanged. Run `tools/cv1/ble_central` scan and
   session with `--expect-serial` per its README. Read `19B10042`: `active=0`,
   `latched=0`; after 60 seconds in the main loop require RTT
   `Safe mode self-test passed` and `omi/bootstate=GOOD`. A later reboot of
   the same version must not print another GOOD write.
2. **Fault builds.** Use a separate build directory per fault. Append a small
   overlay with `CONFIG_DEBUG=y`, `CONFIG_OMI_FAULT_INJECT=y`, and exactly one
   of `CONFIG_OMI_FAULT_INJECT_HARD_FAULT=y`,
   `CONFIG_OMI_FAULT_INJECT_DRIVER_HANG=y`,
   `CONFIG_OMI_FAULT_INJECT_SETTINGS_HANG=y`, or
   `CONFIG_OMI_FAULT_INJECT_WDT_STARVE=y`. For a plain app build pass
   `-DEXTRA_CONF_FILE=/absolute/fault.conf -DOMI_DEVELOPMENT_BUILD=ON`. With
   sysbuild, pass `-Domi_EXTRA_CONF_FILE=...` and set `OMI_DEVELOPMENT_BUILD=1`
   in the environment, because sysbuild does not forward an image-prefixed
   `OMI_DEVELOPMENT_BUILD` to the app. The guard also rejects the NCS default
   `MinSizeRel` build type, so pass `-Domi_CMAKE_BUILD_TYPE=Debug`. A build type
   makes NCS look for a build-type `pm_static` file and silently drop the pinned
   partition map, so also pass `-DPM_STATIC_YML_FILE=/absolute/partitions.yml`,
   copied from a normal build's `build/partitions.yml`, and check that the fault
   build's app, littlefs and settings addresses match it. Use the production
   `omi.conf` as the base.
   Do not publish these artifacts. Omission of the development opt-in must
   fail CMake with `OMI_FAULT_INJECT is forbidden in release builds`;
   the default Kconfig value is n. Inspect the final app `.config` before use.
   The hard-fault variant executes an undefined instruction before BLE:
   `FAULT_INJECT: fatal before BLE`, followed by an immediate fatal reset.
   On the jig, set `CONFIG_OMI_FAULT_INJECT_HARD_FAULT_DELAY_MS=5000` so each
   failing boot dwells long enough for SWD polling to sample it.
   The driver variant is a real `DEVICE_DT_DEFINE` deferred device whose init
   spins unconditionally: `FAULT_INJECT: driver init hang`. Normal
   main calls `device_init()` and WDT resets within 30 seconds; after three
   failures SAFE must reach BLE and feed without invoking that device. There
   is no latch test in its init. Also qualify a hang in a real PDM/SD init
   using a temporary local breakpoint/spin in that driver, keeping it deferred.
   The settings variant spins unconditionally inside `app_settings_init()`:
   `FAULT_INJECT: app settings init hang`. The fourth boot must select SAFE
   without that line, application settings loading or bond loading. Test a
   fresh unbonded central for both variants. The starvation
   variant prints `FAULT_INJECT: watchdog starvation` at uptime 30 seconds,
   then resets by the watchdog about 30 seconds later. After three failed
   boots, require the recovery banner/feed-loop line and `omi/bootstate=SAFE`.
   The normal application path is skipped in latched recovery. Read retained words with J-Link across
   resets; count must rise, never be clobbered by the loader. Diagnostics
   must report `active=1`, `latched=1`, reason 1, count >= 4 and reset cause.
   Verify 1–2 second advertising, DIS and SMP availability under the existing
   permission policy; record all `CONFIG_MCUMGR_TRANSPORT_BT_PERM_*` values.
   Exercise disconnect/reconnect and a fresh unbonded central as well.
3. **Retained corruption, manual and false-latch checks.** Before testing
   corruption, recover/clear durable SAFE so it cannot mask the result. Halt
   after the early hook has sealed the record, flip one bit in count, reset
   cause, latch reason, fatal, firmware, pending or persistence field with
   J-Link while preserving magic, then warm-reset. Each must invalidate RAM,
   start count 1 and never supply a latch. Test the CRC word too. The host
   tests additionally reseal out-of-range count/reason/fatal to prove validation
   is independent of CRC. Restore normal firmware after fault qualification.

   **Manual checks.** On the charger, hold P0.26 for 10 seconds from power-on;
   require latch reason 2. Repeat off the charger, and with the charger
   plugged or unplugged mid-hold: each must boot normally. Power cycle from
   SAFE: the next boot must be normal (3.0.24). `tools/cv1/jig_gestures.py`
   scripts these gestures from the simulator scenarios. Recover; then repeat watchdog resets more than 60 healthy seconds
   apart and require count cleared each time, no false SAFE. Pin resets and
   ordinary software/OFF reboots must not accumulate failed attempts.
4. **Recovery.** Transfer a good **application/image-0-only** package using
   the Omi phone app or nRF Connect. `ble_central` has no SMP/DFU by policy.
   Require `omi/bootstate=TRIAL` and
   `Safe mode DFU finished: fresh trial on next boot`, then reboot, normal
   milestones and after 60 seconds GOOD. Repeat with a same-version image.
   For the commit/reset window, use a debug breakpoint on the DFU callback's
   `new_trial()` after `save_state(TRIAL)` returns success; verify NVS says
   TRIAL and RAM is CRC-valid, latched, with `dfu_pending=1`. Issue a warm system
   reset without resuming the RAM clear: require normal startup/count 1 and GOOD
   after 60 seconds. Reset before the NVS write as the companion case: SAFE must
   remain. Repeat crashes in the recovered trial and confirm the previous TRIAL
   does not prevent relatching. Attempt image 1 and a continuation with image
   omitted: require an SMP error, no network-slot erase/write, unchanged SAFE
   and no DFU-finished witness. Then prove image 0 still completes. Do not install
   a network image.
   Interrupt an upload before completion: SAFE must stay set. A failed
   bootstate write must log a warning and must not claim latch clearance.
5. **Power.** Measure average current and compare recovery against a crash
   loop. Confirm P1.10 SD power remains high and P1.4 PDM enable is low. Release the entry
   gesture, hold button for three seconds, then release: require
   `Safe mode entering system off`, System OFF current, no WDT wake after
   more than 30 seconds, and button wake into a normal boot (3.0.24). Also verify the
   normal long-press path reaches `Entering system off; press usr_btn to
   restart` despite the expected watchdog-disable warning. No battery ADC or
   critical-battery shutdown was added to the minimal recovery path.
6. **Custody.** With preexisting recordings, record ring INFO `read_seq`,
   `write_seq`, `ring_id` before entry and compare after recovery. During the
   safe interval all three must remain unchanged. After normal capture resumes,
   legitimate appends may advance `write_seq`, and acknowledged phone drains
   may advance `read_seq`; account for those rather than requiring a frozen
   write pointer while recording. Require the same ring identity and preserved
   preexisting audio. Safe mode initializes only the SD host/card to quiet SPI3; it never mounts
   the SD ring, starts storage/capture services or mutates the raw ring.
   The backlog custody changes run only in normal mode. Safe
   mode suspends new capture visibly (red pulse/diagnostics); it cannot
   recover recordings lost before entry or promise recording while repairing.
7. **Release.** Run `firmware_release.yml` with publish omitted for build-only
   QA per `AGENTS.md`. Check app artifact version, maps and all bench evidence
   before a separately authorized publish. Retain the installed loader and
   network core; do not flash a sysbuild merged image merely to install this
   app-only release.

## Differences from the scoping snapshot

The backlog already owns a 25-byte telemetry packet at `19B10041`. The combined
candidate keeps that UUID/layout and exposes main's 16-byte recovery
prefix plus the 80-byte boot record at `19B10042`, in the same service. Normal diagnostics follows storage;
SAFE registers the extended recovery state, including boot/storage telemetry. See [gatt-map.md](gatt-map.md)
for exact registration and attribute order. The backlog's fail-closed mute,
persisted device name, power control and custody behavior remain normal-only.
Its CMD12 replacement SD host follows the same deferred-init path as the stock
host. The early watchdog hook captures Zephyr reset flags for normal telemetry
before the state machine captures and clears raw RESETREAS.

Counting only in main, as scoped, would miss every pre-main driver hang.
The count/reset capture therefore moved into the PRE_KERNEL_2 watchdog hook;
main selects from RAM before settings and defers non-recovery devices. Only
invalid RAM restores the durable latch; pending DFU intent resolves a committed
TRIAL using an isolated bootstate read. The production transport previously swallowed advertising failures;
its behavior is preserved, with a separate successful-advertising witness for
GOOD. The approved text's DFU-finished event is named DFU_PENDING in NCS 2.9.0.
Recovery needs an explicit TRIAL NVS write (in addition to SAFE/GOOD) for
same-version cold-reset escape. Latch persistence is unavailable if backend initialization/writing fails;
recovery advertises without loading bonds. No firmware or map claim in
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
are loaded only in normal mode. Notification hooks and image status hooks are both explicitly
enabled for the completed-upload callback; the build checks those dependencies.
