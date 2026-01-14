# watchOS Companion App

The Omi watchOS companion app is **disabled by default** for local development but is **automatically enabled for CI/CD builds** via Codemagic.

## How It Works

The watchOS target (`omiWatchApp`) exists in the Xcode project but is **not linked** to the main Runner target by default. This allows developers to build and run the iOS app without requiring watchOS code signing configuration.

During CI builds on Codemagic, the `enable_watchos.sh` script is run automatically to:
1. Add `omiWatchApp` to the "Embed Watch Content" build phase
2. Add a target dependency from Runner to omiWatchApp
3. Add `WKCompanionAppBundleIdentifier` to Info.plist

## watchOS Source Files

The watchOS source code is in `app/ios/omiWatchApp/`:
- `omiwatchApp.swift` - SwiftUI entry point
- `ContentView.swift` - Main UI with recording button
- `BatteryManager.swift` - Battery monitoring
- `WatchAudioRecorderViewModel.swift` - Audio recording logic
- `Assets.xcassets/` - App icons and assets

## For Local Development

### Option 1: Build iOS Only (Default)

Simply build and run the iOS app normally. The watchOS app will not be built, and no signing configuration is required for it.

### Option 2: Enable watchOS Locally

If you want to test the watchOS app locally:

1. Run the enable script:
   ```bash
   cd app/ios
   ./scripts/enable_watchos.sh
   ```

2. Open `Runner.xcworkspace` in Xcode

3. Select the `omiWatchApp` target and configure signing:
   - Go to **Signing & Capabilities**
   - Select your development team
   - Ensure automatic signing is enabled

4. Build the Runner scheme (it will now include the watch app)

### Option 3: Manual Configuration

If you prefer to configure manually in Xcode:

1. Open `Runner.xcworkspace` in Xcode
2. Select the `Runner` target > **Build Phases**
3. In **Embed Watch Content**, click `+` and add `omiWatchApp.app`
4. Go to **Dependencies** and add `omiWatchApp`
5. Select `Runner/Info.plist` and add:
   ```xml
   <key>WKCompanionAppBundleIdentifier</key>
   <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
   ```

## Why Is watchOS Disabled by Default?

1. **Signing Requirements**: watchOS apps require a valid development team and signing certificate, which blocks new developers from building the iOS app
2. **Optional Feature**: The watchOS companion is optional and not required for core Omi functionality
3. **Faster Development**: Most developers only need the iOS app for development and testing
4. **CI/CD Handles It**: Production builds via Codemagic automatically enable and build the watch app

## Questions?

If you need help with watchOS development, please open an issue on GitHub.
