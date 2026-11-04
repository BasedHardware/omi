# CV1 contributor checks

No jig is needed for the host checks or application-object compilation. These commands never install packages, fetch sources, access signing keys, connect to devices, sign or publish firmware. Prerequisites are Python3.9+, Git and a C11 compiler with UBSan; macOS also needs existing Command Line Tools.

From the monorepo root, create a new evidence directory outside the checkout and run:

```sh
python3 omi/firmware/tools/cv1/contributor.py quick-host --output /tmp/cv1-host-UNIQUE.json
```

The report path must not already exist. `quick-host` discovers this checkout, validates supported baseline ancestry, checks fixture/dependency pins, runs Python host models/replays and compiles/tests `omi/firmware/omi/src/lib/core/audio_packet_logic.c` with its in-tree host test. That seam is not yet linked into the firmware; see `omi/tests/host/README.md`. It does not test every driver or run Zephyr. Editable source is deliberately not frozen by the fixture manifest. Firmware/tool edits are inputs to these tests; update public fixture pins deliberately when fixtures change. Hardware and SDK stages are reported skipped.

If a config is supplied to quick-host, it must select the checkout containing this entrypoint; a different root is rejected rather than attributing these tests to another checkout.

## Boot the real entrypoint without hardware (Linux simulation)

See [CV1 native_sim startup](../../omi/sim/README.md) for the separate Docker-backed
target and one-command build/boot check. It uses this directory's unchanged
startup milestone parser; simulated driver milestones are explicitly labelled.
Macs require a Linux VM plus x86_64 execution support. This is startup evidence,
not RF, PDM/mic analog, SD integrity, power, MCUboot, OTA or network-core coverage;
BLE is stubbed out.

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

## Unattended bench cycle

```sh
python3 bench_loop.py dry-run --candidate-job CANDIDATE.json --restore-job RESTORE.json --profile PROFILE.json --contract CONTRACT.json --pins PINS.json --bench-dir NEW_DIR --output NEW_DIR/run
```

This drives the app-only cycle against a simulated device: admit, identity, baseline check, flash, verify, boot check, restore. It can't reach hardware. Jobs, profile and contract follow `job_dry_run.py`, and the pins file holds `protected_sha256` and `restore_image_sha256`.

The driver holds the safety rules in code: only pages in `[0x10000,0xF6000)` can be erased, identity is read fresh before every erase and program, nothing is retried, restore runs after any write that fails or finishes, and the lease goes idle only with restoration proof or an untouched device. A crash gets no restore. The bench stays blocked until someone reconciles it by hand, as it does after any quarantine. A live adapter stays in the private bench profile, outside this repository, and passing here says nothing about hardware or release.

## Radio tests on an opened board

The mainboard has no antenna part. `RF_COM` ends at pogo pad PP1, labelled "Dual band Antenna" in `omi/hardware/consumer/electrical/mainboard/schematic.pdf`, and the BOM lists six `CA02-PG07` pogo pins and no antenna, so the aluminum covers appear to be the radiator; no document states this and it has not been tested. With its covers off, a board on a jig may have no working antenna contact. One such board advertised at about -100 dBm on a nearby Mac and was not seen at all by another. That is one observation, not a specification, and it does not show that any other board is healthy. Restore the antenna contact before drawing a conclusion from BLE range or RSSI, in either direction.

## macOS BLE central helper

[`ble_central/`](ble_central/README.md) builds an ad-hoc-signed Swift app bundle for explicitly authorized `scan`, read-only `session` with one reconnect, and `audio` captures capped at three seconds. DIS serial is optional for baseline sessions; `--expect-serial` checks identity before reconnect/subscription and is required for audio. Every command has a hard deadline and writes a new local JSON receipt, keeping `no_advertisement` distinct from connection/GATT failures. Only audio notification subscription changes the device; audio is discarded unless a new `--keep-audio` path is supplied. Receipts include observed CoreBluetooth maximum write lengths; raw ATT MTU and read offsets are unavailable. Run `ble_central/test.sh` for pure Swift parsing/sequence/outcome tests without Bluetooth. Building/testing does not authorize or run a live scan; see its README for the `open -n -W ... --args` launch path and console-user consent, neither verified live yet. Fixture pins are unchanged.

## Official and personal firmware

Official contributors use these no-key checks; a shared isolated jig PR-testing service is proposed, not deployed. Maintainer private keys are not distributed to contributors. Everyday owners must also be able to develop/install personal firmware OTA without a jig or maintainer approval per build. That requires explicit owner-authorized trust plus a protected return-to-stock path independent of broken custom firmware, with trial revert as an additional mechanism. Current firmware does not yet implement that enrollment/recovery design. Pairing alone does not enroll a key, and this guide does not tell end users to disable signature validation or acquire a debugger.

See [OTA development design and migration limits](../../docs/ota-development.md), [updater source locations](../../docs/updater-source.md), and the firmware agent guide before changing build/release behavior. No bootloader, partition, key, trust or protection change is implemented by these tools.

## Personal OTA feasibility model

[The concrete design](../../docs/ota-development.md) compares an OTA-installed secure supervisor with a bootloader-delegation/internal-swap option against the retained CV1 map. ota-development-plan.json is an engineering budget, not a flash layout. Run `python3 -m unittest -v test_ota_development_model` from this directory for24 proposed-contract simulations. These are arithmetic/state tests with assumed authorization/isolation, not TrustZone/cryptography/bootloader/device proof. Current firmware still lacks owner enrollment and protected return-to-stock; no bootloader/key/protection behavior is implemented.

Independent in-place design review has NOT cleared Option A for implementation or interruption-safe bootstrap: conventional versions can trigger old-loader secondary erasure after a torn primary header; attribution, shared-bus proxy and recovery-mode contracts remain unresolved. The model tests characterize the revised384KiB-bank proposal, not a working protected updater. The prior overlap warning is conditional on caller rounding; the retained driver performs bounded4KiB erases. The optional [pinned-loader source audit](source_review/README.md) and [bootstrap/ownership contract](../../docs/ota-bootstrap-contract.md) record the exact failure path, maximum-version tradeoff and raw-HCI trust boundary. See the design review disposition before any implementation.

## Optional post-boot checks

Private controllers can call `bench_loop.run(..., checks=[('ble', check)])`.
Each zero-argument callable runs once, after candidate `boot_check` and before
restore, as a stage with its supplied unique name. It returns a dictionary with
`result` equal to `passed`, `failed`, or `skipped`; a skip requires a nonempty
`reason`. A failed check, invalid result or exception stops further checks and
restores, with `candidate_failed_restored` and the existing quarantine policy.
A skip permits subsequent checks and restore, but produces
`candidate_incomplete_restored`, never a pass. Successful restoration after skips
can release the lease. `checks_ran` lists attempted checks; `checks` also records
checks that were not reached. Restore failures retain precedence over all check
outcomes. Process crashes still require manual reconciliation.

`ble_check.BLECheck(private_profile, new_local_receipt_path)` supplies this hook.
The private JSON profile specifies `ssh_host` (one SSH config host alias), absolute
remote `app` and `receipt_dir` paths, and optional `mode` (`session`, the default,
or `audio`) and `expected_serial`. Audio requires the independently obtained
private serial. Session asks the helper for a 20-second deadline and audio for a
3-second capture. SSH allows 65 seconds for the launch and 20 each for the receipt
fetch and its removal. The remote receipt directory must already exist. The adapter
launches the app with `open -n -W` through SSH, then fetches its unique JSON receipt
(up to 4 MiB; larger fails as `ble_invalid_receipt`) and removes the remote copy;
Launch Services exit status alone never establishes a pass. Remote launch or fetch
errors are skipped as `central_unreachable: BLE was not tested`, without including
argv, stdout or stderr. Malformed or empty receipts that arrived still fail as
`ble_invalid_receipt`; local receipt I/O errors also fail. Nothing is retried, and
this module does nothing on import.

Only receipt outcome `passed` with `identity.status == matched` and a configured
`expected_serial` can pass. A session profile without `expected_serial` is allowed
but cannot produce a BLE pass. Other identity statuses on a passed receipt are
skipped because identity was not established. Identity statuses `wrong` and
`absent` are skipped with that status named, including on `gatt_failed` receipts.
`no_advertisement`, `permission_denied`, `bluetooth_off`, `connect_failed` and `interrupted` are
also skipped with an explicit “BLE was not tested” reason. On this antenna-less
bench, missing advertisements or a failed connection cannot diagnose firmware
health. Other `gatt_failed`, `audio_failed` and unknown outcomes fail; unknown
outcomes never become a pass or skip based on identity metadata. An audio pass
establishes notification continuity, not decoded audio quality. Profiles and fetched
receipts can contain private identifiers and must stay outside Git. This tool does not prepare remote
hosts, grant Bluetooth permission, change TCC or retry another target.

Offline verification (no SSH, radio or jig):

```sh
python3 -m unittest discover -s omi/firmware/tools/cv1 -p test_bench_loop.py -v
python3 -m unittest discover -s omi/firmware/tools/cv1 -p test_ble_check.py -v
```
