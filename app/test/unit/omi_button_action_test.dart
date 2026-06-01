import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/omi_button_action.dart';

void main() {
  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  group('Omi button actions', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('keeps stable stored values', () {
      expect(OmiButtonAction.endConversation.value, 0);
      expect(OmiButtonAction.pauseResume.value, 1);
      expect(OmiButtonAction.starConversation.value, 2);
      expect(OmiButtonAction.askQuestion.value, 3);
      expect(OmiButtonAction.noAction.value, 4);
    });

    test('defaults match expected button layout', () {
      final preferences = SharedPreferencesUtil();

      expect(preferences.singleTapAction, OmiButtonAction.askQuestion.value);
      expect(preferences.doubleTapAction, OmiButtonAction.pauseResume.value);
      expect(
          preferences.tripleTapAction, OmiButtonAction.endConversation.value);
    });

    test('maps BLE button states to configurable press types', () {
      expect(OmiButtonPress.fromState(1), OmiButtonPress.singleTap);
      expect(OmiButtonPress.fromState(2), OmiButtonPress.doubleTap);
      expect(OmiButtonPress.fromState(6), OmiButtonPress.tripleTap);
      expect(OmiButtonPress.fromState(3), isNull);
    });

    test('falls back when stored action value is unknown', () {
      expect(
        OmiButtonAction.fromValue(999, fallback: OmiButtonAction.pauseResume),
        OmiButtonAction.pauseResume,
      );
    });
  });
}
