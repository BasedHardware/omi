# Building Omi CV1 Firmware

This is the build contract referenced by `scripts/ci/build-cv1.sh`,
`scripts/ci/README.md`, and `.github/workflows/firmware_release.yml`.

## Toolchain

- **nRF Connect SDK v2.9.0** (pinned; installs with
  `nrfutil toolchain-manager install --ncs-version v2.9.0`)
- CMake ≥ 3.20, Ninja, ccache; Python 3.8+ with the `ecdsa` package
  (needed by MCUboot's `imgtool` signing step)
- CI builds inside `ghcr.io/zephyrproject-rtos/ci:v0.26.13` (digest-pinned in
  `.github/workflows/firmware_release.yml`)

## Workspace

The west workspace is **not** committed. Create it next to the firmware tree:

```bash
cd omi/firmware
mkdir -p v2.9.0 && cd v2.9.0
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.9.0 .
west update
west zephyr-export
```

## Build (the blessed command)

The production config is `omi.conf` — Zephyr builds `prj.conf` by default, so
copy it across first (CI does exactly this):

```bash
cp ../omi/omi.conf ../omi/prj.conf

west build -b omi/nrf5340/cpuapp ../omi --sysbuild -d build --pristine always \
  -- -DBOARD_ROOT=..
```

- Board: `omi/nrf5340/cpuapp` (custom board in `boards/omi/`, registered via
  `-DBOARD_ROOT`). Do **not** use `xiao_ble/nrf52840/sense` — that is the
  DevKit (nRF52840) target.
- `--sysbuild` is required: it builds the application, MCUboot, and the
  network-core image together.
- The firmware version the device advertises over BLE is
  `CONFIG_BT_DIS_FW_REV_STR` in `omi.conf`.

## Outputs (`v2.9.0/build/`)

| File | Purpose |
| --- | --- |
| `dfu_application.zip` | OTA package — what the Omi app / nRF Connect Mobile installs (MCUmgr DFU) |
| `merged.hex` | Full-flash image, application core (J-Link) |
| `merged_CPUNET.hex` | Full-flash image, network core (J-Link) |

CI fails loudly if any of the three is missing.

## Flashing

- **OTA (normal path):** install `dfu_application.zip` via the Omi app
  (Settings → Device Settings → Update Firmware) or nRF Connect for Mobile.
- **J-Link (recovery / first power-on):** flash `merged_CPUNET.hex` first, then
  `merged.hex`, over SWD (see `FLASH_3.0.8/` scripts; target
  `nRF5340_xxAA_NET` then `nRF5340_xxAA_APP`).

## Release

`.github/workflows/firmware_release.yml` (manual dispatch) wraps this build and
publishes the `Omi_CV1_v<ver>` GitHub Release that the backend serves as the
OTA update. See `scripts/ci/README.md`.
