# CV1 contributor checks

No jig is needed for the host checks or application-object compilation. These commands never install packages, fetch sources, access signing keys, connect to devices, sign or publish firmware. Prerequisites are Python3.9+, Git and a C11 compiler with UBSan; macOS also needs existing Command Line Tools.

From the monorepo root, create a new evidence directory outside the checkout and run:

```sh
python3 omi/firmware/tools/cv1/contributor.py quick-host --output /tmp/cv1-host-UNIQUE.json
```

The report path must not already exist. `quick-host` discovers this checkout, validates supported baseline ancestry, checks fixture/dependency pins, runs Python host models/replays and compiles/tests `omi/firmware/omi/src/lib/core/audio_packet_logic.c` with its in-tree host test. That seam is not yet linked into the firmware; see `omi/tests/host/README.md`. It does not test every driver or run Zephyr. Editable source is deliberately not frozen by the fixture manifest. Firmware/tool edits are inputs to these tests; update public fixture pins deliberately when fixtures change. Hardware and SDK stages are reported skipped.

If a config is supplied to quick-host, it must select the checkout containing this entrypoint; a different root is rejected rather than attributing these tests to another checkout.

## Compile active application objects without signing

Copy `checkout.config.example.json` to a local file outside Git and set this checkout plus existing NCS2.9.0 SDK and Nordic toolchain paths. The included lock describes the bench-compatible SDK/tool profile; unsupported/missing dependencies fail explicitly rather than install. Run:

```sh
python3 omi/firmware/tools/cv1/contributor.py compile-only --config /path/to/local-config.json --output /path/to/new-evidence/build.json
```

The evidence parent directory must already exist. This snapshots active tracked app/board source plus untracked C/H additions, excluding key/image paths and untracked configs. In particular an untracked `prj.conf` is neither copied nor changed. Stage new non-C/H build/config files before compiling. Each copied file is hashed; links, oversized/special files and modification during reads reject. The build runs from that unique snapshot with supported skip-MCUboot/no-sign/no-network-child options, audits effective config and command graph, and builds app/Opus static archives only. It does not apply a frozen patch or silently compile old HEAD source.

Outputs are **not flashable or releasable**. No ELF/HEX/BIN/update package is produced. This catches app C and generated-header compile errors; it is not a full kernel/driver/network/bootloader link, hardware test or signed artifact. `firmware-build` is a separate readiness/command-plan target and remains blocked because full baseline sysbuild performs key operations. No dummy signatures or weakened bootloader are substituted.

This is a fixed key-free build profile for reviewed source and an existing trusted SDK/environment, not an execution sandbox. CMake configuration executes before config/graph audits; arbitrary edited build scripts could run unrelated commands. Do not run untrusted fork build scripts on a host holding secrets. The proposed shared PR-testing service needs separate isolation; it is not implemented here.

## Offline admission and reports

`bench.py`, `artifact_preflight.py` and `job_dry_run.py` are offline models/planners, not a live controller. They cannot reset, flash, erase or authorize a release. Artifact admission retains exact hash/board/layout/role/mode gates. Installed b0n is hash-only; provision-key metadata equality is not ECDSA authentication. See [validation model](../../docs/validation-model.md). A host test pass cannot supply missing independent BLE, OTA interruption/recovery or signed-image acceptance evidence.

Startup fixtures are sanitized derivatives; radio fixtures omit unrelated device identifiers. They characterize observed formats and failures, not a full firmware emulator. Shared C parameter cases, Python methods, compilation and actual device evidence are separate coverage categories. Imported receipts and captures are labelled `operator_supplied`: these tools check that their bytes are unchanged, not that a device produced them, so they are not hardware evidence on their own.

## Radio tests on an opened board

The mainboard has no antenna part. `RF_COM` ends at pogo pad PP1, labelled "Dual band Antenna" in `omi/hardware/consumer/electrical/mainboard/schematic.pdf`, and the BOM lists six `CA02-PG07` pogo pins and no antenna, so the aluminum covers appear to be the radiator; no document states this and it has not been tested. With its covers off, a board on a jig may have no working antenna contact. One such board advertised at about -100 dBm on a nearby Mac and was not seen at all by another. That is one observation, not a specification, and it does not show that any other board is healthy. Restore the antenna contact before drawing a conclusion from BLE range or RSSI, in either direction.

## Official and personal firmware

Official contributors use these no-key checks; a shared isolated jig PR-testing service is proposed, not deployed. Maintainer private keys are not distributed to contributors. Everyday owners must also be able to develop/install personal firmware OTA without a jig or maintainer approval per build. That requires explicit owner-authorized trust plus a protected return-to-stock path independent of broken custom firmware, with trial revert as an additional mechanism. Current firmware does not yet implement that enrollment/recovery design. Pairing alone does not enroll a key, and this guide does not tell end users to disable signature validation or acquire a debugger.

See [OTA development design and migration limits](../../docs/ota-development.md), [updater source locations](../../docs/updater-source.md), and the firmware agent guide before changing build/release behavior. No bootloader, partition, key, trust or protection change is implemented by these tools.

## Personal OTA feasibility model

[The concrete design](../../docs/ota-development.md) compares an OTA-installed secure supervisor with a bootloader-delegation/internal-swap option against the retained CV1 map. ota-development-plan.json is an engineering budget, not a flash layout. Run `python3 -m unittest -v test_ota_development_model` from this directory for24 proposed-contract simulations. These are arithmetic/state tests with assumed authorization/isolation, not TrustZone/cryptography/bootloader/device proof. Current firmware still lacks owner enrollment and protected return-to-stock; no bootloader/key/protection behavior is implemented.

Independent in-place design review has NOT cleared Option A for implementation or interruption-safe bootstrap: conventional versions can trigger old-loader secondary erasure after a torn primary header; attribution, shared-bus proxy and recovery-mode contracts remain unresolved. The model tests characterize the revised384KiB-bank proposal, not a working protected updater. The prior overlap warning is conditional on caller rounding; the retained driver performs bounded4KiB erases. The optional [pinned-loader source audit](source_review/README.md) and [bootstrap/ownership contract](../../docs/ota-bootstrap-contract.md) record the exact failure path, maximum-version tradeoff and raw-HCI trust boundary. See the design review disposition before any implementation.

