import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/sign_out.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'btDevice': '{"id":"AA:BB"}',
      'deviceName': 'Omi',
      'doubleTapAction': 2,
      'showShortConversations': true,
      'uid': 'user-123',
      'givenName': 'Ada',
      'onboardingCompleted': true,
    });
    await SharedPreferencesUtil.init();
  });

  test('sign out keeps the paired device and display preferences', () async {
    await clearPreferencesForSignOut();
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('btDevice'), '{"id":"AA:BB"}');
    expect(prefs.getString('deviceName'), 'Omi');
    expect(prefs.getInt('doubleTapAction'), 2);
    expect(prefs.getBool('showShortConversations'), isTrue);
  });

  test('sign out clears account-scoped values', () async {
    await clearPreferencesForSignOut();
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uid'), isNull);
    expect(prefs.getString('givenName'), isNull);
    expect(prefs.getBool('onboardingCompleted'), isNull);
  });

  for (final mode in ['light', 'dark', 'system']) {
    test('sign out preserves explicit $mode appearance across restart', () async {
      await SharedPreferencesUtil().setAppearanceMode(mode);
      await clearPreferencesForSignOut();
      final prefs = await SharedPreferences.getInstance();
      await prefs.reload();
      expect(prefs.getString(SharedPreferencesUtil.appearanceModeKey), mode);
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().appearanceMode, mode);
    });
  }

  test('the keep-list holds no credentials', () {
    for (final key in kPreferencesKeptOnSignOut) {
      expect(key.toLowerCase(), isNot(contains('token')));
      expect(key.toLowerCase(), isNot(contains('password')));
      expect(key, isNot('uid'));
    }
  });
}
