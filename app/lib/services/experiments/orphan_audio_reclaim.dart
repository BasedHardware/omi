import 'package:omi/utils/analytics/analytics_manager.dart';

/// Destructive policy: only a resolved false permits reclaim. Unknown retains.
class OrphanAudioReclaimPolicy {
  static const killSwitchFlag = 'orphan_audio_reclaim_off';
  static Future<bool> isOff() => AnalyticsManager().isFeatureEnabled(killSwitchFlag, fallback: true);
}
