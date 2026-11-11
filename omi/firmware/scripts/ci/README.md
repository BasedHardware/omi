# Firmware CI / Release

Automation for building and releasing **Omi CV1** firmware (nRF5340).

Workflow: [`.github/workflows/firmware_release.yml`](../../../../.github/workflows/firmware_release.yml)

## How it works

A firmware "release" is a **GitHub Release** in a specific shape that the
backend ([`backend/routers/firmware.py`](../../../../backend/routers/firmware.py))
reads and serves to the app as an OTA update. The workflow builds the firmware
or promotes tested artifacts to that Release.

The contract the backend requires (do not break these):

| Requirement | Value |
|---|---|
| Tag | `Omi_CV1_v<ver>` — **no** `OTA` in the tag |
| OTA asset name | must contain `ota` **and** end `.zip` (e.g. `Omi_CV1_OTA_v3.0.20.zip`) |
| Release state | published, **non-draft, non-prerelease** |
| Body | must contain a `<!-- KEY_VALUE_START … KEY_VALUE_END -->` block with `release_firmware_version` |

The firmware version is read from `CONFIG_BT_DIS_FW_REV_STR` in
[`omi/firmware/omi/omi.conf`](../../omi/omi.conf) (the build copies `omi.conf`
→ `prj.conf`, so this string is also baked into the binary's BLE DIS).

## Releasing a new CV1 version

Follow the [tested-byte release runbook](../../docs/cv1-release-safety.md).
Build-only runs produce `cv1-qa-release` and a separate bench-symbols artifact.
Publishing requires `qa_run_id` from this workflow at the exact main SHA and
never rebuilds. OTA packages omit the network image unless explicitly opted in.
New releases start at 1%; David expands the rollout by editing the release body.
The runbook covers missing client identifiers, the kill switch, cache latency,
and reserved emergency-revert versions.

## Scripts

- `build-cv1.sh` — runs inside `ghcr.io/zephyrproject-rtos/ci` (firmware bind-mounted
  at `/omi/firmware`): west init/update of NCS v2.9.0, image-scoped `omi_CONF_FILE=omi.conf`, and
  `west build … --sysbuild` (MCUboot-signed). Mirrors [`omi/firmware/omi/BUILD.md`](../../omi/BUILD.md).
  Outputs `dfu_application.zip`, `merged.hex`, `merged_CPUNET.hex`.
- `cv1_release.py` — validates inputs, packages QA bytes, verifies provenance and promotes them.
- `test_cv1_release.py` — offline packaging and promotion contract tests.
- `make-release-body.sh` — renders the GitHub Release body + `KEY_VALUE` block.

`cv1_bootloader.py` strictly parses and hashes every staged HEX at stage, promotion
and publish. App-core HEX carries the pinned jig-qualified MCUboot plus the exact staged OTA
app. CI must reproduce the approved build hash; equivalence/rebuild evidence is
uploaded separately from release assets. See [the bootloader runbook](../../docs/cv1-bootloader.md).

## Notes

- The Release is created by the **Omi Bot GitHub App** (`actions/create-github-app-token`,
  secrets `OMI_BOT_APP_ID` / `OMI_BOT_PRIVATE_KEY`) so it is clearly attributed to
  automation rather than a person — same as the desktop pipeline. The token is only
  minted on a publish run; build-only QA runs don't need the secrets.
- The build is heavy: ~1.5 GB NCS download + ~20-30 min on a cold cache.
- DK2 / OmiGlass are **not** automated here yet. DK2 can be added as a second job
  (NCS 2.7.0 + `adafruit-nrfutil`); OmiGlass uses a separate ESP32/PlatformIO toolchain.
- MCUboot signing uses the committed key `omi/firmware/bootloader/mcuboot/root-rsa-2048.pem`.
