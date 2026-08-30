import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/sockets/live_listen_auth_recovery.dart';

void main() {
  test('4001 refresh success requests an immediate reconnect', () async {
    final expired = <AuthSessionExpiredEvent>[];

    final disposition = await recoverLiveListenAuthClose(
      closeCode: 4001,
      refreshToken: () async => AuthTokenSuccess(token: 'fresh', expirationTime: DateTime.utc(2027)),
      expireSession: (event) async => expired.add(event),
    );

    expect(disposition, LiveListenAuthDisposition.reconnectNow);
    expect(expired, isEmpty);
  });

  test('4001 transient refresh failure leaves bounded retry armed', () async {
    final disposition = await recoverLiveListenAuthClose(
      closeCode: 4001,
      refreshToken: () async => const AuthTokenTransientFailure(failureClass: 'offline'),
      expireSession: (_) async {},
    );

    expect(disposition, LiveListenAuthDisposition.retryLater);
  });

  test('4001 terminal refresh expires the session instead of looping', () async {
    final expired = <AuthSessionExpiredEvent>[];

    final disposition = await recoverLiveListenAuthClose(
      closeCode: 4001,
      refreshToken: () async => const AuthTokenTerminalFailure(code: 'user-token-expired'),
      expireSession: (event) async => expired.add(event),
    );

    expect(disposition, LiveListenAuthDisposition.sessionExpired);
    expect(expired.single.reason, AuthSessionExpirationReason.terminalTokenFailure);
    expect(expired.single.code, 'user-token-expired');
  });

  test('4001 missing user expires the session instead of retrying', () async {
    final expired = <AuthSessionExpiredEvent>[];

    final disposition = await recoverLiveListenAuthClose(
      closeCode: 4001,
      refreshToken: () async => const AuthTokenMissingUser(),
      expireSession: (event) async => expired.add(event),
    );

    expect(disposition, LiveListenAuthDisposition.sessionExpired);
    expect(expired.single.reason, AuthSessionExpirationReason.missingUser);
  });

  test('4004 expires immediately without attempting refresh', () async {
    var refreshCalls = 0;
    final expired = <AuthSessionExpiredEvent>[];

    final disposition = await recoverLiveListenAuthClose(
      closeCode: 4004,
      refreshToken: () async {
        refreshCalls++;
        return const AuthTokenTransientFailure(failureClass: 'unexpected');
      },
      expireSession: (event) async => expired.add(event),
    );

    expect(disposition, LiveListenAuthDisposition.sessionExpired);
    expect(refreshCalls, 0);
    expect(expired.single.reason, AuthSessionExpirationReason.backendRejectedRefreshedToken);
  });

  test('ordinary closes stay on the transport reconnect path', () async {
    final disposition = await recoverLiveListenAuthClose(
      closeCode: 1006,
      refreshToken: () async => const AuthTokenTransientFailure(failureClass: 'unused'),
      expireSession: (_) async {},
    );

    expect(disposition, LiveListenAuthDisposition.notAuthRelated);
  });
}
