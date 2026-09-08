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

## GATT services exposed

### Device Information (`180A`)

| UUID | Field          | Simulator value   |
|------|----------------|-------------------|
| 2A24 | model          | Omi Devkit        |
| 2A26 | firmware       | sim-1.0.0         |
| 2A27 | hardware       | mac-simulator     |
| 2A29 | manufacturer   | Based Hardware    |
| 2A25 | serial         | OMI-SIM-0001      |

### Battery (`180F`)

| UUID | Field  | Notes                                      |
|------|--------|--------------------------------------------|
| 2A19 | level  | Read + notify; default **87%**; UI slider  |

### Features (`19B10020-…`)

| UUID       | Notes                                                                 |
|------------|-----------------------------------------------------------------------|
| 19B10021-… | 4-byte LE bitmask **388** = button (bit2) + LED (bit7) + mic (bit8) |

Storage (bit6) is **not** advertised — no storage service in this cut.

### Button (`23ba7924-…`)

| UUID       | Notes                                                                 |
|------------|-----------------------------------------------------------------------|
| 23ba7925-… | Notify; UI **Double press** sends `[2,0,0,0,0,0,0,0]` (RN doublePress) |

### Settings (`19B10010-…`)

| UUID       | Field       | Notes                                      |
|------------|-------------|--------------------------------------------|
| 19B10011-… | LED         | Read/write 0–100; default 50               |
| 19B10012-… | mic gain    | Read/write 0–8; default 4                  |
| 19B10013-… | charging    | Read + notify; UI toggle (0/1)             |

### Audio (`19B10000-…`)

Unchanged: notify audio frames + read codec `0` (PCM16).

## Verify from the RN app

1. Start this simulator (Bluetooth on).
2. In the RN v5 app on **Android** or **macOS**, start a BLE scan.
3. The device should appear (filtered by service UUID). Name may show as `Omi Devkit`, `Omi`, or your Mac name depending on platform/local-name behaviour.
4. Connect — expect:
   - `information` map (DIS fields above)
   - `battery` ≈ 87 (updates when you move the slider)
   - `features` = 388 → `buttonSupported` once notify is up
   - `ledBrightness` / `microphoneGain` / `charging` populated
5. Tap **Double press** in the simulator → RN should emit a button double-press event (when audio notify is also active).

Optional: confirm services with LightBlue or nRF Connect.

## Still missing vs a full DevKit

- **Haptic** service (`cab1ab95-…`) — Find Device write path
- **Storage** service (`30295780-…`) + features bit6
- Reliable BLE **local name** on same-Mac discovery (CoreBluetooth quirk)

## Remaining Mac limitation

Advertised BLE local name is not reliably visible to other apps on the same Mac. Prefer service-UUID discovery and Device Information / Features characteristics for a recognisable Omi/DevKit identity.
