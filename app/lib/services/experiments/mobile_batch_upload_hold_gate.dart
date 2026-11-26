import 'package:omi/utils/analytics/analytics_manager.dart';

/// Missing or disabled answers keep the original immediate upload behavior.
abstract final class MobileBatchUploadHoldGate {
  static const enabledFlag = 'mobile-batch-upload-hold';

  static bool enabled() => AnalyticsManager().isBooleanFeatureEnabledCached(enabledFlag);

  static Future<void> refresh() async {
    await AnalyticsManager().reloadFeatureFlags();
  }
}
