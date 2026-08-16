import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('401 refreshes once, replays once, and records recovery', () async {
    final gateway = _Gateway(results: [_token('fresh')]);
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);
    var replayCalls = 0;

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async {
        replayCalls++;
        return http.Response('ok', 200);
      },
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 200);
    expect(gateway.refreshCalls, 1);
    expect(replayCalls, 1);
    expect(gateway.signOutCalls, 0);
    expect(_request401Events(telemetry).single.properties, containsPair('recovered', true));
    expect(_request401Events(telemetry).single.properties, containsPair('outcome', 'refresh_succeeded'));
  });

  test('transient refresh failure does not replay or sign out', () async {
    final gateway = _Gateway(error: StateError('offline'));
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);
    var replayCalls = 0;

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async {
        replayCalls++;
        return http.Response('', 200);
      },
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(gateway.refreshCalls, 3);
    expect(replayCalls, 0);
    expect(gateway.signOutCalls, 0);
    expect(_request401Events(telemetry).single.properties, containsPair('outcome', 'refresh_transient_failure'));
  });

  test('null-token refresh is exhausted before terminal session expiration', () async {
    final gateway = _Gateway(results: [_token(null), _token(null), _token(null)]);
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async => http.Response('', 200),
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(gateway.refreshCalls, 3);
    expect(gateway.signOutCallsDuringRefresh, everyElement(0));
    expect(gateway.signOutCalls, 1, reason: 'session expires only after the bounded null-token budget is exhausted');
    expect(_request401Events(telemetry).single.properties, containsPair('outcome', 'missing_token'));
  });

  test('second 401 after successful refresh expires session exactly once', () async {
    final gateway = _Gateway(results: [_token('fresh')]);
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);
    final sessionEvents = <AuthSessionExpiredEvent>[];
    service.sessionExpiredEvents.listen(sessionEvents.add);

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async => http.Response('', 401),
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(gateway.signOutCalls, 1);
    expect(sessionEvents.single.reason, AuthSessionExpirationReason.backendRejectedRefreshedToken);
    expect(_request401Events(telemetry).single.properties, {
      'recovered': false,
      'outcome': 'backend_rejected_refreshed_token',
      'platform': 'ios',
      'app_version': '1.2.3+456',
      'release_channel': 'testflight',
    });
  });

  test('streaming 401 responses are drained before replay and expiration', () async {
    final gateway = _Gateway(results: [_token('fresh')]);
    final service = _service(gateway, <_Event>[]);
    final drainedStatuses = <int>[];

    final response = await refreshAndReplayAfter401(
      firstResponse: http.StreamedResponse(Stream.value(<int>[1, 2]), 401),
      statusCode: (value) => value.statusCode,
      disposeUnauthorizedResponse: (value) async {
        await value.stream.drain<void>();
        drainedStatuses.add(value.statusCode);
      },
      replay: () async => http.StreamedResponse(Stream.value(<int>[3, 4]), 401),
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(drainedStatuses, [401, 401]);
    expect(gateway.signOutCalls, 1);
  });

  test('terminal refresh failure expires session without replay', () async {
    final gateway = _Gateway(error: FirebaseAuthException(code: 'user-token-expired'));
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);
    var replayCalls = 0;

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async {
        replayCalls++;
        return http.Response('', 200);
      },
      expireTerminalSession: true,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(gateway.refreshCalls, 1);
    expect(replayCalls, 0);
    expect(gateway.signOutCalls, 1);
    expect(_request401Events(telemetry).single.properties, containsPair('outcome', 'terminal_token_failure'));
  });

  test('failed replay records an unrecovered 401 outcome before rethrowing', () async {
    final gateway = _Gateway(results: [_token('fresh')]);
    final telemetry = <_Event>[];
    final service = _service(gateway, telemetry);

    await expectLater(
      refreshAndReplayAfter401(
        firstResponse: http.Response('', 401),
        statusCode: (value) => value.statusCode,
        replay: () async => throw TimeoutException('offline'),
        expireTerminalSession: true,
        authService: service,
      ),
      throwsA(isA<TimeoutException>()),
    );

    expect(_request401Events(telemetry).single.properties, containsPair('recovered', false));
    expect(_request401Events(telemetry).single.properties, containsPair('outcome', 'replay_failed'));
    expect(gateway.signOutCalls, 0);
  });

  test('signOutOn401 false preserves graceful endpoint behavior on second 401', () async {
    final gateway = _Gateway(results: [_token('fresh')]);
    final service = _service(gateway, <_Event>[]);

    final response = await refreshAndReplayAfter401(
      firstResponse: http.Response('', 401),
      statusCode: (value) => value.statusCode,
      replay: () async => http.Response('', 401),
      expireTerminalSession: false,
      authService: service,
    );

    expect(response.statusCode, 401);
    expect(gateway.signOutCalls, 0);
  });

  test('concurrent backend-rejected refreshed tokens share refresh and terminal signout', () async {
    final refreshCompleter = Completer<RefreshedAuthToken?>();
    final gateway = _Gateway(refreshCompleter: refreshCompleter);
    final service = _service(gateway, <_Event>[]);

    Future<http.Response> execute() => refreshAndReplayAfter401(
          firstResponse: http.Response('', 401),
          statusCode: (value) => value.statusCode,
          replay: () async => http.Response('', 401),
          expireTerminalSession: true,
          authService: service,
        );

    final first = execute();
    final second = execute();
    refreshCompleter.complete(_token('fresh'));
    await Future.wait([first, second]);

    expect(gateway.refreshCalls, 1);
    expect(gateway.signOutCalls, 1);
  });
}

List<_Event> _request401Events(List<_Event> events) =>
    events.where((event) => event.name == 'authenticated_request_401').toList();

RefreshedAuthToken _token(String? token) => RefreshedAuthToken(token: token, expirationTime: DateTime.now());

AuthService _service(_Gateway gateway, List<_Event> telemetry) => AuthService.forTesting(
      tokenGateway: gateway,
      refreshDelay: (_) async {},
      recordTelemetry: (name, properties) => telemetry.add(_Event(name, properties)),
      telemetryContextProvider: () => const {
        'platform': 'ios',
        'app_version': '1.2.3+456',
        'release_channel': 'testflight',
      },
    );

final class _Gateway implements AuthTokenGateway {
  _Gateway({this.results = const [], this.error, this.refreshCompleter});

  final List<RefreshedAuthToken?> results;
  final Object? error;
  final Completer<RefreshedAuthToken?>? refreshCompleter;
  int refreshCalls = 0;
  int signOutCalls = 0;
  final List<int> signOutCallsDuringRefresh = [];

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'user-1');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    refreshCalls++;
    signOutCallsDuringRefresh.add(signOutCalls);
    if (error != null) throw error!;
    if (refreshCompleter != null) return refreshCompleter!.future;
    final index = refreshCalls <= results.length ? refreshCalls - 1 : results.length - 1;
    return results[index];
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

final class _Event {
  const _Event(this.name, this.properties);

  final String name;
  final Map<String, dynamic> properties;
}
