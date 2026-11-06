import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/api/apps.dart' as apps;
import 'package:omi/providers/auth_provider.dart';
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

  for (final status in [401, 403]) {
    test('late $status after referral timeout and account switch cannot affect new owner', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final snapshot = service.captureSessionSnapshot()!;
      gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];
      final sent = Completer<void>();
      final reply = Completer<http.StreamedResponse>();
      var sends = 0;
      final pending = makeRawApiCall(
        url: 'https://unit-test.invalid/v1/users/me/referral',
        method: 'GET',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (_) {
          sends++;
          sent.complete();
          return reply.future;
        },
      );
      await sent.future;
      await expectLater(pending.timeout(const Duration(milliseconds: 1)), throwsA(isA<TimeoutException>()));
      gateway.user = const AuthUserSnapshot(uid: 'user-b');
      service.handleAuthUserChanged('user-b');
      final refreshes = gateway.refreshCalls;
      reply.complete(http.StreamedResponse(
          Stream.value(utf8.encode('{"detail":{"code":"account_deletion_in_progress","status":"pending"}}')), status));
      final response = await pending;
      expect(response.statusCode, 401);
      expect(sends, 1);
      expect(gateway.refreshCalls, refreshes);
      expect(gateway.signOutCalls, 0);
      expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
    });
  }

  test('deletion 403 body arriving after switch does not expire the new account', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];
    final body = StreamController<List<int>>();
    final reading = Completer<void>();
    final response = makeRawApiCall(
      url: 'https://unit-test.invalid/v1/users/me/referral',
      method: 'GET',
      sessionSnapshot: snapshot,
      authService: service,
      sendStreaming: (_) async => http.StreamedResponse(body.stream, 403),
    );
    body.onListen = () => reading.complete();
    await reading.future;
    gateway.user = const AuthUserSnapshot(uid: 'user-b');
    service.handleAuthUserChanged('user-b');
    body.add(utf8.encode('{"detail":{"code":"account_deletion_in_progress","status":"pending"}}'));
    await body.close();
    expect((await response).statusCode, 401);
    expect(gateway.signOutCalls, 0);
  });

  for (final status in [401, 403]) {
    test('$status expiration admitted for A cannot sign out B during Siri await', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
      final entered = Completer<void>();
      final release = Completer<void>();
      final service = AuthService.forTesting(
        tokenGateway: gateway,
        refreshDelay: (_) async {},
        prepareSiriSignOut: () {
          entered.complete();
          return release.future;
        },
      );
      final snapshot = service.captureSessionSnapshot()!;
      gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now()), null];
      final pending = makeRawApiCall(
        url: 'https://unit-test.invalid/v1/users/me/referral',
        method: 'GET',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (_) async => http.StreamedResponse(
            Stream.value(utf8.encode('{"detail":{"code":"account_deletion_in_progress","status":"pending"}}')), status),
      );
      await entered.future;
      gateway.user = const AuthUserSnapshot(uid: 'user-b');
      service.markAuthenticatedUser('user-b');
      release.complete();
      await pending;
      expect(gateway.signOutCalls, 0);
      expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
    });
  }

  for (final status in [401, 403]) {
    test('$status pending gateway sign-out completes before replacement sign-in', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
      final entered = Completer<void>();
      final release = Completer<void>();
      gateway.onSignOut = () async {
        entered.complete();
        await release.future;
        // Model the global Firebase side effect at completion, not at call time.
        gateway.user = null;
      };
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final snapshot = service.captureSessionSnapshot()!;
      gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now()), null];
      final pending = makeRawApiCall(
        url: 'https://unit-test.invalid/v1/users/me/referral',
        method: 'GET',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (_) async => http.StreamedResponse(
            Stream.value(utf8.encode('{"detail":{"code":"account_deletion_in_progress","status":"pending"}}')), status),
      );
      await entered.future;
      var replacementStarted = false;
      final replacement = service.runAccountMutation(() async {
        replacementStarted = true;
        gateway.user = const AuthUserSnapshot(uid: 'user-b');
        service.markAuthenticatedUser('user-b');
      });
      await Future<void>.delayed(Duration.zero);
      expect(replacementStarted, isFalse);
      expect(gateway.user!.uid, 'user-a');
      release.complete();
      await Future.wait([pending, replacement]);
      expect(replacementStarted, isTrue);
      expect(gateway.signOutCalls, 1);
      expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
    });
  }

  test('a failed account mutation does not block the next sign-in', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway);
    await expectLater(service.runAccountMutation(() async {
      throw StateError('Failed');
    }), throwsStateError);
    await service.runAccountMutation(() async {
      gateway.user = const AuthUserSnapshot(uid: 'user-b');
      service.markAuthenticatedUser('user-b');
    });
    expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
  });

  test('stale 200 cancels a large stalled body and bounds stalled cancellation', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];
    final releaseCancel = Completer<void>();
    var cancelled = false;
    var bytesConsumed = 0;
    late StreamController<List<int>> body;
    body = StreamController<List<int>>(
      onListen: () => body.add(List<int>.filled(4 * 1024 * 1024, 0)),
      onCancel: () {
        cancelled = true;
        return releaseCancel.future;
      },
    );
    try {
      final response = await makeRawApiCall(
        url: 'https://unit-test.invalid/v1/users/me/referral',
        method: 'GET',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (_) async {
          gateway.user = const AuthUserSnapshot(uid: 'user-b');
          service.markAuthenticatedUser('user-b');
          return http.StreamedResponse(body.stream.map((chunk) {
            bytesConsumed += chunk.length;
            return chunk;
          }), 200);
        },
      ).timeout(const Duration(seconds: 5));
      expect(response.statusCode, 401);
      expect(cancelled, isTrue);
      expect(bytesConsumed, 0);
      expect(gateway.refreshCalls, 1);
      expect(gateway.signOutCalls, 0);
      expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
    } finally {
      releaseCancel.complete();
      await body.close();
    }
  });

  test('stale replayed 200 cancels a large stalled body and bounds stalled cancellation', () async {
    final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'user-a'));
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final snapshot = service.captureSessionSnapshot()!;
    gateway.results = [RefreshedAuthToken(token: 'token-a', expirationTime: DateTime.now())];
    final releaseCancel = Completer<void>();
    var cancelled = false;
    var bytesConsumed = 0;
    var sends = 0;
    var refreshesAtSwitch = 0;
    late StreamController<List<int>> body;
    body = StreamController<List<int>>(
      onListen: () => body.add(List<int>.filled(4 * 1024 * 1024, 0)),
      onCancel: () {
        cancelled = true;
        return releaseCancel.future;
      },
    );
    try {
      final response = await makeRawApiCall(
        url: 'https://unit-test.invalid/v1/users/me/referral',
        method: 'GET',
        sessionSnapshot: snapshot,
        authService: service,
        sendStreaming: (_) async {
          sends++;
          if (sends == 1) return http.StreamedResponse(const Stream.empty(), 401);
          refreshesAtSwitch = gateway.refreshCalls;
          gateway.user = const AuthUserSnapshot(uid: 'user-b');
          service.markAuthenticatedUser('user-b');
          return http.StreamedResponse(body.stream.map((chunk) {
            bytesConsumed += chunk.length;
            return chunk;
          }), 200);
        },
      ).timeout(const Duration(seconds: 5));
      expect(response.statusCode, 401);
      expect(cancelled, isTrue);
      expect(bytesConsumed, 0);
      expect(sends, 2);
      expect(gateway.refreshCalls, refreshesAtSwitch);
      expect(gateway.signOutCalls, 0);
      expect(service.captureSessionSnapshot()!.ownerUid, 'user-b');
    } finally {
      releaseCancel.complete();
      await body.close();
    }
  });

  for (final returnToDestination in [false, true]) {
    test('collision migration rejects delayed 401 after destination churn (ABA=$returnToDestination)', () async {
      final gateway = _Gateway(user: const AuthUserSnapshot(uid: 'destination-b'))
        ..results = [
          RefreshedAuthToken(token: 'token-b', expirationTime: DateTime.now().add(const Duration(hours: 1)))
        ];
      final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
      final destination = service.captureSessionSnapshot()!;
      final pendingResponse = Completer<http.StreamedResponse>();
      final dispatched = Completer<void>();
      final headers = <String?>[];
      final pending = completeProviderLinkAndMigrate(
        linkProvider: () async => ProviderLinkResult(
          destinationUid: destination.ownerUid,
          destinationSession: destination,
          anonymousSourceMigration: const AnonymousSourceMigration(uid: 'anonymous-a', token: 'proof-a'),
        ),
        migrate: (sourceUid, sourceToken, session) => apps.migrateAppOwnerId(
          sourceUid,
          sourceToken,
          destination: session,
          authService: service,
          sendStreaming: (request) {
            headers.add(request.headers['Authorization']);
            expect(jsonDecode(request.body), {'source_token': 'proof-a'});
            dispatched.complete();
            return pendingResponse.future;
          },
        ),
      );
      await dispatched.future;
      gateway.user = const AuthUserSnapshot(uid: 'replacement-c');
      service.handleAuthUserChanged('replacement-c');
      if (returnToDestination) {
        gateway.user = const AuthUserSnapshot(uid: 'destination-b');
        service.handleAuthUserChanged('destination-b');
      }
      final refreshesBefore = gateway.refreshCalls;
      pendingResponse.complete(http.StreamedResponse(const Stream.empty(), 401));
      await pending;
      expect(headers, hasLength(1));
      expect(gateway.refreshCalls, refreshesBefore);
      expect(gateway.signOutCalls, 0);
      expect(gateway.user!.uid, returnToDestination ? 'destination-b' : 'replacement-c');
    });
  }

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
  Future<void> Function()? onSignOut;
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
    await onSignOut?.call();
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
