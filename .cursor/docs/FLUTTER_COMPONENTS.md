# Flutter App Components Reference

Quick reference guide to the Flutter app structure and components.

## App Structure

**Location**: `app/`

**Platforms**: iOS, Android, macOS, Windows

**State Management**: Provider pattern

**Localization**: All user-facing strings use `context.l10n.keyName` (ARB files in `lib/l10n/`)

## Core Directories

### `lib/backend/`

Backend integration layer.

#### `lib/backend/http/`
HTTP client for REST API communication.

**Key Files**:
- `shared.dart` - Shared HTTP utilities
- `http_pool_manager.dart` - HTTP connection pooling
- `openai.dart` - OpenAI API client
- `webhooks.dart` - Webhook handling

#### `lib/backend/http/api/`
API endpoint clients.

**Modules**:
- `conversations.dart` - Conversation API
- `memories.dart` - Memory API
- `messages.dart` - Chat API
- `action_items.dart` - Action items API
- `apps.dart` - App management API
- `dev_api.dart` - Developer API
- `mcp_api.dart` - MCP API
- `users.dart` - User API
- `notifications.dart` - Notifications API
- `speech_profile.dart` - Speech profile API
- `integrations.dart` - Integrations API
- `calendar_meetings.dart` - Calendar API
- `folders.dart` - Folder API
- `goals.dart` - Goals API
- `wrapped.dart` - Wrapped API
- `payment.dart` / `payments.dart` - Payment API
- `imports.dart` - Import API
- `knowledge_graph_api.dart` - Knowledge graph API
- `task_integrations.dart` - Task integration API
- `announcements.dart` - Announcements API
- `device.dart` - Device API
- `privacy.dart` - Privacy API
- `audio.dart` - Audio API

#### `lib/backend/http/webhooks/`
WebSocket client for real-time audio streaming.

**Key Features**:
- WebSocket connection to `/v4/listen`
- Audio streaming
- Real-time transcript reception
- Connection management

#### `lib/backend/schema/`
Data models matching backend schemas.

**Key Models**:
- `conversation.dart` - Conversation model
- `memory.dart` - Memory model
- `message.dart` - Chat message model
- `action_item.dart` - Action item model
- `app.dart` - App model
- `structured.dart` - Structured conversation data
- `transcript_segment.dart` - Transcript segment
- `geolocation.dart` - Location data
- `person.dart` - Person model
- `folder.dart` - Folder model
- `bt_device/bt_device.dart` - Bluetooth device model

### `lib/services/`

Business logic services.

**Key Services**:
- Audio recording and playback
- Bluetooth Low Energy (BLE) device communication
- WebSocket management
- Local storage
- File management
- Analytics
- Notifications
- Authentication
- Sync services

### `lib/providers/`

State management using Provider pattern.

**Key Providers**:
- `auth_provider.dart` - Authentication state
- `conversation_provider.dart` - Conversation list and management
- `message_provider.dart` - Chat messages
- `memories_provider.dart` - Memories
- `action_items_provider.dart` - Action items
- `device_provider.dart` - BLE device connection
- `capture_provider.dart` - Audio capture state
- `voice_recorder_provider.dart` - Voice recording
- `app_provider.dart` - App management
- `integration_provider.dart` - External integrations
- `user_provider.dart` - User data
- `home_provider.dart` - Home screen state
- `folder_provider.dart` - Conversation folders
- `people_provider.dart` - People/contacts
- `speech_profile_provider.dart` - Speech profiles
- `calendar_provider.dart` - Calendar integration
- `developer_mode_provider.dart` - Developer features
- `locale_provider.dart` - Language/locale
- `onboarding_provider.dart` - Onboarding flow
- `sync_provider.dart` - Data synchronization
- `usage_provider.dart` - Usage statistics
- `mcp_provider.dart` - MCP integration
- `task_integration_provider.dart` - Task integrations
- `announcement_provider.dart` - Announcements
- `connectivity_provider.dart` - Network connectivity

### `lib/pages/`

UI screens and pages.

**Key Sections**:
- `conversations/` - Conversation list and detail
- `chat/` - Chat interface
- `memories/` - Memories list and detail
- `action_items/` - Action items/tasks
- `apps/` - App store and management
- `settings/` - Settings screens
- `onboarding/` - Onboarding flow
- `payments/` - Payment and subscription
- `persona/` - Persona chat
- `developer/` - Developer features
- `integrations/` - External integrations
- `folders/` - Conversation folders
- `goals/` - User goals

### `lib/widgets/`

Reusable UI components.

**Key Widgets**:
- `conversation_audio_player_widget.dart` - Audio player
- `transcript.dart` - Transcript display
- `waveform_painter.dart` / `waveform_section.dart` - Audio waveform
- `device_widget.dart` - Device connection UI
- `person_chip.dart` - Person tag
- `photos_grid.dart` - Photo grid
- `photo_viewer_page.dart` - Photo viewer
- `dialog.dart` - Custom dialogs
- `confirmation_dialog.dart` - Confirmation dialogs
- `gradient_button.dart` - Styled buttons
- `language_picker.dart` - Language selection
- `freemium_paywall_page.dart` - Paywall
- `upgrade_alert.dart` - Upgrade prompts
- `calendar_date_picker_sheet.dart` - Date picker
- `collapsible_section.dart` - Collapsible UI
- `expandable_text.dart` - Expandable text
- `custom_refresh_indicator.dart` - Pull to refresh
- `conversation_bottom_bar.dart` - Bottom bar
- `apple_watch_setup_bottom_sheet.dart` - Apple Watch setup
- `consent_bottom_sheet.dart` - Consent dialogs
- `text_selection_controls.dart` - Text selection
- `animated_loading_button.dart` - Loading button
- `base/base_adaptive_widget.dart` - Adaptive widgets

### `lib/utils/`

Utility functions and helpers.

**Key Utilities**:
- `bluetooth/` - BLE device communication
- `audio/` - Audio processing
- `analytics/` - Analytics tracking
- `auth/` - Authentication helpers
- `image/` - Image processing
- `platform/` - Platform-specific code
- `alerts/` - Alert dialogs
- `debugging/` - Debug utilities
- `folders/` - Folder utilities
- `manifest/` - App manifest
- `other/` - Miscellaneous utilities
- `responsive/` - Responsive design
- `ui_guidelines.dart` - UI guidelines
- `wal_file_manager.dart` - WAL file management
- `waveform_utils.dart` - Waveform utilities

### `lib/ui/`

UI components and styling.

**Key Components**:
- Theme configuration
- Color schemes
- Typography
- Spacing and layout
- Platform-specific UI

### `lib/desktop/`

Desktop-specific UI (macOS, Windows).

**Key Features**:
- Desktop home page
- Desktop-specific navigation
- Desktop onboarding
- Desktop settings
- Desktop shortcuts

### `lib/mobile/`

Mobile-specific UI (iOS, Android).

**Key Features**:
- Mobile app structure
- Mobile navigation
- Mobile-specific features

### `lib/core/`

Core app structure.

**Key Files**:
- `app_shell.dart` - Main app shell/wrapper

### `lib/models/`

App-specific data models.

**Key Models**:
- `announcement.dart` - Announcement model
- `custom_stt_config.dart` - STT configuration
- `playback_state.dart` - Audio playback state
- `stt_provider.dart` - STT provider model
- `stt_response_schema.dart` - STT response
- `stt_result.dart` - STT result
- `subscription.dart` - Subscription model
- `sync_state.dart` - Sync state
- `user_usage.dart` - Usage statistics

### `lib/l10n/`

Localization files.

**Structure**:
- ARB files (`.arb`) - Translation source files
- Generated Dart files (`.dart`) - Localization classes

**Usage**: Always use `context.l10n.keyName` for user-facing strings

**Regeneration**: After modifying ARB files, run `cd app && flutter gen-l10n`

## BLE Device Communication

### Device Connection

**Location**: `lib/utils/bluetooth/` and `lib/services/`

**Key Features**:
- BLE device discovery
- Connection management
- Audio streaming
- Codec negotiation (Opus, PCM, Mu-law)
- Battery level monitoring
- Device info service

**Protocol**: See `docs/doc/developer/Protocol.mdx`

### Audio Streaming

**Flow**:
1. Discover device by name "Omi"
2. Connect to BLE services
3. Negotiate codec (Opus preferred)
4. Stream audio data via BLE notifications
5. Decode audio packets (3-byte header + payload)
6. Forward to backend via WebSocket

## Platform-Specific Code

### iOS
- Location: `ios/`
- CocoaPods for dependencies
- Firebase configuration in `ios/Config/`
- WatchOS support

### Android
- Location: `android/`
- Gradle build system
- Firebase configuration in `android/app/src/`
- NDK required for Opus

### macOS
- Location: `macos/`
- CocoaPods for dependencies
- Firebase configuration in `macos/Config/`

### Windows
- Location: `windows/`
- CMake build system
- Native Windows audio capture

## Build Configuration

### Flavors
- **dev**: Development backend
- **prod**: Production backend

### Environment Files
- `.env.template` - Template
- `.dev.env` - Development environment
- Production environment configured via Firebase

### Setup Scripts
- `setup.sh` - Automated setup (macOS/Linux)
- `setup/scripts/setup.ps1` - Windows setup

## Testing

**Location**: `test/`

**Test Command**: `cd app && ./test.sh`

## Related Documentation

- App Setup: `docs/doc/developer/AppSetup.mdx`
- Protocol: `docs/doc/developer/Protocol.mdx`
- Architecture: `.cursor/ARCHITECTURE.md`
