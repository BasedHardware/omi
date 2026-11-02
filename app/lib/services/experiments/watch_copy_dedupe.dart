import 'package:omi/utils/analytics/analytics_manager.dart';

/// Cataloged destructive-dedupe kill switch. Unknown values keep the audio.
class WatchCopyDedupePolicy {
  static const killSwitchFlag = 'watch_copy_dedupe_off';
  static Future<bool> keepRecoveryCopies() => AnalyticsManager().isFeatureEnabled(killSwitchFlag, fallback: true);
}
