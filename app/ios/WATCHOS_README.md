# watchOS Companion App

The Omi watchOS companion app has been **disabled by default** to allow developers to build and run the iOS app without requiring watchOS code signing configuration.

## watchOS Source Files

The watchOS source code is preserved in `app/ios/omiWatchApp/` directory for developers who want to enable it.

## How to Enable watchOS Support

If you want to build the watchOS companion app, you'll need to:

### 1. Add the watchOS Target Back to Xcode

1. Open `app/ios/Runner.xcworkspace` in Xcode
2. Go to **File > New > Target**
3. Select **watchOS > App** and click Next
4. Name it `omiWatchApp`
5. Set the bundle identifier to match your app (e.g., `$(PRODUCT_BUNDLE_IDENTIFIER).watchapp`)
6. Ensure "Watch App for Existing iOS App" is selected

### 2. Configure Code Signing

1. Select the `omiWatchApp` target in Xcode
2. Go to **Signing & Capabilities**
3. Select your development team
4. Ensure automatic signing is enabled

### 3. Link Existing Source Files

1. Delete the auto-generated Swift files in the new target
2. Add the existing files from `omiWatchApp/` directory:
   - `omiwatchApp.swift`
   - `ContentView.swift`
   - `BatteryManager.swift`
   - `WatchAudioRecorderViewModel.swift`
   - `Assets.xcassets`

### 4. Update Info.plist

Add the following to `app/ios/Runner/Info.plist`:

```xml
<key>WKCompanionAppBundleIdentifier</key>
<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
```

### 5. Add Target Dependency

1. Select the `Runner` target
2. Go to **Build Phases > Dependencies**
3. Add `omiWatchApp` as a dependency
4. Add an "Embed Watch Content" build phase if not present

## Why Is watchOS Disabled?

1. **Signing Requirements**: watchOS apps require a valid development team and signing certificate, which blocks new developers from building the iOS app
2. **Optional Feature**: The watchOS companion is optional and not required for core Omi functionality
3. **Faster Development**: Most developers only need the iOS app for development and testing

## Questions?

If you need help enabling watchOS support, please open an issue on GitHub.
