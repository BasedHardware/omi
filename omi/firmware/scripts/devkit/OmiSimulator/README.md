# Omi Simulator

Simulator of BasedHardware Omi device.

The primary emulator is a Rust-owned Crepuscularity/GPUI macOS test bench. It discovers the Bluetooth targets known to macOS, exposes every product type supported by the app, and marks capabilities unavailable unless a matching contract exists in this repository.

The CLI can also advertise an app-connectable Omi peripheral through macOS CoreBluetooth. Rust owns the profile, state, and packets; the Swift process only publishes the configured GATT database and notifications.

```bash
cargo run --bin omi-product-cli -- simulate
button press
button release
battery 42
audio 01020304
status
stop
```

The process advertises the production Omi audio and button services and exposes readable battery, model, firmware, hardware, and manufacturer characteristics. Audio input is hexadecimal fixture bytes and uses the production audio notification characteristic.

```sh
cargo run
cargo test
```

The same Rust button wire values and portable state transitions run on QEMU's Arm MPS2-AN386, a board also supported by Zephyr:

```sh
cd qemu
cargo run --release
```

This checks portable firmware logic on a Cortex-M4 CPU. It does not emulate the nRF5340, its Bluetooth radio, GPIO timing, microphone, storage, power behavior, or flashing.

The nRF5340 BabbleSim lane builds the production Zephyr transport, settings, and button GATT sources with NCS 2.9.0, runs an application core and network core together, and connects a simulated central over the modeled radio:

```sh
omi/firmware/scripts/ci/check-bsim.sh
```

The central verifies Omi advertising, connection, button reads, and persisted settings writes and reads. BabbleSim does not model the CV1 microphone, SD card, haptics, battery ADC, LEDs, or physical button GPIO, so those drivers are disabled while their Bluetooth contracts remain production-owned.

Omi and Omi DevKit expose the firmware button wire values, audio, battery, device information, settings, and storage contracts. Omi Glass exposes only the contracts represented in the app. Other product profiles remain visible with unavailable capabilities instead of simulated success.

Select and validate firmware in the test bench. DevKit flashing requires `adafruit-nrfutil` and a serial port supplied as `OMI_EMULATOR_SERIAL`. The test bench shows running, completed, failed, and cancelled states. Host flashing for other products is unavailable because this repository does not provide a compatible host-side protocol.

The JSON CLI exposes the same live hardware paths:

```sh
cargo run --bin omi-product-cli -- scan
cargo run --bin omi-product-cli -- connect DEVICE_ID
cargo run --bin omi-product-cli -- probe DEVICE_ID
cargo run --bin omi-product-cli -- button monitor DEVICE_ID 30
cargo run --bin omi-product-cli -- disconnect DEVICE_ID
cargo run --bin omi-product-cli -- nrfutil list
cargo run --bin omi-product-cli -- nrfutil program merged.hex CONTROLLER_SERIAL
cargo run --bin omi-product-cli -- mcumgr zephyr.signed.bin 'peer_name=Omi'
```

`probe` reads the discovered service set, standard Device Information and Battery characteristics, and the Omi audio codec, settings, storage, button notification, and SMP surfaces. Nordic controller programming uses `nrfutil device` with read-back verification followed by reset. CV1 BLE OTA uses Zephyr's configured SMP service through `mcumgr` and accepts only a signed MCUboot `.bin`. DevKit serial DFU continues to use `adafruit-nrfutil`. Firmware ZIP inspection rejects corrupt archives, unknown product names, missing programmable CV1 images, and DevKit packages without a JSON manifest.

The Swift Xcode target remains only as the existing CoreBluetooth peripheral adapter reference.

## Limitations

On the Mac, name advertised for the BLE Peripheral is the name of the machine.

The latest source code of the Omi app discovers and connects to the Omi device by service UUID, so this works fine.

However, previoys versions of the Omi app looked for a device named "Friend" (or "Super").

One solution is to rename your machine to one of those names.  

If you need to work with older code, another solution is to rebuild the Omi app yourself.  
In AppWithWearable project, in file /lib/utils/ble/scan.dart, at line 11, add the name of your machine to the condition, like  
``` dart
(device) => device.name == 'Friend' || device.name == 'Super' || device.name == 'my machine name',
```
