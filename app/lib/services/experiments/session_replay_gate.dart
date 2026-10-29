import 'package:flutter/foundation.dart';

/// Who may be recorded by mobile session replay (`SessionReplay` in
/// `lib/utils/analytics/session_replay.dart` acts on it). Lifecycle: rollout; owner: nik; default off.
abstract final class SessionReplayGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'mobile-session-replay';

  /// Debug builds only: `--dart-define=OMI_SESSION_REPLAY=1` reads the flag as on. A dart-define
  /// cannot be flipped on a built artifact and `kDebugMode` excludes every store build.
  static const _debugOverride = String.fromEnvironment('OMI_SESSION_REPLAY');

  static bool get debugOverrideActive => kDebugMode && _debugOverride == '1';

  /// Product analytics on, the flag resolved true for the settled identity, and not App Review.
  /// [appReview] is true when the server hides subscription UI, the app's App Review switch (it also
  /// covers BYOK and reviewer accounts), and null until the subscription loads. App Review installs
  /// carry a sandbox receipt, so a [sandboxInstall] (TestFlight or App Review) waits for the answer.
  static bool allowed({
    required bool trackingEnabled,
    required bool flagEnabled,
    required bool? appReview,
    required bool sandboxInstall,
  }) =>
      trackingEnabled && flagEnabled && appReview != true && (appReview == false || !sandboxInstall);
}
