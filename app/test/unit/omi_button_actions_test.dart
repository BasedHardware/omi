import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('Omi button actions are enabled by default', () {
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isTrue);
  });

  test('Omi button actions setting persists changes', () {
    SharedPreferencesUtil().omiButtonActionsEnabled = false;
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isFalse);

    SharedPreferencesUtil().omiButtonActionsEnabled = true;
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isTrue);
  });

  test('Button action gestures have expected defaults', () {
    final prefs = SharedPreferencesUtil();
    expect(prefs.singleTapAction, equals(3)); // Ask Question
    expect(prefs.doubleTapAction, equals(1)); // Mute / Unmute
    expect(prefs.tripleTapAction, equals(0)); // End & Process
    expect(prefs.doubleTapPausesMuting, isTrue);
  });

  test('Button action gestures persist changes', () {
    final prefs = SharedPreferencesUtil();
    prefs.singleTapAction = 1;
    expect(prefs.singleTapAction, equals(1));

    prefs.doubleTapAction = 2;
    expect(prefs.doubleTapAction, equals(2));
    expect(prefs.doubleTapPausesMuting, isFalse);

    prefs.tripleTapAction = 3;
    expect(prefs.tripleTapAction, equals(3));
  });
}
