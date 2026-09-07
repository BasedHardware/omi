import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/services/auth/local_emulator_auth.dart';

void main() {
  test('local emulator sign-in hold is 5 seconds, not Flutter default long-press', () {
    expect(kLocalEmulatorSignInHoldDuration, const Duration(seconds: 5));
  });

  test('local emulator sign-in is only enabled on the Auth-emulator profile', () {
    expect(localEmulatorSignInEnabled(AppEnvironmentProfile.localDev), isTrue);
    expect(localEmulatorSignInEnabled(AppEnvironmentProfile.localProd), isFalse);
    expect(localEmulatorSignInEnabled(AppEnvironmentProfile.mobileBeta), isFalse);
    expect(localEmulatorSignInEnabled(AppEnvironmentProfile.production), isFalse);
  });

  test('alice credentials match the harness seed and local-emulator runbook', () {
    expect(LocalEmulatorAuthUser.uid, 'alice');
    expect(LocalEmulatorAuthUser.email, 'alice@local.omi.invalid');
    expect(LocalEmulatorAuthUser.password, 'alice-local-password-030');
  });

  test('local walkthrough flags drop reused Alice onboarding so sign-in does not jump home', () async {
    SharedPreferences.setMockInitialValues({
      'onboardingCompleted': true,
      'aiConsentGiven': true,
      'permissionsCompleted': true,
      'hasSetPrimaryLanguage': true,
      'foundOmiSource': 'google',
    });
    await SharedPreferencesUtil.init();

    clearLocalOnboardingWalkthroughFlags();

    expect(SharedPreferencesUtil().onboardingCompleted, isFalse);
    expect(SharedPreferencesUtil().aiConsentGiven, isFalse);
    expect(SharedPreferencesUtil().permissionsCompleted, isFalse);
    expect(SharedPreferencesUtil().hasSetPrimaryLanguage, isFalse);
    expect(SharedPreferencesUtil().foundOmiSource, isEmpty);
  });
}
