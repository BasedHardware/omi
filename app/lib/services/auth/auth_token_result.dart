sealed class AuthTokenResult {
  const AuthTokenResult();

  String? get tokenOrNull => switch (this) {
        AuthTokenSuccess(:final token) => token,
        _ => null,
      };
}

final class AuthTokenSuccess extends AuthTokenResult {
  const AuthTokenSuccess({required this.token, required this.expirationTime});

  final String token;
  final DateTime? expirationTime;
}

final class AuthTokenTransientFailure extends AuthTokenResult {
  const AuthTokenTransientFailure({required this.failureClass, this.code});

  final String failureClass;
  final String? code;
}

final class AuthTokenMissingUser extends AuthTokenResult {
  const AuthTokenMissingUser();
}

final class AuthTokenMissingToken extends AuthTokenResult {
  const AuthTokenMissingToken();
}

final class AuthTokenTerminalFailure extends AuthTokenResult {
  const AuthTokenTerminalFailure({required this.code});

  final String code;
}

enum AuthSessionExpirationReason {
  missingUser,
  missingToken,
  terminalTokenFailure,
  backendRejectedRefreshedToken,
  accountDeleted
}

final class AuthSessionExpiredEvent {
  const AuthSessionExpiredEvent({required this.reason, this.code});

  final AuthSessionExpirationReason reason;
  final String? code;
}

final class AuthUserSnapshot {
  const AuthUserSnapshot({required this.uid, this.email, this.displayName});

  final String uid;
  final String? email;
  final String? displayName;
}

final class RefreshedAuthToken {
  const RefreshedAuthToken({required this.token, required this.expirationTime});

  final String? token;
  final DateTime? expirationTime;
}

abstract interface class AuthTokenGateway {
  AuthUserSnapshot? get currentUser;

  Future<RefreshedAuthToken?> forceRefresh();

  Future<void> signOut();
}

typedef AuthRefreshDelay = Future<void> Function(Duration duration);
typedef AuthTelemetryRecorder = void Function(String eventName, Map<String, dynamic> properties);
typedef AuthTelemetryContextProvider = Map<String, dynamic> Function();
