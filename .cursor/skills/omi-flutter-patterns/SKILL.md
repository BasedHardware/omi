---
name: omi-flutter-patterns
description: "Flutter Dart BLE device communication state management Provider backend integration localization cross-platform iOS Android"
---

# Omi Flutter Patterns Skill

This skill provides guidance for working with the Omi Flutter app, including BLE device communication, state management, backend integration, and localization.

## When to Use

Use this skill when:
- Working on Flutter/Dart code in `app/`
- Implementing BLE device communication
- Working with state management (Provider)
- Integrating with backend APIs
- Adding new UI screens or widgets

## Key Patterns

### State Management

The app uses **Provider pattern** for state management:

```dart
// Define provider
class ConversationProvider extends ChangeNotifier {
  List<Conversation> _conversations = [];
  
  List<Conversation> get conversations => _conversations;
  
  Future<void> loadConversations() async {
    _conversations = await api.getConversations();
    notifyListeners();
  }
}

// Use in widget
final provider = Provider.of<ConversationProvider>(context);
```

### Localization

**CRITICAL**: All user-facing strings must use localization:

```dart
// ✅ GOOD
Text(context.l10n.helloWorld)

// ❌ BAD
Text('Hello World')
```

**Adding keys**: Use `jq` to add keys to ARB files, then run `cd app && flutter gen-l10n`

### Backend Integration

#### REST API

```dart
// lib/backend/http/api/conversations.dart
class ConversationsAPI {
  Future<List<Conversation>> getConversations() async {
    final response = await httpClient.get('/v1/conversations');
    return (response.data['items'] as List)
        .map((json) => Conversation.fromJson(json))
        .toList();
  }
}
```

#### WebSocket

```dart
// lib/backend/http/webhooks.dart
class WebSocketClient {
  Future<void> connect(String uid) async {
    _socket = await WebSocket.connect('$baseUrl/v4/listen?uid=$uid');
    _socket!.listen((data) {
      // Handle transcript
    });
  }
}
```

### BLE Device Communication

#### Device Connection

```dart
// Scan for devices
final devices = await scanForOmiDevices();  // Name: "Omi"

// Connect
await device.connect();

// Discover services
final services = await device.discoverServices();

// Audio service UUID: 19B10000-E8F2-537E-4F6C-D104768A1214
// Audio data UUID: 19B10001-E8F2-537E-4F6C-D104768A1214
// Codec type UUID: 19B10002-E8F2-537E-4F6C-D104768A1214
```

#### Audio Packet Format

- **Header**: 3 bytes (packet number + index)
- **Payload**: 160 audio samples
- **Codec**: Opus (preferred), PCM, Mu-law
- **Byte order**: Little-endian

### Platform Support

The app supports:
- **iOS**: CocoaPods, Firebase config in `ios/Config/`
- **Android**: Gradle, Firebase config in `android/app/src/`
- **macOS**: CocoaPods, Firebase config in `macos/Config/`
- **Windows**: CMake, native Windows audio

Use `PlatformManager` for platform detection.

## Common Tasks

### Adding a New Screen

1. Create page in `lib/pages/`
2. Add route in navigation
3. Use Provider for state
4. Use localization for all strings
5. Test on all platforms

### Adding a New API Endpoint

1. Add method to appropriate API class in `lib/backend/http/api/`
2. Use HttpClient for requests
3. Handle errors gracefully
4. Update data models if needed

### Adding BLE Functionality

1. Use `flutter_blue_plus` package
2. Follow BLE protocol (see Protocol docs)
3. Handle packet fragmentation
4. Support all codec types

## Related Documentation

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **App Setup**: `docs/doc/developer/AppSetup.mdx` - [View online](https://docs.omi.me/doc/developer/AppSetup)
- **BLE Protocol**: `docs/doc/developer/Protocol.mdx` - [View online](https://docs.omi.me/doc/developer/Protocol)
- **Flutter Architecture**: `.cursor/rules/flutter-architecture.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/flutter-architecture.mdc` - App structure and state management
- `.cursor/rules/flutter-backend-integration.mdc` - Backend API integration
- `.cursor/rules/flutter-ble-protocol.mdc` - BLE device communication
- `.cursor/rules/flutter-localization.mdc` - Localization requirements
- `.cursor/rules/flutter-platform-specific.mdc` - Platform-specific code

### Subagents
- `.cursor/agents/flutter-developer/` - Uses this skill for Flutter development

### Commands
- `/flutter-setup` - Uses this skill for setup guidance
- `/flutter-test` - Uses this skill for testing patterns
- `/flutter-build` - Uses this skill for build patterns
