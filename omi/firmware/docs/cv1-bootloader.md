# CV1 factory MCUboot and safe wire flashing

CV1 pendants need the Omi MCUboot main. **Never flash stock MCUboot to CV1.**
OTA replaces the app, not MCUboot. A bootloader-only fix cannot reach fielded
pendants over BLE and does not require a new app firmware version.

## Why the custom main exists

SD and external NOR share SPI3. An uninitialized SD can drive MISO and corrupt
NOR reads. Stock MCUboot calls `boot_go` without releasing that bus; an otherwise
valid secondary image can appear invalid and be erased instead of installed.
The 2026-11-07 jig investigation reproduced this. The factory image has Omi's
main from commit `bbf61c04a59` (#2469):

1. Configure SD power GPIO and set it high.
2. Sleep one second.
3. Resume the SD host; disk ioctl INIT (6).
4. Sleep another second.
5. Disk ioctl DEINIT (7); suspend the SD host.
6. Continue to MCUboot `boot_go`.

The implementation is [`../omi/src/mcuboot_boot_zephyr.c`](../omi/src/mcuboot_boot_zephyr.c).
Until this build integration, the source was dormant and sysbuild selected the
SDK's stock main. Linking an SD driver or finding `SDMMC` in the binary does
not prove the initialization sequence runs before image validation.

## Approved bytes and release policy

[`../bootloader/cv1-bootloader-policy.json`](../bootloader/cv1-bootloader-policy.json)
is the release allowlist. Hash the entire [0, 0x10000) region, filling holes
with 0xff. The approved factory hash is
`c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086`,
from `FLASH_3.0.8/MAC/merged.hex`. Factory initialized data ends at 0xcddc.
The embedded public-key SHA-256 is
`fc5701dc6135e1323847bdc40f04d2e5bee5833b23c29f93593d00018cfa9994`.
Compare public hashes; never print signing-key contents.

**Release app HEX files are app-only.** `cv1_release.py stage` selects only
[0x10000, 0xf6000) from `merged.hex`, preserving installed MCUboot, storage,
settings and UICR. The name `Omi_CV1_v<version>.hex` does not mean full-flash.
The CPUNET HEX remains a separately named asset for explicitly authorized
radio work; it is not part of normal app recovery. OTA ZIPs default to app only.

Staging, promotion and immediately-before-publication validation parse every
staged HEX. Any boot bytes must match the checked-in allowlist. Malformed,
overlapping, truncated or checksum-invalid HEX fails closed. Changing asset
checksums in provenance does not bypass the boot-region gate. Inspect manually:

```sh
python3 omi/firmware/scripts/ci/cv1_bootloader.py path/to/Omi_CV1_vX.hex
```

The new custom build remains a separate **bench artifact**, not a release
bootloader, until the lead reports physical qualification and a reviewed
policy update pins its exact hash. Do not add a hash merely to make a build
pass. The [historical audit](cv1-bootloader-release-audit.md) classifies older
assets; the presence of Omi's sequence alone is not an approval.

## CI and developer build

The existing manual `firmware_release.yml` builds production sysbuild with
NCS 2.9.0 at commit `7787b264984022cda64d9629278942053e6462a5`, its west
manifest's module revisions and the workflow's digest-pinned CI image.
`omi/sysbuild.cmake` registers an MCUboot-only Zephyr module containing the CMake application overlay.
The overlay replaces exactly one SDK `boot/zephyr/main.c` source with Omi's
source after MCUboot declares its sources; zero or multiple matches abort
configuration. It applies to the documented developer sysbuild command too.
The SDK checkout is never patched. Crypto, signing key, production config and
static partitions remain the existing ones.

`build-cv1.sh` uses stable locale/time/hash-seed settings and two build jobs.
`prove_cv1_bootloader.py` checks the embedded public key, generated layout,
production config, custom source selection and disassembled calls before
`boot_go`. MCUboot initialized flash must end below 0xce00; the reserved
region ends at 0x10000, signed slot header starts there, app vectors at 0x10200.
A second clean MCUboot compilation must reproduce the same 64 KiB hash.
App RSA signatures are randomized, so that claim does not apply to app bytes.

The run uploads `cv1-bootloader-<run>-<attempt>` with:

- `cv1-mcuboot.bin`: exactly 65536 padded bytes, only the boot reservation.
- MCUboot ELF/map, main disassembly, effective config and generated partitions.
- `bootloader-report.json`: factory/candidate hashes, differing-byte count,
  loaded ends, public key hash, layout and approval/bench status.
- Rebuild comparison, frozen west manifest and toolchain version.

Use the report to state the actual binary difference; compiler or layout
changes cannot be dismissed merely as “different toolchain.” Until a CI run
and bench receipt exist, source integration is not proof of factory equivalence.

## Safe SWD app recovery

Prefer BLE OTA on a working pendant. For app-only wire recovery:

1. Back up and hash [0, 0x10000) with J-Link APP-core `savebin`. Compare with
   the approved policy. A nonapproved installed loader needs a separately
   reviewed recovery plan; app flashing cannot repair it.
2. Check the exact downloaded HEX with the command above. Require
   `bootloader-free` for normal recovery. Do not use historical merged release
   HEX or copy a new HEX over the archived factory files.
3. With the existing approved probe-selection conventions, use only the
   `nRF5340_xxAA_APP` target and `loadfile` the app-only HEX. Never mass erase,
   recover/unlock, flash CPUNET, change UICR or change protection settings.
4. Read back the boot region again and verify it is unchanged. Reset, reconnect,
   check firmware identity, boot record, SD and capture; verify a subsequent BLE
   OTA install from a cold power cycle.

A blank pendant also needs a qualified bootloader; app-only HEX is insufficient.
Bootloader replacement is a separate factory/bench operation: back up, use
`loadbin` of the exact approved 64 KiB binary at 0, verify by readback and
compare untouched app flash. Do not use `west flash` across all sysbuild domains.
The archived `FLASH_3.0.8` images are evidence, not a generic current installer.

## Qualification and rollback limits

Physical qualification must exercise candidate bootloader + 3.0.21 app,
app-only BLE OTA to 3.0.24, cold SD startup, boot records and restoration of
the factory bootloader. The lead owns the jig. Keep the exact run/attempt,
bootloader and signed-app hashes with its receipt.

Factory/production MCUboot uses **overwrite-only** with downgrade prevention.
It cannot revert an unconfirmed trial. Changing to swap/test/revert is a
separate design and qualification task; do not claim a successful OTA proves
rollback. Application safe-mode/confirmation records do not change that fact.

The native simulator starts at the application entrypoint, stubs the devices
and does not execute MCUboot or model shared-SPI electrical contention. A
boolean “SD initialized” simulation would restate the hypothesis without
validating it. Host tests therefore cover the actual HEX boundary and packaging;
compiled-main evidence and the real jig cover boot order and electrical behavior.
