import 'package:omi/backend/preferences.dart';

enum ButtonAction { askQuestion, endConversation, toggleMute, starConversation, none }

const int maxButtonTapCount = 3;

ButtonAction resolveSingleTapAction(int code) {
  switch (code) {
    case 1:
      return ButtonAction.endConversation;
    case 2:
      return ButtonAction.toggleMute;
    case 3:
      return ButtonAction.starConversation;
    default:
      return ButtonAction.askQuestion;
  }
}

ButtonAction resolveDoubleTapAction(int code) {
  switch (code) {
    case 1:
      return ButtonAction.toggleMute;
    case 2:
      return ButtonAction.starConversation;
    case 3:
      return ButtonAction.none;
    default:
      return ButtonAction.endConversation;
  }
}

ButtonAction resolveTripleTapAction(int code) => resolveDoubleTapAction(code);

ButtonAction resolveSingleTapActionForSession(int code, {required bool onboardingAskQuestionStep}) {
  if (onboardingAskQuestionStep) return ButtonAction.askQuestion;
  return resolveSingleTapAction(code);
}

class ButtonTapDispatcher {
  ButtonTapDispatcher(this._actionForCount);

  final ButtonAction Function(int count) _actionForCount;
  bool _dispatched = false;
  bool _sawTaps = false;

  ButtonAction? onTap(int count) {
    if (count <= 1) _dispatched = false;
    _sawTaps = true;
    if (_dispatched || _waitsForMoreTaps(count)) return null;
    _dispatched = true;
    return _mapped(count);
  }

  ButtonAction? onSequenceEnd(int count) {
    final handled = _dispatched || !_sawTaps;
    _dispatched = false;
    _sawTaps = false;
    return handled ? null : _mapped(count);
  }

  bool _waitsForMoreTaps(int count) {
    for (var next = count + 1; next <= maxButtonTapCount; next++) {
      if (_actionForCount(next) != ButtonAction.none) return true;
    }
    return false;
  }

  ButtonAction? _mapped(int count) {
    if (count < 1 || count > maxButtonTapCount) return null;
    final action = _actionForCount(count);
    return action == ButtonAction.none ? null : action;
  }
}

/// What a single and a triple tap do, stored beside doubleTapAction.
extension ButtonTapPreferences on SharedPreferencesUtil {
  int get singleTapAction => getInt('singleTapAction');

  set singleTapAction(int value) => saveInt('singleTapAction', value);

  int get tripleTapAction => getInt('tripleTapAction');

  set tripleTapAction(int value) => saveInt('tripleTapAction', value);
}
