import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/button_action.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('single tap', () {
    test('an unset preference keeps the current ask-a-question behaviour', () {
      expect(SharedPreferencesUtil().singleTapAction, 0);
      expect(resolveSingleTapAction(SharedPreferencesUtil().singleTapAction), ButtonAction.askQuestion);
    });

    test('maps each stored code to its action', () {
      expect(resolveSingleTapAction(0), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(1), ButtonAction.endConversation);
      expect(resolveSingleTapAction(2), ButtonAction.toggleMute);
      expect(resolveSingleTapAction(3), ButtonAction.starConversation);
    });

    test('falls back to ask a question for an unknown code', () {
      expect(resolveSingleTapAction(99), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(-1), ButtonAction.askQuestion);
    });

    test('round trips through the preference', () async {
      SharedPreferencesUtil().singleTapAction = 2;

      expect(resolveSingleTapAction(SharedPreferencesUtil().singleTapAction), ButtonAction.toggleMute);
    });
  });

  group('double tap', () {
    test('keeps the existing stored encoding', () {
      expect(resolveDoubleTapAction(0), ButtonAction.endConversation);
      expect(resolveDoubleTapAction(1), ButtonAction.toggleMute);
      expect(resolveDoubleTapAction(2), ButtonAction.starConversation);
    });

    test('an unset preference still ends the conversation', () {
      expect(SharedPreferencesUtil().doubleTapAction, 0);
      expect(resolveDoubleTapAction(SharedPreferencesUtil().doubleTapAction), ButtonAction.endConversation);
    });

    test('falls back to ending the conversation for an unknown code', () {
      expect(resolveDoubleTapAction(42), ButtonAction.endConversation);
    });
  });
}
