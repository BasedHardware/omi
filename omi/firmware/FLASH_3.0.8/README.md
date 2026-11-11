# Archived CV1 3.0.8 factory images

These files preserve the factory bootloader reference. They are **not** a generic
installer for current releases. Never replace `merged.hex` with a downloaded
release HEX and run the historical two-core scripts: older release HEX files
may contain stock MCUboot, which breaks OTA installation on CV1.

Use BLE OTA for a working pendant. For SWD app recovery, follow
[the CV1 bootloader runbook](../docs/cv1-bootloader.md): validate the staged qualified app-core HEX,
back up the existing boot region, program only the app core and verify the
new boot hash. App-only recovery is a separate option for preserving an
approved loader; it uses the exact OTA signed app.
A blank device needs a separately qualified bootloader and factory procedure.
Do not mass erase, touch the network core, UICR or protection settings during
app recovery. The legacy batch launchers are disabled; the raw J-Link files
remain archival factory evidence, not an approved recovery path.

The factory region in `MAC/merged.hex` has SHA-256
`c80cf2fd68b67328c9c7692391a21f87630b266698c2ae9e251967f3e43da086`
for [0, 0x10000), with missing bytes filled by 0xff. See
[the historical release audit](../docs/cv1-bootloader-release-audit.md).
