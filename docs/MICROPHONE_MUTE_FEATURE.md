# Microphone Mute Feature

## Overview

The microphone mute feature allows users to temporarily stop audio recording and transcription in the OMI app. This feature provides both immediate mute/unmute functionality and optional timed mute duration.

## Features

### Phase One (Implemented)
- **Toggle Button**: Simple tap to mute/unmute the microphone
- **Visual Feedback**: Clear visual indication of mute state with red coloring and icon changes
- **Persistent State**: Mute state is saved and restored across app sessions
- **Analytics Tracking**: All mute actions are tracked for analytics

### Phase Two (Optional Enhancement)
- **Timed Mute**: Long press to access timer options (30 minutes, 1 hour, 2 hours)
- **Timer Indicator**: Visual indicator when timer mute is active
- **Auto-unmute**: Automatic unmute when timer expires

## Implementation Details

### Architecture

The mute feature is implemented using the Provider pattern with the following components:

1. **MuteProvider** (`app/lib/providers/mute_provider.dart`)
   - Manages mute state (manual and timer-based)
   - Handles persistence via SharedPreferences
   - Provides analytics tracking
   - Manages timer functionality

2. **MuteToggleWidget** (`app/lib/widgets/mute_toggle_widget.dart`)
   - Beautiful UI component with animations
   - Supports both tap and long-press interactions
   - Shows visual feedback for mute state
   - Optional timer selection modal

3. **CaptureProvider Integration**
   - Modified to respect mute state
   - Prevents audio data from being sent to WebSocket when muted
   - Works with both device (Bluetooth) and phone microphone

### Key Files Modified

- `app/lib/providers/mute_provider.dart` - New mute state management
- `app/lib/widgets/mute_toggle_widget.dart` - New mute toggle UI component
- `app/lib/backend/preferences.dart` - Added microphoneMuted preference
- `app/lib/providers/capture_provider.dart` - Integrated mute functionality
- `app/lib/main.dart` - Added MuteProvider to provider tree
- `app/lib/pages/home/page.dart` - Added mute toggle to app bar

### Usage

#### Basic Mute/Unmute
```dart
// Access the mute provider
final muteProvider = context.read<MuteProvider>();

// Toggle mute state
muteProvider.toggleMute();

// Check mute state
bool isMuted = muteProvider.isMuted;
```

#### Timer Mute
```dart
// Mute for specific duration
muteProvider.muteForDuration(Duration(minutes: 30));

// Cancel timer mute
muteProvider.cancelTimerMute();

// Check time remaining
Duration? remaining = muteProvider.timeRemaining;
```

#### Widget Usage
```dart
// Basic mute toggle
MuteToggleWidget()

// With timer options enabled
MuteToggleWidget(
  showTimerOptions: true,
  iconSize: 24.0,
)
```

## User Interface

### Location
The mute toggle is located in the top app bar, positioned between the battery indicator and settings icon for easy access.

### Visual States
- **Unmuted**: White microphone icon
- **Muted**: Red microphone slash icon with red background and border
- **Timer Active**: Orange clock indicator overlay

### Interactions
- **Single Tap**: Toggle mute/unmute
- **Long Press**: Show timer options (when enabled)
- **Haptic Feedback**: Light impact on tap, medium impact on long press

## Technical Implementation

### State Management
```dart
class MuteProvider extends ChangeNotifier {
  bool _isMuted = false;
  bool _isTimerMuteActive = false;
  Timer? _muteTimer;
  DateTime? _muteStartTime;
  Duration? _muteDuration;
  
  // Combined mute state
  bool get isMuted => _isMuted || _isTimerMuteActive;
}
```

### Audio Integration
The mute functionality is integrated at the audio capture level:

```dart
// In CaptureProvider.streamAudioToWs()
final isMuted = muteProvider?.isMuted ?? false;
if (!isMuted) {
  _socket?.send(trimmedValue);
} else {
  debugPrint('Audio muted - not sending to WebSocket');
}
```

### Persistence
Mute state is persisted using SharedPreferences:

```dart
// In SharedPreferencesUtil
bool get microphoneMuted => getBool('microphoneMuted') ?? false;
set microphoneMuted(bool value) => saveBool('microphoneMuted', value);
```

## Testing

Comprehensive tests are provided in `app/test/mute_provider_test.dart` covering:

- Basic mute/unmute functionality
- State persistence
- Timer mute behavior
- Edge cases and error handling

### Running Tests
```bash
cd app
flutter test test/mute_provider_test.dart
```

## Analytics

The following events are tracked:

- `Microphone Mute Toggled` - When user manually toggles mute
- `Microphone Timed Mute Started` - When timer mute is activated
- `Microphone Timed Mute Cancelled` - When timer mute is cancelled
- `Microphone Timed Mute Expired` - When timer mute expires
- `Microphone Unmuted All` - When all mute states are cleared

## Future Enhancements

### Potential Improvements
1. **Custom Timer Durations**: Allow users to set custom mute durations
2. **Mute Scheduling**: Schedule mute periods for specific times
3. **Context-Aware Muting**: Automatic muting based on location or calendar events
4. **Voice Commands**: Voice-activated mute/unmute
5. **Notification Integration**: Show notifications when mute timer expires

### Performance Considerations
- Minimal impact on audio processing performance
- Timer operations are lightweight
- State changes trigger minimal UI updates
- Proper cleanup of timers on disposal

## Troubleshooting

### Common Issues
1. **Mute state not persisting**: Ensure SharedPreferences is properly initialized
2. **Timer not working**: Check that Timer is properly cancelled and recreated
3. **UI not updating**: Verify Provider is properly connected and notifyListeners() is called

### Debug Information
Enable debug prints to see mute state changes:
```dart
debugPrint('Microphone ${_isMuted ? "muted" : "unmuted"} manually');
```

## Contributing

When contributing to the mute feature:

1. Ensure all tests pass
2. Add tests for new functionality
3. Update analytics tracking for new events
4. Follow the existing code style and patterns
5. Update this documentation for any changes

## License

This feature is part of the OMI app and follows the same license terms. 