import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('migrateAuthTokenFromPrefs moves legacy prefs token into secure storage once', () async {
    SharedPreferences.setMockInitialValues({
      'authToken': 'legacy-session-token',
      'tokenExpirationTime': 42,
      'uid': 'user-1',
    });
    FlutterSecureStorage.setMockInitialValues({});

    const secure = FlutterSecureStorage();
    await SharedPreferencesUtil.init(secureStorage: secure);

    expect(SharedPreferencesUtil().authToken, 'legacy-session-token');
    expect(await secure.read(key: 'authToken'), 'legacy-session-token');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('authToken'), isFalse);
    expect(prefs.getBool('authTokenSecureMigrated'), isTrue);
    expect(prefs.getString('nativeAuthToken'), 'legacy-session-token');
    // Non-secret expiry stays in SharedPreferences.
    expect(SharedPreferencesUtil().tokenExpirationTime, 42);
    expect(SharedPreferencesUtil().uid, 'user-1');

    // Second init must not wipe the secure token or re-read a prefs copy.
    await prefs.setString('authToken', 'should-be-ignored');
    await SharedPreferencesUtil.init(secureStorage: secure);
    expect(SharedPreferencesUtil().authToken, 'legacy-session-token');
    expect(await secure.read(key: 'authToken'), 'legacy-session-token');
    expect(prefs.containsKey('authToken'), isFalse);
  });

  test('migrateAuthTokenFromPrefs does not overwrite an existing secure token', () async {
    SharedPreferences.setMockInitialValues({'authToken': 'stale-prefs-token'});
    FlutterSecureStorage.setMockInitialValues({'authToken': 'secure-token'});

    const secure = FlutterSecureStorage();
    await SharedPreferencesUtil.init(secureStorage: secure);

    expect(SharedPreferencesUtil().authToken, 'secure-token');
    expect(await secure.read(key: 'authToken'), 'secure-token');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('authToken'), isFalse);
    expect(prefs.getBool('authTokenSecureMigrated'), isTrue);
  });

  test('authToken setter writes secure storage and clear removes it', () async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    const secure = FlutterSecureStorage();
    await SharedPreferencesUtil.init(secureStorage: secure);

    SharedPreferencesUtil().authToken = 'fresh-token';
    // Allow the fire-and-forget write to complete.
    await Future<void>.delayed(Duration.zero);
    expect(await secure.read(key: 'authToken'), 'fresh-token');

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('authToken'), isFalse);
    expect(prefs.getString('nativeAuthToken'), 'fresh-token');

    await SharedPreferencesUtil().clear();
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(await secure.read(key: 'authToken'), isNull);
  });

  test('init under flutter_test migrates prefs token without a plugin channel', () async {
    SharedPreferences.setMockInitialValues({'authToken': 'test-fallback-token'});
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().authToken, 'test-fallback-token');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('authToken'), isFalse);
    expect(prefs.getBool('authTokenSecureMigrated'), isTrue);
  });
}
