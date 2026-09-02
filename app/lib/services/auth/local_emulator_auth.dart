import 'package:omi/backend/preferences.dart';
import 'package:omi/env/environment_profile.dart';

/// Synthetic Auth-emulator principal used by desktop `make desktop-run-local`
/// and the mobile `local_dev` sign-in long-press (Apple/Google).
///
/// Must stay in lockstep with `scripts/dev-harness/dev_harness/memory_scenarios.py`
/// (`_user`) and `backend/docs/runbooks/local-emulator-manual-qa.md`. These are
/// not secrets — they exist only in the Firebase Auth emulator.
class LocalEmulatorAuthUser {
  static const uid = 'alice';
  static const email = 'alice@local.omi.invalid';
  static const password = 'alice-local-password-030';
}

/// How long Apple/Google must be held in `local_dev` before Alice signs in.
/// Passed as [LongPressGestureRecognizer.duration] so Flutter's default
/// ~500ms long-press cannot accept the arena.
const Duration kLocalEmulatorSignInHoldDuration = Duration(seconds: 5);

/// Google/Apple OAuth is not configured on the local harness. Email/password
/// against the Auth emulator is the supported mobile local-dev path.
bool localEmulatorSignInEnabled(AppEnvironmentProfile profile) => profile.usesFirebaseAuthEmulator;

/// Alice is a reused harness principal whose server doc often already says
/// onboarding is done. Local walkthroughs must not inherit that, or sign-in
/// jumps straight to home.
void clearLocalOnboardingWalkthroughFlags() {
  SharedPreferencesUtil().onboardingCompleted = false;
  SharedPreferencesUtil().aiConsentGiven = false;
  SharedPreferencesUtil().permissionsCompleted = false;
  SharedPreferencesUtil().hasSetPrimaryLanguage = false;
  SharedPreferencesUtil().foundOmiSource = '';
}
