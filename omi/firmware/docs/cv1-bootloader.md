# CV1 factory MCUboot and safe wire flashing

CV1 pendants need the Omi MCUboot main. **Never flash stock MCUboot to CV1.**
OTA replaces the app, not MCUboot. A bootloader-only fix cannot reach fielded
pendants over BLE and does not require a new app firmware version.

Manufacturing pairing and stock-loader field recovery: [3.0.19 + 3.0.24 assessment](cv1-manufacturing-and-field-recovery.md).

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
with 0xff. The build and release bootloader hash is
`6cfd4a70a715c8885dd86db96eb97286590852dd4b0f28d9f7374faad235cad1`.
CI reproduces the historical 3.0.19 loader byte-for-byte. Its initialized bytes
end at 0xcebc, inside the 64 KiB reservation. The lead qualified these exact
bytes with the released 3.0.24 app on 2026-11-11; see the
[committed jig receipt](cv1-bootloader-release-audit.md#jig-qualification-2026-11-11).
The factory hash
`c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086`
from `FLASH_3.0.8/MAC/merged.hex` remains an approved installed/restoration
state. Factory initialized data ends at 0xcddc. CI must build the pinned
3.0.19 hash; accepting factory state does not permit a different build hash.
Both embed public-key SHA-256
`fc5701dc6135e1323847bdc40f04d2e5bee5833b23c29f93593d00018cfa9994`.
Compare public hashes; never print signing-key contents.

**Release app-core HEX files contain the qualified bootloader and app.**
`cv1_release.py stage` constructs them from the pinned MCUboot image and the
exact `omi.signed.bin` bytes in the staged OTA ZIP at 0x10000. It excludes
storage at 0xf6000 and above, UICR and network addresses. It never distributes
the raw sysbuild `merged.hex`. This provides a qualified app-core image for
manufacturing and wired repair of stock-loader units. App-only recovery is
still an option when deliberately preserving an approved installed loader;
it must be derived from the exact OTA signed image, not an old merged HEX.
The CPUNET HEX remains a separately named asset for explicitly authorized
radio work; it is not part of normal app recovery. OTA ZIPs default to app only.

Staging, promotion and immediately-before-publication validation parse every
staged HEX. Release app-core bytes must match the pinned .19 bootloader and
the exact signed app extracted from the staged OTA ZIP. Malformed,
overlapping, truncated or checksum-invalid HEX fails closed. Changing asset
checksums in provenance does not bypass the boot-region gate. Extract
`omi.signed.bin` from the intended OTA ZIP, then inspect manually:

```sh
python3 omi/firmware/scripts/ci/cv1_bootloader.py --require-bootloader --signed-app path/to/omi.signed.bin path/to/Omi_CV1_vX.hex
```

The custom build is jig-qualified and pinned to the reproduced .19 bytes.
Future bootloader changes need a new reviewed qualification and policy update;
do not add a hash merely to make a build pass. The [historical audit](cv1-bootloader-release-audit.md) classifies older
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
`boot_go`. MCUboot initialized flash must fit inside [0, 0x10000), and its full padded
hash must equal the pinned build hash. The signed primary slot starts at
0x10000 with size 0xf0000; its header is 0x200 bytes and app allocation starts
at 0x10200 with size 0xe5e00. The external secondary is also 0xf0000 bytes.
The former 0xce00 heuristic is not a hardware boundary.
A second clean MCUboot compilation must reproduce the same 64 KiB hash.
App RSA signatures are randomized, so that claim does not apply to app bytes.

The run uploads `cv1-bootloader-<run>-<attempt>` with:

- `cv1-mcuboot.bin`: exactly 65536 padded bytes, only the boot reservation.
- MCUboot ELF/map, main disassembly, effective config and generated partitions.
- `bootloader-report.json`: factory/candidate hashes, differing-byte count,
  loaded ends, public key hash, layout and approval/bench status.
- Rebuild comparison, resolved west manifest, active module SHAs and NCS revision and toolchain version.

Use the report to state the actual binary difference; compiler or layout
changes cannot be dismissed merely as “different toolchain.” The recorded CI rebuilds and lead jig receipt bind the approved bytes;
source integration alone is not proof of factory equivalence.

## Safe SWD app-core recovery

Prefer BLE OTA on a working pendant. Wired flashing replaces the bootloader
when using the merged release app-core HEX; use stable power and preserve a
rollback backup. For an authorized wired repair:

1. Back up and hash [0, 0x10000) with J-Link APP-core `savebin`. Preserve the
   backup even if it is stock; do not treat an unknown hash as approved.
2. Validate the exact release HEX with `--require-bootloader` above. The
   staged release must carry `6cfd4a70...35cad1` and the intended app version.
   Never copy it over archived factory files or invoke legacy two-core scripts.
3. With the approved probe-selection conventions, use only the
   `nRF5340_xxAA_APP` target and program the validated app-core HEX. Never mass
   erase, recover/unlock, flash CPUNET, change UICR or change protection settings.
   Use the bench's verified reset-and-halt strategy before the loader reapplies
   its SPU lock. Abort if it remains protected; do not bypass protection.
4. Read back the boot region and require the release's pinned hash. Reset,
   reconnect, check app identity, boot record, SD and capture, then verify a
   subsequent BLE OTA install. Blinking LEDs alone are insufficient evidence.

To deliberately preserve an approved installed loader, extract only
`omi.signed.bin` from the intended OTA ZIP and use APP-core `loadbin` at
0x10000, followed by `verifybin`. Back up/read back the boot region and require
it to be unchanged. This app-only route cannot repair a stock bootloader.
The host helper's `--app-only` validates app-only HEX when that format is used.
A blank pendant needs the separate qualified manufacturing process; an
app-only image is insufficient. Do not use `west flash` across all sysbuild
domains. Archived `FLASH_3.0.8` files are evidence, not a generic installer.

## Qualification and rollback limits

Qualification exercises the approved bootloader + 3.0.21 app,
app-only BLE OTA to 3.0.24, cold SD startup, boot records and restoration of
the factory bootloader. The lead owns the jig and reported this pairing passed on 2026-11-11. Keep the exact run/attempt,
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
