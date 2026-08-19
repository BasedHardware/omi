import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

/// A forced token refresh that never returns must not hang its caller.
///
/// `backend/http/shared.dart` refreshes on the way into *every* authenticated
/// request, so an unbounded stall in the refresh silently freezes all backend
/// traffic app-wide: no error, no snackbar, nothing to report. Measured on
/// iPhone 17 Pro / iOS 27.0 against a Firebase Auth emulator on a non-loopback
/// host, `forceRefresh()` never returned at all — the app completed a clean run
/// of onboarding requests on its cached token and then went permanently silent.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a refresh that never returns resolves as a transient failure', () async {
    final gateway = _StallingGateway(neverCompletes: true);
    final service = _service(gateway, timeout: const Duration(milliseconds: 30));

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenTransientFailure>());
    expect(
      (result as AuthTokenTransientFailure).failureClass,
      'refresh_timeout',
      reason: 'a stall must be distinguishable in telemetry from a refresh that actually failed',
    );
  });

  test('a stalled refresh is still retried, not abandoned after one timeout', () async {
    final gateway = _StallingGateway(neverCompletes: true);
    final service = _service(gateway, timeout: const Duration(milliseconds: 20));

    await service.refreshIdToken();

    // A timeout is classified transient precisely so the existing retry loop
    // still applies; a stall on one attempt may not be a stall on the next.
    expect(gateway.refreshCalls, greaterThan(1));
  });

  test('a slow but successful refresh inside the budget still succeeds', () async {
    // The bound must not turn a merely slow network into a failed session.
    final gateway = _StallingGateway(latency: const Duration(milliseconds: 10));
    final service = _service(gateway, timeout: const Duration(seconds: 5));

    final result = await service.refreshIdToken();

    expect(result, isA<AuthTokenSuccess>());
    expect(result.tokenOrNull, 'slow-token');
  });

  test('the caller gets a result rather than waiting forever', () async {
    // The user-visible property: refreshIdToken() completes. Everything above is
    // about *which* result; this is about it returning at all.
    final gateway = _StallingGateway(neverCompletes: true);
    final service = _service(gateway, timeout: const Duration(milliseconds: 20));

    await expectLater(
      service.refreshIdToken().timeout(const Duration(seconds: 5)),
      completes,
    );
  });
}

AuthService _service(_StallingGateway gateway, {required Duration timeout}) => AuthService.forTesting(
      tokenGateway: gateway,
      refreshDelay: (_) async {},
      refreshAttemptTimeout: timeout,
    );

final class _StallingGateway implements AuthTokenGateway {
  _StallingGateway({this.neverCompletes = false, this.latency});

  final bool neverCompletes;
  final Duration? latency;
  int refreshCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(
        uid: 'user-1',
        email: 'person@example.com',
        displayName: 'Person Example',
      );

  @override
  Future<RefreshedAuthToken?> forceRefresh() {
    refreshCalls++;
    if (neverCompletes) return Completer<RefreshedAuthToken?>().future;
    return Future<RefreshedAuthToken?>.delayed(
      latency ?? Duration.zero,
      () => RefreshedAuthToken(token: 'slow-token', expirationTime: DateTime.now()),
    );
  }

  @override
  Future<void> signOut() async {}
}
