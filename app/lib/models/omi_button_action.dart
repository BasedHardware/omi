/// Raw values the firmware notifies on the button characteristic
/// (`23BA7925-0000-1000-7450-346EAC492E92`). Mirrors
/// `omi/firmware/common/button_gesture.h`.
abstract final class OmiButtonState {
  static const int singleTap = 1;
  static const int doubleTap = 2;

  /// Emitted only by firmware older than the fixed power-off long press.
  static const int longPress = 3;

  /// Emitted only by legacy firmware.
  static const int press = 4;
  static const int release = 5;
  static const int tripleTap = 6;
}

/// What the app does when a remappable button gesture arrives.
///
/// [storedValue] is the on-disk encoding. `0..2` predate this enum
/// (`doubleTapAction` has always stored them), so they must never be renumbered.
enum OmiButtonAction {
  endConversation(storedValue: 0, analyticsName: 'process_conversation'),
  muteUnmute(storedValue: 1, analyticsName: 'mute_unmute'),
  starConversation(storedValue: 2, analyticsName: 'star_conversation'),
  askQuestion(storedValue: 3, analyticsName: 'ask_question'),
  none(storedValue: 4, analyticsName: 'none');

  const OmiButtonAction({required this.storedValue, required this.analyticsName});

  final int storedValue;
  final String analyticsName;

  /// Returns `null` for values this build does not know (a newer app may have
  /// stored one), so callers can fall back to the gesture default.
  static OmiButtonAction? fromStoredValue(int? value) {
    for (final action in values) {
      if (action.storedValue == value) return action;
    }
    return null;
  }
}

/// Button gestures the user may remap. The long press is deliberately absent:
/// it powers the device on/off in firmware and never reaches the app.
enum OmiButtonGesture {
  singleTap(
    buttonState: OmiButtonState.singleTap,
    prefsKey: 'singleTapAction',
    defaultAction: OmiButtonAction.askQuestion,
    analyticsName: 'single_tap',
  ),
  doubleTap(
    buttonState: OmiButtonState.doubleTap,
    prefsKey: 'doubleTapAction',
    defaultAction: OmiButtonAction.muteUnmute,
    analyticsName: 'double_tap',
  ),
  tripleTap(
    buttonState: OmiButtonState.tripleTap,
    prefsKey: 'tripleTapAction',
    defaultAction: OmiButtonAction.endConversation,
    analyticsName: 'triple_tap',
  );

  const OmiButtonGesture({
    required this.buttonState,
    required this.prefsKey,
    required this.defaultAction,
    required this.analyticsName,
  });

  final int buttonState;
  final String prefsKey;
  final OmiButtonAction defaultAction;
  final String analyticsName;

  /// Maps a raw button characteristic value to a remappable gesture, or `null`
  /// for press/release/legacy values that are not user-configurable.
  static OmiButtonGesture? fromButtonState(int state) {
    for (final gesture in values) {
      if (gesture.buttonState == state) return gesture;
    }
    return null;
  }
}
