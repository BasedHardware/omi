# Omi Simulator

Simulator of BasedHardware Omi device.

The primary emulator is a Rust-owned Crepuscularity/GPUI macOS test bench. It discovers the Bluetooth targets known to macOS, exposes every product type supported by the app, and marks capabilities unavailable unless a matching contract exists in this repository.

```sh
cargo run
cargo test
```

Omi and Omi DevKit expose the firmware button wire values, audio, battery, device information, settings, and storage contracts. Omi Glass exposes only the contracts represented in the app. Other product profiles remain visible with unavailable capabilities instead of simulated success.

Select and validate firmware in the test bench. DevKit flashing requires `adafruit-nrfutil` and a serial port supplied as `OMI_EMULATOR_SERIAL`. The test bench shows running, completed, failed, and cancelled states. Host flashing for other products is unavailable because this repository does not provide a compatible host-side protocol.

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
