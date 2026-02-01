# Flutter App Structure Index

Quick reference guide to the Flutter app structure.

## Core Directories

### Backend Integration (`lib/backend/`)

- `http/api/` - REST API clients
- `http/webhooks.dart` - WebSocket client
- `schema/` - Data models

### Services (`lib/services/`)

Business logic services for:
- Audio recording and playback
- BLE device communication
- WebSocket management
- Local storage
- Analytics
- Notifications

### Providers (`lib/providers/`)

State management using Provider pattern:
- `conversation_provider.dart` - Conversations
- `memory_provider.dart` - Memories
- `message_provider.dart` - Chat messages
- `device_provider.dart` - BLE device
- `auth_provider.dart` - Authentication

### Pages (`lib/pages/`)

UI screens:
- `conversations/` - Conversation list and detail
- `chat/` - Chat interface
- `memories/` - Memories list
- `action_items/` - Tasks
- `apps/` - App store
- `settings/` - Settings

### Widgets (`lib/widgets/`)

Reusable UI components:
- `conversation_audio_player_widget.dart` - Audio player
- `transcript.dart` - Transcript display
- `device_widget.dart` - Device connection UI

### Utils (`lib/utils/`)

Utility functions:
- `bluetooth/` - BLE communication
- `audio/` - Audio processing
- `analytics/` - Analytics
- `platform/` - Platform-specific code

### Localization (`lib/l10n/`)

- ARB files (`.arb`) - Translation source
- Generated Dart files - Localization classes

## Platform-Specific

- `ios/` - iOS configuration
- `android/` - Android configuration
- `macos/` - macOS configuration
- `windows/` - Windows configuration

## Related Documentation

- Flutter Components: `.cursor/FLUTTER_COMPONENTS.md`
- Flutter Architecture: `.cursor/rules/flutter-architecture.mdc`
- App Setup: `docs/doc/developer/AppSetup.mdx`
