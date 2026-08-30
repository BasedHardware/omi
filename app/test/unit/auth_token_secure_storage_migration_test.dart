import 'dart:math';

import 'package:flutter/services.dart';
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
    await SharedPreferencesUtil.init(secureStorage: secure, mirrorNativeAuthToken: true);

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
    await SharedPreferencesUtil.init(secureStorage: secure, mirrorNativeAuthToken: true);
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
    await SharedPreferencesUtil.init(secureStorage: secure, mirrorNativeAuthToken: true);

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

  test('the plaintext mirror is cleared where no native reader consumes it', () async {
    SharedPreferences.setMockInitialValues({
      'nativeAuthToken': 'copy-left-by-an-earlier-build',
      'authTokenSecureMigrated': true,
    });
    FlutterSecureStorage.setMockInitialValues({'authToken': 'secure-token'});

    const secure = FlutterSecureStorage();
    await SharedPreferencesUtil.init(secureStorage: secure, mirrorNativeAuthToken: false);

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('nativeAuthToken'), isFalse);

    SharedPreferencesUtil().authToken = 'rotated-token';
    await pumpEventQueue();

    expect(prefs.containsKey('nativeAuthToken'), isFalse);
    expect(await secure.read(key: 'authToken'), 'rotated-token');
  });

  test('a duplicate-item keychain write deletes the stale entry and rewrites', () async {
    SharedPreferences.setMockInitialValues({});
    final storage = _FakeSecureStorage()..duplicateWrites = 1;
    await SharedPreferencesUtil.init(secureStorage: storage);

    SharedPreferencesUtil().authToken = 'fresh-token';
    await pumpEventQueue();

    expect(storage.store['authToken'], 'fresh-token');
    expect(storage.calls, containsAllInOrder(<String>['write', 'delete', 'write']));
    expect(SharedPreferencesUtil().authToken, 'fresh-token');
  });

  test('overlapping token writes never run concurrently in the keychain', () async {
    SharedPreferences.setMockInitialValues({});
    final storage = _FakeSecureStorage();
    await SharedPreferencesUtil.init(secureStorage: storage);

    SharedPreferencesUtil().authToken = 'token-a';
    SharedPreferencesUtil().authToken = 'token-b';
    await pumpEventQueue();

    expect(storage.maxConcurrent, 1);
    expect(storage.store['authToken'], 'token-b');
  });

  test('migration keeps the prefs token when the keychain rejects the write', () async {
    SharedPreferences.setMockInitialValues({'authToken': 'legacy-session-token'});
    final storage = _FakeSecureStorage()..writeError = _keychainError(-25308, 'Interaction is not allowed.');
    await SharedPreferencesUtil.init(secureStorage: storage);

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('authToken'), 'legacy-session-token');
    expect(prefs.getBool('authTokenSecureMigrated'), isNull);
    expect(SharedPreferencesUtil().authToken, 'legacy-session-token');
  });
}

PlatformException _keychainError(int status, String message) {
  return PlatformException(
    code: 'Unexpected security result code',
    message: 'Code: $status, Message: $message',
    details: status,
  );
}

class _FakeSecureStorage extends FlutterSecureStorage {
  _FakeSecureStorage();

  final Map<String, String> store = <String, String>{};
  final List<String> calls = <String>[];

  int duplicateWrites = 0;
  PlatformException? writeError;

  int maxConcurrent = 0;
  int _inFlight = 0;

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    _inFlight++;
    maxConcurrent = max(maxConcurrent, _inFlight);
    try {
      await Future<void>.delayed(Duration.zero);
      calls.add('write');
      if (writeError != null) throw writeError!;
      if (duplicateWrites > 0) {
        duplicateWrites--;
        throw _keychainError(-25299, 'The specified item already exists in the keychain.');
      }
      store[key] = value!;
    } finally {
      _inFlight--;
    }
  }

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    calls.add('read');
    return store[key];
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    calls.add('delete');
    store.remove(key);
  }
}
