import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(SharedPreferencesUtil.resetAuthTokenStorageForTesting);

  test('migrates the legacy token and removes plaintext storage', () async {
    final storage = _FakeAuthTokenStorage();
    SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
    SharedPreferences.setMockInitialValues({'authToken': 'legacy-token'});

    await SharedPreferencesUtil.init();

    final preferences = await SharedPreferences.getInstance();
    expect(SharedPreferencesUtil().authToken, 'legacy-token');
    expect(storage.value, 'legacy-token');
    expect(preferences.containsKey('authToken'), isFalse);
  });

  test('a failed migration does not fail startup and retries on the next init', () async {
    final storage = _FakeAuthTokenStorage(failWrites: 3);
    SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
    SharedPreferences.setMockInitialValues({'authToken': 'legacy-token'});

    await SharedPreferencesUtil.init();

    final preferences = await SharedPreferences.getInstance();
    expect(SharedPreferencesUtil().authToken, 'legacy-token');
    expect(preferences.containsKey('authToken'), isTrue);

    storage.failWrites = 0;
    await SharedPreferencesUtil.init();

    expect(storage.value, 'legacy-token');
    expect(preferences.containsKey('authToken'), isFalse);
    expect(storage.writeCalls, 4);
  });

  test('secure token startup retries legacy plaintext cleanup', () async {
    final storage = _FakeAuthTokenStorage()..value = 'secure-token';
    SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
    SharedPreferences.setMockInitialValues({'authToken': 'legacy-token'});

    await SharedPreferencesUtil.init();

    final preferences = await SharedPreferences.getInstance();
    expect(SharedPreferencesUtil().authToken, 'secure-token');
    expect(preferences.containsKey('authToken'), isFalse);
    expect(storage.writeCalls, 0);
  });

  test('mirrors the secure token for Android background audio and removes the mirror on sign out', () async {
    final previousPlatform = debugDefaultTargetPlatformOverride;
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    try {
      final storage = _FakeAuthTokenStorage();
      SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      await SharedPreferencesUtil().persistAuthToken('android-token');

      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getString('nativeAuthToken'), 'android-token');

      await SharedPreferencesUtil().persistAuthToken('');

      expect(preferences.containsKey('nativeAuthToken'), isFalse);
    } finally {
      debugDefaultTargetPlatformOverride = previousPlatform;
    }
  });

  test('refresh succeeds with an in-memory token when secure persistence fails', () async {
    final storage = _FakeAuthTokenStorage(failWrites: 3);
    SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    storage.failWrites = 3;

    final service = AuthService.forTesting(tokenGateway: _FakeAuthTokenGateway());
    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenSuccess>());
    expect(SharedPreferencesUtil().authToken, 'fresh-token');
  });

  test('sign out completes when secure deletion fails and retries after restart', () async {
    final storage = _FakeAuthTokenStorage();
    SharedPreferencesUtil.setAuthTokenStorageForTesting(storage, retryDelay: (_) async {});
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().persistAuthToken('cached-token');
    storage.failDeletes = 3;

    final gateway = _FakeAuthTokenGateway();
    final service = AuthService.forTesting(tokenGateway: gateway);
    await service.signOut();

    final preferences = await SharedPreferences.getInstance();
    expect(gateway.signOutCalls, 1);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(preferences.getBool('authTokenDeletePending'), isTrue);

    storage.failDeletes = 0;
    await SharedPreferencesUtil.init();

    expect(storage.value, isNull);
    expect(preferences.containsKey('authTokenDeletePending'), isFalse);
  });
}

final class _FakeAuthTokenStorage implements AuthTokenStorage {
  _FakeAuthTokenStorage({this.failWrites = 0});

  String? value;
  int failWrites;
  int failDeletes = 0;
  int writeCalls = 0;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async {
    writeCalls++;
    if (failWrites > 0) {
      failWrites--;
      throw StateError('write failed');
    }
    this.value = value;
  }

  @override
  Future<void> delete() async {
    if (failDeletes > 0) {
      failDeletes--;
      throw StateError('delete failed');
    }
    value = null;
  }
}

final class _FakeAuthTokenGateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'user-1');
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      const RefreshedAuthToken(token: 'fresh-token', expirationTime: null);

  @override
  Future<void> signOut() async {
    signOutCalls++;
    user = null;
  }
}
