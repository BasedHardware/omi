# CV1 tested-byte release runbook

CV1's installed MCUboot is overwrite-only and OTA cannot replace it. A signed
image that boots badly has no automatic runtime rollback. Signing uses randomized
RSA signatures: rebuilding tested source does not reproduce the tested bytes.

Release app-core HEX carries the pinned jig-qualified MCUboot and exact OTA app. Every staged HEX is
reparsed against the [bootloader policy](cv1-bootloader.md) at staging, promotion
and publish. The built/shipped loader must match the qualified .19 hash; factory .8 remains
an approved installed/restoration state. Never wire-flash stock MCUboot.

## Build, test, promote

1. Merge the intended source and firmware revision into main. Normally bump
   `CONFIG_BT_DIS_FW_REV_STR` in `omi/firmware/omi/omi.conf`. A `version` override
   is also supported. The workflow sets both BLE DIS and the app's signed
   MCUboot header version to that value; packaging verifies the signed header.
2. Dispatch `firmware_release.yml` **without** `publish` to build QA artifacts.
   The run first compiles and proves the pinned MCUboot, then executes the simulator gate (`omi/sim/README.md`, "Scenario
   suite": every scenario plus 40 fuzz seeds at this SHA). Staging fails
   closed without a passing `sim-report.json` for the same SHA and version;
   the report ships in the QA artifact, its SHA-256 is in `qa-provenance.json`
   and promotion and publish revalidate it. The simulator is source-level
   evidence, not a test of the signed bytes; the bench (step 3) still is.
   The default OTA zip contains only app image 0. Set `include_network_core=true`
   only when intentionally testing a paired app/radio update. This changes zip
   packaging only. Release staging constructs app-core HEX from the pinned qualified MCUboot and
   staged OTA signed app bytes; settings, UICR and network addresses are excluded. `merged_CPUNET.hex` stays separate.
3. Download `cv1-qa-release-<run ID>-<attempt>` and test its `Omi_CV1_OTA_v<version>.zip` on the bench
   through the stock app. Record the run ID, attempt, asset SHA-256 from
   `qa-provenance.json`, phone/app version, device identity and health results.
   The bench receipt must also report the SHA-256 of `omi.signed.bin` extracted
   from that zip (not the zip hash); compare it with `signed_sha256` in provenance.
   Use the separate `cv1-bench-symbols-v<version>` app ELF for debugger symbols
   (including `curr_tick` when present in that build). Symbols are never released.
   This workflow verifies provenance, not that someone performed physical QA.
4. After approval to publish, dispatch from main with `publish=publish` and
   `qa_run_id=<tested run ID>`, `qa_run_attempt=<tested attempt>` and
   `tested_signed_sha256=<bench-reported omi.signed.bin SHA-256>`.
   All three inputs are required for publish. Use the same `version` and network-core opt-in
   as QA. Example (operator procedure, not an instruction to run now):

   ```bash
   gh workflow run firmware_release.yml --ref main \
     -f publish=publish -f qa_run_id=123456789 -f qa_run_attempt=1 \
     -f tested_signed_sha256='<64 hex characters from the bench receipt>' \
     -f version=3.0.22 -f changelog='Release notes'
   ```

   The run must belong to this repository and workflow, have completed
   successfully as a manual build-only run, and have the exact SHA of the main
   ref being published. Artifacts bind the run attempt, version, network opt-in
   and asset checksums. Missing/expired/old-format artifacts fail closed. A
   rerun cannot replace a tested attempt: promotion queries the exact attempt
   and downloads only its run-and-attempt-scoped artifact name. It never falls
   back to the old run-wide artifact name. Older artifacts need a new QA build
   and bench receipt. A mismatched bench signed-image hash fails closed.
   Advancing main requires a new QA build at that SHA. No rebuild, signing,
   repackaging or renaming occurs on publish. Only the tested zip, qualified merged app-core HEX and separate CPUNET
   HEX are attached. The git refs API atomically creates the tag at the
   tested SHA and refuses existing tags. A release is created as a draft and its
   tag is verified again before publication. If verification fails, it stays a
   draft; inspect the tag/draft before an approved cleanup and retry.

## Release checklist (each gate fails closed)

- **G0 candidate.** Fixes merged to main with host tests green and the
  simulator suite (`omi/sim/scenario_runner.py`) passing at that SHA. Every field bug in the release has
  a scenario whose `baseline_bug` reproduces on the previous release's sources
  (`scenario_runner.py --baseline`) and whose `expect` passes on the candidate.
  `omi/sim/check_isolation.py --base <previous release>` lists only the
  declared fixes.
- **G1 version minted once.** Bump `CONFIG_BT_DIS_FW_REV_STR` only when the fix
  set is complete and G0 is green at that SHA. A blocked candidate does not
  consume a version number.
- **G2 QA build + simulator gate.** Build-only `firmware_release.yml` run at that
  SHA (step 2), `sim-report.json` in the artifact.
- **G3 bench on the QA bytes.** Step 3 plus the safe-mode jig checks in
  `safe-mode.md`; the gesture subset can be scripted from the scenarios with
  `tools/cv1/jig_gestures.py`.
- **G4 publish.** Step 4 with all three provenance inputs; the promoted
  attempt's simulator report is revalidated by code.

## Rollout plan: new releases start at 1%, and David expands

The workflow writes `rollout_percent:1` and `blocked:false` in the existing
`KEY_VALUE` release-body block. A normal publish permits only 0% or 1%; wider
cohorts require editing the published body later. `emergency_revert=true`
explicitly permits an initial cohort up to 100%. `blocked` remains configurable.
The body generator rejects inputs containing lines parsed as policy/version
keys or metadata delimiters, and writes authoritative metadata after changelog.
David
expands the cohort by editing **that block** (for example 1 → 10 → 50 → 100)
only after the current cohort's install success, reconnect, firmware identity,
audio capture and battery checks remain clean. David owns each expansion and
reviews the first cohort before the next expansion; no automatic expansion is
scheduled. Keep the prior eligible release published while observing the ramp.

The app supplies `device_id` as the lowercase hex SHA-256 of the normalized DIS
serial's UTF-8 bytes, never the raw serial. Both automatic discovery and the
firmware update page use the serial already read from the pendant. If no serial
is available, the parameter is omitted.

`/v2/firmware/latest` hashes the supplied `device_id` again with SHA-256, takes the
first eight digest bytes as a big-endian integer modulo 100, and admits buckets
below `rollout_percent`. The hash excludes the release version, so cohorts are
stable and nested. Selection retains publication order, firmware minimums and
newer-version checks; an excluded device receives its newest eligible release,
or the existing 404/no-update response. Missing `rollout_percent` means 100%,
preserving existing releases. Invalid explicit policies exclude the release.

New releases start at 1% of devices on an app build that sends `device_id`.
Older app builds and devices without a usable DIS serial receive a new release
only at 100%, retaining an earlier eligible release during the ramp. David
expands each cohort after the health checks above; there is no automatic ramp.

### Tester audiences

Two optional keys in the same block offer a release to named testers whatever
its `rollout_percent`, so a release published at 0% can reach only them. Neither
needs a DIS serial, so they also reach units on 3.0.21 and earlier.

- `allow_uid_sha256:<hex>,<hex>`: hex SHA-256 of each tester's Firebase uid
  (`printf %s "$UID" | shasum -a 256`). Hashes, because release bodies are
  public. The server verifies the app's token only when some release carries
  this key; a missing or invalid token just isn't on the list.
- `channels:beta`: callers whose `X-Omi-App-Channel` is listed (`beta` is
  TestFlight and non-production builds; `store` is everything else). While
  `channels` is set, nobody outside those channels or the allowlist gets the
  release, whatever the percentage. Remove it to start the device ramp.

A malformed value in either key excludes the release. `blocked:true` still wins.
Stable discovery has no token or channel, so an audience never admits a release there.

Set `blocked:true` in the same block to stop all new offers, even at 100%.
The stable and exact-version endpoints also honor the block. Stable discovery
excludes partial rollouts because it has no device identifier. Explicit version
requests ignore `rollout_percent` for support and emergency reverts, but return
404 for a blocked release. This cannot cancel an in-progress download/install or
recall a cached/direct asset URL. Release metadata is normally cached for five
minutes; during GitHub failures the shared helper may serve last-known-good
metadata for up to a day. Verify fresh responses after any body edit; this is
an offer kill switch, not immediate device revocation. Restoring `blocked:false`
resumes only the configured cohort.

## Reserved emergency revert versions

**3.0.90 through 3.0.99 (3.0.9x) are reserved for emergency reverts.** The workflow
rejects this range unless `emergency_revert=true`, on both QA and publish runs.
Normal versions must leave that space available; do not consume it for features.

Installed MCUboot refuses downgrades based on the signed image header, not the
BLE string. Revert by rebuilding and **re-signing the last good source with a
version higher than the bad installed image**, then testing those new bytes and
promoting that QA run. Do not re-serve a lower-version zip. In particular older
retained artifacts used a `0.0.0+0` signed header; their BLE version alone is not
a sufficient rollback receipt. A revert candidate needs a reviewed source
commit carrying the last good changes and the higher version; QA and publish
must still share the exact main SHA. Set `emergency_revert=true` explicitly in
both dispatches and retain the 1%/David expansion plan or explicitly record the
reason for overriding it. After a 3.0.9x revert, future releases also need a
higher signed version (for example 3.1.0). These ten numbers are finite; never
claim they provide automatic recovery or recover a device that cannot do OTA.

## Packaging evidence and local verification

NCS 2.9.0 [`cmake/sysbuild/zip.cmake`](https://github.com/nrfconnect/sdk-nrf/blob/v2.9.0/cmake/sysbuild/zip.cmake)
selects `omi.signed.bin` as image 0 and the signed network output as
`ipc_radio.bin`, image 1. It calls `generate_dfu_zip` in
[`cmake/fw_zip.cmake`](https://github.com/nrfconnect/sdk-nrf/blob/v2.9.0/cmake/fw_zip.cmake),
which invokes [`scripts/bootloader/generate_zip.py`](https://github.com/nrfconnect/sdk-nrf/blob/v2.9.0/scripts/bootloader/generate_zip.py)
to create a format-1 zip and per-file `manifest.json`. `build-cv1.sh` obtains it
from the unchanged sysbuild. `cv1_release.py` filters the manifest and copies
image 0 verbatim when staging the QA artifact. It preserves the app entry's
size, slot, load address and version and all top-level metadata.

The app's `FirmwareMixin.processZipFile` loops over `manifest.files`, creates
one `mcumgr.Image` per entry and passes the list to `updateManager.update`.
`Manifest.fromJson` requires explicit image indexes only for multi-image input;
`ManifestFile.image` accepts `"0"` and defaults a missing index to 0. No second
image is required by this source path. The locked `mcumgr_flutter` package was
also inspected with its archive SHA-256 checked against `app/pubspec.lock`: its
Dart update method serializes the supplied list, and the Android/iOS bridges
map that list directly into their native manager's list-based start method.
The retained app image has no image-dependency TLV requiring a paired network
update. This is source/artifact verification; a real
single-image BLE install and postboot radio/health checks remain bench gates.

Run offline policy/packaging tests with:

```bash
python3 -m unittest discover -s omi/firmware/scripts/ci -p 'test_cv1_release.py'
```

Backend policy tests live in `backend/tests/unit/test_firmware_rollout.py`;
use the selected-file `BACKEND_UNIT_TEST_FILE_LIST` convention in
`backend/test.sh`. Route tests and preflight through `omi-heavy run --` on shared
hosts. No secrets, workflow dispatch, release mutation or device flashing is
needed for these tests.
