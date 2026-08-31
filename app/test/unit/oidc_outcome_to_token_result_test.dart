import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/oidc_auth_service.dart';

/// Hermetic coverage for the OIDC-outcome -> AuthTokenResult mapping used by the
/// 401-recovery / getIdToken paths (cubic review PR 10887, shared.dart:310 +
/// oidc_auth_service.dart:222). The mapping must preserve the outcome's
/// definitive/transient classification: a definitive refresh failure surfaces a
/// TERMINAL result so the dead session is expired and re-login is forced, while a
/// transient miss keeps the session for a retry. Before the fix every failed OIDC
/// refresh mapped to a transient failure, so a revoked refresh token left the
/// session alive and every request replayed the same rejected token.
void main() {
  const authToken = 'access-token';
  const expiryMs = 1893456000000; // fixed epoch ms

  test('ok outcome with a stored token -> AuthTokenSuccess carrying token + expiry', () {
    final result = AuthService.oidcOutcomeToTokenResult(
      const OidcLoginOutcome.success('user-1'),
      authToken: authToken,
      tokenExpirationMs: expiryMs,
    );
    expect(result, isA<AuthTokenSuccess>());
    expect((result as AuthTokenSuccess).token, authToken);
    expect(result.expirationTime, DateTime.fromMillisecondsSinceEpoch(expiryMs));
  });

  test('definitive failure (revoked refresh) -> terminal AuthTokenMissingToken so the session expires', () {
    final result = AuthService.oidcOutcomeToTokenResult(
      const OidcLoginOutcome.failure('invalid_grant', transient: false),
      authToken: authToken, // a stale token is still cached, but the refresh is definitively dead
      tokenExpirationMs: expiryMs,
    );
    expect(result, isA<AuthTokenMissingToken>());
  });

  test('transient failure (network) -> AuthTokenTransientFailure so the session is kept for a retry', () {
    final result = AuthService.oidcOutcomeToTokenResult(
      const OidcLoginOutcome.failure('Connection refused', transient: true),
      authToken: authToken,
      tokenExpirationMs: expiryMs,
    );
    expect(result, isA<AuthTokenTransientFailure>());
    expect((result as AuthTokenTransientFailure).failureClass, 'oidc_refresh_failed');
  });

  test('contradictory ok-with-no-token -> transient, never expires the session', () {
    final result = AuthService.oidcOutcomeToTokenResult(
      const OidcLoginOutcome.success('user-1'),
      authToken: '',
      tokenExpirationMs: 0,
    );
    expect(result, isA<AuthTokenTransientFailure>());
    expect((result as AuthTokenTransientFailure).failureClass, 'oidc_refresh_ok_no_token');
  });
}
