# Android Phone + Omi Glass Setup Guide

This guide is for developers who are comfortable with Android Studio but have never used Omi or Omi Glass before.

The Omi mobile app in this repository is a **Flutter app**, not a plain native Android app. The Android project lives under `app/android`, while the Flutter source code lives under `app/lib`.

## What you are setting up

You will set up three things:

1. **Your Android phone** as a physical development device.
2. **The Omi Flutter app** from this repository, running as the `dev` flavor on your phone.
3. **Your Omi / Omi Glass device**, paired to the app over Bluetooth Low Energy (BLE).

Useful repository paths:

| Purpose | Path |
| --- | --- |
| Flutter mobile app | `app/` |
| Android Gradle project | `app/android/` |
| Android manifest and permissions | `app/android/app/src/main/AndroidManifest.xml` |
| Mobile app setup script | `app/setup.sh` |
| Omi Glass project | `omiGlass/` |
| Omi Glass firmware guide | `omiGlass/firmware/readme.md` |
| Existing app setup docs | `docs/doc/developer/AppSetup.mdx` |
| Existing Omi Glass onboarding docs | `docs/onboarding/omi-glass.mdx` |

## 1. Install development tools

Install these before opening the project in Android Studio:

- **Android Studio**. Android Studio Panda or newer should work if it has a recent Android SDK.
- **Flutter SDK**. This repo currently expects Flutter around `3.35.3` according to `app/setup.sh`.
- **Dart**, included with Flutter.
- **JDK 21**.
- **Android SDK Platform 36**. The app compiles with `compileSdkVersion 36`.
- **Android NDK `28.2.13676358`**. The app uses native audio dependencies.
- **Git**.

Check your Flutter/Android environment:

```bash
flutter doctor -v
```

If Flutter cannot find JDK 21, point Flutter to it. Example on macOS:

```bash
flutter config --jdk-dir /Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home
```

On Linux, the path is usually under `/usr/lib/jvm/`, for example:

```bash
flutter config --jdk-dir /usr/lib/jvm/java-21-openjdk-amd64
```

## 2. Prepare your Android phone

Use a real Android phone for Omi/Omi Glass testing because Bluetooth, microphone, background services, and companion-device behavior cannot be fully tested in the emulator.

1. Connect your phone to your computer with a USB cable that supports data transfer.
2. On the phone, open **Settings → About phone**.
3. Tap **Build number** 7 times to enable Developer Options.
4. Go back to **Settings → System → Developer options**. The exact path varies by Android manufacturer.
5. Enable **USB debugging**.
6. When prompted, allow USB debugging from your computer.
7. Enable **Bluetooth**.
8. Keep **Location** enabled, especially on Android 11 or older. Android 11 and below require location permission for BLE scanning.

Confirm the phone is visible:

```bash
adb devices
flutter devices
```

You should see your Android phone listed. If it says `unauthorized`, unlock the phone and accept the USB debugging prompt.

## 3. Set up the Omi Flutter app

From the repository root:

```bash
cd app
bash setup.sh android
```

The setup script does several things for Android development:

- Copies the prebuilt Android signing config into `app/android/key.properties`.
- Copies prebuilt Firebase config into `app/android/app/src/dev/google-services.json`.
- Creates `.dev.env` with the development API base URL.
- Runs `flutter pub get`.
- Runs Dart code generation with `dart run build_runner build`.
- Starts the app with `flutter run --flavor dev`.

The dev Android flavor is defined in `app/android/app/build.gradle`:

| Flavor | Android application id | App name |
| --- | --- | --- |
| `dev` | `com.friend.ios.dev` | `Omi Dev` |
| `prod` | `com.friend.ios` | `Omi` |

For local development, use the `dev` flavor unless you specifically know you need production.

## 4. Run the app on your real Android phone from the terminal

If the setup script already launched the app, you can skip this section. Otherwise, from `app/` run:

```bash
flutter devices
flutter run --flavor dev
```

If multiple devices are connected, choose a specific device id:

```bash
flutter run --flavor dev -d YOUR_DEVICE_ID
```

For verbose logs:

```bash
flutter run -v --flavor dev -d YOUR_DEVICE_ID
```

## 5. Run the app from Android Studio

You can use Android Studio, but remember this is a Flutter project.

Recommended workflow:

1. Install the **Flutter** and **Dart** plugins in Android Studio.
2. Open the `app/` folder as the project.
   - Opening only `app/android/` works for Android Gradle inspection, but Flutter run/debug is easier when opening `app/`.
3. Wait for Android Studio to index the project.
4. Select your physical Android phone as the target device.
5. Create or edit a Flutter run configuration:
   - Dart entrypoint: `app/lib/main.dart`
   - Additional run args: `--flavor dev`
6. Press **Run**.

If Android Studio has trouble with the Flutter run configuration, use Android Studio for editing and run from the terminal:

```bash
cd app
flutter run --flavor dev -d YOUR_DEVICE_ID
```

## 6. Build and install an APK on your phone

For day-to-day development, prefer `flutter run` because hot reload/hot restart is faster.

If you want to build an APK and install it manually:

```bash
cd app
flutter build apk --flavor dev
flutter install -d YOUR_DEVICE_ID
```

The generated APK is usually under:

```text
app/build/app/outputs/flutter-apk/
```

## 7. First-time Omi / Omi Glass setup with your Android phone

Before pairing:

1. Charge your Omi / Omi Glass.
2. Keep your Android phone nearby.
3. Turn on Bluetooth on the phone.
4. Open the `Omi Dev` app you just installed.
5. Keep the app running. Do not force-close it, because the BLE connection and transcription rely on the app process.

### Omi Glass power-on

For Omi Glass, the existing onboarding docs say to power on by pressing the side button for about **3 seconds**.

For the standard Omi wearable, the existing onboarding docs say:

- Press the button once to turn it on.
- Red light means powered on but disconnected.
- Blue light means connected.

### Pair in the app

1. Open the Omi app on Android.
2. Sign in if the app asks you to.
3. Start onboarding or open the connection guide.
4. Choose **Omi** or **Omi Glass**.
5. Grant requested permissions:
   - Bluetooth scan/connect.
   - Microphone.
   - Notifications.
   - Background/battery optimization permission if prompted.
   - Location on Android 11 or below, or if your phone requires it for BLE scanning.
6. Wait for nearby devices to appear.
7. Tap your Omi / Omi Glass device.
8. Android may show a system companion-device prompt. Accept it.
9. Wait for the app to show the device as connected.

The app uses BLE scanning and connection code in `app/lib/providers/onboarding_provider.dart`. On Android it may request Android Companion Device association before connecting.

## 8. Test that the device is working

After pairing:

1. Keep the Omi app open in the foreground for the first test.
2. Speak near the Omi / Omi Glass microphone.
3. Wait 30–60 seconds for initial transcription.
4. Check the app for live transcript text or conversation updates.
5. Check whether the battery indicator appears.

If nothing appears immediately, wait a little. The onboarding docs mention that first transcription can be delayed.

### Local YOLOE frame scheduling note

When local YOLOE object announcements are enabled, the app processes Omi Glass photo frames on the Android phone and skips backend image upload for those frames. The app-side scheduler processes every received image frame when inference keeps up; if inference is busy, it keeps only the newest pending frame and drops older pending frames so stale images do not build up lag.

The developer Local YOLOE debug panel reports incoming FPS, inference FPS, received/processed/dropped/throttled frame counts, latency, and last announcement time. If frames arrive slowly, that may be an Omi Glass firmware/photo-controller capture cadence limitation rather than an app scheduling issue. Faster capture rates can require firmware changes; this app-side path is designed to be ready for faster incoming frames when firmware provides them.

## 9. Omi Glass firmware notes

If the glasses do not power on, do not advertise over Bluetooth, or never connect, firmware may need to be flashed.

The detailed firmware guide is here:

```text
omiGlass/firmware/readme.md
```

The easiest firmware path described there is UF2 flashing:

1. Go to the firmware directory:

   ```bash
   cd omiGlass/firmware
   ```

2. Build the UF2 file:

   ```bash
   ./scripts/build_uf2.sh -e uf2_release
   ```

3. Put the ESP32-S3 board into bootloader mode:
   - Hold **BOOT**.
   - Press and release **RESET**.
   - Release **BOOT**.
   - A USB drive named `ESP32S3` should appear.

4. Copy `omi_glass_firmware.uf2` to the `ESP32S3` drive.
5. The board should flash and reboot automatically.

You can also use PlatformIO or Arduino CLI; see `omiGlass/firmware/readme.md` for those advanced paths.

## 10. Important Android permissions

The Android app requests permissions in `app/android/app/src/main/AndroidManifest.xml`, including:

- Internet access.
- Bluetooth scan/connect.
- Legacy Bluetooth permissions for Android 11 and below.
- Fine location.
- Microphone recording.
- Foreground service permissions for connected device, microphone, and location use.
- Companion-device background permissions.

When Android asks for these, allow them during development. Without them, BLE scanning, pairing, background capture, or transcription can fail.

## 11. Troubleshooting

### Android Studio or Flutter cannot see my phone

Try:

```bash
adb devices
flutter devices
```

If the device is missing:

- Use a different USB cable.
- Set USB mode to **File transfer**.
- Re-enable USB debugging.
- Revoke USB debugging authorizations and reconnect.
- Restart the ADB server:

  ```bash
  adb kill-server
  adb start-server
  adb devices
  ```

### `flutter doctor` shows Android SDK, JDK, or NDK problems

Open Android Studio → **Settings → Languages & Frameworks → Android SDK** and install:

- Android SDK Platform 36.
- Android SDK Build-Tools.
- Android SDK Platform-Tools.
- NDK `28.2.13676358`.
- CMake if Android Studio asks for it.

Make sure Flutter is using JDK 21:

```bash
flutter doctor -v
```

### The app builds but cannot find Omi Glass

Check:

- The glasses are charged.
- The glasses are powered on.
- Bluetooth is enabled on the phone.
- The app has Bluetooth permissions.
- On Android 11 or below, Location is enabled and location permission is granted.
- The device is close to the phone.
- The device is not already connected to another phone.

Then restart the app and try scanning again.

### Pairing starts but fails

Try:

- Turn Bluetooth off and on.
- Restart the Omi / Omi Glass device.
- Forget the device in Android Bluetooth settings if it is listed there.
- Reopen the app and pair again.
- Watch terminal logs from `flutter run` for BLE errors.

### Transcription does not appear

Try:

- Wait 30–60 seconds after connection.
- Confirm the phone has internet access.
- Confirm microphone permission is granted.
- Keep the app running; do not force-close it.
- Move the Omi / Omi Glass microphone closer to your mouth.
- Check whether the device battery is low.

### Omi Glass does not power on

Try:

- Charge for at least 30 minutes.
- Use a different USB-C cable.
- Check the charging LED.
- Review the battery and charging section in `omiGlass/firmware/readme.md`.

## 12. Command cheat sheet

From the repository root:

```bash
# Check toolchain
flutter doctor -v

# Set up and run Android dev app
cd app
bash setup.sh android

# List devices
flutter devices

# Run on connected Android phone
flutter run --flavor dev

# Run on a specific phone
flutter run --flavor dev -d YOUR_DEVICE_ID

# Build APK
flutter build apk --flavor dev

# Install built app
flutter install -d YOUR_DEVICE_ID
```

Omi Glass firmware quick path:

```bash
cd omiGlass/firmware
./scripts/build_uf2.sh -e uf2_release
```

Then put the ESP32-S3 into bootloader mode and copy the generated UF2 file to the `ESP32S3` USB drive.

## 13. Where to look next

- App setup: `docs/doc/developer/AppSetup.mdx`
- Omi onboarding: `docs/onboarding/omi.mdx`
- Omi Glass onboarding: `docs/onboarding/omi-glass.mdx`
- Omi Glass firmware: `omiGlass/firmware/readme.md`
- Mobile app source: `app/lib/`
- Android app config: `app/android/`
