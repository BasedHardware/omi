# CV1 startup on native_sim (spike)

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

The only production source changes are guards around Nordic reset-register
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

## Safe-mode regression

The simulator now also links the production `safe_mode.c` state machine.
Use `run.py --cache <dedicated-cache> --safe-mode` to test normal startup, the
`safe-mode.conf` forced-latch overlay, durable SAFE reload, a synthetic completed
upload via `dfu-finished.conf`, and normal TRIAL → GOOD in separate processes
sharing the same NVS flash file. The test uptime is two seconds; production is
60 seconds. The normal nine milestone strings and parser remain unchanged.
Safe boots instead require `Safe mode initialized: BLE DFU only` and
`Safe mode feed loop started`, with no SD/codec/microphone startup. SMP callback
delivery is a stub with the pinned Zephyr signature; no radio/DFU protocol is
simulated. GPIO, retained hardware RAM, fatal reset and early WDT remain host
unit/jig checks. See [the bench plan](../../docs/safe-mode.md).
