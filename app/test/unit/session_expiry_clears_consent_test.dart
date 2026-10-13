import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

// Regression test for #20774: Session expiry keeps AI consent and onboarding,
// so the next account to sign in skips both.
// When a session expires, clearUserDisplayCache() must reset aiConsentGiven,
// onboardingCompleted, and permissionsCompleted so a subsequent account is
// prompted for AI consent and guided through onboarding.

final class _TestTokenGateway implements AuthTokenGateway {
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'user-expired');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'uid': 'user-expired',
      'authToken': 'expired-token',
      'aiConsentGiven': true,
      'onboardingCompleted': true,
      'permissionsCompleted': true,
    });
    await SharedPreferencesUtil.init();
  });

  test('session expiry clears aiConsentGiven, onboardingCompleted, and permissionsCompleted', () async {
    final prefs = SharedPreferencesUtil();
    expect(prefs.aiConsentGiven, isTrue);
    expect(prefs.onboardingCompleted, isTrue);
    expect(prefs.permissionsCompleted, isTrue);

    final gateway = _TestTokenGateway();
    final authService = AuthService.forTesting(
      tokenGateway: gateway,
      prepareSiriSignOut: () async {},
    );

    // Trigger session expiry (e.g. token refresh failed or missingToken)
    await authService.expireSession(
      const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken),
    );

    // After session expiration, user display cache and consent/onboarding flags must be reset
    expect(prefs.uid, isEmpty);
    expect(prefs.authToken, isEmpty);
    expect(prefs.aiConsentGiven, isFalse, reason: 'New account must see AI consent screen');
    expect(prefs.onboardingCompleted, isFalse, reason: 'New account must not skip onboarding');
    expect(prefs.permissionsCompleted, isFalse);
    expect(gateway.signOutCalls, 1);
  });
}
