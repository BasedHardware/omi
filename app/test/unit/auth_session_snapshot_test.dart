import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/user_data_export.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    Env.init(_TestEnvFields());
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await PlatformManager.initializeServices();
  });

  test('snapshot rejects A-to-B-to-A session churn', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});

    final snapshot = service.captureSessionSnapshot();
    expect(snapshot, isNotNull);
    expect(snapshot!.ownerUid, 'user-a');
    expect(service.isSessionSnapshotCurrent(snapshot), isTrue);

    gateway.user = const AuthUserSnapshot(uid: 'user-b');
    service.handleAuthUserChanged('user-b');
    expect(service.isSessionSnapshotCurrent(snapshot), isFalse);

    gateway.user = const AuthUserSnapshot(uid: 'user-a');
    service.handleAuthUserChanged('user-a');
    expect(service.isSessionSnapshotCurrent(snapshot), isFalse);
  });

  test('snapshot capture returns null for missing, anonymous, or mismatched sessions', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});

    expect(service.captureSessionSnapshot(expectedUid: 'someone-else'), isNull);

    gateway.user = const AuthUserSnapshot(uid: 'anon', isAnonymous: true);
    expect(service.captureSessionSnapshot(), isNull);

    gateway.user = null;
    expect(service.captureSessionSnapshot(), isNull);
  });

  test('raw request sends nothing when the session churns during token acquisition', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    var sends = 0;

    gateway.onRefresh = () {
      gateway.user = const AuthUserSnapshot(uid: 'user-b');
      service.handleAuthUserChanged('user-b');
      gateway.user = const AuthUserSnapshot(uid: 'user-a');
      service.handleAuthUserChanged('user-a');
    };
    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];

    final response = await makeRawApiCall(
      url: 'https://unit-test.invalid/v1/users/export?stream=true',
      method: 'GET',
      sessionSnapshot: snapshot,
      authService: service,
      sendStreaming: (request) async {
        sends++;
        return http.StreamedResponse(const Stream.empty(), 200);
      },
    );

    expect(response.statusCode, 401);
    expect(sends, 0);
    expect(gateway.signOutCalls, 0);
  });

  test('snapshot-bound 401 refresh succeeds and replays exactly once', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    var sends = 0;

    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];

    final response = await makeRawApiCall(
      url: 'https://unit-test.invalid/v1/users/export?stream=true',
      method: 'GET',
      sessionSnapshot: snapshot,
      authService: service,
      sendStreaming: (request) async {
        sends++;
        return http.StreamedResponse(const Stream.empty(), sends == 1 ? 401 : 200);
      },
    );

    expect(response.statusCode, 200);
    expect(sends, 2);
    expect(gateway.refreshCalls, greaterThanOrEqualTo(2));
    expect(gateway.signOutCalls, 0);
  });

  test('401 refresh under a churned session never replays and never expires the new session', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    var sends = 0;

    gateway.onRefresh = () {
      if (gateway.refreshCalls == 1) return;
      gateway.user = const AuthUserSnapshot(uid: 'user-b');
      service.handleAuthUserChanged('user-b');
      gateway.user = const AuthUserSnapshot(uid: 'user-a');
      service.handleAuthUserChanged('user-a');
    };
    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];

    final response = await makeRawApiCall(
      url: 'https://unit-test.invalid/v1/users/export?stream=true',
      method: 'GET',
      sessionSnapshot: snapshot,
      authService: service,
      sendStreaming: (request) async {
        sends++;
        return http.StreamedResponse(const Stream.empty(), sends == 1 ? 401 : 200);
      },
    );

    expect(response.statusCode, 401);
    expect(sends, 1);
    expect(gateway.signOutCalls, 0);
  });

  group('exportUserDataToFile session binding', () {
    late Directory tempDir;
    late String filePath;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('export-snapshot-test');
      filePath = '${tempDir.path}/omi-export.json';
    });

    tearDown(() async {
      if (await tempDir.exists()) await tempDir.delete(recursive: true);
    });

    http.StreamedResponse okBody() => http.StreamedResponse(
          Stream.value(utf8.encode('{"ok": true,\n  "export_complete": true\n}\n')),
          200,
          headers: {'content-type': 'application/json'},
        );

    test('renames the completed file while the snapshot stays current', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final snapshot = service.captureSessionSnapshot()!;

      final result = await exportUserDataToFile(
        filePath,
        authorizationSnapshot: snapshot,
        authService: service,
        request: () async => okBody(),
      );

      expect(result, filePath);
      expect(await File(filePath).exists(), isTrue);
    });

    test('A-to-B-to-A churn during download leaves no promoted file', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final snapshot = service.captureSessionSnapshot()!;

      final result = await exportUserDataToFile(
        filePath,
        authorizationSnapshot: snapshot,
        authService: service,
        request: () async {
          gateway.user = const AuthUserSnapshot(uid: 'user-b');
          service.handleAuthUserChanged('user-b');
          gateway.user = const AuthUserSnapshot(uid: 'user-a');
          service.handleAuthUserChanged('user-a');
          return okBody();
        },
      );

      expect(result, isNull);
      expect(await File(filePath).exists(), isFalse);
    });
  });
}

final class _Gateway implements AuthTokenGateway {
  _Gateway({required this.user});

  AuthUserSnapshot? user;
  List<RefreshedAuthToken?> results = const [];
  void Function()? onRefresh;
  int refreshCalls = 0;
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    refreshCalls++;
    onRefresh?.call();
    if (results.isNotEmpty) {
      final index = refreshCalls <= results.length ? refreshCalls - 1 : results.length - 1;
      return results[index];
    }
    return null;
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://unit-test.invalid/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
