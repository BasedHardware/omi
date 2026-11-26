// Own the non-destructive orphan recovery kill switch. Only true disables
// recovery; upload and deletion policy remain with the custody ledger.
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Recovery is non-destructive and paced by the ledger and server. Unknown
/// values keep recovery ON; only an explicit true stops new passes.
class OrphanAudioRecoveryPolicy {
  static const killSwitchFlag = 'orphan_audio_recovery_off';
  static Future<bool> isOff() => AnalyticsManager().isFeatureEnabled(killSwitchFlag, fallback: false);
}
