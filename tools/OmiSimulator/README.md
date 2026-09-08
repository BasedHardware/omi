# Omi Simulator (v5)

macOS CoreBluetooth peripheral that simulates an Omi wearable for local React Native v5 development.

Placed at `tools/OmiSimulator` because the v5 tree has no `firmware/` directory (unlike main). Kept outside `react-native/` so product boundary checks can continue to ban app Swift while allowing this developer tool.

## Build / run (macOS)

Open in Xcode:

```bash
open tools/OmiSimulator/OmiSimulator.xcodeproj
```

Or build from the CLI (from the repo root):

```bash
xcodebuild \
  -project tools/OmiSimulator/OmiSimulator.xcodeproj \
  -scheme OmiSimulator \
  -configuration Debug \
  build
```

Then run the built `OmiSimulator.app`. Grant **Bluetooth** and **Microphone** permissions when prompted.

Do **not** overwrite `/Applications/Omi.app` — this is a separate Simulator target (`com.basedhardware.OmiSimulator`).

## How discovery works

RN v5 scans by the Omi **audio service UUID**:

`19B10000-E8F2-537E-4F6C-D104768A1214`

See:

- `react-native/android/app/src/main/java/com/rnruntime/OmiBleController.kt`
- `react-native/macos/RnRuntime-macOS/OmiNativeModule.mm` / `react-native/ios/RnRuntime/OmiNativeModule.mm`

When the advertisement local name is missing, the Android stack defaults the display name to `"Omi"`.

This simulator advertises local name **`Omi Devkit`**. On macOS, CoreBluetooth often **ignores** `CBAdvertisementDataLocalNameKey` and uses the Mac’s computer name instead — discovery still succeeds via the service UUID.

After connect, RN reads standard Device Information Service `180A` characteristics (see `OmiDeviceInformation`):

| UUID | Field          | Simulator value   |
|------|----------------|-------------------|
| 2A24 | model          | Omi Devkit        |
| 2A26 | firmware       | sim-1.0.0         |
| 2A27 | hardware       | mac-simulator     |
| 2A29 | manufacturer   | Based Hardware    |
| 2A25 | serial         | OMI-SIM-0001      |

## Verify from the RN app

1. Start this simulator (Bluetooth on).
2. In the RN v5 app on **Android** or **macOS**, start a BLE scan.
3. The device should appear (filtered by service UUID). Name may show as `Omi Devkit`, `Omi`, or your Mac name depending on platform/local-name behaviour.
4. Connect — the device `information` map should include model / firmware / hardware / manufacturer / serial as above.

Optional: confirm services with LightBlue or nRF Connect (`180A` + `19B10000-…`).

## Remaining Mac limitation

Advertised BLE local name is not reliably visible to other apps on the same Mac. Prefer service-UUID discovery and the Device Information characteristics for a recognisable Omi/DevKit identity.
