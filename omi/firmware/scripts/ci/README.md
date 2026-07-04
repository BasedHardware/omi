# Firmware CI / Release

Automation for building and releasing **Omi CV1** firmware (nRF5340).

Workflow: [`.github/workflows/firmware_release.yml`](../../../../.github/workflows/firmware_release.yml)

## How it works

A firmware "release" is a **GitHub Release** in a specific shape that the
backend ([`backend/routers/firmware.py`](../../../../backend/routers/firmware.py))
reads and serves to the app as an OTA update. The workflow builds the firmware
and publishes that Release.

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

1. Bump `CONFIG_BT_DIS_FW_REV_STR` in `omi/firmware/omi/omi.conf` and merge it.
2. Dry run (build only, artifacts attached to the Actions run, **no** release):
   ```bash
   gh workflow run firmware_release.yml
   ```
3. Publish:
   ```bash
   gh workflow run firmware_release.yml \
     -f publish=publish \
     -f changelog="Removed BLE bond-key|Bug fixes" \
     -f minimum_firmware_required=3.0.6 \
     -f minimum_app_version=1.0.74 \
     -f minimum_app_version_code=438 \
     -f ota_update_steps=battery,internet
   ```
   `version` defaults to the `omi.conf` value; pass `-f version=3.0.21` to override.

Publishing is only allowed from the **`main`** branch (the build-only path runs
from any branch). The publish step also refuses to overwrite an existing
`Omi_CV1_v<ver>` tag — bump the version if you need to re-release.

## Scripts

- `build-cv1.sh` — runs inside `ghcr.io/zephyrproject-rtos/ci` (firmware bind-mounted
  at `/omi/firmware`): west init/update of NCS v2.9.0, `cp omi.conf prj.conf`, and
  `west build … --sysbuild` (MCUboot-signed). Mirrors [`omi/firmware/omi/BUILD.md`](../../omi/BUILD.md).
  Outputs `dfu_application.zip`, `merged.hex`, `merged_CPUNET.hex`.
- `make-release-body.sh` — renders the GitHub Release body + `KEY_VALUE` block.

## Notes

- The Release is created by the **Omi Bot GitHub App** (`actions/create-github-app-token`,
  secrets `OMI_BOT_APP_ID` / `OMI_BOT_PRIVATE_KEY`) so it is clearly attributed to
  automation rather than a person — same as the desktop pipeline. The token is only
  minted on a publish run; build-only QA runs don't need the secrets.
- The build is heavy: ~1.5 GB NCS download + ~20-30 min on a cold cache.
- DK2 / OmiGlass are **not** automated here yet. DK2 can be added as a second job
  (NCS 2.7.0 + `adafruit-nrfutil`); OmiGlass uses a separate ESP32/PlatformIO toolchain.
- MCUboot signing uses the committed key `omi/firmware/bootloader/mcuboot/root-rsa-2048.pem`.
