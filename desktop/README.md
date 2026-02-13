# OMI Desktop (Swift)

A macOS menu bar app for focus monitoring and distraction detection. This is a Swift/SwiftUI rewrite of the original Python app.

## Features

- **Menu bar app** - Runs in the menu bar, no dock icon
- **Screen capture** - Captures active window every second
- **App switch detection** - Instant detection when switching apps
- **Gemini AI analysis** - Uses Gemini 2.0 Flash to analyze focus state
- **Native notifications** - macOS notifications for distraction alerts
- **Notification cooldown** - 3-second cooldown to prevent spam

## Requirements

- macOS 13.0 (Ventura) or later
- Xcode 15+ or Swift 5.9+ (for building)
- Gemini API key

## Setup

1. Create a `.env` file in the project root with your API key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

2. Grant Screen Recording permission when prompted (System Settings > Privacy & Security > Screen Recording)

## Building

### Using the build script (recommended)

```bash
./build.sh
```

This creates `build/OMI.app` which you can run directly or copy to Applications.

### Using Swift Package Manager

```bash
# Debug build
swift build

# Release build
swift build -c release
```

### Using Xcode

Open the package in Xcode:
```bash
open Package.swift
```

Then build and run from Xcode (⌘R).

## Running

```bash
# Run the built app
open build/OMI.app

# Or install to Applications
cp -r build/OMI.app /Applications/
```

## Project Structure

```
omi-computer-swift/
├── Package.swift              # Swift package manifest
├── build.sh                   # Build script for .app bundle
├── Omi/
│   ├── Info.plist            # App metadata and permissions
│   ├── Omi.entitlements      # App entitlements
│   └── Sources/
│       ├── OmiApp.swift              # Main app entry, MenuBarExtra
│       ├── AppState.swift            # Shared state management
│       ├── ScreenCaptureService.swift # Window capture with CGWindowList
│       ├── WindowMonitor.swift        # App switch observer
│       ├── GeminiService.swift        # Gemini API client
│       ├── NotificationService.swift  # Native notifications
│       └── Logger.swift               # Logging utility
```

## Comparison with Python Version

| Aspect | Python | Swift |
|--------|--------|-------|
| App size | ~50MB+ | ~450KB |
| Startup time | Slower | Instant |
| Dependencies | Many | None (native) |
| UI Framework | rumps | SwiftUI MenuBarExtra |
| Screen capture | PyObjC/Quartz | CGWindowListCreateImage |
| Notifications | rumps | UserNotifications |
| Async | asyncio + threading | Swift Concurrency |

## License

MIT
