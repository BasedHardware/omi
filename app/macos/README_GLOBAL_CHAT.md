# Omi macOS Global Chat Integration

This feature adds a native macOS global hotkey overlay that provides quick access to Omi's chat functionality without switching to the main Flutter app.

## Features

- **Global Hotkey**: Press `Option + Space` from anywhere in macOS to open the chat overlay
- **Floating Window**: Non-intrusive overlay that stays on top of other applications
- **Chat Interface**: Text input with send functionality
- **Voice Recording**: Microphone button for voice input (planned)
- **Auto-expanding**: Window grows to show conversation history
- **Cross-space**: Works across all macOS spaces/desktops

## Setup Instructions

### 1. Install Dependencies

The HotKey dependency is added to the Podfile. To install:

```bash
cd app/macos
pod install
```

### 2. Build and Run

Build the macOS app as usual through Xcode or Flutter:

```bash
flutter build macos
# or
flutter run -d macos
```

### 3. Grant Accessibility Permissions

For global hotkeys to work, the app needs accessibility permissions:

1. Open **System Preferences** → **Security & Privacy** → **Privacy**
2. Select **Accessibility** from the left sidebar
3. Click the lock to make changes
4. Add the Omi app to the list of allowed applications

## Usage

1. **Open Chat**: Press `Option + Space` anywhere in macOS
2. **Type Message**: Type your message and press Enter to send
3. **Voice Input**: Click the microphone icon (implementation pending)
4. **Close Chat**: Press `Option + Space` again or click outside the window

## Architecture

### Files Added

- `HotKeyManager.swift`: Manages global hotkeys and window lifecycle
- `ChatView.swift`: SwiftUI interface for the chat overlay
- `OmiConfig.swift`: Configuration and API endpoint management

### Integration Points

The native chat integrates with Omi's existing infrastructure:

- **API Endpoints**: Uses same chat endpoints as Flutter app
- **Authentication**: Shares user tokens with main app via UserDefaults
- **Device Integration**: Will connect to same Omi device ecosystem

## Current Status

### ✅ Implemented
- Global hotkey (Option + Space)
- Floating window with SwiftUI interface
- Basic chat UI with message history
- Text input and send functionality
- Window management (show/hide/resize)

### 🚧 Next Steps
1. **API Integration**: Connect to actual Omi chat endpoints
2. **Voice Recording**: Implement audio capture and processing
3. **Authentication Sync**: Share auth state with Flutter app
4. **Message Persistence**: Save chat history locally
5. **Enhanced UI**: Better styling and animations
6. **Settings**: Customizable hotkeys and appearance

## Configuration

### API Endpoints
Update `OmiConfig.swift` to point to the correct Omi API endpoints:

```swift
static let baseURL = "https://api.omi.me" // Update with actual URL
```

### Hotkey Customization
Modify the hotkey in `HotKeyManager.swift`:

```swift
hotKey = HotKey(key: .space, modifiers: [.option]) // Change as needed
```

## Development

### Testing
- Use SwiftUI previews for UI development
- Test hotkey functionality requires running on actual macOS
- Console logging available for debugging

### Integration with Flutter
The native overlay is designed to complement, not replace, the main Flutter app:

- Shares authentication and user data
- Uses same API endpoints
- Provides quick access without app switching
- Falls back to main app for complex interactions

## Troubleshooting

### Hotkey Not Working
1. Check accessibility permissions
2. Verify no other app is using the same hotkey
3. Check console for error messages

### Window Not Appearing
1. Ensure the app is running
2. Check if window is hidden behind other apps
3. Try different hotkey combinations

### API Integration Issues
1. Verify API endpoints in `OmiConfig.swift`
2. Check authentication tokens
3. Review network connectivity

## Contributing

When extending this feature:

1. Keep UI lightweight and fast
2. Maintain consistency with main app
3. Follow SwiftUI best practices
4. Test across different macOS versions
5. Consider accessibility requirements
