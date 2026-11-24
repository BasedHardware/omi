import 'package:flutter/foundation.dart';

import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Rollout gate for a shorter phone batch file. A batch file is sealed two
/// seconds after speech stops or when it reaches its length cap; the cap is
/// what bounds how long continuous speech waits on the phone before upload.
///
/// Evaluated from the PostHog flag `mobile-batch-file-cap-15s`, registered in
/// `config/feature-flags.yaml`. Fail-closed: no analytics identity, a failed
/// or late read, or a missing flag keeps the 60-second cap. Read once per app
/// launch, so a flip takes effect on the next launch.
/// Lifecycle: rollout; default off.
abstract final class MobileBatchFileCapGate {
  static const enabledFlag = 'mobile-batch-file-cap-15s';
  static const shortFileSeconds = 15;

  /// Debug-build override: `--dart-define=OMI_MOBILE_BATCH_FILE_CAP_15S=true`.
  static const _debugForce = bool.fromEnvironment('OMI_MOBILE_BATCH_FILE_CAP_15S');

  static bool get debugOverrideActive => kDebugMode && _debugForce;

  static Future<int> maxFileSeconds({Future<bool> Function(String key)? readFlag}) async {
    if (debugOverrideActive) return shortFileSeconds;
    try {
      final enabled =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag).timeout(const Duration(seconds: 2));
      return enabled ? shortFileSeconds : MobileBatchBuffer.defaultMaxFileSeconds;
    } catch (_) {
      return MobileBatchBuffer.defaultMaxFileSeconds;
    }
  }
}
