import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/services/wals/deleted_account_uids.dart';

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

  test('sign out keeps the migrated installation reconnect cap and clears account enrollment', () async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('pendant_reconnect_nudge_last_shown_at:user-123', 100);
    await prefs.setInt('pendant_reconnect_nudge_last_shown_at:another-user', 200);
    await SharedPreferencesUtil.init();
    final preferences = SharedPreferencesUtil();
    preferences.pendantReconnectNudgeLastEnrolledAt = 123;
    expect(preferences.pendantReconnectNudgeLastShownAt, 200);

    await clearPreferencesForSignOut();
    preferences.uid = 'another-user';
    expect(preferences.pendantReconnectNudgeLastShownAt, 200);
    expect(preferences.pendantReconnectNudgeLastEnrolledAt, 0);
    expect(prefs.getInt('pendant_reconnect_nudge_last_enrolled_at:user-123'), isNull);
    expect(prefs.getInt('pendant_reconnect_nudge_last_shown_at:another-user'), isNull);
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

  test('deleted-account uids loaded untyped from disk survive sign out and still read back', () async {
    // After a cold start the store hands lists back as List<Object?>, not List<String>.
    SharedPreferences.setMockInitialValues({
      'uid': 'user-123',
      deletedAccountUidsKey: <Object?>['dead-a', 'dead-b']
    });
    await SharedPreferencesUtil.init();

    await clearPreferencesForSignOut();

    expect(await readDeletedAccountUids(), ['dead-a', 'dead-b']);
    expect((await SharedPreferences.getInstance()).getString('uid'), isNull);
  });

  test('the keep-list holds no credentials', () {
    for (final key in kPreferencesKeptOnSignOut) {
      expect(key.toLowerCase(), isNot(contains('token')));
      expect(key.toLowerCase(), isNot(contains('password')));
      expect(key, isNot('uid'));
    }
  });
}
