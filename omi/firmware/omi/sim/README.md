# CV1 firmware simulator (native_sim)

Two entry points share this Zephyr app:

- `scenario_runner.py`: the **scenario suite**, multi-boot power/button/
  safe-mode/mute/battery/SD scenarios with a fuzz lane, writing
  `sim-report.json`. It is a release gate (see "Scenario suite").
- `run.py`: the original single-boot startup smoke described next.

This separate Zephyr app links the pendant's **actual `../src/main.c`**. It
keeps real Zephyr scheduling, settings over simulated flash/NVS, RTC and error
feedback code. Other device boundaries are startup-only stubs compiled against
production headers. Production CMake, `omi.conf`, board, partitions, bootloader
and release workflow are unchanged.

From a clean checkout, with Python 3.9+ and a running Docker Linux engine:

```sh
python3 omi/firmware/omi/sim/run.py --cache /absolute/scratch/cv1-native-sim
```

The script pulls the release workflow's digest-pinned CI image, shallow-fetches
the NCS v2.9.0 manifest and its pinned Zephyr revision, builds
`native_sim/native/64` with the container's host GCC (no Nordic toolchain needed),
and runs to five simulated seconds. The checkout is mounted read-only. SDK,
build, flash backing file, `boot.log` and `observation.json` go under `--cache`.
Use a dedicated cache per checkout; do not run two instances against it.
Docker images live in the chosen engine's storage. Cold setup needs network
access and several GB for the image; it is heavier than `quick-host`.

The default whole-run deadline is 1800 wall seconds (`--timeout` overrides it);
boot has a separate 30-second wall deadline. A failed build, abnormal simulator
exit, missing milestone, error log or missing second watchdog feed exits nonzero.
The runner removes its named container on success, failure or interruption.
It does not start or modify a Docker VM for you.

## Macs and Linux

`native_sim` is **Linux-only**, not a macOS executable. The default target is
x86 32-bit; this spike uses the 64-bit variant to avoid multilib/i386 execution
requirements. Linux x86_64 runs the container directly. Apple Silicon needs an
amd64 execution layer in its Linux VM (Rosetta or QEMU/binfmt); an ARM Linux VM
alone is insufficient for this runner. Intel Macs still need a Linux VM.

For an isolated Colima profile on a Mac, create its home **before** starting
Colima (v0.10.3 silently ignores a nonexistent `COLIMA_HOME`):

```sh
# From the checkout root: run.py bind-mounts it, so the VM mounts it read-only.
SIM_LAB=/absolute/scratch/cv1-sim
mkdir -p "$SIM_LAB/colima" "$SIM_LAB/cache"
export COLIMA_HOME="$SIM_LAB/colima"
export XDG_CACHE_HOME="$SIM_LAB/cache"
colima start cv1-sim --cpu 4 --memory 8 --disk 45 --vm-type vz \
  --vz-rosetta=false --activate=false --ssh-config=false \
  --mount "$SIM_LAB:w" --mount "$PWD"
export DOCKER_HOST="unix://$COLIMA_HOME/cv1-sim/docker.sock"
# Only in this disposable VM: replace Colima's old QEMU 7 binfmt handler.
docker run --privileged --rm \
  tonistiigi/binfmt:qemu-v10.0.4-56@sha256:30cc9a4d03765acac9be2ed0afc23af1ad018aed2c28ea4be8c2eb9afe03fbd1 \
  --uninstall qemu-x86_64 --install amd64
python3 omi/firmware/omi/sim/run.py --cache "$SIM_LAB/run"
colima stop cv1-sim
colima delete cv1-sim --force --data
```

These Colima commands describe this host setup, not a portable Linux requirement.
Use an amd64 VM instead on Intel Macs; other engines may differ. Stop/delete the
profile even if the runner fails. Do not stop someone else's VM.
Colima's QEMU 7.0.0 ran a tiny probe but intermittently crashed GCC and Ninja
during configuration. The emulator update above follows [Lima's guidance](https://lima-vm.io/docs/config/multi-arch/).
Rosetta was unavailable on the spike host; no host software was installed.

## Meaning of a pass

The **unchanged** `tools/cv1/startup_replay.py::observe()` parses the console.
It requires every existing milestone, including Bluetooth/advertising tokens.
Those two tokens are explicitly `SIM` stub messages: `CONFIG_BT=n`, the overlay
disables host HCI, and there is no advertising or BLE test. Every driver milestone
(watchdog, microphone, battery, SD, storage, transport, codec, LED, SPI flash,
IMU) also comes from a stub, so none of them shows a real driver initialized. What
actually runs is the entrypoint's order and the settings implementation. The report retains all of the
parser's independent hardware-health fields as false, and labels its evidence
`simulated_startup` with a list of the stubs.

The main-loop witness comes from the second call to the watchdog facade stub;
it checks that startup reached the real main loop and yielded once. It does
not check watchdog resets or sustained stability. Settings flash is disposable
simulation state, not device storage. Delete the dedicated cache's flash backing
file to reset persisted simulation settings.

This does **not** test RF, PDM or the mic analog path, SD integrity, power,
MCUboot, OTA, or the network core. BLE stays out of this first cut. It also does
not exercise Opus/PCM processing, the real codec/storage/transport worker threads,
mute/custody state machines, driver error recovery, peripheral timing or real
watchdog enforcement. No fixtures or audio events are injected in deliverable 1.
64-bit host layout can hide 32-bit MCU bugs.

The original production source changes were guards around Nordic reset-register
access in `main.c` and the Nordic GPIO HAL include in `config.h`. They are selected
only by `CONFIG_OMI_NATIVE_SIM`, defined in this simulation app's Kconfig.
The production preprocessor path retains the original code. Codec is stubbed
because the retained Opus build explicitly requires ARM assembly; this spike
makes no codec portability change.

## Spike verification

On Apple Silicon macOS, Colima 0.10.3 (4 CPUs/8 GiB, VZ ARM Linux) plus the
QEMU 10.0.4 binfmt handler built and booted this target in the pinned amd64
container. `observe()` reported all nine milestones, no errors, two expected
unsynchronized-RTC warnings, and all independent health flags false. Real output:

```text
Starting omi ...
[00:00:00.000,000] <inf> app_settings: Settings initialized. dim_ratio=50 mic_gain=6 rtc_epoch=0 lsm6_base_epoch=0 lsm6_base_ts=0x00000000
[00:00:00.000,000] <inf> main: Device initialized successfully
[00:00:01.010,000] <inf> sim_stubs: SIM: main loop alive (2 watchdog feeds)
Stopped at 5.010s
```

The unchanged startup-parser suite passed 18 tests. A one-second runner deadline
returned nonzero and removed its container. Production app compilation was not
established: this host had no existing full NCS/Nordic SDK installation. Resolving
the simulator guards with `unifdef -UCONFIG_OMI_NATIVE_SIM` reproduced both
original production files byte for byte; that is a branch check, not an ARM build.
Physical x86_64 Linux, Intel Macs, Rosetta and 32-bit native_sim were not tested.

## Scenario suite

```sh
python3 omi/firmware/omi/sim/scenario_runner.py --cache /absolute/scratch/cv1-sim
python3 omi/firmware/omi/sim/scenario_runner.py --cache ... --only 'safe/*' --jobs 3
python3 omi/firmware/omi/sim/scenario_runner.py --cache ... --fuzz-seeds 40
python3 omi/firmware/omi/sim/scenario_runner.py --cache ... --baseline   # on 3.0.23 sources
```

Same container, SDK and Mac setup as `run.py`. The runner builds the default
app plus each `builds/<name>.conf` a scenario names (dev fault builds start
with `# dev-build`), then plays every `scenarios/**/*.yaml`.

**What links.** The production `main.c`, `safe_mode.c` (retained-RAM record,
reset classes, manual entry, SAFE loop, DFU callbacks), `button.c` (the real
gesture FSM and `turnoff_all()`), `settings.c` over Zephyr NVS on a flash file,
`capture_mute.c`, `sd_card.c`'s raw-ring worker with `custody.c`, and
`battery_guard.c`. Drivers, BLE, codec and the microphone are stubs
(`stubs.c`). `transport.c` is **not** linked: the battery worker and the
offline audio pusher in `stubs.c` re-create its call sites (guard call,
mute-gated `write_to_file()`), so a regression in transport's own call sites
is caught by the host tests that compile its code verbatim
(`omi/tests/battery`, `run_power_control_test.sh`), not here; the SD card is a RAM disk with ok/absent/slow/dead behaviour
(`sim_sd.c`), persisted per scenario.

**Power model.** `power_model.py` turns one global timeline into a chain of
`zephyr.exe` processes, one per boot. Each boot ends by `-stop_at`, watchdog
(the sim watchdog enforces `CONFIG_OMI_WATCHDOG_TIMEOUT_MS`), fatal error,
`sys_poweroff()` or a scripted `power` event. Reset class and warmth follow
the hardware: watchdog, fatal and software reset keep retained RAM
(`retained.bin`); a power cycle (500 ms off), pin reset and OFF wake are
reported with their RESETREAS bits, and cold boots drop RAM. System OFF wakes
on the next press, or immediately when the button was still held at
power-off. NVS (`flash.bin`) and the SD image always persist.

**Scenario format.**

```yaml
id: safe/poweron-hold-then-cold-boot        # must match the path
summary: one paragraph, the field story
committee: [1]                             # optional cross-reference
tags: [baseline-bug]                       # guard | fix | baseline-bug
build: default                             # or a builds/<name>.conf
initial: {charging: false}                 # button, charging, battery_mv, connected,
                                           # sd, sd_ready_ms, off_retains_ram, power_off_ms
faults: [{op: settings_save, key: omi/muted, rc: -5, boots: [0]}]
timeline:                                  # absolute ms from first power-on
  - {t: 0, hold: 3500}                     # also tap: [press, gap, press...], button: true
  - {t: 8000, power: cycle}                # cycle | pin_reset | soft_reset
  - {t: 9000, charger: "on"}               # connected, battery_mv, sd, app_mute, panic,
                                           # dfu: chunk | chunk-image1 | chunk-net | stopped | pending
end: 30000
expect:
  boot_count: 2
  final: running                           # quote "off" (YAML reads off as false)
  boots:                                   # per-boot SIMSTATE keys, exit, reset, log, not_log
    - {exit: poweroff}
    - {reset: power-on, safe: false}
  invariants: [no-stuck-safe]
baseline_bug:                              # what 3.0.23 did; checked by --baseline
  observed_at: ...
  expect: {...}
```

Tags: `guard` holds on both 3.0.23 and the fixed sources; `fix` is new
behaviour with no 3.0.23 counterpart (skipped by `--baseline`);
`baseline-bug` reproduces a field bug, its `baseline_bug.expect` passing on
the 3.0.23 sources and `expect` passing on the fixed ones.

**OTA, app level.** A `dfu` event delivers one image-management callback
(chunk, stop, completion) to the production `dfu_event()` handler, as mcumgr
would after an SMP request. `ota/*` covers recovery by upload, image-1 and
network-slot rejection in SAFE, and interrupted uploads. SMP framing, the
radio, MCUboot and the signed image are not simulated.

**Invariants** (`power_model.INVARIANTS`) are checked over the whole chain:
`no-stuck-safe` (a cold boot never comes up in SAFE except by the deliberate
gesture), `manual-entry-needs-charger`, `manual-entry-needs-10s-hold`,
`mute-follows-app`, `mute-blocks-capture`, `poweroff-waits-release`,
`no-watchdog`, `critical-battery-respects-charger`,
`sd-mount-attempts-bounded` and `capture-after-settings` (the microphone
starts only after the persisted mute was applied). Mute invariants judge a
boot only once settings were applied; before that the RAM mute is the
fail-closed default and nothing captures.

**Fuzz lane.** `--fuzz-seeds N --fuzz-start S` runs `fuzz.py`: seed N always
builds the same random chain of gestures, charger changes, mute writes, power
cycles, resets, panics, battery dips and settings faults, checked against the
invariants. A failing seed is written to `<cache>/fuzz-failures/seed-N.yaml`,
ready to commit as a named scenario.

**Report and gate.** `sim-report.json` records the verdict, source SHA (with
`-dirty` for an uncommitted firmware tree), firmware version, image and SDK
revisions, every scenario row with per-boot state, the fuzz batch and what is
not covered. `firmware_release.yml` runs the full suite plus 40 fuzz seeds
before staging; `cv1_release.py stage` refuses to package without a passing
report for the same SHA and version (at least 40 scenarios, 20 seeds), the
report travels in the QA artifact with its checksum in `qa-provenance.json`,
and promotion revalidates it. The suite does not yet run on every firmware PR
(that needs a CI budget decision); run it locally before opening one.

**Production isolation.** Simulator code lives here or behind
`CONFIG_OMI_NATIVE_SIM`/`OMI_SAFE_MODE_HOST`/dev fault configs.
`check_isolation.py --base origin/main` lists the production sources whose
production view (sim branches removed with `unifdef`, comments and whitespace
ignored) changed; a simulator-only change lists nothing.

**Not covered.** BLE: there is no BLE lane yet (the plan's BabbleSim
two-image lane is future work), so GATT writes are modelled at the handler
(`app_mute`) and committee items that live in the BLE TX path (storage INFO
flush cadence, TX stall) are jig checks for now. Also RF/PHY, SMP transport, MCUboot and
signing, the network core, real SD timing and wear, current draw, codec and
microphone paths, 32-bit layout. Those stay bench/jig checks
(`tools/cv1/jig_gestures.py` replays the physical subset of these scenarios
through a GPIO button and power relay).

**Adding a scenario.** Write the YAML under the matching folder, run
`python3 omi/firmware/omi/sim/test_power_model.py` (schema and catalog), then
`scenario_runner.py --only '<id>'`. For a field bug, prove `--baseline` on the
released sources first, then fix.
