import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/sign_out.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Customizable button action preferences', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('defaults preserve current behavior', () {
      final prefs = SharedPreferencesUtil();
      expect(prefs.singlePressAction, equals(3)); // Ask Question (today's single tap)
      expect(prefs.doublePressAction, equals(0)); // End & Process (today's double tap default)
      expect(prefs.triplePressAction, equals(4)); // None until the user opts in
      expect(prefs.doubleTapAction, equals(0));
      expect(prefs.doubleTapPausesMuting, isFalse);
    });

    test('custom mappings persist', () {
      final prefs = SharedPreferencesUtil();
      prefs.singlePressAction = 1;
      prefs.doublePressAction = 2;
      prefs.triplePressAction = 3;
      expect(prefs.singlePressAction, equals(1));
      expect(prefs.doublePressAction, equals(2));
      expect(prefs.doubleTapAction, equals(2));
      expect(prefs.triplePressAction, equals(3));
      prefs.singlePressAction = 4;
      expect(prefs.singlePressAction, equals(4));
    });

    test('out-of-range values fall back to defaults', () {
      final prefs = SharedPreferencesUtil();
      prefs.singlePressAction = 99;
      expect(prefs.singlePressAction, equals(3));
      prefs.doublePressAction = 10;
      expect(prefs.doublePressAction, equals(0));
      prefs.triplePressAction = -5;
      expect(prefs.triplePressAction, equals(4));
    });

    test('corrupted stored values fall back to defaults', () async {
      SharedPreferences.setMockInitialValues({
        'singlePressAction': 999,
        'doublePressAction': -10,
        'triplePressAction': 42,
      });
      await SharedPreferencesUtil.init();
      final prefs = SharedPreferencesUtil();
      expect(prefs.singlePressAction, equals(3));
      expect(prefs.doublePressAction, equals(0));
      expect(prefs.triplePressAction, equals(4));
    });

    test('legacy doubleTapAction is honored', () async {
      SharedPreferences.setMockInitialValues({'doubleTapAction': 1});
      await SharedPreferencesUtil.init();
      final prefs = SharedPreferencesUtil();
      expect(prefs.doublePressAction, equals(1));
      expect(prefs.doubleTapPausesMuting, isTrue);
    });

    test('button mappings survive sign-out', () {
      expect(kPreferencesKeptOnSignOut, containsAll(['singlePressAction', 'doubleTapAction', 'triplePressAction']));
    });
  });
}
