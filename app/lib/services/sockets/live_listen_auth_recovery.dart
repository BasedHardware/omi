import 'package:omi/services/auth/auth_token_result.dart';

enum LiveListenAuthDisposition { reconnectNow, retryLater, sessionExpired, notAuthRelated }

Future<LiveListenAuthDisposition> recoverLiveListenAuthClose({
  required int? closeCode,
  required Future<AuthTokenResult> Function() refreshToken,
  required Future<void> Function(AuthSessionExpiredEvent event) expireSession,
}) async {
  if (closeCode == 4004) {
    await expireSession(
      const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.backendRejectedRefreshedToken),
    );
    return LiveListenAuthDisposition.sessionExpired;
  }

  if (closeCode != 4001) return LiveListenAuthDisposition.notAuthRelated;

  final result = await refreshToken();
  return switch (result) {
    AuthTokenSuccess() => LiveListenAuthDisposition.reconnectNow,
    AuthTokenTransientFailure() => LiveListenAuthDisposition.retryLater,
    AuthTokenMissingUser() => await _expireSession(AuthSessionExpirationReason.missingUser, expireSession),
    AuthTokenMissingToken() => await _expireSession(AuthSessionExpirationReason.missingToken, expireSession),
    AuthTokenTerminalFailure(:final code) => await _expireSession(
        AuthSessionExpirationReason.terminalTokenFailure,
        expireSession,
        code: code,
      ),
  };
}

Future<LiveListenAuthDisposition> _expireSession(
    AuthSessionExpirationReason reason, Future<void> Function(AuthSessionExpiredEvent event) expireSession,
    {String? code}) async {
  await expireSession(AuthSessionExpiredEvent(reason: reason, code: code));
  return LiveListenAuthDisposition.sessionExpired;
}
